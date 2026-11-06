"""``app.capture``: the running activity, the live snapshot, checkpoints, add-a-window, start-from-open,
restore.  Owner: builder 2 (CAPTURE).

The pill, the tray, the activity page and the Resume band all read this one
object.  All COM work happens on the capture thread (``capture.engine``);
results arrive here through ``app.run_on_gui``.

Live-list ``status`` values (worst first): ``ambiguous`` (several files with that
name), ``unidentified`` (needs a path: a document app showing a file it could not
find a path for), ``offline`` (identified, its server is down), ``unsaved`` (no file
yet), ``window`` (not a file: an application window with no document), ``identified``.
``monitor`` is "monitor N" (N = 1-based index in ``QGuiApplication.screens()``) and
``placeX/Y/W/H`` the window's rectangle as fractions of that monitor.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from project_opener.capture import diff
from project_opener.capture import windows as W
from project_opener.capture.engine import CaptureEngine, EngineCallbacks, EngineConfig
from project_opener.core import models as M
from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

log = logging.getLogger(__name__)

ENTRY_ROLES = (
    "entryKey", "status", "kind", "name", "path", "title", "process", "appName", "identifiedBy", "monitor",
    "isItem", "isNew", "toSave", "note", "candidates",
    "placeX", "placeY", "placeW", "placeH",      # the window on its monitor, 0..1 (builder 4's Monitors panel)
)
CHECKPOINT_ROLES = ("checkpointId", "takenAt", "takenText", "kind", "label", "count", "identified", "isLatest")
CANDIDATE_ROLES = ("entryKey", "ticked", "name", "path", "appName", "status", "note", "kind")
# "Save N new as items" and the Resume sheet: tick lists grouped under headings (``group`` / ``groupLabel``);
# ``action`` says what ticking adds; ``tickable`` is False for a row that cannot be added or reopened.
NEW_ROLES = ("entryKey", "ticked", "tickable", "name", "path", "appName", "status", "note", "kind", "group",
             "groupLabel", "action")
RESUME_ROLES = ("entryKey", "ticked", "tickable", "name", "path", "appName", "status", "note", "kind", "group",
                "groupLabel", "monitor")

# state: idle (no activity running) | running | needs (a path is needed or a drive is down) | paused | saved
STATES = ("idle", "running", "needs", "paused", "saved")
SAVED_MS = 2000


def time_text(iso: str | None) -> str:
    """"14:32" today, "4 Nov 14:32" another day; "" for nothing."""
    dt = M.parse_iso(iso)
    if dt is None:
        return ""
    local = dt.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%H:%M")
    return f"{local.day} {local.strftime('%b %H:%M')}"


def screen_names() -> list[Any]:
    r"""``QGuiApplication.screens()`` in order, as (name, native left, native top, device pixel ratio).

    Qt 6 names a Windows screen by its model ("DELL E2222H"), not by its device ("\\.\DISPLAY1"), and its
    order need not follow the device numbers, so a recorded monitor is matched by its top-left corner."""
    try:
        from PySide6.QtGui import QGuiApplication
        out = []
        for sc in QGuiApplication.screens():
            g = sc.geometry()
            out.append((sc.name(), g.x(), g.y(), float(sc.devicePixelRatio() or 1.0)))
        return out
    except Exception:  # noqa: BLE001 - no GUI application (tests, tools)
        return []


def _screen_index(device: str, rect: tuple, screens: list[Any]) -> int:
    """0-based index of the screen showing ``device`` (by name, else by the monitor rectangle's top-left
    corner, native or scaled); -1 when none matches."""
    for i, sc in enumerate(screens):
        name = sc if isinstance(sc, str) else sc[0]
        if name.lower() == device.lower():
            return i
    for i, sc in enumerate(screens):
        if isinstance(sc, str) or not rect:
            continue
        _n, x, y, dpr = sc
        if (x, y) == (rect[0], rect[1]) or (round(x * dpr), round(y * dpr)) == (rect[0], rect[1]):
            return i
    return -1


def monitor_and_place(pl: M.WindowPlacement | None, screens: list[Any]) -> tuple[str, dict[str, float]]:
    """("monitor N", {placeX, placeY, placeW, placeH} as 0..1 of that monitor) for the live list.
    N is the 1-based index in ``screens``; the device's short name ("DISPLAY2") when it is not there."""
    if pl is None:
        return "", {}
    idx = _screen_index(pl.monitor, tuple(pl.monitor_rect or ()), screens)
    mon = f"monitor {idx + 1}" if idx >= 0 else pl.monitor.rsplit("\\", 1)[-1]
    mr = pl.monitor_rect
    mw, mh = mr[2] - mr[0], mr[3] - mr[1]
    if mw <= 0 or mh <= 0:
        return mon, {}
    r = pl.window_rect if pl.show_cmd == 3 and pl.window_rect[2] > pl.window_rect[0] else pl.normal_rect

    def clamp(v: float) -> float:
        return round(min(1.0, max(0.0, v)), 4)
    return mon, {"placeX": clamp((r[0] - mr[0]) / mw), "placeY": clamp((r[1] - mr[1]) / mh),
                 "placeW": clamp((r[2] - r[0]) / mw), "placeH": clamp((r[3] - r[1]) / mh)}


class CaptureApi(ApiBase):
    stateChanged = Signal()
    liveChanged = Signal()
    checkpointsChanged = Signal()
    checkpointSaved = Signal(str, int, str)          # checkpoint id, things, "14:32"
    addResult = Signal(bool, str, bool, str)         # ok, message, needs a path, entry key
    hoverIdentified = Signal(int, bool, str)         # hwnd, identifiable, label (the picker's frame + label)
    restoreProgress = Signal(int, int, str)          # done, total, current label
    restoreFinished = Signal("QVariantMap")          # {opened, placed, failed: [...], unrestorable: [...]}
    startCandidatesReady = Signal()
    newCandidatesChanged = Signal()
    resumeCandidatesChanged = Signal()
    saveNewRequested = Signal()                      # open the "Save N new as items" sheet (main window)

    def __init__(self, app: Any):
        super().__init__(app)
        self._live = DictListModel(ENTRY_ROLES, key="entryKey", parent=self)
        self._checkpoints = DictListModel(CHECKPOINT_ROLES, key="checkpointId", parent=self)
        self._candidates = DictListModel(CANDIDATE_ROLES, key="entryKey", parent=self)
        self._new_rows = DictListModel(NEW_ROLES, key="entryKey", parent=self)
        self._resume_rows = DictListModel(RESUME_ROLES, key="entryKey", parent=self)
        self._running_id = ""
        self._running_name = ""
        self._running_label = ""
        self._running_color = ""
        self._state = "idle"
        self._open = 0
        self._identified = 0
        self._needs_path = 0
        self._new = 0
        self._new_to_save = 0
        self._last_checkpoint_text = ""
        self._since_checkpoint = 0
        self._drive_down = False
        # private
        self._engine: CaptureEngine | None = None
        self._snapshot: M.Snapshot | None = None
        self._known: dict[str, M.SnapshotEntry] = {}          # entry key -> entry (live, picker, candidates)
        self._candidate_entries: dict[str, M.SnapshotEntry] = {}
        self._selected_id = ""
        self._user_paused = False
        self._saved_until = False
        self._restoring = False
        self._exclude_pids = {os.getpid()}
        self._watch_hooked = False
        self._before_start: tuple[str, M.Snapshot | None] = ("", None)
        # the running activity's review state (SnapshotStore.review): ignored in the pill's list; left
        # unticked in "Save N new as items".  Neither is offered as new again.
        self._ignored: set[str] = set()
        self._left_out: set[str] = set()
        self._new_entries: dict[str, M.SnapshotEntry] = {}
        self._process_started: float | None = None       # psutil's create time, read once (warm-up)
        self._resume_prep: tuple[str, M.Snapshot | None] = ("", None)

    # ------------------------------------------------------------- models
    @Property(QObject, constant=True)
    def live(self) -> DictListModel:
        """The running activity's live snapshot, worst first (needs a path, offline, identified)."""
        return self._live

    @Property(QObject, constant=True)
    def checkpoints(self) -> DictListModel:
        """The running (or selected) activity's checkpoints, newest first, at most 10."""
        return self._checkpoints

    @Property(QObject, constant=True)
    def startCandidates(self) -> DictListModel:
        """Start from what's open: every window, non-file ones unticked."""
        return self._candidates

    @Property(QObject, constant=True)
    def newCandidates(self) -> DictListModel:  # noqa: N802
        """"Save N new as items": the new things, most likely first; files, folders and pages opened since
        the activity started ticked, everything else unticked."""
        return self._new_rows

    @Property(QObject, constant=True)
    def resumeCandidates(self) -> DictListModel:  # noqa: N802
        """The Resume sheet: what was open at the last snapshot; the activity's items and what was opened
        during the activity ticked, everything else unticked."""
        return self._resume_rows

    # --------------------------------------------------------- properties
    runningId = ro(str, "_running_id", stateChanged)
    runningName = ro(str, "_running_name", stateChanged)
    runningLabel = ro(str, "_running_label", stateChanged)      # the pill's short name
    runningColor = ro(str, "_running_color", stateChanged)
    state = ro(str, "_state", stateChanged)
    openCount = ro(int, "_open", liveChanged)
    identifiedCount = ro(int, "_identified", liveChanged)
    needsPathCount = ro(int, "_needs_path", liveChanged)
    newCount = ro(int, "_new", liveChanged)                     # open, not items yet (the sheet's rows)
    newToSave = ro(int, "_new_to_save", liveChanged)            # of those, ticked when the sheet opens
    lastCheckpointText = ro(str, "_last_checkpoint_text", checkpointsChanged)
    sinceCheckpoint = ro(int, "_since_checkpoint", liveChanged)  # "2 new since"

    @Property("QVariantMap", constant=True)
    def statusMeta(self) -> dict[str, Any]:  # noqa: N802
        """Entry status -> {level, word}: the one table every list of open things reads (the live list, the
        tick lists, the pill's panel; juror T2-1).  "Needs a path" is a document with no path found;
        an unsaved document and a plain window are "Not a file"."""
        from project_opener.ui import text as T
        return {k: {"level": lvl, "word": word} for k, (lvl, word) in T.ENTRY_META.items()}
    driveDown = ro(bool, "_drive_down", stateChanged)            # a root the activity uses is offline (red ring)

    @Property(str, notify=stateChanged)
    def captureState(self) -> str:  # noqa: N802
        """The one capture-state word (ui.text.CAPTURE_STATES): watching | paused | off | idle."""
        if not self._running_id:
            return "idle"
        if not self._capture_on():
            return "off"
        return "paused" if self._user_paused else "watching"

    @Property(str, notify=liveChanged)
    def captureLine(self) -> str:  # noqa: N802
        """"Capture on · watching · 12 things open · 9 identified" / "Capture off · last snapshot 14:32" ...
        for the running activity (the card, the page header, the live list and the pill say the same)."""
        from project_opener.ui import text as T
        state = self.captureState
        last = ""
        if state != "watching" and self._running_id:
            cps = self.app.snapshots.checkpoints(self._running_id)
            snap = self._snapshot or (cps[0].snapshot if cps else None)
            last = snap.taken_at if snap is not None else ""
        return T.capture_line(state, last, self._open, self._identified)

    @Property(bool, notify=stateChanged)
    def liveStale(self) -> bool:  # noqa: N802
        """The live list shows the last snapshot, not what is open now (capture off or paused)."""
        return bool(self._running_id) and self.captureState in ("off", "paused")

    @Property(bool, notify=stateChanged)
    def globalEnabled(self) -> bool:
        return bool(self.app.ctx.settings.capture_enabled)

    # ------------------------------------------------------------- helpers
    @property
    def engine(self) -> CaptureEngine | None:
        return self._engine

    @property
    def snapshot(self) -> M.Snapshot | None:
        """The latest live snapshot (GUI thread)."""
        return self._snapshot

    def _settings(self) -> Any:
        return self.app.ctx.settings

    def _store(self) -> Any:
        return self.app.ctx.store

    def _gui(self, fn: Any) -> Any:
        """Wrap a capture-thread callback so it runs on the GUI thread."""
        def call(*args: Any) -> None:
            self.app.run_on_gui(lambda: fn(*args))
        return call

    def _resolve(self, path: str) -> str:
        return self.app.ctx.resolver.resolve(path).resolved

    def _portable(self, path: str) -> str:
        return self.app.ctx.resolver.portable(path)

    def _open_item(self, item: M.Item) -> object:
        return self.app.ctx.launcher.open_item(item)

    def _toast(self, title: str, body: str = "", level: str = "info") -> None:
        try:
            self.app.toast.emit(title, body, level)
        except (AttributeError, RuntimeError):
            log.info("%s: %s", title, body)

    def _config(self) -> EngineConfig:
        s = self._settings()
        return EngineConfig(interval_s=float(max(1, int(s.capture_interval_s or 3))),
                            want_browser_urls=bool(s.capture_browser_urls),
                            office_via_com=bool(s.open_office_via_com),
                            ignore_rules=[dict(r) for r in s.capture_ignore if isinstance(r, dict)],
                            exclude_pids=set(self._exclude_pids), resolve=self._resolve, portable=self._portable,
                            open_item=self._open_item)

    def _ensure_engine(self) -> CaptureEngine:
        if self._engine is None:
            cb = EngineCallbacks(
                on_snapshot=self._gui(self._on_snapshot), on_identified=self._gui(self._on_identified),
                on_candidates=self._gui(self._on_candidates), on_restore_progress=self._gui(self._on_progress),
                on_restore_done=self._gui(self._on_restore_done), on_checkpoint=self._gui(self._on_checkpoint),
                on_error=self._gui(self._on_error))
            self._engine = CaptureEngine(self.app.snapshots, cb, self._config())
        if not self._engine.alive:
            self._engine.start()
        return self._engine

    def _register_openers(self) -> None:
        """Office files the launcher opens go through COM (architecture section 5) when the launcher
        offers ``openers`` (builder 1) and ``Settings.open_office_via_com`` is on."""
        from project_opener.capture.sources import office
        openers = getattr(self.app.ctx.launcher, "openers", None)
        if not isinstance(openers, dict):
            return
        for ext in office.OPENER_EXT:
            if self._settings().open_office_via_com:
                openers[ext] = office.open_document_any_thread
            elif openers.get(ext) is office.open_document_any_thread:
                del openers[ext]

    def _capture_on(self, activity: M.Activity | None = None) -> bool:
        act = activity or (self._store().activity(self._running_id) if self._running_id else None)
        return bool(self._settings().capture_enabled) and bool(act is None or act.capture_enabled)

    def _hook_watchers(self) -> None:
        if self._watch_hooked:
            return
        watchers = getattr(self.app, "watchers", None)
        sig = getattr(watchers, "rootsChanged", None)
        if sig is not None:
            try:
                sig.connect(self._refresh_live)
                self._watch_hooked = True
            except (RuntimeError, TypeError):
                pass

    def _offline_roots(self) -> set[str]:
        """Roots ``app.watchers.roots`` reports offline (builder 1's health board); empty when unknown."""
        try:
            rows = self.app.watchers.roots.rows
        except (AttributeError, RuntimeError):
            return set()
        return {str(r.get("rootName", "")).lower() for r in rows
                if str(r.get("status", "")).lower() == "offline" and r.get("rootName")}

    def _root_of(self, path: str) -> str:
        from project_opener.core.health import path_root, root_key
        root = path_root(path)
        if not root:
            return ""
        try:
            folded, _share = root_key(root, self.app.ctx.resolver.drive_map)
        except Exception:  # noqa: BLE001
            folded = root
        return folded.lower()

    # -------------------------------------------------------------- state
    def _update_state(self) -> None:
        if not self._running_id:
            new = "idle"
        elif self._saved_until:
            new = "saved"
        elif self._user_paused or not self._capture_on():
            new = "paused"
        elif self._needs_path > 0 or self._drive_down:
            new = "needs"
        else:
            new = "running"
        if new != self._state:
            self._state = new
        self.stateChanged.emit()

    def _set_running(self, activity: M.Activity | None) -> None:
        if activity is None:
            self._running_id = self._running_name = self._running_label = self._running_color = ""
        else:
            self._running_id = activity.id
            self._running_name = activity.name
            self._running_label = activity.label
            color = activity.color
            if not color and activity.project_ids:
                proj = self._store().get(activity.project_ids[0])
                color = getattr(proj, "color", "") if proj else ""
            self._running_color = color or M.DEFAULT_COLOR

    def _refresh_live(self) -> None:
        snap = self._snapshot
        screens = screen_names()
        offline = self._offline_roots()
        entries = [e for e in W.dedupe(snap.entries) if e.key not in self._ignored] if snap else []
        app_items = {i.path.lower() for i in self._running_items() if i.kind == "app"}
        statuses = {e.key: W.display_status(e, bool(offline) and e.identified and self._root_of(e.path) in offline)
                    for e in entries}
        new_list = self._new_list(entries, app_items)
        # what "Save N new as items" saves as it opens: the sheet's default ticks (juror U2-3, one count);
        # only these rows carry the "New" badge
        to_save = {e.key for e, _g, ticked in W.new_rows(snap, new_list) if ticked and W.new_action(e)} if snap else set()
        rows = []
        for e in W.worst_first(entries, statuses):
            self._known[e.key] = e
            mon, place = monitor_and_place(e.placement, screens)
            is_item = self._is_item(e, app_items)
            rows.append({
                "entryKey": e.key, "status": statuses[e.key], "kind": e.kind, "name": W.entry_name(e),
                "path": e.path, "title": e.title, "process": e.process, "appName": e.app,
                "identifiedBy": e.identified_by, "monitor": mon, "isItem": is_item,
                "isNew": not is_item and e.key not in self._left_out, "toSave": e.key in to_save, "note": e.note,
                "candidates": list(e.candidates), **place})
        self._live.sync(rows)
        self._open = len(entries)
        self._identified = sum(1 for e in entries if e.identified)
        self._needs_path = sum(1 for s in statuses.values() if W.needs_you(s))
        self._new = len(new_list)
        self._new_to_save = len(to_save)
        cps = self.app.snapshots.checkpoints(self._running_id) if self._running_id else []
        self._since_checkpoint = len(diff.new_since(cps[0].snapshot if cps else None, snap)) if snap else 0
        roots_used = {self._root_of(i.path) for i in self._running_items()} | {
            self._root_of(e.path) for e in entries if e.identified}
        self._drive_down = bool(offline & {r for r in roots_used if r})
        self.liveChanged.emit()
        self._update_state()

    @staticmethod
    def _is_item(e: M.SnapshotEntry, app_items: set[str]) -> bool:
        """One of the activity's items: matched by path, or the window of an application item."""
        return bool(e.item_id) or (not e.identified and bool(e.exe) and e.exe.lower() in app_items)

    def _new_list(self, entries: list[M.SnapshotEntry], app_items: set[str]) -> list[M.SnapshotEntry]:
        """Every window that is not an item yet, except those ignored or left out for this activity."""
        return [e for e in entries if not self._is_item(e, app_items)
                and e.key not in self._ignored and e.key not in self._left_out]

    def _running_items(self) -> list[M.ActivityItem]:
        act = self._store().activity(self._running_id) if self._running_id else None
        return list(act.items) if act else []

    def _refresh_checkpoints(self) -> None:
        aid = self._selected_id or self._running_id
        cps = self.app.snapshots.checkpoints(aid) if aid else []
        self._checkpoints.reset([{
            "checkpointId": c.id, "takenAt": c.taken_at, "takenText": time_text(c.taken_at), "kind": c.kind,
            "label": c.label, "count": c.snapshot.open_count, "identified": c.snapshot.identified_count,
            "isLatest": i == 0} for i, c in enumerate(cps)])
        running_cps = cps if aid == self._running_id else (
            self.app.snapshots.checkpoints(self._running_id) if self._running_id else [])
        self._last_checkpoint_text = time_text(running_cps[0].taken_at) if running_cps else ""
        self.checkpointsChanged.emit()

    def _add_items(self, activity_id: str, new_items: list[M.ActivityItem]) -> tuple[M.Activity | None, int]:
        act = self._store().activity(activity_id) if activity_id else None
        if act is None:
            return None, 0
        added = 0
        for it in new_items:
            if act.item_by_path(it.path) is None:
                act.items.append(it)
                added += 1
        if added:
            self._store().update_activity(act)
            if activity_id == self._running_id and self._engine is not None:
                self._engine.update_items(act.items)
                if self._snapshot is not None:
                    diff.match_items(self._snapshot, act.items, portable=self._portable, resolve=self._resolve)
                    self._refresh_live()
        return act, added

    # -------------------------------------------------------- engine answers (GUI thread)
    def _on_snapshot(self, snap: M.Snapshot) -> None:
        if snap.activity_id != self._running_id:
            return
        self._snapshot = snap
        self._refresh_live()

    def _on_checkpoint(self, cp: M.Checkpoint) -> None:
        if cp.activity_id in (self._running_id, self._selected_id):
            self._refresh_checkpoints()
        if cp.activity_id == self._running_id:
            self._refresh_live()
            if cp.kind != "close":
                t = time_text(cp.taken_at)
                self.checkpointSaved.emit(cp.id, cp.snapshot.open_count, t)
                self._saved_until = True
                self._update_state()
                QTimer.singleShot(SAVED_MS, self._end_saved)

    def _end_saved(self) -> None:
        self._saved_until = False
        self._update_state()

    def _on_identified(self, hwnd: int, entry: M.SnapshotEntry | None, purpose: str) -> None:
        from project_opener.capture import win32
        own = entry is not None and win32.is_own_window(entry.pid, entry.exe, entry.window_class, self._exclude_pids)
        if purpose == "hover":
            if entry is None:
                self.hoverIdentified.emit(hwnd, False, "")
            elif own:
                self.hoverIdentified.emit(hwnd, False, "Project Opener")
            else:
                self.hoverIdentified.emit(hwnd, entry.identified, W.add_label(entry))
            return
        if entry is None:
            self.addResult.emit(False, "That window cannot be added", False, "")
            return
        if own:
            self.addResult.emit(False, "That is Project Opener's own window", False, "")
            return
        self._known[entry.key] = entry
        label = W.label_lines(entry)[0]
        if not entry.identified:
            self.addResult.emit(False, W.add_message(entry), True, entry.key)
            return
        if not self._running_id:
            self.app.chooserRequested.emit([entry.path])
            self.addResult.emit(False, f"No activity is running: choose where to add {W.entry_name(entry)}", False,
                                entry.key)
            return
        act, added = self._add_items(self._running_id, W.items_from_entries([entry]))
        if act is None:
            self.addResult.emit(False, "The running activity was not found", False, entry.key)
        elif added:
            self.addResult.emit(True, f"Added {label}", False, entry.key)
        else:
            self.addResult.emit(True, f"Already in {act.name}: {label}", False, entry.key)

    def _on_candidates(self, entries: list[M.SnapshotEntry]) -> None:
        entries = W.dedupe(entries)
        self._candidate_entries = {e.key: e for e in entries}
        for e in entries:
            self._known[e.key] = e
        statuses = {e.key: W.display_status(e) for e in entries}
        ordered = sorted(entries, key=lambda e: not W.default_ticked(e))     # ticked first, z-order kept
        self._candidates.reset([{
            "entryKey": e.key, "ticked": W.default_ticked(e) and "ignored by capture" not in e.note,
            "name": W.entry_name(e), "path": e.path, "appName": e.app, "status": statuses[e.key], "note": e.note,
            "kind": e.kind} for e in ordered])
        self.startCandidatesReady.emit()

    def _on_progress(self, done: int, total: int, label: str) -> None:
        self.restoreProgress.emit(done, total, label)

    def _on_restore_done(self, report: dict[str, Any]) -> None:
        self._restoring = False
        self.restoreFinished.emit(report)
        failed = report.get("failed") or []
        unrest = report.get("unrestorable") or []
        body = f"{report.get('opened', 0)} opened, {report.get('placed', 0)} put back in place"
        if failed:
            body += f"; could not open {len(failed)}"
        if unrest:
            body += f"; {len(unrest)} could not be restored (unsaved or no path)"
        self._toast("Restore finished", body, "warning" if failed else "success")

    def _on_error(self, message: str) -> None:
        log.warning("capture: %s", message)
        if message.startswith("snapshot"):
            self._toast("Snapshot", message, "warning")

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Start the capture thread (idle until an activity runs)."""
        self._ensure_engine()
        self._register_openers()
        self._hook_watchers()
        self._warm_up()

    def _warm_up(self) -> None:
        """Off the GUI thread, before anything is opened: import psutil (PySide's import hook reads a module's
        source on first import) and read this process's start time, every activity's snapshot file and the
        running markers into the store's memory, so opening an activity never waits on an import or on the
        data folder's share (the dock's frame times)."""
        run_async = getattr(self.app, "run_async", None)
        if run_async is None:
            return
        ids = [a.id for a in getattr(self._store(), "activities", [])]
        snapshots = self.app.snapshots

        def work() -> float:
            for aid in ids:
                snapshots.review(aid)
            snapshots.markers()
            try:
                import psutil
                return float(psutil.Process().create_time())
            except Exception:  # noqa: BLE001
                return 0.0

        def done(started: float) -> None:
            self._process_started = started
        try:
            run_async(work, done, lambda *_a: None)
        except Exception:  # noqa: BLE001
            log.exception("capture warm-up failed")

    def shutdown(self) -> None:
        """Stop the capture thread; write a final live snapshot; do NOT clear running markers
        (a clean exit with an activity still running keeps its marker only if the user chose so)."""
        if self._engine is not None:
            self._engine.stop(timeout=2.0)          # quit: at most 2 s (the final checkpoint is queued first)
            self._engine = None

    def apply_settings(self) -> None:
        """Capture keys changed in Settings (``SettingsApi.setValue`` calls this): interval, browser URLs,
        ignore rules, Office via COM, the global switch."""
        s = self._settings()
        if self._engine is not None:
            self._engine.set_options(interval_s=float(max(1, int(s.capture_interval_s or 3))),
                                     want_browser_urls=bool(s.capture_browser_urls),
                                     office_via_com=bool(s.open_office_via_com))
            self._engine.set_ignore_rules(list(s.capture_ignore))
            if self._running_id:
                self._engine.set_paused(self._user_paused or not self._capture_on())
        self._register_openers()
        self._update_state()

    # -------------------------------------------------------------- slots
    @Slot(str)
    def startActivity(self, activity_id: str) -> None:
        """Mark running (RunningMarker), begin capture passes for it.  Called by ActivitiesApi.open."""
        act = self._store().activity(activity_id)
        if act is None:
            log.warning("startActivity: unknown activity %s", activity_id)
            return
        if self._running_id and self._running_id != activity_id:
            self.endActivity()
        engine = self._ensure_engine()
        self._register_openers()
        self._hook_watchers()
        started = self._process_started
        if started is None:
            try:
                import psutil
                started = self._process_started = float(psutil.Process().create_time())
            except Exception:  # noqa: BLE001
                started = 0.0
        self.app.snapshots.mark_running(M.RunningMarker(activity_id=act.id, pid=os.getpid(), process_started=started))
        # what was saved before this start: the first pass will overwrite the live snapshot, and the
        # Resume band calls restoreLatest right after startActivity
        self._before_start = (act.id, self.app.snapshots.latest(act.id))
        self._set_running(act)
        self._ignored, self._left_out = self.app.snapshots.review(act.id)
        self._user_paused = False
        self._snapshot = None
        self._selected_id = ""
        engine.run_activity(act.id, act.items)
        engine.set_paused(not self._capture_on(act))
        self._refresh_live()
        self._refresh_checkpoints()

    @Slot()
    def endActivity(self) -> None:
        """Final checkpoint (kind "close"), clear the marker, stop passes."""
        aid = self._running_id
        if not aid:
            return
        if self._engine is not None:
            if self._capture_on() and not self._user_paused:
                self._engine.request_snapshot("close", "")
            self._engine.stop_activity()
        self.app.snapshots.clear_running(aid)
        self._set_running(None)
        self._ignored, self._left_out = set(), set()
        self._new_rows.reset([])
        self._new_entries = {}
        self._snapshot = None
        self._user_paused = False
        self._saved_until = False
        self._refresh_live()
        self._refresh_checkpoints()

    @Slot()
    def snapshotNow(self) -> None:
        """Checkpoint now (Ctrl+Alt+S, the pill, the tray, the activity page)."""
        if not self._running_id:
            self._toast("Snapshot", "No activity is running", "info")
            return
        self._ensure_engine().request_snapshot("manual", "")

    @Slot()
    def saveNewAsItems(self) -> None:
        """"Save N new as items" never adds by itself: it fills ``newCandidates`` and asks for the tick list
        (``saveNewRequested``; the main window opens the sheet)."""
        if not self._running_id:
            return
        self.prepareSaveNew()
        self.saveNewRequested.emit()

    @Slot()
    def prepareSaveNew(self) -> None:  # noqa: N802
        """Fill ``newCandidates`` from the live snapshot (owner decision: everything open is offered; files,
        folders and pages opened since the activity started are ticked, app, chat and mail windows are not)."""
        snap = self._snapshot
        rows: list[dict[str, Any]] = []
        self._new_entries = {}
        if self._running_id and snap is not None:
            app_items = {i.path.lower() for i in self._running_items() if i.kind == "app"}
            entries = self._new_list([e for e in W.dedupe(snap.entries) if e.key not in self._ignored], app_items)
            for e, group, ticked in W.new_rows(snap, entries):
                self._known[e.key] = e
                self._new_entries[e.key] = e
                action = W.new_action(e)
                rows.append({"entryKey": e.key, "ticked": ticked and bool(action), "tickable": bool(action),
                             "name": W.entry_name(e), "path": e.path, "appName": e.app or e.process,
                             "status": W.display_status(e), "note": e.note, "kind": e.kind, "group": group,
                             "groupLabel": W.NEW_GROUPS[group], "action": action})
        self._new_rows.reset(rows)
        self.newCandidatesChanged.emit()

    @Slot(str, bool)
    def setNewTicked(self, entry_key: str, ticked: bool) -> None:  # noqa: N802
        i = self._new_rows.indexOf(entry_key)
        if i >= 0 and self._new_rows.rows[i].get("tickable"):
            self._new_rows.update(i, ticked=bool(ticked))

    @Slot(result=int)
    def saveTicked(self) -> int:  # noqa: N802
        """Add the ticked rows as items (an application window adds the application itself).  The unticked
        rows are left out: they stay in the live list but are not offered as new again for this activity."""
        aid = self._running_id
        if not aid:
            return 0
        rows = self._new_rows.rows
        ticked = [self._new_entries[r["entryKey"]] for r in rows
                  if r.get("ticked") and r["entryKey"] in self._new_entries]
        items: list[M.ActivityItem] = W.items_from_entries(ticked)
        exes = {it.path.lower() for it in items}
        for e in ticked:
            if e.identified:
                continue
            app = W.app_item(e)
            if app is not None and app.path.lower() not in exes:
                exes.add(app.path.lower())
                items.append(app)
        unticked = {r["entryKey"] for r in rows if not r.get("ticked")}
        if unticked:
            self._left_out |= unticked
            self.app.snapshots.set_review(aid, left_out=self._left_out)
        act, added = self._add_items(aid, items)
        self._new_rows.reset([])
        self._new_entries = {}
        self.newCandidatesChanged.emit()
        self._refresh_live()
        if act is not None and added:
            self._toast("Saved as items", f"{added} added to {act.name}", "success")
        return added

    # ------------------------------------------------- ignore, for this activity or always
    @Slot(str)
    def ignoreForActivity(self, entry_key: str) -> None:  # noqa: N802
        """The pill's list: leave this window out of the running activity's list and counts, kept in the
        activity's snapshot file so it stays ignored the next time the activity runs."""
        aid = self._running_id
        if not aid or not entry_key:
            return
        self._ignored.add(entry_key)
        self.app.snapshots.set_review(aid, ignored=self._ignored)
        self._refresh_live()

    @Slot(str)
    def unignoreForActivity(self, entry_key: str) -> None:  # noqa: N802
        aid = self._running_id
        if not aid or entry_key not in self._ignored:
            return
        self._ignored.discard(entry_key)
        self.app.snapshots.set_review(aid, ignored=self._ignored)
        self._refresh_live()

    @Slot(str, result=str)
    def ignoreApp(self, entry_key: str) -> str:  # noqa: N802
        """"Always ignore this app": a ``Settings.capture_ignore`` rule for every window of the entry's
        process (every activity, from now on).  Returns the application's name ("" when unknown)."""
        entry = self._known.get(entry_key)
        if entry is None or not entry.process:
            return ""
        s = self._settings()
        rule = W.app_rule(entry)
        if rule not in s.capture_ignore:
            s.capture_ignore.append(rule)
            s.save()
        if self._engine is not None:
            self._engine.set_ignore_rules(list(s.capture_ignore))
        if self._snapshot is not None:
            proc = entry.process.lower()
            self._snapshot.entries = [e for e in self._snapshot.entries if e.process.lower() != proc]
        self._refresh_live()
        return entry.app or entry.process

    @Slot(str)
    def unignoreApp(self, entry_key: str) -> None:  # noqa: N802
        """Undo "Always ignore this app" (the window comes back with the next pass)."""
        entry = self._known.get(entry_key)
        if entry is None:
            return
        s = self._settings()
        rule = W.app_rule(entry)
        if rule in s.capture_ignore:
            s.capture_ignore.remove(rule)
            s.save()
            if self._engine is not None:
                self._engine.set_ignore_rules(list(s.capture_ignore))

    @Slot()
    def pause(self) -> None:
        if not self._running_id:
            return
        self._user_paused = True
        if self._engine is not None:
            self._engine.set_paused(True)
        self._update_state()

    @Slot()
    def resume(self) -> None:
        if not self._running_id:
            return
        self._user_paused = False
        if self._engine is not None:
            self._engine.set_paused(not self._capture_on())
        self._update_state()

    @Slot(bool)
    def setGlobal(self, on: bool) -> None:
        s = self._settings()
        if bool(s.capture_enabled) != bool(on):
            s.capture_enabled = bool(on)
            s.save()
        if self._engine is not None and self._running_id:
            self._engine.set_paused(self._user_paused or not self._capture_on())
        self._update_state()

    @Slot()
    def addForegroundWindow(self) -> None:
        """Ctrl+Alt+A: identify the window in front and add it; answer with ``addResult``."""
        from project_opener.capture import win32
        hwnd = win32.foreground_window()
        if not hwnd:
            self.addResult.emit(False, "No window is in front", False, "")
            return
        self.addWindow(hwnd)

    @Slot(int)
    def addWindow(self, hwnd: int) -> None:
        """The picker's click: identify ``hwnd`` (GA_ROOT) and add it; answer with ``addResult``."""
        from project_opener.capture import win32
        root = win32.root_of(int(hwnd))
        if win32.is_own_hwnd(root, self._exclude_pids):
            self.addResult.emit(False, "That is Project Opener's own window", False, "")
            return
        self._ensure_engine().request_identify(root, "add")

    @Slot(int)
    def identifyForPicker(self, hwnd: int) -> None:
        """Hovering in the picker: answer with ``hoverIdentified`` (cached, cheap)."""
        from project_opener.capture import win32
        root = win32.root_of(int(hwnd))
        if win32.is_own_hwnd(root, self._exclude_pids):
            self.hoverIdentified.emit(int(hwnd), False, "Project Opener")
            return
        self._ensure_engine().request_identify(root, "hover")

    def _target_activity(self) -> str:
        return self._running_id or self._selected_id

    @Slot(str, str)
    def attachPath(self, entry_key: str, path: str) -> None:
        """An unidentified/ambiguous window: the user gives the path once; it becomes an item."""
        path = (path or "").strip().strip('"')
        aid = self._target_activity()
        if not path or not aid:
            self.addResult.emit(False, "Nothing to attach" if not path else "No activity is running", False,
                                entry_key)
            return
        entry = self._known.get(entry_key)
        item = M.ActivityItem(path=path, kind=M.guess_kind(path))
        act, added = self._add_items(aid, [item])
        if act is None:
            self.addResult.emit(False, "The activity was not found", True, entry_key)
            return
        name = os.path.basename(path.rstrip("\\/")) or path
        if entry is not None:
            entry.status, entry.path, entry.identified_by = "identified", path, "manual"
            entry.kind = item.kind
        self.addResult.emit(True, f"Added {name}" if added else f"Already in {act.name}: {name}", False, entry_key)

    @Slot(str)
    def addAsApplication(self, entry_key: str) -> None:
        """Unsaved "Drawing1" in AutoCAD: add AutoCAD itself as an application item."""
        entry = self._known.get(entry_key)
        aid = self._target_activity()
        item = W.app_item(entry) if entry else None
        if item is None or not aid:
            self.addResult.emit(False, "The application's program file is not known" if aid else
                                "No activity is running", False, entry_key)
            return
        act, added = self._add_items(aid, [item])
        if act is None:
            self.addResult.emit(False, "The activity was not found", False, entry_key)
            return
        self.addResult.emit(True, f"Added {item.label}" if added else f"Already in {act.name}: {item.label}", False,
                            entry_key)

    @Slot(str)
    def ignoreEntry(self, entry_key: str) -> None:
        """Ignore this process + title pattern from now on (Settings.capture_ignore)."""
        entry = self._known.get(entry_key)
        if entry is None:
            return
        s = self._settings()
        rule = W.ignore_rule(entry)
        if rule not in s.capture_ignore:
            s.capture_ignore.append(rule)
            s.save()
        if self._engine is not None:
            self._engine.set_ignore_rules(list(s.capture_ignore))
        if self._snapshot is not None:
            self._snapshot.entries = [e for e in self._snapshot.entries if e.key != entry_key]
        self._refresh_live()

    @Slot(str)
    def selectActivity(self, activity_id: str) -> None:
        """Show ``activity_id``'s checkpoints in the model (the activity page of a non-running activity)."""
        self._selected_id = activity_id or ""
        self._refresh_checkpoints()

    def _restore(self, activity_id: str, snapshot: M.Snapshot | None) -> None:
        if snapshot is None or not snapshot.entries:
            self._toast("Restore", "Nothing saved to restore for this activity", "info")
            self.restoreFinished.emit({"opened": 0, "placed": 0, "failed": [], "unrestorable": [], "seconds": 0})
            return
        act = self._store().activity(activity_id)
        items = list(act.items) if act else []
        self._restoring = True
        self.restoreProgress.emit(0, len(diff.order_for_restore(snapshot, items)), "")
        self._ensure_engine().request_restore(snapshot, items)

    @Slot(str, str)
    def restoreCheckpoint(self, activity_id: str, checkpoint_id: str) -> None:
        cp = self.app.snapshots.checkpoint(activity_id, checkpoint_id)
        self._restore(activity_id, cp.snapshot if cp else None)

    # ---------------------------------------------------------------- resume
    @Slot(str)
    def prepareResume(self, activity_id: str) -> None:  # noqa: N802
        """Fill ``resumeCandidates`` from the activity's latest snapshot (owner decision: a tick list, items
        pre-ticked).  With nothing captured, the activity's items are listed, ticked."""
        snap = self.app.snapshots.latest(activity_id) if activity_id else None
        act = self._store().activity(activity_id) if activity_id else None
        items = list(act.items) if act else []
        self._resume_prep = (activity_id, snap)
        rows: list[dict[str, Any]] = []
        if snap is not None and snap.entries:
            diff.match_items(snap, items, portable=self._portable, resolve=self._resolve)
            screens = screen_names()
            for e, group, ticked in W.resume_rows(snap, items):
                mon, _place = monitor_and_place(e.placement, screens)
                why = "" if e.identified else ("Unsaved: no file to reopen" if e.status == "unsaved"
                                               else "No file path: cannot be reopened")
                rows.append({"entryKey": e.key, "ticked": ticked, "tickable": e.identified,
                             "name": W.entry_name(e), "path": e.path, "appName": e.app or e.process,
                             "status": W.display_status(e), "note": why or e.note, "kind": e.kind,
                             "group": group, "groupLabel": W.RESUME_GROUPS[group], "monitor": mon})
        else:
            for it in (act.enabled_items if act else []):
                if it.path.strip():
                    rows.append({"entryKey": "item:" + it.id, "ticked": True, "tickable": True,
                                 "name": it.display_name, "path": it.path, "appName": "", "status": "identified",
                                 "note": "", "kind": it.kind, "group": "items",
                                 "groupLabel": W.RESUME_GROUPS["items"], "monitor": ""})
        self._resume_rows.reset(rows)
        self.resumeCandidatesChanged.emit()

    @Slot(str, bool)
    def setResumeTicked(self, entry_key: str, ticked: bool) -> None:  # noqa: N802
        i = self._resume_rows.indexOf(entry_key)
        if i >= 0 and self._resume_rows.rows[i].get("tickable"):
            self._resume_rows.update(i, ticked=bool(ticked))

    def resume_prepared(self, activity_id: str) -> bool:
        """Whether the Resume sheet was filled for ``activity_id`` (``ActivitiesApi.resumeNow`` asks)."""
        return bool(activity_id) and self._resume_prep[0] == activity_id

    def resume_ticked(self) -> list[str]:
        """Entry keys ticked in the Resume sheet (``item:<id>`` rows when nothing was captured)."""
        return [r["entryKey"] for r in self._resume_rows.rows if r.get("ticked")]

    @Slot(str)
    def restoreTicked(self, activity_id: str) -> None:  # noqa: N802
        """Reopen only the ticked rows of the prepared snapshot, each placed where it was."""
        aid, snap = self._resume_prep
        if aid != activity_id or snap is None:
            self.restoreLatest(activity_id)
            return
        keys = set(self.resume_ticked())
        chosen = M.Snapshot(activity_id=snap.activity_id, taken_at=snap.taken_at, full=snap.full,
                            monitors=list(snap.monitors), session_start=snap.session_start,
                            entries=[e for e in snap.entries if e.key in keys])
        self._resume_prep = ("", None)
        self._resume_rows.reset([])
        if self._before_start[0] == activity_id:
            self._before_start = ("", None)
        self._restore(activity_id, chosen)

    @Slot(str)
    def restoreLatest(self, activity_id: str) -> None:
        """Resume band: reopen the latest snapshot in order and put windows back.  When the activity was
        just started, "latest" is what was saved before that start (not the new session's first pass)."""
        aid, before = self._before_start
        if aid == activity_id and activity_id == self._running_id:
            self._before_start = ("", None)
            self._restore(activity_id, before)
            return
        self._restore(activity_id, self.app.snapshots.latest(activity_id))

    @Slot()
    def prepareStartFromOpen(self) -> None:
        """Enumerate and identify every window; fill ``startCandidates``; emit ``startCandidatesReady``."""
        self._ensure_engine().request_enumerate_all()

    @Slot(str, bool)
    def setCandidateTicked(self, entry_key: str, ticked: bool) -> None:
        i = self._candidates.indexOf(entry_key)
        if i >= 0:
            self._candidates.update(i, ticked=bool(ticked))

    @Slot(str, str, result=str)
    def startFromOpen(self, name: str, project_id: str) -> str:
        """Create the activity from the ticked candidates, make it running; returns its id."""
        ticked = [self._candidate_entries[r["entryKey"]] for r in self._candidates.rows
                  if r.get("ticked") and r["entryKey"] in self._candidate_entries]
        items: list[M.ActivityItem] = W.items_from_entries(ticked)
        skipped = 0
        exes = {it.path.lower() for it in items}
        for e in ticked:
            if e.identified:
                continue
            app = W.app_item(e) if e.status in ("unidentified", "unsaved") else None
            if app is None:
                skipped += 1
                continue
            if app.path.lower() not in exes:
                exes.add(app.path.lower())
                items.append(app)
        act = M.Activity(name=(name or "").strip() or "From what's open",
                         project_ids=[project_id] if project_id else [], items=items)
        self._store().add_activity(act)
        if skipped:
            self._toast("Start from what's open", f"{skipped} window(s) need a path and were left out", "warning")
        self._candidates.reset([])
        self._candidate_entries = {}
        self.startActivity(act.id)
        return act.id

    @Slot(str, result="QVariantMap")
    def lastWindows(self, activity_id: str) -> dict[str, Any]:  # noqa: N802
        """The Monitors panel of an activity that is not running (juror D2-1, C2-1): the windows of its last
        snapshot (``SnapshotStore.latest``) on their monitors, as {"takenText", "rows"}; each row has
        ``monitor``, ``status``, ``name`` and ``placeX/Y/W/H``.  Empty rows when nothing was recorded."""
        snap = self.app.snapshots.latest(activity_id) if activity_id else None
        if snap is None:
            return {"takenText": "", "rows": []}
        screens = screen_names()
        rows = []
        for e in W.dedupe(snap.entries):
            mon, place = monitor_and_place(e.placement, screens)
            rows.append({"monitor": mon, "status": W.display_status(e), "name": W.entry_name(e), **place})
        return {"takenText": time_text(snap.taken_at), "rows": rows}
