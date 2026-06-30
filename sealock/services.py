"""Application services — UI-agnostic glue between the widgets and the DB.

Each function either returns plain data or raises (DatabaseError / ValueError);
the UI runs them on a worker thread and shows the message on failure. Demo mode
short-circuits to synthetic data so the whole flow works without a database.
"""
from __future__ import annotations

import json
import os

from . import demo, introspect
from .db import Database
from .history import (
    build_changeset_timeline,
    build_timeline,
    summarize,
    summarize_changeset,
)

CONFIG_LOCAL = "config.local.json"

# All-records view: how many of the newest revisions to load per page. Caps the
# cost on large entity tables; "더 보기" pages further back from there.
FULL_HISTORY_PAGE = 200


class AppState:
    """Session-wide state shared by all wizard pages."""

    def __init__(self) -> None:
        self.db = Database()
        self.context: dict | None = None  # confirmed table classification
        self.demo = False


# ── step 1: connection ──────────────────────────────────────────────────
def form_defaults() -> dict:
    """Pre-fill the login form from a git-ignored local config, if present."""
    if os.path.exists(CONFIG_LOCAL):
        try:
            with open(CONFIG_LOCAL, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            return {
                "host": d.get("host", "localhost"),
                "port": d.get("port", 3306),
                "user": d.get("user", ""),
                "password": d.get("password", ""),
                "database": d.get("database", ""),
            }
        except Exception:  # noqa: BLE001
            pass
    return {"host": "localhost", "port": 3306, "user": "", "password": "", "database": ""}


def test_and_connect(state: AppState, p: dict) -> str:
    """Open the persistent connection and return the server version string.

    Always performs a real connection — demo mode is reached only through the
    dedicated "샘플 데이터로 둘러보기" button, which bypasses this path entirely.
    """
    state.db.connect(p.get("host"), p.get("port"), p.get("user"), p.get("password"), p.get("database"))
    row = state.db.query_one("SELECT VERSION() AS v")
    return str((row or {}).get("v", "unknown"))


# ── step 2: table preview ───────────────────────────────────────────────
def list_aud_tables(state: AppState) -> list[str]:
    if state.demo:
        return ["member_AUD", demo.CONFIG_TABLE, "order_AUD", "product_AUD"]
    # Filter in Python (case-insensitive) rather than via SQL LIKE — avoids
    # backslash-escaping / collation / NO_BACKSLASH_ESCAPES pitfalls so both
    # `_AUD` and `_aud` are reliably found whatever the server config.
    tables = introspect.list_tables(state.db)
    return [t for t in tables if t.lower().endswith("_aud")]


def preview_table(state: AppState, table: str) -> dict:
    if state.demo:
        return demo.preview(table)
    return introspect.describe_table(state.db, table)


def confirm_table(state: AppState, table: str, identifier: str | None) -> dict:
    cls = demo.preview(table) if state.demo else introspect.describe_table(state.db, table)
    ident = identifier or cls.get("identifier_default")
    if not ident:
        raise ValueError("식별자(PK) 컬럼을 결정할 수 없습니다. 컬럼을 선택해 주세요.")
    cls["identifier_column"] = ident
    state.context = cls
    return cls


# ── step 3: history ─────────────────────────────────────────────────────
def get_history(state: AppState, id_value) -> dict:
    ctx = state.context
    if not ctx:
        raise ValueError("먼저 테이블을 확정해 주세요.")
    if id_value is None or str(id_value).strip() == "":
        raise ValueError("조회할 ID를 입력하세요.")

    if state.demo:
        rows = [] if str(id_value).strip() == "999" else demo.rows()
    else:
        rows = _fetch_rows(state.db, ctx, id_value)

    timeline = build_timeline(rows, ctx)
    return {
        "table": ctx.get("table"),
        "identifier": {"column": ctx["identifier_column"], "value": id_value},
        "timeline": timeline,
        "summary": summarize(timeline, ctx["identifier_column"], id_value),
        "empty": not rows,
    }


def _fetch_rows(db: Database, ctx: dict, id_value) -> list[dict]:
    q = introspect.quote_ident
    table, rev, ident = ctx["table"], ctx["rev_column"], ctx["identifier_column"]
    ri = ctx.get("revinfo") or {}

    select, join = "a.*", ""
    if ri.get("found") and ri.get("ts_column") and rev:
        select += f", r.{q(ri['ts_column'])} AS __revts"
        join = f" LEFT JOIN {q(ri['table'])} r ON a.{q(rev)} = r.{q(ri['rev_column'])}"
    order = f" ORDER BY a.{q(rev)} ASC" if rev else ""

    sql = f"SELECT {select} FROM {q(table)} a{join} WHERE a.{q(ident)} = %s{order}"
    return db.query(sql, [id_value])


# ── step 3 (id-less tables): whole-table revision timeline ───────────────
def get_full_history(state: AppState, before_rev=None, limit_revs: int = FULL_HISTORY_PAGE) -> dict:
    ctx = state.context
    if not ctx:
        raise ValueError("먼저 테이블을 확정해 주세요.")

    if state.demo:
        data = demo.full_history(before_rev)
    else:
        data = _fetch_all_rows(state.db, ctx, before_rev, limit_revs)

    timeline = build_changeset_timeline(data["rows"], ctx, data.get("baseline"))
    return {
        "table": ctx.get("table"),
        "timeline": timeline,
        "summary": summarize_changeset(timeline, ctx.get("table")),
        "min_rev": data.get("min_rev"),
        "has_more": bool(data.get("has_more")),
        "empty": not data["rows"],
    }


def _fetch_all_rows(db: Database, ctx: dict, before_rev, limit_revs: int) -> dict:
    """Load the newest ``limit_revs`` revisions of the whole table (older than
    ``before_rev`` when paging), plus each record's pre-window baseline so the
    oldest shown diff still resolves a correct "before" value."""
    q = introspect.quote_ident
    table, rev = ctx["table"], ctx["rev_column"]
    idents = ctx.get("identifier_columns") or []
    ri = ctx.get("revinfo") or {}

    # 1. Window = newest `limit_revs` distinct revisions (below before_rev if paging).
    where, params = "", []
    if before_rev is not None:
        where = f" WHERE a.{q(rev)} < %s"
        params.append(before_rev)
    params.append(int(limit_revs))
    rev_rows = db.query(
        f"SELECT DISTINCT a.{q(rev)} AS r FROM {q(table)} a{where} "
        f"ORDER BY a.{q(rev)} DESC LIMIT %s",
        params,
    )
    if not rev_rows:
        return {"rows": [], "baseline": [], "min_rev": None, "has_more": False}
    window = [r["r"] for r in rev_rows]
    lo, hi = min(window), max(window)

    # 2. Every audit row inside the window, ordered for per-record snapshotting.
    select, join = "a.*", ""
    if ri.get("found") and ri.get("ts_column"):
        select += f", r.{q(ri['ts_column'])} AS __revts"
        join = f" LEFT JOIN {q(ri['table'])} r ON a.{q(rev)} = r.{q(ri['rev_column'])}"
    id_order = "".join(f"a.{q(c)}, " for c in idents)
    rows = db.query(
        f"SELECT {select} FROM {q(table)} a{join} "
        f"WHERE a.{q(rev)} BETWEEN %s AND %s "
        f"ORDER BY {id_order}a.{q(rev)} ASC",
        [lo, hi],
    )

    # 3. Baseline: each record's last state strictly before the window edge.
    baseline = []
    if idents:
        idcols = ", ".join(q(c) for c in idents)
        match = " AND ".join(f"a.{q(c)} = b.{q(c)}" for c in idents)
        baseline = db.query(
            f"SELECT a.* FROM {q(table)} a "
            f"JOIN (SELECT {idcols}, MAX({q(rev)}) AS __mr FROM {q(table)} "
            f"      WHERE {q(rev)} < %s GROUP BY {idcols}) b "
            f"  ON {match} AND a.{q(rev)} = b.__mr",
            [lo],
        )

    more = db.query_one(f"SELECT 1 AS x FROM {q(table)} WHERE {q(rev)} < %s LIMIT 1", [lo])
    return {"rows": rows, "baseline": baseline, "min_rev": lo, "has_more": bool(more)}
