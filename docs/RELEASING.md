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
- An admin should open *Updates*, download, and click **Mirror to Team Hub for colleagues** so the
  whole office can update from the LAN without tokens or internet.

## Versioning

Semantic-ish: `MAJOR.MINOR.PATCH`. The updater compares numerically, so `3.10.0 > 3.9.0`.
`min_version` in the manifest is informational for now.

## Rolling back

Install the previous `ProjectOpener-Setup-X.Y.Z.exe` from its release page (or the hub `updates/`
folder, which keeps the two newest). Workspace data is forward-compatible within schema 3.
