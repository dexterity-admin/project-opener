"""Office-wide path health: ``watch/<user>.json`` (a ``HealthObservation``).  Owner: builder 1 (CORE+HUB).

Each PC writes what it saw (only its own file); every PC merges all files into
"nas01 down since 09:40, seen by 3 PCs, 14 jobs affected".  ``since`` is the
earliest time any fresh observation (younger than ``HUB_STALE_S``) reports the
current status.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from project_opener.core import models as M


@dataclass
class OfficeRoot:
    root: str
    status: str
    since: str = ""
    seen_by: list[str] = field(default_factory=list)     # logins
    jobs: list[str] = field(default_factory=list)


class HealthBoard:
    def __init__(self, hub_root: Path | None, user: str):
        self.root = Path(hub_root) / "watch" if hub_root else None
        self.user = user

    def write(self, observation: M.HealthObservation) -> None:
        raise NotImplementedError("HealthBoard.write")

    def read_all(self) -> list[M.HealthObservation]:
        raise NotImplementedError("HealthBoard.read_all")

    def merged(self) -> list[OfficeRoot]:
        raise NotImplementedError("HealthBoard.merged")
