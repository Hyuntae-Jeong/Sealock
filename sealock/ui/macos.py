"""macOS window chrome — drop the title bar, keep the traffic lights.

macOS lets a window hide its title bar without going frameless: the close /
minimise / zoom buttons belong to the *window*, not to the title bar, so they
survive on their own. Three AppKit switches do it — the content view grows to
the full window (``NSWindowStyleMaskFullSizeContentView``), the title bar loses
its background (``titlebarAppearsTransparent``) and its text
(``NSWindowTitleHidden``). Sealock's own topbar then sits where the title bar
used to be, the way VS Code and Spotify do it.

프레임리스(``Qt.FramelessWindowHint``)로 가지 않은 이유가 이것이다 — 그 길은
신호등까지 같이 지워서 셋을 직접 그려야 하고, 눌렀을 때의 반응과 시스템 설정을
따라가는 색까지 흉내 내야 한다.

AppKit 은 ``ctypes`` 로 직접 부른다. pyobjc 를 넣으면 런타임 의존성이 하나 늘고
PyInstaller 빌드에도 딸려 들어가는데, 여기서 필요한 건 셀렉터 몇 개뿐이다.

macOS 가 아니거나 Qt 가 코코아 플러그인으로 떠 있지 않으면(오프스크린 스모크
테스트 등) 아무 일도 하지 않고 ``False`` 를 돌려준다.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QWidget

# NSWindow.h 의 상수들.
_STYLE_MASK_FULL_SIZE_CONTENT_VIEW = 1 << 15
_TITLE_VISIBILITY_HIDDEN = 1

#: 신호등 세 개가 창 왼쪽 위에 차지하는 폭(pt). 톱바 왼쪽을 이만큼 비워 둬야
#: 마스코트와 그 뒤로 뜨고 지는 해·달이 버튼에 걸리지 않는다.
TRAFFIC_LIGHTS_WIDTH = 96


def hide_titlebar(window: QMainWindow, topbar: QWidget) -> bool:
    """Hide ``window``'s title bar, keeping the traffic lights, and hand its
    duties to ``topbar``. Returns False (and changes nothing) off macOS."""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    if not _strip_native_titlebar(window):
        return False

    # Qt 6.9 부터 최상위 위젯의 레이아웃이 safe area 를 존중한다. 제목표시줄
    # 높이만큼 콘텐츠를 밀어내므로, 꺼야 톱바가 진짜 맨 위까지 올라온다.
    window.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
    central = window.centralWidget()
    if central is not None:
        central.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)

    layout = topbar.layout()
    if layout is not None:
        m = layout.contentsMargins()
        layout.setContentsMargins(TRAFFIC_LIGHTS_WIDTH, m.top(), m.right(), m.bottom())

    keeper = _Titlebar(window)
    topbar.installEventFilter(keeper)
    window.installEventFilter(keeper)
    _watch_fullscreen_exit(window)
    return True


class _Titlebar(QObject):
    """제목표시줄이 하던 나머지 일을 톱바가 넘겨받고, 그 상태를 지킨다.

    톱바에 걸면 — 창을 잡고 옮길 데가 없어지므로 빈 곳을 끌면 창이 따라오게
    하고, 더블클릭에는 확대/복원을 붙인다. 마스코트나 단계 버튼처럼 스스로
    클릭을 받는 위젯은 자기 이벤트를 먼저 가져가므로 여기까지 내려오지 않는다.

    창에 걸면 — 창이 다시 만들어지는 등으로 스타일 마스크가 풀렸을 때 되돌린다.
    전체화면을 오가는 길만은 이 필터로 못 잡는다. AppKit 이 애니메이션이 *끝난*
    뒤에 마스크를 되돌려 놓는데 그 시점에는 Qt 이벤트가 더 오지 않아서다 —
    거기는 ``_watch_fullscreen_exit`` 가 맡는다.

    창을 옮기는 일은 ``QWindow.startSystemMove()`` 에 넘기지 않고 직접 한다.
    그 API 는 드래그를 통째로 AppKit 에 넘기는데, AppKit 이 자기 루프 안에서
    버튼을 뗀 이벤트까지 삼켜 버려 Qt 는 버튼이 아직 눌린 줄 안다. 그러면 손을
    떼고 같은 자리에서 다시 누른 두 번째 클릭이 '누름'으로 보이지 않아 창이
    따라오지 않는다 — 마우스를 움직여 Qt 의 상태가 다시 맞춰져야 풀린다.
    여기서 직접 옮기면 누름·이동·뗌이 전부 Qt 를 거치므로 어긋날 자리가 없다.
    """

    _RESTORE_ON = {QEvent.WindowStateChange, QEvent.Resize}

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self._window = window
        self._grab: QPoint | None = None    # 누른 순간의 커서 위치 (전역)
        self._origin: QPoint | None = None  # 그때의 창 위치

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._window:
            if (event.type() in self._RESTORE_ON
                    and not self._window.isFullScreen()
                    and not _has_full_size_content_view(self._window)):
                # 다시 씌우면 safe area 가 또 바뀌어 이 자리로 돌아오지만,
                # 그때는 마스크가 서 있으므로 한 번에 멈춘다.
                _strip_native_titlebar(self._window)
            return False

        kind = event.type()
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            # 여기서 이벤트를 받아 두어야 이어지는 이동·뗌도 톱바로 온다.
            self._grab = event.globalPosition().toPoint()
            self._origin = self._window.pos()
            return True
        if (kind == QEvent.MouseMove and self._grab is not None
                and event.buttons() & Qt.LeftButton):
            # 창이 커서 밑에서 움직이므로 창 기준 좌표는 못 쓴다 — 전역 좌표의
            # 이동량만 더한다.
            self._window.move(self._origin + event.globalPosition().toPoint() - self._grab)
            return True
        if kind == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._grab = self._origin = None
            return True
        if kind == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            self._grab = self._origin = None
            if self._window.isMaximized():
                self._window.showNormal()
            else:
                self._window.showMaximized()
            return True
        return False


# ── AppKit (ctypes) ─────────────────────────────────────────────────────
# objc_msgSend 는 가변 인자라, 부를 때마다 그 호출의 서명대로 다시 캐스팅해야
# 한다 — arm64 에서는 인자가 레지스터에 실리는 방식이 서명마다 달라 필수다.

def _load_objc():
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        return objc
    except Exception:  # noqa: BLE001 - 창 꾸밈이 실패해도 앱은 그대로 뜬다
        return None


_OBJC = _load_objc() if sys.platform == "darwin" else None


def _sel(name: str) -> ctypes.c_void_p:
    return ctypes.c_void_p(_OBJC.sel_registerName(name.encode()))


def _send(restype, *argtypes):
    return ctypes.cast(
        _OBJC.objc_msgSend,
        ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes),
    )


def _class(name: str) -> ctypes.c_void_p:
    _OBJC.objc_getClass.restype = ctypes.c_void_p
    _OBJC.objc_getClass.argtypes = [ctypes.c_char_p]
    return ctypes.c_void_p(_OBJC.objc_getClass(name.encode()))


def _ns_window(widget: QWidget) -> ctypes.c_void_p | None:
    """The NSWindow behind ``widget``, or None if there isn't one to reach."""
    if _OBJC is None:
        return None
    try:
        view = ctypes.c_void_p(int(widget.winId()))
        window = ctypes.c_void_p(_send(ctypes.c_void_p)(view, _sel("window")))
        return window if window.value else None
    except Exception:  # noqa: BLE001
        return None


def _has_full_size_content_view(widget: QWidget) -> bool:
    window = _ns_window(widget)
    if window is None:
        return False
    mask = _send(ctypes.c_ulong)(window, _sel("styleMask"))
    return bool(mask & _STYLE_MASK_FULL_SIZE_CONTENT_VIEW)


def _strip_native_titlebar(widget: QWidget) -> bool:
    """The AppKit half: three setters on the widget's NSWindow."""
    window = _ns_window(widget)
    if window is None:
        return False
    try:
        mask = _send(ctypes.c_ulong)(window, _sel("styleMask"))
        _send(None, ctypes.c_ulong)(
            window, _sel("setStyleMask:"), mask | _STYLE_MASK_FULL_SIZE_CONTENT_VIEW)
        _send(None, ctypes.c_bool)(window, _sel("setTitlebarAppearsTransparent:"), True)
        _send(None, ctypes.c_long)(
            window, _sel("setTitleVisibility:"), _TITLE_VISIBILITY_HIDDEN)
        return True
    except Exception:  # noqa: BLE001
        return False


# ── 전체화면에서 돌아오는 길 ────────────────────────────────────────────
# 전체화면에 들어가면 AppKit 이 스타일 마스크를 원래대로 돌려놓고, 나올 때
# 되돌려 주지 않는다. 그래서 초록 버튼을 한 번 눌렀다 나오면 제목표시줄이
# 되살아난다 — macOS 10.10 부터 초록 버튼이 곧 전체화면이니 가장 밟기 쉬운 길이다.
#
# 되돌리는 시점은 나오는 애니메이션이 *끝난* 뒤여야 한다. 그전에 씌우면 마지막에
# 덮인다. 그 순간을 정확히 짚어 주는 건 AppKit 의 알림뿐이라(Qt 이벤트는 거기서
# 끊긴다) 알림을 받을 객체를 런타임에 만들어 등록한다.

_FULLSCREEN_EXIT = "NSWindowDidExitFullScreenNotification"
_HANDLER = "sealockWindowDidExitFullScreen:"

_observer_class: ctypes.c_void_p | None = None
_watched: dict[int, QWidget] = {}   # 옵저버 주소 → 그 옵저버가 지키는 창
_keepalive: list[object] = []       # ctypes 콜백은 붙들고 있어야 살아 있다


def _watch_fullscreen_exit(widget: QWidget) -> bool:
    """``widget`` 이 전체화면에서 빠져나올 때마다 제목표시줄을 다시 지운다."""
    window = _ns_window(widget)
    if window is None or not _register_observer_class():
        return False
    try:
        observer = _send(ctypes.c_void_p)(
            ctypes.c_void_p(_send(ctypes.c_void_p)(_observer_class, _sel("alloc"))),
            _sel("init"))
        name = _send(ctypes.c_void_p, ctypes.c_char_p)(
            _class("NSString"), _sel("stringWithUTF8String:"),
            _FULLSCREEN_EXIT.encode())
        center = _send(ctypes.c_void_p)(_class("NSNotificationCenter"),
                                        _sel("defaultCenter"))
        # object: 를 이 창으로 좁혀, 다른 창의 전체화면에는 반응하지 않는다.
        _send(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            ctypes.c_void_p(center), _sel("addObserver:selector:name:object:"),
            ctypes.c_void_p(observer), _sel(_HANDLER), ctypes.c_void_p(name), window)
    except Exception:  # noqa: BLE001
        return False
    # alloc/init 로 +1 된 참조를 아무도 풀지 않으므로 옵저버는 앱과 함께 산다.
    _watched[observer] = widget
    return True


def _register_observer_class() -> bool:
    """알림을 받을 ObjC 클래스를 한 번만 만들어 런타임에 등록한다."""
    global _observer_class
    if _observer_class is not None:
        return True
    try:
        _OBJC.objc_allocateClassPair.restype = ctypes.c_void_p
        _OBJC.objc_allocateClassPair.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                 ctypes.c_size_t]
        _OBJC.class_addMethod.restype = ctypes.c_bool
        _OBJC.class_addMethod.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_char_p]
        _OBJC.objc_registerClassPair.argtypes = [ctypes.c_void_p]

        cls = ctypes.c_void_p(_OBJC.objc_allocateClassPair(
            _class("NSObject"), b"SealockTitlebarObserver", 0))
        if not cls.value:
            return False

        def on_exit(observer, _cmd, _note):
            widget = _watched.get(observer)
            if widget is not None:
                # 창이 이미 사라졌다면 _ns_window 가 조용히 None 을 준다.
                _strip_native_titlebar(widget)

        imp = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_void_p)(on_exit)
        _keepalive.append(imp)
        # "v@:@" — 반환 없음, (self, _cmd, NSNotification*) 을 받는다.
        _OBJC.class_addMethod(cls, _sel(_HANDLER), ctypes.cast(imp, ctypes.c_void_p),
                              b"v@:@")
        _OBJC.objc_registerClassPair(cls)
        _observer_class = cls
        return True
    except Exception:  # noqa: BLE001
        return False
