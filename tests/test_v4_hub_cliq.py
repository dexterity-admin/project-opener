"""Zoho Cliq bot client against a fake local HTTP server (no real network)."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from project_opener.core import models as M
from project_opener.lan.cliq import CliqClient
from project_opener.lan.delivery import DeliveredLedger, Dispatcher
from project_opener.lan.hub import TeamHub


class FakeCliq:
    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self, method):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                parts = urlsplit(self.path)
                fake.requests.append({"method": method, "path": parts.path, "query": parse_qs(parts.query),
                                      "body": body})
                status = fake.status
                if method == "GET" and parts.path.startswith("/api/v2/users/") and status == 200:
                    payload = json.dumps({"data": {"id": "60001234", "email_id": "priya@dex.com"}}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(status if status != 200 else 204)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):  # noqa: N802
                self._handle("POST")

            def do_GET(self):  # noqa: N802
                self._handle("GET")

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/api/v2"

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
    f = FakeCliq()
    yield f
    f.close()


def client(base, tmp_path, **kw):
    return CliqClient(base, "officebot", "1001.secret", tmp_path / "cliq-outbox.jsonl", timeout=3, **kw)


def test_dm_uses_bot_message_endpoint_with_zapikey(fake, tmp_path):
    c = client(fake.base, tmp_path)
    res = c.dm(["60001234", "60005678"], "Vikram mentioned you\nprojectopener://task/abc")
    assert res.ok and res.status == 204
    r = fake.requests[-1]
    assert r["method"] == "POST" and r["path"] == "/api/v2/bots/officebot/message"
    assert r["query"]["zapikey"] == ["1001.secret"]
    assert r["body"] == {"text": "Vikram mentioned you\nprojectopener://task/abc", "userids": "60001234,60005678"}


def test_channel_post_as_bot(fake, tmp_path):
    c = client(fake.base, tmp_path)
    assert c.post_channel("#p12513", "Rev C dropped").ok
    r = fake.requests[-1]
    assert r["path"] == "/api/v2/channelsbyname/p12513/message"
    assert r["query"]["bot_unique_name"] == ["officebot"] and r["body"] == {"text": "Rev C dropped"}


def test_lookup_user(fake, tmp_path):
    c = client(fake.base, tmp_path)
    assert c.lookup_user("priya@dex.com") == "60001234"
    assert fake.requests[-1]["path"] == "/api/v2/users/priya%40dex.com" or \
        fake.requests[-1]["path"] == "/api/v2/users/priya@dex.com"
    fake.status = 401
    assert c.lookup_user("priya@dex.com") == ""


def test_transient_failure_is_queued_and_retried(fake, tmp_path):
    c = client(fake.base, tmp_path)
    fake.status = 503
    res = c.send("dm", ["60001234"], "hello")
    assert not res.ok and res.retry and c.pending() == 1
    assert c.flush_outbox() == 0 and c.pending() == 1        # still down: kept
    fake.status = 200
    assert c.flush_outbox() == 1 and c.pending() == 0
    assert fake.requests[-1]["body"]["text"] == "hello"


def test_permanent_failure_is_not_queued(fake, tmp_path):
    c = client(fake.base, tmp_path)
    fake.status = 400
    res = c.send("channel", "nope", "x")
    assert not res.ok and not res.retry and c.pending() == 0


def test_unreachable_server_queues(tmp_path):
    c = client("http://127.0.0.1:9/api/v2", tmp_path)       # discard port: nothing listens
    res = c.send("dm", ["1"], "x")
    assert not res.ok and res.retry and res.status == 0
    assert c.pending() == 1


def test_not_configured_and_dry_run(tmp_path):
    assert not CliqClient("https://cliq.zoho.in/api/v2", "", "", tmp_path / "o").dm(["1"], "x").ok
    c = client("https://cliq.zoho.in/api/v2", tmp_path, dry_run=True)
    assert c.dm(["1"], "x").ok
    assert c.sent[0].url.startswith("https://cliq.zoho.in/api/v2/bots/officebot/message?zapikey=")


def test_dispatcher_dms_owner_and_linked_mentions(fake, tmp_path, hub_root):
    hub = TeamHub(hub_root, "vikram")
    hub.initialise()
    hub.heartbeat()
    priya = TeamHub(hub_root, "priya")
    priya.cliq_id, priya.cliq_linked = "60001234", True
    priya.heartbeat()
    TeamHub(hub_root, "yokesh").heartbeat()                  # not linked: inbox only
    disp = Dispatcher(hub, DeliveredLedger(tmp_path / "d.json"), client(fake.base, tmp_path),
                      tmp_path / "alerts.jsonl", my_cliq_id="60000001")
    ev = M.WatchEvent("w", "new", "New in Rev C", "ISO-003.pdf", link="projectopener://activity/Lot%207", key="k1")
    d = disp.deliver(ev, M.Notify(mentions=["priya", "yokesh"], cliq_dm=True, cliq_channel="p12513"))
    assert d.new and d.cliq_sent and sorted(d.inboxes) == ["priya", "yokesh"]
    dms = [r for r in fake.requests if r["path"].endswith("/bots/officebot/message")]
    assert dms[0]["body"]["userids"] == "60000001,60001234"
    assert "projectopener://activity/Lot%207" in dms[0]["body"]["text"]
    assert any(r["path"].endswith("/channelsbyname/p12513/message") for r in fake.requests)
    before = len(fake.requests)
    assert disp.deliver(ev, M.Notify(cliq_dm=True)).new is False   # never sent twice
    assert len(fake.requests) == before
