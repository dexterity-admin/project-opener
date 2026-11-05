"""Explorer verb and Send to writer (builder 3) against a fake registry and a temp SendTo folder.

Nothing here touches the real registry: every call passes ``reg=FakeRegistry()``.
"""
from project_opener import constants as C
from project_opener.desktop import shellext as S

EXE = r"C:\Users\x\AppData\Local\Programs\Project Opener\ProjectOpener.exe"


def test_verb_written_for_files_and_folders():
    reg = S.FakeRegistry()
    assert S.install_explorer_verb(reg, frozen=True, executable=EXE)
    for key in (rf"Software\Classes\*\shell\{C.EXPLORER_VERB}", rf"Software\Classes\Directory\shell\{C.EXPLORER_VERB}"):
        assert reg.get_value(key, "MUIVerb") == "Add to running activity"
        assert reg.get_value(key, "Icon") == f'"{EXE}",0'
        assert reg.get_value(key + r"\command", "") == f'"{EXE}" --add "%1"'
    assert S.explorer_verb_installed(reg)


def test_verb_removed_completely_and_idempotent():
    reg = S.FakeRegistry()
    reg.set_value(r"Software\Classes\*\shell\SomethingElse\command", "", "x")
    S.install_explorer_verb(reg, frozen=True, executable=EXE)
    S.install_explorer_verb(reg, frozen=True, executable=EXE)
    assert S.remove_explorer_verb(reg)
    assert S.remove_explorer_verb(reg)
    assert not S.explorer_verb_installed(reg)
    assert not any(C.EXPLORER_VERB.lower() in k for k in reg.keys)
    assert reg.get_value(r"Software\Classes\*\shell\SomethingElse\command", "") == "x"   # others untouched


def test_half_installed_is_not_installed():
    reg = S.FakeRegistry()
    S.install_explorer_verb(reg, frozen=True, executable=EXE)
    reg.delete_tree(rf"Software\Classes\Directory\shell\{C.EXPLORER_VERB}")
    assert not S.explorer_verb_installed(reg)


def test_source_command_line_runs_run_py_with_v4():
    cmd = S.verb_command(frozen=False, executable=r"D:\Py\Project_opener_2\.venv\Scripts\python.exe")
    assert cmd.startswith(r'"D:\Py\Project_opener_2\.venv\Scripts\pythonw.exe" ')
    assert "run.py" in cmd and cmd.endswith(' --v4 --add "%1"')


def test_sendto_with_fake_writer(tmp_path):
    calls = []
    folder = tmp_path / "SendTo"

    def writer(lnk, target, args, workdir, icon):
        calls.append((lnk, target, args, workdir, icon))
        lnk.write_bytes(b"lnk")

    assert S.install_sendto(folder, writer, frozen=True, executable=EXE)
    lnk, target, args, workdir, icon = calls[0]
    assert lnk == folder / C.SENDTO_NAME and target == EXE and args == "--sendto"
    assert workdir.endswith("Project Opener") and icon == f"{EXE},0"
    assert S.sendto_installed(folder)
    assert S.remove_sendto(folder) and not S.sendto_installed(folder)
    assert S.remove_sendto(folder)


def test_sendto_writer_failure_is_reported(tmp_path):
    def broken(*_a):
        raise RuntimeError("COM said no")
    assert S.install_sendto(tmp_path, broken, frozen=True, executable=EXE) is False


def test_set_entries_both_ways(tmp_path):
    reg = S.FakeRegistry()

    def writer(lnk, *_a):
        lnk.write_bytes(b"lnk")

    assert S.set_entries(True, True, reg, tmp_path, writer, frozen=True, executable=EXE) == (True, True)
    assert S.set_entries(True, False, reg, tmp_path, writer, frozen=True, executable=EXE) == (True, False)
    assert S.set_entries(False, False, reg, tmp_path, writer, frozen=True, executable=EXE) == (False, False)
    assert not any(C.EXPLORER_VERB.lower() in k for k in reg.keys)


def test_real_shortcut_writer_in_temp(tmp_path):
    """The WScript.Shell writer makes a real .lnk (in pytest's temp folder, not in SendTo)."""
    assert S.install_sendto(tmp_path, frozen=True, executable=EXE)
    assert (tmp_path / C.SENDTO_NAME).stat().st_size > 0
