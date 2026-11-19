"""Juror round 3 copy and counts (U3-1, U3-2, C3-1, T3-2): the pure helpers behind the panel, the Open-now
headings, the checkpoint frames and the watcher rows."""
from __future__ import annotations

from project_opener.core import models as M
from project_opener.desktop.pill import panel_meta
from project_opener.quick.capture_api import live_group_counts, new_note, snapshot_glyph
from project_opener.quick.watchers_api import notify_text


def test_the_paused_panel_says_paused_in_words():
    assert panel_meta(12, 9, "10:52", paused=True) == "Capture paused · last checkpoint 10:52"
    assert panel_meta(12, 9, "", paused=True) == "Capture paused"
    assert panel_meta(12, 9, "10:52").startswith("12 open · 9 identified")


def test_the_panel_note_states_one_fact_per_count():
    assert new_note(2, 1, 0) == "2 can be saved · 1 needs a path"
    assert new_note(0, 2, 0) == "2 need a path"
    assert new_note(1, 0, 1) == "1 can be saved · 1 more to review"
    assert new_note(0, 0, 0) == ""


def test_each_open_now_heading_counts_its_own_rows():
    rows = [{"status": "identified", "toSave": True}, {"status": "identified", "toSave": True},
            {"status": "offline"}, {"status": "offline"}, {"status": "unsaved"}, {"status": "needs-path"}]
    c = live_group_counts(rows)
    assert c["identified"] == 2 and c["identifiedNew"] == 2      # not the 4 identified in the header
    assert c["offline"] == 2 and c["window"] == 1 and c["needs"] == 1
    assert "offlineNew" not in c


def test_a_checkpoint_frame_carries_its_app_glyph():
    assert snapshot_glyph("", "") == "app-window"
    assert snapshot_glyph("app", "") == "app-window"
    assert snapshot_glyph("file", r"D:\P12513\Iso checklist.pdf") != "app-window"


def test_a_watcher_promises_a_cliq_dm_only_once_linked():
    n = M.Notify(toast=True, mentions=["priya"], cliq_dm=True)
    assert notify_text(n, cliq_linked=True) == "Toast · @priya · Cliq DM"
    assert notify_text(n, cliq_linked=False) == "Toast · @priya · Cliq DM once linked"
