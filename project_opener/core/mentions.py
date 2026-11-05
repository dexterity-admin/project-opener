"""@mentions: parsing and expansion (brief section 3.2).

Pure string logic, shared by the hub (who receives what) and the shell's @
picker (what the user is typing).  A mention is ``@`` followed by a login or
group name: letters, digits, ``.``, ``-``, ``_``; it must start the text or
follow whitespace or an opening bracket, so ``name@company.com`` is not one.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from project_opener.core import models as M

MENTION_RE = re.compile(r"(?:^|(?<=[\s(\[{,;]))@([A-Za-z0-9][A-Za-z0-9._-]*)")


def parse_mentions(text: str) -> list[str]:
    """The names mentioned in ``text``, without "@", lower-cased, in order, without repeats.

    A trailing "." or "-" (end of a sentence) is not part of the name.
    """
    out: list[str] = []
    for m in MENTION_RE.finditer(text or ""):
        name = m.group(1).rstrip(".-_").lower()
        if name and name not in out:
            out.append(name)
    return out


def normalise_targets(targets: Iterable[str]) -> list[str]:
    """``["@Priya", "checkers", " @priya "]`` -> ``["priya", "checkers"]`` (the ``for`` list on the hub)."""
    out: list[str] = []
    for t in targets or ():
        name = str(t).strip().lstrip("@").strip().lower()
        if name and name not in out:
            out.append(name)
    return out


def expand(targets: Iterable[str], groups: Iterable[M.Group], known_users: Iterable[str] | None = None,
           exclude: str = "") -> list[str]:
    """Logins reached by ``targets`` (logins and group names), groups expanded one level.

    A name that is both a group and a login means the group.  With ``known_users``
    given, unknown names are dropped (a typo reaches nobody rather than a stranger's
    inbox folder).  ``exclude`` (usually the sender) is removed.
    """
    by_group = {g.name.lower(): [m.lower() for m in g.members] for g in groups}
    known = {u.lower() for u in known_users} if known_users is not None else None
    out: list[str] = []
    for name in normalise_targets(targets):
        logins = by_group.get(name, [name])
        for login in logins:
            if known is not None and login not in known:
                continue
            if login and login != exclude.lower() and login not in out:
                out.append(login)
    return out


def query_at_cursor(text: str, cursor: int) -> tuple[int, str] | None:
    """When the caret sits in a mention being typed, (start index of "@", query typed so far).

    The @ picker opens while this returns a value and narrows by the query.
    """
    cursor = max(0, min(len(text or ""), cursor))
    head = (text or "")[:cursor]
    m = re.search(r"(?:^|[\s(\[{,;])@([A-Za-z0-9._-]*)$", head)
    if not m:
        return None
    start = cursor - len(m.group(1)) - 1
    return start, m.group(1)


def insert_mention(text: str, cursor: int, login: str) -> tuple[str, int]:
    """Replace the mention being typed at ``cursor`` with ``@login `` and return (text, new cursor)."""
    found = query_at_cursor(text, cursor)
    if not found:
        ins = f"@{login} "
        return text[:cursor] + ins + text[cursor:], cursor + len(ins)
    start, _ = found
    ins = f"@{login} "
    tail = text[cursor:]
    return text[:start] + ins + tail.lstrip(" ") if tail.startswith(" ") else text[:start] + ins + tail, start + len(ins)
