"""Automatic watchers: derived from the cards' own items, reconciled as cards change, switchable in Settings."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.core.settings import Settings  # noqa: E402
from project_opener.core.watchers import auto_watcher_specs, reconcile_auto_watchers  # noqa: E402
from project_opener.lan.hub import TeamHub  # noqa: E402
from project_opener.quick.watchers_api import WatchersApi  # noqa: E402
from project_opener.ui.context import AppContext  # noqa: E402

NAS_IN = "\\\\nas01\\P12513\\Incoming"


def folder(path: str, project_id: str = "") -> M.ActivityItem:
    return M.ActivityItem(path=path, kind="folder", project_id=project_id)


def file(path: str) -> M.ActivityItem:
    return M.ActivityItem(path=path, kind="file")


# ------------------------------------------------------------------ pure
def test_specs_from_folders_and_servers_only():
    a = M.Activity("Back check", items=[folder(NAS_IN), file("Z:\\iso\\A.pdf"), file("D:\\local\\b.pdf"),
                                         M.ActivityItem(path="https://example.com", kind="url")])
    specs = auto_watcher_specs([a], [], {"Z:": "\\\\nas02\\share"})
    assert specs[f"folder:{NAS_IN.lower()}"] == {"kind": "folder", "target": NAS_IN, "name": "Watch Incoming",
                                                 "activity_id": a.id, "project_id": ""}
    assert {k for k in specs if k.startswith("health:")} == {"health:\\\\nas01", "health:\\\\nas02"}
    assert len(specs) == 3                          # the local disk D: and the link make none


def test_specs_variable_root_and_project_folder():
    p = M.Project("P12513", items=[M.Item(path="{SERVER_ROOT}\\Jobs\\P12513", kind="folder")])
    specs = auto_watcher_specs([], [p])
    assert specs["folder:{server_root}\\jobs\\p12513"]["project_id"] == p.id
    assert specs["health:{server_root}"]["target"] == "{SERVER_ROOT}"


def test_one_folder_watcher_however_many_cards_hold_it():
    p = M.Project("P1", items=[M.Item(path=NAS_IN + "\\", kind="folder")])
    a = M.Activity("A", items=[folder(NAS_IN, p.id)])
    specs = auto_watcher_specs([a], [p])
    assert [k for k in specs if k.startswith("folder:")] == [f"folder:{NAS_IN.lower()}"]
    assert specs[f"folder:{NAS_IN.lower()}"]["activity_id"] == a.id


def test_reconcile_creates_once_and_never_twice():
    a = M.Activity("A", items=[folder(NAS_IN)])
    specs = auto_watcher_specs([a], [])
    first, removed = reconcile_auto_watchers([], specs, set())
    assert removed == [] and {w.kind for w in first} == {"folder", "health"}
    fw = next(w for w in first if w.kind == "folder")
    assert fw.events == ["new"] and fw.activity_id == a.id and fw.auto_key
    again, removed = reconcile_auto_watchers(first, specs, set())
    assert again == first and removed == []


def test_reconcile_respects_switch_dismissed_and_manual():
    specs = auto_watcher_specs([M.Activity("A", items=[folder(NAS_IN)])], [])
    assert reconcile_auto_watchers([], specs, set(), create=False) == ([], [])
    fkey = f"folder:{NAS_IN.lower()}"
    out, _ = reconcile_auto_watchers([], specs, {fkey})
    assert [w.kind for w in out] == ["health"]
    manual = M.Watcher("Mine", kind="folder", target=NAS_IN + "\\")
    out, _ = reconcile_auto_watchers([manual], specs, set())
    assert [w.auto_key for w in out if w.kind == "folder"] == [""]      # the hand-made one covers it


def test_reconcile_removes_and_relinks():
    a = M.Activity("A", items=[folder(NAS_IN)])
    made, _ = reconcile_auto_watchers([], auto_watcher_specs([a], []), set())
    made[0].notify.toast = False                                        # a user edit
    b = M.Activity("B", items=[folder(NAS_IN)])
    moved, removed = reconcile_auto_watchers(made, auto_watcher_specs([b], []), set())
    fw = next(w for w in moved if w.kind == "folder")
    assert removed == [] and fw.activity_id == b.id and fw.id == made[0].id and fw.notify.toast is False
    gone, removed = reconcile_auto_watchers(moved, {}, set(), create=False)
    assert gone == [] and sorted(removed) == sorted(w.id for w in moved)


def test_watcher_auto_key_round_trips():
    w = M.Watcher("x", auto_key="folder:z:\\a")
    assert M.Watcher.from_dict(w.to_dict()).auto_key == "folder:z:\\a"
    assert M.Watcher.from_dict({"name": "old"}).auto_key == ""


# ------------------------------------------------------------------- api
@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeApp(QObject):
    toast = Signal(str, str, str)

    def __init__(self, data_dir):
        super().__init__()
        self.ctx = AppContext(data_dir)
        self.ctx.user = "vikram"
        self.ctx.hub = TeamHub(None, "vikram", "Vikram")
        self.watchers = WatchersApi(self)

    def run_async(self, fn, done=None, fail=None):
        r = fn()
        if done:
            done(r)

    def run_on_gui(self, fn):
        fn()


@pytest.fixture
def app(qapp, tmp_path):
    a = FakeApp(tmp_path / "data")
    a.watchers.start()
    yield a
    a.watchers.shutdown()


def autos(app):
    return [w for w in app.ctx.store.watchers if w.auto_key]


def test_api_card_created_and_items_gained(app):
    store = app.ctx.store
    act = store.add_activity(M.Activity("Back check", items=[folder(NAS_IN)]))
    assert {w.kind for w in autos(app)} == {"folder", "health"}
    rows = [app.watchers.watchers.rows[i] for i in range(len(app.watchers.watchers.rows))]
    assert all(r["auto"] for r in rows)
    act.items.append(folder("\\\\nas01\\P12513\\Outgoing"))
    store.update_activity(act)
    store.update_activity(act)                                          # re-save: no duplicates
    assert sorted(w.target for w in autos(app) if w.kind == "folder") == [NAS_IN, "\\\\nas01\\P12513\\Outgoing"]
    assert len(autos(app)) == 3
    act.items = [i for i in act.items if i.path != NAS_IN]
    store.update_activity(act)
    assert [w.target for w in autos(app) if w.kind == "folder"] == ["\\\\nas01\\P12513\\Outgoing"]
    store.remove_activity(act.id)
    assert autos(app) == []


def test_api_deleted_auto_watcher_stays_deleted(app):
    store = app.ctx.store
    act = store.add_activity(M.Activity("A", items=[folder(NAS_IN)]))
    fw = next(w for w in autos(app) if w.kind == "folder")
    app.watchers.remove(fw.id)
    store.update_activity(act)
    assert [w.kind for w in autos(app)] == ["health"]
    assert Settings.load(app.ctx.settings._root).auto_watchers_dismissed == [fw.auto_key]
    act.items = []                                                      # folder leaves: the dismissal is forgotten
    store.update_activity(act)
    assert app.ctx.settings.auto_watchers_dismissed == []


def test_api_switch_off_makes_none_and_on_catches_up(app):
    app.ctx.settings.auto_watchers = False
    app.ctx.store.add_activity(M.Activity("A", items=[folder(NAS_IN)]))
    assert autos(app) == []
    wid = app.watchers.create("folder", "C:\\mine", [], {}, {})
    assert app.ctx.store.watcher(wid).auto_key == ""
    app.ctx.settings.auto_watchers = True
    app.watchers._on_setting("auto_watchers")
    assert {w.kind for w in autos(app)} == {"folder", "health"}
    assert app.ctx.store.watcher(wid) is not None


def test_api_edit_keeps_auto_link(app):
    app.ctx.store.add_activity(M.Activity("A", items=[folder(NAS_IN)]))
    fw = next(w for w in autos(app) if w.kind == "folder")
    app.watchers.edit(fw.id, {"name": "Incoming drawings", "events": ["new", "changed"]})
    app.watchers.setEnabled(fw.id, False)
    w = app.ctx.store.watcher(fw.id)
    assert (w.name, w.events, w.enabled, w.auto_key) == ("Incoming drawings", ["new", "changed"], False, fw.auto_key)
