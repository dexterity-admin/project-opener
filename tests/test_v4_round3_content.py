"""Juror round 2, content and usability items: U2-2 (names on first render), U2-3 (one new count), U2-4 (the
Updates line), T2-1 (one status table), T2-2 (the default "Never captured" list), T2-3 (@names, register)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_v4_capture_api import ent, rig  # noqa: E402,F401  (the capture API rig)
from test_v4_hub_apis import FakeApp  # noqa: E402
from test_v4_hub_apis import qapp as qapp  # noqa: E402,F401  (fixture)

from project_opener.core import mentions as MN  # noqa: E402
from project_opener.core import models as M  # noqa: E402
from project_opener.core.settings import Settings  # noqa: E402
from project_opener.core.tasks import TaskStore  # noqa: E402
from project_opener.lan.hub import TeamHub  # noqa: E402
from project_opener.ui import text as T  # noqa: E402


# ------------------------------------------------------------------ U2-2
def test_names_fall_back_to_a_capitalised_login(qapp, tmp_path, hub_root):
    v = FakeApp(tmp_path / "v", hub_root, "vikram", "")
    assert v.hub.name_for("yokesh") == "Yokesh"
    assert v.hub.name_for("vikram") == "Vikram"          # me, with no display name set
    assert MN.person_word("priya") == "Priya" and MN.person_word("") == ""


def test_tasks_rebuild_with_display_names_when_users_load(qapp, tmp_path, hub_root):
    TeamHub(hub_root, "priya", "Priya S").heartbeat()            # users/priya.json: "Priya S"
    v = FakeApp(tmp_path / "v", hub_root, "vikram", "Vikram")
    TaskStore(hub_root / "tasks").save(M.Task(title="Send rev C sheets", owner="priya", created_by="priya"))
    v.tasks.start()                                              # tasks first: the users are not known yet
    assert v.tasks.all.get(0)["ownerName"] == "Priya"            # never the raw login
    seen = []
    v.hub.usersChanged.connect(lambda: seen.append(1))
    v.hub.start()                                                # users load ahead of the full refresh
    assert seen and v.tasks.all.get(0)["ownerName"] == "Priya S"
    assert v.tasks.all.get(0)["createdByName"] == "Priya S"
    v.tasks.shutdown()
    v.hub.shutdown()


def test_home_greets_without_the_login(qapp, isolated_data_dir):
    from project_opener.quick.facade import AppFacade
    f = AppFacade(isolated_data_dir)
    f.ctx.settings.display_name = ""
    assert f.greetName == ""                                     # "Good morning", not "Good morning, vikram"
    f.settings.setValue("display_name", "Vikram")
    assert f.greetName == "Vikram"
    f.deleteLater()


# ------------------------------------------------------------------ U2-3
def test_one_new_count_is_what_the_sheet_ticks(rig):  # noqa: F811
    rig.api.startActivity(rig.act.id)
    since = [ent(r"U:\Lot 7\a.pdf"), ent(r"U:\Lot 7\b.pdf")]
    for e in since:
        e.first_seen = "2026-11-05T10:00:09+00:00"
    before = ent(r"U:\Lot 7\c.pdf")
    s = M.Snapshot(rig.act.id, entries=[*since, before, ent(status="unidentified", title="Calculator"),
                                        ent(status="unsaved", title="Book1"), ent(r"U:\Lot 7\list.xlsx")],
                   session_start="2026-11-05T10:00:00+00:00")
    before.first_seen = s.session_start
    s.entries[-1].item_id = "i1"
    rig.api._on_snapshot(s)
    assert rig.api.newCount == 5 and rig.api.newToSave == 2
    assert sorted(r["path"] for r in rig.api.live.rows if r["toSave"]) == [r"U:\Lot 7\a.pdf", r"U:\Lot 7\b.pdf"]
    rig.api.prepareSaveNew()
    assert sum(1 for r in rig.api.newCandidates.rows if r["ticked"]) == rig.api.newToSave


# ------------------------------------------------------------------ U2-4
def test_updates_line_says_when_automatic_checks_are_off(qapp, isolated_data_dir):
    from project_opener.quick.facade import AppFacade
    f = AppFacade(isolated_data_dir)
    f.ctx.settings.update_check = True
    assert f.settings.checkLine == "Updates are checked every few hours"
    f.settings.setValue("update_check", False)
    f.ctx.settings.update_last_check = ""
    assert f.settings.checkLine == "Automatic checks are off · last checked never"
    f.deleteLater()


# ------------------------------------------------------------------ T2-1
def test_one_status_table_for_every_list():
    assert T.ENTRY_META["unsaved"] == ("neutral", "Not a file")          # Drawing1
    assert T.ENTRY_META["window"] == ("neutral", "Not a file")
    assert T.ENTRY_META["unidentified"] == ("warn", "Needs a path")      # a document whose path was not found
    from pathlib import Path
    qml = Path(__file__).resolve().parents[1] / "project_opener" / "qml"
    for f in ("desktop/PillPanel.qml", "components/TickList.qml", "sheets/StartFromOpenSheet.qml"):
        src = (qml / f).read_text(encoding="utf-8")
        assert "statusMeta" in src and 'unidentified: "Needs a path"' not in src \
            and '? "Needs a path"' not in src, f


# ------------------------------------------------------------------ T2-2
def test_default_never_captured_is_the_office_chat_apps(isolated_data_dir):
    s = Settings()
    assert {r["process"] for r in s.capture_ignore} == {"ms-teams.exe", "teams.exe", "cliq.exe", "zoho cliq.exe"}
    beta = Settings()
    beta.capture_ignore = [{"process": "claude.exe"}, *s.capture_ignore]
    beta._root = isolated_data_dir  # type: ignore[attr-defined]
    beta.save()
    assert all(r["process"] != "claude.exe" for r in Settings.load(isolated_data_dir).capture_ignore)
    mine = Settings.load(isolated_data_dir)
    mine.capture_ignore = [{"process": "claude.exe"}]                  # a list the user chose stays
    mine.save()
    assert Settings.load(isolated_data_dir).capture_ignore == [{"process": "claude.exe"}]


# ------------------------------------------------------------------ T2-3
def test_mentions_show_display_names_and_keep_groups():
    names = {"vikram": "Vikram", "priya": "Priya S"}
    text, logins = MN.display_mentions("@vikram Revision C has two new sheets. cc @checkers, @priya.",
                                       lambda lg: names.get(lg, ""), ["checkers"])
    assert text == "@Vikram Revision C has two new sheets. cc @checkers, @Priya S."
    assert logins == ["vikram", "priya"]
    assert MN.display_mentions("mail me@company.com", lambda lg: "X", [])[0] == "mail me@company.com"


def test_inbox_body_reads_names(qapp, tmp_path, hub_root):
    v = FakeApp(tmp_path / "v", hub_root, "vikram", "Vikram")
    y = FakeApp(tmp_path / "y", hub_root, "yokesh", "Yokesh")
    for a in (v, y):
        a.ctx.peers = a.ctx.hub.peers()
        a.hub._force_refresh()
    y.ctx.hub.send_mention(["vikram"], "@vikram Revision C has two new sheets", "")
    v.hub._force_refresh()
    row = next(r for r in v.hub.inbox.rows if r["kind"] == "mention")
    assert row["messageText"].startswith("@Vikram Revision C") and row["mentionLogins"] == "@vikram"
