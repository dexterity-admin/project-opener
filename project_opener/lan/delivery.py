"""Alert delivery, exactly once (brief section 3.4).  Owner: builder 1 (CORE+HUB).

``Dispatcher.deliver(event, notify)``:
1. skip when ``event.key`` is in ``delivered/<user>.json`` on the hub (or the local
   ``alerts.jsonl`` when no hub) - "nothing is sent twice";
2. append to ``alerts.jsonl`` (the app's alert list) and the user's pulse;
3. for ``notify.mentions``: an inbox entry (kind "mention") per expanded login;
4. for ``notify.cliq_dm`` / ``cliq_channel``: ``lan.cliq.CliqClient`` (queued for retry when down);
5. record the key (``delivered/<user>.json`` keeps the newest 2,000 keys).
The toast itself is raised by the caller on the GUI thread from the returned flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_opener.core import models as M


@dataclass
class Delivery:
    new: bool                       # False when already delivered (no toast)
    inboxes: list[str]
    cliq_sent: bool
    cliq_queued: bool


class DeliveredLedger:
    def __init__(self, path: Path):
        self.path = Path(path)

    def seen(self, key: str) -> bool:
        raise NotImplementedError("DeliveredLedger.seen")

    def add(self, key: str) -> None:
        raise NotImplementedError("DeliveredLedger.add")


class Dispatcher:
    def __init__(self, hub: object, ledger: DeliveredLedger, cliq: object | None, alerts_path: Path):
        self.hub = hub
        self.ledger = ledger
        self.cliq = cliq
        self.alerts_path = Path(alerts_path)

    def deliver(self, event: M.WatchEvent, notify: M.Notify) -> Delivery:
        raise NotImplementedError("Dispatcher.deliver")
