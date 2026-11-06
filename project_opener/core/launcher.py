"""Opening items.

``Launcher.launch`` returns a ``LaunchReport`` listing what opened, what was
missing and what failed, and never raises.  It only decides *how* to open
something (shell, subprocess, browser); it never judges whether a path is the
right one.  Opening itself is done through ``os.startfile`` on Windows (the
same as double-clicking in Explorer) so file associations are honoured.

v4 additions (builder 1):

* **profiles** - an item with ``profile_id`` is started through
  ``core.profiles.build_command`` (arguments, working folder, environment).  The
  launcher finds profiles through ``profiles`` (a callable ``id -> LaunchProfile``),
  or, when none was given, through the process-wide lookup set with
  ``set_profile_lookup`` (so a launcher rebuilt by ``apply_settings`` keeps it).
  A profile that cannot be found is reported in the result's message and the
  item opens as before; nothing is silently skipped.
* **openers** - ``openers`` maps a lower-case extension (".xlsx") to a callable
  ``opener(path) -> bool``; True means it opened the file, False (or an
  exception) falls back to the file association.  The default is the shared
  ``OPENERS`` registry, so the capture builder's Office opener survives a
  rebuilt launcher.  The launcher runs on a pool thread; an opener that needs
  COM initialises it itself.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field

from project_opener.core import models as M
from project_opener.core import winutil
from project_opener.core.pathvars import PathResolver
from project_opener.core.profiles import Command, build_command

log = logging.getLogger(__name__)

UNC_HOST_RE = re.compile(r"^\\\\([^\\]+)\\")

# Fine-grained outcome of one item (``LaunchResult.code``).  ``status`` stays
# the coarse category the history and the summary count: ``offline`` and
# ``variable`` are both ``missing`` there.
CODES = ("opened", "missing", "offline", "variable", "skipped", "failed")

Opener = Callable[[str], bool]
OPENER_TIMEOUT_S = 30.0          # a cold Excel on an old PC takes 10-20 s; past this it is waiting on a message
ProfileLookup = Callable[[str], "M.LaunchProfile | None"]

# Shared registries (see the module docstring).
OPENERS: dict[str, Opener] = {}
_profile_lookup: ProfileLookup | None = None


def set_profile_lookup(fn: ProfileLookup | None) -> None:
    """The process-wide profile lookup used by launchers built without ``profiles``."""
    global _profile_lookup
    _profile_lookup = fn


def register_opener(ext: str, fn: Opener | None) -> None:
    """Register (or with ``None`` remove) the shared opener for an extension (".xlsx")."""
    key = ext.lower() if ext.startswith(".") else "." + ext.lower()
    if fn is None:
        OPENERS.pop(key, None)
    else:
        OPENERS[key] = fn


@dataclass
class LaunchResult:
    item: M.Item
    resolved: str
    status: str          # opened | missing | failed | skipped
    message: str = ""
    code: str = ""       # opened | missing | offline | variable | skipped | failed (defaults to status)

    def __post_init__(self) -> None:
        if not self.code:
            self.code = self.status


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
    def __init__(self, resolver: PathResolver, delay_ms: int = 300, dry_run: bool = False,
                 profiles: ProfileLookup | None = None, openers: dict[str, Opener] | None = None):
        self.resolver = resolver
        self.delay_ms = delay_ms
        self.dry_run = dry_run
        self._profiles = profiles
        self.openers: dict[str, Opener] = OPENERS if openers is None else openers
        self.started: list[Command] = []      # dry-run record of profile launches (tests)
        # An opener (Excel/Word through COM) that does not return blocks every item after it: Office waiting on
        # a message of its own (no disk space, a file in use, a sign-in) never answers.  It gets this long.
        self.opener_timeout_s = OPENER_TIMEOUT_S

    def profile_for(self, item: M.Item) -> M.LaunchProfile | None:
        if not item.profile_id:
            return None
        lookup = self._profiles or _profile_lookup
        if lookup is None:
            return None
        try:
            return lookup(item.profile_id)
        except Exception:  # noqa: BLE001
            log.exception("profile lookup failed")
            return None

    # --------------------------------------------------------------- public
    def launch(self, items: list[M.Item],
               progress: Callable[[int, LaunchResult], None] | None = None,
               starting: Callable[[int], None] | None = None) -> LaunchReport:
        """Open ``items`` one after another.

        ``starting(index)`` is called just before an item is tried and
        ``progress(index, result)`` as soon as it has been tried, in order, on
        the calling thread.  Both are optional; neither may raise into here.
        """
        report = LaunchReport()
        hosts: dict[str, bool] = {}
        for idx, item in enumerate(items):
            if starting:
                starting(idx)
            result = self.open_item(item, hosts)
            report.results.append(result)
            if progress:
                progress(idx, result)
            if idx < len(items) - 1 and self.delay_ms and not self.dry_run:
                time.sleep(self.delay_ms / 1000.0)
        return report

    def open_item(self, item: M.Item, host_cache: dict[str, bool] | None = None) -> LaunchResult:
        raw = item.path.strip()
        if not raw:
            return LaunchResult(item, "", "skipped", "empty path")
        res = self.resolver.resolve(raw)
        target = res.resolved
        if res.unresolved:
            return LaunchResult(item, target, "missing", f"unknown variable {', '.join(res.unresolved)}", code="variable")
        try:
            if item.kind == "url" or _is_url(target):
                return self._open_url(item, target)
            if item.kind == "command":
                return self._run_command(item, target)
            cache = host_cache if host_cache is not None else {}
            if item.profile_id:
                profile = self.profile_for(item)
                if profile is not None:
                    return self._run_profile(item, profile, cache)
                result = self._open_plain(item, target, cache)
                if result.status == "opened":
                    note = f"launch profile {item.profile_id} not found; opened without it"
                    result.message = (result.message + "; " if result.message else "") + note
                return result
            return self._open_plain(item, target, cache)
        except Exception as exc:  # noqa: BLE001 - must never propagate
            log.exception("open failed for %s", target)
            return LaunchResult(item, target, "failed", str(exc))

    def _open_plain(self, item: M.Item, target: str, host_cache: dict[str, bool]) -> LaunchResult:
        if not os.path.exists(target):
            return self._not_found(item, target, host_cache)
        if item.kind == "app" or target.lower().endswith((".exe", ".bat", ".cmd")):
            return self._run_app(item, target)
        opened = self._try_opener(item, target)
        if opened is not None:
            return opened
        return self._shell_open(item, target)

    def _try_opener(self, item: M.Item, target: str) -> LaunchResult | None:
        """A registered opener for the file's extension; None to fall back to the association."""
        if item.kind != "file":
            return None
        fn = self.openers.get(os.path.splitext(target)[1].lower())
        if fn is None:
            return None
        if self.dry_run:
            return LaunchResult(item, target, "opened", "opened through its application")
        box: dict[str, object] = {}

        def call() -> None:
            try:
                box["ok"] = bool(fn(target))
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        worker = threading.Thread(target=call, name="opener", daemon=True)
        worker.start()
        worker.join(self.opener_timeout_s)
        if worker.is_alive():
            # never a second open through the association: the application may still open it after its message
            log.warning("opener for %s did not return in %.0f s", target, self.opener_timeout_s)
            return LaunchResult(item, target, "failed",
                                f"its application did not answer in {self.opener_timeout_s:.0f} s; "
                                "it may be showing a message")
        if box.get("ok"):
            return LaunchResult(item, target, "opened", "opened through its application")
        if "error" in box:
            log.warning("opener failed for %s (%s); using the file association", target, box["error"])
        return None

    def _run_profile(self, item: M.Item, profile: M.LaunchProfile, host_cache: dict[str, bool]) -> LaunchResult:
        cmd = build_command(item, profile, self.resolver)
        label = f"profile {profile.name}"
        if cmd.unresolved:
            return LaunchResult(item, cmd.exe, "missing", f"{label}: unknown variable {', '.join(cmd.unresolved)}",
                                code="variable")
        if not os.path.exists(cmd.exe):
            res = self._not_found(item, cmd.exe, host_cache)
            res.message = f"{label}: {res.message}"
            return res
        cwd = cmd.cwd if cmd.cwd and os.path.isdir(cmd.cwd) else (os.path.dirname(cmd.exe) or None)
        if self.dry_run:
            self.started.append(cmd)
        else:
            env = {**os.environ, **cmd.env} if cmd.env else None
            if sys.platform == "win32" and cmd.exe.lower().endswith((".bat", ".cmd")):
                subprocess.Popen(["cmd", "/c", cmd.exe, *cmd.args], cwd=cwd, env=env,
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen([cmd.exe, *cmd.args], cwd=cwd, env=env)
        msg = label + (" " + " ".join(cmd.args) if cmd.args else "")
        if cmd.cwd and cwd != cmd.cwd:
            msg += f" (working folder {cmd.cwd} not found; used {cwd})"
        return LaunchResult(item, cmd.exe, "opened", msg)

    # -------------------------------------------------------------- private
    @staticmethod
    def _not_found(item: M.Item, target: str, host_cache: dict[str, bool]) -> LaunchResult:
        """``offline`` when the UNC host does not answer, else ``missing`` (same probe as core.health)."""
        m = UNC_HOST_RE.match(target)
        if m:
            host = m.group(1)
            if host not in host_cache:
                host_cache[host] = winutil.host_reachable(host)
            if not host_cache[host]:
                return LaunchResult(item, target, "missing", f"{host} is not reachable", code="offline")
        return LaunchResult(item, target, "missing", "path not found")

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
