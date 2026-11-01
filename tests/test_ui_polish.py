"""Offscreen UI tests for the design pass: dialogs, confirm defaults, palette grouping,
sidebar collapse, the Home finding line, deep-link decoding and the update toast."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.core.health import ItemHealth, ProjectHealth  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _settle() -> None:
    """Deliver deferred deletes so rebuilt rows do not leave stale widgets behind."""
    from PySide6.QtCore import QEvent
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


@pytest.fixture
def ctx(app, isolated_data_dir):
    from project_opener.ui.context import AppContext
    return AppContext(isolated_data_dir)


# ------------------------------------------------------------------ dialogs
def test_project_editor_says_create_for_a_template(app):
    from project_opener.ui.widgets.dialogs import ProjectEditor
    template = M.Project(name="Dropped", items=[M.Item(path=r"C:\x.pdf")])
    dlg = ProjectEditor(template, [], is_new=True)
    assert dlg.windowTitle() == "New project"
    assert dlg.heading.text() == "New project"
    assert dlg.ok_btn.text() == "Create project"
    assert dlg.ok_btn.isDefault()
    edit = ProjectEditor(template, [])
    assert edit.ok_btn.text() == "Save"


def test_project_editor_validates_inline(app):
    from project_opener.ui.widgets.dialogs import ProjectEditor
    dlg = ProjectEditor(None, [])
    dlg.show()
    dlg.accept()                                   # empty name: stays open, says why, no message box
    assert dlg.isVisible()
    assert dlg.error_label.isVisible()
    assert dlg.name.property("invalid") == "true"
    dlg.name.setText("P1")
    dlg.name.textEdited.emit("P1")
    assert not dlg.error_label.isVisible()
    dlg.accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.project.name == "P1"


def test_tag_editor_enter_adds_without_submitting(app):
    from project_opener.ui.widgets.dialogs import ProjectEditor
    dlg = ProjectEditor(None, ["GAD"])
    dlg.name.setText("P1")
    dlg.show()
    dlg.tags.edit.setFocus()
    dlg.tags.edit.setText("as-built")
    QTest.keyClick(dlg.tags.edit, Qt.Key.Key_Return)
    assert dlg.tags.tags == ["as-built"]
    assert dlg.isVisible() and dlg.result() != QDialog.DialogCode.Accepted
    # a suggestion chip adds the tag; the chip then disappears from the suggestions
    chips = [dlg.tags.flow.itemAt(i).widget() for i in range(dlg.tags.flow.count())]
    sug = next(c for c in chips if c.text() == "+ GAD")
    sug.click()
    assert dlg.tags.tags == ["as-built", "GAD"]


def test_item_editor_and_launch_set_validation(app):
    from project_opener.ui.widgets.dialogs import ItemEditor, LaunchSetEditor
    dlg = ItemEditor(None, [])
    dlg.accept()
    assert dlg.error_label.text().startswith("Enter a path")
    p = M.Project(name="P", items=[M.Item(path=r"C:\a.pdf")])
    ls = LaunchSetEditor(p, None)
    ls.name.setText("Checking")
    ls._set_all(False)
    ls.accept()
    assert ls.error_label.text() == "Select at least one item."
    ls._set_all(True)
    ls.accept()
    assert ls.result() == QDialog.DialogCode.Accepted and ls.set.item_ids == [p.items[0].id]


def test_confirm_dialog_defaults(app):
    from project_opener.ui.widgets.dialogs import confirm_box
    dlg, ok = confirm_box(None, "Delete project", "Delete 'P1'?", danger=True, ok_text="Delete project")
    assert ok.text() == "Delete project" and ok.objectName() == "danger"
    assert dlg.cancel_btn.isDefault() and not ok.isDefault()     # Enter never deletes
    safe, ok2 = confirm_box(None, "Update from Team Hub", "Replace?", ok_text="Replace with revision 2")
    assert ok2.isDefault() and ok2.objectName() == "primary"


# ----------------------------------------------------------------- palette
def test_palette_groups_results_and_skips_headings(app, ctx):
    from project_opener.ui.main_window import PALETTE_ACTIONS
    from project_opener.ui.widgets.palette import CommandPalette
    ctx.store.add(M.Project(name="Checking job", items=[M.Item(path=r"C:\check.pdf")]))
    pal = CommandPalette(None, lambda: ctx.store.projects, PALETTE_ACTIONS)
    pal._refresh("check")
    kinds = [None if h is None else h.kind for h in pal._rows]
    assert kinds[0] is None and "project" in kinds and "action" in kinds
    first = pal.list.currentRow()
    assert pal._rows[first] is not None                      # selection starts on a hit, not a heading
    pal._step(-1)
    assert pal.list.currentRow() == first                    # cannot move onto the heading above
    pal._refresh("zzzz-nothing")
    assert "Nothing matches" in pal.footer.text()


# ----------------------------------------------------------------- sidebar
def test_sidebar_hub_line_collapses_to_a_dot(app):
    from project_opener.ui.widgets.sidebar import Sidebar
    sb = Sidebar("Vikram", collapsed=False)
    sb.set_hub_text("Hub connected · 3 online", True)
    assert "Hub connected" in sb.hub_dot.text()
    sb.toggle()
    assert "Hub connected" not in sb.hub_dot.text() and "●" in sb.hub_dot.text()
    assert sb.hub_dot.toolTip() == "Hub connected · 3 online"
    sb.toggle()
    assert "Hub connected" in sb.hub_dot.text()


# -------------------------------------------------------------------- home
def test_home_finding_counts_paths_and_projects(app, ctx):
    from project_opener.ui.views.home import HomePage
    p1 = M.Project(name="A", items=[M.Item(path=r"C:\a"), M.Item(path=r"C:\b")])
    p2 = M.Project(name="B", items=[M.Item(path=r"C:\c")])
    ctx.store.add(p1)
    ctx.store.add(p2)
    ctx.health[p1.id] = ProjectHealth(p1.id, [ItemHealth(p1.items[0].id, "missing", r"C:\a"),
                                              ItemHealth(p1.items[1].id, "offline", r"C:\b")])
    ctx.health[p2.id] = ProjectHealth(p2.id, [ItemHealth(p2.items[0].id, "ok", r"C:\c")])
    page = HomePage(ctx)
    assert page.subtitle_label.text().startswith("2 paths need attention in 1 project")
    ctx.health[p2.id] = ProjectHealth(p2.id, [ItemHealth(p2.items[0].id, "missing", r"C:\c")])
    page._render_finding()
    assert page.subtitle_label.text().startswith("3 paths need attention in 2 projects")


# ------------------------------------------------------------- deep links
def test_deep_link_key_is_url_decoded():
    from project_opener.app import deep_link_key
    assert deep_link_key("projectopener://open/P12513%20As-built%20isometrics/") == "P12513 As-built isometrics"
    assert deep_link_key("projectopener://open/abc123") == "abc123"
    assert deep_link_key("https://example.com") == ""
    assert deep_link_key("") == ""


# ----------------------------------------------------------- update toast
def test_update_toast_says_when_checksum_was_not_provided(app, ctx, tmp_path):
    from project_opener.ui.views.updates import UpdatesPage
    from project_opener.update.updater import CheckResult, UpdateInfo
    page = UpdatesPage(ctx)
    toasts: list[tuple[str, str, str]] = []
    ctx.toast.connect(lambda a, b, c: toasts.append((a, b, c)))
    inst = tmp_path / "ProjectOpener-9.9.9-setup.exe"
    inst.write_bytes(b"x")
    ctx.last_check = CheckResult(update=UpdateInfo(version="9.9.9", installer=inst.name, sha256=""))
    page._ready(inst)
    assert "not provided" in toasts[-1][1] and toasts[-1][2] == "warning"
    ctx.last_check = CheckResult(update=UpdateInfo(version="9.9.9", installer=inst.name, sha256="a" * 64))
    page._ready(inst)
    assert toasts[-1][1].startswith("SHA-256 verified") and toasts[-1][2] == "success"


# ------------------------------------------------------------ round 2
def test_launch_sheet_footer_separates_not_opened_from_skipped():
    from project_opener.core.launcher import LaunchResult
    from project_opener.ui.widgets.launch_sheet import footer_text
    it = M.Item(path=r"C:\a")
    rs = [LaunchResult(it, "", "opened"), LaunchResult(it, "", "missing", code="offline"),
          LaunchResult(it, "", "skipped"), LaunchResult(it, "", "failed")]
    assert footer_text(rs, 2.0) == ("1 opened", " · 2 not opened · 1 skipped · 2.0 s")


def test_flow_last_row_spans_and_rows_are_level(app):
    from PySide6.QtWidgets import QLabel, QWidget

    from project_opener.ui.widgets.flow import FlowLayout
    host = QWidget()
    flow = FlowLayout(host, 0, 16, 16, justify=True, max_columns=3)
    cards = []
    for i in range(5):
        c = QLabel("x" * (3 + i))
        c.setMinimumWidth(300)
        c.setMinimumHeight(100 + 20 * (i % 2))
        flow.addWidget(c)
        cards.append(c)
    host.resize(3 * 300 + 2 * 16, 600)
    flow.setGeometry(host.rect())
    first = [c.geometry() for c in cards[:3]]
    assert len({g.height() for g in first}) == 1                       # one bottom edge per row
    assert cards[3].geometry().width() == cards[4].geometry().width()
    assert cards[3].geometry().width() == (932 - 16) // 2               # the last two share the row


def test_hub_display_name_for(hub_root):
    from project_opener.lan.hub import TeamHub
    other = TeamHub(hub_root, user="priya", display_name="Priya", role="Checker")
    other.initialise()
    other.heartbeat()
    mine = TeamHub(hub_root, user="vikram", display_name="Vikram")
    assert mine.display_name_for("priya") == "Priya"
    assert mine.display_name_for("vikram") == "Vikram"
    assert mine.display_name_for("nobody") == "nobody"
    assert mine.display_name_for("") == ""


def test_home_attention_rows_carry_the_status_pill(app, ctx):
    from project_opener.ui.views.home import HomePage
    from project_opener.ui.widgets.common import Badge
    p = M.Project(name="A", items=[M.Item(path=r"\nas\x", kind="folder", label="Share"), M.Item(path=r"C:\b")])
    ctx.store.add(p)
    ctx.health[p.id] = ProjectHealth(p.id, [ItemHealth(p.items[0].id, "offline", r"\nas\x"),
                                            ItemHealth(p.items[1].id, "ok", r"C:\b")])
    page = HomePage(ctx)
    pills = [b.text() for b in page.attention_panel.findChildren(Badge)]
    assert pills == ["Server offline"]
    assert ctx.store.projects and page.attention_panel.findChildren(Badge)[0].toolTip() == r"\nas\x"


def test_home_empty_workspace_has_no_false_complies(app, ctx):
    from PySide6.QtWidgets import QLabel

    from project_opener.ui.views.home import HomePage
    page = HomePage(ctx)
    texts = [w.text() for w in page.drives_panel.findChildren(QLabel)]
    assert "No paths to check yet." in texts
    assert not page.attention_panel.isVisibleTo(page)          # nothing to list by symptom
    assert page.subtitle_label.text() == "Nothing to open yet"


def test_open_project_disabled_without_items(app, ctx):
    from project_opener.ui.views.detail import ProjectPage
    p = M.Project(name="Bare")
    ctx.store.add(p)
    page = ProjectPage(ctx)
    page.load(p)
    assert not page.launch_btn.isEnabled() and page.launch_btn.toolTip() == "Add an item first"
    p2 = M.Project(name="Full", items=[M.Item(path=r"C:\a")])
    ctx.store.add(p2)
    page.load(p2)
    assert page.launch_btn.isEnabled()


def test_detail_stacks_side_column_when_narrow(app, ctx):
    from PySide6.QtWidgets import QBoxLayout

    from project_opener.ui.views.detail import ProjectPage
    page = ProjectPage(ctx)
    page.show()                                   # resize events are delivered to shown widgets only
    page.resize(1300, 700)
    QApplication.processEvents()
    assert page.cols.direction() == QBoxLayout.Direction.LeftToRight
    page.resize(900, 700)
    QApplication.processEvents()
    assert page.cols.direction() == QBoxLayout.Direction.TopToBottom


def test_sidebar_has_one_new_project_control_and_no_version_stamp(app):
    from PySide6.QtWidgets import QLabel, QPushButton

    from project_opener.ui.widgets.sidebar import Sidebar
    sb = Sidebar("Vikram")
    assert not [b for b in sb.findChildren(QPushButton) if b.text() == "New project"]
    assert not [w for w in sb.findChildren(QLabel) if w.text().startswith("v")]


def test_card_subtitle_never_blank(app):
    from project_opener.ui.widgets.cards import ProjectCard, kinds_summary
    p = M.Project(name="Tools", items=[M.Item(path="https://a", kind="url"), M.Item(path="cmd: x", kind="command"),
                                        M.Item(path="https://b", kind="url")])
    assert kinds_summary(p) == "2 links · 1 command"
    assert ProjectCard(p).subtitle.text() == "2 links · 1 command"
    assert ProjectCard(p).meta.text() == "3 items · never opened"
    p.items[0].enabled = False
    p.last_opened = M.now_iso()
    assert ProjectCard(p).meta.text() == "2 of 3 items · opened just now"


# ------------------------------------------------------------ round 3
def test_title_puts_the_job_number_first():
    assert M.Project(name="As-built isometrics", job_number="P12513", client="FST").title == "P12513 · As-built isometrics"
    assert M.Project(name="ANTEO Isometrics", client="ANTEO").title == "ANTEO Isometrics"      # client already in the name
    assert M.Project(name="Pipe rack", client="Cairn").title == "Cairn · Pipe rack"
    assert M.Project(name="Office tools").title == "Office tools"


def test_roots_group_health_by_cause(monkeypatch):
    from project_opener.core import health as H
    from project_opener.core.health import path_root, roots_health
    monkeypatch.setattr(H, "drive_exists", lambda _r: False)        # no drive letter of this PC answers
    assert path_root(r"Z:\Project\x") == "Z:" and path_root(r"{SERVER_ROOT}\a") == "{SERVER_ROOT}"
    assert path_root(r"\\nas01\Project\P") == r"\\nas01" and path_root("https://x") == ""
    a = M.Project(name="A", items=[M.Item(path=r"Z:\a"), M.Item(path=r"Z:\b"), M.Item(path=r"\\nas01\x\y")])
    b = M.Project(name="B", items=[M.Item(path=r"D:\ok.pdf"), M.Item(path=r"D:\gone.pdf")])
    health = {
        a.id: ProjectHealth(a.id, [ItemHealth(a.items[0].id, "missing", ""), ItemHealth(a.items[1].id, "missing", ""),
                                   ItemHealth(a.items[2].id, "offline", "")]),
        b.id: ProjectHealth(b.id, [ItemHealth(b.items[0].id, "ok", ""), ItemHealth(b.items[1].id, "missing", "")]),
    }
    roots = roots_health([a, b], health)
    assert [(r.root, r.status, len(r.projects), r.items) for r in roots] == [
        (r"\\nas01", "offline", 1, 1), ("Z:", "missing", 1, 2), ("D:", "ok", 1, 2)]   # D: answers: one file gone


def test_home_drives_block_and_unexplained_rows(app, ctx, monkeypatch):
    from project_opener.core import health as H
    from project_opener.ui.views.home import HomePage
    monkeypatch.setattr(H, "drive_exists", lambda _r: False)
    from project_opener.ui.widgets.common import Badge
    a = M.Project(name="A", job_number="P1", items=[M.Item(path=r"Z:\a"), M.Item(path=r"D:\gone.pdf"), M.Item(path=r"D:\ok.pdf")])
    ctx.store.add(a)
    ctx.health[a.id] = ProjectHealth(a.id, [ItemHealth(a.items[0].id, "missing", ""), ItemHealth(a.items[1].id, "missing", ""),
                                            ItemHealth(a.items[2].id, "missing", "")])
    page = HomePage(ctx)
    drive_pills = [b.text() for b in page.drives_panel.findChildren(Badge)]
    assert drive_pills == ["Not found", "Not found"]            # Z: and D: both unanswered on this PC
    assert not page.attention_panel.isVisibleTo(page)            # every problem is explained by its root
    ctx.health[a.id] = ProjectHealth(a.id, [ItemHealth(a.items[0].id, "ok", ""), ItemHealth(a.items[1].id, "missing", ""),
                                            ItemHealth(a.items[2].id, "ok", "")])        # D: answers; one file is gone
    page.refresh()
    assert page.attention_panel.isVisibleTo(page)
    assert [b.text() for b in page.attention_panel.findChildren(Badge)] == ["Not found"]


def test_launch_set_order_is_persisted_and_editable(app):
    from project_opener.ui.views.detail import steps_line
    from project_opener.ui.widgets.dialogs import LaunchSetEditor
    p = M.Project(name="P", items=[M.Item(path=r"C:\a.pdf", group="Checking"), M.Item(path=r"C:\b.xlsx", group="Checking"),
                                    M.Item(path=r"C:\c", kind="folder", group="Folders")])
    ls = M.LaunchSet(name="Checking", item_ids=[p.items[1].id, p.items[0].id])
    assert [i.display_name for i in p.items_for_set(ls)] == ["b.xlsx", "a.pdf"]        # the set's own order
    assert steps_line(p, ls) == "1 b.xlsx · 2 a.pdf"
    dlg = LaunchSetEditor(p, ls)
    assert [dlg.list.item(i).text().split("   ")[0] for i in range(3)] == ["b.xlsx", "a.pdf", "c"]
    dlg.list.setCurrentRow(1)
    dlg.move_current(-1)
    dlg.accept()
    assert ls.item_ids == [p.items[0].id, p.items[1].id]


def test_launch_sheet_numbers_steps_under_group_labels(app, ctx):
    from PySide6.QtWidgets import QLabel, QWidget

    from project_opener.ui.context import LaunchRun
    from project_opener.ui.widgets.launch_sheet import LaunchSheet
    p = M.Project(name="P", job_number="P9", items=[M.Item(path=r"C:\a.pdf", group="Checking"),
                                                     M.Item(path=r"C:\b.xlsx", group="Checking"),
                                                     M.Item(path=r"C:\c", kind="folder", group="Folders")])
    host = QWidget()
    host.resize(1200, 800)
    sheet = LaunchSheet(host, lambda: host.rect())
    sheet.begin(LaunchRun(p, p.items, None))
    assert sheet.title.text() == "Opening P9 · P"
    labels = [w.text() for w in sheet.list_body.findChildren(QLabel)]
    assert labels[:1] == ["Checking"] and "Folders" in labels
    assert [w.text() for w in sheet.list_body.findChildren(QLabel) if w.text() in ("1", "2", "3")] == ["1", "2", "3"]


def test_revision_is_in_the_pulse_and_the_banner(hub_root):
    from project_opener.lan.hub import TeamHub
    hub = TeamHub(hub_root, user="priya", display_name="Priya")
    p = M.Project(name="GAD", job_number="P12513")
    first = hub.publish(p)
    p.origin = M.Origin(source="team", author="priya", published_id=first.published_id, revision=1)
    hub.publish(p)
    details = {r["detail"] for r in hub.pulse_feed(5) if r["event"] == "published"}
    assert details == {"P12513 · GAD rev 2 (was rev 1)", "P12513 · GAD rev 1"}


def test_footer_omits_elapsed_under_a_tenth():
    from project_opener.core.launcher import LaunchResult
    from project_opener.ui.widgets.launch_sheet import footer_text
    it = M.Item(path=r"C:\a")
    assert footer_text([LaunchResult(it, "", "opened")], 0.03) == ("1 opened", "")
    assert footer_text([LaunchResult(it, "", "opened")], 1.26) == ("1 opened", " · 1.3 s")


def test_dropped_paths_accept_every_kind(app):
    from PySide6.QtCore import QMimeData, QUrl

    from project_opener.ui.views.detail import dropped_paths
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(r"C:\x.pdf"), QUrl("https://example.com/a")])
    assert dropped_paths(mime) == ["C:/x.pdf", "https://example.com/a"]     # Qt's local-file form; _add_paths normalises
    text = QMimeData()
    text.setText("cmd: ipconfig" + chr(10) + chr(92) * 2 + "nas01" + chr(92) + "share" + chr(10))
    assert dropped_paths(text) == ["cmd: ipconfig", r"\\nas01\share"]
    assert [M.guess_kind(x) for x in dropped_paths(text)] == ["command", "folder"]



# ------------------------------------------------------------ round 4
def test_roots_fold_a_mapped_letter_into_its_server(monkeypatch):
    from project_opener.core import health as H
    from project_opener.core.health import root_key, roots_health
    monkeypatch.setattr(H, "drive_exists", lambda _r: False)
    dm = {"Z:": r"\\nas01\Project"}
    assert root_key("Z:", dm) == (r"\\nas01", r"\\nas01\Project")
    assert root_key("Z:", {}) == ("Z:", "") and root_key("{X}", dm) == ("{X}", "")
    a = M.Project(name="A", items=[M.Item(path=r"Z:\a"), M.Item(path=r"\\nas01\x\y")])
    health = {a.id: ProjectHealth(a.id, [ItemHealth(a.items[0].id, "offline", ""), ItemHealth(a.items[1].id, "offline", "")])}
    roots = roots_health([a], health, dm)
    assert [(r.root, r.status, r.items) for r in roots] == [(r"\\nas01", "offline", 2)]   # one row per server
    assert roots[0].mapping == r"Z: → \\nas01\Project"


def test_home_drive_rows_action_only_where_needed(app, ctx, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    from project_opener.core import health as H
    from project_opener.ui.views.home import HomePage
    monkeypatch.setattr(H, "drive_exists", lambda _r: False)
    monkeypatch.setattr(ctx, "schedule_health", lambda _p: None)      # the test supplies the health results
    ctx.resolver._drive_map = {}
    a = M.Project(name="A", job_number="P1", items=[M.Item(path=r"Q:\a"), M.Item(path=r"R:\ok")])
    b = M.Project(name="B", job_number="P2", items=[M.Item(path=r"Q:\b")])
    ctx.store.add(a)
    ctx.store.add(b)
    ctx.health[a.id] = ProjectHealth(a.id, [ItemHealth(a.items[0].id, "missing", ""), ItemHealth(a.items[1].id, "ok", "")])
    ctx.health[b.id] = ProjectHealth(b.id, [ItemHealth(b.items[0].id, "missing", "")])
    page = HomePage(ctx)

    def buttons():
        _settle()                                    # rows replaced with deleteLater: drop the stale ones
        return [w.text() for w in page.drives_panel.findChildren(QPushButton)]

    texts = buttons()
    assert "2 projects" in texts                     # Q: is down and used by two projects
    assert "1 drive reachable" in texts              # R: folded behind the expander, no action on it
    assert not [t for t in texts if t.startswith("Open ")]
    page._toggle_reachable()
    texts = buttons()
    assert "1 drive reachable" in texts and "2 projects" in texts and not [t for t in texts if t.startswith("Open ")]
    ctx.health[a.id] = ProjectHealth(a.id, [ItemHealth(a.items[0].id, "ok", ""), ItemHealth(a.items[1].id, "missing", "")])
    ctx.health[b.id] = ProjectHealth(b.id, [ItemHealth(b.items[0].id, "ok", "")])
    page.refresh()
    texts = buttons()
    assert "Open P1" in texts and "2 projects" not in texts   # now only R: is down, used by P1 alone


def test_projects_root_filter(app, ctx):
    from project_opener.ui.views.projects import ProjectsPage, uses_root
    a = M.Project(name="A", items=[M.Item(path=r"Z:\a")])
    b = M.Project(name="B", items=[M.Item(path=r"\\nas01\b")])
    c = M.Project(name="C", items=[M.Item(path="https://x")])
    dm = {"Z:": r"\\nas01\Project"}
    assert uses_root(a, r"\\nas01", dm) and uses_root(b, "Z:", dm) and not uses_root(c, "Z:", dm)
    assert uses_root(a, "Z:", {}) and not uses_root(b, "Z:", {})
    for p_ in (a, b, c):
        ctx.store.add(p_)
    page = ProjectsPage(ctx)
    page.on_show("root:Z:")
    assert page.search.text() == "root:Z:"
    assert "1 shown" in page.subtitle_label.text() or "2 shown" in page.subtitle_label.text()


def test_segment_label_drops_whole_facts(app):
    from project_opener.ui.widgets.common import SegmentLabel
    lbl = SegmentLabel()
    lbl.set_segments(["6 of 6 items enabled", "2 launch sets", "opened 15×, last just now", "2 paths need attention"])
    full = lbl.fitted_text(10_000)
    assert full == "6 of 6 items enabled · 2 launch sets · opened 15×, last just now · 2 paths need attention"
    short = lbl.fitted_text(240)
    assert short in full and short.endswith(("enabled", "launch sets", "just now")) and "…" not in short


def test_activity_register_folds_launches_and_keeps_revisions():
    from project_opener.ui.views.team import activity_register
    rows = [
        {"ts": "2026-11-01T09:00:00+00:00", "user": "vikram", "name": "Vikram", "event": "launched", "detail": "P12513 · As-built"},
        {"ts": "2026-11-01T10:00:00+00:00", "user": "vikram", "name": "Vikram", "event": "launched", "detail": "P12513 · As-built"},
        {"ts": "2026-11-01T11:00:00+00:00", "user": "vikram", "name": "Vikram", "event": "launched", "detail": "P12513 · As-built › Checking"},
        {"ts": "2026-11-01T12:00:00+00:00", "user": "priya", "name": "Priya", "event": "published", "detail": "P12513 · As-built rev 2 (was rev 1)"},
        {"ts": "2026-11-01T12:30:00+00:00", "user": "priya", "name": "Priya", "event": "sent", "detail": "DM-GAD · Mangala → vikram"},
    ]
    reg = activity_register(rows, name_for=lambda u: {"vikram": "Vikram"}.get(u, u), today="2026-11-01")
    assert [g["project"] for g in reg] == ["DM-GAD · Mangala", "P12513 · As-built"]
    p = reg[1]["entries"]
    assert p[0]["text"] == "published (was rev 1)" and p[0]["rev"] == "rev 2" and p[0]["by"] == "Priya"
    assert p[1]["text"] == "opened 3× today" and p[1]["by"] == "Vikram"
    assert reg[0]["entries"][0]["text"] == "sent to Vikram"


def test_current_mirror_hidden_once_an_update_is_downloaded(app, ctx, tmp_path):
    from PySide6.QtWidgets import QPushButton

    from project_opener.ui.views.updates import UpdatesPage
    from project_opener.update.updater import CheckResult, UpdateInfo
    ctx.settings.hub_path = str(tmp_path / "hub")
    ctx.apply_settings()
    page = UpdatesPage(ctx)
    labels = [b.text() for b in page.sources_panel.findChildren(QPushButton)]
    assert any(t.startswith("Mirror ") for t in labels)
    inst = tmp_path / "ProjectOpener-9.9.9-setup.exe"
    inst.write_bytes(b"x")
    ctx.last_check = CheckResult(update=UpdateInfo(version="9.9.9", installer=inst.name, sha256="a" * 64))
    ctx.downloaded = inst
    page.render_state()
    _settle()
    labels = [b.text() for b in page.sources_panel.findChildren(QPushButton)]
    assert not any(t.startswith("Mirror ") for t in labels)


def test_sent_pulse_uses_the_title(hub_root):
    from project_opener.lan.hub import TeamHub
    hub = TeamHub(hub_root, user="priya", display_name="Priya")
    hub.initialise()
    hub.send("vikram", M.Project(name="Mangala", job_number="DM-GAD"))
    assert [r["detail"] for r in hub.pulse_feed(3)] == ["DM-GAD · Mangala → vikram"]


def test_sidebar_company_on_one_line(app):
    from PySide6.QtWidgets import QLabel

    from project_opener import constants as C
    from project_opener.ui.widgets.sidebar import Sidebar
    sb = Sidebar("Vikram")
    assert any(w.text() == "Dexterity Design Services" and not w.wordWrap() for w in sb.findChildren(QLabel))
    assert "Pvt" in C.COMPANY


# ------------------------------------------------------------ round 5
def test_every_page_fits_the_minimum_window(app, ctx):
    from project_opener.ui import theme
    from project_opener.ui.main_window import MainWindow
    from project_opener.ui.widgets.sidebar import EXPANDED
    theme.apply_theme(app, False, theme.DEFAULT_ACCENT)          # the app's own type, not the platform default
    for n in range(3):
        ctx.store.add(M.Project(name=f"Job {n}", job_number=f"P1000{n}", client="FST",
                                items=[M.Item(path=r"\\nas01\Project\x"), M.Item(path=r"{SERVER_ROOT}\a"), M.Item(path=r"Z:\b")]))
    for p in ctx.store.projects:
        ctx.health[p.id] = ProjectHealth(p.id, [ItemHealth(i.id, st, "") for i, st in zip(p.items, ("offline", "variable", "missing"), strict=True)])
    win = MainWindow(ctx)
    win.resize(win.minimumSize())
    win.show()
    for page in win.pages.values():
        page.refresh()
    _settle()
    avail = win.minimumWidth() - EXPANDED
    too_wide = {route: page.body.minimumSizeHint().width() for route, page in win.pages.items()
                if page.body.minimumSizeHint().width() > avail}
    assert not too_wide, f"wider than {avail}: {too_wide}"
    win.quit_app()


def test_uses_text_names_the_jobs():
    from project_opener.ui.views.home import uses_text
    a, b, c = (M.Project(name=f"N{i}", job_number=f"P{i}") for i in range(3))
    assert uses_text([a]) == "1 project · P0"
    assert uses_text([a, b]) == "P0 · P1"
    assert uses_text([a, b, c]) == "P0 · P1 +1"


def test_segment_label_drop_order(app):
    from PySide6.QtGui import QFontMetrics

    from project_opener.ui.widgets.common import SegmentLabel
    lbl = SegmentLabel()
    lbl.set_segments(["6 of 6 items enabled", "2 launch sets", "opened 15×, last just now", "2 paths need attention"],
                     drop_order=[2, 1, 0])
    fm = QFontMetrics(lbl.font())
    full = "6 of 6 items enabled · 2 launch sets · opened 15×, last just now · 2 paths need attention"
    three = "6 of 6 items enabled · 2 launch sets · 2 paths need attention"
    two = "6 of 6 items enabled · 2 paths need attention"
    assert lbl.fitted_text(fm.horizontalAdvance(full)) == full
    assert lbl.fitted_text(fm.horizontalAdvance(full) - 1) == three          # the opened count goes first
    assert lbl.fitted_text(fm.horizontalAdvance(three) - 1) == two           # then the launch sets
    assert lbl.fitted_text(10) == "2 paths need attention"                   # health is the last fact standing
