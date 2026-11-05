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

Cadence (spike section 5, architecture section 5): a full re-identification every
``full_refresh_s`` and whenever the monitor layout changes; incremental passes in between
identify only windows whose (hwnd, title, class, pid) is new.  Adaptive: when a pass took
longer than a third of the interval, the next one is skipped (slow PCs, many windows).
"""
from __future__ import annotations

import copy
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from project_opener import constants as C
from project_opener.capture import diff
from project_opener.core import models as M
from project_opener.core.snapshots import SnapshotStore

log = logging.getLogger(__name__)


@dataclass
class EngineCallbacks:
    on_snapshot: Callable[[M.Snapshot], None] | None = None          # every pass that changed something
    on_identified: Callable[[int, M.SnapshotEntry | None, str], None] | None = None  # identify answers (+ purpose)
    on_candidates: Callable[[list[M.SnapshotEntry]], None] | None = None         # enumerate_all answers
    on_restore_progress: Callable[[int, int, str], None] | None = None
    on_restore_done: Callable[[dict[str, Any]], None] | None = None
    on_checkpoint: Callable[[M.Checkpoint], None] | None = None      # snapshot_now answered (already stored)
    on_error: Callable[[str], None] | None = None


@dataclass
class EngineConfig:
    interval_s: float = float(C.CAPTURE_INTERVAL_S)
    full_refresh_s: float = float(C.CAPTURE_FULL_REFRESH_S)
    write_min_s: float = float(C.CAPTURE_SNAPSHOT_WRITE_MIN_S)
    heartbeat_s: float = float(C.RUNNING_HEARTBEAT_S)
    settle_s: float = float(C.RESTORE_SETTLE_S)
    want_browser_urls: bool = True
    office_via_com: bool = True
    ignore_rules: list[dict[str, str]] = field(default_factory=list)
    exclude_pids: set[int] = field(default_factory=set)              # this process: the pill, picker, shell
    resolve: Callable[[str], str] | None = None      # item path -> real path (variables); thread-safe
    portable: Callable[[str], str] | None = None     # drive letter -> UNC; thread-safe
    open_item: Callable[[M.Item], object] | None = None   # the launcher's open_item (restore of non-Office files)


class CaptureEngine:
    def __init__(self, snapshots: SnapshotStore, callbacks: EngineCallbacks, config: EngineConfig | None = None, *,
                 enumerate_fn: Callable[[set[int]], list] | None = None,
                 monitors_fn: Callable[[], list[M.Monitor]] | None = None,
                 identifier_factory: Callable[[EngineConfig], Any] | None = None,
                 platform_factory: Callable[[Any, EngineConfig], Any] | None = None,
                 com: bool = True, clock: Callable[[], float] = time.monotonic):
        self.snapshots = snapshots
        self.callbacks = callbacks
        self.config = config or EngineConfig()
        self._enumerate = enumerate_fn
        self._monitors = monitors_fn
        self._identifier_factory = identifier_factory
        self._platform_factory = platform_factory
        self._com = com
        self._clock = clock
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._hover_lock = threading.Lock()
        self._hover_hwnd = 0
        self._hover_queued = False
        self.stats: deque[dict[str, Any]] = deque(maxlen=500)   # per pass: ms, full, windows, queried, skipped_next
        # capture-thread state
        self.identifier: Any = None
        self._activity_id = ""
        self._items: list[M.Item] = []
        self._item_paths: list[str] = []
        self._paused = False
        self._next_due = 0.0
        self._last_full = float("-inf")
        self._monitor_sig: tuple = ()
        self._last_emitted: M.Snapshot | None = None
        self._last_written: M.Snapshot | None = None
        self._last_write = float("-inf")
        self._last_touch = float("-inf")
        self._first_seen: dict[str, str] = {}
        self._session_start = ""          # this run's first pass (Snapshot.session_start)

    # ------------------------------------------------------------ lifecycle (GUI thread)
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="po-capture", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        if self._thread is None:
            return
        self._q.put(("stop",))
        self._thread.join(timeout)
        self._thread = None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------ control (any thread)
    def run_activity(self, activity_id: str, items: list[M.Item]) -> None:
        self._q.put(("run", activity_id, list(items)))

    def stop_activity(self) -> None:
        self._q.put(("end",))

    def set_paused(self, paused: bool) -> None:
        self._q.put(("pause", bool(paused)))

    def update_items(self, items: list[M.Item]) -> None:
        self._q.put(("items", list(items)))

    def set_ignore_rules(self, rules: list[dict[str, str]]) -> None:
        self._q.put(("ignore", [dict(r) for r in rules if isinstance(r, dict)]))

    def set_options(self, interval_s: float | None = None, want_browser_urls: bool | None = None,
                    office_via_com: bool | None = None) -> None:
        self._q.put(("options", interval_s, want_browser_urls, office_via_com))

    def request_snapshot(self, kind: str = "manual", label: str = "") -> None:
        """A full pass now, stored as a Checkpoint and answered with ``on_checkpoint``."""
        self._q.put(("snapshot", kind, label))

    def request_identify(self, hwnd: int, purpose: str = "add") -> None:
        """``purpose`` "add" is always answered; "hover" requests coalesce (only the latest is answered)."""
        if purpose == "hover":
            with self._hover_lock:
                self._hover_hwnd = hwnd
                if self._hover_queued:
                    return
                self._hover_queued = True
            self._q.put(("hover",))
            return
        self._q.put(("identify", hwnd, purpose))

    def request_enumerate_all(self) -> None:
        self._q.put(("enumerate",))

    def request_restore(self, snapshot: M.Snapshot, items: list[M.Item]) -> None:
        self._q.put(("restore", copy.deepcopy(snapshot), list(items)))

    # ------------------------------------------------------------ the thread
    def _emit(self, name: str, *args: Any) -> None:
        cb = getattr(self.callbacks, name, None)
        if cb is None:
            return
        try:
            cb(*args)
        except Exception:  # noqa: BLE001 - a GUI-side failure never stops capture
            log.exception("capture callback %s failed", name)

    def _make_identifier(self) -> Any:
        if self._identifier_factory is not None:
            return self._identifier_factory(self.config)
        from project_opener.capture.identify import Identifier
        return Identifier(want_browser_urls=self.config.want_browser_urls, ignore_rules=self.config.ignore_rules,
                          canon=self.config.portable)

    def _loop(self) -> None:
        pythoncom = None
        if self._com:
            import pythoncom  # noqa: F811
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        try:
            self.identifier = self._make_identifier()
            while True:
                running = bool(self._activity_id) and not self._paused
                timeout = max(0.0, self._next_due - self._clock()) if running else None
                try:
                    req = self._q.get(timeout=timeout)
                except queue.Empty:
                    req = None
                if req is not None:
                    if req[0] == "stop":
                        break
                    try:
                        self._handle(req)
                    except Exception as exc:  # noqa: BLE001
                        log.exception("capture request %s failed", req[0])
                        self._emit("on_error", f"{req[0]}: {exc}")
                    continue
                try:
                    self._scheduled_pass()
                except Exception as exc:  # noqa: BLE001
                    log.exception("capture pass failed")
                    self._emit("on_error", f"pass: {exc}")
                    self._next_due = self._clock() + self.config.interval_s
        finally:
            try:
                self._flush_live()
            except Exception:  # noqa: BLE001
                log.exception("final live snapshot write failed")
            self.identifier = None
            if pythoncom is not None:
                pythoncom.CoUninitialize()

    def _resolved_paths(self, items: list[M.Item]) -> list[str]:
        out = []
        for it in items:
            if it.kind not in ("file", "folder"):
                continue
            p = it.path
            if self.config.resolve is not None:
                try:
                    p = self.config.resolve(p) or p
                except Exception:  # noqa: BLE001
                    pass
            out.append(p)
        return out

    def _handle(self, req: tuple) -> None:
        name = req[0]
        if name == "run":
            self._flush_live()
            self._activity_id, self._items = req[1], req[2]
            self._item_paths = self._resolved_paths(self._items)
            self._paused = False
            self._last_emitted = self._last_written = None
            self._last_write = float("-inf")
            self._last_touch = self._clock()          # the facade has just written the marker
            self._last_full = float("-inf")
            self._first_seen = {}
            self._session_start = ""
            self._next_due = 0.0
            if self.identifier is not None:
                self.identifier.items_changed()
        elif name == "end":
            self._flush_live()
            self._activity_id, self._items, self._item_paths = "", [], []
            self._last_emitted = self._last_written = None
        elif name == "pause":
            self._paused = req[1]
            if not self._paused:
                self._next_due = 0.0
        elif name == "items":
            self._items = req[1]
            self._item_paths = self._resolved_paths(self._items)
            if self.identifier is not None:
                self.identifier.items_changed()
            self._next_due = 0.0
        elif name == "ignore":
            self.config.ignore_rules = req[1]
            if self.identifier is not None:
                self.identifier.ignore_rules = list(req[1])
            self._next_due = 0.0
        elif name == "options":
            interval, browser, office = req[1], req[2], req[3]
            if interval:
                self.config.interval_s = max(1.0, float(interval))
            if browser is not None:
                self.config.want_browser_urls = bool(browser)
                if self.identifier is not None:
                    self.identifier.want_browser_urls = bool(browser)
                    self.identifier.cache.clear()
            if office is not None:
                self.config.office_via_com = bool(office)
        elif name == "snapshot":
            self._snapshot_now(req[1], req[2])
        elif name == "hover":
            with self._hover_lock:
                hwnd, self._hover_queued = self._hover_hwnd, False
            self._emit("on_identified", hwnd, self._identify_one(hwnd), "hover")
        elif name == "identify":
            self._emit("on_identified", req[1], self._identify_one(req[1]), req[2])
        elif name == "enumerate":
            self._emit("on_candidates", self._enumerate_all())
        elif name == "restore":
            if self._activity_id and not self._session_start and not self._paused:
                # see what is open before reopening anything, so restored windows count as opened during
                # the activity (the Save-new sheet ticks those) and windows already open do not
                self._after_pass(self._build()[0])
            self._restore(req[1], req[2])

    # ------------------------------------------------------------ passes
    def _windows(self) -> list:
        if self._enumerate is not None:
            return self._enumerate(set(self.config.exclude_pids))
        from project_opener.capture import win32
        return win32.enumerate_windows(set(self.config.exclude_pids))

    def _monitor_list(self) -> list[M.Monitor]:
        if self._monitors is not None:
            return self._monitors()
        from project_opener.capture import win32
        return win32.monitors()

    def _build(self, force_full: bool = False) -> tuple[M.Snapshot, float]:
        t0 = time.perf_counter()
        now = self._clock()
        mons = self._monitor_list()
        sig = tuple((m.device, tuple(m.rect)) for m in mons)
        full = force_full or (now - self._last_full >= self.config.full_refresh_s) or sig != self._monitor_sig
        if full:
            self._last_full = now
        self._monitor_sig = sig
        wins = self._windows()
        entries = self.identifier.identify(wins, self._item_paths, full=full)
        snap = M.Snapshot(activity_id=self._activity_id, full=full, monitors=mons, entries=entries)
        diff.match_items(snap, self._items, portable=self.config.portable, resolve=self.config.resolve)
        first_pass = not self._session_start
        if first_pass:
            self._session_start = M.now_iso()
        seen: dict[str, str] = {}
        for e in snap.entries:
            prior = self._first_seen.get(e.key) or seen.get(e.key)
            # what the first pass finds was open when the activity started: stamped with the start itself
            # (a cached identification may carry an older stamp, so a later newcomer is stamped now)
            e.first_seen = prior or (self._session_start if first_pass else M.now_iso())
            seen.setdefault(e.key, e.first_seen)
        self._first_seen = seen
        snap.session_start = self._session_start
        ms = (time.perf_counter() - t0) * 1000.0
        self.stats.append({"ms": round(ms, 2), "full": full, "windows": len(wins),
                           "queried": getattr(self.identifier, "last_queried", 0), "at": time.time()})
        return snap, ms

    def _scheduled_pass(self) -> None:
        snap, ms = self._build()
        interval = self.config.interval_s
        skip = ms / 1000.0 > interval / 3.0
        self.stats[-1]["skipped_next"] = skip
        self._next_due = self._clock() + interval * (2 if skip else 1)
        self._after_pass(snap)

    def _after_pass(self, snap: M.Snapshot) -> None:
        now = self._clock()
        if diff.changed(self._last_emitted, snap):
            self._last_emitted = snap
            self._emit("on_snapshot", snap)
        self._maybe_write(now)
        if self._activity_id and now - self._last_touch >= self.config.heartbeat_s:
            self._last_touch = now
            try:
                self.snapshots.touch_running(self._activity_id)
            except OSError:
                log.warning("running marker refresh failed")

    def _maybe_write(self, now: float) -> None:
        snap = self._last_emitted
        if snap is None or snap is self._last_written or not snap.activity_id:
            return
        if now - self._last_write < self.config.write_min_s:
            return
        self.snapshots.save_live(snap)
        self._last_written, self._last_write = snap, now

    def _flush_live(self) -> None:
        snap = self._last_emitted
        if snap is not None and snap is not self._last_written and snap.activity_id:
            self.snapshots.save_live(snap)
            self._last_written, self._last_write = snap, self._clock()

    def _snapshot_now(self, kind: str, label: str) -> None:
        if not self._activity_id:
            self._emit("on_error", "no activity is running")
            return
        snap, _ms = self._build(force_full=True)
        self._next_due = self._clock() + self.config.interval_s
        if diff.changed(self._last_emitted, snap):
            self._last_emitted = snap
            self._emit("on_snapshot", snap)
        cp = M.Checkpoint(activity_id=self._activity_id, snapshot=copy.deepcopy(snap), kind=kind, label=label,
                          taken_at=snap.taken_at)
        self.snapshots.add_checkpoint(cp)
        self._last_written, self._last_write = snap, self._clock()
        self._emit("on_checkpoint", cp)

    # ------------------------------------------------------------ requests
    def _identify_one(self, hwnd: int) -> M.SnapshotEntry | None:
        entry = self.identifier.identify_one(hwnd, self._item_paths)
        if entry is not None and self._items:
            diff.match_items(M.Snapshot(activity_id=self._activity_id, entries=[entry]), self._items,
                             portable=self.config.portable, resolve=self.config.resolve)
        return entry

    def _enumerate_all(self) -> list[M.SnapshotEntry]:
        wins = self._windows()
        entries = self.identifier.identify(wins, self._item_paths, full=False, apply_ignore=False)
        for w, e in zip(wins, entries, strict=False):
            if self.identifier.ignored(w):
                e.note = (e.note + "; " if e.note else "") + "ignored by capture"
        return entries

    def _restore(self, snapshot: M.Snapshot, items: list[M.Item]) -> None:
        from project_opener.capture.restore import Restorer, Win32Platform
        if self._platform_factory is not None:
            platform = self._platform_factory(self.identifier, self.config)
        else:
            platform = Win32Platform(self.identifier, set(self.config.exclude_pids))
        open_item = self.config.open_item or (lambda item: None)
        restorer = Restorer(open_item, self.config.settle_s, platform=platform,
                            office_via_com=self.config.office_via_com, portable=self.config.portable,
                            resolve=self.config.resolve)
        report = restorer.restore(snapshot, items,
                                  progress=lambda d, t, lbl: self._emit("on_restore_progress", d, t, lbl))
        self._last_full = float("-inf")
        self._next_due = 0.0
        self._emit("on_restore_done", report.to_dict())
