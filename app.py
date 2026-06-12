"""Sealock entry point — a PySide6 (Qt) desktop app.

Run:  python app.py        (or double-click run.vbs / run.bat)
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from sealock.resources import app_icon
from sealock.ui.splash import SplashScreen
from sealock.ui.theme import QSS
from sealock.ui.window import MainWindow


def _set_windows_app_id() -> None:
    """Give the process an explicit AppUserModelID so Windows shows Sealock's
    own taskbar icon instead of python's. No-op elsewhere / on failure."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sealock")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("Sealock")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(QSS)

    window = MainWindow()  # built behind the splash; shown when it fades out

    splash = SplashScreen()
    splash.start(on_done=window.show)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
