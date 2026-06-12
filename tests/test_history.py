"""Unit tests for the Envers timeline builder (no database required).

Run:  python -m pytest tests          (or)   python tests/test_history.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sealock.history import build_timeline, summarize  # noqa: E402

# Classification mirroring what introspect.classify() would produce for a
# `member_AUD` table with modified-flags enabled.
CLASSIFICATION = {
    "rev_column": "REV",
    "revtype_column": "REVTYPE",
    "data_columns": [
        {"name": "username", "type": "varchar", "mod_flag": "username_MOD"},
        {"name": "email", "type": "varchar", "mod_flag": "email_MOD"},
        {"name": "status", "type": "varchar", "mod_flag": "status_MOD"},
        {"name": "points", "type": "int", "mod_flag": "points_MOD"},
    ],
}

# Each MOD row carries the *full* current snapshot (as Envers does), with the
# _MOD flag marking which columns actually changed.
ROWS = [
    {"REV": 1, "REVTYPE": 0, "__revts": 1704672750000,
     "username": "alice", "email": "a@example.com", "status": "ACTIVE", "points": 0,
     "username_MOD": 1, "email_MOD": 1, "status_MOD": 1, "points_MOD": 1},
    {"REV": 2, "REVTYPE": 1, "__revts": 1707896405000,
     "username": "alice", "email": "a@example.com", "status": "ACTIVE", "points": 100,
     "username_MOD": 0, "email_MOD": 0, "status_MOD": 0, "points_MOD": 1},
    {"REV": 3, "REVTYPE": 1, "__revts": 1711076748000,
     "username": "alice", "email": "alice@example.com", "status": "DORMANT", "points": 100,
     "username_MOD": 0, "email_MOD": 1, "status_MOD": 1, "points_MOD": 0},
    {"REV": 4, "REVTYPE": 2, "__revts": 1718755200000,
     "username": None, "email": None, "status": None, "points": None,
     "username_MOD": 0, "email_MOD": 0, "status_MOD": 0, "points_MOD": 0},
]


def test_add_revision_shows_full_initial_snapshot():
    tl = build_timeline(ROWS, CLASSIFICATION)
    add = tl[0]
    assert add["kind"] == "create"
    cols = {c["column"]: c for c in add["changes"]}
    assert cols["username"]["old"] is None and cols["username"]["new"] == "alice"
    assert cols["points"]["new"] == 0  # zero is shown, not dropped as falsy
    assert add["timestamp"] is not None  # epoch-ms formatted


def test_mod_uses_flags_for_old_to_new():
    tl = build_timeline(ROWS, CLASSIFICATION)
    rev2 = tl[1]
    assert rev2["kind"] == "update"
    assert len(rev2["changes"]) == 1  # only points changed
    ch = rev2["changes"][0]
    assert ch["column"] == "points" and ch["old"] == 0 and ch["new"] == 100


def test_mod_tracks_running_state_across_revisions():
    tl = build_timeline(ROWS, CLASSIFICATION)
    rev3 = {c["column"]: c for c in tl[2]["changes"]}
    assert rev3["email"]["old"] == "a@example.com"
    assert rev3["email"]["new"] == "alice@example.com"
    assert rev3["status"]["old"] == "ACTIVE" and rev3["status"]["new"] == "DORMANT"
    assert "points" not in rev3  # points_MOD = 0


def test_delete_revision():
    tl = build_timeline(ROWS, CLASSIFICATION)
    last = tl[-1]
    assert last["kind"] == "delete" and last["deleted"] is True
    assert last["changes"] == []
    # snapshot keeps the last-known values from before deletion
    assert last["snapshot"]["email"] == "alice@example.com"


def test_fallback_without_mod_flags_uses_value_diff():
    cls = {
        "rev_column": "REV", "revtype_column": "REVTYPE",
        "data_columns": [{"name": "points", "type": "int", "mod_flag": None}],
    }
    rows = [
        {"REV": 1, "REVTYPE": 0, "points": 10},
        {"REV": 2, "REVTYPE": 1, "points": 10},   # unchanged -> no change row
        {"REV": 3, "REVTYPE": 1, "points": 20},   # changed
    ]
    tl = build_timeline(rows, cls)
    assert tl[1]["changes"] == []
    assert tl[2]["changes"][0]["old"] == 10 and tl[2]["changes"][0]["new"] == 20


def test_bit_bytes_value_renders_numeric():
    cls = {"rev_column": "REV", "revtype_column": "REVTYPE",
           "data_columns": [{"name": "enabled", "type": "bit(1)", "mod_flag": None}]}
    rows = [
        {"REV": 1, "REVTYPE": 0, "enabled": b"\x01"},
        {"REV": 2, "REVTYPE": 1, "enabled": b"\x00"},
    ]
    tl = build_timeline(rows, cls)
    assert tl[0]["changes"][0]["new"] == "1"            # BIT -> "1", not a box
    assert tl[1]["changes"][0]["old"] == "1"
    assert tl[1]["changes"][0]["new"] == "0"


def test_zero_or_missing_timestamp_is_none():
    cls = {"rev_column": "REV", "revtype_column": "REVTYPE",
           "data_columns": [{"name": "x", "type": "int", "mod_flag": None}]}
    rows = [{"REV": 1, "REVTYPE": 0, "x": 1, "__revts": 0},
            {"REV": 2, "REVTYPE": 1, "x": 2, "__revts": None}]
    tl = build_timeline(rows, cls)
    assert tl[0]["timestamp"] is None                    # epoch 0 -> not "1970-..."
    assert tl[1]["timestamp"] is None


def test_epoch_millis_formats_in_kst():
    cls = {"rev_column": "REV", "revtype_column": "REVTYPE",
           "data_columns": [{"name": "x", "type": "int", "mod_flag": None}]}
    # 1704672750000 ms = 2024-01-08 09:12:30 KST
    tl = build_timeline([{"REV": 1, "REVTYPE": 0, "x": 1, "__revts": 1704672750000}], cls)
    assert tl[0]["timestamp"] == "2024-01-08 09:12:30"


def test_orphan_mod_flag_shows_changed_without_diff():
    # checkpoints_mod has no `checkpoints` value column (audited collection).
    cls = {
        "rev_column": "REV", "revtype_column": "REVTYPE",
        "data_columns": [{"name": "name", "type": "varchar", "mod_flag": "name_mod"}],
        "orphan_mod_flags": [{"name": "checkpoints_mod", "label": "checkpoints"}],
    }
    rows = [
        {"REV": 1, "REVTYPE": 0, "name": "a", "name_mod": 1, "checkpoints_mod": 0},
        {"REV": 2, "REVTYPE": 1, "name": "a", "name_mod": 0, "checkpoints_mod": 1},
    ]
    tl = build_timeline(rows, cls)
    rev2 = tl[1]["changes"]
    assert len(rev2) == 1                      # no longer "변경된 컬럼이 없습니다"
    assert rev2[0]["kind"] == "flag"
    assert rev2[0]["label"] == "checkpoints"
    assert rev2[0]["old"] is None and rev2[0]["new"] is None


def test_classify_detects_orphan_mod_flag():
    from sealock.introspect import classify  # noqa: PLC0415
    cols = [
        {"name": "id", "type": "bigint", "nullable": False, "key": "PRI", "comment": ""},
        {"name": "name", "type": "varchar", "nullable": True, "key": "", "comment": ""},
        {"name": "name_mod", "type": "bit", "nullable": True, "key": "", "comment": ""},
        {"name": "checkpoints_mod", "type": "bit", "nullable": True, "key": "", "comment": ""},
        {"name": "REV", "type": "int", "nullable": False, "key": "PRI", "comment": ""},
        {"name": "REVTYPE", "type": "tinyint", "nullable": True, "key": "", "comment": ""},
    ]
    cls = classify(cols, ["id", "REV"])
    assert [c["name"] for c in cls["data_columns"]] == ["name"]
    assert cls["orphan_mod_flags"] == [{"name": "checkpoints_mod", "label": "checkpoints"}]


def test_association_mod_flag_with_fk_column_is_not_orphan():
    from sealock.introspect import classify  # noqa: PLC0415
    cols = [
        {"name": "id", "type": "bigint", "nullable": False, "key": "PRI", "comment": ""},
        {"name": "parent_interface_id", "type": "bigint", "nullable": True, "key": "", "comment": ""},
        {"name": "parent_interface_mod", "type": "bit", "nullable": True, "key": "", "comment": ""},
        {"name": "checkpoints_mod", "type": "bit", "nullable": True, "key": "", "comment": ""},
        {"name": "REV", "type": "int", "nullable": False, "key": "PRI", "comment": ""},
        {"name": "REVTYPE", "type": "tinyint", "nullable": True, "key": "", "comment": ""},
    ]
    cls = classify(cols, ["id", "REV"])
    # The FK column parent_interface_id is a real data column (shows A->B),
    # so parent_interface_mod is NOT shown as "변경됨".
    assert "parent_interface_id" in [c["name"] for c in cls["data_columns"]]
    orphan_labels = [o["label"] for o in cls["orphan_mod_flags"]]
    assert "parent_interface" not in orphan_labels
    assert orphan_labels == ["checkpoints"]  # only the true orphan remains


def test_summary():
    tl = build_timeline(ROWS, CLASSIFICATION)
    s = summarize(tl, "id", "42")
    assert s["revisions"] == 4
    assert s["total_changes"] == 4 + 1 + 2 + 0
    assert s["first_ts"] and s["last_ts"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  [OK] {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")
