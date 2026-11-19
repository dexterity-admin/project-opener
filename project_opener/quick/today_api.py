"""``app.today``: the facts the Today screen shows, read from stored data only (docs/V4-PLUS-BRIEF.md section 5,
owner ruling 19 Nov 2026: "real data only").  Nothing here estimates or invents a number: a block whose
source does not exist yet says so (``changed`` = -1 with no folder watcher; an empty ``hero`` with no activity).

* ``hero``: the resume after a shutdown (``app.activities.resume``), else the last-run activity, with its
  restore plan (the latest snapshot's restorable entries; with none, the activity's enabled items).
* ``stats``: my tasks due today / this week (``app.tasks``), files changed overnight (folder watchers'
  ``WatchEvent`` rows since 18:00 yesterday), the day streak (distinct days with a launch, ``store.history``).
* ``week``: every activity's checkpoints since Monday 00:00, one tick each (the Time travel panel).

The pure functions below take plain data and a ``now``, so the tests pin every rule.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any

from PySide6.QtCore import QTimer, Signal

from project_opener.core import models as M
from project_opener.core.jsonio import read_jsonl
from project_opener.core.tasks import parse_due
from project_opener.quick.activities_api import item_glyph
from project_opener.quick.base import ApiBase, ro
from project_opener.ui import text as T

log = logging.getLogger(__name__)

OVERNIGHT_FROM_HOUR = 18                 # "changed overnight" counts from 18:00 yesterday (brief section 5)
FOLDER_EVENTS = ("new", "changed", "gone")
STREAK_SQUARES = 14                      # the streak card's squares: the last two weeks, oldest first
CHIPS_MAX = 12                           # the hero sends this many chips; QML shows what fits, then "+N"
DAY_WORDS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
REFRESH_MS = 10 * 60 * 1000              # the date rolls over; the week and the night move on


def _local(iso: str | None) -> datetime | None:
    dt = M.parse_iso(iso)
    return dt.astimezone() if dt else None


def _now() -> datetime:
    return datetime.now().astimezone()


def moment_text(iso: str | None, now: datetime | None = None) -> str:
    """"today 14:32", "yesterday 18:42", "Mon 17 Nov 14:32", "3 Nov 2025 09:10"; "" for none."""
    dt = _local(iso)
    if dt is None:
        return ""
    today = (now or _now()).astimezone().date()
    hm = dt.strftime("%H:%M")
    if dt.date() == today:
        return f"today {hm}"
    if (today - dt.date()).days == 1:
        return f"yesterday {hm}"
    if dt.year == today.year:
        return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')} {hm}"
    return f"{dt.day} {dt.strftime('%b %Y')} {hm}"


# ------------------------------------------------------------------- tasks
def task_stats(tasks: Iterable[M.Task], me: str, today: date,
               name_for: Callable[[str], str] = lambda u: u) -> dict[str, Any]:
    """My open tasks: due today, overdue, due this week (today to Sunday), without a date, and who set the
    ones due today (logins other than mine, as names)."""
    me_l = (me or "").lower()
    mine = [t for t in tasks if (t.owner or "").lower() == me_l and not t.done]
    week_end = today + timedelta(days=6 - today.weekday())
    due_today, overdue, week, nodate = [], 0, 0, 0
    for t in mine:
        d = parse_due(t.due)
        if d is None:
            nodate += 1
            continue
        if d < today:
            overdue += 1
        elif d <= week_end:
            week += 1
            if d == today:
                due_today.append(t)
    names: list[str] = []
    for t in due_today:
        who = (t.created_by or "").lower()
        if who and who != me_l:
            n = name_for(t.created_by) or t.created_by
            if n not in names:
                names.append(n)
    return {"dueToday": len(due_today), "open": len(mine), "overdue": overdue, "dueWeek": week,
            "noDate": nodate, "weekEnd": f"{week_end.strftime('%a')} {week_end.day} {week_end.strftime('%b')}",
            "fromNames": names}


def tasks_line(s: dict[str, Any]) -> str:
    """"from Ravi · 1 overdue" under Tasks due today; "" when there is nothing to add."""
    parts = []
    if s["fromNames"]:
        parts.append("from " + (s["fromNames"][0] if len(s["fromNames"]) == 1
                                else f"{s['fromNames'][0]} and {len(s['fromNames']) - 1} more"))
    if s["overdue"]:
        parts.append(f"{s['overdue']} overdue")
    return " · ".join(parts)


# --------------------------------------------------------- changed overnight
_LEAD_INT = re.compile(r"^\s*(\d+)\s")


def files_in(row: dict[str, Any]) -> int:
    """The files one folder alert stands for: a collapsed alert (key ``<watcher>:<event>:*:<digest>``, title
    "12 new files in Revision C", written by ``core.watchers.poll_folder``) its count, else one."""
    if ":*:" in str(row.get("key", "")):
        m = _LEAD_INT.match(str(row.get("title", "")))
        if m:
            return int(m.group(1))
    return 1


def overnight_since(now: datetime) -> datetime:
    """18:00 yesterday, local."""
    y = now.astimezone() - timedelta(days=1)
    return y.replace(hour=OVERNIGHT_FROM_HOUR, minute=0, second=0, microsecond=0)


def changed_overnight(rows: Iterable[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Files the folder watchers saw new, changed or gone since 18:00 yesterday, and the same per hour (the
    sparkline, oldest first)."""
    now = now.astimezone()
    since = overnight_since(now)
    hours = max(1, int((now - since).total_seconds() // 3600) + 1)
    spark = [0] * hours
    total = 0
    for r in rows:
        if str(r.get("event", "")) not in FOLDER_EVENTS:
            continue
        ts = _local(str(r.get("ts", "")))
        if ts is None or ts < since or ts > now:
            continue
        n = files_in(r)
        total += n
        spark[min(hours - 1, int((ts - since).total_seconds() // 3600))] += n
    return {"count": total, "spark": spark, "since": since.isoformat(timespec="seconds")}


# ---------------------------------------------------------------- streak
def launch_days(rows: Iterable[dict[str, Any]]) -> set[date]:
    out = set()
    for r in rows:
        dt = _local(str(r.get("ts", "")))
        if dt is not None:
            out.add(dt.date())
    return out


def day_streak(days: set[date], today: date) -> tuple[int, list[bool]]:
    """Consecutive days with a launch, counted back from today (from yesterday while today has none yet).
    A Saturday or Sunday without a launch neither counts nor breaks the run (the office's week); one with a
    launch counts.  Also the last ``STREAK_SQUARES`` days, oldest first, True where something was launched."""
    squares = [(today - timedelta(days=i)) in days for i in range(STREAK_SQUARES - 1, -1, -1)]
    if not days:
        return 0, squares
    first = min(days)
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d >= first:
        if d in days:
            n += 1
        elif d.weekday() < 5:
            break
        d -= timedelta(days=1)
    return n, squares


# ------------------------------------------------------------ time travel
def week_start(now: datetime) -> datetime:
    n = now.astimezone()
    return (n - timedelta(days=n.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def week_ticks(checkpoints: Iterable[tuple[str, str, M.Checkpoint]], now: datetime) -> list[dict[str, Any]]:
    """One tick per checkpoint taken since Monday 00:00 (local), oldest first.  ``checkpoints``:
    (activity id, activity name, checkpoint)."""
    start = week_start(now)
    out = []
    for aid, name, cp in checkpoints:
        dt = _local(cp.taken_at)
        if dt is None or dt < start or dt > now.astimezone() + timedelta(minutes=1):
            continue
        snap = cp.snapshot
        out.append({"activityId": aid, "name": name, "checkpointId": cp.id, "takenAt": cp.taken_at,
                    "day": (dt.date() - start.date()).days, "minute": dt.hour * 60 + dt.minute,
                    "whenText": f"{dt.strftime('%a')} {dt.strftime('%H:%M')}",
                    "windows": snap.open_count if snap else 0,
                    "identified": snap.identified_count if snap else 0, "kind": cp.kind, "label": cp.label})
    out.sort(key=lambda t: t["takenAt"])
    return out


def week_days(now: datetime) -> list[str]:
    """The lanes: Monday to today."""
    return list(DAY_WORDS[: now.astimezone().weekday() + 1])


# ----------------------------------------------------------------- hero
def entry_chip(e: M.SnapshotEntry) -> dict[str, str]:
    name = e.doc_name or os.path.basename((e.path or "").rstrip("\\/")) or e.path or e.title or e.app
    return {"text": name, "glyph": item_glyph(e.kind, e.path), "app": e.app}


def hero_fact(act: M.Activity | None, kind: str, snap: M.Snapshot | None, spine: str,
              resume: dict[str, Any] | None = None, now: datetime | None = None) -> dict[str, Any]:
    """The hero's facts for ``act``.  ``kind``: park (the latest Park; ``resume`` is then the
    ``app.capture.latestPark`` map) | resume (the PC stopped while it ran) | last (the last-run
    activity) | new (activities exist, none opened yet).  The plan is the snapshot's restorable windows; with
    none, the enabled items in launch order."""
    if act is None:
        return {}
    restorable = snap.restorable if snap else []
    if restorable:
        chips = [entry_chip(e) for e in restorable]
        apps = sorted({e.app for e in restorable if e.app})
        plan_kind, plan_count = "windows", len(restorable)
        plan_text = T.join_facts(T.plural(plan_count, "window"), T.plural(len(apps), "app") if apps else "")
    else:
        items = act.enabled_items
        chips = [{"text": os.path.basename(i.path.rstrip("\\/")) or i.path, "glyph": item_glyph(i.kind, i.path),
                  "app": ""} for i in items]
        plan_kind, plan_count = "items", len(items)
        plan_text = T.plural(plan_count, "item") + (" in launch order" if plan_count > 1 else "")
    note, checkpoint_id = "", ""
    if kind == "park":
        park = resume or {}
        when = park.get("takenAt", "")
        moment = moment_text(when, now) if when else ""
        label = T.join_facts(f"Parked {moment}" if moment else "Parked", act.name)
        heading = "Pick up where you parked"
        note, checkpoint_id = park.get("note", ""), park.get("checkpointId", "")
        line = T.join_facts(T.plural(len(restorable), "window") + " to reopen", spine)
        from_text = f"Parked {T.clock(when)}" if when else "Parked"
    elif kind == "resume":
        when = (snap.taken_at if snap and snap.entries else "") or (resume or {}).get("takenIso", "")
        moment = moment_text(when, now) if when else (resume or {}).get("takenAt", "")
        label = T.join_facts(f"Stopped {moment}" if moment else "Stopped", act.name)
        heading = "Pick up where you stopped"
        line = (resume or {}).get("text", "")
        from_text = f"Stopped {T.clock(when)}" if when else "Stopped"
    elif kind == "last":
        moment = moment_text(act.last_opened, now)
        label = T.join_facts(f"Opened {moment}", act.name)
        heading = "Pick up where you left off"
        line = T.join_facts(T.plural(len(act.enabled_items), "item"), spine)
        from_text = f"Opened {T.clock(act.last_opened)}"
    else:
        label = T.join_facts("Not opened yet", act.name)
        heading = "Start where you planned"
        line = T.join_facts(T.plural(len(act.enabled_items), "item"), spine)
        from_text = "Not opened yet"
    return {"activityId": act.id, "kind": kind, "name": act.name, "label": label, "heading": heading,
            "line": line, "planKind": plan_kind, "planCount": plan_count, "planText": plan_text,
            "chips": chips[:CHIPS_MAX], "fromText": from_text, "toText": "Ready", "note": note,
            "checkpointId": checkpoint_id}


def park_wins(park: dict[str, Any], other_at: str | None) -> bool:
    """The latest Park takes the hero unless something newer happened since: a resume snapshot or a launch
    taken after it (``other_at``, ISO).  Unreadable times never hide a park."""
    if not park.get("checkpointId"):
        return False
    p, o = _local(park.get("takenAt")), _local(other_at)
    return p is None or o is None or p >= o

def pick_last(acts: Iterable[M.Activity]) -> tuple[M.Activity | None, str]:
    """The last-run activity ("last"); with none ever opened, the first in stage order ("new")."""
    acts = list(acts)
    opened = [a for a in acts if a.last_opened]
    if opened:
        return max(opened, key=lambda a: a.last_opened or ""), "last"
    return (acts[0], "new") if acts else (None, "")


# ------------------------------------------------------------------- api
class TodayApi(ApiBase):
    heroChanged = Signal()
    statsChanged = Signal()
    weekChanged = Signal()

    def __init__(self, app: Any):
        super().__init__(app)
        self._hero: dict[str, Any] = {}
        self._stats: dict[str, Any] = {"ready": False}
        self._week: list[dict[str, Any]] = []
        self._week_days: list[str] = []
        self._days: set[date] = set()
        self._busy: set[str] = set()
        self._again: set[str] = set()
        self._timer: QTimer | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.refresh_week)

    hero = ro("QVariantMap", "_hero", heroChanged)
    stats = ro("QVariantMap", "_stats", statsChanged)
    week = ro("QVariantList", "_week", weekChanged)
    weekDays = ro("QStringList", "_week_days", weekChanged)

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        a = self.app
        a.activities.resumeChanged.connect(self.refresh_hero)
        a.activities.activitiesChanged.connect(self.refresh_hero)
        a.activities.activitiesChanged.connect(self._debounce.start)
        a.capture.checkpointsChanged.connect(self._debounce.start)
        a.capture.checkpointsChanged.connect(self.refresh_hero)
        a.capture.memoryChanged.connect(self.refresh_hero)
        a.capture.memoryChanged.connect(self.refresh_stats)
        a.tasks.tasksChanged.connect(self.refresh_stats)
        a.watchers.alertsChanged.connect(self.refresh_stats)
        a.watchers.watchersChanged.connect(self.refresh_stats)
        a.ctx.store.subscribe(self._on_store)
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def shutdown(self) -> None:
        for t in (self._timer, self._debounce):
            if t is not None:
                t.stop()

    def _on_store(self, event: str, _payload: Any) -> None:
        if event == "launched":
            self.refresh_days()

    def refresh(self) -> None:
        self.refresh_hero()
        self.refresh_days()
        self.refresh_week()

    # ------------------------------------------------------------- hero
    def refresh_hero(self) -> None:
        store = self.app.ctx.store
        resume = dict(self.app.activities.resume or {})
        act, kind = None, ""
        if resume.get("activityId"):
            act, kind = store.activity(resume["activityId"]), "resume"
        if act is None:
            act, kind = pick_last(store.activities)
        park = dict(self.app.capture.latestPark or {})
        other_at = (resume.get("takenIso") if kind == "resume" else act.last_opened if act else None) or None
        parked = store.activity(park.get("activityId", "")) if park_wins(park, other_at) else None
        if parked is not None:
            act, kind, resume = parked, "park", park
        snap = None
        if act is not None:
            try:
                if kind == "park":
                    cp = self.app.snapshots.checkpoint(act.id, park["checkpointId"])
                    snap = cp.snapshot if cp else None
                else:
                    snap = self.app.snapshots.latest(act.id)
            except Exception:  # noqa: BLE001
                log.exception("no snapshot for the hero")
        proj = store.get(act.primary_project_id) if act is not None else None
        self.set_("_hero", hero_fact(act, kind, snap, proj.spine if proj else "", resume), self.heroChanged)

    # ------------------------------------------------------------ stats
    def refresh_stats(self) -> None:
        now = _now()
        tasks = self.app.tasks
        s = task_stats(tasks.latest(), self.app.ctx.user, now.date(), tasks.name_for)
        folder = any(w.kind == "folder" and w.enabled for w in self.app.ctx.store.watchers)
        ch = changed_overnight(self.app.watchers.alert_rows(), now) if folder \
            else {"count": -1, "spark": [], "since": ""}
        streak, squares = day_streak(self._days, now.date())
        stats = {"ready": True, **s, "tasksLine": tasks_line(s),
                 "changed": ch["count"], "changedSpark": ch["spark"],
                 "changedSince": f"since {OVERNIGHT_FROM_HOUR}:00 yesterday",
                 "streak": streak, "streakDays": squares, "launchDays": len(self._days),
                 "reopened": int(self.app.capture.weekReopened), "restores": int(self.app.capture.weekRestores)}
        self.set_("_stats", stats, self.statsChanged)

    def _run(self, key: str, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        """One pass per key on the pool; a request during a pass runs one more after it."""
        if key in self._busy:
            self._again.add(key)
            return
        self._busy.add(key)

        def finish(res: Any) -> None:
            self._busy.discard(key)
            done(res)
            if key in self._again:
                self._again.discard(key)
                self._run(key, work, done)

        def fail(exc: Exception) -> None:
            log.warning("today %s: %s", key, exc)
            finish(None)

        self.app.run_async(work, finish, fail)

    def refresh_days(self) -> None:
        path = self.app.ctx.store.history_path

        def done(days: set[date] | None) -> None:
            if days is not None:
                self._days = days
            self.refresh_stats()

        self._run("days", lambda: launch_days(read_jsonl(path)), done)

    # ------------------------------------------------------------- week
    def refresh_week(self) -> None:
        acts = [(a.id, a.name) for a in self.app.ctx.store.activities]
        snaps = self.app.snapshots

        def work() -> list[tuple[str, str, M.Checkpoint]]:
            return [(aid, name, cp) for aid, name in acts for cp in snaps.checkpoints(aid)]

        def done(cps: list[tuple[str, str, M.Checkpoint]] | None) -> None:
            now = _now()
            ticks = week_ticks(cps or [], now)
            changed = ticks != self._week or week_days(now) != self._week_days
            self._week, self._week_days = ticks, week_days(now)
            if changed:
                self.weekChanged.emit()

        self._run("week", work, done)
