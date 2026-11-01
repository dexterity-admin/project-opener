"""Project detail: items grouped, launch sets, health, notes, provenance."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QVBoxLayout, QWidget

from project_opener.core import models as M
from project_opener.core import winutil
from project_opener.core.health import ItemHealth
from project_opener.core.search import item_icon
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, clear_layout
from project_opener.ui.widgets.cards import relative_time
from project_opener.ui.widgets.common import Badge, Button, ElidedLabel, IconButton, IconCircle, ToggleSwitch, label
from project_opener.ui.widgets.dialogs import ItemEditor, LaunchSetEditor, confirm

STATUS_META = {
    "ok": ("fa5s.check-circle", "success", "Reachable"),
    "missing": ("fa5s.exclamation-circle", "warning", "Not found"),
    "offline": ("fa5s.plug", "danger", "Server offline"),
    "variable": ("fa5s.question-circle", "warning", "Undefined variable"),
}


class ItemRow(QFrame):
    def __init__(self, page: ProjectPage, project: M.Project, item: M.Item, health: ItemHealth | None, parent=None):
        super().__init__(parent)
        self.page, self.project, self.item = page, project, item
        self.setObjectName("panel2")
        self.setAcceptDrops(False)
        t = theme.current()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(10)
        self.switch = ToggleSwitch(checked=item.enabled)
        self.switch.setToolTip("Include when opening the whole project")
        self.switch.toggled.connect(self._toggle)
        lay.addWidget(self.switch)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(item_icon(item), 16, project.color if item.enabled else t.text_faint))
        ic.setFixedWidth(20)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(item.display_name)
        name.setStyleSheet("font-weight: 600;" + ("" if item.enabled else f" color: {t.text_faint};"))
        col.addWidget(name)
        shown = page.ctx.resolver.localise(item.path)
        sub = ElidedLabel(shown + (f"   {item.args}" if item.args else ""), mode=Qt.TextElideMode.ElideMiddle)
        sub.setObjectName("faint")
        col.addWidget(sub)
        lay.addLayout(col, 1)
        if health:
            icon_name, color_key, text = STATUS_META.get(health.status, STATUS_META["ok"])
            color = getattr(t, color_key)
            b = Badge(text, color)
            b.setToolTip(health.detail or health.resolved)
            lay.addWidget(b)
        open_b = IconButton("fa5s.external-link-alt", "Open this item", size=13)
        open_b.clicked.connect(lambda: page.ctx.open_single(project, item))
        lay.addWidget(open_b)
        reveal = IconButton("fa5s.folder-open", "Show in Explorer", size=13)
        reveal.clicked.connect(self._reveal)
        lay.addWidget(reveal)   # parent first: setVisible on an orphan creates a native window
        reveal.setVisible(item.kind in ("file", "folder", "app"))
        more = IconButton("fa5s.ellipsis-v", "More", size=13)
        more.clicked.connect(lambda: self._menu(more))
        lay.addWidget(more)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _toggle(self, on: bool) -> None:
        self.item.enabled = on
        self.page.save_project()

    def _reveal(self) -> None:
        res = self.page.ctx.resolver.resolve(self.item.path)
        if os.path.exists(res.resolved):
            winutil.reveal_in_explorer(res.resolved)
        else:
            self.page.ctx.toast.emit("Not found", res.resolved, "warning")

    def _menu(self, anchor: QWidget) -> None:
        m = QMenu(self)
        m.addAction(icons.icon("fa5s.pen"), "Edit…", self.page.edit_item_dialog(self.item))
        m.addAction(icons.icon("fa5s.copy"), "Copy path", lambda: self.page.copy_text(self.item.path))
        if self.item.kind in ("file", "folder", "app"):
            m.addAction(icons.icon("fa5s.terminal"), "Open terminal here", lambda: winutil.open_terminal_at(self.page.ctx.resolver.resolve(self.item.path).resolved))
        m.addSeparator()
        m.addAction(icons.icon("fa5s.trash", theme.current().danger), "Remove", lambda: self.page.remove_item(self.item))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self.page.ctx.open_single(self.project, self.item)


class ProjectPage(Page):
    route = "project"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self.project: M.Project | None = None
        self._saving_notes = False
        self._fresh = False          # set by load(); on_show() skips its reload once
        self.setAcceptDrops(True)
        self.content.setContentsMargins(28, 16, 28, 28)
        top = QHBoxLayout()
        back = Button("All projects", "fa5s.arrow-left", "ghost")
        back.clicked.connect(lambda: ctx.navigate.emit("projects", None))
        top.addWidget(back)
        top.addStretch(1)
        self.content.addLayout(top)

        head = QHBoxLayout()
        head.setSpacing(14)
        self.icon = IconCircle("fa5s.folder", "#3B82F6", 56)
        head.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.kicker = label("", "kicker")
        col.addWidget(self.kicker)
        self.title_label = label("", "h1")
        col.addWidget(self.title_label)
        self.desc = ElidedLabel("", mode=Qt.TextElideMode.ElideRight)
        self.desc.setObjectName("muted")
        col.addWidget(self.desc)
        self.tag_row = QHBoxLayout()
        self.tag_row.setSpacing(6)
        col.addLayout(self.tag_row)
        head.addLayout(col, 1)
        actions = QVBoxLayout()
        actions.setSpacing(6)
        self.launch_btn = Button("Open project", "fa5s.play", "primary")
        self.launch_btn.setFixedHeight(38)
        self.launch_btn.clicked.connect(lambda: self.ctx.launch(self.project, parent=self) if self.project else None)
        actions.addWidget(self.launch_btn)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        edit = Button("Edit", "fa5s.pen")
        edit.clicked.connect(lambda: self.ctx.navigate.emit("edit_project", self.project))
        row2.addWidget(edit)
        more = Button("", "fa5s.ellipsis-h")
        more.setFixedWidth(36)
        more.clicked.connect(lambda: self.ctx.navigate.emit("project_menu", (self.project, more.mapToGlobal(more.rect().bottomLeft()))))
        row2.addWidget(more)
        actions.addLayout(row2)
        head.addLayout(actions)
        self.content.addLayout(head)

        self.meta_row = QHBoxLayout()
        self.meta_row.setSpacing(12)
        self.content.addLayout(self.meta_row)
        self.origin_host = QVBoxLayout()
        self.content.addLayout(self.origin_host)

        # Box layouts, not a QGridLayout: grids with height-for-width children
        # (word-wrapped labels) make every layout pass exponentially slow.
        cols = QHBoxLayout()
        cols.setSpacing(16)
        self.items_panel, self.items_lay = self.panel()
        self.sets_panel, self.sets_lay = self.panel()
        self.notes_panel, self.notes_lay = self.panel()
        cols.addWidget(self.items_panel, 3, Qt.AlignmentFlag.AlignTop)
        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(self.sets_panel)
        side.addWidget(self.notes_panel)
        side.addStretch(1)
        cols.addLayout(side, 2)
        self.content.addLayout(cols)
        self.content.addStretch(1)

        # The notes editor is built once and kept: rebuilding it on every
        # project_updated would steal focus mid-typing (the autosave itself
        # emits that signal).
        self.notes_lay.addWidget(label("NOTES", "eyebrow"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Contacts, conventions, reminders… saved automatically.")
        self.notes_edit.setMinimumHeight(120)
        self.notes_edit.textChanged.connect(self._notes_changed)
        self.notes_lay.addWidget(self.notes_edit)
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(700)
        self._notes_timer.timeout.connect(self._save_notes)

        self.bind(ctx.health_updated, self._health_changed)
        self.bind(ctx.project_updated, self._project_changed)
    # ---------------------------------------------------------------- load
    def load(self, project: M.Project) -> None:
        self._flush_notes()
        self.project = project
        self._fresh = True
        self.render()
        self.ctx.schedule_health(project)

    def on_show(self) -> None:
        """Reload the project from the store every time the page is shown."""
        if self._fresh:                     # load() just rendered this very object
            self._fresh = False
            return
        if not self.project:
            return
        fresh = self.ctx.store.get(self.project.id)
        if fresh is None:
            self.project = None
            self.ctx.navigate.emit("projects", "")
            return
        self.project = fresh
        self.render()

    def _project_changed(self, pid: str) -> None:
        if self._saving_notes or not self.project or pid != self.project.id or not self.isVisible():
            return
        self.project = self.ctx.store.get(pid) or self.project
        self.render()

    def _health_changed(self, pid: str) -> None:
        if self.project and pid == self.project.id and self.isVisible():
            self._render_items()
            self._render_meta()

    def refresh(self) -> None:
        self._fresh = False
        if self.project:
            fresh = self.ctx.store.get(self.project.id)
            if fresh is None:
                self.project = None
                self.ctx.navigate.emit("projects", "")
                return
            self.project = fresh
            if self.isVisible():
                self.render()

    def save_project(self) -> bool:
        """Write the current project through the store, unless it was deleted meanwhile.

        Returns False (and leaves the page) when the project no longer exists in
        the store, so an edit can never re-add a removed project via ``store.update``.
        """
        p = self.project
        if not p:
            return False
        if self.ctx.store.get(p.id) is None:
            self.project = None
            self.ctx.toast.emit("Project no longer exists", p.name, "warning")
            self.ctx.navigate.emit("projects", "")
            return False
        self.ctx.store.update(p)
        return True

    def render(self) -> None:
        p = self.project
        if not p:
            return
        t = theme.current()
        self.icon.set(p.icon, p.color)
        self.kicker.setText(" · ".join(x for x in (p.client, p.job_number) if x) or "PROJECT")
        self.title_label.setText(p.name)
        self.desc.setText(p.description)
        self.desc.setVisible(bool(p.description))
        clear_layout(self.tag_row)
        for tag in p.tags:
            self.tag_row.addWidget(Badge(tag, p.color))
        if p.pinned:
            self.tag_row.addWidget(Badge("Pinned", t.accent))
        if p.auto_launch:
            self.tag_row.addWidget(Badge("Auto-launch", t.info))
        self.tag_row.addStretch(1)
        self._render_meta()
        self._render_origin()
        self._render_items()
        self._render_sets()
        self._render_notes()

    def _render_meta(self) -> None:
        clear_layout(self.meta_row)
        p = self.project
        if not p:
            return
        t = theme.current()
        h = self.ctx.health_for(p.id)
        problems = len(h.problems) if h else None
        bits = [
            ("fa5s.link", f"{len(p.enabled_items)} of {len(p.items)} items enabled"),
            ("fa5s.layer-group", f"{len(p.launch_sets)} launch set(s)"),
            ("fa5s.history", f"Opened {p.open_count}× · last {relative_time(p.last_opened).lower()}"),
            ("fa5s.heartbeat", "Checking paths…" if problems is None else ("All paths reachable" if problems == 0 else f"{problems} item(s) need attention")),
        ]
        for ic, text in bits:
            w = QWidget()
            row = QHBoxLayout(w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            lab = QLabel()
            color = t.text_muted
            if ic == "fa5s.heartbeat" and problems is not None:
                color = t.success if problems == 0 else t.warning
            lab.setPixmap(icons.pixmap(ic, 13, color))
            row.addWidget(lab)
            row.addWidget(label(text, "muted"))
            self.meta_row.addWidget(w)
        self.meta_row.addStretch(1)

    def _render_origin(self) -> None:
        clear_layout(self.origin_host)
        p = self.project
        if not p or p.origin.source not in ("team", "inbox"):
            return
        t = theme.current()
        f = QFrame()
        f.setObjectName("banner")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 8, 14, 8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("fa5s.users", 14, t.accent))
        lay.addWidget(ic)
        if p.origin.source == "team":
            txt = f"Team project published by <b>{p.origin.author}</b> · revision {p.origin.revision}"
            newer = self.ctx.hub.newer_revision(p) if self.ctx.hub.reachable() else None
            lbl = QLabel(txt + (f" · <b>revision {newer.revision} available</b>" if newer else ""))
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(lbl, 1)
            if newer:
                b = Button("Update from hub", "fa5s.sync-alt", "primary")
                b.clicked.connect(lambda _=False, pub=newer: self.ctx.navigate.emit("update_from_hub", (p, pub)))
                lay.addWidget(b)
            if p.origin.author == self.ctx.user:
                b2 = Button("Publish changes", "fa5s.cloud-upload-alt")
                b2.clicked.connect(lambda: self.ctx.navigate.emit("publish", p))
                lay.addWidget(b2)
        else:
            lbl = QLabel(f"Received from <b>{p.origin.author}</b>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(lbl, 1)
        self.origin_host.addWidget(f)

    def _render_items(self) -> None:
        clear_layout(self.items_lay)
        p = self.project
        if not p:
            return
        head = QHBoxLayout()
        head.addWidget(label("ITEMS", "eyebrow"))
        head.addStretch(1)
        add_file = Button("File", "fa5s.file")
        add_file.clicked.connect(self._add_files)
        add_folder = Button("Folder", "fa5s.folder-open")
        add_folder.clicked.connect(self._add_folder)
        add_link = Button("Link", "fa5s.link")
        add_link.clicked.connect(lambda: self.edit_item_dialog(None, kind="url")())
        add_any = Button("Add…", "fa5s.plus", "primary")
        add_any.clicked.connect(self.edit_item_dialog(None))
        for b in (add_file, add_folder, add_link, add_any):
            head.addWidget(b)
        self.items_lay.addLayout(head)
        if not p.items:
            self.items_lay.addWidget(label("No items yet. Add files, folders, links, applications or commands — or drag and drop them onto this page.", "muted", wrap=True))
            return
        health = self.ctx.health_for(p.id)
        groups = p.groups()
        for g in groups:
            items = [i for i in p.items if (i.group or "") == g]
            if len(groups) > 1 or g:
                self.items_lay.addWidget(label(g or "Ungrouped", "faint"))
            for it in items:
                self.items_lay.addWidget(ItemRow(self, p, it, health.status_for(it.id) if health else None))

    def _render_sets(self) -> None:
        clear_layout(self.sets_lay)
        p = self.project
        if not p:
            return
        head = QHBoxLayout()
        head.addWidget(label("LAUNCH SETS", "eyebrow"))
        head.addStretch(1)
        add = IconButton("fa5s.plus", "New launch set", size=13)
        add.clicked.connect(lambda: self._edit_set(None))
        head.addWidget(add)
        self.sets_lay.addLayout(head)
        if not p.launch_sets:
            self.sets_lay.addWidget(label("Launch sets open a chosen subset of items together — for example 'Checking' or 'Submission pack'.", "muted", wrap=True))
            return
        for s in p.launch_sets:
            f = QFrame()
            f.setObjectName("panel2")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(10, 6, 6, 6)
            lay.setSpacing(8)
            ic = QLabel()
            ic.setPixmap(icons.pixmap(s.icon, 14, p.color))
            lay.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            nm = QLabel(s.name)
            nm.setStyleSheet("font-weight: 600;")
            col.addWidget(nm)
            col.addWidget(label(f"{len(s.item_ids)} item(s)", "faint"))
            lay.addLayout(col, 1)
            play = Button("Open", "fa5s.play", "primary")
            play.setFixedHeight(28)
            play.clicked.connect(lambda _=False, ls=s: self.ctx.launch(p, ls, parent=self))
            lay.addWidget(play)
            ed = IconButton("fa5s.pen", "Edit", size=12)
            ed.clicked.connect(lambda _=False, ls=s: self._edit_set(ls))
            lay.addWidget(ed)
            rm = IconButton("fa5s.trash", "Delete", size=12)
            rm.clicked.connect(lambda _=False, ls=s: self._delete_set(ls))
            lay.addWidget(rm)
            self.sets_lay.addWidget(f)

    def _render_notes(self) -> None:
        p = self.project
        if not p or self.notes_edit.toPlainText() == p.notes:
            return
        if self.notes_edit.hasFocus() and self._notes_timer.isActive():
            return                      # user is typing; their pending save wins
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(p.notes)
        self.notes_edit.blockSignals(False)

    def _notes_changed(self) -> None:
        self._notes_timer.start()

    def _flush_notes(self) -> None:
        if self._notes_timer.isActive():
            self._notes_timer.stop()
            self._save_notes()

    def _save_notes(self) -> None:
        p = self.project
        if not p or self.notes_edit.toPlainText() == p.notes:
            return
        p.notes = self.notes_edit.toPlainText()
        self._saving_notes = True
        try:
            if not self.save_project():
                return
        finally:
            self._saving_notes = False
        self._render_meta()             # header/meta only; the editor keeps focus

    # ------------------------------------------------------------- actions
    def edit_item_dialog(self, item: M.Item | None, kind: str = ""):
        def run() -> None:
            p = self.project
            if not p:
                return
            new = item is None
            target = item or M.Item(path="", kind=kind or "file")
            dlg = ItemEditor(None if new else target, p.groups(), self)
            if new and kind:
                dlg.kind.setCurrentIndex(max(0, dlg.kind.findData(kind)))
            if dlg.exec():
                if new:
                    p.items.append(dlg.item)
                self.save_project()
        return run

    def _add_files(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(self, "Add files")
        self._add_paths(files)

    def _add_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Add folder")
        if d:
            self._add_paths([d])

    def _add_paths(self, paths: list[str]) -> None:
        p = self.project
        if not p or not paths:
            return
        existing = {i.path.lower() for i in p.items}
        added = 0
        for raw in paths:
            norm = os.path.normpath(raw)
            if norm.lower() in existing:
                continue
            p.items.append(M.Item(path=norm, kind=M.guess_kind(norm)))
            existing.add(norm.lower())
            added += 1
        if added and self.save_project():
            self.ctx.toast.emit(f"Added {added} item(s)", p.name, "success")

    def remove_item(self, item: M.Item) -> None:
        p = self.project
        if p and confirm(self, "Remove item", f"Remove '{item.display_name}' from {p.name}?"):
            p.items = [i for i in p.items if i.id != item.id]
            for s in p.launch_sets:
                s.item_ids = [i for i in s.item_ids if i != item.id]
            self.save_project()

    def _edit_set(self, ls: M.LaunchSet | None) -> None:
        p = self.project
        if not p:
            return
        if not p.items and ls is None:
            self.ctx.toast.emit("Add items first", "A launch set needs items to choose from.", "warning")
            return
        dlg = LaunchSetEditor(p, ls, self)
        if dlg.exec():
            if ls is None:
                p.launch_sets.append(dlg.set)
            self.save_project()

    def _delete_set(self, ls: M.LaunchSet) -> None:
        p = self.project
        if p and confirm(self, "Delete launch set", f"Delete '{ls.name}'? Items stay in the project."):
            p.launch_sets = [s for s in p.launch_sets if s.id != ls.id]
            self.save_project()

    def copy_text(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.ctx.toast.emit("Copied", text, "info")

    # ------------------------------------------------------------- drag/drop
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls() and self.project:
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        self._add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()])
        e.acceptProposedAction()
