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
python run.py            # or: python -m project_opener   (the 4.0 Qt Quick shell)
```

From source without `--data-dir` the app uses `%APPDATA%\DexterityDesign\ProjectOpener-v4dev` (seeded once
from the real folder), so an installed 3.2 keeps its own workspace. Useful flags: `--data-dir
U:\path\po-dev` (separate workspace and its own single-instance key; never a folder on C:),
`--minimised`, `--classic` (the 3.2 widgets UI, until 4.0 ships), `--version`. `PO_CLIQ_DRY_RUN=1` logs
Cliq messages instead of sending them.

## Tests

```powershell
python -m pytest            # every test, 180 s limit per test (pytest-timeout); QML smoke runs in a child process
$env:QT_QPA_PLATFORM="offscreen"; python tools\smoke_v4.py --out build\screens-v4   # every v4 page (what CI does)
$env:QT_QPA_PLATFORM="offscreen"; python tools\smoke_ui.py   # the 3.2 (--classic) pages
ruff check project_opener tests tools
```

`tools/smoke_v4.py` takes `PO_DEMO_ROOT`, `PO_DEMO_HUB`, `PO_DEMO_SERVER_ROOT` and `PO_DEMO_DRIVES` as
`tools/smoke_ui.py` does, so public captures show office-shaped paths and a demo drive map.

Tests set `PO_DATA_DIR` to a temp folder and disable the 1.x migration, so they never touch your
real workspace.

## Benchmark (`--bench`, a release gate)

The frozen exe measures any PC by itself, without the source or Python:

```powershell
# installed build (PowerShell; -Wait keeps the console until the summary is printed)
Start-Process -Wait -NoNewWindow "$env:LOCALAPPDATA\Programs\Project Opener\ProjectOpener.exe" "--bench"
# a one-folder build, writing the result to a folder of your choice
Start-Process -Wait -NoNewWindow .\dist\ProjectOpener\ProjectOpener.exe "--bench","--out","U:\bench"
# the summary into a file as well: with stdout redirected or piped the bench prints there, not to the console
& "$env:LOCALAPPDATA\Programs\Project Opener\ProjectOpener.exe" --bench | Out-File -Encoding utf8 bench-summary.txt
# from source
python -m project_opener --bench --out build\bench
```

It takes about two minutes; leave the PC alone while its window opens and closes the dock. It is harmless:

- it runs in a throwaway data folder under `%TEMP%` (deleted at the end), beside a running Project Opener
  (it never claims the single instance); it never imports this user's 1.x projects into it. The compiled QML
  goes to `%TEMP%\po-bench-qmlcache`: Qt keeps those files mapped until the process ends, so each run empties
  that one folder at its start rather than at its end;
- no Team Hub, presence, update check, capture, pill, tray or hot keys; the launcher is a dry run, so
  nothing is opened and no other window is read, moved or captured; its own window is the only one shown;
- the user's `settings.json` is read (never written) to say what the installed app runs at now.

What it reports (printed, and in `bench-<PC>-<date>-<time>.json` with a `.txt` copy of the summary, next to the
exe or in `%TEMP%` when that folder is not writable; `--out` takes a `.json` path or a folder):

- the machine: CPU, RAM, Windows, graphics adapter, screen size, scale and refresh rate;
- the render backend and the motion level the app would choose on a first start (`quick/motion.py`), and the
  level this user's saved settings run at;
- first frame (process start to the window's first frame, a first start: QML compiled, GPU probed);
- idle memory (private and working set) and CPU over 5 s on Home;
- the demo activity's dock opened 6 times at each level (rich, purposeful, off): the first frame after the
  click (the opening's response time), then frame mean and worst 1 % over the rest of the grow, as the runtime
  guard measures them (two openings over 33 ms mean or 120 ms worst 1 % reduce a level; docs/DESIGN.md,
  "Motion levels"), and the longest GUI-thread stall from a 5 ms heartbeat, then a verdict ("Rich motion holds
  on this PC.").

Exit code 0 on success, 1 when the bench failed (the reason is printed), 2 when the window could not load.
`QSG_RENDER_TIMING=1` in the environment adds Qt's per-frame timings to the app log (developer use).

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
