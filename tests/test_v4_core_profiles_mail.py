"""CAD launch profiles applied by the launcher, openers, Outlook/mailto drafts, bundle import/export."""
from __future__ import annotations

import os
from urllib.parse import unquote

import pytest

from project_opener.core import launcher as L
from project_opener.core import mail
from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver
from project_opener.core.profiles import PRESETS, build_command, split_args


@pytest.fixture
def exe(tmp_path):
    p = tmp_path / "Navis" / "Roamer.exe"
    p.parent.mkdir()
    p.write_bytes(b"MZ")
    return p


def test_split_args_windows_quotes():
    assert split_args('"C:\\a b\\x.nwd" -vp "View 1"') == ["C:\\a b\\x.nwd", "-vp", "View 1"]
    assert split_args("   ") == []


def test_build_command_variables_item_env_cwd(tmp_path, exe):
    model = tmp_path / "Models" / "P12513 site.nwd"
    model.parent.mkdir()
    model.write_text("x", encoding="utf-8")
    resolver = PathResolver({"{NAVIS}": str(exe.parent), "{JOB}": "P12513"}, drive_map={})
    prof = M.LaunchProfile("Navis", app="navisworks", exe="{NAVIS}\\Roamer.exe", args='"{ITEM}" -job {JOB}',
                           cwd=str(tmp_path / "Models"), env={"PO_JOB": "{JOB}", "PO_FILE": "{ITEM}"})
    item = M.Item(str(model), kind="file", profile_id=prof.id)
    cmd = build_command(item, prof, resolver)
    assert os.path.normcase(cmd.exe) == os.path.normcase(str(exe))
    assert cmd.args == [os.path.normpath(str(model)), "-job", "P12513"]   # a path with a space stays one argument
    assert cmd.cwd == str(tmp_path / "Models")
    assert cmd.env == {"PO_JOB": "P12513", "PO_FILE": os.path.normpath(str(model))}
    assert cmd.unresolved == []
    bad = build_command(item, M.LaunchProfile("x", args="{NOPE}"), resolver)
    assert bad.unresolved == ["{NOPE}"]


def test_presets_carry_no_unverified_switches():
    for app, preset in PRESETS.items():
        assert preset["args"] in ("", '"{ITEM}"'), app


def test_launcher_applies_profile(tmp_path, exe):
    prof = M.LaunchProfile("Navis", exe=str(exe), args="-x {ITEM}", cwd=str(tmp_path), env={"A": "1"})
    doc = tmp_path / "m.nwd"
    doc.write_text("x", encoding="utf-8")
    item = M.Item(str(doc), kind="file", profile_id=prof.id)
    lch = L.Launcher(PathResolver({}, drive_map={}), delay_ms=0, dry_run=True,
                     profiles={prof.id: prof}.get)
    res = lch.open_item(item)
    assert res.status == "opened" and "profile Navis" in res.message
    assert lch.started[0].args == ["-x", os.path.normpath(str(doc))] and lch.started[0].env == {"A": "1"}
    missing = M.LaunchProfile("Gone", exe=str(tmp_path / "nope.exe"))
    lch2 = L.Launcher(PathResolver({}, drive_map={}), dry_run=True, profiles={missing.id: missing}.get)
    r2 = lch2.open_item(M.Item(str(doc), profile_id=missing.id))
    assert r2.status == "missing" and r2.message.startswith("profile Gone:")


def test_unknown_profile_opens_plain_and_says_so(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x", encoding="utf-8")
    lch = L.Launcher(PathResolver({}, drive_map={}), dry_run=True, profiles=lambda _id: None)
    res = lch.open_item(M.Item(str(doc), profile_id="deleted"))
    assert res.status == "opened" and "launch profile deleted not found" in res.message


def test_shared_profile_lookup_survives_rebuild(tmp_path, exe):
    prof = M.LaunchProfile("Shared", exe=str(exe))
    L.set_profile_lookup({prof.id: prof}.get)
    try:
        lch = L.Launcher(PathResolver({}, drive_map={}), dry_run=True)      # as apply_settings builds it
        assert lch.open_item(M.Item(str(exe), kind="app", profile_id=prof.id)).message.startswith("profile Shared")
    finally:
        L.set_profile_lookup(None)


def test_openers_registry_and_fallback(tmp_path):
    doc = tmp_path / "sheet.xlsx"
    doc.write_text("x", encoding="utf-8")
    calls = []
    openers = {".xlsx": lambda p: calls.append(p) or True}
    lch = L.Launcher(PathResolver({}, drive_map={}), openers=openers)
    res = lch.open_item(M.Item(str(doc), kind="file"))
    assert res.status == "opened" and calls == [os.path.normpath(str(doc))]

    def broken(_p):
        raise RuntimeError("COM busy")

    opened = []
    lch.openers[".xlsx"] = broken
    lch._shell_open = lambda item, target: opened.append(target) or L.LaunchResult(item, target, "opened")
    assert lch.open_item(M.Item(str(doc), kind="file")).status == "opened" and opened
    assert L.Launcher(PathResolver({})).openers is L.OPENERS            # default: the shared registry
    L.register_opener("DOCX", len)
    try:
        assert L.OPENERS[".docx"] is len
    finally:
        L.register_opener(".docx", None)
    assert ".docx" not in L.OPENERS


def test_bundle_draft_portable_paths():
    resolver = PathResolver({"{SERVER_ROOT}": "\\\\nas01\\Project"}, drive_map={"Z:": "\\\\nas01\\Project"})
    act = M.Activity("Lot 7 check", items=[
        M.ActivityItem("Z:\\P12513\\ISO\\Rev C", kind="folder", label="Rev C"),
        M.ActivityItem("{SERVER_ROOT}\\P12513\\spec.pdf"),
        M.ActivityItem("https://intranet/p", kind="url"),
        M.ActivityItem("Z:\\off.pdf", enabled=False),
    ])
    d = mail.bundle_draft(act, resolver, "projectopener://activity/Lot%207%20check")
    assert d.subject == "Lot 7 check - 3 items"
    assert "Rev C: \\\\nas01\\Project\\P12513\\ISO\\Rev C" in d.body_text
    assert "\\\\nas01\\Project\\P12513\\spec.pdf" in d.body_text
    assert "off.pdf" not in d.body_text
    assert "projectopener://activity/Lot%207%20check" in d.body_text
    assert 'href="file://nas01/Project/P12513/spec.pdf"' in d.body_html


def test_task_draft_and_mailto_fallback():
    t = M.Task("Back-check lot 7", owner="yokesh", due="2026-11-07", note="Rev C only",
               link=M.TaskLink("activity", "a", "", "P12513 · Lot 7", "P12513"))
    d = mail.task_draft(t, "projectopener://task/abc", "Yokesh")
    assert d.subject == "Task: Back-check lot 7"
    assert "Owner: Yokesh" in d.body_text and "For: P12513 · Lot 7 (P12513)" in d.body_text
    assert d.body_text.endswith("Open in Project Opener: projectopener://task/abc")

    opened: list[str] = []

    def no_outlook(_d):
        raise OSError("Outlook not installed")

    assert mail.open_draft(d, "outlook", outlook=no_outlook, open_url=lambda u: opened.append(u) or True)
    url = opened[0]
    assert url.startswith("mailto:?subject=Task%3A%20Back-check%20lot%207&body=")
    assert "projectopener://task/abc" in unquote(url)

    shown: list[mail.Draft] = []
    assert mail.open_draft(d, "outlook", outlook=lambda x: shown.append(x) or True, open_url=lambda u: False)
    assert shown == [d]
    assert mail.open_draft(d, "mailto", outlook=lambda x: 1 / 0, open_url=lambda u: True)


def test_mailto_is_cut_to_length():
    d = mail.Draft("s", "line\n" * 2000)
    url = mail.mailto_url(d)
    assert len(url) <= mail.MAILTO_MAX + 40 and unquote(url).rstrip().endswith("...")


def test_export_import_activities_and_v3_bundle(store):
    proj = M.Project("P12513", job_number="P12513", items=[M.Item("C:\\a.pdf", id="i1")])
    store.add(proj)
    prof = M.LaunchProfile("Navis", exe="C:\\n.exe")
    store.save_profile(prof)
    act = M.Activity("Lot 7", project_ids=[proj.id],
                     items=[M.ActivityItem("C:\\a.pdf", project_id=proj.id, source_item_id="i1", profile_id=prof.id)])
    store.add_activity(act)
    bundle = store.export_bundle([proj.id])
    assert [a["name"] for a in bundle["activities"]] == ["Lot 7"] and bundle["profiles"][0]["name"] == "Navis"

    from project_opener.core.store import WorkspaceStore
    other = WorkspaceStore(store.root.parent / "other")
    assert other.import_bundle(bundle) == (1, 0)
    assert [a.name for a in other.activities] == ["Lot 7"] and other.profile(prof.id) is not None
    assert other.activities[0].items[0].project_id == other.projects[0].id

    # a 3.x export: its launch sets become activities by the migration rules; merging again does not duplicate
    v3 = {"schema": 3, "projects": [{"id": "p3", "name": "DM-GAD", "items": [{"id": "x1", "path": "C:\\g.dwg"}],
                                      "launch_sets": [{"id": "s1", "name": "Checking", "item_ids": ["x1", "gone"]}]}]}
    third = WorkspaceStore(store.root.parent / "third")
    third.import_bundle(v3)
    assert [(a.id, a.name, len(a.items)) for a in third.activities] == [("s1", "Checking", 1)]
    third.import_bundle(v3)
    assert len(third.activities) == 1
