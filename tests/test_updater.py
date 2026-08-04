"""Unit tests for the manual update logic (no network, no database).

The parts that can only be proven on a real install — the swap helpers — are
covered by their sanity checks and rollback; what is testable here is the
decision-making around them: which builds may update, what counts as newer,
which asset belongs to this platform, and how failures are worded.

Run:  python -m pytest tests          (or)   python tests/test_updater.py
"""
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sealock import updater  # noqa: E402


class _Resp:
    """Stands in for the object urlopen() returns as a context manager."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _payload(tag="v9.9.9", assets=None, body="바뀐 것들"):
    names = assets if assets is not None else ["Sealock-macOS.zip", "Sealock-Windows.zip"]
    return {
        "tag_name": tag,
        "body": body,
        "published_at": "2026-07-29T04:52:14Z",
        "assets": [
            {"name": n, "browser_download_url": f"https://example.com/{n}", "size": 1234}
            for n in names
        ],
    }


def _patched_urlopen(monkeypatch_target):
    """Swap urllib.request.urlopen for the duration of one call."""
    original = updater.urllib.request.urlopen
    updater.urllib.request.urlopen = monkeypatch_target
    return original


def _restore(original):
    updater.urllib.request.urlopen = original


# ── version comparison ──────────────────────────────────────────────────
def test_is_newer_compares_release_numbers():
    assert updater.is_newer("0.0.3", "0.0.4")
    assert updater.is_newer("0.0.9", "0.1.0")
    assert not updater.is_newer("0.1.0", "0.0.3")
    assert not updater.is_newer("0.0.3", "0.0.3")


def test_dev_suffix_is_ignored_when_comparing():
    # "0.0.3+dev" is still 0.0.3 — a released 0.0.3 is not an upgrade for it.
    assert not updater.is_newer("0.0.3+dev", "0.0.3")
    assert updater.is_newer("0.0.3+dev", "0.0.4")


def test_unparsable_version_never_claims_an_update():
    assert not updater.is_newer("0.0.3", "nightly")
    assert not updater.is_newer("main", "0.0.4")


def test_dev_build_is_flagged_by_the_local_part():
    assert updater.is_dev_build("0.0.3+dev")
    assert not updater.is_dev_build("0.0.3")


# ── who may update ──────────────────────────────────────────────────────
def test_running_from_source_cannot_self_update():
    # The test suite itself is not a frozen build, so this is the real answer.
    assert not updater.is_frozen()
    assert not updater.can_self_update()
    assert "소스에서 실행" in updater.blocked_reason()


def test_every_blocked_state_explains_itself():
    assert updater.blocked_reason()          # source run: a reason exists
    # ...and a build that can update has nothing to explain.
    assert (updater.blocked_reason() is None) == updater.can_self_update()


# ── release lookup ──────────────────────────────────────────────────────
def test_fetch_picks_the_asset_for_this_platform():
    if sys.platform not in updater.ASSETS:
        return                                  # 이 플랫폼용 릴리즈가 없다
    original = _patched_urlopen(lambda *a, **k: _Resp(_payload()))
    try:
        release, err = updater.fetch_latest()
    finally:
        _restore(original)
    assert err is None
    assert release.tag == "v9.9.9" and release.version == "9.9.9"
    assert release.asset_name == updater.ASSETS[sys.platform]
    assert release.notes == "바뀐 것들"
    assert release.published == "2026-07-29"


def test_release_without_a_build_for_this_platform_is_an_error():
    original = _patched_urlopen(lambda *a, **k: _Resp(_payload(assets=["Sealock-Linux.zip"])))
    try:
        release, err = updater.fetch_latest()
    finally:
        _restore(original)
    assert release is None and err.kind == "no_asset"
    assert "플랫폼" in updater.describe(err)


def test_network_failure_is_reported_as_such():
    def boom(*a, **k):
        raise urllib.error.URLError("nodename nor servname provided")

    original = _patched_urlopen(boom)
    try:
        release, err = updater.fetch_latest()
    finally:
        _restore(original)
    assert release is None and err.kind == "network"
    assert "네트워크" in updater.describe(err)


def test_rate_limit_is_told_apart_from_a_dead_network():
    # Both arrive as failures, but "wait a bit" and "check your connection"
    # are different instructions — the 403 + remaining=0 pair means the former.
    class _Headers(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    def limited(*a, **k):
        raise urllib.error.HTTPError(
            updater.RELEASES_API, 403, "rate limited",
            _Headers({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"}), None)

    original = _patched_urlopen(limited)
    try:
        release, err = updater.fetch_latest()
    finally:
        _restore(original)
    assert release is None and err.kind == "rate_limit"
    assert "한도" in updater.describe(err)


def test_malformed_response_does_not_raise():
    class _Broken(_Resp):
        def read(self):
            return b"{ not json"

    original = _patched_urlopen(lambda *a, **k: _Broken({}))
    try:
        release, err = updater.fetch_latest()
    finally:
        _restore(original)
    assert release is None and err.kind in ("network", "parse")


# ── failure reporting ───────────────────────────────────────────────────
def test_swap_error_tokens_become_readable_korean():
    assert "쓰기 권한" in updater.explain_swap_error("ERR_BACKUP target=/Applications/Sealock.app")
    assert "30초" in updater.explain_swap_error("ERR_WAIT_TIMEOUT pid=123")
    assert updater.explain_swap_error("") == ""
    # An unknown token is passed through rather than swallowed.
    assert updater.explain_swap_error("ERR_WAT boom") == "ERR_WAT boom"


def test_pending_marker_round_trips_once():
    updater.mark_pending("9.9.9")
    assert updater.take_pending() == "9.9.9"
    assert updater.take_pending() is None      # 읽으면 지워진다


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  [OK] {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")
