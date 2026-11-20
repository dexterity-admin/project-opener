"""Alert delivery, exactly once (brief section 3.4).  Owner: builder 1 (CORE+HUB).

``Dispatcher.deliver(event, notify)``:
1. skip when ``event.key`` is in ``delivered/<user>.json`` on the hub (or the local
   ``delivered.json`` in the data folder when no hub) - "nothing is sent twice";
2. append to ``alerts.jsonl`` (the app's alert list) and the user's pulse;
3. for ``notify.mentions``: an inbox entry (kind "mention") per expanded login;
4. for ``notify.connect_dm`` / ``connect_space``: a notice through Dexterity Connect
   (``lan.connect_bot.ConnectClient``; it arrives in the person's conversation with Nib and is
   queued for retry when the hub is away);
5. record the key (``delivered/<user>.json`` keeps the newest 2,000 keys).
The toast itself is raised by the caller on the GUI thread from the returned flag.

``Dispatcher.notify_people`` is the sender's side of a person-to-person note (task
assigned, task done, mention in a publish): inbox entries plus one Connect notice to
those people (all but the ones who turned "Tell me in Connect" off).  ``Dispatcher.receive`` is the recipient's side: an inbox
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
from project_opener.lan.connect_bot import ConnectClient, effective_settings, make_notice

log = logging.getLogger(__name__)

LEDGER_MAX = 2000
ALERTS_KEPT = 500


@dataclass
class Delivery:
    new: bool                       # False when already delivered (no toast)
    inboxes: list[str] = field(default_factory=list)
    connect_sent: bool = False
    connect_queued: bool = False
    unknown: list[str] = field(default_factory=list)     # logins Connect does not know
    away: dict[str, dict[str, Any]] = field(default_factory=dict)   # login -> {"back", "cover"} (on leave)


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
    def __init__(self, hub: Any, ledger: DeliveredLedger, connect: Any | None, alerts_path: Path,
                 me: str = "", notify_me: bool = True, connect_enabled: bool = True):
        self.hub = hub
        self.ledger = ledger
        self.connect = connect
        self.alerts_path = Path(alerts_path)
        self.me = me                      # my Windows sign-in: how Connect knows me
        self.notify_me = notify_me        # Settings > "Tell me in Connect"
        self.connect_enabled = connect_enabled
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
        if self._connect_ready():
            to: list[str] = []
            if notify.connect_dm:
                if self.me and self.notify_me:
                    to.append(self.me)
                if out.inboxes and hub is not None:
                    to += [lg for lg in hub.connect_logins_for(out.inboxes) if lg.lower() not in {t.lower() for t in to}]
            if to or notify.connect_space:
                # the event's own key: my other PC seeing the same hit, or a retry, is never shown twice
                self._send(out, make_notice(to, title=event.title, text=event.detail, link=event.link, kind="alert",
                                            space=notify.connect_space, key=f"po:watch:{event.key}"))
        self.ledger.add(event.key)
        return out

    def _send(self, out: Delivery, notice: dict[str, Any]) -> None:
        """One notice to Connect; a failure never stops the alert (the toast and inbox are already done)."""
        try:
            res = self.connect.send(notice)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            log.warning("Connect notice failed", exc_info=True)
            return
        out.connect_sent = out.connect_sent or bool(res.ok)
        out.connect_queued = out.connect_queued or bool(res.retry)
        out.unknown += [u for u in res.unknown if u not in out.unknown]
        out.away.update(res.away)
        if res.unknown:
            log.info("Connect does not know: %s", ", ".join(res.unknown))
        if not res.ok and not res.retry:
            log.warning("Connect notice not sent: %s", res.message)

    def _inboxes(self, targets: list[str], text: str, link: str) -> list[str]:
        try:
            logins = self.hub.expand_targets(targets)
            written = [lg for lg in logins if self.hub.send_mention([lg], text, link)]
            return written
        except Exception:  # noqa: BLE001
            log.warning("mention inbox write failed", exc_info=True)
            return []

    def _connect_ready(self) -> bool:
        return bool(self.connect_enabled and self.connect is not None and getattr(self.connect, "configured", False))

    # --------------------------------------------- person-to-person notes
    def notify_people(self, logins: list[str], text: str, link: str = "", kind: str = "mention",
                      task_id: str = "", title: str = "", connect: bool = True, inbox: bool = True) -> Delivery:
        """Sender side: inbox entries for ``logins`` (already expanded) and one Connect notice to them.

        ``inbox=False`` when the caller already wrote the entries (publish "for") and only the notice is
        missing.  ``Delivery.away`` names the people Connect says are on leave (and who covers)."""
        out = Delivery(True)
        hub = self.hub
        if hub is None or not getattr(hub, "configured", False) or not logins:
            return out
        for lg in logins:
            if not inbox or hub.send_mention([lg], text, link, kind=kind, task_id=task_id, title=title):
                out.inboxes.append(lg)
        if connect and self._connect_ready() and out.inboxes:
            to = hub.connect_logins_for(out.inboxes)
            if to:
                self._send(out, make_notice(to, title=title or text, text=text if title else "", link=link,
                                            kind={"task": "task", "mention": "mention"}.get(kind, "update"),
                                            sender=self.me))
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


def make_dispatcher(hub: Any, settings: Any, data_dir: Path, user: str, dry_run_connect: bool = False) -> Dispatcher:
    """The dispatcher for the current settings (Team Hub, the Connect hub and token, "Tell me in Connect")."""
    root = hub.root if hub is not None and getattr(hub, "configured", False) else None
    ledger = DeliveredLedger(ledger_path(root, user, data_dir))
    cs = effective_settings(settings, root)      # this PC's own, else the office's from the Team Hub
    connect = ConnectClient(cs["hub"], cs["token"], cs["fingerprint"],
                            Path(data_dir) / C.CONNECT_OUTBOX_FILE, dry_run=dry_run_connect)
    return Dispatcher(hub, ledger, connect, Path(data_dir) / C.ALERTS_FILE, me=user,
                      notify_me=bool(settings.notify_connect))
