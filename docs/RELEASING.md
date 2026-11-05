# Releasing

Releases are produced by GitHub Actions (`.github/workflows/build.yml`). A maintainer only has to
bump one number.

## Every push

- Lint, unit tests, headless UI smoke test, PyInstaller build, Inno Setup installer, portable zip,
  `latest.json`, `SHA256SUMS`.
- All of these are uploaded as workflow **artifacts** (kept 30 days) for every branch and pull
  request, so any commit can be installed and tried.

## Publishing a release

1. Add a section to `CHANGELOG.md` for the new version (it becomes the release notes and the in-app
   update notes).
2. Set `__version__` in `project_opener/__init__.py` **and** `version` in `pyproject.toml`.
3. Push to `main`.

If no tag `vX.Y.Z` exists for that version, the workflow creates the tag and publishes a GitHub
Release with the installer, portable zip, manifest and checksums. Pushing an existing version just
rebuilds artifacts; nothing is released twice.

Pre-release: run the workflow manually (*Actions → build → Run workflow*) with *prerelease* ticked.

## After the release

- Clients with a token see the update within 4 hours (or immediately via *Check for updates*).
- An admin should open *Updates*, download, and click **Copy X.Y.Z to the Team Hub** so the
  whole office can update from the LAN without tokens or internet. To put the version the office
  already runs on the hub (no newer download pending), use **Copy this version to the Team Hub**
  under *Update sources*; it fetches that version's installer from its release, verifies it and
  copies it. It is available only in an installed (frozen) build; a source run says why not.

## Delivery: the program runs from each PC, the share holds the installer

- The installer copies the app to each PC, per user, under `%LOCALAPPDATA%\Programs\Project Opener`
  (no administrator rights). The Start-menu shortcut and `projectopener://` links point there.
- The office share holds only the installer and the update mirror (`<hub>\updates\`: the two newest
  installers and `latest.json`). Never deploy the app folder or the portable zip's contents to the
  share for people to run in place.
- Reason (measured): the frozen exe started from the share takes about 60 s to reach Python, because
  Windows reads every bundled file over SMB; installed locally it starts in a few seconds.
- The user guide says the same in section 2.1 (Install).

## Landing page (GitHub Pages)

`pages.yml` deploys `site/` to https://dexterity-admin.github.io/project-opener/ on every push to
`main` that touches `site/`. The repository is **public** because GitHub Free only serves Pages from
public repositories; for that reason the repo must never contain internal hostnames, IP addresses,
share paths, credentials or personal data (docs use placeholder names such as `\\nas01\Project`).

The site is static (Three.js + GSAP from cdnjs) and can be previewed with
`python -I -m http.server 8765 --directory site`.

## Versioning

Semantic-ish: `MAJOR.MINOR.PATCH`. The updater compares numerically, so `3.10.0 > 3.9.0`.
`min_version` in the manifest is informational for now.

## Rolling back

Install the previous `ProjectOpener-Setup-X.Y.Z.exe` from its release page (or the hub `updates/`
folder, which keeps the two newest). Workspace data is forward-compatible within schema 3.
