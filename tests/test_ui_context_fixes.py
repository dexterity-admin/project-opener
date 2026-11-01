"""Offscreen tests for the AppContext / hub plumbing fixed in 3.1: inbox dismissal
failures, UDP peer merging, the auto-update timer switch, revision notices,
palette actions on an empty query, and page signal disposal."""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.core.search import search_everything  # noqa: E402
from project_opener.lan.hub import Peer, TeamHub  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(app, isolated_data_dir):
    from project_opener.ui.context import AppContext
    return AppContext(isolated_data_dir)


def test_dismiss_inbox_reports_locked_file(hub_root):
    me = TeamHub(hub_root, user="vikram")
    peer = TeamHub(hub_root, user="yokesh")
    assert me.send("yokesh", M.Project(name="Hi"))
    msg = peer.inbox()[0]
    with open(msg.path, "rb"):          # Windows: an open handle blocks unlink
        locked = not peer.dismiss_inbox(msg)
    if os.name == "nt":
        assert locked
    assert peer.dismiss_inbox(msg)      # now it goes
    assert peer.dismiss_inbox(msg)      # already gone counts as success
    assert peer.inbox() == []


def test_udp_peer_is_merged_into_ctx_peers(ctx, app):
    seen = []
    ctx.peers_changed.connect(lambda peers: seen.append(list(peers)))
    ctx.peers = [Peer(user="yokesh", display_name="Yokesh", role="QA", ts=1.0, source="hub")]

    class FakeBeacon:
        display_name = "x"
        current_project = ""

        def online(self):
            now = time.time()
            return [Peer(user="yokesh", display_name="", ts=now, source="udp"),
                    Peer(user="priya", display_name="Priya", ts=now, source="udp")]

        def stop(self):
            pass

    ctx.beacon = FakeBeacon()
    ctx._on_udp_peer(Peer(user="priya"))
    app.processEvents()
    assert seen, "peers_changed was not emitted"
    users = {p.user: p for p in ctx.peers}
    assert users["priya"].online and users["priya"].source == "udp"
    assert users["yokesh"].online and users["yokesh"].role == "QA" and users["yokesh"].display_name == "Yokesh"


def test_update_timer_follows_setting(ctx):
    ctx.settings.update_check = True
    ctx.apply_settings()
    assert ctx.update_timer.isActive()
    ctx.settings.update_check = False
    ctx.apply_settings()
    assert not ctx.update_timer.isActive()


def test_revision_notice_once_per_revision(ctx):
    toasts = []
    ctx.toast_action.connect(lambda *a: toasts.append(a))
    p = M.Project(name="Clone", origin=M.Origin(source="team", author="yokesh", published_id="abc", revision=1))
    pub = type("Pub", (), {"published_id": "abc", "revision": 2, "author": "yokesh"})()
    ctx._notify_revisions([(p, pub)])
    ctx._notify_revisions([(p, pub)])
    assert len(toasts) == 1
    title, body, level, action, target = toasts[0]
    assert "Clone" in title and action == "Open project" and target[0] == "project"
    pub3 = type("Pub", (), {"published_id": "abc", "revision": 3, "author": "yokesh"})()
    ctx._notify_revisions([(p, pub3)])
    assert len(toasts) == 2


def test_palette_actions_survive_many_projects():
    projects = [M.Project(name=f"Project {i:03d}") for i in range(80)]
    actions = [("new_project", "New project", "fa5s.plus"), ("settings", "Open Settings", "fa5s.sliders-h")]
    hits = search_everything("", projects, actions, limit=40)
    assert len(hits) == 40
    assert [h.action_id for h in hits if h.kind == "action"] == ["new_project", "settings"]
    # with a query, ranking is unchanged
    hits = search_everything("sett", projects, actions, limit=40)
    assert hits[0].kind == "action" and hits[0].action_id == "settings"


def test_page_dispose_disconnects_signals(ctx, app):
    from project_opener.ui.views.home import HomePage
    page = HomePage(ctx)
    assert page._bound
    page.dispose()
    assert not page._bound
    page.deleteLater()
    app.processEvents()
    # Emitting after dispose must not reach the deleted page.
    ctx.hub_changed.emit(ctx.hub_status)
    ctx.peers_changed.emit([])
    ctx.health_updated.emit("x")
    app.processEvents()
