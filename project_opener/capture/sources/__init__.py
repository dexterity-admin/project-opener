"""Identification sources, tried per window in this order (spike section 2):

1. ``explorer``  Shell.Application.Windows(): folder path per CabinetWClass hwnd
2. ``office``    Excel/Word per window through AccessibleObjectFromWindow (EXCEL7 / _WwG child,
                 OBJID_NATIVEOM): FullName, Saved, unsaved, Protected View; never "the" ROT instance
3. ``browser``   UI Automation: the "Address and search bar" edit of Chromium windows (active tab)
4. ``titles``    title patterns (PDF viewers, CAD, LibreOffice, "path in the title"), file name matched
                 against the activity's items, then Recent (.lnk); one candidate or it is ambiguous

Every source is a class with an injectable backend (so it is testable with fakes) and the same
shape::

    Source().identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]

returning entries only for the hwnds it could speak about (identified, ambiguous or unsaved; the
title source also returns ``unidentified`` entries that carry the document name it read, so the
list can say "needs a path" rather than "not a file").  Each module also keeps the documented
module-level ``identify(windows, ctx)`` over a default instance.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class SourceContext:
    """What title matching may consult; built by the Identifier for each pass."""
    item_paths: list[str] = field(default_factory=list)      # the running activity's item paths (resolved)
    recent: dict[str, list[str]] = field(default_factory=dict)  # lower-case file name -> full paths
    want_browser_urls: bool = True
    recent_fn: Callable[[], dict[str, list[str]]] | None = None   # loads ``recent`` lazily (first title match)
    canon: Callable[[str], str] | None = None     # path canonicaliser (drive letter -> UNC) for de-duplication
    _recent_loaded: bool = False

    def recent_map(self) -> dict[str, list[str]]:
        if not self._recent_loaded and self.recent_fn is not None:
            try:
                loaded = self.recent_fn() or {}
            except Exception:  # noqa: BLE001 - Recent is a convenience, never fatal
                loaded = {}
            merged = dict(loaded)
            for k, v in self.recent.items():
                merged.setdefault(k, list(v))
            self.recent = merged
        self._recent_loaded = True
        return self.recent
