"""Team Hub: presence, published projects, inbox, announcements, pulse."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from project_opener.core import models as M
from project_opener.lan.hub import InboxMessage, PublishedProject
from project_opener.ui import theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, clear_layout
from project_opener.ui.widgets.cards import relative_time
from project_opener.ui.widgets.common import Avatar, Badge, Button, IconButton, IconCircle, label
from project_opener.ui.widgets.dialogs import AnnouncementDialog, confirm
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout


class TeamPage(Page):
    route = "team"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        row = self.title_row("Team Hub", "Share projects, see who is online and keep everyone on the same drawings.", "COLLABORATION")
        self.status_badge = Badge("", theme.current().text_faint)
        row.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        refresh = Button("Refresh", "fa5s.sync-alt")
        refresh.clicked.connect(self._refresh_now)
        row.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        self.setup_btn = Button("Connect a hub folder", "fa5s.plug", "primary")
        self.setup_btn.clicked.connect(lambda: ctx.navigate.emit("settings", "hub"))
        row.addWidget(self.setup_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.presence_host = QWidget()
        self.presence_flow = FlowLayout(self.presence_host, 0, 10, 10)
        self.content.addWidget(label("ONLINE NOW", "eyebrow"))
        self.content.addWidget(self.presence_host)

        self.tabs = QTabWidget()
        self.tab_published = QWidget()
        self.tab_inbox = QWidget()
        self.tab_ann = QWidget()
        self.tab_pulse = QWidget()
        for w, title in ((self.tab_published, "Published projects"), (self.tab_inbox, "Inbox"),
                         (self.tab_ann, "Announcements"), (self.tab_pulse, "Activity")):
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 12, 0, 0)
            lay.setSpacing(10)
            self.tabs.addTab(w, title)
        self.content.addWidget(self.tabs)
        self.content.addStretch(1)
        ctx.hub_changed.connect(lambda _s: self.refresh())
        ctx.peers_changed.connect(lambda _p: self._render_presence())
        self.refresh()

    def on_show(self, section: str | None = None) -> None:
        self.ctx.refresh_hub()
        self.refresh()
        if section == "inbox":
            self.tabs.setCurrentWidget(self.tab_inbox)

    def _refresh_now(self) -> None:
        self.ctx.refresh_hub()
        self.ctx.toast.emit("Refreshing hub…", "", "info")

    def refresh(self) -> None:
        st = self.ctx.hub_status
        t = theme.current()
        if not st.configured:
            self.status_badge.setText("Not connected")
            self.status_badge.set_color(t.text_faint)
        elif st.reachable:
            self.status_badge.setText(f"Connected · {st.path}")
            self.status_badge.set_color(t.success)
        else:
            self.status_badge.setText("Hub unreachable")
            self.status_badge.set_color(t.danger)
        self.setup_btn.setVisible(not st.configured)
        self.tabs.setVisible(st.configured)
        self._render_presence()
        if st.configured:
            self._render_published()
            self._render_inbox()
            self._render_announcements()
            self._render_pulse()

    # ------------------------------------------------------------ presence
    def _render_presence(self) -> None:
        self.presence_flow.clear()
        peers = [p for p in self.ctx.peers if p.user != self.ctx.user]
        if not self.ctx.hub_status.configured:
            self.presence_flow.addWidget(label("Connect a Team Hub folder (any shared folder on the office LAN) to see colleagues here.", "muted", wrap=True))
            return
        if not peers:
            self.presence_flow.addWidget(label("No colleagues seen yet. Presence appears once others run Project Opener 3 with the same hub folder.", "muted", wrap=True))
            return
        for p in peers[:30]:
            f = QFrame()
            f.setObjectName("card")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(10, 8, 12, 8)
            lay.setSpacing(10)
            lay.addWidget(Avatar(p.label, 34, online=p.online))
            col = QVBoxLayout()
            col.setSpacing(0)
            nm = QLabel(p.label)
            nm.setStyleSheet("font-weight: 600;")
            col.addWidget(nm)
            sub = p.current_project if (p.online and p.current_project) else (f"{p.host} · v{p.version}" if p.online else f"last seen {relative_time(M.parse_iso(p.ts).isoformat() if p.ts else None).lower()}")
            col.addWidget(label(sub, "faint"))
            lay.addLayout(col)
            if p.role:
                lay.addWidget(Badge(p.role, theme.current().info))
            self.presence_flow.addWidget(f)
        self.presence_host.updateGeometry()

    # ----------------------------------------------------------- published
    def _render_published(self) -> None:
        lay = self.tab_published.layout()
        clear_layout(lay)
        pubs = self.ctx.hub.published()
        head = QHBoxLayout()
        head.addWidget(label(f"{len(pubs)} project(s) published by the team. Clone one to get your own copy; subscribers are told when the author publishes a new revision.", "muted", wrap=True), 1)
        pub_btn = Button("Publish one of mine", "fa5s.cloud-upload-alt", "primary")
        pub_btn.clicked.connect(lambda: self.ctx.navigate.emit("publish_picker", None))
        head.addWidget(pub_btn)
        lay.addLayout(head)
        if not pubs:
            lay.addWidget(EmptyState("fa5s.cloud-upload-alt", "Nothing published yet", "Publish a project from its menu (⋯ → Publish to Team Hub)."))
            return
        mine = {p.origin.published_id for p in self.ctx.store.projects if p.origin.published_id}
        grid = QWidget()
        flow = FlowLayout(grid, 0, 12, 12)
        for pub in pubs:
            flow.addWidget(self._published_card(pub, pub.published_id in mine))
        lay.addWidget(grid)

    def _published_card(self, pub: PublishedProject, have: bool) -> QFrame:
        t = theme.current()
        p = pub.project
        f = QFrame()
        f.setObjectName("card")
        f.setFixedWidth(300)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(IconCircle(p.icon, p.color, 36))
        col = QVBoxLayout()
        col.setSpacing(0)
        nm = QLabel(p.name)
        nm.setStyleSheet("font-weight: 700;")
        nm.setWordWrap(True)
        col.addWidget(nm)
        col.addWidget(label(f"by {pub.author} · rev {pub.revision} · {relative_time(pub.published_at).lower()}", "faint"))
        top.addLayout(col, 1)
        lay.addLayout(top)
        if pub.description:
            lay.addWidget(label(pub.description, "muted", wrap=True))
        lay.addWidget(label(f"{len(p.items)} items · {len(p.launch_sets)} launch sets", "faint"))
        row = QHBoxLayout()
        if have:
            row.addWidget(Badge("In my workspace", t.success))
        else:
            b = Button("Clone", "fa5s.clone", "primary")
            b.clicked.connect(lambda: self._clone(pub))
            row.addWidget(b)
        row.addStretch(1)
        if pub.author == self.ctx.user:
            rm = IconButton("fa5s.trash", "Unpublish", size=12)
            rm.clicked.connect(lambda: self._unpublish(pub))
            row.addWidget(rm)
        lay.addLayout(row)
        return f

    def _clone(self, pub: PublishedProject) -> None:
        clone = pub.project.clone(pub.project.name)
        clone.origin = M.Origin(source="team", author=pub.author, published_id=pub.published_id,
                                published_at=pub.published_at, revision=pub.revision)
        self.ctx.store.add(clone)
        self.ctx.toast.emit("Cloned to your workspace", clone.name, "success")
        self.refresh()

    def _unpublish(self, pub: PublishedProject) -> None:
        if confirm(self, "Unpublish", f"Remove '{pub.project.name}' from the Team Hub? Colleagues keep their clones.", danger=True):
            self.ctx.hub.unpublish(pub.published_id)
            for p in self.ctx.store.projects:
                if p.origin.published_id == pub.published_id:
                    p.origin = M.Origin(source="local", author=self.ctx.user)
                    self.ctx.store.update(p)
            self.refresh()

    # --------------------------------------------------------------- inbox
    def _render_inbox(self) -> None:
        lay = self.tab_inbox.layout()
        clear_layout(lay)
        msgs = self.ctx.hub.inbox()
        self.tabs.setTabText(1, f"Inbox ({len(msgs)})" if msgs else "Inbox")
        if not msgs:
            lay.addWidget(EmptyState("fa5s.inbox", "Inbox empty", "Projects colleagues send you land here. Send one from a project's menu (⋯ → Send to colleague)."))
            return
        for m in msgs:
            lay.addWidget(self._inbox_card(m))

    def _inbox_card(self, m: InboxMessage) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        lay.addWidget(Avatar(m.sender, 36))
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(f"<b>{m.sender}</b> sent you <b>{m.project.name}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(title)
        if m.message:
            col.addWidget(label(f"“{m.message}”", "muted", wrap=True))
        col.addWidget(label(f"{len(m.project.items)} items · {relative_time(m.sent_at).lower()}", "faint"))
        lay.addLayout(col, 1)
        acc = Button("Accept", "fa5s.check", "primary")
        acc.clicked.connect(lambda: self._accept(m))
        lay.addWidget(acc)
        dec = Button("Dismiss", "fa5s.times")
        dec.clicked.connect(lambda: self._dismiss(m))
        lay.addWidget(dec)
        return f

    def _accept(self, m: InboxMessage) -> None:
        proj = m.project.clone(m.project.name)
        proj.origin = M.Origin(source="inbox", author=m.sender)
        self.ctx.store.add(proj)
        self.ctx.hub.dismiss_inbox(m)
        self.ctx.toast.emit("Added to your workspace", proj.name, "success")
        self.ctx.refresh_hub()

    def _dismiss(self, m: InboxMessage) -> None:
        self.ctx.hub.dismiss_inbox(m)
        self.ctx.refresh_hub()

    # ------------------------------------------------------- announcements
    def _render_announcements(self) -> None:
        lay = self.tab_ann.layout()
        clear_layout(lay)
        head = QHBoxLayout()
        head.addWidget(label("Announcements show as a banner on everyone's Home page.", "muted"), 1)
        post = Button("Post announcement", "fa5s.bullhorn", "primary")
        post.clicked.connect(self._post)
        head.addWidget(post)
        lay.addLayout(head)
        anns = self.ctx.hub.announcements(include_expired=True)
        if not anns:
            lay.addWidget(EmptyState("fa5s.bullhorn", "No announcements", "Use announcements for drive moves, template changes or deadlines."))
            return
        for a in anns:
            f = QFrame()
            f.setObjectName({"warning": "banner_warn", "critical": "banner_danger"}.get(a.level, "banner"))
            row = QHBoxLayout(f)
            row.setContentsMargins(14, 10, 14, 10)
            col = QVBoxLayout()
            col.setSpacing(2)
            tl = QLabel(a.title)
            tl.setStyleSheet("font-weight: 700;")
            col.addWidget(tl)
            col.addWidget(label(a.body, "muted", wrap=True))
            col.addWidget(label(f"{a.author} · {relative_time(a.ts)}", "faint"))
            row.addLayout(col, 1)
            if a.author == self.ctx.user:
                rm = IconButton("fa5s.trash", "Remove", size=12)
                rm.clicked.connect(lambda _=False, aid=a.id: (self.ctx.hub.remove_announcement(aid), self.ctx.refresh_hub()))
                row.addWidget(rm, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(f)

    def _post(self) -> None:
        dlg = AnnouncementDialog(self)
        if dlg.exec():
            self.ctx.hub.announce(dlg.title_edit.text().strip(), dlg.body.toPlainText().strip(), dlg.level.currentData())
            self.ctx.refresh_hub()
            self.ctx.toast.emit("Announcement posted", "", "success")

    # --------------------------------------------------------------- pulse
    def _render_pulse(self) -> None:
        lay = self.tab_pulse.layout()
        clear_layout(lay)
        rows = self.ctx.hub.pulse_feed(40)
        if not rows:
            lay.addWidget(EmptyState("fa5s.stream", "No activity yet", "Launches and publications appear here when colleagues share their activity (Settings → Team Hub)."))
            return
        for r in rows:
            line = QHBoxLayout()
            line.setSpacing(10)
            who = str(r.get("name") or r.get("user", ""))
            line.addWidget(Avatar(who, 24))
            verb = {"launched": "opened", "published": "published", "sent": "sent"}.get(str(r.get("event", "")), str(r.get("event", "")))
            lbl = QLabel(f"<b>{who}</b> {verb} {r.get('detail', '')}")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            line.addWidget(lbl, 1)
            line.addWidget(label(relative_time(str(r.get("ts", ""))), "faint"))
            lay.addLayout(line)
