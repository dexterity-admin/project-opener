import hashlib
import json

from project_opener.core import models as M
from project_opener.lan.hub import TeamHub
from project_opener.update.updater import UpdateInfo, Updater, is_newer, parse_version, sha256_of


def test_hub_publish_clone_and_revision(hub_root):
    me = TeamHub(hub_root, user="vikram", display_name="Vikram")
    peer = TeamHub(hub_root, user="yokesh")
    p = M.Project(name="P12513", items=[M.Item(path=r"Z:\P12513\a.pdf")])
    pub = me.publish(p, portable_fn=lambda s: s.replace("Z:", r"\\srv\share"))
    assert pub and pub.revision == 1
    assert p.origin.source == "team" and p.origin.published_id == pub.published_id
    listed = peer.published()
    assert listed[0].project.items[0].path == r"\\srv\share\P12513\a.pdf"
    clone = listed[0].project.clone("P12513")
    assert clone.origin.revision == 1
    me.publish(p)
    assert peer.newer_revision(clone).revision == 2


def test_hub_inbox_and_dismiss(hub_root):
    me = TeamHub(hub_root, user="vikram")
    peer = TeamHub(hub_root, user="yokesh")
    assert me.send("yokesh", M.Project(name="Hi"), message="have a look")
    msgs = peer.inbox()
    assert len(msgs) == 1 and msgs[0].sender == "vikram" and msgs[0].project.name == "Hi"
    peer.dismiss_inbox(msgs[0])
    assert peer.inbox() == []


def test_hub_presence_and_announcements(hub_root):
    me = TeamHub(hub_root, user="vikram")
    me.heartbeat(current_project="P12513")
    peers = TeamHub(hub_root, user="x").peers()
    assert peers[0].user == "vikram" and peers[0].online and peers[0].current_project == "P12513"
    me.sign_off()
    assert not TeamHub(hub_root, user="x").peers()[0].online
    a = me.announce("Server move", "Z: moves to the new NAS on Friday", level="warning")
    assert TeamHub(hub_root, user="x").announcements()[0].id == a.id
    me.remove_announcement(a.id)
    assert me.announcements() == []


def test_hub_status_unconfigured_and_corrupt_files(hub_root):
    assert not TeamHub(None).status().configured
    hub = TeamHub(hub_root, user="a")
    hub.initialise()
    (hub_root / "published" / "bad.json").write_text("{", encoding="utf-8")
    (hub_root / "users" / "bad.json").write_text("[]", encoding="utf-8")
    assert hub.published() == [] and hub.peers() == []
    assert hub.status().reachable


def test_pulse_feed(hub_root):
    hub = TeamHub(hub_root, user="a")
    hub.pulse("launched", "P12513")
    assert hub.pulse_feed()[0]["detail"] == "P12513"


def test_version_compare():
    assert parse_version("v3.1.0") == (3, 1, 0)
    assert is_newer("3.0.1", "3.0.0") and not is_newer("3.0.0", "3.0.0") and not is_newer("2.9", "3.0.0")


def test_lan_manifest_download_verify_and_mirror(tmp_path):
    lan = tmp_path / "updates"
    lan.mkdir()
    installer = lan / "ProjectOpener-Setup-9.9.9.exe"
    installer.write_bytes(b"fake installer bytes")
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    (lan / "latest.json").write_text(json.dumps({"version": "9.9.9", "installer": installer.name, "sha256": digest}),
                                     encoding="utf-8")
    up = Updater(lan_dir=lan)
    info = up.check_lan()
    assert info and info.available and info.source == "lan"
    seen = []
    path = up.download(info, progress=lambda d, t: seen.append((d, t)))
    assert path.exists() and sha256_of(path) == digest and seen
    # tampered mirror must be rejected
    (lan / "latest.json").write_text(json.dumps({"version": "9.9.9", "installer": installer.name, "sha256": "00"}),
                                     encoding="utf-8")
    bad = up.check_lan()
    path.unlink()
    try:
        up.download(bad)
    except RuntimeError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("tampered installer accepted")
    # mirroring rewrites the manifest with the real hash
    mirror = tmp_path / "mirror"
    dest = up.mirror_to_lan(UpdateInfo(version="9.9.9", installer=installer.name, sha256="", notes="n"), installer, mirror)
    assert dest.exists()
    assert json.loads((mirror / "latest.json").read_text(encoding="utf-8"))["sha256"] == digest


def test_check_without_lan_or_network_reports_error(monkeypatch):
    up = Updater(timeout=0.01)
    monkeypatch.setattr(up, "check_github", lambda: (_ for _ in ()).throw(RuntimeError("no connection")))
    res = up.check()
    assert res.update is None and res.errors and "lan" in res.checked_sources
