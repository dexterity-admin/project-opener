"""Office-wide path health: watch/<user>.json written by several PCs, merged."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from project_opener.core import models as M
from project_opener.lan.healthboard import HealthBoard, observe


def obs(user, roots, ts=None):
    return M.HealthObservation(user=user, host=f"{user}-pc", ts=ts or M.now_iso(),
                               roots=[M.RootObservation(*r) for r in roots])


def test_merge_from_several_users(hub_root):
    t0 = datetime(2026, 11, 5, 9, 40).astimezone()
    HealthBoard(hub_root, "vikram").write(obs("vikram", [
        ("\\\\nas01", "offline", (t0 + timedelta(minutes=5)).isoformat(), ["P12513", "DM-GAD"], 30),
        ("\\\\nas02", "ok", "", ["P2001"], 4)]))
    HealthBoard(hub_root, "priya").write(obs("priya", [
        ("\\\\nas01", "offline", t0.isoformat(), ["P12513", "P13000"], 12)]))
    HealthBoard(hub_root, "yokesh").write(obs("yokesh", [
        ("\\\\nas01", "ok", "", [], 3), ("\\\\nas02", "ok", "", [], 1)]))
    # a stale observation (a PC that went home yesterday) is ignored
    HealthBoard(hub_root, "rahul").write(obs("rahul", [("\\\\nas02", "offline", t0.isoformat(), ["X"], 1)],
                                             ts=(t0 - timedelta(days=1)).isoformat()))
    (hub_root / "watch" / "junk.json").write_text("[1, 2", encoding="utf-8")

    rows = HealthBoard(hub_root, "vikram").merged()
    assert [r.root for r in rows] == ["\\\\nas01", "\\\\nas02"]
    nas01, nas02 = rows
    assert nas01.status == "offline" and sorted(nas01.seen_by) == ["priya", "vikram"]
    assert nas01.ok_by == ["yokesh"]                              # one PC still reaches it: said, not hidden
    assert nas01.since == t0.isoformat()                          # the earliest report
    assert sorted(nas01.jobs) == ["DM-GAD", "P12513", "P13000"]
    assert "since 09:40" in nas01.text and "seen by 2 PCs" in nas01.text and "3 jobs affected" in nas01.text
    assert nas02.status == "ok" and "X" not in nas02.jobs


def test_only_own_file_is_written(hub_root):
    board = HealthBoard(hub_root, "vikram")
    board.write(obs("someone-else", [("Z:", "missing", "", [], 1)]))
    assert [p.name for p in (hub_root / "watch").iterdir()] == ["vikram.json"]
    assert board.read_all()[0].user == "vikram"
    assert HealthBoard(None, "x").merged() == []


def test_observe_keeps_since_until_status_changes():
    t1 = datetime(2026, 11, 5, 9, 40).astimezone()
    o1, prev = observe({}, {"\\\\nas01": ("offline", ["P1"], 3)}, t1)
    o2, prev = observe(prev, {"\\\\nas01": ("offline", ["P1"], 3)}, t1 + timedelta(minutes=10))
    assert o1[0].since == o2[0].since == t1.isoformat(timespec="seconds")
    o3, _ = observe(prev, {"\\\\nas01": ("ok", ["P1"], 3)}, t1 + timedelta(minutes=20))
    assert o3[0].since == (t1 + timedelta(minutes=20)).isoformat(timespec="seconds")


def test_merge_respects_now_and_stale_window(hub_root):
    HealthBoard(hub_root, "vikram").write(obs("vikram", [("Z:", "missing", "", [], 1)]))
    assert HealthBoard(hub_root, "v").merged()[0].status == "missing"
    assert HealthBoard(hub_root, "v").merged(now=time.time() + 3600) == []
