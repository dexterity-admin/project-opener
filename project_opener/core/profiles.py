"""CAD launch profiles (brief section 3.6).  Owner: builder 1 (CORE+HUB).

A profile is arguments + working folder + environment, named and shareable.
``build_command`` turns (item, profile) into what ``core.launcher`` starts.
``PRESETS`` hold argument templates per application; every switch in them must
be verified against the vendor documentation or a real run before shipping
(the brief's rule: never invent an instruction) - unverified presets stay out.

The presets below therefore carry no vendor switches at all: only ``"{ITEM}"``,
the document path as the first argument, which is what Explorer's own "open"
verb passes to each of these programs.  Viewpoints, seeds, workspaces and
AutoCAD profiles are added by the user (or the office) to a profile's ``args``
once they have been checked on a real run.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver, normalise_var_name

# app -> {"label", "exe_hint", "args" template with {ITEM}, "note"}.
PRESETS: dict[str, dict[str, str]] = {
    "navisworks": {"label": "Navisworks", "exe_hint": "Roamer.exe", "args": '"{ITEM}"',
                   "note": "Opens the model given as {ITEM}. Add switches only after checking them on a real run."},
    "microstation": {"label": "MicroStation", "exe_hint": "ustation.exe", "args": '"{ITEM}"',
                     "note": "Opens the design file given as {ITEM}. Workspace/user switches: add once verified."},
    "autocad": {"label": "AutoCAD", "exe_hint": "acad.exe", "args": '"{ITEM}"',
                "note": "Opens the drawing given as {ITEM}. Profile switches: add once verified."},
    "caesar": {"label": "CAESAR II", "exe_hint": "", "args": '"{ITEM}"',
               "note": "Opens the job given as {ITEM}."},
    "other": {"label": "Other", "exe_hint": "", "args": "", "note": ""},
}

_VAR_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


@dataclass
class Command:
    exe: str
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)   # added to the inherited environment
    unresolved: list[str] = field(default_factory=list)  # {VARIABLES} this PC does not define


def expand(text: str, resolver: PathResolver, item_path: str = "", unresolved: list[str] | None = None) -> str:
    """Replace ``{ITEM}``, ``{VARIABLES}`` and ``%ENV%`` in free text (no path normalisation)."""
    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name.upper() == "ITEM":
            return item_path
        key = normalise_var_name(name)
        if key in resolver.variables:
            return resolver.variables[key]
        if unresolved is not None and key not in unresolved:
            unresolved.append(key)
        return m.group(0)
    return os.path.expandvars(_VAR_RE.sub(sub, text or ""))


def split_args(text: str) -> list[str]:
    """Windows-style split: quoted parts stay together and lose their quotes."""
    if not text.strip():
        return []
    out = []
    for tok in shlex.split(text, posix=False):
        if len(tok) >= 2 and tok[0] == tok[-1] == '"':
            tok = tok[1:-1]
        out.append(tok)
    return out


def build_command(item: M.Item, profile: M.LaunchProfile | None, resolver: PathResolver) -> Command:
    """Resolve variables in exe/args/cwd/env; ``{ITEM}`` is the item's resolved path."""
    unresolved: list[str] = []
    item_res = resolver.resolve(item.path)
    for u in item_res.unresolved or []:
        unresolved.append(u)
    item_path = item_res.resolved
    if profile is None:
        exe = item_path
        args = [expand(a, resolver, item_path, unresolved) for a in split_args(item.args)]
        return Command(exe, args, os.path.dirname(exe), {}, unresolved)
    if profile.exe.strip():
        exe_res = resolver.resolve(expand(profile.exe, resolver, item_path, unresolved))
        exe = exe_res.resolved
    else:
        exe = item_path
    # Split first, then expand, so a path with spaces in {ITEM} stays one argument.
    args = [expand(a, resolver, item_path, unresolved) for a in split_args(profile.args)]
    if not profile.args.strip() and item.args.strip():
        args = [expand(a, resolver, item_path, unresolved) for a in split_args(item.args)]
    cwd = expand(profile.cwd, resolver, item_path, unresolved) if profile.cwd.strip() else os.path.dirname(exe)
    env = {str(k): expand(str(v), resolver, item_path, unresolved) for k, v in profile.env.items() if str(k).strip()}
    return Command(exe, args, cwd, env, unresolved)
