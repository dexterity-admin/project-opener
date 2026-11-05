# Project Opener 4 - architecture

Written 5 November 2026 from `docs/V4-BRIEF.md` (the decisions), the two spikes
(`spikes/capture/REPORT.md`, `spikes/quick/REPORT.md`) and the Stage board. It is the contract
four builders work to in parallel:

| # | Builder | Owns |
|---|---|---|
| 1 | CORE+HUB | data model, migration, store, tasks, watchers, hub extensions, Cliq, Outlook, CAD profiles, and the facade's hub/tasks/watchers APIs |
| 2 | CAPTURE | the capture/restore engine, add-a-window, start-from-what's-open, snapshot persistence, and the facade's capture API |
| 3 | DESKTOP | the pill and its panel, global hotkeys, the window picker, the tray, quiet-time detection, Explorer verb and Send to, single-instance IPC, packaging and installer |
| 4 | SHELL | the Qt Quick application (Stage), the facade root and its activities/settings/ui APIs, motion, theme bridge, bootstrap |

Section 11 assigns every file to exactly one builder. A builder edits only its own files; when it
needs something from another layer it uses the contract below, and asks the owner for a change
rather than editing the file.

## 1. Rules carried over (unchanged from 3.x)

- Layers never reach upward: `core` imports nothing of ours above it; `lan` imports `core`;
  `capture` imports `core` only; `quick` and `desktop` import anything below; `ui` (3.2 widgets) is
  untouched and only `quick.facade` borrows `ui.context.AppContext` and `ui.theme`.
- Deterministic plumbing, no guessing: capture reports unidentified and ambiguous windows as
  such; the launcher reports missing/offline per item; nothing is silently skipped.
- Every write is temp file + `os.replace`; every reader tolerates a bad or foreign file. Hub files
  are owned by one writer each, except the small shared ones (last writer wins, record who).
- Every `open()` passes `encoding="utf-8"`; LF line endings; nothing writes to `C:` during
  development or tests (tests use `build/pytest-tmp`, manual runs use `--data-dir` on `U:`).

## 2. Package layout

New (N) and changed (C) modules. Unlisted 3.2 modules are kept unchanged (section 10).

```
project_opener/
├── __init__.py            C  __version__ = "4.0.0.dev0"
├── constants.py           C  SCHEMA_VERSION 4, v4 file names, capture cadence, hotkey ids, IPC key/protocol
├── app.py                 C  CLI: v4 by default; --classic (3.2), --add, --sendto, --snapshot, --start-from-open
├── app_v4.py              N  bootstrap of the Qt Quick shell (message handler, QApplication, IPC, engine, desktop)
├── ipc.py                 N  single-instance socket protocol 2 (JSON lines), deep-link parsing, forward/listen
├── core/
│   ├── models.py          C  + ActivityItem, Activity, Monitor, WindowPlacement, SnapshotEntry, Snapshot,
│   │                         Checkpoint, RunningMarker, TaskLink, Task, Notify, Watcher, WatchEvent, Group,
│   │                         LaunchProfile, RootObservation, HealthObservation, Workspace; Item.profile_id
│   ├── migrate.py         N  schema 3 -> 4 (launch sets -> activities), pure
│   ├── store.py           C  schema 4 load/save + migration, activities/profiles/watchers CRUD, item sync
│   ├── settings.py        C  v4 settings (motion, capture, pill, hotkeys, Explorer, Cliq token via DPAPI)
│   ├── snapshots.py       N  SnapshotStore: snapshots/<activity>.json (live + 10 checkpoints), running.json
│   ├── mentions.py        N  @mention parsing, expansion through groups, the @ picker's caret logic
│   ├── tasks.py           N  TaskStore over a tasks/ folder (hub or local), due text
│   ├── watchers.py        N  WatcherEngine: folder polling + diff, health, hub, time -> WatchEvent
│   ├── profiles.py        N  CAD launch profiles -> Command (exe, args, cwd, env)
│   ├── mail.py            N  Outlook drafts (bundle, task) via COM, mailto: fallback
│   ├── launcher.py        C  profiles; pluggable openers per extension (Office via COM from capture)
│   └── health.py          C  activities in health and roots_health
├── lan/
│   ├── hub.py             C  published activities, "for" targets, mention/task inbox entries, v4 dirs
│   ├── groups.py          N  groups.json (GroupBook)
│   ├── healthboard.py     N  watch/<user>.json write + office-wide merge
│   ├── delivery.py        N  Dispatcher + DeliveredLedger: every alert exactly once (toast, pulse, inbox, Cliq)
│   └── cliq.py            N  Zoho Cliq bot client + outbox retry
├── capture/               N  (builder 2) all COM on one thread
│   ├── win32.py              EnumWindows, placement, monitors, processes, foreground, GA_ROOT
│   ├── sources/              explorer.py (Shell), office.py (Excel/Word per window; open via COM),
│   │                         browser.py (UIA address bar), titles.py (patterns + items + Recent)
│   ├── identify.py           Identifier + IdentityCache, entry_key
│   ├── diff.py               pure: match items, change detection, new-since, restore order
│   ├── engine.py             CaptureEngine: the "po-capture" thread, pass cadence, request queue
│   ├── restore.py            Restorer: reopen in order, settle, match by identity, place
│   └── windows.py            add-a-window labels, start-from-open defaults
├── quick/                 N  the facade ("AppContext v4") the QML and the pill consume
│   ├── base.py               ApiBase, ro() property helper
│   ├── listmodel.py          DictListModel (the only list model type QML sees)
│   ├── facade.py             AppFacade: composes the 3.2 AppContext + sub-APIs; socket commands; deep links
│   ├── ui_state.py           app.ui: tokens, motion, route
│   ├── motion.py             backend + motion rule, runtime guard (pure)
│   ├── activities_api.py     app.activities
│   ├── settings_api.py       app.settings
│   ├── capture_api.py        app.capture        (builder 2)
│   ├── hub_api.py            app.hub            (builder 1)
│   ├── tasks_api.py          app.tasks          (builder 1)
│   └── watchers_api.py       app.watchers       (builder 1)
├── desktop/               N  (builder 3)
│   ├── integration.py        DesktopIntegration (wiring) + DesktopApi (app.desktop)
│   ├── pill.py               PillController: the focus-less QQuickWindow, edge snapping, per-layout position
│   ├── hotkeys.py            HotkeyManager: RegisterHotKey on a message window + native event filter
│   ├── picker.py             WindowPicker: per-monitor click-through overlay, WindowFromPoint/GA_ROOT
│   ├── tray.py               TrayController: QSystemTrayIcon + QMenu, activity dot
│   ├── quiet.py              full screen / presentation / RDP / Do not disturb
│   └── shellext.py           HKCU Explorer verb + SendTo shortcut
├── qml/                   N
│   ├── Main.qml              (4) window, rail, page loader by app.ui.route
│   ├── components/           (4) Rail, StatusPill, ActionButton, Sheet, MentionField, Toasts, Footlights
│   ├── pages/                (4) Home, Activity, Projects, Project, Hub, Updates, Settings
│   ├── sheets/               (4) LaunchDock, Confirm, ActivityEditor, StartFromOpen, AddChooser, Publish,
│   │                             Task, Watcher, AttachPath
│   └── desktop/              (3) Pill, PillPanel, PickerOverlay
└── ui/                       3.2 widgets UI, behind --classic until 4.0 ships; context.py and text.py change (4)
```

## 3. Data model and file formats

The dataclasses are written in full in `core/models.py` (every builder depends on them); this
section is their reference. All timestamps are ISO-8601 UTC (`now_iso()`), dates `YYYY-MM-DD`
local. Every `from_dict` tolerates missing and wrong-typed fields.

### 3.1 Workspace schema 4 (`%APPDATA%\DexterityDesign\ProjectOpener\workspace.json`)

```json
{
  "schema": 4, "app_version": "4.0.0", "saved_at": "...",
  "projects":   [ Project (as schema 3; items gain "profile_id"; launch_sets kept frozen) ],
  "activities": [ Activity ],
  "profiles":   [ LaunchProfile ],
  "watchers":   [ Watcher ],
  "migration":  { "from_schema": 3, "to_schema": 4, "at": "...", "from_app_version": "3.2.0",
                  "projects": 3, "launch_sets": 3, "activities_from_sets": 3, "activities_from_pinned": 1,
                  "items_copied": 4, "dangling_item_ids": 1 }
}
```

`Item` (unchanged + one field): `id, path, kind (file|folder|url|app|command), label, args,
enabled, group, added_at, profile_id`.

`ActivityItem(Item)`: + `project_id`, `source_item_id` - the project item it was drawn from
("" for captured things that belong to no project). The store copies `path, kind, label, args,
profile_id` from the project item whenever that project is updated, so an activity never drifts
from its job's paths.

`Activity`:

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | str | |
| `short_name` | str | the pill's label; "" -> `label` = name cut at 18 characters |
| `description`, `notes` | str | |
| `icon` | str | Phosphor name `ph.*`; migrated 3.x `fa5s.*` names kept verbatim (the shell maps them) |
| `color` | str | "" = the first project's colour |
| `project_ids` | list[str] | first = the activity's job (its spine in titles) |
| `items` | list[ActivityItem] | launch order |
| `owner`, `created_by` | str | logins |
| `pinned_at` | str or null | |
| `favorite` | bool | |
| `capture_enabled` | bool | per-activity capture switch (global: `Settings.capture_enabled`) |
| `resume_on_start` | bool | offer the Resume band after an unclean shutdown; never automatic |
| `created_at`, `updated_at`, `last_opened`, `open_count` | | |
| `origin` | Origin | as projects: local / team / inbox / import, published id, revision |

`LaunchProfile`: `id, name, app (navisworks|microstation|autocad|caesar|other), exe, args
({VARIABLES} and {ITEM}), cwd, env {}, description, author, published_id, updated_at`.

`Watcher`: `id, name, kind (folder|health|hub|time), target, events[], interval_s (>= 10),
params {}, notify {toast, mentions[], cliq_dm, cliq_channel}, activity_id, project_id, enabled,
created_by, created_at`. Events per kind: folder `new|changed|gone`; health `down|up`; hub
`published|task_assigned|task_done|mention`; time `due|stale|reminder`. Folder params: `pattern`
(glob, "*"), `recursive`; time params: `at`, `every_days`, `stale_days`, `task_id`.

### 3.2 Local runtime files (under the data folder)

| File | Format | Writer |
|---|---|---|
| `snapshots/<activity_id>.json` | `{"schema": 1, "activity_id", "live": Snapshot or null, "checkpoints": [Checkpoint, newest first, max 10], "ignored": [entry key], "left_out": [entry key]}` (`ignored`: Ignore in the pill's list, this activity only; `left_out`: unticked in "Save N new as items") | `SnapshotStore` (in memory; one background writer thread in the app) |
| `running.json` | `{"schema": 1, "markers": [RunningMarker]}` | `SnapshotStore.mark_running/touch_running/clear_running` |
| `tasks/<id>.json` | Task (only when no hub is configured) | `TaskStore` |
| `watch-state/<watcher_id>.json` | `{"files": {name: [size, mtime]}, "listed_at"}` | `WatcherEngine` |
| `alerts.jsonl` | one WatchEvent per line + `"read"` | `Dispatcher` |
| `cliq-outbox.jsonl` | queued Cliq messages | `CliqClient` |
| `backups/pre-v4-workspace-<stamp>.json` | the schema-3 file as it was before migration; never rotated | `WorkspaceStore` |
| `history.jsonl` | as 3.x, v4 rows add `activity_id`, `activity` | `WorkspaceStore.record_activity_launch` |

`Snapshot`: `activity_id, taken_at, full, monitors[Monitor{device, rect, work, dpi, primary}],
entries[SnapshotEntry], session_start` (the run's first pass; that pass stamps what was already open with
exactly this time, so `first_seen > session_start` means "opened while the activity ran"; "" in older files).

`SnapshotEntry`:

| Field | Notes |
|---|---|
| `key` | identity, stable across passes: `path:<lower-case path>`, `url:<url>`, or `win:<process>\|<title>` (`capture.identify.entry_key`) |
| `status` | `identified` (a proven path/URL) / `ambiguous` (several `candidates`) / `unidentified` / `unsaved` |
| `kind`, `path` | item kind and the path or URL; "" unless identified |
| `title`, `process`, `exe`, `window_class`, `app` | what was seen; `app` is the friendly name |
| `identified_by` | `shell`, `office-com`, `uia`, `title+items`, `title+recent`, `title-path`, `manual` |
| `doc_name`, `candidates`, `note` | `note`: "active tab only", "Protected View", "unsaved - cannot be restored" |
| `item_id` | the activity item it matches; "" = new (offered by "Save N new as items") |
| `placement` | `WindowPlacement{show_cmd, normal_rect, window_rect, monitor, monitor_rect}` |
| `hwnd`, `pid` | runtime only |
| `first_seen` | |

`Checkpoint`: `id, activity_id, taken_at, kind (manual|auto|close), label, snapshot`.
`RunningMarker`: `activity_id, started_at, last_seen, pid, process_started, host`.

### 3.3 Hub (`_ProjectOpenerHub/`, hub schema 2; readers accept 1 and 2)

```
hub.json                   + "schema": 2 once a 4.x PC initialises it (3.2 ignores the number)
users/<user>.json          + "email", "cliq_linked": bool, "current_activity"   (heartbeat as 3.x)
groups.json                {"schema": 1, "groups": [Group{name, members[], color, created_by, updated_by, updated_at}]}
published/<id>.json        project:  as 3.x + "type": "project", "for": ["yokesh", "checkers"]
                           activity: {"schema": 2, "type": "activity", "published_id", "author", "author_name",
                                      "published_at", "revision", "description", "for": [...],
                                      "activity": Activity (paths portable), "projects": [{id, title, job_number}]}
inbox/<user>/<id>.json     project/activity as 3.x (+ "kind", "activity" for activities);
                           mention: {"schema": 2, "id", "kind": "mention", "from", "from_name", "to", "sent_at",
                                     "text", "link"}
                           task:    same with "kind": "task", "task_id"
tasks/<id>.json            Task {schema, id, title, owner, due, created_by/at, updated_by/at, done_at, done_by,
                                 link{kind, local_id, published_id, title, job_number}, note, mentions[]}
watch/<user>.json          HealthObservation {schema, user, host, ts, roots[{root, status, since, jobs[], items}]}
delivered/<user>.json      {"keys": {event_key: ts}} newest 2,000
profiles/<id>.json         shared LaunchProfile
announcements.json         items gain "mentions": [...]
pulse/<user>.jsonl         rows gain "kind" (launched|published|sent|task|mention|watch), "mentions", "task_id",
                           "activity" - 3.2 reads "event" and "detail" as before
updates/                   unchanged
```

`for` and mentions hold logins and group names without "@", lower case
(`core.mentions.normalise_targets`); readers expand groups one level (`mentions.expand`) and drop
unknown names. A 3.2 PC skips every v4 file it does not understand: `published()` needs a
`"project"` key and `inbox()` needs a `"project"` key, so activity and mention files are invisible
to it rather than errors.

Concurrency: `tasks/<id>.json` - anyone writes (everyone equal), last writer wins, `updated_by`
records who; `groups.json` - anyone, re-read then write one change; `watch/<me>.json`,
`delivered/<me>.json` - only me.

## 4. Migration rules (3.x -> 4)

Implemented and tested in `core/migrate.py` (`tests/test_v4_models.py`). Triggered by
`WorkspaceStore` on load when `schema < 4`; also applied to restored backups and imported bundles
through `_apply`.

1. A copy of the schema-3 `workspace.json` goes to `backups/pre-v4-workspace-<stamp>.json`
   before the first schema-4 save. Its name does not match the rotation glob, so it is never deleted.
2. Projects stay exactly as they were. Items gain `profile_id = ""`.
3. Every launch set of every project becomes one activity: the set's id (a fresh id only on a
   collision), name and icon; the project's colour; `project_ids = [project.id]`; the set's items as
   `ActivityItem` copies in the set's order, linked by `project_id`/`source_item_id`. Launch sets
   ignored `enabled` in 3.x, so the copies are all enabled. A set listing the same item twice keeps
   one. Ids that pointed at no item are dropped and counted (they opened nothing in 3.x either).
   Empty sets still become (empty) activities. Names are not de-duplicated: the job spine
   distinguishes "P12513 · Checking" from "DM-GAD · Checking".
4. A pinned project with no launch sets also becomes one activity (its name, icon, colour, pin
   time and enabled items), so Home's stage is not empty for people who never made a set.
5. Launch sets stay on the projects, frozen (v4 never edits them), so a 3.2 PC reading the same
   workspace, or a project published from 4.0, still has them. `auto_launch` stays a project flag.
6. The report (counts) is stored in `workspace.json` under `migration`. A schema-4 file is never
   migrated again.
7. Settings: new keys take their defaults; nothing is renamed. History, logs and backups are
   untouched. The hub needs no migration (section 3.3).

Open for builder 1: `import_bundle` of a 3.x export should run the same rules for the imported
projects; `export_bundle` should add `activities`.

## 5. Capture and restore (builder 2)

From the spike, adopted as design rules:

- Cadence: `EnumWindows` every `capture_interval_s` (3 s); identify only windows whose
  `(hwnd, title, class, pid)` is new; full re-identification every 30 s and on a display change;
  skip a pass when the previous took over a third of the interval. Write the live snapshot only on
  change and at most every 10 s; refresh the RunningMarker every 60 s.
- Sources in order: Shell (Explorer) -> Excel/Word per window via `AccessibleObjectFromWindow`
  (never "the" ROT instance) -> UIA address bar (browsers, active tab only) -> title + items +
  Recent. Exactly one candidate or it is ambiguous.
- Exclusions: this process's windows (the pill, the picker, the main window), tool and cloaked
  windows, shell classes, `Settings.capture_ignore` rules.
- Restore: launch order, Office through COM, folders through `explorer.exe`, URLs through the
  recorded browser with `--new-window`, the rest through the launcher (variables, profiles); match
  new windows by identity, title similarity only for title-identified apps; place each as soon as it
  matches; never touch a window it did not open.
- Running markers: written on `startActivity`, cleared on `endActivity`. On start, a marker whose
  pid is not this process is stale: `ActivitiesApi` shows the Resume band for it (if the activity's
  `resume_on_start` is on) with its latest snapshot (`SnapshotStore.latest`).
- `capture.sources.office.open_document` is registered with the launcher as the opener for Office
  extensions (`Launcher` gains `openers: dict[ext, callable]`, builder 1), so 3.x-style launches of
  share files avoid Protected View too. The launcher calls it on a pool thread; it must
  `CoInitialize` there (the pool is not the capture thread).

## 6. Threading model

| Work | Thread | How results come back |
|---|---|---|
| QML, every facade property/model/signal | GUI thread | - |
| Launching items, path health, hub heartbeat/refresh, update check (3.2) | global `QThreadPool` (2-6) via `app.run_async` | `done` callback on the GUI thread |
| Hub v4 refresh (groups, tasks, mentions, published activities), Cliq sends, Outlook drafts | pool via `run_async`; Outlook/Office jobs `CoInitialize`/`CoUninitialize` around their COM | callbacks |
| Capture passes, add-a-window identification, start-from-open enumeration, restore | the single `po-capture` thread (`CaptureEngine`), `CoInitializeEx(COINIT_APARTMENTTHREADED)`; requests through a `queue.Queue`; restore pauses passes | `EngineCallbacks` wrapped with `app.run_on_gui` |
| Watchers | a `QTimer` every `WATCH_TICK_S` (15 s) in `WatchersApi` schedules `WatcherEngine.tick` on the pool (one tick at a time) | events -> `Dispatcher` (pool) -> toast on the GUI thread |
| Hotkeys | GUI thread: `WM_HOTKEY` arrives in the native event filter | direct calls |
| Picker hover | GUI `QTimer` (30 ms) reads the cursor; identification asked of the capture thread, cached | `hoverIdentified` |
| Quiet-time check | GUI `QTimer` (1 s) only while the pill would be visible; each probe on a short-lived worker thread | `quietChanged` (queued back) |
| Snapshot and running-marker writes | one `po-snapshot-writer` thread (`SnapshotStore(background=True)`); reads come from memory, the store's lock is never held across file I/O | - (`flush()`/`close()` at shutdown) |
| UDP presence | 2 daemon threads (3.2) | `run_on_gui` |

Rules: no COM object crosses threads; no Python slot on the render thread (`frameSwapped` handlers
only record timestamps); a pool job never touches a QObject except through `run_on_gui`.

## 7. The facade contract ("AppContext v4")

QML sees one context property, `app` (`quick.facade.AppFacade`). Every list is a `DictListModel`
(roles below; never a QVariantList). Ids in roles are `fooId`; reserved names (`index`, `model`,
`color`, `text`, `enabled`, ...) are refused at construction. All slots are callable from QML and
from Python. Sub-objects never import each other; they call through `self.app.<name>`.

### 7.1 `app` (AppFacade, builder 4)

- Properties: `ui, activities, settings, capture, hub, tasks, watchers` (constant QObjects),
  `desktop` (set by `app_v4`, notify `desktopChanged`), `version`, `login`, `displayName`.
- Signals: `toast(title, body, level)`, `toastAction(title, body, level, button, route, payload)`,
  `showWindowRequested()`, `paletteRequested()`, `chooserRequested(paths)`, `desktopChanged()`.
- Slots: `handle_command(cmd)` (section 8), `start()`. Python: `run_async(fn, done, fail)`,
  `run_on_gui(fn)`, `open_link(kind, key)`, `shutdown()`, `set_desktop(api)`; `ctx` (the 3.2
  AppContext), `snapshots` (SnapshotStore).

### 7.2 `app.ui` (UiState, builder 4)

Properties: `tokens` (map of `ui.theme.Tokens`), `dark`, `motion` (rich|purposeful|off), `backend`
(rhi|software), `k` (duration scale 1 / 0.6 / 0), `ambient` (loops allowed), `route`,
`routePayload`, `minimumWidth` 1040, `minimumHeight` 660. Slots: `go(route, payload)`,
`setMotion(level)`, `reportDockFrames(meanMs, worst1Ms)`, `setTheme(mode)`. Signals:
`tokensChanged, motionChanged, routeChanged, motionReduced(message)`. Routes: `home, activity,
projects, project, hub, updates, settings`.

### 7.3 `app.activities` (ActivitiesApi, builder 4)

- Models: `activities` (activityId, name, label, icon, dotColor, spine, projectTitle, itemCount,
  openCount, lastOpened, lastOpenedText, pinned, running, captureOn, openNow, identifiedNow,
  needsPathNow, healthWorst, healthText, taskLine, ownerName, published); `projects` (projectId,
  name, title, spine, client, dotColor, icon, itemCount, activityCount, pinned, healthWorst,
  healthText, lastOpenedText, published); `items` (itemId, name, path, kind, group, projectId,
  projectTitle, health, healthLabel, profileName, itemEnabled, order); `dock` (order, name, path,
  group, status, statusLabel, message).
- Properties: `currentId`, `current` (map, activity roles), `resume` (map: activityId, title,
  count, takenAt, text; {} when none), `launching`, `launchProgress`, `launchSummary`.
- Slots: `refresh, select(id), open(id), answerConfirm(requestId, ok), openProject(id),
  create(name, projectId) -> id, edit(id, fields), remove(id), duplicate(id) -> id, togglePin(id),
  addPaths(id, paths), addProjectItem(id, projectId, itemId), removeItem(id, itemId),
  moveItem(id, itemId, toIndex), editItem(id, itemId, fields), resumeNow, dismissResume, closeDock,
  mailBundle(id), link(id) -> url`.
- Signals: `activitiesChanged, projectsChanged, currentChanged, resumeChanged, launchChanged,
  launchStarted(id), launchFinished(id, summary), confirmNeeded(requestId, id, count)`.
- `open(id)` = launch through `ctx.launcher` (the 3.2 queue; `LaunchRun` gains an activity) then
  `app.capture.startActivity(id)` when capture is on.

### 7.4 `app.capture` (CaptureApi, builder 2)

- Models: `live` (entryKey, status, kind, name, path, title, process, appName, identifiedBy,
  monitor, isItem, isNew, note, candidates) worst first; `checkpoints` (checkpointId, takenAt,
  takenText, kind, label, count, identified, isLatest); `startCandidates` (entryKey, ticked, name,
  path, appName, status, note, kind).
- Properties: `runningId, runningName, runningLabel, runningColor, state (idle|running|needs|
  paused|saved), openCount, identifiedCount, needsPathCount, newCount, lastCheckpointText,
  sinceCheckpoint, driveDown, globalEnabled`.
- Slots: `startActivity(id), endActivity, snapshotNow, saveNewAsItems, pause, resume,
  setGlobal(on), addForegroundWindow, addWindow(hwnd), identifyForPicker(hwnd),
  attachPath(entryKey, path), addAsApplication(entryKey), ignoreEntry(entryKey),
  selectActivity(id), restoreCheckpoint(id, checkpointId), restoreLatest(id),
  prepareStartFromOpen, setCandidateTicked(entryKey, on), startFromOpen(name, projectId) -> id`.
- Owner decisions of 5 November 2026: "Save N new as items" never adds by itself - `saveNewAsItems` fills
  `newCandidates` (entryKey, ticked, tickable, name, path, appName, status, note, kind, group, groupLabel,
  action; files, folders and pages opened since the start ticked, everything else unticked) and emits
  `saveNewRequested` (the main window opens `sheets/SaveNewSheet.qml`); `prepareSaveNew, setNewTicked(key, on),
  saveTicked() -> added` (unticked rows are left out for the activity). `newCount` counts every window that
  is not an item, ignored or left out. The pill's rows: `ignoreForActivity(key)`, `unignoreForActivity(key)`,
  `ignoreApp(key) -> app name` ("Always ignore this app": `{"process": exe}` in `Settings.capture_ignore`),
  `unignoreApp(key)`. Resume: `prepareResume(id)` fills `resumeCandidates` (as above plus monitor; groups
  items / during / other), `setResumeTicked(key, on)`, `restoreTicked(id)`; `ActivitiesApi.resumeNow` restores
  only the ticked rows when the sheet was prepared.
- Signals: `stateChanged, liveChanged, checkpointsChanged, checkpointSaved(id, count, time),
  addResult(ok, message, needsPath, entryKey), hoverIdentified(hwnd, ok, label),
  restoreProgress(done, total, label), restoreFinished(report), startCandidatesReady`.
- `state` drives the pill: running = colour dot; needs = amber ring (`needsPathCount > 0`), red
  ring (`driveDown`); paused = hollow dot; saved = "Saved · 12 things · 14:32" for 2 s after
  `checkpointSaved`, then back; idle = hidden unless pinned.

### 7.5 `app.hub` (HubApi, builder 1)

- Models: `peers` (login, displayName, role, host, online, doing, initials, hue, cliqLinked);
  `published` (publishedId, type, title, spine, author, authorName, revision, publishedAt,
  publishedText, forText, description, isMine, cloned, itemCount); `inbox` (messageId, kind,
  sender, senderName, sentAt, sentText, message, title, mentionsMe, link); `announcements`
  (announcementId, title, body, level, author, authorName, ts, tsText, mine); `groups` (groupName,
  members, memberCount, dotColor, updatedBy); `mentionCandidates` (login, displayName, role, online,
  isGroup, memberCount); `pulse` (ts, tsText, login, displayName, event, detail, mentionsMe);
  `register` (job, event, revision, by, when, whenText).
- Properties: `configured, reachable, statusText, peersOnline, inboxCount, mentionCount`.
- Slots: `refresh, setMentionQuery(text), mentionAt(text, cursor) -> {start, query},
  insertMention(text, cursor, login) -> {text, cursor}, publishActivity(id, description, for),
  publishProject(id, description, for), unpublish(publishedId), send(kind, localId, targets,
  message), announce(title, body, level, expires), removeAnnouncement(id), acceptInbox(id),
  dismissInbox(id), clonePublished(publishedId) -> localId, saveGroup(name, members, color),
  deleteGroup(name), groupFromProject(projectId) -> name`.
- Signals: `hubChanged, peersChanged, inboxChanged, groupsChanged, mentioned(from, text, link)`.

### 7.6 `app.tasks` (TasksApi, builder 1)

Models `mine`, `all` (taskId, title, owner, ownerName, due, dueText, overdue, done, doneAt, doneBy,
createdBy, createdByName, attachKind, attachId, attachTitle, jobNumber, note, mine). Properties
`openCount, mineOpenCount, groupBy`. Slots `refresh, setGroupBy(owner|job), create(title, owner,
due, attachKind, attachId) -> id, edit(id, fields), setDone(id, done), remove(id), mailTask(id),
lineFor(kind, localId) -> "Task: back-check lot 7, due Fri"`. Signals `tasksChanged,
taskDone(id, by)`.

### 7.7 `app.watchers` (WatchersApi, builder 1)

Models `watchers` (watcherId, name, kind, target, events, watcherEnabled, notifyText, lastHitText,
activityId, projectId), `alerts` (alertKey, ts, tsText, title, detail, level, link, unread,
watcherId), `roots` (rootName, status, statusLabel, mapping, uses, seenBy, since, sinceText,
jobsAffected). Property `unreadCount`. Slots `create(kind, target, events, params, notify) -> id,
edit(id, fields), remove(id), setEnabled(id, on), markRead(alertKey), recheckRoots`. Signals
`watchersChanged, alertsChanged, rootsChanged, alert(title, body, level, link)`.

### 7.8 `app.settings` (SettingsApi, builder 4)

Slots `value(key) -> var`, `setValue(key, value)`, `setCliqToken(token)`, `testCliq()`,
`browseFolder(title, start) -> path`, `browseFile(title, start, filters) -> path`, `variables() ->
map`. Property `hasCliqToken`. Signals `changed(key)`, `cliqTested(ok, message)`. Keys are
`core.settings.Settings` field names; `setValue` routes side effects (hub/variables/updates ->
`ctx.apply_settings`; capture keys -> `app.capture`; pill/hotkey/Explorer keys -> `app.desktop`).

### 7.9 `app.desktop` (DesktopApi, builder 3)

Properties `pillVisible, panelOpen, quiet, hotkeyStatus (key -> {keys, ok, error}),
explorerVerbInstalled, sendToInstalled`. Slots `togglePanel, showPanel, hidePanel, startPicker,
cancelPicker, setPillPinned(on), applyHotkeys, setShellEntries(on)`. Signals `pillChanged,
quietChanged, hotkeysChanged, shellEntriesChanged, pickerFinished(hwnd)`.

The pill's QML (`qml/desktop/Pill.qml`) is loaded by `PillController` into its own window with
the context properties `app` and `pill`; it reads `app.capture` for everything it shows.

## 8. Native integration contract

### 8.1 Command line

| Flag | Meaning |
|---|---|
| (none) | the Qt Quick shell (since integration). From source, without `--data-dir`, it uses `%APPDATA%\DexterityDesign\ProjectOpener-v4dev` (seeded once from the real folder) so development never migrates the workspace an installed 3.2 uses; `--classic` from source uses the same folder |
| `--classic` | the 3.2 widgets UI, until 4.0 ships (then it can be removed); `--v4` is kept as a no-op for old shortcuts |
| `--add PATH...` | add to the running activity (Explorer verb); implies v4 |
| `--sendto PATH...` | Send to > Project Opener; implies v4 |
| `--snapshot` | checkpoint the running activity; implies v4 |
| `--start-from-open` | open the Start-from-what's-open sheet; implies v4 |
| `--minimised`, `--data-dir`, `--version` | as 3.2; `--data-dir` also gives the instance its own single-instance key (two test users on one PC) |
| `projectopener://open/<project>` | 3.x project link (kept) |
| `projectopener://activity/<id or name>` | open the activity's page |
| `projectopener://task/<id>` | the hub's Tasks tab at that task |
| `--quit-after MS` | hidden; quit after MS (smoke tests) |
| env `PO_UI=quick` / `PO_UI=classic` | force the shell / the 3.2 UI; `PO_CLIQ_DRY_RUN=1` logs Cliq messages instead of sending them (testing) |

### 8.2 Single-instance socket (`ipc.py`)

Key `DexterityDesign.ProjectOpener.v4` (`SINGLE_INSTANCE_KEY_V4`; the 3.2 key stays for the
widgets UI). Protocol 2: one JSON object per line, `{"v": 2, "cmd": ...}` with `cmd` in `show`,
`open` (+`link`), `add` (+`paths`), `sendto` (+`paths`), `snapshot`, `start-from-open`. Protocol
1 lines (`show`, bare links) are still accepted. The receiving instance calls
`AppFacade.handle_command`: add/sendto go to the running activity or, with none running, raise
the window and emit `chooserRequested(paths)`.

### 8.3 Hotkeys

| Key (default) | Id | Action |
|---|---|---|
| Ctrl+Alt+S | `HOTKEY_SNAPSHOT` 0xB001 | `app.capture.snapshotNow()` |
| Ctrl+Alt+A | `HOTKEY_ADD_WINDOW` 0xB002 | `app.capture.addForegroundWindow()`; twice within 1 s -> `app.desktop.startPicker()` |
| Ctrl+Alt+P | `HOTKEY_PANEL` 0xB003 | `app.desktop.togglePanel()` |
| Ctrl+Alt+K | `HOTKEY_PALETTE` 0xB004 | `app.paletteRequested()` |

Configurable in `Settings.hotkeys`; registered with `MOD_NOREPEAT`; a refused registration is
shown with Windows' error text in Settings > Snapshot.

### 8.4 Explorer and installer

- Verb: `HKCU\Software\Classes\*\shell\ProjectOpener.AddToActivity` and
  `...\Directory\shell\ProjectOpener.AddToActivity`, `MUIVerb` "Add to running activity",
  command `"<exe>" --add "%1"`. The running instance batches `add` commands that arrive within
  500 ms (one process per selected file).
- Send to: `%APPDATA%\Microsoft\Windows\SendTo\Project Opener.lnk` -> `"<exe>" --sendto`.
- The installer writes both (task "Explorer entries", default on) and removes them on uninstall;
  the app can add/remove them from Settings > Snapshot.
- PyInstaller (`project_opener.spec`): QtQml and QtQuick are no longer excluded; `qml/` ships as
  data; pywin32, comtypes and psutil are hidden imports; comtypes' generated UIA module must be
  pre-generated at build time (note in the spec).

### 8.5 Pill window

`Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus`, plus
`WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` set natively; per-monitor DPI; position saved per monitor
layout in `Settings.pill_positions`; hidden in quiet time (`desktop.quiet`), when there is nothing
to say, and when `Settings.pill_enabled` is off.

## 9. Motion and theme

- Tokens: `ui.theme.build_tokens(dark, accent, density)` exported as `app.ui.tokens` (a map;
  QML property names cannot start with a capital, so components bind `readonly property var tk:
  app.ui.tokens`). No raw colours in QML.
- Motion: `quick.motion` (pure, tested). Backend: software when the GPU probe fails, on the
  Basic Render Driver, or in a remote session. Level for `auto`: off in remote desktop;
  purposeful with software rendering, a screen at or below 1366x768, "Show animations" off or on
  battery; rich otherwise. Runtime guard: two dock openings in a row over 33 ms mean or 120 ms
  worst 1 % drop one level (saved in `Settings.motion_reduced_to`, said once), never climbing back
  automatically. Ambient loops only in rich and only while the window is active. Every duration is
  `app.ui.k * ms`; with `k = 0` every screen is complete and static.

## 10. Kept from 3.2 unchanged

`core/jsonio.py, pathvars.py, search.py, winutil.py, logging_setup.py`; `lan/presence.py`;
`update/updater.py`; `ui/theme.py` (tokens, contrast, tint); the whole 3.2 widgets UI
(`ui/main_window.py`, `ui/views/*`, `ui/widgets/*`, `ui/icons.py`) as the default UI until the
Quick shell replaces it at integration; `tools/*`; the 3.2 hub files and their formats; the
launch queue, health scheduling, hub refresh, presence and update flows of `ui/context.py`
(reused by the facade); the deep link `projectopener://open/<project>`; backups, history,
corrupt-file recovery and 1.x/2.x migration.

## 11. File ownership

"A" = finished by the architect in this skeleton; the named builder owns every later change.

| File | Owner | State |
|---|---|---|
| `project_opener/__init__.py` | 4 | A (version 4.0.0.dev0); only the release bump changes it |
| `project_opener/constants.py` | 1 | A; frozen for the build: other builders keep new constants in their own modules |
| `project_opener/app.py` | 4 | A (flags, routing to app_v4) |
| `project_opener/app_v4.py` | 4 | A (working bootstrap) |
| `project_opener/ipc.py` | 3 | A (protocol, forward, server; batching of `add` is builder 3's) |
| `project_opener/core/models.py` | 1 | A (complete) |
| `project_opener/core/migrate.py` | 1 | A (complete) |
| `project_opener/core/store.py` | 1 | A (schema 4, activity CRUD, sync); import/export of activities to do |
| `project_opener/core/settings.py` | 1 | A (all v4 keys); new keys by request to builder 1 |
| `project_opener/core/mentions.py` | 1 | A (complete) |
| `project_opener/core/snapshots.py` | 2 | A (complete) |
| `project_opener/core/tasks.py` | 1 | stub |
| `project_opener/core/watchers.py` | 1 | stub |
| `project_opener/core/profiles.py` | 1 | stub |
| `project_opener/core/mail.py` | 1 | stub |
| `project_opener/core/launcher.py` | 1 | to change (profiles, `openers`, activity items) |
| `project_opener/core/health.py` | 1 | to change (activities) |
| `project_opener/lan/hub.py` | 1 | stubs added (v4 section) |
| `project_opener/lan/groups.py` | 1 | stub |
| `project_opener/lan/healthboard.py` | 1 | stub |
| `project_opener/lan/delivery.py` | 1 | stub |
| `project_opener/lan/cliq.py` | 1 | stub |
| `project_opener/quick/hub_api.py` | 1 | stub (contract fixed) |
| `project_opener/quick/tasks_api.py` | 1 | stub (contract fixed) |
| `project_opener/quick/watchers_api.py` | 1 | stub (contract fixed) |
| `project_opener/capture/__init__.py` | 2 | A |
| `project_opener/capture/win32.py` | 2 | stub |
| `project_opener/capture/sources/__init__.py` | 2 | A |
| `project_opener/capture/sources/explorer.py` | 2 | stub |
| `project_opener/capture/sources/office.py` | 2 | stub |
| `project_opener/capture/sources/browser.py` | 2 | stub |
| `project_opener/capture/sources/titles.py` | 2 | stub |
| `project_opener/capture/identify.py` | 2 | stub (entry_key, IdentityCache done) |
| `project_opener/capture/diff.py` | 2 | stub |
| `project_opener/capture/engine.py` | 2 | stub |
| `project_opener/capture/restore.py` | 2 | stub |
| `project_opener/capture/windows.py` | 2 | stub |
| `project_opener/quick/capture_api.py` | 2 | stub (contract fixed) |
| `project_opener/desktop/__init__.py` | 3 | A |
| `project_opener/desktop/integration.py` | 3 | stub (DesktopApi contract fixed; `start` is a no-op) |
| `project_opener/desktop/pill.py` | 3 | stub |
| `project_opener/desktop/hotkeys.py` | 3 | stub |
| `project_opener/desktop/picker.py` | 3 | stub |
| `project_opener/desktop/tray.py` | 3 | stub |
| `project_opener/desktop/quiet.py` | 3 | stub |
| `project_opener/desktop/shellext.py` | 3 | stub |
| `project_opener/qml/desktop/Pill.qml`, `PillPanel.qml`, `PickerOverlay.qml` | 3 | placeholders |
| `installer/ProjectOpener.iss` | 3 | to change (Explorer entries task, uninstall cleanup) |
| `project_opener.spec` | 3 | A (Qt Quick, qml data, hidden imports); comtypes pre-generation to do |
| `project_opener/quick/__init__.py` | 4 | A |
| `project_opener/quick/base.py` | 4 | A |
| `project_opener/quick/listmodel.py` | 4 | A (complete) |
| `project_opener/quick/facade.py` | 4 | A (composition, commands, links) |
| `project_opener/quick/ui_state.py` | 4 | stub (tokens, route work) |
| `project_opener/quick/motion.py` | 4 | A (rule); `probe_machine` stub |
| `project_opener/quick/activities_api.py` | 4 | stub (contract fixed) |
| `project_opener/quick/settings_api.py` | 4 | stub (contract fixed) |
| `project_opener/ui/context.py` | 4 | to change (activity launches; the confirm-over-N question becomes `confirmNeeded`) |
| `project_opener/ui/text.py` | 4 | new when the 3.2 view helpers move out of the widgets (spike list) |
| `project_opener/qml/Main.qml`, `components/*`, `pages/*`, `sheets/*` | 4 | Main + Rail + StatusPill working; the rest placeholders |
| `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` | 3 | A (pywin32, comtypes, psutil; qml package data) |
| `tests/test_v4_models.py` | 1 | A |
| `tests/test_v4_core_*.py`, `tests/test_v4_hub_*.py` | 1 | new |
| `tests/test_v4_capture_*.py` | 2 | new (pure parts: diff, titles, windows, identify keys) |
| `tests/test_v4_desktop_*.py` | 3 | new (ipc batching, hotkey parsing, snapping, shellext against a fake registry root) |
| `tests/test_v4_quick_*.py`, `tools/smoke_v4.py` | 4 | new (facade with a seeded store; QML loads offscreen with no warnings; minimum window) |
| `docs/V4-ARCHITECTURE.md` | A | changes by agreement |
| `docs/ARCHITECTURE.md`, `DATA-FORMAT.md`, `LAN-HUB.md` | 1 | rewrite for 4.0 at integration |
| `docs/DESIGN.md` | 4 | v4 section (Stage, motion levels) |

Cross-builder seams (the only places two builders' code meet at run time):

| Seam | Caller -> callee | Contract |
|---|---|---|
| Activity launched | `ActivitiesApi.open` (4) -> `CaptureApi.startActivity` (2) | section 7.4 |
| Resume band | `ActivitiesApi` (4) reads `app.snapshots` (2's store) and calls `CaptureApi.restoreLatest` | 7.3, 7.4 |
| Office opener | `CaptureApi.start` (2) registers `office.open_document` on `ctx.launcher.openers` (1) | section 5 |
| Add from Explorer | `AppFacade.handle_command` (4) -> `ActivitiesApi.addPaths` / `chooserRequested` | 8.2 |
| Hotkeys, tray, pill | `desktop` (3) -> `app.capture.*`, `app.desktop.*`, `app.paletteRequested` | 7.4, 7.9, 8.3 |
| Task line on cards | `ActivitiesApi` (4) -> `TasksApi.lineFor` (1) | 7.6 |
| Drive down ring | `CaptureApi` (2) reads `app.watchers.roots` (1) for the running activity's roots | 7.4, 7.7 |
| Settings side effects | `SettingsApi.setValue` (4) -> `ctx.apply_settings`, `app.capture`, `app.desktop` | 7.8 |

## 12. Decisions the brief did not settle

1. Activities own copies of their items (with a link back to the project item), not references:
   captured things belong to no project, published activities must be self-contained, and the store
   keeps linked copies in step with project edits.
2. Snapshots, checkpoints and running markers live outside `workspace.json` (per-activity files),
   because they change every few seconds and every workspace save rotates a backup.
3. `resume_on_start` means "offer the Resume band for this activity", default on; restore is never
   automatic (brief 3.1 and 6).
4. A pinned project without launch sets becomes an activity at migration; unpinned ones do not.
5. Watchers are personal and local (in `workspace.json`); only their effects (pulse, inbox,
   `watch/`, `delivered/`) are on the hub.
6. Tasks without a hub live in `data_dir()/tasks/` in the hub format and move to the hub when one
   is configured.
7. The v4 shell uses its own single-instance key and, from source, its own data folder, so the
   development shell and an installed 3.2 never collide; integration keeps the v4 key.
8. One COM thread for capture and restore (restore pauses passes) rather than two COM threads.
9. Cliq: the endpoint and token type are left to builder 1 to verify (zapikey bot webhook vs OAuth
   refresh token); the default API base is the India data centre (`cliq.zoho.in`).
10. `4.0.0.dev0` parses as `(4, 0, 0, 0)` in `updater.parse_version`, equal to `4.0.0`: a PC
    running a dev build will not be offered 4.0.0. Acceptable for internal dev builds; do not
    publish a dev build to the hub's update mirror.
