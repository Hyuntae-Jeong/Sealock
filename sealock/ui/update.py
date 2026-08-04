"""설정 패널과 수동 업데이트 화면.

첫 화면 오른쪽 아래 ⚙ 설정에서만 열린다 — 앱이 스스로 새 버전을 확인하는
경로는 없다. 설정은 창 안 패널이라 별도 창이 아니고, 업데이트/릴리즈 노트만
창으로 띄운다. 그 창의 모서리 처리는 _Sheet 주석 참조.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import updater
from ..version import __version__
from .widgets import button, run_async


def _label(text: str, obj: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


PAD = 18            # 헤더·본문·푸터가 공유하는 좌우 여백


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

    def _head(self, title: str, subtitle: str) -> None:
        head = QFrame()
        head.setObjectName("snapHead")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(PAD, 15, PAD, 13)
        hv.setSpacing(3)
        self.title_lab = _label(title, "cardTitle", wrap=True)
        self.sub_lab = _label(subtitle, "emptySub", wrap=True)
        hv.addWidget(self.title_lab)
        hv.addWidget(self.sub_lab)
        self._v.addWidget(head)

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

    def __init__(self, markdown: str, width: int, max_height: int):
        super().__init__()
        self.setObjectName("notesBody")
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenExternalLinks(True)
        self.setFixedWidth(width)
        self._max = max_height
        self._settled = False
        self.setMarkdown(markdown or "_릴리즈 노트가 비어 있습니다._")
        self.document().adjustSize()        # 붙기 전 근사치 (창이 납작해 보이지 않게)
        self._fit()

    def _fit(self) -> None:
        self.setFixedHeight(int(min(self._max, self.document().size().height() + 22)))

    def showEvent(self, event):
        super().showEvent(event)
        if not self._settled:
            self._settled = True
            self._fit()


class NotesSheet(_Sheet):
    """최신 릴리즈 노트 본문만 앱 안에서 보여준다 (브라우저를 열지 않는다)."""

    WIDTH = 460
    MAX_BODY = 320

    def __init__(self, release: updater.Release, parent: QWidget | None = None):
        super().__init__(parent, self.WIDTH)
        self._head(f"릴리즈 노트  ·  {release.tag}",
                   f"{release.published} 릴리즈" if release.published else "")
        self._v.addWidget(_NotesView(release.notes, self.WIDTH, self.MAX_BODY))
        self._foot().addWidget(self._action("닫기", "ghost", self.close))


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
        """설정 버튼 전용 여닫기. 바깥을 클릭해도 닫히지 않는다."""
        if self.isVisible():
            self.hide()
        else:
            self._reset_status()
            self.show()

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
