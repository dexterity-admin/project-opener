"""Juror round 1 fixes in the sheets, the Hub, Settings and Updates (round 2, 5 November 2026).

* D4: the floating shadow's offset rings exist on dark only; light floats a surface on its border ring.
* T4: people by display name (groups, the published "for" line, the For field's chips); the login only in a
  tooltip; the @ picker never offers the user themself.
* Brief 3: "Mail this task" opens a draft (Outlook, else mailto:) with names, not logins.
* T6: the Settings page remembers its tab.
* Brief 6: Update sources (the LAN mirror's reachability) and "Copy this version to the Team Hub" for the
  version the office runs (installed builds only; otherwise the reason).
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from test_v4_hub_apis import FakeApp, qapp  # noqa: E402,F401

from project_opener import constants as C  # noqa: E402
from project_opener.core import mail  # noqa: E402
from project_opener.core import models as M  # noqa: E402
from project_opener.quick.settings_api import SETTINGS_TABS, SettingsApi  # noqa: E402
from project_opener.quick.ui_state import tokens_for  # noqa: E402

QML = Path(__file__).resolve().parents[1] / "project_opener" / "qml"


@pytest.fixture
def office(qapp, tmp_path, hub_root):  # noqa: F811
    vikram = FakeApp(tmp_path / "v", hub_root, "vikram", "Vikram")
    yokesh = FakeApp(tmp_path / "y", hub_root, "yokesh", "Yokesh")
    priya = FakeApp(tmp_path / "p", hub_root, "priya", "Priya")
    for a in (vikram, yokesh, priya):
        a.sync()
    return vikram, yokesh, priya


# ------------------------------------------------------------------ D4
def test_light_has_no_offset_shadow_dark_keeps_it():
    light = tokens_for(False, "#0E7C5B", "comfortable")
    dark = tokens_for(True, "#0E7C5B", "comfortable")
    assert light["shadow_q"] == light["shadow_soft"] == "#00000000"
    assert dark["shadow_q"] != "#00000000" and dark["shadow_soft"] != "#00000000"
    for name in ("Sheet.qml", "Toasts.qml", "MentionPicker.qml"):
        text = (QML / "components" / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "shadow_soft" in line or "shadow_q" in line:
                assert "visible: app.ui.dark" in line or "app.ui.dark" in text, (name, line)


# ------------------------------------------------------------------ T4
def test_picker_never_offers_me_and_names_replace_logins(office):
    vikram, yokesh, priya = office
    vikram.hub.setMentionQuery("")
    logins = [r["login"] for r in vikram.hub.mentionCandidates.rows]
    assert "vikram" not in logins and {"yokesh", "priya"} <= set(logins)
    vikram.hub.setMentionQuery("vik")
    assert vikram.hub.mentionCandidates.rows == []

    vikram.hub.saveGroup("checkers", ["priya", "yokesh"], "")
    vikram.hub._force_refresh()
    row = vikram.hub.groups.get(vikram.hub.groups.indexOf("checkers"))
    assert row["members"] == ["priya", "yokesh"] and row["memberNames"] == "Priya, Yokesh"
    assert vikram.hub.nameFor("yokesh") == "Yokesh" and vikram.hub.nameFor("checkers") == "@checkers"
    assert vikram.hub.nameFor("vikram") == "Vikram"
    assert vikram.hub.for_text(["priya", "checkers"]) == "for Priya, @checkers"
    assert vikram.hub.for_text([]) == ""


def test_published_for_line_reads_names(office):
    vikram, yokesh, _ = office
    proj = vikram.ctx.store.add(M.Project("Lot 7", job_number="P12513"))
    vikram.hub.publishProject(proj.id, "Lot 7 set", ["yokesh"])
    yokesh.sync()
    row = next(r for r in yokesh.hub.published.rows if r["title"].startswith("P12513"))
    assert row["forText"] == "for Yokesh" and row["forTip"] == "@yokesh"
    assert row["authorName"] == "Vikram"


# ------------------------------------------------------------------ brief 3
def test_mail_this_task_opens_a_draft_by_name(office, monkeypatch):
    vikram, yokesh, _ = office
    proj = vikram.ctx.store.add(M.Project("Lot 7", job_number="P12513"))
    act = vikram.ctx.store.add_activity(M.Activity("Lot 7 check", project_ids=[proj.id]))
    tid = vikram.tasks.create("Back-check lot 7", "yokesh", "2026-11-07", "activity", act.id)
    yokesh.sync()
    yokesh.tasks.setDone(tid, True)
    vikram.sync()

    urls: list[str] = []
    monkeypatch.setattr(mail, "_outlook_display", lambda draft: False)      # no Outlook on this PC
    monkeypatch.setattr(mail, "_open_url", lambda url: urls.append(url) or True)
    vikram.ctx.settings.mail_client = "outlook"
    vikram.tasks.mailTask(tid)
    assert len(urls) == 1 and urls[0].startswith("mailto:")
    body = unquote(urls[0])
    assert "subject=Task: Back-check lot 7" in body
    assert "Owner: Yokesh" in body and "by Yokesh" in body and "by yokesh" not in body
    assert "For: P12513 · Lot 7 check (P12513)" in body
    assert f"projectopener://task/{tid}" in body
    assert not vikram.toasts                                                  # something opened: no warning

    monkeypatch.setattr(mail, "_open_url", lambda url: False)
    vikram.tasks.mailTask(tid)
    assert vikram.toasts and vikram.toasts[-1][0] == "No mail program answered"


def test_task_draft_names_the_one_who_finished():
    t = M.Task("Back-check lot 7", "yokesh", "2026-11-07", created_by="vikram")
    t.mark_done("yokesh", True)
    d = mail.task_draft(t, "projectopener://task/x", "Yokesh", "Yokesh")
    assert "Done: " in d.body_text and d.body_text.split("Done: ", 1)[1].split("\n")[0].endswith("by Yokesh")
    assert d.subject == "Task: Back-check lot 7"


def test_mail_this_task_is_reachable_from_the_row_and_the_sheet():
    row = (QML / "components" / "TaskRow.qml").read_text(encoding="utf-8")
    sheet = (QML / "sheets" / "TaskSheet.qml").read_text(encoding="utf-8")
    assert "Mail this task" in row and "app.tasks.mailTask(model.taskId)" in row
    assert "Mail this task" in sheet and "app.tasks.mailTask(s.taskId)" in sheet
    assert 'visible: s.taskId !== ""' in sheet                                # editing only


# ------------------------------------------------------------------ T6
def test_settings_remembers_its_tab(office):
    vikram = office[0]
    api = SettingsApi(vikram)
    assert api.settingsTab == "profile"
    api.setSettingsTab("pill")
    assert api.settingsTab == "pill"
    api.setSettingsTab("nonsense")
    assert api.settingsTab == "pill"
    assert set(SETTINGS_TABS) >= {"profile", "appearance", "snapshot", "pill", "cliq", "updates"}
    page = (QML / "pages" / "SettingsPage.qml").read_text(encoding="utf-8")
    for key in SETTINGS_TABS:
        assert f'visible: page.tab === "{key}"' in page, key


# ------------------------------------------------------------------ brief 6
def test_update_sources_and_the_reason_a_source_run_cannot_copy(office):
    vikram = office[0]
    api = SettingsApi(vikram)
    lan = api.updateSources[0]
    assert lan["name"] == "LAN mirror" and lan["label"] == "Checking…"
    api.refreshSources()                                                      # synchronous in FakeApp
    lan, gh = api.updateSources
    assert lan["status"] == "ok" and lan["label"] == "Reachable" and lan["detail"].endswith("no installer yet")
    assert gh["name"] == "GitHub releases" and gh["label"] == "Not checked yet"
    assert api.mirrorCurrentShown is True
    assert "runs from source" in api.mirrorCurrentReason                      # pytest is not a frozen build
    api.mirrorCurrent()
    assert vikram.toasts[-1][0] == "Cannot copy this version"


def test_no_hub_no_mirror(qapp, tmp_path):  # noqa: F811
    app = FakeApp(tmp_path / "solo", None, "vikram", "Vikram")
    api = SettingsApi(app)
    assert api.updateSources[0]["label"] == "Not set"
    assert api.mirrorCurrentShown is False


def test_copy_this_version_to_the_hub_when_installed(office, monkeypatch, tmp_path):
    vikram = office[0]
    api = SettingsApi(vikram)
    monkeypatch.setattr(C, "is_frozen", lambda: True)
    api.refreshSources()
    assert api.mirrorCurrentReason == ""
    installer = tmp_path / f"ProjectOpener-Setup-{C.VERSION}.exe"
    installer.write_bytes(b"MZ installer")
    calls: list[str] = []
    updater = vikram.ctx.updater

    def fetch(tag):
        calls.append(tag)
        from project_opener.update.updater import UpdateInfo
        return UpdateInfo(version=C.VERSION, installer=installer.name, sha256="", url="https://example.invalid/x.exe")

    monkeypatch.setattr(updater, "fetch_release", fetch)
    monkeypatch.setattr(updater, "download", lambda info, progress=None: installer)
    api.mirrorCurrent()
    assert calls == [f"v{C.VERSION}"]
    hub_updates = vikram.ctx.hub.updates_dir()
    assert (hub_updates / installer.name).is_file() and (hub_updates / "latest.json").is_file()
    assert vikram.toasts[-1][0] == "Copied to the Team Hub"
    assert api.updateState == "idle" and api.mirrorVersion == ""
    assert api.updateSources[0]["detail"].endswith(f"holds {C.VERSION}")


def test_mirror_without_a_hub_folder_never_writes_to_the_working_folder(tmp_path, monkeypatch):
    from project_opener.update.updater import UpdateInfo, Updater
    monkeypatch.chdir(tmp_path)
    installer = tmp_path / "ProjectOpener-Setup-9.9.9.exe"
    installer.write_bytes(b"MZ")
    with pytest.raises(RuntimeError):
        Updater(lan_dir=None).mirror_to_lan(UpdateInfo("9.9.9", installer.name, ""), installer)
    assert not (tmp_path / "latest.json").exists()
