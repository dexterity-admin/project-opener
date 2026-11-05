"""Shared copy (ui/text.py): plurals, times, the pill words, the dock footer, the Resume band."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from project_opener.core import models as M
from project_opener.ui import text as T

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize("n, word, many, expected", [
    (1, "item", "", "1 item"), (2, "item", "", "2 items"), (0, "item", "", "0 items"),
    (2, "activity", "", "2 activities"), (3, "day", "", "3 days"), (2, "box", "", "2 boxes"),
    (2, "person", "people", "2 people"),
])
def test_plural(n, word, many, expected):
    assert T.plural(n, word, many) == expected


def test_relative_time():
    assert T.relative_time(None) == "Never opened"
    assert T.relative_time((NOW - timedelta(seconds=10)).isoformat(), NOW) == "Just now"
    assert T.relative_time((NOW - timedelta(minutes=5)).isoformat(), NOW) == "5 min ago"
    assert T.relative_time((NOW - timedelta(hours=3)).isoformat(), NOW) == "3 h ago"
    assert T.relative_time((NOW - timedelta(days=1, hours=1)).isoformat(), NOW) == "Yesterday"
    assert T.relative_time((NOW - timedelta(days=4)).isoformat(), NOW) == "4 d ago"


def test_health_line_never_reads_like_a_launch_result():
    assert T.health_line(6, 6, None) == "6 items · never opened"
    assert T.health_line(6, 4, (NOW - timedelta(days=2)).isoformat(), NOW) == "4 of 6 items · opened 2 d ago"
    assert T.health_line(1, 1, NOW.isoformat(), NOW) == "1 item · opened just now"


def test_launch_footer_counts_not_opened_and_skipped_apart():
    codes = ["opened"] * 9 + ["offline", "variable", "skipped"]
    assert T.launch_footer(codes, 3.4) == "9 opened · 2 not opened · 1 skipped · 3.4 s"
    assert T.launch_footer(["opened", "opening", "queued"], 0.05) == "1 opened · 0 not opened · 0 skipped"
    assert T.launch_footer(["queued", "opening"]) == ""


def test_launch_words_are_the_pill_words():
    assert T.LAUNCH_META["offline"] == ("bad", "Server offline")
    assert T.LAUNCH_META["variable"] == ("warn", "Undefined variable")
    assert T.LAUNCH_META["missing"] == ("warn", "Not found")
    assert T.STATUS_META["ok"] == ("ok", "Reachable")


def test_resume_band_text():
    title, line = T.resume_text("Lot 7 check", 11, "", "P12513")
    assert title == "Resume Lot 7 check"                  # the name keeps its case (juror T5)
    assert line == "11 items · P12513 · the PC shut down while it ran"
    _t, at = T.resume_text("Lot 7 check", 6, "2026-11-05T09:32:00+00:00")
    assert at.startswith("6 things open at ")                 # the snapshot's open count, as the toast and checkpoint
    title, _ = T.resume_text("GAD review", 1, "")
    assert title == "Resume GAD review"                   # an acronym keeps its case


def test_first_lower():
    assert T.first_lower("Lot 7 check") == "lot 7 check"
    assert T.first_lower("P12513 lot") == "P12513 lot"
    assert T.first_lower("ANTEO handover") == "ANTEO handover"


def test_health_summary_and_worst():
    assert T.health_summary([]) == "No paths to check yet"
    assert T.health_summary(["ok", "ok"]) == "All 2 reachable"
    assert T.health_summary(["ok", "offline", "variable", "ok"]) == "1 server offline · 1 undefined variable · 2 reachable"
    assert T.worst_status(["ok", "missing", "offline"]) == "offline"
    assert T.worst_status([]) == ""


def test_due_text():
    today = date(2026, 11, 5)                             # a Thursday
    assert T.due_text("2026-11-05", today) == "Due today"
    assert T.due_text("2026-11-06", today) == "Due tomorrow"
    assert T.due_text("2026-11-03", today) == "Overdue 2 d"
    assert T.due_text("2026-11-10", today) == "Tue 10 Nov"
    assert T.due_text("", today) == ""


def test_things_line_and_activity_title():
    assert T.things_line(12, 9) == "12 things open · 9 identified"
    assert T.things_line(0, 0) == "Nothing open yet"
    assert T.activity_title("Lot 7 check", "P12513") == "P12513 · Lot 7 check"
    assert T.activity_title("P12513 lot 7", "P12513") == "P12513 lot 7"


def test_kinds_summary_and_subtitle():
    p = M.Project(name="ANTEO", items=[M.Item(path="a.pdf"), M.Item(path="b.pdf"),
                                       M.Item(path="https://x", kind="url")])
    assert T.kinds_summary(p.items) == "2 files · 1 link"
    assert T.subtitle_line(p) == "2 files · 1 link"
    p.client, p.job_number, p.description = "FST", "P12513", "Lot 7"
    assert T.subtitle_line(p) == "FST · Lot 7"


def test_register_folds_launches():
    rows = [{"ts": "2026-11-05T09:00:00", "user": "vikram", "event": "launched", "detail": "P12513 · Lot 7 check"},
            {"ts": "2026-11-05T10:00:00", "user": "vikram", "event": "launched", "detail": "P12513 · Lot 7 check"},
            {"ts": "2026-11-05T11:00:00", "user": "yokesh", "event": "published", "detail": "ANTEO Isometrics rev 2"}]
    reg = T.activity_register(rows, today="2026-11-05")
    lot7 = next(g for g in reg if g["project"] == "P12513 · Lot 7 check")
    assert [e["text"] for e in lot7["entries"]] == ["opened 2× today"]
    anteo = next(g for g in reg if g["project"] == "ANTEO Isometrics")
    assert anteo["entries"][0]["rev"] == "2"


def test_initials():
    assert T.initials("Vikram") == "V"
    assert T.initials("Priya Raman") == "PR"
    assert T.initials("") == "?"
