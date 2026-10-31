"""Updates & About: check, download, install, mirror to the LAN hub; diagnostics."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget

from project_opener import constants as C
from project_opener.core import winutil
from project_opener.core.logging_setup import RING
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, clear_layout
from project_opener.ui.widgets.cards import relative_time
from project_opener.ui.widgets.common import Badge, Button, IconCircle, Spinner, label
from project_opener.update.updater import CheckResult, UpdateInfo


class UpdatesPage(Page):
    route = "updates"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self._installer: Path | None = None
        self._info: UpdateInfo | None = None
        self.title_row("Updates & About", "", "APPLICATION")

        self.card, lay = self.panel()
        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(64, 64))
        head.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(f"{C.APP_NAME} {C.VERSION}", "h2"))
        col.addWidget(label(f"{C.COMPANY} · internal tool · built in-house", "muted"))
        self.last_check = label("", "faint")
        col.addWidget(self.last_check)
        head.addLayout(col, 1)
        self.spinner = Spinner(18)
        self.spinner.hide()
        head.addWidget(self.spinner)
        self.check_btn = Button("Check for updates", "fa5s.sync-alt", "primary")
        self.check_btn.clicked.connect(lambda: self._check())
        head.addWidget(self.check_btn)
        lay.addLayout(head)
        self.state_host = QVBoxLayout()
        lay.addLayout(self.state_host)
        self.content.addWidget(self.card)

        self.sources_panel, sl = self.panel()
        sl.addWidget(label("UPDATE SOURCES", "eyebrow"))
        self.sources_lay = QVBoxLayout()
        sl.addLayout(self.sources_lay)
        self.content.addWidget(self.sources_panel)

        diag, dl = self.panel()
        dl.addWidget(label("DIAGNOSTICS", "eyebrow"))
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(label(f"Data folder: {C.data_dir()}", "muted"))
        info.addWidget(label(f"Executable: {C.bundle_dir()}", "muted"))
        info.addWidget(label(f"Machine: {winutil.IS_WIN and __import__('socket').gethostname()} · user {ctx.user}", "muted"))
        dl.addLayout(info)
        row = QHBoxLayout()
        ob = Button("Open data folder", "fa5s.folder-open")
        ob.clicked.connect(lambda: winutil.reveal_in_explorer(str(C.data_dir())))
        row.addWidget(ob)
        lb = Button("Open log", "fa5s.file-alt")
        lb.clicked.connect(lambda: winutil.reveal_in_explorer(str(C.data_dir() / C.LOG_DIR / "project-opener.log")))
        row.addWidget(lb)
        row.addStretch(1)
        dl.addLayout(row)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        self.log_view.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9pt;")
        dl.addWidget(self.log_view)
        self.content.addWidget(diag)
        self.content.addStretch(1)

        ctx.update_checked.connect(self._checked)
        ctx.update_progress.connect(self._progress)
        ctx.update_ready.connect(self._ready)
        ctx.update_failed.connect(self._failed)
        self.render_state()

    def on_show(self) -> None:
        self.render_state()
        self.log_view.setPlainText("\n".join(list(RING)[-80:]))

    # ------------------------------------------------------------- actions
    def _check(self) -> None:
        self.spinner.start()
        self.check_btn.setEnabled(False)
        self.ctx.check_updates(silent=False)

    def _checked(self, result: CheckResult) -> None:
        self.spinner.stop()
        self.check_btn.setEnabled(True)
        self._info = result.update if result.available else None
        self.render_state()

    def _failed(self, msg: str) -> None:
        self.spinner.stop()
        self.check_btn.setEnabled(True)
        self.ctx.toast.emit("Update failed", msg, "error")
        self.render_state(error=msg)

    def _download(self) -> None:
        if not self._info:
            return
        self.render_state(downloading=True)
        self.ctx.download_update(self._info)

    def _progress(self, done: int, total: int) -> None:
        if hasattr(self, "bar") and self.bar is not None:
            self.bar.setMaximum(max(total, 1))
            self.bar.setValue(done)

    def _ready(self, path: Path) -> None:
        self._installer = path
        self.render_state()
        self.ctx.toast.emit("Update downloaded", "Verified SHA-256. Ready to install.", "success")

    def _install(self) -> None:
        if self._installer:
            self.ctx.install_update(self._installer)

    def _mirror(self) -> None:
        if not (self._installer and self._info):
            return
        try:
            dest = self.ctx.updater.mirror_to_lan(self._info, self._installer)
            self.ctx.toast.emit("Mirrored to Team Hub", f"Colleagues can now update from {dest.parent}", "success")
            self.render_state()
        except Exception as exc:  # noqa: BLE001
            self.ctx.toast.emit("Mirror failed", str(exc), "error")

    def _skip(self) -> None:
        if self._info:
            self.ctx.settings.update_skip_version = self._info.version
            self.ctx.settings.save()
            self._info = None
            self.render_state()

    # -------------------------------------------------------------- render
    def render_state(self, downloading: bool = False, error: str = "") -> None:
        clear_layout(self.state_host)
        t = theme.current()
        s = self.ctx.settings
        self.last_check.setText(f"Last checked {relative_time(s.update_last_check).lower()}" if s.update_last_check else "Not checked yet")
        self.bar = None
        if error:
            self.state_host.addWidget(self._banner("fa5s.exclamation-triangle", error, t.danger))
        res = self.ctx.last_update
        if self._info:
            info = self._info
            f = QFrame()
            f.setObjectName("banner")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(16, 12, 16, 12)
            head = QHBoxLayout()
            head.addWidget(IconCircle("fa5s.arrow-circle-up", t.accent, 36))
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(f"Version {info.version} is available", "h3"))
            src = "Office LAN hub" if info.source == "lan" else "GitHub Releases"
            size = f" · {info.size / 1_048_576:.1f} MB" if info.size else ""
            col.addWidget(label(f"From {src}{size} · {relative_time(info.published_at).lower() if info.published_at else ''}", "muted"))
            head.addLayout(col, 1)
            lay.addLayout(head)
            if info.notes:
                notes = QPlainTextEdit(info.notes.strip())
                notes.setReadOnly(True)
                notes.setMaximumHeight(140)
                lay.addWidget(notes)
            if downloading:
                self.bar = QProgressBar()
                self.bar.setTextVisible(False)
                lay.addWidget(self.bar)
                lay.addWidget(label("Downloading and verifying…", "muted"))
            row = QHBoxLayout()
            if self._installer:
                inst = Button("Install and restart", "fa5s.download", "primary")
                inst.clicked.connect(self._install)
                row.addWidget(inst)
                if self.ctx.hub.configured and info.source != "lan":
                    mir = Button("Mirror to Team Hub for colleagues", "fa5s.share-alt")
                    mir.clicked.connect(self._mirror)
                    row.addWidget(mir)
            elif not downloading:
                dl = Button("Download update", "fa5s.cloud-download-alt", "primary")
                dl.clicked.connect(self._download)
                row.addWidget(dl)
                skip = Button("Skip this version", "fa5s.forward", "ghost")
                skip.clicked.connect(self._skip)
                row.addWidget(skip)
            row.addStretch(1)
            lay.addLayout(row)
            self.state_host.addWidget(f)
        elif res is not None and not res.available:
            msg = "You are on the latest version." if not res.errors else "Checked LAN hub; GitHub: " + "; ".join(res.errors)
            self.state_host.addWidget(self._banner("fa5s.check-circle", msg, t.success if not res.errors else t.warning))
        # sources
        clear_layout(self.sources_lay)
        hub_dir = self.ctx.hub.updates_dir()
        lan_text = f"LAN mirror: {hub_dir}" if hub_dir else "LAN mirror: no Team Hub folder configured"
        lan_ok = bool(hub_dir and self.ctx.hub.reachable())
        self.sources_lay.addWidget(self._source_row("fa5s.network-wired", lan_text, "Checked first; works without internet. Anyone can mirror a release here.", lan_ok))
        gh_ok = bool(s.github_token)
        self.sources_lay.addWidget(self._source_row("fa5b.github", f"GitHub: {C.GITHUB_OWNER}/{C.GITHUB_REPO}",
                                                    "Private repository. " + ("Token configured." if gh_ok else "Add a read-only token in Settings → Updates to check here."), gh_ok))

    def _banner(self, icon_name: str, text: str, color: str) -> QFrame:
        f = QFrame()
        f.setObjectName("panel2")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 10, 14, 10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 16, color))
        lay.addWidget(ic)
        lay.addWidget(label(text, "", wrap=True), 1)
        return f

    def _source_row(self, icon_name: str, title: str, sub: str, ok: bool) -> QWidget:
        t = theme.current()
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)
        lay.addWidget(IconCircle(icon_name, t.success if ok else t.text_faint, 32))
        col = QVBoxLayout()
        col.setSpacing(0)
        tl = QLabel(title)
        tl.setStyleSheet("font-weight: 600;")
        col.addWidget(tl)
        col.addWidget(label(sub, "faint", wrap=True))
        lay.addLayout(col, 1)
        lay.addWidget(Badge("Ready" if ok else "Not set", t.success if ok else t.text_faint))
        return w
