"""Quiet-time logic with fake inputs (builder 3)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication

from project_opener.desktop import quiet as Q


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.mark.parametrize(("facts", "quiet", "reason"), [
    (Q.QuietFacts(Q.QUNS_ACCEPTS_NOTIFICATIONS), False, ""),
    (Q.QuietFacts(0), False, ""),
    (Q.QuietFacts(Q.QUNS_BUSY), True, "full-screen app"),
    (Q.QuietFacts(Q.QUNS_RUNNING_D3D_FULL_SCREEN), True, "full-screen game or video"),
    (Q.QuietFacts(Q.QUNS_PRESENTATION_MODE), True, "presentation"),
    (Q.QuietFacts(Q.QUNS_QUIET_TIME), True, "do not disturb"),
    (Q.QuietFacts(Q.QUNS_APP), True, "full-screen app"),
    (Q.QuietFacts(Q.QUNS_ACCEPTS_NOTIFICATIONS, foreground_fullscreen=True), True, "full-screen window"),
    (Q.QuietFacts(Q.QUNS_PRESENTATION_MODE, remote_session=True), True, "remote desktop session"),
])
def test_decide(facts, quiet, reason):
    assert Q.decide(facts) == (quiet, reason)


def test_covers():
    mon = (0, 0, 1920, 1080)
    assert Q.covers((0, 0, 1920, 1080), mon)
    assert Q.covers((-8, -8, 1928, 1088), mon)          # a maximised-style overhang still covers
    assert not Q.covers((0, 0, 1920, 1040), mon)        # a maximised window leaves the taskbar
    assert not Q.covers((1920, 0, 3840, 1080), mon)     # the other monitor
    assert Q.covers((1920, 0, 3840, 1080), (1920, 0, 3840, 1080))


def test_watcher_emits_on_change_only(qapp):
    facts = [Q.QuietFacts(5)]
    w = Q.QuietWatcher(probe=lambda: facts[0])
    seen = []
    w.changed.connect(seen.append)
    w.check()
    facts[0] = Q.QuietFacts(Q.QUNS_BUSY)
    w.check()
    w.check()
    assert w.reason == "full-screen app"
    facts[0] = Q.QuietFacts(5)
    w.check()
    assert seen == [True, False]


def test_watcher_stop_ends_quiet_and_survives_a_bad_probe(qapp):
    w = Q.QuietWatcher(probe=lambda: Q.QuietFacts(remote_session=True))
    seen = []
    w.changed.connect(seen.append)
    w.start()
    assert w.running and w.quiet
    w.stop()
    assert not w.running and not w.quiet and seen == [True, False]

    def boom():
        raise OSError("no")
    w2 = Q.QuietWatcher(probe=boom)
    assert w2.check() is False


def test_real_probes_answer_without_error():
    assert isinstance(Q.notification_state(), int)
    assert isinstance(Q.foreground_is_fullscreen(), bool)
    assert isinstance(Q.remote_session(), bool)
