import json

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.store import WorkspaceStore


def test_add_update_remove_persists(store, isolated_data_dir):
    p = store.add(M.Project(name="P12513"))
    assert (isolated_data_dir / C.WORKSPACE_FILE).exists()
    p.items.append(M.Item(path=r"Z:\a.pdf"))
    store.update(p)
    again = WorkspaceStore(isolated_data_dir)
    assert again.get(p.id).items[0].path == r"Z:\a.pdf"
    again.remove(p.id)
    assert WorkspaceStore(isolated_data_dir).projects == []


def test_duplicate_names_are_suffixed(store):
    store.add(M.Project(name="Same"))
    second = store.add(M.Project(name="same"))
    assert second.name == "same (2)"


def test_backups_rotate(store):
    for i in range(3):
        store.add(M.Project(name=f"p{i}"))
    assert len(store.backups()) >= 2


def test_backups_unique_within_one_clock_tick(store, isolated_data_dir, monkeypatch):
    """CI (fast runner): several saves inside one clock tick each keep a backup, in save order; the
    rotation keeps MAX_BACKUPS and never touches the pre-v4 backup."""
    from datetime import datetime as real_datetime

    from project_opener.core import store as store_mod

    class Frozen(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 5, 10, 0, 0, 123456)

    monkeypatch.setattr(store_mod, "datetime", Frozen)
    bdir = isolated_data_dir / C.BACKUP_DIR
    bdir.mkdir(exist_ok=True)
    pre = bdir / f"{C.PRE_V4_BACKUP_PREFIX}20261101-090000.json"
    pre.write_text("{}", encoding="utf-8")
    for i in range(5):
        store.add(M.Project(name=f"p{i}"))
    names = [p.name for p in store.backups()]
    assert len(names) == len(set(names)) >= 4
    assert names == sorted(names, reverse=True)
    assert names[0].endswith(f"-123456-{len(names) - 1:02d}.json")   # the newest save sorts first
    for i in range(C.MAX_BACKUPS + 3):
        store.add(M.Project(name=f"q{i}"))
    assert len(store.backups()) == C.MAX_BACKUPS
    assert pre.exists()


def test_corrupt_workspace_restores_backup(store, isolated_data_dir):
    store.add(M.Project(name="keep"))
    store.add(M.Project(name="also"))
    (isolated_data_dir / C.WORKSPACE_FILE).write_text("{not json", encoding="utf-8")
    recovered = WorkspaceStore(isolated_data_dir)
    assert "keep" in recovered.names()
    assert (isolated_data_dir / "workspace.corrupt.json").exists()


def test_v1_auto_migration(tmp_path, monkeypatch, isolated_data_dir):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "projects.json").write_text(json.dumps({"Old": {"files": ["C:/a.txt"], "notes": "n"}}), encoding="utf-8")
    (legacy / "auto_launch.json").write_text(json.dumps({"Old": True}), encoding="utf-8")
    monkeypatch.setattr(C, "legacy_v1_dir", lambda: legacy)
    s = WorkspaceStore(isolated_data_dir)
    assert s.migrated_from == "Project Opener 1.x"
    assert s.by_name("Old").auto_launch is True


def test_import_v2_file(store, tmp_path):
    f = tmp_path / "vikram.json"
    f.write_text(json.dumps({"projects": {"ANTEO": {"activities": [{"name": "A", "items": [{"type": "file", "path": "C:/x"}]}]}}}),
                 encoding="utf-8")
    assert store.import_v2_file(f, author="vikram") == 1
    assert store.by_name("ANTEO").launch_sets[0].name == "A"


def test_export_import_bundle_merge_and_replace(store):
    store.add(M.Project(name="A"))
    bundle = store.export_bundle()
    other = store.add(M.Project(name="B"))
    added, updated = store.import_bundle(bundle, mode="merge")
    assert (added, updated) == (0, 1)
    assert store.get(other.id) is not None
    added, updated = store.import_bundle(bundle, mode="replace")
    assert store.names() == ["A"]


def test_import_v1_backup_format(store):
    data = {"projects": {"Legacy": {"files": [{"path": "C:/f.pdf", "selected": True}], "notes": ""}},
            "auto_launch": {"Legacy": True}}
    added, _ = store.import_bundle(data)
    assert added == 1 and store.by_name("Legacy").auto_launch


def test_history_and_stats(store):
    p = store.add(M.Project(name="H", items=[M.Item(path="x")]))
    store.record_launch(p, p.items, ok=1)
    assert store.get(p.id).open_count == 1
    st = store.stats()
    assert st["launches_total"] == 1 and st["launches_today"] == 1
    assert store.history()[0]["project"] == "H"


def test_sorting_pinned_first(store):
    a = store.add(M.Project(name="b"))
    store.add(M.Project(name="a"))
    store.toggle_pin(a.id)
    assert [p.name for p in store.sorted_projects("name")] == ["b", "a"]
    store.toggle_pin(a.id)
    assert [p.name for p in store.sorted_projects("name")] == ["a", "b"]


def test_listeners_called(store):
    seen = []
    store.subscribe(lambda ev, payload: seen.append(ev))
    store.add(M.Project(name="x"))
    assert "added" in seen and "saved" in seen
