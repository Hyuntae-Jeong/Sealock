"""설정 패널과 수동 업데이트 화면.

첫 화면 오른쪽 아래 ⚙ 설정에서만 열린다 — 앱이 스스로 새 버전을 확인하는
경로는 없다. 설정은 창 안 패널이라 별도 창이 아니고, 업데이트/릴리즈 노트만
창으로 띄운다. 그 창의 모서리 처리는 _Sheet 주석 참조.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QTextCursor
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import updater
from ..version import __version__
from .theme import C, NOTES_PAD
from .widgets import button, run_async


def _label(text: str, obj: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


PAD = 18            # 헤더·본문·푸터가 공유하는 좌우 여백
VERSION_GAP = 26    # 노트에서 버전이 바뀌는 자리의 간격 (그 한가운데가 구분선)


class _CloseDot(QPushButton):
    """macOS 신호등 스타일 닫기 점.

    커서를 올리면 ✕ 가 드러난다 — 색만 있는 점은 눌러도 되는 것인지 알기 어렵고,
    항상 ✕ 를 띄워두면 조용해야 할 자리가 시끄럽다. QSS 로는 글자를 바꿀 수
    없어서 enter/leave 에서 직접 넣고 뺀다.
    """

    def __init__(self, slot):
        super().__init__("")
        self.setObjectName("closeDot")
        self.setFixedSize(14, 14)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)     # Tab 순서에 끼어들지 않는다
        self.setToolTip("닫기")
        self.clicked.connect(slot)

    def enterEvent(self, e):
        self.setText("✕")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setText("")
        super().leaveEvent(e)


class _Sheet(QWidget):
    """A frameless rounded card that behaves like a dialog.

    창 자체는 투명하고 배경은 안쪽 QFrame 이 그린다 — splash.py 와 같은 구조다.
    최상위 위젯에 직접 배경을 칠하면 macOS 합성 단계에서 헤더 영역이 뚫리고,
    라운드 마스크로 오려내면 모서리가 계단처럼 깨진다. 자식이 그리면
    border-radius 가 안티에일리어싱된 채로 남는다.
    """

    def __init__(self, parent: QWidget | None, width: int):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedWidth(width)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("snapPopup")
        outer.addWidget(card)
        self._v = QVBoxLayout(card)
        self._v.setContentsMargins(0, 0, 0, 0)
        self._v.setSpacing(0)

    def center_on(self, anchor: QWidget | None) -> None:
        self._anchor = anchor
        self.adjustSize()
        self._recenter()
        self.show()
        # 본문(릴리즈 노트)은 화면에 붙은 뒤 높이가 확정되므로 한 박자 뒤에
        # 창 크기와 위치를 다시 맞춘다.
        QTimer.singleShot(0, self._recenter)

    def _recenter(self) -> None:
        self.adjustSize()
        win = getattr(self, "_anchor", None)
        win = win.window() if win is not None else None
        if win is not None:
            geo = win.frameGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)

    def _head(self, title: str, subtitle: str,
              margins: tuple[int, int, int, int] = (PAD, 15, PAD, 13),
              closable: bool = False) -> None:
        head = QFrame()
        head.setObjectName("snapHead")
        hv = QHBoxLayout(head)
        hv.setContentsMargins(*margins)
        hv.setSpacing(10)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(3)
        self.title_lab = _label(title, "cardTitle", wrap=True)
        self.sub_lab = _label(subtitle, "emptySub", wrap=True)
        text.addWidget(self.title_lab)
        text.addWidget(self.sub_lab)
        hv.addLayout(text, 1)
        if closable:
            # 제목 첫 줄과 눈높이를 맞춘다 — 부제까지 두 줄이어도 위에 붙어 있다.
            hv.addWidget(_CloseDot(self.close), 0, Qt.AlignTop)
        self._v.addWidget(head)

    def keyPressEvent(self, e):
        # 창틀이 없는 창이라 Esc 를 직접 받는다. 닫기 점 하나뿐인 시트에서는
        # 이게 유일한 키보드 탈출구다. close() 를 거치므로 내려받는 중이라면
        # UpdateSheet.closeEvent 가 평소처럼 취소로 처리한다.
        if e.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def _foot(self) -> QHBoxLayout:
        foot = QFrame()
        foot.setObjectName("snapFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(PAD, 12, PAD, 12)   # 좌우는 헤더·본문과 같은 선에 맞춘다
        fh.setSpacing(8)
        fh.addStretch(1)
        self._v.addWidget(foot)
        return fh

    @staticmethod
    def _action(text: str, kind: str, slot) -> QPushButton:
        b = button(text, kind)
        b.setMaximumHeight(34)
        b.setMinimumWidth(92)
        b.clicked.connect(slot)
        return b


class _NotesView(QTextBrowser):
    """내용 높이에 맞춰 자라는 릴리즈 노트 뷰 (``max_height`` 까지).

    높이를 고정하면 짧은 노트는 아래가 휑하게 비고 긴 노트는 잘린다. 그런데
    문서 높이는 위젯이 제 뷰포트 폭을 갖고 레이아웃을 마친 뒤에야 정확해진다 —
    붙기 전에는 0 이 나오고, adjustSize() 추정도 폭이 좁으면 15px 가까이
    모자란다. 그래서 처음 화면에 붙을 때 한 번 다시 맞춘다.
    """

    def __init__(self, markdown: str, width: int, max_height: int, roomy: bool = False):
        super().__init__()
        self.setObjectName("notesBody")
        # roomy 는 좌우 여백을 QSS 에 맡긴다는 표시 — 시트 폭 그대로 놓이는
        # 릴리즈 노트용이다. 업데이트 시트의 노트는 바깥 레이아웃이 이미 여백을
        # 주므로 켜지 않는다 (켜면 제목보다 안쪽으로 밀려 줄이 어긋난다).
        self.setProperty("roomy", roomy)
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenExternalLinks(True)
        self.setFixedWidth(width)
        self._max = max_height
        self._settled = False
        self.setMarkdown(markdown or "_릴리즈 노트가 비어 있습니다._")
        self._space_versions()
        self.document().adjustSize()        # 붙기 전 근사치 (창이 납작해 보이지 않게)
        self._fit()

    def _fit(self) -> None:
        self.setFixedHeight(int(min(self._max, self.document().size().height() + 22)))

    # ── 버전 사이 경계 ──────────────────────────────────────────────
    def _version_heads(self):
        """첫 버전을 뺀 버전 머리글 블록들 — 그 위가 버전이 바뀌는 자리다.

        건너뛴 버전이 있을 때만 머리글이 붙으므로(updater._collect_notes),
        한 버전짜리 노트에서는 아무것도 나오지 않는다.
        """
        block, first = self.document().begin(), True
        while block.isValid():
            if block.blockFormat().headingLevel() == 2:
                if not first:
                    yield block
                first = False
            block = block.next()

    def _space_versions(self) -> None:
        """버전이 바뀌는 자리를 벌린다. 그 한가운데를 paintEvent 가 선으로 메운다."""
        cursor = QTextCursor(self.document())
        for block in self._version_heads():
            fmt = block.blockFormat()
            fmt.setTopMargin(VERSION_GAP)
            cursor.setPosition(block.position())
            cursor.setBlockFormat(fmt)

    def paintEvent(self, event):
        """버전 경계에 구분선을 긋는다.

        마크다운의 `---` 를 쓰면 문서 안에 남지만, Qt 가 그리는 그 선은 본문
        글자색을 따라가 너무 진하고 팔레트로도 char format 으로도 바뀌지 않는다.
        여기서 직접 그으면 테마의 테두리 색을 그대로 쓸 수 있고, 원본 노트
        (릴리즈 본문 = CHANGELOG)에 표시용 문자를 섞지 않아도 된다.
        """
        super().paintEvent(event)
        layout = self.document().documentLayout()
        offset = -self.verticalScrollBar().value()
        painter = QPainter(self.viewport())
        painter.setPen(QColor(C["border"]))
        for block in self._version_heads():
            top = layout.blockBoundingRect(block).top() + offset
            y = int(top - VERSION_GAP / 2)
            painter.drawLine(0, y, self.viewport().width(), y)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._settled:
            self._settled = True
            self._fit()


class NotesSheet(_Sheet):
    """최신 릴리즈 노트 본문만 앱 안에서 보여준다 (브라우저를 열지 않는다).

    읽으라고 띄우는 창이라 다른 시트보다 여백을 넉넉히 준다. 아래 버튼 줄도
    두지 않는다 — 누를 것이 "닫기" 하나뿐인데 줄 하나를 통째로 쓰면 본문만
    좁아진다. 그 자리를 오른쪽 위 닫기 점이 대신한다 (Esc 도 받는다).
    """

    WIDTH = 460
    MAX_BODY = 320

    def __init__(self, release: updater.Release, parent: QWidget | None = None):
        super().__init__(parent, self.WIDTH)
        self._head(f"릴리즈 노트  ·  {release.tag}",
                   f"{release.published} 릴리즈" if release.published else "",
                   margins=(NOTES_PAD, 20, NOTES_PAD, 17), closable=True)
        # 본문의 좌우 여백은 QSS(#notesBody)가, 위아래는 이 컨테이너가 잡는다.
        # 높이를 여기서 주면 _NotesView 의 높이 계산은 문서 크기만 보면 된다.
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 12, 0, 22)
        bv.setSpacing(0)
        bv.addWidget(_NotesView(release.notes, self.WIDTH, self.MAX_BODY, roomy=True))
        self._v.addWidget(body)


class UpdateSheet(_Sheet):
    """새 버전 안내 → 내려받기 → 재시작. 각 단계를 한 창 안에서 바꿔 낀다."""

    progress = Signal(int, int)     # 워커 스레드에서 GUI 스레드로 진행률 전달
    WIDTH = 440

    def __init__(self, release: updater.Release, parent: QWidget | None = None):
        super().__init__(parent, self.WIDTH)
        self._release = release
        self._zip = updater.download_path(release)
        self._cancelled = False
        self._downloading = False

        size_mb = release.asset_size / (1024 * 1024)
        self._head(f"새 버전 {release.tag} 이 있습니다",
                   f"{__version__}  →  {release.version}   ·   "
                   f"{release.asset_name}  {size_mb:.1f} MB")

        self._body = QWidget()
        self._bv = QVBoxLayout(self._body)
        self._bv.setContentsMargins(PAD, 14, PAD, 14)
        self._bv.setSpacing(9)
        self._v.addWidget(self._body)
        self._buttons = self._foot()

        self.progress.connect(self._on_progress)
        self._show_release_notes()

    # ── 단계별 화면 ─────────────────────────────────────────────────
    @staticmethod
    def _drop(item) -> None:
        """레이아웃에서 뺀 위젯을 위젯 트리에서도 바로 떼낸다.

        deleteLater() 만 하면 파괴는 이벤트 루프 다음 차례로 밀리고, 그 사이의
        sizeHint 에는 사라질 위젯의 높이가 그대로 잡혀 창이 필요 이상으로 커진다.
        """
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()

    def _clear_body(self) -> None:
        while self._bv.count():
            self._drop(self._bv.takeAt(0))

    def _clear_buttons(self) -> None:
        while self._buttons.count() > 1:            # addStretch 는 남겨둔다
            self._drop(self._buttons.takeAt(1))

    def _add_button(self, text: str, kind: str, slot) -> QPushButton:
        b = self._action(text, kind, slot)
        self._buttons.addWidget(b)
        return b

    def _fit(self) -> None:
        """단계마다 내용 높이가 달라지므로 창을 다시 맞춘다 — 그러지 않으면
        릴리즈 노트를 걷어낸 뒤에도 그만큼 빈 자리가 남는다."""
        self.setMinimumHeight(0)
        self._body.layout().activate()   # 방금 뺀/넣은 위젯까지 반영된 크기를 읽는다
        self._v.activate()
        self.resize(self.width(), self.sizeHint().height())

    def _show_release_notes(self) -> None:
        self._clear_body()
        self._clear_buttons()
        notes = self._release.notes.strip()
        if notes:
            self._bv.addWidget(_label("변경 사항", "sectionLabel"))
            self._bv.addWidget(_NotesView(notes, self.WIDTH - PAD * 2, 200))
        self._add_button("나중에", "ghost", self.close)
        self._add_button("업데이트", "primary", self._start_download)
        self._fit()

    def _start_download(self) -> None:
        self._clear_body()
        self._clear_buttons()
        self.title_lab.setText("업데이트 내려받는 중")
        self.sub_lab.setText(f"{self._release.asset_name}  ·  "
                             f"{self._release.asset_size / (1024 * 1024):.1f} MB")
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setRange(0, 100)
        self._bv.addWidget(self._bar)
        self._amount = _label("0 MB / …", "emptySub")
        self._bv.addWidget(self._amount)
        self._add_button("취소", "ghost", self.close)
        self._fit()

        self._downloading = True
        run_async(updater.download, self._downloaded, self._failed,
                  self._release, self._zip,
                  on_progress=self.progress.emit, cancel=lambda: self._cancelled)

    def closeEvent(self, event):
        """내려받는 중에 닫으면 취소로 본다.

        워커가 아직 이 객체로 진행률을 보내고 있으므로 지금 파괴하면
        "Signal source has been deleted" 로 죽는다. 숨기기만 하고, 워커가
        돌아온 뒤에 파괴한다 (_dismissed).
        """
        if self._downloading:
            self._cancelled = True
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)

    def _dismissed(self) -> bool:
        """사용자가 이미 창을 닫았다면 결과를 그리지 않고 정리만 한다."""
        if self.isHidden():
            self.deleteLater()
            return True
        return False

    def _on_progress(self, done: int, total: int) -> None:
        mb = 1024 * 1024
        if total:
            self._bar.setValue(int(done * 100 / total))
            self._amount.setText(f"{done / mb:.1f} MB / {total / mb:.1f} MB")
        else:
            self._amount.setText(f"{done / mb:.1f} MB")

    def _downloaded(self, error: str | None) -> None:
        self._downloading = False
        if self._dismissed():
            return
        if error == updater.CANCELLED:
            self.close()
            return
        if error:
            self._failed(error)
            return
        self._clear_body()
        self._clear_buttons()
        self.title_lab.setText("재시작하면 적용됩니다")
        self.sub_lab.setText(f"{self._release.tag} 로 교체할 준비가 끝났습니다")
        self._bv.addWidget(_label(
            "‘지금 재시작’ 을 누르면 앱이 닫히고 새 버전으로 다시 열립니다.",
            "emptySub", wrap=True))
        self._add_button("나중에", "ghost", self.close)
        self._add_button("지금 재시작", "primary", self._apply)
        self._fit()

    def _failed(self, message: str) -> None:
        self._downloading = False
        if self._dismissed():
            return
        self._clear_body()
        self._clear_buttons()
        self.title_lab.setText("업데이트하지 못했습니다")
        self.sub_lab.setText(f"{__version__} 그대로 사용합니다")
        self._bv.addWidget(_label(str(message), "emptySub", wrap=True))
        self._add_button("닫기", "ghost", self.close)
        self._fit()

    def _apply(self) -> None:
        # 마커를 먼저 남긴다 — 교체가 성공해 새 버전이 뜨면 그때 안내한다.
        updater.mark_pending(self._release.version)
        try:
            updater.launch_swap(self._zip)
        except Exception as exc:  # noqa: BLE001 - 헬퍼 실행 실패는 여기서만 보고 가능
            self._failed(f"업데이트 도우미를 실행하지 못했습니다: {exc}")
            return
        # 헬퍼가 이 프로세스의 종료를 기다리고 있다 — 바로 닫는다.
        QApplication.instance().quit()


class SettingsPanel(QFrame):
    """창 오른쪽에 붙는 설정 영역.

    별도 팝업 창이 아니라 페이지 레이아웃의 일부다 — 열리면 자리를 차지해
    본문이 밀리고, 창 밖으로 나갈 일도 둥근 모서리를 마스크로 오려낼 일도 없다.
    버전은 여기서만 보여주고, 상태 줄이 확인 결과를 대신한다.
    """

    WIDTH = 264

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setFixedWidth(self.WIDTH)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 20)
        v.setSpacing(0)
        v.addStretch(1)                     # 내용을 아래에 붙인다

        v.addWidget(_label("Sealock", "panelName"))
        v.addSpacing(3)
        self.status = _label("", "panelNote", wrap=True)
        v.addWidget(self.status)
        v.addSpacing(14)
        sep = QFrame()
        sep.setObjectName("panelSep")
        v.addWidget(sep)
        v.addSpacing(6)

        self.check_btn = self._row("⟳   업데이트 확인", self._check)
        self.notes_btn = self._row("↗   릴리즈 노트 보기", self._notes)
        v.addWidget(self.check_btn)
        v.addWidget(self.notes_btn)
        self.hide()                         # 레이아웃 자리도 차지하지 않는다
        self._reset_status()

    def _row(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("menuItem")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def toggle(self) -> None:
        """설정 버튼으로 여닫기. 바깥 배경을 눌러도 닫힌다 (ConnectionPage)."""
        if self.isVisible():
            self.hide()
        else:
            self._reset_status()
            self.show()

    def mousePressEvent(self, e):
        # 패널 안을 누른 것은 "바깥 클릭" 이 아니다. QFrame 은 마우스 이벤트를
        # 그냥 흘려보내서 부모인 페이지까지 올라가는데, 페이지는 그걸 배경
        # 클릭으로 읽고 방금 연 패널을 도로 닫아버린다.
        e.accept()

    def _reset_status(self) -> None:
        """열 때마다 버전 — 업데이트할 수 없는 빌드면 그 이유까지 — 를 보여준다."""
        self.status.setText(updater.blocked_reason() or f"v{__version__}")

    def _busy(self, on: bool, text: str) -> None:
        self.check_btn.setEnabled(not on)
        self.notes_btn.setEnabled(not on)
        self.status.setText(text)

    # ── 업데이트 확인 ───────────────────────────────────────────────
    def _check(self) -> None:
        blocked = updater.blocked_reason()
        if blocked:
            self.status.setText(blocked)
            return
        self._busy(True, f"v{__version__}  ·  확인 중…")
        run_async(updater.fetch_latest, self._checked, self._fetch_failed)

    def _checked(self, result) -> None:
        release, err = result
        self._busy(False, f"v{__version__}")
        if err is not None:
            self.status.setText(updater.describe(err))
            return
        if not updater.is_newer(__version__, release.version):
            self.status.setText(f"v{__version__}  ·  최신 버전입니다")
            return
        self.status.setText(f"v{__version__}  →  {release.tag} 사용 가능")
        self._open_sheet(UpdateSheet, release)

    def _open_sheet(self, sheet_cls, release) -> None:
        # 패널은 열어 둔다 — 버튼으로만 여닫기로 했으므로 여기서 닫지 않는다.
        owner = self.parentWidget()
        sheet_cls(release, owner).center_on(owner)

    def _fetch_failed(self, message: str) -> None:
        self._busy(False, f"v{__version__}")
        self.status.setText(f"확인 실패: {message}")

    # ── 릴리즈 노트 ─────────────────────────────────────────────────
    def _notes(self) -> None:
        self._busy(True, f"v{__version__}  ·  불러오는 중…")
        run_async(updater.fetch_latest, self._notes_ready, self._fetch_failed)

    def _notes_ready(self, result) -> None:
        release, err = result
        self._busy(False, f"v{__version__}")
        if err is not None:
            self.status.setText(updater.describe(err))
            return
        self._open_sheet(NotesSheet, release)
