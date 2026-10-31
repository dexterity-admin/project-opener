"""UDP presence beacon.

Broadcasts a tiny JSON datagram every few seconds and listens for everyone
else's.  This gives sub-minute "who's online" without touching the hub share.
The Windows firewall may block inbound datagrams for per-user installs, which
is why the hub heartbeat remains the source of truth and this is an optional
accelerator that the user can switch off.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections.abc import Callable

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.lan.hub import Peer

log = logging.getLogger(__name__)
MAGIC = "PO3"


class PresenceBeacon:
    def __init__(self, user: str | None = None, display_name: str = "", port: int = C.PRESENCE_PORT,
                 on_peer: Callable[[Peer], None] | None = None):
        self.user = user or M.current_user()
        self.display_name = display_name
        self.host = M.current_host()
        self.port = port
        self.on_peer = on_peer
        self.current_project = ""
        self.peers: dict[str, Peer] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._sock_rx: socket.socket | None = None

    # ------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        try:
            rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rx.settimeout(1.0)
            rx.bind(("", self.port))
            self._sock_rx = rx
        except OSError as exc:
            log.info("presence listener unavailable: %s", exc)
            self._sock_rx = None
        self._stop.clear()
        t_tx = threading.Thread(target=self._tx_loop, name="po-presence-tx", daemon=True)
        t_tx.start()
        self._threads = [t_tx]
        if self._sock_rx:
            t_rx = threading.Thread(target=self._rx_loop, name="po-presence-rx", daemon=True)
            t_rx.start()
            self._threads.append(t_rx)
        return True

    def stop(self) -> None:
        self._stop.set()
        self._send(status="offline")
        for t in self._threads:
            t.join(timeout=2)
        if self._sock_rx:
            try:
                self._sock_rx.close()
            except OSError:
                pass

    # ------------------------------------------------------------- transmit
    def _payload(self, status: str = "online") -> bytes:
        return json.dumps({
            "m": MAGIC, "u": self.user, "n": self.display_name, "h": self.host, "v": C.VERSION,
            "p": self.current_project, "s": status, "t": time.time(),
        }).encode("utf-8")

    def _send(self, status: str = "online") -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
                tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                tx.sendto(self._payload(status), ("255.255.255.255", self.port))
        except OSError as exc:
            log.debug("presence send failed: %s", exc)

    def _tx_loop(self) -> None:
        while not self._stop.is_set():
            self._send()
            self._stop.wait(C.PRESENCE_INTERVAL_S)

    # -------------------------------------------------------------- receive
    def _rx_loop(self) -> None:
        assert self._sock_rx is not None
        while not self._stop.is_set():
            try:
                data, addr = self._sock_rx.recvfrom(2048)
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                d = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("m") != MAGIC or not d.get("u"):
                continue
            user = str(d["u"])
            if user == self.user and str(d.get("h", "")) == self.host:
                continue
            peer = Peer(user=user, display_name=str(d.get("n", "")), host=str(d.get("h", "")),
                        version=str(d.get("v", "")), ts=time.time() if d.get("s") != "offline" else 0,
                        current_project=str(d.get("p", "")), status=str(d.get("s", "")), source="udp")
            self.peers[user] = peer
            if self.on_peer:
                try:
                    self.on_peer(peer)
                except Exception:  # pragma: no cover
                    log.exception("on_peer failed")

    def online(self) -> list[Peer]:
        now = time.time()
        return [p for p in self.peers.values() if now - p.ts < C.PRESENCE_STALE_S]
