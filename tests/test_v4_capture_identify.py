"""Identifier, identity cache, ignore rules (fake sources; no real windows)."""
from __future__ import annotations

from project_opener.capture.identify import Identifier, IdentityCache, entry_key, rule_matches
from project_opener.capture.win32 import WindowInfo
from project_opener.core import models as M


def win(hwnd, title, cls="X", process="app.exe", pid=100, rect=(0, 0, 100, 100)):
    return WindowInfo(hwnd=hwnd, title=title, window_class=cls, pid=pid, process=process, exe=f"C:\\x\\{process}",
                      placement=M.WindowPlacement(1, list(rect), list(rect), "\\\\.\\DISPLAY1", [0, 0, 1920, 1080]))


class FakeSource:
    def __init__(self, name, answers):
        self.name = name
        self.answers = answers         # hwnd -> (status, path, by)
        self.calls: list[list[int]] = []
        self.retry: set[int] = set()

    def identify(self, windows, ctx):
        self.calls.append([w.hwnd for w in windows])
        out = {}
        for w in windows:
            if w.hwnd in self.answers:
                status, path, by = self.answers[w.hwnd]
                out[w.hwnd] = M.SnapshotEntry(key="", status=status, path=path, kind="file" if path else "",
                                              identified_by=by, doc_name="doc" if status != "identified" else "")
        return out


def make(sources, **kw):
    return Identifier(sources=sources, recent_fn=lambda: {}, **kw)


def test_entry_key_forms():
    assert entry_key("identified", r"U:\Lot 7\A.PDF\\") == r"path:u:\lot 7\a.pdf"
    assert entry_key("identified", "https://x.com/A") == "url:https://x.com/A"
    assert entry_key("unidentified", "", "ACAD.EXE", "Drawing1") == "win:acad.exe|Drawing1"


def test_sources_run_in_order_and_identified_answers_are_final():
    first = FakeSource("a", {1: ("identified", r"U:\one", "shell"), 2: ("unidentified", "", "")})
    second = FakeSource("b", {1: ("identified", r"U:\WRONG", "x"), 2: ("identified", r"U:\two", "title+items")})
    idf = make([first, second])
    out = idf.identify([win(1, "one"), win(2, "two"), win(3, "three")], [])
    assert [e.path for e in out] == [r"U:\one", r"U:\two", ""]
    assert second.calls == [[2, 3]]                          # 1 was settled by the first source
    assert out[2].status == "unidentified" and out[2].key == "win:app.exe|three"
    assert out[0].key == r"path:u:\one" and out[0].hwnd == 1 and out[0].app == "App"


def test_cache_skips_known_windows_and_title_change_reidentifies():
    src = FakeSource("a", {1: ("identified", r"U:\one", "shell")})
    idf = make([src])
    idf.identify([win(1, "one")], [])
    idf.identify([win(1, "one", rect=(5, 5, 50, 50))], [])
    assert src.calls == [[1]]
    out = idf.identify([win(1, "one", rect=(5, 5, 50, 50))], [])
    assert out[0].placement.normal_rect == [5, 5, 50, 50]     # fresh placement from the cached identity
    assert idf.last_queried == 0
    idf.identify([win(1, "one - renamed")], [])
    assert src.calls == [[1], [1]]


def test_full_refresh_reasks_everything_except_browsers():
    src = FakeSource("a", {1: ("identified", r"U:\one", "shell"), 2: ("identified", "https://x.com", "uia")})
    idf = make([src])
    ws = [win(1, "one"), win(2, "x - Google Chrome", process="chrome.exe")]
    idf.identify(ws, [])
    idf.identify(ws, [], full=True)
    assert src.calls == [[1, 2], [1]]


def test_busy_answers_are_not_cached():
    src = FakeSource("a", {})
    src.retry = {1}
    idf = make([src])
    idf.identify([win(1, "x - Excel")], [])
    idf.identify([win(1, "x - Excel")], [])
    assert src.calls == [[1], [1]]


def test_failing_source_does_not_stop_the_others():
    class Boom:
        def identify(self, windows, ctx):
            raise RuntimeError("COM died")
    good = FakeSource("b", {1: ("identified", r"U:\one", "title+items")})
    out = make([Boom(), good]).identify([win(1, "one")], [])
    assert out[0].identified


def test_ignore_rules_and_prune():
    src = FakeSource("a", {})
    idf = make([src], ignore_rules=[{"process": "claude.exe"}, {"process": "app.exe", "title": "secret*"}])
    out = idf.identify([win(1, "Claude", process="Claude.exe"), win(2, "secret plans"), win(3, "public")], [])
    assert [e.hwnd for e in out] == [3]
    assert len(idf.cache) == 1
    idf.identify([], [])
    assert len(idf.cache) == 0


def test_identify_one_ignores_rules_and_uses_cache():
    src = FakeSource("a", {1: ("identified", r"U:\one", "shell")})
    windows = {1: win(1, "Claude", process="claude.exe")}
    idf = make([src], ignore_rules=[{"process": "claude.exe"}], window_info_fn=windows.get)
    e = idf.identify_one(1, [])
    assert e is not None and e.path == r"U:\one"
    assert idf.identify_one(1, []).path == r"U:\one"
    assert src.calls == [[1]]
    assert idf.identify_one(2, []) is None


def test_items_changed_invalidates_title_matches_only():
    src = FakeSource("a", {1: ("identified", r"U:\one", "shell"), 2: ("identified", r"U:\two.pdf", "title+items"),
                           3: ("unidentified", "", "")})
    idf = make([src])
    ws = [win(1, "one"), win(2, "two"), win(3, "three")]
    idf.identify(ws, [])
    idf.items_changed()
    idf.identify(ws, [])
    assert src.calls == [[1, 2, 3], [2, 3]]


def test_rule_matches():
    assert rule_matches({"process": "TEAMS.exe"}, "teams.exe", "anything")
    assert not rule_matches({"process": "teams.exe"}, "slack.exe", "x")
    assert rule_matches({"title": "*Zoho Mail*"}, "x.exe", "Inbox - Zoho Mail (v)")
    assert not rule_matches({}, "x.exe", "y")


def test_identity_cache_invalidate():
    c = IdentityCache()
    w = win(1, "a")
    c.put(w, M.SnapshotEntry(key="k", status="unidentified"))
    assert c.invalidate(lambda e: e.status == "unidentified") == 1
    assert c.get(w) is None
