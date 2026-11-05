"""CaptureEngine: the capture thread.  Owner: builder 2.

One ``threading.Thread`` ("po-capture") that calls ``pythoncom.CoInitializeEx(COINIT_APARTMENTTHREADED)``
on entry and ``CoUninitialize`` on exit, and owns every COM object the app uses for
capture and restore.  It runs:

* a pass every ``Settings.capture_interval_s`` while an activity runs and capture is on
  (enumerate -> identify (cached) -> match items -> callback ``on_snapshot(Snapshot)``);
* requests from a ``queue.Queue`` in between passes: ``identify_hwnd``, ``snapshot_now``,
  ``enumerate_all`` (start from what's open), ``restore`` (the Restorer runs here, passes paused).

Callbacks run on the capture thread; the facade wraps them with ``run_on_gui``.
The engine writes the live snapshot through ``core.snapshots.SnapshotStore`` (at most every
``CAPTURE_SNAPSHOT_WRITE_MIN_S`` and only on change) and refreshes the RunningMarker.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from project_opener.core import models as M
from project_opener.core.snapshots import SnapshotStore


@dataclass
class EngineCallbacks:
    on_snapshot: Callable[[M.Snapshot], None] | None = None          # every pass that changed something
    on_identified: Callable[[int, M.SnapshotEntry | None], None] | None = None   # identify_hwnd answers
    on_candidates: Callable[[list[M.SnapshotEntry]], None] | None = None         # enumerate_all answers
    on_restore_progress: Callable[[int, int, str], None] | None = None
    on_restore_done: Callable[[dict[str, Any]], None] | None = None
    on_error: Callable[[str], None] | None = None


@dataclass
class EngineConfig:
    interval_s: float = 3.0
    full_refresh_s: float = 30.0
    want_browser_urls: bool = True
    ignore_rules: list[dict[str, str]] = field(default_factory=list)
    exclude_pids: set[int] = field(default_factory=set)              # this process: the pill, picker, shell


class CaptureEngine:
    def __init__(self, snapshots: SnapshotStore, callbacks: EngineCallbacks, config: EngineConfig | None = None):
        self.snapshots = snapshots
        self.callbacks = callbacks
        self.config = config or EngineConfig()

    # lifecycle (GUI thread)
    def start(self) -> None:
        raise NotImplementedError("CaptureEngine.start")

    def stop(self, timeout: float = 3.0) -> None:
        raise NotImplementedError("CaptureEngine.stop")

    # control (any thread; queued to the capture thread)
    def run_activity(self, activity_id: str, item_paths: list[str]) -> None:
        raise NotImplementedError("CaptureEngine.run_activity")

    def stop_activity(self) -> None:
        raise NotImplementedError("CaptureEngine.stop_activity")

    def set_paused(self, paused: bool) -> None:
        raise NotImplementedError("CaptureEngine.set_paused")

    def update_items(self, item_paths: list[str]) -> None:
        raise NotImplementedError("CaptureEngine.update_items")

    def request_snapshot(self) -> None:
        """A pass now, answered with ``on_snapshot`` (the caller then stores a Checkpoint)."""
        raise NotImplementedError("CaptureEngine.request_snapshot")

    def request_identify(self, hwnd: int) -> None:
        raise NotImplementedError("CaptureEngine.request_identify")

    def request_enumerate_all(self) -> None:
        raise NotImplementedError("CaptureEngine.request_enumerate_all")

    def request_restore(self, snapshot: M.Snapshot, items: list[M.Item]) -> None:
        raise NotImplementedError("CaptureEngine.request_restore")
