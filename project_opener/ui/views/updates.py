"""Updates & About: check, download, install, mirror to the LAN hub; diagnostics.

Update state (last check result, downloaded installer) lives on the AppContext
so it survives a window rebuild after a theme change; this page only renders it.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
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


def _alive(widget: QWidget) -> bool:
    """True while the C++ side of a widget still exists (the page may be rebuilt mid-job)."""
    try:
        from shiboken6 import isValid
        return isValid(widget)
    except Exception:  # noqa: BLE001  # pragma: no cover
        return True


class UpdatesPage(Page):
    route = "updates"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(ctx, parent)
        self._mirroring = False
        self.title_row("Updates", "Version, update sources and diagnostics", "APPLICATION")

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
        log_path = C.data_dir() / C.LOG_DIR / "project-opener.log"
        lb = Button("Open log", "fa5s.file-alt")
        lb.setToolTip(str(log_path))
        lb.clicked.connect(lambda: self._open_log(log_path))
        row.addWidget(lb)
        sb = Button("Show in folder", "fa5s.folder")
        sb.clicked.connect(lambda: winutil.reveal_in_explorer(str(log_path)))
        row.addWidget(sb)
        row.addStretch(1)
        dl.addLayout(row)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        self.log_view.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9pt;")
        dl.addWidget(self.log_view)
        self.content.addWidget(diag)
        self.content.addStretch(1)

        self.bind(ctx.update_checked, self._checked)
        self.bind(ctx.update_progress, self._progress)
        self.bind(ctx.update_ready, self._ready)
        self.bind(ctx.update_failed, self._failed)
        self.render_state()

    def on_show(self) -> None:
        self.render_state()
        self.log_view.setPlainText("\n".join(list(RING)[-80:]))

    # ------------------------------------------------------ shared state
    # Kept on the AppContext (ctx.last_check / ctx.downloaded) so a window
    # rebuild does not lose it.  getattr fallbacks cover a context that does
    # not define the attributes yet.
    @property
    def _result(self) -> CheckResult | None:
        res = getattr(self.ctx, "last_check", None)
        return res if res is not None else getattr(self.ctx, "last_update", None)

    @_result.setter
    def _result(self, value: CheckResult | None) -> None:
        self.ctx.last_check = value
        self.ctx.last_update = value

    @property
    def _info(self) -> UpdateInfo | None:
        res = self._result
        return res.update if res is not None and res.available else None

    @property
    def _installer(self) -> Path | None:
        """The verified download for the currently offered update, if any."""
        path = getattr(self.ctx, "downloaded", None)
        info = self._info
        if not path or info is None:
            return None
        path = Path(path)
        return path if path.name == info.installer and path.exists() else None

    @_installer.setter
    def _installer(self, value: Path | None) -> None:
        self.ctx.downloaded = Path(value) if value else None

    @property
    def _skipped(self) -> bool:
        info = self._info
        return bool(info and info.version == self.ctx.settings.update_skip_version)

    # ------------------------------------------------------------- actions
    def _check(self) -> None:
        self.spinner.start()
        self.check_btn.setEnabled(False)
        self.ctx.check_updates(silent=False)

    def _checked(self, result: CheckResult) -> None:
        self.spinner.stop()
        self.check_btn.setEnabled(True)
        self._result = result
        self.render_state()

    def _failed(self, msg: str) -> None:
        self.spinner.stop()
        self.check_btn.setEnabled(True)
        self.ctx.toast.emit("Update failed", msg, "error")
        self.render_state(error=msg)

    def _download(self) -> None:
        info = self._info
        if not info:
            return
        self.render_state(downloading=True)
        self.ctx.download_update(info)

    def _progress(self, done: int, total: int) -> None:
        bar = getattr(self, "bar", None)
        if bar is not None and _alive(bar):
            bar.setMaximum(max(total, 1))
            bar.setValue(done)

    def _ready(self, path: Path) -> None:
        self._installer = path
        self.render_state()
        self.ctx.toast.emit("Update downloaded", "Verified SHA-256. Ready to install.", "success")

    def _install(self) -> None:
        installer = self._installer
        if installer:
            self.ctx.install_update(installer)

    def _skip(self) -> None:
        info = self._info
        if info:
            self.ctx.settings.update_skip_version = info.version
            self.ctx.settings.save()
            self.render_state()

    def _unskip(self) -> None:
        self.ctx.settings.update_skip_version = ""
        self.ctx.settings.save()
        self.render_state()

    def _open_log(self, path: Path) -> None:
        if not path.exists():
            self.ctx.toast.emit("No log file yet", str(path), "info")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            winutil.reveal_in_explorer(str(path))

    # -------------------------------------------------------------- mirror
    def _mirror_downloaded(self) -> None:
        """Mirror the newer release that has already been downloaded and verified."""
        info, installer = self._info, self._installer
        if info and installer:
            self._start_mirror(info, installer)

    def _mirror_current(self) -> None:
        """Mirror the version that is running right now (so colleagues can install it from the hub)."""
        info, installer = self._info, self._installer
        if info and installer and info.version == C.VERSION:
            self._start_mirror(info, installer)
        else:
            self._start_mirror(None, None)

    def _start_mirror(self, info: UpdateInfo | None, installer: Path | None) -> None:
        if self._mirroring:
            return
        if not self.ctx.hub.configured:
            self.ctx.toast.emit("No Team Hub folder", "Configure one in Settings → Team Hub first.", "warning")
            return
        updater = self.ctx.updater
        ctx = self.ctx
        version = info.version if info else C.VERSION
        self._mirroring = True
        self.render_state(mirroring=version)

        def progress(done: int, total: int) -> None:
            ctx.run_on_gui(lambda: self._progress(done, total) if _alive(self) else None)

        def work() -> Path:
            if info is not None and installer is not None:
                return updater.mirror_to_lan(info, installer)
            rel = updater.fetch_release(f"v{C.VERSION}")
            if rel is None:
                raise RuntimeError(f"release v{C.VERSION} has no installer on GitHub")
            path = updater.download(rel, progress=progress)   # verifies SHA-256
            return updater.mirror_to_lan(rel, path)

        def done(dest: Path) -> None:
            self._mirroring = False
            ctx.toast.emit("Mirrored to Team Hub", f"Version {version} · colleagues can now update from {dest.parent}", "success")
            if _alive(self):
                self.render_state()

        def fail(exc: Exception) -> None:
            self._mirroring = False
            ctx.toast.emit("Mirror failed", str(exc), "error")
            if _alive(self):
                self.render_state()

        ctx.run_async(work, done, fail)

    # -------------------------------------------------------------- render
    def render_state(self, downloading: bool = False, error: str = "", mirroring: str = "") -> None:
        clear_layout(self.state_host)
        t = theme.current()
        s = self.ctx.settings
        self.last_check.setText(f"Last checked {relative_time(s.update_last_check).lower()}" if s.update_last_check else "Not checked yet")
        self.bar = None
        if error:
            self.state_host.addWidget(self._banner("fa5s.exclamation-triangle", error, t.danger))
        res = self._result
        info = self._info
        installer = self._installer
        if info and self._skipped:
            f = QFrame()
            f.setObjectName("panel2")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(14, 10, 14, 10)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("fa5s.forward", 16, t.text_faint))
            lay.addWidget(ic)
            lay.addWidget(label(f"Version {info.version} skipped. You will not be reminded about it; un-skip to see it again.", "", wrap=True), 1)
            un = Button("Un-skip", "fa5s.undo", "ghost")
            un.clicked.connect(self._unskip)
            lay.addWidget(un)
            self.state_host.addWidget(f)
        elif info:
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
            if installer:
                inst = Button("Install and restart", "fa5s.download", "primary")
                inst.clicked.connect(self._install)
                row.addWidget(inst)
                if self.ctx.hub.configured and info.source != "lan":
                    mir = Button("Mirror to Team Hub for colleagues", "fa5s.share-alt")
                    mir.setEnabled(not self._mirroring)
                    mir.clicked.connect(self._mirror_downloaded)
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
        if mirroring:
            box = QFrame()
            box.setObjectName("panel2")
            blay = QVBoxLayout(box)
            blay.setContentsMargins(14, 10, 14, 10)
            blay.addWidget(label(f"Mirroring version {mirroring} to the Team Hub…", "muted"))
            self.bar = QProgressBar()
            self.bar.setTextVisible(False)
            self.bar.setRange(0, 0)          # busy until the download reports a size
            blay.addWidget(self.bar)
            self.state_host.addWidget(box)
        # sources
        clear_layout(self.sources_lay)
        hub_dir = self.ctx.hub.updates_dir()
        lan_text = f"LAN mirror: {hub_dir}" if hub_dir else "LAN mirror: no Team Hub folder configured"
        lan_ok = bool(hub_dir and self.ctx.hub.reachable())
        self.sources_lay.addWidget(self._source_row("fa5s.network-wired", lan_text, "Checked first; works without internet. Anyone can mirror a release here.", lan_ok))
        if self.ctx.hub.configured:
            mrow = QHBoxLayout()
            mrow.setContentsMargins(42, 0, 0, 6)
            mc = Button(f"Mirror this version ({C.VERSION}) to the hub", "fa5s.share-alt")
            mc.setToolTip("Copies the installer for the version you are running into the hub's updates folder "
                          "(downloaded from GitHub if needed) so colleagues can update over the LAN.")
            mc.setEnabled(not self._mirroring)
            mc.clicked.connect(self._mirror_current)
            mrow.addWidget(mc)
            mrow.addStretch(1)
            self.sources_lay.addLayout(mrow)
        gh_ok = bool(s.github_token)
        self.sources_lay.addWidget(self._source_row("fa5b.github", f"GitHub: {C.GITHUB_OWNER}/{C.GITHUB_REPO}",
                                                    "Public releases; no token needed. " + ("Token configured (higher API rate limit)." if gh_ok else "A token in Settings → Updates is optional."), True))

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
