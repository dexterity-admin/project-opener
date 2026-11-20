"""Nib (Dexterity Connect's companion) as Project Opener's messenger and leave source.

The hub is faked at the transport (``NibClient(transport=...)``) and, for the certificate check, at
``http.client.HTTPSConnection``; Handover runs on two fake PCs sharing a temp hub folder (as in test_v4_team) with
Nib's leave fed through a fake ``LeaveWatch``.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from project_opener.core import models as M
from project_opener.core.tasks import TaskStore
from project_opener.lan import nib as N
from project_opener.lan.delivery import DeliveredLedger, Dispatcher

FP = "AB:" * 31 + "AB"
KEY = "nibt_abc"


def write_config(root, **over):
    cfg = {"hub": "https://dexhub:47900", "fingerprint": FP, "nib_key": KEY, **over}
    (root / N.CONFIG_FILE).write_text(json.dumps(cfg), encoding="utf-8")


class FakeHub:
    """The hub's Nib routes, recording each request; ``down`` makes it unreachable."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.down = False
        self.status = 200
        self.leave: list[dict] = []
        self.cursor = 0
        self.changed: list[str] = []

    def __call__(self, method, path, body):
        if self.down:
            raise OSError("connection refused")
        self.calls.append((method, path, body))
        if path.startswith("/api/nib/message"):
            if self.status != 200:
                return self.status, {"ok": False, "error": "nope"}
            return 200, {"ok": True, "delivered": [f"dex\\{t}" for t in body["to"]], "unknown": [], "failed": []}
        if path.startswith("/api/nib/leave/changes"):
            return 200, {"ok": True, "cursor": self.cursor, "accounts": list(self.changed)}
        if path.startswith("/api/nib/leave"):
            return 200, {"ok": True, "today": "2026-11-19", "leave": self.leave}
        return 404, {"ok": False}


def client(tmp_path, hub=None):
    return N.NibClient(N.NibConfig("https://dexhub:47900", N.normalise_fingerprint(FP), KEY),
                       tmp_path / N.OUTBOX_FILE, transport=hub or FakeHub())


# ------------------------------------------------------------------ config
def test_config_comes_from_the_team_hub_and_must_be_complete(tmp_path):
    assert N.load_config(None) is None and N.load_config(tmp_path) is None
    write_config(tmp_path)
    cfg = N.load_config(tmp_path)
    assert cfg is not None and cfg.fingerprint == "ab" * 32 and cfg.key == KEY
    write_config(tmp_path, hub="http://dexhub:47900")              # never without TLS
    assert N.load_config(tmp_path) is None
    write_config(tmp_path, fingerprint="")                         # never without a pinned certificate
    assert N.load_config(tmp_path) is None
    write_config(tmp_path, nib_key="dxc_bot_token")                # an ordinary integration token is not a Nib key
    assert N.load_config(tmp_path) is None


def test_login_and_message_ids():
    assert N.login_of("DEX\\ravi") == "ravi" and N.login_of("ravi") == "ravi"
    a = N.message_id("watch", "k1")
    assert a == N.message_id("watch", "k1") != N.message_id("watch", "k2")
    assert len(a) <= 64 and all(c.isalnum() or c in "._:-" for c in a)


# ---------------------------------------------------------------- messages
def test_message_carries_an_id_and_a_link_card(tmp_path):
    hub = FakeHub()
    res = client(tmp_path, hub).message(["priya"], "Vikram mentioned you", "Open P-12 routing",
                                        "projectopener://activity/a1", "po-1")
    assert res.ok and res.delivered == ["dex\\priya"]
    method, path, body = hub.calls[0]
    assert (method, path) == ("POST", "/api/nib/message")
    assert body == {"id": "po-1", "to": ["priya"], "text": "Vikram mentioned you",
                    "card": {"title": "Open P-12 routing", "url": "projectopener://activity/a1"}}


def test_unreachable_hub_queues_and_the_retry_keeps_the_id(tmp_path):
    hub = FakeHub()
    c = client(tmp_path, hub)
    hub.down = True
    res = c.send(["priya"], "Task for you", "Open task", "projectopener://task/t1", "po-t1")
    assert not res.ok and res.retry and c.pending() == 1
    assert c.flush_outbox() == 0 and c.pending() == 1           # still down: kept
    hub.down = False
    assert c.flush_outbox() == 1 and c.pending() == 0
    assert hub.calls[-1][2]["id"] == "po-t1"                    # the hub sends each id once per person


def test_refused_message_is_dropped_not_retried(tmp_path):
    hub = FakeHub()
    c = client(tmp_path, hub)
    hub.down = True
    c.send(["priya"], "x", msg_id="po-x")
    hub.down, hub.status = False, 403                           # the key lost the scope: do not keep asking
    assert c.flush_outbox() == 0 and c.pending() == 0


def test_unconfigured_client_sends_nothing(tmp_path):
    c = N.NibClient(None, tmp_path / N.OUTBOX_FILE)
    assert not c.configured and not c.reachable()
    assert not c.message(["priya"], "x").ok and c.pending() == 0


# ------------------------------------------------------- certificate pinning
class FakeSock:
    def __init__(self, der):
        self.der = der

    def getpeercert(self, binary_form=False):
        return self.der


class FakeConn:
    requests: list = []
    der = b""

    def __init__(self, host, port, timeout=None, context=None):
        self.sock = None

    def connect(self):
        self.sock = FakeSock(FakeConn.der)

    def request(self, method, path, body=None, headers=None):
        FakeConn.requests.append((method, path, headers))

    def getresponse(self):
        class R:
            status = 200

            def read(self):
                return b'{"ok": true, "cursor": 3, "accounts": []}'
        return R()

    def close(self):
        pass


def test_the_hub_is_trusted_only_by_its_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(N.http.client, "HTTPSConnection", FakeConn)
    der = b"the hub's certificate"
    cfg = N.NibConfig("https://dexhub:47900", hashlib.sha256(der).hexdigest(), KEY)
    FakeConn.requests = []
    FakeConn.der = b"someone else's certificate"
    c = N.NibClient(cfg, tmp_path / N.OUTBOX_FILE)
    assert c.leave_changes(0) is None
    assert FakeConn.requests == []                              # nothing sent, not even the key
    FakeConn.der = der
    assert c.leave_changes(0) == (3, [])
    assert FakeConn.requests[0][2]["Authorization"] == f"Bearer {KEY}"


# -------------------------------------------------------------- leave watch
def test_leave_watch_reads_again_only_when_named_or_the_day_turns(tmp_path):
    hub = FakeHub()
    hub.leave = [{"id": "L1", "from": "2026-11-23", "to": "2026-11-27", "half": None, "current": False,
                  "cover": {"account": "dex\\yokesh", "name": "Yokesh"}}]
    w = N.LeaveWatch(client(tmp_path, hub), "vikram")
    assert w.read("2026-11-19")[0]["id"] == "L1"
    reads = lambda: sum(1 for c in hub.calls if c[1].startswith("/api/nib/leave?"))  # noqa: E731
    assert reads() == 1
    w.read("2026-11-19")
    assert reads() == 1                                         # nothing changed: no read
    hub.cursor, hub.changed = 4, ["dex\\priya"]
    w.read("2026-11-19")
    assert reads() == 1                                         # someone else's leave
    hub.cursor, hub.changed = 5, ["DEX\\Vikram"]
    w.read("2026-11-19")
    assert reads() == 2                                         # mine
    hub.changed = []
    w.read("2026-11-20")
    assert reads() == 3                                         # a new day: "current" may have changed
    hub.down = True
    assert w.read("2026-11-20") is None                         # no answer: nothing concluded


# ------------------------------------------------------------------ delivery
class FakeNib:
    configured = True

    def __init__(self, reachable=True):
        self._reachable = reachable
        self.sent: list[tuple] = []

    def reachable(self):
        return self._reachable

    def send(self, to, text, title="", link="", msg_id=""):
        self.sent.append((list(to), text, title, link, msg_id))
        return N.NibResult(True, 200)


class FakeCliq:
    configured = True

    def __init__(self):
        self.sent: list[tuple] = []

    def send(self, kind, target, text):
        self.sent.append((kind, target, text))
        return N.NibResult(True, 200)


class HubStub:
    configured = True

    def pulse(self, *a, **k):
        pass

    def expand_targets(self, targets):
        return [t.lstrip("@") for t in targets]

    def send_mention(self, to, text, link="", **k):
        return True

    def cliq_ids_for(self, logins):
        return {lg: f"cliq-{lg}" for lg in logins}


def dispatcher(tmp_path, nib, cliq=None, prefer_cliq=False):
    return Dispatcher(HubStub(), DeliveredLedger(tmp_path / "d.json"), cliq, tmp_path / "alerts.jsonl",
                      my_cliq_id="cliq-me", cliq_enabled=cliq is not None, nib=nib, my_login="vikram",
                      prefer_cliq=prefer_cliq)


def event(key="w1"):
    return M.WatchEvent(key=key, watcher_id="w", event="changed", title="ISO-1001 changed",
                        detail="rev C", link="projectopener://activity/a1")


def test_watcher_hits_go_through_nib_to_me_and_the_people_mentioned(tmp_path):
    nib = FakeNib()
    d = dispatcher(tmp_path, nib).deliver(event(), M.Notify(mentions=["priya"], cliq_dm=True))
    assert d.nib_sent and not d.cliq_sent
    to, text, title, link, mid = nib.sent[0]
    assert to == ["vikram", "priya"] and text == "ISO-1001 changed\nrev C"
    assert link == "projectopener://activity/a1" and mid == N.message_id("watch", "w1")
    assert not dispatcher(tmp_path, nib).deliver(event(), M.Notify(cliq_dm=True)).new   # once


def test_cliq_only_when_chosen_or_while_the_connect_hub_is_down(tmp_path):
    nib, cliq = FakeNib(), FakeCliq()
    dispatcher(tmp_path, nib, cliq, prefer_cliq=True).deliver(event("a"), M.Notify(cliq_dm=True))
    assert cliq.sent and not nib.sent                           # "Use Zoho Cliq instead"
    nib2, cliq2 = FakeNib(reachable=False), FakeCliq()
    dispatcher(tmp_path, nib2, cliq2).deliver(event("b"), M.Notify(cliq_dm=True))
    assert cliq2.sent and not nib2.sent                         # Connect down, Cliq set up
    nib3 = FakeNib(reachable=False)
    d = dispatcher(tmp_path, nib3).deliver(event("c"), M.Notify(cliq_dm=True))
    assert nib3.sent and d.nib_sent                             # no Cliq: Nib (its outbox waits for the hub)


def test_people_notes_go_through_nib(tmp_path):
    nib = FakeNib()
    d = dispatcher(tmp_path, nib).notify_people(["yokesh"], "Vikram gave you a task", "projectopener://task/t1",
                                                kind="task", title="Send rev C")
    assert d.inboxes == ["yokesh"] and d.nib_sent
    assert nib.sent[0][:4] == (["yokesh"], "Vikram gave you a task", "Send rev C", "projectopener://task/t1")


def test_make_dispatcher_needs_nothing_from_the_person(tmp_path):
    from project_opener.core.settings import Settings
    from project_opener.lan.delivery import make_dispatcher
    from project_opener.lan.hub import TeamHub
    hub_root = tmp_path / "hub"
    hub_root.mkdir()
    hub = TeamHub(hub_root, "vikram")
    hub.initialise()
    st = Settings()
    assert make_dispatcher(hub, st, tmp_path, "vikram").nib.configured is False
    write_config(hub_root)
    disp = make_dispatcher(hub, st, tmp_path, "vikram")
    assert disp.nib.configured and not disp.prefer_cliq and not disp._cliq_ready()
    assert disp.my_login == "vikram"


# ------------------------------------------------------------------ handover
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from test_v4_team import FakeApp  # noqa: E402  (the two-PC harness)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeWatch:
    def __init__(self, rows):
        self.rows = rows
        self.client = None

    def read(self, today):
        return self.rows


def leave(lid="L1", start="2026-11-19", end="2026-11-24", current=True, cover="dex\\yokesh", name="Yokesh"):
    return {"id": lid, "from": start, "to": end, "half": None, "current": current,
            "cover": {"account": cover, "name": name} if cover else None}


@pytest.fixture
def office(qapp, tmp_path, hub_root):
    vikram = FakeApp(tmp_path / "v", hub_root, "vikram", "Vikram")
    yokesh = FakeApp(tmp_path / "y", hub_root, "yokesh", "Yokesh")
    return vikram, yokesh, hub_root


def nib_rows(app, rows):
    watch = FakeWatch(rows)
    app.team._leave_watch = lambda: watch
    return watch


def test_no_nib_leave_changes_nothing(office):
    vikram, _yokesh, _root = office
    nib_rows(vikram, [])
    vikram.sync()
    assert vikram.team.nibLeave == {} and vikram.team.handover == {}
    nib_rows(vikram, None)                                       # Nib not answering
    vikram.sync()
    assert vikram.team.nibLeave == {}


def test_nib_leave_prefills_the_page_with_a_known_cover_only(office):
    vikram, yokesh, _root = office
    yokesh.sync()
    nib_rows(vikram, [leave(start="2026-11-23", end="2026-11-27", current=False)])
    vikram.sync()
    nl = vikram.team.nibLeave
    assert (nl["start"], nl["end"], nl["coverLogin"], nl["coverName"], nl["current"]) == \
        ("2026-11-23", "2026-11-27", "yokesh", "Yokesh", False)
    assert vikram.team.handover == {}                             # not started: nothing done
    nib_rows(vikram, [leave(cover="dex\\stranger", name="Stranger", current=False)])
    vikram.sync()
    assert vikram.team.nibLeave["coverLogin"] == "" and vikram.team.nibLeave["coverName"] == "Stranger"


def test_offer_mode_toasts_once_when_the_leave_starts(office):
    vikram, yokesh, _root = office
    yokesh.sync()
    nib_rows(vikram, [leave()])
    vikram.sync()
    vikram.sync()
    offers = [t for t in vikram.toasts if t[0] == "You are on leave"]
    assert len(offers) == 1 and "Yokesh" in offers[0][1]
    assert vikram.team.handover == {}                             # offered, not done


def test_auto_mode_hands_over_and_hands_back_when_the_leave_ends_in_nib(office):
    vikram, yokesh, hub_root = office
    vikram.ctx.settings.handover_on_leave = "auto"
    ts = TaskStore(hub_root / "tasks")
    task = M.Task("Send rev C sheets to FST", owner="vikram")
    ts.save(task)
    yokesh.sync()
    nib_rows(vikram, [leave()])
    vikram.sync()
    vikram.sync()
    mine = vikram.team.handover
    assert mine["toName"] == "Yokesh" and mine["taskCount"] == 1
    assert (mine["start"], mine["end"]) == ("2026-11-19", "2026-11-24")
    yokesh.sync()
    yokesh.team.acceptHandover(yokesh.team.incoming.rows[0]["handoverId"])
    assert ts.get(task.id).owner == "yokesh"
    nib_rows(vikram, [])                                          # cancelled (or over) in Nib
    vikram.sync()
    assert ts.get(task.id).owner == "vikram" and vikram.team.handover == {}
    nib_rows(vikram, [leave()])                                   # the same leave is not handed over twice
    vikram.sync()
    assert vikram.team.handover == {}


def test_auto_mode_without_a_known_cover_only_offers(office):
    vikram, _yokesh, _root = office
    vikram.ctx.settings.handover_on_leave = "auto"
    nib_rows(vikram, [leave(cover=None)])
    vikram.sync()
    assert vikram.team.handover == {}
    assert any(t[0] == "You are on leave" for t in vikram.toasts)


def test_off_mode_does_nothing(office):
    vikram, yokesh, _root = office
    vikram.ctx.settings.handover_on_leave = "off"
    yokesh.sync()
    nib_rows(vikram, [leave()])
    vikram.sync()
    assert vikram.team.handover == {} and not any(t[0] == "You are on leave" for t in vikram.toasts)


def test_a_handover_on_the_nib_dates_follows_the_nib_leave(office):
    vikram, yokesh, hub_root = office
    ts = TaskStore(hub_root / "tasks")
    task = M.Task("GAD comments", owner="vikram")
    ts.save(task)
    yokesh.sync()
    nib_rows(vikram, [leave(start="2026-11-23", end="2026-11-27", current=False)])
    vikram.sync()
    assert vikram.team.startHandover("yokesh", "2026-11-23", "2026-11-27", [], [task.id]) == ""
    vikram.sync()
    assert vikram.team.handover
    nib_rows(vikram, [])                                          # leave cancelled in Nib before it starts
    vikram.sync()
    assert vikram.team.handover == {}

