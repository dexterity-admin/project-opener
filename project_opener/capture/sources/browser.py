"""Chromium browsers (Chrome, Edge, Brave) through UI Automation.  Owner: builder 2.

The active tab's URL from the "Address and search bar" edit (name list configurable;
fallback: any Edit whose value looks like a URL).  Once per window per title change
(UIA switches Chromium into accessibility mode; keep touches rare).  Note "active tab only".
"""
from __future__ import annotations

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

BROWSER_PROCS = frozenset({"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "opera.exe", "firefox.exe"})
ADDRESS_BAR_NAMES = ("Address and search bar", "Address and Search Bar", "Search or enter web address")


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    raise NotImplementedError("browser.identify")


def open_url(url: str, browser_exe: str = "") -> None:
    """``<browser> --new-window <url>`` when the snapshot recorded the browser, else the default handler."""
    raise NotImplementedError("browser.open_url")
