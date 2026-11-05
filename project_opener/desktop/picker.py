"""The window picker: a transparent click-through overlay per monitor.  Owner: builder 3 (DESKTOP).

While active, a timer reads the cursor, takes ``WindowFromPoint`` -> ``GetAncestor(GA_ROOT)``
(skipping our own windows), asks ``app.capture.identifyForPicker(hwnd)`` and frames
the window green (identifiable) or amber, with the label from ``hoverIdentified``.
Click adds (``app.capture.addWindow``), Esc cancels.  QML: ``qml/desktop/PickerOverlay.qml``.

The overlays are ``WindowTransparentForInput`` (WS_EX_TRANSPARENT | WS_EX_LAYERED), so
``WindowFromPoint`` sees through them.  The click and Esc are read with low-level mouse and
keyboard hooks that exist only while the picker is open and swallow just that click / that Esc,
so the window being picked is not clicked as well.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot

log = logging.getLogger(__name__)

GA_ROOT = 2
GW_HWNDNEXT = 2
WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0201, 0x0202, 0x0204, 0x0205
VK_ESCAPE = 0x1B
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def to_local(rect: tuple[int, int, int, int], origin: tuple[int, int], dpr: float) -> list[float]:
    """A physical-pixel screen rect (l, t, r, b) -> [x, y, w, h] in an overlay's logical coordinates.

    Qt 6 keeps each screen's top-left at its native position and scales sizes by the screen's
    device pixel ratio, so a point maps as ``(p - origin) / dpr`` inside that screen's overlay.
    """
    dpr = dpr or 1.0
    left, top, right, bottom = rect
    ox, oy = origin
    return [(left - ox) / dpr, (top - oy) / dpr, (right - left) / dpr, (bottom - top) / dpr]


# -------------------------------------------------------------- Win32 bits
def _user32() -> Any:
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.WindowFromPoint.restype = wintypes.HWND
    u.WindowFromPoint.argtypes = [wintypes.POINT]
    u.GetAncestor.restype = wintypes.HWND
    u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindow.restype = wintypes.HWND
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    return u


def window_pid(hwnd: int) -> int:
    from ctypes import wintypes
    pid = wintypes.DWORD(0)
    ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """The visible frame (DWMWA_EXTENDED_FRAME_BOUNDS, without the invisible resize border)."""
    from ctypes import wintypes
    rect = wintypes.RECT()
    try:
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rect),
                                                        ctypes.sizeof(rect))
        if hr == 0:
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:  # noqa: BLE001
        pass
    ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 512)
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(ctypes.c_void_p(hwnd), buf, 256)
    return buf.value


def cursor_pos() -> tuple[int, int]:
    from ctypes import wintypes
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def root_window_at(x: int, y: int, exclude: set[int] | None = None) -> int:
    """Top-level window under the screen point, ignoring ``exclude`` hwnds, this process's windows and
    the shell (desktop, taskbar); 0 when none."""
    if sys.platform != "win32":
        return 0
    from ctypes import wintypes
    u = _user32()
    exclude = exclude or set()
    me = os.getpid()
    hwnd = u.WindowFromPoint(wintypes.POINT(x, y))
    root = int(u.GetAncestor(hwnd, GA_ROOT) or 0) if hwnd else 0

    def acceptable(h: int) -> bool:
        return bool(h) and h not in exclude and window_pid(h) != me and window_class(h) not in SHELL_CLASSES

    if acceptable(root):
        return root
    if not root or window_class(root) in SHELL_CLASSES:
        return 0
    # One of ours is on top at that point: walk down the z-order for the next visible window there.
    h = int(u.GetWindow(wintypes.HWND(root), GW_HWNDNEXT) or 0)
    for _ in range(2000):
        if not h:
            return 0
        if u.IsWindowVisible(wintypes.HWND(h)) and not u.IsIconic(wintypes.HWND(h)):
            left, top, right, bottom = window_rect(h)
            if left <= x < right and top <= y < bottom and window_pid(h) != me and h not in exclude:
                return 0 if window_class(h) in SHELL_CLASSES else h
        h = int(u.GetWindow(wintypes.HWND(h), GW_HWNDNEXT) or 0)
    return 0


class LowLevelHooks:
    """WH_MOUSE_LL + WH_KEYBOARD_LL for as long as the picker (or the panel's Esc) needs them.

    ``on_click(button)`` gets "left"/"right" and returns True to swallow the click (the matching
    button-up is swallowed too); ``on_escape()`` returns True to swallow Esc.  The callbacks run on
    the GUI thread (low-level hooks call back on the installing thread's message loop) and must be
    quick: Windows drops a hook that keeps it waiting.
    """

    def __init__(self, on_click: Callable[[str], bool] | None, on_escape: Callable[[], bool] | None):
        self.on_click = on_click
        self.on_escape = on_escape
        self._mouse = None
        self._kbd = None
        self._procs: list[Any] = []
        self._swallow_up: set[int] = set()

    @property
    def active(self) -> bool:
        return bool(self._mouse or self._kbd)

    def install(self) -> bool:
        if sys.platform != "win32" or self.active:
            return self.active
        from ctypes import wintypes
        u = ctypes.windll.user32
        hookproc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u.SetWindowsHookExW.restype = ctypes.c_void_p
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, hookproc, wintypes.HINSTANCE, wintypes.DWORD]
        u.CallNextHookEx.restype = ctypes.c_ssize_t
        u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        k32 = ctypes.windll.kernel32
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        module = k32.GetModuleHandleW(None)

        class KBD(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        def mouse(code: int, wparam: int, lparam: int) -> int:
            if code == 0:
                try:
                    if wparam in (WM_LBUTTONUP, WM_RBUTTONUP) and wparam in self._swallow_up:
                        self._swallow_up.discard(wparam)
                        return 1
                    if wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN) and self.on_click:
                        button = "left" if wparam == WM_LBUTTONDOWN else "right"
                        if self.on_click(button):
                            self._swallow_up.add(WM_LBUTTONUP if button == "left" else WM_RBUTTONUP)
                            return 1
                except Exception:  # noqa: BLE001
                    log.exception("picker mouse hook")
            return u.CallNextHookEx(None, code, wparam, lparam)

        def keyboard(code: int, wparam: int, lparam: int) -> int:
            if code == 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN) and self.on_escape:
                try:
                    if KBD.from_address(lparam).vkCode == VK_ESCAPE and self.on_escape():
                        return 1
                except Exception:  # noqa: BLE001
                    log.exception("picker keyboard hook")
            return u.CallNextHookEx(None, code, wparam, lparam)

        mproc, kproc = hookproc(mouse), hookproc(keyboard)
        self._procs = [mproc, kproc]
        if self.on_click:
            self._mouse = u.SetWindowsHookExW(WH_MOUSE_LL, mproc, module, 0)
        if self.on_escape:
            self._kbd = u.SetWindowsHookExW(WH_KEYBOARD_LL, kproc, module, 0)
        return self.active

    def remove(self) -> None:
        if sys.platform != "win32":
            return
        u = ctypes.windll.user32
        u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        for attr in ("_mouse", "_kbd"):
            h = getattr(self, attr)
            if h:
                u.UnhookWindowsHookEx(h)
                setattr(self, attr, None)
        self._swallow_up.clear()


# ------------------------------------------------------------------ picker
class WindowPicker(QObject):
    hovered = Signal(int, "QVariantList")      # hwnd, [l, t, r, b] in screen pixels
    finished = Signal(int)                     # hwnd or 0
    frameChanged = Signal()                    # for the overlays' QML (``picker`` context property)

    def __init__(self, facade: Any, engine: Any, qml_dir: Path | None = None):
        super().__init__(facade)
        self.facade = facade
        self.engine = engine
        self.qml_dir = qml_dir
        self.active = False
        self._overlays: list[Any] = []
        self._component = None
        self._hooks = LowLevelHooks(self._on_click, self._on_escape)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)
        self._hwnd = 0
        self._rect: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._labels: dict[int, tuple[bool, str]] = {}
        capture = getattr(facade, "capture", None)
        if capture is not None and hasattr(capture, "hoverIdentified"):
            capture.hoverIdentified.connect(self._on_identified)

    # ---------------------------------------------------- QML-facing state
    def frame(self, overlay_origin: tuple[int, int], dpr: float) -> dict[str, Any]:
        ok, label = self._labels.get(self._hwnd, (False, ""))
        known = self._hwnd in self._labels
        x, y, w, h = to_local(self._rect, overlay_origin, dpr)
        title = window_title(self._hwnd) if self._hwnd and sys.platform == "win32" else ""
        return {"hwnd": self._hwnd, "x": x, "y": y, "w": w, "h": h, "visible": bool(self._hwnd),
                "ok": ok, "known": known, "label": label or title or "", "title": title}

    @Slot(int, int, float, result="QVariantMap")
    def frameFor(self, origin_x: int, origin_y: int, dpr: float) -> dict[str, Any]:  # noqa: N802
        return self.frame((origin_x, origin_y), dpr)

    @Slot(result=str)
    def hint(self) -> str:
        name = ""
        cap = getattr(self.facade, "capture", None)
        if cap is not None:
            name = str(cap.property("runningLabel") or cap.property("runningName") or "")
        target = f"to {name}" if name else "to the running activity"
        return f"Click a window to add it {target} · Esc to cancel"

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self.active:
            return
        self.active = True
        self._hwnd = 0
        self._labels.clear()
        self._create_overlays()
        self._hooks.install()
        self._timer.start()
        self._poll()

    def cancel(self) -> None:
        self._finish(0)

    def _finish(self, hwnd: int) -> None:
        if not self.active:
            return
        self.active = False
        self._timer.stop()
        self._hooks.remove()
        for ov in self._overlays:
            ov.hide()
        if hwnd:
            try:
                self.facade.capture.addWindow(hwnd)
            except NotImplementedError:
                log.warning("picker: app.capture.addWindow is not available yet")
        self.finished.emit(hwnd)

    def close(self) -> None:
        """On exit: hooks off, overlays destroyed."""
        self._finish(0)
        for ov in self._overlays:
            ov.deleteLater()
        self._overlays.clear()

    def _create_overlays(self) -> None:
        if self._overlays or self.engine is None or self.qml_dir is None:
            for ov in self._overlays:
                self._place_overlay(ov)
                ov.show()
            return
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine
        comp = QQmlComponent(self.engine, QUrl.fromLocalFile(str(self.qml_dir / "desktop" / "PickerOverlay.qml")))
        self._component = comp          # PySide ties created objects to the component's wrapper
        for screen in QGuiApplication.screens():
            ctx_obj = comp.createWithInitialProperties({"picker": self, "screenRef": screen})
            if ctx_obj is None:
                log.error("PickerOverlay.qml: %s", comp.errorString())
                return
            QQmlEngine.setObjectOwnership(ctx_obj, QQmlEngine.ObjectOwnership.CppOwnership)
            ctx_obj.setScreen(screen)
            self._overlays.append(ctx_obj)
            self._place_overlay(ctx_obj)
            ctx_obj.show()

    @staticmethod
    def _place_overlay(ov: Any) -> None:
        g = ov.screen().geometry()
        ov.setGeometry(g)

    def overlay_hwnds(self) -> set[int]:
        return {int(ov.winId()) for ov in self._overlays}

    # ------------------------------------------------------------- polling
    def _poll(self) -> None:
        if not self.active:
            return
        x, y = cursor_pos()
        hwnd = root_window_at(x, y, self.overlay_hwnds())
        rect = window_rect(hwnd) if hwnd else (0, 0, 0, 0)
        if hwnd != self._hwnd or rect != self._rect:
            changed = hwnd != self._hwnd
            self._hwnd, self._rect = hwnd, rect
            if changed and hwnd and hwnd not in self._labels:
                try:
                    self.facade.capture.identifyForPicker(hwnd)
                except NotImplementedError:
                    self._labels[hwnd] = (False, f"{window_title(hwnd) or 'This window'} · cannot identify yet")
            self.hovered.emit(hwnd, list(rect))
            self.frameChanged.emit()

    def _on_identified(self, hwnd: int, ok: bool, label: str) -> None:
        self._labels[int(hwnd)] = (bool(ok), str(label))
        if int(hwnd) == self._hwnd:
            self.frameChanged.emit()

    def _on_click(self, button: str) -> bool:
        if not self.active:
            return False
        hwnd = self._hwnd if button == "left" else 0
        QTimer.singleShot(0, lambda: self._finish(hwnd))   # leave the hook callback at once
        return True

    def _on_escape(self) -> bool:
        if not self.active:
            return False
        QTimer.singleShot(0, self.cancel)
        return True
