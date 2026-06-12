"""Color palette and the global Qt style sheet (QSS) for Sealock.

A single light theme: soft surfaces, an indigo accent, rounded cards. Variants
are selected via objectName (e.g. #primary) or the dynamic ``state`` property
(re-polished at runtime through widgets.repolish()).
"""

# Palette (kept in sync with the QSS below; handy for QPainter-drawn widgets).
C = {
    "bg": "#eef1f7",
    "surface": "#ffffff",
    "surface2": "#f7f8fc",
    "border": "#e4e7f0",
    "border_strong": "#d4d9e8",
    "text": "#1f2440",
    "text_soft": "#5b6178",
    "text_faint": "#939ab5",
    "primary": "#5b5bf0",
    "primary_700": "#3f3bc7",
    "green": "#16a34a",
    "green_text": "#157f3b",
    "blue": "#2563eb",
    "red": "#dc2626",
    "rail": "#d9deea",
}

MONO = '"Consolas", "D2Coding", "Cascadia Mono", monospace'

QSS = f"""
* {{ font-family: "Malgun Gothic", "Segoe UI", "Noto Sans KR", sans-serif; }}
QWidget#root {{ background: {C['bg']}; }}
QToolTip {{ background: #2a2f4a; color: #fff; border: none; padding: 6px 9px; border-radius: 6px; }}

/* ── topbar ── */
QFrame#topbar {{ background: #ffffff; border: none; border-bottom: 1px solid {C['border']}; }}
QLabel#brandMark {{ background: transparent; }}
QLabel#brandTitle {{ font-size: 16px; font-weight: 700; color: {C['text']}; }}
QLabel#brandSub {{ font-size: 11px; color: {C['text_faint']}; }}

/* ── stepper ── */
QLabel#stepNum {{ background: #ffffff; border: 2px solid {C['border_strong']}; color: {C['text_faint']};
    border-radius: 13px; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; font-weight: 700; }}
QLabel#stepNum[state="active"] {{ background: {C['primary']}; border-color: {C['primary']}; color: #ffffff; }}
QLabel#stepNum[state="done"]   {{ background: {C['green']}; border-color: {C['green']}; color: #ffffff; }}
QLabel#stepLabel {{ color: {C['text_faint']}; font-size: 13px; font-weight: 600; }}
QLabel#stepLabel[state="active"], QLabel#stepLabel[state="done"] {{ color: {C['text']}; }}
QFrame#stepLine {{ background: {C['border_strong']}; border: none; max-height: 2px; min-height: 2px; }}
QFrame#stepLine[state="done"] {{ background: {C['primary']}; }}

/* ── cards ── */
QFrame#card {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 16px; }}
QLabel#cardTitle {{ font-size: 18px; font-weight: 700; color: {C['text']}; }}
QLabel#cardDesc {{ font-size: 13px; color: {C['text_soft']}; }}

/* ── inputs ── */
QLabel#fieldLabel {{ font-size: 12px; font-weight: 600; color: {C['text_soft']}; }}
QLineEdit, QComboBox {{ background: {C['surface2']}; border: 2px solid {C['border']}; border-radius: 10px;
    padding: 0 12px; min-height: 38px; color: {C['text']}; font-size: 13px;
    selection-background-color: {C['primary']}; selection-color: #ffffff; }}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{ border: 2px solid {C['primary']}; background: #ffffff; }}
QLineEdit::placeholder {{ color: {C['text_faint']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #ffffff; border: 1px solid {C['border_strong']};
    border-radius: 8px; selection-background-color: #eceaff; selection-color: {C['primary_700']}; outline: none; padding: 4px; }}

/* ── buttons ── */
QPushButton {{ border-radius: 10px; padding: 0 18px; min-height: 38px; font-size: 13px; font-weight: 600; border: 2px solid transparent; }}
QPushButton#primary {{ background: {C['primary']}; color: #ffffff; }}
QPushButton#primary:hover {{ background: #4b48e0; }}
QPushButton#primary:disabled {{ background: #c7c7f3; color: #eef0ff; }}
QPushButton#secondary {{ background: #eceaff; color: {C['primary_700']}; }}
QPushButton#secondary:hover {{ background: #e2dfff; }}
QPushButton#secondary:disabled {{ color: #b0aee0; }}
QPushButton#ghost {{ background: transparent; color: {C['text_soft']}; border: 2px solid {C['border_strong']}; }}
QPushButton#ghost:hover {{ background: {C['surface2']}; color: {C['text']}; }}
QPushButton#chip {{ background: {C['surface2']}; color: {C['text_soft']}; border: 1px solid {C['border_strong']};
    border-radius: 14px; min-height: 26px; padding: 0 12px; font-size: 12px; font-family: {MONO}; }}
QPushButton#chip:hover {{ background: #eceaff; color: {C['primary_700']}; border-color: {C['primary']}; }}

/* ── connection status ── */
QLabel#statusOk {{ background: #e7f7ec; color: {C['green_text']}; border: 1px solid #bfe9cd; border-radius: 10px; padding: 11px 14px; font-weight: 600; }}
QLabel#statusErr {{ background: #fdecec; color: #b91c1c; border: 1px solid #f4c9c9; border-radius: 10px; padding: 11px 14px; font-weight: 600; }}
QLabel#statusBusy {{ background: {C['surface2']}; color: {C['text_soft']}; border: 1px solid {C['border']}; border-radius: 10px; padding: 11px 14px; font-weight: 600; }}

/* ── preview (step 2) ── */
QLabel#metaBadge {{ background: {C['surface2']}; border: 1px solid {C['border']}; color: {C['text_soft']}; border-radius: 8px; padding: 6px 11px; font-size: 12px; }}
QLabel#metaGood {{ background: #e7f7ec; border: 1px solid #bfe9cd; color: {C['green_text']}; border-radius: 8px; padding: 6px 11px; font-size: 12px; }}
QLabel#metaWarn {{ background: #fff7e6; border: 1px solid #f3dca6; color: #b45309; border-radius: 8px; padding: 6px 11px; font-size: 12px; }}
QLabel#sectionLabel {{ color: {C['text_faint']}; font-size: 11px; font-weight: 700; }}
QLabel#sysPill {{ background: {C['surface2']}; border: 1px solid {C['border']}; color: {C['text_soft']}; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-family: {MONO}; }}
QFrame#tableHead {{ border: none; border-bottom: 1px solid {C['border']}; }}
QFrame#tableRow {{ border: none; border-bottom: 1px solid {C['border']}; }}
QLabel#thCell {{ color: {C['text_faint']}; font-size: 11px; font-weight: 700; }}
QLabel#tdName {{ color: {C['text']}; font-weight: 600; font-size: 13px; font-family: {MONO}; }}
QLabel#tdType {{ color: {C['text_soft']}; font-size: 12px; font-family: {MONO}; }}
QLabel#flagYes {{ color: {C['green']}; font-weight: 700; font-size: 12px; font-family: {MONO}; }}
QLabel#flagNo {{ color: {C['text_faint']}; font-size: 12px; }}

/* ── summary + timeline (step 3) ── */
QFrame#summaryBar {{ background: #f1f3fb; border: 1px solid {C['border']}; border-radius: 10px; }}
QLabel#sumK {{ color: {C['text_faint']}; font-size: 11px; font-weight: 600; }}
QLabel#sumV {{ color: {C['text']}; font-size: 16px; font-weight: 700; }}
QFrame#tlCard {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; outline: none; }}
QFrame#tlCard[selected="true"] {{ border: 1px solid {C['primary']}; background: #f4f3fe; }}
QFrame#tlHead {{ border: none; border-bottom: 1px solid {C['border']}; }}
QLabel#revChip {{ background: {C['surface2']}; border: 1px solid {C['border_strong']}; color: {C['text_soft']};
    border-radius: 6px; padding: 2px 9px; font-size: 12px; font-weight: 700; font-family: {MONO}; }}
QLabel#typeCreate {{ background: #e7f7ec; color: {C['green_text']}; border-radius: 9px; padding: 3px 11px; font-size: 11px; font-weight: 700; }}
QLabel#typeUpdate {{ background: #e8f0fe; color: #1d4ed8; border-radius: 9px; padding: 3px 11px; font-size: 11px; font-weight: 700; }}
QLabel#typeDelete {{ background: #fdecec; color: #b91c1c; border-radius: 9px; padding: 3px 11px; font-size: 11px; font-weight: 700; }}
QLabel#tlTime {{ color: {C['text_faint']}; font-size: 12px; font-family: {MONO}; }}
QLabel#tlChevron {{ color: {C['text_faint']}; font-size: 13px; padding: 0 2px; }}
QLabel#tlChevron:hover {{ color: {C['primary']}; }}
QLabel#colName {{ color: {C['text']}; font-weight: 600; font-size: 13px; font-family: {MONO}; }}
QLabel#valOld {{ background: #fdecec; color: #b42318; border: 1px solid #f4c9c9; border-radius: 7px; padding: 3px 9px; font-size: 12px; font-family: {MONO}; }}
QLabel#valNew {{ background: #e7f7ec; color: {C['green_text']}; border: 1px solid #bfe9cd; border-radius: 7px; padding: 3px 9px; font-size: 12px; font-family: {MONO}; }}
QLabel#valNull {{ background: {C['surface2']}; color: {C['text_faint']}; border: 1px solid {C['border_strong']}; border-radius: 7px; padding: 3px 9px; font-size: 12px; font-family: {MONO}; }}
QLabel#arrow {{ color: {C['text_faint']}; font-size: 15px; font-weight: 700; }}
QLabel#tag {{ background: #eceaff; color: {C['primary_700']}; border-radius: 5px; padding: 2px 7px; font-size: 10px; font-weight: 700; }}
QLabel#flagChanged {{ background: #e8f0fe; color: #1d4ed8; border: 1px solid #cfe0fb; border-radius: 7px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
QLabel#delNote {{ color: #b91c1c; font-weight: 600; font-size: 13px; }}
QLabel#noChange {{ color: {C['text_faint']}; font-size: 12px; font-style: italic; }}
QLabel#emptyTitle {{ color: {C['text_soft']}; font-size: 14px; }}
QLabel#emptySub {{ color: {C['text_faint']}; font-size: 12px; }}

/* ── scroll + toast ── */
QFrame#chipsArea {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 10px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border_strong']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #b9bfd2; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLabel#toast {{ background: #2a2f4a; color: #ffffff; border-radius: 11px; padding: 12px 18px; font-size: 13px; font-weight: 600; }}
QLabel#toastErr {{ background: #b3261e; color: #ffffff; border-radius: 11px; padding: 12px 18px; font-size: 13px; font-weight: 600; }}
QLabel#copyToast {{ color: #5b6178; font-size: 12px; font-weight: 700; }}
"""
