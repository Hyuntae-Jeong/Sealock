"""Headless (offscreen) smoke test — constructs the whole Qt UI and renders the
demo preview + timeline without a display or a database.

Run:  python scripts/smoke_ui.py
It sets QT_QPA_PLATFORM=offscreen so it works in CI / over SSH with no screen.
Exit 0 = the UI builds and renders; any construction error raises and fails.
"""
import os
import sys
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QDate, QPoint  # noqa: E402
from PySide6.QtGui import QContextMenuEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sealock import demo, services  # noqa: E402
from sealock.ui.theme import QSS  # noqa: E402
from sealock.ui.widgets import SnapshotPopup  # noqa: E402
from sealock.ui.window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication([])
    app.setStyleSheet(QSS)

    win = MainWindow()
    win.show()
    st = win.state
    st.demo = True

    win.goto(1)
    win.page_table._fill_chips([f"sample_{i}_aud" for i in range(30)] + ["member_AUD"])
    win.page_table._render_chips("sample_1")
    win.page_table._render_preview(demo.preview())

    services.confirm_table(st, "member_AUD", "id")
    win.goto(2)
    win.page_hist.on_enter()
    win.page_hist._render(services.get_history(st, "42"))

    # 우클릭 스냅샷 팝업: 수정 / 삭제 리비전 각각 렌더된다.
    for card in (win.page_hist._cards[2], win.page_hist._cards[-1]):
        pos = QPoint(120, 40)
        card.contextMenuEvent(
            QContextMenuEvent(QContextMenuEvent.Mouse, pos, card.mapToGlobal(pos)))
        app.processEvents()
    for w in app.topLevelWidgets():
        if isinstance(w, SnapshotPopup):
            w.close()

    win.page_hist._empty({"column": "id", "value": "999"})
    win.page_hist._placeholder()

    # name-keyed config table: search mode works too, plus the "전체 이력" toggle.
    win.page_table._render_preview(demo.preview(demo.CONFIG_TABLE))
    services.confirm_table(st, demo.CONFIG_TABLE, None)
    ph = win.page_hist
    ph.on_enter()                       # defaults to search mode, no async load
    ph._set_mode("search")
    ph._mode = "full"
    r = services.get_full_history(st)
    ph._cs_nodes = list(r["timeline"])
    ph._cs_min_rev, ph._cs_has_more = r["min_rev"], True   # force "더 보기" branch
    ph._render_changeset()
    ph._cs_has_more = False
    ph._render_changeset()
    ph._empty_full()

    # 기간 필터: pre-load tally, a preset pick, and an explicit range.
    ph.range_row.show()
    ph._preset, ph._loaded = "all", False
    ph._show_count(services.count_full_history(st))
    ph._pick_preset("365d")             # fills the pickers, re-tallies
    ph._set_dates(QDate(2026, 6, 1), QDate(2026, 6, 30))
    ph._on_date_edited()                # -> 직접 선택
    ph._applied = (date(2026, 6, 1), date(2026, 6, 30))
    scoped = services.get_full_history(st, None, services.FULL_HISTORY_PAGE, *ph._applied)
    ph._cs_nodes = list(scoped["timeline"])
    ph._cs_min_rev, ph._cs_has_more = scoped["min_rev"], False
    ph._render_changeset()
    ph._show_count(services.count_full_history(st, *ph._applied))
    ph._loaded = False
    ph._empty_full()                    # empty state names the applied period
    app.processEvents()

    # 여러 레코드가 든 리비전 카드 — 커서가 놓인 레코드의 스냅샷을 고른다.
    ph._cs_nodes = list(r["timeline"])
    ph._render_changeset()
    app.processEvents()                 # let the layout settle before hit-testing
    card = ph._cards[-1]
    zones = card._zones
    assert len(zones) == 3, f"expected 3 record blocks, got {len(zones)}"
    y = zones[1][0].mapTo(card, QPoint(0, 0)).y() + 8
    assert card._record_at(QPoint(120, y)) is zones[1][1]
    card.contextMenuEvent(QContextMenuEvent(
        QContextMenuEvent.Mouse, QPoint(120, y), card.mapToGlobal(QPoint(120, y))))
    app.processEvents()
    for w in app.topLevelWidgets():
        if isinstance(w, SnapshotPopup):
            w.close()
    app.processEvents()

    print("[smoke] OK - MainWindow built; search + full-history + date-range + snapshot popup rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
