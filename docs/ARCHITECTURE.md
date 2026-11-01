# Architecture

Project Opener 3 is a Python 3.11+ / PySide6 (Qt 6) desktop application packaged with
PyInstaller and Inno Setup. The code is organised in four layers; **lower layers never import
higher ones, and only `ui` imports Qt widgets**.

```
project_opener/
├── __init__.py        __version__ (single source of truth for CI, installer and About page)
├── constants.py       names, paths, ports, GitHub repo, data folder resolution
├── app.py             bootstrap: logging, single instance, theme, crash guard, main window
├── core/              pure Python domain layer (tested without a display)
│   ├── models.py      Project, Item, LaunchSet, Origin + v1/v2 converters
│   ├── store.py       workspace.json persistence, backups, history, import/export
│   ├── settings.py    typed settings, DPAPI-encrypted secrets
│   ├── jsonio.py      atomic JSON writes, tolerant reads, JSONL
│   ├── pathvars.py    {VARIABLES}, drive-letter <-> UNC portability
│   ├── launcher.py    opening items (shell, apps with args, URLs, commands) -> LaunchReport
│   ├── health.py      ok / missing / offline / variable checks
│   ├── search.py      fuzzy ranking for the palette and grid
│   ├── winutil.py     DPAPI, mapped drives, Run key, Explorer, dark title bar
│   └── logging_setup.py
├── lan/
│   ├── hub.py         Team Hub on a shared folder (presence, publish, inbox, announcements, pulse)
│   └── presence.py    UDP broadcast beacon (optional accelerator)
├── update/
│   └── updater.py     LAN mirror + GitHub Releases, SHA-256 verify, silent install, mirror
└── ui/
    ├── theme.py       design tokens -> palette + generated QSS (dark/light/accent/density); the rules are in docs/DESIGN.md
    ├── icons.py       qtawesome wrapper, app icon, project icon catalogue
    ├── context.py     AppContext: services + thread pool + Qt signals (the only thing views talk to)
    ├── main_window.py sidebar + stacked pages, routing, shortcuts, tray, project menu
    ├── widgets/       common controls, cards, toasts, command palette, sidebar, dialogs, flow layout
    └── views/         home, projects, detail, team, updates, settings
```

## Data flow

1. `app.main()` creates `AppContext`, which loads `Settings` and `WorkspaceStore`
   (migrating 1.x data on first run) and builds the `PathResolver`, `Launcher`, `TeamHub` and
   `Updater` from the settings.
2. Views render from the store and subscribe to `AppContext` signals
   (`projects_changed`, `health_updated`, `hub_changed`, `peers_changed`, `update_*`).
3. Mutations go through the store (`add/update/remove/...`). The store saves atomically, rotates a
   backup, and notifies listeners; the context relays this as Qt signals so every open page refreshes.
4. Anything that touches the network or the filesystem beyond a quick stat runs on the global
   `QThreadPool` via `AppContext.run_async`, and results are marshalled back to the GUI thread.

## Key design decisions

- **No server.** Collaboration uses a shared folder the office already has. Each writer owns its own
  files (per-user names) so there is no locking; shared files are small and written atomically.
- **Portable paths.** Items are stored exactly as entered. When publishing or sending, drive letters are
  converted to UNC using *this* machine's drive map; when opening, `{VARIABLES}` and
  `{X_DRIVE}` variables are resolved for *that* machine.
- **Never guess.** The launcher reports *missing* / *failed* per item; health checks say *offline*
  only after a real port-445 probe fails. Nothing is silently skipped.
- **Crash-safe.** Every save is temp-file + rename, preceded by a timestamped backup (30 kept).
  A corrupt `workspace.json` is preserved as `workspace.corrupt.json` and the newest good backup is loaded.
- **Updates are verifiable.** The updater refuses an installer whose SHA-256 does not match the manifest,
  whether it came from GitHub or the LAN mirror.

## Performance notes (learned the hard way)

- Do not put word-wrapped `QLabel`s inside nested `QGridLayout`s in a scroll area; height-for-width
  propagation makes each layout pass cost seconds. Pages use box layouts.
- Always add a widget to its layout **before** calling `setVisible()`; showing an orphan widget creates a
  native top-level window.
- `ElidedLabel` paints its own text and keeps a constant size hint so re-eliding never re-triggers layout.

## Threads

| Work | Where | Result delivery |
|---|---|---|
| Path health (`health.check_project`) | thread pool | `health_updated(project_id)` |
| Hub heartbeat/status/peers | thread pool, every 60 s | `hub_changed`, `peers_changed` |
| UDP presence | 2 daemon threads | `peers_changed` |
| Update check/download | thread pool | `update_checked`, `update_progress`, `update_ready` |
| Launching items | GUI thread (fast, `os.startfile`) with a configurable pause between items | toast |

## Where things live at runtime

| Item | Path |
|---|---|
| Workspace | `%APPDATA%\DexterityDesign\ProjectOpener\workspace.json` |
| Settings | `...\settings.json` (token DPAPI-encrypted) |
| Backups | `...\backups\workspace-YYYYMMDD-HHMMSS-ffffff.json` |
| History | `...\history.jsonl` |
| Logs | `...\logs\project-opener.log` (rotating, 1 MB x 3) |
| Downloads | `...\downloads\ProjectOpener-Setup-X.Y.Z.exe` |
| Install | `%LOCALAPPDATA%\Programs\Project Opener\` (per-user, no admin) |
