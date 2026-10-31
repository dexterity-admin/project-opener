# Updates

Project Opener updates itself. Two sources are checked, in this order, every 4 hours and on demand
(*Updates → Check for updates*):

| Source | What it needs | Why |
|---|---|---|
| **1. LAN mirror** `<hub>/updates/latest.json` | a Team Hub folder | works without internet or GitHub access; one person mirrors, the whole office updates |
| **2. GitHub Releases** `dexterity-admin/project-opener` | a read-only token (*Settings → Updates*) because the repository is private | the canonical source, produced by CI |

The newest version found wins. The user is told where it came from.

## The manifest (`latest.json`)

Produced by `tools/make_manifest.py` in CI and attached to every release:

```json
{
  "version": "3.1.0",
  "installer": "ProjectOpener-Setup-3.1.0.exe",
  "sha256": "…",
  "size": 41234567,
  "published_at": "2026-11-07T09:12:00+00:00",
  "url": "https://github.com/dexterity-admin/project-opener/releases/download/v3.1.0/ProjectOpener-Setup-3.1.0.exe",
  "notes": "…CHANGELOG section for 3.1.0…",
  "min_version": "3.0.0",
  "prerelease": false
}
```

## Flow inside the app

1. `Updater.check()` reads the LAN manifest (if any) and asks the GitHub API for the latest release
   (`/releases/latest`, or `/releases` when the channel includes pre-releases). For GitHub it downloads
   the `latest.json` asset through the API with the token.
2. If `version` is newer than `project_opener.__version__`, a toast appears and the Updates page shows
   the notes with **Download update**.
3. `Updater.download()` streams the installer to `%APPDATA%\DexterityDesign\ProjectOpener\downloads\`
   (from the LAN folder or the GitHub asset URL) and **verifies the SHA-256**. A mismatch deletes the
   file and reports an error.
4. **Install and restart** runs the Inno Setup installer with
   `/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /RESTARTAPPLICATIONS`
   and quits. Inno Setup closes the running app, replaces the files in
   `%LOCALAPPDATA%\Programs\Project Opener`, and relaunches it.
5. **Mirror to Team Hub for colleagues** copies the verified installer and a fresh manifest into
   `<hub>/updates/` so everyone else updates over the LAN (only the two newest installers are kept).

## Getting a token (admins)

GitHub → *Settings → Developer settings → Fine-grained personal access tokens → Generate*:
repository access = only `project-opener`, permission *Contents: Read-only*. Paste it in
*Settings → Updates → Save token*. It is stored with Windows DPAPI, bound to the Windows account.

Most colleagues never need a token: one admin checks GitHub, downloads, clicks *Mirror to Team Hub*,
and everyone else gets the update from the LAN.

## Skipping and channels

*Skip this version* hides that version until a newer one appears. *Include pre-releases* opts into
releases marked pre-release in GitHub (CI can create them with the `prerelease` input).

## Manual fallback

Download `ProjectOpener-Setup-X.Y.Z.exe` from the release page (or the hub `updates/` folder), check it
against `SHA256SUMS`, and run it. Settings and the workspace are untouched by updates.
