"""Office-wide path health: ``watch/<user>.json`` (a ``HealthObservation``).  Owner: builder 1 (CORE+HUB).

Each PC writes what it saw (only its own file); every PC merges all files into
"nas01 down since 09:40, seen by 3 PCs, 14 jobs affected".  ``since`` is the
earliest time any fresh observation (younger than ``HUB_STALE_S``) reports the
current status.

Merging reports what was seen, never a guess: a root that some PCs see down and
others see up is shown with its worst status, ``seen_by`` (who saw that) and
``ok_by`` (who still reaches it), so the reader can tell "nas01 is down" from
"one PC lost its network".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)

RANK = {"offline": 3, "variable": 2, "missing": 1, "ok": 0}


def _ts(value: str) -> float:
    dt = M.parse_iso(value)
    return dt.timestamp() if dt else float("inf")


@dataclass
class OfficeRoot:
    root: str
    status: str
    since: str = ""
    seen_by: list[str] = field(default_factory=list)     # logins
    jobs: list[str] = field(default_factory=list)
    ok_by: list[str] = field(default_factory=list)       # logins that reach it (status "ok")
    items: int = 0

    @property
    def text(self) -> str:
        """"\\\\nas01 offline since 09:40, seen by 3 PCs, 14 jobs affected"."""
        if self.status == "ok":
            return f"{self.root} ok"
        parts = [f"{self.root} {self.status}"]
        dt = M.parse_iso(self.since)
        if dt:
            parts[0] += f" since {dt.astimezone().strftime('%H:%M')}"
        n = len(self.seen_by)
        parts.append(f"seen by {n} PC{'s' if n != 1 else ''}")
        if self.jobs:
            parts.append(f"{len(self.jobs)} job{'s' if len(self.jobs) != 1 else ''} affected")
        return ", ".join(parts)


class HealthBoard:
    def __init__(self, hub_root: Path | None, user: str):
        self.root = Path(hub_root) / "watch" if hub_root else None
        self.user = user

    def write(self, observation: M.HealthObservation) -> None:
        if self.root is None:
            return
        observation.user = self.user
        write_json_atomic(self.root / f"{self.user}.json", observation.to_dict())

    def read_all(self) -> list[M.HealthObservation]:
        if self.root is None:
            return []
        out: list[M.HealthObservation] = []
        try:
            files = sorted(self.root.glob("*.json"))
        except OSError:
            return out
        for f in files:
            d = read_json(f, None)
            if not isinstance(d, dict):
                continue
            obs = M.HealthObservation.from_dict(d)
            obs.user = obs.user or f.stem
            out.append(obs)
        return out

    def merged(self, now: float | None = None, stale_s: int = C.HUB_STALE_S) -> list[OfficeRoot]:
        """One row per root from every fresh observation; problems first."""
        now = time.time() if now is None else now
        rows: dict[str, OfficeRoot] = {}
        keys: dict[str, str] = {}
        for obs in self.read_all():
            ts = M.parse_iso(obs.ts)
            if ts is None or now - ts.timestamp() > stale_s:
                continue
            for r in obs.roots:
                if not r.root:
                    continue
                k = r.root.lower()
                row = rows.get(k)
                if row is None:
                    row = rows[k] = OfficeRoot(r.root, "ok")
                    keys[k] = r.root
                row.items = max(row.items, r.items)
                for j in r.jobs:
                    if j not in row.jobs:
                        row.jobs.append(j)
                if r.status == "ok":
                    if obs.user not in row.ok_by:
                        row.ok_by.append(obs.user)
                    continue
                rank, cur = RANK.get(r.status, 1), RANK.get(row.status, 0)
                if rank > cur:
                    row.status, row.since, row.seen_by = r.status, r.since, [obs.user]
                elif rank == cur and obs.user not in row.seen_by:
                    row.seen_by.append(obs.user)
                    if r.since and (not row.since or _ts(r.since) < _ts(row.since)):
                        row.since = r.since
        for row in rows.values():
            if row.status == "ok":
                row.seen_by = list(row.ok_by)
        return sorted(rows.values(), key=lambda r: (-RANK.get(r.status, 0), r.root.lower()))


def observe(previous: dict[str, tuple[str, str]], current: dict[str, tuple[str, list[str], int]],
            now: datetime | None = None) -> tuple[list[M.RootObservation], dict[str, tuple[str, str]]]:
    """This PC's roots as ``RootObservation``s with ``since`` kept across calls.

    ``previous``: root -> (status, since) from the last call; ``current``: root -> (status, jobs, items).
    Returns the observations and the new ``previous``.
    """
    stamp = (now or datetime.now().astimezone()).astimezone().isoformat(timespec="seconds")
    out: list[M.RootObservation] = []
    nxt: dict[str, tuple[str, str]] = {}
    for root, (status, jobs, items) in current.items():
        before = previous.get(root)
        since = before[1] if before and before[0] == status and before[1] else stamp
        nxt[root] = (status, since)
        out.append(M.RootObservation(root, status, since, list(jobs), items))
    return out, nxt
