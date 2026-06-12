"""AudViewer entry point — a PySide6 (Qt) desktop app.

Run:  python app.py        (or double-click run.vbs / run.bat)
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from audviewer.resources import app_icon
from audviewer.ui.theme import QSS
from audviewer.ui.window import MainWindow


def _set_windows_app_id() -> None:
    """Give the process an explicit AppUserModelID so Windows shows AudViewer's
    own taskbar icon instead of python's. No-op elsewhere / on failure."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AudViewer")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("AudViewer")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
