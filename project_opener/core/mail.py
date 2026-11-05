"""Outlook: mail a bundle, mail a task (brief sections 3.3, 3.6).  Owner: builder 1 (CORE+HUB).

``Outlook.Application`` ``CreateItem(0)`` then ``Display()`` (never ``Send``: the user
sends).  Runs on a pool thread with its own ``CoInitialize``/``CoUninitialize``.
Without Outlook, falls back to a ``mailto:`` URL (subject + plain body, links as text).
Paths go out in portable form (drive letters -> UNC through the resolver).
"""
from __future__ import annotations

from dataclasses import dataclass

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver


@dataclass
class Draft:
    subject: str
    body_text: str
    body_html: str = ""
    to: str = ""


def bundle_draft(activity: M.Activity, resolver: PathResolver, link: str) -> Draft:
    """The activity's items as links plus a ``projectopener://activity/...`` link.  Pure."""
    raise NotImplementedError("bundle_draft")


def task_draft(task: M.Task, link: str, owner_name: str = "") -> Draft:
    raise NotImplementedError("task_draft")


def open_draft(draft: Draft, client: str = "outlook") -> bool:
    """Show the draft in Outlook (or the mailto: fallback).  True when something opened."""
    raise NotImplementedError("open_draft")
