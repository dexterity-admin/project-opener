"""Juror round 2, the dock (D2-2, U2-1): rows from the first frame, only a dock on screen builds rows, a settling
row re-binds the progress bar alone, the idle pre-warm, the pipeline cache, and the guard over the grow."""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import test_v4_quick_facade as QF  # noqa: E402

qapp, seeded, facade, pump = QF.qapp, QF.seeded, QF.facade, QF.pump      # the facade tests' fixtures

QML = Path(__file__).resolve().parents[1] / "project_opener" / "qml"


def _read(rel: str) -> str:
    return (QML / rel).read_text(encoding="utf-8")


def test_settling_rows_rebind_the_progress_bar_only(facade, seeded):
    """Each settled row used to emit launchChanged, re-running every dock binding on Home (up to 175 ms of GUI
    time per row); it now emits progressChanged, and launchChanged only opens and closes the run."""
    api = facade.activities
    counts = {"launch": 0, "progress": 0}
    api.launchChanged.connect(lambda: counts.__setitem__("launch", counts["launch"] + 1))
    api.progressChanged.connect(lambda: counts.__setitem__("progress", counts["progress"] + 1))
    done: list = []
    api.launchFinished.connect(lambda aid, s: done.append(s))
    api.open(seeded["act"])
    deadline = time.monotonic() + 10
    while not done and time.monotonic() < deadline:
        pump(30)
    assert done and api.launchProgress == 1.0
    assert counts["progress"] >= 3 + 2          # begin, one per row, done
    assert counts["launch"] == 2                # begin and done only


def test_dock_rows_are_there_from_the_first_frame():
    dock = _read("components/DockView.qml")
    assert "holdMs" not in dock and "arrive" not in dock          # no waiting for the grow
    assert 'model.status === "queued"' in dock and "waiting ? 0.35 : 1" in dock
    scene = _read("components/Scene.qml")
    assert "holdMs" not in scene and "clip: growing" in scene
    assert "PauseAnimation { duration: Math.max(0, scene.growMs - 120) }" not in scene


def test_only_a_dock_on_screen_builds_rows():
    dock = _read("components/DockView.qml")
    assert "model: dock.visible ? dock.rows : null" in dock
    assert "sourceComponent: Tip { visible: true; text: model.path }" in dock      # built on hover


def test_idle_prewarm_of_the_dock():
    main = _read("Main.qml")
    assert 'objectName: "warmDock"' in main and "DockView { rows: warmRows" in main
    assert "running: root.visible && !root.dockWarmed" in main
    assert 'status: "queued"' in main and 'status: "opening"' in main


def test_pipeline_cache_files_set_before_show(tmp_path, qapp):
    from PySide6.QtQuick import QQuickGraphicsConfiguration

    from project_opener import app_v4

    class Win:
        def __init__(self):
            self.cfg = QQuickGraphicsConfiguration()

        def graphicsConfiguration(self):  # noqa: N802
            return self.cfg

        def setGraphicsConfiguration(self, cfg):  # noqa: N802
            self.cfg = cfg

    w = Win()
    path = app_v4.configure_pipeline_cache(w, tmp_path, "rhi")
    assert path == tmp_path / "cache" / "rhi-pipelines.bin" and path.parent.is_dir()
    assert w.cfg.pipelineCacheSaveFile() == str(path) and w.cfg.pipelineCacheLoadFile() == ""
    path.write_bytes(b"cache")
    w2 = Win()
    app_v4.configure_pipeline_cache(w2, tmp_path, "rhi")
    assert w2.cfg.pipelineCacheLoadFile() == str(path)
    assert app_v4.configure_pipeline_cache(Win(), tmp_path, "software") is None


def test_guard_window_follows_the_level(facade):
    ui = facade.ui
    ui.setMotion("rich")
    assert ui.dockMeasureMs == 500
    ui.setMotion("purposeful")
    assert ui.dockMeasureMs == 332
    ui.setMotion("off")
    assert ui.dockMeasureMs == 0
