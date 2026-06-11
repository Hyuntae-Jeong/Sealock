"""AudViewer entry point — a PySide6 (Qt) desktop app.

Run:  python app.py        (or double-click run.vbs / run.bat)
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from audviewer.ui.theme import QSS
from audviewer.ui.window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AudViewer")
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
