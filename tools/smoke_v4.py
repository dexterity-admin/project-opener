r"""Smoke test and screenshots of the Qt Quick (4.0) shell: what CI runs for v4.  (tools/smoke_ui.py is the
3.2 widgets UI's, which stays reachable with ``--classic`` until 4.0 ships.)

Seeds a demo workspace through the v4 store and the hub, loads ``qml/Main.qml`` with the real facade, visits
every route (each Team Hub tab, the sheets, the palette, the dock) in both themes at both sizes, then the long
pages at full height, and fails on any Qt or QML warning or on a page whose minimum width does not fit the
1040 x 660 window (or whose rows pass the page's right edge).

    python tools/smoke_v4.py --out build/screens-v4      (every page, sheet, palette and dock; what CI runs)
    python tools/smoke_v4.py --check                     (no screenshots: what the pytest smoke runs)
    python tools/smoke_v4.py --empty                     (live models as the app fills them: the empty states)
    python tools/smoke_v4.py --first-run                 (a true empty workspace: no projects, no hub)

Passes (all on by default; the pytest smoke splits them across tests):

* the routes at ``--sizes`` (1400x860, 1040x660): ``home``, ``activity`` (Lot 7, waiting to be resumed),
  ``activity-running`` (the activity that runs now), ``activities``, ``projects``, ``project``,
  ``hub-<tab>`` for every Team Hub tab, ``updates``, ``settings``; then the sheets, the palette, the dock and
  a toast at each size.
* the tall pass at ``--tall-size`` (1400x3400; "" turns it off): Settings (each tab when the page has tabs),
  Home, both activity pages, Updates and every hub tab at full height.  The layout checks apply.
* ``--first-run``: a fresh data folder with no projects, activities, hub or running markers; every route.

The demo story is one coherent set of facts, seeded as real objects so the app's own code computes the
numbers (``STORY`` holds the times): Lot 7 check ran until the power cut (last checkpoint at 14:32, six
things, all identified, four ticked to reopen) and waits to be resumed; nas01 has been down since 14:40,
seen by 3 PCs; after the restart Mangala GAD review runs now (its files are on Z:, so they show offline).
The Revision C watcher on Lot 7 fired "2 new sheets in Revision C" at 10:41; two open tasks hang on Lot 7.
The offscreen platform gets two 1920 x 1080 screens, as the windows in the snapshots were seen on two.
``--empty`` keeps the stored objects but leaves the live models as the app fills them.  The launcher runs in
dry-run mode: nothing is opened, and the dock's open never starts capture on this PC's windows.

Public captures show office-shaped paths, as tools/smoke_ui.py does for 3.2 (the repository is public):
``PO_DEMO_ROOT`` (e.g. D:\Projects\P12513; its parent holds the other demo jobs), ``PO_DEMO_HUB`` (the
demo hub folder, rebuilt on every run) and ``PO_DEMO_SERVER_ROOT`` (the {SERVER_ROOT} variable; unset, it
stays undefined so the drive map shows that state).  This PC's real drive mappings are replaced by a demo
map (Z: -> \\nas01\Project, W: -> \\nas01\Submissions); ``PO_DEMO_DRIVES=0`` turns that off.  Demo folders
named by the environment are only added to, never emptied.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen") and sys.platform == "win32":
    fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    if fonts.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))

# Offscreen frames are slow software renders; a frame-stepped animation driver would then run the dock's
# 1.3 s at a fraction of real time.  The simple driver steps by the wall clock, as on a real screen.
os.environ.setdefault("QSG_USE_SIMPLE_ANIMATION_DRIVER", "1")

WORK = Path(os.environ.get("PO_SMOKE_ROOT", r"U:\Vikram\_Claude_Work\temp\b4"))
SIZES = ((1400, 860), (1040, 660))
HUB_TABS = ("published", "inbox", "tasks", "announcements", "activity", "groups")
ROUTES = ("home", "activity", "activity-running", "activities", "projects", "project",
          *(f"hub-{t}" for t in HUB_TABS), "updates", "settings")
TALL_ROUTES = ("settings", "home", "activity", "activity-running", "updates", *(f"hub-{t}" for t in HUB_TABS))
FIRST_RUN_ROUTES = ("home", "activity", "activities", "projects", "project", "hub", "updates", "settings")
MESSAGES: list[str] = []
STEP = ["start"]                       # what the run was doing when a warning came (printed with it)
# Messages that are not about our QML (the offscreen platform's own notes).
BENIGN = ("propagateSizeHints", "QFont::setPointSize", "Populating font family aliases",
          "OpenType support missing", "This plugin does not support")

# One story, one set of times (local, today).  Everything that prints a time reads it from here.
STORY = {
    "lot7_opened": "09:12",            # Lot 7 check opened (its session start)
    "cp_early": "11:20",               # Lot 7 checkpoints kept by the watcher
    "cp_mid": "13:05",
    "rev_c_hit": "10:41",              # the Revision C watcher: 2 new sheets
    "iso_1043_seen": "10:45",          # one of them opened in PDF-XChange
    "resume": "14:32",                 # Lot 7's last checkpoint before the power cut
    "drive_down": "14:40",             # nas01 down (the power cut), seen by 3 PCs
    "gad_started": "15:05",            # after the restart: Mangala GAD review runs
    "gad_cp": "15:20",
    "gad_live": "15:24",
}
# Two monitors side by side (the offscreen platform is given the same two; see offscreen_screens()).
SCREENS = ((r"\\.\DISPLAY1", 0, 0, 1920, 1080), (r"\\.\DISPLAY2", 1920, 0, 1920, 1080))


def today_at(hhmm: str) -> str:
    """Today at ``hhmm`` local time, as the ISO stamps the stores write."""
    h, m = (int(v) for v in hhmm.split(":"))
    return datetime.now().astimezone().replace(hour=h, minute=m, second=0, microsecond=0).isoformat(
        timespec="seconds")


def offscreen_screens(work: Path) -> None:
    """Give the offscreen platform the demo's two screens (Qt's ``configfile`` option), so the Monitors panel
    and the "monitor 1" / "monitor 2" of the snapshots agree.  Qt splits platform options at ':', so the path
    is passed relative to the working folder (no drive letter)."""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    work.mkdir(parents=True, exist_ok=True)
    cfg = work / "offscreen-screens.json"
    with open(cfg, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"screens": [{"name": n, "x": x, "y": y, "width": w, "height": h, "logicalDpi": 96,
                                "logicalBpp": 32, "dpr": 1} for n, x, y, w, h in SCREENS]}, fh, indent=1)
    if os.path.splitdrive(str(cfg))[0].lower() != os.path.splitdrive(os.getcwd())[0].lower():
        os.chdir(cfg.parent)
    rel = os.path.relpath(cfg).replace("\\", "/")
    if ":" not in rel:
        os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={rel}"


# ------------------------------------------------------------------- seed
def _place(mon: int, x: int, y: int, w: int, h: int, maxed: bool = False) -> Any:
    from project_opener.core import models as M
    name, mx, my, mw, mh = SCREENS[mon - 1]
    r = [mx, my, mx + mw, my + mh] if maxed else [mx + x, my + y, mx + x + w, my + y + h]
    return M.WindowPlacement(show_cmd=3 if maxed else 1, normal_rect=list(r), window_rect=list(r), monitor=name,
                             monitor_rect=[mx, my, mx + mw, my + mh])


def _entry(path: str = "", app: str = "", process: str = "", *, status: str = "identified", kind: str = "file",
           title: str = "", doc: str = "", by: str = "title+items", seen: str = "", mon: int = 1,
           rect: tuple[int, int, int, int] = (40, 40, 1400, 900), maxed: bool = False, item_id: str = "",
           note: str = "", candidates: list[str] | None = None, exe: str = "") -> Any:
    from project_opener.core import models as M
    ident = status == "identified" and bool(path)
    if ident:
        key = ("url:" + path) if kind == "url" else ("path:" + path.lower())
    else:
        key = f"win:{process.lower()}|{title}"
    return M.SnapshotEntry(key=key, status=status, kind=kind, path=path if ident else "", title=title,
                           process=process, exe=exe, app=app, identified_by=by if ident else "", doc_name=doc,
                           candidates=list(candidates or []), note=note, item_id=item_id,
                           placement=_place(mon, *rect, maxed=maxed), first_seen=today_at(seen) if seen else "")


def seed(data_dir: Path, hub_dir: Path, demo_dir: Path) -> dict[str, str]:
    """A demo workspace in schema 4 plus a hub; returns ids the run needs."""
    import psutil

    from project_opener.core import models as M
    from project_opener.core.jsonio import write_json_atomic
    from project_opener.core.settings import Settings
    from project_opener.core.snapshots import SnapshotStore
    from project_opener.core.store import WorkspaceStore
    from project_opener.core.tasks import TaskStore
    from project_opener.lan.groups import GroupBook
    from project_opener.lan.hub import TeamHub

    shutil.rmtree(data_dir, ignore_errors=True)        # our own scratch data folder
    shutil.rmtree(hub_dir, ignore_errors=True)         # the demo hub would otherwise accumulate copies
    if not os.environ.get("PO_DEMO_ROOT"):
        shutil.rmtree(demo_dir, ignore_errors=True)    # the default scratch demo folder only
    for d in (data_dir, hub_dir, demo_dir):
        d.mkdir(parents=True, exist_ok=True)
    (demo_dir / "P12513" / "Lot 7").mkdir(parents=True, exist_ok=True)
    (demo_dir / "ANTEO").mkdir(parents=True, exist_ok=True)
    files = {
        "check": demo_dir / "P12513" / "Iso checklist.pdf", "lines": demo_dir / "P12513" / "Line list.xlsx",
        "register": demo_dir / "P12513" / "Lot 7" / "Comment register.xlsx",
        "iso": demo_dir / "P12513" / "P12513-ISO-1042-C.pdf", "anteo": demo_dir / "ANTEO" / "Line list.xlsx",
        "clash": demo_dir / "Clash register.xlsx", "gad_comments": demo_dir / "DM-GAD" / "GAD comments.xlsx",
    }
    files["gad_comments"].parent.mkdir(parents=True, exist_ok=True)
    for f in files.values():
        if not f.exists():
            f.write_bytes(b"demo")
    me = M.current_user()
    rev_c = r"\\nas01\Project\P12513\ISO\Revision C"

    s = Settings.load(data_dir)
    s.display_name, s.role, s.hub_path = "Vikram", "Piping QA", str(hub_dir)
    s.presence_udp = False
    s.update_check = False
    s.capture_enabled = False            # the smoke never starts a capture thread on this PC's windows
    s.confirm_launch_over = 8
    s.variables = {"{SERVER_ROOT}": os.environ["PO_DEMO_SERVER_ROOT"]} if os.environ.get("PO_DEMO_SERVER_ROOT") else {}
    s.save()

    store = WorkspaceStore(data_dir)
    p1 = M.Project(name="As-built isometrics", client="FST", job_number="P12513", color="#2F5BFF",
                   icon="ph.compass", tags=["as-built", "FST", "isometrics"],
                   description="RLM red-line cross-check", pinned_at=M.now_iso(), favorite=True,
                   items=[
                       M.Item(path=str(files["check"]), kind="file", group="Checking"),
                       M.Item(path=str(files["lines"]), kind="file", group="Checking"),
                       M.Item(path=str(files["register"]), kind="file", group="Checking"),
                       M.Item(path=str(demo_dir / "P12513"), kind="folder", group="Folders", label="Working folder"),
                       M.Item(path=rev_c, kind="folder", group="Folders", label="Revision C"),
                       M.Item(path=r"{SERVER_ROOT}\P12513\Rulings.docx", kind="file", group="References"),
                       M.Item(path=str(files["iso"]), kind="file", group="Isos"),
                   ])
    p2 = M.Project(name="ANTEO Isometrics", client="ANTEO", color="#10B981", icon="ph.anchor",
                   tags=["isometrics", "handover"],
                   items=[M.Item(path=str(files["anteo"]), group="Checking"),
                          M.Item(path="https://teams.microsoft.com", kind="url", group="Links")])
    gad_dir = r"Z:\Project\Mangala\GAD"
    p3 = M.Project(name="Mangala Piping GAD", client="Cairn", job_number="DM-GAD", color="#F97316",
                   icon="ph.factory", tags=["GAD", "piping"],
                   items=[M.Item(path=gad_dir, kind="folder", label="GAD"),
                          M.Item(path=gad_dir + r"\GAD-0120-B.pdf", kind="file")])
    p4 = M.Project(name="Navisworks clash review", job_number="P14414", color="#8B5CF6", icon="ph.cube",
                   tags=["3D", "review"],
                   items=[M.Item(path=r"C:\Program Files\Autodesk\Navisworks Manage 2025\Roamer.exe", kind="app",
                                 label="Navisworks"),
                          M.Item(path=str(files["clash"]), group="Review")])
    p5 = M.Project(name="Office tools", color="#14B8A6", icon="ph.wrench", tags=["tools"],
                   items=[M.Item(path="https://outlook.office.com", kind="url"),
                          M.Item(path="cmd: ipconfig", kind="command")])
    for p in (p1, p2, p3, p4, p5):
        store.add(p)
    store.activities.clear()

    def from_proj(p: M.Project, idx: list[int]) -> list[M.ActivityItem]:
        out = []
        for i in idx:
            it = M.ActivityItem.from_item(p.items[i], p.id, p.items[i].id)
            it.id = M.new_id()
            out.append(it)
        return out

    lot7 = M.Activity(name="Lot 7 check", short_name="Lot 7 check", icon="ph.checks", project_ids=[p1.id],
                      items=from_proj(p1, [0, 1, 2, 3, 4, 5, 6]) + from_proj(p2, [0]),
                      description="Back-check of lot 7 against the RLM mark-ups", pinned_at=M.now_iso())
    lot7.open_count, lot7.last_opened = 14, today_at(STORY["lot7_opened"])
    gad = M.Activity(name="Mangala GAD review", project_ids=[p3.id], items=from_proj(p3, [0, 1]))
    gad.open_count, gad.last_opened = 3, today_at(STORY["gad_started"])
    clash = M.Activity(name="Tuesday clash meeting", project_ids=[p4.id], items=from_proj(p4, [0, 1]))
    anteo = M.Activity(name="ANTEO handover", project_ids=[p2.id], items=from_proj(p2, [0, 1]))
    for a in (lot7, gad, clash, anteo):
        store.add_activity(a)

    # ---- Lot 7: what was open at each checkpoint; the last one (14:32) is what Resume offers
    snaps = SnapshotStore(data_dir)
    opened = STORY["lot7_opened"]
    l7 = {
        "check": _entry(str(files["check"]), "PDF-XChange", "PDFXEdit.exe", title="Iso checklist.pdf - PDF-XChange Editor",
                        seen=opened, mon=1, rect=(0, 0, 960, 1040), item_id=lot7.items[0].id),
        "lines": _entry(str(files["lines"]), "Excel", "EXCEL.EXE", title="Line list.xlsx - Excel", by="office-com",
                        seen=opened, mon=1, rect=(960, 0, 960, 1040), item_id=lot7.items[1].id),
        "register": _entry(str(files["register"]), "Excel", "EXCEL.EXE", title="Comment register.xlsx - Excel",
                           by="office-com", seen=opened, mon=2, maxed=True, item_id=lot7.items[2].id),
        "iso1043": _entry(rev_c + r"\P12513-ISO-1043-C.pdf", "PDF-XChange", "PDFXEdit.exe",
                          title="P12513-ISO-1043-C.pdf - PDF-XChange Editor", seen=STORY["iso_1043_seen"], mon=2,
                          rect=(120, 80, 1500, 900)),
        "timesheet": _entry(r"D:\Users\checker\Documents\Timesheet Nov.xlsx", "Excel", "EXCEL.EXE",
                            title="Timesheet Nov.xlsx - Excel", by="office-com", seen=opened, mon=1,
                            rect=(200, 120, 1200, 760)),
        "clash": _entry(str(files["clash"]), "Excel", "EXCEL.EXE", title="Clash register.xlsx - Excel",
                        by="office-com", seen=opened, mon=2, rect=(300, 200, 1200, 760)),
    }
    for when, keys, kind in (
            (STORY["cp_early"], ("check", "lines", "register", "timesheet"), "auto"),
            (STORY["cp_mid"], ("check", "lines", "register", "iso1043", "timesheet"), "auto"),
            (STORY["resume"], ("check", "lines", "register", "iso1043", "timesheet", "clash"), "auto")):
        snap = M.Snapshot(activity_id=lot7.id, taken_at=today_at(when), session_start=today_at(opened),
                          monitors=[M.Monitor(device=n, rect=[x, y, x + w, y + h], work=[x, y, x + w, y + h - 40],
                                              primary=i == 0) for i, (n, x, y, w, h) in enumerate(SCREENS)],
                          entries=[M.SnapshotEntry.from_dict(l7[k].to_dict()) for k in keys])
        snaps.add_checkpoint(M.Checkpoint(activity_id=lot7.id, snapshot=snap, kind=kind, taken_at=today_at(when)))
    # the PC went down while it ran: a marker from a process that is gone
    snaps.mark_running(M.RunningMarker(activity_id=lot7.id, pid=999_999, started_at=today_at(opened),
                                       last_seen=today_at(STORY["resume"])))

    # ---- Mangala GAD review: running now (this process's marker), its live snapshot and one checkpoint
    started = STORY["gad_started"]
    g = {
        "pdf": _entry(gad_dir + r"\GAD-0120-B.pdf", "PDF-XChange", "PDFXEdit.exe", title="GAD-0120-B.pdf - PDF-XChange Editor",
                      seen=started, mon=1, rect=(0, 0, 1100, 1040), item_id=gad.items[1].id),
        "folder": _entry(gad_dir, "Explorer", "explorer.exe", kind="folder", title="GAD", by="shell", seen=started,
                         mon=1, rect=(1100, 0, 820, 600), item_id=gad.items[0].id),
        "ambiguous": _entry("", "PDF-XChange", "PDFXEdit.exe", status="ambiguous", kind="file",
                            title="GAD-0121-B.pdf - PDF-XChange Editor", doc="GAD-0121-B.pdf", seen="15:12", mon=2,
                            rect=(0, 0, 1100, 1040), note="two files with this name in the activity's folders",
                            candidates=[gad_dir + r"\GAD-0121-B.pdf", gad_dir + r"\Superseded\GAD-0121-B.pdf"]),
        "comments": _entry(str(files["gad_comments"]), "Excel", "EXCEL.EXE",
                           title="GAD comments.xlsx - Excel", by="office-com", seen="15:14", mon=2,
                           rect=(1100, 0, 820, 1040)),
        "drawing1": _entry("", "AutoCAD", "acad.exe", status="unsaved", kind="", title="Drawing1 - AutoCAD",
                           doc="Drawing1.dwg", seen=started, mon=2, maxed=True, note="unsaved - cannot be restored",
                           exe=r"C:\Program Files\Autodesk\AutoCAD 2025\acad.exe"),
        "dgn": _entry("", "MicroStation", "ustation.exe", status="unidentified", kind="",
                      title="PIPE-GAD-0120.dgn - MicroStation", doc="PIPE-GAD-0120.dgn", seen=started, mon=1,
                      rect=(160, 90, 1500, 900), note="MicroStation gave no file path",
                      exe=r"C:\Program Files\Bentley\MicroStation\ustation.exe"),
        "outlook": _entry("", "Outlook", "OUTLOOK.EXE", status="unidentified", kind="", title="Inbox - Outlook",
                          seen=started, mon=2, rect=(300, 120, 1300, 860),
                          exe=r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE"),
        "portal": _entry("https://portal.cairn.example/DM-GAD", "Edge", "msedge.exe", kind="url",
                         title="Cairn portal · DM-GAD - Microsoft Edge", doc="Cairn portal · DM-GAD", by="uia",
                         seen="15:16", mon=1, rect=(240, 60, 1400, 950), note="active tab only"),
    }
    gad_mons = [M.Monitor(device=n, rect=[x, y, x + w, y + h], work=[x, y, x + w, y + h - 40], primary=i == 0)
                for i, (n, x, y, w, h) in enumerate(SCREENS)]
    cp = M.Snapshot(activity_id=gad.id, taken_at=today_at(STORY["gad_cp"]), session_start=today_at(started),
                    monitors=gad_mons, entries=[M.SnapshotEntry.from_dict(g[k].to_dict())
                                                for k in ("pdf", "folder", "drawing1", "dgn", "outlook")])
    snaps.add_checkpoint(M.Checkpoint(activity_id=gad.id, snapshot=cp, kind="auto", taken_at=today_at(STORY["gad_cp"])))
    snaps.save_live(M.Snapshot(activity_id=gad.id, taken_at=today_at(STORY["gad_live"]), session_start=today_at(started),
                               monitors=gad_mons, entries=[M.SnapshotEntry.from_dict(e.to_dict()) for e in g.values()]))
    try:
        proc_started = float(psutil.Process().create_time())
    except Exception:  # noqa: BLE001
        proc_started = 0.0
    snaps.mark_running(M.RunningMarker(activity_id=gad.id, pid=os.getpid(), process_started=proc_started,
                                       started_at=today_at(started), last_seen=today_at(STORY["gad_live"])))
    snaps.close()

    # ---- watchers on Lot 7 (their hits are alerts; see seed_alerts)
    w_rev = M.Watcher(name="Revision C sheets", kind="folder", target=rev_c, events=["new", "changed"],
                      notify=M.Notify(toast=True, cliq_dm=True), activity_id=lot7.id)
    w_nas = M.Watcher(name="nas01 health", kind="health", target=r"\\nas01", events=["down", "up"],
                      notify=M.Notify(toast=True, cliq_dm=True), activity_id=lot7.id)
    store.save_watcher(w_rev)
    store.save_watcher(w_nas)

    # ---- the hub: people, a group starting with "pr" (the @ picker), publishes, a mention, tasks, health
    hub = TeamHub(hub_dir, user="yokesh", display_name="Yokesh", role="Designer")
    hub.initialise()
    hub.heartbeat(current_project="ANTEO Isometrics")
    hub.publish(M.Project.from_dict(p2.to_dict()), description="Standard ANTEO checking bundle")
    hub.announce("Z: drive moves on Friday", "The Project share moves to the new NAS at 18:00.", "warning")
    hub2 = TeamHub(hub_dir, user="priya", display_name="Priya", role="Checker")
    hub2.heartbeat(current_project="DM-GAD · Mangala GAD review")
    hub2.send(me, p3, "Have a look at the Mangala bundle before the review.")
    hub2.send_mention([me], f"@{me} Revision C has two new sheets for lot 7.", title="P12513 · Lot 7 check")
    hub3 = TeamHub(hub_dir, user="ravi", display_name="Ravi", role="Designer")
    hub3.heartbeat(current_project="Navisworks clash review")
    hub4 = TeamHub(hub_dir, user="prakash", display_name="Prakash", role="Procurement")
    hub4.heartbeat()
    hub4.sign_off()                                    # away: the picker lists him after those online
    mine = TeamHub(hub_dir, user=me, display_name="Vikram", role="Piping QA")
    mine.publish_activity(M.Activity.from_dict(lot7.to_dict()), description=(
        "Lot 7 back-check set. Watch Revision C for the modeller's sheets."), for_targets=["checkers"],
        projects=[M.Project.from_dict(p1.to_dict()), M.Project.from_dict(p2.to_dict())])
    # A run takes minutes and the hub calls a heartbeat older than HUB_STALE_S offline: the colleagues' heartbeats
    # (and their health observations below) are dated an hour ahead, so they stay online for the whole run.
    ahead = time.time() + 3600
    for login in ("yokesh", "priya", "ravi"):
        f = hub_dir / "users" / f"{login}.json"
        with open(f, encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["ts"] = ahead
        write_json_atomic(f, rec)
    book = GroupBook(hub_dir)
    for name, members in (("checkers", ["priya", me]), ("P12513-team", ["priya", "ravi", "yokesh", me]),
                          ("procurement", ["prakash", "ravi"])):
        book.save(M.Group(name=name, members=members), by="priya")

    tasks = TaskStore(hub_dir / "tasks")
    today = datetime.now().astimezone().date()
    friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    monday = today + timedelta(days=(0 - today.weekday()) % 7 or 7)
    lot7_link = M.TaskLink(kind="activity", local_id=lot7.id, title="P12513 · Lot 7 check", job_number="P12513")
    for t in (
            M.Task("Send rev C sheets to FST", owner=me, due=today.isoformat(), created_by="yokesh", link=lot7_link),
            M.Task("Back-check lot 7", owner=me, due=friday.isoformat(), created_by="yokesh",
                   link=M.TaskLink(**lot7_link.to_dict())),
            M.Task("GAD comments to Cairn", owner=me, due=monday.isoformat(), created_by="priya",
                   link=M.TaskLink(kind="activity", local_id=gad.id, title="DM-GAD · Mangala GAD review",
                                   job_number="DM-GAD")),
            M.Task("Update line list after clash", owner="priya", created_by=me,
                   link=M.TaskLink(kind="project", local_id=p4.id, title="Navisworks clash review",
                                   job_number="P14414"))):
        if t.owner == "priya":
            t.mark_done("priya")
        tasks.save(t)

    # office-wide health: two colleagues see nas01 down since the power cut (this PC is the third)
    down = today_at(STORY["drive_down"])
    for login, host, jobs in (
            ("yokesh", "PC-YOKESH", ["P12513", "P13020", "P13105", "P14002", "ANTEO-2", "P12877", "P13311"]),
            ("priya", "PC-PRIYA", ["DM-GAD", "P12513", "P11870", "P12990", "P13562", "P14120", "P14415", "P14414"])):
        write_json_atomic(hub_dir / "watch" / f"{login}.json", M.HealthObservation(
            user=login, host=host, ts=datetime.fromtimestamp(ahead).astimezone().isoformat(timespec="seconds"),
            roots=[M.RootObservation(r"\\nas01", "offline", down, jobs, 23)]).to_dict())
    return {"lot7": lot7.id, "p1": p1.id, "gad": gad.id, "running": gad.id, "w_rev": w_rev.id, "w_nas": w_nas.id,
            "rev_c": rev_c}


def seed_alerts(app: Any, ids: dict[str, str]) -> None:
    """The two watcher hits, written where the dispatcher keeps alerts (read back by the app at start)."""
    from project_opener.core import models as M
    from project_opener.core.jsonio import append_jsonl
    path = app.watchers.dispatcher().alerts_path
    for ev in (
            M.WatchEvent(ids["w_rev"], "new", "2 new sheets in Revision C", "P12513-ISO-1043-C.pdf, P12513-ISO-1044-C.pdf",
                         path=ids["rev_c"], level="info", ts=today_at(STORY["rev_c_hit"])),
            M.WatchEvent(ids["w_nas"], "down", r"\\nas01 is down", "Z: and W: are not reachable from this PC",
                         path=r"\\nas01", level="warning", ts=today_at(STORY["drive_down"]))):
        append_jsonl(path, {**ev.to_dict(), "read": False})
    # this PC first saw nas01 down at the same time (watch/<me>.json keeps it)
    app.watchers._root_since = {r"\\nas01": ("offline", today_at(STORY["drive_down"])),
                                "{SERVER_ROOT}": ("variable", today_at(STORY["lot7_opened"]))}


def seed_first_run(data_dir: Path) -> None:
    """A true empty workspace: a fresh data folder, no projects, activities, hub or running markers."""
    from project_opener.core.settings import Settings
    shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    s = Settings.load(data_dir)
    s.presence_udp = False
    s.update_check = False
    s.capture_enabled = False
    s.hub_path = ""
    s.save()


# ------------------------------------------------------- demo of the stubs
def demo_fill(app: Any, ids: dict[str, str]) -> None:
    """The running activity (Mangala GAD review) from its stored live snapshot, worked by the capture API's own
    code (counts, statuses, monitors, "Save N new" and the Resume sheet for Lot 7); hub rows only where the
    hub left a model empty."""
    from project_opener.capture import windows as W
    from project_opener.ui import text as T

    cap, hub = app.capture, app.hub
    store = app.ctx.store

    def fill(model: Any, rows: list[dict[str, Any]]) -> bool:
        if model.rowCount() == 0:
            model.reset([{r: row.get(r, "") for r in model.roles} for row in rows])
            return True
        return False

    # capture is on (in memory only: the engine never runs an activity in the smoke, so no window is read)
    app.ctx.settings.capture_enabled = True
    gad = store.activity(ids["running"])
    cap._set_running(gad)
    cap._ignored, cap._left_out = app.snapshots.review(gad.id)
    cap._snapshot = app.snapshots.live(gad.id)
    cap._hook_watchers()
    cap._refresh_live()
    cap._refresh_checkpoints()
    cap.prepareSaveNew()
    cap.prepareResume(ids["lot7"])
    snap = cap._snapshot
    cap._candidates.reset([{"entryKey": e.key, "ticked": W.default_ticked(e), "name": W.entry_name(e),
                            "path": e.path, "appName": e.app, "status": W.display_status(e), "kind": e.kind,
                            "note": e.note} for e in (snap.entries if snap else [])])
    DEMO["live_snapshot"] = snap

    people = [("yokesh", "Yokesh", "Designer", True, "in ANTEO Isometrics", "#8A5A00"),
              ("priya", "Priya", "Checker", True, "in DM-GAD · Mangala GAD review", "#4F46A3"),
              ("ravi", "Ravi", "Designer", True, "in Navisworks clash review", "#B4452E"),
              ("prakash", "Prakash", "Procurement", False, "away", "#0F766E")]
    if fill(hub.peers, [{"login": lg, "displayName": dn, "role": r, "host": "PC-" + lg.upper(), "online": on,
                         "doing": d, "initials": T.initials(dn), "hue": h, "cliqLinked": lg != "prakash"}
                        for lg, dn, r, on, d, h in people]):
        hub.peersChanged.emit()
    fill(hub.register, [
        {"job": "P12513 · Lot 7 check", "event": "published for @checkers", "revision": "1", "by": "Vikram",
         "whenText": STORY["resume"]},
        {"job": "P12513 · Lot 7 check", "event": "watcher hit · 2 new sheets in Revision C", "revision": "",
         "by": "this PC", "whenText": STORY["rev_c_hit"]},
        {"job": "P12513 · Lot 7 check", "event": "task created · Send rev C sheets to FST", "revision": "",
         "by": "Yokesh", "whenText": "09:50"},
        {"job": "ANTEO Isometrics", "event": "published", "revision": "1", "by": "Yokesh", "whenText": "08:30"},
    ])
    app.activities.refresh()


def wait_for(app: Any, what: str, cond: Any, seconds: float) -> bool:
    """Pump until ``cond()`` holds (the app's loads run on its pool); say so when it never does."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if cond():
                return True
        except Exception:  # noqa: BLE001
            pass
        pump(app, 100)
    print(f"[seed] {what}: not ready after {seconds:.0f} s")
    return False


def fast_offline_shares() -> None:
    """The demo's nas01 and fileserver shares do not exist; Windows takes 20 s or more to say so for a
    UNC path.  The smoke answers "offline" for them at once (health and the dry-run launcher)."""
    import os as _os

    from project_opener.core import health as H
    from project_opener.core import launcher as L
    from project_opener.core import winutil

    fake = ("\\\\nas01", "\\\\fileserver", "z:", "w:")

    class _Path:
        def __getattr__(self, name: str) -> Any:
            return getattr(_os.path, name)

        def exists(self, p: Any) -> bool:
            return False if str(p).lower().startswith(fake) else _os.path.exists(p)

        def isdir(self, p: Any) -> bool:
            return False if str(p).lower().startswith(fake) else _os.path.isdir(p)

    class _Os:
        path = _Path()

        def __getattr__(self, name: str) -> Any:
            return getattr(_os, name)

    H.os = _Os()          # type: ignore[assignment]
    L.os = _Os()          # type: ignore[assignment]
    real = winutil.host_reachable
    winutil.host_reachable = lambda host, timeout=0.8: False if host.lower() in ("nas01", "fileserver") else real(host, timeout)


# --------------------------------------------------------------------- run
def _install_handler(verbose: bool) -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def handler(mode: Any, ctx: Any, msg: str) -> None:
        if mode == QtMsgType.QtDebugMsg or any(b in msg for b in BENIGN):
            return
        where = f" ({ctx.file}:{ctx.line})" if ctx is not None and ctx.file else ""
        line = f"[qt] {msg}{where}  <{STEP[0]}>"
        MESSAGES.append(line)
        if verbose:
            print(line, file=sys.stderr, flush=True)

    qInstallMessageHandler(handler)


T0 = time.monotonic()
DEMO: dict[str, Any] = {"job": r"D:\Projects\P12513"}


def _job(rel: str = "") -> str:
    """A path under the demo job folder (PO_DEMO_ROOT or the scratch demo), as the seeded items have it."""
    return str(Path(DEMO["job"]) / rel) if rel else str(DEMO["job"])


def trace(what: str) -> None:
    if os.environ.get("PO_SMOKE_TRACE"):
        print(f"{time.monotonic() - T0:7.1f} s  {what}", flush=True)


def flush_deletes() -> None:
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(app: Any, ms: int) -> None:
    """Run the event loop for ``ms``.  processEvents() never runs deferred deletes (only a real exec()
    does), so they are flushed here: a page the Loader replaced is gone, as it is in the app."""
    from PySide6.QtCore import QCoreApplication, QEvent
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.01)


def overflow(page: Any, limit: float) -> list[str]:
    """Visible items whose right edge passes the page's right edge (a clipped row at the minimum window).
    Items inside a clipping or scrolling ancestor below the page are skipped (they scroll or clip by design)."""
    from PySide6.QtQuick import QQuickItem
    out: list[str] = []

    def walk(item: QQuickItem, clipped: bool) -> None:
        for child in item.childItems():
            if not child.isVisible() or child.opacity() == 0:
                continue
            c = clipped or child.clip()
            if not c and child.width() > 0:
                right = child.mapToItem(page, child.width(), 0).x()
                if right > limit + 1:
                    name = child.objectName() or type(child).__name__
                    txt = child.property("text") if child.property("text") is not None else ""
                    out.append(f"{name} '{str(txt)[:40]}' right edge {right:.0f} > {limit:.0f}")
            walk(child, c)

    walk(page, False)
    return out


def _plain(v: Any) -> Any:
    """A QML ``var`` read from Python (QJSValue or already converted) as Python data."""
    return v.toVariant() if hasattr(v, "toVariant") else v


def settings_tabs(page: Any) -> tuple[str, list[str]]:
    """(the property that holds the current tab, the tab keys) when the Settings page shows one area at a time;
    ("", []) while it is one long page."""
    if page is None:
        return "", []
    for name in ("tab", "currentTab", "section", "currentSection", "area"):
        if isinstance(page.property(name), str):
            for list_name in ("tabs", "sections", "areas"):
                rows = _plain(page.property(list_name))
                if isinstance(rows, list) and rows:
                    keys = [str(r.get("key", "")) for r in rows if isinstance(r, dict) and r.get("key")]
                    if keys:
                        return name, keys
    return "", []


def route_target(route: str, ids: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """A smoke route ("hub-inbox", "activity-running", "settings-hub") as (the app's route, its payload)."""
    if route.startswith("hub-"):
        return "hub", {"tab": route[4:]}
    if route == "activity":
        return "activity", {"activityId": ids.get("lot7", "")}
    if route == "activity-running":
        return "activity", {"activityId": ids.get("running", "")}
    if route == "project":
        return "project", {"projectId": ids.get("p1", "")}
    if route.startswith("settings-"):
        key = route[len("settings-"):]
        return "settings", {"tab": key, "section": key}
    return route, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WORK / "shots"))
    ap.add_argument("--check", action="store_true", help="no screenshots: load every page, fail on warnings")
    ap.add_argument("--empty", "--stubs", dest="stubs", action="store_true",
                    help="leave the live models as the app fills them (the empty states)")
    ap.add_argument("--first-run", action="store_true",
                    help="a true empty workspace: no projects, activities, hub or markers; every route")
    ap.add_argument("--themes", default="dark,light")
    ap.add_argument("--sizes", default="1400x860,1040x660", help='"" skips the routes at the normal sizes')
    ap.add_argument("--routes", default="")
    ap.add_argument("--tall-size", default="1400x3400", help='the full-height pass; "" turns it off')
    ap.add_argument("--tall-routes", default=",".join(TALL_ROUTES))
    ap.add_argument("--sheets", action="store_true", default=True)
    ap.add_argument("--no-sheets", dest="sheets", action="store_false")
    ap.add_argument("--work", default=str(WORK))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    work = Path(args.work).absolute()          # absolute, not resolved: U: stays U: (not its UNC path)
    out = Path(args.out).absolute()
    data_dir, hub_dir, demo_dir = work / "smoke-data", work / "smoke-hub", work / "demo"
    if args.first_run:
        data_dir = work / "smoke-first-run"
    if os.environ.get("PO_DEMO_ROOT"):
        demo_dir = Path(os.environ["PO_DEMO_ROOT"]).parent       # D:\Projects\P12513 -> D:\Projects
    if os.environ.get("PO_DEMO_HUB"):
        hub_dir = Path(os.environ["PO_DEMO_HUB"])
    DEMO["job"] = str(demo_dir / "P12513")
    os.environ["PO_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("QML_DISK_CACHE_PATH", str(work / "qmlcache"))
    offscreen_screens(work)
    _install_handler(args.verbose)

    from PySide6.QtCore import Q_ARG, QMetaObject, QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # noqa: F401
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    QQuickStyle.setStyle("Basic")
    from project_opener import constants as C
    C.legacy_v1_dir = lambda: work / "no-legacy"          # type: ignore[assignment]
    if os.environ.get("PO_DEMO_DRIVES", "1") != "0":
        # captures must never show this PC's real mappings (office servers): the demo map stands in
        from project_opener.core import winutil
        winutil.mapped_drives = lambda: {"Z:": r"\\nas01\Project", "W:": r"\\nas01\Submissions"}
    if args.first_run:
        seed_first_run(data_dir)
        ids: dict[str, str] = {}
    else:
        ids = seed(data_dir, hub_dir, demo_dir)
    trace("seed")
    fast_offline_shares()

    from project_opener.app_v4 import qml_dir
    from project_opener.quick import motion as MO
    from project_opener.quick.facade import AppFacade
    from project_opener.ui import theme

    theme.load_fonts()
    facade = AppFacade(data_dir)
    trace("facade")
    facade.ctx.launcher.dry_run = True
    facade.ui.set_machine(MO.MachineFacts(screen_w=1920, screen_h=1080), "rhi")
    if ids:
        seed_alerts(facade, ids)
    try:
        from project_opener.desktop.integration import DesktopApi
        desk = DesktopApi(facade)
        desk._hotkey_status = {"snapshot": {"keys": "Ctrl+Alt+S", "ok": True, "error": ""},
                               "add_window": {"keys": "Ctrl+Alt+A", "ok": True, "error": ""},
                               "panel": {"keys": "Ctrl+Alt+P", "ok": True, "error": ""},
                               "palette": {"keys": "Ctrl+Alt+K", "ok": False,
                                           "error": "Hot key is already registered."}}
        if not args.stubs and not args.first_run:
            facade.set_desktop(desk)
    except Exception as exc:  # noqa: BLE001
        print(f"desktop api unavailable: {exc}")

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("app", facade)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    trace("engine.load")
    if not engine.rootObjects():
        print("\n".join(MESSAGES))
        print("Main.qml failed to load")
        return 2
    win = engine.rootObjects()[0]
    facade.ui.attach_window(win)
    win.show()
    facade.start()
    trace("facade.start()")
    facade.ctx.hub_timer.stop()
    for t in ("_timer", "_retry_timer"):              # no watcher pass: the seeded hits are the story
        timer = getattr(facade.watchers, t, None)
        if timer is not None:
            timer.stop()
    pump(app, 1500)
    if ids:
        w = facade.watchers
        wait_for(app, "hub", lambda: facade.hub.configured and facade.hub.mentionCandidates.rowCount() > 0, 15)
        wait_for(app, "tasks", lambda: facade.tasks.all.rowCount() > 0, 15)
        wait_for(app, "alerts", lambda: w.alerts.rowCount() >= 2, 15)
        wait_for(app, "drive map", lambda: any(r.get("rootName", "").lower() == "\\\\nas01" and r.get("status") == "offline"
                                               for r in w.roots.rows), 20)
    if ids and not args.stubs:
        demo_fill(facade, ids)
        trace("demo_fill")
    pump(app, 400)

    if not args.check:
        out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    notes: list[str] = []
    shots = 0

    def shot(name: str) -> None:
        nonlocal shots
        if args.check:
            return
        img = win.grabWindow()
        img.save(str(out / f"{name}.png"))
        shots += 1

    def call(fn: str, *vals: Any) -> None:
        QMetaObject.invokeMethod(win, fn, *[Q_ARG("QVariant", v) for v in vals])
        flush_deletes()

    def check_layout(tag: str, w: int, h: int, overflow_check: bool) -> None:
        page_min = int(win.property("pageMinimumWidth") or 0)
        if page_min > C_MIN_AVAIL:
            problems.append(f"{tag}: minimum width {page_min} > {C_MIN_AVAIL} beside the rail")
        if overflow_check:
            page = win.property("pageItem")
            if page is not None:
                for o in overflow(page, w - 68)[:5]:
                    problems.append(f"{tag}: {o}")

    def visit(route: str, tag: str, w: int, h: int, overflow_check: bool, take: bool = True) -> Any:
        real, payload = route_target(route, ids)
        STEP[0] = tag
        facade.ui.go(real, payload)
        flush_deletes()
        pump(app, 700)
        page = win.property("pageItem")
        if real == "hub" and payload.get("tab") and page is not None and facade.hub.configured \
                and page.property("tab") != payload["tab"]:
            problems.append(f"{tag}: the hub shows tab {page.property('tab')!r}, not {payload['tab']!r}")
        call("clearToasts")
        pump(app, 50)
        check_layout(tag, w, h, overflow_check)
        if h > 1000 and page is not None:
            ch = float(page.property("contentHeight") or 0)
            if ch > h:
                notes.append(f"{tag}: page is {ch:.0f} px tall, the window {h} px (the shot shows the top)")
        if take:
            shot(tag)
        trace(tag)
        return page

    themes = [t for t in args.themes.split(",") if t]
    sizes = [tuple(int(v) for v in s.split("x")) for s in args.sizes.split(",") if s]
    if args.routes:
        routes = [r for r in args.routes.split(",") if r]
    else:
        routes = list(FIRST_RUN_ROUTES if args.first_run else ROUTES)
    if not ids.get("running"):
        routes = [r for r in routes if r != "activity-running"]
    tall = tuple(int(v) for v in args.tall_size.split("x")) if args.tall_size and not args.first_run else None
    tall_routes = [r for r in args.tall_routes.split(",") if r and (ids.get("running") or r != "activity-running")]
    prefix = "first-" if args.first_run else ""
    lot7_toast = toast_text(facade, ids)
    for th in themes:
        STEP[0] = f"theme {th}"
        facade.ui.setTheme(th)
        for w, h in sizes:
            win.resize(w, h)
            pump(app, 200)
            for route in routes:
                visit(route, f"{prefix}{th}-{w}x{h}-{route}", w, h, (w, h) == (1040, 660))
            if args.sheets:
                for n, (sheet, props) in enumerate(SHEETS(ids), start=1):
                    facade.ui.go("home", {})
                    flush_deletes()
                    pump(app, 200)
                    STEP[0] = f"{th} {w}x{h} sheet {sheet}"
                    if props.get("demoMention"):
                        facade.hub.setMentionQuery("pr")   # typed before the picker shows: it opens narrowed
                    call("openSheet", sheet, props)
                    pump(app, 600)
                    call("clearToasts")
                    pump(app, 50)
                    shot(f"{prefix}{th}-{w}x{h}-sheet-{n:02d}-{sheet}")
                    call("closeSheet")
                    pump(app, 200)
                    if props.get("demoMention"):
                        facade.hub.setMentionQuery("")
                facade.ui.go("home", {})
                STEP[0] = f"{th} {w}x{h} palette"
                call("openPalette", "lot")
                pump(app, 500)
                shot(f"{prefix}{th}-{w}x{h}-palette")
                call("closePalette")
                pump(app, 200)
            if ids.get("lot7") and args.sheets:
                # The dock: open Lot 7 check (dry run) and catch it mid-way and settled.  Capture is not
                # started (it would read this PC's windows); Lot 7 stays the one waiting to be resumed.
                cap = facade.capture
                facade.ctx.settings.confirm_launch_over = 0
                STEP[0] = f"{th} {w}x{h} dock"
                cap.startActivity = lambda _aid: None          # type: ignore[method-assign]
                before = facade.ctx.store.activity(ids["lot7"]).to_dict()
                # the dry run takes 250 ms an item, as a real open does, so the shots show the rows queued (35 %),
                # opening and settled: mid-grow, at 900 ms and settled (juror D2-2)
                launcher = facade.ctx.launcher
                real_open = launcher.open_item
                launcher.open_item = lambda item, hosts=None, _o=real_open: (time.sleep(0.25), _o(item, hosts))[1]
                try:
                    facade.activities.open(ids["lot7"])
                    pump(app, 200)
                    shot(f"{prefix}{th}-{w}x{h}-dock-growing")
                    pump(app, 700)
                    shot(f"{prefix}{th}-{w}x{h}-dock-opening")
                    pump(app, 3500)
                    shot(f"{prefix}{th}-{w}x{h}-dock-settled")
                    facade.activities.closeDock()
                finally:
                    del cap.startActivity
                    del launcher.open_item
                    # the dock's open counted a launch; Lot 7 is still the one paused at 14:32
                    from project_opener.core import models as M
                    facade.ctx.store.update_activity(M.Activity.from_dict(before))
                    facade.activities.refresh()
                facade.ctx.settings.confirm_launch_over = 8
                facade.ui.go("home", {})
                pump(app, 300)
                call("clearToasts")
                facade.toast.emit(lot7_toast, "The checkpoint is in the activity's history.", "success")
                pump(app, 500)
                shot(f"{prefix}{th}-{w}x{h}-toast")
                pump(app, 300)
        if tall is not None and tall_routes:
            w, h = tall
            win.resize(w, h)
            pump(app, 300)
            for route in tall_routes:
                page = visit(route, f"{th}-tall-{route}", w, h, True, take=route != "settings")
                if route == "settings":
                    prop, keys = settings_tabs(page)
                    if not keys:
                        shot(f"{th}-tall-settings")
                    for key in keys:
                        tag = f"{th}-tall-settings-{key}"
                        p = visit(f"settings-{key}", tag, w, h, True)
                        if p is not None and p.property(prop) != key:
                            p.setProperty(prop, key)
                            pump(app, 400)
                            check_layout(tag, w, h, True)
                            shot(tag)
            win.resize(*(sizes[0] if sizes else SIZES[0]))
            pump(app, 200)

    pump(app, 300)
    warnings = list(MESSAGES)
    for m in warnings:
        print(m)
    for p in problems:
        print("[layout]", p)
    for n in notes:
        print("[note]", n)
    print(f"{shots} screenshots in {out}" if not args.check else "check pass done")
    print(f"{len(warnings)} Qt/QML warnings, {len(problems)} layout problems")
    print(f"run time {time.monotonic() - T0:.0f} s")
    win.close()
    trace("win.close()")
    import shiboken6
    win = None
    shiboken6.delete(engine)
    facade.shutdown()
    trace("facade.shutdown()")
    return 1 if warnings or problems else 0


def toast_text(app: Any, ids: dict[str, str]) -> str:
    """"Saved · 6 things · 14:32" from Lot 7's newest checkpoint (the one Resume offers)."""
    from project_opener.ui import text as T
    cps = app.snapshots.checkpoints(ids["lot7"]) if ids.get("lot7") else []
    if not cps:
        return "Saved"
    return f"Saved · {T.plural(cps[0].snapshot.open_count, 'thing')} · {T.clock(cps[0].taken_at)}"


C_MIN_AVAIL = 1040 - 68


def SHEETS(ids: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:  # noqa: N802
    lot7, p1 = ids.get("lot7", ""), ids.get("p1", "")
    return [
        ("ActivityEditor", {"activityId": lot7}),
        ("ActivityEditor", {"activityId": "", "projectId": p1}),
        ("ProjectEditor", {"projectId": p1}),
        ("ConfirmSheet", {"title": "Delete Lot 7 check?", "body": "Its 8 items and checkpoints go; the projects stay.",
                          "confirm": "Delete activity", "destructive": True}),
        ("PublishSheet", {"mode": "activity", "targetId": lot7, "demoMention": True}),
        ("PublishSheet", {"mode": "announce"}),
        ("TaskSheet", {"attachKind": "activity", "attachId": lot7}),
        ("WatcherSheet", {"activityId": lot7}),
        ("StartFromOpenSheet", {}),
        ("SaveNewSheet", {}),
        ("ResumeSheet", {}),
        ("AddChooserSheet", {"paths": [_job(r"Lot 8\Comment register.xlsx")]}),
        ("AttachPathSheet", {"entryKey": "win:ustation.exe|PIPE-GAD-0120.dgn - MicroStation",
                             "windowTitle": "PIPE-GAD-0120.dgn - MicroStation", "appName": "MicroStation"}),
    ]


if __name__ == "__main__":
    sys.exit(main())
