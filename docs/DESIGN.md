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
- Empty states keep the frame and the heading and say the next step in one sentence.

## Motion

App: feedback only (press, hover, focus, a menu or toast arriving), 150-250 ms, `OutCubic`. No
entrance choreography. Site: one signature move (the hero's launch sequence), staggered entrances
(heading → text → picture, 60-90 ms apart, 16-24 px rise, once), hover/press feedback, one moving
picture; everything has a `prefers-reduced-motion` fallback that keeps the content.

## Copy

Sentence case. Controls name their action ("Open project", "Publish to Team Hub", "Download for
Windows"). Errors name the problem and the recovery. No genre verbs (unlock, seamless, supercharge).
The product's own words: project, launch set, item, hub, inbox, revision.

## Icon

Flat: an accent-green squircle, a white folder with its flap lifting and an arrow leaving it to the
right. No gradient, no glow. Source `resources/icon/app.svg`; `tools/build_icon.py` renders the PNG
sizes and `app.ico`.

## Checks before shipping a screen

Contrast computed, not eyeballed (`tools/check_contrast.py`); one filled accent per screen; no
eyebrow, no icon circle, no gradient, no resting shadow; every number tabular; the screen names the
product and offers its main job in one click; both themes screenshotted by `tools/smoke_ui.py`.
