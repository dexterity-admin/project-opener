"""Snapshot and running-marker persistence (local, per user).

Snapshots change every few seconds while an activity runs, so they do not live
in ``workspace.json`` (whose every save rotates a backup).  Layout under
``data_dir()``::

    snapshots/<activity_id>.json   {"schema": 1, "activity_id", "live": Snapshot | null,
                                    "checkpoints": [Checkpoint, ... newest first, thinned by age],
                                    "ignored": [entry key, ...],     # Ignore in the pill's list, this activity only
                                    "left_out": [entry key, ...]}    # unticked in "Save N new as items"
    running.json                   {"schema": 1, "markers": [RunningMarker, ...]}
    restores.json                  {"schema": 1, "events": [{"at", "activity_id", "source", "reopened"}, ...]}

Checkpoint retention (owner ruling, 19 Nov 2026): every checkpoint is kept ``CHECKPOINT_KEEP_DAYS`` (14),
then the newest of each local day up to ``CHECKPOINT_THIN_DAYS`` (60), then none (``thin_checkpoints``).
The restore log records what each restore and launch actually reopened (windows already open are not
counted); Today's "windows reopened this week" reads it.  Events older than ``RESTORE_LOG_DAYS`` go.

Pure file I/O (atomic writes, tolerant reads), thread-safe.  The data folder is
often a network share (``U:``), where one write can take hundreds of
milliseconds, so the store keeps the files' content in memory: reads never touch
the disk after the first and never wait for a write, and the lock that guards
the in-memory copies is never held across file I/O.  With ``background=True``
(the app) a writer thread does every write, so no caller - the GUI thread
included - waits on the share; ``flush()`` waits for pending writes (shutdown,
tests).  Without it (tests, tools) each write happens in the caller's thread.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)

SNAPSHOT_FILE_SCHEMA = 1
_RUNNING = "\x00running"          # the pending-write key of running.json (never a sanitised activity id)
_RESTORES = "\x00restores"        # ... and of restores.json
RESTORE_SOURCES = ("restore", "launch")


def _when(iso: Any) -> datetime | None:
    return M.parse_iso(str(iso or ""))


def thin_checkpoints(dicts: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Checkpoint dicts newest first, thinned by the retention rule: all within ``CHECKPOINT_KEEP_DAYS``,
    then the newest of each local day within ``CHECKPOINT_THIN_DAYS``, nothing older.  A checkpoint whose
    time cannot be read is kept (it cannot age out, and it is not ours to judge)."""
    now = now or datetime.now(UTC)
    keep_after = now - timedelta(days=C.CHECKPOINT_KEEP_DAYS)
    thin_after = now - timedelta(days=C.CHECKPOINT_THIN_DAYS)
    ordered = sorted(dicts, key=lambda c: _when(c.get("taken_at")) or now, reverse=True)
    out: list[dict[str, Any]] = []
    days_kept: set[str] = set()
    for c in ordered:
        when = _when(c.get("taken_at"))
        if when is None or when >= keep_after:
            out.append(c)
        elif when >= thin_after:
            day = when.astimezone().date().isoformat()
            if day not in days_kept:
                days_kept.add(day)
                out.append(c)
    return out


class SnapshotStore:
    def __init__(self, root: Path | None = None, *, background: bool = False):
        self.root = Path(root) if root else C.data_dir()
        self.dir = self.root / C.SNAPSHOT_DIR
        self.running_path = self.root / C.RUNNING_FILE
        self.restores_path = self.root / C.RESTORE_LOG_FILE
        self.background = background
        # The in-memory copies.  Documents are replaced, never mutated in place, so a reference taken
        # under the lock stays a consistent picture after it is released.
        self._lock = threading.Lock()
        self._docs: dict[str, dict[str, Any]] = {}
        self._running_doc: dict[str, Any] | None = None
        self._restores_doc: dict[str, Any] | None = None
        # Writes: one at a time, always of the newest in-memory content.
        self._io_lock = threading.Lock()
        self._pending: dict[str, str] = {}             # key -> "write" | "delete"
        self._cond = threading.Condition(threading.Lock())
        self._writing = False
        self._writer: threading.Thread | None = None
        self._closed = False

    # ------------------------------------------------------------ plumbing
    def _safe(self, activity_id: str) -> str:
        return "".join(ch for ch in activity_id if ch.isalnum() or ch in "-_") or "unknown"

    def _path(self, activity_id: str) -> Path:
        return self.dir / f"{self._safe(activity_id)}.json"

    def _doc(self, activity_id: str) -> dict[str, Any]:
        safe = self._safe(activity_id)
        with self._lock:
            doc = self._docs.get(safe)
        if doc is not None:
            return doc
        d = read_json(self._path(activity_id), {}) or {}           # first read only, outside the lock
        d = d if isinstance(d, dict) else {}
        with self._lock:
            return self._docs.setdefault(safe, d)

    def _update(self, activity_id: str, change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """Replace the activity's document with ``change(current)`` (cheap, no I/O) and schedule its write."""
        safe = self._safe(activity_id)
        self._doc(activity_id)
        with self._lock:
            cur = self._docs.get(safe) or {}
            new = change(cur)
            new.update({"schema": SNAPSHOT_FILE_SCHEMA, "activity_id": activity_id})
            self._docs[safe] = new
        self._schedule(safe, "write")
        return new

    def _schedule(self, key: str, op: str) -> None:
        if not self.background or self._closed:
            self._run_op(key, op)
            return
        with self._cond:
            self._pending[key] = op
            if self._writer is None or not self._writer.is_alive():
                self._writer = threading.Thread(target=self._write_loop, name="po-snapshot-writer", daemon=True)
                self._writer.start()
            self._cond.notify_all()

    def _write_loop(self) -> None:
        while True:
            with self._cond:
                while not self._pending:
                    if self._closed:
                        return
                    self._cond.wait(5.0)
                    if not self._pending and self._closed:
                        return
                key, op = next(iter(self._pending.items()))
                del self._pending[key]
                self._writing = True
            try:
                self._run_op(key, op)
            except Exception:  # noqa: BLE001 - a failed write must not end the writer
                log.exception("snapshot store: %s of %s failed", op, key)
            finally:
                with self._cond:
                    self._writing = False
                    self._cond.notify_all()

    def _run_op(self, key: str, op: str) -> None:
        """Write the newest in-memory content of ``key`` (or delete its file).  Serialised by ``_io_lock``;
        never holds ``_lock`` while touching the disk."""
        with self._io_lock:
            if key in (_RUNNING, _RESTORES):
                with self._lock:
                    doc = self._running_doc if key == _RUNNING else self._restores_doc
                if doc is not None:
                    write_json_atomic(self.running_path if key == _RUNNING else self.restores_path, doc)
                return
            path = self.dir / f"{key}.json"
            if op == "delete":
                try:
                    path.unlink()
                except OSError:
                    pass
                return
            with self._lock:
                doc = self._docs.get(key)
            if doc is not None:
                self.dir.mkdir(parents=True, exist_ok=True)
                write_json_atomic(path, doc)

    def flush(self, timeout: float = 10.0) -> bool:
        """Wait until every scheduled write is on disk (background mode); True when nothing is left."""
        if not self.background:
            return True
        with self._cond:
            return self._cond.wait_for(lambda: not self._pending and not self._writing, timeout)

    def close(self, timeout: float = 10.0) -> None:
        """Flush, stop the writer; later writes happen in the caller's thread."""
        self.flush(timeout)
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    # ------------------------------------------------------------ snapshots
    def live(self, activity_id: str) -> M.Snapshot | None:
        d = self._doc(activity_id).get("live")
        return M.Snapshot.from_dict(d) if isinstance(d, dict) else None

    def save_live(self, snapshot: M.Snapshot) -> None:
        live = snapshot.to_dict()
        self._update(snapshot.activity_id, lambda cur: {**cur, "live": live})

    def _checkpoint_dicts(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        raw = doc.get("checkpoints", [])
        return [c for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []

    def checkpoints(self, activity_id: str) -> list[M.Checkpoint]:
        """Newest first."""
        cps = [M.Checkpoint.from_dict(c) for c in self._checkpoint_dicts(self._doc(activity_id))]
        cps.sort(key=lambda c: c.taken_at, reverse=True)
        return cps

    def add_checkpoint(self, checkpoint: M.Checkpoint) -> list[M.Checkpoint]:
        """Store a checkpoint (and make its snapshot the live one); the history is thinned by age
        (``thin_checkpoints``)."""
        new = checkpoint.to_dict()
        live = checkpoint.snapshot.to_dict() if checkpoint.snapshot else None

        def change(cur: dict[str, Any]) -> dict[str, Any]:
            rest = [c for c in self._checkpoint_dicts(cur) if c.get("id") != checkpoint.id]
            return {**cur, "live": live, "checkpoints": thin_checkpoints([new] + rest)}
        self._update(checkpoint.activity_id, change)
        return self.checkpoints(checkpoint.activity_id)

    def checkpoint(self, activity_id: str, checkpoint_id: str) -> M.Checkpoint | None:
        return next((c for c in self.checkpoints(activity_id) if c.id == checkpoint_id), None)

    def checkpoints_since(self, activity_ids: Iterable[str], since: datetime) -> list[M.Checkpoint]:
        """Every checkpoint of ``activity_ids`` taken at or after ``since``, newest first."""
        out: list[tuple[datetime, M.Checkpoint]] = []
        for aid in activity_ids:
            for c in self.checkpoints(aid):
                when = _when(c.taken_at)
                if when is not None and when >= since:
                    out.append((when, c))
        out.sort(key=lambda wc: wc[0], reverse=True)
        return [c for _w, c in out]

    def latest_of_kind(self, activity_ids: Iterable[str], kind: str) -> M.Checkpoint | None:
        """The newest checkpoint of ``kind`` across ``activity_ids`` (the latest Park), or None."""
        best: tuple[datetime, M.Checkpoint] | None = None
        for aid in activity_ids:
            for c in self.checkpoints(aid):
                when = _when(c.taken_at)
                if c.kind == kind and when is not None and (best is None or when > best[0]):
                    best = (when, c)
        return best[1] if best else None

    # ------------------------------------------------------------ restore log
    def _restore_log(self) -> dict[str, Any]:
        with self._lock:
            doc = self._restores_doc
        if doc is not None:
            return doc
        d = read_json(self.restores_path, {}) or {}
        d = d if isinstance(d, dict) else {}
        with self._lock:
            if self._restores_doc is None:
                self._restores_doc = d
            return self._restores_doc

    def restore_events(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """Logged restores and launches in the order they happened (at or after ``since`` when given); each
        {"at", "activity_id", "source": restore | launch, "reopened": windows actually opened}."""
        raw = self._restore_log().get("events", [])
        events = [e for e in raw if isinstance(e, dict) and _when(e.get("at")) is not None] \
            if isinstance(raw, list) else []
        if since is not None:
            events = [e for e in events if (_when(e.get("at")) or since) >= since]
        return events

    def log_reopened(self, activity_id: str, source: str, reopened: int, at: str | None = None) -> dict[str, Any]:
        """Record one restore or launch and how many windows it actually reopened (never negative)."""
        event = {"at": at or M.now_iso(), "activity_id": str(activity_id or ""),
                 "source": source if source in RESTORE_SOURCES else "restore",
                 "reopened": max(0, int(reopened or 0))}
        self._restore_log()
        cutoff = datetime.now(UTC) - timedelta(days=C.RESTORE_LOG_DAYS)
        with self._lock:
            raw = (self._restores_doc or {}).get("events", [])
            raw = [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []
            kept = [e for e in raw if (_when(e.get("at")) or cutoff) > cutoff]
            self._restores_doc = {"schema": SNAPSHOT_FILE_SCHEMA, "events": kept + [event]}
        self._schedule(_RESTORES, "write")
        return event

    def reopened_since(self, since: datetime) -> tuple[int, int]:
        """(windows reopened, restores) at or after ``since``: the sum of every logged event's ``reopened``
        (restores and launches) and the number of restore events."""
        events = self.restore_events(since)
        return (sum(int(e.get("reopened", 0) or 0) for e in events),
                sum(1 for e in events if e.get("source") == "restore"))

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
        safe = self._safe(activity_id)
        with self._lock:
            self._docs[safe] = {}
        self._schedule(safe, "delete")

    # ------------------------------------------------- the activity's review state
    def review(self, activity_id: str) -> tuple[set[str], set[str]]:
        """(ignored, left out): entry keys the user ignored in the pill's list for this activity, and those
        left unticked when saving new things as items.  Neither is offered as new again."""
        doc = self._doc(activity_id)

        def keys(name: str) -> set[str]:
            v = doc.get(name)
            return {str(k) for k in v if isinstance(k, str) and k} if isinstance(v, list) else set()
        return keys("ignored"), keys("left_out")

    def set_review(self, activity_id: str, ignored: set[str] | None = None, left_out: set[str] | None = None) -> None:
        def change(cur: dict[str, Any]) -> dict[str, Any]:
            out = dict(cur)
            if ignored is not None:
                out["ignored"] = sorted(ignored)
            if left_out is not None:
                out["left_out"] = sorted(left_out)
            return out
        self._update(activity_id, change)

    # ------------------------------------------------------- running markers
    def _markers_doc(self) -> dict[str, Any]:
        with self._lock:
            doc = self._running_doc
        if doc is not None:
            return doc
        d = read_json(self.running_path, {}) or {}
        d = d if isinstance(d, dict) else {}
        with self._lock:
            if self._running_doc is None:
                self._running_doc = d
            return self._running_doc

    def markers(self) -> list[M.RunningMarker]:
        raw = self._markers_doc().get("markers", [])
        raw = raw if isinstance(raw, list) else []
        return [M.RunningMarker.from_dict(m) for m in raw if isinstance(m, dict) and m.get("activity_id")]

    def _change_markers(self, change: Callable[[list[M.RunningMarker]], list[M.RunningMarker]]) -> None:
        self._markers_doc()
        with self._lock:
            raw = (self._running_doc or {}).get("markers", [])
            raw = raw if isinstance(raw, list) else []
            ms = change([M.RunningMarker.from_dict(m) for m in raw if isinstance(m, dict) and m.get("activity_id")])
            self._running_doc = {"schema": SNAPSHOT_FILE_SCHEMA, "markers": [m.to_dict() for m in ms]}
        self._schedule(_RUNNING, "write")

    def mark_running(self, marker: M.RunningMarker) -> None:
        self._change_markers(lambda ms: [m for m in ms if m.activity_id != marker.activity_id] + [marker])

    def touch_running(self, activity_id: str) -> None:
        def change(ms: list[M.RunningMarker]) -> list[M.RunningMarker]:
            for m in ms:
                if m.activity_id == activity_id:
                    m.last_seen = M.now_iso()
            return ms
        self._change_markers(change)

    def clear_running(self, activity_id: str) -> None:
        """The activity ended cleanly."""
        self._change_markers(lambda ms: [m for m in ms if m.activity_id != activity_id])

    def stale_markers(self, alive: Callable[[M.RunningMarker], bool] | None = None) -> list[M.RunningMarker]:
        """Markers left by a process that is gone (unclean shutdown).  ``alive(marker)`` decides; the
        default treats every marker whose pid is not this process as stale, which is right at start-up."""
        if alive is None:
            def alive(m: M.RunningMarker) -> bool:
                return m.pid == os.getpid()
        return [m for m in self.markers() if not alive(m)]
