"""Excel and Word, per window and per instance.  Owner: builder 2.

Identify through AccessibleObjectFromWindow on the EXCEL7 / _WwG child with
OBJID_NATIVEOM (the ROT may hand back a hidden orphan instance; spike section 2).
Open through COM ``Workbooks.Open`` / ``Documents.Open`` (the shell association
sends share files into Protected View and can take minutes, or never show Word).
Release every COM reference before returning; never keep an Application alive
across passes.  ``open_document`` is also registered with ``core.launcher`` as the
opener for Office extensions when ``Settings.open_office_via_com`` is on.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

log = logging.getLogger(__name__)

EXCEL_EXT = (".xlsx", ".xlsm", ".xls", ".xlsb", ".csv")
WORD_EXT = (".docx", ".docm", ".doc", ".rtf")
# Extensions the launcher hands to ``open_document`` (csv/rtf keep their own association).
OPENER_EXT = (".xlsx", ".xlsm", ".xls", ".xlsb", ".docx", ".docm", ".doc")

EXCEL_CLASSES = frozenset({"XLMAIN", "XLMAINPV"})
WORD_CLASSES = frozenset({"OpusApp"})
DOC_CHILD = {"XLMAIN": "EXCEL7", "XLMAINPV": "EXCEL7", "OpusApp": "_WwG"}

OBJID_NATIVEOM = 0xFFFFFFF0
RPC_BUSY = (-2147418111, -2147417846)          # RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER


@dataclass
class OfficeDoc:
    full_name: str
    has_path: bool
    saved: bool = True
    protected: bool = False


class OfficeBusy(Exception):
    """The instance refused the call (cell edit mode, a modal dialog): try again next pass."""


DocForWindowFn = Callable[[WindowInfo], OfficeDoc | None]


# ------------------------------------------------------------------ COM plumbing
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


_IID_IDISPATCH = _GUID(0x00020400, 0, 0, (ctypes.c_ubyte * 8)(0xC0, 0, 0, 0, 0, 0, 0, 0x46))


def _release_raw(ptr: int) -> None:
    """IUnknown::Release on a raw interface pointer (vtable slot 2)."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    release(ptr)


def native_om(child_hwnd: int):
    """The Office object model's Window behind an EXCEL7/_WwG child, as a win32com Dispatch; None when refused.

    ``pythoncom.ObjectFromAddress`` takes its own reference, so the one AccessibleObjectFromWindow
    handed us is released here: nothing leaks into the user's Office process (a leaked reference
    keeps an Excel the user closed alive in the background)."""
    import pythoncom
    import win32com.client
    ptr = ctypes.c_void_p()
    hr = ctypes.oledll.oleacc.AccessibleObjectFromWindow  # raises OSError on a failing HRESULT
    try:
        hr(wt.HWND(child_hwnd), wt.DWORD(OBJID_NATIVEOM), ctypes.byref(_IID_IDISPATCH), ctypes.byref(ptr))
    except OSError:
        return None
    if not ptr.value:
        return None
    try:
        disp = pythoncom.ObjectFromAddress(ptr.value, pythoncom.IID_IDispatch)
    finally:
        _release_raw(ptr.value)
    return win32com.client.Dispatch(disp)


def _is_busy(exc: Exception) -> bool:
    code = getattr(exc, "hresult", None)
    if code is None and getattr(exc, "args", None):
        code = exc.args[0]
    return code in RPC_BUSY


def doc_for_window(w: WindowInfo) -> OfficeDoc | None:
    """The workbook / document shown in this top-level window, read through that window's own object."""
    from project_opener.capture import win32
    child_cls = DOC_CHILD.get(w.window_class)
    if not child_cls:
        return None
    child = win32.find_child(w.hwnd, child_cls)
    if not child:
        return None
    win = doc = None
    try:
        win = native_om(child)
        if win is None:
            return None
        doc = win.Parent if w.window_class in EXCEL_CLASSES else win.Document
        full = str(doc.FullName or "")
        path = str(doc.Path or "")
        saved = bool(doc.Saved)
        return OfficeDoc(full_name=full, has_path=bool(path), saved=saved,
                         protected=w.window_class == "XLMAINPV" or "[Protected View]" in w.title)
    except Exception as exc:  # noqa: BLE001
        if _is_busy(exc):
            raise OfficeBusy(str(exc)) from exc
        log.debug("office object model refused for %s: %s", w.title, exc)
        return None
    finally:
        del doc, win


# ------------------------------------------------------------------ the source
class OfficeSource:
    name = "office-com"

    def __init__(self, doc_for_window_fn: DocForWindowFn | None = None):
        self._doc_for_window = doc_for_window_fn or doc_for_window
        self.retry: set[int] = set()          # hwnds whose instance was busy: do not cache, ask again

    def identify(self, windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
        self.retry = set()
        out: dict[int, M.SnapshotEntry] = {}
        for w in windows:
            if w.window_class not in EXCEL_CLASSES and w.window_class not in WORD_CLASSES:
                continue
            app = "Excel" if w.window_class in EXCEL_CLASSES else "Word"
            try:
                doc = self._doc_for_window(w)
            except OfficeBusy:
                self.retry.add(w.hwnd)
                continue
            if doc is None or not doc.full_name:
                continue
            name = os.path.basename(doc.full_name.rstrip("\\/")) or doc.full_name
            note = "Protected View" if doc.protected else ""
            if doc.has_path:
                out[w.hwnd] = M.SnapshotEntry(key="", status="identified", kind="file", path=doc.full_name, app=app,
                                              identified_by="office-com", doc_name=name, note=note)
            else:
                out[w.hwnd] = M.SnapshotEntry(key="", status="unsaved", kind="file", app=app,
                                              identified_by="office-com", doc_name=name,
                                              note="unsaved - cannot be restored")
        return out


_default = OfficeSource()


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    return _default.identify(windows, ctx)


# ------------------------------------------------------------------ install / open
def office_installed() -> dict[str, bool]:
    """{"excel": bool, "word": bool} from the registered ProgIDs."""
    import winreg
    out = {}
    for key, prog in (("excel", "Excel.Application"), ("word", "Word.Application")):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog + "\\CLSID"):
                out[key] = True
        except OSError:
            out[key] = False
    return out


def app_for_path(path: str) -> str:
    """"excel" | "word" | "" by extension."""
    low = path.lower()
    if low.endswith(EXCEL_EXT):
        return "excel"
    if low.endswith(WORD_EXT):
        return "word"
    return ""


def _visible_application(kind: str):
    """The Application object of a visible Excel/Word window, through that window (never the ROT)."""
    from project_opener.capture import win32
    classes = ("XLMAIN",) if kind == "excel" else ("OpusApp",)
    for w in win32.enumerate_windows():
        if w.window_class not in classes:
            continue
        child = win32.find_child(w.hwnd, DOC_CHILD[w.window_class])
        if not child:
            continue
        try:
            win = native_om(child)
            if win is not None:
                app = win.Application
                del win
                return app
        except Exception:  # noqa: BLE001 - busy or refusing: try the next window
            continue
    return None


def open_document(path: str) -> bool:
    """Open an Excel/Word file in a visible instance through COM; False to let the caller fall back
    to the association.  Must be called on a thread that has CoInitialize'd."""
    kind = app_for_path(path)
    if not kind or not os.path.exists(path):
        return False
    if not office_installed().get(kind):
        return False
    import win32com.client
    app = doc = None
    try:
        app = _visible_application(kind)
        if app is None:
            app = win32com.client.DispatchEx("Excel.Application" if kind == "excel" else "Word.Application")
            app.Visible = True
            if kind == "excel":
                app.UserControl = True       # stays open for the user when our references go
        if kind == "excel":
            doc = app.Workbooks.Open(path)
        else:
            doc = app.Documents.Open(path)
            try:
                doc.Activate()
            except Exception:  # noqa: BLE001
                pass
        return True
    except Exception as exc:  # noqa: BLE001
        log.info("COM open failed for %s: %s", path, exc)
        return False
    finally:
        del doc, app


def open_document_any_thread(path: str) -> bool:
    """``open_document`` for the launcher's pool threads: CoInitialize / CoUninitialize around it."""
    import pythoncom
    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        initialised = True
    except pythoncom.com_error:          # already initialised in another model on this thread
        initialised = False
    try:
        return open_document(path)
    finally:
        if initialised:
            pythoncom.CoUninitialize()
