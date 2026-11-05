"""``app.settings``: every setting as get/set by key, native file dialogs, secrets.  Owner: builder 4 (SHELL).

The Settings page (including Settings > Snapshot) reads ``value(key)`` and
writes ``setValue(key, v)``; ``changed(key)`` tells other bindings.  Keys are
``core.settings.Settings`` field names.  Changing hub, variables or update
settings calls ``app.ctx.apply_settings``; capture keys tell ``app.capture``;
pill/hotkey/explorer keys tell ``app.desktop``.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from project_opener.quick.base import ApiBase


class SettingsApi(ApiBase):
    changed = Signal(str)
    cliqTested = Signal(bool, str)

    @Slot(str, result="QVariant")
    def value(self, key: str) -> Any:
        return getattr(self.app.ctx.settings, key, None)

    @Slot(str, "QVariant")
    def setValue(self, key: str, value: Any) -> None:  # noqa: N802
        self.todo("SettingsApi.setValue")

    @Property(bool, notify=changed)
    def hasCliqToken(self) -> bool:  # noqa: N802
        return bool(self.app.ctx.settings.cliq_token_enc)

    @Slot(str)
    def setCliqToken(self, token: str) -> None:  # noqa: N802
        """Stored with DPAPI; never echoed back to QML."""
        self.todo("SettingsApi.setCliqToken")

    @Slot()
    def testCliq(self) -> None:  # noqa: N802
        """Look up my Cliq id by e-mail and send myself a test DM; answer with ``cliqTested``."""
        self.todo("SettingsApi.testCliq")

    @Slot(str, str, result=str)
    def browseFolder(self, title: str, start: str) -> str:  # noqa: N802
        """Native folder dialog, modal to the main window; "" when cancelled."""
        return self.todo("SettingsApi.browseFolder")

    @Slot(str, str, str, result=str)
    def browseFile(self, title: str, start: str, filters: str) -> str:  # noqa: N802
        return self.todo("SettingsApi.browseFile")

    @Slot(result="QVariantMap")
    def variables(self) -> dict[str, str]:
        return dict(self.app.ctx.settings.variables)
