"""Chromium browsers (Chrome, Edge, Brave) through UI Automation.  Owner: builder 2.

The active tab's URL from the "Address and search bar" edit (name list configurable;
fallback: any Edit whose value looks like a URL).  Once per window per title change
(UIA switches Chromium into accessibility mode; keep touches rare: the Identifier's
cache guarantees it).  Note "active tab only".
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from collections.abc import Callable

from project_opener.capture.sources import SourceContext
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M

log = logging.getLogger(__name__)

BROWSER_PROCS = frozenset({"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "opera.exe", "firefox.exe"})
ADDRESS_BAR_NAMES = ("Address and search bar", "Address and Search Bar", "Search or enter web address")
APP_NAMES = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "brave.exe": "Brave", "vivaldi.exe": "Vivaldi",
             "opera.exe": "Opera", "firefox.exe": "Firefox"}
# The tab title the browser puts before its own name ("<tab> - Google Chrome"); Edge adds a zero-width space.
TAB_SUFFIX = re.compile(r"\s+[-–]\s+(?:Google Chrome|Microsoft​? Edge|Brave|Vivaldi|Opera|Mozilla Firefox)$")
URL_LIKE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://\S+|[\w.-]+\.[a-z]{2,}(?:[/:?#]\S*)?)$", re.IGNORECASE)

# hwnd -> (field name, value) of the address bar; None when not found
ReadAddressFn = Callable[[int], tuple[str, str] | None]

UIA_EditControlTypeId = 50004
UIA_ControlTypePropertyId = 30003
UIA_IsValuePatternAvailablePropertyId = 30043
UIA_ValuePatternId = 10002
TreeScope_Descendants = 4

_tls = threading.local()


def _uia():
    """The IUIAutomation object of this thread (created on first use; the capture thread only)."""
    obj = getattr(_tls, "uia", None)
    if obj is None:
        import comtypes.client
        try:
            from comtypes.gen import UIAutomationClient as UIA  # type: ignore[attr-defined]
        except ImportError:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA  # type: ignore[attr-defined]
        obj = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        _tls.uia, _tls.mod = obj, UIA
    return obj, _tls.mod


def read_address(hwnd: int, names: tuple[str, ...] = ADDRESS_BAR_NAMES) -> tuple[str, str] | None:
    """(field name, value) of the window's address bar through UIA; None when there is none."""
    uia, mod = _uia()
    root = uia.ElementFromHandle(hwnd)
    cond = uia.CreateAndCondition(uia.CreatePropertyCondition(UIA_ControlTypePropertyId, UIA_EditControlTypeId),
                                  uia.CreatePropertyCondition(UIA_IsValuePatternAvailablePropertyId, True))
    arr = root.FindAll(TreeScope_Descendants, cond)
    fallback: tuple[str, str] | None = None
    wanted = {n.lower() for n in names}
    for i in range(arr.Length):
        el = arr.GetElement(i)
        name = el.CurrentName or ""
        try:
            vp = el.GetCurrentPattern(UIA_ValuePatternId).QueryInterface(mod.IUIAutomationValuePattern)
            val = vp.CurrentValue or ""
        except Exception:  # noqa: BLE001
            continue
        if name.lower() in wanted:
            return name, val
        if fallback is None and URL_LIKE.match(val.strip()):
            fallback = (name, val)
    return fallback


def normalise_url(value: str) -> str:
    """Add back the scheme Chromium hides ("github.com/x" -> "https://github.com/x")."""
    v = value.strip()
    if v and not re.match(r"^[a-z][a-z0-9+.-]*:", v, re.IGNORECASE):
        v = "https://" + v
    return v


def tab_title(title: str) -> str:
    return TAB_SUFFIX.sub("", title).strip()


class BrowserSource:
    name = "uia"

    def __init__(self, read_address_fn: ReadAddressFn | None = None):
        self._read = read_address_fn or read_address

    def identify(self, windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
        if not ctx.want_browser_urls:
            return {}
        out: dict[int, M.SnapshotEntry] = {}
        for w in windows:
            proc = w.process.lower()
            if proc not in BROWSER_PROCS:
                continue
            try:
                found = self._read(w.hwnd)
            except Exception as exc:  # noqa: BLE001
                log.debug("UIA failed on %s: %s", w.title, exc)
                continue
            if not found:
                continue
            url = normalise_url(found[1])
            if not URL_LIKE.match(url) or url.lower().startswith(("chrome://", "edge://", "brave://", "about:")):
                continue          # new tab page, settings, a search typed but not run: not a page to reopen
            out[w.hwnd] = M.SnapshotEntry(key="", status="identified", kind="url", path=url,
                                          app=APP_NAMES.get(proc, w.process), identified_by="uia",
                                          doc_name=tab_title(w.title), note="active tab only")
        return out


_default = BrowserSource()


def identify(windows: list[WindowInfo], ctx: SourceContext) -> dict[int, M.SnapshotEntry]:
    return _default.identify(windows, ctx)


def open_url(url: str, browser_exe: str = "") -> None:
    """``<browser> --new-window <url>`` when the snapshot recorded the browser, else the default handler."""
    if browser_exe and os.path.basename(browser_exe).lower() in BROWSER_PROCS and os.path.exists(browser_exe):
        flag = "-new-window" if os.path.basename(browser_exe).lower() == "firefox.exe" else "--new-window"
        subprocess.Popen([browser_exe, flag, url], close_fds=True)
        return
    os.startfile(url)  # type: ignore[attr-defined]
