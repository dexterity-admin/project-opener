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
