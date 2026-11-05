"""Title-only applications: PDF viewers, CAD, LibreOffice, editors with a path in the title.  Owner: builder 2.

``TITLE_PATTERNS`` per process parse the document name out of the title; the name
is matched (exact, case-insensitive) against the activity's items, then Recent.
One candidate -> identified ("title+items" / "title+recent"); several ->
ambiguous with ``candidates``; none -> unidentified.  "Drawing1" style names ->
unsaved.  A full existing path in the title -> identified ("title-path").
"""
from __future__ import annotations

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

# process (lower case) -> (regex with a "name" group, friendly app name, default extension or "")
TITLE_PATTERNS: dict[str, tuple[str, str, str]] = {}


def parse_title(process: str, title: str) -> tuple[str, str] | None:
    """(document name with extension when known, app name) or None."""
    raise NotImplementedError("titles.parse_title")


def recent_targets() -> dict[str, list[str]]:
    """``%APPDATA%\\Microsoft\\Windows\\Recent\\*.lnk`` resolved once per link, re-read on folder mtime change."""
    raise NotImplementedError("titles.recent_targets")


def match_name(doc_name: str, item_paths: list[str], recent: dict[str, list[str]]) -> tuple[str, list[str], str]:
    """(status, candidates, identified_by): status identified | ambiguous | unidentified."""
    raise NotImplementedError("titles.match_name")


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    raise NotImplementedError("titles.identify")
