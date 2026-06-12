"""Synthetic Envers data for the "샘플 데이터로 둘러보기" mode (no DB needed).

All values are fabricated (example.com) so they are safe to ship in a public
repo. The rows are shaped exactly like real Envers audit rows so they flow
through the same history.build_timeline() path as live data.
"""
from __future__ import annotations

import datetime as _dt


def _ms(y, mo, d, h, mi, s) -> int:
    return int(_dt.datetime(y, mo, d, h, mi, s).timestamp() * 1000)


def preview() -> dict:
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
