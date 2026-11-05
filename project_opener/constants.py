"""Paths, identifiers and tunables shared by every layer.

Nothing here imports Qt, so the constants can be used by tests, the build
tooling and the installer script generator alike.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from project_opener import __app_name__, __company__, __version__

APP_NAME = __app_name__
APP_ID = "ProjectOpener"
COMPANY = __company__
COMPANY_SHORT = "Dexterity Design Services"
VERSION = __version__

# GitHub repository the updater talks to.  Releases are public, so no token is
# needed; one may be added (stored encrypted with DPAPI) for a higher API rate
# limit.  Offline machines use the LAN mirror described in docs/UPDATES.md.
GITHUB_OWNER = "dexterity-admin"
GITHUB_REPO = "project-opener"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

# Single-instance IPC name and the URI scheme used for deep links.
SINGLE_INSTANCE_KEY = "DexterityDesign.ProjectOpener.v3"
URI_SCHEME = "projectopener"

# LAN presence beacon (UDP broadcast).  Optional; the hub heartbeat is the
# primary presence mechanism because SMB always works in the office.
PRESENCE_PORT = 48620
PRESENCE_INTERVAL_S = 15
PRESENCE_STALE_S = 90

# Team hub heartbeat written to <hub>/users/<user>.json
HUB_HEARTBEAT_S = 60
HUB_STALE_S = 180

# Automatic update checks
UPDATE_CHECK_INTERVAL_H = 4

SCHEMA_VERSION = 4
HUB_SCHEMA_V4 = 2           # hub files written by 4.x; readers accept 1 and 2

# ------------------------------------------------------------------- v4
# Single instance for the Qt Quick shell.  Different from the 3.x key on purpose
# while ``--v4`` is a development flag, so a v4 run never forwards to an
# installed 3.2 and exits.  At integration (one shell) the app keeps this key.
SINGLE_INSTANCE_KEY_V4 = "DexterityDesign.ProjectOpener.v4"
IPC_PROTOCOL = 2            # JSON lines over the local socket (project_opener.ipc)

# Capture (brief 3.1, spikes/capture/REPORT.md section 5)
CAPTURE_INTERVAL_S = 3      # EnumWindows pass
CAPTURE_FULL_REFRESH_S = 30  # full re-identification
CAPTURE_SNAPSHOT_WRITE_MIN_S = 10  # live snapshot written at most this often (and only on change)
RESTORE_SETTLE_S = 25
CHECKPOINTS_KEPT = 10
RUNNING_HEARTBEAT_S = 60    # RunningMarker.last_seen refresh

# Global hotkeys (RegisterHotKey ids; app range 0x0000-0xBFFF)
HOTKEY_SNAPSHOT = 0xB001
HOTKEY_ADD_WINDOW = 0xB002
HOTKEY_PANEL = 0xB003
HOTKEY_PALETTE = 0xB004
HOTKEY_DEFAULTS = {
    "snapshot": "Ctrl+Alt+S",
    "add_window": "Ctrl+Alt+A",
    "panel": "Ctrl+Alt+P",
    "palette": "Ctrl+Alt+K",
}
HOTKEY_IDS = {"snapshot": HOTKEY_SNAPSHOT, "add_window": HOTKEY_ADD_WINDOW,
              "panel": HOTKEY_PANEL, "palette": HOTKEY_PALETTE}
ADD_WINDOW_DOUBLE_PRESS_MS = 1000

# Watchers and the hub additions
WATCH_TICK_S = 15           # watcher engine tick; each folder watcher polls at its own interval
HUB_TASKS_REFRESH_S = 60
CLIQ_RETRY_S = 300

# Explorer integration (per-user, no admin)
EXPLORER_VERB = "ProjectOpener.AddToActivity"
SENDTO_NAME = "Project Opener.lnk"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) is True


def bundle_dir() -> Path:
    """Directory holding bundled resources (PyInstaller or source tree)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return bundle_dir().joinpath("resources", *parts)


def data_dir() -> Path:
    """Per-user data folder.  Overridable for tests via PO_DATA_DIR."""
    override = os.environ.get("PO_DATA_DIR")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("APPDATA", Path.home())) / "DexterityDesign" / APP_ID
    else:
        p = Path.home() / ".config" / "DexterityDesign" / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def legacy_v1_dir() -> Path:
    """Where Project Opener 1.x kept projects.json / auto_launch.json."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "ProjectOpener"
    return Path.home() / ".config" / "ProjectOpener"


WORKSPACE_FILE = "workspace.json"
SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.jsonl"
BACKUP_DIR = "backups"
LOG_DIR = "logs"
MAX_BACKUPS = 30
PRE_V4_BACKUP_PREFIX = "pre-v4-workspace-"   # never rotated (does not match workspace-*.json)

# v4 runtime files, all under data_dir()
SNAPSHOT_DIR = "snapshots"          # snapshots/<activity_id>.json: live snapshot + checkpoints
RUNNING_FILE = "running.json"       # RunningMarkers of activities that are running
LOCAL_TASKS_DIR = "tasks"           # tasks when no hub is configured (same format as hub tasks/)
WATCH_STATE_DIR = "watch-state"     # watch-state/<watcher_id>.json: last folder listing
ALERTS_FILE = "alerts.jsonl"        # alerts shown in the app (WatchEvent rows)
CLIQ_OUTBOX_FILE = "cliq-outbox.jsonl"  # undelivered Cliq messages, retried
IDENTITY_CACHE_FILE = "capture-ignore.json"  # per-process/title ignore rules chosen by the user
