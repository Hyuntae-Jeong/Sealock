"""Main window and the three wizard pages (connection / table / history)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import services
from ..resources import app_icon, asset_path
from ..services import AppState
from .widgets import (FlowLayout, Stepper, TimelineCard, button, clear_layout,
                      field, meta_badge, name_column_width, repolish, run_async,
                      soft_shadow, summary_bar, timeline_node)


def _title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("cardTitle")
    return lab


def _desc(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("cardDesc")
    lab.setWordWrap(True)
    return lab


def _centered(card: QWidget) -> QHBoxLayout:
    # Let the card grow toward its maximumWidth; the flanking stretches only
    # take the leftover space, keeping it centred without compressing it.
    card.setSizePolicy(QSizePolicy.Expanding, card.sizePolicy().verticalPolicy())
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(card, 10)
    row.addStretch(1)
    return row


# ════════════════════════════ STEP 1 ════════════════════════════
class ConnectionPage(QWidget):
    proceed = Signal(bool)  # demo?
    error = Signal(str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(560)
        soft_shadow(card)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(30, 28, 30, 26)
        cv.setSpacing(0)

        cv.addWidget(_title("데이터베이스 연결"))
        cv.addSpacing(4)
        cv.addWidget(_desc("MariaDB 접속 정보를 입력하고 연결을 테스트하세요."))
        cv.addSpacing(22)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        host_w, self.host = field("호스트", "localhost")
        port_w, self.port = field("포트", "3306")
        user_w, self.user = field("사용자", "root")
        pw_w, self.password = field("비밀번호", "••••••••", echo=True)
        db_w, self.database = field("데이터베이스 (스키마)", "my_schema")
        grid.addWidget(host_w, 0, 0)
        grid.addWidget(port_w, 0, 1)
        grid.addWidget(user_w, 1, 0)
        grid.addWidget(pw_w, 1, 1)
        grid.addWidget(db_w, 2, 0, 1, 2)
        cv.addLayout(grid)

        self.status = QLabel()
        self.status.setObjectName("statusBusy")
        self.status.setWordWrap(True)
        self.status.hide()
        cv.addSpacing(16)
        cv.addWidget(self.status)

        cv.addSpacing(22)
        foot = QHBoxLayout()
        self.demo_btn = button("샘플 데이터로 둘러보기", "ghost")
        self.test_btn = button("연결 테스트", "secondary")
        self.next_btn = button("다음  →", "primary")
        self.next_btn.setEnabled(False)
        foot.addWidget(self.demo_btn)
        foot.addStretch(1)
        foot.addWidget(self.test_btn)
        foot.addWidget(self.next_btn)
        cv.addLayout(foot)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 28, 24, 28)
        root.addStretch(1)
        root.addLayout(_centered(card))
        root.addStretch(1)

        d = services.form_defaults()
        self.host.setText(str(d["host"]))
        self.port.setText(str(d["port"]))
        self.user.setText(d["user"])
        self.password.setText(d["password"])
        self.database.setText(d["database"])

        self.test_btn.clicked.connect(self._test)
        self.demo_btn.clicked.connect(lambda: self.proceed.emit(True))
        self.next_btn.clicked.connect(lambda: self.proceed.emit(False))
        self.database.returnPressed.connect(self._test)
        self.password.returnPressed.connect(self._test)

    def _payload(self) -> dict:
        return {
            "host": self.host.text().strip() or "localhost",
            "port": self.port.text().strip() or 3306,
            "user": self.user.text().strip(),
            "password": self.password.text(),
            "database": self.database.text().strip(),
        }

    def _set_status(self, kind: str, text: str) -> None:
        self.status.setObjectName({"ok": "statusOk", "err": "statusErr", "busy": "statusBusy"}[kind])
        repolish(self.status)
        self.status.setText(text)
        self.status.show()

    def _test(self) -> None:
        p = self._payload()
        if not p["database"]:
            self.error.emit("데이터베이스(스키마) 이름을 입력하세요.")
            return
        self._set_status("busy", "연결 테스트 중…")
        self.test_btn.setEnabled(False)

        def ok(version):
            self.test_btn.setEnabled(True)
            self._set_status("ok", f"연결 성공 · MariaDB {version}")
            self.next_btn.setEnabled(True)

        def err(msg):
            self.test_btn.setEnabled(True)
            self.next_btn.setEnabled(False)
            self._set_status("err", msg)

        run_async(services.test_and_connect, ok, err, self.state, p)


# ════════════════════════════ STEP 2 ════════════════════════════
class TablePage(QWidget):
    proceed = Signal()
    back = Signal()
    error = Signal(str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.preview_data: dict | None = None
        self.ident_combo: QComboBox | None = None
        self._all_aud_tables: list[str] = []

        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(980)
        soft_shadow(card)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(30, 28, 30, 24)
        cv.setSpacing(0)

        cv.addWidget(_title("감사(AUD) 테이블 선택"))
        cv.addSpacing(4)
        cv.addWidget(_desc("aud 테이블 이름을 입력하면 컬럼 구성을 미리 볼 수 있습니다."))
        cv.addSpacing(20)

        inp = QHBoxLayout()
        inp.setSpacing(12)
        tw, self.table_name = field("테이블 이름", "이름 입력 또는 아래 목록에서 선택")
        inp.addWidget(tw, 1)
        cv.addLayout(inp)

        self.chips_caption = QLabel("")
        self.chips_caption.setObjectName("sectionLabel")
        self.chips_holder = QWidget()
        self.chips_flow = FlowLayout(self.chips_holder, hspace=8, vspace=8)
        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setWidget(self.chips_holder)
        chips_scroll.setFrameShape(QFrame.NoFrame)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chips_area = QFrame()
        chips_area.setObjectName("chipsArea")
        chips_area.setFixedHeight(180)
        ca = QVBoxLayout(chips_area)
        ca.setContentsMargins(8, 8, 8, 8)
        ca.addWidget(chips_scroll)
        cv.addSpacing(12)
        cv.addWidget(self.chips_caption)
        cv.addSpacing(6)
        cv.addWidget(chips_area)

        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 8, 0, 0)
        self.preview_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview_container)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cv.addSpacing(6)
        cv.addWidget(scroll, 1)

        foot = QHBoxLayout()
        self.back_btn = button("←  이전", "ghost")
        self.next_btn = button("이 테이블로 진행  →", "primary")
        self.next_btn.setEnabled(False)
        foot.addWidget(self.back_btn)
        foot.addStretch(1)
        foot.addWidget(self.next_btn)
        cv.addSpacing(14)
        cv.addLayout(foot)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addLayout(_centered(card), 1)

        self.table_name.returnPressed.connect(self._preview)
        self.table_name.textEdited.connect(self._render_chips)
        self.back_btn.clicked.connect(self.back.emit)
        self.next_btn.clicked.connect(self._confirm)

    def on_enter(self) -> None:
        self.next_btn.setEnabled(False)
        clear_layout(self.preview_layout)
        clear_layout(self.chips_flow)
        self._all_aud_tables = []
        self.chips_caption.setText("_AUD 테이블 불러오는 중…")
        # Empty by default; demo pre-fills its sample table. (Set before the
        # async fill so the chip filter starts from the right text.)
        self.table_name.setText("member_AUD" if self.state.demo else "")
        run_async(services.list_aud_tables, self._fill_chips, self._chips_error, self.state)
        if self.state.demo:
            self._preview()
        else:
            self.table_name.setFocus()

    def _fill_chips(self, tables: list[str]) -> None:
        self._all_aud_tables = tables
        self._render_chips(self.table_name.text())

    def _chips_error(self, msg: str) -> None:
        self.chips_caption.setText("_AUD 테이블 목록을 불러오지 못했습니다 — 이름을 직접 입력하세요.")
        self.error.emit(f"_AUD 테이블 목록 조회 실패: {msg}")

    def _render_chips(self, needle: str) -> None:
        clear_layout(self.chips_flow)
        needle = (needle or "").strip().lower()
        matches = [t for t in self._all_aud_tables if needle in t.lower()]
        for t in matches:
            chip = QPushButton(t)
            chip.setObjectName("chip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, name=t: self._pick_chip(name))
            self.chips_flow.addWidget(chip)

        total = len(self._all_aud_tables)
        if total == 0:
            self.chips_caption.setText("이 스키마에서 _AUD 테이블을 찾지 못했습니다 — 이름을 직접 입력하세요.")
        elif needle:
            self.chips_caption.setText(f"_AUD 테이블 {total}개 중 {len(matches)}개  ·  클릭하면 바로 미리보기")
        else:
            self.chips_caption.setText(f"_AUD 테이블 {total}개  ·  클릭하면 바로 미리보기 (이름 입력해 필터)")

    def _pick_chip(self, name: str) -> None:
        # Clicking a candidate fills the name and previews it immediately.
        self.table_name.setText(name)
        self._preview()

    def _preview(self) -> None:
        table = self.table_name.text().strip()
        if not table:
            self.error.emit("테이블 이름을 입력하세요.")
            return
        self.next_btn.setEnabled(False)

        def ok(data):
            self.preview_data = data
            self._render_preview(data)
            self.next_btn.setEnabled(True)

        def err(msg):
            clear_layout(self.preview_layout)
            self.error.emit(msg)

        run_async(services.preview_table, ok, err, self.state, table)

    def _render_preview(self, d: dict) -> None:
        clear_layout(self.preview_layout)
        ri = d.get("revinfo") or {}

        meta_holder = QWidget()
        flow = FlowLayout(meta_holder, hspace=10, vspace=10)
        flow.addWidget(meta_badge(f"리비전 컬럼  ·  {d.get('rev_column') or '—'}"))
        flow.addWidget(meta_badge(f"타입 컬럼  ·  {d.get('revtype_column') or '—'}"))
        flow.addWidget(meta_badge(
            f"✓  _MOD 변경 플래그 {len(d.get('mod_flag_columns', []))}개" if d.get("has_mod_flags")
            else "⚠  _MOD 플래그 없음 (값 비교로 대체)",
            "metaGood" if d.get("has_mod_flags") else "metaWarn"))
        flow.addWidget(meta_badge(
            f"✓  REVINFO {ri.get('table')}  ·  시간 {ri.get('ts_column') or '—'}" if ri.get("found")
            else "⚠  REVINFO 없음 (시간 표시 불가)",
            "metaGood" if ri.get("found") else "metaWarn"))
        self.preview_layout.addWidget(meta_holder)
        self.preview_layout.addSpacing(16)

        id_row = QHBoxLayout()
        cap = QLabel("식별자(조회 기준) 컬럼")
        cap.setObjectName("fieldLabel")
        self.ident_combo = QComboBox()
        names = d.get("identifier_columns") or [c["name"] for c in d.get("all_columns", [])]
        self.ident_combo.addItems(names)
        if d.get("identifier_default") in names:
            self.ident_combo.setCurrentText(d["identifier_default"])
        self.ident_combo.setMaximumWidth(220)
        id_row.addWidget(cap)
        id_row.addSpacing(10)
        id_row.addWidget(self.ident_combo)
        id_row.addStretch(1)
        self.preview_layout.addLayout(id_row)
        self.preview_layout.addSpacing(18)

        data_cols = d.get("data_columns", [])
        self.preview_layout.addWidget(self._section_label(f"데이터 컬럼 ({len(data_cols)})  ·  변경 추적 대상"))
        self.preview_layout.addSpacing(8)
        self.preview_layout.addWidget(self._columns_table(data_cols))

        self.preview_layout.addSpacing(18)
        self.preview_layout.addWidget(self._section_label("시스템 컬럼"))
        self.preview_layout.addSpacing(8)
        sys_holder = QWidget()
        sflow = FlowLayout(sys_holder, hspace=7, vspace=7)
        for c in d.get("system_columns", []):
            sflow.addWidget(meta_badge(c["name"], "sysPill"))
        if not d.get("system_columns"):
            sflow.addWidget(meta_badge("없음", "sysPill"))
        self.preview_layout.addWidget(sys_holder)
        self.preview_layout.addStretch(1)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lab = QLabel(text.upper())
        lab.setObjectName("sectionLabel")
        return lab

    def _columns_table(self, cols: list[dict]) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QFrame()
        head.setObjectName("tableHead")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(12, 6, 12, 8)
        for text, stretch in (("컬럼", 3), ("타입", 3), ("_MOD 플래그", 4)):
            lab = QLabel(text)
            lab.setObjectName("thCell")
            hh.addWidget(lab, stretch)
        v.addWidget(head)

        if not cols:
            empty = QLabel("데이터 컬럼이 없습니다.")
            empty.setObjectName("flagNo")
            empty.setContentsMargins(12, 10, 12, 10)
            v.addWidget(empty)
            return wrap

        for c in cols:
            row = QFrame()
            row.setObjectName("tableRow")
            rh = QHBoxLayout(row)
            rh.setContentsMargins(12, 9, 12, 9)
            name = QLabel(c["name"])
            name.setObjectName("tdName")
            typ = QLabel(c["type"])
            typ.setObjectName("tdType")
            if c.get("mod_flag"):
                flag = QLabel(f"●  {c['mod_flag']}")
                flag.setObjectName("flagYes")
            else:
                flag = QLabel("없음")
                flag.setObjectName("flagNo")
            rh.addWidget(name, 3)
            rh.addWidget(typ, 3)
            rh.addWidget(flag, 4)
            v.addWidget(row)
        return wrap

    def _confirm(self) -> None:
        table = self.table_name.text().strip()
        ident = self.ident_combo.currentText() if self.ident_combo else (self.preview_data or {}).get("identifier_default")
        self.next_btn.setEnabled(False)

        def ok(_ctx):
            self.next_btn.setEnabled(True)
            self.proceed.emit()

        def err(msg):
            self.next_btn.setEnabled(True)
            self.error.emit(msg)

        run_async(services.confirm_table, ok, err, self.state, table, ident)


# ════════════════════════════ STEP 3 ════════════════════════════
class HistoryPage(QWidget):
    back = Signal()
    error = Signal(str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._cards: list[TimelineCard] = []
        self._selected = -1

        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(980)
        soft_shadow(card)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(30, 28, 30, 24)
        cv.setSpacing(0)

        head_row = QHBoxLayout()
        head_box = QVBoxLayout()
        head_box.setSpacing(4)
        head_box.addWidget(_title("변경 이력 조회"))
        self.desc = _desc("식별자 값을 입력하면 시간순 변경 이력을 보여줍니다.")
        head_box.addWidget(self.desc)
        head_row.addLayout(head_box, 1)
        self.back_btn = button("←  테이블 변경", "ghost")
        self.back_btn.setMaximumHeight(34)
        head_row.addWidget(self.back_btn, 0, Qt.AlignTop)
        cv.addLayout(head_row)
        cv.addSpacing(18)

        inp = QHBoxLayout()
        inp.setSpacing(12)
        id_box = QVBoxLayout()
        id_box.setSpacing(7)
        self.id_caption = QLabel("ID")
        self.id_caption.setObjectName("fieldLabel")
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("예: 42")
        id_box.addWidget(self.id_caption)
        id_box.addWidget(self.id_edit)
        self.load_btn = button("이력 불러오기", "primary")
        btn_wrap = QVBoxLayout()
        btn_wrap.addStretch(1)
        btn_wrap.addWidget(self.load_btn)
        inp.addLayout(id_box, 1)
        inp.addLayout(btn_wrap)
        cv.addLayout(inp)

        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(0, 0, 4, 0)
        self.result_layout.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self.result_container)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cv.addSpacing(8)
        cv.addWidget(self._scroll, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addLayout(_centered(card), 1)

        self.load_btn.clicked.connect(self._load)
        self.id_edit.returnPressed.connect(self._load)
        self.back_btn.clicked.connect(self.back.emit)
        # Deselect the focused card when clicking anywhere outside the cards.
        QApplication.instance().installEventFilter(self)

    def on_enter(self) -> None:
        ctx = self.state.context or {}
        ident = ctx.get("identifier_column", "ID")
        self.id_caption.setText(ident)
        self.desc.setText(f"'{ctx.get('table')}' 테이블에서 {ident} 값을 기준으로 변경 이력을 조회합니다.")
        self.id_edit.setText("42" if self.state.demo else "")
        self._placeholder()
        self.id_edit.setFocus()

    def _load(self) -> None:
        idv = self.id_edit.text().strip()
        if not idv:
            self.error.emit("조회할 ID를 입력하세요.")
            return
        self.load_btn.setEnabled(False)

        def ok(r):
            self.load_btn.setEnabled(True)
            if r.get("empty") or not r.get("timeline"):
                self._empty(r["identifier"])
            else:
                self._render(r)

        def err(msg):
            self.load_btn.setEnabled(True)
            self.error.emit(msg)

        run_async(services.get_history, ok, err, self.state, idv)

    def _render(self, r: dict) -> None:
        clear_layout(self.result_layout)
        self._cards = []
        self._selected = -1
        self.result_layout.addSpacing(20)
        self.result_layout.addWidget(summary_bar(r["summary"], r["identifier"]))
        self.result_layout.addSpacing(22)
        tl = r["timeline"]
        # Align value pills into a column: size every name cell to the widest
        # column name across the whole timeline.
        name_w = name_column_width([c["label"] for n in tl for c in n["changes"]])
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(2, 0, 0, 0)
        hv.setSpacing(0)
        for i, node in enumerate(tl):
            wrap, cardw = timeline_node(node, first=(i == 0), last=(i == len(tl) - 1), name_width=name_w)
            self._cards.append(cardw)
            cardw.activated.connect(self._on_card_activated)
            cardw.navigate.connect(self._on_navigate)
            hv.addWidget(wrap)
        self.result_layout.addWidget(holder)
        self.result_layout.addStretch(1)

    # ── card selection / keyboard navigation ────────────────────────────
    def _on_card_activated(self, card) -> None:
        try:
            self._select(self._cards.index(card))
        except ValueError:
            pass

    def _select(self, idx: int) -> None:
        if not (0 <= idx < len(self._cards)):
            return
        if 0 <= self._selected < len(self._cards):
            self._cards[self._selected].set_selected(False)
        self._selected = idx
        card = self._cards[idx]
        card.set_selected(True)
        card.setFocus()
        self._reveal(card)

    def _reveal(self, card) -> None:
        """Scroll the card into view, keeping its header (top) visible — even
        when the card is taller than the viewport."""
        sb = self._scroll.verticalScrollBar()
        vp_h = self._scroll.viewport().height()
        if vp_h <= 0:
            return
        top = card.mapTo(self.result_container, QPoint(0, 0)).y()
        bottom = top + card.height()
        cur = sb.value()
        margin = 12
        if card.height() >= vp_h - margin or top < cur + margin:
            sb.setValue(max(0, top - margin))            # align header to the top
        elif bottom > cur + vp_h - margin:
            sb.setValue(min(sb.maximum(), bottom - vp_h + margin))

    def _on_navigate(self, delta: int) -> None:
        if self._selected < 0:
            return
        self._select(max(0, min(self._selected + delta, len(self._cards) - 1)))

    def _deselect(self) -> None:
        if 0 <= self._selected < len(self._cards):
            self._cards[self._selected].set_selected(False)
        self._selected = -1

    @staticmethod
    def _within_card(w) -> bool:
        while w is not None:
            if isinstance(w, TimelineCard):
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and self._selected >= 0:
            if not self._within_card(QApplication.widgetAt(QCursor.pos())):
                self._deselect()
        return False

    def _placeholder(self) -> None:
        ident = self.id_caption.text()
        self._center_message("🔎", f"조회할 {ident} 값을 입력하고 '이력 불러오기'를 누르세요.",
                             "해당 레코드의 모든 변경 이력이 시간순으로 표시됩니다.")

    def _empty(self, identifier: dict) -> None:
        self._center_message("📭", f"{identifier['column']} = {identifier['value']} 에 대한 변경 이력이 없습니다.",
                             "ID를 다시 확인해 주세요.")

    def _center_message(self, glyph: str, title: str, sub: str) -> None:
        clear_layout(self.result_layout)
        self._cards = []
        self._selected = -1
        self.result_layout.addStretch(1)
        em = QLabel(glyph)
        em.setAlignment(Qt.AlignCenter)
        em.setStyleSheet("font-size: 30px;")
        t = QLabel(title)
        t.setObjectName("emptyTitle")
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        s = QLabel(sub)
        s.setObjectName("emptySub")
        s.setAlignment(Qt.AlignCenter)
        for w in (em, t, s):
            self.result_layout.addWidget(w)
            self.result_layout.addSpacing(6)
        self.result_layout.addStretch(1)


# ════════════════════════════ MAIN WINDOW ════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sealock — MariaDB Audit History")
        self.setWindowIcon(app_icon())
        self.resize(1240, 960)
        self.setMinimumSize(1040, 740)
        self.state = AppState()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        rv = QVBoxLayout(root)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        rv.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        self.page_conn = ConnectionPage(self.state)
        self.page_table = TablePage(self.state)
        self.page_hist = HistoryPage(self.state)
        for p in (self.page_conn, self.page_table, self.page_hist):
            self.stack.addWidget(p)
        rv.addWidget(self.stack, 1)

        self._toast = QLabel(root)
        self._toast.setObjectName("toast")
        self._toast.hide()

        self.page_conn.proceed.connect(self._from_conn)
        self.page_conn.error.connect(lambda m: self.toast(m, True))
        self.page_table.proceed.connect(self._from_table)
        self.page_table.back.connect(lambda: self.goto(0))
        self.page_table.error.connect(lambda m: self.toast(m, True))
        self.page_hist.back.connect(lambda: self.goto(1))
        self.page_hist.error.connect(lambda m: self.toast(m, True))

    def _build_topbar(self) -> QFrame:
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(70)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(28, 0, 28, 0)

        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setFixedSize(44, 44)
        _logo = QPixmap(asset_path("app.png")).scaled(
            88, 88, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        _logo.setDevicePixelRatio(2.0)  # crisp at 44px logical on 1x and 2x displays
        mark.setPixmap(_logo)
        mark.setAlignment(Qt.AlignCenter)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.setContentsMargins(0, 0, 0, 0)
        bt = QLabel("Sealock")
        bt.setObjectName("brandTitle")
        bs = QLabel("MariaDB Envers 변경 이력 뷰어")
        bs.setObjectName("brandSub")
        # 두 줄을 자연 높이의 한 덩어리로 묶어 세로 중앙에 정렬 → 아이콘 높이와 맞춤
        brand_text.addStretch(1)
        brand_text.addWidget(bt)
        brand_text.addWidget(bs)
        brand_text.addStretch(1)
        brand = QHBoxLayout()
        brand.setSpacing(12)
        brand.addWidget(mark)
        brand.addLayout(brand_text)

        self.stepper = Stepper(["연결", "테이블", "이력"])
        tb.addLayout(brand)
        tb.addStretch(1)
        tb.addWidget(self.stepper)
        return topbar

    def goto(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        self.stepper.set_current(idx + 1)

    def _from_conn(self, demo: bool) -> None:
        self.state.demo = bool(demo)
        self.goto(1)
        self.page_table.on_enter()

    def _from_table(self) -> None:
        self.goto(2)
        self.page_hist.on_enter()

    def toast(self, msg: str, error: bool = False) -> None:
        self._toast.setObjectName("toastErr" if error else "toast")
        repolish(self._toast)
        self._toast.setText(msg)
        self._toast.adjustSize()
        self._position_toast()
        self._toast.show()
        self._toast.raise_()
        QTimer.singleShot(3600, self._toast.hide)

    def _position_toast(self) -> None:
        if not self._toast.parent():
            return
        pw = self._toast.parent().width()
        ph = self._toast.parent().height()
        w = self._toast.width()
        h = self._toast.height()
        self._toast.move(max(20, pw - w - 24), max(20, ph - h - 24))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._toast.isVisible():
            self._position_toast()

    def closeEvent(self, e):
        try:
            self.state.db.close()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(e)
