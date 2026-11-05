"""Single-instance IPC (builder 3): protocol, add batching, a real socket round trip, CLI arguments."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication

from project_opener import ipc


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def test_encode_decode_round_trip():
    cmds = [{"cmd": "add", "paths": [r"Z:\P12513\ISO\a b.pdf", "D:\\x"]}, {"cmd": "snapshot"},
            {"cmd": "open", "link": "projectopener://activity/Lot%207"}]
    data = b"".join(ipc.encode(c) for c in cmds)
    out = ipc.decode(data)
    assert [c["cmd"] for c in out] == ["add", "snapshot", "open"]
    assert out[0]["paths"] == [r"Z:\P12513\ISO\a b.pdf", "D:\\x"] and out[0]["v"] == 2


def test_decode_protocol_1_and_junk():
    data = b'show\nprojectopener://open/P12513\n{bad json\n{"cmd": "rm -rf"}\nhello\n'
    assert ipc.decode(data) == [{"v": 1, "cmd": "show"},
                                {"v": 1, "cmd": "open", "link": "projectopener://open/P12513"}]


def test_links():
    assert ipc.parse_link("projectopener://activity/Lot%207") == ("activity", "Lot 7")
    assert ipc.parse_link("PROJECTOPENER://task/abc/") == ("task", "abc")
    assert ipc.parse_link("http://x") == ("", "")
    assert ipc.parse_link(ipc.make_link("activity", "P12513 · Lot/7")) == ("activity", "P12513 · Lot/7")


def test_merge_batched():
    cmds = [{"cmd": "add", "paths": [r"Z:\a.pdf"]}, {"cmd": "add", "paths": [r"z:\A.PDF", r"Z:\b.pdf"]},
            {"cmd": "sendto", "paths": [r"Z:\c"]}, {"cmd": "snapshot"}, {"cmd": "add", "paths": []}]
    assert ipc.merge_batched(cmds) == [{"v": 2, "cmd": "add", "paths": [r"Z:\a.pdf", r"Z:\b.pdf"]},
                                       {"v": 2, "cmd": "sendto", "paths": [r"Z:\c"]}]


def _pump(until, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        QCoreApplication.processEvents()
        time.sleep(0.01)


def test_server_batches_adds_and_passes_others_at_once(qapp):
    srv = ipc.InstanceServer("test-unused-key", batch_ms=80)
    got = []
    srv.command.connect(got.append)
    for p in ("a", "b", "c"):
        srv.receive({"cmd": "add", "paths": [p]})
    srv.receive({"cmd": "show"})
    assert got == [{"cmd": "show"}]
    _pump(lambda: len(got) == 2)
    assert got[1] == {"v": 2, "cmd": "add", "paths": ["a", "b", "c"]}
    srv.close()


def test_socket_round_trip(qapp):
    """A second process forwards two Explorer adds and a snapshot; the running instance gets one add.

    Cross-process on purpose: a client in the server's own thread blocks the only event loop that
    could read the pipe, which never happens in the app (its own CLI commands skip the socket).
    """
    import subprocess
    import sys
    key = f"DexterityDesign.ProjectOpener.test-{os.getpid()}"
    srv = ipc.InstanceServer(key, batch_ms=400)
    assert srv.listen()
    got = []
    srv.command.connect(got.append)
    code = ("from PySide6.QtCore import QCoreApplication; a = QCoreApplication([]); from project_opener import ipc; "
            f"ok1 = ipc.forward({key!r}, [{{'cmd': 'add', 'paths': ['Z:/one.pdf']}}], 2000); "
            f"ok2 = ipc.forward({key!r}, [{{'cmd': 'add', 'paths': ['Z:/two.pdf']}}, {{'cmd': 'snapshot'}}], 2000); "
            "print(ok1, ok2)")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=root, stdout=subprocess.PIPE, text=True,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    try:
        _pump(lambda: proc.poll() is not None, timeout=30)
        _pump(lambda: any(c["cmd"] == "add" for c in got), timeout=3)
    finally:
        srv.close()
    assert proc.stdout.read().split() == ["True", "True"]
    assert {"v": 2, "cmd": "snapshot"} in got
    adds = [c for c in got if c["cmd"] == "add"]
    assert adds == [{"v": 2, "cmd": "add", "paths": ["Z:/one.pdf", "Z:/two.pdf"]}]
    assert ipc.forward(key, [{"cmd": "show"}], timeout_ms=100) is False      # nobody listens now


def test_claim_instance_is_exclusive():
    key = f"DexterityDesign.ProjectOpener.claimtest-{os.getpid()}"
    assert ipc.claim_instance(key) is True
    assert ipc.claim_instance(key) is False


def test_cli_arguments_from_the_real_parser(monkeypatch):
    """What the Explorer verb, Send to and the hotkey-less flags put on the command line, parsed by
    ``app.main``'s own parser, becomes the right IPC commands."""
    import project_opener.app_v4 as app_v4
    from project_opener import app
    seen = {}

    def fake_v4(args):
        seen["args"] = args
        return 0
    monkeypatch.setattr(app_v4, "main", fake_v4)

    def cmds(*argv):
        monkeypatch.setattr("sys.argv", ["ProjectOpener.exe", *argv])
        assert app.main() == 0
        return ipc.commands_from_args(seen["args"])

    assert cmds("--add", r"Z:\P12513\ISO\a b.pdf") == [{"cmd": "add", "paths": [r"Z:\P12513\ISO\a b.pdf"]}]
    assert cmds("--v4", "--sendto", r"Z:\a", r"Z:\b c") == [{"cmd": "sendto", "paths": [r"Z:\a", r"Z:\b c"]}]
    assert [c["cmd"] for c in cmds("--snapshot")] == ["snapshot"]
    assert [c["cmd"] for c in cmds("--start-from-open")] == ["start-from-open"]
    assert cmds("--v4", "projectopener://activity/Lot%207") == [
        {"cmd": "open", "link": "projectopener://activity/Lot%207"}]
