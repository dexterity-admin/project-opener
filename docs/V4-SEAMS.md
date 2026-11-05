# Project Opener 4 - seams between builders

Requests for changes in files another builder owns (docs/V4-ARCHITECTURE.md section 11). Each
builder appends under its own heading; the owner answers or marks the item done.

## Builder 3 asks

1. **Builder 4 - `app_v4.py`: the multi-file Explorer race.** "Add to running activity" on N selected
   files starts N processes at once. With no instance running, every one of them fails `ipc.forward`
   and starts a full app. `ipc.py` now has `claim_instance(key)` (a named mutex) and
   `forward_retry(key, cmds)`. Suggested start of `app_v4.main`, before `InstanceServer.listen()`:
   `if ipc.forward(KEY, cmds): return 0` then
   `if not ipc.claim_instance(KEY): return 0 if ipc.forward_retry(KEY, cmds) else 1`.
2. **Builder 4 - `SettingsApi.setValue` side effects to `app.desktop`:**
   `pill_enabled`, `pill_rest_style`, `pill_pinned`, `pill_positions` -> `app.desktop.applyPill()`
   (a slot added to `DesktopApi`, beyond 7.9); `hotkeys`, `hotkeys_enabled` -> `app.desktop.applyHotkeys()`;
   `explorer_verb`, `sendto_entry` -> `app.desktop.setShellEntries(on)` (installs or removes both and
   saves both keys). `app.desktop.setPillPinned(on)` saves the setting itself.
3. **Builder 4 - Settings > Snapshot** can show `app.desktop.hotkeyStatus[name]` = `{keys, ok, error}`:
   `keys` is the canonical spelling ("Ctrl+Alt+S"); `error` is Windows' own text ("Hot key is already
   registered."), "Already used here for snapshot", the parse error for a typed combination, "No
   shortcut set" or "Turned off".
4. **Builder 4 - `quick/activities_api.py` lines 464 and 479:** `rstrip("\/")` is an invalid escape
   (`SyntaxWarning` at every start); `rstrip("\\/")` was meant.
5. **Builder 2 - `hoverIdentified(hwnd, ok, label)` label:** the picker shows the first line bold and the
   rest muted, split at the first `\n`, e.g. "AutoCAD · Drawing1" + `\n` + "No file path. You will be
   asked for it once.", or "Excel · Line list.xlsx" + `\n` + the path. One line is fine too. Until the answer
   arrives the frame is amber and shows the window title.
6. **Builder 2 - `live` rows, `status` values the pill's panel maps:** `identified` -> "Identified"
   (green), `unidentified` -> "Needs a path", `ambiguous` -> "Ambiguous", `unsaved` -> "Unsaved" (amber),
   `offline` -> "Server offline" (red). If a row on a down drive uses another marker, tell me and the
   panel will follow it. Rows are shown in model order (the contract's "worst first").
7. **Builder 2 - the "saved" state:** the pill flashes "Saved · N things · 14:32" for 2 s by itself on
   `checkpointSaved(id, count, "14:32")`, so `CaptureApi.state` does not need its own 2 s timer (a
   `saved` state is shown the same way if it is set).
8. **Builder 2 - the picker's click:** the picker calls `app.capture.addWindow(hwnd)` with a GA_ROOT
   hwnd; Ctrl+Alt+A calls `addWindow(hwnd)` with the window that was in front at the first press
   (after the 1 s double-press window) and only falls back to `addForegroundWindow()` when there was none.
9. **All - `Settings.pill_positions` format** (builder 1's field, written only by `desktop.pill`):
   `{layout_key: {"edge": "bottom|top|left|right", "offset": int, "monitor": QScreen name}}`; a
   positive offset is measured from the edge's start (left/top) to the pill's near side, a negative one
   from its end (right/bottom) to the pill's far side.

## Builder 1 asks

1. **Builder 4 - `ui/context.py`: launch profiles.** Build the launcher with the store's profile lookup in
   both `__init__` and `apply_settings`:
   `Launcher(self.resolver, delay_ms=self.settings.launch_delay_ms, profiles=self.store.profile)`.
   Until then `WatchersApi.start` installs the same lookup process-wide
   (`core.launcher.set_profile_lookup`), so profiles already work once the facade has started.
   Openers need nothing from you: `Launcher.openers` defaults to the shared registry
   `core.launcher.OPENERS`, so builder 2's Office opener survives a launcher rebuilt by `apply_settings`
   (`core.launcher.register_opener(ext, fn)` is the tidy way to add one).
2. **Builder 4 - `SettingsApi.testCliq` / `setCliqToken`.** The token is a Zoho Cliq **webhook token**
   (Cliq: Bots & Tools > Webhook Tokens), stored with `settings.cliq_token = token` (DPAPI). Test:
   `c = lan.cliq.CliqClient(st.cliq_api_base, st.cliq_bot, st.cliq_token, data_dir / C.CLIQ_OUTBOX_FILE)`;
   `uid = st.cliq_user_id or c.lookup_user(st.email)` - `lookup_user` returns "" when Cliq refuses the
   lookup (it is documented for OAuth only), then ask the user to paste their Cliq user id into
   `cliq_user_id`; then `c.dm([uid], "Project Opener test")` -> `cliqTested(res.ok, res.message)`. Run it
   with `app.run_async`. No other side effect is needed for the `cliq_*`, `email` or `notify_cliq_default`
   keys: `app.watchers.dispatcher()` rebuilds itself when they change and `app.hub` republishes them in the
   heartbeat.
3. **Builder 4 - `ActivitiesApi.mailBundle(id)`:**
   `draft = core.mail.bundle_draft(act, ctx.resolver, self.link(id))`, then
   `app.run_async(lambda: core.mail.open_draft(draft, ctx.settings.mail_client), done)`; `done(False)`
   means neither Outlook nor a `mailto:` handler opened (toast a warning).
4. **Builder 4 - toasts for mentions.** `app.hub.mentioned(from, text, link)` fires once per mention or
   task note (de-duplicated across the user's PCs); `HubApi` does not raise `app.toast` for it, so the
   shell should show it (a `toastAction` with "Open" -> `app.open_link(*ipc.parse_link(link))` fits).
   Received projects/activities, watcher alerts, publish results and task moves are toasted by my APIs
   through `app.toast` already.
5. **All - helpers the other sub-APIs may call (beyond section 7):** `app.watchers.dispatcher()`
   (the `lan.delivery.Dispatcher` for the current settings), `app.watchers.push_hub_events(...)`,
   `app.tasks.latest()` (tasks as of the last refresh), `app.hub.name_for(login)` (display name from the
   heartbeats), `app.hub.adopt_activity(activity, origin, projects)` (add a received activity with only
   provable project links).
6. **Contract note (architecture section 3.3 / 2):** `TeamHub.publish_activity` returns a
   `lan.hub.PublishedActivity` (not a `PublishedProject`) and `published_activities()` returns
   `list[PublishedActivity]` rather than dicts; with no hub the delivery ledger is `<data>/delivered.json`
   (the architecture's "or the local alerts.jsonl"); `Dispatcher` takes two optional extra arguments
   (`my_cliq_id`, `cliq_enabled`). Cross-PC links use names (`projectopener://activity/<name>`), because
   activity ids differ per PC; `open_link` already falls back to the name.

## Builder 4 answers

- Builder 3 ask 1 (`app_v4` instance race): done; `main` forwards, then `ipc.claim_instance`, and a
  process that loses the claim calls `ipc.forward_retry` and exits.
- Builder 3 ask 2 (`SettingsApi.setValue` side effects): done; `pill_enabled`, `pill_rest_style`,
  `pill_positions`, `hide_when_fullscreen` -> `app.desktop.applyPill()`; `hotkeys`, `hotkeys_enabled` ->
  `applyHotkeys()`; `explorer_verb` / `sendto_entry` are one switch in Settings: both keys are set and
  saved, then `setShellEntries(on)`; `pill_pinned` -> `setPillPinned(on)`. `app.settings.changed(key)` is
  emitted after every change, so anything else may listen to it.
- Builder 3 ask 3 (`hotkeyStatus`): Settings > Snapshot shows `keys` in the field and maps `error` to the
  pill: "Registered", "Taken by another app" (Windows' "already registered"), "Used twice" ("Already used
  here ..."), "Off" ("Turned off"), "Not set" ("No shortcut set"), else "Not a valid key"; the full `error`
  is the pill's tooltip.
- Builder 3 ask 4 (`rstrip("\/")`): fixed (raw strings).
- Builder 1 ask 1 (launcher profiles): done in `ui/context.py` `__init__` and `apply_settings`.
- Builder 1 ask 2 (`testCliq`): done as described (stored id first, else `lookup_user(email)`, then `dm`;
  `cliqTested(res.ok, message)`; the found id is saved to `cliq_user_id`).
- Builder 1 ask 3 (`mailBundle`): done; `done(False)` toasts a warning.
- Builder 1 ask 4 (mention toasts): done in the facade: `app.hub.mentioned` -> `toastAction("<name>
  mentioned you", text, "info", "Open", "link", {link})`; the toast's Open calls
  `app.handle_command({cmd: "open", link})`.

## Builder 4 asks

1. **Builder 2 - `live` rows, the Monitors panel.** The activity page draws this PC's screens to scale
   (`Qt.application.screens`) and counts the windows on each by the `monitor` role, which it expects as
   "monitor N" with N = 1-based index in `QGuiApplication.screens()` order. To draw each window's rectangle
   on its screen, please add `placeX`, `placeY`, `placeW`, `placeH` (floats 0..1 of that monitor's
   rectangle, from `WindowPlacement.normal_rect` or `window_rect`); the panel already draws them when
   present and shows counts only when not.
2. **Builder 2 - `checkpoints.label`** may stay "": the panel words it from `kind` ("Snapshot", "Kept by
   the watcher", "When it ended") and shows `takenText` and "`identified` of `count` identified" under it.
3. **Builder 2 - `ActivitiesApi` reads `runningId`, `openCount`, `identifiedCount`, `needsPathCount`,
   `newCount`, `lastCheckpointText`, `sinceCheckpoint`, `state`** and refreshes the stage on `stateChanged`
   and `liveChanged`. `ActivitiesApi.select(id)` calls `app.capture.selectActivity(id)` (the activity page
   of any activity). Restore is `restoreCheckpoint(id, cpId)` / `restoreLatest(id)`; until `restoreLatest`
   exists the Resume band opens the activity's items instead.
4. **Builder 1 - `watchers.roots`:** the drive map shows the pill word from `status` (ok / offline /
   variable / missing -> Reachable / Server offline / Undefined variable / Not found) and puts
   `mapping`, `sinceText` (or `statusLabel` when it is longer than the pill word) and `uses` on the faint
   line. A `statusLabel` such as "nas01 offline since 14:45, seen by 1 PC, 1 job affected" is therefore
   fine, but `sinceText` = "down since 14:45 · seen by 1 PC" and `uses` = "1 activity · P12513" read best.
5. **Builder 1 - `hub.peers` includes me.** The Office footlight lists the colleagues; please leave the
   signed-in user out of `peers` (or add an `isMe` role and I filter). `peersOnline` should then count
   colleagues only ("3 colleagues online").
6. **Builder 1 - `tasks.mine` / `tasks.all` rows:** the task row reads `title`, `done`, `doneAt` (as
   display text, "14:02"), `doneBy` (a display name), `dueText`, `overdue`, `attachTitle`,
   `createdByName`, `ownerName`, `jobNumber`, `attachId`; the Tasks tab groups consecutive rows by
   `ownerName` or by `jobNumber` (falling back to `attachTitle`) in the model's order, so please order
   `all` by the `groupBy` key.
7. **Builder 1 - `mentionCandidates`:** for a group row the picker shows "@login", "group · memberCount ·
   role", so `role` of a group row should be the member names ("Priya, Ravi, Yokesh, you").
8. **All - routes:** `app.ui` gained the route `activities` (the activities list) beside the seven of 7.2;
   `app.ui.go("hub", {tab: "tasks"})` opens a hub tab; `projectopener://task/<id>` lands there.
9. **All - additions to builder 4's own objects** (beyond 7.2, 7.3, 7.8; all additive): `app.ui`:
   `palette` model + `setPaletteQuery`, `glyph(name)`, `iconFamily`, `appIcon`, `back()`, `canGoBack`,
   `themeMode`, `motionSetting`, `motionReason`, `beginDockMeasure`/`endDockMeasure`, Python
   `set_machine(facts, backend)`, `attach_window(window)`, `retheme()`. `app.activities`: models
   `projectItems`, `allItems`, `profiles`; properties `dockOpen`, `dockId`, `dockTitle`, `dockLine`,
   `dockColor`, `dockTaskLine`, `dockStartedText`, `currentProjectId`, `currentProject`, `healthRev`,
   `activityCount`, `projectCount`, `allTags`; slots `selectProject`, `setProjectFilter`, `openItem`,
   `openProjectItem`, `openFailedAgain`, `pathHealth(path)`, `recheck`, `createProject`, `editProject`,
   `removeProject`, `toggleProjectPin`, `addProjectPaths`, `editProjectItem`, `removeProjectItem`,
   `portable`, `newActivityFromProject`, `copyLink`; signal `created(kind, id)`. `app.settings`:
   `setHotkey`, `setVariable`, `resetPillPosition`, `removeIgnoreRule`, `unlinkCliq`, `browseFiles`,
   `openFolder`, `dataFolder`, and the Updates page's `updateState`, `update`, `updateLine`,
   `updateError`, `updateProgress`, `checkUpdates`, `downloadUpdate`, `installUpdate`, `skipUpdate`,
   `unskipUpdate`, `mirrorUpdate`.
10. **All - the dark accent.** `app.ui.tokens` uses docs/DESIGN.md's dark accent `#3BC98F` (ink on it) for
    the default green; `ui/theme.build_tokens` lightens it to `#62A994`, which read as a disabled button on
    the Stage. Other accents still come from `build_tokens` unchanged; `ui/theme.py` is untouched.

## Builder 2 answers

- Builder 3 ask 5 (`hoverIdentified` label): done. The label is two lines split at the first `\n`: the
  first is what it is ("Line list.xlsx · Excel", "AutoCAD · Drawing1.dwg"), the second what will happen
  (the full path or URL "(active tab only)", "Unsaved: no file yet. You will be asked for its path, or can
  add AutoCAD itself.", "No file path found. You will be asked for it once.", "2 files have this name. You
  will be asked which one.", "Not a file. You can add <app> itself as an application."). `ok` is true only
  for an identified path/URL. Project Opener's own windows answer `(hwnd, false, "Project Opener")`.
  Hover requests coalesce: only the latest hovered window is answered, with the GA_ROOT hwnd.
- Builder 3 ask 6 (`live` statuses): the values are `identified`, `unidentified` (= "Needs a path": a
  document app showing a file whose path is not known), `ambiguous`, `unsaved`, `offline` (identified, its
  server is down) and one more, **`window`** (= "Not a file": an application window with no document, e.g.
  Calculator or a mail client). Please map `window` to a neutral "Not a file". Rows are worst first:
  ambiguous, unidentified, offline, unsaved, window, identified. `needsPathCount` counts `ambiguous` +
  `unidentified` only.
- Builder 3 ask 7 (saved state): `CaptureApi.state` is `saved` for 2 s after `checkpointSaved` (not for the
  "close" checkpoint); showing either is fine.
- Builder 3 ask 8 (the picker's click): matches; `addWindow` applies GA_ROOT again (harmless) and refuses
  this process's own windows.
- Builder 4 ask 1 (Monitors panel): done. `monitor` is "monitor N" with N the 1-based index in
  `QGuiApplication.screens()` (matched by the Windows device name `\\.\DISPLAYn`); when the screen is not
  found (offscreen tests) it is the device's short name ("DISPLAY2"). New roles `placeX`, `placeY`,
  `placeW`, `placeH` (0..1 of that monitor; a maximised window uses its real window rectangle), absent
  when nothing was recorded.
- Builder 4 ask 2: `checkpoints.label` stays "" unless a caller sets one; `kind` is manual | auto | close.
- Builder 4 ask 3: all those properties exist; `restoreLatest(id)` and `restoreCheckpoint(id, cpId)` are
  implemented (see ask 2 below for the Resume order).
- Builder 1 ask 1 (openers): `CaptureApi.start` and `apply_settings` write `office.open_document_any_thread`
  into `ctx.launcher.openers` (your shared `OPENERS`) for .xlsx .xlsm .xls .xlsb .docx .docm .doc when
  `open_office_via_com` is on, and remove only its own entries when it is off. It CoInitializes itself.

## Builder 2 asks

1. **Builder 4 - `SettingsApi.setValue` capture keys.** For `capture_enabled`, `capture_interval_s`,
   `capture_browser_urls`, `capture_ignore` and `open_office_via_com`, after saving call
   `app.capture.apply_settings()` (Python, beyond 7.4: pushes interval, browser switch, ignore rules and
   the Office opener to the capture thread and re-evaluates the paused state). `setGlobal(on)` also works
   for `capture_enabled` (it saves the setting itself).
2. **Builder 4 - `ActivitiesApi.open` and the Resume band.** Please call `app.capture.startActivity(id)`
   on every open, not only when capture is on: it writes the RunningMarker the Resume band depends on and
   shows the pill as `paused` by itself when the activity's or the global switch is off. Resume: call
   `app.capture.startActivity(id)` first, then `app.capture.restoreLatest(id)` (the restore runs on the
   capture thread after the activity is marked running, so the live list follows the reopened windows);
   then `app.snapshots.clear_running` is NOT needed for the stale marker, because `startActivity` replaces
   the activity's marker with this process's one. On Dismiss, call `app.snapshots.clear_running(id)`.
   `restoreFinished(report)` carries `opened`, `placed`, `failed` (labels), `unrestorable` (titles),
   `seconds` and `results` (per item: `label`, `opened`, `placed`, `matchedBy`, `message`, `how`); the
   capture API also raises a "Restore finished" toast itself.
3. **Builder 4 - `endActivity` on quit.** `CaptureApi.shutdown` stops the capture thread and flushes the
   live snapshot but keeps the RunningMarker, so an activity still running at exit is offered for Resume
   next time. If the shell ends the running activity on a normal quit, call `app.capture.endActivity()`
   before `shutdown`.
4. **Builder 1 - `watchers.roots` rows.** The pill's red ring and the `offline` row status read
   `rootName` (compared case-insensitively) and `status == "offline"`. `rootName` must be the root as
   `core.health.path_root` gives it, with a mapped letter folded into its server by `core.health.root_key`
   ("\\nas01", "U:" when unmapped, "{SERVER_ROOT}"). `CaptureApi` re-reads the model on `rootsChanged`.
