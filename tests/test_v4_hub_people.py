"""Hub v4: groups, mentions, publishing "for", published activities, shared profiles, 3.2 compatibility."""
from __future__ import annotations

import json

from project_opener.core import mentions as MN
from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver
from project_opener.lan.groups import GroupBook, clean_name
from project_opener.lan.hub import TeamHub


def office(hub_root):
    hubs = {u: TeamHub(hub_root, u, u.title()) for u in ("vikram", "priya", "yokesh", "rahul")}
    hubs["vikram"].initialise()
    for h in hubs.values():
        h.heartbeat()
    return hubs


def test_initialise_v4_dirs_and_schema(hub_root):
    (hub_root / "hub.json").write_text(json.dumps({"schema": 1, "name": "old"}), encoding="utf-8")
    TeamHub(hub_root, "vikram").initialise()
    for d in ("tasks", "watch", "delivered", "profiles", "users", "published", "inbox"):
        assert (hub_root / d).is_dir()
    meta = json.loads((hub_root / "hub.json").read_text(encoding="utf-8"))
    assert meta["schema"] == 2 and meta["name"] == "old"


def test_group_book_crud_last_writer_wins(hub_root):
    a, b = GroupBook(hub_root), GroupBook(hub_root)
    a.save(M.Group("@Checkers", ["@Priya", "yokesh", "priya"]), by="vikram")
    b.save(M.Group("P12513 team", ["rahul"]), by="priya")     # a second editor, another group
    names = [g.name for g in a.all()]
    assert names == ["checkers", "p12513-team"]
    g = a.get("checkers")
    assert g.members == ["priya", "yokesh"] and g.updated_by == "vikram"
    b.save(M.Group("checkers", ["priya"]), by="priya")        # last writer wins, records who
    assert a.get("@CHECKERS").members == ["priya"] and a.get("checkers").updated_by == "priya"
    assert a.remove("checkers") and not a.remove("checkers")
    assert clean_name("  @P12513 Team ") == "p12513-team" and clean_name("@@") == ""
    (hub_root / "groups.json").write_text("{broken", encoding="utf-8")
    assert a.all() == []
    assert GroupBook(None).all() == []


def test_mention_expansion_through_groups(hub_root):
    hubs = office(hub_root)
    GroupBook(hub_root).save(M.Group("checkers", ["priya", "yokesh", "vikram"]))
    v = hubs["vikram"]
    assert v.expand_targets(["@checkers"]) == ["priya", "yokesh"]           # the sender is left out
    assert v.expand_targets(["@checkers"], include_self=True) == ["priya", "yokesh", "vikram"]
    assert v.expand_targets(["rahul", "typo", "../evil"]) == ["rahul"]      # unknown names reach nobody
    text = "Rev C is out @checkers, also @Rahul. mail me at vikram@dex.com"
    assert MN.parse_mentions(text) == ["checkers", "rahul"]
    assert v.expand_targets(MN.parse_mentions(text)) == ["priya", "yokesh", "rahul"]


def test_publish_project_for_targets_lands_in_inboxes(hub_root):
    hubs = office(hub_root)
    GroupBook(hub_root).save(M.Group("checkers", ["priya", "yokesh"]))
    proj = M.Project("P12513 Checking", job_number="P12513", items=[M.Item("Z:\\P12513\\ISO")])
    resolver = PathResolver({}, drive_map={"Z:": "\\\\nas01\\Project"})
    pub = hubs["vikram"].publish(proj, resolver.portable, "Rev C for checking", ["@checkers"])
    raw = json.loads((hub_root / "published" / f"{pub.published_id}.json").read_text(encoding="utf-8"))
    assert raw["type"] == "project" and raw["for"] == ["checkers"]
    assert raw["project"]["items"][0]["path"] == "\\\\nas01\\Project\\P12513\\ISO"
    for user in ("priya", "yokesh"):
        msgs = hubs[user].inbox()                      # the 3.2 reader still sees project entries
        assert len(msgs) == 1 and msgs[0].project.name == "P12513 Checking"
        assert hubs[user].inbox_entries()[0]["published_id"] == pub.published_id
    assert hubs["rahul"].inbox() == [] and hubs["vikram"].inbox() == []
    pulse = hubs["vikram"].pulse_feed()[0]
    assert pulse["kind"] == "published" and pulse["mentions"] == ["checkers"] and pulse["event"] == "published"


def test_published_activity_portable_and_invisible_to_32(hub_root):
    hubs = office(hub_root)
    proj = M.Project("Lot 7", job_number="P12513")
    act = M.Activity("Lot 7 check", project_ids=[proj.id], items=[
        M.ActivityItem("Z:\\P12513\\ISO\\Rev C", kind="folder", project_id=proj.id, source_item_id="i1"),
        M.ActivityItem("{SERVER_ROOT}\\specs.pdf"),
        M.ActivityItem("https://intranet/p12513", kind="url"),
    ], pinned_at=M.now_iso(), open_count=9)
    resolver = PathResolver({}, drive_map={"Z:": "\\\\nas01\\Project"})
    pub = hubs["vikram"].publish_activity(act, resolver.portable, "Lot 7", ["yokesh"], [proj])
    assert act.origin.published_id == pub.published_id and pub.revision == 1
    paths = [i.path for i in pub.activity.items]
    assert paths == ["\\\\nas01\\Project\\P12513\\ISO\\Rev C", "{SERVER_ROOT}\\specs.pdf", "https://intranet/p12513"]
    assert pub.activity.pinned_at is None and pub.activity.open_count == 0
    # anyone may republish: the revision counts up and the record shows who
    again = hubs["priya"].publish_activity(M.Activity.from_dict(act.to_dict()), resolver.portable)
    assert again.revision == 2 and again.author == "priya"
    listed = hubs["yokesh"].published_activities()
    assert len(listed) == 1 and listed[0].revision == 2
    assert listed[0].projects == [{"id": proj.id, "title": proj.title, "job_number": "P12513"}]
    # a 3.2 reader skips activity files instead of failing
    assert hubs["yokesh"].published() == []
    assert hubs["yokesh"].inbox() == []                      # 3.2 inbox ignores the activity entry
    entries = hubs["yokesh"].inbox_entries()
    assert [e["kind"] for e in entries] == ["activity"] and entries[0]["activity"]["name"] == "Lot 7 check"
    assert hubs["vikram"].published_for()[pub.published_id] == []   # priya's republish had no "for"


def test_send_activity_and_mentions(hub_root):
    hubs = office(hub_root)
    act = M.Activity("Checking", items=[M.ActivityItem("C:\\x.pdf")])
    assert hubs["vikram"].send_activity(["priya", "yokesh"], act, "please look") == 2
    assert hubs["priya"].inbox_entries()[0]["message"] == "please look"
    n = hubs["priya"].send_mention(["vikram", "priya", "../x"], "@vikram see this", "projectopener://task/abc")
    assert n == 1                                            # never to myself, never an unsafe name
    m = hubs["vikram"].mentions()
    assert m[0]["kind"] == "mention" and m[0]["from"] == "priya" and m[0]["link"] == "projectopener://task/abc"
    assert hubs["vikram"].dismiss_entry(m[0]["id"]) and hubs["vikram"].mentions() == []
    assert hubs["vikram"].dismiss_entry("../../hub") is False


def test_announcement_mentions(hub_root):
    hubs = office(hub_root)
    GroupBook(hub_root).save(M.Group("checkers", ["priya", "yokesh"]))
    a = hubs["vikram"].announce("Server move", "@checkers nas01 is down at 6 pm", "warning")
    raw = json.loads((hub_root / "announcements.json").read_text(encoding="utf-8"))
    assert raw["items"][0]["mentions"] == ["checkers"] and raw["items"][0]["id"] == a.id
    assert hubs["priya"].mentions()[0]["title"] == "Server move"
    assert hubs["rahul"].mentions() == []
    assert [x.title for x in hubs["rahul"].announcements()] == ["Server move"]   # 3.2 reader unchanged
    hubs["vikram"].remove_announcement(a.id)
    assert hubs["rahul"].announcements() == []


def test_heartbeat_v4_fields_and_cliq_ids(hub_root):
    hubs = office(hub_root)
    p = hubs["priya"]
    p.email, p.cliq_id, p.cliq_linked, p.current_activity = "priya@dex.com", "6000123", True, "Lot 7 check"
    p.heartbeat()
    y = hubs["yokesh"]
    y.cliq_id, y.cliq_linked = "6000999", False                    # has an id but opted out
    y.heartbeat()
    rec = hubs["vikram"].user_records()["priya"]
    assert rec["email"] == "priya@dex.com" and rec["cliq_linked"] is True and rec["current_activity"] == "Lot 7 check"
    assert hubs["vikram"].cliq_ids_for(["priya", "yokesh", "rahul"]) == {"priya": "6000123"}
    assert hubs["vikram"].display_name_for("priya") == "Priya"


def test_shared_profiles(hub_root):
    hubs = office(hub_root)
    prof = M.LaunchProfile("Navis P12513", app="navisworks", exe="C:\\Navis\\Roamer.exe", args='"{ITEM}"')
    pid = hubs["vikram"].publish_profile(prof)
    assert prof.published_id == pid
    got = hubs["priya"].shared_profiles()
    assert [p.name for p in got] == ["Navis P12513"] and got[0].published_id == pid
