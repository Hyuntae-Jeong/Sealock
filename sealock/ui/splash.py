"""Startup splash — a brief, frameless brand card shown before the main window.

Sealock opens instantly, so this is a short first-impression screen (mascot +
wordmark + a sweeping loading bar), not a load-masking one. It fades in, holds,
then fades out and hands off to the main window via the ``start`` callback.
"""
from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, Qt, QTimer,
)
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout,
    QWidget,
)

from sealock.resources import asset_path
from sealock.ui.theme import C

def _splash_qss() -> str:
    """Built per call so the splash honours the active palette (light/dark)."""
    return f"""
QFrame#splashCard {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 20px; }}
QLabel#splashTitle {{ font-size: 27px; font-weight: 800; color: {C['text']}; letter-spacing: 0.5px; }}
QLabel#splashSub {{ font-size: 12px; color: {C['text_faint']}; letter-spacing: 0.3px; }}
"""

# Timing (ms): fade in, hold at full opacity, fade out.
_FADE_IN, _HOLD, _FADE_OUT = 240, 1150, 280


class _LoadingBar(QWidget):
    """A thin indeterminate bar: an indigo pill sweeps smoothly back and forth."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(190, 5)
        self._t = 0.0  # 0..1 phase, drives the pill position
        self._anim = QPropertyAnimation(self, b"phase", self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1100)
        self._anim.setLoopCount(-1)

    def start(self) -> None:
        self._anim.start()

    def _get_phase(self) -> float:
        return self._t

    def _set_phase(self, v: float) -> None:
        self._t = v
        self.update()

    phase = Property(float, _get_phase, _set_phase)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["border"]))
        p.drawRoundedRect(0, 0, w, h, r, r)

        pill = w * 0.34
        travel = w - pill
        # cosine ease → smooth 0→1→0 ping-pong with no jolt at the ends
        pos = (1 - math.cos(self._t * 2 * math.pi)) / 2
        p.setBrush(QColor(C["primary"]))
        p.drawRoundedRect(travel * pos, 0, pill, h, r, r)


class SplashScreen(QWidget):
    """Frameless rounded brand splash. Call ``start(on_done)`` once."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(_splash_qss())
        self._on_done: Callable[[], None] | None = None

        card = QFrame(self)
        card.setObjectName("splashCard")

        logo = QLabel(card)
        pix = QPixmap(asset_path("app.png")).scaled(
            200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(2.0)  # crisp 100px logical on 1x/2x displays
        logo.setPixmap(pix)
        logo.setAlignment(Qt.AlignCenter)

        title = QLabel("Sealock", card)
        title.setObjectName("splashTitle")
        title.setAlignment(Qt.AlignCenter)

        sub = QLabel("MariaDB Envers 변경 이력 뷰어", card)
        sub.setObjectName("splashSub")
        sub.setAlignment(Qt.AlignCenter)

        self._bar = _LoadingBar(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(52, 40, 52, 36)
        lay.setSpacing(12)
        lay.addWidget(logo, 0, Qt.AlignCenter)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(12)
        lay.addWidget(self._bar, 0, Qt.AlignCenter)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(31, 36, 64, 65))
        card.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(34, 30, 34, 40)  # breathing room for the shadow
        outer.addWidget(card)

        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._pending: Callable[[], None] | None = None
        self._anim.finished.connect(self._on_fade_done)

    # -- public ----------------------------------------------------------
    def start(self, on_done: Callable[[], None]) -> None:
        """Show the splash, then fade out and call ``on_done`` (e.g. window.show)."""
        self._on_done = on_done
        self.setWindowOpacity(0.0)
        self.adjustSize()
        self._center()
        self.show()
        self.raise_()
        self._bar.start()
        self._fade(0.0, 1.0, _FADE_IN, QEasingCurve.OutCubic)
        QTimer.singleShot(_FADE_IN + _HOLD, self._leave)

    # -- internal --------------------------------------------------------
    def _leave(self) -> None:
        self._fade(1.0, 0.0, _FADE_OUT, QEasingCurve.InCubic, self._finish)

    def _finish(self) -> None:
        if self._on_done is not None:
            self._on_done()
        self.close()

    def _fade(self, start: float, end: float, ms: int,
              curve: QEasingCurve.Type, done: Callable[[], None] | None = None) -> None:
        self._anim.stop()  # stop() does not emit finished, so _pending is safe
        self._pending = done
        self._anim.setDuration(ms)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(curve)
        self._anim.start()

    def _on_fade_done(self) -> None:
        cb, self._pending = self._pending, None
        if cb is not None:
            cb()

    def _center(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center() - self.rect().center())
