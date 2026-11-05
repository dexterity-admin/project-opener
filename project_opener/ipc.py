"""Single-instance messaging for the v4 app (docs/V4-ARCHITECTURE.md section 8).

A second ``ProjectOpener.exe`` (an Explorer verb, Send to, a deep link, a
second start) forwards what it was asked to do to the running instance over a
``QLocalSocket`` and exits.  Protocol 2: one JSON object per line, UTF-8::

    {"v": 2, "cmd": "show"}
    {"v": 2, "cmd": "open", "link": "projectopener://activity/<id-or-name>"}
    {"v": 2, "cmd": "add", "paths": ["Z:\\\\P12513\\\\ISO\\\\a.pdf", ...]}     Explorer "Add to running activity"
    {"v": 2, "cmd": "sendto", "paths": [...]}                                Send to > Project Opener
    {"v": 2, "cmd": "snapshot"}                                              --snapshot
    {"v": 2, "cmd": "start-from-open"}                                       --start-from-open

Protocol 1 (3.x) lines are still understood: a bare ``show`` and bare
``projectopener://...`` links.

Deep links: ``projectopener://open/<project id or name>`` (3.x, a project),
``projectopener://activity/<id or name>``, ``projectopener://task/<id>``.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import unquote

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from project_opener import constants as C

log = logging.getLogger(__name__)

COMMANDS = ("show", "open", "add", "sendto", "snapshot", "start-from-open")
LINK_KINDS = ("open", "activity", "task")


def parse_link(text: str) -> tuple[str, str]:
    """``projectopener://activity/Lot%207`` -> ("activity", "Lot 7"); ("", "") when not a link.

    ``open`` is the 3.x project link and stays a project link.
    """
    text = (text or "").strip()
    prefix = f"{C.URI_SCHEME}://"
    if not text.lower().startswith(prefix):
        return "", ""
    rest = text[len(prefix):]
    kind, _, key = rest.partition("/")
    kind = kind.lower()
    if kind not in LINK_KINDS:
        return "", ""
    return kind, unquote(key.strip("/"))


def make_link(kind: str, key: str) -> str:
    from urllib.parse import quote
    return f"{C.URI_SCHEME}://{kind}/{quote(key, safe='')}"


def encode(cmd: dict[str, Any]) -> bytes:
    msg = {"v": C.IPC_PROTOCOL, **cmd}
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def decode(data: bytes) -> list[dict[str, Any]]:
    """Every command in a received buffer; unknown lines are dropped (and logged)."""
    out: list[dict[str, Any]] = []
    for line in data.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                log.warning("ipc: bad line %r", line[:200])
                continue
            if isinstance(msg, dict) and msg.get("cmd") in COMMANDS:
                if "paths" in msg:
                    msg["paths"] = [str(p) for p in msg.get("paths") or [] if str(p).strip()]
                out.append(msg)
            continue
        if line == "show":                      # protocol 1
            out.append({"v": 1, "cmd": "show"})
        elif parse_link(line)[0]:
            out.append({"v": 1, "cmd": "open", "link": line})
    return out


def commands_from_args(args: Any) -> list[dict[str, Any]]:
    """The commands an argparse namespace from ``app.main`` asks for, in a stable order."""
    cmds: list[dict[str, Any]] = []
    if getattr(args, "add", None):
        cmds.append({"cmd": "add", "paths": list(args.add)})
    if getattr(args, "sendto", None):
        cmds.append({"cmd": "sendto", "paths": list(args.sendto)})
    if getattr(args, "snapshot", False):
        cmds.append({"cmd": "snapshot"})
    if getattr(args, "start_from_open", False):
        cmds.append({"cmd": "start-from-open"})
    target = getattr(args, "target", None)
    if target and parse_link(target)[0]:
        cmds.append({"cmd": "open", "link": target})
    return cmds


def forward(key: str, cmds: list[dict[str, Any]], timeout_ms: int = 300) -> bool:
    """Send ``cmds`` (preceded by "show" unless the commands are silent) to a running instance.

    Returns False when no instance listens on ``key``.  ``add``, ``snapshot`` and
    ``start-from-open`` do not raise the main window by themselves; the running
    instance decides (the chooser, the pill's "Saved" flash).
    """
    sock = QLocalSocket()
    sock.connectToServer(key)
    if not sock.waitForConnected(timeout_ms):
        return False
    payload = b"".join(encode(c) for c in (cmds or [{"cmd": "show"}]))
    sock.write(payload)
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Listens on ``key``; emits ``command(dict)`` on the GUI thread for each decoded command."""

    command = Signal(dict)

    def __init__(self, key: str, parent: QObject | None = None):
        super().__init__(parent)
        self.key = key
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        QLocalServer.removeServer(self.key)
        ok = self._server.listen(self.key)
        if not ok:
            log.warning("ipc: cannot listen on %s: %s", self.key, self._server.errorString())
        return ok

    def close(self) -> None:
        self._server.close()

    def _on_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        buf = bytearray()

        def read() -> None:
            buf.extend(bytes(conn.readAll()))

        def done() -> None:
            read()
            for cmd in decode(bytes(buf)):
                self.command.emit(cmd)
            conn.deleteLater()

        conn.readyRead.connect(read)
        conn.disconnected.connect(done)
