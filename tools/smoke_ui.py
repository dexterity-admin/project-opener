"""Headless-ish UI smoke test: seeds a demo workspace + hub, opens every page,
captures screenshots to --out and exits.  Used in CI (offscreen) and locally.

    python tools/smoke_ui.py --out build/screens [--theme light] [--keep-open]

The default run captures the eight page screens CI and the README depend on
(``<theme>-home.png`` … ``<theme>-palette.png``).  More captures, all optional:

    --dialogs          every editing dialog and the delete confirmation
    --states           palette without a query, toasts, the launch sheet (mixed
                       results, and all opened), collapsed sidebar, the Team Hub
                       tabs, a project with no items, every Updates state
    --empty            a workspace with no projects / no hub / empty inbox
                       (runs instead of the seeded pass; names end in -empty)
    --all              --dialogs --states, then the --empty pass
    --density compact  compact density (file names gain "-compact")
    --scale 2          2x rendering (file names gain "-2x")

Qt warnings printed while capturing are counted and listed at the end.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The offscreen platform uses Qt's FreeType font database, which on Windows
# does not scan the system fonts folder by itself; without this it renders a
# built-in fallback face and the screenshots look nothing like the app.
if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and sys.platform == "win32":
    fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    if fonts.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))

QT_MESSAGES: list[str] = []


def seed(data_dir: Path, hub_dir: Path) -> None:
    from project_opener.core import models as M
    from project_opener.core.store import WorkspaceStore
    from project_opener.lan.hub import TeamHub

    store = WorkspaceStore(data_dir)
    if store.projects:
        return
    # PO_DEMO_ROOT lets a capture run show office-shaped paths (e.g. D:\Projects\P12513)
    # instead of the temp folder; CI keeps the default.
    docs = Path(os.environ.get("PO_DEMO_ROOT") or (Path(tempfile.gettempdir()) / "po-demo"))
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "Line list.xlsx").write_bytes(b"demo")
    (docs / "Iso checklist.pdf").write_bytes(b"demo")
    p1 = M.Project(name="P12513 As-built isometrics", client="FST", job_number="P12513", color="#2F5BFF",
                   icon="fa5s.drafting-compass", tags=["as-built", "FST", "isometrics"],
                   description="RLM red-line cross-check lot 7", pinned_at=M.now_iso(), favorite=True,
                   items=[
                       M.Item(path=str(docs / "Iso checklist.pdf"), kind="file", group="Checking"),
                       M.Item(path=str(docs / "Line list.xlsx"), kind="file", group="Checking"),
                       M.Item(path=str(docs), kind="folder", group="Folders", label="Working folder"),
                       M.Item(path=r"\\nas01\Project\P12513\ISO", kind="folder", group="Folders", label="Submission share"),
                       M.Item(path="https://github.com/dexterity-admin/project-opener", kind="url", group="Links"),
                       M.Item(path=r"{SERVER_ROOT}\P12513\Rulings.docx", kind="file", group="References"),
                   ])
    p1.launch_sets.append(M.LaunchSet(name="Checking", item_ids=[p1.items[0].id, p1.items[1].id]))
    p1.launch_sets.append(M.LaunchSet(name="Submission pack", item_ids=[p1.items[2].id, p1.items[3].id], icon="fa5s.file-signature"))
    p1.open_count = 14
    p1.last_opened = M.now_iso()
    p2 = M.Project(name="ANTEO Isometrics", client="ANTEO", color="#10B981", icon="fa5s.ship", tags=["isometrics", "handover"],
                   items=[M.Item(path=str(docs / "Line list.xlsx")), M.Item(path="https://teams.microsoft.com", kind="url")])
    p3 = M.Project(name="Mangala Piping GAD", client="Cairn", job_number="DM-GAD", color="#F97316", icon="fa5s.industry",
                   tags=["GAD", "piping"], items=[M.Item(path=r"Z:\Project\Mangala\GAD", kind="folder")])
    p4 = M.Project(name="Navisworks clash review", color="#8B5CF6", icon="fa5s.cubes", tags=["3D", "review"],
                   items=[M.Item(path=r"C:\Program Files\Autodesk\Navisworks Manage 2024\Roamer.exe", kind="app", args="")])
    p5 = M.Project(name="Office tools", color="#14B8A6", icon="fa5s.tools", tags=["tools"],
                   items=[M.Item(path="https://outlook.office.com", kind="url"), M.Item(path="cmd: ipconfig", kind="command")])
    for p in (p1, p2, p3, p4, p5):
        store.add(p)
    store.record_launch(p1, p1.items[:2], "Checking", ok=2)
    store.record_launch(p2, p2.items, ok=2)
    hub = TeamHub(hub_dir, user="yokesh", display_name="Yokesh")
    hub.initialise()
    hub.heartbeat(current_project="ANTEO Isometrics")
    first = hub.publish(M.Project.from_dict(p2.to_dict()), description="Standard ANTEO checking bundle")
    if first is not None:                       # my copy is a clone of revision 1; the hub then gets revision 2
        p2.origin = M.Origin(source="team", author="yokesh", published_id=first.published_id,
                             published_at=first.published_at, revision=1)
        store.update(p2)
        hub.publish(M.Project.from_dict(p2.to_dict()), description="Standard ANTEO checking bundle, rev B line list")
    hub.announce("Z: drive moves on Friday", "The Project share moves to the new NAS at 18:00. Mapped drives reconnect automatically.", "warning")
    hub.pulse("launched", "ANTEO Isometrics › Handover")
    hub2 = TeamHub(hub_dir, user="priya", display_name="Priya", role="Checker")
    hub2.heartbeat(current_project="P14414 GAD")
    hub2.send(M.current_user(), p3, "Have a look at the Mangala bundle before the review.")
    hub2.publish(M.Project.from_dict(p3.to_dict()), description="GAD review bundle, rev B drawings")
    hub3 = TeamHub(hub_dir, user="ravi", display_name="Ravi", role="Designer")
    hub3.heartbeat(current_project="Navisworks clash review")
    hub3.publish(M.Project.from_dict(p4.to_dict()), description="Clash review set for the Tuesday meeting")  # publish() pulses by itself


def _install_message_handler() -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def handler(mode, context, message):
        kind = {QtMsgType.QtWarningMsg: "warning", QtMsgType.QtCriticalMsg: "critical",
                QtMsgType.QtFatalMsg: "fatal"}.get(mode)
        if kind and "propagateSizeHints" in message:
            return      # the offscreen platform plugin says this for every top-level dialog; not ours
        if kind:
            QT_MESSAGES.append(f"{kind}: {message}")
            print(f"QT {kind}: {message}", file=sys.stderr)

    qInstallMessageHandler(handler)


class Capturer:
    """Grabs the window (and any floating dialog) into ``out`` with a stable name."""

    def __init__(self, out: Path, theme_name: str, density: str, scale: int):
        self.out = out
        suffix = ("-compact" if density == "compact" else "") + (f"-{scale}x" if scale != 1 else "")
        self.prefix = f"{theme_name}{suffix}-"
        self.win = None

    def path(self, name: str) -> Path:
        return self.out / f"{self.prefix}{name}.png"

    def shot(self, name: str, keep_toasts: bool = False, overlay=None) -> None:
        from PySide6.QtGui import QPainter
        from PySide6.QtTest import QTest
        win = self.win
        if not keep_toasts:
            for toast in list(win.toasts._toasts):   # clean captures: no toast over the content
                toast.dismiss()
        QTest.qWait(500)
        pm = win.grab()
        if overlay is not None and overlay.isVisible():
            painter = QPainter(pm)
            painter.drawPixmap(overlay.pos() - win.pos(), overlay.grab())
            painter.end()
        pm.save(str(self.path(name)))
        print("captured", name)


def _capture_pages(cap: Capturer, ctx, win) -> None:
    from PySide6.QtTest import QTest
    _wait_health(ctx)                 # Home's Drives block and pills show the real states
    win.pages["home"].refresh()
    QTest.qWait(300)
    cap.shot("home")
    win.go("projects")
    cap.shot("projects")
    win.ctx.settings.view_mode = "list"
    win.pages["projects"].refresh()
    cap.shot("projects-list")
    win.ctx.settings.view_mode = "grid"
    first = ctx.store.projects[0]
    win.open_project(first)
    _wait_health(ctx)
    cap.shot("project")
    win.go("team")
    QTest.qWait(800)
    cap.shot("team")
    win.go("updates")
    cap.shot("updates")
    win.go("settings")
    cap.shot("settings")
    win.go("home")
    win.open_palette()
    QTest.qWait(300)
    win.palette.edit.setText("check")
    QTest.qWait(300)
    cap.shot("palette", overlay=win.palette)
    win.palette.reject()


def _wait_health(ctx) -> None:
    from PySide6.QtTest import QTest
    for _ in range(240):          # up to 60 s: an unreachable UNC host can take 20 s+ to time out
        if all(ctx.health_for(p.id) is not None for p in ctx.store.projects):
            break
        QTest.qWait(250)
    QTest.qWait(300)


def _capture_dialogs(cap: Capturer, ctx, win) -> None:
    """Every editing dialog, shown modeless just long enough to grab it."""
    from PySide6.QtTest import QTest

    from project_opener.ui.widgets import dialogs as D
    first = ctx.store.projects[0]
    peers = [p.user for p in ctx.peers if p.user != ctx.user] or ["priya", "ravi"]
    win.open_project(first)
    _wait_health(ctx)
    page = win.pages["project"]
    specs = [
        ("dialog-project-editor", lambda: D.ProjectEditor(first, ctx.store.all_tags(), win)),
        ("dialog-project-new", lambda: D.ProjectEditor(None, ctx.store.all_tags(), win)),
        ("dialog-item-editor", lambda: D.ItemEditor(first.items[3], first.groups(), page)),
        ("dialog-item-new", lambda: D.ItemEditor(None, first.groups(), page)),
        ("dialog-launchset-editor", lambda: D.LaunchSetEditor(first, first.launch_sets[0], page)),
        ("dialog-send-to", lambda: D.SendToDialog(first, peers, win)),
        ("dialog-announcement", lambda: D.AnnouncementDialog(win)),
        ("dialog-publish", lambda: D.PublishDialog(first, win)),
        ("dialog-confirm-delete", lambda: D.confirm_box(win, "Delete project",
                                                        f"Delete ‘{first.name}’ from your workspace? The files themselves are not touched.", danger=True)[0]),
    ]
    for name, make in specs:
        dlg = make()
        if name == "dialog-item-editor":
            dlg.show_error("Enter a path, folder, link, application or command.", dlg.path)   # the field outlined, focused
        dlg.show()
        dlg.adjustSize()
        QTest.qWait(400)
        g = win.geometry()
        dlg.move(g.center().x() - dlg.width() // 2, g.center().y() - dlg.height() // 2)
        QTest.qWait(200)
        cap.shot(name, overlay=dlg)
        dlg.close()
        dlg.deleteLater()
        QTest.qWait(100)


def _capture_launch_sheet(cap: Capturer, ctx, win) -> None:
    """The launch sheet after a dry run (nothing is really opened): mixed results, then all opened."""
    from PySide6.QtTest import QTest

    from project_opener.core.launcher import Launcher

    def run_and_wait(project):
        run = ctx.launch(project, parent=win)
        for _ in range(240):           # an unreachable UNC host can take 20 s+ to time out
            if run is None or run.done:
                break
            QTest.qWait(250)
        QTest.qWait(300)
        return run

    real = ctx.launcher
    ctx.launcher = Launcher(ctx.resolver, delay_ms=0, dry_run=True)
    try:
        win.go("home")
        QTest.qWait(200)
        # P12513 has a server-offline folder and a not-found reference: the sheet stays
        run_and_wait(ctx.store.projects[0])
        cap.shot("launch-sheet")
        win.sheet.dismiss()
        QTest.qWait(200)
        # every item opened: captured before the sheet closes itself
        win.launch_sheet().auto_close_ms = 0
        run_and_wait(ctx.store.by_name("ANTEO Isometrics"))
        cap.shot("launch-sheet-ok")
        win.sheet.dismiss()
        win.sheet.auto_close_ms = 2500
        QTest.qWait(200)
    finally:
        ctx.launcher = real


def _capture_states(cap: Capturer, ctx, win) -> None:
    from PySide6.QtTest import QTest

    from project_opener.core import models as M
    from project_opener.update.updater import CheckResult, UpdateInfo

    # palette without a query
    win.go("home")
    win.open_palette()
    QTest.qWait(300)
    cap.shot("palette-empty", overlay=win.palette)
    win.palette.reject()
    _capture_launch_sheet(cap, ctx, win)
    # toasts
    ctx.toast.emit("Published to Team Hub", "P12513 As-built isometrics · revision 2", "success")
    QTest.qWait(400)
    cap.shot("toast", keep_toasts=True)
    for toast in list(win.toasts._toasts):
        toast.dismiss()
    QTest.qWait(300)
    ctx.toast_action.emit("1 project in your inbox", "Priya sent Mangala Piping GAD.", "info", "Open inbox", ("team", "inbox"))
    QTest.qWait(400)
    cap.shot("toast-action", keep_toasts=True)
    ctx.toast.emit("Team Hub unreachable", r"\\nas01\Project\_ProjectOpenerHub", "error")
    ctx.toast.emit("Not found", r"Z:\Project\Mangala\GAD", "warning")
    QTest.qWait(400)
    cap.shot("toast-stack", keep_toasts=True)
    # a search with no match
    win.go("projects")
    win.pages["projects"].search.setText("boiler")
    QTest.qWait(400)
    cap.shot("projects-nomatch")
    win.pages["projects"].search.setText("")
    QTest.qWait(300)
    # sidebar collapsed
    win.sidebar.toggle()
    QTest.qWait(500)
    cap.shot("sidebar-collapsed")
    win.sidebar.toggle()
    QTest.qWait(500)
    # team hub tabs
    win.go("team", "inbox")
    QTest.qWait(600)
    cap.shot("team-inbox")
    team = win.pages["team"]
    team.tabs.setCurrentWidget(team.tab_ann)
    cap.shot("team-announcements")
    team.tabs.setCurrentWidget(team.tab_pulse)
    cap.shot("team-activity")
    team.tabs.setCurrentWidget(team.tab_published)
    # a project with no items and no launch sets
    bare = M.Project(name="P14414 Pipe rack GAD", client="Cairn", job_number="P14414", color="#A16207", icon="fa5s.industry")
    ctx.store.add(bare)
    win.open_project(bare)
    QTest.qWait(400)
    cap.shot("project-empty")
    ctx.store.remove(bare.id)
    # a long name: the title elides, the actions stay on the row
    long = M.Project(name="P12513 As-built isometrics, RLM red-line cross-check, lot 7 of 12, Mangala East processing terminal",
                     client="FST", job_number="P12513", color="#2F5BFF", icon="fa5s.drafting-compass",
                     items=[M.Item(path=r"\\nas01\Project\P12513\ISO\Revision C\Line list rev C with comments (2026-10-30).xlsx")])
    ctx.store.add(long)
    win.open_project(long)
    QTest.qWait(400)
    cap.shot("project-longname")
    ctx.store.remove(long.id)
    # the smallest window the app allows
    win.resize(win.minimumSize())
    QTest.qWait(400)
    win.go("home")
    cap.shot("minsize-home")
    win.open_project(ctx.store.projects[0])
    QTest.qWait(300)
    cap.shot("minsize-project")
    too_wide = pages_over_minimum(win)
    if too_wide:
        raise SystemExit(f"pages wider than the minimum window: {too_wide}")
    print("every page fits the minimum window")
    win.resize(1400, 860)
    QTest.qWait(400)
    # updates states
    win.go("updates")
    page = win.pages["updates"]
    from project_opener import constants as C
    from project_opener.update.updater import parse_version
    major, minor = parse_version(C.VERSION)[:2]
    newer = f"{major}.{minor + 1}.0"          # always newer than the running version, so the state renders
    info = UpdateInfo(version=newer, installer=f"ProjectOpener-{newer}-setup.exe", sha256="0" * 64,
                      url=f"https://github.com/dexterity-admin/project-opener/releases/download/v{newer}/ProjectOpener-{newer}-setup.exe",
                      size=38_400_000, published_at=M.now_iso(), source="github",
                      notes="Team Hub: announcements can expire.\nProject page: items grouped by folder.\nFixes for mapped-drive paths.")
    ctx.settings.update_last_check = M.now_iso()
    ctx.last_check = CheckResult(update=None, checked_sources=["lan", "github"])
    page.render_state()
    cap.shot("updates-uptodate")
    ctx.last_check = CheckResult(update=info, checked_sources=["lan", "github"])
    page.render_state()
    cap.shot("updates-available")
    page.render_state(downloading=True)
    if page.bar is not None:
        page.bar.setMaximum(100)
        page.bar.setValue(62)
    cap.shot("updates-downloading")
    inst = Path(tempfile.gettempdir()) / info.installer
    inst.write_bytes(b"demo")
    ctx.downloaded = inst
    page.render_state()
    cap.shot("updates-ready")
    page.render_state(mirroring=newer)
    cap.shot("updates-mirroring")
    ctx.downloaded = None
    ctx.settings.update_skip_version = newer
    page.render_state()
    cap.shot("updates-skipped")
    ctx.settings.update_skip_version = ""
    ctx.last_check = CheckResult(update=None, errors=["GitHub: name resolution failed"], checked_sources=["lan"])
    page.render_state(error="Could not reach GitHub (name resolution failed). The LAN mirror was checked.")
    cap.shot("updates-error")
    ctx.last_check = None
    ctx.settings.update_last_check = ""
    page.render_state()


def pages_over_minimum(win) -> list[tuple[str, int, int]]:
    """(route, page minimum width, available width) for every page that cannot fit the window's
    minimum size beside the sidebar.  Empty when every page fits."""
    from project_opener.ui.widgets.sidebar import EXPANDED
    avail = win.minimumWidth() - EXPANDED
    out = []
    for route, page in win.pages.items():
        need = page.body.minimumSizeHint().width()
        if need > avail:
            out.append((route, need, avail))
    return out


def _capture_empty(cap: Capturer, ctx, win, hub_dir: Path) -> None:
    """A workspace with nothing in it: no projects, no hub, then an empty hub."""
    from PySide6.QtTest import QTest

    from project_opener.core import models as M
    cap.shot("home-empty")
    win.go("projects")
    cap.shot("projects-empty")
    win.go("team")
    QTest.qWait(400)
    cap.shot("team-nohub")
    ctx.settings.hub_path = str(hub_dir)
    ctx.apply_settings()
    ctx.hub.initialise()
    ctx.refresh_hub()
    QTest.qWait(1200)
    win.go("team")
    QTest.qWait(400)
    cap.shot("team-empty")
    team = win.pages["team"]
    team.tabs.setCurrentWidget(team.tab_inbox)
    cap.shot("team-inbox-empty")
    team.tabs.setCurrentWidget(team.tab_ann)
    cap.shot("team-announcements-empty")
    team.tabs.setCurrentWidget(team.tab_pulse)
    cap.shot("team-activity-empty")
    bare = M.Project(name="P14414 Pipe rack GAD", client="Cairn", job_number="P14414", color="#A16207", icon="fa5s.industry")
    ctx.store.add(bare)
    win.open_project(bare)
    QTest.qWait(400)
    cap.shot("project-empty")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "screens"))
    ap.add_argument("--theme", default="dark")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument("--data", default="")
    ap.add_argument("--density", default="comfortable", choices=("comfortable", "compact"))
    ap.add_argument("--scale", type=int, default=1, choices=(1, 2))
    ap.add_argument("--dialogs", action="store_true", help="also capture every dialog")
    ap.add_argument("--states", action="store_true", help="also capture toasts, palette, sidebar, tabs and Updates states")
    ap.add_argument("--empty", action="store_true", help="capture the empty workspace instead of the seeded one")
    ap.add_argument("--all", action="store_true", help="--dialogs --states, then the --empty pass")
    args = ap.parse_args()
    if args.all:
        args.dialogs = args.states = True
    if args.scale != 1:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    _install_message_handler()
    app = QApplication(sys.argv)

    passes = [False] if not args.empty else [True]
    if args.all:
        passes = [False, True]
    rc = 0
    for empty in passes:
        rc = _run_pass(app, args, out, empty)
        if rc:
            break
        if args.keep_open:
            return rc
    if QT_MESSAGES:
        print(f"\n{len(QT_MESSAGES)} Qt warning(s):")
        for m in QT_MESSAGES:
            print("  " + m)
    else:
        print("\nno Qt warnings")
    return rc


def _run_pass(app, args, out: Path, empty: bool) -> int:
    data_dir = Path(args.data) if args.data and not empty else Path(tempfile.mkdtemp(prefix="po-smoke-"))
    hub_dir = Path(os.environ["PO_DEMO_HUB"]) if os.environ.get("PO_DEMO_HUB") and not empty else data_dir / "hub"
    os.environ["PO_DATA_DIR"] = str(data_dir)
    # Captures must never show this PC's real drive mappings (office servers):
    # the demo drive map stands in for them.  Set PO_DEMO_DRIVES=0 to disable.
    if os.environ.get("PO_DEMO_DRIVES", "1") != "0":
        from project_opener.core import winutil
        winutil.mapped_drives = lambda: {"Z:": r"\\nas01\Project", "W:": r"\\nas01\Submissions"}
    from project_opener import constants as C
    C.legacy_v1_dir = lambda: data_dir / "nolegacy"  # type: ignore[assignment]

    from PySide6.QtTest import QTest

    from project_opener.core.settings import Settings
    from project_opener.ui import theme
    from project_opener.ui.context import AppContext
    from project_opener.ui.main_window import MainWindow

    s = Settings.load(data_dir)
    s.theme = args.theme
    s.hub_path = "" if empty else str(hub_dir)
    s.display_name = "Vikram"
    s.role = "Piping QA"
    s.density = args.density
    s.variables = {"{SERVER_ROOT}": (os.environ.get("PO_DEMO_SERVER_ROOT") or str(Path(tempfile.gettempdir()) / "po-demo-server"))}  # folder absent -> Not found
    s.update_check = False
    s.presence_udp = False
    s.first_run_done = True
    s.auto_launch_on_start = False
    s.save()
    if not empty:
        if os.environ.get("PO_DEMO_HUB") and hub_dir.exists():
            shutil.rmtree(hub_dir)            # a persistent demo hub would otherwise accumulate copies
        seed(data_dir, hub_dir)
    else:
        hub_dir.mkdir(exist_ok=True)
    ctx = AppContext(data_dir)
    theme.apply_theme(app, args.theme != "light", ctx.settings.accent, args.density)
    win = MainWindow(ctx)
    win.resize(1400, 860)
    win.show()
    ctx.start()
    QTest.qWait(1500)
    cap = Capturer(out, args.theme, args.density, args.scale)
    cap.win = win
    if empty:
        _capture_empty(cap, ctx, win, hub_dir)
    else:
        _capture_pages(cap, ctx, win)
        if args.dialogs:
            _capture_dialogs(cap, ctx, win)
        if args.states:
            _capture_states(cap, ctx, win)
    if args.keep_open:
        return app.exec()
    win.quit_app()
    QTest.qWait(200)
    return 0


if __name__ == "__main__":
    sys.exit(main())
