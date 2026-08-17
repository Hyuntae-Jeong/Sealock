"""Headless (offscreen) smoke test — constructs the whole Qt UI and renders the
demo preview + timeline without a display or a database.

Run:  python scripts/smoke_ui.py
It sets QT_QPA_PLATFORM=offscreen so it works in CI / over SSH with no screen.
Exit 0 = the UI builds and renders; any construction error raises and fails.
"""
import os
import sys
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QDate, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QContextMenuEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
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

    # 설정 패널 여닫기. 배경 클릭으로 닫는 규칙은 "아무도 안 가져간 클릭 = 배경"
    # 이라는 전제 위에 서 있어서, 중간의 위젯 하나가 이벤트를 삼키거나 흘려보내는
    # 순간 조용히 깨진다 — 눈으로만 확인할 수 없으니 여기서 눌러 본다.
    conn, panel = win.page_conn, win.page_conn.settings_panel

    def click(w, pos):
        QTest.mouseClick(w, Qt.LeftButton, Qt.KeyboardModifiers(), pos)
        app.processEvents()

    click(conn.gear_btn, conn.gear_btn.rect().center())
    assert panel.isVisible(), "설정 버튼으로 패널이 열리지 않았다"
    click(panel, QPoint(panel.width() // 2, 40))
    assert panel.isVisible(), "패널 안을 눌렀는데 닫혔다"
    click(conn.host, conn.host.rect().center())
    assert panel.isVisible(), "입력란을 눌렀는데 패널이 닫혔다"
    click(conn, QPoint(12, 12))
    assert not panel.isVisible(), "배경을 눌렀는데 패널이 닫히지 않았다"
    click(conn.gear_btn, conn.gear_btn.rect().center())
    click(conn.gear_btn, conn.gear_btn.rect().center())
    assert not panel.isVisible(), "설정 버튼이 닫았다가 다시 열었다"

    win.goto(1)
    win.page_table._fill_chips([f"sample_{i}_aud" for i in range(30)] + demo.tables())
    win.page_table._filter_chips("sample_1")
    win.page_table._render_preview(demo.preview())

    services.confirm_table(st, demo.DEFAULT_TABLE, "id")
    win.goto(2)
    win.page_hist.on_enter()
    win.page_hist._render(services.get_history(st, demo.example_id(demo.DEFAULT_TABLE)))

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

    # 전체 이력 모드 — 배치 리비전이 가장 넓은 product_aud 로 렌더한다.
    win.page_table._render_preview(demo.preview("product_aud"))
    services.confirm_table(st, "product_aud", None)
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
    today = demo._TODAY.date()
    month = (today - timedelta(days=29), today)
    ph.range_row.show()
    ph._preset, ph._loaded = "all", False
    ph._show_count(services.count_full_history(st))
    ph._pick_preset("365d")             # fills the pickers, re-tallies
    ph._set_dates(*(QDate(d.year, d.month, d.day) for d in month))
    ph._on_date_edited()                # -> 직접 선택
    ph._applied = month
    scoped = services.get_full_history(st, None, services.FULL_HISTORY_PAGE, *ph._applied)
    ph._cs_nodes = list(scoped["timeline"])
    ph._cs_min_rev, ph._cs_has_more = scoped["min_rev"], False
    ph._render_changeset()
    ph._show_count(services.count_full_history(st, *ph._applied))
    ph._loaded = False
    ph._empty_full()                    # empty state names the applied period
    app.processEvents()

    # 여러 레코드가 든 리비전 카드 — 커서가 놓인 레코드의 스냅샷을 고른다.
    # 그 리비전만 그린다: 타임라인을 통째로 올리면 화면 밖 카드는 레이아웃이
    # 잡히지 않아 좌표로 때릴 수가 없다.
    widest = max(r["timeline"], key=lambda n: n["record_count"])
    ph._cs_nodes = [widest]
    ph._applied, ph._cs_has_more = None, False
    ph._render_changeset()
    app.processEvents()                 # let the layout settle before hit-testing
    card, want = ph._cards[0], widest["record_count"]
    zones = card._zones
    assert len(zones) == want >= 3, f"expected {want} record blocks, got {len(zones)}"
    y = zones[1][0].mapTo(card, QPoint(0, 0)).y() + 8
    assert card._record_at(QPoint(120, y)) is zones[1][1]
    card.contextMenuEvent(QContextMenuEvent(
        QContextMenuEvent.Mouse, QPoint(120, y), card.mapToGlobal(QPoint(120, y))))
    app.processEvents()
    for w in app.topLevelWidgets():
        if isinstance(w, SnapshotPopup):
            w.close()
    app.processEvents()

    # 고볼륨 테이블: 첫 페이지를 그린 뒤 "이전 리비전 더 보기" 로 이어붙인다.
    services.confirm_table(st, "order_aud", None)
    ph.on_enter()
    ph._mode = "full"
    page1 = services.get_full_history(st)
    assert page1["has_more"], "order_aud 샘플이 한 페이지에 다 들어가면 페이징을 못 본다"
    ph._cs_nodes = list(page1["timeline"])
    ph._cs_min_rev, ph._cs_has_more = page1["min_rev"], True
    ph._render_changeset()
    page2 = services.get_full_history(st, ph._cs_min_rev)
    ph._cs_nodes.extend(page2["timeline"])
    ph._cs_min_rev, ph._cs_has_more = page2["min_rev"], page2["has_more"]
    ph._render_changeset()              # 누적 렌더 — 실제 "더 보기" 이후 화면
    app.processEvents()

    print(f"[smoke] OK - MainWindow built; search + full-history "
          f"({len(ph._cs_nodes)} revisions over 2 pages) + date-range + snapshot popup rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
