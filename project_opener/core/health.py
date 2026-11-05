"""Path health: which items will actually open right now?

Pure functions over the resolver; the UI runs them in a worker thread and
caches results per project.  Statuses:

* ``ok``        - path exists (or is a URL / command we cannot verify)
* ``missing``   - the path does not exist
* ``offline``   - the server hosting a UNC path does not answer on port 445
* ``variable``  - the path uses a variable this machine has not defined
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from project_opener.core import models as M
from project_opener.core import winutil
from project_opener.core.pathvars import PathResolver

UNC_HOST_RE = re.compile(r"^\\\\([^\\]+)\\")


@dataclass
class ItemHealth:
    item_id: str
    status: str
    resolved: str
    detail: str = ""


@dataclass
class ProjectHealth:
    project_id: str
    items: list[ItemHealth] = field(default_factory=list)

    @property
    def problems(self) -> list[ItemHealth]:
        return [i for i in self.items if i.status not in ("ok",)]

    @property
    def score(self) -> float:
        if not self.items:
            return 1.0
        return 1 - len(self.problems) / len(self.items)

    def status_for(self, item_id: str) -> ItemHealth | None:
        return next((i for i in self.items if i.item_id == item_id), None)


VAR_RE = re.compile(r"^\{[A-Za-z0-9_]+\}")
DRIVE_RE = re.compile(r"^[A-Za-z]:")
STATUS_RANK = {"offline": 3, "variable": 2, "missing": 1, "ok": 0}


def path_root(path: str) -> str:
    """The root an item path depends on: ``Z:``, ``\\nas01`` or ``{SERVER_ROOT}``; "" for links and commands."""
    p = (path or "").strip()
    m = VAR_RE.match(p)
    if m:
        return m.group(0)
    m = UNC_HOST_RE.match(p)
    if m:
        return "\\\\" + m.group(1)
    m = DRIVE_RE.match(p)
    if m:
        return m.group(0).upper()
    return ""


@dataclass
class RootHealth:
    """One drive, share or variable as this PC sees it, from the health results of every project.

    A mapped drive letter is folded into its server (``\\nas01``) so a server that is down
    appears once; ``shares`` keeps each letter's mapping ("Z:" -> "\\nas01\\Project")."""
    root: str
    status: str                       # ok | missing | offline | variable
    projects: list[str] = field(default_factory=list)   # project ids that use it
    items: int = 0
    shares: dict[str, str] = field(default_factory=dict)

    @property
    def mapping(self) -> str:
        """"Z: → \\nas01\\Project" for a mapped letter (or letters), "" otherwise."""
        return " · ".join(f"{k} → {v}" for k, v in sorted(self.shares.items()))


def drive_exists(root: str) -> bool:
    """Whether a drive letter answers on this PC (patched in tests)."""
    return os.path.isdir(root + os.sep)


def root_key(root: str, drive_map: dict | None) -> tuple[str, str]:
    """(the row's root, the letter's share) with a mapped letter folded into its server."""
    if drive_map and DRIVE_RE.match(root):
        share = drive_map.get(root.upper(), "")
        m = UNC_HOST_RE.match(share + "\\") if share else None
        if m:
            return "\\\\" + m.group(1), share
    return root, ""


def roots_health(projects: list, health: dict, drive_map: dict | None = None) -> list[RootHealth]:
    """Group every checked item by its path root; worst status wins, problems first.

    A root is ``missing`` only when none of its items is reachable (the drive or
    folder is absent on this PC); one missing file on a reachable drive leaves the
    root ``ok`` and the file is reported on its own.  With ``drive_map``
    ({"Z:": "\\\\nas01\\Project"}) a letter's items count under its server."""
    out: dict[str, RootHealth] = {}
    seen_ok: dict[str, bool] = {}
    for p in projects:
        h = health.get(p.id)
        if h is None:
            continue
        for it in p.items:
            letter = path_root(it.path)
            if not letter:
                continue
            root, share = root_key(letter, drive_map)
            st = h.status_for(it.id)
            if st is None:
                continue
            r = out.setdefault(root, RootHealth(root, "ok"))
            if share:
                r.shares[letter] = share
            r.items += 1
            if p.id not in r.projects:
                r.projects.append(p.id)
            if st.status == "ok":
                seen_ok[root] = True
            elif STATUS_RANK.get(st.status, 0) > STATUS_RANK.get(r.status, 0):
                r.status = st.status
    for root, r in out.items():
        if r.status == "missing" and (seen_ok.get(root) or (DRIVE_RE.match(root) and drive_exists(root))):
            r.status = "ok"             # the drive answers; only some files under it are gone
    return sorted(out.values(), key=lambda r: (-STATUS_RANK.get(r.status, 0), r.root.lower()))


def check_item(item: M.Item, resolver: PathResolver, host_cache: dict[str, bool] | None = None) -> ItemHealth:
    host_cache = host_cache if host_cache is not None else {}
    res = resolver.resolve(item.path)
    target = res.resolved
    if res.unresolved:
        return ItemHealth(item.id, "variable", target, "undefined " + ", ".join(res.unresolved))
    if item.kind in ("url", "command") or target.lower().startswith(("http://", "https://", "mailto:")):
        return ItemHealth(item.id, "ok", target)
    if os.path.exists(target):
        return ItemHealth(item.id, "ok", target)
    m = UNC_HOST_RE.match(target)
    if m:
        host = m.group(1)
        if host not in host_cache:
            host_cache[host] = winutil.host_reachable(host)
        if not host_cache[host]:
            return ItemHealth(item.id, "offline", target, f"{host} is not reachable")
    return ItemHealth(item.id, "missing", target, "not found")


def check_project(project: M.Project, resolver: PathResolver, host_cache: dict[str, bool] | None = None) -> ProjectHealth:
    host_cache = host_cache if host_cache is not None else {}
    return ProjectHealth(project.id, [check_item(i, resolver, host_cache) for i in project.items])


def check_activity(activity: M.Activity, resolver: PathResolver,
                   host_cache: dict[str, bool] | None = None) -> ProjectHealth:
    """Health of an activity's items, keyed by the activity id (``ProjectHealth.project_id``).

    ``roots_health`` takes activities as well as projects (both have ``id`` and
    ``items``), so captured items that belong to no project count under their root.
    """
    host_cache = host_cache if host_cache is not None else {}
    return ProjectHealth(activity.id, [check_item(i, resolver, host_cache) for i in activity.items])


def jobs_for_root(root: RootHealth, titles: dict[str, str]) -> list[str]:
    """The job labels (``titles``: id -> job number or title) of the projects/activities using ``root``."""
    out: list[str] = []
    for pid in root.projects:
        label = titles.get(pid, "")
        if label and label not in out:
            out.append(label)
    return out
