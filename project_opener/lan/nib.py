"""Nib, Dexterity Connect's office companion, as Project Opener's messenger and leave source.

Connect's contract for office tools is its ``docs/TOOL-NOTICES.md``: one integration token per tool,
notices through Nib, and (when an administrator allows it) who is on leave.

Nothing to set up per person.  An administrator, once for the office:

1. in Dexterity Connect, Control room > Integrations: creates the integration ``Project Opener``,
   presses **Copy settings** and ticks **Reads leave** on its row;
2. saves the copied block as ``connect.json`` in the Team Hub folder::

       {"connect": {"enabled": true, "hub": "dexhub:47900", "fingerprint": "AB:CD:...", "token": "dxc_..."}}

   (the flat form ``{"hub", "fingerprint", "token"}`` is read too).

Every Project Opener reads it from there.  The token only posts notices under this tool's name and
reads leave dates and covers; Connect audits it and the administrator can revoke it at any time.

* ``notify(to, title, text, link, key, ...)``: ``POST /api/bot/notify``; the people (Windows sign-ins)
  are told in their conversation with Nib, under "Project Opener", with a ``projectopener://`` link;
  ``space`` also posts in a Connect Space.  ``key`` makes a retry harmless: the hub delivers each key to
  each person once.  The answer says who is on leave (``away``).
* ``send(...)`` queues a notice that got no answer, 429, 5xx or "failed" in an outbox
  (``nib-outbox.jsonl``), retried by ``flush_outbox`` (the same pattern as ``lan.cliq``).
* ``hello()``: the Test button (``GET /api/bot/hello``).
* ``leave(account)``: that member's leave from today on; ``leave_changes(since)``: who changed since.

The hub is trusted by its certificate's SHA-256 fingerprint, never by a certificate authority, and a
request (and so the token) is never sent before the certificate matches.  Standard library only.
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
DEFAULT_PORT = 47900
TIMEOUT_S = 10
OUTBOX_MAX = 500
MAX_ATTEMPTS = 50
MAX_RECIPIENTS = 50              # the hub's limit for one notice
REACH_TTL_S = 60                 # how long a reachability answer is trusted
KINDS = ("task", "mention", "alert", "reminder", "review", "update")

# (method, path, body) -> (status, payload); raises OSError when the hub cannot be reached
Transport = Callable[[str, str, "dict[str, Any] | None"], "tuple[int, Any]"]


@dataclass
class NibConfig:
    hub: str
    fingerprint: str
    token: str

    @property
    def complete(self) -> bool:
        return bool(self.hub and self.fingerprint and self.token)


def normalise_fingerprint(fp: str) -> str:
    """"AB:CD:..." (as Connect shows it) or plain hex -> 64 lowercase hex digits ("" when it is not one)."""
    hexes = "".join(c for c in (fp or "").lower() if c in "0123456789abcdef")
    return hexes if len(hexes) == 64 else ""


def normalise_hub(text: str) -> str:
    """``https://host:47900`` from ``host``, ``host:port`` or ``https://host:port``; "" otherwise (never http)."""
    raw = (text or "").strip().rstrip("/")
    if not raw or any(ch.isspace() for ch in raw):
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return ""
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query:
        return ""
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"https://{host}:{port or DEFAULT_PORT}"


def load_config(hub_root: Path | str | None) -> NibConfig | None:
    """``connect.json`` from the Team Hub folder, or None when it is missing, off or incomplete."""
    if not hub_root:
        return None
    d = read_json(Path(hub_root) / CONFIG_FILE, None)
    if isinstance(d, dict) and isinstance(d.get("connect"), dict):
        d = d["connect"]
    if not isinstance(d, dict):
        return None
    if d.get("enabled") is False:
        return None
    cfg = NibConfig(normalise_hub(str(d.get("hub") or "")), normalise_fingerprint(str(d.get("fingerprint") or "")),
                    str(d.get("token") or "").strip())
    if not (cfg.complete and cfg.token.startswith("dxc_")):
        log.warning("%s on the Team Hub is incomplete; Nib is off", CONFIG_FILE)
        return None
    return cfg


def login_of(account: str) -> str:
    """``DEX\\ravi`` -> ``ravi`` (Project Opener's logins are Windows sign-ins without the domain)."""
    return (account or "").rsplit("\\", 1)[-1].strip()


def notice_key(*parts: str) -> str:
    """A stable key (up to 160 characters) for the same thing happening, never for the time it was sent."""
    return "po:" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:40]


class CertificateMismatch(OSError):
    """The hub's certificate is not the one in ``connect.json``: nothing was sent."""


@dataclass
class NibResult:
    ok: bool
    status: int = 0
    message: str = ""
    retry: bool = False          # transient (unreachable, 429, 5xx, "failed"): worth queueing
    delivered: list[str] = field(default_factory=list)      # sign-ins told now or before (duplicates)
    unknown: list[str] = field(default_factory=list)
    away: dict[str, dict[str, str]] = field(default_factory=dict)  # login -> {"back", "cover"}

    def __bool__(self) -> bool:
        return self.ok


def pinned_transport(cfg: NibConfig, timeout: float = TIMEOUT_S) -> Transport:
    """HTTPS to the hub, trusting only the certificate with ``cfg.fingerprint``."""
    parts = urlsplit(cfg.hub)
    host, port = parts.hostname or "", parts.port or DEFAULT_PORT

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
            headers = {"Authorization": f"Bearer {cfg.token}", "Accept": "application/json"}
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


def make_notice(to: list[str] | None = None, title: str = "", text: str = "", link: str = "", key: str = "",
                kind: str = "", sender: str = "", space: str = "", lines: list[str] | None = None) -> dict[str, Any]:
    """The body of ``POST /api/bot/notify`` (only the fields that are set)."""
    n: dict[str, Any] = {}
    people = [t.strip().lstrip("@") for t in (to or []) if t and t.strip()]
    if people:
        n["to"] = people[:MAX_RECIPIENTS]
    if space.strip():
        n["space"] = space.strip().lstrip("#")
    if key:
        n["key"] = key[:160]
    if kind in KINDS:
        n["kind"] = kind
    if sender:
        n["from"] = sender
    if title:
        n["title"] = title[:200]
    if text:
        n["text"] = text[:2000]
    if lines:
        n["lines"] = [str(x)[:300] for x in lines[:8]]
    if link:
        n["link"] = {"title": "Open in Project Opener", "url": link}
    return n


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
            return NibResult(False, 0, "Connect is not set up on the Team Hub"), None
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
        if status == 401:
            msg = "Connect refused the token. Ask an administrator for the integration's settings again."
        transient = status == 429 or status >= 500
        return NibResult(ok, status, msg, transient), payload

    def reachable(self) -> bool:
        """The hub answered lately (probed with ``/api/bot/hello`` when the last answer is old)."""
        if not self.configured:
            return False
        if self.dry_run:
            return True
        if self._reach and time.monotonic() - self._reach[0] < REACH_TTL_S:
            return self._reach[1]
        self._request("GET", "/api/bot/hello")
        return bool(self._reach and self._reach[1])

    def hello(self) -> NibResult:
        res, payload = self._request("GET", "/api/bot/hello")
        if res.ok and isinstance(payload, dict):
            name = str((payload.get("integration") or {}).get("name") or "")
            res.message = f"Connected as {name}" if name else "Connected"
        return res

    # -------------------------------------------------------------- notices
    def notify(self, notice: dict[str, Any]) -> NibResult:
        """One notice; ``failed`` results make it worth sending again (same key: no repeats)."""
        if not notice.get("to") and not notice.get("space"):
            return NibResult(False, 0, "nobody to tell")
        res, payload = self._request("POST", "/api/bot/notify", notice)
        if not isinstance(payload, dict):
            return res
        for r in payload.get("results") or []:
            if not isinstance(r, dict):
                continue
            who = str(r.get("to") or "")
            status = r.get("status")
            if status in ("delivered", "duplicate"):
                res.delivered.append(who)
            elif status == "unknown":
                res.unknown.append(who)
            elif status == "failed":
                res.retry = True
            away = r.get("away")
            if isinstance(away, dict) and who and not who.startswith("space:"):
                res.away[login_of(who)] = {"back": str(away.get("back") or ""),
                                           "cover": login_of(str(away.get("cover") or ""))}
        return res

    def send(self, notice: dict[str, Any]) -> NibResult:
        """``notify``; a notice that did not get through now waits in the outbox (with its key)."""
        if "key" not in notice:
            notice = {**notice, "key": notice_key(json.dumps(notice, sort_keys=True), M.now_iso())}
        res = self.notify(notice)
        if res.retry:
            self.queue(notice)
        return res

    # ----------------------------------------------------------------- leave
    def leave(self, account: str) -> list[dict[str, Any]] | None:
        """That member's leave from today on (``[]`` when none); None when the hub could not say."""
        res, payload = self._request("GET", f"/api/bot/leave?account={quote(account, safe='')}")
        if res.status == 404:
            return []
        if not res.ok or not isinstance(payload, dict):
            return None
        rows = payload.get("leave")
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else None

    def leave_changes(self, since: int) -> tuple[int, list[str]] | None:
        """(cursor, accounts changed since ``since``); None when the hub could not say (or may not)."""
        res, payload = self._request("GET", f"/api/bot/leave/changes?since={int(since)}")
        if not res.ok or not isinstance(payload, dict):
            return None
        return int(payload.get("cursor") or 0), [str(a) for a in payload.get("accounts") or []]

    # ---------------------------------------------------------------- outbox
    def queue(self, notice: dict[str, Any]) -> None:
        row = {"notice": notice, "queued_at": M.now_iso(), "attempts": 0}
        with self._lock:
            rows = [r for r in read_jsonl(self.outbox) if (r.get("notice") or {}).get("key") != notice.get("key")]
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
        """Retry queued notices; returns how many went out."""
        if not self.configured:
            return 0
        with self._lock:
            rows = read_jsonl(self.outbox)
            if not rows:
                return 0
            keep: list[dict[str, Any]] = []
            sent = 0
            waiting = False
            for r in rows:
                notice = r.get("notice")
                if not isinstance(notice, dict):
                    continue
                if waiting:                  # the hub is away or asked us to wait: do not hammer it
                    keep.append(r)
                    continue
                res = self.notify(notice)
                if res.ok and not res.retry:
                    sent += 1
                    continue
                if res.retry:
                    r["attempts"] = int(r.get("attempts", 0) or 0) + 1
                    if r["attempts"] < MAX_ATTEMPTS:
                        keep.append(r)
                    if res.status in (0, 429):
                        waiting = True
                else:
                    log.warning("dropping a queued Nib notice (%s)", res.message)
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
