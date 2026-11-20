"""Dexterity Connect notices against a fake hub on this PC (no real network): the requests, the
outbox, the older hub, the certificate fingerprint, the office's settings and the dispatcher."""
from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from project_opener.core import models as M
from project_opener.core.settings import Settings
from project_opener.lan import connect_bot as CB
from project_opener.lan.connect_bot import ConnectClient, make_notice
from project_opener.lan.delivery import DeliveredLedger, Dispatcher, make_dispatcher
from project_opener.lan.hub import TeamHub

TOKEN = "dxc_test-token"


class FakeHub:
    """Connect's Bot API as docs/TOOL-NOTICES.md describes it: keys delivered once, unknown people named."""

    def __init__(self, tls: tuple[str, str] | None = None):
        self.requests: list[dict] = []
        self.status = 200                 # what /api/bot/notify answers
        self.retry_after = ""
        self.legacy = False               # a hub from before tool notices
        self.people = {"vikram", "priya", "yokesh"}
        self.away: dict[str, dict] = {}
        self.failing: set[str] = set()    # people the hub cannot write to right now
        self.seen: set[tuple[str, str]] = set()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, status: int, payload: dict, headers: dict | None = None) -> None:
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self, method: str) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                fake.requests.append({"method": method, "path": self.path, "body": body,
                                      "auth": self.headers.get("Authorization", "")})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._json(401, {"ok": False, "error": "Unknown or revoked integration token."})
                if self.path == "/api/bot/hello" and not fake.legacy:
                    return self._json(200, {"ok": True, "api": 1, "integration": {"id": "b1", "name": "Project Opener"},
                                            "hub": {"id": "h1", "name": "Dexterity Mumbai"},
                                            "notices": {"via": "nib", "perMinute": 120}})
                if self.path == "/api/bot/notify" and not fake.legacy:
                    if fake.status != 200:
                        return self._json(fake.status, {"ok": False, "error": "no"},
                                          {"Retry-After": fake.retry_after} if fake.retry_after else None)
                    results = []
                    for who in body.get("to", []):
                        name = who.split("\\")[-1].lower()
                        if name not in fake.people:
                            results.append({"to": who, "status": "unknown"})
                        elif name in fake.failing:
                            results.append({"to": who, "status": "failed"})
                        elif (body.get("key"), name) in fake.seen:
                            results.append({"to": who, "status": "duplicate", "via": "nib"})
                        else:
                            fake.seen.add((body.get("key"), name))
                            r = {"to": who, "status": "delivered", "via": "nib", "account": f"dex\\{name}"}
                            if name in fake.away:
                                r["away"] = fake.away[name]
                            results.append(r)
                    if body.get("space"):
                        ok = body["space"].lower() == "piping p-12"
                        results.append({"to": f"space:{body['space']}", "status": "delivered" if ok else "unknown",
                                        **({"via": "integration"} if ok else {})})
                    good = [r for r in results if r["status"] in ("delivered", "duplicate")]
                    return self._json(200, {"ok": bool(good), "api": 1, "results": results,
                                            "unknown": [r["to"] for r in results if r["status"] == "unknown"]})
                if self.path == "/api/bot/message":
                    unknown = [w for w in body.get("to", []) if w.lower() not in fake.people]
                    delivered = [w for w in body.get("to", []) if w.lower() in fake.people]
                    return self._json(200 if delivered or body.get("space") else 404,
                                      {"ok": bool(delivered), "delivered": delivered, "unknown": unknown})
                return self._json(404, {"ok": False, "error": "not found"})

            def do_POST(self):  # noqa: N802
                self._handle("POST")

            def do_GET(self):  # noqa: N802
                self._handle("GET")

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.handle_error = lambda *a: None   # a client that hangs up on a wrong certificate is the test
        scheme = "http"
        if tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(*tls)
            self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
            scheme = "https"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"{scheme}://127.0.0.1:{self.server.server_address[1]}"

    def notices(self) -> list[dict]:
        return [r["body"] for r in self.requests if r["path"] == "/api/bot/notify"]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


@pytest.fixture
def fake():
    f = FakeHub()
    yield f
    f.close()


def client(url, tmp_path, **kw):
    return ConnectClient(url, TOKEN, "", tmp_path / "connect-outbox.jsonl", timeout=3, **kw)


# ---------------------------------------------------------------- the requests
def test_notify_posts_one_notice_with_the_token_and_a_key(fake, tmp_path):
    c = client(fake.url, tmp_path)
    n = make_notice(["priya", "Priya", "nobody"], title="Check ISO-1001", text="Vikram gave you a task",
                    link="projectopener://task/abc", kind="task", sender="vikram")
    res = c.notify(n)
    assert res.ok and res.delivered == ["priya"] and res.unknown == ["nobody"] and res.via == "nib"
    r = fake.requests[-1]
    assert (r["method"], r["path"], r["auth"]) == ("POST", "/api/bot/notify", f"Bearer {TOKEN}")
    assert r["body"] == {"key": n["key"], "to": ["priya", "nobody"], "title": "Check ISO-1001",
                         "text": "Vikram gave you a task", "kind": "task", "from": "vikram",
                         "link": {"title": "Open in Project Opener", "url": "projectopener://task/abc"}}
    assert n["key"].startswith("po:") and make_notice(["priya"], title="x")["key"] != n["key"]


def test_hello_says_who_we_are_and_refuses_a_bad_token(fake, tmp_path):
    res = client(fake.url, tmp_path).hello()
    assert res.ok and res.message == "Connected to Dexterity Mumbai as Project Opener." and res.via == "nib"
    bad = ConnectClient(fake.url, "dxc_wrong", "", tmp_path / "o").hello()
    assert not bad.ok and bad.status == 401 and not bad.retry and "refused the token" in bad.message


def test_nobody_known_is_not_ok_and_never_retried(fake, tmp_path):
    c = client(fake.url, tmp_path)
    res = c.send(make_notice(["nobody"], title="x"))
    assert not res.ok and not res.retry and res.unknown == ["nobody"] and c.pending() == 0


def test_someone_on_leave_is_told_and_the_caller_learns_it(fake, tmp_path):
    fake.away["priya"] = {"back": "2026-11-24", "cover": "dex\\yokesh"}
    res = client(fake.url, tmp_path).notify(make_notice(["priya"], title="x"))
    assert res.ok and res.away == {"priya": {"back": "2026-11-24", "cover": "dex\\yokesh"}}


def test_more_than_fifty_people_go_in_batches_with_one_key(fake, tmp_path):
    fake.people |= {f"u{i}" for i in range(120)}
    n = make_notice([f"u{i}" for i in range(120)], title="Office notice", space="Piping P-12")
    res = client(fake.url, tmp_path).notify(n)
    assert res.ok and len(res.delivered) == 121
    sent = fake.notices()
    assert [len(b["to"]) for b in sent] == [50, 50, 20] and {b["key"] for b in sent} == {n["key"]}
    assert [("space" in b) for b in sent] == [True, False, False]


# ---------------------------------------------------------------- the outbox
def test_transient_failure_is_queued_and_the_retry_carries_the_same_key(fake, tmp_path):
    c = client(fake.url, tmp_path)
    fake.status = 503
    n = make_notice(["priya"], title="hello")
    res = c.send(n)
    assert not res.ok and res.retry and c.pending() == 1
    assert c.flush_outbox() == 0 and c.pending() == 1        # still down: kept
    fake.status = 200
    assert c.flush_outbox() == 1 and c.pending() == 0
    assert {b["key"] for b in fake.notices()} == {n["key"]}   # the hub can tell it is the same notice


def test_rate_limit_waits_and_holds_the_rest_of_the_outbox(fake, tmp_path):
    c = client(fake.url, tmp_path)
    fake.status, fake.retry_after = 429, "17"
    res = c.send(make_notice(["priya"], title="one"))
    assert res.retry and res.retry_after == 17
    c.send(make_notice(["priya"], title="two"))
    before = len(fake.requests)
    assert c.flush_outbox() == 0 and c.pending() == 2
    assert len(fake.requests) == before + 1                   # the second was not tried: Connect asked us to wait
    fake.status = 200
    assert c.flush_outbox() == 2 and c.pending() == 0


def test_partly_failed_is_sent_again_and_only_reaches_the_rest(fake, tmp_path):
    c = client(fake.url, tmp_path)
    fake.failing = {"yokesh"}
    res = c.send(make_notice(["priya", "yokesh"], title="Rev C"))
    assert res.ok and res.retry and res.delivered == ["priya"] and c.pending() == 1
    fake.failing = set()
    assert c.flush_outbox() == 1 and c.pending() == 0
    assert ("po", "priya") not in fake.seen and len([k for k in fake.seen if k[1] == "priya"]) == 1


def test_permanent_failures_are_not_queued(fake, tmp_path):
    c = client(fake.url, tmp_path)
    fake.status = 400
    res = c.send(make_notice(["priya"], title="x"))
    assert not res.ok and not res.retry and c.pending() == 0
    bad = ConnectClient(fake.url, "dxc_revoked", "", tmp_path / "o2")
    assert not bad.send(make_notice(["priya"], title="x")).retry and bad.pending() == 0


def test_unreachable_hub_queues_and_gives_up_after_many_tries(tmp_path, monkeypatch):
    c = client("http://127.0.0.1:9", tmp_path)               # discard port: nothing listens
    res = c.send(make_notice(["priya"], title="x"))
    assert not res.ok and res.retry and res.status == 0 and c.pending() == 1
    monkeypatch.setattr(CB, "MAX_ATTEMPTS", 2)
    c.flush_outbox()
    assert c.pending() == 1
    c.flush_outbox()
    assert c.pending() == 0


def test_outbox_keeps_the_newest_and_ignores_rows_it_does_not_know(tmp_path, monkeypatch):
    monkeypatch.setattr(CB, "OUTBOX_MAX", 3)
    c = client("http://127.0.0.1:9", tmp_path)
    for i in range(5):
        c.queue(make_notice(["priya"], title=f"n{i}"))
    rows = [json.loads(x) for x in c.outbox.read_text(encoding="utf-8").splitlines()]
    assert [r["notice"]["title"] for r in rows] == ["n2", "n3", "n4"]
    n = make_notice(["priya"], title="same")
    c.queue(n)
    c.queue(n)                                                # the same notice is queued once
    assert c.pending() == 3
    c.outbox.write_text('{"kind": "dm", "target": ["600"], "text": "an old Cliq row"}\n', encoding="utf-8")
    fake = FakeHub()
    try:
        ok = client(fake.url, tmp_path)
        assert ok.flush_outbox() == 0 and ok.pending() == 0 and fake.requests == []
    finally:
        fake.close()


# ---------------------------------------------------------------- an older hub
def test_older_hub_gets_the_same_words_as_a_message(fake, tmp_path):
    fake.legacy = True
    c = client(fake.url, tmp_path)
    assert c.hello().ok and c.hello().via == "message"
    res = c.notify(make_notice(["priya", "nobody"], title="Check ISO-1001", text="Due Friday",
                               link="projectopener://task/abc", lines=["3 drawings"]))
    assert res.ok and res.via == "message" and res.delivered == ["priya"] and res.unknown == ["nobody"]
    assert fake.requests[-1]["path"] == "/api/bot/message"
    assert fake.requests[-1]["body"] == {
        "to": ["priya", "nobody"],
        "text": "**Check ISO-1001**\nDue Friday\n- 3 drawings\n[Open in Project Opener](projectopener://task/abc)"}
    before = len(fake.requests)
    c.notify(make_notice(["priya"], title="again"))
    assert [r["path"] for r in fake.requests[before:]] == ["/api/bot/message"]   # /notify is not asked every time
    assert not c.send(make_notice(["nobody"], title="x")).retry


# ---------------------------------------------------------------- settings
def test_not_configured_dry_run_and_what_is_missing(tmp_path):
    assert not ConnectClient("", "", "", tmp_path / "o").notify(make_notice(["a"], title="x")).ok
    no_fp = ConnectClient("hub-pc", TOKEN, "", tmp_path / "o")
    assert not no_fp.configured and "fingerprint" in no_fp.why_not()
    c = ConnectClient("hub-pc:47900", TOKEN, "AA:" * 31 + "AA", tmp_path / "o", dry_run=True)
    assert c.configured and c.hub == "https://hub-pc:47900"
    res = c.notify(make_notice(["priya"], title="x", space="#Piping"))
    assert res.ok and res.delivered == ["priya", "space:Piping"] and c.sent[0].path == "/api/bot/notify"


def test_what_connect_copies_is_understood():
    block = json.dumps({"connect": {"enabled": True, "hub": "hub-pc:47900", "fingerprint": "AB:" * 31 + "AB",
                                    "token": "dxc_abc"}}, indent=2)
    assert CB.parse_settings(block) == {"hub": "https://hub-pc:47900", "fingerprint": "ab" * 32, "token": "dxc_abc"}
    assert CB.parse_settings(" dxc_abc ") == {"hub": "", "fingerprint": "", "token": "dxc_abc"}
    assert CB.parse_settings("hello") == {} and CB.parse_settings("{}") == {} and CB.parse_settings("[1]") == {}
    assert CB.normalize_hub("hub-pc") == "https://hub-pc:47900"
    assert CB.normalize_hub("https://10.0.0.5:47900/") == "https://10.0.0.5:47900"
    assert CB.normalize_hub("ftp://x") == "" and CB.normalize_hub("hub pc") == "" and CB.normalize_hub("https://x/y") == ""
    assert CB.normalize_fingerprint("zz") == "" and len(CB.normalize_fingerprint("ab " * 32)) == 64


def test_office_settings_in_the_team_hub_serve_every_pc(tmp_path, hub_root):
    s = Settings()
    assert CB.effective_settings(s, hub_root)["source"] == ""
    assert CB.share_office_settings(hub_root, "hub-pc", "ab" * 32, TOKEN, by="vikram")
    assert CB.effective_settings(s, hub_root) == {"hub": "https://hub-pc:47900", "fingerprint": "ab" * 32,
                                                  "token": TOKEN, "source": "office"}
    hub = TeamHub(hub_root, "priya")
    hub.initialise()
    assert make_dispatcher(hub, s, tmp_path, "priya").connect.configured      # a PC nobody set up
    s.connect_hub, s.connect_fingerprint = "https://other:47900", "cd" * 32
    s.connect_token = "dxc_mine"
    assert CB.effective_settings(s, hub_root)["source"] == "pc"               # this PC's own win
    assert CB.unshare_office_settings(hub_root) and CB.unshare_office_settings(hub_root)
    assert CB.office_settings(hub_root) == {} and not CB.share_office_settings(None, "hub-pc", "", TOKEN)
    (hub_root / CB.OFFICE_FILE).write_text("not json", encoding="utf-8")
    assert CB.office_settings(hub_root) == {}


def test_settings_carry_over_only_the_wish_from_cliq(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "notify_cliq_default": False, "cliq_bot": "officebot", "cliq_user_id": "600", "settings_tab": "cliq"}),
        encoding="utf-8")
    s = Settings.load(tmp_path)
    assert s.notify_connect is False and s.settings_tab == "connect" and not hasattr(s, "cliq_bot")
    assert "connect_token_enc" not in s.to_public_dict()
    old = M.Notify.from_dict({"toast": True, "cliq_dm": True, "cliq_channel": "p12513"})
    assert old.connect_dm is True and old.connect_space == ""               # a Cliq channel is not a Space
    assert M.Notify.from_dict(M.Notify(connect_dm=True, connect_space="Piping").to_dict()).connect_space == "Piping"


# ---------------------------------------------------------------- the hub's certificate
@pytest.fixture(scope="module")
def cert(tmp_path_factory):
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is not on this PC: the fingerprint test needs it to make a certificate")
    d = tmp_path_factory.mktemp("tls")
    key, crt = d / "k.pem", d / "c.pem"
    done = subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out",
                           str(crt), "-days", "2", "-subj", "/CN=Project Opener test hub"],
                          capture_output=True, check=False, timeout=60)
    if done.returncode != 0:
        pytest.skip("openssl could not make a certificate here")
    der = ssl.PEM_cert_to_DER_cert(crt.read_text(encoding="ascii"))
    fp = hashlib.sha256(der).hexdigest().upper()
    return str(crt), str(key), ":".join(fp[i:i + 2] for i in range(0, 64, 2))


def test_the_hub_is_trusted_by_its_fingerprint_and_the_token_goes_nowhere_else(cert, tmp_path):
    crt, key, fingerprint = cert
    hub = FakeHub(tls=(crt, key))
    try:
        good = ConnectClient(hub.url, TOKEN, fingerprint, tmp_path / "o", timeout=5)
        assert good.hello().ok and good.notify(make_notice(["priya"], title="x")).ok
        asked = len(hub.requests)
        wrong = ConnectClient(hub.url, TOKEN, "00" * 32, tmp_path / "o", timeout=5)
        res = wrong.send(make_notice(["priya"], title="x"))
        assert not res.ok and not res.retry and "fingerprint" in res.message
        assert len(hub.requests) == asked and wrong.pending() == 0    # nothing was sent, nothing waits to be
    finally:
        hub.close()


# ---------------------------------------------------------------- the dispatcher
def people(hub_root):
    hub = TeamHub(hub_root, "vikram")
    hub.initialise()
    hub.heartbeat()
    TeamHub(hub_root, "priya").heartbeat()
    quiet = TeamHub(hub_root, "yokesh")
    quiet.connect_notify = False                              # turned "Tell me in Connect" off: inbox only
    quiet.heartbeat()
    return hub


def test_dispatcher_tells_the_owner_and_the_people_mentioned_once(fake, tmp_path, hub_root):
    hub = people(hub_root)
    disp = Dispatcher(hub, DeliveredLedger(tmp_path / "d.json"), client(fake.url, tmp_path),
                      tmp_path / "alerts.jsonl", me="vikram")
    ev = M.WatchEvent("w", "new", "New in Rev C", "ISO-003.pdf", link="projectopener://activity/Lot%207", key="k1")
    d = disp.deliver(ev, M.Notify(mentions=["priya", "yokesh"], connect_dm=True, connect_space="Piping P-12"))
    assert d.new and d.connect_sent and not d.connect_queued and sorted(d.inboxes) == ["priya", "yokesh"]
    n = fake.notices()[-1]
    assert n["to"] == ["vikram", "priya"] and n["space"] == "Piping P-12" and n["key"] == "po:watch:k1"
    assert (n["title"], n["text"], n["kind"]) == ("New in Rev C", "ISO-003.pdf", "alert")
    assert n["link"]["url"] == "projectopener://activity/Lot%207"
    before = len(fake.requests)
    assert disp.deliver(ev, M.Notify(connect_dm=True)).new is False   # never sent twice
    assert len(fake.requests) == before
    # my other PC (its own ledger) sees the same hit: the key is the same, the hub drops it
    other = Dispatcher(hub, DeliveredLedger(tmp_path / "d2.json"), client(fake.url, tmp_path),
                       tmp_path / "alerts2.jsonl", me="vikram")
    other.deliver(ev, M.Notify(connect_dm=True))
    assert fake.notices()[-1]["key"] == "po:watch:k1" and len([k for k in fake.seen if k[1] == "vikram"]) == 1


def test_dispatcher_respects_my_own_switch_and_survives_connect_being_away(fake, tmp_path, hub_root):
    hub = people(hub_root)
    quiet = Dispatcher(hub, DeliveredLedger(tmp_path / "d.json"), client(fake.url, tmp_path),
                       tmp_path / "alerts.jsonl", me="vikram", notify_me=False)
    quiet.deliver(M.WatchEvent("w", "new", "Hit", key="k2"), M.Notify(connect_dm=True))
    assert fake.notices() == []                               # nobody to tell: no request at all
    down = Dispatcher(hub, DeliveredLedger(tmp_path / "d3.json"), client("http://127.0.0.1:9", tmp_path),
                      tmp_path / "alerts3.jsonl", me="vikram")
    d = down.deliver(M.WatchEvent("w", "new", "Hit", key="k3"), M.Notify(connect_dm=True))
    assert d.new and not d.connect_sent and d.connect_queued and down.connect.pending() == 1
    assert [r["key"] for r in down.alerts()] == ["k3"]        # the alert itself never waited for Connect


def test_notify_people_sends_one_notice_from_me_and_reports_leave(fake, tmp_path, hub_root):
    hub = people(hub_root)
    fake.away["priya"] = {"back": "2026-11-24", "cover": None}
    disp = Dispatcher(hub, DeliveredLedger(tmp_path / "d.json"), client(fake.url, tmp_path),
                      tmp_path / "alerts.jsonl", me="vikram")
    d = disp.notify_people(["priya", "yokesh", "rahul"], "Vikram gave you a task", "projectopener://task/t1",
                           kind="task", task_id="t1", title="Check ISO-1001")
    assert sorted(d.inboxes) == ["priya", "rahul", "yokesh"] and d.connect_sent
    n = fake.notices()[-1]
    assert n["to"] == ["priya", "rahul"] and n["from"] == "vikram" and n["kind"] == "task"   # yokesh opted out
    assert (n["title"], n["text"]) == ("Check ISO-1001", "Vikram gave you a task")
    assert d.unknown == ["rahul"] and d.away == {"priya": {"back": "2026-11-24", "cover": None}}
    # two separate notes are two notices (each its own key), not one swallowed as a duplicate
    disp.notify_people(["priya"], "Vikram gave you a task", "projectopener://task/t1", kind="task", title="Check ISO-1001")
    assert fake.notices()[-1]["key"] != n["key"]
    assert not disp.notify_people(["priya"], "x", connect=False).connect_sent
