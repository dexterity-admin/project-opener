# Changelog

All notable changes to Project Opener. The version in `project_opener/__init__.py`
is the single source of truth; CI publishes a release when a new version lands on `main`.

## 3.2.0 - 2026-11-01

### Added
- **The job number is the spine**: every card, row, palette hit, launch-sheet title, hub card and
  the project page's title read "P12513 · As-built isometrics", the number first in tabular figures
  (the client stands in when a job has no number; `Project.title`).
- **Drives on this PC** (Home): the paths of every project grouped by what they depend on (a drive
  letter, a `\\server` share, a `{VARIABLE}`), built from the health results. Only the roots that
  are down are listed, each with its pill (Not found, Server offline, Undefined variable), the
  letter's mapping ("Z: → \\nas01\Project"; a mapped letter counts under its server, so a server that
  is down appears once), which job uses it ("1 project · P12513" or "2 projects") and the office's
  verb ("Open P12513", or "2 projects" to open the Projects page filtered by that root); the
  reachable ones fold behind "N drives reachable". Needs attention keeps the paths a root does not
  explain (a file gone from a drive that answers).
- **Launch sets as a checklist**: items are numbered steps in their launch order under their group
  label, in the launch sheet and in the project page's Launch sets panel; the launch set editor has
  Move up / Move down and the order is saved with the set.
- **Revisions on the hub**: published cards show "rev 2" as a figure beside the name, and a cloned
  project's banner says which revision you have and which is available.
- **Activity as a register**: the Team Hub's Activity tab is grouped under each project with the
  columns Event · Rev · By · When; repeated launches by one person on one day fold into
  "opened 3× today".
- Home's drive map and Team pulse stack under each other below 960 px, and every page is checked
  (smoke test and unit test) to fit the 1040 × 660 minimum window.
- The Projects search understands `root:` ("root:\\nas01", "root:Z:", "root:{SERVER_ROOT}") to list
  the projects that depend on a drive, share or variable.
- **Launch sheet**: opening a project (card Open, "Open project", a launch set, the tray, a deep
  link, start-up) shows a sheet over the content area with one row per item whose status pill
  changes live as each item is tried (Opening… → Opened, Not found, Server offline, Undefined
  variable, Skipped, Failed), a footer with the counts and the elapsed time, and the project's
  launch sets as pills. It closes itself when everything opened and stays otherwise (× or Esc).
  Items now open on the worker thread, one launch after another, and report per-item progress.

### Changed
- Dropping onto a project page accepts files, folders, applications, web links and `cmd:` lines.
- One filled control per screen on Updates: "Download update" while an update is offered,
  "Install and restart" once it is downloaded, otherwise "Check for updates".
- The result toast after a launch is replaced by the launch sheet. The tray balloon summary is kept
  for launches made while the window is hidden or minimised.

## 3.1.0 - 2026-11-01

### Changed
- **New visual system ("Aurora, disciplined")**, documented in `docs/DESIGN.md`: one bundled typeface
  (Onest, with tabular figures), a single flat aurora-green accent, flat pastel colour fields, pill
  controls, 16 px cards with a 1 px edge and no shadow, outline icons (Phosphor), status pills with a
  pale tint and dark ink, one filled primary action per screen, sentence-case headings and no
  eyebrow labels. Light and dark are each composed, not inverted.
- Home shows the finding under the greeting and one divided KPI strip instead of four icon tiles.
- New flat app icon (folder with an arrow leaving it) and a rebuilt landing page: a working Home
  screen in the hero that plays the launch sequence, real screenshots, flat colour-field sections,
  no WebGL.
- Default accent moves from blue to aurora green; the old default is migrated on first start (a
  custom accent is kept).

### Fixed
- Theme changes no longer leave stale signal connections on destroyed pages (Ctrl+B, hub refresh
  and health updates after switching theme); "Follow Windows" now reacts to a live OS theme switch.
- Project page reloads on every visit, never re-creates a deleted project, and the notes editor keeps
  focus while autosaving.
- Single click on a card opens the project; the Open button launches (double-click no longer did both).
- Team Hub: unpublish, announce and inbox accept/dismiss report failures instead of pretending success;
  accepting an inbox item cannot create duplicates; UDP-discovered colleagues show immediately, even
  without a hub folder; "Share my activity" off also stops the heartbeat and beacon from sending the
  current project; a toast announces new revisions of cloned projects.
- Updates: the auto-check switch starts/stops the timer at once; skipped versions show as skipped with
  an Un-skip button (and a Clear row in Settings); "Mirror this version to the hub" works at any time
  and runs off the UI thread; "Open log" opens the log; update state survives a theme change.
- Toasts can carry an action button (Open Updates, Open inbox, Open project); the sidebar inbox badge
  survives collapsing; tray and deep-link launches honour the "confirm over N items" setting; palette
  actions always appear on an empty query.

### Added
- Settings: Start minimised switch. Announcements can expire after N days. Launch sets get an icon
  picker. Publishing asks for a hub description.

## 3.0.0 - 2026-10-31

Complete rebuild of the app ("Project Opener 3").

### Added
- **Launch bundles**: projects hold files, folders, links, applications (with arguments) and
  commands; **launch sets** open named subsets together; auto-launch at start-up; pin and favourite;
  tags, client and job number; colours and icons; notes saved automatically.
- **Command palette** (Ctrl+K) with fuzzy search across projects, launch sets, items and actions.
- **Dashboard** with quick launch, stats, "needs attention", team pulse, announcements and history.
- **Path health**: every item is checked in the background and flagged *not found*, *server offline*
  or *undefined variable* before you click.
- **Portable paths**: `{VARIABLES}` resolved per machine plus automatic drive-letter ↔ UNC mapping, so
  a project shared from one PC opens on another even when drive letters differ.
- **Team Hub** on any shared folder (no server): who is online, publish projects, clone, revision
  notices, send a project to a colleague's inbox, announcements, activity pulse.
- **LAN presence beacon** (UDP, optional) for near-instant online status.
- **In-app updates**: LAN mirror first, then GitHub Releases (public releases, token optional);
  SHA-256 verified; silent install and restart; one click to mirror a release for the whole office.
- **System tray** with quick launch, start with Windows, single instance, `projectopener://open/...`
  deep links, drag-and-drop to create projects or add items.
- **Themes**: dark, light or follow Windows; ten accent colours; comfortable/compact density.
- **Crash-safe storage** with atomic writes, 30 rotating backups and one-click restore; export/import.
- **Automatic migration** of Project Opener 1.x (`%APPDATA%\ProjectOpener`) and import of 2.x hub files.
- **Build & release**: PyInstaller + Inno Setup; GitHub Actions builds an installer on every push and
  publishes a release when the version number changes; GitHub Pages landing site.

### Changed
- Rewritten from a single 2,300-line script (PyQt6) into a layered package (PySide6, LGPL).
- Data now lives in `%APPDATA%\DexterityDesign\ProjectOpener` (schema 3).
