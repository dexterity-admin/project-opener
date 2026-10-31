import sys

import pytest

from project_opener.core import models as M
from project_opener.core.launcher import Launcher
from project_opener.core.pathvars import PathResolver, normalise_var_name


def test_normalise_var_name():
    assert normalise_var_name("server root") == "{SERVER_ROOT}"
    assert normalise_var_name("{Z_DRIVE}") == "{Z_DRIVE}"
    assert normalise_var_name("") == ""


def test_resolve_variables():
    r = PathResolver({"{SERVER_ROOT}": r"\\192.168.0.200\Project"}, drive_map={})
    res = r.resolve(r"{SERVER_ROOT}\P12513\iso.pdf")
    assert res.used_variable
    assert res.resolved.startswith(r"\\192.168.0.200\Project")
    assert res.resolved.endswith(r"P12513\iso.pdf")


def test_unresolved_variable_reported():
    r = PathResolver({}, drive_map={})
    res = r.resolve(r"{NOPE}\x")
    assert res.unresolved == ["{NOPE}"]


def test_portable_and_localise_roundtrip():
    r = PathResolver({}, drive_map={"Z:": r"\\192.168.0.200\Project"})
    unc = r.portable(r"Z:\P12513\a.pdf")
    assert unc == r"\\192.168.0.200\Project\P12513\a.pdf"
    assert r.localise(unc) == r"Z:\P12513\a.pdf"
    assert r.portable("https://x.y") == "https://x.y"


@pytest.mark.skipif(sys.platform != "win32", reason="drive remap is Windows-only")
def test_remap_unmapped_drive_letter_to_unc():
    r = PathResolver({"{Q_DRIVE}": r"\\server\share"}, drive_map={})
    res = r.resolve(r"Q:\folder\file.txt")
    assert res.remapped_drive
    assert res.resolved == r"\\server\share\folder\file.txt"


def test_launcher_dry_run_reports(tmp_path):
    real = tmp_path / "exists.txt"
    real.write_text("x", encoding="utf-8")
    items = [
        M.Item(path=str(real), kind="file"),
        M.Item(path=str(tmp_path / "missing.txt"), kind="file"),
        M.Item(path="https://example.com", kind="url"),
        M.Item(path="{UNDEFINED}/x", kind="file"),
        M.Item(path="", kind="file"),
    ]
    rep = Launcher(PathResolver({}, drive_map={}), delay_ms=0, dry_run=True).launch(items)
    statuses = [r.status for r in rep.results]
    assert statuses == ["opened", "missing", "opened", "missing", "skipped"]
    assert "1 missing" in rep.summary() or "2 missing" in rep.summary()
    assert not rep.ok
