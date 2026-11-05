"""Outlook: mail a bundle, mail a task (brief sections 3.3, 3.6).  Owner: builder 1 (CORE+HUB).

``Outlook.Application`` ``CreateItem(0)`` then ``Display()`` (never ``Send``: the user
sends).  Runs on a pool thread with its own ``CoInitialize``/``CoUninitialize``.
Without Outlook, falls back to a ``mailto:`` URL (subject + plain body, links as text).
Paths go out in portable form (drive letters -> UNC through the resolver).
"""
from __future__ import annotations

import html
import logging
import os
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver
from project_opener.core.tasks import due_text

log = logging.getLogger(__name__)

MAILTO_MAX = 1900          # Windows shell + most mail clients cut mailto: URLs around 2,000 characters


@dataclass
class Draft:
    subject: str
    body_text: str
    body_html: str = ""
    to: str = ""


def portable_path(path: str, resolver: PathResolver) -> str:
    """The path a colleague can open: variables expanded, then a drive letter turned into UNC."""
    if (path or "").lower().startswith(("http://", "https://", "mailto:", "ftp://")):
        return path
    res = resolver.resolve(path)
    return resolver.portable(res.resolved if not res.unresolved else path)


def file_url(path: str) -> str:
    r"""``\\nas01\Project\a b.pdf`` -> ``file://nas01/Project/a%20b.pdf``; URLs unchanged."""
    if "://" in path or path.lower().startswith("mailto:"):
        return path
    p = path.replace("\\", "/")
    if p.startswith("//"):
        return "file:" + quote(p, safe="/:")
    return "file:///" + quote(p, safe="/:")


def bundle_draft(activity: M.Activity, resolver: PathResolver, link: str) -> Draft:
    """The activity's items as links plus a ``projectopener://activity/...`` link.  Pure."""
    items = activity.enabled_items
    lines = [f"{activity.name}", ""]
    rows_html = []
    for it in items:
        target = portable_path(it.path, resolver)
        lines.append(f"- {it.display_name}: {target}")
        rows_html.append(f'<li>{html.escape(it.display_name)}: <a href="{html.escape(file_url(target))}">'
                         f"{html.escape(target)}</a></li>")
    if not items:
        lines.append("(no items)")
    lines += ["", f"Open in Project Opener: {link}"] if link else []
    body_html = (f"<p><b>{html.escape(activity.name)}</b></p><ul>{''.join(rows_html) or '<li>(no items)</li>'}</ul>"
                 + (f'<p>Open in Project Opener: <a href="{html.escape(link)}">{html.escape(link)}</a></p>'
                    if link else ""))
    count = len(items)
    subject = f"{activity.name} - {count} item{'s' if count != 1 else ''}"
    return Draft(subject, "\n".join(lines), body_html)


def task_draft(task: M.Task, link: str, owner_name: str = "", done_by_name: str = "") -> Draft:
    """The task as a mail: title, owner and the one who finished it by display name (the login when no
    name is given), due date, what it is for, the note, and the projectopener:// link.  Pure."""
    lines = [f"Task: {task.title}"]
    if task.owner:
        lines.append(f"Owner: {owner_name or task.owner}")
    if task.due:
        lines.append(f"Due: {task.due} ({due_text(task.due)})")
    if task.link and task.link.title:
        lines.append(f"For: {task.link.title}" + (f" ({task.link.job_number})" if task.link.job_number else ""))
    if task.done:
        lines.append(f"Done: {task.done_at[:10]} by {done_by_name or task.done_by}")
    if task.note:
        lines += ["", task.note]
    if link:
        lines += ["", f"Open in Project Opener: {link}"]
    paras = [f"<p>{html.escape(line)}</p>" for line in lines if line and not line.startswith("Open in Project Opener")]
    if link:
        paras.append(f'<p>Open in Project Opener: <a href="{html.escape(link)}">{html.escape(link)}</a></p>')
    body_html = "".join(paras)
    return Draft(f"Task: {task.title}", "\n".join(lines), body_html)


def mailto_url(draft: Draft) -> str:
    """``mailto:`` with subject and plain body, cut to stay under the URL length limit."""
    body = draft.body_text
    url = f"mailto:{quote(draft.to)}?subject={quote(draft.subject)}&body={quote(body)}"
    while len(url) > MAILTO_MAX and body:
        body = body[: max(0, len(body) - max(40, len(url) - MAILTO_MAX))].rstrip() + "\n..."
        url = f"mailto:{quote(draft.to)}?subject={quote(draft.subject)}&body={quote(body)}"
        if body == "\n...":
            break
    return url


def _open_url(url: str) -> bool:
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
        return True
    return webbrowser.open(url)  # pragma: no cover


def _outlook_display(draft: Draft) -> bool:
    """Outlook through COM on this thread (initialised and released here)."""
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        return False
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.Subject = draft.subject
        if draft.to:
            mail.To = draft.to
        if draft.body_html:
            mail.HTMLBody = draft.body_html
        else:
            mail.Body = draft.body_text
        mail.Display(False)
        return True
    except Exception as exc:  # noqa: BLE001 - Outlook absent, profile not set up, ...
        log.info("Outlook not available (%s); using mailto:", exc)
        return False
    finally:
        pythoncom.CoUninitialize()


def open_draft(draft: Draft, client: str = "outlook", *, outlook: Callable[[Draft], bool] | None = None,
               open_url: Callable[[str], bool] | None = None) -> bool:
    """Show the draft in Outlook (or the mailto: fallback).  True when something opened.

    ``outlook`` and ``open_url`` replace the COM call and the shell in tests.
    """
    if client != "mailto":
        try:
            if (outlook or _outlook_display)(draft):
                return True
        except Exception as exc:  # noqa: BLE001
            log.info("Outlook draft failed (%s); using mailto:", exc)
    try:
        return bool((open_url or _open_url)(mailto_url(draft)))
    except Exception as exc:  # noqa: BLE001
        log.warning("mailto: failed: %s", exc)
        return False
