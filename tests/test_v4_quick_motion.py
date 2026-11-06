"""The motion level and backend rules (spikes/quick/REPORT.md "Fallback rule"; quick/motion.py)."""
from __future__ import annotations

import pytest

from project_opener.quick import motion as MO

GPU_BIG = MO.MachineFacts(gpu_ok=True, screen_w=1920, screen_h=1080)


@pytest.mark.parametrize("setting, facts, expected", [
    ("auto", GPU_BIG, "rhi"),
    ("auto", MO.MachineFacts(gpu_ok=False), "software"),
    ("auto", MO.MachineFacts(remote_session=True), "software"),
    ("gpu", MO.MachineFacts(gpu_ok=False), "rhi"),
    ("software", GPU_BIG, "software"),
])
def test_backend_rule(setting, facts, expected):
    assert MO.resolve_backend(setting, facts) == expected


@pytest.mark.parametrize("facts, backend, expected", [
    (GPU_BIG, "rhi", "rich"),
    (GPU_BIG, "software", "purposeful"),                                   # no GPU: never rich
    (MO.MachineFacts(screen_w=1366, screen_h=768), "rhi", "purposeful"),   # the unsafe row of the spike
    (MO.MachineFacts(screen_w=1440, screen_h=768), "rhi", "purposeful"),
    (MO.MachineFacts(animations_off=True), "rhi", "purposeful"),
    (MO.MachineFacts(on_battery=True), "rhi", "purposeful"),
    (MO.MachineFacts(remote_session=True), "software", "off"),
])
def test_auto_level(facts, backend, expected):
    assert MO.resolve_motion("auto", "", facts, backend) == expected


def test_explicit_choice_wins_over_machine_and_guard():
    assert MO.resolve_motion("rich", "off", MO.MachineFacts(remote_session=True), "software") == "rich"
    assert MO.resolve_motion("off", "", GPU_BIG, "rhi") == "off"


def test_auto_never_climbs_above_the_guard():
    assert MO.resolve_motion("auto", "purposeful", GPU_BIG, "rhi") == "purposeful"
    assert MO.resolve_motion("auto", "off", GPU_BIG, "rhi") == "off"
    # a reduction above what the machine earns changes nothing
    assert MO.resolve_motion("auto", "rich", MO.MachineFacts(on_battery=True), "rhi") == "purposeful"


def test_k_scale_and_next_lower():
    assert MO.K == {"rich": 1.0, "purposeful": 0.6, "off": 0.0}
    assert MO.next_lower("rich") == "purposeful"
    assert MO.next_lower("purposeful") == "off"
    assert MO.next_lower("off") == "off"


@pytest.mark.parametrize("mean, worst, slow", [
    (16.7, 40.0, False), (33.0, 120.0, False), (33.1, 50.0, True), (20.0, 120.5, True),
])
def test_slow_dock_threshold(mean, worst, slow):
    assert MO.dock_frames_too_slow(mean, worst) is slow


def test_guard_drops_one_level_after_two_slow_openings_in_a_row():
    g = MO.RuntimeGuard()
    assert g.report("rich", 40.0, 50.0) == ""            # one slow opening: stay
    assert g.report("rich", 40.0, 50.0) == "purposeful"  # two in a row: drop one level
    assert g.report("purposeful", 50.0, 200.0) == ""     # the count restarts after a drop
    assert g.report("purposeful", 50.0, 200.0) == "off"


def test_guard_needs_the_two_in_a_row():
    g = MO.RuntimeGuard()
    assert g.report("rich", 40.0, 50.0) == ""
    assert g.report("rich", 16.0, 30.0) == ""            # a good one resets
    assert g.report("rich", 40.0, 50.0) == ""


def test_guard_ignores_off():
    g = MO.RuntimeGuard()
    for _ in range(3):
        assert g.report("off", 250.0, 290.0) == ""       # off: the numbers are the launcher's cadence


def test_frame_stats():
    stamps = [i * 0.016 for i in range(11)]              # 10 gaps of 16 ms
    stamps.append(stamps[-1] + 0.1)                      # one 100 ms hitch
    mean, worst = MO.frame_stats(stamps)
    assert worst == pytest.approx(100.0, abs=0.01)       # under 100 frames the worst 1 % is the worst frame
    assert mean == pytest.approx((10 * 16 + 100) / 11, abs=0.01)
    assert MO.frame_stats([1.0]) == (0.0, 0.0)


def test_guard_leaves_out_the_click_to_first_frame():
    """The first interval is the opening's response time, the same at every level (round 3); the guard
    judges the grow's frames after it."""
    t0 = 10.0
    stamps = [t0, t0 + 0.2] + [t0 + 0.2 + i * 0.016 for i in range(1, 19)]
    assert MO.frame_stats(stamps)[1] == 200.0
    mean, worst = MO.guard_stats(stamps)
    assert worst < 17 and mean < 17 and not MO.dock_frames_too_slow(mean, worst)
    assert MO.first_frame_ms(stamps) == 200.0
    hitch = [t0, t0 + 0.016, t0 + 0.032, t0 + 0.232, t0 + 0.248]
    assert MO.guard_stats(hitch)[1] == 200.0                 # a hitch inside the grow still counts
    assert MO.guard_stats([t0, t0 + 0.3, t0 + 0.316]) == (0.0, 0.0)


def test_probe_uses_the_cache_per_adapter(monkeypatch):
    monkeypatch.setattr(MO, "primary_adapter", lambda: "NVIDIA GeForce GT 710")
    monkeypatch.setattr(MO, "_remote_session", lambda: False)
    monkeypatch.setattr(MO, "_animations_off", lambda: False)
    monkeypatch.setattr(MO, "_on_battery", lambda: False)
    calls = []
    monkeypatch.setattr(MO, "_rhi_ok", lambda: calls.append(1) or False)
    monkeypatch.setattr(MO.sys, "platform", "win32")
    cache: dict[str, str] = {}
    facts = MO.probe_machine(cache, (1920, 1080))
    assert not facts.gpu_ok and cache == {"NVIDIA GeForce GT 710": "failed"}
    facts = MO.probe_machine(cache, (1920, 1080))         # the second start reads the cache
    assert len(calls) == 1 and not facts.gpu_ok
    assert MO.resolve_backend("auto", facts) == "software"


def test_probe_basic_render_driver_is_no_gpu(monkeypatch):
    monkeypatch.setattr(MO, "primary_adapter", lambda: "Microsoft Basic Render Driver")
    monkeypatch.setattr(MO, "_rhi_ok", lambda: True)
    facts = MO.probe_machine({}, (1366, 768))
    assert facts.gpu_ok is False
    assert MO.resolve_motion("auto", "", facts, MO.resolve_backend("auto", facts)) == "purposeful"


def test_guard_window_is_cut_where_the_grow_ends():
    """endDockMeasure's timer fires late when the GUI thread is busy; frames after the window are not the grow's."""
    t0 = 5.0
    grow = [t0] + [t0 + i * 0.016 for i in range(1, 31)]            # 480 ms of smooth frames
    late = grow + [t0 + 1.3]                                          # an 820 ms stall after the grow
    cut = MO.window_stamps(late, 500)
    assert cut[-1] == t0 + 0.5 and len(cut) == len(grow) + 1
    assert MO.guard_stats(cut)[1] < 25
    stall = [t0, t0 + 0.016, t0 + 0.032, t0 + 0.9]                    # a stall that starts inside the grow
    cut = MO.window_stamps(stall, 500)
    assert cut == [t0, t0 + 0.016, t0 + 0.032, t0 + 0.5] and MO.guard_stats(cut)[1] > 400
    assert MO.window_stamps(grow, 0) == grow
