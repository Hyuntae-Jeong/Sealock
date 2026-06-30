"""Synthetic Envers data for the "샘플 데이터로 둘러보기" mode (no DB needed).

All values are fabricated (example.com) so they are safe to ship in a public
repo. The rows are shaped exactly like real Envers audit rows so they flow
through the same history.build_timeline() path as live data.
"""
from __future__ import annotations

import datetime as _dt


def _ms(y, mo, d, h, mi, s) -> int:
    return int(_dt.datetime(y, mo, d, h, mi, s).timestamp() * 1000)


CONFIG_TABLE = "notification_mass_block_config_AUD"


def preview(table: str | None = None) -> dict:
    """Dispatch to the right synthetic table preview by name.

    The `name`-keyed config table has no `id`, so it flows through the
    all-records revision timeline; everything else uses the member example.
    """
    if table == CONFIG_TABLE:
        return _preview_config()
    return _preview_member()


def _preview_member() -> dict:
    """Mirror of introspect.describe_table() for a `member_AUD` table."""
    return {
        "table": "member_AUD",
        "rev_column": "REV",
        "revtype_column": "REVTYPE",
        "has_mod_flags": True,
        "mod_flag_columns": ["username_MOD", "email_MOD", "status_MOD", "points_MOD", "grade_MOD"],
        "identifier_columns": ["id"],
        "identifier_default": "id",
        "data_columns": [
            {"name": "username", "type": "varchar(50)", "mod_flag": "username_MOD"},
            {"name": "email", "type": "varchar(120)", "mod_flag": "email_MOD"},
            {"name": "status", "type": "varchar(20)", "mod_flag": "status_MOD"},
            {"name": "points", "type": "int(11)", "mod_flag": "points_MOD"},
            {"name": "grade", "type": "varchar(20)", "mod_flag": "grade_MOD"},
        ],
        "system_columns": [
            {"name": "REV", "type": "int(11)"},
            {"name": "REVTYPE", "type": "tinyint(4)"},
        ],
        "orphan_mod_flags": [],
        "revinfo": {"found": True, "table": "REVINFO", "rev_column": "REV", "ts_column": "REVTSTMP"},
        "all_columns": [{"name": "id", "type": "bigint(20)"}],
    }


def _preview_config() -> dict:
    """Mirror of introspect.describe_table() for a `name`-keyed config table —
    no `id`, so Sealock browses its whole revision timeline."""
    return {
        "table": CONFIG_TABLE,
        "rev_column": "REV",
        "revtype_column": "REVTYPE",
        "has_mod_flags": True,
        "mod_flag_columns": ["value_MOD", "value_type_MOD"],
        "identifier_columns": ["name"],
        "identifier_default": "name",
        "data_columns": [
            {"name": "value", "type": "varchar(1000)", "mod_flag": "value_MOD"},
            {"name": "value_type", "type": "int(11)", "mod_flag": "value_type_MOD"},
        ],
        "system_columns": [
            {"name": "REV", "type": "bigint(20)"},
            {"name": "REVTYPE", "type": "tinyint(4)"},
        ],
        "orphan_mod_flags": [],
        "revinfo": {"found": True, "table": "REVINFO", "rev_column": "REV", "ts_column": "REVTSTMP"},
        "all_columns": [{"name": "name", "type": "varchar(100)"}],
    }


def _cfg(rev, rtype, ts, name, value, vmod, vt=13, vtmod=0):
    return {"REV": rev, "REVTYPE": rtype, "__revts": ts, "name": name,
            "value": value, "value_MOD": vmod, "value_type": vt, "value_type_MOD": vtmod}


def full_history(before_rev=None) -> dict:
    """All-records changeset page for the demo config table: three settings
    created together, then edited in two later revisions. One page only."""
    if before_rev is not None:          # demo has a single page — nothing older
        return {"rows": [], "baseline": [], "min_rev": None, "has_more": False}
    c, e, t = _ms(2025, 6, 13, 15, 0, 28), _ms(2026, 6, 20, 9, 14, 2), _ms(2026, 6, 28, 15, 0, 28)
    rows = [  # ordered by name, then REV ascending (as the live query returns)
        _cfg(100, 0, c, "notification.mass.block.check_interval_sec", "5", 1),
        _cfg(100, 0, c, "notification.mass.block.enable", "0", 1),
        _cfg(151, 1, t, "notification.mass.block.enable", "1", 1),
        _cfg(100, 0, c, "notification.mass.block.threshold_count", "30", 1),
        _cfg(142, 1, e, "notification.mass.block.threshold_count", "50", 1),
    ]
    return {"rows": rows, "baseline": [], "min_rev": 100, "has_more": False}


def rows() -> list[dict]:
    """Five revisions of member id=42: create, three edits, delete."""
    return [
        {"REV": 1, "REVTYPE": 0, "__revts": _ms(2024, 1, 8, 9, 12, 30),
         "username": "alice", "email": "alice@example.com", "status": "ACTIVE", "points": 0, "grade": "BRONZE",
         "username_MOD": 1, "email_MOD": 1, "status_MOD": 1, "points_MOD": 1, "grade_MOD": 1},
        {"REV": 2, "REVTYPE": 1, "__revts": _ms(2024, 2, 14, 16, 40, 5),
         "username": "alice", "email": "alice@example.com", "status": "ACTIVE", "points": 100, "grade": "SILVER",
         "username_MOD": 0, "email_MOD": 0, "status_MOD": 0, "points_MOD": 1, "grade_MOD": 1},
        {"REV": 3, "REVTYPE": 1, "__revts": _ms(2024, 3, 22, 11, 5, 48),
         "username": "alice", "email": "alice.kim@example.com", "status": "DORMANT", "points": 100, "grade": "SILVER",
         "username_MOD": 0, "email_MOD": 1, "status_MOD": 1, "points_MOD": 0, "grade_MOD": 0},
        {"REV": 4, "REVTYPE": 1, "__revts": _ms(2024, 5, 30, 20, 15, 12),
         "username": "alice", "email": "alice.kim@example.com", "status": "DORMANT", "points": 250, "grade": "GOLD",
         "username_MOD": 0, "email_MOD": 0, "status_MOD": 0, "points_MOD": 1, "grade_MOD": 1},
        {"REV": 5, "REVTYPE": 2, "__revts": _ms(2024, 6, 19, 8, 0, 0),
         "username": None, "email": None, "status": None, "points": None, "grade": None,
         "username_MOD": 0, "email_MOD": 0, "status_MOD": 0, "points_MOD": 0, "grade_MOD": 0},
    ]
