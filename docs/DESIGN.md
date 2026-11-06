# DESIGN.md - Project Opener 3 visual system ("Aurora, disciplined")

The durable visual decisions for the desktop app (`project_opener/ui`) and the landing page
(`site/`). Every token, rule and exception lives here; code references tokens, never raw values.
Companion: `docs/PRODUCT.md` (who uses it and for what).

## Where it comes from

Concept 2 "Aurora Glass" was chosen by the owner (1 Nov 2026) and then disciplined with two
published design methods, `taste-skill` v2 and `impeccable`. Where the two conflicted with the
chosen concept, the concept's identity won (impeccable: "the brief wins"); where the methods
sharpened it, they won. Kept from Aurora: light-first, soft luminous colour, generous white,
large radii, pill controls, friendly tone, a composed dark mode. Changed by the methods:

| Aurora as drawn | Shipped | Why |
|---|---|---|
| Indigo→pink gradient accent, gradient word | One flat accent, aurora green `#0E7C5B` | Gradients and violet/indigo are the most recognisable generated look; a real aurora is green |
| Blurred pastel blobs, frosted glass, backdrop blur | Flat pastel colour fields (site); opaque surfaces one tone step apart (app) | Glass and glow are banned; fields are the stronger colour move |
| Mono eyebrows, tracked uppercase section labels | Sentence-case headings in the text face | Eyebrows are a ban in both methods |
| Icon in a tinted circle on every stat tile and card | Label over value in one divided strip; one plain grey icon where it helps | 0 of 23 studied product screens do it |
| Soft shadow under every card | 1 px border, no shadow; shadows only on what floats (menus, toasts, palette, dialogs) | |
| Every card with a filled gradient "Open" pill | One filled accent control per screen; other actions are outlined pills | Accent under 5 % of pixels; rarity gives it force |
| Monospace paths | Paths in the text face, muted | Mono only for real code |
| Navy-tinted dark mode | True neutral darks with a faint green tint | No navy/slate dark themes |

## Type

- **App (Operate mode): one family, Onest** (OFL, bundled in `resources/fonts/Onest[wght].ttf`,
  loaded by `theme.apply_theme`). Fallback: Segoe UI Variable Text, Segoe UI, Arial.
  Roles (pt → px at 96 dpi): title 18 pt / 24 px weight 600; section 12 pt / 16 px 600;
  KPI value 18 pt / 24 px weight 400; body, nav, cells 10 pt / 13.3 px 400; small 9 pt / 12 px.
  Nothing under 9 pt. Tabular figures on every number that lines up (`QFont.setFeature("tnum")`).
  Sentence case everywhere; no tracked uppercase; no display face in the app.
- **Site (Persuade mode): Unbounded 600** for the two headline sizes (hero `clamp(2.6rem, 1rem + 5.2vw, 4.5rem)`,
  tracking -0.04em, leading 1.0; section headings `clamp(1.9rem, 1rem + 2.6vw, 3rem)`), **Onest** for
  everything else (body 17-19 px, lead 20-26 px, small 13-14 px). Five sizes, far apart. Every headline
  two lines or fewer at 390, 768 and 1440 (hero ≤ 32 characters).

## Colour

Roles, light theme (`theme.build_tokens(dark=False)`):

| Token | Value | Use |
|---|---|---|
| `bg` | `#F5F8F6` | ground, tinted from the product's world (a faint mint) |
| `bg_alt` | `#F5F8F6` | sidebar = ground (never a dark or tinted sidebar on light) |
| `surface` | `#FFFFFF` | cards, inputs |
| `surface_2` | `#EEF3F0` | active nav pill, hover, raised wells |
| `surface_3` | `#E4EBE7` | pressed |
| `border` | `#E3E9E5` | card and row edges |
| `border_strong` | `#C9D3CD` | control borders, scrollbar |
| `text` | `#141A17` | ink |
| `text_muted` | `#5B6660` | secondary (5.9:1 on white) |
| `text_faint` | `#66706A` | meta, placeholders (4.7:1 on white) |
| `accent` | `#0E7C5B` | the one accent: primary action, focus, selection, data hue |
| `accent_hover` | `#0B6A4E` | |
| `accent_soft` | `#DDF3EA` | selected rows, checked chips, info banners |
| `accent_fg` | `#FFFFFF` | text on accent |
| `success` / `warning` / `danger` / `info` | `#1F7A4D` / `#92400E` / `#B42318` / `#175CD3` | status text and icons (all ≥ 4.5:1 on white) |
| `pill_*_bg` / `pill_*_ink` | ok `#DCFAE5`/`#04250E`, warn `#FFF4D6`/`#7A3E00`, bad `#FEE4E2`/`#7A1C14`, info `#E0ECFF`/`#0B3A8C`, neutral `#EEF3F0`/`#3A443E` | status pills: pale tint, dark text of the same hue |
| `field_mint` / `field_sky` / `field_blush` | `#DDF3EA` / `#DCEBF7` / `#FCE4E6` | flat colour fields (site sections, the one "aurora" of the app: the Home greeting band) |
| `shadow` | `rgba(16,24,20,0.12)` | floating surfaces only |

Dark theme: `bg` `#0F1211`, `surface` `#171B19`, `surface_2` `#202623`, `surface_3` `#2A312D`,
`border` `#262D29`, `border_strong` `#3A443E`, `text` `#ECF0ED`, `text_muted` `#A8B3AD`,
`text_faint` `#8A958E`, `accent` `#3BC98F` with `accent_fg` `#0F1211`, `accent_soft` `#163A2C`,
status `#3FC07A` / `#F5B73B` / `#F07070` / `#6FB1FF`, pills on dark tints of themselves
(`#172A1D`, `#2E2410`, `#2C1A1A`, `#14243A`). Dark is composed, not inverted: lighter weights, more
leading, surfaces lift by lightness only.

Proportion: ground 70-90 %, ink, accent under 5 % of any screen. Project colours are data (the
project's own icon tint and a 6 px dot), never chrome. People get a stable pale tint of their own hue
(`Avatar`), identity not data. User-selectable accent is kept (Settings → Appearance) with ten
flat choices that each pass 4.5:1 with white text.

## Shape and space

- 4 px base. Card padding 20 (comfortable) / 14 (compact). One gap value per screen: 16.
- Radii, soft family: cards 16, inputs 10, pills 999 (buttons are 34 px tall → radius 17), chips 999.
- Borders 1 px (`border`); controls one step stronger. A border or a shadow, never both. Cards have no
  shadow. Menus, popovers, toasts, the command palette and dialogs float: `0 8px 24px shadow`.
- Sidebar 232 px on the page ground, no border; collapsed 68. Active item: `surface_2` pill, label
  unchanged. Counts only on queues that need action (Inbox).
- Page title 24 px 600, one per page, a noun (Home keeps its greeting: it is a personal home). One
  optional grey line under it: the finding, never a description of the interface.
- KPIs: one card divided by 1 px rules, label (12 px grey) over value (24 px 400). No icons, no
  sparklines, no deltas without their window.
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

App: feedback only (press, hover, focus, a menu or toast arriving), 150-250 ms, `OutCubic`. No
entrance choreography. Site: one signature move (the hero's launch sequence), staggered entrances
(heading → text → picture, 60-90 ms apart, 16-24 px rise, once), hover/press feedback, one moving
picture; everything has a `prefers-reduced-motion` fallback that keeps the content.

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
sizes and `app.ico`.

## Checks before shipping a screen

Contrast computed, not eyeballed (`tools/check_contrast.py`); one filled accent per screen; no
eyebrow, no icon circle, no gradient, no resting shadow; every number tabular; the screen names the
product and offers its main job in one click; both themes screenshotted by `tools/smoke_ui.py`,
including every dialog and state (`--all`), compact density (`--density compact`) and 2×
(`--scale 2`), with no Qt warnings in its output.

## Project Opener 4: Stage (the Qt Quick shell)

Concept "Stage" (docs/V4-BRIEF.md section 4, the concept round's `concept-1-stage`), built in Qt Quick
(`project_opener/qml`).  Everything above still holds; this section adds what the stage changes.

- **Shell.** A 68 px rail on the ground (the mark, Search, Home, Activities, Projects, Team Hub, Updates,
  Settings, the person at the foot); the current route is the raised `surface_2` circle; counts only on the
  hub (inbox) and my open tasks.  Labels are tooltips and accessible names.  One page at a time, routed by
  `app.ui.route`; sheets, the palette and toasts float above it.
- **Home is a stage.** The Resume band (the one flat colour field, `field_mint`; Resume is the screen's
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
- **Colour.** Unchanged discipline: identity (6 px dot, the icon tile's tint) and health (the pills) only.
  QML reads `app.ui.tokens` (= `ui.theme.build_tokens`) plus three QML-only tokens: `shadow_q` and
  `shadow_soft` (the floating shadow as `#AARRGGBB`, two offset rings on dark only: QML cannot parse `rgba()` and the
  software renderer has no blur; on light both are transparent and the surface's 1 px `border_strong` ring is
  the whole edge, because an offset ring read as a misregistered second shape), `scrim` (the 40 % ink behind a sheet or the palette).  With the default
  green, the dark accent is this file's `#3BC98F` with ink on it (`build_tokens`' generic lightening gives
  `#62A994`, which reads as a disabled control on the dark ground).
- **Icons** are Phosphor (regular) from the icon font qtawesome ships, one stroke everywhere; 3.x
  `fa5s.*` names on migrated activities map to Phosphor names (`ui_state.FA_TO_PH`).
- **Sheets** are the one dialog grammar (`components/Sheet.qml`): scrim, 16 px radius surface, heading
  21 px 600 and one grey line naming the object, labels above fields, the error above the buttons, Cancel
  then the named confirming button; destructive = outlined negative with Cancel as the Enter default; at
  most 640 px tall, the body scrolls.  The @ picker and the "For" field float in the window's overlay so a
  sheet never clips them.
- **Tick lists** (owner decisions, 5 November 2026: "everything open, I untick"; "a tick list, items
  pre-ticked"): `components/TickList.qml` in `sheets/SaveNewSheet.qml` and `sheets/ResumeSheet.qml`. Rows sit
  under small muted group headings, most likely first; a row that cannot be added or reopened keeps an empty
  box at 45 % and says why ("No file path: cannot be reopened"); the confirming button counts the ticks
  ("Save 2 as items", "Reopen 9").  Nothing is ticked that the evidence does not support.
- **The pill's panel** is the main window's surface (`surface`, opaque, `border_strong` edge) with the same
  text tokens; its opening animation always completes (a timer finishes it), so it never rests translucent.
  Rows offer Ignore on hover; the note under the list offers "Always ignore <app>" and Undo.
- **Every page fits 1040 × 660.** Each page declares `minimumWidth` (860, beside the 68 px rail);
  `tools/smoke_v4.py` fails when one exceeds the 972 px beside the rail, when any visible item runs past
  the page's right edge at the minimum window, or on any Qt or QML warning.

### Motion levels

`quick/motion.py` decides; `app.ui.k` scales every duration (rich 1, purposeful 0.6, off 0) and
`app.ui.ambient` gates loops (rich only, and QML adds "window active").

| Level | When (auto) | What moves |
|---|---|---|
| rich | a GPU and a screen above 1366 × 768 | everything, including the office's breath |
| purposeful | software rendering, a screen at or below 1366 × 768, Windows animations off, battery | every transition at 0.6×, no loop |
| off | remote desktop | nothing; every screen complete and still |

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
- **Six real launches (round 3).** Two .xlsx, a .docx, a PDF and two folders on an i7-6700 with a GT 710:
  - the first interval was 158–243 ms, while every later frame of the grow was 34 ms or less;
  - counting the first interval, the guard saw a worst 1 % of 156–314 ms and dropped Rich on a PC that
    animates the grow at 60 Hz;
  - without it, the worst 1 % is 19–33 ms.
- **What the bench shows.** `--bench` (a dry run, nothing opened) measured worst 1 % of 47–72 ms. It also
  reports the response time on its own (first frame median and max per level), so a slow opening stays
  visible without changing the motion level.

The window is cut where the grow ends (`motion.window_stamps`). Its timer fires late when the GUI thread is
busy, and in round 3 one closed 2.2 s late and counted a 750 ms stall after the grow. A stall that starts
inside the grow still counts, up to the window's end.

The limits stay at 33 ms and 120 ms. With about 25 frames in a grow, the worst 1 % is the single longest
animation frame, so 120 ms still catches one visible hitch in the grow itself.  Feedback durations follow the craft table:
press 90 ms, hover 140 ms, state 180-240 ms, the dock's grow 420 ms; exits are faster than entrances; no
bounce.
