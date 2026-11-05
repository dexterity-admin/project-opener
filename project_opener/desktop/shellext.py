"""Explorer entries, per user, no admin.  Owner: builder 3 (DESKTOP).

* Verb "Add to running activity" on files and folders::

    HKCU\\Software\\Classes\\*\\shell\\<EXPLORER_VERB>                 (MUIVerb, Icon)
    HKCU\\Software\\Classes\\Directory\\shell\\<EXPLORER_VERB>
        \\command  = "<exe>" --add "%1"

  A "%1" verb on a multi-selection starts one process per file, so the
  running instance batches ``add`` commands that arrive within 500 ms into
  one chooser / one toast (``ipc.InstanceServer``).  Send to is the many-files route.
* Send to: ``%APPDATA%\\Microsoft\\Windows\\SendTo\\<SENDTO_NAME>`` pointing at
  ``"<exe>" --sendto`` (Windows appends every selected path).

The installer (installer/ProjectOpener.iss) writes the same keys; the app can
add or remove them from Settings > Snapshot (``set_entries``).  Source runs (not
frozen) call ``pythonw "<repo>\\run.py"``.

Every function takes an optional ``reg`` (a ``Registry``) and ``sendto_dir``, so the tests run
against ``FakeRegistry`` and a temp folder; the defaults are the real HKCU and the user's SendTo.
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from project_opener import constants as C

log = logging.getLogger(__name__)

VERB_TEXT = "Add to running activity"
VERB_PARENTS = (r"Software\Classes\*\shell", r"Software\Classes\Directory\shell")


def verb_keys() -> list[str]:
    """The two HKCU-relative keys the verb lives under."""
    return [f"{parent}\\{C.EXPLORER_VERB}" for parent in VERB_PARENTS]


# ---------------------------------------------------------------- registry
class Registry(Protocol):
    """The four operations the Explorer verb needs, relative to HKCU."""

    def set_value(self, key: str, name: str, value: str) -> None: ...
    def get_value(self, key: str, name: str) -> str | None: ...
    def delete_tree(self, key: str) -> None: ...
    def key_exists(self, key: str) -> bool: ...


class WinRegistry:
    """HKEY_CURRENT_USER through ``winreg`` (only ever HKCU)."""

    def __init__(self) -> None:
        import winreg
        self._w = winreg
        self._root = winreg.HKEY_CURRENT_USER

    def set_value(self, key: str, name: str, value: str) -> None:
        with self._w.CreateKeyEx(self._root, key, 0, self._w.KEY_SET_VALUE) as k:
            self._w.SetValueEx(k, name, 0, self._w.REG_SZ, value)

    def get_value(self, key: str, name: str) -> str | None:
        try:
            with self._w.OpenKey(self._root, key, 0, self._w.KEY_READ) as k:
                return str(self._w.QueryValueEx(k, name)[0])
        except OSError:
            return None

    def key_exists(self, key: str) -> bool:
        try:
            with self._w.OpenKey(self._root, key, 0, self._w.KEY_READ):
                return True
        except OSError:
            return False

    def delete_tree(self, key: str) -> None:
        try:
            with self._w.OpenKey(self._root, key, 0, self._w.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        sub = self._w.EnumKey(k, 0)
                    except OSError:
                        break
                    self.delete_tree(f"{key}\\{sub}")
            self._w.DeleteKey(self._root, key)
        except FileNotFoundError:
            pass


class FakeRegistry:
    """In-memory registry for tests: ``{key (lower case): {name: value}}``; key creation makes parents."""

    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}
        self.writes = 0

    @staticmethod
    def _norm(key: str) -> str:
        return key.strip("\\").lower()

    def set_value(self, key: str, name: str, value: str) -> None:
        parts = self._norm(key).split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        self.keys[self._norm(key)][name] = value
        self.writes += 1

    def get_value(self, key: str, name: str) -> str | None:
        return self.keys.get(self._norm(key), {}).get(name)

    def key_exists(self, key: str) -> bool:
        return self._norm(key) in self.keys

    def delete_tree(self, key: str) -> None:
        k = self._norm(key)
        for name in [n for n in self.keys if n == k or n.startswith(k + "\\")]:
            del self.keys[name]


def _registry(reg: Registry | None) -> Registry:
    return reg if reg is not None else WinRegistry()


# ------------------------------------------------------------- the command
def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def launcher_parts(frozen: bool | None = None, executable: str | None = None) -> tuple[str, list[str]]:
    """(program, leading arguments) that start Project Opener 4 from an Explorer entry."""
    frozen = C.is_frozen() if frozen is None else frozen
    exe = executable or sys.executable
    if frozen:
        return exe, []
    pyw = Path(exe).with_name("pythonw.exe")
    program = str(pyw if pyw.exists() or executable else Path(exe))
    return program, [str(_source_root() / "run.py"), "--v4"]


def _quote(arg: str) -> str:
    return f'"{arg}"' if (" " in arg or not arg) and not arg.startswith('"') else arg


def command_line(frozen: bool | None = None, executable: str | None = None) -> str:
    """The exe (frozen) or ``pythonw "<repo>\\run.py" --v4`` (source) that the entries call."""
    program, args = launcher_parts(frozen, executable)
    return " ".join([f'"{program}"', *(_quote(a) for a in args)])


def verb_command(frozen: bool | None = None, executable: str | None = None) -> str:
    return f'{command_line(frozen, executable)} --add "%1"'


def icon_value(frozen: bool | None = None, executable: str | None = None) -> str:
    frozen = C.is_frozen() if frozen is None else frozen
    if frozen:
        return f'"{executable or sys.executable}",0'
    return str(C.resource_path("icon", "app.ico"))


# -------------------------------------------------------------- the verb
def install_explorer_verb(reg: Registry | None = None, frozen: bool | None = None,
                          executable: str | None = None) -> bool:
    try:
        r = _registry(reg)
        for key in verb_keys():
            r.set_value(key, "MUIVerb", VERB_TEXT)
            r.set_value(key, "Icon", icon_value(frozen, executable))
            r.set_value(f"{key}\\command", "", verb_command(frozen, executable))
        return True
    except OSError:
        log.exception("could not write the Explorer verb")
        return False


def remove_explorer_verb(reg: Registry | None = None) -> bool:
    try:
        r = _registry(reg)
        for key in verb_keys():
            r.delete_tree(key)
        return True
    except OSError:
        log.exception("could not remove the Explorer verb")
        return False


def explorer_verb_installed(reg: Registry | None = None) -> bool:
    try:
        r = _registry(reg)
        return all(r.get_value(f"{key}\\command", "") for key in verb_keys())
    except OSError:
        return False


# ---------------------------------------------------------------- Send to
def sendto_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo"


ShortcutWriter = Callable[[Path, str, str, str, str], None]   # lnk, target, arguments, workdir, icon


def write_shortcut(lnk: Path, target: str, arguments: str, workdir: str, icon: str) -> None:
    """A .lnk through IShellLinkW + IPersistFile (pywin32), no scripting host."""
    import pythoncom
    from win32com.shell import shell
    pythoncom.CoInitialize()
    try:
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                          shell.IID_IShellLink)
        link.SetPath(target)
        link.SetArguments(arguments)
        link.SetWorkingDirectory(workdir)
        link.SetDescription("Add the selected files to the running activity in Project Opener")
        if icon:
            path, _, index = icon.rpartition(",")
            if path and index.strip().lstrip("-").isdigit():
                link.SetIconLocation(path, int(index))
            else:
                link.SetIconLocation(icon, 0)
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(lnk), True)
        del link
    finally:
        pythoncom.CoUninitialize()


def install_sendto(folder: Path | None = None, writer: ShortcutWriter | None = None,
                   frozen: bool | None = None, executable: str | None = None) -> bool:
    folder = folder or sendto_dir()
    program, args = launcher_parts(frozen, executable)
    arguments = " ".join([*(_quote(a) for a in args), "--sendto"])
    icon = icon_value(frozen, executable).replace('"', "")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (writer or write_shortcut)(folder / C.SENDTO_NAME, program, arguments, str(Path(program).parent), icon)
        return True
    except Exception:  # noqa: BLE001  (COM errors are not OSError)
        log.exception("could not write the Send to shortcut")
        return False


def remove_sendto(folder: Path | None = None) -> bool:
    try:
        (folder or sendto_dir()).joinpath(C.SENDTO_NAME).unlink(missing_ok=True)
        return True
    except OSError:
        log.exception("could not remove the Send to shortcut")
        return False


def sendto_installed(folder: Path | None = None) -> bool:
    return (folder or sendto_dir()).joinpath(C.SENDTO_NAME).exists()


# ----------------------------------------------------------------- both
def set_entries(verb: bool, sendto: bool, reg: Registry | None = None, folder: Path | None = None,
                writer: ShortcutWriter | None = None, frozen: bool | None = None,
                executable: str | None = None) -> tuple[bool, bool]:
    """Bring both entries to the wanted state (Settings.explorer_verb / sendto_entry).

    Returns what is installed afterwards: (verb installed, Send to installed).
    """
    if verb:
        install_explorer_verb(reg, frozen, executable)
    else:
        remove_explorer_verb(reg)
    if sendto:
        install_sendto(folder, writer, frozen, executable)
    else:
        remove_sendto(folder)
    return explorer_verb_installed(reg), sendto_installed(folder)
