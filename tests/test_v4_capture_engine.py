"""CaptureEngine: passes, cadence, writes, checkpoints, requests (fake desktop; no COM)."""
from __future__ import annotations

import threading
import time

from project_opener.capture.engine import CaptureEngine, EngineCallbacks, EngineConfig
from project_opener.capture.identify import Identifier
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M
from project_opener.core.snapshots import SnapshotStore

MON = [M.Monitor("D1", [0, 0, 1920, 1080], [0, 0, 1920, 1040], 96, True)]


class PathSource:
    """Identifies windows whose title is a path; counts calls."""

    def __init__(self, delay=0.0):
        self.calls = 0
        self.delay = delay

    def identify(self, windows, ctx):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return {w.hwnd: M.SnapshotEntry(key="", status="identified", kind="file", path=w.title, identified_by="shell")
                for w in windows if w.title.startswith("U:")}


class Rig:
    def __init__(self, tmp_path, delay=0.0, interval=3.0):
        self.t = 0.0
        self.desk: list[WindowInfo] = [WindowInfo(1, r"U:\a.pdf", "C", 5, "x.exe"),
                                       WindowInfo(2, "Calculator", "C", 6, "calc.exe")]
        self.monitors = list(MON)
        self.src = PathSource(delay)
        self.got: dict[str, list] = {"snap": [], "cp": [], "ident": [], "cands": [], "err": [], "done": []}
        cb = EngineCallbacks(on_snapshot=self.got["snap"].append, on_checkpoint=self.got["cp"].append,
                             on_identified=lambda h, e, p: self.got["ident"].append((h, e, p)),
                             on_candidates=self.got["cands"].append, on_error=self.got["err"].append,
                             on_restore_done=self.got["done"].append)
        self.store = SnapshotStore(tmp_path)
        self.engine = CaptureEngine(
            self.store, cb, EngineConfig(interval_s=interval, ignore_rules=[{"process": "calc.exe"}]),
            enumerate_fn=lambda ex: [w for w in self.desk if w.pid not in ex], monitors_fn=lambda: self.monitors,
            identifier_factory=lambda cfg: Identifier(sources=[self.src], ignore_rules=cfg.ignore_rules,
                                                      recent_fn=lambda: {},
                                                      window_info_fn=lambda h: next((w for w in self.desk
                                                                                     if w.hwnd == h), None)),
            com=False, clock=lambda: self.t)
        self.engine.identifier = self.engine._make_identifier()

    def pass_(self):
        self.engine._scheduled_pass()


def test_pass_emits_on_change_writes_live_at_most_every_10_s(tmp_path):
    r = Rig(tmp_path)
    e = r.engine
    e._handle(("run", "act1", [M.Item(path=r"U:\a.pdf", id="i1")]))
    r.pass_()
    assert len(r.got["snap"]) == 1
    s = r.got["snap"][0]
    assert [x.path for x in s.entries] == [r"U:\a.pdf"]          # calc.exe ignored
    assert s.entries[0].item_id == "i1" and s.full
    assert r.store.live("act1") is not None                       # first write immediately
    r.t = 3.0
    r.pass_()
    assert len(r.got["snap"]) == 1                                # nothing changed: no callback, no write
    r.desk.append(WindowInfo(3, r"U:\b.pdf", "C", 5, "x.exe"))
    r.t = 6.0
    r.pass_()
    assert len(r.got["snap"]) == 2
    assert len(r.store.live("act1").entries) == 1                 # changed, but within 10 s of the last write
    r.t = 12.0
    r.pass_()
    assert len(r.store.live("act1").entries) == 2


def test_cadence_full_refresh_every_30s_and_on_display_change(tmp_path):
    r = Rig(tmp_path)
    r.engine._handle(("run", "act1", []))
    fulls = []
    for i in range(12):
        r.t = i * 3.0
        r.pass_()
        fulls.append(r.engine.stats[-1]["full"])
    assert fulls == [True] + [False] * 9 + [True, False]
    r.monitors = MON + [M.Monitor("D2", [1920, 0, 3840, 1080], [1920, 0, 3840, 1040], 96, False)]
    r.t += 3
    r.pass_()
    assert r.engine.stats[-1]["full"]
    assert r.engine._next_due == r.t + 3.0


def test_adaptive_skip_when_a_pass_is_slow(tmp_path):
    r = Rig(tmp_path, delay=0.05, interval=0.09)
    r.engine._handle(("run", "act1", []))
    r.pass_()
    assert r.engine.stats[-1]["skipped_next"]
    assert abs(r.engine._next_due - (r.t + 0.18)) < 1e-9


def test_incremental_pass_asks_sources_only_for_new_windows(tmp_path):
    r = Rig(tmp_path)
    r.engine._handle(("run", "act1", []))
    r.pass_()
    calls = r.src.calls
    r.t = 3.0
    r.pass_()
    assert r.src.calls == calls and r.engine.stats[-1]["queried"] == 0


def test_snapshot_now_stores_checkpoint_and_heartbeat(tmp_path):
    r = Rig(tmp_path)
    r.store.mark_running(M.RunningMarker("act1", last_seen="2000-01-01T00:00:00+00:00"))
    r.engine._handle(("run", "act1", []))
    r.engine._handle(("snapshot", "manual", "before lunch"))
    cp = r.got["cp"][0]
    assert cp.kind == "manual" and cp.label == "before lunch" and cp.snapshot.open_count == 1
    assert r.store.checkpoints("act1")[0].id == cp.id
    r.t = 61.0
    r.pass_()
    assert r.store.markers()[0].last_seen != "2000-01-01T00:00:00+00:00"


def test_snapshot_without_activity_is_an_error(tmp_path):
    r = Rig(tmp_path)
    r.engine._handle(("snapshot", "manual", ""))
    assert r.got["err"] and not r.got["cp"]


def test_end_flushes_pending_live_snapshot(tmp_path):
    r = Rig(tmp_path)
    r.engine._handle(("run", "act1", []))
    r.pass_()
    r.desk.append(WindowInfo(3, r"U:\b.pdf", "C", 5, "x.exe"))
    r.t = 3.0
    r.pass_()
    assert len(r.store.live("act1").entries) == 1
    r.engine._handle(("end",))
    assert len(r.store.live("act1").entries) == 2


def test_identify_and_enumerate_requests(tmp_path):
    r = Rig(tmp_path)
    r.engine._handle(("run", "act1", [M.Item(path=r"U:\a.pdf", id="i1")]))
    r.engine._handle(("identify", 1, "add"))
    h, e, purpose = r.got["ident"][0]
    assert h == 1 and e.path == r"U:\a.pdf" and e.item_id == "i1" and purpose == "add"
    r.engine._handle(("enumerate",))
    cands = r.got["cands"][0]
    assert {c.process for c in cands} == {"x.exe", "calc.exe"}        # every window, ignored ones marked
    assert "ignored by capture" in next(c for c in cands if c.process == "calc.exe").note


def test_hover_requests_coalesce(tmp_path):
    r = Rig(tmp_path)
    e = r.engine
    e.request_identify(1, "hover")
    e.request_identify(2, "hover")
    e.request_identify(1, "hover")
    assert e._q.qsize() == 1
    e._handle(e._q.get_nowait())
    assert [(h, p) for h, _e, p in r.got["ident"]] == [(1, "hover")]


def test_restore_request_uses_platform_and_resets_cadence(tmp_path):
    r = Rig(tmp_path)

    class P:
        def existing_hwnds(self):
            return set()

        def windows(self):
            return []

        def identify(self, w, p, full):
            return []

        def monitors(self):
            return MON

        def now(self):
            return 0.0

        def sleep(self, s):
            pass
    r.engine._platform_factory = lambda ident, cfg: P()
    r.engine._handle(("restore", M.Snapshot("act1"), []))
    assert r.got["done"][0]["opened"] == 0 and r.engine._next_due == 0.0


def test_real_thread_runs_passes_and_stops(tmp_path):
    seen = threading.Event()
    store = SnapshotStore(tmp_path)
    desk = [WindowInfo(1, r"U:\a.pdf", "C", 5, "x.exe")]
    eng = CaptureEngine(store, EngineCallbacks(on_snapshot=lambda s: seen.set()),
                        EngineConfig(interval_s=0.05), enumerate_fn=lambda ex: desk, monitors_fn=lambda: MON,
                        identifier_factory=lambda cfg: Identifier(sources=[PathSource()], recent_fn=lambda: {}),
                        com=False)
    eng.start()
    try:
        eng.run_activity("act1", [])
        assert seen.wait(3.0)
        assert eng.alive
    finally:
        eng.stop()
    assert not eng.alive
    assert store.live("act1") is not None
