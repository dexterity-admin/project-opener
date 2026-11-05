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

*Open (decide in the concept round)*: the UI layer. Three ways to get rich motion with the Python
core unchanged:

| Option | For | Against |
|---|---|---|
| Qt Widgets + QPropertyAnimation, as today | No rewrite of the shell; everything in 3.2 carries over | Motion is laborious; depth and layered scenes are hard; stays "an app" |
| **Qt Quick (QML) shell over the Python core** | Built for animated, layered, GPU-rendered UI; scales down with `Qt.Quick` software rendering on old PCs; still one Python process | The whole UI layer is rewritten; new skills; a few widgets (file dialogs) stay native |
| Qt WebEngine shell (HTML/CSS/JS, like the landing page) | The landing page's look and motion directly; web tooling | A browser engine per app (memory, cold start on old PCs); two languages; offline-only must be enforced |

Recommendation to test in the concept round: **Qt Quick**, with a one-screen prototype (Home with
the dock) measured on an older office PC before committing.

## 5. Build plan (one 4.0)

1. **Concepts** (1 round): three boards for the cinematic workspace, each showing Home with the
   activity dock, an activity open with capture running, the hub with mentions and tasks. Owner
   picks one.
2. **Spike**: capture and restore on this PC (Excel, Acrobat, Explorer, Edge, Navisworks) and the
   Qt Quick prototype on an old PC. These are the two risks; everything else is plumbing.
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
| UI layer | Still open: decided by the Qt Quick prototype on an older office PC in the spike (section 5). |
