"""Dexterity Connect, the office messenger: share a project into a conversation.

Project Opener builds a ``dexconnect://share`` link and hands it to Windows. Dexterity Connect
shows a confirmation with the project's name and a ``projectopener://open/<id>`` link filled in;
the person picks who it is for and presses Share. Anyone who has the same project (from the
Team Hub or a colleague) opens it from that link with one click.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote, urlencode

from ..constants import URI_SCHEME
from . import models as M

CONNECT_SCHEME = "dexconnect"


def open_link(project: M.Project) -> str:
    """The link that opens this project in Project Opener."""
    return f"{URI_SCHEME}://open/{quote(project.id, safe='')}"


def share_text(project: M.Project) -> str:
    lines = [f"**{project.title}**"]
    if project.client.strip() and project.client.strip() not in project.title:
        lines.append(f"Client: {project.client.strip()}")
    if project.description.strip():
        lines.append(project.description.strip()[:500])
    enabled = len(project.enabled_items)
    if enabled:
        lines.append(f"{enabled} item{'s' if enabled != 1 else ''} to open")
    return "\n".join(lines)


def share_url(project: M.Project, to: str | None = None) -> str:
    """``dexconnect://share?…`` for this project (Connect asks before sending anything)."""
    params: list[tuple[str, str]] = [
        ("from", "Project Opener"),
        ("text", share_text(project)),
        ("title", "Open in Project Opener"),
        ("link", open_link(project)),
    ]
    if to:
        params.append(("to", to))
    return f"{CONNECT_SCHEME}://share?{urlencode(params, quote_via=quote)}"


def connect_installed() -> bool:
    """Is Dexterity Connect installed for this user (its link scheme is registered)?"""
    if sys.platform != "win32":  # pragma: no cover - Windows only
        return False
    import winreg  # noqa: PLC0415

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"Software\Classes\{CONNECT_SCHEME}"):
                return True
        except OSError:
            continue
    return False


def share(project: M.Project, to: str | None = None) -> bool:
    """Open the share dialog in Dexterity Connect. False when Connect is not installed."""
    if not connect_installed():
        return False
    os.startfile(share_url(project, to))  # type: ignore[attr-defined]  # noqa: S606
    return True
