"""Opening items.

``Launcher.launch`` returns a ``LaunchReport`` listing what opened, what was
missing and what failed, and never raises.  It only decides *how* to open
something (shell, subprocess, browser); it never judges whether a path is the
right one.  Opening itself is done through ``os.startfile`` on Windows (the
same as double-clicking in Explorer) so file associations are honoured.
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver

log = logging.getLogger(__name__)


@dataclass
class LaunchResult:
    item: M.Item
    resolved: str
    status: str          # opened | missing | failed | skipped
    message: str = ""


@dataclass
class LaunchReport:
    results: list[LaunchResult] = field(default_factory=list)

    @property
    def opened(self) -> list[LaunchResult]:
        return [r for r in self.results if r.status == "opened"]

    @property
    def missing(self) -> list[LaunchResult]:
        return [r for r in self.results if r.status == "missing"]

    @property
    def failed(self) -> list[LaunchResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.failed

    def summary(self) -> str:
        parts = [f"{len(self.opened)} opened"]
        if self.missing:
            parts.append(f"{len(self.missing)} missing")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts)


def _is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://", "ftp://", "mailto:", "ms-teams:", "onenote:", "file://"))


class Launcher:
    def __init__(self, resolver: PathResolver, delay_ms: int = 300, dry_run: bool = False):
        self.resolver = resolver
        self.delay_ms = delay_ms
        self.dry_run = dry_run

    # --------------------------------------------------------------- public
    def launch(self, items: list[M.Item]) -> LaunchReport:
        report = LaunchReport()
        for idx, item in enumerate(items):
            report.results.append(self.open_item(item))
            if idx < len(items) - 1 and self.delay_ms and not self.dry_run:
                time.sleep(self.delay_ms / 1000.0)
        return report

    def open_item(self, item: M.Item) -> LaunchResult:
        raw = item.path.strip()
        if not raw:
            return LaunchResult(item, "", "skipped", "empty path")
        res = self.resolver.resolve(raw)
        target = res.resolved
        if res.unresolved:
            return LaunchResult(item, target, "missing", f"unknown variable {', '.join(res.unresolved)}")
        try:
            if item.kind == "url" or _is_url(target):
                return self._open_url(item, target)
            if item.kind == "command":
                return self._run_command(item, target)
            if not os.path.exists(target):
                return LaunchResult(item, target, "missing", "path not found")
            if item.kind == "app" or target.lower().endswith((".exe", ".bat", ".cmd")):
                return self._run_app(item, target)
            return self._shell_open(item, target)
        except Exception as exc:  # noqa: BLE001 - must never propagate
            log.exception("open failed for %s", target)
            return LaunchResult(item, target, "failed", str(exc))

    # -------------------------------------------------------------- private
    def _open_url(self, item: M.Item, url: str) -> LaunchResult:
        if "://" not in url and not url.lower().startswith("mailto:"):
            url = "https://" + url
        if not self.dry_run:
            if sys.platform == "win32":
                os.startfile(url)  # type: ignore[attr-defined]
            else:  # pragma: no cover
                webbrowser.open(url)
        return LaunchResult(item, url, "opened")

    def _shell_open(self, item: M.Item, target: str) -> LaunchResult:
        if not self.dry_run:
            if sys.platform == "win32":
                os.startfile(target)  # type: ignore[attr-defined]
            else:  # pragma: no cover
                subprocess.Popen(["xdg-open", target])
        return LaunchResult(item, target, "opened")

    def _run_app(self, item: M.Item, target: str) -> LaunchResult:
        args = shlex.split(item.args, posix=False) if item.args.strip() else []
        args = [self.resolver.resolve(a).resolved if "{" in a or ":" in a else a for a in args]
        cwd = os.path.dirname(target) or None
        if not self.dry_run:
            if sys.platform == "win32":
                if target.lower().endswith((".bat", ".cmd")):
                    subprocess.Popen(["cmd", "/c", target, *args], cwd=cwd,
                                     creationflags=subprocess.CREATE_NEW_CONSOLE)
                elif args:
                    subprocess.Popen([target, *args], cwd=cwd)
                else:
                    os.startfile(target)  # type: ignore[attr-defined]  # honours UAC manifests / .lnk
            else:  # pragma: no cover
                subprocess.Popen([target, *args], cwd=cwd)
        return LaunchResult(item, target, "opened", " ".join(args))

    def _run_command(self, item: M.Item, target: str) -> LaunchResult:
        """``cmd:`` or ``ps:`` prefixed one-liners, run in a visible console."""
        low = target.lower()
        if low.startswith("cmd:"):
            cmdline = target[4:].strip()
            argv = ["cmd", "/k", cmdline]
        elif low.startswith("ps:"):
            cmdline = target[3:].strip()
            argv = ["powershell", "-NoExit", "-Command", cmdline]
        else:
            argv = ["cmd", "/k", target]
        if not self.dry_run:
            flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            subprocess.Popen(argv, creationflags=flags)
        return LaunchResult(item, target, "opened")
