"""Updater.fetch_release: one specific GitHub release by tag, same asset parsing as check_github."""
import io
import json
import urllib.error

import pytest

from project_opener.update import updater as U
from project_opener.update.updater import Updater

RELEASE = {
    "tag_name": "v3.0.0", "draft": False, "prerelease": False, "body": "Rebuild", "published_at": "2026-10-30T00:00:00Z",
    "assets": [
        {"name": "ProjectOpener-Setup-3.0.0.exe", "url": "https://api.example/assets/1", "size": 123},
        {"name": "latest.json", "url": "https://api.example/assets/2", "size": 10},
    ],
}
MANIFEST = {"version": "3.0.0", "installer": "ProjectOpener-Setup-3.0.0.exe", "sha256": "ABC", "size": 123}


class _Resp(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _fake_urlopen(routes: dict[str, object]):
    calls: list[str] = []

    def urlopen(req, timeout=0):
        url = req.full_url
        calls.append(url)
        for key, payload in routes.items():
            if key in url:
                if isinstance(payload, Exception):
                    raise payload
                return _Resp(payload)
        raise AssertionError(f"unexpected URL {url}")

    return urlopen, calls


def test_fetch_release_by_tag_parses_assets_and_manifest(monkeypatch):
    urlopen, calls = _fake_urlopen({"/releases/tags/v3.0.0": RELEASE, "assets/2": MANIFEST})
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)
    up = Updater(channel="stable")
    info = up.fetch_release("3.0.0")          # bare version is prefixed with 'v'
    assert info is not None
    assert info.version == "3.0.0" and info.installer == "ProjectOpener-Setup-3.0.0.exe"
    assert info.sha256 == "abc" and info.size == 123 and info.source == "github"
    assert info.url == "https://api.example/assets/1"
    assert info.notes == "Rebuild" and not info.prerelease
    assert calls[0].endswith("/releases/tags/v3.0.0")


def test_fetch_release_ignores_channel_and_rejects_drafts(monkeypatch):
    urlopen, calls = _fake_urlopen({"/releases/tags/v9.9.9": dict(RELEASE, draft=True)})
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)
    assert Updater(channel="all").fetch_release("v9.9.9") is None
    assert len(calls) == 1 and "per_page" not in calls[0]


def test_fetch_release_without_installer_returns_none(monkeypatch):
    urlopen, _ = _fake_urlopen({"/releases/tags/": dict(RELEASE, assets=[])})
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)
    assert Updater().fetch_release("v3.0.0") is None


def test_fetch_release_missing_tag_raises_like_check_github(monkeypatch):
    err = urllib.error.HTTPError("u", 404, "nf", {}, None)  # type: ignore[arg-type]
    urlopen, _ = _fake_urlopen({"/releases/tags/": err})
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        Updater().fetch_release("v0.0.1")


def test_check_github_unchanged_latest_endpoint(monkeypatch):
    urlopen, calls = _fake_urlopen({"/releases/latest": RELEASE, "assets/2": MANIFEST})
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)
    info = Updater(channel="stable").check_github()
    assert info and info.version == "3.0.0" and calls[0].endswith("/releases/latest")
    urlopen, calls = _fake_urlopen({"/releases?per_page=10": [dict(RELEASE, draft=True), RELEASE], "assets/2": MANIFEST})
    monkeypatch.setattr(U.urllib.request, "urlopen", urlopen)
    info = Updater(channel="all").check_github()
    assert info and info.version == "3.0.0" and "per_page=10" in calls[0]
