"""Reusable Qt widgets and helpers: async worker, stepper, timeline pieces."""
from __future__ import annotations

import math

from PySide6.QtCore import (Property, QEasingCurve, QObject, QPoint, QPointF,
                            QPropertyAnimation, QRect, QRectF, QRunnable, QSize,
                            Qt, QThreadPool, QTimer, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QRadialGradient)
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..resources import asset_path
from .theme import C


# ── style helpers ───────────────────────────────────────────────────────
def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def set_state(w: QWidget, state: str) -> None:
    w.setProperty("state", state)
    repolish(w)


def soft_shadow(w: QWidget, blur=26, dy=6, alpha=28) -> None:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(31, 36, 64, alpha))
    w.setGraphicsEffect(eff)


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        if child:
            child.deleteLater()
        elif item.layout():
            clear_layout(item.layout())


# ── async ───────────────────────────────────────────────────────────────
class _Signals(QObject):
    success = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self):  # noqa: D401 - runs on a thread-pool thread
        try:
            self.signals.success.emit(self.fn(*self.args, **self.kwargs))
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))


# Workers must be kept referenced until they finish, otherwise Python may GC the
# Worker (and its signals QObject) while the pool thread is still running — which
# manifests as a hung callback or a hard crash. We hold each one here until it
# emits, then release it.
_active_workers: set = set()


def run_async(fn, on_ok, on_err=None, *args, **kwargs) -> None:
    w = Worker(fn, *args, **kwargs)
    _active_workers.add(w)

    def _release(*_):
        _active_workers.discard(w)

    w.signals.success.connect(on_ok)
    if on_err:
        w.signals.error.connect(on_err)
    w.signals.success.connect(_release)
    w.signals.error.connect(_release)
    QThreadPool.globalInstance().start(w)


# ── small factories ─────────────────────────────────────────────────────
def button(text: str, kind: str = "primary") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    return b


def field(label: str, placeholder: str = "", echo: bool = False) -> tuple[QWidget, QLineEdit]:
    wrap = QWidget()
    v = QVBoxLayout(wrap)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(7)
    lab = QLabel(label)
    lab.setObjectName("fieldLabel")
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    if echo:
        edit.setEchoMode(QLineEdit.Password)
    v.addWidget(lab)
    v.addWidget(edit)
    return wrap, edit


def hline_label(text: str, obj: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(obj)
    return lab


# ── flow layout (wraps children to next line) ───────────────────────────
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hspace=8, vspace=8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._items: list = []
        self._h, self._v = hspace, vspace

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            w = it.sizeHint().width()
            h = it.sizeHint().height()
            if x + w > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + self._v
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x += w + self._h
            line_h = max(line_h, h)
        return y + line_h - rect.y()


# ── stepper ─────────────────────────────────────────────────────────────
class _Step(QWidget):
    """One clickable step: a number circle plus its text label."""

    clicked = Signal(int)  # 0-based index of this step

    def __init__(self, index: int, text: str):
        super().__init__()
        self._index = index
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.num = QLabel(str(index + 1))
        self.num.setObjectName("stepNum")
        self.num.setAlignment(Qt.AlignCenter)
        self.lab = QLabel(text)
        self.lab.setObjectName("stepLabel")
        # 라벨 위 클릭도 통째로 _Step이 받도록 마우스 이벤트를 통과시킨다
        self.num.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        h.addWidget(self.num)
        h.addWidget(self.lab)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(e)


class Stepper(QWidget):
    step_clicked = Signal(int)  # 0-based index the user clicked

    def __init__(self, labels: list[str]):
        super().__init__()
        self._steps: list[_Step] = []
        self._lines: list[QFrame] = []
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for i, text in enumerate(labels):
            if i > 0:
                line = QFrame()
                line.setObjectName("stepLine")
                line.setFixedWidth(30)
                self._lines.append(line)
                h.addWidget(line)
            step = _Step(i, text)
            step.clicked.connect(self.step_clicked)
            self._steps.append(step)
            h.addWidget(step)
        self.set_current(1)

    def set_current(self, n: int) -> None:
        for i, step in enumerate(self._steps, start=1):
            state = "done" if i < n else "active" if i == n else "todo"
            step.num.setText("✓" if state == "done" else str(i))
            set_state(step.num, state)
            set_state(step.lab, state)
            # 완료된 단계만 클릭해 되돌아갈 수 있음 → 그 단계에만 손가락 커서
            step.setCursor(Qt.PointingHandCursor if state == "done"
                           else Qt.ArrowCursor)
        for i, line in enumerate(self._lines, start=1):
            set_state(line, "done" if n > i else "todo")


# ── brand mark (mascot + sunrise/sunset, doubles as the theme toggle) ─────
def _draw_sun(p: QPainter, x: float, y: float, r: float) -> None:
    p.setPen(QPen(QColor("#FFB23E"), 1.7, Qt.SolidLine, Qt.RoundCap))
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(x + math.cos(a) * (r + 2.4), y + math.sin(a) * (r + 2.4)),
                   QPointF(x + math.cos(a) * (r + 4.7), y + math.sin(a) * (r + 4.7)))
    g = QRadialGradient(x - 1.6, y - 1.6, r * 1.7)
    g.setColorAt(0.0, QColor("#FFE680"))
    g.setColorAt(1.0, QColor("#FF9F1C"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), r, r)


def _draw_moon(p: QPainter, x: float, y: float, r: float) -> None:
    disc = QPainterPath()
    disc.addEllipse(QPointF(x, y), r, r)
    cut = QPainterPath()
    cut.addEllipse(QPointF(x + 3.4, y - 2.6), r, r)
    g = QLinearGradient(x - r, y - r, x + r, y + r)
    g.setColorAt(0.0, QColor("#FFF3B0"))
    g.setColorAt(1.0, QColor("#F6C544"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(disc.subtracted(cut))


class BrandMark(QWidget):
    """The mascot with a sunrise / sunset orbiting behind it — also the theme
    toggle. Sun and moon ride one big circle centred below the widget, so only
    the arc's top shows; the mascot is painted in front (transparent PNG), so
    the bodies are hidden as they swing behind it and only appear in the open
    upper-left — they look like they rise and set from behind the seal. Clicking
    emits ``clicked``; each toggle advances the orbit another half-turn the same
    way (``angle``, in radians, is animated by the host).
    """

    clicked = Signal()

    _MS = 60                    # mascot size (px)
    _PAD_L, _PAD_T = 16, 2      # mascot offset → sky room opens at the left/top
    _CX, _CY, _R = 21.0, 45.0, 30.0       # orbit: wide, apex at upper-left
    _SUN_RAD, _MOON_RAD = 5.0, 8.0        # sun smaller so its rays clear the lower edge when set

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("brandMark")
        self.setFixedSize(self._PAD_L + self._MS, self._PAD_T + self._MS + 2)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self._base = 0.0  # orbit angle (radians), accumulated one way
        pm = QPixmap(asset_path("app.png")).scaled(
            self._MS * 2, self._MS * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(2.0)  # crisp on 1x/2x displays
        self._pix = pm
        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setDuration(1050)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    def set_dark(self, dark: bool, animate: bool = False) -> None:
        want_odd = 1 if dark else 0
        self._anim.stop()
        if not animate:
            self._base = math.pi if dark else 0.0
            self.update()
            return
        # advance another half-turn (same direction) only when the parity flips
        if round(self._base / math.pi) % 2 != want_odd:
            self._anim.setStartValue(self._base)
            self._anim.setEndValue(self._base + math.pi)
            self._anim.start()

    def _get_angle(self) -> float:
        return self._base

    def _set_angle(self, v: float) -> None:
        self._base = v
        self.update()

    angle = Property(float, _get_angle, _set_angle)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        b = self._base
        _draw_sun(p, self._CX + self._R * math.sin(b),
                  self._CY - self._R * math.cos(b), self._SUN_RAD)
        _draw_moon(p, self._CX - self._R * math.sin(b),
                   self._CY + self._R * math.cos(b), self._MOON_RAD)
        p.drawPixmap(self._PAD_L, self._PAD_T, self._pix)  # mascot in front


# ── timeline pieces ─────────────────────────────────────────────────────
_KIND_KEY = {"create": "green", "update": "blue", "delete": "red"}
_KIND_GLYPH = {"create": "+", "update": "✎", "delete": "✕"}
_KIND_KO = {"create": "생성", "update": "수정", "delete": "삭제"}


class _Rail(QWidget):
    """The vertical timeline line with a coloured dot for one revision node.
    Clicking the dot toggles its card's collapsed state."""

    clicked = Signal()

    def __init__(self, kind: str, first: bool, last: bool):
        super().__init__()
        self.kind = kind
        self.first, self.last = first, last
        self.setFixedWidth(36)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(C[_KIND_KEY.get(self.kind, "blue")])  # live per-theme
        cx, cy, r = 14, 20, 11
        top = cy if self.first else 0
        bot = cy if self.last else self.height()
        p.setPen(QPen(QColor(C["rail"]), 2))
        p.drawLine(cx, top, cx, bot)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["bg"]))
        p.drawEllipse(QPoint(cx, cy), r + 4, r + 4)
        p.setBrush(color)
        p.drawEllipse(QPoint(cx, cy), r, r)

        # White glyph drawn as vectors (font-independent — renders identically
        # everywhere, unlike the ✎/✕ symbol glyphs which can break per machine).
        white = QColor("#ffffff")
        if self.kind == "create":
            p.setPen(QPen(white, 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
            p.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))
        elif self.kind == "delete":
            p.setPen(QPen(white, 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - 3.5, cy - 3.5), QPointF(cx + 3.5, cy + 3.5))
            p.drawLine(QPointF(cx - 3.5, cy + 3.5), QPointF(cx + 3.5, cy - 3.5))
        else:  # update -> a pencil: eraser (upper-right) + body + tip (lower-left)
            p.save()
            p.translate(cx, cy)
            p.rotate(45)
            p.setPen(Qt.NoPen)
            p.setBrush(white)
            p.drawRoundedRect(QRectF(-1.7, -5.0, 3.4, 1.9), 0.7, 0.7)        # eraser cap
            p.drawRect(QRectF(-1.5, -3.2, 3.0, 6.2))                          # wooden body
            p.drawPolygon(QPolygonF([QPointF(-1.5, 3.0), QPointF(1.5, 3.0),
                                     QPointF(0.0, 5.3)]))                     # sharpened cone
            p.setBrush(color)
            p.drawPolygon(QPolygonF([QPointF(-0.7, 4.3), QPointF(0.7, 4.3),
                                     QPointF(0.0, 5.3)]))                     # exposed lead
            p.setPen(QPen(color, 0.9))
            p.drawLine(QPointF(-1.7, -3.2), QPointF(1.7, -3.2))              # ferrule line
            p.restore()


# ── click-to-copy ───────────────────────────────────────────────────────
_toasts: list = []  # keep live toasts referenced until they finish fading


class _CopyToast(QLabel):
    """A frameless 'copied' toast — text only (no background), shown near the
    cursor. Text paints fine on a translucent top-level even though a QSS
    background would not."""

    def __init__(self, text: str):
        super().__init__(text, None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setObjectName("copyToast")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAlignment(Qt.AlignCenter)


def copy_value(text: str, global_pos: QPoint) -> None:
    """Copy text to the clipboard and flash a fading toast near the cursor."""
    QApplication.clipboard().setText(str(text))

    toast = _CopyToast("복사됨")
    _toasts.append(toast)
    toast.adjustSize()
    # Sit right above the top tip of the mouse pointer.
    toast.move(max(4, global_pos.x() - toast.width() // 2),
               max(4, global_pos.y() - toast.height() - 2))
    toast.show()
    toast.raise_()

    # Hold at full for ~1s, then fade the whole toast out gently.
    anim = QPropertyAnimation(toast, b"windowOpacity", toast)
    anim.setDuration(700)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InOutQuad)

    def _done():
        toast.close()
        if toast in _toasts:
            _toasts.remove(toast)

    anim.finished.connect(_done)
    toast._anim = anim  # keep referenced
    QTimer.singleShot(1000, anim.start)


class _CopyableLabel(QLabel):
    """A value pill that copies its text to the clipboard when clicked."""

    def __init__(self, text: str):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            copy_value(self.text(), e.globalPosition().toPoint())
        super().mousePressEvent(e)


def value_pill(value, variant: str) -> QLabel:
    if value is None:
        lab = QLabel("∅ null")
        lab.setObjectName("valNull")
    else:
        lab = _CopyableLabel(str(value))
        lab.setObjectName("valOld" if variant == "old" else "valNew")
        if variant == "old":
            f = lab.font()
            f.setStrikeOut(True)
            lab.setFont(f)
    lab.setWordWrap(True)
    lab.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    return lab


def name_column_width(labels) -> int:
    """Width for the column-name cell: wide enough for the longest name in the
    timeline (so values line up in a column), clamped to a sane range."""
    f = QFont("Consolas")
    f.setPixelSize(13)
    f.setWeight(QFont.Weight.DemiBold)
    fm = QFontMetrics(f)
    widest = max((fm.horizontalAdvance(str(x)) for x in labels), default=0)
    return max(150, min(widest + 10, 400))


def _change_row(change: dict, name_width: int = 150) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 7, 0, 7)
    h.setSpacing(12)

    name = QLabel(change["label"])
    name.setObjectName("colName")
    name.setWordWrap(False)
    name.setFixedWidth(name_width)
    name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    name.setTextInteractionFlags(Qt.TextSelectableByMouse)
    h.addWidget(name, 0, Qt.AlignTop)

    diff = QHBoxLayout()
    diff.setSpacing(9)
    if change["kind"] == "flag":
        # Changed, but the audit table stores no value (e.g. a collection).
        badge = QLabel("변경됨")
        badge.setObjectName("flagChanged")
        diff.addWidget(badge)
    elif change["kind"] == "create":
        diff.addWidget(value_pill(change["new"], "new"))
        tag = QLabel("신규")
        tag.setObjectName("tag")
        diff.addWidget(tag)
    else:
        diff.addWidget(value_pill(change["old"], "old"))
        arrow = QLabel("→")
        arrow.setObjectName("arrow")
        diff.addWidget(arrow)
        diff.addWidget(value_pill(change["new"], "new"))
    diff.addStretch(1)
    h.addLayout(diff, 1)
    return row


class TimelineCard(QFrame):
    """One revision card. Click to select (focus mode); Up/Down navigate revs."""

    activated = Signal(object)   # emits self when clicked
    navigate = Signal(int)       # emits -1 (up) / +1 (down) on arrow keys

    def __init__(self, node: dict, name_width: int = 150):
        super().__init__()
        self.setObjectName("tlCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setFocusPolicy(Qt.StrongFocus)
        self._collapsed = False
        cv = QVBoxLayout(self)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        head = QFrame()
        head.setObjectName("tlHead")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(14, 10, 14, 10)
        hh.setSpacing(10)
        rev = QLabel(f"REV {node['rev']}")
        rev.setObjectName("revChip")
        tchip = QLabel(_KIND_KO.get(node["kind"], ""))
        tchip.setObjectName({"create": "typeCreate", "update": "typeUpdate", "delete": "typeDelete"}[node["kind"]])
        time = QLabel(node.get("timestamp") or f"REV {node['rev']}")
        time.setObjectName("tlTime")
        hh.addWidget(rev)
        hh.addWidget(tchip)
        hh.addStretch(1)
        hh.addWidget(time)
        self._chevron = QLabel("▾")
        self._chevron.setObjectName("tlChevron")
        self._chevron.setCursor(Qt.PointingHandCursor)
        self._chevron.mousePressEvent = self._chevron_clicked
        hh.addWidget(self._chevron)
        cv.addWidget(head)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(14, 4, 14, 8)
        bv.setSpacing(0)
        if node.get("records") is not None:
            # All-records view: one revision touched several records — show each
            # under its identifier heading.
            recs = node["records"]
            for ri, rec in enumerate(recs):
                ident = QLabel(rec["identifier"])
                ident.setObjectName("recIdent")
                ident.setTextInteractionFlags(Qt.TextSelectableByMouse)
                bv.addWidget(ident)
                self._fill_changes(bv, rec, name_width)
                if ri < len(recs) - 1:
                    sep = QFrame()
                    sep.setObjectName("recSep")
                    bv.addWidget(sep)
        else:
            self._fill_changes(bv, node, name_width)
        self._body = body
        cv.addWidget(body)

    @staticmethod
    def _fill_changes(bv, node: dict, name_width: int) -> None:
        """Render one record's change rows (or its deleted / no-change note)."""
        if node["kind"] == "delete":
            note = QLabel("🗑  이 시점에 레코드가 삭제되었습니다.")
            note.setObjectName("delNote")
            bv.addWidget(note)
        elif not node["changes"]:
            nc = QLabel("변경된 컬럼이 없습니다.")
            nc.setObjectName("noChange")
            bv.addWidget(nc)
        else:
            for i, ch in enumerate(node["changes"]):
                r = _change_row(ch, name_width)
                if i < len(node["changes"]) - 1:
                    r.setStyleSheet("border-bottom: 1px dashed #e9ecf4;")
                bv.addWidget(r)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", bool(on))
        repolish(self)

    def mousePressEvent(self, e):
        self.activated.emit(self)
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up:
            self.navigate.emit(-1)
            e.accept()
        elif e.key() == Qt.Key_Down:
            self.navigate.emit(1)
            e.accept()
        elif e.key() == Qt.Key_Left:        # collapse (header only)
            self.set_collapsed(True)
            e.accept()
        elif e.key() == Qt.Key_Right:       # expand
            self.set_collapsed(False)
            e.accept()
        else:
            super().keyPressEvent(e)

    def set_collapsed(self, on: bool) -> None:
        self._collapsed = bool(on)
        self._body.setVisible(not self._collapsed)
        self._chevron.setText("▸" if self._collapsed else "▾")

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _on_rail_clicked(self) -> None:
        self.activated.emit(self)
        self.toggle_collapsed()

    def _chevron_clicked(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.activated.emit(self)
            self.toggle_collapsed()
        e.accept()


def timeline_node(node: dict, first: bool, last: bool, name_width: int = 150):
    """Return (wrap, card): the rail+card row, and the selectable TimelineCard."""
    wrap = QWidget()
    outer = QHBoxLayout(wrap)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    rail = _Rail(node["kind"], first, last)
    outer.addWidget(rail)

    # The card sits at the top; a fixed gap below keeps cards apart while the
    # rail (which fills the full node height) draws a continuous line through it.
    right = QWidget()
    rv = QVBoxLayout(right)
    rv.setContentsMargins(0, 0, 0, 0)
    rv.setSpacing(0)
    card = TimelineCard(node, name_width)
    rail.clicked.connect(card._on_rail_clicked)
    rv.addWidget(card)
    if not last:
        rv.addSpacing(18)
    outer.addWidget(right, 1)
    return wrap, card


def summary_bar(summary: dict, identifier: dict) -> QFrame:
    bar = QFrame()
    bar.setObjectName("summaryBar")
    h = QHBoxLayout(bar)
    h.setContentsMargins(18, 13, 18, 13)
    h.setSpacing(26)
    rng = "—"
    if summary.get("first_ts") and summary.get("last_ts"):
        rng = f"{summary['first_ts'].split(' ')[0]} ~ {summary['last_ts'].split(' ')[0]}"
    items = [
        ("식별자", f"{identifier['column']} = {identifier['value']}"),
        ("리비전", str(summary["revisions"])),
        ("변경 항목", str(summary["total_changes"])),
        ("기간", rng),
    ]
    for k, v in items:
        col = QVBoxLayout()
        col.setSpacing(2)
        kk = QLabel(k)
        kk.setObjectName("sumK")
        vv = QLabel(v)
        vv.setObjectName("sumV")
        if k in ("식별자", "기간"):
            vv.setStyleSheet("font-size: 13px;")
        col.addWidget(kk)
        col.addWidget(vv)
        h.addLayout(col)
    h.addStretch(1)
    return bar


def changeset_summary_bar(summary: dict) -> QFrame:
    """Summary bar for the all-records (id-less) revision timeline."""
    bar = QFrame()
    bar.setObjectName("summaryBar")
    h = QHBoxLayout(bar)
    h.setContentsMargins(18, 13, 18, 13)
    h.setSpacing(26)
    rng = "—"
    if summary.get("first_ts") and summary.get("last_ts"):
        rng = f"{summary['first_ts'].split(' ')[0]} ~ {summary['last_ts'].split(' ')[0]}"
    rev_text = str(summary.get("revisions", 0))
    if summary.get("has_more"):
        rev_text += "+"
    items = [
        ("대상", "테이블 전체"),
        ("리비전", rev_text),
        ("레코드", str(summary.get("records", 0))),
        ("변경 항목", str(summary.get("total_changes", 0))),
        ("기간", rng),
    ]
    for k, v in items:
        col = QVBoxLayout()
        col.setSpacing(2)
        kk = QLabel(k)
        kk.setObjectName("sumK")
        vv = QLabel(v)
        vv.setObjectName("sumV")
        if k in ("대상", "기간"):
            vv.setStyleSheet("font-size: 13px;")
        col.addWidget(kk)
        col.addWidget(vv)
        h.addLayout(col)
    h.addStretch(1)
    return bar


def meta_badge(text: str, kind: str = "metaBadge") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(kind)
    return lab
