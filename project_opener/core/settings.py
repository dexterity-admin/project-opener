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


# "Never captured" by default: the office's chat apps only (juror T2-2).  4.0 betas also listed claude.exe; an
# untouched old default is moved to this one on load.
IGNORE_DEFAULT: tuple[dict[str, str], ...] = (
    {"process": "ms-teams.exe"}, {"process": "teams.exe"}, {"process": "cliq.exe"}, {"process": "zoho cliq.exe"},
)
_IGNORE_DEFAULT_BETA = [{"process": "claude.exe"}, *IGNORE_DEFAULT]


@dataclass
class Settings:
    theme: str = "dark"                 # dark | light | system
    accent: str = "#0E7C5B"
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
    # Path variables: {"{SERVER_ROOT}": "\\\\nas01\\Project"}
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

    # ------------------------------------------------------------------ v4
    # Shell and motion (docs/V4-ARCHITECTURE.md section 6; spikes/quick/REPORT.md fallback rule)
    shell: str = "widgets"              # widgets (3.2) | quick (4.0); ``--v4`` forces quick
    motion: str = "auto"                # auto | rich | purposeful | off (the user's choice)
    motion_reduced_to: str = ""         # set by the runtime guard ("purposeful" | "off"); auto never climbs back
    render_backend: str = "auto"        # auto | gpu | software
    gpu_probe: dict[str, str] = field(default_factory=dict)   # adapter name -> "ok" | "failed" | "basic"
    # Capture (brief 3.1)
    capture_enabled: bool = True        # the global switch; Activity.capture_enabled is the per-activity one
    capture_interval_s: int = 3
    capture_browser_urls: bool = True   # UI Automation on Chromium windows (active tab only)
    capture_ignore: list[dict[str, str]] = field(default_factory=lambda: [dict(r) for r in IGNORE_DEFAULT])
    # rules: {"process": ..., "title": glob (optional)}; the office's chat apps (Teams, Cliq) by default
    open_office_via_com: bool = True    # Office files through COM (no Protected View stall on the share)
    # Snapshot surfaces (brief 3.8)
    pill_enabled: bool = True
    settings_tab: str = ""            # the Settings page's last tab (remembered across restarts)
    pill_rest_style: str = "pill"       # pill | edge
    pill_pinned: bool = False           # show even when no activity runs (offers Start from what's open)
    pill_positions: dict[str, dict[str, Any]] = field(default_factory=dict)  # monitor-layout key -> {edge, offset, monitor}
    hotkeys_enabled: bool = True
    hotkeys: dict[str, str] = field(default_factory=lambda: dict(C.HOTKEY_DEFAULTS))
    explorer_verb: bool = True          # "Add to running activity" on files and folders
    sendto_entry: bool = True           # Send to > Project Opener
    hide_when_fullscreen: bool = True   # full screen, presentation, remote desktop, Do not disturb
    # People and integrations (brief 3.2, 3.5, 3.6)
    email: str = ""                     # used to look up the Cliq user id
    cliq_user_id: str = ""
    cliq_api_base: str = "https://cliq.zoho.in/api/v2"
    cliq_bot: str = ""                  # bot unique name
    cliq_token_enc: str = ""            # DPAPI blob of the office bot token (shared service account)
    notify_cliq_default: bool = True    # DM me on mention / task / watcher hits when linked
    mail_client: str = "outlook"        # outlook | mailto

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
        for name in ("gpu_probe", "pill_positions"):
            if not isinstance(getattr(s, name), dict):
                setattr(s, name, {})
        if not isinstance(s.hotkeys, dict):
            s.hotkeys = dict(C.HOTKEY_DEFAULTS)
        else:
            s.hotkeys = {**C.HOTKEY_DEFAULTS, **{str(k): str(v) for k, v in s.hotkeys.items()}}
        if not isinstance(s.capture_ignore, list) or s.capture_ignore == _IGNORE_DEFAULT_BETA:
            s.capture_ignore = cls().capture_ignore
        if s.accent in ("#4F7DFF", "#2F5BFF"):   # 3.0 default blue -> 3.1 default (docs/DESIGN.md)
            s.accent = cls.accent
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

    @property
    def cliq_token(self) -> str:
        if not self.cliq_token_enc:
            return ""
        try:
            return winutil.unprotect(self.cliq_token_enc)
        except Exception as exc:  # pragma: no cover
            log.warning("could not decrypt Cliq token: %s", exc)
            return ""

    @cliq_token.setter
    def cliq_token(self, value: str) -> None:
        self.cliq_token_enc = winutil.protect(value) if value else ""

    # ------------------------------------------------------------------ alias
    @property
    def update_auto(self) -> bool:
        """Alias of ``update_check`` (the name the auto-update timer code uses)."""
        return self.update_check

    @update_auto.setter
    def update_auto(self, value: bool) -> None:
        self.update_check = bool(value)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("github_token_enc", None)
        d.pop("cliq_token_enc", None)
        return d
