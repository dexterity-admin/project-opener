"""Explorer windows through ``Shell.Application.Windows()``.  Owner: builder 2.

250-650 ms per enumeration: call only when a new or re-titled CabinetWClass window exists.
Keys nothing on the explorer pid (folder windows may live in a separate explorer.exe).
"""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from urllib.parse import unquote, urlparse

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

log = logging.getLogger(__name__)

EXPLORER_CLASSES = frozenset({"CabinetWClass", "ExploreWClass"})

# wanted hwnds (None = all) -> {hwnd: folder path (drive-letter or UNC form, as the user navigated)}
ShellWindowsFn = Callable[[set[int] | None], dict[int, str]]


def path_from_location_url(url: str) -> str:
    r"""``file:///U:/a%20b`` -> ``U:\a b``; ``file://server/share/x`` -> ``\\server\share\x``; "" otherwise."""
    if not url.lower().startswith("file:"):
        return ""
    p = urlparse(url)
    path = unquote(p.path).lstrip("/").replace("/", "\\")
    if p.netloc and p.netloc.lower() != "localhost":
        return "\\\\" + p.netloc + "\\" + path
    return path


def shell_windows(wanted: set[int] | None = None) -> dict[int, str]:
    """Explorer folder windows: hwnd -> path.  COM; call on a CoInitialize'd thread.

    Only ``wanted`` hwnds are read (each read is a cross-process call).  The path comes from
    ``LocationURL`` (cheap) and, when that is not a file URL, from ``Document.Folder.Self.Path``.
    The Shell object is created per call and released before returning (no COM object outlives
    the call, so nothing crosses threads or keeps Explorer references alive)."""
    import win32com.client
    out: dict[int, str] = {}
    shell = win32com.client.Dispatch("Shell.Application")
    try:
        for w in shell.Windows():
            try:
                hwnd = int(w.HWND)
                if wanted is not None and hwnd not in wanted:
                    continue
                url = str(w.LocationURL or "")
                path = path_from_location_url(url)
                if not path:
                    try:
                        path = str(w.Document.Folder.Self.Path)
                    except Exception:  # noqa: BLE001 - special folders (This PC) have no path
                        path = ""
                if not path or path.startswith("::") or "::{" in path:
                    continue                      # IE tabs and shell namespaces (This PC, Recycle Bin)
                out[hwnd] = path
            except Exception:  # noqa: BLE001 - a window closing mid-enumeration
                continue
    finally:
        del shell
    return out


class ExplorerSource:
    name = "shell"

    def __init__(self, shell_windows_fn: ShellWindowsFn | None = None):
        self._shell_windows = shell_windows_fn or shell_windows

    def identify(self, windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
        mine = [w for w in windows if w.window_class in EXPLORER_CLASSES]
        if not mine:
            return {}
        try:
            paths = self._shell_windows({w.hwnd for w in mine})
        except Exception as exc:  # noqa: BLE001
            log.debug("Shell.Application failed: %s", exc)
            return {}
        out: dict[int, M.SnapshotEntry] = {}
        for w in mine:
            path = paths.get(w.hwnd, "")
            if not path:
                continue          # not (yet) in ShellWindows, or a namespace view: stays unidentified
            out[w.hwnd] = M.SnapshotEntry(key="", status="identified", kind="folder", path=path, app="Explorer",
                                          identified_by="shell")
        return out


_default = ExplorerSource()


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    return _default.identify(windows, ctx)


def open_folder(path: str) -> None:
    """``explorer.exe <path>`` (a new window)."""
    subprocess.Popen(["explorer.exe", path], close_fds=True)
