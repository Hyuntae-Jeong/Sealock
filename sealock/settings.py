"""Persisted UI preferences, kept separate from DB credentials.

Stored via :class:`QSettings` — the platform-native store (the registry under
``HKCU\\Software\\Sealock`` on Windows), so no extra file lands in the project.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

_ORG, _APP = "Sealock", "Sealock"


def _store() -> QSettings:
    return QSettings(_ORG, _APP)


def load_theme() -> str:
    """The saved theme name ('light' or 'dark'); defaults to 'light'."""
    value = _store().value("ui/theme", "light")
    return "dark" if str(value).lower() == "dark" else "light"


def save_theme(name: str) -> None:
    """Persist the chosen theme name."""
    _store().setValue("ui/theme", "dark" if name == "dark" else "light")
