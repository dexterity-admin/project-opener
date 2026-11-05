"""Explorer windows through ``Shell.Application.Windows()``.  Owner: builder 2.

250-650 ms per enumeration: call only when a new or re-titled CabinetWClass window exists.
Keys nothing on the explorer pid (folder windows may live in a separate explorer.exe).
"""
from __future__ import annotations

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    raise NotImplementedError("explorer.identify")


def open_folder(path: str) -> None:
    """``explorer.exe <path>`` (a new window)."""
    raise NotImplementedError("explorer.open_folder")
