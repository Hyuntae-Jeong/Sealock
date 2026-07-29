"""Application services — UI-agnostic glue between the widgets and the DB.

Each function either returns plain data or raises (DatabaseError / ValueError);
the UI runs them on a worker thread and shows the message on failure. Demo mode
short-circuits to synthetic data so the whole flow works without a database.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from . import demo, introspect
from .db import Database
from .history import (
    build_changeset_timeline,
    build_timeline,
    format_ts,
    summarize,
    summarize_changeset,
)

CONFIG_LOCAL = "config.local.json"

# All-records view: how many of the newest revisions to load per page. Caps the
# cost on large entity tables; "더 보기" pages further back from there.
FULL_HISTORY_PAGE = 200

# Revision timestamps are rendered in KST (see history.format_ts), so a picked
# date means the KST day — the filter bounds are built in the same zone.
_KST = _dt.timezone(_dt.timedelta(hours=9))

# Open ends of a one-sided date range.
_DATE_MIN = _dt.date(1970, 1, 1)
_DATE_MAX = _dt.date(2999, 12, 31)


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
def _as_date(value):
    """Accept a date / datetime / 'YYYY-MM-DD' string; None means "open end"."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"날짜 형식이 올바르지 않습니다: {value} (YYYY-MM-DD)") from exc


def _norm_range(date_from, date_to):
    """Validate a picked range; returns (from, to) dates or None when unbounded."""
    d_from, d_to = _as_date(date_from), _as_date(date_to)
    if d_from is None and d_to is None:
        return None
    d_from, d_to = d_from or _DATE_MIN, d_to or _DATE_MAX
    if d_from > d_to:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return d_from, d_to


def _epoch_bounds(rng, scale: int) -> tuple[int, int]:
    """Half-open [start, end) epoch bounds in KST; ``scale`` 1000 = milliseconds."""
    d_from, d_to = rng
    start = _dt.datetime.combine(d_from, _dt.time.min, _KST)
    end = _dt.datetime.combine(d_to + _dt.timedelta(days=1), _dt.time.min, _KST)
    return int(start.timestamp() * scale), int(end.timestamp() * scale)


def _ts_scale(db: Database, ri: dict) -> int:
    """1000 when a numeric REVINFO timestamp stores milliseconds, else 1.

    Uses the same >= 1e12 rule as history.format_ts so filtering and rendering
    agree. Probed once per session and cached on the revinfo dict.
    """
    if "ts_scale" not in ri:
        q = introspect.quote_ident
        row = db.query_one(f"SELECT MAX({q(ri['ts_column'])}) AS m FROM {q(ri['table'])}")
        try:
            biggest = int((row or {}).get("m") or 0)
        except (TypeError, ValueError):
            biggest = 0
        ri["ts_scale"] = 1000 if biggest >= 1_000_000_000_000 else 1
    return ri["ts_scale"]


def _sql_bounds(db: Database, ctx: dict, rng):
    """Range bounds typed to match the REVINFO timestamp column, or None.

    DATETIME/TIMESTAMP columns are stored and displayed as wall-clock, so they
    compare against naive datetimes; numeric columns compare against epochs.
    """
    if rng is None:
        return None
    ri = ctx.get("revinfo") or {}
    if not (ri.get("found") and ri.get("ts_column")):
        raise ValueError(
            "리비전 시각(REVINFO) 정보를 찾을 수 없어 기간을 지정할 수 없습니다."
        )
    d_from, d_to = rng
    if any(t in (ri.get("ts_type") or "").lower() for t in ("datetime", "timestamp", "date")):
        return (
            _dt.datetime.combine(d_from, _dt.time.min),
            _dt.datetime.combine(d_to + _dt.timedelta(days=1), _dt.time.min),
        )
    return _epoch_bounds(rng, _ts_scale(db, ri))


def supports_date_range(state: AppState) -> bool:
    """Whether the confirmed table can be filtered by date (needs REVINFO time)."""
    ri = (state.context or {}).get("revinfo") or {}
    return bool(ri.get("found") and ri.get("ts_column"))


def count_full_history(state: AppState, date_from=None, date_to=None) -> dict:
    """Tally what a full-history load would return, without building it.

    Shown before the first load so a wide table's size is visible up front.
    """
    ctx = state.context
    if not ctx:
        raise ValueError("먼저 테이블을 확정해 주세요.")
    rng = _norm_range(date_from, date_to)

    if state.demo:
        return demo.full_history_count(_epoch_bounds(rng, 1000) if rng else None)
    return _count_all_rows(state.db, ctx, _sql_bounds(state.db, ctx, rng))


def get_full_history(
    state: AppState,
    before_rev=None,
    limit_revs: int = FULL_HISTORY_PAGE,
    date_from=None,
    date_to=None,
) -> dict:
    ctx = state.context
    if not ctx:
        raise ValueError("먼저 테이블을 확정해 주세요.")
    rng = _norm_range(date_from, date_to)

    if state.demo:
        data = demo.full_history(before_rev, _epoch_bounds(rng, 1000) if rng else None)
    else:
        bounds = _sql_bounds(state.db, ctx, rng)
        data = _fetch_all_rows(state.db, ctx, before_rev, limit_revs, bounds)

    timeline = build_changeset_timeline(data["rows"], ctx, data.get("baseline"))
    return {
        "table": ctx.get("table"),
        "timeline": timeline,
        "summary": summarize_changeset(timeline, ctx.get("table")),
        "min_rev": data.get("min_rev"),
        "has_more": bool(data.get("has_more")),
        "empty": not data["rows"],
    }


def _count_all_rows(db: Database, ctx: dict, bounds) -> dict:
    """One aggregate pass over the audit table: revisions, rows and time span."""
    q = introspect.quote_ident
    table, rev = ctx["table"], ctx["rev_column"]
    ri = ctx.get("revinfo") or {}

    span, join, where, params = "", "", "", []
    if ri.get("found") and ri.get("ts_column"):
        ts = f"r.{q(ri['ts_column'])}"
        # Inner join only when filtering — otherwise a revision missing from
        # REVINFO would silently drop out of the tally.
        join = (f" {'JOIN' if bounds else 'LEFT JOIN'} {q(ri['table'])} r "
                f"ON a.{q(rev)} = r.{q(ri['rev_column'])}")
        span = f", MIN({ts}) AS mn, MAX({ts}) AS mx"
        if bounds:
            where = f" WHERE {ts} >= %s AND {ts} < %s"
            params = list(bounds)

    row = db.query_one(
        f"SELECT COUNT(*) AS n, COUNT(DISTINCT a.{q(rev)}) AS revs{span} "
        f"FROM {q(table)} a{join}{where}",
        params,
    ) or {}
    return {
        "revisions": int(row.get("revs") or 0),
        "rows": int(row.get("n") or 0),
        "first_ts": format_ts(row.get("mn")),
        "last_ts": format_ts(row.get("mx")),
    }


def _fetch_all_rows(db: Database, ctx: dict, before_rev, limit_revs: int, bounds=None) -> dict:
    """Load the newest ``limit_revs`` revisions of the whole table (older than
    ``before_rev`` when paging), plus each record's pre-window baseline so the
    oldest shown diff still resolves a correct "before" value.

    ``bounds`` is a half-open [start, end) pair on the REVINFO timestamp: paging
    then walks back through that period only. The baseline stays unbounded on
    purpose — the value a period *starts* from was set before the period began.
    """
    q = introspect.quote_ident
    table, rev = ctx["table"], ctx["rev_column"]
    idents = ctx.get("identifier_columns") or []
    ri = ctx.get("revinfo") or {}

    # Date filter: join REVINFO so only revisions committed inside the period
    # are considered — by the window, the rows, and the "더 보기" probe alike.
    rev_join, ts_cond, ts_params = "", "", []
    if bounds:
        ts = f"r.{q(ri['ts_column'])}"
        ts_cond = f"{ts} >= %s AND {ts} < %s"
        ts_params = list(bounds)
        rev_join = f" JOIN {q(ri['table'])} r ON a.{q(rev)} = r.{q(ri['rev_column'])}"

    # 1. Window = newest `limit_revs` distinct revisions (below before_rev if paging).
    conds, params = [], []
    if before_rev is not None:
        conds.append(f"a.{q(rev)} < %s")
        params.append(before_rev)
    if ts_cond:
        conds.append(ts_cond)
        params.extend(ts_params)
    where = f" WHERE {' AND '.join(conds)}" if conds else ""
    params.append(int(limit_revs))
    rev_rows = db.query(
        f"SELECT DISTINCT a.{q(rev)} AS r FROM {q(table)} a{rev_join}{where} "
        f"ORDER BY a.{q(rev)} DESC LIMIT %s",
        params,
    )
    if not rev_rows:
        return {"rows": [], "baseline": [], "min_rev": None, "has_more": False}
    window = [r["r"] for r in rev_rows]
    lo, hi = min(window), max(window)

    # 2. Every audit row inside the window, ordered for per-record snapshotting.
    #    The REVINFO join is already there for __revts, so the period condition
    #    rides along on the same alias.
    select, join = "a.*", ""
    if ri.get("found") and ri.get("ts_column"):
        select += f", r.{q(ri['ts_column'])} AS __revts"
        join = (f" {'JOIN' if bounds else 'LEFT JOIN'} {q(ri['table'])} r "
                f"ON a.{q(rev)} = r.{q(ri['rev_column'])}")
    id_order = "".join(f"a.{q(c)}, " for c in idents)
    rows = db.query(
        f"SELECT {select} FROM {q(table)} a{join} "
        f"WHERE a.{q(rev)} BETWEEN %s AND %s{f' AND {ts_cond}' if ts_cond else ''} "
        f"ORDER BY {id_order}a.{q(rev)} ASC",
        [lo, hi] + ts_params,
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

    more = db.query_one(
        f"SELECT 1 AS x FROM {q(table)} a{rev_join} "
        f"WHERE a.{q(rev)} < %s{f' AND {ts_cond}' if ts_cond else ''} LIMIT 1",
        [lo] + ts_params,
    )
    return {"rows": rows, "baseline": baseline, "min_rev": lo, "has_more": bool(more)}
