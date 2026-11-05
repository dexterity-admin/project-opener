"""Win32 plumbing for capture: windows, placement, monitors, processes.  Owner: builder 2.

From the spike (``spikes/capture/capture.py`` sections 1 and restore): EnumWindows
over visible, titled, un-cloaked top-level windows, skipping tool windows, the
shell classes and this process's own windows (the pill, the picker, the shell).

Read-only except ``apply_placement``, which the Restorer calls only on windows it
has just opened (never on a window the user already had).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
from dataclasses import dataclass, field

from project_opener.core import models as M

SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                           "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow"})

IS_WIN = sys.platform == "win32"

SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
DWMWA_CLOAKED = 14
MONITOR_DEFAULTTONEAREST = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    window_class: str
    pid: int
    process: str = ""                 # "EXCEL.EXE"
    exe: str = ""
    placement: M.WindowPlacement | None = None
    extra: dict = field(default_factory=dict)

    @property
    def cache_key(self) -> tuple[int, str, str, int]:
        """Identity-cache key: re-identify only when this changes (spike section 5.1)."""
        return (self.hwnd, self.title, self.window_class, self.pid)


# ---------------------------------------------------------------- ctypes setup
if IS_WIN:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        _dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:  # pragma: no cover
        _dwmapi = None

    class _RECT(ctypes.Structure):
        _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", wt.LONG), ("y", wt.LONG)]

    class _WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT), ("ptMinPosition", _POINT),
                    ("ptMaxPosition", _POINT), ("rcNormalPosition", _RECT)]

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", wt.DWORD),
                    ("szDevice", wt.WCHAR * 32)]

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(_RECT), wt.LPARAM)

    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wt.LPARAM]
    _user32.EnumChildWindows.argtypes = [wt.HWND, _WNDENUMPROC, wt.LPARAM]
    _user32.IsWindowVisible.argtypes = [wt.HWND]
    _user32.IsWindow.argtypes = [wt.HWND]
    _user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
    _user32.GetWindow.restype = wt.HWND
    _user32.GetParent.argtypes = [wt.HWND]
    _user32.GetParent.restype = wt.HWND
    _user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    _user32.GetAncestor.restype = wt.HWND
    _user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = wt.LONG
    _user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    _user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    _user32.GetWindowPlacement.argtypes = [wt.HWND, ctypes.POINTER(_WINDOWPLACEMENT)]
    _user32.SetWindowPlacement.argtypes = [wt.HWND, ctypes.POINTER(_WINDOWPLACEMENT)]
    _user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(_RECT)]
    _user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    _user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    _user32.MonitorFromWindow.restype = wt.HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(_MONITORINFOEXW)]
    _user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(_RECT), _MONITORENUMPROC, wt.LPARAM]
    _user32.GetForegroundWindow.restype = wt.HWND
    _kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _kernel32.OpenProcess.restype = wt.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    try:
        _GetDpiForWindow = _user32.GetDpiForWindow
        _GetDpiForWindow.argtypes = [wt.HWND]
        _GetDpiForWindow.restype = wt.UINT
    except AttributeError:  # pragma: no cover - before Windows 10 1607
        _GetDpiForWindow = None
    try:
        _shcore = ctypes.WinDLL("shcore")
        _GetDpiForMonitor = _shcore.GetDpiForMonitor
        _GetDpiForMonitor.argtypes = [wt.HMONITOR, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT)]
    except (OSError, AttributeError):  # pragma: no cover
        _GetDpiForMonitor = None


def _rect(r) -> list[int]:
    return [int(r.left), int(r.top), int(r.right), int(r.bottom)]


# ---------------------------------------------------------------- window basics
def window_text(hwnd: int) -> str:
    n = _user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(_user32.IsWindow(hwnd))


def is_cloaked(hwnd: int) -> bool:
    if _dwmapi is None:
        return False
    val = ctypes.c_int(0)
    try:
        _dwmapi.DwmGetWindowAttribute(wt.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    except OSError:
        return False
    return val.value != 0


def find_child(hwnd: int, cls: str) -> int:
    """The first descendant window of class ``cls`` (EXCEL7, _WwG); 0 when none."""
    found: list[int] = []

    @_WNDENUMPROC
    def cb(h, _lp):
        if class_name(h) == cls:
            found.append(int(h))
            return False
        return True
    _user32.EnumChildWindows(hwnd, cb, 0)
    return found[0] if found else 0


# ---------------------------------------------------------------- processes
_proc_lock = threading.Lock()
_proc_cache: dict[int, tuple[str, str]] = {}


def process_name(pid: int) -> tuple[str, str]:
    """(image name, full exe path); ("", "") when access is denied.  Cached per pid (pruned by enumerate)."""
    with _proc_lock:
        hit = _proc_cache.get(pid)
    if hit is not None:
        return hit
    name, exe = "", ""
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid) if pid else None
    if h:
        try:
            size = wt.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                exe = buf.value
                name = os.path.basename(exe)
        finally:
            _kernel32.CloseHandle(h)
    if not name and pid:
        try:
            import psutil
            p = psutil.Process(pid)
            name = p.name()
            try:
                exe = p.exe()
            except Exception:  # noqa: BLE001
                exe = ""
        except Exception:  # noqa: BLE001
            name = ""
    result = (name, exe)
    with _proc_lock:
        _proc_cache[pid] = result
    return result


def _prune_proc_cache(alive_pids: set[int]) -> None:
    with _proc_lock:
        for pid in [p for p in _proc_cache if p not in alive_pids]:
            del _proc_cache[pid]


# ---------------------------------------------------------------- placement
def _monitor_of(hwnd: int) -> tuple[str, list[int], list[int], int]:
    hmon = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
    if hmon and _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return mi.szDevice, _rect(mi.rcMonitor), _rect(mi.rcWork), int(hmon)
    return "", [0, 0, 0, 0], [0, 0, 0, 0], 0


def get_placement(hwnd: int) -> M.WindowPlacement:
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    _user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    wr = _RECT()
    window_rect = _rect(wr) if _user32.GetWindowRect(hwnd, ctypes.byref(wr)) else [0, 0, 0, 0]
    device, mrect, _work, _h = _monitor_of(hwnd)
    return M.WindowPlacement(show_cmd=int(wp.showCmd), normal_rect=_rect(wp.rcNormalPosition),
                             window_rect=window_rect, monitor=device, monitor_rect=mrect)


def placement_held(wanted: M.WindowPlacement, after: M.WindowPlacement, tolerance: int = 2) -> bool:
    """Whether ``after`` (read back) shows ``wanted``: same show state family and normal rect within ``tolerance`` px."""
    if wanted.show_cmd == SW_SHOWMAXIMIZED and after.show_cmd != SW_SHOWMAXIMIZED:
        return False
    if wanted.show_cmd == SW_SHOWMINIMIZED and after.show_cmd != SW_SHOWMINIMIZED:
        return False
    if wanted.show_cmd not in (SW_SHOWMAXIMIZED, SW_SHOWMINIMIZED) and after.show_cmd in (SW_SHOWMAXIMIZED,
                                                                                          SW_SHOWMINIMIZED):
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(wanted.normal_rect, after.normal_rect, strict=False))


def apply_placement(hwnd: int, placement: M.WindowPlacement) -> bool:
    """SetWindowPlacement(normal rect) then SW_SHOWMAXIMIZED when saved maximised; verify; True when it held."""
    if not is_window(hwnd):
        return False
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    wp.flags = 0
    wp.showCmd = SW_SHOWNORMAL
    wp.ptMinPosition = _POINT(-1, -1)
    wp.ptMaxPosition = _POINT(-1, -1)
    left, top, right, bottom = (list(placement.normal_rect) + [0, 0, 0, 0])[:4]
    wp.rcNormalPosition = _RECT(left, top, right, bottom)
    if not _user32.SetWindowPlacement(hwnd, ctypes.byref(wp)):
        return False
    if placement.show_cmd == SW_SHOWMAXIMIZED:
        _user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
    elif placement.show_cmd == SW_SHOWMINIMIZED:
        _user32.ShowWindow(hwnd, SW_SHOWMINIMIZED)
    return placement_held(placement, get_placement(hwnd))


def monitors() -> list[M.Monitor]:
    out: list[M.Monitor] = []

    @_MONITORENUMPROC
    def cb(hmon, _hdc, _lprc, _lp):
        mi = _MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            dpi = 96
            if _GetDpiForMonitor is not None:
                x, y = wt.UINT(0), wt.UINT(0)
                try:
                    if _GetDpiForMonitor(hmon, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
                        dpi = int(x.value) or 96
                except OSError:  # pragma: no cover
                    pass
            out.append(M.Monitor(device=mi.szDevice, rect=_rect(mi.rcMonitor), work=_rect(mi.rcWork), dpi=dpi,
                                 primary=bool(mi.dwFlags & 1)))
        return True
    _user32.EnumDisplayMonitors(None, None, cb, 0)
    return out


def foreground_window() -> int:
    return int(_user32.GetForegroundWindow() or 0)


def root_of(hwnd: int) -> int:
    """GetAncestor(hwnd, GA_ROOT)."""
    if not hwnd:
        return 0
    return int(_user32.GetAncestor(hwnd, GA_ROOT) or hwnd)


# ---------------------------------------------------------------- our own windows
# Brief 3.8: the app is left out of its own captures.  The process id alone misses another copy of the app
# (a frozen build's windows when the capture runs elsewhere, a second user's instance, an installed 3.2), so a
# window is ours when its process is this one, when its image is this frozen build's own executable, or when
# it is a Qt-registered window class ("Qt6..QWindowIcon") of a process whose image is ProjectOpener.exe.
OWN_IMAGE = "projectopener.exe"


def own_exe() -> str:
    """This build's executable (normalised); "" when running from source (python.exe is not ours)."""
    if getattr(sys, "frozen", False):
        return os.path.normcase(os.path.abspath(sys.executable))
    return ""


def is_qt_class(window_class: str) -> bool:
    return window_class.startswith("Qt") and "QWindow" in window_class


def is_own_window(pid: int, exe: str, window_class: str, exclude_pids: set[int],
                  own_exe_path: str | None = None) -> bool:
    """Pure: whether a window belongs to Project Opener itself (never captured, never added)."""
    if pid in exclude_pids:
        return True
    e = os.path.normcase(exe or "")
    own = own_exe() if own_exe_path is None else own_exe_path
    if own and e == own:
        return True
    return is_qt_class(window_class or "") and os.path.basename(e) == OWN_IMAGE


def is_own_hwnd(hwnd: int, exclude_pids: set[int]) -> bool:
    pid = window_pid(hwnd)
    if pid in exclude_pids:
        return True
    _name, exe = process_name(pid)
    return is_own_window(pid, exe, class_name(hwnd), exclude_pids)


# ---------------------------------------------------------------- enumeration
def _info(hwnd: int, with_placement: bool = True) -> WindowInfo:
    pid = window_pid(hwnd)
    name, exe = process_name(pid)
    return WindowInfo(hwnd=hwnd, title=window_text(hwnd), window_class=class_name(hwnd), pid=pid, process=name,
                      exe=exe, placement=get_placement(hwnd) if with_placement else None)


def capturable(hwnd: int) -> bool:
    """Visible, un-owned, titled, not a tool window, not cloaked, not a shell class."""
    if not _user32.IsWindowVisible(hwnd):
        return False
    if _user32.GetParent(hwnd):                     # owned popups and child windows
        return False
    if _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    if _user32.GetWindowTextLengthW(hwnd) <= 0:
        return False
    if class_name(hwnd) in SHELL_CLASSES:
        return False
    return not is_cloaked(hwnd)


def all_top_level_hwnds() -> set[int]:
    """Every top-level hwnd, visible or not (restore's "before" set: never touch any of these)."""
    out: set[int] = set()

    @_WNDENUMPROC
    def cb(h, _lp):
        out.add(int(h))
        return True
    _user32.EnumWindows(cb, 0)
    return out


def enumerate_windows(exclude_pids: set[int] | None = None) -> list[WindowInfo]:
    """Visible top-level windows worth capturing, z-order (front first)."""
    exclude = exclude_pids or set()
    hwnds: list[int] = []

    @_WNDENUMPROC
    def cb(h, _lp):
        h = int(h)
        try:
            if capturable(h):
                hwnds.append(h)
        except OSError:  # a window that died mid-call
            pass
        return True
    _user32.EnumWindows(cb, 0)
    out: list[WindowInfo] = []
    pids: set[int] = set()
    for h in hwnds:
        pid = window_pid(h)
        pids.add(pid)
        if pid in exclude:
            continue
        try:
            info = _info(h)
        except OSError:  # pragma: no cover
            continue
        if is_own_window(info.pid, info.exe, info.window_class, exclude):
            continue
        out.append(info)
    _prune_proc_cache(pids | exclude)
    return out


def window_info(hwnd: int) -> WindowInfo | None:
    """One window's WindowInfo (for "add this window"); None when it is not a capturable window."""
    hwnd = root_of(hwnd)
    if not is_window(hwnd) or not capturable(hwnd):
        return None
    return _info(hwnd)
