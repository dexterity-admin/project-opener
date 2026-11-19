"""Weekly Wrapped: one person's week, counted from what the app already records.  Owner: po4-team.

Sources (docs/V4-PLUS-BRIEF.md section 4; no invented numbers, no raw hours, no window titles):

* activities run  - ``history.jsonl`` rows that carry ``activity_id`` (``WorkspaceStore.record_activity_launch``)
* day streak      - the local days with any launch in ``history.jsonl`` (projects too)
* tasks closed    - hub tasks with ``done_by`` = me and ``done_at`` in the week
* on-time rate    - of those with a due date, the share closed on or before it; ``None`` when none had one
* windows reopened - the restore log (a parallel 4.0 change): ``None`` until it exists, and the page says so

A streak counts calendar days ending today (or yesterday, when today has no launch yet: the day is not over).
Saturdays and Sundays without a launch neither count nor break it: the office works a five-day week.
Everything here is plain functions over plain data so tests can drive them with fixed dates.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from project_opener.core import models as M
from project_opener.core.tasks import parse_due

STREAK_LOOKBACK_DAYS = 120          # launch days kept in a board file (enough for any streak worth showing)


def week_start(day: date) -> date:
    """The Monday of ``day``'s week."""
    return day - timedelta(days=day.weekday())


def week_id(day: date) -> str:
    """"2026-W47" (ISO week of ``day``)."""
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def local_day(iso: str) -> date | None:
    dt = M.parse_iso(iso)
    return dt.astimezone().date() if dt is not None else None


def launch_days(rows: Iterable[dict[str, Any]]) -> set[date]:
    """Local days with any launch (activity or project) in the history rows."""
    out: set[date] = set()
    for r in rows:
        d = local_day(str(r.get("ts", "")))
        if d is not None:
            out.add(d)
    return out


def activities_run(rows: Iterable[dict[str, Any]], start: date, end: date) -> int:
    """Activity launches with a local day in ``[start, end]``."""
    n = 0
    for r in rows:
        if not r.get("activity_id"):
            continue
        d = local_day(str(r.get("ts", "")))
        if d is not None and start <= d <= end:
            n += 1
    return n


def day_streak(days: Iterable[date], today: date) -> int:
    """Consecutive active days up to ``today`` (see the module notes for today and weekends)."""
    active = set(days)
    d = today if today in active else today - timedelta(days=1)
    n = 0
    while True:
        if d in active:
            n += 1
        elif d.weekday() < 5:            # a working day without a launch ends it
            break
        if (today - d).days > 400:       # bounded: a year of weekends is no streak
            break
        d -= timedelta(days=1)
    return n


def week_squares(days: Iterable[date], start: date) -> list[bool]:
    """Monday..Sunday of the week from ``start``: True where there was a launch."""
    active = set(days)
    return [start + timedelta(days=i) in active for i in range(7)]


def tasks_closed(tasks: Iterable[M.Task], login: str, start: date, end: date) -> dict[str, int]:
    """``{"closed", "with_due", "on_time"}`` for the tasks ``login`` closed in ``[start, end]``."""
    low = (login or "").lower()
    closed = with_due = on_time = 0
    for t in tasks:
        if not t.done or t.done_by.lower() != low:
            continue
        d = local_day(t.done_at)
        if d is None or not (start <= d <= end):
            continue
        closed += 1
        due = parse_due(t.due)
        if due is not None:
            with_due += 1
            if d <= due:
                on_time += 1
    return {"closed": closed, "with_due": with_due, "on_time": on_time}


def on_time_rate(with_due: int, on_time: int) -> int | None:
    """Whole per cent, or None when no closed task had a due date (a rate of nothing is not 0 %)."""
    if with_due <= 0:
        return None
    return round(100 * on_time / with_due)


def week_stats(history: list[dict[str, Any]], tasks: Iterable[M.Task], login: str, day: date,
               today: date | None = None, windows_reopened: int | None = None) -> dict[str, Any]:
    """One person's numbers for the week holding ``day`` (on this PC's history).

    ``today`` bounds the streak (default ``day``); for a past week the streak is the one at its Sunday."""
    start = week_start(day)
    end = start + timedelta(days=6)
    today = today or day
    days = launch_days(history)
    t = tasks_closed(tasks, login, start, end)
    streak_at = min(today, end)
    return {
        "week": week_id(start), "start": start.isoformat(), "end": end.isoformat(),
        "activities_run": activities_run(history, start, end),
        "tasks_closed": t["closed"], "tasks_with_due": t["with_due"], "tasks_on_time": t["on_time"],
        "on_time_rate": on_time_rate(t["with_due"], t["on_time"]),
        "day_streak": day_streak(days, streak_at),
        "squares": week_squares(days, start),
        "windows_reopened": windows_reopened,
        "launch_days": sorted(d.isoformat() for d in days if (streak_at - d).days <= STREAK_LOOKBACK_DAYS
                              and d <= streak_at),
    }


def merge_person(parts: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """One person's week from the board files of each of their PCs.

    Launches are per PC, so activities run add up and launch days are joined (the streak is recomputed);
    tasks live on the hub, so every PC counted the same tasks and the largest count is the true one.
    A restore count is per PC too: added, or None when no PC has one."""
    if not parts:
        return {}
    first = parts[0]
    start = date.fromisoformat(str(first["start"]))
    end = start + timedelta(days=6)
    days: set[date] = set()
    for p in parts:
        for s in p.get("launch_days") or []:
            try:
                days.add(date.fromisoformat(str(s)))
            except ValueError:
                continue
    best = max(parts, key=lambda p: (int(p.get("tasks_closed") or 0), int(p.get("tasks_with_due") or 0)))
    reopened = [int(p["windows_reopened"]) for p in parts if p.get("windows_reopened") is not None]
    streak_at = min(today, end)
    return {
        "week": first["week"], "start": start.isoformat(), "end": end.isoformat(),
        "activities_run": sum(int(p.get("activities_run") or 0) for p in parts),
        "tasks_closed": int(best.get("tasks_closed") or 0),
        "tasks_with_due": int(best.get("tasks_with_due") or 0),
        "tasks_on_time": int(best.get("tasks_on_time") or 0),
        "on_time_rate": on_time_rate(int(best.get("tasks_with_due") or 0), int(best.get("tasks_on_time") or 0)),
        "day_streak": day_streak(days, streak_at),
        "squares": week_squares(days, start),
        "windows_reopened": sum(reopened) if reopened else None,
    }


BOARD_SORTS = {
    "tasks": ("tasks_closed", "activities_run", "day_streak"),
    "activities": ("activities_run", "tasks_closed", "day_streak"),
    "streak": ("day_streak", "tasks_closed", "activities_run"),
}


def rank(rows: list[dict[str, Any]], by: str = "tasks") -> list[dict[str, Any]]:
    """Board rows best first by ``by`` (tasks | activities | streak), ties by the other two, then name.
    Equal numbers share a place ("1, 1, 3")."""
    keys = BOARD_SORTS.get(by, BOARD_SORTS["tasks"])

    def k(r: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(-int(r.get(x) or 0) for x in keys) + (str(r.get("name", "")).lower(),)

    out = sorted(rows, key=k)
    place = 0
    prev: tuple[int, ...] | None = None
    for i, r in enumerate(out, start=1):
        cur = tuple(int(r.get(x) or 0) for x in keys)
        if cur != prev:
            place, prev = i, cur
        r["place"] = place
    return out


def cliq_text(name: str, stats: dict[str, Any], place: int = 0, of: int = 0) -> str:
    """The Cliq post: the week's counts as the page shows them, nothing more (no hours, no window titles)."""
    start = date.fromisoformat(str(stats["start"]))
    lines = [f"*{name}'s week* ({start.day} {start.strftime('%b')})",
             f"Activities run: {stats['activities_run']}",
             f"Tasks closed: {stats['tasks_closed']}"]
    rate = stats.get("on_time_rate")
    lines.append(f"On time: {rate} %" if rate is not None else "On time: no due dates")
    lines.append(f"Day streak: {stats['day_streak']}")
    if stats.get("windows_reopened") is not None:
        lines.append(f"Windows reopened: {stats['windows_reopened']}")
    if place and of > 1:
        lines.append(f"Office board: {place} of {of}")
    return "\n".join(lines)
