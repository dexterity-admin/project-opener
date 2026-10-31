# Changelog

All notable changes to Project Opener. The version in `project_opener/__init__.py`
is the single source of truth; CI publishes a release when a new version lands on `main`.

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
- **In-app updates**: LAN mirror first, then GitHub Releases (private repo with a read-only token);
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
