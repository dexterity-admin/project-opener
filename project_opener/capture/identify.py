"""The Identifier: sources in order plus the identity cache.  Owner: builder 2.

Cadence (spike section 5): every pass enumerates windows (3-30 ms); a window is
identified only when its ``cache_key`` (hwnd, title, class, pid) is new; a full
re-identification runs every ``CAPTURE_FULL_REFRESH_S`` and on a display change.
Adaptive: skip a pass when the previous one took longer than a third of the interval.
"""
from __future__ import annotations

from collections.abc import Iterable

from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M


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

    def clear(self) -> None:
        self._entries.clear()


class Identifier:
    """Must be used on the capture thread only (COM)."""

    def __init__(self, want_browser_urls: bool = True, ignore_rules: list[dict[str, str]] | None = None):
        self.cache = IdentityCache()
        self.want_browser_urls = want_browser_urls
        self.ignore_rules = list(ignore_rules or [])

    def ignored(self, w: WindowInfo) -> bool:
        """``Settings.capture_ignore`` rules: {"process": name, "title": glob (optional)}."""
        raise NotImplementedError("Identifier.ignored")

    def identify(self, windows: list[WindowInfo], item_paths: list[str], full: bool = False) -> list[M.SnapshotEntry]:
        """One entry per non-ignored window, in z-order, reusing the cache unless ``full``."""
        raise NotImplementedError("Identifier.identify")

    def identify_one(self, hwnd: int, item_paths: list[str]) -> M.SnapshotEntry | None:
        """For "add this window" and the picker's hover label."""
        raise NotImplementedError("Identifier.identify_one")
