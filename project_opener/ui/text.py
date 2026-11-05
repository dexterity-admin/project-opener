"""Shared copy for both shells: sentence case, plurals, relative times, the pill words.

Pure functions (no Qt widgets), so the Qt Quick models (``project_opener.quick``)
and tests call them directly.  They are the spike's list of 3.2 view helpers
(``widgets/cards.py``, ``views/home.py``, ``views/team.py``, ``views/detail.py``)
plus the v4 lines (activities, capture, launch dock, resume band).  The 3.2
widgets keep their own copies until integration removes them; the wording here is
the same, so both shells say the same thing (docs/DESIGN.md, "Copy").
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any

from project_opener.core import models as M

# --------------------------------------------------------------- the pill words
# health status -> (pill level, word); one status mark per row (3.2 STATUS_META)
STATUS_META: dict[str, tuple[str, str]] = {
    "ok": ("ok", "Reachable"),
    "missing": ("warn", "Not found"),
    "offline": ("bad", "Server offline"),
    "variable": ("warn", "Undefined variable"),
}
# launch result code -> (pill level, word): the launch dock's pills
LAUNCH_META: dict[str, tuple[str, str]] = {
    "queued": ("neutral", ""),
    "opening": ("opening", "Opening…"),
    "opened": ("ok", "Opened"),
    "missing": ("warn", "Not found"),
    "offline": ("bad", "Server offline"),
    "variable": ("warn", "Undefined variable"),
    "skipped": ("neutral", "Skipped"),
    "failed": ("bad", "Failed"),
}
# capture entry status -> (pill level, word)
ENTRY_META: dict[str, tuple[str, str]] = {
    "identified": ("ok", "Identified"),
    "ambiguous": ("warn", "Ambiguous"),
    "unidentified": ("warn", "Needs a path"),
    "unsaved": ("neutral", "Unsaved"),
}
HEALTH_RANK = {"offline": 3, "variable": 2, "missing": 1, "ok": 0, "": -1}
KIND_WORDS = {"file": "file", "folder": "folder", "url": "link", "app": "application", "command": "command"}


def status_level(status: str) -> str:
    return STATUS_META.get(status, ("neutral", ""))[0]


def status_word(status: str) -> str:
    return STATUS_META.get(status, ("neutral", ""))[1]


# --------------------------------------------------------------------- numbers
def plural(n: int, word: str, many: str = "") -> str:
    """"1 item", "2 items", "2 activities"; ``many`` spells an irregular plural."""
    if n == 1:
        return f"{n} {word}"
    if many:
        return f"{n} {many}"
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy", "uy")):
        return f"{n} {word[:-1]}ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return f"{n} {word}es"
    return f"{n} {word}s"


def join_facts(*parts: str) -> str:
    """" · " between the non-empty facts."""
    return " · ".join(p for p in parts if p)


def first_upper(text: str) -> str:
    """Sentence case for a line that starts with a lower-case fact."""
    return text[:1].upper() + text[1:] if text else text


def first_lower(text: str) -> str:
    """"Lot 7 check" -> "lot 7 check" mid-sentence, but an acronym or job number stays ("P12513", "GAD")."""
    if len(text) > 1 and text[0].isupper() and not text[1].isupper() and not text[1].isdigit():
        return text[0].lower() + text[1:]
    return text


# ----------------------------------------------------------------------- times
def _now() -> datetime:
    return datetime.now(UTC)


def relative_time(iso: str | None, now: datetime | None = None) -> str:
    """"Just now", "5 min ago", "3 h ago", "Yesterday", "4 d ago", "05 Nov 2026"; "Never opened" for none.
    Callers lower-case it mid-sentence."""
    dt = M.parse_iso(iso)
    if not dt:
        return "Never opened"
    delta = (now or _now()) - dt
    s = int(delta.total_seconds())
    if s < 60:
        return "Just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    if delta.days == 1:
        return "Yesterday"
    if delta.days < 7:
        return f"{delta.days} d ago"
    return dt.astimezone().strftime("%d %b %Y")


def clock(iso: str | None) -> str:
    """Local "14:32" for a timestamp; "" when there is none."""
    dt = M.parse_iso(iso)
    return dt.astimezone().strftime("%H:%M") if dt else ""


def when_text(iso: str | None, now: datetime | None = None) -> str:
    """A time a register reads: "14:32" today, "yesterday", "Mon 3 Nov" this year, else "3 Nov 2025"."""
    dt = M.parse_iso(iso)
    if not dt:
        return ""
    local = dt.astimezone()
    today = (now or _now()).astimezone().date()
    if local.date() == today:
        return local.strftime("%H:%M")
    if (today - local.date()).days == 1:
        return "yesterday"
    if local.year == today.year:
        return f"{local.strftime('%a')} {local.day} {local.strftime('%b')}"
    return f"{local.day} {local.strftime('%b %Y')}"


def greeting(hour: int | None = None) -> str:
    h = datetime.now().hour if hour is None else hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


def due_text(due: str, today: date | None = None) -> str:
    """"Due today", "Due tomorrow", "Overdue 2 d", "Fri 7 Nov"; "" for no date (the task strip)."""
    try:
        d = date.fromisoformat((due or "")[:10])
    except ValueError:
        return ""
    today = today or date.today()
    days = (d - today).days
    if days < 0:
        return f"Overdue {-days} d"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


# -------------------------------------------------------------------- projects
def kinds_summary(items: Iterable[M.Item]) -> str:
    """"2 files · 1 folder · 1 link": what a project or activity holds, by kind, in order of count."""
    counts: dict[str, int] = {}
    for it in items:
        k = KIND_WORDS.get(it.kind, it.kind)
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return "No items yet"
    return " · ".join(plural(n, k) for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def subtitle_line(project: M.Project) -> str:
    """A card's second line, never blank: client (when the job number leads the title) and the
    description, else what the project holds."""
    parts = []
    if project.job_number.strip() and project.client.strip():
        parts.append(project.client.strip())
    if project.description.strip():
        parts.append(project.description.strip())
    return " · ".join(parts) or kinds_summary(project.items)


def health_line(total: int, enabled: int, last_opened: str | None, now: datetime | None = None) -> str:
    """"6 items · opened just now", "4 of 6 items · opened 2 d ago", "1 item · never opened"."""
    count = plural(total, "item") if enabled == total else f"{enabled} of {total} items"
    when = f"opened {relative_time(last_opened, now).lower()}" if last_opened else "never opened"
    return f"{count} · {when}"


def uses_text(names: list[str], word: str = "activity", many: str = "activities") -> str:
    """Who uses a root: "1 activity · P12513", or "P12513 · ANTEO +1" when a button carries the count."""
    if not names:
        return ""
    if len(names) == 1:
        return f"1 {word} · {names[0]}"
    text = " · ".join(names[:2])
    return text + (f" +{len(names) - 2}" if len(names) > 2 else "")


# ------------------------------------------------------------------ activities
def activity_title(name: str, spine: str) -> str:
    """"P12513 · Lot 7 check": the job first, unless the name already carries it."""
    if spine and spine.lower() not in name.lower():
        return f"{spine} · {name}"
    return name


def worst_status(statuses: Iterable[str]) -> str:
    """The worst health status among ``statuses`` ("" when none were checked)."""
    worst = ""
    for s in statuses:
        if HEALTH_RANK.get(s, 0) > HEALTH_RANK.get(worst, -1):
            worst = s
    return worst


def health_summary(statuses: list[str]) -> str:
    """"All 6 reachable", "1 server offline · 4 reachable"; "No paths to check yet" for none."""
    if not statuses:
        return "No paths to check yet"
    counts: dict[str, int] = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1
    if set(counts) == {"ok"}:
        return f"All {counts['ok']} reachable" if counts["ok"] > 1 else "Reachable"
    parts = [f"{counts[s]} {status_word(s).lower()}" for s in ("offline", "variable", "missing") if counts.get(s)]
    if counts.get("ok"):
        parts.append(f"{counts['ok']} reachable")
    return " · ".join(parts)


def things_line(open_count: int, identified: int) -> str:
    """"12 things open · 9 identified" (the card and the page header)."""
    if open_count <= 0:
        return "Nothing open yet"
    return f"{plural(open_count, 'thing')} open · {identified} identified"


def resume_text(name: str, count: int, taken_at: str, spine: str = "") -> tuple[str, str]:
    """The Resume band: ("Resume lot 7 check", "11 items from 14:32 · P12513 · the PC shut down while it ran")."""
    when = clock(taken_at)
    lead = f"{plural(count, 'item')} from {when}" if when else plural(count, "item")
    return f"Resume {first_lower(name)}", join_facts(lead, spine, "the PC shut down while it ran")


def launch_footer(results: list[str], elapsed_s: float = 0.0) -> str:
    """"9 opened · 2 not opened · 0 skipped · 3.4 s" from the dock's result codes (DESIGN.md: "not
    opened" counts failed, not found, offline and undefined variable; "skipped" only skips).
    The elapsed time is left out under 0.1 s."""
    done = [r for r in results if r not in ("queued", "opening", "")]
    if not done:
        return ""
    opened = sum(1 for r in done if r == "opened")
    skipped = sum(1 for r in done if r == "skipped")
    not_opened = len(done) - opened - skipped
    parts = [f"{opened} opened", f"{not_opened} not opened", f"{skipped} skipped"]
    if elapsed_s >= 0.1:
        parts.append(f"{elapsed_s:.1f} s")
    return " · ".join(parts)


def checkpoint_label(kind: str, taken_at: str, count: int) -> str:
    """"Snapshot · 14:32 · 12 things"."""
    word = {"manual": "Snapshot", "auto": "Kept by the watcher", "close": "When it ended"}.get(kind, "Snapshot")
    return join_facts(word, clock(taken_at), plural(count, "thing"))


# ------------------------------------------------------------------ hub, pulse
def _project_of(detail: str) -> str:
    for sep in (" › ", " rev ", " → "):
        if sep in detail:
            detail = detail.split(sep, 1)[0]
    return detail.strip()


def pulse_detail_names(detail: str, name_for: Callable[[str], str]) -> str:
    """The "→ login" tail of a sent pulse shown with the colleague's display name."""
    if " → " in detail:
        head, _, who = detail.rpartition(" → ")
        return f"{head} → {name_for(who)}"
    return detail


def activity_register(rows: list[dict[str, Any]], name_for: Callable[[str], str] = lambda u: u,
                      today: str | None = None) -> list[dict[str, Any]]:
    """Pulse rows as a register grouped by job: [{"project", "entries": [{"text", "rev", "by", "ts"}]}].

    Launches by one person of one job on one day fold into "opened 3× today"."""
    today = today or _now().date().isoformat()
    groups: dict[str, dict[str, Any]] = {}
    folds: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: str(x.get("ts", "")), reverse=True):
        detail = pulse_detail_names(str(r.get("detail", "")), name_for)
        who = str(r.get("name") or name_for(str(r.get("user", ""))))
        ev = str(r.get("event", ""))
        ts = str(r.get("ts", ""))
        project = _project_of(detail) or "(unknown project)"
        g = groups.setdefault(project, {"project": project, "entries": []})
        if ev == "launched":
            day = ts[:10]
            key = (project, who, day)
            if key in folds:
                folds[key]["count"] += 1
                folds[key]["text"] = f"opened {folds[key]['count']}× {'today' if day == today else 'on ' + day}"
                continue
            entry = {"text": "opened" + (f" › {detail.split(' › ', 1)[1]}" if " › " in detail else ""),
                     "rev": "", "by": who, "ts": ts, "count": 1}
            folds[key] = entry
            g["entries"].append(entry)
        elif ev == "published":
            rev = detail.split(" rev ", 1)[1] if " rev " in detail else ""
            g["entries"].append({"text": "published", "rev": rev.split(" ")[0] if rev else "", "by": who, "ts": ts})
        elif ev == "sent":
            to = detail.split(" → ", 1)[1] if " → " in detail else ""
            g["entries"].append({"text": f"sent to {to}" if to else "sent", "rev": "", "by": who, "ts": ts})
        else:
            g["entries"].append({"text": ev, "rev": "", "by": who, "ts": ts})
    return list(groups.values())


def initials(name: str) -> str:
    parts = [p for p in (name or "").replace(".", " ").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()
