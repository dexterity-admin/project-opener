"""Team Hub: presence, published projects, inbox, announcements, pulse."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from project_opener.core import models as M
from project_opener.lan.hub import InboxMessage, PublishedProject
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, badge, clear_layout, row_widget
from project_opener.ui.widgets.cards import relative_time
from project_opener.ui.widgets.common import Avatar, Button, IconButton, label
from project_opener.ui.widgets.dialogs import AnnouncementDialog, confirm
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout


class TeamPage(Page):
    route = "team"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        row = self.title_row("Team Hub", "Not connected")
        self.status_host = QHBoxLayout()
        self.status_host.setContentsMargins(0, 0, 0, 0)
        row.addLayout(self.status_host)
        row.setAlignment(self.status_host, Qt.AlignmentFlag.AlignTop)
        self.status_badge = badge("Not connected", "neutral")
        self.status_host.addWidget(self.status_badge)
        refresh = IconButton("fa5s.sync-alt", "Refresh", size=14)
        refresh.clicked.connect(self._refresh_now)
        row.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        self.setup_btn = Button("Connect a hub folder", "fa5s.plug")
        self.setup_btn.clicked.connect(lambda: ctx.navigate.emit("settings", "hub"))
        row.addWidget(self.setup_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.publish_btn = Button("Publish a project", "fa5s.cloud-upload-alt", "primary")
        self.publish_btn.clicked.connect(lambda: ctx.navigate.emit("publish_picker", None))
        row.addWidget(self.publish_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.presence_host = QWidget()
        self.presence_flow = FlowLayout(self.presence_host, 0, 10, 10)
        self.presence_col = self.section("Online now")
        self.presence_col.addWidget(self.presence_host)

        self.tabs = QTabWidget()
        self.tab_published = QWidget()
        self.tab_inbox = QWidget()
        self.tab_ann = QWidget()
        self.tab_pulse = QWidget()
        for w, title in ((self.tab_published, "Published projects"), (self.tab_inbox, "Inbox"),
                         (self.tab_ann, "Announcements"), (self.tab_pulse, "Activity")):
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 16, 0, 0)
            lay.setSpacing(10)
            self.tabs.addTab(w, title)
        self.content.addWidget(self.tabs)
        self.content.addStretch(1)
        self.bind(ctx.hub_changed, lambda _s: self.refresh())
        self.bind(ctx.peers_changed, lambda _p: self._render_presence())
        self.refresh()

    def on_show(self, section: str | None = None) -> None:
        self.ctx.refresh_hub()
        self.refresh()
        if section == "inbox":
            self.tabs.setCurrentWidget(self.tab_inbox)

    def _refresh_now(self) -> None:
        self.ctx.refresh_hub()
        self.ctx.toast.emit("Refreshing hub…", "", "info")

    def _set_status(self, text: str, level: str) -> None:
        clear_layout(self.status_host)
        self.status_badge = badge(text, level)
        self.status_host.addWidget(self.status_badge)

    def refresh(self) -> None:
        st = self.ctx.hub_status
        online = sum(1 for p in self.ctx.peers if p.online and p.user != self.ctx.user)
        if not st.configured:
            self._set_status("Not connected", "neutral")
            self.set_subtitle("Not connected")
        elif st.reachable:
            self._set_status("Connected", "ok")
            self.set_subtitle(f"Connected · {st.path} · {online} online")
        else:
            self._set_status("Hub unreachable", "bad")
            self.set_subtitle(f"Hub unreachable · {st.path}")
        self.setup_btn.setVisible(not st.configured)
        self.publish_btn.setVisible(bool(st.configured))
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
        if not self.ctx.hub_status.configured and not peers:
            self.presence_flow.addWidget(label("Connect a Team Hub folder (any shared folder on the office LAN) to see colleagues here.", "muted", wrap=True))
            return
        if not peers:
            self.presence_flow.addWidget(label("No colleagues seen yet. Presence appears once others run Project Opener 3 with the same hub folder.", "muted", wrap=True))
            return
        for p in peers[:30]:
            f = QFrame()
            f.setObjectName("card")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(12, 10, 14, 10)
            lay.setSpacing(10)
            lay.addWidget(Avatar(p.label, 32, online=p.online))
            col = QVBoxLayout()
            col.setSpacing(0)
            nm = QLabel(p.label)
            nm.setFont(theme.ui_font(weight=500))
            col.addWidget(nm)
            if p.online and p.current_project:
                sub = f"working in {p.current_project}"
            elif p.online:
                sub = f"{p.host} · v{p.version}"
            else:
                sub = f"last seen {relative_time(M.parse_iso(p.ts).isoformat() if p.ts else None).lower()}"
            col.addWidget(label(sub, "faint"))
            lay.addLayout(col)
            if p.role:
                lay.addWidget(badge(p.role, "neutral"))
            self.presence_flow.addWidget(f)
        self.presence_host.updateGeometry()

    # ----------------------------------------------------------- published
    def _render_published(self) -> None:
        lay = self.tab_published.layout()
        clear_layout(lay)
        pubs = self.ctx.hub.published()
        n = len(pubs)
        lay.addWidget(label(f"{n} project{'s' if n != 1 else ''} published by the team. Clone one to get your own copy; "
                            "subscribers are told when the author publishes a new revision.", "muted", wrap=True))
        if not pubs:
            lay.addWidget(EmptyState("fa5s.cloud-upload-alt", "Nothing published yet", "Publish a project from its menu (⋯ → Publish to Team Hub)."))
            return
        mine = {p.origin.published_id for p in self.ctx.store.projects if p.origin.published_id}
        grid = QWidget()
        flow = FlowLayout(grid, 0, 16, 16, justify=True, max_columns=3)
        for pub in pubs:
            flow.addWidget(self._published_card(pub, pub.published_id in mine))
        lay.addWidget(grid)

    def _published_card(self, pub: PublishedProject, have: bool) -> QFrame:
        t = theme.current()
        p = pub.project
        f = QFrame()
        f.setObjectName("card")
        f.setMinimumWidth(300)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(t.pad, t.pad - 4, t.pad, t.pad - 4)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(p.icon, 16, t.text_muted))
        ic.setFixedWidth(20)
        top.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        nm = QLabel(p.name)
        nm.setFont(theme.ui_font(weight=500))
        nm.setWordWrap(True)
        col.addWidget(nm)
        col.addWidget(label(f"by {pub.author} · rev {pub.revision} · {relative_time(pub.published_at).lower()}", "muted"))
        top.addLayout(col, 1)
        lay.addLayout(top)
        if pub.description:
            lay.addWidget(label(pub.description, "muted", wrap=True))
        lay.addWidget(label(f"{len(p.items)} items · {len(p.launch_sets)} launch sets", "faint"))
        row = QHBoxLayout()
        if have:
            row.addWidget(badge("In my workspace", "ok"))
        else:
            b = Button("Clone", "fa5s.clone")
            b.clicked.connect(lambda: self._clone(pub))
            row.addWidget(b)
        row.addStretch(1)
        if pub.author == self.ctx.user:
            rm = IconButton("fa5s.trash", "Unpublish", size=14)
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
            if not self.ctx.hub.unpublish(pub.published_id):
                self.ctx.toast.emit("Unpublish failed", "The hub folder is not writable or the file is locked.", "error")
                return
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
        t = theme.current()
        f = QFrame()
        f.setObjectName("card")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(t.pad - 4, 12, t.pad - 4, 12)
        lay.setSpacing(12)
        lay.addWidget(Avatar(m.sender, 32))
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(f"<b>{m.sender}</b> sent you <b>{m.project.name}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(title)
        if m.message:
            col.addWidget(label(f"“{m.message}”", "muted", wrap=True))
        col.addWidget(label(f"{len(m.project.items)} items · {relative_time(m.sent_at).lower()}", "faint"))
        lay.addLayout(col, 1)
        acc = Button("Accept", "fa5s.check")
        acc.clicked.connect(lambda: self._accept(m))
        lay.addWidget(acc)
        dec = Button("Dismiss", "fa5s.times", "ghost")
        dec.clicked.connect(lambda: self._dismiss(m))
        lay.addWidget(dec)
        return f

    def _accept(self, m: InboxMessage) -> None:
        if not self.ctx.hub.dismiss_inbox(m):
            self.ctx.toast.emit("Could not accept", "The inbox file is locked or the hub is unreachable; try again.", "error")
            return
        proj = m.project.clone(m.project.name)
        proj.origin = M.Origin(source="inbox", author=m.sender)
        self.ctx.store.add(proj)
        self.ctx.toast.emit("Added to your workspace", proj.name, "success")
        self.ctx.refresh_hub()

    def _dismiss(self, m: InboxMessage) -> None:
        if not self.ctx.hub.dismiss_inbox(m):
            self.ctx.toast.emit("Could not dismiss", "The inbox file is locked or the hub is unreachable.", "error")
        self.ctx.refresh_hub()

    # ------------------------------------------------------- announcements
    def _render_announcements(self) -> None:
        lay = self.tab_ann.layout()
        clear_layout(lay)
        head = QHBoxLayout()
        head.addWidget(label("Announcements show as a banner on everyone's Home page.", "muted"), 1)
        post = Button("Post announcement", "fa5s.bullhorn")
        post.clicked.connect(self._post)
        head.addWidget(post)
        lay.addLayout(head)
        anns = self.ctx.hub.announcements(include_expired=True)
        if not anns:
            lay.addWidget(EmptyState("fa5s.bullhorn", "No announcements", "Use announcements for drive moves, template changes or deadlines."))
            return
        t = theme.current()
        for a in anns:
            f = QFrame()
            f.setObjectName({"warning": "banner_warn", "critical": "banner_danger"}.get(a.level, "banner"))
            row = QHBoxLayout(f)
            row.setContentsMargins(14, 10, 14, 10)
            row.setSpacing(10)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("fa5s.bullhorn", 16, {"warning": t.warning, "critical": t.danger}.get(a.level, t.info)))
            ic.setFixedWidth(18)
            row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            tl = QLabel(a.title)
            tl.setFont(theme.ui_font(weight=600))
            col.addWidget(tl)
            col.addWidget(label(a.body, "muted", wrap=True))
            col.addWidget(label(f"{a.author} · {relative_time(a.ts)}", "faint"))
            row.addLayout(col, 1)
            if a.author == self.ctx.user:
                rm = IconButton("fa5s.trash", "Remove", size=14)
                rm.clicked.connect(lambda _=False, aid=a.id: (self.ctx.hub.remove_announcement(aid), self.ctx.refresh_hub()))
                row.addWidget(rm, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(f)

    def _post(self) -> None:
        dlg = AnnouncementDialog(self)
        if dlg.exec():
            posted = self.ctx.hub.announce(dlg.title_edit.text().strip(), dlg.body.toPlainText().strip(),
                                           dlg.level.currentData(), expires=dlg.expires)
            self.ctx.refresh_hub()
            if posted:
                self.ctx.toast.emit("Announcement posted", "", "success")
            else:
                self.ctx.toast.emit("Announcement not posted", "The hub folder is not writable.", "error")

    # --------------------------------------------------------------- pulse
    def _render_pulse(self) -> None:
        lay = self.tab_pulse.layout()
        clear_layout(lay)
        rows = self.ctx.hub.pulse_feed(40)
        if not rows:
            lay.addWidget(EmptyState("fa5s.stream", "No activity yet", "Launches and publications appear here when colleagues share their activity (Settings → Team Hub)."))
            return
        lay.setSpacing(0)
        for r in rows:
            w, line = row_widget(40)
            who = str(r.get("name") or r.get("user", ""))
            line.addWidget(Avatar(who, 24))
            verb = {"launched": "opened", "published": "published", "sent": "sent"}.get(str(r.get("event", "")), str(r.get("event", "")))
            lbl = QLabel(f"<b>{who}</b> {verb} {r.get('detail', '')}")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            line.addWidget(lbl, 1)
            tm = label(relative_time(str(r.get("ts", ""))), "faint")
            tm.setFont(theme.ui_font(theme.current().font_size - 1, tabular=True))
            line.addWidget(tm)
            lay.addWidget(w)
