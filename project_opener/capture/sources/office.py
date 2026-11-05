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

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

EXCEL_EXT = (".xlsx", ".xlsm", ".xls", ".xlsb", ".csv")
WORD_EXT = (".docx", ".docm", ".doc", ".rtf")


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    raise NotImplementedError("office.identify")


def office_installed() -> dict[str, bool]:
    """{"excel": bool, "word": bool} from the registered ProgIDs."""
    raise NotImplementedError("office.office_installed")


def open_document(path: str) -> bool:
    """Open an Excel/Word file in a visible instance through COM; False to let the caller fall back
    to the association.  Must be called on a thread that has CoInitialize'd."""
    raise NotImplementedError("office.open_document")
