"""Main window: sidebar + stacked pages + routing + tray + shortcuts."""
from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QEvent, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMenu, QStackedWidget, QSystemTrayIcon, QWidget

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core import winutil
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.detail import ProjectPage
from project_opener.ui.views.home import HomePage
from project_opener.ui.views.projects import ProjectsPage
from project_opener.ui.views.settings import SettingsPage
from project_opener.ui.views.team import TeamPage
from project_opener.ui.views.updates import UpdatesPage
from project_opener.ui.widgets.dialogs import ProjectEditor, PublishDialog, SendToDialog, confirm
from project_opener.ui.widgets.palette import CommandPalette
from project_opener.ui.widgets.sidebar import Sidebar
from project_opener.ui.widgets.toast import ToastManager

log = logging.getLogger(__name__)

PALETTE_ACTIONS = [
    ("new_project", "New project", "fa5s.plus"),
    ("projects", "Go to Projects", "fa5s.th-large"),
    ("team", "Go to Team Hub", "fa5s.users"),
    ("updates", "Check for updates", "fa5s.sync-alt"),
    ("settings", "Open Settings", "fa5s.sliders-h"),
    ("toggle_theme", "Toggle dark / light theme", "fa5s.adjust"),
    ("recheck", "Re-check all paths", "fa5s.heartbeat"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        self.setWindowTitle(C.APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1040, 660)
        self.resize(1360, 840)
        self._really_quit = False

        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = Sidebar(ctx.display_name(), ctx.settings.sidebar_collapsed)
        lay.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.pages: dict[str, QWidget] = {}
        for cls in (HomePage, ProjectsPage, TeamPage, UpdatesPage, SettingsPage, ProjectPage):
            page = cls(ctx)
            self.pages[cls.route] = page
            self.stack.addWidget(page)
        self._route_history: list[str] = ["home"]

        self.toasts = ToastManager(self)
        self.palette = CommandPalette(self, lambda: ctx.store.projects, PALETTE_ACTIONS)
        self.palette.hit_chosen.connect(self._palette_hit)

        # wiring
        self.sidebar.route_changed.connect(self.go)
        self.sidebar.new_project.connect(lambda: self.new_project())
        self.sidebar.palette_requested.connect(self.open_palette)
        self.sidebar.profile_clicked.connect(lambda: self.go("settings", "profile"))
        ctx.navigate.connect(self._navigate)
        ctx.toast.connect(self._toast)
        ctx.toast_action.connect(self._toast_with_action)
        ctx.hub_changed.connect(self._hub_status)
        ctx.projects_changed.connect(self._rebuild_tray_menu)

        self._shortcuts()
        self._tray()
        self.go("home")
        self._restore_geometry()
        QTimer.singleShot(200, self._first_run)

    # --------------------------------------------------------------- routing
    def go(self, route: str, payload=None) -> None:
        page = self.pages.get(route)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(route if route != "project" else "projects")
        if route != self._route_history[-1]:
            self._route_history.append(route)
            self._route_history = self._route_history[-20:]
        hook = getattr(page, "on_show", None)
        if hook:
            try:
                hook(payload) if route in ("settings", "team") else hook()
            except TypeError:
                hook()

    def open_project(self, project: M.Project) -> None:
        self.pages["project"].load(project)  # type: ignore[attr-defined]
        self.go("project")

    def _navigate(self, route: str, payload) -> None:
        if route == "project" and isinstance(payload, M.Project):
            self.open_project(payload)
        elif route == "new_project":
            self.new_project(payload if isinstance(payload, M.Project) else None)
        elif route == "edit_project" and isinstance(payload, M.Project):
            self.edit_project(payload)
        elif route == "project_menu" and isinstance(payload, tuple):
            self.project_menu(*payload)
        elif route == "palette":
            self.open_palette()
        elif route == "retheme":
            self.retheme()
        elif route == "profile_changed":
            self.sidebar.set_user(self.ctx.display_name())
        elif route == "publish" and isinstance(payload, M.Project):
            self.publish(payload)
        elif route == "publish_picker":
            self.publish_picker()
        elif route == "update_from_hub" and isinstance(payload, tuple):
            self.update_from_hub(*payload)
        else:
            self.go(route, payload)

    def open_palette(self) -> None:
        self.palette.open_at(self)

    def _palette_hit(self, hit) -> None:
        if hit.kind == "project" and hit.project:
            self.open_project(hit.project)
        elif hit.kind == "set" and hit.project:
            self.ctx.launch(hit.project, hit.launch_set, parent=self)
        elif hit.kind == "item" and hit.project and hit.item:
            self.ctx.open_single(hit.project, hit.item)
        elif hit.kind == "action":
            self._action(hit.action_id)

    def _action(self, action_id: str) -> None:
        if action_id == "new_project":
            self.new_project()
        elif action_id == "toggle_theme":
            self.ctx.settings.theme = "light" if theme.current().dark else "dark"
            self.ctx.settings.save()
            self.retheme()
        elif action_id == "recheck":
            self.ctx.refresh_all_health()
            self._toast("Re-checking paths…", "", "info")
        elif action_id == "updates":
            self.go("updates")
            self.ctx.check_updates(silent=False)
        else:
            self.go(action_id)

    # ------------------------------------------------------------- projects
    def new_project(self, template: M.Project | None = None) -> None:
        dlg = ProjectEditor(template, self.ctx.store.all_tags(), self)
        if template is not None:
            dlg.setWindowTitle("New project")
            dlg.heading.setText("New project")
        if dlg.exec():
            proj = self.ctx.store.add(dlg.project)
            self._toast("Project created", proj.name, "success")
            self.open_project(proj)

    def edit_project(self, project: M.Project) -> None:
        dlg = ProjectEditor(project, self.ctx.store.all_tags(), self)
        if dlg.exec():
            self.ctx.store.update(dlg.project)

    def project_menu(self, project: M.Project, pos) -> None:
        t = theme.current()
        m = QMenu(self)
        m.addAction(icons.icon("fa5s.play", t.accent), "Open all enabled items", lambda: self.ctx.launch(project, parent=self))
        if project.launch_sets:
            sub = m.addMenu(icons.icon("fa5s.layer-group"), "Open launch set")
            for s in project.launch_sets:
                sub.addAction(icons.icon(s.icon), s.name, lambda _=False, ls=s: self.ctx.launch(project, ls, parent=self))
        m.addAction(icons.icon("fa5s.folder-open"), "View details", lambda: self.open_project(project))
        m.addAction(icons.icon("fa5s.pen"), "Edit…", lambda: self.edit_project(project))
        m.addSeparator()
        m.addAction(icons.icon("fa5s.thumbtack"), "Unpin" if project.pinned else "Pin to top", lambda: self.ctx.store.toggle_pin(project.id))
        m.addAction(icons.icon("fa5s.star"), "Remove from favourites" if project.favorite else "Add to favourites", lambda: self.ctx.store.toggle_favorite(project.id))
        auto = m.addAction(icons.icon("fa5s.power-off"), "Auto-launch at start-up")
        auto.setCheckable(True)
        auto.setChecked(project.auto_launch)
        auto.triggered.connect(lambda on: self._set_auto(project, on))
        m.addAction(icons.icon("fa5s.clone"), "Duplicate", lambda: self.ctx.store.duplicate(project.id))
        m.addSeparator()
        m.addAction(icons.icon("fa5s.cloud-upload-alt"), "Publish to Team Hub…", lambda: self.publish(project))
        m.addAction(icons.icon("fa5s.paper-plane"), "Send to colleague…", lambda: self.send_to(project))
        m.addAction(icons.icon("fa5s.file-export"), "Export as JSON…", lambda: self.export_one(project))
        m.addSeparator()
        m.addAction(icons.icon("fa5s.trash", t.danger), "Delete project", lambda: self.delete_project(project))
        m.exec(pos)

    def _set_auto(self, project: M.Project, on: bool) -> None:
        project.auto_launch = on
        self.ctx.store.update(project)

    def delete_project(self, project: M.Project) -> None:
        if confirm(self, "Delete project", f"Delete '{project.name}'? The files themselves are not touched.", danger=True):
            self.ctx.store.remove(project.id)
            self._toast("Project deleted", project.name, "info")
            if self.stack.currentWidget() is self.pages["project"]:
                self.go("projects")

    def export_one(self, project: M.Project) -> None:
        from PySide6.QtWidgets import QFileDialog

        from project_opener.core.jsonio import write_json_atomic
        f, _ = QFileDialog.getSaveFileName(self, "Export project", f"{project.name}.json", "JSON (*.json)")
        if f:
            write_json_atomic(f, self.ctx.store.export_bundle([project.id]))
            self._toast("Exported", f, "success")

    # ------------------------------------------------------------------ hub
    def _require_hub(self) -> bool:
        if not self.ctx.hub.configured:
            self._toast("Connect a Team Hub first", "Settings → Team Hub → choose a shared folder.", "warning")
            self.go("settings", "hub")
            return False
        if not self.ctx.hub.reachable():
            self._toast("Team Hub unreachable", str(self.ctx.hub.root), "error")
            return False
        return True

    def publish(self, project: M.Project) -> None:
        if not self._require_hub():
            return
        dlg = PublishDialog(project, self)
        if not dlg.exec():
            return
        pub = self.ctx.hub.publish(project, description=dlg.description, portable_fn=self.ctx.resolver.portable)
        if pub:
            self.ctx.store.update(project)
            self._toast("Published to Team Hub", f"{project.name} · revision {pub.revision}", "success")
            self.ctx.refresh_hub()
        else:
            self._toast("Publish failed", "Hub folder not writable", "error")

    def publish_picker(self) -> None:
        if not self._require_hub():
            return
        from PySide6.QtWidgets import QInputDialog
        names = [p.name for p in self.ctx.store.sorted_projects("name")]
        if not names:
            self._toast("No projects to publish", "", "info")
            return
        choice, ok = QInputDialog.getItem(self, "Publish", "Project to publish:", names, 0, False)
        if ok and choice:
            proj = self.ctx.store.by_name(choice)
            if proj:
                self.publish(proj)

    def send_to(self, project: M.Project) -> None:
        if not self._require_hub():
            return
        peers = [p.user for p in self.ctx.peers if p.user != self.ctx.user]
        dlg = SendToDialog(project, peers, self)
        if dlg.exec() and dlg.recipient:
            ok = self.ctx.hub.send(dlg.recipient, project, dlg.message.toPlainText().strip(), portable_fn=self.ctx.resolver.portable)
            self._toast("Sent" if ok else "Send failed", f"{project.name} → {dlg.recipient}", "success" if ok else "error")

    def update_from_hub(self, project: M.Project, pub) -> None:
        if not confirm(self, "Update from hub", f"Replace items and launch sets of '{project.name}' with revision {pub.revision} from {pub.author}? Your notes and settings are kept."):
            return
        fresh = pub.project
        project.items = [M.Item.from_dict(i.to_dict()) for i in fresh.items]
        project.launch_sets = [M.LaunchSet.from_dict(s.to_dict()) for s in fresh.launch_sets]
        project.description = fresh.description or project.description
        project.tags = fresh.tags or project.tags
        project.origin = M.Origin(source="team", author=pub.author, published_id=pub.published_id,
                                  published_at=pub.published_at, revision=pub.revision)
        self.ctx.store.update(project)
        self._toast("Updated from Team Hub", f"{project.name} · revision {pub.revision}", "success")

    def _hub_status(self, st) -> None:
        if not st.configured:
            self.sidebar.set_hub_text("Team Hub not connected", False)
        elif st.reachable:
            self.sidebar.set_hub_text(f"Hub connected · {st.peers_online} online", True)
        else:
            self.sidebar.set_hub_text("Hub unreachable", False)
        self.sidebar.set_inbox_count(st.inbox)
        if st.inbox and getattr(self, "_last_inbox", 0) < st.inbox:
            self._toast_with_action(f"{st.inbox} project(s) in your inbox", "Accept them from the Team Hub inbox.",
                                    "info", "Open inbox", ("team", "inbox"))
        self._last_inbox = st.inbox

    # --------------------------------------------------------------- theme
    def retheme(self) -> None:
        app = QApplication.instance()
        s = self.ctx.settings
        dark = s.theme == "dark" or (s.theme == "system" and _system_dark())
        theme.apply_theme(app, dark, s.accent, s.density)
        winutil.apply_dark_title_bar(int(self.winId()), dark)
        # Rebuild pages so custom-painted widgets pick up the new tokens.
        current = self.stack.currentWidget()
        route = next((r for r, p in self.pages.items() if p is current), "home")
        proj = getattr(self.pages["project"], "project", None)
        for page in list(self.pages.values()):
            dispose = getattr(page, "dispose", None)
            if dispose:
                dispose()
            self.stack.removeWidget(page)
            page.deleteLater()
        self.pages.clear()
        for cls in (HomePage, ProjectsPage, TeamPage, UpdatesPage, SettingsPage, ProjectPage):
            page = cls(self.ctx)
            self.pages[cls.route] = page
            self.stack.addWidget(page)
        self.sidebar.deleteLater()
        self.sidebar = Sidebar(self.ctx.display_name(), s.sidebar_collapsed)
        self.centralWidget().layout().insertWidget(0, self.sidebar)
        self.sidebar.route_changed.connect(self.go)
        self.sidebar.new_project.connect(lambda: self.new_project())
        self.sidebar.palette_requested.connect(self.open_palette)
        self.sidebar.profile_clicked.connect(lambda: self.go("settings", "profile"))
        self.palette = CommandPalette(self, lambda: self.ctx.store.projects, PALETTE_ACTIONS)
        self.palette.hit_chosen.connect(self._palette_hit)
        self._hub_status(self.ctx.hub_status)
        if route == "project" and proj:
            self.open_project(proj)
        else:
            self.go(route)

    # ----------------------------------------------------------- shortcuts
    def _shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+K"), self, self.open_palette)
        QShortcut(QKeySequence("Ctrl+P"), self, self.open_palette)
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.new_project())
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.go("home"))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.go("projects"))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.go("team"))
        QShortcut(QKeySequence("Ctrl+,"), self, lambda: self.go("settings"))
        QShortcut(QKeySequence("Ctrl+B"), self, lambda: self.sidebar.toggle())  # sidebar is rebuilt on retheme
        QShortcut(QKeySequence("F5"), self, self.ctx.refresh_all_health)
        QShortcut(QKeySequence("Alt+Left"), self, self._back)

    def _focus_search(self) -> None:
        self.go("projects")
        self.pages["projects"].focus_search()  # type: ignore[attr-defined]

    def _back(self) -> None:
        if len(self._route_history) > 1:
            self._route_history.pop()
            self.go(self._route_history[-1])

    # ---------------------------------------------------------------- tray
    def _tray(self) -> None:
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip(C.APP_NAME)
        self.tray_menu = QMenu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self._rebuild_tray_menu()
        self.tray.show()

    def _rebuild_tray_menu(self) -> None:
        m = self.tray_menu
        m.clear()
        m.addAction(icons.icon("fa5s.window-maximize"), "Show Project Opener", self.show_normal)
        m.addAction(icons.icon("fa5s.search"), "Search…  (Ctrl+K)", lambda: (self.show_normal(), self.open_palette()))
        m.addSeparator()
        quick = [p for p in self.ctx.store.sorted_projects("smart")][:10]
        if quick:
            for p in quick:
                m.addAction(icons.icon(p.icon, p.color), p.name, lambda _=False, pr=p: self.ctx.launch(pr, parent=self))
            m.addSeparator()
        m.addAction(icons.icon("fa5s.power-off"), "Quit", self.quit_app)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_normal()

    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._really_quit = True
        self.close()

    # --------------------------------------------------------------- toasts
    def _toast(self, title: str, body: str = "", level: str = "info") -> None:
        if not self.ctx.settings.show_toasts and level not in ("error",):
            return
        if self.isVisible() and not self.isMinimized():
            self.toasts.show_toast(title, body, level)
        elif hasattr(self, "tray") and self.tray.isVisible():
            icon = {"success": QSystemTrayIcon.MessageIcon.Information, "warning": QSystemTrayIcon.MessageIcon.Warning,
                    "error": QSystemTrayIcon.MessageIcon.Critical}.get(level, QSystemTrayIcon.MessageIcon.Information)
            self.tray.showMessage(title, body, icon, 4000)

    def _toast_with_action(self, title: str, body: str, level: str, action: str, target) -> None:
        """Toast with a button that navigates somewhere (route, payload)."""
        if not self.ctx.settings.show_toasts and level not in ("error",):
            return
        if self.isVisible() and not self.isMinimized():
            route, payload = target if isinstance(target, tuple) else (str(target), None)
            self.toasts.show_toast(title, body, level, action=action,
                                   on_action=lambda: self._navigate(route, payload), timeout=8000)
        else:
            self._toast(title, body, level)

    # --------------------------------------------------------- first run
    def _first_run(self) -> None:
        s = self.ctx.settings
        if self.ctx.store.migrated_from:
            self._toast(f"Imported from {self.ctx.store.migrated_from}",
                        f"{len(self.ctx.store.projects)} project(s) brought across. Backups stay untouched.", "success")
        if s.last_seen_version != C.VERSION:
            s.last_seen_version = C.VERSION
            s.save()
        if not s.first_run_done:
            s.first_run_done = True
            s.save()
            if not s.hub_path:
                self._toast("Welcome to Project Opener 3", "Connect a Team Hub folder in Settings to collaborate over the LAN.", "info")
        if s.auto_launch_on_start:
            QTimer.singleShot(900, self._auto_launch)

    def _auto_launch(self) -> None:
        projects = self.ctx.store.auto_launch_projects()
        for p in projects:
            self.ctx.launch(p)
        if projects:
            self._toast(f"Auto-launched {len(projects)} project(s)", ", ".join(p.name for p in projects), "success")

    # ------------------------------------------------------------- window
    def _restore_geometry(self) -> None:
        g = self.ctx.settings.window_geometry
        if g:
            try:
                self.restoreGeometry(QByteArray.fromBase64(g.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self.toasts.host_resized()

    def changeEvent(self, e: QEvent) -> None:  # noqa: N802
        super().changeEvent(e)
        # "Follow Windows": re-theme when the OS switches between light and dark.
        if e.type() in (QEvent.Type.ThemeChange, QEvent.Type.ApplicationPaletteChange) and self.ctx.settings.theme == "system":
            if getattr(self, "_retheme_pending", False):
                return
            self._retheme_pending = True

            def run() -> None:
                self._retheme_pending = False
                if (_system_dark() != theme.current().dark):
                    self.retheme()

            QTimer.singleShot(150, run)

    def closeEvent(self, e: QCloseEvent) -> None:  # noqa: N802
        self.ctx.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.ctx.settings.sidebar_collapsed = self.sidebar.collapsed
        if self.ctx.settings.minimise_to_tray and not self._really_quit and self.tray.isVisible():
            self.hide()
            if not getattr(self, "_tray_hint_shown", False):
                self._tray_hint_shown = True
                self.tray.showMessage(C.APP_NAME, "Still running in the tray. Right-click the icon to quit.",
                                      QSystemTrayIcon.MessageIcon.Information, 3000)
            e.ignore()
            return
        self.ctx.shutdown()
        self.tray.hide()
        e.accept()


def _system_dark() -> bool:
    try:
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() == _Qt.ColorScheme.Dark
    except Exception:  # noqa: BLE001
        return True
