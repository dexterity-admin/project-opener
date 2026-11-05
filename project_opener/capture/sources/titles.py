"""Title-only applications: PDF viewers, CAD, LibreOffice, editors with a path in the title.  Owner: builder 2.

``TITLE_PATTERNS`` per process parse the document name out of the title; the name
is matched (exact, case-insensitive) against the activity's items, then Recent.
One candidate -> identified ("title+items" / "title+recent"); several ->
ambiguous with ``candidates``; none -> unidentified (with the document name, so
the list says "needs a path").  "Drawing1" style names with no match -> unsaved.
A full existing path in the title -> identified ("title-path").

Verified on the spike PC: PDF-XChange Editor (title drops ".pdf"), Excel/Word titles,
LibreOffice (pattern checked against the observed title).  Navisworks, MicroStation,
AutoCAD, Acrobat, Foxit and SumatraPDF patterns are from their documented title formats
and unverified on a live window.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

log = logging.getLogger(__name__)

# process (lower case) -> (regexes with a "name" group, friendly app name, default extension or "")
TITLE_PATTERNS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "pdfxedit.exe": ((r"^(?P<name>.+?)\*? - PDF-XChange Editor",), "PDF-XChange Editor", ".pdf"),
    "pdfxcview.exe": ((r"^(?P<name>.+?)\*? - PDF-XChange Viewer",), "PDF-XChange Viewer", ".pdf"),
    "acrobat.exe": ((r"^(?P<name>.+?\.pdf)\*? - Adobe Acrobat",), "Acrobat", ".pdf"),
    "acrord32.exe": ((r"^(?P<name>.+?\.pdf)\*? - Adobe Acrobat Reader",), "Acrobat Reader", ".pdf"),
    "foxitpdfreader.exe": ((r"^(?P<name>.+?)\*? - Foxit PDF Reader",), "Foxit PDF Reader", ".pdf"),
    "foxitpdfeditor.exe": ((r"^(?P<name>.+?)\*? - Foxit PDF Editor",), "Foxit PDF Editor", ".pdf"),
    "sumatrapdf.exe": ((r"^(?P<name>.+?) - SumatraPDF",), "SumatraPDF", ".pdf"),
    "roamer.exe": ((r"^(?P<name>.+?\.(?:nwd|nwf|nwc))\*? - Autodesk Navisworks",
                    r"Autodesk Navisworks[^-]* - (?P<name>.+?\.(?:nwd|nwf|nwc))"), "Navisworks", ""),
    "navisworksfreedom.exe": ((r"^(?P<name>.+?\.(?:nwd|nwf|nwc)) - Autodesk Navisworks",), "Navisworks Freedom", ""),
    "microstation.exe": ((r"^(?P<name>.+?\.(?:dgn|dwg|i01|dxf))(?: \[.*?\])?.* - MicroStation",), "MicroStation", ""),
    "ustation.exe": ((r"^(?P<name>.+?\.(?:dgn|dwg|i01|dxf))(?: \[.*?\])?.* - MicroStation",), "MicroStation", ""),
    "powerdraft.exe": ((r"^(?P<name>.+?\.(?:dgn|dwg|i01|dxf))(?: \[.*?\])?.* - (?:MicroStation|PowerDraft)",),
                       "PowerDraft", ""),
    "acad.exe": ((r"\[(?P<name>[^\[\]]+?\.dwg)\]", r"^(?P<name>.+?\.dwg)\*? - Autodesk AutoCAD",
                  r"Autodesk AutoCAD[^-]* - (?P<name>.+?\.dwg)"), "AutoCAD", ".dwg"),
    "soffice.bin": ((r"^(?P<name>.+?)(?: \(read-only\))? [-\u2013] LibreOffice",), "LibreOffice", ""),
    "notepad.exe": ((r"^\*?(?P<name>.+?) - Notepad$",), "Notepad", ""),
    "notepad++.exe": ((r"^\*?(?P<name>.+?) - Notepad\+\+",), "Notepad++", ""),
    "excel.exe": ((r"^(?P<name>.+?)\s+\[Protected View\]\s+-\s+Excel$", r"^(?P<name>.+?)(?:\s+\[[^\]]+\])?\s+-\s+Excel$"),
                  "Excel", ""),
    "winword.exe": ((r"^(?P<name>.+?)\s+\[Protected View\]\s+-\s+Word$",
                     r"^(?P<name>.+?)(?:\s+\[[^\]]+\])?\s+-\s+Word$"), "Word", ""),
}
# Processes whose titles are web pages or chat: never matched against files.
SKIP_PROCS = frozenset({"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "opera.exe", "firefox.exe",
                        "explorer.exe"})
# Tried, in this order, when a name carries no known extension (Office hides it when Explorer does).
KNOWN_EXT = (".pdf", ".xlsx", ".xlsm", ".xls", ".docx", ".doc", ".dwg", ".dgn", ".i01", ".nwd", ".nwf", ".nwc",
             ".odt", ".ods", ".txt", ".csv")
# Default names of documents that were never saved.
UNSAVED_RE = re.compile(r"^(?:drawing|document|book|untitled|sheet|presentation|new text document)\s*\d*"
                        r"(?:\.\w{1,5})?$", re.IGNORECASE)
PATH_START_RE = re.compile(r"(?:[A-Za-z]:\\|\\\\[^\\\s]+\\)")
TRIM_SEPARATORS = (" - ", " \u2013 ", " [", " (", " |")


def parse_title(process: str, title: str) -> tuple[str, str] | None:
    """(document name with extension when known, app name) or None."""
    spec = TITLE_PATTERNS.get(process.lower())
    if not spec:
        return None
    patterns, app, default_ext = spec
    for pat in patterns:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            name = m.group("name").strip().rstrip("*").strip()
            if not name:
                continue
            if default_ext and not _has_known_ext(name):
                name = name + default_ext
            return name, app
    return None


def _has_known_ext(name: str) -> bool:
    return name.lower().endswith(KNOWN_EXT)


def protected_view(title: str) -> bool:
    return "[protected view]" in title.lower()


# ---------------------------------------------------------------- Recent (.lnk)
def _resolve_lnk_batch(paths: list[str]) -> dict[str, str]:
    """Target of each .lnk through WScript.Shell (created and released here; capture thread)."""
    import win32com.client
    out: dict[str, str] = {}
    shell = win32com.client.Dispatch("WScript.Shell")
    try:
        for p in paths:
            try:
                out[p] = str(shell.CreateShortcut(p).TargetPath or "")
            except Exception:  # noqa: BLE001
                out[p] = ""
    finally:
        del shell
    return out


class RecentIndex:
    """``%APPDATA%\\Microsoft\\Windows\\Recent\\*.lnk``: lower-case file name -> targets.

    Re-read only when the folder's mtime changes; each link resolved once per (path, mtime)."""

    def __init__(self, folder: Path | None = None,
                 resolve_batch: Callable[[list[str]], dict[str, str]] | None = None):
        self.folder = folder or Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
        self._resolve = resolve_batch or _resolve_lnk_batch
        self._mtime: float | None = None
        self._map: dict[str, list[str]] = {}
        self._resolved: dict[tuple[str, float], str] = {}
        self._lock = threading.Lock()

    def targets(self) -> dict[str, list[str]]:
        with self._lock:
            try:
                mtime = self.folder.stat().st_mtime
            except OSError:
                return self._map
            if mtime == self._mtime:
                return self._map
            links: list[tuple[str, float]] = []
            for lnk in self.folder.glob("*.lnk"):
                try:
                    links.append((str(lnk), lnk.stat().st_mtime))
                except OSError:
                    continue
            todo = [p for p, m in links if (p, m) not in self._resolved]
            fresh = self._resolve(todo) if todo else {}
            keep: dict[tuple[str, float], str] = {}
            out: dict[str, list[str]] = {}
            for key in links:
                target = self._resolved.get(key, fresh.get(key[0], ""))
                keep[key] = target
                if target:
                    lst = out.setdefault(os.path.basename(target.rstrip("\\/")).lower(), [])
                    if target not in lst:
                        lst.append(target)
            self._resolved, self._map, self._mtime = keep, out, mtime
            return self._map


_recent = RecentIndex()


def recent_targets() -> dict[str, list[str]]:
    """``%APPDATA%\\Microsoft\\Windows\\Recent\\*.lnk`` resolved once per link, re-read on folder mtime change."""
    return _recent.targets()


# ---------------------------------------------------------------- matching
def _norm(p: str) -> str:
    return p.strip().rstrip("\\/").lower()


def match_name(doc_name: str, item_paths: list[str], recent: dict[str, list[str]],
               canon: Callable[[str], str] | None = None) -> tuple[str, list[str], str]:
    """(status, candidates, identified_by): status identified | ambiguous | unidentified.

    Exact, case-insensitive file-name match only.  A name without a known extension is also
    tried with each known extension.  The candidates from the items and from Recent are pooled
    (same path counted once): exactly one -> identified, several -> ambiguous (two same-named
    isometrics in different lots are never guessed between), none -> unidentified.  ``canon``
    folds equivalent spellings (drive letter vs UNC) so one file is not counted twice."""
    def key(p: str) -> str:
        return _norm(canon(p) if canon else p)

    name = doc_name.strip().lower()
    if not name:
        return "unidentified", [], ""
    names = [name] if _has_known_ext(name) else [name] + [name + ext for ext in KNOWN_EXT]
    pool: dict[str, tuple[str, str]] = {}           # norm path -> (path, source)
    for p in item_paths:
        if os.path.basename(p.rstrip("\\/")).lower() in names:
            pool.setdefault(key(p), (p, "title+items"))
    for n in names:
        for p in recent.get(n, []):
            pool.setdefault(key(p), (p, "title+recent"))
    found = list(pool.values())
    if len(found) == 1:
        return "identified", [found[0][0]], found[0][1]
    if len(found) > 1:
        by = "title+items" if all(src == "title+items" for _p, src in found) else "title+recent"
        return "ambiguous", [p for p, _src in found], by
    return "unidentified", [], ""


def path_in_title(title: str, exists: Callable[[str], bool]) -> str:
    """A full path written in the title that exists ("D:\\logs\\huge.log - Slate"); "" when none."""
    for m in PATH_START_RE.finditer(title):
        rest = title[m.start():].strip()
        tried: list[str] = []
        cand = rest
        while cand:
            c = cand.strip().rstrip("*").strip()
            if c and c not in tried:
                tried.append(c)
                if len(c) > 3 and exists(c):
                    return c
            cut = max(cand.rfind(sep) for sep in TRIM_SEPARATORS)
            if cut <= 0:
                break
            cand = cand[:cut]
    return ""


class TitleSource:
    name = "titles"

    def __init__(self, exists: Callable[[str], bool] | None = None):
        self._exists = exists or os.path.exists

    def identify(self, windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
        out: dict[int, M.SnapshotEntry] = {}
        for w in windows:
            proc = w.process.lower()
            if proc in SKIP_PROCS:
                continue
            parsed = parse_title(proc, w.title)
            note = "Protected View" if protected_view(w.title) else ""
            if parsed is None:
                path = path_in_title(w.title, self._exists)
                if path:
                    kind = "folder" if os.path.isdir(path) else "file"
                    out[w.hwnd] = M.SnapshotEntry(key="", status="identified", kind=kind, path=path,
                                                  identified_by="title-path",
                                                  doc_name=os.path.basename(path.rstrip("\\/")), note=note)
                continue
            name, app = parsed
            status, candidates, by = match_name(name, ctx.item_paths, ctx.recent_map(), ctx.canon)
            if status == "identified":
                out[w.hwnd] = M.SnapshotEntry(key="", status="identified", kind="file", path=candidates[0], app=app,
                                              identified_by=by, doc_name=name, note=note)
            elif status == "ambiguous":
                out[w.hwnd] = M.SnapshotEntry(key="", status="ambiguous", app=app, identified_by=by, doc_name=name,
                                              candidates=candidates,
                                              note=f"{len(candidates)} files named {name}" + (f"; {note}" if note else ""))
            elif UNSAVED_RE.match(name):
                out[w.hwnd] = M.SnapshotEntry(key="", status="unsaved", app=app, doc_name=name,
                                              note="unsaved - cannot be restored")
            else:
                out[w.hwnd] = M.SnapshotEntry(key="", status="unidentified", app=app, doc_name=name,
                                              note=note or "no path found for this name")
        return out


_default = TitleSource()


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    return _default.identify(windows, ctx)
