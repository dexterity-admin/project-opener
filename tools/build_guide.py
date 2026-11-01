"""Build the user guide PDF from docs/guide/guide.html.

    python tools/build_guide.py [--out docs/Project-Opener-User-Guide.pdf]

Pass 1 prints the HTML with headless Chrome/Edge (A4, CSS @page margins).
Pass 2 finds where every numbered heading landed, writes those page numbers
into the contents table, prints again, then stamps the running header, the
footer, "Page X of N" and the PDF outline with PyMuPDF.  Everything is
deterministic: the same source gives the same PDF.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "guide"
SRC = GUIDE / "guide.html"

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

INK = (0x1D / 255, 0x22 / 255, 0x30 / 255)
MUTED = (0x5B / 255, 0x62 / 255, 0x75 / 255)
ACCENT = (0x0E / 255, 0x7C / 255, 0x5B / 255)
RULE = (0xD9 / 255, 0xE2 / 255, 0xDD / 255)


def browser() -> str:
    for b in BROWSERS:
        if Path(b).is_file():
            return b
    sys.exit("No Chrome or Edge found to print the PDF")


def print_pdf(html: Path, out: Path) -> None:
    cmd = [
        browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=10000",
        f"--print-to-pdf={out}", html.resolve().as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    if not out.is_file():
        sys.exit("Chrome produced no PDF")


def heading_pages(pdf: Path) -> dict[str, int]:
    """Map 'N' or 'N.M' section numbers to the 1-based page they start on."""
    found: dict[str, int] = {}
    with pymupdf.open(pdf) as doc:
        for pno, page in enumerate(doc, start=1):
            for b in page.get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    spans = line["spans"]
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in spans).strip()
                    size = spans[0]["size"]
                    m = re.match(r"^(\d+)(?:\.(\d+))?\s+\S", text)
                    if m and size >= 12.5:
                        key = m.group(1) + ("." + m.group(2) if m.group(2) else "")
                        found.setdefault(key, pno)
    return found


def stamp(pdf: Path, out: Path, meta: dict, toc: list[tuple[int, str, int]]) -> None:
    doc = pymupdf.open(pdf)
    n = len(doc)
    logo = GUIDE / "dexterity-logo.png"
    font = GUIDE / "Onest-Regular.ttf"
    head = f"{meta['title']} · {meta['doc_no']} · Rev {meta['rev']}"
    FN = "onest"
    kw = dict(fontsize=7.5, fontname=FN, fontfile=str(font))
    onest = pymupdf.Font(fontfile=str(font))

    def width(t: str) -> float:
        return onest.text_length(t, fontsize=7.5)

    foot = f"{meta['company']} · {meta['classification']}"
    for i, page in enumerate(doc, start=1):
        w, h = page.rect.width, page.rect.height
        if i > 1:
            if logo.is_file():
                page.insert_image(pymupdf.Rect(42, 14, 42 + 26, 14 + 20.4), filename=str(logo), keep_proportion=True)
            page.insert_text((w - 42 - width(head), 30), head, color=MUTED, **kw)
            page.draw_line((42, 40), (w - 42, 40), color=RULE, width=0.6)
        page.draw_line((42, h - 34), (w - 42, h - 34), color=RULE, width=0.6)
        page.insert_text((42, h - 22), foot, color=MUTED, **kw)
        pn = f"Page {i} of {n}"
        page.insert_text((w - 42 - width(pn), h - 22), pn, color=MUTED, **kw)
    doc.set_metadata({"title": meta["title"], "author": meta["company"], "subject": meta["subject"],
                      "keywords": meta.get("keywords", ""), "creator": "tools/build_guide.py"})
    if toc:
        doc.set_toc(toc)
    doc.save(out, garbage=3, deflate=True)
    doc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "Project-Opener-User-Guide.pdf"))
    a = ap.parse_args()
    src = SRC.read_text(encoding="utf-8")
    meta = json.loads(re.search(r"<script id=\"meta\" type=\"application/json\">(.*?)</script>", src, re.S).group(1))
    tmp = Path(tempfile.mkdtemp(prefix="guide-"))
    try:
        # pass 1: page numbers unknown
        html1 = GUIDE / "_pass1.html"
        html1.write_text(src, encoding="utf-8")
        pdf1 = tmp / "pass1.pdf"
        print_pdf(html1, pdf1)
        pages = heading_pages(pdf1)
        html1.unlink()
        # pass 2: fill the contents table
        def fill(m: re.Match) -> str:
            key = m.group(1)
            return f'<span class="toc-page" data-sec="{key}">{pages.get(key, "")}</span>'
        src2 = re.sub(r'<span class="toc-page" data-sec="([\d.]+)">[^<]*</span>', fill, src)
        html2 = GUIDE / "_pass2.html"
        html2.write_text(src2, encoding="utf-8")
        pdf2 = tmp / "pass2.pdf"
        print_pdf(html2, pdf2)
        html2.unlink()
        pages2 = heading_pages(pdf2)
        if pages2 != pages:
            # a third pass settles the rare case where filling the numbers moved a heading
            src3 = re.sub(r'<span class="toc-page" data-sec="([\d.]+)">[^<]*</span>',
                          lambda m: f'<span class="toc-page" data-sec="{m.group(1)}">{pages2.get(m.group(1), "")}</span>', src)
            html2.write_text(src3, encoding="utf-8")
            print_pdf(html2, pdf2)
            html2.unlink()
            pages2 = heading_pages(pdf2)
        toc = []
        for m in re.finditer(r'<h([23])[^>]*>\s*(\d+(?:\.\d+)?)\s+([^<]+?)\s*</h\1>', src):
            lvl, key, title = int(m.group(1)) - 1, m.group(2), re.sub(r"\s+", " ", m.group(3))
            if key in pages2:
                toc.append((lvl, f"{key} {title}", pages2[key]))
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        stamp(pdf2, out, meta, toc)
        print(f"{out}  ({len(pymupdf.open(out))} pages, {out.stat().st_size // 1024} KB)")
        missing = [k for k in re.findall(r'data-sec="([\d.]+)"', src) if k not in pages2]
        if missing:
            print("WARNING: contents entries without a page:", missing)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
