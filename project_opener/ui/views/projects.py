"""All projects: grid/list, live search, sort, tag filters, drag-and-drop creation."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from project_opener.core import models as M
from project_opener.core.health import path_root, root_key
from project_opener.core.search import search_projects
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, clear_layout
from project_opener.ui.widgets.cards import ProjectCard, ProjectRow
from project_opener.ui.widgets.common import Button, Chip, IconButton, label
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout


def uses_root(project: M.Project, root: str, drive_map: dict | None = None) -> bool:
    """Whether any item of ``project`` sits under ``root`` (a mapped letter counts under its server)."""
    want = root_key(root, drive_map)[0].lower()
    return any(root_key(path_root(i.path), drive_map)[0].lower() == want for i in project.items if path_root(i.path))


class ProjectsPage(Page):
    route = "projects"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self.setAcceptDrops(True)
        self._cards: dict[str, QWidget] = {}
        self._tag_filter: set[str] = set()
        self._only_favorites = False
        row = self.title_row("Projects", "")
        self.count_lbl = self.subtitle_label      # "{n} projects · {m} pinned", tabular
        new = Button("New project", "fa5s.plus", "primary")
        new.clicked.connect(lambda: ctx.navigate.emit("new_project", None))
        row.addWidget(new, 0, Qt.AlignmentFlag.AlignTop)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search name, client, job, tag or item")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(theme.current().control_h)
        self.search.textChanged.connect(self._debounced)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.refresh)
        self._search_icon = QLabel(self.search)
        self._search_icon.setPixmap(icons.pixmap("fa5s.search", 14, theme.current().text_faint))
        self._search_icon.move(12, (theme.current().control_h - 14) // 2)
        tools.addWidget(self.search, 1)
        self.sort = QComboBox()
        for key, text in (("smart", "Pinned + recent"), ("name", "Name"), ("recent", "Last opened"), ("most_used", "Most used"), ("created", "Created")):
            self.sort.addItem(text, key)
        self.sort.setCurrentIndex(max(0, self.sort.findData(ctx.settings.sort_key)))
        self.sort.currentIndexChanged.connect(self._sort_changed)
        self.sort.setFixedHeight(theme.current().control_h)
        tools.addWidget(self.sort)
        self.fav_btn = IconButton("fa5s.star", "Only favourites", size=14, checkable=True)
        self.fav_btn.toggled.connect(self._toggle_fav)
        tools.addWidget(self.fav_btn)
        self.grid_btn = IconButton("fa5s.th-large", "Grid view", size=14, checkable=True)
        self.list_btn = IconButton("fa5s.list", "List view", size=14, checkable=True)
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        grp.addButton(self.grid_btn)
        grp.addButton(self.list_btn)
        (self.grid_btn if ctx.settings.view_mode == "grid" else self.list_btn).setChecked(True)
        self.grid_btn.toggled.connect(lambda on: self._view_changed("grid" if on else "list"))
        for b in (self.fav_btn, self.grid_btn, self.list_btn):
            b.setFixedSize(theme.current().control_h, theme.current().control_h)
            tools.addWidget(b)
        self.content.addLayout(tools)

        self.tags_host = QWidget()
        self.tags_flow = FlowLayout(self.tags_host, 0, 6, 6)
        self.content.addWidget(self.tags_host)

        self.host = QWidget()
        self.flow = FlowLayout(self.host, 0, 16, 16, justify=True)
        self.list_lay = QVBoxLayout()
        self.list_lay.setSpacing(8)
        self.empty_host = QVBoxLayout()
        self.content.addWidget(self.host)
        self.content.addLayout(self.list_lay)
        self.content.addLayout(self.empty_host)
        self.content.addStretch(1)
        self.drop_hint = label("Release to start a project from these items", "faint")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.hide()                 # shown only while something is dragged over the page
        self.content.addWidget(self.drop_hint)

        self.bind(ctx.projects_changed, self.refresh)
        self.bind(ctx.health_updated, self._health)
        self.refresh()

    # --------------------------------------------------------------- events
    def _debounced(self) -> None:
        self._timer.start()

    def _sort_changed(self) -> None:
        self.ctx.settings.sort_key = self.sort.currentData()
        self.ctx.settings.save()
        self.refresh()

    def _view_changed(self, mode: str) -> None:
        self.ctx.settings.view_mode = mode
        self.ctx.settings.save()
        self.refresh()

    def _toggle_fav(self, on: bool) -> None:
        self._only_favorites = on
        self.refresh()

    def _toggle_tag(self, tag: str, on: bool) -> None:
        if on:
            self._tag_filter.add(tag)
        else:
            self._tag_filter.discard(tag)
        self.refresh()

    def _clear_filters(self) -> None:
        self._tag_filter.clear()
        self._only_favorites = False
        self.fav_btn.setChecked(False)
        self.search.clear()
        self.refresh()

    def on_show(self, payload=None) -> None:
        """A "root:…" payload (from Home's drive map) prefills the search with that root."""
        if isinstance(payload, str) and payload.lower().startswith("root:"):
            self.search.setText(payload)
            self.refresh()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _health(self, pid: str) -> None:
        w = self._cards.get(pid)
        if w is not None and hasattr(w, "set_health"):
            w.set_health(self.ctx.health_for(pid))

    # -------------------------------------------------------------- render
    def refresh(self) -> None:
        store = self.ctx.store
        # tags
        self.tags_flow.clear()
        all_tags = store.all_tags()
        self._tag_filter &= set(all_tags)
        for tag in all_tags[:24]:
            c = Chip(tag)
            c.setChecked(tag in self._tag_filter)
            c.toggled.connect(lambda on, tg=tag: self._toggle_tag(tg, on))
            self.tags_flow.addWidget(c)
        self.tags_host.setVisible(bool(all_tags))

        query = self.search.text().strip()
        projects = store.sorted_projects(self.sort.currentData() or "smart")
        if query.lower().startswith("root:"):            # "root:\\nas01" / "root:Z:" / "root:{SERVER_ROOT}": by drive, share or variable
            projects = [p for p in projects if uses_root(p, query[5:].strip(), self.ctx.resolver.drive_map)]
        elif query:
            hits = search_projects(query, projects, limit=500)
            projects = [h.project for h in hits if h.project]
        if self._tag_filter:
            projects = [p for p in projects if self._tag_filter.issubset({t for t in p.tags})]
        if self._only_favorites:
            projects = [p for p in projects if p.favorite]
        pinned = sum(1 for p in store.projects if p.pinned)
        total = len(store.projects)
        parts = [f"{total} project{'s' if total != 1 else ''}", f"{pinned} pinned"]
        if len(projects) != total:
            parts.insert(1, f"{len(projects)} shown")
        self.set_subtitle(" · ".join(parts))

        self.flow.clear()
        clear_layout(self.list_lay)
        clear_layout(self.empty_host)
        self._cards.clear()
        if not store.projects:
            self.host.setVisible(False)
            self.empty_host.addWidget(EmptyState(
                "fa5s.folder-plus", "No projects yet", "",
                "New project", lambda: self.ctx.navigate.emit("new_project", None)))
            return
        if not projects:
            self.host.setVisible(False)
            what = f"“{query}”" if query else "these filters"
            self.empty_host.addWidget(EmptyState("fa5s.search", f"Nothing matches {what}",
                                                 "Search looks at the name, client, job number, tags and item paths.",
                                                 "Clear search and filters", self._clear_filters, action_icon="fa5s.times"))
            return
        grid = self.ctx.settings.view_mode == "grid"
        self.host.setVisible(grid)
        for p in projects:
            w = ProjectCard(p) if grid else ProjectRow(p)
            w.set_health(self.ctx.health_for(p.id))
            w.launch_requested.connect(lambda proj: self.ctx.launch(proj, parent=self))
            w.open_requested.connect(lambda proj: self.ctx.navigate.emit("project", proj))
            w.menu_requested.connect(lambda proj, pos: self.ctx.navigate.emit("project_menu", (proj, pos)))
            if grid:
                w.launch_set_requested.connect(lambda proj, ls: self.ctx.launch(proj, ls, parent=self))
                w.pin_requested.connect(lambda proj: self.ctx.store.toggle_pin(proj.id))
                w.favorite_requested.connect(lambda proj: self.ctx.store.toggle_favorite(proj.id))
                self.flow.addWidget(w)
            else:
                self.list_lay.addWidget(w)
            self._cards[p.id] = w
        self.host.updateGeometry()

    # ------------------------------------------------------------- drag/drop
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop_hint.show()

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self.drop_hint.hide()

    def dropEvent(self, e) -> None:  # noqa: N802
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        self.drop_hint.hide()
        if not paths:
            return
        e.acceptProposedAction()
        first = paths[0]
        name = os.path.basename(first.rstrip("\\/")) or "New project"
        proj = M.Project(name=name, items=[M.Item(path=os.path.normpath(p), kind=M.guess_kind(p)) for p in paths])
        self.ctx.navigate.emit("new_project", proj)
