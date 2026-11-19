# Project Opener 4 - feature pool and Cleanly-hybrid look (interview 19 Nov 2026)

Extends `docs/V4-BRIEF.md`. Decisions below come from a three-round interview with the owner.
**Delivery: one big release** - 4.0 is held until the look and every feature here are in.

## 1. Features in scope

### Signature features (all three)
| Feature | Decision |
|---|---|
| **Time-travel timeline** | Scrub through past captures of your workspace and restore any moment. A snapshot is **windows + open files + window positions only** - no screen images. Every few minutes while an activity runs. Private to each person. Builds on the existing capture/restore. |
| **Visual revision diff** | v1 compares **PDF drawings** (render both revisions, red/green overlay) and **Office docs** (Excel cell-level changes, Word text changes). Native CAD and scans are out of v1. |
| **Weekly Wrapped** | Animated weekly recap, **with an office leaderboard** (per-person stats visible to everyone: streaks, tasks closed, activities run). Shareable to Cliq. |

### Daily rhythm
- **Today** screen: yesterday's resume, tasks due, overnight changes in watched folders.
- **Park** at day end: one key captures the workspace + a "where I left off" note shown next morning.
- **Timesheets: out of scope** (owner ruling).

### Drawings & docs
- **Revision radar - DROPPED from this release (see section 4).** Original idea, kept for later: watches project folders; a new revision in a filename marks the older file
  *superseded* wherever it is linked (activities, items, mentions). How revisions are recognised in filenames
  (naming rules) must live in a reference/config file, not be hard-coded (CLAUDE.md: rules an engineer
  knows don't go in Python). The radar reports what it sees; it never decides which file is approved.
- Transmittal builder and PDF drop actions: **not chosen**.

### Share hygiene + team
- **Space Map + duplicates**: Cleanly-style bubbles of project-share usage, duplicate drawings, stale files. Report only - no deleting from the share.
- **Office pulse**: who is on which project now.
- **Handover pack**: give your activities + tasks to a colleague while on leave.

### Not chosen
Find-anything palette / AI assistant, transmittal builder, PDF drop actions, focus mode, snippet shelf, timesheets.

## 2. Look: Cleanly hybrid

Reference: Cleanly (github.com/0xCodez/cleanly, Electron + React). Tokens read from its bundled CSS
(`D:\Cleanly\resources\app.asar` -> `dist/assets/index-*.css`). Licence not yet verified (GitHub API timed
out) - check before copying any code or assets verbatim.

Adopted from Cleanly (overrides the matching bans in `docs/DESIGN.md`, which must be rewritten):
| Signature | Cleanly source value |
|---|---|
| Big display numerals and titles | `Unbounded Variable` for stats and screen titles |
| Soft glow + glass | paper `#f2f3f6`; radial glows `#fff` at 20%/-10% and `#d6cdff8c` at 110%/110%; grain + dot grid; glass `blur(22px) saturate(1.5)`, card `#ffffffd6`, border `#e2e5ea`, shadow `0 24px 60px #0f12180f` |
| Mono small labels | `JetBrains Mono Variable` 10.5px, letter-spacing .14em, uppercase, ink-3 `#5b6270` |
| Signature motion | one easing `cubic-bezier(.2,.8,.2,1)`; `rise` entrance (opacity 0, blur 6px, +12px Y); shine sweep on the main button; breathing hero; bubble physics in Space Map |

Kept from current system: Onest UI font (Cleanly uses it too), pill buttons, radius trend (Cleanly 28px cards).
**Accent: the Dexterity brand colours** (`dexterity-brand` skill, kit at `U:\Vikram\Dexterity-Brand`), replacing aurora green and Cleanly blue.

### Concept chosen (19 Nov 2026): **B - Drafted Glass**
Board: `docs/concepts/v4plus-boards.html` (served by the `concept-boards` preview config; keys 1/2/3, L = old-PC tier).
- The Dexterity brand leads: Archivo light (250-300) for numerals and titles instead of Unbounded, Instrument Sans body,
  JetBrains Mono uppercase labels, hairlines, 5-8 px radii, faint 30/150-degree isometric grid on the background, a teal rule on top of the hero.
- Cleanly contributes the layout (236 px sidebar, hero, four stat cards, three panels) and the motion
  (blur-rise entrances staggered 60 ms, shine on the main action, breathing hero glow). Glass only on things that float (sheets, the pill, the hero).
- Amber is the one action per screen (Resume); teal is structure.
- Must carry into the app: **line-of-flow restore pipe**, **handwritten Park note** (Cormorant italic),
  **physics Space Map** (drag, drift, bump; amber = duplicate/stale), **count-up numerals** and popping streak squares.
- **Today layout approved as shown**: hero (resume parked activity + restore plan), 4 stats (tasks due,
  changed overnight, day streak, setup saved), then Time travel | Office pulse | Space map/Wrapped.

## 3. Motion and speed
**Rich everywhere with auto-degrade**: measure frame time at start-up; on slow PCs drop blur, glass, grain and
shader effects first, then shorten motion. Lists and navigation must stay lag-free at every tier.
Qt Quick equivalents: `MultiEffect` (blur/shadow), `ShaderEffect` (glow/grain), `Behavior`/`NumberAnimation` with the one easing curve.

## 4. Answers to the open questions (19 Nov 2026)
- **Snapshots: not too often - the user's PC must never feel it.** Proposal: a snapshot on activity
  start/switch, on Park, and at most every 15 minutes while windows have changed (none while idle);
  low-priority thread; history kept 14 days, then thinned to one per day for 60 days.
- **Leaderboard: anyone can opt out** (Settings, one switch; opted-out people vanish from the board but
  still see their own Wrapped). Proposed counts: activities run, tasks closed, on-time rate,
  day streak, setup time saved by restores. No raw hours, no window titles.
- **Revision radar: dropped from this release** (owner ruling). Filename revision patterns are not built.
- **Space Map scope: every project folder on the hub's project cards** (all cards created by anyone on
  the LAN) - that covers every folder the office works in. No other share roots.

## 5. Build state and plan (19 Nov 2026, end of the design session)

**Done (uncommitted on branch v4, beside juror round 4's uncommitted work):** docs/DESIGN.md rewritten to
Drafted Glass; brand fonts bundled as TTF (`resources/fonts/`, OFL notice `OFL-brand-fonts.txt`); brand tokens in
`ui/theme.py` (`accent` = teal-ink #1C7680, `teal` for graphics, `action` amber = `ActionButton` kind primary,
`mist`, `grid`; contrast check passes both themes); accent picker retired (`Settings.load` resets it); `Txt` roles
`label` (mono) and `note` (Cormorant italic), titles/numerals in Archivo light; the **sidebar**
(`qml/components/Sidebar.qml`, 236 px, folds to the 68 px rail below a 1100 px window; `Main.navWidth`, read by
`tools/smoke_v4.py`); StatusPill/Scene ScriptActions replaced by `onFinished` handlers (invalid-context flake);
`tests/test_v4_desktop_fakes.py` gained `newNote`. Full suite green; 64-shot smoke clean.

**Owner rulings for Today (19 Nov 2026):**
- Build Today v1 on **real data only**, then the backends (Park, the restore log, Space map, Wrapped).
- **Setup saved = windows reopened** this week, counted from what each restore actually opened. No time estimate.
- **The hero grows into the launch dock** (as the Stage centre does now), so the dock grow, `motion.dock_measure_ms`,
  the guard and `--bench` keep measuring one animation.

**Today v1 - data map (no invented numbers):**
| Block | Source |
|---|---|
| Hero: "Pick up where you parked" | `app.activities.resume` (until Park exists: the resume after a shutdown, else the last-run activity); restore-plan chips = that snapshot's restorable entries (`snapshots.latest`, `restorable`), +N |
| Tasks due today | `app.tasks` (mine, due today, of N open) |
| Changed overnight | watcher `WatchEvent`s since the last session end / 18:00 yesterday |
| Day streak | distinct days with a launch, from `store.history()` |
| Windows reopened (week) | **needs the restore log** - until then hide the card or show the 4th real stat (open tasks this week) |
| Time travel lanes | checkpoints across activities this week (`snapshots.checkpoints`), click = restore that checkpoint |
| Office pulse | the existing `OfficePanel` data (hub peers) |
| 3rd panel | Drives on this PC (existing `DrivesPanel`) until Space map / Wrapped exist |

**Then the backends, each its own change:** (1) restore log -> windows reopened; (2) Park: Ctrl+Alt+P captures the
workspace + a note, Today's hero shows it; (3) Space map scan of every hub project card's folder (report only,
duplicates and stale files); (4) Wrapped weekly stats + leaderboard with the opt-out switch. Sidebar routes for
Time travel, Space map, Wrapped and Handover are added as their pages land.
