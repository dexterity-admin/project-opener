"""Snapshot and running-marker persistence (local, per user).

Snapshots change every few seconds while an activity runs, so they do not live
in ``workspace.json`` (whose every save rotates a backup).  Layout under
``data_dir()``::

    snapshots/<activity_id>.json   {"schema": 1, "activity_id", "live": Snapshot | null,
                                    "checkpoints": [Checkpoint, ... newest first, at most 10]}
    running.json                   {"schema": 1, "markers": [RunningMarker, ...]}

Pure file I/O (atomic writes, tolerant reads); thread-safe so the capture
thread can write the live snapshot while the GUI thread reads checkpoints.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.jsonio import read_json, write_json_atomic

SNAPSHOT_FILE_SCHEMA = 1


class SnapshotStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else C.data_dir()
        self.dir = self.root / C.SNAPSHOT_DIR
        self.running_path = self.root / C.RUNNING_FILE
        self._lock = threading.RLock()

    # ------------------------------------------------------------ snapshots
    def _path(self, activity_id: str) -> Path:
        safe = "".join(ch for ch in activity_id if ch.isalnum() or ch in "-_") or "unknown"
        return self.dir / f"{safe}.json"

    def _read(self, activity_id: str) -> dict:
        d = read_json(self._path(activity_id), {}) or {}
        return d if isinstance(d, dict) else {}

    def _write(self, activity_id: str, live: M.Snapshot | None, checkpoints: list[M.Checkpoint]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path(activity_id), {
            "schema": SNAPSHOT_FILE_SCHEMA, "activity_id": activity_id,
            "live": live.to_dict() if live else None,
            "checkpoints": [c.to_dict() for c in checkpoints[:C.CHECKPOINTS_KEPT]],
        })

    def live(self, activity_id: str) -> M.Snapshot | None:
        with self._lock:
            d = self._read(activity_id).get("live")
        return M.Snapshot.from_dict(d) if isinstance(d, dict) else None

    def save_live(self, snapshot: M.Snapshot) -> None:
        with self._lock:
            self._write(snapshot.activity_id, snapshot, self.checkpoints(snapshot.activity_id))

    def checkpoints(self, activity_id: str) -> list[M.Checkpoint]:
        """Newest first."""
        with self._lock:
            raw = self._read(activity_id).get("checkpoints", [])
        cps = [M.Checkpoint.from_dict(c) for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []
        cps.sort(key=lambda c: c.taken_at, reverse=True)
        return cps

    def add_checkpoint(self, checkpoint: M.Checkpoint) -> list[M.Checkpoint]:
        """Store a checkpoint (and make its snapshot the live one); keeps the newest ``CHECKPOINTS_KEPT``."""
        with self._lock:
            cps = [checkpoint] + [c for c in self.checkpoints(checkpoint.activity_id) if c.id != checkpoint.id]
            cps = cps[:C.CHECKPOINTS_KEPT]
            self._write(checkpoint.activity_id, checkpoint.snapshot, cps)
            return cps

    def checkpoint(self, activity_id: str, checkpoint_id: str) -> M.Checkpoint | None:
        return next((c for c in self.checkpoints(activity_id) if c.id == checkpoint_id), None)

    def latest(self, activity_id: str) -> M.Snapshot | None:
        """What to resume: the live snapshot when it holds anything, else the newest checkpoint that does.

        A live snapshot with no entries means the windows were closed before the app stopped (by hand, or by
        Windows closing applications one by one); "nothing open" is not a state to restore, so the last
        moment that held something wins.  With nothing anywhere, the empty live snapshot (or None) comes back."""
        live = self.live(activity_id)
        if live is not None and live.entries:
            return live
        cps = self.checkpoints(activity_id)
        for cp in cps:
            if cp.snapshot is not None and cp.snapshot.entries:
                return cp.snapshot
        return live if live is not None else (cps[0].snapshot if cps else None)

    def forget(self, activity_id: str) -> None:
        with self._lock:
            try:
                self._path(activity_id).unlink()
            except OSError:
                pass

    # ------------------------------------------------------- running markers
    def markers(self) -> list[M.RunningMarker]:
        with self._lock:
            d = read_json(self.running_path, {}) or {}
        raw = d.get("markers", []) if isinstance(d, dict) else []
        return [M.RunningMarker.from_dict(m) for m in raw if isinstance(m, dict) and m.get("activity_id")]

    def _write_markers(self, markers: list[M.RunningMarker]) -> None:
        write_json_atomic(self.running_path, {"schema": SNAPSHOT_FILE_SCHEMA,
                                              "markers": [m.to_dict() for m in markers]})

    def mark_running(self, marker: M.RunningMarker) -> None:
        with self._lock:
            ms = [m for m in self.markers() if m.activity_id != marker.activity_id] + [marker]
            self._write_markers(ms)

    def touch_running(self, activity_id: str) -> None:
        with self._lock:
            ms = self.markers()
            for m in ms:
                if m.activity_id == activity_id:
                    m.last_seen = M.now_iso()
            self._write_markers(ms)

    def clear_running(self, activity_id: str) -> None:
        """The activity ended cleanly."""
        with self._lock:
            self._write_markers([m for m in self.markers() if m.activity_id != activity_id])

    def stale_markers(self, alive: Callable[[M.RunningMarker], bool] | None = None) -> list[M.RunningMarker]:
        """Markers left by a process that is gone (unclean shutdown).  ``alive(marker)`` decides; the
        default treats every marker whose pid is not this process as stale, which is right at start-up."""
        if alive is None:
            def alive(m: M.RunningMarker) -> bool:
                return m.pid == os.getpid()
        return [m for m in self.markers() if not alive(m)]
