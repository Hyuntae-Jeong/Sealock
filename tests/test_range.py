"""Unit tests for the full-history 기간 filter (no database required).

Covers date normalisation, the bounds handed to SQL, and the demo-mode
filtering that the UI exercises without a connection.

Run:  python -m pytest tests          (or)   python tests/test_range.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sealock import demo, services  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))


def _state():
    st = services.AppState()
    st.demo = True
    services.confirm_table(st, demo.CONFIG_TABLE, None)
    return st


class _FakeDB:
    """Stands in for Database when only the ts-scale probe is needed."""

    def __init__(self, biggest):
        self.biggest = biggest

    def query_one(self, sql, params=None):
        return {"m": self.biggest}


# ── date normalisation ──────────────────────────────────────────────────
def test_as_date_accepts_date_datetime_and_iso_text():
    assert services._as_date(dt.date(2026, 6, 1)) == dt.date(2026, 6, 1)
    assert services._as_date(dt.datetime(2026, 6, 1, 13, 30)) == dt.date(2026, 6, 1)
    assert services._as_date("2026-06-01") == dt.date(2026, 6, 1)
    assert services._as_date(None) is None
    assert services._as_date("   ") is None


def test_as_date_rejects_other_formats():
    try:
        services._as_date("2026/06/01")
    except ValueError as exc:
        assert "YYYY-MM-DD" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_norm_range_open_ends_and_ordering():
    assert services._norm_range(None, None) is None
    assert services._norm_range("2026-06-01", None)[1] == services._DATE_MAX
    assert services._norm_range(None, "2026-06-01")[0] == services._DATE_MIN
    try:
        services._norm_range("2026-07-01", "2026-06-01")
    except ValueError as exc:
        assert "시작일" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# ── bounds handed to the query ──────────────────────────────────────────
def test_epoch_bounds_are_half_open_kst_days():
    lo, hi = services._epoch_bounds((dt.date(2026, 6, 28), dt.date(2026, 6, 28)), 1000)
    assert lo == int(dt.datetime(2026, 6, 28, tzinfo=KST).timestamp() * 1000)
    assert hi == int(dt.datetime(2026, 6, 29, tzinfo=KST).timestamp() * 1000)
    assert hi - lo == 86_400_000                      # exactly one day, end exclusive


def test_epoch_bounds_follow_the_column_scale():
    rng = (dt.date(2026, 6, 28), dt.date(2026, 6, 28))
    assert services._epoch_bounds(rng, 1000)[0] == services._epoch_bounds(rng, 1)[0] * 1000


def test_sql_bounds_use_wall_clock_for_datetime_columns():
    ctx = {"revinfo": {"found": True, "table": "REVINFO", "rev_column": "REV",
                       "ts_column": "rev_date", "ts_type": "datetime"}}
    lo, hi = services._sql_bounds(None, ctx, (dt.date(2026, 6, 1), dt.date(2026, 6, 30)))
    assert lo == dt.datetime(2026, 6, 1, 0, 0)
    assert hi == dt.datetime(2026, 7, 1, 0, 0)        # day after the last, exclusive


def test_sql_bounds_probe_millis_vs_seconds_once():
    ctx = {"revinfo": {"found": True, "table": "REVINFO", "rev_column": "REV",
                       "ts_column": "REVTSTMP", "ts_type": "bigint(20)"}}
    rng = (dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    millis = services._sql_bounds(_FakeDB(1_780_000_000_000), ctx, rng)
    assert ctx["revinfo"]["ts_scale"] == 1000        # cached on the revinfo dict
    ctx["revinfo"].pop("ts_scale")
    seconds = services._sql_bounds(_FakeDB(1_780_000_000), ctx, rng)
    assert ctx["revinfo"]["ts_scale"] == 1
    assert millis[0] == seconds[0] * 1000


def test_date_range_needs_a_revinfo_timestamp():
    ctx = {"revinfo": {"found": False}}
    try:
        services._sql_bounds(None, ctx, (dt.date(2026, 6, 1), dt.date(2026, 6, 30)))
    except ValueError as exc:
        assert "REVINFO" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    assert services._sql_bounds(None, ctx, None) is None


# ── end-to-end through demo mode ────────────────────────────────────────
def test_count_tallies_the_whole_table_by_default():
    c = services.count_full_history(_state())
    assert (c["revisions"], c["rows"]) == (3, 5)
    assert c["first_ts"] < c["last_ts"]


def test_count_narrows_to_the_picked_period():
    c = services.count_full_history(_state(), dt.date(2026, 6, 25), dt.date(2026, 6, 30))
    assert (c["revisions"], c["rows"]) == (1, 1)
    empty = services.count_full_history(_state(), dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    assert (empty["revisions"], empty["rows"]) == (0, 0)
    assert empty["first_ts"] is None


def test_filtered_load_keeps_the_pre_period_before_value():
    # Only the rev-151 edit falls in the period; its "before" value comes from
    # the creation at rev 100, which is outside it.
    r = services.get_full_history(_state(), None, services.FULL_HISTORY_PAGE,
                                  dt.date(2026, 6, 28), dt.date(2026, 6, 28))
    assert not r["empty"] and len(r["timeline"]) == 1
    node = r["timeline"][0]
    assert node["rev"] == 151
    change = node["records"][0]["changes"][0]
    assert (change["old"], change["new"]) == ("0", "1")


def test_period_with_no_revisions_reads_as_empty():
    r = services.get_full_history(_state(), None, services.FULL_HISTORY_PAGE,
                                  dt.date(2020, 1, 1), dt.date(2020, 2, 1))
    assert r["empty"] and r["timeline"] == [] and r["min_rev"] is None


def test_unfiltered_load_is_unchanged():
    r = services.get_full_history(_state())
    assert [n["rev"] for n in r["timeline"]] == [151, 142, 100]
    assert r["min_rev"] == 100 and not r["has_more"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  [OK] {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")
