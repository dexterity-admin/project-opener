r"""Smoke test and screenshots of the Qt Quick (4.0) shell: what CI runs for v4.  (tools/smoke_ui.py is the
3.2 widgets UI's, which stays reachable with ``--classic`` until 4.0 ships.)

Seeds a demo workspace through the v4 store (projects, activities drawn from several of them, a stale
running marker so Home offers Resume, checkpoints), loads ``qml/Main.qml`` with the real facade, visits
every route (and the sheets, the palette, the dock) in both themes at both sizes, and fails on any Qt or
QML warning or on a page whose minimum width does not fit the 1040 x 660 window.

    python tools/smoke_v4.py --out build/screens-v4      (every page, sheet, palette and dock; what CI runs)
    python tools/smoke_v4.py --check                     (no screenshots: what the pytest smoke runs)
    python tools/smoke_v4.py --empty                     (live models as the app fills them: the empty states)

By default the live models (capture, hub, tasks, watchers) are filled with demo rows *when they are still
empty*, so the screenshots show every block in use; ``--empty`` keeps them as they are.  The launcher runs
in dry-run mode: nothing is opened.

Public captures show office-shaped paths, as tools/smoke_ui.py does for 3.2 (the repository is public):
``PO_DEMO_ROOT`` (e.g. D:\Projects\P12513; its parent holds the other demo jobs), ``PO_DEMO_HUB`` (the
demo hub folder, rebuilt on every run) and ``PO_DEMO_SERVER_ROOT`` (the {SERVER_ROOT} variable; unset, it
stays undefined so the drive map shows that state).  This PC's real drive mappings are replaced by a demo
map (Z: -> \\nas01\Project, W: -> \\nas01\Submissions); ``PO_DEMO_DRIVES=0`` turns that off.  Demo folders
named by the environment are only added to, never emptied.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and sys.platform == "win32":
    fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    if fonts.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))

# Offscreen frames are slow software renders; a frame-stepped animation driver would then run the dock's
# 1.3 s at a fraction of real time.  The simple driver steps by the wall clock, as on a real screen.
os.environ.setdefault("QSG_USE_SIMPLE_ANIMATION_DRIVER", "1")

WORK = Path(os.environ.get("PO_SMOKE_ROOT", r"U:\Vikram\_Claude_Work\temp\b4"))
SIZES = ((1400, 860), (1040, 660))
ROUTES = ("home", "activity", "activities", "projects", "project", "hub", "updates", "settings")
MESSAGES: list[str] = []
STEP = ["start"]                       # what the run was doing when a warning came (printed with it)
# Messages that are not about our QML (the offscreen platform's own notes).
BENIGN = ("propagateSizeHints", "QFont::setPointSize", "Populating font family aliases",
          "OpenType support missing", "This plugin does not support")


# ------------------------------------------------------------------- seed
def seed(data_dir: Path, hub_dir: Path, demo_dir: Path) -> dict[str, str]:
    """A demo workspace in schema 4 plus a hub; returns ids the run needs."""
    from project_opener.core import models as M
    from project_opener.core.settings import Settings
    from project_opener.core.snapshots import SnapshotStore
    from project_opener.core.store import WorkspaceStore
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
        "clash": demo_dir / "Clash register.xlsx",
    }
    for f in files.values():
        if not f.exists():
            f.write_bytes(b"demo")

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
                       M.Item(path=r"\\nas01\Project\P12513\ISO\Revision C", kind="folder", group="Folders",
                              label="Revision C"),
                       M.Item(path=r"{SERVER_ROOT}\P12513\Rulings.docx", kind="file", group="References"),
                       M.Item(path=str(files["iso"]), kind="file", group="Isos"),
                   ])
    p2 = M.Project(name="ANTEO Isometrics", client="ANTEO", color="#10B981", icon="ph.anchor",
                   tags=["isometrics", "handover"],
                   items=[M.Item(path=str(files["anteo"]), group="Checking"),
                          M.Item(path="https://teams.microsoft.com", kind="url", group="Links")])
    p3 = M.Project(name="Mangala Piping GAD", client="Cairn", job_number="DM-GAD", color="#F97316",
                   icon="ph.factory", tags=["GAD", "piping"],
                   items=[M.Item(path=r"Z:\Project\Mangala\GAD", kind="folder", label="GAD"),
                          M.Item(path=r"Z:\Project\Mangala\GAD\GAD-0120-B.pdf", kind="file")])
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
    lot7.open_count, lot7.last_opened = 14, M.now_iso()
    gad = M.Activity(name="Mangala GAD review", project_ids=[p3.id], items=from_proj(p3, [0, 1]))
    gad.open_count, gad.last_opened = 3, "2026-11-02T09:10:00+00:00"
    clash = M.Activity(name="Tuesday clash meeting", project_ids=[p4.id], items=from_proj(p4, [0, 1]))
    anteo = M.Activity(name="ANTEO handover", project_ids=[p2.id], items=from_proj(p2, [0, 1]))
    for a in (lot7, gad, clash, anteo):
        store.add_activity(a)

    snaps = SnapshotStore(data_dir)
    entries = [
        M.SnapshotEntry(key="path:" + str(files["check"]).lower(), status="identified", kind="file",
                        path=str(files["check"]), title="Iso checklist.pdf - PDF-XChange Editor", app="PDF-XChange Editor",
                        process="PDFXEdit.exe", identified_by="title+items", item_id=lot7.items[0].id),
        M.SnapshotEntry(key="path:" + str(files["lines"]).lower(), status="identified", kind="file",
                        path=str(files["lines"]), title="Line list.xlsx - Excel", app="Excel", process="EXCEL.EXE",
                        identified_by="office-com", item_id=lot7.items[1].id),
        M.SnapshotEntry(key="win:acad.exe|Drawing1", status="unidentified", title="Drawing1 - AutoCAD",
                        app="AutoCAD", process="acad.exe", note="unsaved - cannot be restored"),
    ]
    snap = M.Snapshot(activity_id=lot7.id, taken_at="2026-11-05T09:02:00+00:00", entries=entries)
    snaps.add_checkpoint(M.Checkpoint(activity_id=lot7.id, snapshot=snap, kind="auto",
                                      taken_at="2026-11-05T09:02:00+00:00"))
    snaps.mark_running(M.RunningMarker(activity_id=lot7.id, pid=999_999, started_at="2026-11-05T07:40:00+00:00",
                                       last_seen="2026-11-05T09:02:00+00:00"))

    hub = TeamHub(hub_dir, user="yokesh", display_name="Yokesh", role="Designer")
    hub.initialise()
    hub.heartbeat(current_project="ANTEO Isometrics")
    hub.publish(M.Project.from_dict(p2.to_dict()), description="Standard ANTEO checking bundle")
    hub.announce("Z: drive moves on Friday", "The Project share moves to the new NAS at 18:00.", "warning")
    hub2 = TeamHub(hub_dir, user="priya", display_name="Priya", role="Checker")
    hub2.heartbeat(current_project="DM-GAD · Mangala GAD review")
    hub2.send(M.current_user(), p3, "Have a look at the Mangala bundle before the review.")
    hub3 = TeamHub(hub_dir, user="ravi", display_name="Ravi", role="Designer")
    hub3.heartbeat(current_project="Navisworks clash review")
    return {"lot7": lot7.id, "p1": p1.id, "gad": gad.id}


# ------------------------------------------------------- demo of the stubs
def demo_fill(app: Any, ids: dict[str, str]) -> None:
    """Fill the other builders' models with demo rows where they are still empty (stubs)."""
    from project_opener.core import models as M
    from project_opener.ui import text as T

    cap, hub, tasks, watchers = app.capture, app.hub, app.tasks, app.watchers
    lot7 = app.ctx.store.activity(ids["lot7"])

    def fill(model: Any, rows: list[dict[str, Any]]) -> bool:
        if model.rowCount() == 0:
            model.reset([{r: row.get(r, "") for r in model.roles} for row in rows])
            return True
        return False

    live = [
        ("Iso checklist.pdf", _job(r"Iso checklist.pdf"), "identified", "PDF-XChange", "file", 1, True, False, ""),
        ("P12513-ISO-1042-C.pdf", r"\\nas01\Project\P12513\ISO\Revision C\P12513-ISO-1042-C.pdf", "identified", "PDF-XChange", "file", 2, True, False, ""),
        ("P12513-ISO-1043-C.pdf", r"\\nas01\Project\P12513\ISO\Revision C\P12513-ISO-1043-C.pdf", "identified", "PDF-XChange", "file", 2, False, True, ""),
        ("Line list.xlsx", _job(r"Line list.xlsx"), "identified", "Excel", "file", 1, True, False, ""),
        ("Comment register.xlsx", _job(r"Lot 7\Comment register.xlsx"), "identified", "Excel", "file", 1, True, False, ""),
        ("Working folder", _job(), "identified", "Explorer", "folder", 1, True, False, ""),
        ("FST portal · P12513", "https://portal.fst.example/P12513", "identified", "Edge", "url", 2, False, True, "active tab only"),
        ("", "", "unidentified", "AutoCAD", "", 1, False, False, "AutoCAD gave no file path; the drawing may be unsaved"),
        ("", "", "unidentified", "Navisworks", "", 2, False, False, "no document title; the window may be a start page"),
        ("", "", "ambiguous", "PDF-XChange", "file", 2, False, False, "two files with this name in the activity's folders"),
    ]
    titles = {"AutoCAD": "Drawing1 - AutoCAD", "Navisworks": "Navisworks Manage 2025",
              "ambiguous": "P12513-ISO-1050-C.pdf - PDF-XChange Editor"}
    rows = []
    for n, (name, path, st, appn, kind, mon, is_item, is_new, note) in enumerate(live):
        title = titles["ambiguous"] if st == "ambiguous" else titles.get(appn, name)
        rows.append({"entryKey": f"k{n}", "status": st, "kind": kind, "name": name or title, "path": path,
                     "title": title, "process": appn.lower() + ".exe", "appName": appn,
                     "identifiedBy": "office-com" if appn == "Excel" else "shell" if appn == "Explorer" else "title+items",
                     "monitor": f"monitor {mon}", "isItem": is_item, "isNew": is_new, "note": note,
                     "candidates": [r"\\nas01\Project\P12513\ISO\Revision C\P12513-ISO-1050-C.pdf",
                                    _job(r"Superseded\P12513-ISO-1050-C.pdf")] if st == "ambiguous" else []})
    DEMO["live"] = rows
    if fill(cap.live, rows):
        cap._running_id, cap._running_name, cap._running_label = lot7.id, lot7.name, lot7.label
        cap._running_color, cap._state = "#2F5BFF", "needs"
        cap._open, cap._identified, cap._needs_path, cap._new = len(rows), 7, 3, 2
        cap._since_checkpoint, cap._last_checkpoint_text = 2, "10:52"
        cap.stateChanged.emit()
        cap.liveChanged.emit()
    cps = [("c1", "2026-11-05T10:52:40+00:00", "manual", 12, 9), ("c2", "2026-11-05T10:20:00+00:00", "auto", 11, 9),
           ("c3", "2026-11-05T09:12:00+00:00", "auto", 9, 8), ("c4", "2026-11-04T17:58:00+00:00", "close", 10, 9)]
    if fill(cap.checkpoints, [{"checkpointId": c, "takenAt": t, "takenText": T.when_text(t), "kind": k,
                               "label": T.checkpoint_label(k, t, n), "count": n, "identified": i, "isLatest": c == "c1"}
                              for c, t, k, n, i in cps]):
        cap.checkpointsChanged.emit()
    fill(cap.startCandidates, [
        {"entryKey": "s1", "ticked": True, "name": "Iso checklist.pdf", "path": _job(r"Iso checklist.pdf"), "appName": "PDF-XChange", "status": "identified", "kind": "file"},
        {"entryKey": "s2", "ticked": True, "name": "Line list.xlsx", "path": _job(r"Line list.xlsx"), "appName": "Excel", "status": "identified", "kind": "file"},
        {"entryKey": "s3", "ticked": True, "name": "P12513", "path": _job(), "appName": "Explorer", "status": "identified", "kind": "folder"},
        {"entryKey": "s4", "ticked": False, "name": "Zoho Cliq", "path": "", "appName": "Cliq", "status": "unidentified", "kind": "", "note": "a chat window; it has no address to keep"},
        {"entryKey": "s5", "ticked": False, "name": "Inbox - Outlook", "path": "", "appName": "Outlook", "status": "unidentified", "kind": ""},
    ])

    people = [("yokesh", "Yokesh", "Designer", True, "in ANTEO Isometrics", "#8A5A00"),
              ("priya", "Priya", "Checker", True, "in DM-GAD · Mangala GAD review", "#4F46A3"),
              ("ravi", "Ravi", "Designer", True, "in Navisworks clash review", "#B4452E"),
              ("pradeep", "Pradeep", "Designer", False, "away since 13:10", "#0F766E")]
    if fill(hub.peers, [{"login": lg, "displayName": dn, "role": r, "host": "PC-" + lg.upper(), "online": on,
                         "doing": d, "initials": T.initials(dn), "hue": h, "cliqLinked": lg != "pradeep"}
                        for lg, dn, r, on, d, h in people]):
        hub._configured, hub._reachable = True, True
        hub._status_text, hub._peers_online, hub._inbox_count, hub._mention_count = "Connected", 3, 2, 1
        hub.hubChanged.emit()
        hub.peersChanged.emit()
        hub.inboxChanged.emit()
    fill(hub.published, [
        {"publishedId": "pub1", "type": "activity", "title": "P12513 · Lot 7 check", "spine": "P12513", "author": M.current_user(),
         "authorName": "Vikram", "revision": 3, "publishedText": "10:58", "forText": "for @checkers",
         "description": "Lot 7 back-check set. Watch Revision C for the modeller's sheets.", "isMine": True, "cloned": False, "itemCount": 11},
        {"publishedId": "pub2", "type": "project", "title": "ANTEO Isometrics", "spine": "ANTEO", "author": "yokesh",
         "authorName": "Yokesh", "revision": 2, "publishedText": "yesterday", "forText": "",
         "description": "Standard ANTEO checking bundle, rev B line list", "isMine": False, "cloned": True, "itemCount": 2},
        {"publishedId": "pub3", "type": "project", "title": "DM-GAD · Mangala Piping GAD", "spine": "DM-GAD", "author": "priya",
         "authorName": "Priya", "revision": 1, "publishedText": "Mon 3 Nov", "forText": "for Vikram",
         "description": "GAD review bundle, rev B drawings", "isMine": False, "cloned": False, "itemCount": 2},
    ])
    fill(hub.inbox, [
        {"messageId": "m1", "kind": "mention", "sender": "priya", "senderName": "Priya", "sentText": "10:41",
         "message": "@vikram Revision C has two new sheets for lot 7.", "title": "P12513 · Lot 7 check", "mentionsMe": True, "link": ""},
        {"messageId": "m2", "kind": "project", "sender": "priya", "senderName": "Priya", "sentText": "yesterday",
         "message": "Have a look at the Mangala bundle before the review.", "title": "DM-GAD · Mangala Piping GAD", "mentionsMe": False, "link": ""},
    ])
    fill(hub.announcements, [{"announcementId": "an1", "title": "Z: drive moves on Friday",
                              "body": "The Project share moves to the new NAS at 18:00. Mapped drives reconnect automatically.",
                              "level": "warning", "authorName": "Yokesh", "tsText": "09:15", "mine": False}])
    fill(hub.groups, [{"groupName": "checkers", "members": ["priya", "vikram"], "memberCount": 2, "dotColor": "#4F46A3", "updatedBy": "Priya"},
                      {"groupName": "P12513-team", "members": ["priya", "ravi", "yokesh", "vikram"], "memberCount": 4, "dotColor": "#2F5BFF", "updatedBy": "Vikram"}])
    fill(hub.mentionCandidates, [
        {"login": "priya", "displayName": "Priya", "role": "Checker", "online": True, "isGroup": False, "memberCount": 0},
        {"login": "pradeep", "displayName": "Pradeep", "role": "Designer", "online": False, "isGroup": False, "memberCount": 0},
        {"login": "P12513-team", "displayName": "P12513-team", "role": "Priya, Ravi, Yokesh, you", "online": True, "isGroup": True, "memberCount": 4}])
    fill(hub.register, [
        {"job": "P12513 · Lot 7 check", "event": "published for @checkers", "revision": "3", "by": "Vikram", "whenText": "10:58"},
        {"job": "P12513 · Lot 7 check", "event": "watcher hit · 2 new sheets in Revision C", "revision": "", "by": "this PC", "whenText": "10:41"},
        {"job": "P12513 · Lot 7 check", "event": "task created · Send rev C sheets to FST", "revision": "", "by": "Yokesh", "whenText": "09:50"},
        {"job": "P12513 · Lot 7 check", "event": "opened 2× today", "revision": "2", "by": "Vikram", "whenText": "09:12"},
        {"job": "ANTEO Isometrics", "event": "published", "revision": "2", "by": "Yokesh", "whenText": "10:30"},
        {"job": "ANTEO Isometrics", "event": "cloned", "revision": "2", "by": "Ravi", "whenText": "10:33"},
    ])
    task_rows = [
        ("t1", "Send rev C sheets to FST", "vikram", "Vikram", "2026-11-05", "Due today", True, False, "Yokesh", "activity", lot7.id, "Lot 7 check", "P12513"),
        ("t2", "Back-check lot 7", "vikram", "Vikram", "2026-11-07", "Fri 7 Nov", False, False, "Yokesh", "activity", lot7.id, "Lot 7 check", "P12513"),
        ("t3", "GAD comments to Cairn", "vikram", "Vikram", "2026-11-10", "Mon 10 Nov", False, False, "Priya", "activity", ids["gad"], "Mangala GAD review", "DM-GAD"),
        ("t4", "Update line list after clash", "priya", "Priya", "", "", False, True, "Vikram", "project", "", "Navisworks clash review", "P14414"),
    ]
    rows = [{"taskId": t, "title": ti, "owner": o, "ownerName": on, "due": d, "dueText": dt, "overdue": False, "done": done,
             "doneAt": "14:02" if done else "", "doneBy": on if done else "", "createdBy": cb.lower(), "createdByName": cb,
             "attachKind": ak, "attachId": ai, "attachTitle": at, "jobNumber": jn, "note": "", "mine": o == "vikram",
             "dueSoon": dt == "Due today"} for t, ti, o, on, d, dt, _soon, done, cb, ak, ai, at, jn in task_rows]
    if fill(tasks.all, rows):
        fill(tasks.mine, [r for r in rows if r["mine"] and not r["done"]])
        tasks._open_count, tasks._mine_open_count = 3, 3
        tasks.tasksChanged.emit()
    fill(watchers.roots, [
        {"rootName": r"\\nas01", "status": "offline", "statusLabel": "Server offline", "mapping": r"Z: → \\nas01\Project",
         "uses": "2 activities · P12513 · DM-GAD", "seenBy": 3, "since": "09:40", "sinceText": "down since 09:40 · seen by 3 PCs", "jobsAffected": 14},
        {"rootName": "{SERVER_ROOT}", "status": "variable", "statusLabel": "Undefined variable", "mapping": "",
         "uses": "1 activity · lot 7 check", "seenBy": 1, "since": "", "sinceText": "", "jobsAffected": 1},
        {"rootName": "D:", "status": "ok", "statusLabel": "Reachable", "mapping": "", "uses": "3 activities", "seenBy": 1,
         "since": "", "sinceText": "", "jobsAffected": 0},
        {"rootName": r"\\fileserver", "status": "ok", "statusLabel": "Reachable", "mapping": r"Y: → \\fileserver\Standards",
         "uses": "1 activity", "seenBy": 1, "since": "", "sinceText": "", "jobsAffected": 0},
    ])
    fill(watchers.watchers, [
        {"watcherId": "w1", "name": "Revision C sheets", "kind": "folder", "target": r"\\nas01\Project\P12513\ISO\Revision C",
         "events": ["new", "changed"], "watcherEnabled": True, "notifyText": "Toast · Cliq DM", "lastHitText": "2 new sheets 10:41",
         "activityId": lot7.id, "projectId": ""},
        {"watcherId": "w2", "name": "nas01 health", "kind": "health", "target": r"\\nas01", "events": ["down", "up"],
         "watcherEnabled": True, "notifyText": "Toast · Cliq DM when it comes back", "lastHitText": "down since 09:40",
         "activityId": lot7.id, "projectId": ""},
    ])
    fill(watchers.alerts, [{"alertKey": "al1", "tsText": "10:41", "title": "2 new sheets in Revision C",
                            "detail": "P12513-ISO-1043-C.pdf, P12513-ISO-1044-C.pdf", "level": "info", "link": "",
                            "unread": True, "watcherId": "w1"}])
    try:
        watchers.alertsChanged.emit()
        watchers.rootsChanged.emit()
        watchers.watchersChanged.emit()
    except Exception:  # noqa: BLE001
        pass
    app.activities.refresh()


def fast_offline_shares() -> None:
    """The demo's nas01 and fileserver shares do not exist; Windows takes 20 s or more to say so for a
    UNC path.  The smoke answers "offline" for them at once (health and the dry-run launcher)."""
    import os as _os

    from project_opener.core import health as H
    from project_opener.core import launcher as L
    from project_opener.core import winutil

    fake = ("\\\\nas01", "\\\\fileserver")

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


def set_running(app: Any, activity_id: str) -> None:
    """Demo only: show ``activity_id`` as the running one (the stub capture API has no engine)."""
    cap = app.capture
    if type(cap).__module__.endswith("capture_api") and getattr(cap, "_engine", None) is None:
        act = app.ctx.store.activity(activity_id) if activity_id else None
        cap._running_id = activity_id
        cap._running_name = act.name if act else ""
        cap._running_label = act.label if act else ""
        cap._state = "needs" if act else "idle"
        cap.stateChanged.emit()
        app.activities.refresh()


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WORK / "shots"))
    ap.add_argument("--check", action="store_true", help="no screenshots: load every page, fail on warnings")
    ap.add_argument("--empty", "--stubs", dest="stubs", action="store_true",
                    help="leave the live models as the app fills them (the empty states)")
    ap.add_argument("--themes", default="dark,light")
    ap.add_argument("--sizes", default="1400x860,1040x660")
    ap.add_argument("--routes", default=",".join(ROUTES))
    ap.add_argument("--sheets", action="store_true", default=True)
    ap.add_argument("--no-sheets", dest="sheets", action="store_false")
    ap.add_argument("--work", default=str(WORK))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    work = Path(args.work)
    data_dir, hub_dir, demo_dir = work / "smoke-data", work / "smoke-hub", work / "demo"
    if os.environ.get("PO_DEMO_ROOT"):
        demo_dir = Path(os.environ["PO_DEMO_ROOT"]).parent       # D:\Projects\P12513 -> D:\Projects
    if os.environ.get("PO_DEMO_HUB"):
        hub_dir = Path(os.environ["PO_DEMO_HUB"])
    DEMO["job"] = str(demo_dir / "P12513")
    os.environ["PO_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("QML_DISK_CACHE_PATH", str(work / "qmlcache"))
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
    ids = seed(data_dir, hub_dir, demo_dir)
    trace('ids = seed(data_dir, hub_dir, demo_dir)')
    fast_offline_shares()

    from project_opener.app_v4 import qml_dir
    from project_opener.quick import motion as MO
    from project_opener.quick.facade import AppFacade
    from project_opener.ui import theme

    theme.load_fonts()
    facade = AppFacade(data_dir)
    trace('facade = AppFacade(data_dir)')
    facade.ctx.launcher.dry_run = True
    facade.ui.set_machine(MO.MachineFacts(screen_w=1920, screen_h=1080), "rhi")
    try:
        from project_opener.desktop.integration import DesktopApi
        desk = DesktopApi(facade)
        desk._hotkey_status = {"snapshot": {"keys": "Ctrl+Alt+S", "ok": True, "error": ""},
                               "add_window": {"keys": "Ctrl+Alt+A", "ok": True, "error": ""},
                               "panel": {"keys": "Ctrl+Alt+P", "ok": True, "error": ""},
                               "palette": {"keys": "Ctrl+Alt+K", "ok": False,
                                           "error": "Hot key is already registered."}}
        if not args.stubs:
            facade.set_desktop(desk)
    except Exception as exc:  # noqa: BLE001
        print(f"desktop api unavailable: {exc}")

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("app", facade)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    trace('engine.load(QUrl.fromLocalFile(str(qml_d')
    if not engine.rootObjects():
        print("\n".join(MESSAGES))
        print("Main.qml failed to load")
        return 2
    win = engine.rootObjects()[0]
    facade.ui.attach_window(win)
    win.show()
    facade.start()
    trace('facade.start()')
    facade.ctx.hub_timer.stop()
    pump(app, 1500)
    if not args.stubs:
        demo_fill(facade, ids)
        trace('demo_fill(facade, ids)')
    pump(app, 400)

    out = Path(args.out)
    if not args.check:
        out.mkdir(parents=True, exist_ok=True)
    payloads = {"activity": {"activityId": ids["lot7"]}, "project": {"projectId": ids["p1"]}}
    problems: list[str] = []
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

    themes = [t for t in args.themes.split(",") if t]
    sizes = [tuple(int(v) for v in s.split("x")) for s in args.sizes.split(",") if s]
    routes = [r for r in args.routes.split(",") if r]
    for th in themes:
        STEP[0] = f"theme {th}"
        facade.ui.setTheme(th)
        for w, h in sizes:
            win.resize(w, h)
            pump(app, 200)
            for route in routes:
                if not args.stubs:
                    set_running(facade, ids["lot7"] if route == "activity" else "")
                STEP[0] = f"{th} {w}x{h} {route}"
                facade.ui.go(route, payloads.get(route, {}))
                flush_deletes()
                pump(app, 700)
                if route == "activity" and not args.stubs and DEMO.get("live") and facade.capture.live.rowCount() == 0:
                    cap = facade.capture                 # the capture API cleared its live list for a stub run
                    cap.live.reset([{r: row.get(r, "") for r in cap.live.roles} for row in DEMO["live"]])
                    cap._open, cap._identified, cap._needs_path, cap._new = len(DEMO["live"]), 7, 3, 2
                    cap.liveChanged.emit()
                    pump(app, 400)
                call("clearToasts")
                pump(app, 50)
                tag = f"{th}-{w}x{h}-{route}"
                page_min = int(win.property("pageMinimumWidth") or 0)
                avail = w - 68
                if page_min > C_MIN_AVAIL:
                    problems.append(f"{route}: minimum width {page_min} > {C_MIN_AVAIL} beside the rail")
                if (w, h) == (1040, 660):
                    page = win.property("pageItem")
                    if page is not None:
                        for o in overflow(page, avail)[:5]:
                            problems.append(f"{tag}: {o}")
                shot(tag)
                trace('shot(tag)')
            if args.sheets and (w, h) in ((1400, 860), (1040, 660)):
                for n, (sheet, props) in enumerate(SHEETS(ids), start=1):
                    facade.ui.go("home", {})
                    flush_deletes()
                    pump(app, 200)
                    STEP[0] = f"{th} {w}x{h} sheet {sheet}"
                    call("openSheet", sheet, props)
                    pump(app, 600)
                    call("clearToasts")
                    pump(app, 50)
                    shot(f"{th}-{w}x{h}-sheet-{n:02d}-{sheet}")
                    call("closeSheet")
                    pump(app, 200)
                facade.ui.go("home", {})
                STEP[0] = f"{th} {w}x{h} palette"
                call("openPalette", "lot")
                pump(app, 500)
                shot(f"{th}-{w}x{h}-palette")
                call("closePalette")
                pump(app, 200)
                # The dock: open Lot 7 check (dry run) and catch it mid-way and settled.
                facade.ctx.settings.confirm_launch_over = 0
                STEP[0] = f"{th} {w}x{h} dock"
                facade.activities.open(ids["lot7"])
                pump(app, 900)
                shot(f"{th}-{w}x{h}-dock-opening")
                pump(app, 3500)
                shot(f"{th}-{w}x{h}-dock-settled")
                facade.activities.closeDock()
                facade.ctx.settings.confirm_launch_over = 8
                facade.toast.emit("Saved · 12 things · 14:32", "The checkpoint is in the activity's history.", "success")
                pump(app, 500)
                shot(f"{th}-{w}x{h}-toast")
                pump(app, 300)

    pump(app, 300)
    warnings = [m for m in MESSAGES]
    for m in warnings:
        print(m)
    for p in problems:
        print("[layout]", p)
    print(f"{shots} screenshots in {out}" if not args.check else "check pass done")
    print(f"{len(warnings)} Qt/QML warnings, {len(problems)} layout problems")
    win.close()
    trace('win.close()')
    import shiboken6
    win = None
    shiboken6.delete(engine)
    facade.shutdown()
    trace('facade.shutdown()')
    return 1 if warnings or problems else 0


C_MIN_AVAIL = 1040 - 68


def SHEETS(ids: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:  # noqa: N802
    return [
        ("ActivityEditor", {"activityId": ids["lot7"]}),
        ("ActivityEditor", {"activityId": "", "projectId": ids["p1"]}),
        ("ProjectEditor", {"projectId": ids["p1"]}),
        ("ConfirmSheet", {"title": "Delete Lot 7 check?", "body": "Its 8 items and checkpoints go; the projects stay.",
                          "confirm": "Delete activity", "destructive": True}),
        ("PublishSheet", {"mode": "activity", "targetId": ids["lot7"], "demoMention": True}),
        ("PublishSheet", {"mode": "announce"}),
        ("TaskSheet", {"attachKind": "activity", "attachId": ids["lot7"]}),
        ("WatcherSheet", {"activityId": ids["lot7"]}),
        ("StartFromOpenSheet", {}),
        ("AddChooserSheet", {"paths": [_job(r"Lot 8\Comment register.xlsx")]}),
        ("AttachPathSheet", {"entryKey": "k7", "windowTitle": "Drawing1 - AutoCAD", "appName": "AutoCAD"}),
    ]


if __name__ == "__main__":
    sys.exit(main())
