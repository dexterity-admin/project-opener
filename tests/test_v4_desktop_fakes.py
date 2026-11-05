"""Fakes of the facade pieces the desktop layer reads (builder 3), and a check that they match the contract.

``FakeCapture`` mirrors ``app.capture`` (docs/V4-ARCHITECTURE.md 7.4): the property and signal names
are compared with the real ``CaptureApi`` below, so the fake cannot drift from the contract.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener.quick.base import ro
from project_opener.quick.listmodel import DictListModel

ENTRY_ROLES = ("entryKey", "status", "kind", "name", "path", "title", "process", "appName", "identifiedBy",
               "monitor", "isItem", "isNew", "note", "candidates")


class FakeCapture(QObject):
    stateChanged = Signal()
    liveChanged = Signal()
    checkpointsChanged = Signal()
    checkpointSaved = Signal(str, int, str)
    hoverIdentified = Signal(int, bool, str)
    addResult = Signal(bool, str, bool, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._live = DictListModel(ENTRY_ROLES, key="entryKey", parent=self)
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
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    @Property(QObject, constant=True)
    def live(self) -> DictListModel:
        return self._live

    runningId = ro(str, "_running_id", stateChanged)
    runningName = ro(str, "_running_name", stateChanged)
    runningLabel = ro(str, "_running_label", stateChanged)
    runningColor = ro(str, "_running_color", stateChanged)
    state = ro(str, "_state", stateChanged)
    openCount = ro(int, "_open", liveChanged)
    identifiedCount = ro(int, "_identified", liveChanged)
    needsPathCount = ro(int, "_needs_path", liveChanged)
    newCount = ro(int, "_new", liveChanged)
    lastCheckpointText = ro(str, "_last_checkpoint_text", checkpointsChanged)
    sinceCheckpoint = ro(int, "_since_checkpoint", liveChanged)
    driveDown = ro(bool, "_drive_down", stateChanged)

    def set(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self, "_" + k, v)
        self.stateChanged.emit()
        self.liveChanged.emit()
        self.checkpointsChanged.emit()

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))

    @Slot()
    def snapshotNow(self) -> None:  # noqa: N802
        self._record("snapshotNow")

    @Slot()
    def saveNewAsItems(self) -> None:  # noqa: N802
        self._record("saveNewAsItems")

    @Slot(str)
    def ignoreForActivity(self, key: str) -> None:  # noqa: N802
        self._record("ignoreForActivity", key)

    @Slot(str)
    def unignoreForActivity(self, key: str) -> None:  # noqa: N802
        self._record("unignoreForActivity", key)

    @Slot(str, result=str)
    def ignoreApp(self, key: str) -> str:  # noqa: N802
        self._record("ignoreApp", key)
        return "AutoCAD"

    @Slot(str)
    def unignoreApp(self, key: str) -> None:  # noqa: N802
        self._record("unignoreApp", key)

    @Slot()
    def pause(self) -> None:
        self._record("pause")

    @Slot()
    def resume(self) -> None:
        self._record("resume")

    @Slot()
    def endActivity(self) -> None:  # noqa: N802
        self._record("endActivity")

    @Slot()
    def addForegroundWindow(self) -> None:  # noqa: N802
        self._record("addForegroundWindow")

    @Slot(int)
    def addWindow(self, hwnd: int) -> None:  # noqa: N802
        self._record("addWindow", hwnd)

    @Slot(int)
    def identifyForPicker(self, hwnd: int) -> None:  # noqa: N802
        self._record("identifyForPicker", hwnd)


class FakeUi(QObject):
    tokensChanged = Signal()
    motionChanged = Signal()

    def __init__(self, tokens: dict[str, Any], motion: str = "off", k: float = 0.0, parent: QObject | None = None):
        super().__init__(parent)
        self._tokens = tokens
        self._motion = motion
        self._k = k
        self.routes: list[tuple[str, dict[str, Any]]] = []

    tokens = ro("QVariantMap", "_tokens", tokensChanged)
    motion = ro(str, "_motion", motionChanged)
    k = ro(float, "_k", motionChanged)

    @Slot(str, "QVariantMap")
    def go(self, route: str, payload: dict[str, Any]) -> None:
        self.routes.append((route, dict(payload or {})))


class FakeFacade(QObject):
    toast = Signal(str, str, str)
    showWindowRequested = Signal()
    paletteRequested = Signal()
    desktopChanged = Signal()

    def __init__(self, data_dir: Any, dark: bool = True):
        super().__init__()
        from project_opener.core.settings import Settings
        from project_opener.quick.ui_state import tokens_for
        settings = Settings.load(data_dir)
        self.ctx = SimpleNamespace(settings=settings, store=SimpleNamespace(sorted_activities=lambda: []))
        self._capture = FakeCapture(self)
        self._ui = FakeUi(tokens_for(dark, settings.accent, settings.density), parent=self)
        self._desktop: QObject | None = None
        self.commands: list[dict[str, Any]] = []

    @Property(QObject, constant=True)
    def capture(self) -> FakeCapture:
        return self._capture

    @Property(QObject, constant=True)
    def ui(self) -> FakeUi:
        return self._ui

    @Property(QObject, notify=desktopChanged)
    def desktop(self) -> QObject | None:
        return self._desktop

    def set_desktop(self, api: QObject) -> None:
        self._desktop = api
        self.desktopChanged.emit()

    @Slot("QVariantMap")
    def handle_command(self, cmd: dict[str, Any]) -> None:
        self.commands.append(dict(cmd))


def test_fake_capture_matches_the_contract():
    from project_opener.quick.capture_api import CaptureApi

    def names(cls: type, kind: type) -> set[str]:
        return {n for n in dir(cls) if isinstance(getattr(cls, n, None), kind)}

    fake_props = names(FakeCapture, Property)
    real_props = names(CaptureApi, Property)
    assert fake_props <= real_props, fake_props - real_props
    fake_sigs = {n for n in dir(FakeCapture) if isinstance(getattr(FakeCapture, n), Signal)}
    real_sigs = {n for n in dir(CaptureApi) if isinstance(getattr(CaptureApi, n), Signal)}
    assert fake_sigs <= real_sigs, fake_sigs - real_sigs
    for slot in ("snapshotNow", "saveNewAsItems", "pause", "resume", "endActivity", "addForegroundWindow",
                 "addWindow", "identifyForPicker"):
        assert callable(getattr(CaptureApi, slot))
