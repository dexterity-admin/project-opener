"""``app.ui``: theme tokens, motion level, routing.  Owner: builder 4 (SHELL).

Tokens are ``ui.theme.build_tokens`` as a QVariantMap (the QML never holds a raw
colour).  The motion level follows ``quick.motion`` and the runtime guard.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from project_opener.quick import motion as MO
from project_opener.quick.base import ApiBase, ro

log = logging.getLogger(__name__)

ROUTES = ("home", "activity", "projects", "project", "hub", "updates", "settings")
MIN_W, MIN_H = 1040, 660


def tokens_for(dark: bool, accent: str, density: str) -> dict[str, Any]:
    from project_opener.ui import theme
    return dict(dataclasses.asdict(theme.build_tokens(dark=dark, accent=accent, density=density)))


class UiState(ApiBase):
    tokensChanged = Signal()
    motionChanged = Signal()
    routeChanged = Signal()
    motionReduced = Signal(str)              # message said once

    def __init__(self, app: Any):
        super().__init__(app)
        s = app.ctx.settings
        self._dark = s.theme != "light"      # "system" resolved by builder 4 (ui.main_window._system_dark)
        self._tokens = tokens_for(self._dark, s.accent, s.density)
        self._backend = "rhi"
        self._motion = MO.resolve_motion(s.motion, s.motion_reduced_to, MO.MachineFacts(), self._backend)
        self._route = "home"
        self._route_payload: dict[str, Any] = {}
        self._slow_docks = 0

    tokens = ro("QVariantMap", "_tokens", tokensChanged)
    dark = ro(bool, "_dark", tokensChanged)
    motion = ro(str, "_motion", motionChanged)          # rich | purposeful | off
    backend = ro(str, "_backend", motionChanged)        # rhi | software
    route = ro(str, "_route", routeChanged)
    routePayload = ro("QVariantMap", "_route_payload", routeChanged)

    @Property(float, notify=motionChanged)
    def k(self) -> float:
        """Duration scale: QML writes ``duration: app.ui.k * 220``."""
        return MO.K.get(self._motion, 0.6)

    @Property(bool, notify=motionChanged)
    def ambient(self) -> bool:
        """Ambient loops allowed (rich only; QML also gates on the window being active)."""
        return self._motion == "rich"

    @Property(int, constant=True)
    def minimumWidth(self) -> int:
        return MIN_W

    @Property(int, constant=True)
    def minimumHeight(self) -> int:
        return MIN_H

    @Slot(str, "QVariantMap")
    def go(self, route: str, payload: dict[str, Any] | None = None) -> None:
        if route not in ROUTES:
            log.warning("unknown route %s", route)
            return
        self._route, self._route_payload = route, dict(payload or {})
        self.routeChanged.emit()

    @Slot(str)
    def setMotion(self, level: str) -> None:
        """Settings > Appearance: auto | rich | purposeful | off."""
        self.todo("UiState.setMotion")

    @Slot(float, float)
    def reportDockFrames(self, mean_ms: float, worst1_ms: float) -> None:
        """The shell reports each dock opening; two slow ones in a row drop a level (saved, said once)."""
        self.todo("UiState.reportDockFrames")

    @Slot(str)
    def setTheme(self, mode: str) -> None:
        """dark | light | system: rebuild tokens."""
        self.todo("UiState.setTheme")
