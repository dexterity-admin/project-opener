"""Identification sources with fake backends (no real windows, no COM)."""
from __future__ import annotations

import os

from project_opener.capture.sources import SourceContext
from project_opener.capture.sources.browser import BrowserSource, normalise_url, tab_title
from project_opener.capture.sources.explorer import ExplorerSource, path_from_location_url
from project_opener.capture.sources.office import OfficeBusy, OfficeDoc, OfficeSource, app_for_path
from project_opener.capture.sources.titles import (
    RecentIndex,
    TitleSource,
    match_name,
    parse_title,
    path_in_title,
)
from project_opener.capture.win32 import WindowInfo


def win(hwnd: int, title: str, cls: str = "X", process: str = "app.exe", pid: int = 100) -> WindowInfo:
    return WindowInfo(hwnd=hwnd, title=title, window_class=cls, pid=pid, process=process, exe=f"C:\\x\\{process}")


# ------------------------------------------------------------------ explorer
def test_explorer_identifies_folder_windows_only_and_asks_only_for_them():
    asked = []

    def fake(wanted):
        asked.append(wanted)
        return {1: r"U:\Lot 7 isos", 2: r"\\nas01\Project\P12513", 99: r"C:\other"}

    src = ExplorerSource(fake)
    ws = [win(1, "Lot 7 isos", "CabinetWClass", "explorer.exe"), win(2, "P12513", "CabinetWClass", "explorer.exe"),
          win(3, "Line list.xlsx - Excel", "XLMAIN", "EXCEL.EXE")]
    out = src.identify(ws, SourceContext())
    assert set(out) == {1, 2}
    assert asked == [{1, 2}]
    assert out[1].status == "identified" and out[1].kind == "folder" and out[1].path == r"U:\Lot 7 isos"
    assert out[1].identified_by == "shell" and out[1].app == "Explorer"
    assert out[2].path == r"\\nas01\Project\P12513"


def test_explorer_without_folder_windows_makes_no_com_call():
    src = ExplorerSource(lambda wanted: (_ for _ in ()).throw(AssertionError("called")))
    assert src.identify([win(3, "x", "Notepad")], SourceContext()) == {}


def test_explorer_window_not_yet_in_shellwindows_stays_unanswered():
    src = ExplorerSource(lambda wanted: {})
    assert src.identify([win(1, "Lot 7", "CabinetWClass")], SourceContext()) == {}


def test_explorer_shell_failure_is_not_fatal():
    def boom(wanted):
        raise OSError("RPC server unavailable")
    assert ExplorerSource(boom).identify([win(1, "Lot 7", "CabinetWClass")], SourceContext()) == {}


def test_location_url_paths():
    assert path_from_location_url("file:///U:/Vikram/a%20b") == r"U:\Vikram\a b"
    assert path_from_location_url("file://192.168.0.200/free%20exchange%20-%20updated/Vikram") == \
        r"\\192.168.0.200\free exchange - updated\Vikram"
    assert path_from_location_url("https://example.com") == ""
    assert path_from_location_url("") == ""


# ------------------------------------------------------------------ office
def test_office_reads_each_window_and_reports_unsaved_and_protected():
    docs = {
        1: OfficeDoc(r"U:\Lot 7\Line list.xlsx", True, True),
        2: OfficeDoc("Book1", False, False),
        3: OfficeDoc(r"U:\Lot 7\notes.docx", True, True, protected=True),
    }
    src = OfficeSource(lambda w: docs.get(w.hwnd))
    ws = [win(1, "Line list.xlsx - Excel", "XLMAIN", "EXCEL.EXE"), win(2, "Book1 - Excel", "XLMAIN", "EXCEL.EXE"),
          win(3, "notes.docx [Protected View] - Word", "OpusApp", "WINWORD.EXE"), win(4, "Untitled - Notepad")]
    out = src.identify(ws, SourceContext())
    assert set(out) == {1, 2, 3}
    assert out[1].status == "identified" and out[1].path == r"U:\Lot 7\Line list.xlsx"
    assert out[1].identified_by == "office-com" and out[1].app == "Excel" and out[1].kind == "file"
    assert out[2].status == "unsaved" and out[2].path == "" and "cannot be restored" in out[2].note
    assert out[3].app == "Word" and out[3].note == "Protected View"


def test_office_busy_instance_is_retried_not_answered():
    def busy(w):
        raise OfficeBusy("call rejected")
    src = OfficeSource(busy)
    assert src.identify([win(1, "x - Excel", "XLMAIN", "EXCEL.EXE")], SourceContext()) == {}
    assert src.retry == {1}


def test_office_refusal_leaves_window_for_later_sources():
    src = OfficeSource(lambda w: None)
    assert src.identify([win(1, "x - Excel", "XLMAIN", "EXCEL.EXE")], SourceContext()) == {}
    assert src.retry == set()


def test_app_for_path():
    assert app_for_path(r"U:\a.XLSX") == "excel"
    assert app_for_path(r"U:\a.docx") == "word"
    assert app_for_path(r"U:\a.pdf") == ""


# ------------------------------------------------------------------ browser
def test_browser_reads_active_tab_url_and_restores_scheme():
    src = BrowserSource(lambda hwnd: ("Address and search bar", "github.com/dexterity-admin/project-opener"))
    out = src.identify([win(1, "project-opener - Google Chrome", "Chrome_WidgetWin_1", "chrome.exe")], SourceContext())
    e = out[1]
    assert e.status == "identified" and e.kind == "url"
    assert e.path == "https://github.com/dexterity-admin/project-opener"
    assert e.note == "active tab only" and e.identified_by == "uia" and e.app == "Chrome"
    assert e.doc_name == "project-opener"


def test_browser_switch_off_and_non_browsers_and_internal_pages():
    calls = []

    def read(hwnd):
        calls.append(hwnd)
        return ("Address and search bar", "chrome://newtab")
    src = BrowserSource(read)
    w_chrome = win(1, "New Tab - Google Chrome", "Chrome_WidgetWin_1", "chrome.exe")
    assert src.identify([w_chrome], SourceContext(want_browser_urls=False)) == {}
    assert calls == []
    assert src.identify([w_chrome, win(2, "x", "Notepad", "notepad.exe")], SourceContext()) == {}
    assert calls == [1]


def test_browser_without_address_bar_or_failing_uia():
    assert BrowserSource(lambda h: None).identify([win(1, "x", "C", "msedge.exe")], SourceContext()) == {}

    def boom(h):
        raise OSError("uia")
    assert BrowserSource(boom).identify([win(1, "x", "C", "msedge.exe")], SourceContext()) == {}


def test_tab_title_and_url_helpers():
    assert tab_title("Issues \u00b7 repo - Microsoft\u200b Edge") == "Issues \u00b7 repo"
    assert tab_title("Inbox - Brave") == "Inbox"
    assert normalise_url("https://x.com/a") == "https://x.com/a"
    assert normalise_url("x.com/a") == "https://x.com/a"


# ------------------------------------------------------------------ titles
def test_parse_title_patterns():
    assert parse_title("PDFXEdit.exe", "PO-spike iso P12513-001 - PDF-XChange Editor") == \
        ("PO-spike iso P12513-001.pdf", "PDF-XChange Editor")
    assert parse_title("soffice.bin", "notes.docx (read-only) \u2013 LibreOffice Writer") == ("notes.docx", "LibreOffice")
    assert parse_title("acad.exe", "Autodesk AutoCAD 2024 - [GA-101.dwg]") == ("GA-101.dwg", "AutoCAD")
    assert parse_title("EXCEL.EXE", "Line list.xlsx  [Protected View] - Excel") == ("Line list.xlsx", "Excel")
    assert parse_title("roamer.exe", "P12513 model.nwd - Autodesk Navisworks Manage 2022")[0] == "P12513 model.nwd"
    assert parse_title("unknown.exe", "anything") is None
    assert parse_title("PDFXEdit.exe", "PDF-XChange Editor") is None


def test_match_name_single_ambiguous_none():
    items = [r"U:\Lot 7\iso-001.pdf", r"U:\Lot 7\list.xlsx"]
    assert match_name("ISO-001.pdf", items, {}) == ("identified", [r"U:\Lot 7\iso-001.pdf"], "title+items")
    recent = {"iso-001.pdf": [r"U:\Lot 8\iso-001.pdf"]}
    status, cands, _by = match_name("iso-001.pdf", items, recent)
    assert status == "ambiguous" and len(cands) == 2          # same name, two lots: never guessed
    assert match_name("iso-002.pdf", items, {"iso-002.pdf": [r"D:\x\iso-002.pdf"]}) == \
        ("identified", [r"D:\x\iso-002.pdf"], "title+recent")
    assert match_name("iso-009.pdf", items, {})[0] == "unidentified"
    assert match_name("", items, {})[0] == "unidentified"


def test_match_name_tries_known_extensions_and_folds_spellings():
    assert match_name("list", [r"U:\Lot 7\list.xlsx"], {})[0] == "identified"
    # the same file, once as U: and once as UNC: one candidate with a canonicaliser, two without
    items = [r"U:\Lot 7\iso-001.pdf"]
    recent = {"iso-001.pdf": [r"\\nas01\share\Lot 7\iso-001.pdf"]}

    def canon(p):
        return p.replace("U:", r"\\nas01\share")
    assert match_name("iso-001.pdf", items, recent)[0] == "ambiguous"
    assert match_name("iso-001.pdf", items, recent, canon)[0] == "identified"


def test_title_source_states():
    src = TitleSource(exists=lambda p: p == r"D:\logs\huge.log")
    ctx = SourceContext(item_paths=[r"U:\Lot 7\iso-001.pdf"],
                        recent={"iso-002.pdf": [r"U:\a\iso-002.pdf", r"U:\b\iso-002.pdf"]})
    ws = [
        win(1, "iso-001 - PDF-XChange Editor", process="PDFXEdit.exe"),
        win(2, "iso-002 - PDF-XChange Editor", process="PDFXEdit.exe"),
        win(3, "Autodesk AutoCAD 2024 - [Drawing1.dwg]", process="acad.exe"),
        win(4, "GA-777.dwg - Autodesk AutoCAD 2024", process="acad.exe"),
        win(5, r"D:\logs\huge.log - Slate", process="slate.exe"),
        win(6, "Inbox - Google Chrome", process="chrome.exe"),
        win(7, "Calculator", process="calc.exe"),
    ]
    out = src.identify(ws, ctx)
    assert out[1].status == "identified" and out[1].path == r"U:\Lot 7\iso-001.pdf" and out[1].identified_by == "title+items"
    assert out[2].status == "ambiguous" and len(out[2].candidates) == 2
    assert out[3].status == "unsaved"
    assert out[4].status == "unidentified" and out[4].doc_name == "GA-777.dwg"
    assert out[5].status == "identified" and out[5].identified_by == "title-path" and out[5].path == r"D:\logs\huge.log"
    assert 6 not in out and 7 not in out


def test_recent_is_loaded_lazily_and_only_once():
    calls = []

    def load():
        calls.append(1)
        return {"x.pdf": [r"U:\x.pdf"]}
    ctx = SourceContext(recent_fn=load)
    TitleSource().identify([win(1, "Calculator", process="calc.exe")], ctx)
    assert calls == []
    TitleSource().identify([win(1, "x - PDF-XChange Editor", process="PDFXEdit.exe")], ctx)
    TitleSource().identify([win(2, "x - PDF-XChange Editor", process="PDFXEdit.exe")], ctx)
    assert calls == [1]


def test_path_in_title_trims_suffixes():
    exists = {r"D:\work\a b.txt", r"\\nas01\share\x"}.__contains__
    assert path_in_title(r"*D:\work\a b.txt - Notepad++ [Administrator]", exists) == r"D:\work\a b.txt"
    assert path_in_title(r"\\nas01\share\x - Total Commander", exists) == r"\\nas01\share\x"
    assert path_in_title("no path here", exists) == ""
    assert path_in_title(r"D:\missing.txt - Editor", exists) == ""


def test_recent_index_resolves_each_link_once_and_rereads_on_change(tmp_path):
    folder = tmp_path / "Recent"
    folder.mkdir()
    (folder / "a.pdf.lnk").write_bytes(b"x")
    (folder / "b.pdf.lnk").write_bytes(b"x")
    resolved: list[list[str]] = []

    def resolve(paths):
        resolved.append(sorted(os.path.basename(p) for p in paths))
        return {p: rf"U:\docs\{os.path.basename(p)[:-4]}" for p in paths}
    idx = RecentIndex(folder, resolve)
    m = idx.targets()
    assert m == {"a.pdf": [r"U:\docs\a.pdf"], "b.pdf": [r"U:\docs\b.pdf"]}
    assert idx.targets() is m                    # unchanged folder: no work
    (folder / "c.pdf.lnk").write_bytes(b"x")
    st = folder.stat()
    os.utime(folder, (st.st_atime, st.st_mtime + 5))
    m2 = idx.targets()
    assert "c.pdf" in m2
    assert resolved == [["a.pdf.lnk", "b.pdf.lnk"], ["c.pdf.lnk"]]
