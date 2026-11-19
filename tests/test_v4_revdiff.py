"""Visual revision diff core (project_opener/core/revdiff.py) on generated revision pairs (tools/revdiff_samples.py).

The fixture PDFs are drawn with PyMuPDF (a dev tool here, never imported by the app); the app reads them
with QtPdf."""
from __future__ import annotations

import json
import os
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from project_opener.core import revdiff as R  # noqa: E402
from tools import revdiff_samples as S  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def pdf_result(tmp_path_factory, qapp):
    d = tmp_path_factory.mktemp("pdf")
    a, b = S.make_pdf_pair(d)
    return R.compare(a, b, d / "out")


# ------------------------------------------------------------------------------------------------ PDF
def test_pdf_pages_status(pdf_result):
    pages = pdf_result["pages"]
    assert [p["status"] for p in pages] == ["changed", "same", "added"]
    assert pdf_result["summary"] == "2 of 3 pages changed · 4 regions · 1 page added"


def test_pdf_realigns_a_replotted_sheet(pdf_result):
    """Rev C was drawn 2 pt right and 1.5 pt up: aligned, the unchanged border and BOM leave no region."""
    import re
    p = pdf_result["pages"][0]
    note = next(n for n in p["notes"] if n.startswith("Newer revision aligned by"))
    dx, dy = (float(v) for v in re.findall(r"[+-]\d+\.\d", note))
    px_mm = 25.4 / 150                                       # one pixel at the render's 150 dpi
    assert abs(dx - -2 * 25.4 / 72) <= px_mm + 0.05 and abs(dy - 1.5 * 25.4 / 72) <= px_mm + 0.05
    assert len(p["regions"]) == 2
    for r in p["regions"]:                                   # nothing near the border or the BOM
        assert r["mm"][0] > 40


def test_pdf_regions_carry_the_words(pdf_result):
    regions = pdf_result["pages"][0]["regions"]
    reroute, rev = regions
    assert reroute["kind"] == "both" and reroute["wordsAdded"] == ["FW-12"]
    assert rev["wordsAdded"] == ["C"] and rev["wordsRemoved"] == ["B"]
    assert all(0 <= r[k] <= 1 for r in regions for k in ("x", "y", "w", "h"))
    assert [r["n"] for r in regions] == [1, 2]


def test_pdf_overlay_colours(pdf_result):
    from PySide6.QtGui import QImage
    p = pdf_result["pages"][0]
    img = QImage(p["overlay"])
    assert (img.width(), img.height()) == (p["width"], p["height"])
    colours = set()
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            colours.add((c.red(), c.green(), c.blue()))
    assert R.ADDED in colours and R.REMOVED in colours and R.UNCHANGED in colours
    assert colours <= {R.PAPER, R.ADDED, R.REMOVED, R.UNCHANGED}


def test_cells_count_pixels_per_block():
    w, h = 16, 16
    data = bytearray(w * h)
    for x, y in ((0, 0), (7, 7), (8, 0), (15, 15), (9, 12)):
        data[y * w + x] = 1
    assert R._cells(int.from_bytes(bytes(data), "big"), w, h) == [2, 1, 0, 2]


def test_pdf_same_file_has_no_change(tmp_path):
    a, _ = S.make_pdf_pair(tmp_path)
    res = R.compare(a, a, tmp_path / "out")
    assert res["changedPages"] == 0 and res["regionCount"] == 0
    assert all(p["status"] == "same" for p in res["pages"])


def test_pdf_removed_page(tmp_path):
    a, b = S.make_pdf_pair(tmp_path)
    res = R.compare(b, a, tmp_path / "out")                # newer -> older: page 3 removed
    assert res["pages"][2]["status"] == "removed"
    assert "1 page removed" in res["summary"]


def test_result_is_cached_and_deterministic(tmp_path):
    a, b = S.make_pdf_pair(tmp_path)
    first = R.compare(a, b, tmp_path / "out")
    folder = tmp_path / "out" / R.cache_key(a, b)
    assert (folder / "result.json").is_file()
    again = R.compare(a, b, tmp_path / "out")
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    fresh = R.compare(a, b, tmp_path / "out2")              # computed again from scratch: the same facts
    strip = lambda r: [{k: v for k, v in p.items() if k not in ("overlay", "thumb")} for p in r["pages"]]  # noqa: E731
    assert strip(first) == strip(fresh)


# ------------------------------------------------------------------------------------------------ Excel
def test_xlsx_cells_with_rows_aligned(tmp_path):
    a, b = S.make_xlsx_pair(tmp_path)
    res = R.compare(a, b, tmp_path / "out")
    sheets = {s["name"]: s for s in res["sheets"]}
    assert [s["name"] for s in res["sheets"]] == ["Line list", "Notes", "Holds", "Revisions"]
    assert sheets["Notes"]["status"] == "same"
    assert sheets["Holds"]["status"] == "removed" and sheets["Revisions"]["status"] == "added"
    ll = sheets["Line list"]
    got = {(r["cell"], r["kind"]): (r["old"], r["new"]) for r in ll["rows"]}
    assert got[("D2", "changed")] == ("B", "C")
    assert got[("F2", "changed")] == ("42.5", "44.1")
    assert got[("E2", "changed")] == ("2026-10-05", "2026-11-19")      # date-formatted serials shown as dates
    assert got[("B4", "changed")] == ("2", "3")
    assert got[("A6", "added")] == ("", '8"-P-1205-A1A')
    # the inserted row does not cascade: Total moved from row 6 to 7 and only its formula changed
    total = [r for r in ll["rows"] if r["cell"] == "F7"]
    assert total == [{"cell": "F7", "oldCell": "F6", "kind": "formula", "old": "", "new": "",
                      "oldFormula": "=SUM(F2:F5)", "newFormula": "=SUM(F2:F6)"}]
    assert not any(r["cell"] == "A7" for r in ll["rows"])
    assert ll["rowsInserted"] == 1 and ll["rowsDeleted"] == 0
    assert res["summary"] == "15 cells differ in 3 of 4 sheets · 5 changed · 8 added · 2 removed"


def test_xlsx_rich_and_inline_strings(tmp_path):
    p = tmp_path / "rich.xlsx"
    S.write_xlsx(p, {"S": [["x"]]})
    with zipfile.ZipFile(p) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    parts["xl/sharedStrings.xml"] = (
        f'<sst xmlns="{R.NS_MAIN}"><si><r><t>Line </t></r><r><t>6"</t></r><rPh><t>ignored</t></rPh></si></sst>'
    ).encode()
    parts["xl/worksheets/sheet1.xml"] = (
        f'<worksheet xmlns="{R.NS_MAIN}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
        '<c r="B1" t="inlineStr"><is><t>inline</t></is></c><c r="C1" t="b"><v>1</v></c>'
        '<c r="D1"><v>0.30000000000000004</v></c><c r="E1" s="0"/></row></sheetData></worksheet>').encode()
    with zipfile.ZipFile(p, "w") as z:
        for n, data in parts.items():
            z.writestr(n, data)
    cells = R.read_xlsx(p)["S"]
    assert cells == {"A1": ('Line 6"', ""), "B1": ("inline", ""), "C1": ("TRUE", ""), "D1": ("0.3", "")}


def test_col_letters_round_trip():
    for n in (1, 26, 27, 52, 703, 16384):
        assert R.col_index(R.col_letters(n)) == n
    assert R.col_letters(28) == "AB"


# ------------------------------------------------------------------------------------------------ Word
def test_docx_paragraphs_tables_and_header(tmp_path):
    a, b = S.make_docx_pair(tmp_path)
    res = R.compare(a, b, tmp_path / "out")
    rows = [(r["kind"], r["where"]) for r in res["paragraphs"]]
    assert ("changed", "Paragraph 2") in rows
    assert ("changed", "Table 1, row 2, cell 4") in rows          # Open -> Closed, paired by its cell
    assert ("removed", "Paragraph 3") in rows
    assert ("changed", "Header 1") in rows
    assert sum(k == "added" for k, _ in rows) == 4                 # the new register row, cell by cell
    p2 = next(r for r in res["paragraphs"] if r["where"] == "Paragraph 2")
    assert p2["segments"] == [
        {"op": "eq", "text": "All isometrics were checked against the RLM mark-ups"},
        {"op": "ins", "text": " and the line list"}, {"op": "eq", "text": "."}]
    cell = next(r for r in res["paragraphs"] if r["where"] == "Table 1, row 2, cell 4")
    assert (cell["old"], cell["new"]) == ("Open", "Closed")
    assert res["summary"] == "3 paragraphs changed · 4 paragraphs added · 1 paragraph removed"


def test_docx_tracked_changes_read_as_accepted(tmp_path):
    p = tmp_path / "t.docx"
    S.write_docx(p, ["x"])
    body = (f'<w:document xmlns:w="{R.NS_W}"><w:body><w:p><w:r><w:t>Rev </w:t></w:r>'
            '<w:del><w:r><w:delText>B</w:delText></w:r></w:del><w:ins><w:r><w:t>C</w:t></w:r></w:ins>'
            '<w:r><w:tab/><w:t>issued</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(p) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    parts["word/document.xml"] = body.encode()
    with zipfile.ZipFile(p, "w") as z:
        for n, data in parts.items():
            z.writestr(n, data)
    assert R.read_docx(p) == [("", "Rev C\tissued")]


def test_docx_same_file(tmp_path):
    a, _ = S.make_docx_pair(tmp_path)
    res = R.compare(a, a, tmp_path / "out")
    assert res["paragraphs"] == [] and res["summary"] == "No text differs"


# ------------------------------------------------------------------------------------------------ errors
def test_pairs_that_cannot_be_compared(tmp_path):
    a, _ = S.make_docx_pair(tmp_path)
    x, _ = S.make_xlsx_pair(tmp_path)
    old = tmp_path / "old.xls"
    old.write_bytes(b"\xd0\xcf\x11\xe0")
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1032")
    with pytest.raises(R.DiffError, match="different kinds"):
        R.check_pair(a, x)
    with pytest.raises(R.DiffError, match=r"Save it as \.xlsx"):
        R.check_pair(old, x)
    with pytest.raises(R.DiffError, match="PDF, .xlsx and .docx files only"):
        R.check_pair(dwg, dwg)
    with pytest.raises(R.DiffError, match="was not found"):
        R.check_pair(tmp_path / "gone.pdf", tmp_path / "gone2.pdf")
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(R.DiffError, match="could not be read"):
        R.compare(bad, x, tmp_path / "out")


# ------------------------------------------------------------------------------------------------ app.diff
class _FakeUi:
    def __init__(self):
        self.went = []

    def go(self, route, payload=None):
        self.went.append((route, payload))


@pytest.fixture
def diff_api(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QObject, Signal
    QCoreApplication.instance() or QCoreApplication([])
    from project_opener.quick import diff_api as D

    class FakeApp(QObject):
        toast = Signal(str, str, str)

        def __init__(self):
            super().__init__()
            self.ui = _FakeUi()

        def run_async(self, fn, done=None, fail=None):
            try:
                r = fn()
            except Exception as exc:  # noqa: BLE001
                if fail:
                    fail(exc)
                return
            if done:
                done(r)

        def run_on_gui(self, fn):
            fn()

    monkeypatch.setattr(D, "out_dir", lambda: tmp_path / "renders")
    fake = FakeApp()
    return D.DiffApi(fake), fake


def test_api_drop_two_orders_by_modified_date(tmp_path, diff_api):
    import os
    api, _ = diff_api
    a, b = S.make_xlsx_pair(tmp_path)
    os.utime(b, (1_700_000_000, 1_700_000_000))            # rev C saved earlier than rev B
    os.utime(a, (1_800_000_000, 1_800_000_000))
    api.dropped([b.as_uri(), a.as_uri()][::-1])
    assert (api.fileA, api.fileB) == (str(b), str(a))
    assert api.state == "done" and api.result["kind"] == "xlsx"
    api.swap()
    assert (api.fileA, api.fileB) == (str(a), str(b))
    assert api.result["nameA"] == a.name


def test_api_one_file_then_the_other(tmp_path, diff_api):
    api, _ = diff_api
    a, b = S.make_pdf_pair(tmp_path)
    api.dropped([str(a)])
    assert api.state == "idle" and api.fileA == str(a) and api.fileB == ""
    api.setFile("", str(b))
    assert api.state == "done"
    assert all(p["overlayUrl"].startswith("file:") for p in api.result["pages"])


def test_api_error_and_open_pair(tmp_path, diff_api):
    api, fake = diff_api
    a, _ = S.make_pdf_pair(tmp_path)
    x, _ = S.make_xlsx_pair(tmp_path)
    api.compare(str(a), str(x))
    assert api.state == "error" and "different kinds" in api.error
    api.openPair(str(x), str(a))
    route, payload = fake.ui.went[-1]
    assert route == "diff" and set(payload) == {"a", "b"}
    api.clear()
    assert (api.state, api.fileA, api.fileB, api.result) == ("idle", "", "", {})


def test_kind_of():
    assert [R.kind_of(p) for p in ("a.PDF", "b.xlsm", "c.docx", "d.dwg")] == ["pdf", "xlsx", "docx", ""]
