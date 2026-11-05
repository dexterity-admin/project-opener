"""CAD launch profiles (brief section 3.6).  Owner: builder 1 (CORE+HUB).

A profile is arguments + working folder + environment, named and shareable.
``build_command`` turns (item, profile) into what ``core.launcher`` starts.
``PRESETS`` hold argument templates per application; every switch in them must
be verified against the vendor documentation or a real run before shipping
(the brief's rule: never invent an instruction) - unverified presets stay out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver

# app -> {"label", "exe_hint", "args" template with {ITEM}, "note"}; filled by builder 1 with verified switches.
PRESETS: dict[str, dict[str, str]] = {}


@dataclass
class Command:
    exe: str
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)   # added to the inherited environment


def build_command(item: M.Item, profile: M.LaunchProfile | None, resolver: PathResolver) -> Command:
    """Resolve variables in exe/args/cwd/env; ``{ITEM}`` is the item's resolved path."""
    raise NotImplementedError("build_command")
