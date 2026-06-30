"""Turn ordered Envers audit rows into a human-readable change timeline.

The audit table only stores the *new* value at each revision, so to show a
"before -> after" diff we walk the revisions oldest-first, keep a running
snapshot of the last-known value of every column, and read the "before"
value out of that snapshot.

Whether a column changed in a MOD revision is decided by its <col>_MOD flag
when present; otherwise we fall back to comparing against the snapshot.
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal

# Korea Standard Time (UTC+9, no DST) — epoch timestamps are rendered in KST.
_KST = _dt.timezone(_dt.timedelta(hours=9))

REVTYPE_META = {
    0: {"label": "CREATED", "ko": "생성", "kind": "create"},
    1: {"label": "MODIFIED", "ko": "수정", "kind": "update"},
    2: {"label": "DELETED", "ko": "삭제", "kind": "delete"},
}


def _truthy(v) -> bool:
    """Interpret a _MOD flag value (could be int, bool, b'\\x01', '1')."""
    if v is None:
        return False
    if isinstance(v, (bytes, bytearray)):
        return v not in (b"", b"\x00")
    if isinstance(v, str):
        return v.strip() not in ("", "0", "false", "False")
    return bool(v)


def _display(v):
    """Make a value JSON-friendly for the UI; keep None as None (rendered ∅)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        # BIT / binary columns arrive as bytes; show printable text as-is,
        # otherwise render numerically (BIT(1) -> "0"/"1") or as hex.
        try:
            s = v.decode("utf-8")
            if s == "" or s.isprintable():
                return s
        except UnicodeDecodeError:
            pass
        if len(v) <= 8:
            return str(int.from_bytes(v, "big"))
        return v.hex()
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat(sep=" ") if isinstance(v, _dt.datetime) else v.isoformat()
    return str(v)


def _format_ts(value):
    """Render a revision timestamp in KST.

    Accepts an epoch value (milliseconds or seconds) from a REVINFO bigint, or a
    datetime/date from a DATETIME/TIMESTAMP revision column. 0 or negative is
    treated as "missing" (returns None) so a join miss never shows 1970-01-01.
    """
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, _dt.date):
        return value.isoformat()
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    secs = n / 1000 if n >= 1_000_000_000_000 else n  # >= 1e12 -> milliseconds
    try:
        return _dt.datetime.fromtimestamp(secs, _KST).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return None


def _change(col, old, new, kind):
    return {
        "column": col,
        "label": col,
        "old": _display(old),
        "new": _display(new),
        "kind": kind,
    }


def _flag_change(label):
    """A change with no stored old/new value — only that it changed.

    Used for _MOD flags that have no value column in the audit table (audited
    collections / relations), so we can report the change but not a diff.
    """
    return {"column": label, "label": label, "old": None, "new": None, "kind": "flag"}


def _coerce_revtype(value) -> int:
    """Normalise a REVTYPE cell to 0/1/2, defaulting to MOD (1)."""
    try:
        return int(value) if value is not None else 1
    except (TypeError, ValueError):
        return 1


def _diff_row(row, rtype, data_cols, orphan_flags, state) -> list[dict]:
    """Compute one revision's change rows, mutating ``state`` (the running
    last-known snapshot of this record) as we go.

    Shared by the single-record timeline and the all-records changeset view.
    """
    changes: list[dict] = []

    if rtype == 0:  # ADD — show the full initial snapshot
        for dc in data_cols:
            val = row.get(dc["name"])
            if val is not None:
                changes.append(_change(dc["name"], None, val, "create"))
            state[dc["name"]] = val
        for of in orphan_flags:
            if _truthy(row.get(of["name"])):
                changes.append(_flag_change(of["label"]))

    elif rtype == 2:  # DEL — record vanished; carry snapshot untouched
        pass

    else:  # MOD — diff changed columns against the running snapshot
        for dc in data_cols:
            val = row.get(dc["name"])
            flag = dc.get("mod_flag")
            if flag and flag in row:
                changed = _truthy(row.get(flag))
            else:
                changed = val != state.get(dc["name"])
            if changed:
                changes.append(_change(dc["name"], state.get(dc["name"]), val, "update"))
            state[dc["name"]] = val
        for of in orphan_flags:
            if _truthy(row.get(of["name"])):
                changes.append(_flag_change(of["label"]))

    return changes


def build_timeline(rows: list[dict], classification: dict) -> list[dict]:
    """Build an ordered list of revision nodes from raw audit rows.

    ``rows`` must be ordered by REV ascending and may carry a synthetic
    ``__revts`` key (epoch millis) from the REVINFO join.
    """
    rev_col = classification["rev_column"]
    revtype_col = classification["revtype_column"]
    data_cols = classification["data_columns"]
    orphan_flags = classification.get("orphan_mod_flags", [])

    state: dict = {}
    timeline: list[dict] = []

    for row in rows:
        rev = row.get(rev_col) if rev_col else None
        rtype = _coerce_revtype(row.get(revtype_col) if revtype_col else 1)
        meta = REVTYPE_META.get(rtype, REVTYPE_META[1])
        ts_ms = row.get("__revts")

        changes = _diff_row(row, rtype, data_cols, orphan_flags, state)

        timeline.append(
            {
                "rev": rev,
                "revtype": rtype,
                "revtype_label": meta["label"],
                "revtype_ko": meta["ko"],
                "kind": meta["kind"],
                "deleted": rtype == 2,
                "timestamp_ms": ts_ms,
                "timestamp": _format_ts(ts_ms),
                "changes": changes,
                "snapshot": {k: _display(v) for k, v in state.items()},
            }
        )

    return timeline


def build_changeset_timeline(
    rows: list[dict], classification: dict, baseline_rows: list[dict] | None = None
) -> list[dict]:
    """Build an all-records, revision-grouped timeline (newest rev first).

    Used for tables browsed without an identifier (e.g. ``name``-keyed config
    tables): every revision becomes one node whose ``records`` list holds the
    per-record diffs that happened in that revision.

    ``rows`` must be ordered by identifier, then REV ascending, so each record's
    running snapshot is built in order. ``baseline_rows`` (each record's last
    state *before* the loaded window) seed those snapshots so the oldest shown
    diff still resolves a correct "before" value at the window edge.
    """
    revtype_col = classification["revtype_column"]
    data_cols = classification["data_columns"]
    orphan_flags = classification.get("orphan_mod_flags", [])
    ident_cols = classification.get("identifier_columns") or []

    def ident_key(row):
        return tuple(row.get(c) for c in ident_cols)

    def ident_label(row):
        return " · ".join(f"{c} = {_display(row.get(c))}" for c in ident_cols)

    # Seed each record's snapshot from its last-known state before the window.
    states: dict = {}
    for br in baseline_rows or []:
        states[ident_key(br)] = {dc["name"]: br.get(dc["name"]) for dc in data_cols}

    nodes: dict = {}  # rev -> node (insertion order is identifier-then-rev)
    for row in rows:
        rev = row.get(classification["rev_column"])
        rtype = _coerce_revtype(row.get(revtype_col) if revtype_col else 1)
        meta = REVTYPE_META.get(rtype, REVTYPE_META[1])
        state = states.setdefault(ident_key(row), {})

        changes = _diff_row(row, rtype, data_cols, orphan_flags, state)

        node = nodes.get(rev)
        if node is None:
            ts_ms = row.get("__revts")
            node = nodes[rev] = {
                "rev": rev,
                "timestamp_ms": ts_ms,
                "timestamp": _format_ts(ts_ms),
                "records": [],
                "_kinds": set(),
            }
        node["_kinds"].add(meta["kind"])
        node["records"].append(
            {
                "identifier": ident_label(row),
                "revtype": rtype,
                "revtype_label": meta["label"],
                "revtype_ko": meta["ko"],
                "kind": meta["kind"],
                "deleted": rtype == 2,
                "changes": changes,
            }
        )

    timeline = []
    for rev in sorted(nodes, key=lambda r: (r is None, r), reverse=True):
        node = nodes[rev]
        kinds = node.pop("_kinds")
        # Rev-level kind drives the rail colour; mixed revisions read as "update".
        node["kind"] = next(iter(kinds)) if len(kinds) == 1 else "update"
        node["record_count"] = len(node["records"])
        node["change_count"] = sum(len(r["changes"]) for r in node["records"])
        timeline.append(node)
    return timeline


def summarize(timeline: list[dict], identifier_column, identifier_value) -> dict:
    times = [n["timestamp"] for n in timeline if n.get("timestamp")]
    total_changes = sum(len(n["changes"]) for n in timeline)
    return {
        "identifier_column": identifier_column,
        "identifier_value": identifier_value,
        "revisions": len(timeline),
        "total_changes": total_changes,
        "first_ts": times[0] if times else None,
        "last_ts": times[-1] if times else None,
    }


def summarize_changeset(timeline: list[dict], table) -> dict:
    """Roll up an all-records changeset timeline for the summary bar."""
    times = sorted(n["timestamp"] for n in timeline if n.get("timestamp"))
    records = {
        rec["identifier"] for n in timeline for rec in n.get("records", [])
    }
    return {
        "table": table,
        "revisions": len(timeline),
        "records": len(records),
        "total_changes": sum(n.get("change_count", 0) for n in timeline),
        "first_ts": times[0] if times else None,
        "last_ts": times[-1] if times else None,
    }
