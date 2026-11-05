"""v4 data model: round trips, tolerance, and the schema 3 -> 4 migration of a seeded 3.2 workspace."""
import json

import pytest

from project_opener import constants as C
from project_opener.core import migrate
from project_opener.core import models as M
from project_opener.core.store import WorkspaceStore


def roundtrip(obj):
    """to_dict -> JSON text -> from_dict, as the store and the hub do it."""
    data = json.loads(json.dumps(obj.to_dict()))
    return type(obj).from_dict(data)


# ------------------------------------------------------------------ fixtures
def placement():
    return M.WindowPlacement(show_cmd=3, normal_rect=[1950, 20, 2850, 520], window_rect=[1920, -4, 3840, 1036],
                             monitor="\\\\.\\DISPLAY1", monitor_rect=[1920, -4, 3840, 1076])


def entry(status="identified", path=r"\\nas01\Project\P12513\ISO\Line list.xlsx", item_id="a1"):
    kind = "url" if path.startswith("http") else "file"
    return M.SnapshotEntry(key=f"path:{path.lower()}", status=status, kind=kind, path=path,
                           title="Line list.xlsx - Excel", process="EXCEL.EXE", exe=r"C:\Office\EXCEL.EXE",
                           window_class="XLMAIN", app="Excel", identified_by="office-com", doc_name="Line list.xlsx",
                           candidates=[], note="", item_id=item_id, placement=placement(), hwnd=1234, pid=99)


def snapshot():
    return M.Snapshot(activity_id="act1", full=True,
                      monitors=[M.Monitor("\\\\.\\DISPLAY1", [1920, -4, 3840, 1076], [1920, -4, 3840, 1036], 96, False),
                                M.Monitor("\\\\.\\DISPLAY2", [0, 0, 1920, 1080], [0, 0, 1920, 1040], 120, True)],
                      entries=[entry(),
                               entry("ambiguous", "", ""),
                               M.SnapshotEntry(key="win:acad.exe|Drawing1.dwg - AutoCAD", status="unsaved",
                                               title="Drawing1.dwg - AutoCAD", process="acad.exe",
                                               note="unsaved - cannot be restored"),
                               entry(path="https://github.com/dexterity-admin/project-opener", item_id="")])


ALL_V4 = [
    lambda: M.ActivityItem(path=r"Z:\P12513\ISO\a.pdf", kind="file", label="Iso", args="", enabled=False,
                           group="Checking", profile_id="prof1", project_id="p1", source_item_id="i1"),
    lambda: M.Activity(name="Lot 7 check", short_name="Lot 7", description="d", notes="n", icon="ph.ruler",
                       color="#2F5BFF", project_ids=["p1", "p2"],
                       items=[M.ActivityItem(path=r"\\nas01\x.xlsx", project_id="p1", source_item_id="i9")],
                       owner="vikram", created_by="priya", pinned_at="2026-11-05T09:00:00+00:00", favorite=True,
                       capture_enabled=False, resume_on_start=False, last_opened="2026-11-05T10:00:00+00:00",
                       open_count=4, origin=M.Origin("team", "priya", "pub1", "2026-11-04T00:00:00+00:00", 3)),
    lambda: M.Monitor("\\\\.\\DISPLAY2", [0, 0, 1920, 1080], [0, 0, 1920, 1040], 144, True),
    placement,
    entry,
    snapshot,
    lambda: M.Checkpoint(activity_id="act1", snapshot=snapshot(), kind="close", label="Before lunch"),
    lambda: M.RunningMarker(activity_id="act1", pid=4242, process_started=1730790000.5, host="PC-07"),
    lambda: M.TaskLink(kind="project", local_id="p1", published_id="pub1", title="P12513 · Iso", job_number="P12513"),
    lambda: M.Task(title="Back-check lot 7", owner="yokesh", due="2026-11-07", created_by="vikram",
                   link=M.TaskLink(local_id="act1", title="P12513 · Lot 7 check"), note="@priya see sheet 4",
                   mentions=["priya"], done_at="2026-11-06T12:00:00+00:00", done_by="yokesh"),
    lambda: M.Notify(toast=False, mentions=["@checkers"], cliq_dm=True, cliq_channel="p12513"),
    lambda: M.Watcher(name="Rev C drops", kind="folder", target=r"\\nas01\Project\P12513\ISO\Revision C",
                      events=["new", "changed"], interval_s=120, params={"pattern": "*.pdf", "recursive": False},
                      notify=M.Notify(mentions=["@priya"], cliq_dm=True), activity_id="act1", project_id="p1",
                      enabled=False, created_by="vikram"),
    lambda: M.WatchEvent(watcher_id="w1", event="new", title="New sheet", detail="P12513-001.pdf",
                         path=r"\\nas01\x\P12513-001.pdf", link="projectopener://activity/act1", level="warning"),
    lambda: M.Group(name="checkers", members=["priya", "ravi"], color="#10B981", created_by="vikram",
                    updated_by="priya"),
    lambda: M.LaunchProfile(name="Navisworks clash", app="navisworks", exe=r"C:\Nav\Roamer.exe", args='"{ITEM}"',
                            cwd=r"D:\Models", env={"NW_SEARCHSETS": r"\\nas01\sets"}, description="x",
                            author="ravi", published_id="pp1"),
    lambda: M.RootObservation(root="\\\\nas01", status="offline", since="2026-11-05T09:40:00+00:00",
                              jobs=["P12513", "ANTEO"], items=14),
    lambda: M.HealthObservation(user="vikram", host="PC-07",
                                roots=[M.RootObservation(root="Z:", status="missing", jobs=["DM-GAD"])]),
]


@pytest.mark.parametrize("make", ALL_V4, ids=lambda f: type(f()).__name__)
def test_every_v4_dataclass_round_trips(make):
    obj = make()
    assert roundtrip(obj) == obj


def test_item_profile_id_round_trips_and_old_items_default():
    it = M.Item(path=r"C:\Nav\Roamer.exe", kind="app", profile_id="prof1")
    assert roundtrip(it) == it
    assert M.Item.from_dict({"path": "x.pdf"}).profile_id == ""


def test_workspace_round_trips():
    ws = M.Workspace(projects=[M.Project(name="P12513", items=[M.Item(path="a.pdf")])],
                     activities=[ALL_V4[1]()], profiles=[ALL_V4[-3]()], watchers=[ALL_V4[11]()],
                     migration={"from_schema": 3})
    again = M.Workspace.from_dict(json.loads(json.dumps(ws.to_dict("4.0.0"))))
    assert again == ws


@pytest.mark.parametrize("cls", [M.Activity, M.ActivityItem, M.SnapshotEntry, M.Snapshot, M.Checkpoint,
                                 M.RunningMarker, M.Task, M.Watcher, M.WatchEvent, M.Group, M.LaunchProfile,
                                 M.HealthObservation, M.Workspace, M.Monitor])
def test_from_dict_tolerates_garbage(cls):
    bad = {"items": "nope", "entries": [1, None, "x"], "snapshot": 5, "placement": [1, 2], "monitors": {},
           "members": "@solo", "env": ["a"], "events": ["bogus"], "kind": "weird", "status": "?",
           "interval_s": "fast", "open_count": "many", "rect": [1, 2, "x", 4], "color": "red", "roots": "no",
           "projects": None, "activities": [{}], "schema": "x", "pid": "nan", "due": 20261107}
    obj = cls.from_dict(bad)          # must not raise
    assert obj is not None
    cls.from_dict({})
    cls.from_dict(None)


def test_tolerance_details():
    assert M.Watcher.from_dict({"kind": "weird", "events": ["bogus"]}).kind == "folder"
    assert M.Watcher.from_dict({"kind": "hub"}).events == list(M.WATCHER_EVENTS["hub"])
    assert M.Watcher.from_dict({"interval_s": 1}).interval_s == 10
    assert M.Group.from_dict({"name": "@Checkers ", "members": ["@priya", "priya", "ravi"]}).members == ["priya", "ravi"]
    assert M.Activity.from_dict({"color": "red"}).color == ""
    assert M.SnapshotEntry.from_dict({"status": "??", "process": "a.exe", "title": "T"}).key == "win:a.exe|T"
    assert M.WindowPlacement.from_dict(None) is None
    assert M.TaskLink.from_dict("x") is None


def test_snapshot_counts_and_activity_helpers():
    s = snapshot()
    assert (s.open_count, s.identified_count, s.needs_path_count) == (4, 2, 1)
    assert [e.path for e in s.new_entries] == ["https://github.com/dexterity-admin/project-opener"]
    assert s.new_entries[0].to_item("p1").kind == "url"
    a = M.Activity(name="A very long activity name indeed")
    assert a.label.endswith("…") and len(a.label) <= 18
    a.items.append(M.ActivityItem(path="Z:\\Jobs\\P1\\"))
    assert a.item_by_path("z:\\jobs\\p1") is a.items[0]
    c = a.clone()
    assert c.id != a.id and c.items[0].id != a.items[0].id and c.items[0].path == a.items[0].path


# ----------------------------------------------------------------- migration
def seeded_v32_workspace() -> dict:
    """A 3.2 workspace.json as 3.2 wrote it (no profile_id, no activities)."""
    def item(iid, path, enabled=True, group=""):
        return {"id": iid, "path": path, "kind": M.guess_kind(path), "label": "", "args": "", "enabled": enabled,
                "group": group, "added_at": "2026-10-31T17:00:00+00:00"}
    return {
        "schema": 3, "app_version": "3.2.0", "saved_at": "2026-11-04T10:00:00+00:00",
        "projects": [
            {"id": "p12513", "name": "As-built isometrics", "job_number": "P12513", "client": "FST",
             "color": "#2F5BFF", "icon": "fa5s.drafting-compass", "tags": ["as-built"], "description": "lot 7",
             "notes": "n", "pinned_at": None, "favorite": True, "auto_launch": True,
             "created_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-11-01T00:00:00+00:00",
             "last_opened": "2026-11-04T09:00:00+00:00", "open_count": 14,
             "origin": {"source": "team", "author": "yokesh", "published_id": "pub9", "published_at": "x",
                        "revision": 2},
             "items": [item("i1", r"\\nas01\Project\P12513\ISO", group="Folders"),
                       item("i2", r"{SERVER_ROOT}\P12513\Rulings.docx", enabled=False, group="References"),
                       item("i3", r"Z:\P12513\Line list.xlsx"),
                       item("i4", "https://portal.example.com")],
             "launch_sets": [
                 {"id": "set1", "name": "Checking", "item_ids": ["i3", "i2", "gone", "i3"], "icon": "fa5s.check"},
                 {"id": "set2", "name": "Submission", "item_ids": ["i1"], "icon": "fa5s.rocket"},
                 {"id": "set3", "name": "Empty", "item_ids": [], "icon": "fa5s.rocket"},
             ]},
            {"id": "dmgad", "name": "Mangala Piping GAD", "job_number": "DM-GAD", "color": "#F97316",
             "pinned_at": "2026-10-20T00:00:00+00:00",
             "items": [item("g1", r"Z:\Project\Mangala\GAD"), item("g2", r"Z:\x.pdf", enabled=False)],
             "launch_sets": []},
            {"id": "anteo", "name": "ANTEO Isometrics", "items": [item("a1", r"D:\Projects\ANTEO")],
             "launch_sets": []},
        ],
    }


def test_migrate_workspace_rules():
    data = seeded_v32_workspace()
    ws = migrate.migrate_workspace(data)
    assert ws.schema == 4
    # 1. projects unchanged (apart from the new profile_id key)
    before = [M.Project.from_dict(p).to_dict() for p in data["projects"]]
    assert [p.to_dict() for p in ws.projects] == before
    assert [len(p.launch_sets) for p in ws.projects] == [3, 0, 0]          # 4. launch sets kept
    # 2. one activity per launch set, same id, order and links; 3. pinned project without sets
    by_id = {a.id: a for a in ws.activities}
    assert set(by_id) >= {"set1", "set2", "set3"} and len(ws.activities) == 4
    checking = by_id["set1"]
    assert checking.name == "Checking" and checking.icon == "fa5s.check" and checking.color == "#2F5BFF"
    assert checking.project_ids == ["p12513"]
    assert [i.source_item_id for i in checking.items] == ["i3", "i2"]       # set order, duplicate kept once
    assert all(i.project_id == "p12513" and i.enabled for i in checking.items)  # sets ignored "enabled"
    assert checking.items[1].path == r"{SERVER_ROOT}\P12513\Rulings.docx"
    assert by_id["set3"].items == []                                         # empty sets survive
    pinned = [a for a in ws.activities if a.id not in ("set1", "set2", "set3")]
    assert len(pinned) == 1 and pinned[0].name == "Mangala Piping GAD"
    assert [i.source_item_id for i in pinned[0].items] == ["g1"] and pinned[0].pinned
    # 5. report
    r = ws.migration
    assert (r["from_schema"], r["launch_sets"], r["activities_from_sets"], r["activities_from_pinned"],
            r["dangling_item_ids"], r["items_copied"]) == (3, 3, 3, 1, 1, 4)
    # idempotent
    again = migrate.migrate_workspace(json.loads(json.dumps(ws.to_dict("4.0.0"))))
    assert [a.id for a in again.activities] == [a.id for a in ws.activities]


def test_migrate_option_skips_pinned_projects():
    ws = migrate.migrate_workspace(seeded_v32_workspace(), pinned_projects_as_activities=False)
    assert {a.id for a in ws.activities} == {"set1", "set2", "set3"}


def test_store_migrates_seeded_32_workspace(isolated_data_dir):
    path = isolated_data_dir / C.WORKSPACE_FILE
    path.write_text(json.dumps(seeded_v32_workspace(), indent=2), encoding="utf-8")
    store = WorkspaceStore(isolated_data_dir)
    assert store.migrated_from and len(store.activities) == 4 and len(store.projects) == 3
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema"] == 4 and len(saved["activities"]) == 4 and saved["migration"]["from_schema"] == 3
    keep = list((isolated_data_dir / C.BACKUP_DIR).glob(f"{C.PRE_V4_BACKUP_PREFIX}*.json"))
    assert len(keep) == 1 and json.loads(keep[0].read_text(encoding="utf-8"))["schema"] == 3
    # the pre-v4 copy is not touched by backup rotation
    for i in range(C.MAX_BACKUPS + 3):
        store.add(M.Project(name=f"p{i}"))
    assert list((isolated_data_dir / C.BACKUP_DIR).glob(f"{C.PRE_V4_BACKUP_PREFIX}*.json")) == keep
    # reload: no second migration, nothing duplicated
    again = WorkspaceStore(isolated_data_dir)
    assert again.migrated_from is None and len(again.activities) == 4
    # a 3.2 reader still finds its projects and launch sets
    raw = json.loads(path.read_text(encoding="utf-8"))
    p = M.Project.from_dict(next(x for x in raw["projects"] if x["id"] == "p12513"))
    assert [s.name for s in p.launch_sets] == ["Checking", "Submission", "Empty"]


def test_store_keeps_activity_items_in_step_with_projects(store):
    proj = store.add(M.Project(name="P1", items=[M.Item(path=r"Z:\old.pdf", id="i1")]))
    act = store.add_activity(M.Activity(name="Check", project_ids=[proj.id], items=[
        M.ActivityItem.from_item(proj.items[0], project_id=proj.id, source_item_id="i1"),
        M.ActivityItem(path=r"D:\loose.txt")]))
    events = []
    store.subscribe(lambda e, p: events.append(e))
    proj.items[0].path = r"\\nas01\new.pdf"
    store.update(proj)
    again = WorkspaceStore(store.root).activity(act.id)
    assert again.items[0].path == r"\\nas01\new.pdf" and again.items[1].path == r"D:\loose.txt"
    assert "activity_updated" in events
    assert [a.id for a in store.activities_for_project(proj.id)] == [act.id]
    store.remove_activity(act.id)
    assert WorkspaceStore(store.root).activities == []


# ------------------------------------------------------- snapshots, mentions
def test_snapshot_store_checkpoints_and_markers(isolated_data_dir):
    from project_opener.core.snapshots import SnapshotStore
    ss = SnapshotStore(isolated_data_dir)
    assert ss.live("act1") is None and ss.checkpoints("act1") == []
    ss.save_live(snapshot())
    assert ss.live("act1").open_count == 4 and ss.latest("act1").identified_count == 2
    for i in range(C.CHECKPOINTS_KEPT + 3):
        ss.add_checkpoint(M.Checkpoint(activity_id="act1", snapshot=snapshot(),
                                       taken_at=f"2026-11-05T10:{i:02d}:00+00:00", label=str(i)))
    cps = ss.checkpoints("act1")
    assert len(cps) == C.CHECKPOINTS_KEPT and cps[0].label == str(C.CHECKPOINTS_KEPT + 2)
    assert ss.checkpoint("act1", cps[3].id) == cps[3]
    ss.mark_running(M.RunningMarker(activity_id="act1", pid=1))
    ss.mark_running(M.RunningMarker(activity_id="act2", pid=1))
    assert {m.activity_id for m in ss.stale_markers()} == {"act1", "act2"}
    ss.clear_running("act1")
    assert [m.activity_id for m in ss.markers()] == ["act2"]


def test_mentions():
    from project_opener.core import mentions as X
    assert X.parse_mentions("@Priya please check, cc @checkers. mail a@b.com (@ravi) @priya") == \
        ["priya", "checkers", "ravi"]
    groups = [M.Group("checkers", ["ravi", "priya", "vikram"])]
    assert X.expand(["@checkers", "Priya", "@nobody"], groups, known_users=["ravi", "priya", "vikram"],
                    exclude="vikram") == ["ravi", "priya"]
    assert X.query_at_cursor("hello @pr", 9) == (6, "pr")
    assert X.query_at_cursor("mail a@b", 8) is None
    assert X.insert_mention("hello @pr", 9, "priya") == ("hello @priya ", 13)


def test_ipc_protocol():
    from project_opener import ipc
    data = ipc.encode({"cmd": "add", "paths": [r"Z:\a.pdf", ""]}) + b"show\nprojectopener://open/P12513\n{bad\n"
    cmds = ipc.decode(data)
    assert [c["cmd"] for c in cmds] == ["add", "show", "open"]
    assert cmds[0]["paths"] == [r"Z:\a.pdf"] and cmds[0]["v"] == C.IPC_PROTOCOL
    assert ipc.parse_link("projectopener://activity/Lot%207%20check") == ("activity", "Lot 7 check")
    assert ipc.parse_link("https://x") == ("", "")
    assert ipc.parse_link(ipc.make_link("task", "t 1")) == ("task", "t 1")


def test_motion_rule():
    from project_opener.quick import motion as MO
    gpu_big = MO.MachineFacts(gpu_ok=True, screen_w=1920, screen_h=1080)
    assert MO.resolve_motion("auto", "", gpu_big, MO.resolve_backend("auto", gpu_big)) == "rich"
    no_gpu = MO.MachineFacts(gpu_ok=False)
    assert MO.resolve_backend("auto", no_gpu) == "software"
    assert MO.resolve_motion("auto", "", no_gpu, "software") == "purposeful"
    assert MO.resolve_motion("auto", "", MO.MachineFacts(remote_session=True), "software") == "off"
    assert MO.resolve_motion("auto", "off", gpu_big, "rhi") == "off"
    assert MO.resolve_motion("rich", "off", no_gpu, "software") == "rich"


def test_dict_list_model_rejects_reserved_roles_and_syncs():
    from project_opener.quick.listmodel import DictListModel
    with pytest.raises(ValueError):
        DictListModel(["itemId", "color"])
    m = DictListModel(["rowId", "name"], key="rowId", rows=[{"rowId": "a", "name": "A"}, {"rowId": "b", "name": "B"}])
    m.sync([{"rowId": "c", "name": "C"}, {"rowId": "a", "name": "A2"}])
    assert [r["rowId"] for r in m.rows] == ["c", "a"] and m.rows[1]["name"] == "A2"
    assert m.rowCount() == 2 and m.get(0)["name"] == "C" and m.indexOf("a") == 1
