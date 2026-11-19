"""The office board (Weekly Wrapped) and handovers, on the Team Hub folder.  Owner: po4-team.

Layout under the hub root (every writer owns its own files, as in ``lan.hub``)::

    board/<login>/<host>.json      this PC's weekly numbers for <login> (the last BOARD_WEEKS weeks);
                                   ``hidden`` = the person opted out (no numbers are written at all)
    handover/<id>.json             a handover, written only by the person going on leave
    handover/<id>.accepted.json    written only by the colleague who accepted it

A handover is "on" from ``start`` to ``end`` (local dates, inclusive) until the person who left marks it
``returned`` (back early, or the first start of their PC after ``end``).  Tasks change owner when the colleague
accepts and go back when it is returned; ``tasks_moved`` in the acceptance says which, so a task someone else
reassigned meanwhile is left alone.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from project_opener.core import models as M
from project_opener.core import wrapped as W
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)

BOARD_WEEKS = 6
SCHEMA = 1
_HOST_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(name: str) -> bool:
    from project_opener.lan.hub import safe_name
    return safe_name(name)


def host_file(host: str) -> str:
    return (_HOST_RE.sub("_", host or "pc") or "pc")[:63]


class TeamBoard:
    """Reads and writes the board and handover files through a ``TeamHub`` (its root, user and display name)."""

    def __init__(self, hub: Any):
        self.hub = hub

    @property
    def root(self) -> Path | None:
        return Path(self.hub.root) if getattr(self.hub, "configured", False) else None

    @property
    def me(self) -> str:
        return str(self.hub.user)

    # ------------------------------------------------------------ board
    def write_week(self, stats: dict[str, Any] | None, hidden: bool, name: str = "") -> bool:
        """This PC's file: the week's numbers merged into the last BOARD_WEEKS weeks; opted out = no numbers."""
        root = self.root
        if root is None or not _safe(self.me):
            return False
        path = root / "board" / self.me / f"{host_file(self.hub.host)}.json"
        old = read_json(path, {}) or {}
        weeks = dict(old.get("weeks") or {}) if isinstance(old, dict) and not hidden else {}
        if stats and not hidden:
            weeks[str(stats["week"])] = stats
        keep = sorted(weeks)[-BOARD_WEEKS:]
        data = {"schema": SCHEMA, "user": self.me, "host": self.hub.host, "name": name or self.hub.display_name,
                "hidden": bool(hidden), "updated_at": M.now_iso(), "weeks": {k: weeks[k] for k in keep}}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(path, data)
            return True
        except OSError as exc:
            log.warning("board write failed: %s", exc)
            return False

    def read_week(self, week: str, today: date) -> tuple[list[dict[str, Any]], set[str]]:
        """(one merged row per person who has numbers for ``week``, the logins who opted out).

        A person is hidden when any of their PCs says so: the switch is per PC, and opting out must win."""
        root = self.root
        if root is None:
            return [], set()
        parts: dict[str, list[dict[str, Any]]] = {}
        names: dict[str, str] = {}
        hidden: set[str] = set()
        try:
            people = [p for p in (root / "board").iterdir() if p.is_dir()]
        except OSError:
            return [], set()
        for folder in people:
            try:
                files = list(folder.glob("*.json"))
            except OSError:
                continue
            for f in files:
                d = read_json(f, None)
                if not isinstance(d, dict):
                    continue
                login = str(d.get("user") or folder.name).lower()
                if d.get("hidden"):
                    hidden.add(login)
                    continue
                if d.get("name"):
                    names[login] = str(d["name"])
                wk = (d.get("weeks") or {}).get(week)
                if isinstance(wk, dict) and wk.get("start"):
                    parts.setdefault(login, []).append(wk)
        rows = []
        for login, ps in parts.items():
            if login in hidden:
                continue
            row = W.merge_person(ps, today)
            row.update(login=login, name=names.get(login, login))
            rows.append(row)
        return rows, hidden

    # --------------------------------------------------------- handover
    def _hdir(self) -> Path | None:
        return self.root / "handover" if self.root is not None else None

    def create_handover(self, to_user: str, start: str, end: str, activities: list[dict[str, Any]],
                        tasks: list[M.Task], to_name: str = "", projects: list[dict[str, str]] | None = None) -> str:
        """Write ``handover/<id>.json`` and the colleague's inbox entry; returns the id ("" on failure)."""
        d = self._hdir()
        if d is None or not _safe(to_user) or to_user.lower() == self.me.lower():
            return ""
        hid = M.new_id()
        row = {"schema": SCHEMA, "id": hid, "from": self.me, "from_name": self.hub.display_name, "to": to_user,
               "to_name": to_name, "start": start, "end": end, "created_at": M.now_iso(), "state": "offered",
               "activities": activities, "projects": projects or [],
               "tasks": [{"id": t.id, "title": t.title, "due": t.due} for t in tasks]}
        try:
            d.mkdir(parents=True, exist_ok=True)
            write_json_atomic(d / f"{hid}.json", row)
        except OSError as exc:
            log.warning("handover write failed: %s", exc)
            return ""
        n_act, n_task = len(activities), len(tasks)
        what = ", ".join(x for x in (_plural(n_act, "activity", "activities"), _plural(n_task, "open task"))
                         if not x.startswith("0 "))
        self.hub._write_inbox(to_user, {"kind": "handover", "handover_id": hid,
                                        "title": f"Handover {_span(start, end)}",
                                        "text": f"{what or 'Nothing'} while {self.hub.display_name or self.me} is on leave"})
        return hid

    def handovers(self) -> list[dict[str, Any]]:
        """Every handover on the hub with its acceptance folded in (``accepted_by``, ``accepted_at``,
        ``tasks_moved``); newest first."""
        d = self._hdir()
        out: list[dict[str, Any]] = []
        if d is None:
            return out
        try:
            files = list(d.glob("*.json"))
        except OSError:
            return out
        acc: dict[str, dict[str, Any]] = {}
        for f in files:
            if f.name.endswith(".accepted.json"):
                a = read_json(f, None)
                if isinstance(a, dict):
                    acc[str(a.get("id") or f.name.split(".")[0])] = a
        for f in files:
            if f.name.endswith(".accepted.json"):
                continue
            h = read_json(f, None)
            if not isinstance(h, dict) or not h.get("from") or not h.get("to"):
                continue
            h = dict(h)
            a = acc.get(str(h.get("id")), {})
            h["accepted_by"] = str(a.get("by", ""))
            h["accepted_at"] = str(a.get("accepted_at", ""))
            h["tasks_moved"] = [str(x) for x in a.get("tasks_moved", []) or []]
            out.append(h)
        out.sort(key=lambda h: str(h.get("created_at", "")), reverse=True)
        return out

    def get(self, hid: str) -> dict[str, Any] | None:
        return next((h for h in self.handovers() if h.get("id") == hid), None)

    def accept(self, hid: str, tasks_moved: list[str]) -> bool:
        d = self._hdir()
        if d is None or not _safe(hid):
            return False
        try:
            write_json_atomic(d / f"{hid}.accepted.json", {"schema": SCHEMA, "id": hid, "by": self.me,
                                                           "accepted_at": M.now_iso(), "tasks_moved": tasks_moved})
            return True
        except OSError as exc:
            log.warning("handover accept failed: %s", exc)
            return False

    def mark_returned(self, hid: str) -> bool:
        """The person who left is back: their own file says so (only they write it)."""
        d = self._hdir()
        if d is None or not _safe(hid):
            return False
        p = d / f"{hid}.json"
        h = read_json(p, None)
        if not isinstance(h, dict) or str(h.get("from", "")).lower() != self.me.lower():
            return False
        h["state"], h["returned_at"] = "returned", M.now_iso()
        try:
            write_json_atomic(p, h)
            return True
        except OSError as exc:
            log.warning("handover return failed: %s", exc)
            return False


def is_on(h: dict[str, Any], today: date) -> bool:
    """On leave now under this handover: not returned and today within ``start``..``end``."""
    if h.get("state") == "returned":
        return False
    try:
        return date.fromisoformat(str(h["start"])) <= today <= date.fromisoformat(str(h["end"]))
    except (KeyError, ValueError):
        return False


def is_due_back(h: dict[str, Any], today: date) -> bool:
    """Past its end and not yet returned: the leaver's PC reverses it on its next refresh."""
    if h.get("state") == "returned":
        return False
    try:
        return today > date.fromisoformat(str(h["end"]))
    except (KeyError, ValueError):
        return False


def _plural(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _span(start: str, end: str) -> str:
    """"24 Nov – 28 Nov"; the raw strings when they are not dates."""
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return f"{start} – {end}"
    fa = f"{a.day} {a.strftime('%b')}"
    fb = f"{b.day} {b.strftime('%b')}"
    return fa if a == b else f"{fa} – {fb}"
