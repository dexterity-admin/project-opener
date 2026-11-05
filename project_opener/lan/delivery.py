"""Alert delivery, exactly once (brief section 3.4).  Owner: builder 1 (CORE+HUB).

``Dispatcher.deliver(event, notify)``:
1. skip when ``event.key`` is in ``delivered/<user>.json`` on the hub (or the local
   ``delivered.json`` in the data folder when no hub) - "nothing is sent twice";
2. append to ``alerts.jsonl`` (the app's alert list) and the user's pulse;
3. for ``notify.mentions``: an inbox entry (kind "mention") per expanded login;
4. for ``notify.cliq_dm`` / ``cliq_channel``: ``lan.cliq.CliqClient`` (queued for retry when down);
5. record the key (``delivered/<user>.json`` keeps the newest 2,000 keys).
The toast itself is raised by the caller on the GUI thread from the returned flag.

``Dispatcher.notify_people`` is the sender's side of a person-to-person note (task
assigned, task done, mention in a publish): inbox entries plus a Cliq DM to the
people who linked Cliq.  ``Dispatcher.receive`` is the recipient's side: an inbox
entry is toasted once (ledger key ``inbox:<id>``) on whichever PC sees it first.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.jsonio import append_jsonl, read_json, read_jsonl, write_json_atomic

log = logging.getLogger(__name__)

LEDGER_MAX = 2000
ALERTS_KEPT = 500


@dataclass
class Delivery:
    new: bool                       # False when already delivered (no toast)
    inboxes: list[str] = field(default_factory=list)
    cliq_sent: bool = False
    cliq_queued: bool = False


class DeliveredLedger:
    """``{"keys": {event_key: ts}}``; one writer (its user).  Cached by file mtime."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._keys: dict[str, str] | None = None
        self._mtime = -1.0
        self._lock = threading.Lock()

    def _load(self) -> dict[str, str]:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if self._keys is None or mtime != self._mtime:
            d = read_json(self.path, {}) or {}
            raw = d.get("keys", {}) if isinstance(d, dict) else {}
            self._keys = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
            self._mtime = mtime
        return self._keys

    def seen(self, key: str) -> bool:
        with self._lock:
            return key in self._load()

    def add(self, key: str) -> None:
        self.add_many([key])

    def add_many(self, keys: list[str]) -> None:
        with self._lock:
            self._keys = None                 # re-read: my other PC may have written meanwhile
            cur = dict(self._load())
            now = M.now_iso()
            for k in keys:
                cur[k] = now
            if len(cur) > LEDGER_MAX:
                cur = dict(sorted(cur.items(), key=lambda kv: kv[1])[-LEDGER_MAX:])
            write_json_atomic(self.path, {"schema": 1, "keys": cur}, indent=0)
            self._keys, self._mtime = None, -1.0


def ledger_path(hub_root: Path | None, user: str, data_dir: Path) -> Path:
    """``<hub>/delivered/<user>.json`` with a hub, else ``<data>/delivered.json``."""
    if hub_root:
        return Path(hub_root) / "delivered" / f"{user}.json"
    return Path(data_dir) / "delivered.json"


class Dispatcher:
    def __init__(self, hub: Any, ledger: DeliveredLedger, cliq: Any | None, alerts_path: Path,
                 my_cliq_id: str = "", cliq_enabled: bool = True):
        self.hub = hub
        self.ledger = ledger
        self.cliq = cliq
        self.alerts_path = Path(alerts_path)
        self.my_cliq_id = my_cliq_id
        self.cliq_enabled = cliq_enabled
        self._lock = threading.Lock()

    # ------------------------------------------------------------- alerts
    def deliver(self, event: M.WatchEvent, notify: M.Notify) -> Delivery:
        if self.ledger.seen(event.key):
            return Delivery(False)
        out = Delivery(True)
        row = event.to_dict()
        row["read"] = False
        with self._lock:
            append_jsonl(self.alerts_path, row)
        hub = self.hub
        if hub is not None and getattr(hub, "configured", False):
            try:
                hub.pulse(event.event, event.title, kind="watch", mentions=notify.mentions)
            except Exception:  # noqa: BLE001
                log.debug("pulse failed", exc_info=True)
            if notify.mentions:
                text = event.title + (f" - {event.detail}" if event.detail else "")
                out.inboxes = self._inboxes(notify.mentions, text, event.link)
        text = self._cliq_text(event.title, event.detail, event.link)
        if self._cliq_ready():
            ids: list[str] = []
            if notify.cliq_dm:
                if self.my_cliq_id:
                    ids.append(self.my_cliq_id)
                if out.inboxes and hub is not None:
                    ids += [i for i in hub.cliq_ids_for(out.inboxes).values() if i not in ids]
            for kind, target in (("dm", ids), ("channel", notify.cliq_channel)):
                if not target:
                    continue
                res = self.cliq.send(kind, target, text)  # type: ignore[union-attr]
                out.cliq_sent = out.cliq_sent or res.ok
                out.cliq_queued = out.cliq_queued or (not res.ok and res.retry)
        self.ledger.add(event.key)
        return out

    def _inboxes(self, targets: list[str], text: str, link: str) -> list[str]:
        try:
            logins = self.hub.expand_targets(targets)
            written = [lg for lg in logins if self.hub.send_mention([lg], text, link)]
            return written
        except Exception:  # noqa: BLE001
            log.warning("mention inbox write failed", exc_info=True)
            return []

    def _cliq_ready(self) -> bool:
        return bool(self.cliq_enabled and self.cliq is not None and getattr(self.cliq, "configured", False))

    @staticmethod
    def _cliq_text(title: str, detail: str, link: str) -> str:
        return "\n".join(x for x in (title, detail, link) if x)

    # --------------------------------------------- person-to-person notes
    def notify_people(self, logins: list[str], text: str, link: str = "", kind: str = "mention",
                      task_id: str = "", title: str = "", cliq: bool = True, inbox: bool = True) -> Delivery:
        """Sender side: inbox entries for ``logins`` (already expanded) and one Cliq DM to those linked.

        ``inbox=False`` when the caller already wrote the entries (publish "for") and only the DM is missing."""
        out = Delivery(True)
        hub = self.hub
        if hub is None or not getattr(hub, "configured", False) or not logins:
            return out
        for lg in logins:
            if not inbox or hub.send_mention([lg], text, link, kind=kind, task_id=task_id, title=title):
                out.inboxes.append(lg)
        if cliq and self._cliq_ready() and out.inboxes:
            ids = list(hub.cliq_ids_for(out.inboxes).values())
            if ids:
                res = self.cliq.send("dm", ids, self._cliq_text(title or text, text if title else "", link))  # type: ignore[union-attr]
                out.cliq_sent, out.cliq_queued = res.ok, (not res.ok and res.retry)
        return out

    def receive(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Recipient side: the inbox entries not yet toasted anywhere; they are recorded as delivered."""
        fresh = [e for e in entries if not self.ledger.seen(f"inbox:{e.get('id', '')}")]
        if fresh:
            self.ledger.add_many([f"inbox:{e.get('id', '')}" for e in fresh])
        return fresh

    # --------------------------------------------------------- alert list
    def alerts(self, limit: int = 200) -> list[dict[str, Any]]:
        """Newest first; ``read`` merged from later ``{"read_key": ...}`` rows."""
        rows = read_jsonl(self.alerts_path)
        read = {str(r["read_key"]) for r in rows if r.get("read_key")}
        out = [r for r in rows if r.get("key")]
        for r in out:
            if r["key"] in read:
                r["read"] = True
        out.reverse()
        return out[:limit]

    def mark_read(self, key: str) -> None:
        with self._lock:
            append_jsonl(self.alerts_path, {"read_key": key, "ts": M.now_iso()})
            self._compact()

    def _compact(self) -> None:
        rows = read_jsonl(self.alerts_path)
        if len(rows) <= ALERTS_KEPT * 2:
            return
        read = {str(r["read_key"]) for r in rows if r.get("read_key")}
        keep = [r for r in rows if r.get("key")][-ALERTS_KEPT:]
        for r in keep:
            if r["key"] in read:
                r["read"] = True
        tmp = self.alerts_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(self.alerts_path)


def make_dispatcher(hub: Any, settings: Any, data_dir: Path, user: str, dry_run_cliq: bool = False) -> Dispatcher:
    """The dispatcher for the current settings (hub, Cliq token, my Cliq id)."""
    from project_opener.lan.cliq import CliqClient
    root = hub.root if hub is not None and getattr(hub, "configured", False) else None
    ledger = DeliveredLedger(ledger_path(root, user, data_dir))
    cliq = CliqClient(settings.cliq_api_base, settings.cliq_bot, settings.cliq_token,
                      Path(data_dir) / C.CLIQ_OUTBOX_FILE, dry_run=dry_run_cliq)
    return Dispatcher(hub, ledger, cliq, Path(data_dir) / C.ALERTS_FILE,
                      my_cliq_id=settings.cliq_user_id if settings.notify_cliq_default else "",
                      cliq_enabled=True)
