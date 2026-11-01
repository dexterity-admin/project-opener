"""Offscreen UI tests: detail-page notes autosave / staleness guards, card clicks, dialogs."""
from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(app, isolated_data_dir):
    from project_opener.ui.context import AppContext
    return AppContext(isolated_data_dir)


def _project(ctx, **kw) -> M.Project:
    p = M.Project(name=kw.pop("name", "Demo"), items=[M.Item(path=r"C:\Windows\notepad.exe", kind="app")], **kw)
    ctx.store.add(p)
    return p


def _page(ctx, project):
    from project_opener.ui.views.detail import ProjectPage
    page = ProjectPage(ctx)
    page.resize(900, 700)
    page.show()
    page.load(project)
    page.on_show()
    QApplication.processEvents()
    return page


# ----------------------------------------------------------------- detail page
def test_notes_autosave_keeps_editor_and_focus(ctx):
    p = _project(ctx)
    page = _page(ctx, p)
    editor = page.notes_edit
    editor.setFocus()
    editor.setPlainText("hello")
    assert page._notes_timer.isActive()
    page._notes_timer.stop()
    page._save_notes()                       # what the timer would do 700 ms later
    QApplication.processEvents()
    assert ctx.store.get(p.id).notes == "hello"
    assert page.notes_edit is editor         # not rebuilt
    assert editor.toPlainText() == "hello"
    assert editor.hasFocus()


def test_on_show_reloads_from_store(ctx):
    p = _project(ctx)
    page = _page(ctx, p)
    fresh = M.Project.from_dict(p.to_dict())
    fresh.name = "Renamed elsewhere"
    ctx.store.update(fresh)
    page.hide()
    page.show()
    page.on_show()
    assert page.project.name == "Renamed elsewhere"
    assert page.title_label.text() == "Renamed elsewhere"


def test_on_show_leaves_when_project_deleted(ctx):
    p = _project(ctx)
    page = _page(ctx, p)
    routes: list[tuple[str, object]] = []
    ctx.navigate.connect(lambda r, payload: routes.append((r, payload)))
    ctx.store.remove(p.id)
    page.on_show()
    assert routes == [("projects", "")]
    assert page.project is None


def test_save_never_readds_deleted_project(ctx):
    p = _project(ctx)
    page = _page(ctx, p)
    ctx.store.remove(p.id)
    page.notes_edit.setPlainText("typed after delete")
    page._notes_timer.stop()
    page._save_notes()
    assert ctx.store.get(p.id) is None
    assert page.save_project() is False
    assert ctx.store.get(p.id) is None


# ------------------------------------------------------------------- cards
def _double_click(widget):
    pos = QPointF(widget.rect().center())
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, pos, widget.mapToGlobal(pos.toPoint()).toPointF(),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def _release(widget):
    pos = QPointF(widget.rect().center())
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, pos, widget.mapToGlobal(pos.toPoint()).toPointF(),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


@pytest.mark.parametrize("cls_name", ["ProjectCard", "ProjectRow"])
def test_cards_single_click_opens_and_double_click_does_not_launch(app, cls_name):
    from project_opener.ui.widgets import cards
    p = M.Project(name="Demo")
    w = getattr(cards, cls_name)(p)
    w.show()
    launched, opened = [], []
    w.launch_requested.connect(launched.append)
    w.open_requested.connect(opened.append)
    _release(w)
    assert opened == [p]
    _double_click(w)
    assert launched == []


# ----------------------------------------------------------------- dialogs
def test_launch_set_editor_saves_icon(app):
    from project_opener.ui.widgets.dialogs import LaunchSetEditor
    p = M.Project(name="Demo", items=[M.Item(path="a.txt"), M.Item(path="b.txt")])
    dlg = LaunchSetEditor(p, None)
    dlg.name.setText("Checking")
    dlg.icon_picker._pick("fa5s.clipboard-check")
    dlg.accept()
    assert dlg.result() == 1
    assert dlg.set.icon == "fa5s.clipboard-check"
    assert dlg.set.name == "Checking"
    assert len(dlg.set.item_ids) == 2
    # editing keeps an existing icon selected
    dlg2 = LaunchSetEditor(p, dlg.set)
    assert dlg2.icon_picker.icon_name() == "fa5s.clipboard-check"


def test_announcement_dialog_expires(app):
    from project_opener.ui.widgets.dialogs import AnnouncementDialog
    dlg = AnnouncementDialog()
    assert dlg.expires == ""
    dlg.expires_days.setValue(3)
    exp = dlg.expires
    when = datetime.fromisoformat(exp)
    assert when.tzinfo is not None
    delta = when - datetime.now(UTC)
    assert 2.9 < delta.total_seconds() / 86400 <= 3.0
    assert exp > M.now_iso()                     # string-comparable with hub timestamps


def test_publish_dialog_description(app):
    from project_opener.ui.widgets.dialogs import PublishDialog
    p = M.Project(name="Demo", description="Standard bundle")
    dlg = PublishDialog(p)
    assert dlg.description == "Standard bundle"
    dlg.description_edit.setPlainText("  Updated text  ")
    assert dlg.description == "Updated text"


def test_ask_text_removed():
    from project_opener.ui.widgets import dialogs
    assert not hasattr(dialogs, "ask_text")
