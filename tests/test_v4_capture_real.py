"""Opt-in end-to-end capture and restore on the real desktop (set PO_REAL_CAPTURE=1).

Opens ONLY its own test files from ``PO_REAL_CAPTURE_DIR`` (default
``U:\\Vikram\\_Claude_Work\\temp\\b2\\real``): a folder, an .xlsx, a .docx (Office through COM)
and a PDF (association).  Arranges those windows, captures through the real CaptureEngine
(its own COM thread), closes ONLY those windows (by identity; Office documents through their
own window object; the PDF viewer only when this test started its process), restores through
the engine, checks each window came back at its saved place, then closes what it restored.
It never moves, closes or ends anything that existed before it started.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("PO_REAL_CAPTURE") != "1",
                                reason="real desktop test: set PO_REAL_CAPTURE=1")

WORK = Path(os.environ.get("PO_REAL_CAPTURE_DIR", r"U:\Vikram\_Claude_Work\temp\b2\real"))
SPIKE = Path(r"U:\Vikram\_Claude_Work\temp\po-spike")


def _norm(p: str) -> str:
    return (p or "").strip().rstrip("\\/").lower()


def _make_files() -> dict[str, Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    folder = WORK / "Lot 7 isos"
    folder.mkdir(exist_ok=True)
    (folder / "readme.txt").write_text("capture test folder\n", encoding="utf-8")
    files = {"folder": folder, "xlsx": WORK / "PO4 line list.xlsx", "docx": WORK / "PO4 check notes.docx",
             "pdf": WORK / "PO4 iso P12513-001.pdf"}
    sources = {"xlsx": SPIKE / "PO-spike line list.xlsx", "docx": SPIKE / "PO-spike check notes.docx",
               "pdf": SPIKE / "PO-spike iso P12513-001.pdf"}
    for k, src in sources.items():
        if not files[k].exists():
            if not src.exists():
                pytest.skip(f"test source file missing: {src}")
            shutil.copyfile(src, files[k])
    return files


def _tiles(monitors):
    primary = next(m for m in monitors if m.primary)
    other = next((m for m in monitors if not m.primary), primary)

    def tile(m, col, row):
        left, top, right, bottom = m.work
        w, h = (right - left) // 2, (bottom - top) // 2
        x, y = left + col * w + 20, top + row * h + 20
        return [x, y, x + w - 40, y + h - 40]
    return {"folder": (1, tile(primary, 0, 0)), "xlsx": (1, tile(other, 0, 0)), "docx": (1, tile(other, 1, 0)),
            "pdf": (3, tile(other, 0, 1))}


def _close_mine(entries, my_pids_after_start: set[int]):
    """Close exactly these windows: Explorer by its hwnd, Office documents through their own window object
    (quitting the instance only when it is empty and was started during this test), the PDF viewer by
    WM_CLOSE (ending its process only when this test started it)."""
    import psutil
    import win32com.client
    import win32con
    import win32gui

    from project_opener.capture import win32
    from project_opener.capture.sources import office
    for e in entries:
        proc = e.process.lower()
        try:
            if e.kind == "folder":
                for w in win32com.client.Dispatch("Shell.Application").Windows():
                    try:
                        if int(w.HWND) == e.hwnd:
                            w.Quit()
                    except Exception:  # noqa: BLE001
                        pass
            elif proc in ("excel.exe", "winword.exe"):
                child = win32.find_child(e.hwnd, "EXCEL7" if proc == "excel.exe" else "_WwG")
                win = office.native_om(child) if child else None
                if win is not None:
                    app = win.Application
                    doc = win.Parent if proc == "excel.exe" else win.Document
                    doc.Close(False)
                    del doc, win
                    coll = app.Workbooks if proc == "excel.exe" else app.Documents
                    if coll.Count == 0 and e.pid in my_pids_after_start:
                        app.Quit()
                    del coll, app
            elif e.pid in my_pids_after_start:
                win32gui.PostMessage(e.hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception as exc:  # noqa: BLE001
            print("close error", e.process, e.title, repr(exc))
    time.sleep(4)
    for e in entries:
        if e.kind == "file" and e.process.lower() not in ("excel.exe", "winword.exe") and e.pid in my_pids_after_start:
            if psutil.pid_exists(e.pid):
                psutil.Process(e.pid).terminate()


def test_real_capture_close_restore_placement():
    import psutil
    import pythoncom

    from project_opener.capture import win32
    from project_opener.capture.engine import CaptureEngine, EngineCallbacks, EngineConfig
    from project_opener.capture.identify import Identifier
    from project_opener.capture.sources import explorer, office
    from project_opener.core import models as M
    from project_opener.core.launcher import Launcher
    from project_opener.core.pathvars import PathResolver
    from project_opener.core.snapshots import SnapshotStore

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    files = _make_files()
    paths = {k: str(v) for k, v in files.items()}
    mine_keys = {_norm(p) for p in paths.values()}
    before_pids = set(psutil.pids())
    if any(w.process.lower() == "pdfxedit.exe" for w in win32.enumerate_windows()):
        pytest.skip("a PDF-XChange window is already open; the test would open its PDF as a tab in it")
    idf = Identifier(recent_fn=lambda: {})
    items = [M.Item(path=paths[k], id=k, kind="folder" if k == "folder" else "file") for k in ("folder", "xlsx",
                                                                                              "docx", "pdf")]
    item_paths = [i.path for i in items]

    def mine_now():
        es = idf.identify(win32.enumerate_windows({os.getpid()}), item_paths, full=True, apply_ignore=False)
        return [e for e in es if e.identified and _norm(e.path) in mine_keys]

    def wait_for(n, timeout=60.0):
        t0 = time.time()
        found = []
        while time.time() - t0 < timeout:
            found = {(_norm(e.path)): e for e in mine_now()}
            if len(found) >= n:
                break
            time.sleep(1.0)
        return list(found.values())

    report: dict = {"steps": []}
    data = WORK / "data"
    store = SnapshotStore(data)
    got: dict = {}
    ev_cp, ev_done = threading.Event(), threading.Event()
    launcher = Launcher(PathResolver({}))
    eng = CaptureEngine(store, EngineCallbacks(on_checkpoint=lambda cp: (got.__setitem__("cp", cp), ev_cp.set()),
                                               on_restore_done=lambda r: (got.__setitem__("done", r), ev_done.set())),
                        EngineConfig(exclude_pids={os.getpid()}, open_item=launcher.open_item))
    eng.start()
    opened: list = []
    restored: list = []
    restore_started = False
    try:
        # 1. open my things
        t0 = time.perf_counter()
        explorer.open_folder(paths["folder"])
        assert office.open_document(paths["xlsx"]), "Excel through COM"
        assert office.open_document(paths["docx"]), "Word through COM"
        os.startfile(paths["pdf"])  # type: ignore[attr-defined]
        opened = wait_for(4, 180)
        report["steps"].append(f"opened {len(opened)}/4 in {time.perf_counter() - t0:.1f} s")
        assert len(opened) == 4, [e.title for e in mine_now()]
        my_pids = {p for p in psutil.pids() if p not in before_pids}
        # 2. arrange my windows
        tiles = _tiles(win32.monitors())
        for e in opened:
            k = next(k for k, p in paths.items() if _norm(p) == _norm(e.path))
            show, rect = tiles[k]
            win32.apply_placement(e.hwnd, M.WindowPlacement(show, rect))
        time.sleep(1.5)
        # 3. capture through the engine (a checkpoint)
        eng.run_activity("real-test", items)
        eng.request_snapshot("manual", "real test")
        assert ev_cp.wait(30), "checkpoint"
        snap = got["cp"].snapshot
        saved = {(_norm(e.path)): e for e in snap.entries if e.identified and _norm(e.path) in mine_keys}
        report["captured"] = {k: {"by": e.identified_by, "show": e.placement.show_cmd,
                                  "rect": e.placement.normal_rect, "monitor": e.placement.monitor}
                              for k, e in saved.items()}
        assert len(saved) == 4, list(saved)
        # 4. close only mine
        _close_mine(opened, my_pids)
        left = mine_now()
        report["steps"].append(f"after close, still open: {[e.title for e in left]}")
        assert not left
        # 5. restore through the engine
        restore_snap = M.Snapshot("real-test", monitors=snap.monitors, entries=list(saved.values()))
        t1 = time.perf_counter()
        eng.request_restore(restore_snap, items)
        restore_started = True
        assert ev_done.wait(300), "restore"
        report["restore"] = got["done"]
        report["steps"].append(f"restore took {time.perf_counter() - t1:.1f} s")
        time.sleep(2)
        restored = wait_for(4, 60)
        # 6. compare
        compare = {}
        for e in restored:
            want = saved[_norm(e.path)].placement
            got_pl = e.placement
            same = (got_pl.show_cmd == want.show_cmd and got_pl.monitor == want.monitor
                    and all(abs(a - b) <= 2 for a, b in zip(got_pl.normal_rect, want.normal_rect, strict=False)))
            compare[_norm(e.path)] = {"same": same, "before": [want.show_cmd, want.normal_rect, want.monitor],
                                      "after": [got_pl.show_cmd, got_pl.normal_rect, got_pl.monitor]}
        report["compare"] = compare
        assert len(restored) == 4 and all(v["same"] for v in compare.values()), compare
    finally:
        if restore_started:
            ev_done.wait(300)            # never clean up while the restore may still open things
        try:
            if opened or restored:
                # whatever of my own test files is still open (the restored windows, or the originals on failure)
                _close_mine(mine_now(), {p for p in psutil.pids() if p not in before_pids})
        finally:
            eng.stop(30)
            (WORK / "real_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            pythoncom.CoUninitialize()
