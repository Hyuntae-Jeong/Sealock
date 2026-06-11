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
        try:
            return v.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return v.hex()
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat(sep=" ") if isinstance(v, _dt.datetime) else v.isoformat()
    return str(v)


def _format_ts(ms):
    if ms is None:
        return None
    try:
        return _dt.datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")
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


def build_timeline(rows: list[dict], classification: dict) -> list[dict]:
    """Build an ordered list of revision nodes from raw audit rows.

    ``rows`` must be ordered by REV ascending and may carry a synthetic
    ``__revts`` key (epoch millis) from the REVINFO join.
    """
    rev_col = classification["rev_column"]
    revtype_col = classification["revtype_column"]
    data_cols = classification["data_columns"]

    state: dict = {}
    timeline: list[dict] = []

    for row in rows:
        rev = row.get(rev_col) if rev_col else None
        rtype = row.get(revtype_col) if revtype_col else 1
        try:
            rtype = int(rtype) if rtype is not None else 1
        except (TypeError, ValueError):
            rtype = 1
        meta = REVTYPE_META.get(rtype, REVTYPE_META[1])
        ts_ms = row.get("__revts")

        changes: list[dict] = []

        if rtype == 0:  # ADD — show the full initial snapshot
            for dc in data_cols:
                val = row.get(dc["name"])
                if val is not None:
                    changes.append(_change(dc["name"], None, val, "create"))
                state[dc["name"]] = val

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
                    changes.append(
                        _change(dc["name"], state.get(dc["name"]), val, "update")
                    )
                state[dc["name"]] = val

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
