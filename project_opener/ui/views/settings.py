"""Settings: profile, appearance, behaviour, Team Hub, path variables, updates, data."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from project_opener import constants as C
from project_opener.core import winutil
from project_opener.core.jsonio import read_json, write_json_atomic
from project_opener.core.pathvars import normalise_var_name
from project_opener.ui import theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page
from project_opener.ui.widgets.common import Button, IconButton, SwitchRow, label
from project_opener.ui.widgets.dialogs import confirm

ACCENTS = ["#4F7DFF", "#2F5BFF", "#19C8FF", "#8B5CF6", "#EC4899", "#F97316", "#10B981", "#14B8A6", "#F59E0B", "#EF4444"]


class SettingsPage(Page):
    route = "settings"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self.title_row("Settings", "", "PREFERENCES")
        s = ctx.settings
        self._anchors: dict[str, QWidget] = {}

        # ---------------------------------------------------------- profile
        p, lay = self.panel()
        self._anchors["profile"] = p
        lay.addWidget(label("YOU", "eyebrow"))
        row = QHBoxLayout()
        self.display_name = QLineEdit(s.display_name)
        self.display_name.setPlaceholderText(f"Display name (Windows user: {ctx.user})")
        self.role = QLineEdit(s.role)
        self.role.setPlaceholderText("Role, e.g. Piping designer / Checker / Admin")
        row.addWidget(self.display_name, 1)
        row.addWidget(self.role, 1)
        lay.addLayout(row)
        self.display_name.editingFinished.connect(self._save_profile)
        self.role.editingFinished.connect(self._save_profile)
        self.content.addWidget(p)

        # ------------------------------------------------------- appearance
        p, lay = self.panel()
        self._anchors["appearance"] = p
        lay.addWidget(label("APPEARANCE", "eyebrow"))
        trow = QHBoxLayout()
        trow.addWidget(label("Theme"))
        self.theme_group = QButtonGroup(self)
        for key, text in (("dark", "Dark"), ("light", "Light"), ("system", "Follow Windows")):
            b = QPushButton(text)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(s.theme == key)
            b.clicked.connect(lambda _=False, k=key: self._set_theme(k))
            self.theme_group.addButton(b)
            trow.addWidget(b)
        trow.addSpacing(20)
        trow.addWidget(label("Accent"))
        for c in ACCENTS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(c)
            border = theme.current().text if c.lower() == s.accent.lower() else "transparent"
            b.setStyleSheet(f"QPushButton {{ background-color: {c}; border: 2px solid {border}; border-radius: 11px; }}")
            b.clicked.connect(lambda _=False, cc=c: self._set_accent(cc))
            trow.addWidget(b)
        trow.addSpacing(20)
        trow.addWidget(label("Density"))
        self.density = QComboBox()
        self.density.addItem("Comfortable", "comfortable")
        self.density.addItem("Compact", "compact")
        self.density.setCurrentIndex(max(0, self.density.findData(s.density)))
        self.density.currentIndexChanged.connect(self._set_density)
        trow.addWidget(self.density)
        trow.addStretch(1)
        lay.addLayout(trow)
        self.content.addWidget(p)

        # -------------------------------------------------------- behaviour
        p, lay = self.panel()
        self._anchors["behaviour"] = p
        lay.addWidget(label("BEHAVIOUR", "eyebrow"))
        self.sw_startup = SwitchRow("Start with Windows", "Launch Project Opener minimised to the tray when you sign in.", winutil.is_run_at_startup())
        self.sw_startup.toggled.connect(self._set_startup)
        lay.addWidget(self.sw_startup)
        self.sw_autolaunch = SwitchRow("Run auto-launch projects at start-up", "Projects marked 'Auto-launch' open their enabled items when the app starts.", s.auto_launch_on_start)
        self.sw_autolaunch.toggled.connect(lambda v: self._set("auto_launch_on_start", v))
        lay.addWidget(self.sw_autolaunch)
        self.sw_tray = SwitchRow("Minimise to tray on close", "Keep running in the notification area for instant launches.", s.minimise_to_tray)
        self.sw_tray.toggled.connect(lambda v: self._set("minimise_to_tray", v))
        lay.addWidget(self.sw_tray)
        self.sw_toasts = SwitchRow("Show notifications", "Toasts for launches, updates and hub events.", s.show_toasts)
        self.sw_toasts.toggled.connect(lambda v: self._set("show_toasts", v))
        lay.addWidget(self.sw_toasts)
        nrow = QHBoxLayout()
        nrow.addWidget(label("Pause between items"))
        self.delay = QSpinBox()
        self.delay.setRange(0, 5000)
        self.delay.setSingleStep(50)
        self.delay.setSuffix(" ms")
        self.delay.setValue(s.launch_delay_ms)
        self.delay.valueChanged.connect(lambda v: self._set("launch_delay_ms", v, rebuild=True))
        nrow.addWidget(self.delay)
        nrow.addSpacing(20)
        nrow.addWidget(label("Confirm when opening more than"))
        self.confirm_n = QSpinBox()
        self.confirm_n.setRange(0, 200)
        self.confirm_n.setValue(s.confirm_launch_over)
        self.confirm_n.setSuffix(" items")
        self.confirm_n.valueChanged.connect(lambda v: self._set("confirm_launch_over", v))
        nrow.addWidget(self.confirm_n)
        nrow.addStretch(1)
        lay.addLayout(nrow)
        self.content.addWidget(p)

        # -------------------------------------------------------- team hub
        p, lay = self.panel()
        self._anchors["hub"] = p
        lay.addWidget(label("TEAM HUB", "eyebrow"))
        lay.addWidget(label("Pick any folder on a shared drive that every colleague can read and write (for example "
                            r"\\192.168.0.200\Project\_ProjectOpenerHub). No server is needed.", "muted", wrap=True))
        hrow = QHBoxLayout()
        self.hub_path = QLineEdit(s.hub_path)
        self.hub_path.setPlaceholderText(r"\\server\share\_ProjectOpenerHub")
        hrow.addWidget(self.hub_path, 1)
        browse = Button("Browse…", "fa5s.folder-open")
        browse.clicked.connect(self._browse_hub)
        hrow.addWidget(browse)
        connect = Button("Connect", "fa5s.plug", "primary")
        connect.clicked.connect(self._connect_hub)
        hrow.addWidget(connect)
        lay.addLayout(hrow)
        self.hub_status = label("", "faint")
        lay.addWidget(self.hub_status)
        self.sw_pulse = SwitchRow("Share my activity", "Let colleagues see which project you are working in and what you open.", s.hub_share_pulse)
        self.sw_pulse.toggled.connect(lambda v: self._set("hub_share_pulse", v))
        lay.addWidget(self.sw_pulse)
        self.sw_udp = SwitchRow("Fast LAN presence (UDP beacon)", f"Announce yourself on the local subnet on port {C.PRESENCE_PORT} so 'online' updates within seconds.", s.presence_udp)
        self.sw_udp.toggled.connect(lambda v: self._set("presence_udp", v, rebuild=True))
        lay.addWidget(self.sw_udp)
        self.content.addWidget(p)

        # ---------------------------------------------------- path variables
        p, lay = self.panel()
        self._anchors["variables"] = p
        head = QHBoxLayout()
        head.addWidget(label("PATH VARIABLES", "eyebrow"))
        head.addStretch(1)
        sug = Button("Add my mapped drives", "fa5s.magic")
        sug.setToolTip("Creates {X_DRIVE} variables for every network drive on this PC so shared projects can swap drive letters for UNC paths.")
        sug.clicked.connect(self._suggest_vars)
        head.addWidget(sug)
        addv = Button("Add row", "fa5s.plus")
        addv.clicked.connect(lambda: self._add_var_row("", ""))
        head.addWidget(addv)
        lay.addLayout(head)
        lay.addWidget(label("Use {NAME} inside any path. Each PC resolves variables to its own location, so a project shared "
                            "with the team works for everyone even when drive letters differ.", "muted", wrap=True))
        self.vars = QTableWidget(0, 3)
        self.vars.setHorizontalHeaderLabels(["Variable", "Value on this PC", ""])
        self.vars.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.vars.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.vars.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.vars.verticalHeader().setVisible(False)
        self.vars.setMinimumHeight(140)
        self.vars.itemChanged.connect(lambda _i: self._save_vars())
        lay.addWidget(self.vars)
        self._load_vars()
        self.content.addWidget(p)

        # ---------------------------------------------------------- updates
        p, lay = self.panel()
        self._anchors["updates"] = p
        lay.addWidget(label("UPDATES", "eyebrow"))
        self.sw_update = SwitchRow("Check for updates automatically", f"Every {C.UPDATE_CHECK_INTERVAL_H} hours: LAN hub first, then GitHub.", s.update_check)
        self.sw_update.toggled.connect(lambda v: self._set("update_check", v))
        lay.addWidget(self.sw_update)
        trow = QHBoxLayout()
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("GitHub token with read access to the private repository (stored encrypted with Windows DPAPI)")
        self.token.setText(s.github_token)
        trow.addWidget(self.token, 1)
        save_tok = Button("Save token", "fa5s.key")
        save_tok.clicked.connect(self._save_token)
        trow.addWidget(save_tok)
        lay.addLayout(trow)
        crow = QHBoxLayout()
        crow.addWidget(label("Channel"))
        self.channel = QComboBox()
        self.channel.addItem("Stable releases only", "stable")
        self.channel.addItem("Include pre-releases", "all")
        self.channel.setCurrentIndex(max(0, self.channel.findData(s.update_channel)))
        self.channel.currentIndexChanged.connect(lambda _i: self._set("update_channel", self.channel.currentData(), rebuild=True))
        crow.addWidget(self.channel)
        crow.addStretch(1)
        lay.addLayout(crow)
        self.content.addWidget(p)

        # ------------------------------------------------------------- data
        p, lay = self.panel()
        self._anchors["data"] = p
        lay.addWidget(label("DATA", "eyebrow"))
        lay.addWidget(label(f"Workspace: {ctx.store.path}", "muted", wrap=True))
        drow = QHBoxLayout()
        exp = Button("Export workspace…", "fa5s.file-export")
        exp.clicked.connect(self._export)
        drow.addWidget(exp)
        imp = Button("Import…", "fa5s.file-import")
        imp.setToolTip("Import a Project Opener 3 export, a 1.x backup, or a 2.x hub file (<user>.json)")
        imp.clicked.connect(self._import)
        drow.addWidget(imp)
        v1 = Button("Import from Project Opener 1.x", "fa5s.history")
        v1.clicked.connect(self._import_v1)
        drow.addWidget(v1)
        drow.addStretch(1)
        lay.addLayout(drow)
        brow = QHBoxLayout()
        brow.addWidget(label("Backups are kept automatically before every save."))
        rb = Button("Restore a backup…", "fa5s.undo")
        rb.clicked.connect(self._restore)
        brow.addWidget(rb)
        ob = Button("Open backups folder", "fa5s.folder-open")
        ob.clicked.connect(lambda: winutil.reveal_in_explorer(str(ctx.store.root / C.BACKUP_DIR)))
        brow.addWidget(ob)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.content.addWidget(p)
        self.content.addStretch(1)
        ctx.hub_changed.connect(self._hub_status)

    # ---------------------------------------------------------------- nav
    def on_show(self, section: str | None = None) -> None:
        self._hub_status(self.ctx.hub_status)
        if section and section in self._anchors:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.scroll.ensureWidgetVisible(self._anchors[section], 0, 40))

    # ------------------------------------------------------------ helpers
    def _set(self, key: str, value, rebuild: bool = False) -> None:
        setattr(self.ctx.settings, key, value)
        if rebuild:
            self.ctx.apply_settings()
        else:
            self.ctx.settings.save()

    def _save_profile(self) -> None:
        self.ctx.settings.display_name = self.display_name.text().strip()
        self.ctx.settings.role = self.role.text().strip()
        self.ctx.apply_settings()
        self.ctx.navigate.emit("profile_changed", None)

    def _set_theme(self, key: str) -> None:
        self.ctx.settings.theme = key
        self.ctx.settings.save()
        self.ctx.navigate.emit("retheme", None)

    def _set_accent(self, c: str) -> None:
        self.ctx.settings.accent = c
        self.ctx.settings.save()
        self.ctx.navigate.emit("retheme", None)

    def _set_density(self) -> None:
        self.ctx.settings.density = self.density.currentData()
        self.ctx.settings.save()
        self.ctx.navigate.emit("retheme", None)

    def _set_startup(self, on: bool) -> None:
        if winutil.set_run_at_startup(on):
            self.ctx.settings.run_at_startup = on
            self.ctx.settings.save()
        else:
            self.ctx.toast.emit("Could not change start-up setting", "", "error")

    # ---------------------------------------------------------------- hub
    def _browse_hub(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose the Team Hub folder", self.hub_path.text() or "")
        if d:
            self.hub_path.setText(d.replace("/", "\\"))

    def _connect_hub(self) -> None:
        path = self.hub_path.text().strip()
        self.ctx.settings.hub_path = path
        self.ctx.apply_settings()
        if path:
            ok = self.ctx.hub.initialise()
            self.ctx.toast.emit("Team Hub connected" if ok else "Hub folder not writable", path, "success" if ok else "error")
            self.ctx.refresh_hub()
        else:
            self.ctx.toast.emit("Team Hub disconnected", "", "info")

    def _hub_status(self, st) -> None:
        t = theme.current()
        color = t.success if st.reachable else (t.text_faint if not st.configured else t.danger)
        self.hub_status.setText(f"<span style='color:{color}'>●</span> {st.message}")

    # ---------------------------------------------------------- variables
    def _load_vars(self) -> None:
        self.vars.blockSignals(True)
        self.vars.setRowCount(0)
        for k, v in self.ctx.settings.variables.items():
            self._add_var_row(k, v, signal=False)
        self.vars.blockSignals(False)

    def _add_var_row(self, k: str, v: str, signal: bool = True) -> None:
        self.vars.blockSignals(True)
        r = self.vars.rowCount()
        self.vars.insertRow(r)
        self.vars.setItem(r, 0, QTableWidgetItem(k))
        self.vars.setItem(r, 1, QTableWidgetItem(v))
        rm = IconButton("fa5s.trash", "Remove", size=12)
        rm.clicked.connect(lambda: self._remove_var_row(rm))
        self.vars.setCellWidget(r, 2, rm)
        self.vars.blockSignals(False)
        if signal:
            self.vars.editItem(self.vars.item(r, 0))

    def _remove_var_row(self, btn: QWidget) -> None:
        for r in range(self.vars.rowCount()):
            if self.vars.cellWidget(r, 2) is btn:
                self.vars.removeRow(r)
                break
        self._save_vars()

    def _save_vars(self) -> None:
        out: dict[str, str] = {}
        for r in range(self.vars.rowCount()):
            k = self.vars.item(r, 0).text() if self.vars.item(r, 0) else ""
            v = self.vars.item(r, 1).text() if self.vars.item(r, 1) else ""
            nk = normalise_var_name(k)
            if nk and v.strip():
                out[nk] = v.strip()
        self.ctx.settings.variables = out
        self.ctx.apply_settings()

    def _suggest_vars(self) -> None:
        sug = self.ctx.resolver.variable_suggestions()
        if not sug:
            self.ctx.toast.emit("No mapped network drives found", "", "info")
            return
        added = 0
        for k, v in sug.items():
            if k not in self.ctx.settings.variables:
                self._add_var_row(k, v, signal=False)
                added += 1
        self._save_vars()
        self.ctx.toast.emit(f"Added {added} drive variable(s)", ", ".join(sug.keys()), "success")

    # -------------------------------------------------------------- token
    def _save_token(self) -> None:
        self.ctx.settings.github_token = self.token.text().strip()
        self.ctx.apply_settings()
        self.ctx.toast.emit("Token saved" if self.token.text().strip() else "Token cleared", "Stored encrypted for this Windows account.", "success")

    # --------------------------------------------------------------- data
    def _export(self) -> None:
        f, _ = QFileDialog.getSaveFileName(self, "Export workspace", str(Path.home() / "Documents" / "project-opener-export.json"), "JSON (*.json)")
        if f:
            write_json_atomic(f, self.ctx.store.export_bundle())
            self.ctx.toast.emit("Exported", f, "success")

    def _import(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Import projects", "", "JSON (*.json)")
        if not f:
            return
        data = read_json(f)
        if not isinstance(data, dict):
            self.ctx.toast.emit("Import failed", "Not a valid JSON file", "error")
            return
        projects = data.get("projects")
        if isinstance(projects, dict) and projects and all(isinstance(v, dict) and "activities" in v for v in projects.values()):
            n = self.ctx.store.import_v2_file(Path(f), author=Path(f).stem)
            self.ctx.toast.emit(f"Imported {n} project(s) from Project Opener 2.x", "", "success")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Import mode")
        box.setText("Merge with the current workspace, or replace it?")
        merge = box.addButton("Merge", QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton("Replace everything", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is merge:
            a, u = self.ctx.store.import_bundle(data, "merge")
        elif box.clickedButton() is replace:
            a, u = self.ctx.store.import_bundle(data, "replace")
        else:
            return
        self.ctx.toast.emit("Import complete", f"{a} added, {u} updated", "success")

    def _import_v1(self) -> None:
        src = C.legacy_v1_dir() / "projects.json"
        data = read_json(src)
        if not isinstance(data, dict) or not data:
            self.ctx.toast.emit("No Project Opener 1.x data found", str(src), "warning")
            return
        auto = read_json(C.legacy_v1_dir() / "auto_launch.json", {}) or {}
        a, u = self.ctx.store.import_bundle({"projects": data, "auto_launch": auto}, "merge")
        self.ctx.toast.emit("Imported from Project Opener 1.x", f"{a} added, {u} updated", "success")

    def _restore(self) -> None:
        backups = self.ctx.store.backups()
        if not backups:
            self.ctx.toast.emit("No backups yet", "", "info")
            return
        from PySide6.QtWidgets import QInputDialog
        names = [b.name for b in backups[:30]]
        choice, ok = QInputDialog.getItem(self, "Restore backup", "Choose a backup (newest first):", names, 0, False)
        if ok and choice and confirm(self, "Restore", f"Replace the current workspace with {choice}?", danger=True):
            if self.ctx.store.restore_backup(backups[names.index(choice)]):
                self.ctx.toast.emit("Backup restored", choice, "success")
