"""Updates & About: check, download, install, mirror to the LAN hub; diagnostics.

Update state (last check result, downloaded installer) lives on the AppContext
so it survives a window rebuild after a theme change; this page only renders it.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from project_opener import constants as C
from project_opener.core import winutil
from project_opener.core.logging_setup import RING
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.views.base import Page, badge, clear_layout, row_widget, section_label
from project_opener.ui.widgets.cards import relative_time
from project_opener.ui.widgets.common import Button, Spinner, label
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
        row = self.title_row("Updates", f"{C.APP_NAME} {C.VERSION}")
        self.last_check = self.subtitle_label       # "Project Opener 3.x.y · last checked …"
        self.spinner = Spinner(18)
        self.spinner.hide()
        row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignTop)
        self.check_btn = Button("Check for updates", "fa5s.sync-alt", "primary")
        self.check_btn.clicked.connect(lambda: self._check())
        row.addWidget(self.check_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.card, lay = self.panel()
        lay.addWidget(section_label("This PC"))
        self.state_host = QVBoxLayout()
        self.state_host.setSpacing(10)
        lay.addLayout(self.state_host)
        self.content.addWidget(self.card)

        self.sources_panel, sl = self.panel()
        sl.addWidget(section_label("Update sources"))
        self.sources_lay = QVBoxLayout()
        sl.addLayout(self.sources_lay)
        self.content.addWidget(self.sources_panel)

        diag, dl = self.panel()
        dl.addWidget(section_label("Diagnostics"))
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(label(f"{C.APP_NAME} {C.VERSION} · {C.COMPANY}", "muted"))
        info.addWidget(label(f"Data folder: {C.data_dir()}", "muted"))
        info.addWidget(label(f"Executable: {C.bundle_dir()}", "muted"))
        info.addWidget(label(f"Machine: {__import__('socket').gethostname()} · user {ctx.user}", "muted"))
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
        self.log_view.setFixedHeight(120)
        self.log_view.setFont(theme.ui_font(9))
        self.log_view.setPlaceholderText("No log lines yet this session.")
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
        self.ctx.toast.emit("Update check failed", msg, "error")
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
        info = self._info
        verified = bool(info and info.sha256)
        self.ctx.toast.emit("Update downloaded",
                            "SHA-256 verified. Ready to install." if verified
                            else "Checksum not provided by the release, so it was not verified. Ready to install.",
                            "success" if verified else "warning")

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
        checked = f" · last checked {relative_time(s.update_last_check).lower()}" if s.update_last_check else ""
        self.set_subtitle(f"{C.APP_NAME} {C.VERSION}{checked}")
        self.bar = None
        res = self._result
        if error:
            f = self._banner("fa5s.exclamation-triangle", error, t.danger, "banner_danger")
            retry = Button("Try again", "fa5s.sync-alt")          # outlined, ink: a control, not a note
            retry.clicked.connect(lambda: self._check())
            f.layout().addWidget(retry, 0, Qt.AlignmentFlag.AlignVCenter)
            self.state_host.addWidget(f)
            res = None                      # the one message is the error; no second banner
        info = self._info
        installer = self._installer
        if mirroring:
            res = info = None               # the mirror box is the state while it runs; no banner above or under it
        # One filled control on the screen: "Install and restart" when an
        # update is ready, otherwise "Check for updates".
        # One filled control: Download / Install while an update is offered, else Check for updates.
        offered = bool(info) and not self._skipped and not mirroring
        self.check_btn.setObjectName("" if offered else "primary")
        self.check_btn.setIcon(icons.icon("fa5s.sync-alt", t.text_muted if offered else t.accent_fg))
        self.check_btn.style().unpolish(self.check_btn)
        self.check_btn.style().polish(self.check_btn)
        if info and self._skipped:
            f = QFrame()
            f.setObjectName("panel2")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(14, 10, 14, 10)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("fa5s.forward", 16, t.text_faint))
            lay.addWidget(ic)
            lay.addWidget(label(f"Version {info.version} is skipped: it is not offered again until a newer one appears.", "muted", wrap=True), 1)
            un = Button("Offer it again", "fa5s.undo", "ghost")
            un.clicked.connect(self._unskip)
            lay.addWidget(un)
            self.state_host.addWidget(f)
        elif info:
            f = QFrame()
            f.setObjectName("banner")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(16, 12, 16, 12)
            head = QHBoxLayout()
            head.setSpacing(10)
            up = QLabel()
            up.setPixmap(icons.pixmap("fa5s.arrow-circle-up", 16, t.info))
            up.setFixedWidth(18)
            head.addWidget(up, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(f"Version {info.version} is available", "h3"))
            src = "the LAN mirror" if info.source == "lan" else "GitHub"
            size = f" · {info.size / 1_048_576:.1f} MB" if info.size else ""
            when = f" · published {relative_time(info.published_at).lower()}" if info.published_at else ""
            col.addWidget(label(f"From {src}{size}{when}", "muted"))
            head.addLayout(col, 1)
            lay.addLayout(head)
            if info.notes:
                notes = label(info.notes.strip(), "muted", wrap=True)
                notes.setContentsMargins(28, 0, 0, 0)
                lay.addWidget(notes)
            if downloading:
                self.bar = QProgressBar()
                self.bar.setTextVisible(False)
                self.bar.setFixedHeight(4)
                self.bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                lay.addWidget(self.bar)
                lay.addWidget(label("Downloading, then checking the SHA-256", "muted"))
            row = QHBoxLayout()
            if installer:
                inst = Button("Install and restart", "fa5s.download", "primary")
                inst.clicked.connect(self._install)
                row.addWidget(inst)
                if self.ctx.hub.configured and info.source != "lan":
                    mir = Button(f"Mirror {info.version} to the Team Hub", "fa5s.share-alt")
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
            if not res.errors:
                msg = "You are on the latest version."
                self.state_host.addWidget(self._banner("fa5s.check-circle", msg, t.success, "banner"))
            else:
                checked_src = " and ".join("the LAN mirror" if x == "lan" else "GitHub" for x in res.checked_sources) or "the LAN mirror"
                msg = f"No newer version on {checked_src}. GitHub could not be reached: " + "; ".join(res.errors) + "."
                self.state_host.addWidget(self._banner("fa5s.exclamation-triangle", msg, t.warning, "banner_warn"))
        elif res is None and not error and not mirroring:
            self.state_host.addWidget(label(
                f"Not checked yet. Checks run every {C.UPDATE_CHECK_INTERVAL_H} hours, LAN mirror first, then GitHub."
                if s.update_check else "Not checked yet. Automatic checks are off (Settings → Updates).", "muted", wrap=True))
        if mirroring:
            box = QFrame()
            box.setObjectName("banner")       # the bar's track (surface_2) must show against the well
            blay = QVBoxLayout(box)
            blay.setContentsMargins(14, 10, 14, 12)
            blay.setSpacing(8)
            blay.addWidget(label(f"Mirroring version {mirroring} to the Team Hub", "muted"))
            self.bar = QProgressBar()
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(4)
            self.bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.bar.setRange(0, 0)          # busy until the download reports its size, then the true ratio
            blay.addWidget(self.bar)
            self.state_host.addWidget(box)
        # sources
        clear_layout(self.sources_lay)
        hub_dir = self.ctx.hub.updates_dir()
        lan_ok = bool(hub_dir and self.ctx.hub.reachable())
        self.sources_lay.addWidget(self._source_row("fa5s.network-wired", "LAN mirror",
                                                    str(hub_dir) if hub_dir else "Needs a Team Hub folder (Settings → Team Hub). Checked first; works without internet.", lan_ok))
        if self.ctx.hub.configured and not installer:   # once a newer installer is downloaded, that one is the mirror
            mrow = QHBoxLayout()
            mrow.setContentsMargins(28, 0, 0, 6)
            mc = Button(f"Mirror {C.VERSION} to the Team Hub", "fa5s.share-alt")
            mc.setToolTip("Copies the installer for the version you are running into the hub's updates folder "
                          "(downloaded from GitHub if needed) so colleagues can update over the LAN.")
            mc.setEnabled(not self._mirroring)
            mc.clicked.connect(self._mirror_current)
            mrow.addWidget(mc)
            mrow.addStretch(1)
            self.sources_lay.addLayout(mrow)
        gh_ok = bool(s.github_token)
        self.sources_lay.addWidget(self._source_row("fa5b.github", "GitHub releases",
                                                    f"{C.GITHUB_OWNER}/{C.GITHUB_REPO} · " + ("token set, higher API rate limit" if gh_ok else "public, no token needed"), True))

    def _banner(self, icon_name: str, text: str, color: str, kind: str = "banner") -> QFrame:
        f = QFrame()
        f.setObjectName(kind)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 16, color))
        ic.setFixedWidth(18)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(label(text, "", wrap=True), 1)
        return f

    def _source_row(self, icon_name: str, title: str, sub: str, ok: bool) -> QWidget:
        t = theme.current()
        w, lay = row_widget(44)
        lay.setContentsMargins(0, 4, 0, 4)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 16, t.text_muted))
        ic.setFixedWidth(18)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        tl = QLabel(title)
        tl.setFont(theme.ui_font(weight=500))
        col.addWidget(tl)
        col.addWidget(label(sub, "faint", wrap=True))
        lay.addLayout(col, 1)
        lay.addWidget(badge("Reachable" if ok else "Not set", "ok" if ok else "neutral"), 0, Qt.AlignmentFlag.AlignTop)
        return w
