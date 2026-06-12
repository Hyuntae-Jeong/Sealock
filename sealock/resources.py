"""Locate bundled assets and build the app icon — works in dev and when frozen.

PyInstaller unpacks bundled data under ``sys._MEIPASS``; a normal ``python``
run falls back to the package directory. Keep every runtime image asset in
``sealock/assets/`` so both lookups line up.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon


def asset_path(name: str) -> str:
    """Absolute path to ``sealock/assets/<name>`` (dev or PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        base = os.path.join(sys._MEIPASS, "sealock", "assets")
    else:
        base = os.path.join(os.path.dirname(__file__), "assets")
    return os.path.join(base, name)


def app_icon() -> QIcon:
    """Multi-size application icon (window title bar + Windows taskbar)."""
    return QIcon(asset_path("app.ico"))
