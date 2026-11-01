"""Headless-ish UI smoke test: seeds a demo workspace + hub, opens every page,
captures screenshots to --out and exits.  Used in CI (offscreen) and locally.

    python tools/smoke_ui.py --out build/screens [--theme light] [--keep-open]
"""
from __future__ import annotations

import argparse
import os
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


def seed(data_dir: Path, hub_dir: Path) -> None:
    from project_opener.core import models as M
    from project_opener.core.store import WorkspaceStore
    from project_opener.lan.hub import TeamHub

    store = WorkspaceStore(data_dir)
    if store.projects:
        return
    docs = Path(tempfile.gettempdir()) / "po-demo"
    docs.mkdir(exist_ok=True)
    (docs / "Line list.xlsx").write_bytes(b"demo")
    (docs / "Iso checklist.pdf").write_bytes(b"demo")
    p1 = M.Project(name="P12513 As-built isometrics", client="FST", job_number="P12513", color="#2F5BFF",
                   icon="fa5s.drafting-compass", tags=["as-built", "FST", "isometrics"],
                   description="RLM red-line cross-check lot 7", pinned_at=M.now_iso(), favorite=True,
                   items=[
                       M.Item(path=str(docs / "Iso checklist.pdf"), kind="file", group="Checking"),
                       M.Item(path=str(docs / "Line list.xlsx"), kind="file", group="Checking"),
                       M.Item(path=str(docs), kind="folder", group="Folders", label="Working folder"),
                       M.Item(path=r"\\fileserver\p12513\ISO", kind="folder", group="Folders", label="Submission share"),
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
    hub.publish(p2, description="Standard ANTEO checking bundle")
    hub.announce("Z: drive moves on Friday", "The Project share moves to the new NAS at 18:00. Mapped drives reconnect automatically.", "warning")
    hub.pulse("launched", "ANTEO Isometrics › Handover")
    hub2 = TeamHub(hub_dir, user="priya", display_name="Priya", role="Checker")
    hub2.heartbeat(current_project="P14414 GAD")
    hub2.send(M.current_user(), p3, "Have a look at the Mangala bundle before the review.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "screens"))
    ap.add_argument("--theme", default="dark")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument("--data", default="")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data_dir = Path(args.data) if args.data else Path(tempfile.mkdtemp(prefix="po-smoke-"))
    hub_dir = data_dir / "hub"
    os.environ["PO_DATA_DIR"] = str(data_dir)
    from project_opener import constants as C
    C.legacy_v1_dir = lambda: data_dir / "nolegacy"  # type: ignore[assignment]

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from project_opener.core.settings import Settings
    from project_opener.ui import theme
    from project_opener.ui.context import AppContext
    from project_opener.ui.main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    s = Settings.load(data_dir)
    s.theme = args.theme
    s.hub_path = str(hub_dir)
    s.display_name = "Vikram"
    s.role = "Piping QA"
    s.variables = {"{SERVER_ROOT}": r"\\nas01\Project"}
    s.update_check = False
    s.presence_udp = False
    s.first_run_done = True
    s.auto_launch_on_start = False
    s.save()
    seed(data_dir, hub_dir)
    ctx = AppContext(data_dir)
    theme.apply_theme(app, args.theme != "light", ctx.settings.accent)
    win = MainWindow(ctx)
    win.resize(1400, 860)
    win.show()
    ctx.start()
    QTest.qWait(1500)

    def shot(name: str) -> None:
        for toast in list(win.toasts._toasts):   # clean captures: no toast over the content
            toast.dismiss()
        QTest.qWait(500)
        pm = win.grab()
        pm.save(str(out / f"{args.theme}-{name}.png"))
        print("captured", name)

    shot("home")
    win.go("projects")
    shot("projects")
    win.ctx.settings.view_mode = "list"
    win.pages["projects"].refresh()
    shot("projects-list")
    win.ctx.settings.view_mode = "grid"
    first = ctx.store.projects[0]
    win.open_project(first)
    for _ in range(20):           # wait for the path-health pass so the pills show real states
        if all(ctx.health_for(p.id) is not None for p in ctx.store.projects):
            break
        QTest.qWait(250)
    QTest.qWait(300)
    shot("project")
    win.go("team")
    QTest.qWait(800)
    shot("team")
    win.go("updates")
    shot("updates")
    win.go("settings")
    shot("settings")
    win.go("home")
    win.open_palette()
    QTest.qWait(300)
    win.palette.edit.setText("check")
    QTest.qWait(300)
    from PySide6.QtGui import QPainter
    pm = win.grab()
    painter = QPainter(pm)
    painter.drawPixmap(win.palette.pos() - win.pos(), win.palette.grab())
    painter.end()
    pm.save(str(out / f"{args.theme}-palette.png"))
    win.palette.reject()
    print("captured palette")
    if args.keep_open:
        return app.exec()
    win.quit_app()
    QTest.qWait(200)
    return 0


if __name__ == "__main__":
    sys.exit(main())
