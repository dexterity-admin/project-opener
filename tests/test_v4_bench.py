"""``ProjectOpener.exe --bench``: the release benchmark (project_opener/bench.py).

The numbers are the PC's; these tests hold the plumbing: the CLI reaches the bench before anything picks a
data folder or claims the single instance, the stats and verdicts follow the app's own guard, the output goes
where the docs say, and a real run (offscreen, one opening per level) writes its JSON and summary, leaves no
throwaway folder behind and never writes to the user's data folder.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from project_opener import bench as B
from project_opener.quick import motion as MO

ROOT = Path(__file__).resolve().parents[1]


def test_cli_routes_to_the_bench_before_any_data_folder(monkeypatch):
    from project_opener import app, app_v4
    seen = {}
    monkeypatch.setattr(B, "main", lambda args: seen.setdefault("args", args) and 0 or 0)
    monkeypatch.setattr(app_v4, "dev_data_dir", lambda: (_ for _ in ()).throw(AssertionError("data folder picked")))
    monkeypatch.setattr(app_v4, "main", lambda args: (_ for _ in ()).throw(AssertionError("the shell started")))
    assert app.main(["--bench", "--out", "x.json", "--bench-runs", "2"]) == 0
    assert seen["args"].bench and seen["args"].out == "x.json" and seen["args"].bench_runs == 2


def test_guard_measures_the_grow_only():
    assert MO.dock_measure_ms("rich") == 420 + 80
    assert MO.dock_measure_ms("purposeful") == round(420 * 0.6) + 80
    assert MO.dock_measure_ms("off") == 0
    home = (ROOT / "project_opener" / "qml" / "pages" / "HomePage.qml").read_text(encoding="utf-8")
    assert "interval: Math.max(1, app.ui.dockMeasureMs)" in home and "interval: 1400" not in home


def test_frame_stats_follow_the_guard():
    t0 = 100.0
    stamps = [t0 + i * 0.016 for i in range(1, 30)] + [t0 + 0.6]       # the last is past a 500 ms window
    r = B.frame_stats(t0, stamps, 500)
    assert r["frames"] == 29 and abs(r["mean_ms"] - 16.0) < 1.0 and not r["slow"]   # the window end clips the gap
    # a 200 ms frame inside the grow: slow
    r = B.frame_stats(t0, [t0 + 0.016, t0 + 0.032, t0 + 0.232, t0 + 0.248], 500)
    assert r["worst1_ms"] == 200.0 and r["slow"] and r["first_ms"] == 16.0
    # a 200 ms first frame (the click's work and the launcher starting Office), then a smooth grow: the
    # response time is reported, the guard does not count it (docs/DESIGN.md, "Motion levels")
    r = B.frame_stats(t0, [t0 + 0.2 + i * 0.016 for i in range(0, 18)], 500)
    assert r["first_ms"] == 200.0 and r["longest_ms"] == 200.0 and r["worst1_ms"] < 17 and not r["slow"]
    assert B.frame_stats(t0, [], 500)["frames"] == 0


def test_seed_never_imports_the_users_1x_projects(tmp_path, monkeypatch):
    """A fresh store imports 1.x's projects.json from %APPDATA%/ProjectOpener; the bench's must not (they are
    the user's, and their health checks reach the user's shares)."""
    from project_opener import constants as C
    from project_opener.core.store import WorkspaceStore
    appdata = tmp_path / "appdata"
    (appdata / "ProjectOpener").mkdir(parents=True)
    (appdata / "ProjectOpener" / "projects.json").write_text(
        json.dumps({"Real job": {"files": ["Z:/P1/a.pdf"]}}), encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    # the production lookup (conftest points it at an empty folder for every test)
    monkeypatch.setattr(C, "legacy_v1_dir", lambda: Path(os.environ["APPDATA"]) / "ProjectOpener")
    probe = tmp_path / "probe"
    probe.mkdir()
    assert [p.name for p in WorkspaceStore(probe).projects] == ["Real job"]     # the import this guards against
    data = tmp_path / "work" / "data"
    data.mkdir(parents=True)
    B.seed(data)
    assert os.environ["APPDATA"] == str(appdata)                                # put back
    assert sorted(p.name for p in WorkspaceStore(data).projects) == ["ANTEO Isometrics", "As-built isometrics"]


def test_gui_stalls_and_summary():
    assert B.gui_stalls([0.0, 0.005, 0.010, 0.210, 0.215]) == {"gui_longest_ms": 200.0, "gui_over_50ms": 1}
    runs = [{"frames": 20, "mean_ms": 18.0, "worst1_ms": 60.0, "slow": False, "gui_longest_ms": 40.0}] * 3
    s = B.level_summary(runs)
    assert s["runs"] == 3 and s["mean_ms"] == 18.0 and s["slow_runs"] == 0 and s["gui_longest_ms_max"] == 40.0


def test_guard_verdicts():
    fast = [{"mean_ms": 18.0, "worst1_ms": 60.0}] * 6
    slow = [{"mean_ms": 18.0, "worst1_ms": 200.0}] * 6
    assert B.guard_verdict("rich", fast) == ""
    assert B.guard_verdict("rich", slow) == "purposeful after opening 2"
    dock = {"rich": {"guard": ""}}
    assert B.overall_verdict("rich", dock) == "Rich motion holds on this PC."
    dock = {"rich": {"guard": "purposeful after opening 2"}, "purposeful": {"guard": ""}}
    assert "reduce Rich to Purposeful" in B.overall_verdict("rich", dock)
    assert "remote" in B.overall_verdict("off", {})


def test_output_goes_next_to_the_exe_else_temp(tmp_path, monkeypatch):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    p = B.default_out(exe_dir=exe_dir)
    assert p.parent == exe_dir and p.name.startswith("bench-") and p.suffix == ".json"
    monkeypatch.setattr(B, "_writable", lambda folder: False)
    import tempfile
    assert B.default_out(exe_dir=exe_dir).parent == Path(tempfile.gettempdir())
    monkeypatch.undo()
    assert B.resolve_out(str(tmp_path / "r.json")) == tmp_path / "r.json"
    assert B.resolve_out(str(tmp_path / "folder")).parent == tmp_path / "folder"


def test_summary_reads_plainly():
    run = {"frames": 25, "mean_ms": 19.0, "worst1_ms": 70.0, "longest_ms": 70.0, "slow": False, "gui_longest_ms": 50.0}
    dock = {lvl: {"runs": [run] * 2, "summary": B.level_summary([run] * 2), "guard": ""} for lvl in B.LEVELS}
    res = {"version": "4.0.0", "runs": 2,
           "machine": {"computer": "PC-OLD", "cpu": "Intel Core i3", "cores": 4, "ram_gb": 8.0, "windows": "Windows 10",
                       "adapter": "Intel HD Graphics 4000",
                       "screen": {"width": 1366, "height": 768, "scale_pct": 100, "refresh_hz": 60}},
           "app": {"backend": "rhi", "motion_auto": "purposeful", "motion_reason": "chosen for a 1366 x 768 screen",
                   "motion_saved": "purposeful"},
           "start": {"first_frame_s": 3.2, "window_to_frame_ms": 450},
           "idle": {"private_mb": 150.0, "working_set_mb": 160.0, "cpu_pct_one_core": 0.4},
           "dock": dock, "verdict": B.overall_verdict("purposeful", dock), "qt_warnings": []}
    text = "\n".join(B.summary_lines(res))
    assert "Intel HD Graphics 4000" in text and "1366 x 768" in text
    assert "start in Purposeful motion" in text and "Purposeful motion holds on this PC." in text
    assert "First frame 3.2 s" in text and "150 MB" in text


@pytest.mark.timeout(240)
def test_bench_cli_end_to_end(tmp_path):
    """A real run, offscreen and short: rc 0, the JSON and the .txt, no throwaway folder left, the user's data
    folder untouched."""
    user = tmp_path / "user-data"
    user.mkdir()
    (user / "settings.json").write_text(json.dumps({"motion": "purposeful"}), encoding="utf-8")
    before = sorted(p.name for p in user.rglob("*"))
    temp = tmp_path / "temp"
    temp.mkdir()
    out = tmp_path / "out" / "bench.json"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PO_DATA_DIR": str(user), "TEMP": str(temp), "TMP": str(temp),
           "QSG_USE_SIMPLE_ANIMATION_DRIVER": "1"}
    if sys.platform == "win32":
        env.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"))
    proc = subprocess.run([sys.executable, "-m", "project_opener", "--bench", "--bench-runs", "1", "--out", str(out)],
                          cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=220)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    res = json.loads(out.read_text(encoding="utf-8"))
    for key in ("version", "machine", "app", "start", "idle", "dock", "verdict", "summary"):
        assert key in res, key
    assert set(res["dock"]) == {"rich", "purposeful", "off"}
    assert all(len(res["dock"][lvl]["runs"]) == 1 for lvl in res["dock"])
    assert res["app"]["backend"] in ("rhi", "software") and res["app"]["motion_auto"] in MO.LEVELS
    assert res["app"]["motion_saved"] == "purposeful"            # read from the user's settings, never written
    assert res["idle"]["private_mb"] > 0
    assert out.with_suffix(".txt").read_text(encoding="utf-8").startswith("Project Opener ")
    assert "Verdict:" in proc.stdout and str(out) in proc.stdout
    assert sorted(p.name for p in user.rglob("*")) == before
    # the throwaway folder is gone; only the QML cache folder may stay (Qt maps its files until the process ends;
    # the next run empties it)
    assert not [p for p in temp.iterdir() if p.name.startswith("po-bench-") and p.name != B.QML_CACHE_DIR]
