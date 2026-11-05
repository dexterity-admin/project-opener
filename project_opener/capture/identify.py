"""The Identifier: sources in order plus the identity cache.  Owner: builder 2.

Cadence (spike section 5): every pass enumerates windows (3-30 ms); a window is
identified only when its ``cache_key`` (hwnd, title, class, pid) is new; a full
re-identification runs every ``CAPTURE_FULL_REFRESH_S`` and on a display change.
Adaptive: skip a pass when the previous one took longer than a third of the interval
(the engine does that; this module only answers "what is this window").
"""
from __future__ import annotations

import copy
import fnmatch
import os
from collections.abc import Callable, Iterable

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

APP_NAMES = {
    "excel.exe": "Excel", "winword.exe": "Word", "explorer.exe": "Explorer", "chrome.exe": "Chrome",
    "msedge.exe": "Edge", "brave.exe": "Brave", "firefox.exe": "Firefox", "pdfxedit.exe": "PDF-XChange Editor",
    "acad.exe": "AutoCAD", "roamer.exe": "Navisworks", "microstation.exe": "MicroStation", "ustation.exe":
    "MicroStation", "powerdraft.exe": "PowerDraft", "soffice.bin": "LibreOffice", "outlook.exe": "Outlook",
    "notepad.exe": "Notepad", "notepad++.exe": "Notepad++", "code.exe": "VS Code",
}


# Processes whose cached answer holds until the title changes, even on a full refresh.
TITLE_STABLE_PROCS = frozenset({"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "opera.exe", "firefox.exe"})


def app_name(process: str) -> str:
    low = process.lower()
    if low in APP_NAMES:
        return APP_NAMES[low]
    stem = os.path.splitext(process)[0]
    return stem[:1].upper() + stem[1:] if stem else ""


def entry_key(status: str, path: str = "", process: str = "", title: str = "") -> str:
    """The ``SnapshotEntry.key`` identity: "path:<lower path>" / "url:<url>" / "win:<process>|<title>"."""
    if path:
        if path.lower().startswith(("http://", "https://")):
            return f"url:{path}"
        return f"path:{path.strip().rstrip(chr(92) + '/').lower()}"
    return f"win:{process.lower()}|{title}"


class IdentityCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[int, str, str, int], M.SnapshotEntry] = {}

    def get(self, w: WindowInfo) -> M.SnapshotEntry | None:
        return self._entries.get(w.cache_key)

    def put(self, w: WindowInfo, entry: M.SnapshotEntry) -> None:
        self._entries[w.cache_key] = entry

    def prune(self, alive: Iterable[WindowInfo]) -> None:
        keep = {w.cache_key for w in alive}
        self._entries = {k: v for k, v in self._entries.items() if k in keep}

    def invalidate(self, pred: Callable[[M.SnapshotEntry], bool]) -> int:
        """Forget entries for which ``pred`` holds (e.g. title matches when the items changed)."""
        drop = [k for k, v in self._entries.items() if pred(v)]
        for k in drop:
            del self._entries[k]
        return len(drop)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def default_sources() -> list:
    from project_opener.capture.sources.browser import BrowserSource
    from project_opener.capture.sources.explorer import ExplorerSource
    from project_opener.capture.sources.office import OfficeSource
    from project_opener.capture.sources.titles import TitleSource
    return [ExplorerSource(), OfficeSource(), BrowserSource(), TitleSource()]


def rule_matches(rule: dict[str, str], process: str, title: str) -> bool:
    """One ``Settings.capture_ignore`` rule: {"process": name, "title": glob (optional)}, case-insensitive."""
    rp = str(rule.get("process", "") or "").strip().lower()
    rt = str(rule.get("title", "") or "")
    if not rp and not rt:
        return False
    if rp and rp != process.lower():
        return False
    return not rt or fnmatch.fnmatchcase(title.lower(), rt.lower())


def title_matched(e: M.SnapshotEntry) -> bool:
    """Entries whose answer depends on the item list (re-ask when the items change)."""
    return e.identified_by.startswith("title+") or e.status in ("unidentified", "ambiguous")


class Identifier:
    """Must be used on the capture thread only (COM)."""

    def __init__(self, want_browser_urls: bool = True, ignore_rules: list[dict[str, str]] | None = None,
                 sources: list | None = None, recent_fn: Callable[[], dict[str, list[str]]] | None = None,
                 canon: Callable[[str], str] | None = None,
                 window_info_fn: Callable[[int], WindowInfo | None] | None = None):
        self.cache = IdentityCache()
        self.want_browser_urls = want_browser_urls
        self.ignore_rules = list(ignore_rules or [])
        self.sources = sources if sources is not None else default_sources()
        if recent_fn is None:
            from project_opener.capture.sources.titles import recent_targets
            recent_fn = recent_targets
        self.recent_fn = recent_fn
        self.canon = canon
        self._window_info = window_info_fn
        self.last_queried = 0                 # windows actually sent to the sources in the last call

    def ignored(self, w: WindowInfo) -> bool:
        """``Settings.capture_ignore`` rules: {"process": name, "title": glob (optional)}."""
        return any(rule_matches(r, w.process, w.title) for r in self.ignore_rules if isinstance(r, dict))

    def items_changed(self) -> None:
        """The activity's items changed: title-matched answers may change too."""
        self.cache.invalidate(title_matched)

    # ------------------------------------------------------------- core
    def _context(self, item_paths: list[str]) -> SourceContext:
        return SourceContext(item_paths=list(item_paths), want_browser_urls=self.want_browser_urls,
                             recent_fn=self.recent_fn, canon=self.canon)

    @staticmethod
    def _finish(e: M.SnapshotEntry, w: WindowInfo) -> M.SnapshotEntry:
        e.title, e.process, e.exe, e.window_class = w.title, w.process, w.exe, w.window_class
        e.hwnd, e.pid, e.placement = w.hwnd, w.pid, w.placement
        if not e.app:
            e.app = app_name(w.process)
        if e.status != "identified":
            e.path, e.kind = "", e.kind if e.status == "unsaved" else ""
        e.key = entry_key(e.status, e.path, w.process, w.title)
        return e

    def _run_sources(self, todo: list[WindowInfo], item_paths: list[str]) -> tuple[dict[int, M.SnapshotEntry],
                                                                                    set[int]]:
        ctx = self._context(item_paths)
        found: dict[int, M.SnapshotEntry] = {}
        retry: set[int] = set()
        remaining = list(todo)
        for src in self.sources:
            if not remaining:
                break
            try:
                got = src.identify(remaining, ctx) or {}
            except Exception:  # noqa: BLE001 - one failing source never stops the others
                got = {}
            retry |= set(getattr(src, "retry", set()) or set())
            for hwnd, e in got.items():
                prev = found.get(hwnd)
                # a later source may improve on an earlier non-identified answer, never replace an identified one
                if prev is None or (prev.status != "identified" and e.status == "identified"):
                    found[hwnd] = e
            # windows a source answered definitively (identified/unsaved) are not offered to later sources
            remaining = [w for w in remaining if w.hwnd not in found or found[w.hwnd].status in ("unidentified",
                                                                                                 "ambiguous")]
        return found, retry

    def identify(self, windows: list[WindowInfo], item_paths: list[str], full: bool = False,
                 apply_ignore: bool = True) -> list[M.SnapshotEntry]:
        """One entry per non-ignored window, in z-order, reusing the cache unless ``full``."""
        wins = [w for w in windows if not (apply_ignore and self.ignored(w))]
        # A full refresh re-asks every source except UIA: a browser is read once per window per
        # title change (touching Chromium through UIA costs it CPU; spike section 6).
        todo = [w for w in wins if self.cache.get(w) is None
                or (full and w.process.lower() not in TITLE_STABLE_PROCS)]
        self.last_queried = len(todo)
        found, retry = self._run_sources(todo, item_paths) if todo else ({}, set())
        todo_hwnds = {w.hwnd for w in todo}
        out: list[M.SnapshotEntry] = []
        for w in wins:
            if w.hwnd in todo_hwnds:
                e = found.get(w.hwnd) or M.SnapshotEntry(key="", status="unidentified")
                e = self._finish(e, w)
                if w.hwnd not in retry:
                    self.cache.put(w, copy.deepcopy(e))
            else:
                cached = self.cache.get(w)
                e = copy.deepcopy(cached) if cached is not None else M.SnapshotEntry(key="")
                e = self._finish(e, w)              # fresh placement, same identity
            out.append(e)
        if apply_ignore:
            self.cache.prune(windows)
        return out

    def identify_one(self, hwnd: int, item_paths: list[str]) -> M.SnapshotEntry | None:
        """For "add this window" and the picker's hover label (ignore rules do not apply: the user chose it)."""
        if self._window_info is None:
            from project_opener.capture import win32
            info = win32.window_info(hwnd)
        else:
            info = self._window_info(hwnd)
        if info is None:
            return None
        cached = self.cache.get(info)
        if cached is not None:
            return self._finish(copy.deepcopy(cached), info)
        return self.identify([info], item_paths, full=True, apply_ignore=False)[0]
