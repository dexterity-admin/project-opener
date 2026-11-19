"""Space map: the scanner (sizes, duplicates, stale files, skipped paths, cache, cancel, long paths), the map's
levels, and ``app.spacemap`` over a hub with published cards.  Report only: the tree is checked unchanged."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from project_opener.core import spacemap as S  # noqa: E402

NOW = time.time()
OLD = NOW - 30 * S.MONTH_S                      # 30 months ago


def _write(p: Path, data: bytes, mtime: float | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


@pytest.fixture
def tree(tmp_path):
    """job/ with two copies of one drawing (one in a subfolder), a same-size file that differs only after the
    64 KiB head, two same-size small files that differ, a stale file and tiny files under the duplicate floor."""
    job = tmp_path / "P12513"
    same = os.urandom(100_000)
    _write(job / "iso-1043.pdf", same)
    _write(job / "Rev C" / "iso-1043 copy.pdf", same)
    _write(job / "Rev C" / "iso-1044.pdf", same[:90_000] + os.urandom(10_000))  # same size and head, other tail
    _write(job / "a.dwg", b"A" * 5000)
    _write(job / "b.dwg", b"B" * 5000)                                        # same size, other content
    _write(job / "old" / "rlm-2019.pdf", os.urandom(20_000), OLD)
    _write(job / "t1.txt", b"x")
    _write(job / "t2.txt", b"x")                                              # equal, but under min_dup_bytes
    other = tmp_path / "ANTEO"
    _write(other / "gad.pdf", same, NOW - 2 * S.MONTH_S)                       # the oldest copy, another card
    return tmp_path


def _snapshot(root: Path) -> dict[str, tuple[int, float]]:
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            st = os.stat(os.path.join(dp, f))
            out[os.path.join(dp, f)] = (st.st_size, st.st_mtime)
    return out


def _scan(roots, cards=None, **kw) -> S.ScanResult:
    return S.Scanner(roots, cards=cards, now=NOW, **kw).run()


# ----------------------------------------------------------------- roots
def test_roots_from_cards_dedupes_and_nests(tmp_path):
    a, b = str(tmp_path / "P12513"), str(tmp_path / "P12513" / "Rev C")
    roots, cards = S.roots_from_cards([("P12513 · Lot 7", [a, b]), ("P12513 · Rev C", [b]), ("Empty", []),
                                       ("ANTEO", [str(tmp_path / "ANTEO"), str(tmp_path / "ANTEO") + "\\"])])
    assert [r.path for r in roots] == [os.path.normpath(a), os.path.normpath(str(tmp_path / "ANTEO"))]
    assert roots[0].cards == ["P12513 · Lot 7", "P12513 · Rev C"]        # the nested card scans with the outer
    assert cards["P12513 · Lot 7"] == [os.path.normpath(a)]               # its own nested folder counts once
    assert cards["P12513 · Rev C"] == [os.path.normpath(b)]
    assert len(cards["ANTEO"]) == 1 and "Empty" not in cards


# ----------------------------------------------------------------- scan
def test_scan_sizes_duplicates_stale(tree):
    before = _snapshot(tree)
    roots, cards = S.roots_from_cards([("P12513", [str(tree / "P12513")]), ("ANTEO", [str(tree / "ANTEO")])])
    res = _scan(roots, cards, stale_months=12)
    assert res.complete
    assert _snapshot(tree) == before                                        # report only: nothing changed

    job = res.folder(str(tree / "P12513"))
    total = sum(s for p, (s, _m) in before.items() if p.startswith(str(tree / "P12513") + os.sep))
    assert job.size == total and job.files == 8
    revc = res.folder(str(tree / "P12513" / "Rev C"))
    assert revc.size == 200_000 and revc.files == 2
    assert res.size == total + 100_000 and res.files == 9

    groups = {tuple(sorted(os.path.basename(p) for p in g["paths"])) for g in res.duplicates}
    assert groups == {("gad.pdf", "iso-1043 copy.pdf", "iso-1043.pdf")}     # not iso-1044 (other tail), not a/b
    g = res.duplicates[0]
    assert g["size"] == 100_000 and g["wasted"] == 200_000

    assert res.stale_count == 1 and res.stale[0]["path"].endswith("rlm-2019.pdf")
    assert res.stale_bytes == 20_000
    # flagged: the job's two extra copies (gad.pdf is the oldest copy) and the stale file
    assert job.flagged == 100_000 * 2 + 20_000
    assert res.folder(str(tree / "ANTEO")).flagged == 0
    assert res.skipped == []


def test_unreachable_and_denied_paths_are_skipped(tree):
    bad = str(tree / "no such folder")
    unc = r"\\127.0.0.1\no-such-share-po4" if sys.platform == "win32" else "/no/such/share"
    roots, cards = S.roots_from_cards([("P12513", [str(tree / "P12513")]), ("Gone", [bad]), ("Share", [unc])])
    res = _scan(roots, cards)
    assert res.complete
    reasons = {r["path"]: r["reason"] for r in res.skipped}
    assert reasons[os.path.normpath(bad)] == "not reachable from this PC"
    assert os.path.normpath(unc) in reasons
    assert res.folder(str(tree / "P12513")).files == 8                       # the good root is still scanned
    lv = S.level(res, [])
    assert {b["label"] for b in lv["bubbles"]} == {"P12513"}                 # no bubble for an unscanned card


@pytest.mark.skipif(sys.platform != "win32", reason="Windows long paths")
def test_long_paths(tmp_path):
    deep = str(tmp_path / "deep")
    for i in range(12):
        deep = os.path.join(deep, f"folder-with-a-long-name-{i:02d}")
    assert len(deep) > 260
    os.makedirs(S.long_path(deep))
    with open(S.long_path(os.path.join(deep, "sheet.pdf")), "wb") as fh:
        fh.write(b"z" * 10_000)
    res = _scan([S.ScanRoot(str(tmp_path / "deep"), ["Deep"])])
    assert res.files == 1 and res.size == 10_000
    assert not [s for s in res.skipped if s["reason"] == "path too long"]
    assert S.short_path(S.long_path(deep)) == deep


def test_cancel_keeps_what_was_listed(tree):
    sc = S.Scanner([S.ScanRoot(str(tree / "P12513"), ["P12513"])], now=NOW)
    sc.cancel()
    res = sc.run()
    assert not res.complete
    assert res.skipped[-1]["reason"] == "scan stopped before the end"


def test_background_thread_reports_progress_and_result(tree):
    seen, done = [], []
    sc = S.Scanner([S.ScanRoot(str(tree / "P12513"), ["P12513"])], now=NOW, tick_s=0,
                   on_progress=seen.append, on_done=done.append)
    sc.start()
    sc.join(20)
    assert done and done[0].complete
    assert seen and seen[-1].phase == "saving" and seen[-1].files == 8
    assert any(p.phase == "listing" for p in seen)


def test_cache_reuses_hashes_and_loads(tree, tmp_path):
    cache = tmp_path / "cache" / "scan.json"
    roots = [S.ScanRoot(str(tree / "P12513"), ["P12513"])]
    first = _scan(roots, cache_path=cache)
    assert len(first.duplicates) == 1 and cache.is_file()
    # change the copy's content but keep its size and time: the cached hash stands (no re-read)
    copy = tree / "P12513" / "Rev C" / "iso-1043 copy.pdf"
    st = copy.stat()
    copy.write_bytes(os.urandom(100_000))
    os.utime(copy, (st.st_atime, st.st_mtime))
    second = _scan(roots, cache_path=cache)
    assert len(second.duplicates) == 1
    loaded = S.load_cached(cache)
    assert loaded is not None and loaded.complete and loaded.size == second.size
    assert loaded.folder(str(tree / "P12513" / "Rev C")).size == 200_000
    assert loaded.cards == {"P12513": [str(tree / "P12513")]}
    assert S.load_cached(tmp_path / "none.json") is None


# ----------------------------------------------------------------- levels
def test_levels_and_scope(tree):
    roots, cards = S.roots_from_cards([("P12513", [str(tree / "P12513")]), ("ANTEO", [str(tree / "ANTEO")])])
    res = _scan(roots, cards)
    top = S.level(res, [])
    assert [b["label"] for b in top["bubbles"]] == ["P12513", "ANTEO"]      # largest first
    assert top["scope"] is None and top["crumbs"] == [{"label": "All projects", "depth": 0}]
    p = top["bubbles"][0]
    assert p["drillable"] and 0 < p["share"] < 1 and p["sizeText"].endswith("KB")

    one = S.level(res, ["card:P12513"])                  # a one-folder card opens straight onto its folder
    labels = {b["label"] for b in one["bubbles"]}
    assert labels == {"Rev C", "old", "Files here"}
    assert one["scope"] == [str(tree / "P12513")]
    assert [c["label"] for c in one["crumbs"]] == ["All projects", "P12513"]
    files_here = next(b for b in one["bubbles"] if b["label"] == "Files here")
    assert not files_here["drillable"] and files_here["bytes"] == 100_000 + 10_000 + 2

    rev = S.level(res, ["card:P12513", str(tree / "P12513" / "Rev C")])
    assert [c["label"] for c in rev["crumbs"]][-1] == "Rev C"
    assert S.in_scope(str(tree / "P12513" / "Rev C" / "x.pdf"), rev["scope"])
    assert not S.in_scope(str(tree / "ANTEO" / "gad.pdf"), rev["scope"])


def test_level_groups_the_small_ones(tmp_path):
    for i in range(S.MAX_BUBBLES + 5):
        _write(tmp_path / "job" / f"f{i:02d}" / "a.bin", b"x" * (100 + i))
    res = _scan([S.ScanRoot(str(tmp_path / "job"), ["Job"])])
    lv = S.level(res, ["card:Job"])
    assert len(lv["bubbles"]) == S.MAX_BUBBLES
    more = [b for b in lv["bubbles"] if b["bubbleKey"] == "more:"]
    assert more and more[0]["label"] == "6 smaller" and not more[0]["drillable"]


def test_texts():
    assert S.size_text(0) == "0 B" and S.size_text(2048) == "2 KB"
    assert S.size_text(5 * 1024 ** 3) == "5.0 GB" and S.size_text(300 * 1024 ** 3) == "300 GB"
    assert S.age_text(NOW - 14 * S.MONTH_S, NOW) == "14 months"
    assert S.age_text(NOW - 30 * S.MONTH_S, NOW) == "2 years"
    assert S.age_text(NOW - 1.2 * S.MONTH_S, NOW) == "1 month"


# ----------------------------------------------------------------- app.spacemap
@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _pump(cond, timeout=20.0):
    from PySide6.QtWidgets import QApplication
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def hubbed(qapp, isolated_data_dir, hub_root, tree, monkeypatch):
    from project_opener.core import models as M
    from project_opener.core.settings import Settings
    from project_opener.lan.hub import TeamHub
    s = Settings.load(isolated_data_dir)
    s.hub_path = str(hub_root)
    s.save()
    hub = TeamHub(hub_root, user="vikram")
    hub.initialise()
    hub.publish(M.Project(name="Lot 7", job_number="P12513",
                          items=[M.Item(path=str(tree / "P12513"), kind="folder"),
                                 M.Item(path=str(tree / "P12513" / "iso-1043.pdf"), kind="file")]))
    hub.publish(M.Project(name="ANTEO Isometrics", items=[M.Item(path=str(tree / "ANTEO"), kind="folder")]))
    hub.publish(M.Project(name="Gone", items=[M.Item(path=str(tree / "missing"), kind="folder")]))
    from project_opener.quick.facade import AppFacade
    app = AppFacade(isolated_data_dir)
    yield app
    app.spacemap.shutdown()
    app.deleteLater()


def test_api_scan_drill_and_lists(hubbed, hub_root, tree):
    sm = hubbed.spacemap
    assert sm is hubbed.spacemap                                     # one API, built on first read
    sm.load()
    assert _pump(lambda: sm.state in ("idle", "done"))
    assert not sm.hasResult and sm.summary == "Not scanned yet."
    sm.scan()
    assert _pump(lambda: sm.state == "done"), sm.error
    assert (hub_root / "spacemap" / "scan.json").is_file()           # the cache is on the hub
    rows = sm.bubbles.rows
    assert [r["label"] for r in rows] == ["P12513 · Lot 7", "ANTEO Isometrics"]
    assert sm.stats["skipped"] == 1 and sm.skipped.rows[0]["reason"] == "not reachable from this PC"
    assert sm.duplicateCount == 1 and sm.staleCount == 1
    dup = sm.duplicates.rows[0]
    assert dup["countText"] == "3 copies" and len(dup["paths"]) == 3
    total = S.size_text(sum(os.path.getsize(os.path.join(d, f)) for job in ("P12513", "ANTEO")
                            for d, _n, fs in os.walk(tree / job) for f in fs))
    assert sm.summary.startswith(f"{total} in 2 folders on 3 cards · 1 not reachable · scanned ")

    sm.drill("card:ANTEO Isometrics")                                # scope: the lists follow the drill-down
    assert sm.depth == 1 and [c["label"] for c in sm.crumbs] == ["All projects", "ANTEO Isometrics"]
    assert sm.duplicateCount == 1 and sm.staleCount == 0
    sm.goTo(0)
    assert sm.depth == 0 and len(sm.bubbles.rows) == 2
    sm.drill("files:x")                                              # not drillable
    assert sm.depth == 0

    sm.setStaleMonths("36")
    assert hubbed.ctx.settings.spacemap_stale_months == 36 and sm.staleMonths == 36
    assert sm.scannedMonths == 12                                   # the shown scan keeps its own threshold


def test_api_without_a_hub_says_so(qapp, isolated_data_dir):
    from project_opener.quick.facade import AppFacade
    app = AppFacade(isolated_data_dir)
    sm = app.spacemap
    sm.scan()
    assert _pump(lambda: sm.state == "error")
    assert sm.error.startswith("No Team Hub folder set")
    app.deleteLater()
