"""Update discovery, download, verification and installation.

Two channels are consulted, in order:

1. **LAN mirror** - ``<hub>/updates/latest.json`` next to the installer.  Any
   machine can mirror a release there from the Updates page; afterwards every
   colleague updates over the office LAN with no internet or GitHub access.
2. **GitHub Releases** - the repository's latest release (public; a token in
   Settings → Updates is optional).  The release carries a
   ``latest.json`` asset produced by CI with the installer's SHA-256.

The manifest format (``latest.json``)::

    {"version": "3.1.0", "installer": "ProjectOpener-Setup-3.1.0.exe",
     "sha256": "...", "size": 41234567, "published_at": "...", "notes": "...",
     "url": "https://github.com/.../ProjectOpener-Setup-3.1.0.exe",
     "min_version": "3.0.0"}

Installation runs the Inno Setup installer silently; it closes the running
app, replaces the files and restarts it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from project_opener import constants as C
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)
USER_AGENT = f"ProjectOpener/{C.VERSION}"
Progress = Callable[[int, int], None]


# ----------------------------------------------------------------- versions
def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: str = C.VERSION) -> bool:
    return parse_version(candidate) > parse_version(current)


@dataclass
class UpdateInfo:
    version: str
    installer: str
    sha256: str
    url: str = ""
    local_path: str = ""
    size: int = 0
    notes: str = ""
    published_at: str = ""
    source: str = "github"      # github | lan
    min_version: str = ""
    prerelease: bool = False

    @property
    def available(self) -> bool:
        return is_newer(self.version)

    def to_manifest(self) -> dict:
        return {"version": self.version, "installer": self.installer, "sha256": self.sha256, "url": self.url,
                "size": self.size, "notes": self.notes, "published_at": self.published_at,
                "min_version": self.min_version, "prerelease": self.prerelease}

    @classmethod
    def from_manifest(cls, d: dict, source: str) -> UpdateInfo:
        return cls(version=str(d.get("version", "")), installer=str(d.get("installer", "")),
                   sha256=str(d.get("sha256", "")).lower(), url=str(d.get("url", "")), size=int(d.get("size", 0) or 0),
                   notes=str(d.get("notes", "")), published_at=str(d.get("published_at", "")), source=source,
                   min_version=str(d.get("min_version", "")), prerelease=bool(d.get("prerelease", False)))


@dataclass
class CheckResult:
    update: UpdateInfo | None = None
    errors: list[str] = field(default_factory=list)
    checked_sources: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.update and self.update.available)


# ------------------------------------------------------------------- client
class Updater:
    def __init__(self, token: str = "", lan_dir: Path | None = None, channel: str = "stable",
                 timeout: float = 12.0):
        self.token = token
        self.lan_dir = Path(lan_dir) if lan_dir else None
        self.channel = channel
        self.timeout = timeout
        self.download_dir = C.data_dir() / "downloads"

    # ------------------------------------------------------------- checking
    def check(self) -> CheckResult:
        result = CheckResult()
        candidates: list[UpdateInfo] = []
        lan = self.check_lan()
        result.checked_sources.append("lan")
        if lan:
            candidates.append(lan)
        try:
            gh = self.check_github()
            result.checked_sources.append("github")
            if gh:
                candidates.append(gh)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"GitHub: {exc}")
        if candidates:
            candidates.sort(key=lambda u: (parse_version(u.version), u.source == "lan"), reverse=True)
            result.update = candidates[0]
        return result

    def check_lan(self) -> UpdateInfo | None:
        if not self.lan_dir:
            return None
        manifest = self.lan_dir / "latest.json"
        try:
            if not manifest.exists():
                return None
        except OSError:
            return None
        d = read_json(manifest)
        if not isinstance(d, dict) or not d.get("version"):
            return None
        info = UpdateInfo.from_manifest(d, "lan")
        local = self.lan_dir / info.installer
        info.local_path = str(local) if local.exists() else ""
        if not info.local_path and not info.url:
            return None
        return info

    def _request(self, url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept,
                                                  "X-GitHub-Api-Version": "2022-11-28"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        return req

    def _get_json(self, url: str):
        try:
            with urllib.request.urlopen(self._request(url), timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise RuntimeError(f"GitHub answered HTTP {exc.code}; if the repository is private add a read-only token in Settings → Updates") from exc
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"no connection ({getattr(exc, 'reason', exc)})") from exc

    def check_github(self) -> UpdateInfo | None:
        url = f"{C.GITHUB_API}/releases?per_page=10" if self.channel == "all" else f"{C.GITHUB_API}/releases/latest"
        data = self._get_json(url)
        releases = data if isinstance(data, list) else [data]
        releases = [r for r in releases if isinstance(r, dict) and not r.get("draft")]
        if not releases:
            return None
        return self._release_info(releases[0])

    def fetch_release(self, tag: str) -> UpdateInfo | None:
        """UpdateInfo for one specific GitHub release (``tag`` like ``v3.0.0``), regardless of channel.

        Used to mirror the currently running version to the hub.  Returns None
        when the release carries no installer asset; raises RuntimeError (as
        ``check_github`` does) when GitHub cannot be reached or the tag does
        not exist.
        """
        tag = tag if tag.startswith("v") else f"v{tag}"
        data = self._get_json(f"{C.GITHUB_API}/releases/tags/{tag}")
        if not isinstance(data, dict) or data.get("draft"):
            return None
        return self._release_info(data)

    def _release_info(self, rel: dict) -> UpdateInfo | None:
        assets = {a.get("name", ""): a for a in rel.get("assets", []) if isinstance(a, dict)}
        manifest = None
        if "latest.json" in assets:
            try:
                with urllib.request.urlopen(self._request(assets["latest.json"]["url"], "application/octet-stream"),
                                            timeout=self.timeout) as resp:
                    manifest = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("latest.json download failed: %s", exc)
        info = UpdateInfo.from_manifest(manifest or {}, "github")
        if not info.version:
            info.version = str(rel.get("tag_name", "")).lstrip("v")
        info.prerelease = bool(rel.get("prerelease"))
        info.notes = info.notes or str(rel.get("body", "") or "")
        info.published_at = info.published_at or str(rel.get("published_at", ""))
        setup = next((a for n, a in assets.items() if n.lower().endswith(".exe")), None)
        if setup:
            info.installer = info.installer or str(setup.get("name", ""))
            info.url = str(setup.get("url", ""))          # API asset URL works with a token
            info.size = info.size or int(setup.get("size", 0) or 0)
        if not info.installer:
            return None
        return info

    # ------------------------------------------------------------ download
    def download(self, info: UpdateInfo, progress: Progress | None = None) -> Path:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        target = self.download_dir / info.installer
        if target.exists() and info.sha256 and sha256_of(target) == info.sha256:
            return target
        if info.local_path and Path(info.local_path).exists():
            src = Path(info.local_path)
            total = src.stat().st_size
            done = 0
            with open(src, "rb") as fin, open(target, "wb") as fout:
                while chunk := fin.read(1 << 20):
                    fout.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        else:
            req = self._request(info.url, "application/octet-stream")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp, open(target, "wb") as fout:
                total = int(resp.headers.get("Content-Length") or info.size or 0)
                done = 0
                while chunk := resp.read(1 << 18):
                    fout.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if info.sha256:
            actual = sha256_of(target)
            if actual != info.sha256:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"checksum mismatch (expected {info.sha256[:12]}…, got {actual[:12]}…)")
        return target

    # --------------------------------------------------------------- install
    def install(self, installer: Path, restart: bool = True) -> None:
        args = [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                "/FORCECLOSEAPPLICATIONS"]
        if restart:
            args.append("/RESTARTAPPLICATIONS")
        log.info("launching installer: %s", " ".join(args))
        if sys.platform == "win32":
            subprocess.Popen(args, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        else:  # pragma: no cover
            subprocess.Popen(args)

    # ---------------------------------------------------------------- mirror
    def mirror_to_lan(self, info: UpdateInfo, installer: Path, lan_dir: Path | None = None) -> Path:
        """Copy an installer + manifest into the hub so colleagues update offline."""
        target_dir = Path(lan_dir or self.lan_dir or "")
        if not str(target_dir):
            raise RuntimeError("no Team Hub folder configured")
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / installer.name
        shutil.copy2(installer, dest)
        manifest = info.to_manifest()
        manifest["installer"] = installer.name
        manifest["sha256"] = sha256_of(dest)
        manifest["size"] = dest.stat().st_size
        manifest["mirrored_by"] = os.environ.get("USERNAME", "")
        write_json_atomic(target_dir / "latest.json", manifest)
        # keep only the two newest installers on the share
        exes = sorted(target_dir.glob("*.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in exes[2:]:
            try:
                old.unlink()
            except OSError:
                pass
        return dest


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()
