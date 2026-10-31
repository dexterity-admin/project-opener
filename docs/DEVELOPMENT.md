# Development

## Prerequisites

- Windows 10/11 (the app runs its core on any OS, but packaging and most features target Windows)
- Python 3.11 – 3.14 (CI uses 3.12)
- Inno Setup 6 or 7 for installers (`ISCC.exe`); not needed to run from source

## Set up

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python run.py            # or: python -m project_opener
```

Useful flags: `--data-dir C:\temp\po-dev` (separate workspace), `--minimised`, `--version`.

## Tests

```powershell
python -m pytest            # core, LAN hub and updater tests (no display needed)
python tools\smoke_ui.py    # opens every page with demo data and writes build\screens\*.png
$env:QT_QPA_PLATFORM="offscreen"; python tools\smoke_ui.py   # headless (what CI does)
ruff check project_opener tests tools
```

Tests set `PO_DATA_DIR` to a temp folder and disable the 1.x migration, so they never touch your
real workspace.

## Build

```powershell
.\tools\build.ps1                      # tests + icon + PyInstaller + Inno Setup + manifest + zip
.\tools\build.ps1 -SkipTests -SkipInstaller
```

Outputs in `dist\`: `ProjectOpener\` (one-folder build), `ProjectOpener-Setup-X.Y.Z.exe`,
`ProjectOpener-Portable-X.Y.Z.zip`, `latest.json`, `SHA256SUMS`.

## Project conventions

- `core/`, `lan/`, `update/` must stay Qt-free so they are testable and reusable.
- Views talk only to `AppContext`; never to the filesystem/network directly.
- Anything slower than a stat goes through `AppContext.run_async`.
- Colours and spacing come from `ui/theme.py` tokens; never hard-code colours in views (use
  `theme.current()`), so both themes and every accent keep working.
- Icons are Font Awesome 5 names via qtawesome (`fa5s.*`, `fa5r.*`, `fa5b.*`).
- Add a widget to its layout **before** `setVisible()`; avoid word-wrapped labels inside grid layouts
  (see ARCHITECTURE.md → Performance notes).
- Public behaviour changes get a CHANGELOG entry under the upcoming version.

## Adding a page

1. Create `ui/views/<name>.py` with `class XPage(Page)` and a unique `route`.
2. Register it in `MainWindow.__init__` (the `for cls in (...)` loop) and in `retheme()`.
3. Add a sidebar entry in `widgets/sidebar.py::NAV` if it should be navigable.

## Adding an item kind

1. Extend `ITEM_KINDS` and `guess_kind()` in `core/models.py`.
2. Teach `core/launcher.py` how to open it and `core/health.py` how to check it.
3. Add an icon mapping in `core/search.py::item_icon` and `ui/icons.py::KIND_ICONS`.
4. Add it to the type combo in `ui/widgets/dialogs.py::ItemEditor`.

## Debugging

- Logs: *Updates → Open log* or `%APPDATA%\DexterityDesign\ProjectOpener\logs\project-opener.log`.
- The last 400 log lines are shown live on the Updates page.
- Unhandled exceptions open a dialog with the traceback and are logged; the workspace is saved after
  every change, so nothing is lost.
