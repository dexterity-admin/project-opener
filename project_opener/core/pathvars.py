"""Path variables and drive-letter portability.

Two office machines rarely map the same share to the same letter.  A project
shared through the Team Hub therefore stores paths in *portable* form where
possible:

* ``{SERVER_ROOT}\\P12513\\ISO`` - a user-defined variable, resolved per machine;
* ``\\\\nas01\\Project\\P12513`` - a UNC path, which works everywhere.

``PathResolver.resolve`` expands variables and, when a mapped drive letter is
not present on this machine, swaps it for the UNC path recorded alongside it.
``PathResolver.portable`` does the reverse when publishing: it rewrites a
local drive letter into a UNC path using the machine's own drive map.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from project_opener.core import winutil

VAR_RE = re.compile(r"\{([A-Z0-9_]+)\}")
DRIVE_RE = re.compile(r"^([A-Za-z]):([\\/]|$)")


def normalise_var_name(name: str) -> str:
    name = name.strip().upper().strip("{}")
    name = re.sub(r"[^A-Z0-9_]+", "_", name)
    return f"{{{name}}}" if name else ""


@dataclass
class Resolved:
    original: str
    resolved: str
    used_variable: bool = False
    remapped_drive: bool = False
    unresolved: list[str] | None = None


class PathResolver:
    def __init__(self, variables: dict[str, str] | None = None, drive_map: dict[str, str] | None = None):
        self.variables = {normalise_var_name(k): v for k, v in (variables or {}).items() if normalise_var_name(k)}
        self._drive_map = drive_map

    # ------------------------------------------------------------- drive map
    @property
    def drive_map(self) -> dict[str, str]:
        if self._drive_map is None:
            try:
                self._drive_map = {k.upper(): v.rstrip("\\") for k, v in winutil.mapped_drives().items()}
            except Exception:
                self._drive_map = {}
        return self._drive_map

    def refresh_drive_map(self) -> None:
        self._drive_map = None

    # --------------------------------------------------------------- resolve
    def resolve(self, path: str) -> Resolved:
        if not path:
            return Resolved(path, path)
        out = path
        used = False
        unresolved: list[str] = []
        for m in VAR_RE.finditer(path):
            key = "{" + m.group(1) + "}"
            if key in self.variables:
                out = out.replace(key, self.variables[key])
                used = True
            else:
                unresolved.append(key)
        # Environment variables like %USERPROFILE% are also allowed.
        out = os.path.expandvars(out)
        remapped = False
        if winutil.IS_WIN and not out.lower().startswith(("http://", "https://", "mailto:", "ftp://")):
            dm = DRIVE_RE.match(out)
            if dm:
                letter = dm.group(1).upper() + ":"
                if not os.path.exists(letter + "\\"):
                    # Letter not mapped here: find a UNC for it via variables.
                    unc = self._unc_for_letter(letter)
                    if unc:
                        out = unc + out[2:]
                        remapped = True
            out = os.path.normpath(out) if not out.startswith("\\\\") else "\\\\" + os.path.normpath(out[2:])
        return Resolved(path, out, used, remapped, unresolved or None)

    def _unc_for_letter(self, letter: str) -> str | None:
        """Look for a variable value that mentions the letter: {Z_DRIVE} = \\\\server\\share."""
        key = f"{{{letter[0]}_DRIVE}}"
        val = self.variables.get(key)
        if val and val.startswith("\\\\"):
            return val.rstrip("\\")
        return None

    # -------------------------------------------------------------- portable
    def portable(self, path: str) -> str:
        """Rewrite ``Z:\\x`` to ``\\\\server\\share\\x`` using this machine's drive map."""
        if not path or path.lower().startswith(("http", "mailto:", "ftp://")) or VAR_RE.search(path):
            return path
        dm = DRIVE_RE.match(path)
        if not dm:
            return path
        letter = dm.group(1).upper() + ":"
        unc = self.drive_map.get(letter)
        if unc:
            return unc + path[2:]
        return path

    def localise(self, path: str) -> str:
        """Rewrite a UNC path to the drive letter this machine maps it to (for display)."""
        if not path.startswith("\\\\"):
            return path
        low = path.lower()
        best = ""
        best_letter = ""
        for letter, unc in self.drive_map.items():
            u = unc.lower()
            if low.startswith(u) and len(u) > len(best):
                best, best_letter = u, letter
        if best:
            return best_letter + path[len(best):]
        return path

    def variable_suggestions(self) -> dict[str, str]:
        """Suggested {X_DRIVE} variables for every mapped drive on this machine."""
        return {f"{{{letter[0]}_DRIVE}}": unc for letter, unc in self.drive_map.items()}
