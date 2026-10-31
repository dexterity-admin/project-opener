"""Thin Windows helpers (DPAPI, mapped drives, startup entry, dark title bar).

Every function degrades gracefully off Windows so the test-suite runs on any
platform.  Nothing here imports Qt.
"""
from __future__ import annotations

import base64
import ctypes
import logging
import os
import string
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger(__name__)
IS_WIN = sys.platform == "win32"


# ----------------------------------------------------------------- DPAPI
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
    size = int(blob.cbData)
    buf = ctypes.create_string_buffer(size)
    ctypes.memmove(buf, blob.pbData, size)
    ctypes.windll.kernel32.LocalFree(blob.pbData)  # type: ignore[attr-defined]
    return buf.raw


def protect(text: str) -> str:
    raw = text.encode("utf-8")
    if not IS_WIN:
        return "b64:" + base64.b64encode(raw).decode("ascii")
    inp = _DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_byte)))
    out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inp), "ProjectOpener", None, None, None, 0, ctypes.byref(out)):  # type: ignore[attr-defined]
        raise OSError("CryptProtectData failed")
    return "dpapi:" + base64.b64encode(_blob_to_bytes(out)).decode("ascii")


def unprotect(token: str) -> str:
    if token.startswith("b64:"):
        return base64.b64decode(token[4:]).decode("utf-8")
    if not token.startswith("dpapi:"):
        return token
    if not IS_WIN:
        raise OSError("DPAPI blobs can only be decrypted on Windows")
    raw = base64.b64decode(token[6:])
    inp = _DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_byte)))
    out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):  # type: ignore[attr-defined]
        raise OSError("CryptUnprotectData failed")
    return _blob_to_bytes(out).decode("utf-8")


# ---------------------------------------------------------- mapped drives
def mapped_drives() -> dict[str, str]:
    """Return {"Z:": "\\\\server\\share"} for every mapped network drive."""
    result: dict[str, str] = {}
    if not IS_WIN:
        return result
    mpr = ctypes.windll.mpr  # type: ignore[attr-defined]
    for letter in string.ascii_uppercase:
        drive = f"{letter}:"
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        rc = mpr.WNetGetConnectionW(drive, buf, ctypes.byref(size))
        if rc == 0 and buf.value:
            result[drive] = buf.value
    return result


def drive_type(path: str) -> str:
    """'network' | 'fixed' | 'removable' | 'cdrom' | 'unknown'."""
    if not IS_WIN:
        return "unknown"
    root = os.path.splitdrive(path)[0]
    if not root:
        return "unknown"
    if root.startswith("\\\\"):
        return "network"
    t = ctypes.windll.kernel32.GetDriveTypeW(root + "\\")  # type: ignore[attr-defined]
    return {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}.get(t, "unknown")


def host_reachable(host: str, timeout: float = 0.8) -> bool:
    """Quick SMB port probe so the health worker can tell 'server down' from 'file missing'."""
    import socket
    try:
        with socket.create_connection((host, 445), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------- startup entry
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "DexterityProjectOpener"


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimised'
    return f'"{sys.executable}" -m project_opener --minimised'


def set_run_at_startup(enabled: bool) -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        log.warning("startup registry update failed: %s", exc)
        return False


def is_run_at_startup() -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


# ----------------------------------------------------------- shell helpers
def reveal_in_explorer(path: str) -> None:
    p = Path(path)
    if IS_WIN:
        if p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            subprocess.Popen(["explorer", str(p)])
    else:  # pragma: no cover
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])


def open_terminal_at(path: str) -> None:
    p = Path(path)
    folder = p if p.is_dir() else p.parent
    if IS_WIN:
        wt = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "wt.exe"
        if wt.exists():
            subprocess.Popen([str(wt), "-d", str(folder)])
        else:
            subprocess.Popen(["cmd", "/K", f"cd /d \"{folder}\""], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:  # pragma: no cover
        subprocess.Popen(["x-terminal-emulator"], cwd=str(folder))


def apply_dark_title_bar(hwnd: int, dark: bool) -> None:
    """Ask DWM for a dark (or light) caption; Windows 10 1809+ / Windows 11."""
    if not IS_WIN or not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20; 19 before 20H1)
            if dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        # Windows 11: rounded corners + Mica backdrop are harmless no-ops on 10.
        corner = ctypes.c_int(2)  # DWMWCP_ROUND
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception as exc:  # pragma: no cover
        log.debug("DWM attribute failed: %s", exc)


def set_app_user_model_id(app_id: str) -> None:
    """Make the taskbar group under our own icon instead of python.exe's."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass
