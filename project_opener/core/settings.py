"""User settings with typed defaults.

Secrets (the optional GitHub token) are stored encrypted with Windows DPAPI
so they are bound to the Windows user account; on other platforms they are
stored base64-obfuscated only, which is acceptable because the app is a
Windows product and non-Windows runs are for tests.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from project_opener import constants as C
from project_opener.core import winutil
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)


@dataclass
class Settings:
    theme: str = "dark"                 # dark | light | system
    accent: str = "#4F7DFF"
    density: str = "comfortable"        # comfortable | compact
    view_mode: str = "grid"             # grid | list
    sort_key: str = "smart"
    sidebar_collapsed: bool = False
    launch_delay_ms: int = 350          # pause between items so Windows keeps up
    confirm_launch_over: int = 8        # ask before opening more than N items
    minimise_to_tray: bool = True
    start_minimised: bool = False
    run_at_startup: bool = False
    auto_launch_on_start: bool = True
    show_toasts: bool = True
    window_geometry: str = ""
    display_name: str = ""
    role: str = ""
    # Team hub
    hub_path: str = ""
    hub_share_pulse: bool = True
    presence_udp: bool = True
    # Path variables: {"{SERVER_ROOT}": "\\\\192.168.0.200\\Project"}
    variables: dict[str, str] = field(default_factory=dict)
    # Updates
    update_channel: str = "stable"      # stable | all
    update_check: bool = True
    update_last_check: str = ""
    update_skip_version: str = ""
    github_token_enc: str = ""
    # Misc
    first_run_done: bool = False
    last_seen_version: str = ""

    # ------------------------------------------------------------ persistence
    @classmethod
    def load(cls, root: Path | None = None) -> Settings:
        root = root or C.data_dir()
        data = read_json(root / C.SETTINGS_FILE, {}) or {}
        s = cls()
        if isinstance(data, dict):
            valid = {f.name: f.type for f in fields(cls)}
            for k, v in data.items():
                if k in valid:
                    setattr(s, k, v)
        if not isinstance(s.variables, dict):
            s.variables = {}
        s._root = root  # type: ignore[attr-defined]
        return s

    def save(self) -> None:
        root = getattr(self, "_root", None) or C.data_dir()
        write_json_atomic(root / C.SETTINGS_FILE, asdict(self))

    # ---------------------------------------------------------------- secrets
    @property
    def github_token(self) -> str:
        if not self.github_token_enc:
            return ""
        try:
            return winutil.unprotect(self.github_token_enc)
        except Exception as exc:  # pragma: no cover
            log.warning("could not decrypt token: %s", exc)
            return ""

    @github_token.setter
    def github_token(self, value: str) -> None:
        self.github_token_enc = winutil.protect(value) if value else ""

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("github_token_enc", None)
        return d
