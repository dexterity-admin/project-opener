"""Home dashboard: greeting, quick launch, stats, team pulse, announcements, attention list."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, clear_layout
from project_opener.ui.widgets.cards import ProjectCard, StatTile, relative_time
from project_opener.ui.widgets.common import Avatar, Badge, Button, IconButton, IconCircle, label
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout


def greeting() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


class HomePage(Page):
    route = "home"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self.row = self.title_row(f"{greeting()}, {ctx.display_name()}", "", "DASHBOARD")
        self.row.addWidget(self._header_buttons())
        self.banner_host = QVBoxLayout()
        self.banner_host.setSpacing(8)
        self.content.addLayout(self.banner_host)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(12)
        self.content.addLayout(self.stats_row)

        self.quick_col = self.section("Quick launch")
        self.quick_host = QWidget()
        self.quick_flow = FlowLayout(self.quick_host, 0, 14, 14)
        self.quick_col.addWidget(self.quick_host)

        # Box layouts only (see detail.py): grids + wrapped labels thrash layout.
        cols = QHBoxLayout()
        cols.setSpacing(16)
        self.attention_panel, self.attention_lay = self.panel()
        self.pulse_panel, self.pulse_lay = self.panel()
        self.history_panel, self.history_lay = self.panel()
        cols.addWidget(self.attention_panel, 1, Qt.AlignmentFlag.AlignTop)
        cols.addWidget(self.pulse_panel, 1, Qt.AlignmentFlag.AlignTop)
        self.content.addLayout(cols)
        self.content.addWidget(self.history_panel)
        self.content.addStretch(1)

        ctx.projects_changed.connect(self.refresh)
        ctx.health_updated.connect(lambda _pid: self._render_attention())
        ctx.hub_changed.connect(lambda _s: self._render_hub())
        ctx.peers_changed.connect(lambda _p: self._render_hub())
        self.refresh()

    def _header_buttons(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        b = Button("Search", "fa5s.search")
        b.clicked.connect(lambda: self.ctx.navigate.emit("palette", None))
        lay.addWidget(b)
        n = Button("New project", "fa5s.plus", "primary")
        n.clicked.connect(lambda: self.ctx.navigate.emit("new_project", None))
        lay.addWidget(n)
        return w

    # ------------------------------------------------------------ refresh
    def on_show(self) -> None:
        self.title_label.setText(f"{greeting()}, {self.ctx.display_name()}")
        self.refresh()
        self.ctx.refresh_hub()

    def refresh(self) -> None:
        self._render_stats()
        self._render_quick()
        self._render_attention()
        self._render_history()
        self._render_hub()

    def _render_stats(self) -> None:
        clear_layout(self.stats_row)
        st = self.ctx.store.stats()
        t = theme.current()
        self.stats_row.addWidget(StatTile("Projects", str(st["projects"]), "fa5s.th-large"))
        self.stats_row.addWidget(StatTile("Items linked", str(st["items"]), "fa5s.link", t.info))
        self.stats_row.addWidget(StatTile("Launches today", str(st["launches_today"]), "fa5s.play", t.success))
        online = sum(1 for p in self.ctx.peers if p.online and p.user != self.ctx.user)
        self.stats_row.addWidget(StatTile("Colleagues online", str(online), "fa5s.users", "#8B5CF6"))

    def _render_quick(self) -> None:
        self.quick_flow.clear()
        store = self.ctx.store
        pinned = [p for p in store.sorted_projects("smart") if p.pinned]
        recent = [p for p in store.recent(8) if not p.pinned]
        shown = (pinned + recent)[:8]
        if len(shown) < 8:
            seen = {p.id for p in shown}
            shown += [p for p in store.sorted_projects("smart") if p.id not in seen][:8 - len(shown)]
        if not shown:
            self.quick_flow.addWidget(EmptyState("fa5s.folder-plus", "No projects yet",
                                                 "Create your first project, or import from Project Opener 1.x / 2.x in Settings → Data.",
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

    def _render_attention(self) -> None:
        clear_layout(self.attention_lay)
        t = theme.current()
        head = QHBoxLayout()
        head.addWidget(label("NEEDS ATTENTION", "eyebrow"))
        head.addStretch(1)
        rb = IconButton("fa5s.redo", "Re-check all paths", size=12)
        rb.clicked.connect(self.ctx.refresh_all_health)
        head.addWidget(rb)
        self.attention_lay.addLayout(head)
        problems = []
        for p in self.ctx.store.projects:
            h = self.ctx.health_for(p.id)
            if h and h.problems:
                problems.append((p, h))
        if not problems:
            row = QHBoxLayout()
            row.addWidget(IconCircle("fa5s.check", t.success, 32))
            row.addWidget(label("All linked paths are reachable right now.", "muted"), 1)
            self.attention_lay.addLayout(row)
            return
        for p, h in problems[:6]:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(IconCircle(p.icon, p.color, 30))
            col = QVBoxLayout()
            col.setSpacing(0)
            name = QLabel(p.name)
            name.setStyleSheet("font-weight: 600;")
            col.addWidget(name)
            kinds = {}
            for pr in h.problems:
                kinds[pr.status] = kinds.get(pr.status, 0) + 1
            desc = ", ".join(f"{n} {k}" for k, n in kinds.items())
            col.addWidget(label(desc, "faint"))
            row.addLayout(col, 1)
            b = Button("Review", "fa5s.arrow-right")
            b.clicked.connect(lambda _=False, proj=p: self.ctx.navigate.emit("project", proj))
            row.addWidget(b)
            self.attention_lay.addLayout(row)
        if len(problems) > 6:
            self.attention_lay.addWidget(label(f"… and {len(problems) - 6} more projects", "faint"))

    def _render_hub(self) -> None:
        clear_layout(self.pulse_lay)
        clear_layout(self.banner_host)
        t = theme.current()
        st = self.ctx.hub_status
        for a in st.announcements[:3]:
            f = QFrame()
            f.setObjectName({"warning": "banner_warn", "critical": "banner_danger"}.get(a.level, "banner"))
            lay = QHBoxLayout(f)
            lay.setContentsMargins(14, 10, 14, 10)
            ic = QLabel()
            color = {"warning": t.warning, "critical": t.danger}.get(a.level, t.accent)
            ic.setPixmap(icons.pixmap("fa5s.bullhorn", 16, color))
            lay.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            tl = QLabel(a.title)
            tl.setStyleSheet("font-weight: 700;")
            col.addWidget(tl)
            if a.body:
                col.addWidget(label(a.body, "muted", wrap=True))
            col.addWidget(label(f"{a.author} · {relative_time(a.ts)}", "faint"))
            lay.addLayout(col, 1)
            self.banner_host.addWidget(f)
        head = QHBoxLayout()
        head.addWidget(label("TEAM PULSE", "eyebrow"))
        head.addStretch(1)
        go = Button("Team Hub", "fa5s.arrow-right")
        go.setObjectName("ghost")
        go.clicked.connect(lambda: self.ctx.navigate.emit("team", None))
        head.addWidget(go)
        self.pulse_lay.addLayout(head)
        if not st.configured:
            self.pulse_lay.addWidget(label("Connect a Team Hub folder in Settings to see who is online and share projects.", "muted", wrap=True))
            return
        if not st.reachable:
            self.pulse_lay.addWidget(label(st.message, "muted", wrap=True))
            return
        online = [p for p in self.ctx.peers if p.online and p.user != self.ctx.user]
        row = QHBoxLayout()
        row.setSpacing(-6)
        for p in online[:8]:
            av = Avatar(p.label, 28, online=True)
            av.setToolTip(f"{p.label}\n{p.host} · v{p.version}" + (f"\nWorking in {p.current_project}" if p.current_project else ""))
            row.addWidget(av)
        row.addSpacing(10)
        row.addWidget(label(f"{len(online)} online" if online else "Nobody else online right now", "muted"))
        row.addStretch(1)
        self.pulse_lay.addLayout(row)
        feed = self.ctx.hub.pulse_feed(6) if self.ctx.hub.reachable() else []
        for r in feed:
            line = QHBoxLayout()
            line.setSpacing(8)
            line.addWidget(Avatar(str(r.get("name") or r.get("user", "?")), 20))
            who = str(r.get("name") or r.get("user", ""))
            ev = str(r.get("event", ""))
            det = str(r.get("detail", ""))
            verb = {"launched": "opened", "published": "published", "sent": "sent"}.get(ev, ev)
            lbl = label(f"<b>{who}</b> {verb} {det}", "muted")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            line.addWidget(lbl, 1)
            line.addWidget(label(relative_time(str(r.get("ts", ""))), "faint"))
            self.pulse_lay.addLayout(line)
        if st.inbox:
            b = Button(f"{st.inbox} project(s) waiting in your inbox", "fa5s.inbox", "primary")
            b.clicked.connect(lambda: self.ctx.navigate.emit("team", "inbox"))
            self.pulse_lay.addWidget(b)

    def _render_history(self) -> None:
        clear_layout(self.history_lay)
        self.history_lay.addWidget(label("RECENT ACTIVITY", "eyebrow"))
        rows = self.ctx.store.history(8)
        if not rows:
            self.history_lay.addWidget(label("Launches will appear here.", "muted"))
            return
        t = theme.current()
        for r in rows:
            line = QHBoxLayout()
            line.setSpacing(10)
            ic = QLabel()
            ok = int(r.get("missing", 0) or 0) == 0
            ic.setPixmap(icons.pixmap("fa5s.play-circle" if ok else "fa5s.exclamation-circle", 14, t.success if ok else t.warning))
            line.addWidget(ic)
            text = f"<b>{r.get('project', '')}</b>" + (f" › {r.get('set')}" if r.get("set") else "")
            lbl = QLabel(text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            line.addWidget(lbl, 1)
            line.addWidget(Badge(f"{r.get('ok', r.get('count', 0))} opened", t.text_muted))
            line.addWidget(label(relative_time(str(r.get("ts", ""))), "faint"))
            self.history_lay.addLayout(line)
