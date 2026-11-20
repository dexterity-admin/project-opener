"""Dexterity Connect notices: Project Opener tells people through Nib.

The office's messenger, Dexterity Connect, lets an office tool tell a person something with one
request and an integration token (Connect's ``docs/TOOL-NOTICES.md`` is the contract).  The notice
arrives in the person's conversation with Nib, the office's companion, under this tool's name, with
a ``projectopener://`` link back here.  People are addressed by their Windows sign-in, the same
login the Team Hub uses, so nobody links an account.

One integration for the office: an administrator creates it in Connect (Control room >
Integrations > Create token) and pastes the settings it shows into Settings > Connect and mail.
The token is kept with DPAPI (``Settings.connect_token``).  The client:

* ``hello()``: is the hub there, is the token good (the Test button);
* ``notify(notice)``: one notice for people (``to``: Windows sign-ins) and/or a Space;
* ``send(notice)``: the same, and a notice that could not be delivered now waits in the outbox
  (``data_dir()/connect-outbox.jsonl``), retried every ``CONNECT_RETRY_S``; the toast never waits
  for Connect;
* every notice carries a ``key``, so a retry after a lost answer is never shown twice (the hub
  delivers a key once per person).

The hub has its own certificate: it is trusted by its SHA-256 fingerprint, checked on the open
connection before the token is sent.  A hub from before tool notices answers 404 to
``/api/bot/notify``; the same words then go to ``/api/bot/message`` (a Direct message from the
integration) until the hub is updated.

Standard library only (``http.client``, ``ssl``), timeouts of 10 s, no retries inline.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from project_opener.core import models as M
from project_opener.core.jsonio import read_json, read_jsonl, write_json_atomic

log = logging.getLogger(__name__)

TIMEOUT_S = 10
DEFAULT_PORT = 47900
OUTBOX_MAX = 500           # oldest queued notices are dropped beyond this
MAX_ATTEMPTS = 50          # ~4 days at one retry every 5 minutes
MAX_RECIPIENTS = 50        # the hub's limit for one notice
LEGACY_RECHECK_S = 1800    # an older hub is asked for /api/bot/notify again after this long
TOOL_NAME = "Project Opener"


def normalize_fingerprint(text: str) -> str:
    """64 lower-case hex digits from ``AA:BB:…`` (colons and spaces are fine); "" when it is not one."""
    fp = "".join(ch for ch in (text or "") if ch not in ": \t\r\n-").lower()
    return fp if len(fp) == 64 and all(ch in "0123456789abcdef" for ch in fp) else ""


def normalize_hub(text: str) -> str:
    """``https://host:47900`` from ``host``, ``host:port`` or a full address; "" when it is not one."""
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
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.path not in ("", "/") or parts.query:
        return ""
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{parts.scheme}://{host}:{port or DEFAULT_PORT}"


def parse_settings(text: str) -> dict[str, str]:
    """What Connect's **Copy settings** gives: ``{"connect": {"hub", "fingerprint", "token"}}``.

    Returns ``{"hub", "fingerprint", "token"}`` with what was found ("" for the rest); ``{}`` when
    the text is not that block.  A bare token (``dxc_…``) is accepted as ``{"token": …}``."""
    raw = (text or "").strip()
    if raw.startswith("dxc_") and not any(ch.isspace() for ch in raw):
        return {"hub": "", "fingerprint": "", "token": raw}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("connect"), dict):
        data = data["connect"]
    if not isinstance(data, dict) or not any(k in data for k in ("hub", "token", "fingerprint")):
        return {}
    return {"hub": normalize_hub(str(data.get("hub") or "")),
            "fingerprint": normalize_fingerprint(str(data.get("fingerprint") or "")),
            "token": str(data.get("token") or "").strip()}


# ------------------------------------------------------- the office's settings
OFFICE_FILE = "connect.json"       # in the Team Hub folder: set once, every PC picks it up


def office_settings(hub_root: Path | str | None) -> dict[str, str]:
    """The Connect settings someone shared with the office through the Team Hub; ``{}`` when none."""
    if not hub_root:
        return {}
    data = read_json(Path(hub_root) / OFFICE_FILE, {}) or {}
    if not isinstance(data, dict):
        return {}
    got = {"hub": normalize_hub(str(data.get("hub") or "")),
           "fingerprint": normalize_fingerprint(str(data.get("fingerprint") or "")),
           "token": str(data.get("token") or "").strip()}
    return got if got["hub"] and got["token"] else {}


def share_office_settings(hub_root: Path | str | None, hub: str, fingerprint: str, token: str, by: str = "") -> bool:
    """Write them to the Team Hub so no other PC has to be set up.  Anyone who can open the Team Hub
    folder can read the file: the token only posts notices under this tool's name, and an
    administrator can revoke it in Connect."""
    if not hub_root or not (normalize_hub(hub) and token.strip()):
        return False
    try:
        write_json_atomic(Path(hub_root) / OFFICE_FILE, {
            "schema": 1, "hub": normalize_hub(hub), "fingerprint": normalize_fingerprint(fingerprint),
            "token": token.strip(), "shared_by": by, "shared_at": M.now_iso()})
        return True
    except OSError as exc:
        log.warning("could not share the Connect settings: %s", exc)
        return False


def unshare_office_settings(hub_root: Path | str | None) -> bool:
    if not hub_root:
        return False
    try:
        (Path(hub_root) / OFFICE_FILE).unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError as exc:
        log.warning("could not remove the shared Connect settings: %s", exc)
        return False


def effective_settings(settings: Any, hub_root: Path | str | None) -> dict[str, str]:
    """What this PC uses: its own settings when it has them, else the office's from the Team Hub.
    ``source`` is "pc", "office" or "" (not set up)."""
    hub, token = normalize_hub(getattr(settings, "connect_hub", "")), getattr(settings, "connect_token", "")
    if hub and token:
        return {"hub": hub, "fingerprint": normalize_fingerprint(getattr(settings, "connect_fingerprint", "")),
                "token": token, "source": "pc"}
    office = office_settings(hub_root)
    return {**office, "source": "office"} if office else {"hub": "", "fingerprint": "", "token": "", "source": ""}


@dataclass
class ConnectResult:
    ok: bool
    status: int = 0
    message: str = ""
    retry: bool = False        # a transient failure (network, 429, 5xx): worth queueing
    retry_after: int = 0       # seconds the hub asked us to wait (429)
    delivered: list[str] = field(default_factory=list)     # recipients as we wrote them
    unknown: list[str] = field(default_factory=list)       # not known to Connect: never retried
    away: dict[str, dict[str, Any]] = field(default_factory=dict)   # recipient -> {"back", "cover"}
    via: str = ""              # "nib" | "integration" | "message" (an older hub) | "dry run"
    info: dict[str, Any] = field(default_factory=dict)     # hello(): the hub's answer

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class _Sent:
    method: str
    path: str
    body: dict[str, Any] = field(default_factory=dict)


def make_notice(to: list[str] | None = None, *, title: str = "", text: str = "", link: str = "",
                link_title: str = "Open in Project Opener", kind: str = "", sender: str = "",
                space: str = "", lines: list[str] | None = None, key: str = "") -> dict[str, Any]:
    """A notice as the hub takes it.  Without ``key`` one is made now, once, so every retry of
    this notice carries the same one."""
    n: dict[str, Any] = {"key": (key or f"po:{M.new_id()}")[:160]}
    people: list[str] = []                      # each person once, however the login was typed
    for x in to or []:
        name = str(x).strip()
        if name and name.lower() not in {p.lower() for p in people}:
            people.append(name)
    if people:
        n["to"] = people
    if space.strip().lstrip("#"):
        n["space"] = space.strip().lstrip("#")
    if title.strip():
        n["title"] = title.strip()[:200]
    if text.strip():
        n["text"] = text.strip()[:2000]
    if lines:
        n["lines"] = [str(x)[:300] for x in lines if str(x).strip()][:8]
    if link.strip():
        n["link"] = {"title": link_title, "url": link.strip()}
    if kind:
        n["kind"] = kind
    if sender.strip():
        n["from"] = sender.strip()
    return n


def _as_message(notice: dict[str, Any]) -> dict[str, Any]:
    """The same words for ``/api/bot/message`` (a hub from before tool notices)."""
    parts: list[str] = []
    if notice.get("title"):
        parts.append(f"**{notice['title']}**")
    if notice.get("text"):
        parts.append(str(notice["text"]))
    parts += [f"- {x}" for x in notice.get("lines", [])]
    link = notice.get("link") or {}
    if link.get("url"):
        parts.append(f"[{link.get('title') or 'Open'}]({link['url']})")
    body: dict[str, Any] = {"text": "\n".join(parts)}
    if notice.get("to"):
        body["to"] = list(notice["to"])
    if notice.get("space"):
        body["space"] = notice["space"]
    return body


class ConnectClient:
    def __init__(self, hub: str, token: str, fingerprint: str, outbox: Path, *, dry_run: bool = False,
                 timeout: float = TIMEOUT_S):
        self.hub = normalize_hub(hub)
        self.token = (token or "").strip()
        self.fingerprint = normalize_fingerprint(fingerprint)
        self.outbox = Path(outbox)
        self.dry_run = dry_run
        self.timeout = timeout
        self.sent: list[_Sent] = []          # dry-run record
        self._lock = threading.Lock()
        self._legacy_until = 0.0             # an older hub: use /api/bot/message until then

    @property
    def configured(self) -> bool:
        """A hub and a token, and for an https hub the fingerprint that proves it is ours."""
        return bool(self.hub and self.token and (self.fingerprint or self.hub.startswith("http://")))

    # ---------------------------------------------------------------- http
    def _connection(self) -> http.client.HTTPConnection:
        parts = urlsplit(self.hub)
        host, port = parts.hostname or "", parts.port or DEFAULT_PORT
        if parts.scheme == "http":           # a test hub on this PC; the real hub only speaks https
            return http.client.HTTPConnection(host, port, timeout=self.timeout)
        # the hub's certificate is its own (no authority signs it): it is trusted by fingerprint,
        # compared below on the open connection, before anything is sent
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(host, port, timeout=self.timeout, context=ctx)
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True) if conn.sock else None  # type: ignore[union-attr]
        if not der or hashlib.sha256(der).hexdigest() != self.fingerprint:
            conn.close()
            raise _WrongHub
        return conn

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[ConnectResult, Any]:
        if self.dry_run:
            self.sent.append(_Sent(method, path, dict(body or {})))
            log.info("connect dry run: %s %s %s", method, path, json.dumps(body or {}, ensure_ascii=False)[:300])
            return ConnectResult(True, 200, "dry run", via="dry run"), {}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        conn: http.client.HTTPConnection | None = None
        try:
            conn = self._connection()
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read(1_000_000)
            status = resp.status
            retry_after = resp.getheader("Retry-After") or ""
        except _WrongHub:
            # never retried: the token must not go to a hub we cannot recognise
            return ConnectResult(False, 0, "The hub's certificate does not match the fingerprint in Settings. "
                                           "Paste the settings from Connect again."), None
        except (OSError, http.client.HTTPException) as exc:      # refused, timed out, reset, bad TLS
            return ConnectResult(False, 0, f"Connect is not reachable: {exc}", True), None
        finally:
            if conn is not None:
                conn.close()
        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError:
                payload = None
        if 200 <= status < 300:
            return ConnectResult(True, status, "sent"), payload if isinstance(payload, dict) else {}
        said = str(payload.get("error") or "") if isinstance(payload, dict) else ""
        if status == 401:
            said = "Connect refused the token. Ask an administrator for the integration's settings again."
        elif status == 403:
            said = said or "Connect takes notices on the office network only."
        transient = status in (408, 429) or status >= 500
        wait = int(retry_after) if retry_after.isdigit() else 0
        return ConnectResult(False, status, said or f"Connect answered {status}", transient, wait), payload

    # -------------------------------------------------------------- public
    def hello(self) -> ConnectResult:
        """Is the hub there and the token good?  ``info`` holds the hub's answer."""
        if not self.configured:
            return ConnectResult(False, 0, self.why_not())
        res, payload = self._request("GET", "/api/bot/hello")
        if res.ok and isinstance(payload, dict):
            res.info = payload
            hub = (payload.get("hub") or {}).get("name") or "the hub"
            name = (payload.get("integration") or {}).get("name") or TOOL_NAME
            via = (payload.get("notices") or {}).get("via")
            res.via = str(via or "")
            res.message = f"Connected to {hub} as {name}." + (
                "" if via != "integration" else " Notices arrive as its own messages, not through Nib.")
        elif res.status == 404:
            # a hub from before tool notices: the token cannot be checked without posting
            res = ConnectResult(True, 404, "Connected to an older hub: notices arrive as messages from "
                                           "the integration until the hub is updated.", via="message")
        return res

    def why_not(self) -> str:
        if not self.hub:
            return "Connect is not set up: paste the settings from Connect first."
        if not self.token:
            return "No token yet: paste the settings from Connect."
        return "The hub's fingerprint is missing: paste the settings from Connect again."

    def notify(self, notice: dict[str, Any]) -> ConnectResult:
        """One request; nothing is queued.  ``send`` is what the app uses."""
        if not self.configured:
            return ConnectResult(False, 0, self.why_not())
        to = [str(x) for x in notice.get("to", [])]
        if not to and not notice.get("space"):
            return ConnectResult(False, 0, "nobody to tell")
        if len(to) > MAX_RECIPIENTS:         # the hub takes 50 at a time: the rest in further requests, same key
            out = ConnectResult(True, 200, "sent")
            for i in range(0, len(to), MAX_RECIPIENTS):
                part = dict(notice, to=to[i:i + MAX_RECIPIENTS])
                if i:
                    part.pop("space", None)
                res = self.notify(part)
                if not res.ok and (res.retry or not out.delivered):
                    res.delivered = out.delivered + res.delivered
                    return res
                out.delivered += res.delivered
                out.unknown += res.unknown
                out.away.update(res.away)
                out.via = out.via or res.via
            return out
        if time.monotonic() < self._legacy_until:
            return self._message(notice)
        res, payload = self._request("POST", "/api/bot/notify", notice)
        if res.status == 404 and not isinstance(payload, dict):
            return ConnectResult(False, 404, "Nothing answers at that address like a Connect hub.")
        if res.status == 404 and "results" not in payload:
            self._legacy_until = time.monotonic() + LEGACY_RECHECK_S
            return self._message(notice)
        if not res.ok or self.dry_run:
            if self.dry_run:
                res.delivered = to + ([f"space:{notice['space']}"] if notice.get("space") else [])
            return res
        results = payload.get("results") if isinstance(payload, dict) else None
        failed = False
        for r in results if isinstance(results, list) else []:
            if not isinstance(r, dict):
                continue
            who, status = str(r.get("to", "")), r.get("status")
            if status in ("delivered", "duplicate"):
                res.delivered.append(who)
                res.via = res.via or str(r.get("via") or "")
                if isinstance(r.get("away"), dict):
                    res.away[who] = dict(r["away"])
            elif status == "unknown":
                res.unknown.append(who)
            elif status == "failed":
                failed = True
        if failed:
            # the hub could not write some of them: the same request again reaches only those
            # (the others answer "duplicate"), so it is worth queueing as a whole
            res.ok, res.retry, res.message = bool(res.delivered), True, "Connect could not deliver to everyone yet"
        elif not res.delivered:
            res.ok = False
            res.message = "Connect does not know " + ", ".join(res.unknown) if res.unknown else "nothing was delivered"
        return res

    def _message(self, notice: dict[str, Any]) -> ConnectResult:
        res, payload = self._request("POST", "/api/bot/message", _as_message(notice))
        res.via = "message"
        if isinstance(payload, dict):
            res.unknown = [str(x) for x in payload.get("unknown", []) if isinstance(x, str)]
            wanted = [str(x) for x in notice.get("to", [])] + (
                [f"space:{notice['space']}"] if notice.get("space") else [])
            res.delivered = [w for w in wanted if w not in res.unknown] if res.ok else []
        if res.status == 404 and res.unknown:          # the old API's "nobody was known": not worth a retry
            res.message = "Connect does not know " + ", ".join(res.unknown)
        return res

    def send(self, notice: dict[str, Any]) -> ConnectResult:
        """``notify``; a transient failure is queued for ``flush_outbox``."""
        res = self.notify(notice)
        if res.retry:
            self.queue(notice)
        return res

    # -------------------------------------------------------------- outbox
    def queue(self, notice: dict[str, Any]) -> None:
        row = {"id": M.new_id(), "notice": notice, "queued_at": M.now_iso(), "attempts": 0}
        with self._lock:
            rows = [r for r in read_jsonl(self.outbox)
                    if (r.get("notice") or {}).get("key") != notice.get("key")
                    or (r.get("notice") or {}).get("to") != notice.get("to")]
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
                    continue                 # not ours to send: dropped
                if waiting:                  # Connect is away or asked us to wait: do not hammer it with the rest
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
                    log.warning("dropping a queued Connect notice (%s)", res.message)
            self._write_outbox(keep)
            return sent


class _WrongHub(Exception):
    """The certificate on the connection is not the hub's."""
