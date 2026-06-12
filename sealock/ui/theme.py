"""Color palettes and the global Qt style sheet (QSS) for Sealock.

Two themes — light and dark — share one set of semantic keys. The active
palette lives in the module-level dict ``C``, swapped *in place* by
``set_palette`` so that widgets reading ``C[...]`` at paint time (and modules
that imported ``C``) all see the new values without re-importing. Call
``qss()`` for the style sheet of the current palette and re-apply it after a
swap; variants within a theme are still selected via objectName (e.g. #primary)
or the dynamic ``state`` property (re-polished at runtime through repolish()).
"""
from __future__ import annotations

# ── palettes ────────────────────────────────────────────────────────────
# Every key exists in both palettes. LIGHT keeps the original look; DARK is a
# soft dark-indigo theme tuned so text stays legible on its own surfaces.
LIGHT = {
    "bg": "#eef1f7",
    "surface": "#ffffff",
    "surface2": "#f7f8fc",
    "surface3": "#f1f3fb",
    "border": "#e4e7f0",
    "border_strong": "#d4d9e8",
    "text": "#1f2440",
    "text_soft": "#5b6178",
    "text_faint": "#939ab5",
    "rail": "#d9deea",

    "primary": "#5b5bf0",
    "primary_700": "#3f3bc7",
    "primary_hover": "#4b48e0",
    "primary_soft": "#eceaff",
    "primary_soft_hover": "#e2dfff",
    "primary_tint": "#f4f3fe",
    "primary_dis_bg": "#c7c7f3",
    "primary_dis_fg": "#eef0ff",
    "secondary_dis_fg": "#b0aee0",

    "green": "#16a34a",
    "green_text": "#157f3b",
    "blue": "#2563eb",
    "red": "#dc2626",

    "success_bg": "#e7f7ec",
    "success_border": "#bfe9cd",
    "danger_bg": "#fdecec",
    "danger_border": "#f4c9c9",
    "danger_text": "#b91c1c",
    "danger_strong": "#b3261e",
    "info_bg": "#e8f0fe",
    "info_border": "#cfe0fb",
    "info_text": "#1d4ed8",
    "warn_bg": "#fff7e6",
    "warn_border": "#f3dca6",
    "warn_text": "#b45309",

    "overlay": "#2a2f4a",
    "overlay_text": "#ffffff",
    "on_primary": "#ffffff",
    "scroll": "#d4d9e8",
    "scroll_hover": "#b9bfd2",
}

DARK = {
    "bg": "#13151d",
    "surface": "#1b1e29",
    "surface2": "#222536",
    "surface3": "#1f2230",
    "border": "#2d3142",
    "border_strong": "#3b4055",
    "text": "#e7e9f2",
    "text_soft": "#abb1c6",
    "text_faint": "#7d84a0",
    "rail": "#343a4e",

    "primary": "#6f6df6",
    "primary_700": "#a5a2ff",
    "primary_hover": "#7e7cf8",
    "primary_soft": "#2b2c55",
    "primary_soft_hover": "#363873",
    "primary_tint": "#20224a",
    "primary_dis_bg": "#343663",
    "primary_dis_fg": "#8f90c0",
    "secondary_dis_fg": "#6f6f9e",

    "green": "#22c55e",
    "green_text": "#4ade80",
    "blue": "#60a5fa",
    "red": "#f87171",

    "success_bg": "#15301f",
    "success_border": "#1f5235",
    "danger_bg": "#381a1c",
    "danger_border": "#5d2a2d",
    "danger_text": "#f87171",
    "danger_strong": "#c2403a",
    "info_bg": "#17243f",
    "info_border": "#2a3a5e",
    "info_text": "#93b4f7",
    "warn_bg": "#2e2611",
    "warn_border": "#574a20",
    "warn_text": "#f0b760",

    "overlay": "#2f3450",
    "overlay_text": "#ffffff",
    "on_primary": "#ffffff",
    "scroll": "#3b4258",
    "scroll_hover": "#4d5570",
}

MONO = '"Consolas", "D2Coding", "Cascadia Mono", monospace'

# Active palette — populated in place by set_palette() so existing references
# (imports, QPainter widgets) observe swaps without re-importing.
C: dict[str, str] = {}


def _build_qss(c: dict[str, str]) -> str:
    """The full style sheet for palette ``c``."""
    return f"""
* {{ font-family: "Malgun Gothic", "Segoe UI", "Noto Sans KR", sans-serif; }}
QWidget#root {{ background: {c['bg']}; }}
QToolTip {{ background: {c['overlay']}; color: {c['overlay_text']}; border: none; padding: 6px 9px; border-radius: 6px; }}

/* ── topbar ── */
QFrame#topbar {{ background: {c['surface']}; border: none; border-bottom: 1px solid {c['border']}; }}
QLabel#brandMark {{ background: transparent; }}
QLabel#brandTitle {{ font-size: 16px; font-weight: 700; color: {c['text']}; }}
QLabel#brandSub {{ font-size: 11px; color: {c['text_faint']}; }}

/* ── theme toggle ── */
QPushButton#themeToggle {{ background: transparent; border: none; border-radius: 8px; }}

/* ── stepper ── */
QLabel#stepNum {{ background: {c['surface']}; border: 2px solid {c['border_strong']}; color: {c['text_faint']};
    border-radius: 13px; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; font-weight: 700; }}
QLabel#stepNum[state="active"] {{ background: {c['primary']}; border-color: {c['primary']}; color: {c['on_primary']}; }}
QLabel#stepNum[state="done"]   {{ background: {c['green']}; border-color: {c['green']}; color: {c['on_primary']}; }}
QLabel#stepLabel {{ color: {c['text_faint']}; font-size: 13px; font-weight: 600; }}
QLabel#stepLabel[state="active"], QLabel#stepLabel[state="done"] {{ color: {c['text']}; }}
QFrame#stepLine {{ background: {c['border_strong']}; border: none; max-height: 2px; min-height: 2px; }}
QFrame#stepLine[state="done"] {{ background: {c['primary']}; }}

/* ── cards ── */
QFrame#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 16px; }}
QLabel#cardTitle {{ font-size: 18px; font-weight: 700; color: {c['text']}; }}
QLabel#cardDesc {{ font-size: 13px; color: {c['text_soft']}; }}

/* ── inputs ── */
QLabel#fieldLabel {{ font-size: 12px; font-weight: 600; color: {c['text_soft']}; }}
QLineEdit, QComboBox {{ background: {c['surface2']}; border: 2px solid {c['border']}; border-radius: 10px;
    padding: 0 12px; min-height: 38px; color: {c['text']}; font-size: 13px;
    selection-background-color: {c['primary']}; selection-color: {c['on_primary']}; }}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{ border: 2px solid {c['primary']}; background: {c['surface']}; }}
QLineEdit::placeholder {{ color: {c['text_faint']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border_strong']};
    border-radius: 8px; selection-background-color: {c['primary_soft']}; selection-color: {c['primary_700']}; outline: none; padding: 4px; }}

/* ── buttons ── */
QPushButton {{ border-radius: 10px; padding: 0 18px; min-height: 38px; font-size: 13px; font-weight: 600; border: 2px solid transparent; }}
QPushButton#primary {{ background: {c['primary']}; color: {c['on_primary']}; }}
QPushButton#primary:hover {{ background: {c['primary_hover']}; }}
QPushButton#primary:disabled {{ background: {c['primary_dis_bg']}; color: {c['primary_dis_fg']}; }}
QPushButton#secondary {{ background: {c['primary_soft']}; color: {c['primary_700']}; }}
QPushButton#secondary:hover {{ background: {c['primary_soft_hover']}; }}
QPushButton#secondary:disabled {{ color: {c['secondary_dis_fg']}; }}
QPushButton#ghost {{ background: transparent; color: {c['text_soft']}; border: 2px solid {c['border_strong']}; }}
QPushButton#ghost:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QPushButton#chip {{ background: {c['surface2']}; color: {c['text_soft']}; border: 1px solid {c['border_strong']};
    border-radius: 14px; min-height: 26px; padding: 0 12px; font-size: 12px; font-family: {MONO}; }}
QPushButton#chip:hover {{ background: {c['primary_soft']}; color: {c['primary_700']}; border-color: {c['primary']}; }}

/* ── connection status ── */
QLabel#statusOk {{ background: {c['success_bg']}; color: {c['green_text']}; border: 1px solid {c['success_border']}; border-radius: 10px; padding: 11px 14px; font-weight: 600; }}
QLabel#statusErr {{ background: {c['danger_bg']}; color: {c['danger_text']}; border: 1px solid {c['danger_border']}; border-radius: 10px; padding: 11px 14px; font-weight: 600; }}
QLabel#statusBusy {{ background: {c['surface2']}; color: {c['text_soft']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 11px 14px; font-weight: 600; }}

/* ── preview (step 2) ── */
QLabel#metaBadge {{ background: {c['surface2']}; border: 1px solid {c['border']}; color: {c['text_soft']}; border-radius: 8px; padding: 6px 11px; font-size: 12px; }}
QLabel#metaGood {{ background: {c['success_bg']}; border: 1px solid {c['success_border']}; color: {c['green_text']}; border-radius: 8px; padding: 6px 11px; font-size: 12px; }}
QLabel#metaWarn {{ background: {c['warn_bg']}; border: 1px solid {c['warn_border']}; color: {c['warn_text']}; border-radius: 8px; padding: 6px 11px; font-size: 12px; }}
QLabel#sectionLabel {{ color: {c['text_faint']}; font-size: 11px; font-weight: 700; }}
QLabel#sysPill {{ background: {c['surface2']}; border: 1px solid {c['border']}; color: {c['text_soft']}; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-family: {MONO}; }}
QFrame#tableHead {{ border: none; border-bottom: 1px solid {c['border']}; }}
QFrame#tableRow {{ border: none; border-bottom: 1px solid {c['border']}; }}
QLabel#thCell {{ color: {c['text_faint']}; font-size: 11px; font-weight: 700; }}
QLabel#tdName {{ color: {c['text']}; font-weight: 600; font-size: 13px; font-family: {MONO}; }}
QLabel#tdType {{ color: {c['text_soft']}; font-size: 12px; font-family: {MONO}; }}
QLabel#flagYes {{ color: {c['green']}; font-weight: 700; font-size: 12px; font-family: {MONO}; }}
QLabel#flagNo {{ color: {c['text_faint']}; font-size: 12px; }}

/* ── summary + timeline (step 3) ── */
QFrame#summaryBar {{ background: {c['surface3']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QLabel#sumK {{ color: {c['text_faint']}; font-size: 11px; font-weight: 600; }}
QLabel#sumV {{ color: {c['text']}; font-size: 16px; font-weight: 700; }}
QFrame#tlCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; outline: none; }}
QFrame#tlCard[selected="true"] {{ border: 1px solid {c['primary']}; background: {c['primary_tint']}; }}
QFrame#tlHead {{ border: none; border-bottom: 1px solid {c['border']}; }}
QLabel#revChip {{ background: {c['surface2']}; border: 1px solid {c['border_strong']}; color: {c['text_soft']};
    border-radius: 6px; padding: 2px 9px; font-size: 12px; font-weight: 700; font-family: {MONO}; }}
QLabel#typeCreate {{ background: {c['success_bg']}; color: {c['green_text']}; border-radius: 9px; padding: 3px 11px; font-size: 11px; font-weight: 700; }}
QLabel#typeUpdate {{ background: {c['info_bg']}; color: {c['info_text']}; border-radius: 9px; padding: 3px 11px; font-size: 11px; font-weight: 700; }}
QLabel#typeDelete {{ background: {c['danger_bg']}; color: {c['danger_text']}; border-radius: 9px; padding: 3px 11px; font-size: 11px; font-weight: 700; }}
QLabel#tlTime {{ color: {c['text_faint']}; font-size: 12px; font-family: {MONO}; }}
QLabel#tlChevron {{ color: {c['text_faint']}; font-size: 13px; padding: 0 2px; }}
QLabel#tlChevron:hover {{ color: {c['primary']}; }}
QLabel#colName {{ color: {c['text']}; font-weight: 600; font-size: 13px; font-family: {MONO}; }}
QLabel#valOld {{ background: {c['danger_bg']}; color: {c['danger_text']}; border: 1px solid {c['danger_border']}; border-radius: 7px; padding: 3px 9px; font-size: 12px; font-family: {MONO}; }}
QLabel#valNew {{ background: {c['success_bg']}; color: {c['green_text']}; border: 1px solid {c['success_border']}; border-radius: 7px; padding: 3px 9px; font-size: 12px; font-family: {MONO}; }}
QLabel#valNull {{ background: {c['surface2']}; color: {c['text_faint']}; border: 1px solid {c['border_strong']}; border-radius: 7px; padding: 3px 9px; font-size: 12px; font-family: {MONO}; }}
QLabel#arrow {{ color: {c['text_faint']}; font-size: 15px; font-weight: 700; }}
QLabel#tag {{ background: {c['primary_soft']}; color: {c['primary_700']}; border-radius: 5px; padding: 2px 7px; font-size: 10px; font-weight: 700; }}
QLabel#flagChanged {{ background: {c['info_bg']}; color: {c['info_text']}; border: 1px solid {c['info_border']}; border-radius: 7px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
QLabel#delNote {{ color: {c['danger_text']}; font-weight: 600; font-size: 13px; }}
QLabel#noChange {{ color: {c['text_faint']}; font-size: 12px; font-style: italic; }}
QLabel#emptyTitle {{ color: {c['text_soft']}; font-size: 14px; }}
QLabel#emptySub {{ color: {c['text_faint']}; font-size: 12px; }}

/* ── scroll + toast ── */
QFrame#chipsArea {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['scroll']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['scroll_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLabel#toast {{ background: {c['overlay']}; color: {c['overlay_text']}; border-radius: 11px; padding: 12px 18px; font-size: 13px; font-weight: 600; }}
QLabel#toastErr {{ background: {c['danger_strong']}; color: #ffffff; border-radius: 11px; padding: 12px 18px; font-size: 13px; font-weight: 600; }}
QLabel#copyToast {{ color: {c['text_soft']}; font-size: 12px; font-weight: 700; }}
"""


def set_palette(name: str) -> str:
    """Activate 'light' or 'dark' in place; returns the resolved name."""
    name = "dark" if str(name).lower() == "dark" else "light"
    C.clear()
    C.update(DARK if name == "dark" else LIGHT)
    return name


def is_dark() -> bool:
    """True when the dark palette is currently active."""
    return C.get("bg") == DARK["bg"]


def qss() -> str:
    """Style sheet for the currently active palette."""
    return _build_qss(C)


set_palette("light")  # default until app.py applies the saved choice
# Back-compat: a module-level snapshot of the light style sheet.
QSS = qss()
