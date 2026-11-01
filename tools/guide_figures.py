"""Capture the figures for docs/guide at 2x from the seeded demo workspace.

    set QT_QPA_PLATFORM=offscreen
    python tools/guide_figures.py [--out docs/guide/figures] [--theme light]

Reuses tools/smoke_ui.py (seed data, message handler).  Every figure is a
direct grab of the widget it documents (a dialog, the full-height Settings
page, the tray menu, the palette), not a crop of the window, so the PDF
shows each control at its native size.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    if fonts.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))

import smoke_ui  # noqa: E402  (tools/smoke_ui.py)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "guide" / "figures"))
    ap.add_argument("--theme", default="light")
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    smoke_ui._install_message_handler()
    app = QApplication(sys.argv)

    data_dir = Path(tempfile.mkdtemp(prefix="po-guide-"))
    hub_dir = Path(os.environ["PO_DEMO_HUB"]) if os.environ.get("PO_DEMO_HUB") else data_dir / "hub"
    if hub_dir.exists() and os.environ.get("PO_DEMO_HUB"):
        import shutil
        shutil.rmtree(hub_dir, ignore_errors=True)   # a fresh hub every run: no duplicated demo items
    os.environ["PO_DATA_DIR"] = str(data_dir)
    # Captures must never show this PC's real drive mappings (office servers):
    # the demo drive map stands in for them.  Set PO_DEMO_DRIVES=0 to disable.
    if os.environ.get("PO_DEMO_DRIVES", "1") != "0":
        from project_opener.core import winutil
        winutil.mapped_drives = lambda: {"Z:": r"\\nas01\Project", "W:": r"\\nas01\Submissions"}
    from project_opener import constants as C
    C.legacy_v1_dir = lambda: data_dir / "nolegacy"  # type: ignore[assignment]
    from project_opener.core.settings import Settings
    from project_opener.ui import theme
    from project_opener.ui.context import AppContext
    from project_opener.ui.main_window import MainWindow
    from project_opener.ui.widgets import dialogs as D

    s = Settings.load(data_dir)
    s.theme = args.theme
    s.hub_path = str(hub_dir)
    s.display_name = "Vikram"
    s.role = "Piping QA"
    s.variables = {"{SERVER_ROOT}": (os.environ.get("PO_DEMO_SERVER_ROOT") or str(Path(tempfile.gettempdir()) / "po-demo-server"))}
    s.update_check = False
    s.presence_udp = False
    s.first_run_done = True
    s.auto_launch_on_start = False
    s.save()
    smoke_ui.seed(data_dir, hub_dir)
    ctx = AppContext(data_dir)
    theme.apply_theme(app, args.theme != "light", ctx.settings.accent, "comfortable")
    win = MainWindow(ctx)
    win.resize(1400, 860)
    win.show()
    ctx.start()
    QTest.qWait(1500)
    smoke_ui._wait_health(ctx)

    def save(name: str, pm) -> None:
        pm.save(str(out / f"{name}.png"))
        print("figure", name, pm.width(), "x", pm.height())

    def window(name: str, overlay=None) -> None:
        for toast in list(win.toasts._toasts):
            toast.dismiss()
        QTest.qWait(500)
        pm = win.grab()
        if overlay is not None and overlay.isVisible():
            p = QPainter(pm)
            p.drawPixmap(overlay.pos() - win.pos(), overlay.grab())
            p.end()
        save(name, pm)

    def widget(name: str, w) -> None:
        QTest.qWait(300)
        save(name, w.grab())

    first = ctx.store.projects[0]

    # Pages
    win.go("home")
    QTest.qWait(600)
    window("fig-home")
    window("fig-window")
    win.go("projects")
    QTest.qWait(600)
    window("fig-projects")
    page = win.pages["projects"]
    from project_opener.ui.widgets.cards import ProjectCard
    cards = page.findChildren(ProjectCard)
    if cards:
        widget("fig-card", cards[0])
    win.open_project(first)
    QTest.qWait(600)
    smoke_ui._wait_health(ctx)
    window("fig-detail")
    detail = win.pages["project"]
    widget("fig-item-rows", detail.items_panel)
    win.go("team")
    QTest.qWait(600)
    window("fig-team")
    team = win.pages["team"]
    team.tabs.setCurrentIndex(1)
    QTest.qWait(400)
    widget("fig-inbox", team.tab_inbox)
    team.tabs.setCurrentIndex(0)
    ctx.settings.update_check = True      # the sentence colleagues see; the timer stays off
    win.go("updates")
    QTest.qWait(600)
    for toast in list(win.toasts._toasts):
        toast.dismiss()
    QTest.qWait(400)
    pm = win.grab()
    upd = win.pages["updates"]
    y_diag = upd.body.findChildren(QLabel)
    cut = None
    for lbl in y_diag:
        if lbl.text() == "Diagnostics":
            cut = lbl.mapTo(win, QPoint(0, 0)).y() - 28
    if cut:
        pm = pm.copy(0, 0, pm.width(), int(cut * pm.devicePixelRatio()))
    save("fig-updates", pm)
    win.go("settings")
    QTest.qWait(600)
    settings = win.pages["settings"]
    inner = settings.body
    QTest.qWait(300)
    pm = inner.grab()
    save("fig-settings-full", pm)
    dpr = pm.devicePixelRatio()
    ys = {k: w.mapTo(inner, QPoint(0, 0)).y() for k, w in settings._anchors.items()}
    print("anchors", ys)

    def crop(name, y0, y1):
        r = pm.copy(0, int(max(0, y0 - 6) * dpr), pm.width(), int((y1 - max(0, y0 - 6)) * dpr))
        save(name, r)
    crop("fig-settings-1", ys["profile"], ys["behaviour"] - 10)
    crop("fig-settings-2", ys["behaviour"], ys["variables"] - 10)
    crop("fig-settings-3", ys["variables"], ys["data"] - 10)   # the data card names a temp folder in captures

    # Empty workspace Home: temporarily hide projects
    # (captured by smoke --empty instead; see guide-figures-empty)

    # Dialogs, grabbed directly
    win.open_project(first)
    QTest.qWait(400)
    page = win.pages["project"]
    peers = [p.user for p in ctx.peers if p.user != ctx.user] or ["priya", "ravi"]
    specs = [
        ("fig-project-editor", lambda: D.ProjectEditor(None, ctx.store.all_tags(), win, is_new=True)),
        ("fig-item-editor", lambda: D.ItemEditor(None, first.groups(), page)),
        ("fig-launchset-editor", lambda: D.LaunchSetEditor(first, None, page)),
        ("fig-send", lambda: D.SendToDialog(first, peers, win)),
        ("fig-announce", lambda: D.AnnouncementDialog(win)),
        ("fig-publish", lambda: D.PublishDialog(first, win)),
    ]
    for name, make in specs:
        dlg = make()
        if name == "fig-project-editor":
            dlg.name.setText("P12513 As-built isometrics")
            dlg.client.setText("FST")
            dlg.job.setText("P12513")
            dlg.description.setText("RLM red-line cross-check lot 7")
        if name == "fig-item-editor":
            dlg.path.setText(r"{SERVER_ROOT}\P12513\Rulings.docx")
            dlg.label.setText("Rulings")
        dlg.show()
        dlg.adjustSize()
        QTest.qWait(500)
        widget(name, dlg)
        dlg.close()
        dlg.deleteLater()
        QTest.qWait(100)

    # Palette with a query
    win.go("home")
    QTest.qWait(300)
    win.open_palette()
    QTest.qWait(300)
    pal = win.palette
    if pal is not None:
        pal.edit.setText("check")
        QTest.qWait(400)
        widget("fig-palette", pal)
        pal.close()

    # Tray menu
    try:
        menu = win.tray.contextMenu()
        menu.popup(win.mapToGlobal(QPoint(300, 300)))
        QTest.qWait(300)
        widget("fig-tray", menu)
        menu.close()
    except Exception as exc:  # pragma: no cover
        print("tray menu not captured:", exc)

    # Launch sheet (finished state with mixed results), dry run so nothing really opens
    from project_opener.core.launcher import Launcher
    real = ctx.launcher
    ctx.launcher = Launcher(ctx.resolver, delay_ms=120, dry_run=True)
    win.go("home")
    QTest.qWait(300)
    run = ctx.launch(first, parent=win)
    for _ in range(80):
        QTest.qWait(250)
        if run is not None and getattr(run, "done", False):
            break
    QTest.qWait(400)
    if win.sheet is not None and win.sheet.isVisible():
        widget("fig-launch", win.sheet)
        window("fig-launch-window", overlay=win.sheet)
    ctx.launcher = real

    win.quit_app()
    QTest.qWait(200)
    if smoke_ui.QT_MESSAGES:
        print(f"{len(smoke_ui.QT_MESSAGES)} Qt warning(s):")
        for m in smoke_ui.QT_MESSAGES:
            print("  " + m)
    else:
        print("no Qt warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
