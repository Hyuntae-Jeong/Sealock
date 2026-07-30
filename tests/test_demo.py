"""Unit tests for the "샘플 데이터로 둘러보기" sample data (no database required).

The demo rows are generated from an event log, so these tests guard the shape
that generation has to keep: rows Envers could actually have written, both
조회 모드 telling the same story, and every 기간 preset landing on something.

Run:  python -m pytest tests          (or)   python tests/test_demo.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sealock import demo, services  # noqa: E402


def _state(table):
    st = services.AppState()
    st.demo = True
    services.confirm_table(st, table, None)
    return st


def _day(days_ago: int) -> dt.date:
    return (demo._TODAY - dt.timedelta(days=days_ago)).date()


def _changeset(table, **kw):
    """The whole table as one page — paging is exercised in test_range."""
    return services.get_full_history(_state(table), None, 10_000, **kw)["timeline"]


# ── the sample table list ───────────────────────────────────────────────
def test_sample_tables_are_lowercase_aud_and_have_no_config_table():
    assert demo.tables() == ["member_aud", "order_aud", "product_aud"]
    assert all(t == t.lower() and t.endswith("_aud") for t in demo.tables())
    assert demo.DEFAULT_TABLE in demo.tables()


def test_unknown_table_falls_back_to_the_default_sample():
    # Demo mode lets the name be typed by hand, so anything unknown still
    # previews something rather than dead-ending.
    assert demo.preview("whatever_aud")["table"] == demo.DEFAULT_TABLE
    assert demo.preview()["table"] == demo.DEFAULT_TABLE


def test_preview_matches_the_generated_rows():
    for table in demo.tables():
        d = demo.preview(table)
        assert d["table"] == table and d["identifier_default"] == "id"
        row = demo._ROWS[table][0]
        for col in d["data_columns"]:
            assert col["name"] in row and col["mod_flag"] in row
        for orphan in d["orphan_mod_flags"]:
            assert orphan["name"] in row
        assert d["revinfo"]["found"]        # 기간 지정이 가능해야 한다


def test_example_id_resolves_to_a_record_that_exists():
    for table in demo.tables():
        tl = services.get_history(_state(table), demo.example_id(table))["timeline"]
        assert len(tl) >= 4                 # 둘러볼 만한 길이의 이력


# ── rows have to look like Envers wrote them ────────────────────────────
def test_one_row_per_record_per_revision():
    for table in demo.tables():
        seen = {(r["REV"], r["id"]) for r in demo._ROWS[table]}
        assert len(seen) == len(demo._ROWS[table])


def test_each_record_starts_with_add_and_dies_at_most_once():
    for table in demo.tables():
        per = {}
        for row in demo._ROWS[table]:
            per.setdefault(row["id"], []).append(row)
        for rid, rows in per.items():
            assert rows[0]["REVTYPE"] == 0, f"{table} id={rid} does not start with ADD"
            assert [r["REV"] for r in rows] == sorted(r["REV"] for r in rows)
            assert [r["__revts"] for r in rows] == sorted(r["__revts"] for r in rows)
            assert all(r["REVTYPE"] != 2 for r in rows[:-1]), (
                f"{table} id={rid} lives on after DELETE")


def test_delete_rows_null_every_value_column():
    for table in demo.tables():
        cols = [c["name"] for c in demo.preview(table)["data_columns"]]
        for row in demo._ROWS[table]:
            if row["REVTYPE"] == 2:
                assert all(row[c] is None for c in cols)
                assert all(row[f"{c}_MOD"] == 0 for c in cols)


def test_revision_numbers_are_a_single_shared_sequence():
    # One REVINFO for the whole schema: a revision belongs to one table, ...
    owner = {}
    for table in demo.tables():
        for row in demo._ROWS[table]:
            assert owner.setdefault(row["REV"], table) == table
    # ... and each table's numbers have gaps, because the other tables' commits
    # took the numbers in between — as a shared sequence really behaves.
    for table in demo.tables():
        revs = {row["REV"] for row in demo._ROWS[table]}
        assert max(revs) - min(revs) + 1 > len(revs), f"{table} REVs are contiguous"


# ── what the screen actually shows ──────────────────────────────────────
def test_no_revision_renders_as_an_empty_card():
    for table in demo.tables():
        for node in _changeset(table):
            for rec in node["records"]:
                assert rec["kind"] == "delete" or rec["changes"], (
                    f"{table} REV {node['rev']} {rec['identifier']} 변경된 컬럼이 없습니다")


def test_search_and_full_history_tell_the_same_story():
    for table in demo.tables():
        by_record = {}
        for node in _changeset(table):
            for rec in node["records"]:
                by_record.setdefault(rec["identifier"], []).append(
                    (node["rev"], len(rec["changes"])))
        for ident, expected in by_record.items():
            rid = ident.split(" = ")[1]
            tl = services.get_history(_state(table), rid)["timeline"]
            assert [(n["rev"], len(n["changes"])) for n in tl] == sorted(expected)


def test_every_table_shows_create_update_and_delete():
    for table in demo.tables():
        kinds = {rec["kind"] for node in _changeset(table) for rec in node["records"]}
        assert kinds == {"create", "update", "delete"}


def test_batch_revisions_touch_several_records_at_once():
    # 여러 레코드가 한 리비전에 묶이는 것이 전체 이력 모드의 볼거리다.
    for table in demo.tables():
        widest = max(n["record_count"] for n in _changeset(table))
        assert widest >= 3, f"{table} has no multi-record revision"


def test_orphan_mod_flag_is_reported_as_changed_without_a_diff():
    # order_aud carries an audited collection (items) with no value column.
    flags = [c for node in _changeset("order_aud") for rec in node["records"]
             for c in rec["changes"] if c["kind"] == "flag"]
    assert flags and {c["label"] for c in flags} == {"items"}
    assert all(c["old"] is None and c["new"] is None for c in flags)


def test_bit_column_renders_as_a_number_not_bytes():
    changes = [c for node in _changeset("product_aud") for rec in node["records"]
               for c in rec["changes"] if c["column"] == "on_sale"]
    assert changes and {c["new"] for c in changes} <= {"0", "1"}


# ── the 기간 presets have to land on data ───────────────────────────────
def test_every_period_preset_finds_something_in_every_table():
    for table in demo.tables():
        st = _state(table)
        previous = 0
        for days in (7, 30, 90, 365):
            count = services.count_full_history(st, _day(days - 1), _day(0))
            assert count["revisions"] > 0, f"{table}: 최근 {days}일에 볼 것이 없다"
            assert count["revisions"] >= previous     # 기간이 넓어지면 줄지 않는다
            previous = count["revisions"]
        assert previous < services.count_full_history(st)["revisions"]


def test_sample_data_stays_in_the_past():
    now = dt.datetime.now().timestamp() * 1000
    for table in demo.tables():
        assert all(r["__revts"] < now for r in demo._ROWS[table])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  [OK] {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")
