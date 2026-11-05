# Project Opener 4 - brief

Written 5 November 2026 from an interview with the owner. This is the picture the concept round
and the build start from. Everything here is a decision unless marked *open*.

## 1. The one job, restated

A piping office works in **activities**: for one task (checking lot 7 of P12513, a GAD review for
Mangala, a Tuesday clash meeting) a person needs a mixed set of things open at once: isometric PDFs,
the line list in Excel, a Navisworks model, two or three folders and sub-folders, a client portal,
a Teams or Cliq channel, the office standards. The set differs for every activity, even inside one
project. Setting it up by hand takes minutes every time, and when the power goes and the PC shuts
down, all of it has to be redone.

Version 3 answered this with projects and launch sets. Version 4 makes the **activity** the thing
you open, lets the app **capture** what you have open so the set builds itself, and brings it all
back after a restart with one click. Around that, the Team Hub stops being a notice board and
starts **routing work to people**: mentions, tasks, watchers and Cliq messages.

Decisions from the interview:

| Question | Decision |
|---|---|
| Main outcome | All four: team coordination, path reliability, speed of daily use, wow factor |
| Architecture | Shared folder, no server, as today. Every feature must fit files on the share. |
| Office | 10 to 30 people, one office, one LAN, one hub folder |
| Work arrives by | Chat or mail from a lead, checker-to-modeller rounds, files appearing on the share, spoken |
| Unit of a task | A free-form to-do: title, owner, due date, done; attached to an activity or a project |
| Watchers | New or changed file in a job folder; a path or server going down; a colleague publishing or finishing; time-based |
| Look | "Cinematic workspace": dark by default, depth and motion, the job as a scene |
| Motion | Rich, with graceful degradation on the older office PCs (mixed fleet) |
| Integrations | Zoho Cliq (bot, per-person DMs; the owner can create the bot), Outlook / e-mail, CAD launch profiles |
| Permissions | Everyone equal; the record shows who did what |
| Capture | Always-on background watcher while an activity runs; snapshot kept fresh; restore after a crash or power cut from a prompt on Home |
| Activities | First-class and cross-project: an activity draws items from any projects |
| Delivery | One 4.0: concept round (three boards), then build, release when the independent jurors say 10 |
| Day one | New look and motion, activities with capture and restore, mentions and groups, tasks, watchers with Cliq |

## 2. The model

```
Workspace
├── Project            a job: number, client, name, colour, icon, tags, notes
│   └── Item           file / folder / link / app + args / command, with a group
├── Activity           the thing you open: name, icon, items drawn from ANY projects, launch order,
│   │                  last snapshot, owner, "resume on start" flag
│   └── Snapshot       what was open the last time this activity ran (windows, documents, folders,
│                      URLs), captured by the app; restores them in order
├── Task               title, owner (@user), due, done, created by, attached to an activity or project
└── Watcher            a rule: path + what to watch for (new file, change, gone, server down,
                       due date, hub event) + who to tell (toast, @mentions, Cliq DM)
```

On the hub (still only JSON files, every writer owns its files, every reader tolerates a bad one):

```
_ProjectOpenerHub/
├── users/<user>.json        heartbeat as today + Cliq user id (optional)
├── groups.json              @checkers, @P12513-team ... (anyone may edit; last writer wins)
├── published/<id>.json      projects AND activities, with "for": ["yokesh", "@checkers"]
├── inbox/<user>/<id>.json   as today; mentions land here too
├── tasks/<id>.json          one file per task; owner's PC marks done
├── watch/<user>.json        the office-wide path health a PC observed (server down since 09:40)
├── announcements.json       as today, with optional @mentions
├── pulse/<user>.jsonl       activity feed, now with mentions, tasks, watcher events
└── updates/                 as today
```

## 3. Features

### 3.1 Activities, capture and restore (the core)

- An activity is opened from Home, the palette, the tray or a `projectopener://` link. Its launch
  sheet (as in 3.2) opens the items in order.
- **Capture.** While an activity is running, a background watcher (on by default; a switch per
  activity and a global switch) enumerates what the user has open every few seconds (Win32 window list plus the Shell for Explorer windows, COM for Excel and Word documents,
  document titles for Acrobat and browsers, Navisworks and MicroStation window titles) and keeps
  a snapshot: the documents, folders and URLs it could identify, with their window positions. The
  activity's card shows "12 things open, 9 identified". One click, or a prompt when the activity is
  closed, saves the identified things as the activity's items.
- **Restore.** On start after an unclean shutdown (the app records a "running" marker per activity),
  a band at the top of Home offers *Resume lot 7 check: 11 items from 14:32* with Resume and Dismiss;
  restore opens them in launch order and, where the application allows, puts each window back on
  its monitor at its size and position. Never automatic.
- **Honesty rule.** The app lists what it could not identify ("a window titled 'Drawing1 - AutoCAD'
  with no file path") rather than guessing. The user can attach a path to it by hand.
- Items keep 3.x's portable paths, variables and health. Activities publish to the hub exactly as
  projects do, with the same drive-letter conversion.

### 3.2 People: mentions, groups, targeted publishing

- `@` in any text field on the hub (publish description, announcement, task, inbox note) opens a
  picker fed from `users/*.json` and `groups.json`: display name, login, role, online dot. Typing
  narrows it; Enter inserts `@login`.
- Publishing or announcing "for" people writes the item to each person's inbox and tags the pulse
  line; the mentioned person gets a toast, a sidebar count, and a Cliq DM if they linked Cliq.
- Groups are a small JSON everyone may edit: name, members, optional colour. `@P12513-team` is
  created from a project page with one click ("make a group from everyone holding this job").

### 3.3 Tasks and hand-offs

- A task is a file on the hub: title, owner, due date, created by, done at, attached activity or
  project. Everyone equal: anyone can create and assign; the record shows who.
- Where it shows: a **My tasks** strip on Home (due soonest first), a task count on the sidebar, a
  Tasks tab on the hub (by owner, by job), the task on the activity's card, and the launch sheet's
  footer ("Task: back-check lot 7, due Fri").
- Marking done pulses "Yokesh finished back-check lot 7" and tells the creator (toast, Cliq DM).
- Mail: "Mail this task" opens Outlook with the task and a `projectopener://` link; *open*: parsing
  assignments out of incoming mail is a later version.

### 3.4 Watchers and alerts

- Folder watchers poll the share (ReadDirectoryChangesW is unreliable over SMB), listing the folder
  every N seconds and diffing: new file, changed file, file gone. A watcher on
  `\\nas01\Project\P12513\ISO\Revision C` tells the checker when the modeller drops a sheet.
- Health watchers: whoever first sees a server down writes it to `watch/<user>.json`; the drive map
  on every Home says "nas01 down since 09:40, seen by 3 PCs, 14 jobs affected".
- Hub watchers: a revision published, a task done, a mention.
- Time watchers: due dates, "activity not opened for 30 days", reminders.
- Every alert is a toast with an action, a pulse line, and optionally a Cliq DM. Nothing is sent
  twice; a small per-user "delivered" file on the hub de-duplicates.

### 3.5 Zoho Cliq

- One office bot under a shared Zoho service account (the owner creates it); its token stored with DPAPI like the GitHub token.
- Each user links their Cliq id in Settings (the bot looks it up by e-mail).
- The bot DMs on mention, task assigned, task due, watcher hit; the message carries a
  `projectopener://` link that opens the activity or task. Posting to a channel is a per-watcher
  option. If the bot is unreachable the toast still shows and the DM is retried later.

### 3.6 CAD launch profiles and mail

- Items of kind Application gain **profiles**: Navisworks with a saved viewpoint and the right
  search sets, MicroStation with a seed and a workspace, AutoCAD with a profile, CAESAR with a job.
  A profile is arguments plus a working folder plus environment variables, named and shareable.
- Outlook: mail a bundle (the activity's items as links), mail a task.

### 3.7 Everything 3.2 keeps

Portable paths and variables, path health and the drive map, the launch sheet, the job-number
spine, revisions and the Activity register, the command palette, the tray, deep links, in-app
updates with the LAN mirror, backups, migration from 1.x/2.x and now from 3.x.

### 3.8 Snapshot surfaces: capture from anywhere

The watcher records by itself while an activity runs (section 3.1). These surfaces are for the
moments the user wants to act, and they live where the user already is, because capture matters
most when Project Opener is hidden behind Navisworks and Excel. Board: `snapshot-surfaces` in the
concept round's folder.

**The pill.** A small capsule docked to a screen edge, by default bottom-right just above the
notification area: the running activity's colour dot, its short name and how many things are open
("Lot 7 check 12"). It is a frameless tool window that never takes focus, never appears in
Alt+Tab, is left out of its own captures, and remembers its place per monitor layout; drag it to
any edge and it snaps.

| State | Shows |
|---|---|
| Running | Colour dot, short name, things open |
| Needs you | Amber ring and "3 need a path" (unidentified windows); red ring when a drive the activity uses is down |
| Capture paused | Hollow dot, "paused"; the last snapshot is kept |
| Just saved | "Saved · 12 things · 14:32" for two seconds after a checkpoint; no sound, no toast |
| No activity running | Not on screen, unless pinned; pinned, it offers **Start from what's open** |
| Edge tab (rest style) | A 6 px line in the activity's colour on the screen edge, for people who want nothing visible |

Hover for half a second (or **Ctrl+Alt+P**) and it opens upward into a **panel**: the activity's
title, "12 open · 9 identified · last checkpoint 10:52, 2 new since", the watcher's list worst
first (Needs a path, Server offline, Identified), and three actions: **Snapshot now** (the one
filled button), **Add a window**, **Review**; plus pause capture and open in Project Opener.

**Snapshot now** marks a checkpoint: time and list, kept in the activity's history (last ten,
each restorable). When the watcher has found things that are not yet the activity's items, the same
place offers **Save 2 new as items**, so the set grows by itself as the user works.

**Add a window.** The screen dims slightly, the window under the pointer is framed (green when it
can be identified, amber when it cannot) with a label saying exactly what will be added; click to
add, Esc to cancel. **Ctrl+Alt+A** with a window already in front adds that window directly.
Nothing is guessed: an unsaved "Drawing1" in AutoCAD is reported as having no file and the user is
asked for the path once, or offered AutoCAD itself as an application item. A browser adds its
active tab's address; Excel and Word add the document read from that window (instance-proof,
section 4).

**Start from what's open** (pill, tray, Home, Send to). The cold start: open what a task needs
the usual way, then turn the open windows into a new activity in one sheet: every window listed
with its pill, non-file windows (chat, mail) unticked by default, a name and a project, then
"Start activity · 9 items". Nobody builds a set by hand again.

**Tray.** Left-click opens the pill's panel; right-click shows the running activity on the first
line, then Snapshot now, Add a window, Pause capture, End activity, Start an activity from what's
open, Open an activity, Show the pill, Search, Show Project Opener, Quit. The icon carries a dot in
the activity's colour while one runs.

**Explorer.** "Add to running activity" on any file or folder (a per-user registry verb, no
admin), and "Send to > Project Opener" for several files at once. Both reach the running instance
over the single-instance socket; with no activity running they open a chooser (add to an activity,
or start a new one from the selection).

**Keys from anywhere** (RegisterHotKey, configurable, conflicts shown as Windows reports them):

| Keys | Action |
|---|---|
| Ctrl+Alt+S | Snapshot now |
| Ctrl+Alt+A | Add the window in front; pressed twice within a second, opens the picker |
| Ctrl+Alt+P | Show or hide the pill's panel |
| Ctrl+Alt+K | The command palette over whatever is in front |

**Inside the app.** The activity page header carries the capture switch, Snapshot now, Add a
window and the checkpoints; its one filled button follows what is waiting ("Save 2 new as items"
when there are new things, otherwise Snapshot now). Home offers Start from what's open when
nothing runs.

**Rules that keep it out of the way.** Never takes focus. Default place outside the usual drawing
area. Hidden while a full-screen app, a presentation, a remote-desktop session or Windows' "Do not
disturb" is in front, and back by itself. Hidden when there is nothing to say. Quiet: one ring
colour, no sounds, no growing badges. Not in its own captures. Settings > Snapshot turns each
surface on or off (pill, rest style, position, the four keys, the Explorer entries). Motion follows
the app's setting: rich grows the panel from the pill in 180 ms, purposeful fades, off appears.

**Build notes.** The pill is its own QQuickWindow (Qt.Tool, FramelessWindowHint,
WindowStaysOnTopHint, WindowDoesNotAcceptFocus, with WS_EX_NOACTIVATE set natively) in the same
process as the main window. Full-screen detection: SHQueryUserNotificationState plus the foreground
window covering its monitor. Hotkeys: RegisterHotKey on a hidden message window, read through a
native event filter. The picker: a transparent click-through overlay per monitor and WindowFromPoint
with GA_ROOT. Per-monitor DPI throughout.

## 4. The look: "cinematic workspace", rich motion, graceful degradation

- Dark by default; light stays. Depth from layered surfaces and motion, not from gradients and
  glass (the 3.x discipline about colour on data, not chrome, stays).
- The activity is a scene: its card grows into a dock that shows what is open, what is reachable
  and what the task is; the launch sheet becomes the dock's opening act.
- Motion that explains state: pills settle, rows arrive in launch order, the office map breathes
  when someone comes online, page transitions carry the job's colour.
- Degradation: a `motion` setting (rich, purposeful, off) chosen automatically from the GPU and
  the window size and overridable; every screen is complete with motion off.
- Three concept boards, as for 3.1, then the jurors.

**Decided (5 November 2026): concept "Stage", built in Qt Quick.**

*Stage*: one activity stands in the light at a time. Home is a stage with the current activity in
the centre at full size and the others in the wings; opening it is the scene growing into the page;
the shell recedes to a narrow rail; drives, tasks and the office are a footlights strip. Two pieces
are borrowed from the other boards: Control room's office panel (desks that breathe once when
someone arrives) as the third footlight and its Monitors panel on the running-activity page, and
Desk's dashed tile as the row style for unidentified windows. Section 3.8 adds the snapshot
surfaces. The boards and the comparison are in the concept round's folder (`concept-1-stage`,
`COMPARISON.md`, `snapshot-surfaces`).

*Qt Quick*, measured on this PC by the spike (`spikes/quick/REPORT.md`; i7-6700, GT 710, with a
background indexer loading the CPU, so the ratios are the signal):

| | Widgets 3.2 shell | Qt Quick prototype | WebEngine |
|---|---|---|---|
| First frame | 8.2 to 13.8 s | 1.7 to 2.6 s | 4 to 9 s warm |
| Idle memory, 1366×768 | 140 MB | 79 MB software, 89 to 95 MB GPU | 205 MB, two processes |
| Dock animation | not attempted | 16.6 to 17.3 ms per frame, GPU and software at 1440×900 | 19 to 21 ms, worst 1 % up to 167 ms |
| Idle CPU, purposeful or off | 0 % | 0 to 0.3 % | 51 to 63 % with one CSS loop |

The one unsafe combination is software rendering at 1366×768 with rich motion (the worst 1 % of
frames at 134 to 298 ms). Fallback rule: probe the GPU once per adapter; software rendering when it
fails, on the Basic Render Driver or in a remote session; motion defaults to rich only with a GPU
and a screen above 1366×768, purposeful otherwise, off in remote desktop; two slow dock openings in
a row drop one level, saved, said once. Ambient loops run only in rich and only while the window is
active. The real older-PC run is still to do; `spikes/quick/bench.py` runs there unchanged.

What carries over unchanged: `core/`, `lan/`, `update/`, almost all of `ui/context.py`, the theme
tokens and contrast check, and about 250 lines of pure view helpers. Rewritten in QML: the main
window, the views and the widgets (about 6,000 lines). QML rules learned in the spike: models are
QAbstractListModels, never QVariantLists; install a Qt message handler first; minimum-window checks
become explicit per-page minimums.

*Capture and restore*, proved on this PC by the spike (`spikes/capture/REPORT.md`): Explorer,
Word, Excel, PDF-XChange and Chrome identified with full paths, closed, reopened and put back at
their exact size and position on the right monitor in 23 s. Watcher cost with an identity cache:
6 ms per pass, 0.57 % of one core. Design rules from it: Excel and Word are read per window through
AccessibleObjectFromWindow (the Running Object Table can return a stray instance); Office files are
opened through COM, not the shell association (the shell path sends files on the share into
Protected View and can take minutes); restored windows are matched by identity, title only as a
fallback; browsers give the active tab; title-only applications match against the activity's items
and recent files, and two same-named isometric PDFs are reported as ambiguous, never guessed;
unsaved documents are listed and not restorable.

## 5. Build plan (one 4.0)

1. **Concepts**: done. Stage chosen, with the snapshot surfaces of section 3.8.
2. **Spikes**: done on this PC (capture and restore; Qt Quick). Still to do: run
   `spikes/quick/bench.py` on one older office PC, and try Navisworks and MicroStation titles with
   real files.
3. **Core and hub**: the model in section 2, migration from 3.x (projects stay; launch sets become
   activities), hub files, Cliq bot client, watcher engine, tasks.
4. **Shell**: the chosen concept, screen by screen, with the 3.2 verification set (tests, contrast,
   smoke, minimum window, click-through) and the independent-juror loop until 10/10.
5. **Landing page, guide, README** regenerated from the final app, as for 3.2; release 4.0.0.

## 6. Answers from the owner (5 November 2026)

| Question | Answer |
|---|---|
| Window positions on restore | Reopen the documents **and** put the windows back on their monitor, size and position where the application allows; otherwise reopen in launch order. |
| Capture | **Always on** as a background watcher while an activity is running (the snapshot is always fresh, so a power cut loses nothing). A switch per activity and a global switch turn it off; "Snapshot now" also exists. |
| Resume after a restart | A band at the top of Home: *Resume lot 7 check: 11 items from 14:32*, with Resume and Dismiss. Never automatic. |
| Name of the concept | **Activity** (the office's word; 2.x used it too). |
| Shared office activities | Anyone may republish them; last writer wins; the record shows who; revisions as today. |
| Cliq bot owner | A shared office service account, so the bot survives staff changes; one token, entered in Settings and stored with DPAPI. |
| Concept | **Stage**, plus a snapshot pill and snapshot surfaces outside the app (section 3.8). |
| UI layer | **Qt Quick** over the unchanged Python core, from the spike's measurements (section 4). |
