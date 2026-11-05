"""Identification sources, tried per window in this order (spike section 2):

1. ``explorer``  Shell.Application.Windows(): folder path per CabinetWClass hwnd
2. ``office``    Excel/Word per window through AccessibleObjectFromWindow (EXCEL7 / _WwG child,
                 OBJID_NATIVEOM): FullName, Saved, unsaved, Protected View; never "the" ROT instance
3. ``browser``   UI Automation: the "Address and search bar" edit of Chromium windows (active tab)
4. ``titles``    title patterns (PDF viewers, CAD, LibreOffice, "path in the title"), file name matched
                 against the activity's items, then Recent (.lnk); one candidate or it is ambiguous

Every source has the same shape::

    def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]

returning entries only for the hwnds it could speak about (identified, ambiguous or unsaved).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceContext:
    """What title matching may consult; built by the Identifier for each pass."""
    item_paths: list[str] = field(default_factory=list)      # the running activity's item paths (resolved)
    recent: dict[str, list[str]] = field(default_factory=dict)  # lower-case file name -> full paths
    want_browser_urls: bool = True
