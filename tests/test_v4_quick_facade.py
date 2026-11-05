"""The facade's own sub-APIs (builder 4): model roles, ActivitiesApi over a seeded store, UiState routing,
motion guard and palette, SettingsApi coercion and side effects."""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.quick import activities_api as AA  # noqa: E402
from project_opener.quick.listmodel import DictListModel  # noqa: E402

CONTRACT_ACTIVITY_ROLES = (
    "activityId", "name", "label", "icon", "dotColor", "spine", "projectTitle", "itemCount", "openCount",
    "lastOpened", "lastOpenedText", "pinned", "running", "captureOn", "openNow", "identifiedNow",
    "needsPathNow", "healthWorst", "healthText", "taskLine", "ownerName", "published",
)
CONTRACT_PROJECT_ROLES = (
    "projectId", "name", "title", "spine", "client", "dotColor", "icon", "itemCount", "activityCount",
    "pinned", "healthWorst", "healthText", "lastOpenedText", "published",
)
CONTRACT_ITEM_ROLES = ("itemId", "name", "path", "kind", "group", "projectId", "projectTitle", "health",
                       "healthLabel", "profileName", "itemEnabled", "order")
CONTRACT_DOCK_ROLES = ("order", "name", "path", "group", "status", "statusLabel", "message")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(ms: int = 50) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.005)


@pytest.fixture
def seeded(isolated_data_dir, tmp_path):
    from project_opener.core.store import WorkspaceStore
    docs = tmp_path / "docs"
    docs.mkdir()
    for n in ("a.pdf", "b.xlsx", "c.docx"):
        (docs / n).write_bytes(b"x")
    store = WorkspaceStore(isolated_data_dir)
    p1 = M.Project(name="As-built isometrics", job_number="P12513", client="FST", color="#2F5BFF",
                   items=[M.Item(path=str(docs / "a.pdf"), group="Checking"), M.Item(path=str(docs / "b.xlsx"))])
    p2 = M.Project(name="ANTEO Isometrics", client="ANTEO", color="#10B981", items=[M.Item(path=str(docs / "c.docx"))])
    store.add(p1)
    store.add(p2)
    store.activities.clear()
    act = M.Activity(name="Lot 7 check", project_ids=[p1.id],
                     items=[M.ActivityItem.from_item(p1.items[0], p1.id, p1.items[0].id),
                            M.ActivityItem.from_item(p1.items[1], p1.id, p1.items[1].id),
                            M.ActivityItem.from_item(p2.items[0], p2.id, p2.items[0].id)])
    for it in act.items:
        it.id = M.new_id()
    store.add_activity(act)
    return {"dir": isolated_data_dir, "docs": docs, "p1": p1.id, "p2": p2.id, "act": act.id}


@pytest.fixture
def facade(qapp, seeded):
    from project_opener.quick.facade import AppFacade
    app = AppFacade(seeded["dir"])
    app.ctx.launcher.dry_run = True
    app.ctx.settings.capture_enabled = False
    app.activities.refresh()
    yield app
    app.deleteLater()
    pump(20)


# ----------------------------------------------------------------- models
def test_listmodel_refuses_reserved_roles():
    with pytest.raises(ValueError):
        DictListModel(["name", "color"])
    with pytest.raises(ValueError):
        DictListModel(["index"])


def test_listmodel_sync_keeps_rows_in_place(qapp):
    m = DictListModel(["rowId", "label"], key="rowId",
                      rows=[{"rowId": "a", "label": "A"}, {"rowId": "b", "label": "B"}, {"rowId": "c", "label": "C"}])
    changed: list = []
    m.dataChanged.connect(lambda tl, br, roles: changed.append((tl.row(), list(roles))))
    m.sync([{"rowId": "c", "label": "C"}, {"rowId": "a", "label": "A2"}])
    assert [r["rowId"] for r in m.rows] == ["c", "a"]
    assert m.get(1)["label"] == "A2"
    assert changed and changed[-1][0] == 1                     # only the changed row, only its role


def test_api_models_carry_the_contract_roles():
    assert set(CONTRACT_ACTIVITY_ROLES) <= set(AA.ACTIVITY_ROLES)
    assert set(CONTRACT_PROJECT_ROLES) <= set(AA.PROJECT_ROLES)
    assert set(CONTRACT_ITEM_ROLES) <= set(AA.ITEM_ROLES)
    assert set(CONTRACT_DOCK_ROLES) <= set(AA.DOCK_ROLES)
    for roles in (AA.ACTIVITY_ROLES, AA.PROJECT_ROLES, AA.ITEM_ROLES, AA.DOCK_ROLES):
        DictListModel(roles)                                    # no reserved names


# ------------------------------------------------------------- activities
def test_activity_rows(facade, seeded):
    m = facade.activities.activities
    assert m.rowCount() == 1
    row = m.get(0)
    assert row["title"] == "P12513 · Lot 7 check"
    assert row["spine"] == "P12513"
    assert row["itemCount"] == 3 and row["projectCount"] == 2
    assert row["subtitle"].startswith("FST · 3 items from 2 projects")
    assert row["dotColor"] == "#2F5BFF"                         # the first project's colour
    assert row["lastOpenedText"] == "3 items · never opened"
    assert row["running"] is False and row["captureOn"] is False   # capture is off globally in the fixture
    assert facade.activities.projects.rowCount() == 2


def test_select_fills_items_in_launch_order(facade, seeded):
    facade.activities.select(seeded["act"])
    items = facade.activities.items
    assert [items.get(i)["order"] for i in range(items.rowCount())] == [1, 2, 3]
    assert items.get(2)["projectTitle"] == "ANTEO Isometrics"
    assert facade.activities.current["activityId"] == seeded["act"]


def test_move_add_remove_items(facade, seeded):
    api, aid = facade.activities, seeded["act"]
    api.select(aid)
    first = api.items.get(0)["itemId"]
    api.moveItem(aid, first, 2)
    api.refresh()
    assert api.items.get(2)["itemId"] == first
    new = str(seeded["docs"] / "new.pdf")
    api.addPaths(aid, [new, new, str(seeded["docs"] / "a.pdf")])  # duplicates and an existing path are skipped
    act = facade.ctx.store.activity(aid)
    assert len(act.items) == 4
    api.removeItem(aid, act.items[-1].id)
    assert len(facade.ctx.store.activity(aid).items) == 3


def test_add_project_item_links_it(facade, seeded):
    api = facade.activities
    p2 = facade.ctx.store.get(seeded["p2"])
    aid = api.create("Handover", seeded["p2"])
    api.addProjectItem(aid, p2.id, p2.items[0].id)
    api.addProjectItem(aid, p2.id, p2.items[0].id)               # once only
    act = facade.ctx.store.activity(aid)
    assert len(act.items) == 1 and act.items[0].source_item_id == p2.items[0].id
    assert act.project_ids == [p2.id]


def test_edit_fields(facade, seeded):
    api, aid = facade.activities, seeded["act"]
    api.edit(aid, {"name": "Lot 8 check", "shortName": "Lot 8", "captureOn": False, "resumeOnStart": False,
                   "icon": "ruler", "projectIds": [seeded["p2"], "nope"]})
    act = facade.ctx.store.activity(aid)
    assert (act.name, act.short_name, act.capture_enabled, act.resume_on_start) == ("Lot 8 check", "Lot 8", False, False)
    assert act.icon == "ph.ruler" and act.project_ids == [seeded["p2"]]
    api.togglePin(aid)
    assert facade.ctx.store.activity(aid).pinned


def test_open_over_the_limit_asks_first(facade, seeded):
    api = facade.activities
    facade.ctx.settings.confirm_launch_over = 2
    asked: list = []
    api.confirmNeeded.connect(lambda rid, aid, n: asked.append((rid, aid, n)))
    finished: list = []
    api.launchFinished.connect(lambda aid, summary: finished.append(summary))
    api.open(seeded["act"])
    assert asked and asked[0][1:] == (seeded["act"], 3)
    assert not api.dockOpen
    api.answerConfirm(asked[0][0], True)
    assert api.dockOpen and api.dock.rowCount() == 3
    deadline = time.monotonic() + 10
    while not finished and time.monotonic() < deadline:
        pump(30)
    assert finished and finished[0].startswith("3 opened · 0 not opened")
    assert [api.dock.get(i)["statusLabel"] for i in range(3)] == ["Opened"] * 3
    assert facade.ctx.store.activity(seeded["act"]).open_count == 1


def test_resume_band_from_a_stale_marker(facade, seeded):
    facade.snapshots.mark_running(M.RunningMarker(activity_id=seeded["act"], pid=999_999))
    facade.activities._compute_resume()
    r = facade.activities.resume
    assert r["activityId"] == seeded["act"] and r["title"] == "Resume lot 7 check"
    assert "the PC shut down while it ran" in r["text"]
    facade.activities.dismissResume()
    assert facade.activities.resume == {}
    assert facade.snapshots.markers() == []


def test_projects_filter(facade, seeded):
    api = facade.activities
    api.setProjectFilter("anteo", "")
    assert api.projects.rowCount() == 1 and api.projects.get(0)["projectId"] == seeded["p2"]
    api.setProjectFilter("", "")
    assert api.projects.rowCount() == 2


def test_project_crud(facade):
    api = facade.activities
    pid = api.createProject({"name": "Clash review", "jobNumber": "P14414", "tags": "3D, review", "icon": "cube"})
    p = facade.ctx.store.get(pid)
    assert (p.title, p.tags, p.icon) == ("P14414 · Clash review", ["3D", "review"], "ph.cube")
    api.addProjectPaths(pid, [r"D:\Projects\P14414", r"D:\Projects\P14414\\"])
    assert len(facade.ctx.store.get(pid).items) == 1
    aid = api.newActivityFromProject(pid)
    assert facade.ctx.store.activity(aid).items[0].project_id == pid


# --------------------------------------------------------------- ui state
def test_routes_and_back(facade):
    ui = facade.ui
    ui.go("projects", {})
    ui.go("project", {"projectId": "x"})
    assert ui.route == "project" and ui.routePayload == {"projectId": "x"} and ui.canGoBack
    ui.go("nowhere", {})
    assert ui.route == "project"
    ui.back()
    assert ui.route == "projects"


def test_motion_guard_drops_and_saves(facade):
    from project_opener.quick import motion as MO
    ui, s = facade.ui, facade.ctx.settings
    s.motion = "auto"
    ui.set_machine(MO.MachineFacts(screen_w=1920, screen_h=1080), "rhi")
    assert ui.motion == "rich" and ui.k == 1.0 and ui.ambient
    said: list = []
    ui.motionReduced.connect(said.append)
    ui.reportDockFrames(45.0, 60.0)
    assert ui.motion == "rich"
    ui.reportDockFrames(45.0, 60.0)
    assert ui.motion == "purposeful" and s.motion_reduced_to == "purposeful" and len(said) == 1
    assert ui.k == pytest.approx(0.6) and not ui.ambient
    ui.setMotion("rich")                                         # a choice clears the reduction
    assert ui.motion == "rich" and s.motion_reduced_to == ""


def test_explicit_motion_is_not_reduced(facade):
    ui = facade.ui
    ui.setMotion("rich")
    ui.reportDockFrames(80.0, 300.0)
    ui.reportDockFrames(80.0, 300.0)
    assert ui.motion == "rich"


def test_theme_tokens(facade):
    ui = facade.ui
    ui.setTheme("light")
    assert ui.dark is False and ui.tokens["bg"] == "#F5F8F6"
    assert ui.tokens["scrim"].startswith("#") and len(ui.tokens["shadow_q"]) == 9
    ui.setTheme("dark")
    assert ui.dark is True and ui.tokens["bg"] == "#0F1211"


def test_icons_map_old_names(facade):
    ui = facade.ui
    assert ui.glyph("house") != ""
    assert ui.glyph("fa5s.ship") == ui.glyph("anchor")
    assert ui.glyph("ph.ruler") == ui.glyph("ruler")


def test_palette_groups(facade):
    ui = facade.ui
    ui.setPaletteQuery("")
    rows = ui.palette.rows
    headings = [r["title"] for r in rows if r["rowKind"] == "heading"]
    assert headings == ["Activities", "Projects", "Actions"]
    ui.setPaletteQuery("b.xlsx")
    assert [r["title"] for r in ui.palette.rows if r["rowKind"] == "heading"] == ["Activities", "Projects", "Items"]
    ui.setPaletteQuery("zzzz-nothing")
    assert ui.palette.rowCount() == 0


# ---------------------------------------------------------------- settings
def test_settings_coercion_and_side_effects(facade):
    from project_opener.quick.settings_api import coerce
    assert coerce("launch_delay_ms", 150.0) == 150
    assert coerce("show_toasts", "false") is False
    assert coerce("variables", None) == {}
    api = facade.settings
    seen: list = []
    api.changed.connect(seen.append)
    api.setValue("confirm_launch_over", 12.0)
    assert facade.ctx.settings.confirm_launch_over == 12 and seen == ["confirm_launch_over"]
    api.setValue("theme", "light")
    assert facade.ui.dark is False
    api.setVariable("server_root", r"\\nas01\Project")
    assert facade.ctx.settings.variables == {"{SERVER_ROOT}": r"\\nas01\Project"}
    assert api.value("cliq_token_enc") is None                  # secrets never reach QML
    api.setValue("github_token_enc", "x")
    assert facade.ctx.settings.github_token_enc == ""
