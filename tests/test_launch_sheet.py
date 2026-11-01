"""The launch sheet and the per-item progress behind it: launcher callbacks in order, the
context's LaunchRun signals on the GUI thread, the status mapping, auto-close only when every
item opened, Esc, and the launch-set pills."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.core import winutil  # noqa: E402
from project_opener.core.launcher import Launcher, LaunchReport, LaunchResult  # noqa: E402
from project_opener.core.pathvars import PathResolver  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(app, isolated_data_dir):
    from project_opener.ui.context import AppContext
    c = AppContext(isolated_data_dir)
    c.launcher = Launcher(c.resolver, delay_ms=0, dry_run=True)   # nothing is really opened
    c.settings.show_toasts = True
    return c


def _project(tmp_path, offline=True) -> M.Project:
    real = tmp_path / "exists.pdf"
    real.write_text("x", encoding="utf-8")
    items = [
        M.Item(path=str(real), kind="file", group="Checking"),
        M.Item(path=str(tmp_path / "missing.xlsx"), kind="file", group="Checking"),
        M.Item(path="https://example.com", kind="url", group="Links"),
        M.Item(path=r"{UNDEFINED}\x.docx", kind="file", group="References"),
    ]
    if offline:
        items.append(M.Item(path=r"\\nas-not-here\share\ISO", kind="folder", group="Folders", label="Share"))
    p = M.Project(name="P1 Test", client="FST", job_number="P1", items=items)
    p.launch_sets.append(M.LaunchSet(name="Checking", item_ids=[items[0].id, items[1].id]))
    return p


def _wait_done(run, ms=5000) -> None:
    for _ in range(ms // 20):
        if run.done:
            break
        QTest.qWait(20)
    QTest.qWait(50)
    assert run.done


# ------------------------------------------------------------ launcher
def test_launcher_reports_each_item_in_order_with_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(winutil, "host_reachable", lambda host, timeout=0.8: False)
    p = _project(tmp_path)
    seen: list[tuple[int, str]] = []
    started: list[int] = []
    rep = Launcher(PathResolver({}, drive_map={}), delay_ms=0, dry_run=True).launch(
        p.items, progress=lambda i, r: seen.append((i, r.code)), starting=started.append)
    assert started == [0, 1, 2, 3, 4]
    assert seen == [(0, "opened"), (1, "missing"), (2, "opened"), (3, "variable"), (4, "offline")]
    # the coarse status the history counts is unchanged: offline and variable are both "missing"
    assert [r.status for r in rep.results] == ["opened", "missing", "opened", "missing", "missing"]
    assert rep.summary() == "2 opened, 3 missing"


# ------------------------------------------------------------- context
def test_context_launch_runs_on_worker_and_signals_in_order(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(winutil, "host_reachable", lambda host, timeout=0.8: False)
    p = _project(tmp_path)
    ctx.store.add(p)
    ctx.settings.hub_share_pulse = False
    events: list = []
    toasts: list = []
    ctx.toast.connect(lambda a, b, c: toasts.append((a, c)))
    ctx.launch_started.connect(lambda run: events.append(("started", len(run.items))))
    run = ctx.launch(p)
    assert run is not None
    run.item_started.connect(lambda i: events.append(("try", i)))
    run.item_finished.connect(lambda i, r: events.append(("done", i, r.code)))
    run.finished.connect(lambda rep: events.append(("finished", rep.summary())))
    _wait_done(run)
    assert events[0] == ("started", 5)
    body = events[1:-1]
    assert body == [("try", 0), ("done", 0, "opened"), ("try", 1), ("done", 1, "missing"),
                    ("try", 2), ("done", 2, "opened"), ("try", 3), ("done", 3, "variable"),
                    ("try", 4), ("done", 4, "offline")]
    assert events[-1] == ("finished", "2 opened, 3 missing")
    assert run.elapsed >= 0
    # history, open count and the summary toast (no sheet took this run) behave as before
    assert ctx.store.get(p.id).open_count == 1
    assert ctx.store.history()[0]["ok"] == 2 and ctx.store.history()[0]["missing"] == 3
    assert toasts and toasts[-1][1] == "warning"


def test_context_skips_summary_toast_when_a_sheet_took_the_run(ctx, tmp_path):
    p = _project(tmp_path, offline=False)
    ctx.store.add(p)
    ctx.settings.hub_share_pulse = False
    toasts: list = []
    ctx.toast.connect(lambda a, b, c: toasts.append(a))
    ctx.launch_started.connect(lambda run: setattr(run, "sheet_shown", True))
    run = ctx.launch(p)
    _wait_done(run)
    assert toasts == []
    assert ctx.store.get(p.id).open_count == 1


def test_context_nothing_to_open_is_unchanged(ctx):
    p = M.Project(name="Empty", items=[M.Item(path="  ")])
    toasts: list = []
    ctx.toast.connect(lambda a, b, c: toasts.append(a))
    assert ctx.launch(p) is None
    assert toasts == ["Nothing to open"]


# --------------------------------------------------------------- sheet
def test_status_pill_mapping():
    from project_opener.ui.widgets.launch_sheet import footer_text, pill_for
    it = M.Item(path=r"C:\x.pdf")
    assert pill_for(LaunchResult(it, "", "opened")) == ("ok", "Opened")
    assert pill_for(LaunchResult(it, "", "missing", "path not found")) == ("warn", "Not found")
    assert pill_for(LaunchResult(it, "", "missing", "nas is not reachable", code="offline")) == ("bad", "Server offline")
    assert pill_for(LaunchResult(it, "", "missing", "unknown variable", code="variable")) == ("warn", "Undefined variable")
    assert pill_for(LaunchResult(it, "", "skipped")) == ("neutral", "Skipped")
    assert pill_for(LaunchResult(it, "", "failed", "boom")) == ("bad", "Failed")
    main, rest = footer_text([LaunchResult(it, "", "opened"), LaunchResult(it, "", "missing"), None], 1.84)
    assert (main, rest) == ("1 opened", " · 1 not opened · 1.8 s")


@pytest.fixture
def host(app):
    w = QWidget()
    w.resize(1200, 800)
    w.show()
    yield w
    w.close()


def _sheet(host, auto_close_ms=60):
    from project_opener.ui.widgets.launch_sheet import LaunchSheet
    return LaunchSheet(host, area_fn=lambda: QRect(240, 0, 960, 800), auto_close_ms=auto_close_ms)


def test_sheet_follows_a_run_and_auto_closes_only_when_everything_opened(ctx, host, tmp_path, monkeypatch):
    monkeypatch.setattr(winutil, "host_reachable", lambda host, timeout=0.8: False)
    ctx.settings.hub_share_pulse = False
    sheet = _sheet(host, auto_close_ms=300)
    mixed = _project(tmp_path)
    ctx.store.add(mixed)
    run = ctx.launch(mixed)
    sheet.begin(run)
    assert sheet.isVisible()
    assert sheet.title.text() == "Opening P1 Test"
    assert sheet.subtitle.text() == "5 items · FST"      # the job number now leads the title
    assert len(sheet.rows) == 5
    _wait_done(run)
    pills = [(r.pill.text(), r.pill._level) for r in sheet.rows]
    assert pills == [("Opened", "ok"), ("Not found", "warn"), ("Opened", "ok"),
                     ("Undefined variable", "warn"), ("Server offline", "bad")]
    assert sheet.rows[4].pill.toolTip() == "nas-not-here is not reachable"
    assert sheet.foot_main.text() == "2 opened"
    assert sheet.foot_rest.text().startswith(" · 3 not opened")      # elapsed omitted under 0.1 s
    QTest.qWait(200)
    assert sheet.isVisible()                       # something did not open: it stays
    # centred over the content area, not the sidebar
    assert sheet.x() >= 240 and abs((sheet.x() + sheet.width() // 2) - (240 + 480)) <= 1
    # a second launch replaces the content; every item opens -> closes itself
    ok = _project(tmp_path, offline=False)
    ok.items = ok.items[:1] + ok.items[2:3]
    ok.name = "P2 All good"
    ctx.store.add(ok)
    run2 = ctx.launch(ok)
    sheet.begin(run2)
    assert sheet.title.text() == "Opening P1 · P2 All good" and len(sheet.rows) == 2   # job number first
    _wait_done(run2)
    assert all(r.pill.text() == "Opened" for r in sheet.rows)
    assert sheet.isVisible()                       # not yet: it closes itself after auto_close_ms
    QTest.qWait(600)
    assert not sheet.isVisible()


def test_sheet_esc_and_close_button_dismiss(ctx, host, tmp_path):
    ctx.settings.hub_share_pulse = False
    sheet = _sheet(host, auto_close_ms=0)
    p = _project(tmp_path, offline=False)
    ctx.store.add(p)
    closed: list = []
    sheet.closed.connect(lambda: closed.append(1))
    run = ctx.launch(p)
    sheet.begin(run)
    _wait_done(run)
    assert sheet.isVisible()
    QTest.keyClick(sheet, Qt.Key.Key_Escape)
    assert not sheet.isVisible() and closed == [1]
    sheet.begin(ctx.launch(p))
    assert sheet.isVisible()
    sheet.close_btn.click()
    assert not sheet.isVisible() and closed == [1, 1]
    # the close button and the launch-set pills take keyboard focus (Tab reaches them)
    assert sheet.close_btn.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert sheet._set_buttons and all(b.focusPolicy() == Qt.FocusPolicy.StrongFocus for b in sheet._set_buttons)


def test_sheet_launch_set_pill_starts_that_set(ctx, host, tmp_path):
    ctx.settings.hub_share_pulse = False
    sheet = _sheet(host, auto_close_ms=0)
    p = _project(tmp_path, offline=False)
    ctx.store.add(p)
    asked: list = []
    sheet.set_requested.connect(lambda proj, ls: asked.append((proj.id, ls.name)))
    run = ctx.launch(p)
    sheet.begin(run)
    _wait_done(run)
    assert [b.text() for b in sheet._set_buttons] == ["Checking"]
    sheet._set_buttons[0].click()
    assert asked == [(p.id, "Checking")]


def test_main_window_shows_sheet_and_pill_launches_the_set(ctx, tmp_path):
    from project_opener.ui.main_window import MainWindow
    ctx.settings.hub_share_pulse = False
    ctx.settings.show_toasts = False                # the sheet is feedback, not a notification
    p = _project(tmp_path, offline=False)
    ctx.store.add(p)
    win = MainWindow(ctx)
    win.show()
    QTest.qWait(100)
    run = ctx.launch(p, parent=win)
    assert run.sheet_shown
    _wait_done(run)
    assert win.sheet is not None and win.sheet.isVisible()
    assert win.sheet.x() >= win.stack.x()
    assert win.toasts._toasts == []
    win.sheet._set_buttons[0].click()
    run2 = win.sheet.run
    assert run2 is not run and run2.set_name == "Checking" and len(run2.items) == 2
    assert win.sheet.subtitle.text() == "2 items · Checking · FST"
    _wait_done(run2)
    win.sheet.dismiss()
    # hidden window: no sheet, the summary toast path is used (tray balloon / toast)
    win.hide()
    toasts: list = []
    ctx.toast.connect(lambda a, b, c: toasts.append(a))
    run3 = ctx.launch(p)
    assert not run3.sheet_shown
    _wait_done(run3)
    assert toasts == ["P1 Test: 2 opened, 2 missing"]
    win.quit_app()


def test_launch_report_from_results():
    it = M.Item(path=r"C:\x.pdf")
    rep = LaunchReport([LaunchResult(it, "", "opened"), LaunchResult(it, "", "failed", "x")])
    assert not rep.ok and len(rep.failed) == 1
