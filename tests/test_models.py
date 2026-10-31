from project_opener.core import models as M


def test_guess_kind():
    assert M.guess_kind("https://example.com") == "url"
    assert M.guess_kind("mailto:a@b.c") == "url"
    assert M.guess_kind(r"C:\tools\run.exe") == "app"
    assert M.guess_kind(r"Z:\Project\P12513\iso.pdf") == "file"
    assert M.guess_kind(r"Z:\Project\P12513") == "folder"
    assert M.guess_kind("\\\\nas01\\Project\\P12513\\") == "folder"
    assert M.guess_kind("cmd: dir") == "command"


def test_project_roundtrip():
    p = M.Project(name="ANTEO", tags=["iso", "fst"], items=[M.Item(path=r"Z:\x\a.pdf", kind="file")])
    p.launch_sets.append(M.LaunchSet(name="Morning", item_ids=[p.items[0].id]))
    d = p.to_dict()
    q = M.Project.from_dict(d)
    assert q.name == "ANTEO" and q.tags == ["iso", "fst"]
    assert q.items[0].path == r"Z:\x\a.pdf"
    assert q.items_for_set(q.launch_sets[0])[0].id == p.items[0].id


def test_clone_gets_fresh_ids_and_remaps_sets():
    p = M.Project(name="A", items=[M.Item(path="a.pdf"), M.Item(path="b.pdf")])
    p.launch_sets.append(M.LaunchSet(name="s", item_ids=[p.items[1].id]))
    c = p.clone()
    assert c.id != p.id
    assert c.name == "A (copy)"
    assert {i.id for i in c.items}.isdisjoint({i.id for i in p.items})
    assert c.launch_sets[0].item_ids == [c.items[1].id]


def test_from_dict_tolerates_garbage():
    p = M.Project.from_dict({"name": "", "color": "nonsense", "items": [1, {"path": "x.txt", "selected": False}, {}],
                             "launch_sets": ["bad"], "open_count": "7"})
    assert p.name == "Untitled"
    assert p.color == M.DEFAULT_COLOR
    assert len(p.items) == 2 and p.items[0].enabled is False
    assert p.open_count == 7


def test_v1_migration():
    v1 = {"files": [{"path": r"C:\a.pdf", "selected": True}, r"C:\b"], "notes": "hello",
          "color": "#e0e0e0", "last_opened": 1700000000.0, "pinned": 1700000001.0}
    p = M.project_from_v1("Old", v1)
    assert p.name == "Old" and p.notes == "hello"
    assert p.pinned and p.last_opened
    assert p.color == M.DEFAULT_COLOR
    assert [i.kind for i in p.items] == ["file", "folder"]


def test_v2_migration_builds_launch_sets():
    v2 = {"name": "ANTEO", "description": "d", "activities": [
        {"name": "Isometric checking", "items": [{"type": "file", "path": "C:/x.pdf"}, {"type": "exe", "path": "notepad.exe", "args": "a.txt"}]},
        {"name": "Handover", "items": []}]}
    p = M.project_from_v2("ANTEO", v2, author="vikram")
    assert len(p.items) == 2 and p.items[1].kind == "app" and p.items[1].args == "a.txt"
    assert [s.name for s in p.launch_sets] == ["Isometric checking", "Handover"]
    assert p.items_for_set(p.launch_sets[0])[0].group == "Isometric checking"


def test_dedupe_name():
    assert M.dedupe_name("A", ["a", "A (2)"]) == "A (3)"
    assert M.dedupe_name("B", ["A"]) == "B"
