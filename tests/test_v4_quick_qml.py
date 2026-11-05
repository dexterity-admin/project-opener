"""The Qt Quick shell loads every page and sheet offscreen with no QML warning, and every page fits the
1040 x 660 minimum window beside the rail (tools/smoke_quick.py --check, in a child process so the QML
engine never shares this process's QApplication)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PO_SMOKE_ROOT"] = str(tmp_path / "smoke")
    env["QML_DISK_CACHE_PATH"] = str(ROOT / "build" / "qmlcache")
    env.pop("PO_DATA_DIR", None)
    return subprocess.run([sys.executable, str(ROOT / "tools" / "smoke_quick.py"), "--check", *extra],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600)


def test_every_page_and_sheet_loads_without_warnings(tmp_path):
    res = _run(tmp_path, "--themes", "dark,light", "--sizes", "1400x860,1040x660")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out[-4000:]
    assert "0 Qt/QML warnings, 0 layout problems" in out, out[-4000:]


def test_stub_empty_states_load_without_warnings(tmp_path):
    """The other builders' models as their stubs give them: every block shows its empty state."""
    res = _run(tmp_path, "--stubs", "--themes", "dark", "--sizes", "1040x660", "--no-sheets")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out[-4000:]
    assert "0 Qt/QML warnings, 0 layout problems" in out, out[-4000:]
