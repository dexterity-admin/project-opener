"""Create the release manifest (latest.json) and SHA256SUMS for an installer.

    python tools/make_manifest.py dist/ProjectOpener-Setup-3.0.0.exe --notes CHANGELOG.md

The manifest is what the in-app updater reads (from a GitHub release asset or
from the Team Hub's updates/ folder).  See docs/UPDATES.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_opener import __version__  # noqa: E402
from project_opener.constants import GITHUB_OWNER, GITHUB_REPO  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def changelog_section(path: Path, version: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^## \[?{re.escape(version)}\]?[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("installer", type=Path)
    ap.add_argument("--notes", type=Path, default=ROOT / "CHANGELOG.md")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--version", default=__version__)
    ap.add_argument("--prerelease", action="store_true")
    args = ap.parse_args()
    inst = args.installer
    if not inst.exists():
        raise SystemExit(f"installer not found: {inst}")
    out_dir = args.out or inst.parent
    digest = sha256(inst)
    manifest = {
        "version": args.version,
        "installer": inst.name,
        "sha256": digest,
        "size": inst.stat().st_size,
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/v{args.version}/{inst.name}",
        "notes": changelog_section(args.notes, args.version),
        "min_version": "3.0.0",
        "prerelease": args.prerelease,
    }
    (out_dir / "latest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / "SHA256SUMS").write_text(f"{digest}  {inst.name}\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
