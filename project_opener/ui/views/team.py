"""Team Hub: presence, published projects, inbox, announcements, pulse."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from project_opener.core import models as M
from project_opener.lan.hub import InboxMessage, PublishedProject
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, badge, clear_layout, make_transparent
from project_opener.ui.widgets.cards import plural, relative_time
from project_opener.ui.widgets.common import Avatar, Button, ElidedLabel, IconButton, label
from project_opener.ui.widgets.dialogs import AnnouncementDialog, confirm
from project_opener.ui.widgets.empty import EmptyState
from project_opener.ui.widgets.flow import FlowLayout

BY_W = 120          # the register's By column: identity text, left-aligned on a fixed width


def _project_of(detail: str) -> str:
    """The project title a pulse row is about: before " › set", " rev N" or " → person"."""
    for sep in (" › ", " rev ", " → "):
        if sep in detail:
            detail = detail.split(sep, 1)[0]
    return detail.strip()


def activity_register(rows: list[dict], name_for=lambda u: u, today: str | None = None) -> list[dict]:
    """Pulse rows as a register: [{"project", "entries": [{"text", "rev", "by", "ts"}]}], newest first.

    Launches by one person of one project on one day fold into "opened 3× today"
    (or "opened 2× on <date>"); published and sent rows keep their revision and person."""
    from datetime import UTC, datetime
    today = today or datetime.now(UTC).date().isoformat()
    groups: dict[str, dict] = {}
    folds: dict[tuple[str, str, str], dict] = {}
    for r in sorted(rows, key=lambda x: str(x.get("ts", "")), reverse=True):
        detail = pulse_detail_names(str(r.get("detail", "")), name_for)
        who = str(r.get("name") or name_for(str(r.get("user", ""))))
        ev = str(r.get("event", ""))
        ts = str(r.get("ts", ""))
        project = _project_of(detail) or "(unknown project)"
        g = groups.setdefault(project, {"project": project, "entries": []})
        if ev == "launched":
            day = ts[:10]
            key = (project, who, day)
            if key in folds:
                folds[key]["count"] += 1
                folds[key]["text"] = f"opened {folds[key]['count']}× {'today' if day == today else 'on ' + day}"
                continue
            entry = {"text": "opened" + (f" › {detail.split(' › ', 1)[1]}" if " › " in detail else ""), "rev": "", "by": who, "ts": ts, "count": 1}
            folds[key] = entry
            g["entries"].append(entry)
        elif ev == "published":
            rev = detail.split(" rev ", 1)[1] if " rev " in detail else ""
            entry = {"text": "published" + (f" (was rev {rev.split('(was rev ')[1].rstrip(')')})" if "(was rev " in rev else ""),
                     "rev": "rev " + rev.split(" ")[0] if rev else "", "by": who, "ts": ts}
            g["entries"].append(entry)
        elif ev == "sent":
            to = detail.split(" → ", 1)[1] if " → " in detail else ""
            g["entries"].append({"text": f"sent to {to}" if to else "sent", "rev": "", "by": who, "ts": ts})
        else:
            g["entries"].append({"text": ev, "rev": "", "by": who, "ts": ts})
    return list(groups.values())


def pulse_detail_names(detail: str, name_for) -> str:
    """The "→ login" tail of a sent pulse shown with the colleague's display name."""
    if " → " in detail:
        head, _, who = detail.rpartition(" → ")
        return f"{head} → {name_for(who)}"
    return detail


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
        self.refresh_btn = IconButton("fa5s.sync-alt", "Refresh", size=14)
        self.refresh_btn.clicked.connect(self._refresh_now)
        row.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.publish_btn = Button("Publish a project", "fa5s.cloud-upload-alt", "primary")
        self.publish_btn.clicked.connect(lambda: ctx.navigate.emit("publish_picker", None))
        row.addWidget(self.publish_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.presence_block = QWidget()
        make_transparent(self.presence_block)
        pb = QVBoxLayout(self.presence_block)
        pb.setContentsMargins(0, 0, 0, 0)
        pb.setSpacing(10)
        self.presence_head = QHBoxLayout()
        self.presence_head.setSpacing(8)
        self.presence_head.addWidget(label("Online now", "section"))
        self.presence_count = label("", "muted")
        self.presence_count.setFont(theme.ui_font(theme.current().font_size + 2, 400, tabular=True))
        self.presence_head.addWidget(self.presence_count)
        self.presence_head.addStretch(1)
        pb.addLayout(self.presence_head)
        self.presence_host = QWidget()
        self.presence_flow = FlowLayout(self.presence_host, 0, 10, 10)
        pb.addWidget(self.presence_host)
        self.content.addWidget(self.presence_block)
        self.empty_host = QVBoxLayout()          # the not-connected state, where the data would be
        self.content.addLayout(self.empty_host)

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
        elif section == "announcements":
            self.tabs.setCurrentWidget(self.tab_ann)

    def _refresh_now(self) -> None:
        self.ctx.refresh_hub()
        self.ctx.toast.emit("Refreshing the hub", "", "info")

    def _set_status(self, text: str, level: str) -> None:
        clear_layout(self.status_host)
        self.status_badge = badge(text, level)
        self.status_host.addWidget(self.status_badge)

    def refresh(self) -> None:
        st = self.ctx.hub_status
        online = sum(1 for p in self.ctx.peers if p.online and p.user != self.ctx.user)
        clear_layout(self.empty_host)
        if not st.configured:
            self._set_status("Not connected", "neutral")
            self.set_subtitle("")
            self.empty_host.addWidget(EmptyState(
                "fa5s.users", "Team Hub not connected",
                "Pick a shared folder on the office LAN, for example" + chr(10) + r"\\nas01\Project\_ProjectOpenerHub",
                "Connect a hub folder", lambda: self.ctx.navigate.emit("settings", "hub"), action_icon="fa5s.plug"))
        elif st.reachable:
            self._set_status("Connected", "ok")
            self.set_subtitle(f"{st.path} · {plural(online, 'colleague')} online")
        else:
            self._set_status("Unreachable", "bad")
            self.set_subtitle(f"{st.path} · {st.message}" if st.message else st.path)
        self.publish_btn.setVisible(bool(st.configured))
        self.refresh_btn.setVisible(bool(st.configured))
        self.tabs.setVisible(st.configured)
        self.presence_block.setVisible(st.configured)
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
        online = sum(1 for p in peers if p.online)
        self.presence_count.setText(str(online) if peers else "")
        if not self.ctx.hub_status.configured and not peers:
            return
        if not peers:
            lbl = label("Nobody else has used this hub folder yet.", "muted")
            self.presence_flow.addWidget(lbl)
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
                # "who is in which job" reads by sight: the project's own icon in its colour
                proj = self.ctx.store.by_name(p.current_project)
                line = QHBoxLayout()
                line.setSpacing(5)
                ic = QLabel()                   # the slot is always there: sublines start on one x
                ic.setPixmap(icons.pixmap(proj.icon, 13, proj.color) if proj is not None
                             else icons.pixmap("fa5s.folder", 13, theme.current().text_faint))
                ic.setFixedWidth(15)
                line.addWidget(ic)
                line.addWidget(label(f"in {p.current_project}", "faint"))
                line.addStretch(1)
                col.addLayout(line)
            elif p.online:
                col.addWidget(label(f"{p.host} · v{p.version}", "faint"))
            else:
                col.addWidget(label(f"last seen {relative_time(M.parse_iso(p.ts).isoformat() if p.ts else None).lower()}", "faint"))
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
        if not pubs:
            lay.addWidget(EmptyState("fa5s.cloud-upload-alt", "No projects published yet", "",
                                     "Publish a project", lambda: self.ctx.navigate.emit("publish_picker", None),
                                     action_icon="fa5s.cloud-upload-alt"))
            lay.addStretch(1)
            return
        lay.addWidget(label(f"{plural(n, 'project')} published by the team", "muted"))
        mine = {p.origin.published_id for p in self.ctx.store.projects if p.origin.published_id}
        grid = QWidget()
        flow = FlowLayout(grid, 0, 16, 16, justify=True, max_columns=3)
        for pub in pubs:
            flow.addWidget(self._published_card(pub, pub.published_id in mine))
        lay.addWidget(grid)
        lay.addStretch(1)

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
        nm = QLabel(p.title)
        nm.setFont(theme.ui_font(weight=500))
        nm.setWordWrap(True)
        col.addWidget(nm)
        col.addWidget(label(f"{self.ctx.hub.display_name_for(pub.author)} · {relative_time(pub.published_at).lower()}", "muted"))
        top.addLayout(col, 1)
        rev = QLabel(f"rev {pub.revision}")           # the revision is the hub's first-class figure
        rev.setObjectName("muted")
        rev.setFont(theme.ui_font(theme.current().font_size, 500, tabular=True))
        top.addWidget(rev, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)
        if pub.description:
            lay.addWidget(label(pub.description, "muted", wrap=True))
        lay.addWidget(label(f"{plural(len(p.items), 'item')} · {plural(len(p.launch_sets), 'launch set')}", "faint"))
        lay.addStretch(1)                 # the action pins to the card's foot: cards in a row share a bottom edge
        row = QHBoxLayout()
        if have:
            row.addWidget(badge("In your workspace", "ok"))
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
        if confirm(self, "Unpublish project", f"Remove ‘{pub.project.name}’ from the Team Hub? Colleagues keep their clones.", danger=True, ok_text="Unpublish"):
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
        self.tabs.setTabText(1, f"Inbox {len(msgs)}" if msgs else "Inbox")
        if not msgs:
            lay.addWidget(EmptyState("fa5s.inbox", "Nothing sent to you yet"))
            lay.addStretch(1)
            return
        for m in msgs:
            lay.addWidget(self._inbox_card(m))
        lay.addStretch(1)

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
        title = QLabel(f"<b>{self.ctx.hub.display_name_for(m.sender)}</b> sent you <b>{m.project.title}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(title)
        if m.message:
            col.addWidget(label(f"“{m.message}”", "muted", wrap=True))
        col.addWidget(label(f"{plural(len(m.project.items), 'item')} · {relative_time(m.sent_at).lower()}", "faint"))
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
        anns = self.ctx.hub.announcements(include_expired=True)
        head = QHBoxLayout()
        head.addWidget(label(plural(len(anns), "announcement") if anns else "", "muted"), 1)
        post = Button("Post announcement", "fa5s.bullhorn")
        post.clicked.connect(self._post)
        head.addWidget(post)
        lay.addLayout(head)
        if not anns:
            lay.addWidget(EmptyState("fa5s.bullhorn", "No announcements"))
            lay.addStretch(1)
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
            col.addWidget(label(f"{self.ctx.hub.display_name_for(a.author)} · {relative_time(a.ts).lower()}", "faint"))
            row.addLayout(col, 1)
            if a.author == self.ctx.user:
                rm = IconButton("fa5s.trash", "Remove", size=14)
                rm.clicked.connect(lambda _=False, aid=a.id: (self.ctx.hub.remove_announcement(aid), self.ctx.refresh_hub()))
                row.addWidget(rm, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(f)
        lay.addStretch(1)

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
        """Activity as a register: grouped under the project, columns Event · Rev · By · When,
        repeated launches by one person on one day folded into "opened 3× today"."""
        lay = self.tab_pulse.layout()
        clear_layout(lay)
        rows = self.ctx.hub.pulse_feed(60)
        if not rows:
            lay.addWidget(EmptyState("fa5s.stream", "No activity yet"))
            lay.addStretch(1)
            return
        lay.setSpacing(0)
        t = theme.current()
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        for c, head in enumerate(("Project", "Rev", "By", "When")):
            h = label(head, "faint")
            h.setFont(theme.ui_font(9))
            if c in (1, 3):                              # figures right; identity text (By) left on a fixed column
                h.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            h.setFixedHeight(26)
            grid.addWidget(h, 0, c)
        grid.setColumnMinimumWidth(2, BY_W)
        row_i = 1
        for group in activity_register(rows, self.ctx.hub.display_name_for):
            title = QLabel(group["project"])
            title.setFont(theme.ui_font(weight=600))
            title.setFixedHeight(32)
            grid.addWidget(title, row_i, 0, 1, 4)
            row_i += 1
            for entry in group["entries"]:
                ev = QLabel(entry["text"])
                ev.setObjectName("muted")
                ev.setFixedHeight(28)
                ev.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                grid.addWidget(ev, row_i, 0)
                rev = QLabel(entry["rev"] or "–")
                rev.setObjectName("muted" if entry["rev"] else "faint")
                rev.setFont(theme.ui_font(t.font_size, 500 if entry["rev"] else 400, tabular=True))
                rev.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(rev, row_i, 1)
                by = ElidedLabel(entry["by"], mode=Qt.TextElideMode.ElideRight)
                by.setFixedWidth(BY_W)
                grid.addWidget(by, row_i, 2)
                when = label(relative_time(entry["ts"]).lower(), "faint")
                when.setFont(theme.ui_font(t.font_size - 1, tabular=True))
                when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(when, row_i, 3)
                row_i += 1
        lay.addLayout(grid)
        lay.addStretch(1)
