# Design system: Kiln Intelligence × Astrikos AI × Dalmia

**Direction:** Astrikos AI's industrial intelligence layer, expressed through a Dalmia Cement visual environment, led by **green**.
Precision, depth, trust. Not a SaaS template, not a sustainability site: green is the brand language, the subject is the kiln.

The hierarchy on every page is **brand → product → context → insight → evidence → detail**:
the lockup and product line (top bar), the page band (title and question), the one insight statement,
then white analytical surfaces, then detail.

## Where the tokens live

| File | Holds |
|---|---|
| `src/theme.ts` | The only source of colour, gradient, elevation, motion and font: `colors` (the green scale), `semantic` (roles), `dalmia`, `gradient`, `status`, `track`, `systemColor` / `systemLabel`, `severityColor`, `issueColor`, `elevation`, `motion`, `font`, `chart`, `echartsTheme`. Plain TS. |
| `tailwind.config.ts` | Maps theme.ts to Tailwind names (`forest`, `brunswick`, `moss`, `eucalyptus`, `sage`, `lichen`, `polar`, `mist`, `emerald`, `ink-*`, `track-*`, `page`…), the type scale, shadows, `bg-hero` / `bg-sidebar` / `bg-deck` / `bg-accent` / `bg-rule` gradients and the motion durations. |
| `src/index.css` | Surface classes (`.card`, `.surface-dark`, `.atmosphere`, `.surface-glass`, `.hatch`), type roles (`.eyebrow`, `.eyebrow-dark`), buttons, chips, focus rings, motion keyframes, reduced motion, print. Reads tokens through `theme()`. |
| `src/charts/tooltip.ts` | The one tooltip layout. Escapes every string, including swatch colours. |
| `src/copy.ts` | Every user-facing string. `tests/wording.test.ts` scans it. |

**Rule:** no hex or `rgb(a)`/`hsl` literal anywhere in `src/` except `theme.ts`. `tests/tokens.test.ts` enforces it.
The logo SVGs in `src/assets/brand/` keep their own artwork colours. `index.html` carries the theme colour and favicon.

## Colour: structure, attention, secondary, breathing room

| Role | Tokens | Use |
|---|---|---|
| Structure and authority | `forest` #0f2f24 (Deep Forest), `brunswick` #0c4137, `moss` #1f4d3a | Top bar, sidebar, hero and deck surfaces, headings (`ink` = Deep Forest), actions on light (Brunswick), borders on dark (Moss) |
| Attention and interaction | `emerald` #06d6a0 | Active nav, selected timeline position, primary button on dark, focus ring on dark, eyebrows on dark, key metric. Never text on light |
| Secondary analytical layers | `eucalyptus` #4f8f75, `sage` #9fc3b2, `moss` | Comparison series, "Normal" on the dark track, reference lines, tertiary text on dark |
| Breathing room | `polar` #e6fbf6, `lichen` #e7f1ec, white | Tints and panels, page canvas, cards |

Brunswick, Emerald and Polar are the canonical palette. The tonal greens come from the second reference by its **RGB values** (its printed HEX values conflict): Deep Forest 15·47·36, Moss Shadow 31·77·58, Eucalyptus 79·143·117, Sage Mist 159·195·178, Pale Lichen 231·241·236. `mist` #c5ddd2 (secondary text on dark) is a Sage→Polar blend; `emeraldDeep` #0b9f7a (graphics on light, the primary chart series, 3.3:1 on white) and `emeraldInk` #0a6b50 (text on light, 6:1) are Emerald for light surfaces, because #06d6a0 is only 1.9:1 on white.

Contrast on dark: Emerald on Brunswick 6.1:1, Sage 6.0:1, Mist 10:1. Focus ring: Brunswick on light, Emerald with a Deep Forest halo on dark.

### Gradients (all in `theme.ts → gradient`)

Every one travels the same ladder — **Abyss → Deep Forest → Brunswick → an Emerald light** — and every one is radial first: a flat linear wash reads as a recoloured template, radial light reads as atmosphere. `abyss` #08201a is the darkest step of the Deep Forest family and exists **only** as a gradient anchor and dark edge; it is never a flat fill behind content.

Strength is a hierarchy, not a default:

| Layer | Gradient | Strength |
|---|---|---|
| Hero bands, top bar | `bg-hero`, `bg-header` | Strongest: an Emerald sun off one corner, a second low pool, dark Abyss edges |
| Console deck, sidebar | `bg-deck`, `bg-sidebar` | Medium: one corner light, plus a soft glow behind the timeline |
| Timeline well | `bg-track` | Recessed: an Abyss floor with one Emerald light rising from under the track |
| Page canvas | `gradient.canvas` | A whisper: a green descent from the dark band above, gone by the first card row |
| Rules | `bg-accent`, `bg-rule` | Emerald → Brunswick / → transparent: accent rules, the hairline under hero bands, the product-name rule |

Emerald behaves as **light, not paint**: radial, off-centre, never above 0.34 alpha. Ordinary cards get no gradient at all — cards, charts and controls are solids. If the gradient is the first thing noticed, it is too strong.

### Status colours (`status`, `track`)
Normal / Watch / Warning describe **historical analytical states**, not an alarm system: no flashing, no red panels, no "alert" wording. Normal is green (`#087f62` on light, Eucalyptus on the dark track), Watch muted amber, Warning a deeper warm tone, **Data gap is neutral slate** and is never a process colour. Colour is never the only signal: the word always ships with it.

Process systems keep a fixed categorical order (`systemColor`): teal-blue, violet, rose, Eucalyptus, slate, grey. Greens are reserved for brand and Normal. `systemLabel` picks the readable label colour on each fill.

Magnitude (period severity, issue severity) uses a Deep Forest → Sage ramp. Dalmia orange marks high-severity periods and period-start annotations only.

## Brand: the co-brand lockup

`components/Brand.tsx`. One capsule with two equal panels: the **Astrikos** artwork on `forest`, the **Dalmia Bharat** artwork on white. Both logos are the supplied artwork, unrecoloured, placed on grounds they were designed for, with a small `×` chip on the seam.

- `src/assets/brand/astrikos.svg` is byte-identical to the supplied file.
- `src/assets/brand/dalmia.svg` differs from the supplied file **only in its `viewBox`** (cropped to the artwork's bounds). Every path is unchanged.
- The lockup appears **once**, top-left of the top bar. The sidebar and footer are text only.
- The top bar reads **"Ariyalur / Historical analysis · Jun–Aug 2025"** with a history icon. There is no live-status dot. The second line needs 1280 px; below that the plant name alone shares the bar, and below 1024 px the whole block gives way to the product name (the wording is still carried by the page ribbon, the footer and the screen-reader text).

### The product name is the product name

`Brand.tsx → ProductLine`. **KILN INTELLIGENCE** beside the lockup is the identity, not a navigation label: bold, tight (`-0.045em`), "Kiln" in Polar and "Intelligence" in Emerald, standing in the header's Emerald light (`.glow-text`), with a short Emerald rule and the plant caption under it. It is the strongest text in the bar by a wide margin, and the logos are **not** enlarged to match — the hierarchy is Astrikos × Dalmia → **KILN INTELLIGENCE** → supporting context.

Sizes step with the bar, and `--header-h` steps with them (`index.css`): 24 → 32 (768) → 48 (1024) → 56 (1280) → 64 px (1536), against a header of 4 → 4.5 → 5.25 → 6 → 6.75 rem. The ceiling at each width is set by the bar itself: the name is `whitespace-nowrap`, so at every breakpoint it must clear the lockup and the status block without running under them. Hidden below 640 px, where the page hero names the product instead.

## Pitch order and routes

Nav order = presentation order (← → in presentation mode): **01 Kiln Health Console** (`/console`), 02 Executive Summary (`/summary`), 03 Efficiency Story, 04 Abnormal Periods, 05 Alternative Fuel, 06 Data Readiness, 07 How we validated, 08 Roadmap & Value. `routes.tsx → pages` is the single order; `HOME` is `/console` and `/` redirects to it. Only the Summary changed URL (`/` → `/summary`). The sidebar groups are Intelligence (01–05), Evidence (06–07), Roadmap (08), each item numbered. The active item is an Emerald-tinted row with an inset ring and a thin Emerald bar, not a solid block.

## Backgrounds and surfaces

| Surface | Class | Look |
|---|---|---|
| Canvas | `body` | `lichen` with a faint Brunswick lift at the top |
| Surface | `.card` | White, 1 px `line` border, 1 px shadow |
| Open | (no box) | A 2 px top rule or an Emerald→Brunswick accent bar; `InsightCard`, `Lead` |
| Elevated | Drawer, tooltip | White drawer with a 3 px Brunswick top rule; tooltip is Deep Forest |
| Dark | `.surface-dark` | Brunswick → Deep Forest gradient, Moss border |
| Atmosphere | `.atmosphere` | The hero: Deep Forest → Brunswick, one Emerald light top-right, a fine 44 px grid that fades out, `ProcessLines`, and an Emerald hairline at the bottom edge |
| Glass | `.surface-glass` | 5% white on dark, only inside a hero |

`ProcessLines` is the industrial motif (kiln-shell arcs, flow lines, node ticks): decorative, `aria-hidden`, low opacity. There are no photographs.

## Type (2 families)

Inter for UI, headings and numbers (tabular figures with `.num`). JetBrains Mono (latin 400/500) for eyebrows and technical metadata.

| Class | Size / line | Role |
|---|---|---|
| `text-masthead` | 68/64 (58 at `sm`, 44 below) | The Executive Summary H1, "KILN INTELLIGENCE" |
| `text-hero` | 46/50 | Validation verdict |
| `text-numeral` | 56/56 | The core-finding numbers |
| `text-display` | 34/40 | Hero statement on narrow screens |
| `text-title` | 28/34 | Page H1, drawer title |
| `text-lead` | 22/30 | Lead statement |
| `text-section` / `text-kpi` | 18/25, 38/42 | Section and chart-card titles, KPI numbers |
| `text-card` / `text-body` / `text-label` / `text-caption` | 16 / 15 / 13 / 12 | Card title, body, labels, metadata |
| `.eyebrow` / `.eyebrow-dark` | 11/16, mono, caps | Kicker, KPI category, group heading (Emerald on dark) |

Executive Summary hero: eyebrow (Dalmia Cement · Ariyalur kiln) → H1 "KILN INTELLIGENCE" (68 px) → Emerald hairline → supporting sentence (17 px) → period chip → CTAs.

## KPI tiles

`KpiTile` with `category`: **category eyebrow → large number (+ unit, micro chart) → the metric's name in plain words → one context line → evidence line**. Without `category` it is the compact tile (label eyebrow → number → context), used on the Periods page. Names: "Process records analysed", "KPI-derived abnormal periods", "Efficiency deterioration index" (the index's real name: higher means worse), "Data quality issues caught".

## Page structure and card levels

`Page` (ui.tsx) = dark `atmosphere` band (eyebrow, H1, question, evidence badges) + content container. `PageBand` is the band alone (the Console memoises it). The Executive Summary and Validation have bespoke bands.

| Level | Components | Look |
|---|---|---|
| 1 Hero insight | Page band, Summary hero + core finding, Validation verdict, closing ask (`HeroBand`), `Lead` | Dark atmosphere, or a statement against an accent rule |
| 2 Primary evidence | `.card`, `ChartCard`, `KpiTile` | White, bordered; KPI tiles have a left accent rule |
| 3 Supporting | `InsightCard`, `.panel`, `.inset`, `.card-dashed`, `Source`, `Badge` | No shadow; dashed = illustrative or not yet operational |

## Charts

All colour from `theme.ts → chart`: green-grey axes, whisper grid, **Emerald-deep primary** (`#0b9f7a`), **Moss dashed comparison**, Sage reference, Dalmia orange for period-start annotations only. Tooltip: Deep Forest shell, white title, Mist rows, a short Emerald rule, an evidence note; HTML is escaped. Gaps (`null`) stay gaps: shaded and labelled on charts, hatched and labelled in the Console. Never interpolated. Every `ChartCard` has "View data", the accessible table.

## Console: one integrated historical timeline

The deck (`rounded-shell`, `bg-deck`, sticky on large tall screens) is **one container**, and the timeline inside it is **one object**. Nothing the timeline depicts floats outside its well: there is no legend above it, no labels beside it, no markers below it.

Deck, top to bottom:

1. **Deck header:** "Historical kiln console" and the selected timestamp (largest), the Kiln Health Index with its state word, the operating state (Kiln running / stopped, data available / none).
2. **The timeline well** — `bg-track`, `shadow-inset`, `overflow-hidden`, one border, about 196 px tall. Three fused parts, no gap between them:
   - **Internal header strip:** the title, the range of recorded history (derived from the data, e.g. "1 Jun – 23 Aug"), and the four state keys. The keys sit on the track's own strip, never floating above it.
   - **The lane** — every row shares one horizontal grid, so marker, ribbon, strip and scale line up exactly: the **marker flag** (an Emerald pill carrying the selected stamp, clamped inside the lane, with its caret at the true position) → the **state ribbon** (52 px; one column per day, the recorded share of Normal / Watch / Warning, Warning on top; columns butt together with a half-pixel overlap and no divider, so the days read as a band and not a comb; Warning carries a faint **horizontal** weave so state is never colour alone — the texture runs across the columns, because a vertical one at that pitch beats into visual static; stopped or missing data is a recessive slate hatch) → the **period strip** (KPI-derived periods, orange for high severity) → the **date scale** (1st, 8th, 15th, 22nd: a tick at the mark with its label beside it, never a full-height rule, which would cut the object into cells) → the **selected marker**, an Emerald line running the depth of the ribbon and strip and no further.
   - **Footer strip:** the period keys, the evidence labels, and how to read a column ("One column per day · Warning on top").
3. **Controls** after a hairline, outside the well but inside the deck: Play, 1×/4×, step back/forward, go-to, jump chips.

The range input is an invisible overlay on the track panel (keyboard and pointer), with `aria-valuetext` of the full stamp. The track is memoised; only the marker moves. Nothing flashes or pulses. The state bar is a presentation aggregate (counts of the recorded zone per row, per day); it adds no score and has no "dominant state" rule, which would hide short Warning excursions. The deck names the operating state from the gap kind: "Kiln stopped" only where the data says stopped, "Data not recorded" for missing data. The slider's `aria-valuetext` is "time: state, index".

## Motion

`theme.ts → motion`: fast 120, normal 180, slow 240 ms. Page change: fade + 6 px rise. Drawer: 24 px slide. Hover/press 120 ms. Count-up once, 300 ms, Executive Summary KPIs only. `prefers-reduced-motion` sets all animation and transition to 0.01 ms; charts turn animation off. No looping or ambient animation anywhere.

## Focus and interaction

- Light surfaces: 2 px Brunswick ring, 2 px offset. Dark surfaces (`.on-dark`): Emerald ring with a Deep Forest halo. Filled Brunswick buttons: white ring.
- Shortcuts: Shift+P toggles presentation mode; ← → page through in pitch order; Esc exits.

## Print

The dark bands print with their colour. `aside`, `header` and `.no-print` are hidden, so **content must not be an `<aside>`** (the core finding is a `<section>` for this reason).

## Documented one-offs

- Executive Summary micro charts (ticks, bars, severity strip) are inline and `aria-hidden`; their text carries the meaning, and they use only fields already in `summary.json`.
- The Console track is a custom layered panel over an opacity-0 range input.
- Roadmap stage 1 uses an inset top rule (`shadow-[inset_0_3px_0_theme(colors.normal.DEFAULT)]`) so card heights stay aligned.
