# DESIGN.md - Project Opener 4 visual system ("Drafted Glass")

The durable visual decisions for the desktop app (`project_opener/qml`, `project_opener/ui`) and the
landing page (`site/`). Every token, rule and exception lives here; code references tokens, never raw
values. Companions: `docs/PRODUCT.md` (who uses it and for what), `docs/V4-BRIEF.md` and
`docs/V4-PLUS-BRIEF.md` (what 4.0 does), the concept board `docs/concepts/v4plus-boards.html` (concept B).

**This contract leads the code.** As of 19 November 2026 the app still renders the 3.x "Aurora" tokens
inside the Stage shell. Sections marked *(to build)* describe the target. The behaviour rules further
down (dialogs, launch sheet, copy, motion levels, the office's own objects) carry over unchanged.

## Where it comes from

- **3.x, "Aurora, disciplined"** (1 Nov 2026): light, pastel, Onest, one flat aurora-green accent. It
  was disciplined by `taste-skill` and `impeccable`, which banned glass, gradients, eyebrows and mono labels.
- **4.0, "Drafted Glass"** (owner, 19 Nov 2026): concept B of three boards built after the v4-plus
  interview. Two sources:
  - **The Dexterity brand** (`U:\Vikram\Dexterity-Brand\BRAND.md`; skill `dexterity-brand`) gives the
    identity. It is drawn, not bubbly: hairlines, small radii, title-block labels, teal for structure,
    amber for the one action, and "Line of flow" motion.
  - **Cleanly** (github.com/0xCodez/cleanly; tokens read from its bundled CSS) gives the layout
    (labelled sidebar, hero, stat cards, panels) and the motion (blur-rise entrances, shine, breathing
    glow, bubble physics). Cleanly's licence is not verified yet, so take ideas and values, not code or assets.

What 4.0 reverses from the 3.x bans, and why:

| 3.x rule | 4.0 | Why |
|---|---|---|
| No glass, no backdrop blur | Glass on what floats (sheets, palette, the pill's panel, toasts) and on the Today hero, rich motion only | Owner ruling: the Cleanly-grade look; degrades to opaque surfaces |
| No gradients | One soft radial "mist" glow on the ground and a breathing glow behind the hero; never on text, buttons or data | Atmosphere only, never as the accent |
| No eyebrows, no mono labels | Mono uppercase section labels (the brand's drawing title-block voice) | Brand rule: "labels, numbers, annotations: JetBrains Mono" |
| No display face in the app | Archivo light for page titles, the hero and stat numerals | Brand headings; large and quiet |
| No sparklines or icons on KPIs | Today's stat cards may carry one small graphic (sparkline, streak squares) | Approved board |
| One flat green accent, user-selectable | Brand colours fixed: teal for structure, amber for the one action | Owner ruling: Dexterity brand accent |
| Onest everywhere | Instrument Sans body (brand) | Brand body face |

Kept from 3.x: one primary per screen, no resting shadows on cards, a border or a shadow but never
both, tabular figures, contrast computed rather than eyeballed, and every copy and behaviour rule below.

## Type *(fonts bundled and `Txt` roles built 19 Nov 2026; screens still to follow)*

Four families, all OFL, bundled under `resources/fonts/`. The brand kit ships woff2, so convert to TTF
for Qt with fontTools. Do not link to U: at run time.

| Role | Face | Size / weight | Notes |
|---|---|---|---|
| Page title | Archivo | 30 px, 300, tracking -0.03 em | one per page, a noun |
| Hero heading | Archivo | 32 px, 250 | Today's hero only |
| Stat numeral | Archivo | 44-46 px, 250, tracking -0.04 em, tabular | unit beside it in body 13 px, muted |
| Body, nav, rows | Instrument Sans | 13.5-14 px, 400 / 500 / 600 | fallback Segoe UI |
| Small | Instrument Sans | 12 px | nothing smaller in body text |
| Section label | JetBrains Mono | 10.5 px, 500, uppercase, tracking 0.14 em | labels and annotations only, never a sentence |
| Park note | Cormorant Garamond italic | 19 px, 500 | a person's own note; never UI text |

Tabular figures on every number that lines up. Titles are never tabular (see "The office's own objects").

## Colour *(tokens built 19 Nov 2026; screens still to follow)*

Brand tokens (`--dx-*` in the kit) mapped onto the existing `build_tokens` roles. Light:

| Token | Value | Use |
|---|---|---|
| `bg` | `#F6FAFA` | paper: the ground and the sidebar |
| `surface` | `#FFFFFF` | cards (`#FFFFFFF0` where glass is on), inputs |
| `surface_2` | `#E8F2F3` | stone: active nav item, hover, chips |
| `surface_3` | `#D6E8EA` | pressed |
| `border` | deep teal at 16 % on white (`#DBE5E6`) | hairlines (cards, rows, the hero); flattened to opaque so QSS and QML draw the same line |
| `border_strong` | deep teal at 30 % on white (`#BBCFD1`) | control borders, stat-card top rule, scrollbar |
| `text` | `#132B2E` | ink |
| `text_muted` | `#4C6366` | graphite, secondary |
| `text_faint` | `#5A7073` | meta, labels, placeholders |
| `accent` | `#1C7680` | teal-ink: selection, focus, links, accent text, fills that carry white text (the brand's AA teal) |
| `teal` | `#2A8C98` | brand teal for graphics only (rules, progress, ticks, the line of flow; 3:1, never body text) |
| `teal_deep` | `#1E6066` | deep teal: time-travel ticks, dark panels |
| `action` / `action_hover` / `action_fg` | `#F7AF44` / 8 % darker / ink | amber: **the one thing to press per screen** (`ActionButton` kind primary), the line-of-flow slug, a done node |
| `action_ink` | `#9A5B00` | amber as text on light |
| status and pills | unchanged from 3.x | already contrast-checked |
| `mist` | radial `#E3F1F2` at the top-right of the ground | the one ground glow |
| `grid` | 30° / 150° hairlines `#1E60660D`, 26 px pitch | house texture behind everything; dropped below rich |

Dark (passes `tools/check_contrast.py`, 19 Nov 2026): `bg` `#0F2124`, `surface` `#152B2F`,
`surface_2` `#1C363A`, `surface_3` `#24434A`, `border` `#FFFFFF1C`, `border_strong` `#FFFFFF33`,
`text` `#EAF4F5`, `text_muted` `#B5C9CB`, `text_faint` `#8FA7AA`, `accent` `#4FB3BE` (ink text on it),
`teal` `#3FA3AF`, `action` `#F7AF44` with ink text, `grid` `#0AFFFFFF`. Dark is ink-teal, not navy and not neutral grey.

Proportion: ground 70-90 %, teal for structure and data, **amber under 2 % of any screen**: one
filled amber control and the line-of-flow slug. Project colours are data (the icon tile's tint, a 6 px
dot), never chrome. People get a stable tint (`Avatar`), shown as a 4 px-radius square. The 3.x
user-selectable accent is retired: `Settings.load` migrates any stored accent to the brand, and
Settings > Appearance keeps Theme and Density only.
## Shape and space

- 4 px base. Card padding 16-18 (comfortable) / 12 (compact). One gap value per screen: 14 on Today, 16 elsewhere.
- **Radii, drawn family** *(to build)*: cards 8, inputs 6, nav items 5, avatars 4, sheets and the
  palette 10, window corners 10. Buttons and chips stay pills (999), as on the company site.
- **Hairlines, not boxes**: 1 px `border` on cards and rows; controls one step stronger. A border or a
  shadow, never both. Cards have no resting shadow. Things that float (menus, toasts, the palette,
  sheets, the pill's panel) carry the floating shadow and, in rich motion, glass.
- **Title-block rules**: Today's hero has a 2 px `accent` rule on its top edge; each stat card has a
  2 px `border_strong` top rule that turns `accent` on hover. Label (mono) over value (Archivo numeral).
- **Glass** *(to build)*: in rich motion, a floating surface is `surface` at 94 % over a 14 px blur of
  the page behind it (Qt Quick `MultiEffect`, saturation 1.3). Below rich, or on the software renderer
  (which has no blur), it is opaque `surface`. A glass surface never sits on another glass surface.
- **Sidebar** *(built 19 Nov 2026, `components/Sidebar.qml`)*: 236 px on the page ground, with a hairline on its right edge. The brand mark
  and "Project Opener" at the top. Mono uppercase group labels: WORKSPACE (Today, Activities, Projects,
  Tasks, Time travel) and OFFICE (Office pulse, Space map, Wrapped, Handover); a route appears only once its
  page exists (built: Today, Activities, Projects, Tasks = the hub's Tasks tab, Team Hub; Updates and Settings sit
  at the foot over the person). The active item is a
  `surface_2` fill with a 2 px `accent` bar on its left; counts are mono, faint, right-aligned, and only
  on queues. Below a 1100 px window the sidebar folds to the
  68 px rail (labels become tooltips), so pages keep their 860 px minimum.
- Page title Archivo 30 px, one per page, a noun (Today keeps its date beside it as a mono label). One
  optional grey line under it: the finding, never a description of the interface.
- Stats (Today): four cards in one row, each a mono label, an Archivo numeral with its unit, and one line
  or one small graphic (sparkline, streak squares). Elsewhere KPIs keep the 3.x divided strip.
- Rows 44-56 px; two-line rows 56+; one status mark per row; numbers right-aligned tabular.
- Empty states keep the frame and the heading, span the block they stand in (never a narrow
  island in a flow), say in one sentence what the block will hold, and offer one action where
  the data will appear (`widgets/empty.py`). Text measure 420 px.
- Tags on cards and rows are pale neutral pills (`Badge`, 20 px, no border); an outlined 1 px box
  per tag was a counted tell. Outlined chips are only for *interactive* filters (Projects page).
- Columns inside list rows are real columns: trailing actions take a fixed slot per row (a hidden
  button still reserves its 30 px), so every status pill ends on one line.
- Two panels that share a row share a bottom edge: both stretch, content top-aligned, rows capped
  (Home: 4) so neither carries a blank band. A lone count leads each panel's heading in grey,
  tabular, instead of a KPI strip above them all (app-screens §5: a strip whose every cell names a
  panel below is dropped).
- Every page's title row carries the page's one primary and nothing the sidebar already offers
  (no second Search button).
- Combo boxes draw a 12 px chevron (`theme.caret_image`); a control that opens says so.
- **Toggles are chrome, so they carry no colour**: the on-state track is `text` ink (near-black on
  light, white on dark) with the knob in `bg`; off is the `border_strong` track. The accent stays on
  data, the one primary and the focus ring (app-screens §8.1: "the on colour is a semantic green or
  near-black, not the brand accent"; our accent is the brand green, so ink it is).
- **One "New project" control per screen**: the filled primary in the title row of Home and Projects.
  The sidebar carries none (Ctrl+N and the palette reach it from every page). The sidebar names the
  product and the company, never the version: the version lives on Updates.
- **Card grids** (`FlowLayout(justify=True)`): rows of equal columns; the last row's cards share the
  full width so no card stands beside empty ground; every card in a row takes the row's height, with
  its action pinned to the foot, so a row has one bottom edge. A card's second line is never blank:
  client · job, else the description, else what the project holds ("2 links · 1 command").
- **Home**: Quick launch shows one row (3 cards) with "All projects" in its heading, so Needs attention
  and Team pulse, the rows that answer "is anything wrong", sit on the first screen. Needs attention
  lists one row per path with the same status pill as the project page and the launch sheet (the
  product's signature element on the first screen). Announcements: the newest only, as one band with
  the body on one line and "+N more" to the right; the rest live on the Team Hub.
- **Project page**: the 32 px icon tile sits inline with the title so the title, its line, the tags and
  the meta line share one left edge; the back link and the card titles share the other. Below 1180 px
  page width the side column (launch sets, notes) stacks under the items so the identity column keeps
  its width. "Open project" is disabled, with the reason in its tooltip, when nothing is enabled.
- **Dialogs** float over a 40 % ink scrim on the main window (`_Scrim`), so the page behind reads as
  behind.
- **Progress** bars are 4 px, full width under their label, never centred in a well.
- **People** are shown by display name everywhere (`TeamHub.display_name_for`), the login only in a
  tooltip. A fact appears once per screen: the version in the Updates subtitle only; an item count as
  "6 of 6 items" on the project page; on cards and rows the health line reads "6 items · opened
  just now", "4 of 6 items · opened 2 d ago" only when some items are switched off, and "never
  opened" when never opened (`cards.health_line`), so it never reads like a launch result beside
  the launch sheet's "4 opened".
- **Launch sheet** footer: "N opened · N not opened · N skipped": "not opened" counts items that failed,
  were not found, whose server was offline or whose variable is undefined; "skipped" only items the
  launcher skipped on purpose.
- A drag target ("Release to start a project from these items") shows only while something is
  dragged over the page; no instruction sits in empty ground otherwise.
- **The office's own objects organise the screens** (round 3):
  - *Job number first.* `Project.title` is "P12513 · As-built isometrics" (the client when there is no
    job number; nothing added when it is already in the name). Every title, card, row, palette hit,
    hub card and launch-sheet heading uses it, set in tabular figures at title weight. The card's
    second line then carries the client and description, else what the project holds.
  - *Health by cause, then by symptom.* Home's left column is "Drives on this PC" over "Needs
    attention". The drive map lists only the roots that are down (drive letter, `\\server` share,
    `{VARIABLE}`), worst first, each with its pill, the letter's mapping as a faint subline
    ("Z: → \\nas01\Project"; a mapped letter folds into its server so a server down is one row),
    which job uses it ("1 project · P12513" / "2 projects") and an action only where the row needs
    doing: "Open P12513" for one project, "2 projects" (the Projects page filtered with
    `root:<root>`) for more; rows without an action keep the action column's width. Reachable roots
    fold behind one ghost line "N drives reachable" that expands on click. Needs attention lists
    only paths a root does not explain and is hidden when there are none. Re-check sits in the
    drive map's heading and disappears with no projects. The same pills everywhere (`STATUS_META`).
  - *A launch set is a checklist.* Items are numbered steps in launch order under their group label
    (launch sheet, Launch sets panel "1 Iso checklist.pdf · 2 Line list.xlsx"); the editor's list order
    is the launch order (Move up / Move down) and is saved in `LaunchSet.item_ids`.
  - *Revision is a figure.* "rev 2" tabular in the hub card's corner; the clone banner "you have
    revision 1 · revision 2 available". Activity is a register, not a feed: grouped under the
    project title with the columns Event · Rev · By · When (figures and times right-aligned,
    tabular), launches by one person on one day folded into "opened 3× today"
    (`team.activity_register`).
  - *Tabular figures are for figures that line up* (rows, pills, the rev column, the meta line,
    the sheet footer), never for a title: a title lines up with nothing and `tnum` letter-spaces
    the job number.
  - *A line of facts drops whole facts.* The project meta line (`SegmentLabel`) removes " · "
    segments from the right when the width is short; it never elides inside a word.
- Empty states are one trade-word line and the action, never a description of what the block is for
  ("No projects published yet." + Publish a project; "Nothing sent to you yet."; the hub: "Pick a
  shared folder, for example \\nas01\Project\_ProjectOpenerHub." + Connect). A control that can do
  nothing is hidden (Re-check with no projects, Refresh with no hub).
- Settings rows use one grammar: every control has its label above it (`field_block`), including
  Theme | Accent | Density, whose three blocks sit on one top with every control row at the
  control height (34 px) and its contents centred.
- The sidebar names the product and the company on one line each ("Dexterity Design Services");
  the legal name lives on Updates → Diagnostics only. Pulses (opened, published, sent) carry the
  project's title, so one object has one name across Team pulse and Activity.
- Once a newer installer is downloaded, the "mirror the current version" control under LAN mirror
  is hidden: the one mirror action on the screen is the downloaded version's.
- A lone card in the last row of a grid keeps its column width, left-aligned; two or more share the row.
- **Every page fits the 1040 × 660 minimum window**: `tools/smoke_ui.py` fails when any page's minimum
  width exceeds the content area beside the sidebar, and `test_every_page_fits_the_minimum_window`
  checks the same. Home's two side-by-side blocks (the drive map, Team pulse) stack below 960 px of
  page width, as the project page's side column does below 1000 px; names, mappings and usage on
  rows are `ElidedLabel`s so no row can widen a page.
- The register's By column is identity text: fixed width, left-aligned, header the same; Rev and
  When stay right-aligned figures.
- A drive row used by several projects names the jobs in its cell ("P12513 · ANTEO", up to two,
  then "+N") while the button carries the count; a single project reads "1 project · P12513".
- The project meta line drops facts by priority: the opened count first, then launch sets, then
  the enabled count; the health fact is the last one standing (`SegmentLabel.set_segments(…,
  drop_order=)`).
- The launch-sheet footer omits the elapsed time under 0.1 s. Busy progress (no size yet) uses the
  indeterminate bar on a tinted well; a determinate bar shows the true ratio.

## Dialogs

One form grammar (`widgets/dialogs.py`, `_BaseDialog`):

- Heading 16 pt 600; an optional grey line under it naming the object ("P12513 As-built
  isometrics"), never the object inside the heading in quotes.
- Labels **above** fields (`field_block`), 500 weight; placeholders are examples, never labels.
  One faint help line under a field only where it earns its place; it says what the field does,
  not what the interface is.
- Two short fields share a row (Client | Job number, Type | Group); everything else is one column.
  A dialog stays under 640 px tall so it fits a 768 px laptop: Notes are edited on the project page.
- Validation is inline: `show_error(text, widget)` puts the sentence above the buttons, outlines
  the field in the negative colour (`[invalid="true"]`) and focuses it; the outline clears as the
  user types. No `QMessageBox`.
- Buttons right-aligned: Cancel, then the confirming button named for its action ("Create
  project", "Add item", "Send", "Publish", "Post"). The confirming button is the default, so Enter
  accepts and Esc cancels. A field that uses Enter itself (the tag editor) consumes the key.
- Confirmations (`ConfirmDialog`, via `confirm(..., ok_text=)`): the question names the object and
  its consequence; the confirming button names the action. For a destructive action it is outlined
  in the negative colour and **Cancel takes the default and focus**, so Enter never deletes. Qt's
  own Import-mode box keeps Merge (AcceptRole) as the safe default.
- Command palette rows are grouped under grey headings (Projects, Launch sets, Items, Actions);
  arrow keys skip headings; actions show their shortcut on the right; a miss says
  "Nothing matches “…”".

## Launch sheet

Opening a project is the product's one moment, so it gets live feedback instead of a result toast
(`widgets/launch_sheet.py`):

- One frameless surface, 640 px wide, centred over the content area (never over the sidebar), with
  the toast's drop shadow (the floating things are the only ones with a shadow). Title "Opening
  <project>" (16 px 600) and one grey line "<N items> · <client> · <job>" (the launch set's name
  sits after the count when a set is opened).
- One row per item **in this launch** (enabled items, or the set's items): group (faint, left),
  kind icon, name over the resolved path (faint, elided in the middle), status pill on the right.
  The pill is the project page's pill, same levels and words: queued rows have none, the item
  being tried shows "Opening…" (neutral), then Opened (ok), Not found (warn), Server offline
  (bad), Undefined variable (warn), Skipped (neutral) or Failed (bad, tooltip says why).
- A 3 px progress line under the heading; the list scrolls past 60 % of the window height.
- Footer: bold "N opened" · "M skipped" · elapsed seconds (tabular figures); on the right the
  project's launch sets as small ghost pills that open that set.
- It closes itself 2.5 s after every item has **Opened**; when anything did not, it stays until
  × or Esc. A new launch replaces its content. Tab reaches × and the launch-set pills.
- It is feedback, not a notification: it shows with "Show notifications" off. When the window is
  hidden or minimised (a tray launch) there is no sheet and the tray balloon summarises as before.
- Compact density tightens the rows (40 px instead of 48).

## Motion

Motion is part of the look in 4.0, but it never slows work. Lists, navigation, typing and scrolling
stay at frame rate at every motion level, and every effect below has a still form.

| Move | Spec | Where | Levels |
|---|---|---|---|
| Feedback | press 90 ms, hover 140 ms, state 180-240 ms; exits faster than entrances; no bounce | everywhere | rich, purposeful (x0.6) |
| Rise | opacity 0 to 1, 10-12 px up, blur 6 px to 0 (blur in rich only), 600-700 ms, staggered 60 ms | once per page arrival, never on a data refresh | rich, purposeful (fade only) |
| Count-up | 0 to value, 900 ms, ease-out cubic, after the rise; streak squares pop 45 ms apart | Today's stat numerals | rich, purposeful |
| Shine | a soft highlight sweeps across the amber primary every 4.5 s | Today's Resume only | rich, active window only |
| Breathe | the hero's mist glow scales 0.96 to 1.04 and back over 6 s | Today's hero | rich, active window only |
| Line of flow | brand table: draws to the far node (1.6 s), then an amber slug travels every few seconds; done = far node fills amber and a tick draws in | restore plan, hub link, any transfer | rich (loops), purposeful (one pass, then still) |
| Space Map physics | bubbles drift gently, can be dragged and bump each other; amber = duplicate or stale | Space map | rich (drift), purposeful (settle, then stop), off (packed, still) |

Easing: `cubic-bezier(.2,.7,.2,1)` for entrances and feedback (`Easing.Bezier`), `cubic-bezier(.65,0,.35,1)`
for flow. Durations scale with `app.ui.k`; loops are gated by `app.ui.ambient` (see Motion levels). Site:
the same moves, with a `prefers-reduced-motion` fallback that keeps the content.

## Copy

Sentence case. Controls name their action ("Open project", "Publish to Team Hub", "Download for
Windows"). Errors name the problem and the recovery, once (never the same message in two
banners). No genre verbs (unlock, seamless, supercharge). The product's own words: project, launch
set, item, hub, inbox, revision, path. Plurals are spelled out by `cards.plural` ("1 item",
"2 items"), never "item(s)". Status words are the pill's words everywhere ("not found", "server
offline", "undefined variable"), not the status keys. Relative times are lower-case mid-sentence
("opened 15×, last just now"); a count of zero says the true thing ("never opened", "No items
yet") instead of "0 of 0"; an empty workspace never claims "every path is reachable" ("No paths to
check yet."). Quotation marks are curly (‘…’). No line describes the interface ("this page shows…"); a sentence under
a heading is a finding, a count or the next step.

## Icon

Flat: an accent-green squircle, a white folder with its flap lifting and an arrow leaving it to the
right. No gradient, no glow. Source `resources/icon/app.svg`; `tools/build_icon.py` renders the PNG
sizes and `app.ico`. *Open (4.0):* whether the app icon moves to the brand teal and amber. The
sidebar already carries the Dexterity mark (`logos/dexterity-mark-*.png` from the kit, copied into
`resources/`), which is never redrawn.

## Checks before shipping a screen

Contrast computed, not eyeballed (`tools/check_contrast.py`, both themes, the brand tokens);
**one amber control per screen**; glass only on floating surfaces and the Today hero; mono only for
section labels, annotations and counts, never for a sentence; Archivo only for titles, the hero and
numerals; no resting shadow on a card; no gradient on text, buttons or data; every number that lines up
tabular; the screen names the product and offers its main job in one click; every effect has its
purposeful and off forms (screenshot all three levels); both themes screenshotted by `tools/smoke_v4.py`
with no Qt or QML warnings; the bench (`--bench`) holds Rich on the reference PC.

## Project Opener 4: Stage (the Qt Quick shell)

Concept "Stage" (docs/V4-BRIEF.md section 4, the concept round's `concept-1-stage`), built in Qt Quick
(`project_opener/qml`).  Everything above still holds; this section adds what the stage changes.
Items marked *superseded* are what is built today and are replaced by the 4.0 Drafted Glass rules above.

- **Shell** *(superseded by the 236 px labelled sidebar in "Shape and space"; the rail stays as its folded
  form below 1100 px).* A 68 px rail on the ground (the mark, Search, Home, Activities, Projects, Team Hub, Updates,
  Settings, the person at the foot); the current route is the raised `surface_2` circle; counts only on the
  hub (inbox) and my open tasks.  Labels are tooltips and accessible names.  One page at a time, routed by
  `app.ui.route`; sheets, the palette and toasts float above it.
- **Today** *(to build; replaces "Home is a stage")*. The approved board, top to bottom:
  - Title row: "Today", the date as a mono label, then "Start from what's open" and "Park day" (with its
    shortcut) as outlined pills.
  - **Hero**, a glass card with the 2 px teal top rule and the breathing mist glow. Left: a mono label
    ("Parked yesterday 18:42 · P12513 back-check"), the Archivo heading "Pick up where you parked", the
    person's Park note in Cormorant italic, then **Resume activity** (the screen's one amber control, with
    the shine) and "Pick another moment" (opens Time travel). Right: the restore plan, with a mono label,
    the window count, chips for the windows that will reopen (+N), and the line of flow from "Parked
    18:42" to "Ready". With nothing parked, the hero offers the last activity instead; with no activity
    at all, it offers New activity.
  - **Four stats**: Tasks due today (of N open, and who from), Changed overnight (files, with a
    sparkline), Day streak (days, with squares), Setup saved this week (h m, and how many restores).
  - **Three panels**, sharing a bottom edge: Time travel this week (a lane per day, a tick per snapshot;
    hover or click shows when, the window count and the activity, and Restore), Office pulse (avatar,
    name, current project; green = active, amber = idle, faint = away, on leave names the handover),
    and Space map / Wrapped (one panel that flips between the bubbles and the week's board, with the
    "Show me on the office board" switch).
  - Resume opens through the dock, as below.
- **Home is a stage** *(superseded by Today)*. The Resume band (the one flat colour field, `field_mint`; Resume is the screen's
  one primary while it waits) and then the current activity in the centre at full size: icon tile and title,
  its line, and the three questions in three columns (what was open, health on this PC, the task and the
  watchers).  The others stand in the wings, smaller (scale .94) and dimmer (62 %); below 1180 px of page
  width they fold under the centre as two compact cards.  The footlights strip under the stage: Drives on
  this PC, My tasks, the Office; the three share a bottom edge, and stack two-over-one below 1000 px.
- **The dock is the centre grown.** Open activity: the wings recede (scale .84, fade), the centre grows to
  the page width (420 ms, OutCubic on x, y, width, height), rows arrive in launch order 60 ms apart with an
  8 px rise, each pill reads Opening… then settles (fill cross-fade 180 ms, the word swaps at the midpoint).
  All opened: 1.2 s later the scene becomes the activity page.  Anything not opened: the dock stays with
  "Open the N again".  Esc or × closes it.  Away from Home the same dock is a card (`sheets/LaunchDock.qml`).
- **The activity page** (board B): the header carries the capture switch, Snapshot now, Add a window and
  the one filled button that follows what is waiting (Save N new as items, else Snapshot now, else Open
  activity).  Left: Open now, worst first; a window with no path is Desk's **dashed tile** (1 px
  `border_strong`, 4/3 dash, radius 10) with the title in curly quotes, the reason, Attach a path and
  Ignore; nothing is guessed.  Right: the launch record ("Opened at 09:12"), the task and watchers, Control
  room's **Monitors panel** (this PC's screens to scale with the windows seen on each), the checkpoints.
- **The office breathes once.** A colleague who comes online gets one ring that grows 8 to 20 px beyond
  the avatar and fades over 2.4 s.  Only in rich motion and only while the window is active.
- **Colour** *(the green accent is superseded by the brand tokens in "Colour"; the QML-only tokens stay)*.
  Unchanged discipline: identity (6 px dot, the icon tile's tint) and health (the pills) only.
  QML reads `app.ui.tokens` (= `ui.theme.build_tokens`) plus three QML-only tokens: `shadow_q` and
  `shadow_soft` (the floating shadow as `#AARRGGBB`, two offset rings on dark only: QML cannot parse `rgba()` and the
  software renderer has no blur; on light both are transparent and the surface's 1 px `border_strong` ring is
  the whole edge, because an offset ring read as a misregistered second shape), `scrim` (the 40 % ink behind a sheet or the palette).  With the default
  green, the dark accent is this file's `#3BC98F` with ink on it (`build_tokens`' generic lightening gives
  `#62A994`, which reads as a disabled control on the dark ground).
- **Icons** are Phosphor (regular) from the icon font qtawesome ships, one stroke everywhere; 3.x
  `fa5s.*` names on migrated activities map to Phosphor names (`ui_state.FA_TO_PH`).
- **Sheets** are the one dialog grammar (`components/Sheet.qml`): scrim, 10 px radius surface (glass in rich
  motion; 16 px and opaque as built today), heading 21 px 600 and one grey line naming the object, labels above fields, the error above the buttons, Cancel
  then the named confirming button; destructive = outlined negative with Cancel as the Enter default; at
  most 640 px tall, the body scrolls.  The @ picker and the "For" field float in the window's overlay so a
  sheet never clips them.
- **Tick lists** (owner decisions, 5 November 2026: "everything open, I untick"; "a tick list, items
  pre-ticked"): `components/TickList.qml` in `sheets/SaveNewSheet.qml` and `sheets/ResumeSheet.qml`. Rows sit
  under small muted group headings, most likely first; a row that cannot be added or reopened keeps an empty
  box at 45 % and says why ("No file path: cannot be reopened"); the confirming button counts the ticks
  ("Save 2 as items", "Reopen 9").  Nothing is ticked that the evidence does not support.
- **The pill's panel** is the main window's surface (`surface`, `border_strong` edge) with the same
  text tokens; its opening animation always completes (a timer finishes it), so it never rests half-faded.
  In rich motion it is glass (see "Glass"); otherwise it is opaque.
  Rows offer Ignore on hover; the note under the list offers "Always ignore <app>" and Undo.
- **Every page fits 1040 × 660.** Each page declares `minimumWidth` (860, beside the 68 px rail);
  `tools/smoke_v4.py` fails when one exceeds the 972 px beside the rail, when any visible item runs past
  the page's right edge at the minimum window, or on any Qt or QML warning.

### Motion levels

`quick/motion.py` decides; `app.ui.k` scales every duration (rich 1, purposeful 0.6, off 0) and
`app.ui.ambient` gates loops (rich only, and QML adds "window active").

| Level | When (auto) | What moves |
|---|---|---|
| rich | a GPU and a screen above 1366 × 768 | everything, including the office's breath; glass, the isometric grid, the rise's blur, shine, breathe, line-of-flow loops, Space Map drift |
| purposeful | software rendering, a screen at or below 1366 × 768, Windows animations off, battery | every transition at 0.6×, no loop; surfaces opaque, no grid, no blur; rise is a fade; line of flow runs once; Space Map settles, then stops |
| off | remote desktop | nothing; every screen complete and still; numerals show their value, the Space Map is packed |

Effects are dropped in this order when the guard lowers a level: glass and blur first (the costliest on
an old GPU), then the grid and glows, then loops, then durations. Lists, navigation and typing are never
animated in a way the guard has to measure.

The runtime guard measures each dock opening over its grow (`frameSwapped` stamps for 420 ms × k plus
80 ms, `motion.dock_measure_ms`): two in a row over 33 ms mean or 120 ms worst 1 % drop one level, saved in
`Settings.motion_reduced_to`, said once, never climbing back by itself; a choice in Settings > Appearance
clears it.

The guard judges the grow's frames after the first (`motion.guard_stats`, round 3). The first interval,
from the click to the first frame, is the opening's response time, and the guard does not count it:

- **What it carries.** That frame holds the opening's one-time work: the dock's rows and bindings, plus
  the launcher starting Excel, Word and a PDF viewer beside the app. That contention is outside the app's
  control, and it is the same at every level, Off included. A lower level cannot shorten it, so counting
  it reduced motion for no gain and never gave it back.
- **Six real launches (round 3, `run-fin2_1..6`).** Two .xlsx, a .docx, a PDF and two folders on an
  i7-6700 with a GT 710:
  - the first interval was 118–379 ms;
  - without it, the guard's mean was 14.6–17.6 ms and its worst 1 % 21.6–40.9 ms, and Rich held in 6 of 6;
  - counting it (the round-2 guard), the worst 1 % was 156–314 ms and Rich was dropped on a PC that animates
    the grow at 60 Hz.
- **What the bench shows.** `--bench` (a dry run, nothing opened; `temp\fin\bench\frozen-2.txt`, the
  frozen exe on the same PC) measured Rich at a worst 1 % median of 22 ms (max 32) and Purposeful at a median
  of 23 ms (max 56). It also reports the response time on its own (first frame median and max per level), so
  a slow opening stays visible without changing the motion level.
- **Round 4, the frozen exe from local disk** (`build\local-dist\bench\run-1..2`, same PC): Rich mean
  16–17 ms with a worst 1 % median of 20–22 ms (max 47), Purposeful 13–16 ms (median 20 ms), Rich held in
  both runs; first frame after the click median 58–59 ms (max 223). Six real launches with the dock driver
  (`fin4\runs\final_1..6`): guard mean 12.6–16.7 ms, worst 1 % 20.2–33.6 ms, Rich held in 6 of 6.
- **The stall after the grow is not ours to fix.** Those launches still show one 0.6–0.9 s gap after the
  grow. Frame logs show the GUI thread doing native/QML event work in it, not rendering and not Python (the
  Python stack is only `app.exec`), and it coincides with the first Explorer window appearing. No
  window-active gate in the app does work on a focus change, so there is nothing to debounce.

The window is cut where the grow ends (`motion.window_stamps`). Its timer fires late when the GUI thread is
busy, and in round 3 one closed 2.2 s late and counted a 750 ms stall after the grow. A stall that starts
inside the grow still counts, up to the window's end.

The limits stay at 33 ms and 120 ms. With about 25 frames in a grow, the worst 1 % is the single longest
animation frame, so 120 ms still catches one visible hitch in the grow itself.

Feedback durations follow the craft table:
press 90 ms, hover 140 ms, state 180-240 ms, the dock's grow 420 ms; exits are faster than entrances; no
bounce.
