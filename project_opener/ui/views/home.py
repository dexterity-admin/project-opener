"""Home: greeting, the finding, quick launch, KPI strip, attention list, team pulse, recent activity."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import KpiStrip, Page, badge, clear_layout, row_widget, section_label
from project_opener.ui.widgets.cards import ProjectCard, relative_time
from project_opener.ui.widgets.common import Avatar, Button, IconButton, label
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout


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


class HomePage(Page):
    route = "home"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self.row = self.title_row(f"{greeting()}, {ctx.display_name()}", "")
        self.row.addWidget(self._header_buttons(), 0, Qt.AlignmentFlag.AlignTop)
        self.banner_host = QVBoxLayout()
        self.banner_host.setSpacing(8)
        self.content.addLayout(self.banner_host)

        self.kpis = KpiStrip([("Projects", "0"), ("Items linked", "0"), ("Launches today", "0"), ("Colleagues online", "0")])
        self.content.addWidget(self.kpis)

        self.quick_col = self.section("Quick launch")
        self.quick_host = QWidget()
        self.quick_flow = FlowLayout(self.quick_host, 0, 16, 16, justify=True)
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

        self.bind(ctx.projects_changed, self.refresh)
        self.bind(ctx.health_updated, lambda _pid: (self._render_attention(), self._render_finding()))
        self.bind(ctx.hub_changed, lambda _s: self._render_hub())
        self.bind(ctx.peers_changed, lambda _p: (self._render_hub(), self._render_stats()))
        self.refresh()

    def _header_buttons(self) -> QWidget:
        w, lay = row_widget(theme.current().control_h)
        lay.setSpacing(8)
        b = Button("Search  Ctrl+K", "fa5s.search", "ghost")
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
        self._render_finding()

    def _online_count(self) -> int:
        return sum(1 for p in self.ctx.peers if p.online and p.user != self.ctx.user)

    def _attention_count(self) -> int:
        n = 0
        for p in self.ctx.store.projects:
            h = self.ctx.health_for(p.id)
            if h and h.problems:
                n += 1
        return n

    def _render_finding(self) -> None:
        """The one grey line under the greeting: what needs the user, from real data."""
        st = self.ctx.store.stats()
        parts = []
        n = self._attention_count()
        if n:
            parts.append(f"{n} item{'s' if n != 1 else ''} need{'' if n != 1 else 's'} attention")
        online = self._online_count()
        if online:
            parts.append(f"{online} colleague{'s' if online != 1 else ''} online")
        launches = int(st.get("launches_today", 0) or 0)
        if launches:
            parts.append(f"{launches} launch{'es' if launches != 1 else ''} today")
        self.set_subtitle(" · ".join(parts) if parts else "Everything reachable")

    def _render_stats(self) -> None:
        st = self.ctx.store.stats()
        self.kpis.set_values([str(st["projects"]), str(st["items"]), str(st["launches_today"]), str(self._online_count())])

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
        head = QHBoxLayout()
        head.addWidget(section_label("Needs attention"))
        head.addStretch(1)
        rb = IconButton("fa5s.redo", "Re-check all paths", size=14)
        rb.clicked.connect(self.ctx.refresh_all_health)
        head.addWidget(rb)
        self.attention_lay.addLayout(head)
        problems = []
        for p in self.ctx.store.projects:
            h = self.ctx.health_for(p.id)
            if h and h.problems:
                problems.append((p, h))
        if not problems:
            self.attention_lay.addWidget(label("All linked paths are reachable right now.", "muted", wrap=True))
            return
        for p, h in problems[:6]:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(_icon_label(p.icon))
            col = QVBoxLayout()
            col.setSpacing(0)
            name = QLabel(p.name)
            name.setFont(theme.ui_font(weight=500))
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
            lay.setSpacing(10)
            color = {"warning": t.warning, "critical": t.danger}.get(a.level, t.info)
            lay.addWidget(_icon_label("fa5s.bullhorn", 16, color), 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(0)
            tl = QLabel(a.title)
            tl.setFont(theme.ui_font(weight=600))
            col.addWidget(tl)
            if a.body:
                col.addWidget(label(a.body, "muted", wrap=True))
            col.addWidget(label(f"{a.author} · {relative_time(a.ts)}", "faint"))
            lay.addLayout(col, 1)
            self.banner_host.addWidget(f)
        head = QHBoxLayout()
        head.addWidget(section_label("Team pulse"))
        head.addStretch(1)
        go = Button("Team Hub", "fa5s.arrow-right", "ghost")
        go.clicked.connect(lambda: self.ctx.navigate.emit("team", None))
        head.addWidget(go)
        self.pulse_lay.addLayout(head)
        online = [p for p in self.ctx.peers if p.online and p.user != self.ctx.user]
        if not st.configured or not st.reachable:
            msg = ("Connect a Team Hub folder in Settings to see who is online and share projects."
                   if not st.configured else st.message)
            self.pulse_lay.addWidget(label(msg, "muted", wrap=True))
            if online:  # UDP presence works without a hub folder
                row = QHBoxLayout()
                row.setSpacing(-6)
                for p in online[:8]:
                    av = Avatar(p.label, 28, online=True)
                    av.setToolTip(f"{p.label}\n{p.host} · v{p.version}")
                    row.addWidget(av)
                row.addSpacing(10)
                row.addWidget(label(f"{len(online)} online on the LAN", "muted"))
                row.addStretch(1)
                self.pulse_lay.addLayout(row)
            return
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
            b = Button(f"{st.inbox} project(s) waiting in your inbox", "fa5s.inbox")
            b.clicked.connect(lambda: self.ctx.navigate.emit("team", "inbox"))
            self.pulse_lay.addWidget(b)

    def _render_history(self) -> None:
        clear_layout(self.history_lay)
        self.history_lay.addWidget(section_label("Recent activity"))
        rows = self.ctx.store.history(8)
        if not rows:
            self.history_lay.addWidget(label("Launches will appear here.", "muted"))
            return
        t = theme.current()
        for r in rows:
            w, line = row_widget(44)
            ok = int(r.get("missing", 0) or 0) == 0
            line.addWidget(_icon_label("fa5s.play-circle" if ok else "fa5s.exclamation-circle", 16, t.text_muted if ok else t.warning))
            name = QLabel(str(r.get("project", "")))
            name.setFont(theme.ui_font(weight=500))
            line.addWidget(name)
            if r.get("set"):
                line.addWidget(label(f"› {r.get('set')}", "muted"))
            line.addStretch(1)
            line.addWidget(badge(f"{r.get('ok', r.get('count', 0))} opened", "neutral"))
            tm = label(relative_time(str(r.get("ts", ""))), "faint")
            tm.setFont(theme.ui_font(theme.current().font_size - 1, tabular=True))
            line.addWidget(tm)
            self.history_lay.addWidget(w)
