# Verification record - Project Opener 3.0.0

What was checked before calling 3.0.0 complete, and how. Dates are 31 Oct - 1 Nov 2026,
machine DDS-030 (Windows 10 Pro 19045), Python 3.14 locally, Python 3.12 in CI.

## 1. Feature parity with 1.x and 2.x

| 1.x / 2.x capability | 3.0 equivalent | Checked by |
|---|---|---|
| Project = list of files with checkboxes, notes, colour | Project with items (`enabled` flag), notes, colour + icon, tags, client/job | `tests/test_models.py::test_v1_migration` |
| Open checked items | *Open project* (enabled items) | `tests/test_pathvars_launcher.py::test_launcher_dry_run_reports` |
| Pin to top, last-opened, auto-launch at start | pinned_at, last_opened/open_count, auto_launch (+ settings switch) | `tests/test_store.py::test_sorting_pinned_first`, `test_v1_auto_migration` |
| Import/export JSON backup | Export workspace / Import (merge or replace), v1 backups accepted | `tests/test_store.py::test_export_import_bundle_merge_and_replace`, `test_import_v1_backup_format` |
| Dark mode | Dark / light / follow Windows + accent + density | screenshots `docs/screenshots/dark-*.png`, `light-*.png` |
| 2.x activities with typed items (exe + args) | Launch sets + item groups; `app` items with arguments | `tests/test_models.py::test_v2_migration_builds_launch_sets`, `tests/test_store.py::test_import_v2_file` |
| 2.x shared hub (per-user JSON, clone) | Team Hub: publish/clone with revisions, inbox, announcements, pulse, presence | `tests/test_hub_updater.py` (5 tests) |
| 2.x path variables | `{VARIABLES}` + `{X_DRIVE}` auto-mapping + UNC localisation | `tests/test_pathvars_launcher.py` |

## 2. Automated tests

`python -m pytest tests -q` → **36 passed** (models, store incl. corrupt-file recovery and backup
rotation, path variables, launcher, search, health, hub, updater incl. checksum rejection and LAN mirror).
`ruff check project_opener tests tools` → clean.

A midnight rollover during verification exposed one real bug (launches-today compared a UTC
timestamp with the local date); fixed in `store.stats()` and covered by `test_history_and_stats`.

## 3. UI smoke test

`tools/smoke_ui.py` seeds a demo workspace and a demo hub (two peers, one published project, one
inbox message, one announcement), opens every page in both themes and saves screenshots
(`docs/screenshots/`). It runs offscreen in CI on every push.

Performance issues found and fixed with it: a 3 s GUI stall per page render (word-wrapped labels in
nested grids) and ~0.5 s per item row (`setVisible` on an orphan widget). Page renders now take
well under 100 ms.

## 4. Packaging on this machine

`tools\build.ps1` → tests, icon, PyInstaller one-folder build, Inno Setup installer, manifest, zip.

| Artefact | Result |
|---|---|
| `dist\ProjectOpener\ProjectOpener.exe --version` | prints `Project Opener 3.0.0`, exit 0 |
| `dist\ProjectOpener-Setup-3.0.0.exe` | 35.0 MB, SHA-256 `0f1f0de4…f4c6a83` (in `SHA256SUMS` / `latest.json`) |
| `dist\ProjectOpener-Portable-3.0.0.zip` | 51.2 MB |

## 5. Real installation and migration

- Silent install (`/VERYSILENT`) into `%LOCALAPPDATA%\Programs\Project Opener`: success, no admin.
- The previous **Project Opener 2.3** install (different AppId, same folder) was uninstalled by the
  new installer's `[Code]` section; Programs & Features shows a single entry afterwards; the stray
  `Project Opener_SR2.exe` was removed from the folder.
- `projectopener://` URL protocol registered in HKCU; uninstall entry registered.
- First start of the installed app migrated the real 1.x data on this PC:
  `ANTEO (As-Built)` (5 items), `Mangala` (12 items), `DM - Piping GAD` (6 items), auto-launch flags
  preserved; the 1.x files were left untouched.
- Starting a second copy exited with code 0 after forwarding to the running instance (log line
  `another instance is running; forwarded and exiting`).

## 6. Continuous integration

Repository `dexterity-admin/project-opener` (private). Workflow `build.yml` on every push:
lint → tests → offscreen UI smoke → PyInstaller → frozen-exe start check → Inno Setup → manifest +
checksums + zip → artifacts; on `main` with an untagged version → tag + GitHub Release.

First run failed only at the frozen-exe check because PowerShell does not wait for a GUI-subsystem
process (`$LASTEXITCODE` was stale even though the exe printed its version). Fixed with
`Start-Process -Wait`. See the Actions tab for the green run and the `v3.0.0` release with
`ProjectOpener-Setup-3.0.0.exe`, `ProjectOpener-Portable-3.0.0.zip`, `latest.json`, `SHA256SUMS`.

## 7. Landing page

`site/` rendered in the desktop app's browser over `http://localhost:8765`: WebGL hero with orbiting
cards around the icon, sections revealing on scroll, no console errors, no horizontal scroll at
360 px. Not yet live: GitHub Free cannot serve Pages from a private repository (API returned 422);
publishing needs the public showcase repo described in RELEASING.md.

## 8. Known limits (stated, not hidden)

- GitHub update channel needs a read-only token per PC, or the LAN mirror.
- UDP presence may be blocked inbound by Windows Firewall; the hub heartbeat is authoritative.
- Second-instance forwarding takes ~3 s because Qt starts before the single-instance check.
- The UI smoke test exercises rendering and navigation, not every click path; dialogs were
  exercised manually through the demo workspace.
