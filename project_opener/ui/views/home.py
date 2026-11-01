"""Home: greeting, the finding, quick launch, attention list, team pulse, recent activity.

The screen's one question (PRODUCT.md): which job do I open now, and is anything
wrong with it?  So the cards are the biggest block and come first; every other
panel leads with its own number instead of a KPI strip above them all.
"""
from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from project_opener.core.health import path_root, root_key, roots_health
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, badge, clear_layout, make_transparent, row_widget, section_label
from project_opener.ui.views.detail import STATUS_META
from project_opener.ui.widgets.cards import ProjectCard, plural, relative_time
from project_opener.ui.widgets.common import Avatar, Button, ElidedLabel, label
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout

ROWS = 4            # rows per side panel, so the two share a bottom edge
NARROW_W = 960      # page width below which the drive map and Team pulse stack (1040-px window → 808)
QUICK = 3           # one row of cards: the question block below stays on the first screen
ACTION_W = 120      # the action column on the drive and path rows, kept on rows without an action
USES_W = 118        # two job numbers fit; longer lists elide with the full text in the tooltip
DRIVE_LIKE = re.compile(r"^([A-Za-z]:|\\\\)")


def uses_text(projects: list) -> str:
    """Who uses a root: "1 project · P12513", or the jobs themselves ("P12513 · ANTEO", up to two,
    then "+N") when the button beside it already carries the count."""
    if len(projects) == 1:
        p = projects[0]
        return f"1 project · {p.spine or p.name}"
    names = [p.spine or p.name for p in projects]
    text = " · ".join(names[:2])
    return text + (f" +{len(names) - 2}" if len(names) > 2 else "")


def open_button(ctx, projects: list, root_filter: str):
    """The office's verb: "Open P12513" for one project, "2 projects" (Projects filtered to them) for more."""
    if len(projects) == 1:
        p = projects[0]
        b = Button(f"Open {p.spine}" if p.spine else "Open project")      # text only: it must fit the 120 px slot
        b.setToolTip(p.title)
        b.clicked.connect(lambda _=False, proj=p: ctx.navigate.emit("project", proj))
    else:
        b = Button(plural(len(projects), "project"))
        b.setToolTip("Show these projects")
        b.clicked.connect(lambda _=False, q=root_filter: ctx.navigate.emit("projects", q))
    return b


def greeting() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


def _icon_label(name: str, size: int = 16, color: str | None = None) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(icons.pixmap(name, size, color or theme.current().text_muted))
    lbl.setFixedWidth(size + 2)
    return lbl


def pulse_detail(hub, detail: str) -> str:
    """A pulse row's detail with any trailing "→ login" shown as the colleague's display name."""
    if " → " in detail:
        head, _, who = detail.rpartition(" → ")
        return f"{head} → {hub.display_name_for(who)}"
    return detail


def _count_head(text: str, count: str = "") -> QHBoxLayout:
    """Section heading with its number after it, in grey, tabular."""
    head = QHBoxLayout()
    head.setSpacing(8)
    head.addWidget(section_label(text))
    if count:
        c = label(count, "muted")
        c.setFont(theme.ui_font(theme.current().font_size + 2, 400, tabular=True))
        head.addWidget(c)
    head.addStretch(1)
    return head


class HomePage(Page):
    route = "home"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self.row = self.title_row(f"{greeting()}, {ctx.display_name()}", "")
        new = Button("New project", "fa5s.plus", "primary")
        new.clicked.connect(lambda: self.ctx.navigate.emit("new_project", None))
        self.row.addWidget(new, 0, Qt.AlignmentFlag.AlignTop)
        self.banner_host = QVBoxLayout()
        self.banner_host.setSpacing(8)
        self.content.addLayout(self.banner_host)

        all_btn = Button("All projects", "fa5s.arrow-right", "ghost")
        all_btn.clicked.connect(lambda: self.ctx.navigate.emit("projects", None))
        self.quick_col = self.section("Quick launch", trailing=all_btn)
        self.quick_host = QWidget()
        self.quick_flow = FlowLayout(self.quick_host, 0, 16, 16, justify=True)
        self.quick_col.addWidget(self.quick_host)
        self.quick_empty_host = QVBoxLayout()
        self.quick_col.addLayout(self.quick_empty_host)

        # Box layouts only (see detail.py): grids + wrapped labels thrash layout.
        # The two panels share a row and a bottom edge: both stretch, content top-aligned.
        # Below NARROW_W the two columns stack, so the page never outgrows the 1040-px window.
        self.cols = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.cols.setSpacing(16)
        self._stacked = False
        cols = self.cols
        left = QVBoxLayout()
        left.setSpacing(16)
        self.drives_panel, self.drives_lay = self.panel()      # health by cause: the office's drive map
        self.attention_panel, self.attention_lay = self.panel()   # health by symptom: paths not explained by a root
        left.addWidget(self.drives_panel)
        left.addWidget(self.attention_panel)
        left.addStretch(1)                       # each panel keeps its own height (no blank band inside a card)
        self.pulse_panel, self.pulse_lay = self.panel()
        cols.addLayout(left, 1)
        cols.addWidget(self.pulse_panel, 1, Qt.AlignmentFlag.AlignTop)
        self.content.addLayout(cols)
        self.history_panel, self.history_lay = self.panel()
        self.content.addWidget(self.history_panel)
        self.content.addStretch(1)

        self._show_reachable = False
        self.bind(ctx.projects_changed, self.refresh)
        self.bind(ctx.health_updated, lambda _pid: (self._render_drives(), self._render_attention(), self._render_finding()))
        self.bind(ctx.hub_changed, lambda _s: self._render_hub())
        self.bind(ctx.peers_changed, lambda _p: self._render_hub())
        self.refresh()

    # ------------------------------------------------------------ refresh
    def on_show(self) -> None:
        self.title_label.setText(f"{greeting()}, {self.ctx.display_name()}")
        self.refresh()
        self.ctx.refresh_hub()

    def refresh(self) -> None:
        self._render_quick()
        self._render_drives()
        self._render_attention()
        self._render_history()
        self._render_hub()
        self._render_finding()

    def _online_count(self) -> int:
        return sum(1 for p in self.ctx.peers if p.online and p.user != self.ctx.user)

    def _problems(self) -> list[tuple]:
        """(project, health) for every project with at least one item that is not reachable."""
        out = []
        for p in self.ctx.store.projects:
            h = self.ctx.health_for(p.id)
            if h and h.problems:
                out.append((p, h))
        return out

    def _render_finding(self) -> None:
        """The one grey line under the greeting: what needs the user, from real data."""
        st = self.ctx.store.stats()
        parts = []
        problems = self._problems()
        n_items = sum(len(h.problems) for _p, h in problems)
        if n_items:
            where = plural(len(problems), "project")
            parts.append(f"{plural(n_items, 'path')} need{'s' if n_items == 1 else ''} attention in {where}")
        online = self._online_count()
        if online:
            parts.append(f"{plural(online, 'colleague')} online")
        launches = int(st.get("launches_today", 0) or 0)
        if launches:
            parts.append(f"{launches} launch{'es' if launches != 1 else ''} today")
        if not self.ctx.store.projects:
            self.set_subtitle("Nothing to open yet")
            return
        if any(self.ctx.health_for(p.id) is None for p in self.ctx.store.projects):
            parts.append("checking paths…")
        self.set_subtitle(" · ".join(parts) if parts else "Every linked path is reachable")

    def _render_quick(self) -> None:
        self.quick_flow.clear()
        clear_layout(self.quick_empty_host)
        store = self.ctx.store
        pinned = [p for p in store.sorted_projects("smart") if p.pinned]
        recent = [p for p in store.recent(QUICK) if not p.pinned]
        shown = (pinned + recent)[:QUICK]
        if len(shown) < QUICK:
            seen = {p.id for p in shown}
            shown += [p for p in store.sorted_projects("smart") if p.id not in seen][:QUICK - len(shown)]
        self.quick_host.setVisible(bool(shown))
        if not shown:
            self.quick_empty_host.addWidget(EmptyState(
                "fa5s.folder-plus", "No projects yet", "",
                "New project", lambda: self.ctx.navigate.emit("new_project", None)))
            return
        for p in shown:
            card = ProjectCard(p)
            card.set_health(self.ctx.health_for(p.id))
            card.launch_requested.connect(lambda proj: self.ctx.launch(proj, parent=self))
            card.launch_set_requested.connect(lambda proj, ls: self.ctx.launch(proj, ls, parent=self))
            card.open_requested.connect(lambda proj: self.ctx.navigate.emit("project", proj))
            card.menu_requested.connect(lambda proj, pos: self.ctx.navigate.emit("project_menu", (proj, pos)))
            card.pin_requested.connect(lambda proj: self.ctx.store.toggle_pin(proj.id))
            card.favorite_requested.connect(lambda proj: self.ctx.store.toggle_favorite(proj.id))
            self.quick_flow.addWidget(card)
        self.quick_host.updateGeometry()

    def _render_drives(self) -> None:
        """Health by cause: every drive letter, share and variable the projects depend on, as this
        PC sees it, with the projects that use it.  The one thing only this product knows."""
        clear_layout(self.drives_lay)
        projects = self.ctx.store.projects
        roots = roots_health(projects, self.ctx.health, self.ctx.resolver.drive_map)
        down = [r for r in roots if r.status != "ok"]
        fine = [r for r in roots if r.status == "ok"]
        head = _count_head("Drives on this PC", (f"{len(down)} down" if down else "all reachable") if roots else "")
        if projects:
            rb = Button("Re-check", "fa5s.redo", "ghost")
            rb.setToolTip("Check every path again (F5)")
            rb.clicked.connect(self.ctx.refresh_all_health)
            head.addWidget(rb)
        else:
            spacer = QWidget()
            make_transparent(spacer)
            spacer.setFixedSize(1, theme.current().control_h)
            head.addWidget(spacer)
        self.drives_lay.addLayout(head)
        if not roots:
            if not projects:
                text = "No paths to check yet."
            elif any(self.ctx.health_for(p.id) is None for p in projects):
                text = "Checking paths…"
            else:
                text = "No drives, shares or variables in use."
            self.drives_lay.addWidget(label(text, "muted"))
            return
        by_id = {p.id: p for p in projects}
        shown = down + (fine if self._show_reachable else [])
        for r in shown:
            self.drives_lay.addWidget(self._root_row(r, by_id))
        if fine:
            n = len(fine)
            word = "drive" if all(DRIVE_LIKE.match(r.root) for r in fine) else "root"
            toggle = Button(f"{plural(n, word)} reachable", "fa5s.angle-down" if not self._show_reachable else "fa5s.angle-up", "ghost")
            toggle.setToolTip("Show them" if not self._show_reachable else "Hide them")
            toggle.clicked.connect(self._toggle_reachable)
            self.drives_lay.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.drives_lay.addStretch(1)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self.set_stacked(self.width() < NARROW_W)

    def set_stacked(self, stacked: bool) -> None:
        if stacked == self._stacked:
            return
        self._stacked = stacked
        self.cols.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)

    def _toggle_reachable(self) -> None:
        self._show_reachable = not self._show_reachable
        self._render_drives()

    def _root_row(self, r, by_id: dict) -> QWidget:
        """One drive, share or variable: its name (and the letter's mapping), who uses it, its pill,
        and an action only where the row needs doing."""
        two_lines = bool(r.mapping)
        w, row = row_widget(44 if two_lines else 40)
        row.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = ElidedLabel(r.root, mode=Qt.TextElideMode.ElideMiddle)     # elides, so a long share never widens the page
        name.setFont(theme.ui_font(weight=500))
        name.setToolTip(r.root)
        col.addWidget(name)
        if two_lines:
            mapping = ElidedLabel(r.mapping, mode=Qt.TextElideMode.ElideMiddle)      # "Z: → \\nas01\Project"
            mapping.setObjectName("faint")
            mapping.setFont(theme.ui_font(9))
            mapping.setToolTip(r.mapping)
            col.addWidget(mapping)
        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(col)
        holder.setMinimumWidth(84)
        row.addWidget(holder, 1)                  # the share name is the fact the row exists for: it takes the slack
        projs = [by_id[pid] for pid in r.projects if pid in by_id]
        used_lbl = ElidedLabel(uses_text(projs), mode=Qt.TextElideMode.ElideRight)
        used_lbl.setObjectName("faint")
        used_lbl.setToolTip(" · ".join(p.title for p in projs))
        used_lbl.setFixedWidth(USES_W)            # a fixed jobs column, so the mapping never elides while there is room
        row.addWidget(used_lbl)
        level, text = STATUS_META.get(r.status, ("warn", r.status))
        pill = badge(text, level)
        pill.setToolTip(f"{plural(r.items, 'item')} under {r.root}")
        row.addWidget(pill)
        slot = QWidget()                              # the action column keeps its width on every row
        make_transparent(slot)
        slot.setFixedWidth(ACTION_W)
        sl = QHBoxLayout(slot)
        sl.setContentsMargins(0, 0, 0, 0)
        if r.status != "ok" and projs:
            sl.addWidget(open_button(self.ctx, projs, f"root:{r.root}"))
        row.addWidget(slot)
        return w

    def _render_attention(self) -> None:
        """Health by symptom: one row per path that is not reachable *and* is not explained by its
        root (a file gone from a drive that answers), with the same status pill as the project page
        and the launch sheet."""
        clear_layout(self.attention_lay)
        drive_map = self.ctx.resolver.drive_map
        roots = {r.root: r for r in roots_health(self.ctx.store.projects, self.ctx.health, drive_map)}
        rows: list[tuple] = []
        for p, h in self._problems():
            for pr in h.problems:
                item = next((i for i in p.items if i.id == pr.item_id), None)
                if item is None:
                    continue
                root = roots.get(root_key(path_root(item.path), drive_map)[0])
                if root is not None and root.status != "ok":
                    continue                        # explained by the drive, share or variable above
                rows.append((p, item, pr))
        self.attention_panel.setVisible(bool(rows))
        if not rows:
            return
        head = _count_head("Needs attention", str(len(rows)))
        self.attention_lay.addLayout(head)
        for p, item, pr in rows[:ROWS]:
            w, row = row_widget(44)
            row.setSpacing(10)
            row.addWidget(_icon_label(p.icon))
            col = QVBoxLayout()
            col.setSpacing(0)
            name = ElidedLabel(item.display_name, mode=Qt.TextElideMode.ElideRight)
            name.setFont(theme.ui_font(weight=500))
            col.addWidget(name)
            sub = ElidedLabel(p.title, mode=Qt.TextElideMode.ElideRight)
            sub.setObjectName("faint")
            col.addWidget(sub)
            holder = QWidget()
            make_transparent(holder)
            holder.setLayout(col)
            holder.setMinimumWidth(84)
            row.addWidget(holder, 1)
            level, text = STATUS_META.get(pr.status, ("warn", pr.status))
            pill = badge(text, level)
            pill.setToolTip(pr.detail or pr.resolved)
            row.addWidget(pill)
            slot = QWidget()
            make_transparent(slot)
            slot.setFixedWidth(ACTION_W)
            sl = QHBoxLayout(slot)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.addWidget(open_button(self.ctx, [p], ""))
            row.addWidget(slot)
            self.attention_lay.addWidget(w)
        if len(rows) > ROWS:
            b = Button(f"{len(rows) - ROWS} more", "fa5s.arrow-right", "ghost")
            b.clicked.connect(lambda: self.ctx.navigate.emit("projects", None))
            self.attention_lay.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        self.attention_lay.addStretch(1)

    def _render_hub(self) -> None:
        clear_layout(self.pulse_lay)
        clear_layout(self.banner_host)
        t = theme.current()
        st = self.ctx.hub_status
        anns = sorted(st.announcements, key=lambda a: a.ts, reverse=True)
        if anns:                                   # the newest only, one band; the rest are one click away
            a = anns[0]
            f = QFrame()
            f.setObjectName({"warning": "banner_warn", "critical": "banner_danger"}.get(a.level, "banner"))
            lay = QHBoxLayout(f)
            lay.setContentsMargins(14, 8, 10, 8)
            lay.setSpacing(10)
            color = {"warning": t.warning, "critical": t.danger}.get(a.level, t.info)
            lay.addWidget(_icon_label("fa5s.bullhorn", 16, color), 0, Qt.AlignmentFlag.AlignVCenter)
            tl = QLabel(a.title)
            tl.setFont(theme.ui_font(weight=600))
            lay.addWidget(tl)
            body = ElidedLabel(" ".join(a.body.split()), mode=Qt.TextElideMode.ElideRight)
            body.setObjectName("muted")
            lay.addWidget(body, 1)
            who = f"{self.ctx.hub.display_name_for(a.author)} · {relative_time(a.ts).lower()}"
            lay.addWidget(label(who, "faint"))
            more = Button(f"+{len(anns) - 1} more" if len(anns) > 1 else "Team Hub", "fa5s.arrow-right", "ghost")
            more.clicked.connect(lambda: self.ctx.navigate.emit("team", "announcements"))
            lay.addWidget(more)
            self.banner_host.addWidget(f)
        online = [p for p in self.ctx.peers if p.online and p.user != self.ctx.user]
        head = _count_head("Team pulse", f"{len(online)} online" if (st.configured and st.reachable) else "")
        if st.configured:
            go = Button("Team Hub", "fa5s.arrow-right", "ghost")
            go.clicked.connect(lambda: self.ctx.navigate.emit("team", None))
        else:
            go = Button("Connect a hub folder", "fa5s.plug", "ghost")
            go.clicked.connect(lambda: self.ctx.navigate.emit("settings", "hub"))
        head.addWidget(go)
        self.pulse_lay.addLayout(head)
        if not st.configured or not st.reachable:
            msg = "Team Hub not connected." if not st.configured else st.message
            self.pulse_lay.addWidget(label(msg, "muted", wrap=True))
            if online:  # UDP presence works without a hub folder
                self._avatar_row(online, f"{len(online)} online on the LAN")
            self.pulse_lay.addStretch(1)
            return
        self._avatar_row(online, "" if online else "Nobody else online right now")
        feed = self.ctx.hub.pulse_feed(ROWS) if self.ctx.hub.reachable() else []
        for r in feed:
            w, line = row_widget(32)
            line.setSpacing(8)
            line.addWidget(Avatar(str(r.get("name") or r.get("user", "?")), 20))
            who = str(r.get("name") or self.ctx.hub.display_name_for(str(r.get("user", ""))))
            ev = str(r.get("event", ""))
            det = pulse_detail(self.ctx.hub, str(r.get("detail", "")))
            verb = {"launched": "opened", "published": "published", "sent": "sent"}.get(ev, ev)
            lbl = label(f"<b>{who}</b> {verb} {det}", "muted")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)   # never widens the page
            line.addWidget(lbl, 1)
            tm = label(relative_time(str(r.get("ts", ""))).lower(), "faint")
            tm.setFont(theme.ui_font(t.font_size - 1, tabular=True))
            line.addWidget(tm)
            self.pulse_lay.addWidget(w)
        self.pulse_lay.addStretch(1)
        if st.inbox:
            b = Button(f"{plural(st.inbox, 'project')} waiting in your inbox", "fa5s.inbox")
            b.clicked.connect(lambda: self.ctx.navigate.emit("team", "inbox"))
            self.pulse_lay.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)

    def _avatar_row(self, online: list, text: str) -> None:
        if not online and not text:
            return
        w, row = row_widget(32)
        row.setSpacing(-6)
        for p in online[:8]:
            av = Avatar(p.label, 28, online=True)
            av.setToolTip(f"{p.label}\n{p.host} · v{p.version}" + (f"\nWorking in {p.current_project}" if p.current_project else ""))
            row.addWidget(av)
        if online:
            row.addSpacing(10)
        if text:
            row.addWidget(label(text, "muted"))
        row.addStretch(1)
        self.pulse_lay.addWidget(w)

    def _render_history(self) -> None:
        clear_layout(self.history_lay)
        rows = self.ctx.store.history(8)
        today = int(self.ctx.store.stats().get("launches_today", 0) or 0)
        self.history_lay.addLayout(_count_head("Recent activity", f"{today} today" if today else ""))
        if not rows:
            self.history_lay.addWidget(label("Nothing opened yet.", "muted"))
            return
        t = theme.current()
        for r in rows:
            w, line = row_widget(40)
            ok = int(r.get("missing", 0) or 0) == 0
            line.addWidget(_icon_label("fa5s.play-circle" if ok else "fa5s.exclamation-circle", 16, t.text_muted if ok else t.warning))
            name = QLabel(str(r.get("project", "")))
            name.setFont(theme.ui_font(weight=500))
            line.addWidget(name)
            if r.get("set"):
                line.addWidget(label(f"› {r.get('set')}", "muted"))
            line.addStretch(1)
            opened = int(r.get("ok", r.get("count", 0)) or 0)
            line.addWidget(badge(plural(opened, "item") + " opened", "neutral"))
            tm = label(relative_time(str(r.get("ts", ""))).lower(), "faint")
            tm.setFont(theme.ui_font(t.font_size - 1, tabular=True))
            tm.setMinimumWidth(72)
            tm.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            line.addWidget(tm)
            self.history_lay.addWidget(w)
