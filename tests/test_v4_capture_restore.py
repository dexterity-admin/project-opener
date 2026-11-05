"""Restore: placement maths, window matching, and the Restorer over a fake desktop."""
from __future__ import annotations

from project_opener.capture.identify import entry_key
from project_opener.capture.restore import Restorer, match_window, plan_placement
from project_opener.capture.win32 import WindowInfo, placement_held
from project_opener.core import models as M

D1 = M.Monitor("\\\\.\\DISPLAY1", [1920, -4, 3840, 1076], [1920, -4, 3840, 1036], 96, False)
D2 = M.Monitor("\\\\.\\DISPLAY2", [0, 0, 1920, 1080], [0, 0, 1920, 1040], 96, True)


def pl(rect, show=1, mon=D1):
    return M.WindowPlacement(show, list(rect), list(rect), mon.device, list(mon.rect))


# ------------------------------------------------------------------ placement maths
def test_plan_same_monitor_is_exact():
    saved = pl((1950, 20, 2850, 520), 3)
    plan = plan_placement(saved, [D2, D1])
    assert plan.normal_rect == [1950, 20, 2850, 520] and plan.show_cmd == 3 and plan.monitor == D1.device


def test_plan_moved_monitor_shifts_with_it():
    moved = M.Monitor(D1.device, [1920, 100, 3840, 1180], [1920, 100, 3840, 1140], 96, False)
    plan = plan_placement(pl((1950, 20, 2850, 520)), [D2, moved])
    assert plan.normal_rect == [1950, 124, 2850, 624]


def test_plan_gone_monitor_goes_to_primary_and_fits():
    plan = plan_placement(pl((1950, 20, 2850, 520)), [D2])
    assert plan.monitor == D2.device and plan.normal_rect == [30, 24, 930, 524]
    big = plan_placement(pl((1920, -4, 4000, 1300)), [D2])
    assert big.normal_rect == [0, 0, 1920, 1040]


def test_plan_nothing_saved():
    assert plan_placement(None, [D2]) is None
    assert plan_placement(pl((0, 0, 0, 0)), [D2]) is None


def test_placement_held_tolerates_rounding_but_not_state():
    want = pl((10, 10, 110, 110))
    assert placement_held(want, pl((11, 10, 110, 109)))
    assert not placement_held(want, pl((10, 10, 110, 110), 3))
    assert not placement_held(pl((10, 10, 110, 110), 3), pl((10, 10, 110, 110), 1))
    assert not placement_held(want, pl((50, 10, 150, 110)))


# ------------------------------------------------------------------ matching
def ent(path, kind="file", title="t", process="app.exe", by="shell", doc="", rect=(1950, 20, 2850, 520), show=1,
        exe=""):
    return M.SnapshotEntry(key=entry_key("identified", path), status="identified", kind=kind, path=path, title=title,
                           process=process, identified_by=by, doc_name=doc, exe=exe, placement=pl(rect, show))


def test_match_by_identity_first():
    a, b = ent(r"U:\a.xlsx", process="EXCEL.EXE"), ent(r"U:\b.xlsx", process="EXCEL.EXE")
    found = ent(r"u:\B.xlsx")
    assert match_window(found, "Excel", "EXCEL.EXE", [a, b]) == (b, "identity")


def test_title_fallback_only_for_title_identified_entries():
    pdf = ent(r"U:\iso-001.pdf", title="iso-001 - PDF-XChange Editor", process="PDFXEdit.exe", by="title+items",
              doc="iso-001.pdf")
    xl = ent(r"U:\a.xlsx", title="a.xlsx - Excel", process="EXCEL.EXE", by="office-com")
    unknown = M.SnapshotEntry(key="w", status="unidentified", title="iso-001 - PDF-XChange Editor")
    assert match_window(unknown, "iso-001 - PDF-XChange Editor", "pdfxedit.exe", [pdf, xl]) == (pdf, "title")
    # Excel is matched by identity only: a bare "Excel" title never claims a pending workbook
    assert match_window(None, "a.xlsx - Excel", "EXCEL.EXE", [xl]) == (None, "")
    assert match_window(None, "something else entirely", "PDFXEdit.exe", [pdf]) == (None, "")


# ------------------------------------------------------------------ the Restorer
class FakeDesktop:
    """Windows appear a few polls after their launch; identification is by a lookup table."""

    def __init__(self, existing: list[WindowInfo], identities: dict[int, M.SnapshotEntry]):
        self.t = 0.0
        self.desk = {w.hwnd: w for w in existing}
        self.ident = dict(identities)
        self.scheduled: list[tuple[float, WindowInfo]] = []
        self.launch: dict[str, tuple[int, str, str]] = {}      # path -> (hwnd, title, process) to appear
        self.opened: list[tuple[str, str]] = []
        self.placed: dict[int, M.WindowPlacement] = {}
        self.refuse_once: set[int] = set()
        self.next_hwnd = 1000

    def _appear(self, path, how):
        self.opened.append((how, path))
        hwnd, title, proc = self.launch.get(path, (0, "", ""))
        if hwnd:
            self.scheduled.append((self.t + 1.2, WindowInfo(hwnd, title, "C", 5, proc)))

    def existing_hwnds(self):
        return set(self.desk)

    def windows(self):
        return list(self.desk.values())

    def identify(self, windows, item_paths, full):
        out = []
        for w in windows:
            e = self.ident.get(w.hwnd)
            out.append(M.SnapshotEntry(key=e.key, status=e.status, path=e.path, kind=e.kind) if e else
                       M.SnapshotEntry(key=f"win:{w.process}|{w.title}", title=w.title))
        return out

    def monitors(self):
        return [D2, D1]

    def apply_placement(self, hwnd, plan):
        assert hwnd not in self.existing_before, "touched a window the user already had"
        if hwnd in self.refuse_once:
            self.refuse_once.discard(hwnd)
            return False
        self.placed[hwnd] = plan
        return True

    def open_office(self, path):
        self._appear(path, "com")
        return True

    def open_folder(self, path):
        self._appear(path, "explorer")

    def open_url(self, url, exe):
        self._appear(url, f"url:{exe}")

    def exists(self, path):
        return not path.endswith("missing")

    def sleep(self, s):
        self.t += s
        for at, w in list(self.scheduled):
            if at <= self.t:
                self.desk[w.hwnd] = w
                self.scheduled.remove((at, w))

    def now(self):
        return self.t


def test_restore_opens_in_order_matches_new_windows_and_places_them():
    folder = ent(r"U:\Lot 7", kind="folder", process="explorer.exe", rect=(300, 100, 1500, 900))
    xl = ent(r"U:\Lot 7\list.xlsx", process="EXCEL.EXE", by="office-com", show=3)
    url = ent("https://github.com/x", kind="url", process="chrome.exe", by="uia", exe=r"C:\Chrome\chrome.exe")
    pdf = ent(r"U:\Lot 7\iso.pdf", title="iso - PDF-XChange Editor", process="PDFXEdit.exe", by="title+items",
              doc="iso.pdf")
    open_already = ent(r"U:\notes.docx", process="WINWORD.EXE", by="office-com")
    missing = ent(r"U:\gone\missing", kind="folder", process="explorer.exe")
    unsaved = M.SnapshotEntry(key="win:excel.exe|Book1", status="unsaved", title="Book1 - Excel")
    snapshot = M.Snapshot("a1", entries=[folder, xl, url, pdf, open_already, missing, unsaved])
    user_word = WindowInfo(50, "notes.docx - Word", "OpusApp", 9, "WINWORD.EXE")
    user_chrome = WindowInfo(51, "github - Google Chrome", "C", 9, "chrome.exe")
    desk = FakeDesktop([user_word, user_chrome], {50: open_already, 101: folder, 102: xl, 103: url})
    desk.existing_before = {50, 51}
    desk.launch = {folder.path: (101, "Lot 7", "explorer.exe"), xl.path: (102, "Excel", "EXCEL.EXE"),
                   url.path: (103, "x - Google Chrome", "chrome.exe"),
                   pdf.path: (104, "iso - PDF-XChange Editor", "PDFXEdit.exe")}
    desk.refuse_once = {101}
    opened_items = []

    def open_item(item):
        opened_items.append(item.path)
        desk._appear(item.path, "assoc")
        return type("R", (), {"status": "opened", "message": ""})()
    progress = []
    r = Restorer(open_item, settle_s=25, platform=desk, gap_s=0.3, poll_s=0.5)
    report = r.restore(snapshot, [], progress=lambda d, t, lbl: progress.append((d, t)))
    res = {x.label: x for x in report.results}
    # opening: Office through COM, folder through explorer, URL through the recorded browser, PDF by association
    assert ("com", xl.path) in desk.opened and ("explorer", folder.path) in desk.opened
    assert ("url:" + url.exe, url.path) in desk.opened and opened_items == [pdf.path]
    assert res["notes.docx"].message.startswith("already open") and not res["notes.docx"].placed
    assert not res["missing"].opened and res["missing"].message == "folder not found"
    assert res["list.xlsx"].placed and res["list.xlsx"].matched_by == "identity"
    assert desk.placed[102].show_cmd == 3
    assert res["Lot 7"].placed                          # refused once, held on the retry
    assert res["iso.pdf"].matched_by == "title" and res["iso.pdf"].placed
    assert 50 not in desk.placed and 51 not in desk.placed
    assert [e.title for e in report.unrestorable] == ["Book1 - Excel"]
    assert progress[-1] == (6, 6) and report.seconds < 25
    d = report.to_dict()
    assert d["failed"] == ["missing"] and d["placed"] == 4 and d["unrestorable"] == ["Book1 - Excel"]


def test_restore_reports_windows_that_never_came():
    xl = ent(r"U:\slow.xlsx", process="EXCEL.EXE", by="office-com")
    desk = FakeDesktop([], {})
    desk.existing_before = set()
    report = Restorer(lambda i: None, settle_s=5, platform=desk).restore(M.Snapshot("a", entries=[xl]), [])
    assert report.results[0].opened and not report.results[0].placed
    assert "no window found within 5 s" in report.results[0].message
    assert 4.9 <= report.seconds <= 6.5


def test_restore_follows_item_launch_order():
    a, b = ent(r"U:\a.pdf", by="title+items"), ent(r"U:\b.pdf", by="title+items")
    a.item_id, b.item_id = "ia", "ib"
    desk = FakeDesktop([], {})
    desk.existing_before = set()
    order = []

    def open_item(item):
        order.append(item.path)
        return type("R", (), {"status": "opened"})()
    items = [M.Item(path=r"U:\b.pdf", id="ib"), M.Item(path=r"U:\a.pdf", id="ia")]
    Restorer(open_item, settle_s=1, platform=desk).restore(M.Snapshot("x", entries=[a, b]), items)
    assert order == [r"U:\b.pdf", r"U:\a.pdf"]


def test_settle_window_starts_after_a_slow_launch():
    """A cold Office start longer than the settle window must not leave the restore no time to match."""
    xl = ent(r"U:\a.xlsx", process="EXCEL.EXE", by="office-com")
    pdf = ent(r"U:\b.pdf", title="b - PDF-XChange Editor", process="PDFXEdit.exe", by="title+items", doc="b.pdf")
    desk = FakeDesktop([], {201: xl})
    desk.existing_before = set()
    desk.launch = {xl.path: (201, "a.xlsx - Excel", "EXCEL.EXE"), pdf.path: (202, "b - PDF-XChange Editor",
                                                                           "PDFXEdit.exe")}
    slow_office = desk.open_office

    def open_office(path):
        desk.t += 30.0                          # Excel took 30 s to answer COM
        return slow_office(path)
    desk.open_office = open_office

    def open_item(item):
        desk._appear(item.path, "assoc")
        return type("R", (), {"status": "opened"})()
    report = Restorer(open_item, settle_s=25, platform=desk).restore(M.Snapshot("a", entries=[xl, pdf]), [])
    assert all(r.placed for r in report.results), [r.message for r in report.results]
    assert next(r for r in report.results if r.label == "a.xlsx").open_s == 30.0
