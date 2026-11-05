"""Pure snapshot arithmetic and the add-a-window / start-from-open helpers."""
from __future__ import annotations

from project_opener.capture import diff
from project_opener.capture import windows as W
from project_opener.capture.identify import entry_key, rule_matches
from project_opener.core import models as M


def ent(path="", status="identified", kind="file", title="t", process="app.exe", show=1, rect=(0, 0, 10, 10),
        by="shell", doc="", hwnd=1, exe=""):
    e = M.SnapshotEntry(key=entry_key(status, path if status == "identified" else "", process, title), status=status,
                        kind=kind if status == "identified" else "", path=path if status == "identified" else "",
                        title=title, process=process, identified_by=by, doc_name=doc, hwnd=hwnd, exe=exe,
                        app=process.split(".")[0].title(),
                        placement=M.WindowPlacement(show, list(rect), list(rect), "D1", [0, 0, 1920, 1080]))
    return e


def snap(*entries):
    return M.Snapshot(activity_id="a1", entries=list(entries))


# ------------------------------------------------------------------ match_items
def test_match_items_case_trailing_portable_resolve_and_urls():
    items = [M.Item(path=r"U:\Lot 7\List.xlsx", id="i1"), M.Item(path=r"{JOB}\isos", kind="folder", id="i2"),
             M.Item(path="https://github.com/x/y/", kind="url", id="i3"), M.Item(path=r"Z:\share\a.pdf", id="i4")]
    s = snap(ent(r"u:\lot 7\list.xlsx\\"), ent(r"\\nas\job\isos", kind="folder"), ent("https://www.github.com/x/y#top",
             kind="url"), ent(r"\\srv\share\a.pdf"), ent(r"U:\new.pdf"), ent(status="unidentified", title="Calc"))

    def resolve(p):
        return p.replace("{JOB}", r"\\nas\job")

    def portable(p):
        return p.replace("Z:", r"\\srv")
    diff.match_items(s, items, portable=portable, resolve=resolve)
    assert [e.item_id for e in s.entries] == ["i1", "i2", "i3", "i4", "", ""]
    assert [e.is_new for e in s.entries] == [False, False, False, False, True, False]


def test_match_items_clears_stale_links():
    s = snap(ent(r"U:\a.pdf"))
    s.entries[0].item_id = "gone"
    diff.match_items(s, [])
    assert s.entries[0].item_id == ""


# ------------------------------------------------------------------ changed
def test_changed_ignores_zorder_hwnds_and_time_but_sees_placement_and_status():
    a = snap(ent(r"U:\a.pdf", hwnd=1), ent(r"U:\b.pdf", hwnd=2))
    b = snap(ent(r"U:\b.pdf", hwnd=7), ent(r"U:\a.pdf", hwnd=8))
    b.taken_at = "2030-01-01T00:00:00+00:00"
    assert diff.changed(None, a)
    assert not diff.changed(a, b)
    c = snap(ent(r"U:\a.pdf"), ent(r"U:\b.pdf", rect=(5, 5, 50, 50)))
    assert diff.changed(a, c)
    d = snap(ent(r"U:\a.pdf"), ent(r"U:\b.pdf", show=3))
    assert diff.changed(a, d)
    e = snap(ent(r"U:\a.pdf"))
    assert diff.changed(a, e)
    f = snap(ent(r"U:\a.pdf"), ent(r"U:\b.pdf"), ent(r"U:\b.pdf"))     # a second window on the same file
    assert diff.changed(a, f)


# ------------------------------------------------------------------ new_since
def test_new_since_checkpoint():
    cp = snap(ent(r"U:\a.pdf"), ent(status="unidentified", title="x"))
    now = snap(ent(r"U:\a.pdf"), ent(r"U:\b.pdf"), ent(r"U:\b.pdf", hwnd=3), ent(status="unidentified", title="y"))
    assert [e.path for e in diff.new_since(cp, now)] == [r"U:\b.pdf"]
    assert len(diff.new_since(None, now)) == 2


# ------------------------------------------------------------------ order_for_restore
def test_order_for_restore_items_first_in_launch_order_then_back_to_front():
    items = [M.Item(path=r"U:\b.pdf", id="ib"), M.Item(path=r"U:\a.pdf", id="ia")]
    s = snap(ent(r"U:\front.pdf"), ent(r"U:\a.pdf"), ent(r"U:\middle.pdf"), ent(r"U:\b.pdf"), ent(r"U:\back.pdf"),
             ent(status="unsaved", title="Book1 - Excel"), ent(r"U:\a.pdf", hwnd=9))
    diff.match_items(s, items)
    order = [e.path for e in diff.order_for_restore(s, items)]
    assert order == [r"U:\b.pdf", r"U:\a.pdf", r"U:\back.pdf", r"U:\middle.pdf", r"U:\front.pdf"]
    assert [e.title for e in diff.unrestorable(s)] == ["Book1 - Excel"]


def test_same_target():
    assert diff.same_target("https://WWW.x.com/a/", "http://x.com/a")
    assert not diff.same_target("https://x.com/a", "https://x.com/b")
    assert diff.same_target(r"U:\A\\", r"u:\a")
    assert not diff.same_target("", "")


# ------------------------------------------------------------------ windows helpers
def test_display_status_and_worst_first():
    entries = [ent(r"U:.pdf"), ent(status="unidentified", title="Calculator"),
               ent(status="unidentified", title="GA.dwg - AutoCAD", doc="GA.dwg"),
               ent(status="ambiguous", title="iso - PDF", doc="iso.pdf"), ent(status="unsaved", title="Book1")]
    st = {e.key: W.display_status(e) for e in entries}
    assert list(st.values()) == ["identified", "window", "unidentified", "ambiguous", "unsaved"]
    assert W.display_status(entries[0], offline=True) == "offline"
    assert [st[e.key] for e in W.worst_first(entries, st)] == ["ambiguous", "unidentified", "unsaved", "window",
                                                               "identified"]
    assert W.needs_you("unidentified") and W.needs_you("ambiguous") and not W.needs_you("window")


def test_default_ticked():
    assert W.default_ticked(ent(r"U:\a.pdf"))
    assert W.default_ticked(ent("https://x.com", kind="url"))
    assert not W.default_ticked(ent(r"U:\a.pdf", process="OUTLOOK.EXE"))
    assert not W.default_ticked(ent(status="unidentified", title="Calc"))
    assert not W.default_ticked(ent(status="unsaved", title="Book1"))


def test_add_labels_say_exactly_what_will_be_added():
    xl = ent(r"U:\Lot 7\Line list.xlsx", process="EXCEL.EXE")
    assert W.add_label(xl) == "Line list.xlsx · Excel\n" + r"U:\Lot 7\Line list.xlsx"
    url = ent("https://x.com/a", kind="url", process="chrome.exe", doc="Issues")
    assert W.add_label(url) == "Issues · Chrome\nhttps://x.com/a (active tab only)"
    unsaved = ent(status="unsaved", title="Autodesk AutoCAD - [Drawing1.dwg]", process="acad.exe", doc="Drawing1.dwg")
    first, second = W.label_lines(unsaved)
    assert first == "Acad · Drawing1.dwg" and second.startswith("Unsaved: no file yet")
    amb = ent(status="ambiguous", title="iso - PDF", doc="iso.pdf")
    amb.candidates = ["a", "b"]
    assert "2 files have this name" in W.add_label(amb)
    assert W.add_label(ent(status="unidentified", title="Calculator", process="calc.exe")) == \
        "Calc · Calculator\nNot a file. You can add Calc itself as an application."
    assert W.add_message(ent(status="unidentified", title="GA.dwg - X", doc="GA.dwg")) == \
        "App · GA.dwg: No file path found. You will be asked for it once."


def test_items_from_entries_dedupes_and_keeps_order():
    es = [ent(r"U:\b.pdf"), ent(r"u:\B.pdf\\"), ent(r"U:\a", kind="folder"), ent(status="unidentified", title="x"),
          ent("https://x.com/a", kind="url", doc="Tab")]
    items = W.items_from_entries(es, "p1")
    assert [(i.path, i.kind) for i in items] == [(r"U:\b.pdf", "file"), (r"U:\a", "folder"),
                                                 ("https://x.com/a", "url")]
    assert items[2].label == "Tab" and all(i.project_id == "p1" for i in items)


def test_app_item_and_ignore_rule_round_trip():
    e = ent(status="unsaved", title="Drawing1 [x]*? - AutoCAD", process="ACAD.EXE", exe=r"C:\AutoCAD\acad.exe")
    item = W.app_item(e)
    assert item.kind == "app" and item.path == r"C:\AutoCAD\acad.exe"
    assert W.app_item(ent(status="unidentified", title="x")) is None
    rule = W.ignore_rule(e)
    assert rule["process"] == "acad.exe"
    assert rule_matches(rule, "acad.exe", e.title)
    assert not rule_matches(rule, "acad.exe", "Drawing1 x - AutoCAD")
