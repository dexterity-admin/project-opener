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
COMPANY_SHORT = "Dexterity Design"
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

SCHEMA_VERSION = 3


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
