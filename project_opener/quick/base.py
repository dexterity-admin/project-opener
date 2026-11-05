"""Shared base of the facade's sub-objects (``app.activities``, ``app.capture`` ...).

Each sub-API is a ``QObject`` the QML reads through properties, models and
slots.  It reaches the services through ``self.app`` (the ``AppFacade``):
``app.ctx`` (the 3.2 ``AppContext``: store, settings, resolver, launcher, hub,
pool), ``app.snapshots`` (``SnapshotStore``), ``app.run_async`` and
``app.run_on_gui``.  Sub-APIs never import each other; they talk through the
facade's signals or by calling another sub-API through ``self.app.<name>``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, Signal

if TYPE_CHECKING:  # pragma: no cover
    from project_opener.quick.facade import AppFacade

log = logging.getLogger(__name__)


def ro(type_: Any, attr: str, notify: Signal | None = None) -> Property:
    """A read-only QML property backed by ``self.<attr>``; ``notify`` is the class's change signal.

    Usage in a class body::

        stateChanged = Signal()
        state = ro(str, "_state", stateChanged)
    """
    def getter(self: Any) -> Any:
        return getattr(self, attr)
    if notify is None:
        return Property(type_, getter, constant=True)
    return Property(type_, getter, notify=notify)


class ApiBase(QObject):
    def __init__(self, app: AppFacade):
        super().__init__(app)
        self.app = app

    def set_(self, attr: str, value: Any, signal: Any) -> bool:
        """Store ``value`` in ``self.<attr>`` and emit ``signal`` when it changed."""
        if getattr(self, attr, None) == value:
            return False
        setattr(self, attr, value)
        signal.emit()
        return True

    # Lifecycle hooks the facade calls; override as needed.
    def start(self) -> None:
        """After the window is up (timers, first refresh)."""

    def shutdown(self) -> None:
        """Before the process exits (stop threads, flush files)."""

    @staticmethod
    def todo(name: str) -> Any:
        """Placeholder body for a slot a builder has not written yet."""
        log.warning("not implemented yet: %s", name)
        raise NotImplementedError(name)
