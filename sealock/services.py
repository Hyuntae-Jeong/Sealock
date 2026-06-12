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
from .history import build_timeline, summarize

CONFIG_LOCAL = "config.local.json"


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
        return ["member_AUD", "order_AUD", "product_AUD"]
    # Filter in Python (case-insensitive) rather than via SQL LIKE — avoids
    # backslash-escaping / collation / NO_BACKSLASH_ESCAPES pitfalls so both
    # `_AUD` and `_aud` are reliably found whatever the server config.
    tables = introspect.list_tables(state.db)
    return [t for t in tables if t.lower().endswith("_aud")]


def preview_table(state: AppState, table: str) -> dict:
    if state.demo:
        return demo.preview()
    return introspect.describe_table(state.db, table)


def confirm_table(state: AppState, table: str, identifier: str | None) -> dict:
    cls = demo.preview() if state.demo else introspect.describe_table(state.db, table)
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
