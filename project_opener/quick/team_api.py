"""``app.team``: Weekly Wrapped with the office board, the Office pulse, and Handover.  Owner: po4-team.

Counting lives in ``core.wrapped`` and the hub files in ``lan.teamboard``; this object runs them on the pool,
keeps the QML models, and does the two-sided handover steps:

* Wrapped: this PC's week from ``history.jsonl`` and the hub's tasks; the board file is rewritten on every
  refresh (opted out = a file that says ``hidden`` and carries no numbers).
* Office: the hub's peers (``app.hub.peers``) with a state each: active (in an activity or project), idle
  (signed in, nothing open), away (no heartbeat for ``HUB_STALE_S``), leave (a handover is on).
* Handover: the leaver writes it; the colleague accepts it from the inbox (``kind`` "handover"): the activities
  are added to their workspace and the open tasks change owner.  The leaver's "I'm back", or the first refresh
  on their PC after the end date, gives the tasks back; the colleague's PC then removes the copies it added
  that nobody changed.
* Nib's leave note (Dexterity Connect): when I noted leave there, the page is prefilled with its cover and first
  and last day (``nibLeave``).  When that leave starts, the handover is offered (a toast and the page) or done
  (``handover_on_leave``: offer | auto | off); when it ends or is cancelled in Nib, the work is handed back.  With
  no leave in Nib, or a cover who is not on the Team Hub, nothing is guessed: the page works as before.

Windows reopened: HOOK for the restore log (a parallel 4.0 change).  ``SnapshotStore.windows_reopened(start,
end) -> int`` is read when it exists; until then the number is None and the page says it is not counted yet.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from project_opener.core import models as M
from project_opener.core import wrapped as W
from project_opener.core.jsonio import read_json, read_jsonl, write_json_atomic
from project_opener.core.tasks import TaskStore, due_text, when_text
from project_opener.lan import teamboard as TB
from project_opener.lan.nib import LeaveWatch, login_of
from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

log = logging.getLogger(__name__)

BOARD_ROLES = ("login", "name", "initials", "hue", "place", "activitiesRun", "tasksClosed", "onTimeText",
               "dayStreak", "isMe")
OFFICE_ROLES = ("login", "displayName", "initials", "hue", "presence", "presenceText", "doing", "leaveText", "role",
                "seenText")
INCOMING_ROLES = ("handoverId", "fromLogin", "fromName", "spanText", "stateText", "accepted", "activityCount",
                  "taskCount", "taskTitles", "on")
RECEIVED_FILE = "handovers-received.json"
NIB_FILE = "nib-leave.json"        # {"handled": [Nib leave ids acted on], "links": {handover id: Nib leave id}}
REFRESH_S = 120
MIN_TICK_S = 60
STATE_ORDER = {"active": 0, "idle": 1, "leave": 2, "away": 3}


def span_text(start: str, end: str) -> str:
    return TB._span(start, end)


def _fingerprint(act: M.Activity | None) -> str:
    """What a colleague can change in a handed-over activity: its name, notes and items (opening it is not a
    change)."""
    if act is None:
        return ""
    return "|".join([act.name, act.notes, *(f"{i.path}*{int(i.enabled)}" for i in act.items)])


class TeamApi(ApiBase):
    wrappedChanged = Signal()
    boardChanged = Signal()
    officeChanged = Signal()
    handoverChanged = Signal()

    def __init__(self, app: Any):
        super().__init__(app)
        self._board = DictListModel(BOARD_ROLES, key="login", parent=self)
        self._office = DictListModel(OFFICE_ROLES, key="login", parent=self)
        self._incoming = DictListModel(INCOMING_ROLES, key="handoverId", parent=self)
        self._wrapped: dict[str, Any] = {}
        self._week_offset = 0
        self._board_sort = "tasks"
        self._board_rows: list[dict[str, Any]] = []
        self._board_hidden: set[str] = set()
        self._handovers: list[dict[str, Any]] = []
        self._mine: dict[str, Any] = {}
        self._nib_leave: dict[str, Any] = {}
        self._nib_rows: list[dict[str, Any]] | None = None      # None: Nib did not answer on the last refresh
        self._nib_watch: LeaveWatch | None = None
        self._office_counts: dict[str, int] = {}
        self._choices: dict[str, Any] = {"activities": [], "tasks": []}
        self._busy = False
        self._board_count = self._office_count = self._incoming_count = 0
        self._refreshing = False
        self._last = 0.0
        self._timer: QTimer | None = None
        self.today_fn = date.today               # tests pin the date

    # ------------------------------------------------------------- models
    @Property(QObject, constant=True)
    def board(self) -> DictListModel:
        return self._board

    @Property(QObject, constant=True)
    def office(self) -> DictListModel:
        return self._office

    @Property(QObject, constant=True)
    def incoming(self) -> DictListModel:
        """Handovers given to me that are not returned."""
        return self._incoming

    @Property("QVariantMap", notify=wrappedChanged)
    def wrapped(self) -> dict[str, Any]:
        return self._wrapped

    @Property("QVariantMap", notify=handoverChanged)
    def handover(self) -> dict[str, Any]:
        """My own handover that is not returned ({} when none)."""
        return self._mine

    @Property("QVariantMap", notify=handoverChanged)
    def nibLeave(self) -> dict[str, Any]:  # noqa: N802
        """My leave from Nib's leave note ({} when none): start, end, spanText, current, coverLogin (only a
        colleague on the Team Hub, else ""), coverName."""
        return self._nib_leave

    @Property("QVariantMap", notify=handoverChanged)
    def choices(self) -> dict[str, Any]:
        """What a new handover can carry: my activities and my open tasks."""
        return self._choices

    @Property("QVariantMap", notify=officeChanged)
    def officeCounts(self) -> dict[str, int]:  # noqa: N802
        return self._office_counts

    weekOffset = ro(int, "_week_offset", wrappedChanged)
    boardSort = ro(str, "_board_sort", boardChanged)
    busy = ro(bool, "_busy", handoverChanged)
    boardCount = ro(int, "_board_count", boardChanged)
    officeCount = ro(int, "_office_count", officeChanged)
    incomingCount = ro(int, "_incoming_count", handoverChanged)

    @Property(bool, notify=wrappedChanged)
    def showOnBoard(self) -> bool:  # noqa: N802
        return bool(getattr(self.ctx.settings, "board_show_me", True))

    @Property(bool, notify=wrappedChanged)
    def cliqReady(self) -> bool:  # noqa: N802
        s = self.ctx.settings
        return bool(getattr(s, "messages_via", "nib") == "cliq" and s.cliq_token_enc and s.cliq_bot)

    # ------------------------------------------------------------ helpers
    @property
    def ctx(self) -> Any:
        return self.app.ctx

    @property
    def me(self) -> str:
        return self.ctx.user

    def today(self) -> date:
        return self.today_fn()

    def _hub(self) -> Any:
        return self.ctx.hub

    def _tb(self) -> TB.TeamBoard:
        return TB.TeamBoard(self._hub())

    def _tasks_store(self) -> TaskStore | None:
        hub = self._hub()
        return TaskStore(hub.sub("tasks")) if hub.configured else None

    def _name(self, login: str) -> str:
        hub_api = getattr(self.app, "hub", None)
        if hub_api is not None and hasattr(hub_api, "name_for"):
            return hub_api.name_for(login)
        return login

    def _toast(self, title: str, body: str = "", level: str = "info") -> None:
        try:
            self.app.toast.emit(title, body, level)
        except Exception:  # noqa: BLE001
            log.info("%s: %s", title, body)

    def _received_path(self) -> Path:
        return Path(self.ctx.store.root) / RECEIVED_FILE

    def _windows_reopened(self, start: date, end: date) -> int | None:
        """HOOK (restore log): None until ``SnapshotStore.windows_reopened`` exists."""
        fn = getattr(getattr(self.app, "snapshots", None), "windows_reopened", None)
        if not callable(fn):
            return None
        try:
            n = fn(start, end)
            return int(n) if n is not None else None
        except Exception:  # noqa: BLE001
            log.debug("restore log read failed", exc_info=True)
            return None

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        sig = getattr(self.ctx, "hub_changed", None)
        if sig is not None:
            sig.connect(lambda _s: self._tick())
        peers = getattr(getattr(self.app, "hub", None), "peersChanged", None)
        if peers is not None:
            peers.connect(self._sync_office)
        changed = getattr(getattr(self.app, "settings", None), "changed", None)
        if changed is not None:
            changed.connect(self._on_setting)
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_S * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def shutdown(self) -> None:
        if self._timer:
            self._timer.stop()

    def _tick(self) -> None:
        """The hub's heartbeat: at most one refresh (and one board-file write) a minute."""
        if not self._last or time.monotonic() - self._last >= MIN_TICK_S:
            self.refresh()

    def _on_setting(self, key: str) -> None:
        if key in ("board_show_me", "hub_path", "display_name"):
            self._last = 0.0
            self.refresh()

    # -------------------------------------------------------------- slots
    @Slot()
    def refresh(self) -> None:
        """Count my week, write my board file, read the board and the handovers (all on the pool)."""
        if self._refreshing:
            return
        self._refreshing = True
        hub = self._hub()
        tb = self._tb()
        store = self.ctx.store
        settings = self.ctx.settings
        today = self.today()
        day = today + timedelta(weeks=self._week_offset)
        this_week = W.week_start(today)
        history_path = store.history_path
        me = self.me
        name = (settings.display_name or "").strip() or self._name(me)
        show = bool(getattr(settings, "board_show_me", True))
        watch = self._leave_watch()

        def work() -> dict[str, Any]:
            history = read_jsonl(history_path)
            ts = self._tasks_store()
            tasks = ts.all() if ts is not None else []
            start = W.week_start(day)
            mine = W.week_stats(history, tasks, me, day, today=today,
                                windows_reopened=self._windows_reopened(start, start + timedelta(days=6)))
            res: dict[str, Any] = {"mine": mine, "configured": hub.configured, "reachable": False,
                                   "board": [], "hidden": set(), "handovers": [], "nib_leave": None}
            if watch is not None:
                try:
                    res["nib_leave"] = watch.read(today.isoformat())
                except Exception:  # noqa: BLE001 - Nib is optional: a failure only means "Nib said nothing"
                    log.debug("Nib leave read failed", exc_info=True)
            if not hub.configured or not hub.reachable():
                return res
            res["reachable"] = True
            # the board file always carries this week (and keeps the earlier ones it has)
            cur = mine if W.week_start(day) == this_week else W.week_stats(
                history, tasks, me, today, today=today,
                windows_reopened=self._windows_reopened(this_week, this_week + timedelta(days=6)))
            tb.write_week(cur, hidden=not show, name=name)
            if mine is not cur:
                tb.write_week(mine, hidden=not show, name=name)
            res["board"], res["hidden"] = tb.read_week(mine["week"], today)
            res["handovers"] = tb.handovers()
            return res

        def done(res: dict[str, Any]) -> None:
            self._refreshing = False
            self._last = time.monotonic()
            self._apply(res)

        def fail(exc: Exception) -> None:
            self._refreshing = False
            log.warning("team refresh failed: %s", exc)

        self.app.run_async(work, done, fail)

    @Slot(int)
    def setWeekOffset(self, offset: int) -> None:  # noqa: N802
        offset = max(-(TB.BOARD_WEEKS - 1), min(0, int(offset)))
        if offset != self._week_offset:
            self._week_offset = offset
            self.wrappedChanged.emit()
            self.refresh()

    @Slot(str)
    def setBoardSort(self, by: str) -> None:  # noqa: N802
        if by in W.BOARD_SORTS and by != self._board_sort:
            self._board_sort = by
            self._sync_board()
            self.boardChanged.emit()

    @Slot(bool)
    def setShowOnBoard(self, on: bool) -> None:  # noqa: N802
        """The Settings switch (also reachable from the Wrapped page)."""
        api = getattr(self.app, "settings", None)
        if api is not None and hasattr(api, "setValue"):
            api.setValue("board_show_me", bool(on))            # emits changed -> refresh
        else:
            self.ctx.settings.board_show_me = bool(on)
            self.ctx.settings.save()
            self.refresh()
        self.wrappedChanged.emit()

    @Slot(str)
    def postToCliq(self, channel: str) -> None:  # noqa: N802
        """Post my week to a Cliq channel through the office bot (the watchers' Cliq client)."""
        ch = (channel or "").strip().lstrip("#")
        st = self._wrapped
        if not ch or not st.get("start"):
            return
        if getattr(self.ctx.settings, "wrapped_channel", "") != ch:
            self.ctx.settings.wrapped_channel = ch
            self.ctx.settings.save()
        text = W.cliq_text(st.get("name") or self._name(self.me), st.get("raw") or {}, int(st.get("place") or 0),
                           int(st.get("of") or 0))
        watchers = getattr(self.app, "watchers", None)
        if watchers is None:
            self._toast("Cliq is not set up", "Add the office bot in Settings > Cliq.", "warning")
            return
        cliq = watchers.dispatcher().cliq

        def work() -> Any:
            return cliq.send("channel", ch, text)

        def done(res: Any) -> None:
            if getattr(res, "ok", False):
                self._toast("Posted to Cliq", f"#{ch}", "success")
            elif getattr(res, "retry", False):
                self._toast("Cliq is not reachable", "The post is queued and goes when Cliq answers.", "warning")
            else:
                self._toast("Cliq refused the post", getattr(res, "message", "") or "", "error")

        self.app.run_async(work, done, lambda e: self._toast("Cliq post failed", str(e), "error"))

    # -------------------------------------------------------------- apply
    def _apply(self, res: dict[str, Any]) -> None:
        mine = res["mine"]
        self._board_rows = list(res.get("board") or [])
        self._board_hidden = set(res.get("hidden") or set())
        self._handovers = list(res.get("handovers") or [])
        self._nib_rows = res.get("nib_leave")
        self._sync_nib_leave()
        self._sync_board()
        self._set_wrapped(mine, res)
        self._sync_handovers()
        self._sync_office()
        self._sync_choices()
        self.boardChanged.emit()
        self._after_refresh()

    def _set_wrapped(self, st: dict[str, Any], res: dict[str, Any]) -> None:
        start = date.fromisoformat(st["start"])
        end = date.fromisoformat(st["end"])
        today = self.today()
        place, of = 0, len(self._board_rows)
        for r in self._board.rows:
            if r["isMe"]:
                place = int(r["place"])
        rate = st.get("on_time_rate")
        reopened = st.get("windows_reopened")
        name = (self.ctx.settings.display_name or "").strip() or self._name(self.me)
        self._wrapped = {
            "name": name, "week": st["week"], "start": st["start"], "end": st["end"],
            "rangeText": span_text(st["start"], st["end"]),
            "title": "This week" if self._week_offset == 0 else "Last week" if self._week_offset == -1
            else f"Week of {start.day} {start.strftime('%b')}",
            "current": start <= today <= end,
            "activitiesRun": int(st["activities_run"]), "tasksClosed": int(st["tasks_closed"]),
            "tasksWithDue": int(st["tasks_with_due"]), "tasksOnTime": int(st["tasks_on_time"]),
            "onTimeRate": -1 if rate is None else int(rate),
            "onTimeLine": ("no closed task had a due date" if rate is None
                           else f"{st['tasks_on_time']} of {st['tasks_with_due']} with a due date"),
            "dayStreak": int(st["day_streak"]), "squares": list(st["squares"]),
            "squaresToday": (today - start).days if start <= today <= end else -1,
            "windowsReopened": -1 if reopened is None else int(reopened),
            "place": place, "of": of, "hub": bool(res.get("configured")), "reachable": bool(res.get("reachable")),
            "raw": {k: st[k] for k in ("start", "activities_run", "tasks_closed", "on_time_rate", "day_streak",
                                       "windows_reopened")},
        }
        self.wrappedChanged.emit()

    def _sync_board(self) -> None:
        from project_opener.quick.hub_api import hue, initials
        me = self.me.lower()
        rows = W.rank([dict(r) for r in self._board_rows], self._board_sort)
        out = []
        for r in rows:
            login = str(r["login"])
            name = self._name(login) if login != r.get("name") else str(r.get("name"))
            if login.lower() == me:
                name = (self.ctx.settings.display_name or "").strip() or name
            rate = r.get("on_time_rate")
            out.append({"login": login, "name": name, "initials": initials(name), "hue": hue(login),
                        "place": int(r["place"]), "activitiesRun": int(r.get("activities_run") or 0),
                        "tasksClosed": int(r.get("tasks_closed") or 0),
                        "onTimeText": "–" if rate is None else f"{rate} %",
                        "dayStreak": int(r.get("day_streak") or 0), "isMe": login.lower() == me})
        self._board.reset(out)
        self._board_count = len(out)

    # ---- office
    def _leave_for(self, login: str, today: date) -> dict[str, Any] | None:
        low = login.lower()
        for h in self._handovers:
            if str(h.get("from", "")).lower() == low and TB.is_on(h, today):
                return h
        return None

    @Slot()
    def _sync_office(self) -> None:
        hub_api = getattr(self.app, "hub", None)
        peers = list(getattr(getattr(hub_api, "peers", None), "rows", []) or [])
        users = getattr(hub_api, "_users", {}) or {}
        today = self.today()
        rows = []
        counts = {"active": 0, "idle": 0, "away": 0, "leave": 0}
        for p in peers:
            login = str(p.get("login", ""))
            doing = str(p.get("doing") or "")
            leave = self._leave_for(login, today)
            if leave is not None:
                state = "leave"
            elif p.get("online"):
                state = "active" if doing else "idle"
            else:
                state = "away"
            counts[state] += 1
            to_name = self._name(str(leave.get("to", ""))) if leave else ""
            seen = str((users.get(login.lower()) or {}).get("iso") or "")
            rows.append({
                "login": login, "displayName": p.get("displayName") or self._name(login),
                "initials": p.get("initials") or "?", "hue": p.get("hue") or 0, "presence": state,
                "presenceText": {"active": "active", "idle": "idle", "away": "away", "leave": "on leave"}[state],
                "doing": doing if state == "active" else "",
                "leaveText": (f"on leave · handed to {to_name}" if leave else ""),
                "role": p.get("role") or "",
                "seenText": (f"until {span_text(leave['end'], leave['end'])}" if leave
                             else "" if p.get("online") else (f"last seen {when_text(seen)}" if seen else "")),
            })
        rows.sort(key=lambda r: (STATE_ORDER[r["presence"]], str(r["displayName"]).lower()))
        self._office.reset(rows)
        self._office_count = len(rows)
        self._office_counts = counts
        self.officeChanged.emit()

    # ---- handovers
    def _sync_handovers(self) -> None:
        today = self.today()
        me = self.me.lower()
        mine = next((h for h in self._handovers if str(h.get("from", "")).lower() == me
                     and h.get("state") != "returned"), None)
        if mine:
            self._mine = {
                "id": mine["id"], "to": mine["to"], "toName": self._name(str(mine["to"])),
                "start": mine["start"], "end": mine["end"], "spanText": span_text(mine["start"], mine["end"]),
                "on": TB.is_on(mine, today), "accepted": bool(mine.get("accepted_by")),
                "activityCount": len(mine.get("activities") or []), "taskCount": len(mine.get("tasks") or []),
                "movedCount": len(mine.get("tasks_moved") or []),
            }
        else:
            self._mine = {}
        rows = []
        for h in self._handovers:
            if str(h.get("to", "")).lower() != me or h.get("state") == "returned":
                continue
            rows.append({"handoverId": h["id"], "fromLogin": h["from"], "fromName": self._name(str(h["from"])),
                         "spanText": span_text(h["start"], h["end"]),
                         "stateText": "accepted" if h.get("accepted_by") else "waiting for you",
                         "accepted": bool(h.get("accepted_by")),
                         "activityCount": len(h.get("activities") or []), "taskCount": len(h.get("tasks") or []),
                         "taskTitles": ", ".join(str(t.get("title", "")) for t in h.get("tasks") or [])[:200],
                         "on": TB.is_on(h, today)})
        self._incoming.reset(rows)
        self._incoming_count = len(rows)
        self.handoverChanged.emit()

    def _sync_choices(self) -> None:
        store = self.ctx.store
        me = self.me.lower()
        acts = sorted(store.activities, key=lambda a: a.last_opened or "", reverse=True)
        cutoff = (self.today() - timedelta(days=30)).isoformat()
        tasks = [r for r in getattr(getattr(self.app, "tasks", None), "_tasks", {}).values()
                 if not r.done and r.owner.lower() == me]
        self._choices = {
            "activities": [{"id": a.id, "name": a.name, "recent": bool(a.last_opened and a.last_opened >= cutoff)}
                           for a in acts],
            "tasks": [{"id": t.id, "title": t.title, "dueText": due_text(t.due)} for t in tasks],
        }
        self.handoverChanged.emit()

    def _after_refresh(self) -> None:
        """The two automatic steps: my handover past its end goes back; copies of a returned one go away."""
        today = self.today()
        me = self.me.lower()
        for h in self._handovers:
            if str(h.get("from", "")).lower() == me and TB.is_due_back(h, today):
                self.endHandover(str(h["id"]))
                break
        else:
            self._follow_nib()
        self._clean_received()

    # ---- Nib's leave note
    def _leave_watch(self) -> LeaveWatch | None:
        watchers = getattr(self.app, "watchers", None)
        try:
            client = watchers.dispatcher().nib if watchers is not None else None
        except Exception:  # noqa: BLE001
            client = None
        if client is None or not getattr(client, "configured", False):
            self._nib_watch = None
            return None
        if self._nib_watch is None or self._nib_watch.client is not client:
            self._nib_watch = LeaveWatch(client, self.me)
        return self._nib_watch

    def _nib_path(self) -> Path:
        return Path(self.ctx.store.root) / NIB_FILE

    def _nib_state(self) -> dict[str, Any]:
        d = read_json(self._nib_path(), {}) or {}
        if not isinstance(d, dict):
            d = {}
        if not isinstance(d.get("handled"), list):
            d["handled"] = []
        if not isinstance(d.get("links"), dict):
            d["links"] = {}
        return d

    def _known_login(self, login: str) -> str:
        """``login`` as the Team Hub knows it, or "" (a cover who is not on the hub is never guessed)."""
        hub = self._hub()
        if not login or not hub.configured:
            return ""
        try:
            known = hub.known_users()
        except Exception:  # noqa: BLE001
            return ""
        return next((k for k in known if k.lower() == login.lower()), "")

    def _sync_nib_leave(self) -> None:
        rows = self._nib_rows
        if rows is None:                  # Nib did not answer: keep what the page shows
            return
        leave = next((r for r in rows if r.get("from") and r.get("to")), None)
        if leave is None:
            self._nib_leave = {}
            return
        cover = leave.get("cover") if isinstance(leave.get("cover"), dict) else None
        cover_login = self._known_login(login_of(str(cover.get("account", "")))) if cover else ""
        start, end = str(leave["from"]), str(leave["to"])
        self._nib_leave = {
            "id": str(leave.get("id", "")), "start": start, "end": end, "spanText": span_text(start, end),
            "current": bool(leave.get("current")), "half": leave.get("half") or "",
            "coverLogin": cover_login, "coverName": str(cover.get("name", "")) if cover else "",
        }

    def _follow_nib(self) -> None:
        """Nib answered this refresh: hand back what a cancelled or ended leave gave away, and offer or do the
        handover when a leave has started."""
        if self._nib_rows is None or self._busy:
            return
        state = self._nib_state()
        live = {str(r.get("id", "")) for r in self._nib_rows}
        mine_id = str(self._mine.get("id", ""))
        linked = str(state["links"].get(mine_id, "")) if mine_id else ""
        if linked and linked not in live:
            log.info("Nib leave %s ended or was cancelled: handing back %s", linked, mine_id)
            state["links"].pop(mine_id, None)
            write_json_atomic(self._nib_path(), state)
            self.endHandover(mine_id)
            return
        leave = self._nib_leave
        mode = getattr(self.ctx.settings, "handover_on_leave", "offer")
        if (mode not in ("offer", "auto") or not leave.get("current") or self._mine
                or leave.get("id") in state["handled"]):
            return
        state["handled"] = (list(state["handled"]) + [leave["id"]])[-50:]
        write_json_atomic(self._nib_path(), state)
        cover = leave.get("coverLogin") or ""
        if mode == "auto" and cover:
            acts = [a["id"] for a in self._choices.get("activities", []) if a.get("recent")]
            tasks = [t["id"] for t in self._choices.get("tasks", [])]
            reason = self._start(cover, leave["start"], leave["end"], acts, tasks, nib_leave_id=leave["id"])
            if reason:
                self._toast("Handover not done", f"Nib says you are on leave {leave['spanText']}: {reason}",
                            "warning")
            return
        who = f" to {leave.get('coverName') or cover}" if cover else ""
        self._toast("You are on leave", f"Nib's leave note says {leave['spanText']}. Hand your work over{who} "
                    "on the Handover page.", "info")

    # ---- handover slots
    @Slot(str, str, str, "QStringList", "QStringList", result=str)
    def startHandover(self, to: str, start: str, end: str, activity_ids: list[str],  # noqa: N802
                      task_ids: list[str]) -> str:
        """Hand my activities and open tasks to ``to`` from ``start`` to ``end``; returns "" or the reason it
        cannot (the page shows it inline).  On the dates of my Nib leave it follows that leave (handed back
        when the leave is cancelled in Nib)."""
        leave = self._nib_leave
        same = (leave.get("start"), leave.get("end")) == ((start or "").strip(), (end or "").strip())
        return self._start(to, start, end, list(activity_ids), list(task_ids),
                           nib_leave_id=str(leave.get("id", "")) if same else "")

    def _start(self, to: str, start: str, end: str, activity_ids: list[str], task_ids: list[str],
               nib_leave_id: str = "") -> str:
        hub = self._hub()
        to = (to or "").strip().lstrip("@")
        if not hub.configured:
            return "Set up the Team Hub first: a handover goes through the shared folder."
        if not to:
            return "Pick the colleague who takes over."
        if to.lower() == self.me.lower():
            return "Pick a colleague, not yourself."
        try:
            a, b = date.fromisoformat(start.strip()), date.fromisoformat(end.strip())
        except ValueError:
            return "Dates are YYYY-MM-DD, for example 2026-11-24."
        if b < a:
            return "The last day is before the first."
        if b < self.today():
            return "The last day has passed."
        if self._mine:
            return f"You already handed over to {self._mine.get('toName')}. Say you are back first."
        if not activity_ids and not task_ids:
            return "Tick at least one activity or task."
        store = self.ctx.store
        portable = self.ctx.resolver.portable
        acts, projects = [], {}
        for aid in activity_ids:
            act = store.activity(aid)
            if act is None:
                continue
            data = act.to_dict()
            for it in data["items"]:
                it["path"] = portable(it["path"])
            data.update(pinned_at=None, last_opened=None, open_count=0, favorite=False)
            acts.append(data)
            for pid in act.project_ids:
                p = store.get(pid)
                if p is not None:
                    projects[p.id] = {"id": p.id, "title": p.title, "job_number": p.job_number}
        to_name = self._name(to)
        me_low = self.me.lower()
        tb = self._tb()
        ts = self._tasks_store()
        dispatcher = getattr(getattr(self.app, "watchers", None), "dispatcher", None)
        self._busy = True
        self.handoverChanged.emit()

        def work() -> str:
            tasks = []
            for tid in task_ids:
                t = ts.get(tid) if ts is not None else None
                if t is not None and not t.done and t.owner.lower() == me_low:
                    tasks.append(t)
            hid = tb.create_handover(to, a.isoformat(), b.isoformat(), acts, tasks, to_name, list(projects.values()))
            if hid:
                hub.pulse("handover", f"on leave {span_text(a.isoformat(), b.isoformat())} · handed to {to_name}",
                          kind="handover", mentions=[to])
                if dispatcher is not None:
                    try:
                        dispatcher().notify_people([to], f"{hub.display_name or hub.user} handed work to you "
                                                   f"for {span_text(a.isoformat(), b.isoformat())}",
                                                   "", title="Handover", inbox=False)
                    except Exception:  # noqa: BLE001
                        log.debug("handover note failed", exc_info=True)
            return hid

        def done(hid: str) -> None:
            self._busy = False
            if hid and nib_leave_id:
                state = self._nib_state()
                state["links"][hid] = nib_leave_id
                state["handled"] = (list(state["handled"]) + [nib_leave_id])[-50:]
                write_json_atomic(self._nib_path(), state)
            if hid:
                self._toast(f"Handed over to {to_name}", f"{span_text(a.isoformat(), b.isoformat())} · "
                            "they accept it from their inbox", "success")
            else:
                self._toast("Handover failed", "The hub folder is not writable.", "error")
            self.refresh()

        def fail(exc: Exception) -> None:
            self._busy = False
            self.handoverChanged.emit()
            self._toast("Handover failed", str(exc), "error")

        self.app.run_async(work, done, fail)
        return ""

    @Slot(str)
    def acceptHandover(self, hid: str) -> None:  # noqa: N802
        """The colleague's side: add the activities, take the open tasks still owned by the leaver."""
        tb = self._tb()
        h = tb.get(hid)
        me = self.me
        if h is None or str(h.get("to", "")).lower() != me.lower():
            self._toast("Handover not found", "It may have been returned already.", "warning")
            return
        if h.get("accepted_by") or h.get("state") == "returned":
            return
        src = str(h["from"])
        hub_api = getattr(self.app, "hub", None)
        added: list[str] = []
        for a in h.get("activities") or []:
            act = M.Activity.from_dict(a)
            origin = M.Origin(source="handover", author=src)
            if hub_api is not None and hasattr(hub_api, "adopt_activity"):
                clone = hub_api.adopt_activity(act, origin, h.get("projects") or [])
            else:
                clone = act.clone(act.name)
                clone.origin = origin
                self.ctx.store.add_activity(clone)
            added.append(clone.id)
        rec = read_json(self._received_path(), {}) or {}
        rec[hid] = {"ids": added, "stamps": {i: _fingerprint(self.ctx.store.activity(i)) for i in added}}
        write_json_atomic(self._received_path(), rec)
        ts = self._tasks_store()
        hub = self._hub()
        task_ids = [str(t.get("id")) for t in h.get("tasks") or []]

        def work() -> list[str]:
            moved = []
            for tid in task_ids:
                t = ts.get(tid) if ts is not None else None
                if t is None or t.done or t.owner.lower() != src.lower():
                    continue
                t.owner = me
                t.updated_by, t.updated_at = me, M.now_iso()
                ts.save(t)
                moved.append(t.id)
            tb.accept(hid, moved)
            hub.pulse("handover", f"took over from {h.get('from_name') or src} until "
                      f"{span_text(h['end'], h['end'])}", kind="handover", mentions=[src])
            return moved

        def done(moved: list[str]) -> None:
            self._toast("Handover accepted", f"{TB._plural(len(added), 'activity', 'activities')} added · "
                        f"{TB._plural(len(moved), 'task')} yours until {span_text(h['end'], h['end'])}", "success")
            tasks_api = getattr(self.app, "tasks", None)
            if tasks_api is not None:
                tasks_api.refresh()
            for mid, e in list(getattr(hub_api, "_entries", {}).items()):     # accepted here: the inbox item goes
                if e.get("kind") == "handover" and str(e.get("handover_id")) == hid:
                    hub_api.dismissInbox(mid)
            self.refresh()

        self.app.run_async(work, done, lambda e: self._toast("Accept failed", str(e), "error"))

    @Slot(str)
    def endHandover(self, hid: str = "") -> None:  # noqa: N802
        """I am back: the tasks the colleague took go back to me (those they still own and have not
        finished), and the handover is marked returned."""
        hid = hid or str(self._mine.get("id", ""))
        tb = self._tb()
        h = tb.get(hid) if hid else None
        if h is None or str(h.get("from", "")).lower() != self.me.lower():
            return
        ts = self._tasks_store()
        me = self.me
        taker = str(h.get("accepted_by") or "")
        hub = self._hub()

        def work() -> int:
            back = 0
            for tid in h.get("tasks_moved") or []:
                t = ts.get(tid) if ts is not None else None
                if t is None or t.done or not taker or t.owner.lower() != taker.lower():
                    continue
                t.owner = me
                t.updated_by, t.updated_at = me, M.now_iso()
                ts.save(t)
                back += 1
            tb.mark_returned(hid)
            hub.pulse("handover", "back from leave", kind="handover", mentions=[str(h["to"])])
            return back

        def done(back: int) -> None:
            self._toast("Welcome back", f"{TB._plural(back, 'task')} returned to you", "success")
            tasks_api = getattr(self.app, "tasks", None)
            if tasks_api is not None:
                tasks_api.refresh()
            self.refresh()

        self.app.run_async(work, done, lambda e: self._toast("Could not end the handover", str(e), "error"))

    def _clean_received(self) -> None:
        """On the colleague's PC: copies of a returned handover go, unless someone changed them."""
        path = self._received_path()
        rec = read_json(path, {}) or {}
        if not isinstance(rec, dict) or not rec:
            return
        returned = {str(h["id"]) for h in self._handovers if h.get("state") == "returned"}
        known = {str(h["id"]) for h in self._handovers}
        store = self.ctx.store
        kept = 0
        changed = False
        for hid in list(rec):
            if hid not in returned and hid in known:
                continue
            if hid not in known and self._handovers == []:
                continue                      # the hub is not readable now: decide later
            entry = rec.pop(hid)
            changed = True
            for aid in entry.get("ids") or []:
                act = store.activity(aid)
                if act is None:
                    continue
                if _fingerprint(act) == (entry.get("stamps") or {}).get(aid):
                    store.remove_activity(aid)
                else:
                    kept += 1
        if changed:
            write_json_atomic(path, rec)
            if kept:
                self._toast("Handover returned", f"You changed {TB._plural(kept, 'activity', 'activities')}, "
                            "so they stay in your workspace.", "info")


def _get(facade: Any) -> TeamApi:
    """Built on first read (the sidebar reads it at load) and started on the next event-loop turn, so the
    board file is written and an overdue handover is returned without the facade's start list changing."""
    api = getattr(facade, "_team_api", None)
    if api is None:
        api = TeamApi(facade)
        facade._team_api = api
        QTimer.singleShot(0, api.start)
    return api


# The facade registers the API with one line in its class body:
#     from project_opener.quick.team_api import team  # app.team
team = Property(QObject, _get, constant=True)
