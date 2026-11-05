"""``app.settings``: every setting as get/set by key, native file dialogs, secrets, and the
Updates page's state.  Owner: builder 4 (SHELL).

The Settings page (including Settings > Snapshot) reads ``value(key)`` and
writes ``setValue(key, v)``; ``changed(key)`` tells other bindings (and other
builders: ``app.desktop`` connects to it for the pill keys).  Keys are
``core.settings.Settings`` field names.  Changing hub, variables or update
settings calls ``app.ctx.apply_settings``; capture keys tell ``app.capture``;
hotkey and Explorer keys tell ``app.desktop``.

Updates (no other sub-API owns them): ``updateState`` (idle | checking |
available | none | downloading | ready | skipped | error | mirroring) and the
slots ``checkUpdates``, ``downloadUpdate``, ``installUpdate``, ``skipUpdate``,
``unskipUpdate``, ``mirrorUpdate`` over the 3.2 ``AppContext`` update flow.
"""
from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from project_opener import constants as C
from project_opener.core.settings import Settings
from project_opener.quick.base import ApiBase, ro
from project_opener.ui import text as T

log = logging.getLogger(__name__)

APPLY_KEYS = {"hub_path", "hub_share_pulse", "presence_udp", "display_name", "role", "variables",
              "update_channel", "update_check", "launch_delay_ms"}
THEME_KEYS = {"accent", "density"}
CAPTURE_KEYS = {"capture_enabled", "capture_interval_s", "capture_browser_urls", "capture_ignore",
                "open_office_via_com"}
HOTKEY_KEYS = {"hotkeys", "hotkeys_enabled"}
SHELL_KEYS = {"explorer_verb", "sendto_entry"}
PILL_KEYS = {"pill_enabled", "pill_rest_style", "pill_positions", "hide_when_fullscreen"}
SECRET_KEYS = {"github_token_enc", "cliq_token_enc"}
FIELD_TYPES = {f.name: f.default if f.default is not dataclasses.MISSING else f.default_factory()  # type: ignore[misc]
               for f in dataclasses.fields(Settings)}


def coerce(key: str, value: Any) -> Any:
    """``value`` from QML as the type of the Settings field ``key`` (ints arrive as floats, maps as dicts)."""
    default = FIELD_TYPES.get(key)
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(default, int):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return "" if value is None else str(value)
    if isinstance(default, dict):
        return {str(k): v for k, v in dict(value or {}).items()}
    if isinstance(default, list):
        return list(value or [])
    return value


class SettingsApi(ApiBase):
    changed = Signal(str)
    cliqTested = Signal(bool, str)
    updatesChanged = Signal()

    def __init__(self, app: Any):
        super().__init__(app)
        self._update_state = "idle"
        self._update_error = ""
        self._update_progress = 0.0
        ctx = app.ctx
        ctx.update_checked.connect(self._on_checked)
        ctx.update_progress.connect(self._on_progress)
        ctx.update_ready.connect(self._on_ready)
        ctx.update_failed.connect(self._on_failed)
        if ctx.downloaded is not None:
            self._update_state = "ready"

    # ------------------------------------------------------------ values
    @Slot(str, result="QVariant")
    def value(self, key: str) -> Any:
        if key in SECRET_KEYS:
            return None
        return getattr(self.app.ctx.settings, key, None)

    @Slot(str, "QVariant")
    def setValue(self, key: str, value: Any) -> None:  # noqa: N802
        s = self.app.ctx.settings
        if key in SECRET_KEYS or not hasattr(s, key) or key.startswith("_"):
            log.warning("setValue: unknown or protected key %s", key)
            return
        new = coerce(key, value)
        if getattr(s, key) == new:
            return
        if key == "run_at_startup":
            from project_opener.core import winutil
            if not winutil.set_run_at_startup(bool(new)):
                self.app.toast.emit("Could not change the startup entry", "Windows refused the change.", "error")
                return
        setattr(s, key, new)
        self._side_effects(key, new)
        self.changed.emit(key)

    def _side_effects(self, key: str, value: Any) -> None:
        s = self.app.ctx.settings
        if key == "theme":
            self.app.ui.setTheme(value)
            return
        if key == "motion":
            self.app.ui.setMotion(value)
            return
        if key in THEME_KEYS:
            s.save()
            self.app.ui.retheme()
            return
        if key in APPLY_KEYS:
            self.app.ctx.apply_settings()
            return
        s.save()
        if key == "capture_enabled":
            self._call("capture", "setGlobal", bool(value))      # saves the setting and re-evaluates paused
            self.app.activities.refresh()
        elif key in CAPTURE_KEYS:
            # interval, browser URLs, ignore rules, Office via COM -> the capture thread (V4-SEAMS, builder 2 ask 1)
            self._call("capture", "apply_settings")
        elif key in HOTKEY_KEYS:
            self._call("desktop", "applyHotkeys")
        elif key in SHELL_KEYS:
            # one switch for both entries: the desktop installs or removes both and saves both keys
            s.explorer_verb = s.sendto_entry = bool(value)
            s.save()
            self._call("desktop", "setShellEntries", bool(value))
        elif key == "pill_pinned":
            self._call("desktop", "setPillPinned", bool(value))
        elif key in PILL_KEYS:
            self._call("desktop", "applyPill")

    def _call(self, api: str, slot: str, *args: Any) -> None:
        obj = getattr(self.app, api, None)
        if obj is None:
            return
        try:
            getattr(obj, slot)(*args)
        except Exception:  # noqa: BLE001
            log.exception("%s.%s failed", api, slot)

    @Slot(str, str)
    def setHotkey(self, action: str, keys: str) -> None:  # noqa: N802
        """One of the four keys (snapshot | add_window | panel | palette)."""
        hk = dict(self.app.ctx.settings.hotkeys)
        hk[action] = keys.strip()
        self.setValue("hotkeys", hk)

    @Slot(str, str)
    def setVariable(self, name: str, value: str) -> None:  # noqa: N802
        """``{NAME}`` -> value; an empty value removes it."""
        from project_opener.core.pathvars import normalise_var_name
        key = normalise_var_name(name)
        if not key:
            return
        var = dict(self.app.ctx.settings.variables)
        if value.strip():
            var[key] = value.strip()
        else:
            var.pop(key, None)
        self.setValue("variables", var)

    @Slot()
    def resetPillPosition(self) -> None:  # noqa: N802
        """Forget the remembered pill places: it returns to bottom right above the notification area."""
        self.setValue("pill_positions", {})

    @Slot(str, result=str)
    def removeIgnoreRule(self, process: str) -> str:  # noqa: N802
        rules = [r for r in self.app.ctx.settings.capture_ignore if r.get("process") != process]
        self.setValue("capture_ignore", rules)
        return process

    # ------------------------------------------------------------- Cliq
    @Property(bool, notify=changed)
    def hasCliqToken(self) -> bool:  # noqa: N802
        return bool(self.app.ctx.settings.cliq_token_enc)

    @Slot(str)
    def setCliqToken(self, token: str) -> None:  # noqa: N802
        """Stored with DPAPI; never echoed back to QML.  An empty token removes it."""
        s = self.app.ctx.settings
        s.cliq_token = token.strip()
        s.save()
        self.changed.emit("cliq_token_enc")

    @Slot()
    def testCliq(self) -> None:  # noqa: N802
        """Find my Cliq id (the stored one, else by e-mail) and send myself a test message; answer with
        ``cliqTested``.  The token is the office bot's webhook token (V4-SEAMS, builder 1 ask 2)."""
        s = self.app.ctx.settings
        if not s.cliq_token_enc or not s.cliq_bot:
            self.cliqTested.emit(False, "Enter the office bot's name and token first.")
            return
        if not s.cliq_user_id and not s.email.strip():
            self.cliqTested.emit(False, "Enter your e-mail address first; the bot finds you by it.")
            return
        root = Path(getattr(self.app.ctx.store, "root", C.data_dir()))
        email, base, bot, token, known = s.email.strip(), s.cliq_api_base, s.cliq_bot, s.cliq_token, s.cliq_user_id
        outbox = root / getattr(C, "CLIQ_OUTBOX_FILE", "cliq-outbox.jsonl")

        def work() -> tuple[bool, str, str]:
            from project_opener.lan.cliq import CliqClient
            client = CliqClient(base, bot, token, outbox)
            uid = known or client.lookup_user(email)
            if not uid:
                return False, (f"Cliq would not look up {email}. Paste your Cliq user id below instead "
                               "(Cliq, your profile)."), ""
            res = client.dm([uid], "Project Opener test: your Cliq account is linked.")
            ok = bool(getattr(res, "ok", False))
            msg = "Linked: a test message is in your Cliq." if ok else (
                getattr(res, "message", "") or "Cliq refused the message.")
            return ok, msg, uid

        def done(result: tuple[bool, str, str]) -> None:
            ok, msg, uid = result
            if ok and uid and uid != s.cliq_user_id:
                s.cliq_user_id = uid
                s.save()
                self.changed.emit("cliq_user_id")
            self.cliqTested.emit(ok, msg)

        def fail(exc: Exception) -> None:
            self.cliqTested.emit(False, str(exc) or type(exc).__name__)

        self.app.run_async(work, done, fail)

    @Slot()
    def unlinkCliq(self) -> None:  # noqa: N802
        self.setValue("cliq_user_id", "")

    # ----------------------------------------------------------- dialogs
    def _dialog_parent(self) -> Any:
        return getattr(self.app.ui, "_window", None)

    @Slot(str, str, result=str)
    def browseFolder(self, title: str, start: str) -> str:  # noqa: N802
        """Native folder dialog, modal to the main window; "" when cancelled."""
        from PySide6.QtWidgets import QFileDialog
        return QFileDialog.getExistingDirectory(None, title or "Choose a folder", start or "") or ""

    @Slot(str, str, str, result=str)
    def browseFile(self, title: str, start: str, filters: str) -> str:  # noqa: N802
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(None, title or "Choose a file", start or "", filters or "")
        return path or ""

    @Slot(str, str, result="QStringList")
    def browseFiles(self, title: str, start: str) -> list[str]:  # noqa: N802
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(None, title or "Choose files", start or "")
        return list(paths or [])

    @Slot(result="QVariantMap")
    def variables(self) -> dict[str, str]:
        return dict(self.app.ctx.settings.variables)

    @Slot(str)
    def openFolder(self, path: str) -> None:  # noqa: N802
        """Explorer at ``path`` (the data folder, the log folder)."""
        import os
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        except Exception as exc:  # noqa: BLE001
            self.app.toast.emit("Could not open the folder", str(exc), "error")

    @Property(str, constant=True)
    def dataFolder(self) -> str:  # noqa: N802
        return str(getattr(self.app.ctx.store, "root", C.data_dir()))

    # ----------------------------------------------------------- updates
    updateState = ro(str, "_update_state", updatesChanged)
    updateError = ro(str, "_update_error", updatesChanged)
    updateProgress = ro(float, "_update_progress", updatesChanged)

    def _info(self) -> Any:
        res = self.app.ctx.last_check
        return res.update if res and res.available else None

    @Property("QVariantMap", notify=updatesChanged)
    def update(self) -> dict[str, Any]:
        """{version, source, size, published, notes} of the offered version; {} when none."""
        info = self._info()
        if info is None:
            return {}
        return {"version": info.version, "source": "the LAN mirror" if info.source == "lan" else "GitHub",
                "size": f"{info.size / 1_048_576:.1f} MB" if info.size else "",
                "published": f"published {T.relative_time(info.published_at).lower()}" if info.published_at else "",
                "notes": (info.notes or "").strip()}

    @Property(str, notify=updatesChanged)
    def updateLine(self) -> str:  # noqa: N802
        """"Project Opener 4.0.0 · last checked 5 min ago"."""
        s = self.app.ctx.settings
        checked = f"last checked {T.relative_time(s.update_last_check).lower()}" if s.update_last_check else ""
        return T.join_facts(f"{C.APP_NAME} {C.VERSION}", checked)

    @Slot()
    def checkUpdates(self) -> None:  # noqa: N802
        self._set_update("checking")
        self.app.ctx.check_updates(silent=True)

    def _set_update(self, state: str, error: str = "") -> None:
        self._update_state, self._update_error = state, error
        self.updatesChanged.emit()

    def _on_checked(self, result: Any) -> None:
        if result.errors and not result.available:
            self._set_update("error", "; ".join(result.errors))
        elif result.available and result.update.version == self.app.ctx.settings.update_skip_version:
            self._set_update("skipped")
        else:
            self._set_update("available" if result.available else "none")

    def _on_progress(self, done: int, total: int) -> None:
        self._update_progress = (done / total) if total else 0.0
        self._set_update("downloading")

    def _on_ready(self, _path: Any) -> None:
        self._set_update("ready")

    def _on_failed(self, msg: str) -> None:
        self._set_update("error", msg)

    @Slot()
    def downloadUpdate(self) -> None:  # noqa: N802
        info = self._info()
        if info is None:
            return
        self._update_progress = 0.0
        self._set_update("downloading")
        self.app.ctx.download_update(info)

    @Slot()
    def installUpdate(self) -> None:  # noqa: N802
        if self.app.ctx.downloaded is not None:
            self.app.ctx.install_update(self.app.ctx.downloaded)

    @Slot()
    def skipUpdate(self) -> None:  # noqa: N802
        info = self._info()
        if info is not None:
            self.app.ctx.settings.update_skip_version = info.version
            self.app.ctx.settings.save()
            self._set_update("skipped")

    @Slot()
    def unskipUpdate(self) -> None:  # noqa: N802
        self.app.ctx.settings.update_skip_version = ""
        self.app.ctx.settings.save()
        self._set_update("available" if self._info() else "idle")

    @Slot()
    def mirrorUpdate(self) -> None:  # noqa: N802
        """Copy the downloaded installer into the hub's updates/ folder for colleagues."""
        ctx = self.app.ctx
        info, installer = self._info(), ctx.downloaded
        if not ctx.hub.configured:
            self.app.toast.emit("No Team Hub folder", "Choose one in Settings first.", "warning")
            return
        if info is None or installer is None:
            return
        self._set_update("mirroring")
        updater = ctx.updater

        def done(dest: Path) -> None:
            self.app.toast.emit("Mirrored to the Team Hub", f"Version {info.version} · {dest.parent}", "success")
            self._set_update("ready")

        def fail(exc: Exception) -> None:
            self.app.toast.emit("Mirror failed", str(exc), "error")
            self._set_update("ready")

        self.app.run_async(lambda: updater.mirror_to_lan(info, installer), done, fail)
