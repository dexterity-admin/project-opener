"""Nib, Dexterity Connect's office companion, as Project Opener's messenger and leave source.

Nothing to set up per person.  An administrator makes one Nib key for Project Opener in Dexterity
Connect (Control room > Integrations > Nib for office tools) and saves it with the hub's address and
certificate fingerprint in the Team Hub folder as ``connect.json``::

    {"hub": "https://dexhub:47900", "fingerprint": "AB:CD:...", "nib_key": "nibt_..."}

Every Project Opener in the office reads it from there.  The key can only have Nib write to a member
and read members' leave (dates and cover); the hub audits every message and the administrator can
revoke it at any time.

* ``message(to, text, title, link, msg_id)``: Nib writes to those members (Windows sign-ins) in their
  conversation with Nib, with a ``projectopener://`` link card.  ``msg_id`` makes a retry harmless:
  the hub sends each id to each person once.
* ``send(...)`` queues a transient failure in an outbox (``nib-outbox.jsonl``) retried by
  ``flush_outbox`` (the same pattern as ``lan.cliq``).
* ``leave(account)``: that member's leave from today on; ``leave_changes(since)``: who changed since.

The hub is trusted by its certificate's SHA-256 fingerprint, never by a certificate authority, and a
request is never sent before the certificate matches.  Standard library only.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from project_opener.core import models as M
from project_opener.core.jsonio import read_json, read_jsonl

log = logging.getLogger(__name__)

CONFIG_FILE = "connect.json"     # in the Team Hub root
OUTBOX_FILE = "nib-outbox.jsonl"
TIMEOUT_S = 10
OUTBOX_MAX = 500
MAX_ATTEMPTS = 50
REACH_TTL_S = 60                 # how long a reachability answer is trusted

# (method, path, body) -> (status, payload); raises OSError when the hub cannot be reached
Transport = Callable[[str, str, "dict[str, Any] | None"], "tuple[int, Any]"]


@dataclass
class NibConfig:
    hub: str
    fingerprint: str
    key: str

    @property
    def complete(self) -> bool:
        return bool(self.hub and self.fingerprint and self.key)


def normalise_fingerprint(fp: str) -> str:
    """"AB:CD:..." (as Connect shows it) or plain hex -> lowercase hex."""
    return "".join(c for c in (fp or "").lower() if c in "0123456789abcdef")


def load_config(hub_root: Path | str | None) -> NibConfig | None:
    """``connect.json`` from the Team Hub folder, or None when it is missing or incomplete."""
    if not hub_root:
        return None
    d = read_json(Path(hub_root) / CONFIG_FILE, None)
    if not isinstance(d, dict):
        return None
    cfg = NibConfig(str(d.get("hub") or "").strip().rstrip("/"), normalise_fingerprint(str(d.get("fingerprint") or "")),
                    str(d.get("nib_key") or "").strip())
    if not (cfg.complete and cfg.hub.lower().startswith("https://") and len(cfg.fingerprint) == 64
            and cfg.key.startswith("nibt_")):
        log.warning("%s on the Team Hub is incomplete; Nib is off", CONFIG_FILE)
        return None
    return cfg


def login_of(account: str) -> str:
    """``DEX\\ravi`` -> ``ravi`` (Project Opener's logins are Windows sign-ins without the domain)."""
    return (account or "").rsplit("\\", 1)[-1].strip()


def message_id(*parts: str) -> str:
    """A stable id the hub accepts (``[A-Za-z0-9._:-]{1,64}``) for the same message."""
    return "po-" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:40]


class CertificateMismatch(OSError):
    """The hub's certificate is not the one in ``connect.json``: nothing was sent."""


@dataclass
class NibResult:
    ok: bool
    status: int = 0
    message: str = ""
    retry: bool = False          # transient (unreachable, 429, 5xx): worth queueing
    delivered: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def pinned_transport(cfg: NibConfig, timeout: float = TIMEOUT_S) -> Transport:
    """HTTPS to the hub, trusting only the certificate with ``cfg.fingerprint``."""
    parts = urlsplit(cfg.hub)
    host, port = parts.hostname or "", parts.port or 47900

    def call(method: str, path: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE          # trust is the fingerprint check below, before any request
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
        try:
            conn.connect()
            der = conn.sock.getpeercert(binary_form=True) if conn.sock else None  # type: ignore[union-attr]
            if not der or hashlib.sha256(der).hexdigest() != cfg.fingerprint:
                raise CertificateMismatch("the hub's certificate does not match connect.json")
            data = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {"Authorization": f"Bearer {cfg.key}", "Accept": "application/json"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                payload = {}
            return resp.status, payload
        finally:
            conn.close()

    return call


class NibClient:
    def __init__(self, cfg: NibConfig | None, outbox: Path, *, transport: Transport | None = None,
                 dry_run: bool = False):
        self.cfg = cfg
        self.outbox = Path(outbox)
        self.dry_run = dry_run
        self.sent: list[dict[str, Any]] = []          # dry-run record
        self._transport = transport or (pinned_transport(cfg) if cfg else None)
        self._lock = threading.Lock()
        self._reach: tuple[float, bool] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.cfg and self.cfg.complete and self._transport)

    # ---------------------------------------------------------------- http
    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[NibResult, Any]:
        if not self.configured:
            return NibResult(False, 0, "Nib is not set up on the Team Hub"), None
        if self.dry_run:
            self.sent.append({"method": method, "path": path, "body": dict(body or {})})
            log.info("nib dry run: %s %s %s", method, path, json.dumps(body or {}, ensure_ascii=False)[:300])
            return NibResult(True, 200, "dry run", delivered=list((body or {}).get("to") or [])), {}
        try:
            status, payload = self._transport(method, path, body)  # type: ignore[misc]
        except CertificateMismatch as exc:
            log.warning("Nib: %s", exc)
            self._reach = (time.monotonic(), False)
            return NibResult(False, 0, f"Dexterity Connect's hub is not the one the office set up ({exc})", True), None
        except (OSError, http.client.HTTPException) as exc:
            self._reach = (time.monotonic(), False)
            return NibResult(False, 0, f"Dexterity Connect's hub is not reachable: {exc}", True), None
        self._reach = (time.monotonic(), True)
        payload = payload if isinstance(payload, dict) else {}
        ok = 200 <= status < 300 and payload.get("ok", True) is not False
        msg = "sent" if ok else str(payload.get("error") or f"the hub answered {status}")
        transient = status in (429, 503) or status >= 500
        return NibResult(ok, status, msg, transient, [str(x) for x in payload.get("delivered") or []]), payload

    def reachable(self) -> bool:
        """The hub answered lately (probed with a cheap read when the last answer is old)."""
        if not self.configured:
            return False
        if self.dry_run:
            return True
        if self._reach and time.monotonic() - self._reach[0] < REACH_TTL_S:
            return self._reach[1]
        self._request("GET", "/api/nib/leave/changes")
        return bool(self._reach and self._reach[1])

    # -------------------------------------------------------------- messages
    def message(self, to: list[str], text: str, title: str = "", link: str = "", msg_id: str = "") -> NibResult:
        logins = [t.strip() for t in to if t and t.strip()]
        if not logins:
            return NibResult(False, 0, "nobody to message")
        body: dict[str, Any] = {"id": msg_id or message_id(",".join(logins), text, title, link), "to": logins,
                                "text": text}
        if title or link:
            body["card"] = {"title": title or "Open in Project Opener", "url": link} if link else {"title": title}
        res, _ = self._request("POST", "/api/nib/message", body)
        return res

    def send(self, to: list[str], text: str, title: str = "", link: str = "", msg_id: str = "") -> NibResult:
        """``message``; a transient failure is queued (with its id) for ``flush_outbox``."""
        mid = msg_id or message_id(",".join(to), text, title, link, M.now_iso())
        res = self.message(to, text, title, link, mid)
        if not res.ok and res.retry:
            self.queue(to, text, title, link, mid)
        return res

    # ----------------------------------------------------------------- leave
    def leave(self, account: str) -> list[dict[str, Any]] | None:
        """That member's leave from today on (``[]`` when none); None when the hub could not say."""
        res, payload = self._request("GET", f"/api/nib/leave?account={quote(account, safe='')}")
        if res.status == 404:
            return []
        if not res.ok or not isinstance(payload, dict):
            return None
        rows = payload.get("leave")
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else None

    def leave_changes(self, since: int) -> tuple[int, list[str]] | None:
        """(cursor, accounts changed since ``since``); None when the hub could not say."""
        res, payload = self._request("GET", f"/api/nib/leave/changes?since={int(since)}")
        if not res.ok or not isinstance(payload, dict):
            return None
        return int(payload.get("cursor") or 0), [str(a) for a in payload.get("accounts") or []]

    # ---------------------------------------------------------------- outbox
    def queue(self, to: list[str], text: str, title: str, link: str, msg_id: str) -> None:
        row = {"id": msg_id, "to": list(to), "text": text, "title": title, "link": link,
               "queued_at": M.now_iso(), "attempts": 0}
        with self._lock:
            rows = [r for r in read_jsonl(self.outbox) if r.get("id") != msg_id]
            rows.append(row)
            self._write_outbox(rows[-OUTBOX_MAX:])

    def pending(self) -> int:
        return len(read_jsonl(self.outbox))

    def _write_outbox(self, rows: list[dict[str, Any]]) -> None:
        self.outbox.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            try:
                self.outbox.unlink()
            except FileNotFoundError:
                pass
            return
        tmp = self.outbox.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(self.outbox)

    def flush_outbox(self) -> int:
        """Retry queued messages; returns how many went out."""
        if not self.configured:
            return 0
        with self._lock:
            rows = read_jsonl(self.outbox)
            if not rows:
                return 0
            keep: list[dict[str, Any]] = []
            sent = 0
            reachable = True
            for r in rows:
                if not reachable:
                    keep.append(r)
                    continue
                res = self.message([str(x) for x in r.get("to") or []], str(r.get("text", "")),
                                   str(r.get("title", "")), str(r.get("link", "")), str(r.get("id", "")))
                if res.ok:
                    sent += 1
                    continue
                if res.retry:
                    r["attempts"] = int(r.get("attempts", 0) or 0) + 1
                    if r["attempts"] < MAX_ATTEMPTS:
                        keep.append(r)
                    if res.status == 0:
                        reachable = False
                else:
                    log.warning("dropping queued Nib message (%s)", res.message)
            self._write_outbox(keep)
            return sent


def make_client(hub_root: Path | str | None, data_dir: Path, dry_run: bool = False) -> NibClient:
    return NibClient(load_config(hub_root), Path(data_dir) / OUTBOX_FILE, dry_run=dry_run)


class LeaveWatch:
    """One member's leave from Nib, read again only when the hub's change cursor names them or the day turns."""

    def __init__(self, client: NibClient, account: str):
        self.client = client
        self.account = account
        self._cursor = 0
        self._rows: list[dict[str, Any]] | None = None
        self._day = ""

    def read(self, today: str) -> list[dict[str, Any]] | None:
        """The leave rows (``[]`` when none); None when the hub did not answer (then nothing is concluded)."""
        if not self.client.configured:
            return None
        changes = self.client.leave_changes(self._cursor)
        if changes is None:
            return None
        cursor, accounts = changes
        me = login_of(self.account).lower()
        if self._rows is None or today != self._day or any(login_of(a).lower() == me for a in accounts):
            rows = self.client.leave(self.account)
            if rows is None:
                return None
            self._rows, self._day = rows, today
        self._cursor = cursor
        return self._rows
