"""Generated revision pairs for the visual revision diff: tests and smoke screenshots (no customer files).

    make_pdf_pair(folder)  -> (rev B .pdf, rev C .pdf)   an isometric-style sheet; rev C moved 2 pt by a
                                                          re-plot, one leg rerouted, a field weld added, the
                                                          revision letter changed; page 2 the same; page 3 new
    make_xlsx_pair(folder) -> (rev B .xlsx, rev C .xlsx) a line list (stdlib zipfile XML)
    make_docx_pair(folder) -> (rev B .docx, rev C .docx) a comment register (stdlib zipfile XML)
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

# ------------------------------------------------------------------------------------------------ PDF


def _sheet(page, rev: str, reroute: bool, weld: bool, dx: float = 0.0, dy: float = 0.0) -> None:
    import pymupdf as fitz

    def P(x: float, y: float):  # noqa: N802
        return fitz.Point(x + dx, y + dy)

    w, h = page.rect.width, page.rect.height
    page.draw_rect(fitz.Rect(P(20, 20), P(w - 20, h - 20)), color=(0, 0, 0), width=1.2)
    # title block
    tb = fitz.Rect(P(w - 300, h - 110), P(w - 20, h - 20))
    page.draw_rect(tb, color=(0, 0, 0), width=1)
    page.draw_line(P(w - 300, h - 80), P(w - 20, h - 80), color=(0, 0, 0), width=0.6)
    page.insert_text(P(w - 290, h - 90), "P12513  AS-BUILT ISOMETRIC", fontsize=11)
    page.insert_text(P(w - 290, h - 60), "LINE 6\"-P-1201-A1A", fontsize=10)
    page.insert_text(P(w - 290, h - 35), f"SHEET 1 OF 1   REV {rev}", fontsize=10)
    # the isometric: a run of pipe with an elbow
    pts = [(120, 420), (260, 340), (260, 220), (420, 128)]
    if reroute:
        pts = [(120, 420), (260, 340), (260, 260), (420, 168)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        page.draw_line(P(x0, y0), P(x1, y1), color=(0, 0, 0), width=2.4)
    page.draw_circle(P(260, 340), 5, color=(0, 0, 0), width=1)
    page.insert_text(P(140, 395), "6\" PIPE", fontsize=9)
    page.insert_text(P(275, 300), "EL +102.450", fontsize=9)
    if weld:
        page.draw_circle(P(340, 214), 7, color=(0, 0, 0), width=1.4)
        page.insert_text(P(352, 210), "FW-12", fontsize=9)
    # bill of materials
    page.insert_text(P(40, 60), "BILL OF MATERIALS", fontsize=10)
    for k, row in enumerate(("1  PIPE 6\" SCH40", "2  ELBOW 90 LR", "3  GASKET SW")):
        page.insert_text(P(40, 80 + 14 * k), row, fontsize=8)


def make_pdf_pair(folder: str | Path) -> tuple[Path, Path]:
    import pymupdf as fitz
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    a, b = folder / "6-P-1201 rev B.pdf", folder / "6-P-1201 rev C.pdf"
    size = (842, 595)                                   # A4 landscape, points
    for path, rev, later in ((a, "B", False), (b, "C", True)):
        doc = fitz.open()
        page = doc.new_page(width=size[0], height=size[1])
        _sheet(page, rev, reroute=later, weld=later, dx=2.0 if later else 0.0, dy=-1.5 if later else 0.0)
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_text((60, 80), "GENERAL NOTES", fontsize=12)
        page.insert_text((60, 110), "1. ALL DIMENSIONS IN MM UNLESS NOTED.", fontsize=10)
        page.draw_rect(fitz.Rect(20, 20, size[0] - 20, size[1] - 20), color=(0, 0, 0), width=1.2)
        if later:
            page = doc.new_page(width=size[0], height=size[1])
            page.insert_text((60, 80), "SUPPORT DETAIL SD-04", fontsize=12)
            page.draw_rect(fitz.Rect(100, 120, 300, 260), color=(0, 0, 0), width=1.5)
        doc.save(str(path))
        doc.close()
    return a, b


# ------------------------------------------------------------------------------------------------ zip XML
def _zip(path: Path, parts: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(name, text)


_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def write_xlsx(path: str | Path, sheets: dict[str, list[list[object]]]) -> Path:
    """A minimal .xlsx: strings go to the shared-string table, numbers stay numbers, a str starting with "="
    is a formula (cached value omitted), a ("date", serial) tuple is a date-formatted number."""
    path = Path(path)
    shared: list[str] = []
    sheet_parts = {}
    for k, rows in enumerate(sheets.values(), 1):
        out = []
        for r, row in enumerate(rows, 1):
            cells = []
            for c, v in enumerate(row, 1):
                col = ""
                n = c
                while n:
                    n, rem = divmod(n - 1, 26)
                    col = chr(65 + rem) + col
                ref = f"{col}{r}"
                if v is None:
                    continue
                if isinstance(v, tuple) and v[0] == "date":
                    cells.append(f'<c r="{ref}" s="1"><v>{v[1]}</v></c>')
                elif isinstance(v, str) and v.startswith("="):
                    cells.append(f'<c r="{ref}"><f>{escape(v[1:])}</f></c>')
                elif isinstance(v, str):
                    if v not in shared:
                        shared.append(v)
                    cells.append(f'<c r="{ref}" t="s"><v>{shared.index(v)}</v></c>')
                else:
                    cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            out.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_parts[f"xl/worksheets/sheet{k}.xml"] = (
            f'{_XML}<worksheet xmlns="{_MAIN}"><sheetData>{"".join(out)}</sheetData></worksheet>')
    names = list(sheets)
    parts = {
        "[Content_Types].xml": f'{_XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(f'<Override PartName="/xl/worksheets/sheet{k}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                  for k in range(1, len(names) + 1)) + "</Types>",
        "_rels/.rels": f'{_XML}<Relationships xmlns="{_PKG}"><Relationship Id="rId1" '
        f'Type="{_R}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'{_XML}<workbook xmlns="{_MAIN}" xmlns:r="{_R}"><sheets>'
        + "".join(f'<sheet name="{escape(n)}" sheetId="{k}" r:id="rId{k}"/>' for k, n in enumerate(names, 1))
        + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": f'{_XML}<Relationships xmlns="{_PKG}">'
        + "".join(f'<Relationship Id="rId{k}" Type="{_R}/worksheet" Target="worksheets/sheet{k}.xml"/>'
                  for k in range(1, len(names) + 1))
        + f'<Relationship Id="rId{len(names) + 1}" Type="{_R}/styles" Target="styles.xml"/>'
        + f'<Relationship Id="rId{len(names) + 2}" Type="{_R}/sharedStrings" Target="sharedStrings.xml"/>'
        + "</Relationships>",
        "xl/styles.xml": f'{_XML}<styleSheet xmlns="{_MAIN}"><numFmts count="1">'
        '<numFmt numFmtId="164" formatCode="dd-mmm-yy"/></numFmts>'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164" applyNumberFormat="1"/></cellXfs></styleSheet>',
        "xl/sharedStrings.xml": f'{_XML}<sst xmlns="{_MAIN}" count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t xml:space=\"preserve\">{escape(s)}</t></si>" for s in shared) + "</sst>",
    }
    parts.update(sheet_parts)
    _zip(path, parts)
    return path


LINE_LIST_B = [
    ["Line No", "Size", "Spec", "Rev", "Issued", "Length m"],
    ["6\"-P-1201-A1A", 6, "A1A", "B", ("date", 46300), 42.5],
    ["4\"-P-1202-A1A", 4, "A1A", "B", ("date", 46300), 18],
    ["2\"-D-1203-B2C", 2, "B2C", "A", ("date", 46290), 7.25],
    ["3\"-CW-1204-A1A", 3, "A1A", "B", ("date", 46300), 30],
    ["Total", None, None, None, None, "=SUM(F2:F5)"],
]
LINE_LIST_C = [
    ["Line No", "Size", "Spec", "Rev", "Issued", "Length m"],
    ["6\"-P-1201-A1A", 6, "A1A", "C", ("date", 46345), 44.1],
    ["4\"-P-1202-A1A", 4, "A1A", "B", ("date", 46300), 18],
    ["2\"-D-1203-B2C", 3, "B2C", "A", ("date", 46290), 7.25],
    ["3\"-CW-1204-A1A", 3, "A1A", "B", ("date", 46300), 30],
    ["8\"-P-1205-A1A", 8, "A1A", "0", ("date", 46345), 12],
    ["Total", None, None, None, None, "=SUM(F2:F6)"],
]


def make_xlsx_pair(folder: str | Path) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    a = write_xlsx(folder / "Line list rev B.xlsx", {
        "Line list": LINE_LIST_B, "Notes": [["Area 12 lines only"]], "Holds": [["HOLD-3", "Valve data"]]})
    b = write_xlsx(folder / "Line list rev C.xlsx", {
        "Line list": LINE_LIST_C, "Notes": [["Area 12 lines only"]], "Revisions": [["C", "Rerouted 6\"-P-1201"]]})
    return a, b


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def write_docx(path: str | Path, blocks: list[object], header: str = "") -> Path:
    """A minimal .docx: a str is a paragraph, a list of lists of str is a table."""
    path = Path(path)

    def para(text: str) -> str:
        return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'

    body = []
    for b in blocks:
        if isinstance(b, str):
            body.append(para(b))
        else:
            rows = "".join("<w:tr>" + "".join(f"<w:tc>{para(c)}</w:tc>" for c in row) + "</w:tr>" for row in b)
            body.append(f"<w:tbl>{rows}</w:tbl>")
    parts = {
        "[Content_Types].xml": f'{_XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": f'{_XML}<Relationships xmlns="{_PKG}"><Relationship Id="rId1" '
        f'Type="{_R}/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": f'{_XML}<w:document xmlns:w="{_W}"><w:body>{"".join(body)}</w:body></w:document>',
    }
    if header:
        parts["word/header1.xml"] = f'{_XML}<w:hdr xmlns:w="{_W}">{para(header)}</w:hdr>'
    _zip(path, parts)
    return path


def make_docx_pair(folder: str | Path) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    a = write_docx(folder / "Comment register rev B.docx", [
        "Back-check comments, lot 7",
        "All isometrics were checked against the RLM mark-ups.",
        [["No", "Drawing", "Comment", "Status"],
         ["1", "6-P-1201", "Elevation at elbow missing", "Open"],
         ["2", "4-P-1202", "Support SD-04 not shown", "Open"]],
        "Issued for review.",
    ], header="P12513 rev B")
    b = write_docx(folder / "Comment register rev C.docx", [
        "Back-check comments, lot 7",
        "All isometrics were checked against the RLM mark-ups and the line list.",
        [["No", "Drawing", "Comment", "Status"],
         ["1", "6-P-1201", "Elevation at elbow missing", "Closed"],
         ["2", "4-P-1202", "Support SD-04 not shown", "Open"],
         ["3", "6-P-1201", "Field weld FW-12 added", "Open"]],
    ], header="P12513 rev C")
    return a, b
