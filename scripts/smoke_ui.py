"""Headless (offscreen) smoke test — constructs the whole Qt UI and renders the
demo preview + timeline without a display or a database.

Run:  python scripts/smoke_ui.py
It sets QT_QPA_PLATFORM=offscreen so it works in CI / over SSH with no screen.
Exit 0 = the UI builds and renders; any construction error raises and fails.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from sealock import demo, services  # noqa: E402
from sealock.ui.theme import QSS  # noqa: E402
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
    app.processEvents()

    print("[smoke] OK - MainWindow built; search + full-history toggle views rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
