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

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from project_opener import constants as C

log = logging.getLogger(__name__)

COMMANDS = ("show", "open", "add", "sendto", "snapshot", "start-from-open")
LINK_KINDS = ("open", "activity", "task")
BATCHED = ("add", "sendto")
ADD_BATCH_MS = 500          # an Explorer verb on N selected files starts N processes; one command for them
ADD_BATCH_MAX_MS = 3000     # never hold a batch longer than this


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


_MUTEXES: list[int] = []


def claim_instance(key: str) -> bool:
    """True when this process is the first to start on ``key`` (a named mutex held until exit).

    An Explorer verb on several files with no instance running starts several processes at once;
    only the one that claims the mutex starts the app, the others ``forward_retry`` to it.
    """
    import sys
    if sys.platform != "win32":
        return True
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    handle = k32.CreateMutexW(None, False, "Local\\" + key + ".instance")
    if not handle:
        return True
    if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS
        k32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _MUTEXES.append(handle)
    return True


def forward_retry(key: str, cmds: list[dict[str, Any]], total_ms: int = 8000, step_ms: int = 250) -> bool:
    """``forward`` until the starting instance listens (or ``total_ms`` passes)."""
    import time
    end = time.monotonic() + total_ms / 1000
    while True:
        if forward(key, cmds):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(step_ms / 1000)


def merge_batched(cmds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``add``/``sendto`` commands -> one command per kind (first-seen order), paths in arrival order,
    duplicates (case-insensitive, as Windows paths are) dropped."""
    out: dict[str, dict[str, Any]] = {}
    seen: dict[str, set[str]] = {}
    for c in cmds:
        name = c.get("cmd")
        if name not in BATCHED:
            continue
        merged = out.setdefault(name, {"v": C.IPC_PROTOCOL, "cmd": name, "paths": []})
        keys = seen.setdefault(name, set())
        for path in c.get("paths") or []:
            k = str(path).lower()
            if k not in keys:
                keys.add(k)
                merged["paths"].append(str(path))
    return [m for m in out.values() if m["paths"]]


class InstanceServer(QObject):
    """Listens on ``key``; emits ``command(dict)`` on the GUI thread for each decoded command.

    ``add`` and ``sendto`` are held for ``batch_ms`` after the last one arrived (at most
    ``ADD_BATCH_MAX_MS``) and emitted as one command each, so a multi-file Explorer verb gives one
    toast / one chooser.  Every other command is emitted at once.
    """

    command = Signal(dict)

    def __init__(self, key: str, parent: QObject | None = None, batch_ms: int = ADD_BATCH_MS):
        super().__init__(parent)
        self.key = key
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        self._batch: list[dict[str, Any]] = []
        self._batch_started = 0.0
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.setInterval(batch_ms)
        self._batch_timer.timeout.connect(self.flush)

    def receive(self, cmd: dict[str, Any]) -> None:
        """One decoded command (from a connection, or from a test)."""
        if cmd.get("cmd") not in BATCHED:
            self.command.emit(cmd)
            return
        import time
        now = time.monotonic()
        if not self._batch:
            self._batch_started = now
        self._batch.append(cmd)
        if (now - self._batch_started) * 1000 >= ADD_BATCH_MAX_MS:
            self.flush()
        else:
            self._batch_timer.start()

    def flush(self) -> None:
        self._batch_timer.stop()
        batch, self._batch = self._batch, []
        for merged in merge_batched(batch):
            self.command.emit(merged)

    def listen(self) -> bool:
        QLocalServer.removeServer(self.key)
        ok = self._server.listen(self.key)
        if not ok:
            log.warning("ipc: cannot listen on %s: %s", self.key, self._server.errorString())
        return ok

    def close(self) -> None:
        self.flush()
        self._server.close()

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            if conn is not None:
                self._serve(conn)

    def _serve(self, conn: QLocalSocket) -> None:
        """Read the whole message, then decode it once the client hangs up.

        A forwarding client writes and disconnects at once, so by the time the event loop hands
        the connection over it may already be closed: read what is buffered and finish right away
        rather than waiting for a ``disconnected`` that has already happened.
        """
        buf = bytearray()
        finished = False

        def read() -> None:
            buf.extend(bytes(conn.readAll()))

        def done() -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            read()
            for cmd in decode(bytes(buf)):
                self.receive(cmd)
            conn.deleteLater()

        conn.readyRead.connect(read)
        conn.disconnected.connect(done)
        read()
        if conn.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            done()
