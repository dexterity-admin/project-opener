"""Win32 plumbing for capture: windows, placement, monitors, processes.  Owner: builder 2.

From the spike (``spikes/capture/capture.py`` sections 1 and restore): EnumWindows
over visible, titled, un-cloaked top-level windows, skipping tool windows, the
shell classes and this process's own windows (the pill, the picker, the shell).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from project_opener.core import models as M

SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                           "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow"})


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


def enumerate_windows(exclude_pids: set[int] | None = None) -> list[WindowInfo]:
    """Visible top-level windows worth capturing, z-order (front first)."""
    raise NotImplementedError("enumerate_windows")


def get_placement(hwnd: int) -> M.WindowPlacement:
    raise NotImplementedError("get_placement")


def apply_placement(hwnd: int, placement: M.WindowPlacement) -> bool:
    """SetWindowPlacement(normal rect) then SW_SHOWMAXIMIZED when saved maximised; verify; True when it held."""
    raise NotImplementedError("apply_placement")


def monitors() -> list[M.Monitor]:
    raise NotImplementedError("monitors")


def foreground_window() -> int:
    raise NotImplementedError("foreground_window")


def root_of(hwnd: int) -> int:
    """GetAncestor(hwnd, GA_ROOT)."""
    raise NotImplementedError("root_of")


def window_info(hwnd: int) -> WindowInfo | None:
    """One window's WindowInfo (for "add this window"); None when it is not a capturable window."""
    raise NotImplementedError("window_info")


def process_name(pid: int) -> tuple[str, str]:
    """(image name, full exe path); ("", "") when access is denied."""
    raise NotImplementedError("process_name")
