"""``app.capture``: the running activity, the live snapshot, checkpoints, add-a-window, start-from-open,
restore.  Owner: builder 2 (CAPTURE).

The pill, the tray, the activity page and the Resume band all read this one
object.  All COM work happens on the capture thread (``capture.engine``);
results arrive here through ``app.run_on_gui``.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

ENTRY_ROLES = (
    "entryKey", "status", "kind", "name", "path", "title", "process", "appName", "identifiedBy", "monitor",
    "isItem", "isNew", "note", "candidates",
)
CHECKPOINT_ROLES = ("checkpointId", "takenAt", "takenText", "kind", "label", "count", "identified", "isLatest")
CANDIDATE_ROLES = ("entryKey", "ticked", "name", "path", "appName", "status", "note", "kind")

# state: idle (no activity running) | running | needs (a path is needed or a drive is down) | paused | saved
STATES = ("idle", "running", "needs", "paused", "saved")


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

    def __init__(self, app: Any):
        super().__init__(app)
        self._live = DictListModel(ENTRY_ROLES, key="entryKey", parent=self)
        self._checkpoints = DictListModel(CHECKPOINT_ROLES, key="checkpointId", parent=self)
        self._candidates = DictListModel(CANDIDATE_ROLES, key="entryKey", parent=self)
        self._running_id = ""
        self._running_name = ""
        self._running_label = ""
        self._running_color = ""
        self._state = "idle"
        self._open = 0
        self._identified = 0
        self._needs_path = 0
        self._new = 0
        self._last_checkpoint_text = ""
        self._since_checkpoint = 0
        self._drive_down = False

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

    # --------------------------------------------------------- properties
    runningId = ro(str, "_running_id", stateChanged)
    runningName = ro(str, "_running_name", stateChanged)
    runningLabel = ro(str, "_running_label", stateChanged)      # the pill's short name
    runningColor = ro(str, "_running_color", stateChanged)
    state = ro(str, "_state", stateChanged)
    openCount = ro(int, "_open", liveChanged)
    identifiedCount = ro(int, "_identified", liveChanged)
    needsPathCount = ro(int, "_needs_path", liveChanged)
    newCount = ro(int, "_new", liveChanged)                     # identified, not items yet
    lastCheckpointText = ro(str, "_last_checkpoint_text", checkpointsChanged)
    sinceCheckpoint = ro(int, "_since_checkpoint", liveChanged)  # "2 new since"
    driveDown = ro(bool, "_drive_down", stateChanged)            # a root the activity uses is offline (red ring)

    @Property(bool, notify=stateChanged)
    def globalEnabled(self) -> bool:
        return bool(self.app.ctx.settings.capture_enabled)

    # -------------------------------------------------------------- slots
    def start(self) -> None:
        """Start the capture thread (idle until an activity runs)."""

    def shutdown(self) -> None:
        """Stop the capture thread; write a final live snapshot; do NOT clear running markers
        (a clean exit with an activity still running keeps its marker only if the user chose so)."""

    @Slot(str)
    def startActivity(self, activity_id: str) -> None:
        """Mark running (RunningMarker), begin capture passes for it.  Called by ActivitiesApi.open."""
        self.todo("CaptureApi.startActivity")

    @Slot()
    def endActivity(self) -> None:
        """Final checkpoint (kind "close"), clear the marker, stop passes."""
        self.todo("CaptureApi.endActivity")

    @Slot()
    def snapshotNow(self) -> None:
        """Checkpoint now (Ctrl+Alt+S, the pill, the tray, the activity page)."""
        self.todo("CaptureApi.snapshotNow")

    @Slot()
    def saveNewAsItems(self) -> None:
        self.todo("CaptureApi.saveNewAsItems")

    @Slot()
    def pause(self) -> None:
        self.todo("CaptureApi.pause")

    @Slot()
    def resume(self) -> None:
        self.todo("CaptureApi.resume")

    @Slot(bool)
    def setGlobal(self, on: bool) -> None:
        self.todo("CaptureApi.setGlobal")

    @Slot()
    def addForegroundWindow(self) -> None:
        """Ctrl+Alt+A: identify the window in front and add it; answer with ``addResult``."""
        self.todo("CaptureApi.addForegroundWindow")

    @Slot(int)
    def addWindow(self, hwnd: int) -> None:
        """The picker's click: identify ``hwnd`` (GA_ROOT) and add it; answer with ``addResult``."""
        self.todo("CaptureApi.addWindow")

    @Slot(int)
    def identifyForPicker(self, hwnd: int) -> None:
        """Hovering in the picker: answer with ``hoverIdentified`` (cached, cheap)."""
        self.todo("CaptureApi.identifyForPicker")

    @Slot(str, str)
    def attachPath(self, entry_key: str, path: str) -> None:
        """An unidentified/ambiguous window: the user gives the path once; it becomes an item."""
        self.todo("CaptureApi.attachPath")

    @Slot(str)
    def addAsApplication(self, entry_key: str) -> None:
        """Unsaved "Drawing1" in AutoCAD: add AutoCAD itself as an application item."""
        self.todo("CaptureApi.addAsApplication")

    @Slot(str)
    def ignoreEntry(self, entry_key: str) -> None:
        """Ignore this process + title pattern from now on (Settings.capture_ignore)."""
        self.todo("CaptureApi.ignoreEntry")

    @Slot(str)
    def selectActivity(self, activity_id: str) -> None:
        """Show ``activity_id``'s checkpoints in the model (the activity page of a non-running activity)."""
        self.todo("CaptureApi.selectActivity")

    @Slot(str, str)
    def restoreCheckpoint(self, activity_id: str, checkpoint_id: str) -> None:
        self.todo("CaptureApi.restoreCheckpoint")

    @Slot(str)
    def restoreLatest(self, activity_id: str) -> None:
        """Resume band: reopen the latest snapshot in order and put windows back."""
        self.todo("CaptureApi.restoreLatest")

    @Slot()
    def prepareStartFromOpen(self) -> None:
        """Enumerate and identify every window; fill ``startCandidates``; emit ``startCandidatesReady``."""
        self.todo("CaptureApi.prepareStartFromOpen")

    @Slot(str, bool)
    def setCandidateTicked(self, entry_key: str, ticked: bool) -> None:
        self.todo("CaptureApi.setCandidateTicked")

    @Slot(str, str, result=str)
    def startFromOpen(self, name: str, project_id: str) -> str:
        """Create the activity from the ticked candidates, make it running; returns its id."""
        return self.todo("CaptureApi.startFromOpen")
