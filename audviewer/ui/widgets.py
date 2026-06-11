"""Reusable Qt widgets and helpers: async worker, stepper, timeline pieces."""
from __future__ import annotations

from PySide6.QtCore import (QObject, QPoint, QRect, QRectF, QRunnable, QSize, Qt,
                            QThreadPool, Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QLayout, QLineEdit, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

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
class Stepper(QWidget):
    def __init__(self, labels: list[str]):
        super().__init__()
        self._nums: list[QLabel] = []
        self._labs: list[QLabel] = []
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
            num = QLabel(str(i + 1))
            num.setObjectName("stepNum")
            num.setAlignment(Qt.AlignCenter)
            lab = QLabel(text)
            lab.setObjectName("stepLabel")
            self._nums.append(num)
            self._labs.append(lab)
            h.addWidget(num)
            h.addWidget(lab)
        self.set_current(1)

    def set_current(self, n: int) -> None:
        for i, (num, lab) in enumerate(zip(self._nums, self._labs), start=1):
            state = "done" if i < n else "active" if i == n else "todo"
            num.setText("✓" if state == "done" else str(i))
            set_state(num, state)
            set_state(lab, state)
        for i, line in enumerate(self._lines, start=1):
            set_state(line, "done" if n > i else "todo")


# ── timeline pieces ─────────────────────────────────────────────────────
_KIND_COLOR = {"create": C["green"], "update": C["blue"], "delete": C["red"]}
_KIND_GLYPH = {"create": "+", "update": "✎", "delete": "✕"}
_KIND_KO = {"create": "생성", "update": "수정", "delete": "삭제"}


class _Rail(QWidget):
    """The vertical timeline line with a coloured dot for one revision node."""

    def __init__(self, kind: str, first: bool, last: bool):
        super().__init__()
        self.color = QColor(_KIND_COLOR.get(kind, C["blue"]))
        self.glyph = _KIND_GLYPH.get(kind, "•")
        self.first, self.last = first, last
        self.setFixedWidth(36)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy, r = 14, 20, 11
        top = cy if self.first else 0
        bot = cy if self.last else self.height()
        p.setPen(QPen(QColor(C["rail"]), 2))
        p.drawLine(cx, top, cx, bot)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["bg"]))
        p.drawEllipse(QPoint(cx, cy), r + 4, r + 4)
        p.setBrush(self.color)
        p.drawEllipse(QPoint(cx, cy), r, r)
        p.setPen(QColor("#ffffff"))
        f = QFont("Segoe UI Symbol")
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(cx - r, cy - r, 2 * r, 2 * r), Qt.AlignCenter, self.glyph)


def value_pill(value, variant: str) -> QLabel:
    if value is None:
        lab = QLabel("∅ null")
        lab.setObjectName("valNull")
    else:
        lab = QLabel(str(value))
        lab.setObjectName("valOld" if variant == "old" else "valNew")
        if variant == "old":
            f = lab.font()
            f.setStrikeOut(True)
            lab.setFont(f)
    lab.setWordWrap(True)
    lab.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    return lab


def _change_row(change: dict) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 7, 0, 7)
    h.setSpacing(12)

    name = QLabel(change["label"])
    name.setObjectName("colName")
    name.setWordWrap(False)
    name.setMinimumWidth(150)
    name.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    name.setTextInteractionFlags(Qt.TextSelectableByMouse)
    h.addWidget(name, 0, Qt.AlignTop)

    diff = QHBoxLayout()
    diff.setSpacing(9)
    if change["kind"] == "create":
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


def timeline_node(node: dict, first: bool, last: bool) -> QWidget:
    wrap = QWidget()
    outer = QHBoxLayout(wrap)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(_Rail(node["kind"], first, last))

    # The card sits at the top; a fixed gap below keeps cards apart while the
    # rail (which fills the full node height) draws a continuous line through it.
    right = QWidget()
    rv = QVBoxLayout(right)
    rv.setContentsMargins(0, 0, 0, 0)
    rv.setSpacing(0)

    card = QFrame()
    card.setObjectName("tlCard")
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    cv = QVBoxLayout(card)
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
    cv.addWidget(head)

    body = QWidget()
    bv = QVBoxLayout(body)
    bv.setContentsMargins(14, 4, 14, 8)
    bv.setSpacing(0)
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
            r = _change_row(ch)
            if i < len(node["changes"]) - 1:
                r.setStyleSheet("border-bottom: 1px dashed #e9ecf4;")
            bv.addWidget(r)
    cv.addWidget(body)

    rv.addWidget(card)
    if not last:
        rv.addSpacing(18)
    outer.addWidget(right, 1)
    return wrap


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


def meta_badge(text: str, kind: str = "metaBadge") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(kind)
    return lab
