# Design system: Kiln Intelligence × Astrikos AI × Dalmia

**Direction:** Astrikos AI's industrial intelligence layer, expressed through a Dalmia Cement visual environment.
Precision, depth, trust. Not a SaaS template, not a cyberpunk panel.

The hierarchy on every page is **brand → product → context → insight → evidence → detail**:
the lockup and product line (top bar), the page band (title and question), the one insight statement,
then white analytical surfaces, then detail.

## Where the tokens live

| File | Holds |
|---|---|
| `src/theme.ts` | The only source of colour, gradient, elevation, motion and font: `brand`, `dalmia`, `background`, `gradient`, `status`, `systemColor`, `severityColor`, `issueColor`, `elevation`, `motion`, `font`, `chart`, `echartsTheme`. Plain TS. |
| `tailwind.config.ts` | Maps theme.ts to Tailwind names (`night`, `midnight`, `steel`, `slate`, `haze`, `mist`, `sky`, `dalmia-*`, `navy-*`, `ink-*`, `page`…), the type scale, shadows, `bg-hero` / `bg-sidebar` / `bg-accent` gradients and the motion durations. |
| `src/index.css` | Surface classes (`.card`, `.surface-dark`, `.atmosphere`, `.surface-glass`, `.hatch`), type roles (`.eyebrow`, `.eyebrow-dark`), buttons, chips, focus rings, motion keyframes, reduced motion, print. Reads tokens through `theme()`. |
| `src/charts/tooltip.ts` | The one tooltip layout. Escapes every string, including swatch colours. |
| `src/copy.ts` | Every user-facing string. `tests/wording.test.ts` scans it. |

**Rule:** no hex or `rgb(a)`/`hsl` literal anywhere in `src/` except `theme.ts`. `tests/tokens.test.ts` enforces it.
The logo SVGs in `src/assets/brand/` keep their own artwork colours.

## Brand: the co-brand lockup

`components/Brand.tsx`. One capsule with two equal panels: the **Astrikos** artwork on `night`, the **Dalmia Bharat** artwork on white.
Both logos are the supplied artwork, unrecoloured. They are placed on grounds they were designed for
(Astrikos is light grey, built for dark; Dalmia is dark blue plus colour, built for white), so the two read as one unit, with a small `×` chip on the seam.

- `src/assets/brand/astrikos.svg` is byte-identical to the supplied file.
- `src/assets/brand/dalmia.svg` differs from the supplied file **only in its `viewBox`**, cropped from the 652×652 canvas to the artwork's measured bounds (`12 184 606 292`) so it sits tight in the panel. Every path is unchanged.
- Alt text: "Astrikos AI" and "Dalmia Bharat". The link name is "Kiln Intelligence: Astrikos AI × Dalmia Bharat, home".
- The lockup appears **once**, top-left of the top bar. The sidebar carries a text-only "Astrikos × Dalmia · Proof of concept"; the footer is text only.

| Viewport | Lockup | Product line (Kiln Intelligence · Ariyalur) |
|---|---|---|
| ≥ 1280 | 44 px | beside it |
| 1024–1279 | 40 px | beside it |
| 768–1023 | 36 px | hidden |
| < 768 | 32 px | hidden |

The top-bar status reads **"Ariyalur / Historical · Jun–Aug 2025"** with a history icon. There is no live-status dot.

## Colour (70 / 20 / 10)

| Share | Tokens | Use |
|---|---|---|
| 70% navy · white · cool grey | `night` #091226, `midnight` #0f1d3b, `steel` #2e4265, `page` (canvas) #eef1f6, white, `line` | Top bar, sidebar, hero bands, canvas, cards |
| 20% blue · indigo · slate | `navy` #2a469c, `indigo` #4863b8, `sky` #79aef0, `slate` #8599ab, `haze` #8fa3bc, `mist` #a8b5c2 | Actions, active rules, data blue, text on dark |
| 10% Dalmia accents | `dalmia.orange` #f39500, `.green` #00923f, `.blue` #0054a6, `.grey` #959c98 | Annotations and emphasis only |

`steel`, `slate`, `mist`, `fog`, `haze` are the supplied reference palette (2E4265, 8599AB, A8B5C2, D5D5D6, 8FA3BC).

- **Dalmia orange** marks: period-start annotations on charts, high-severity ticks and markers on the timeline and Console scrubber, one insight accent bar. Never a Health Index state, never body text on white. Where it labels something it is paired with the word ("High severity").
- **Status colours** (`status.N/W/A/C`) remain reserved for Health Index states and always ship with the word.
- **Magnitude** (period severity, data-issue severity) uses the navy → slate ramp, never alarm colours. Missing data is dark navy, not orange.

## Backgrounds and surfaces

| Surface | Class | Look |
|---|---|---|
| Canvas | `body` | `page` with a faint cool lift at the top (`gradient.canvas`) |
| Surface | `.card` | White, 1 px `line` border, 1 px shadow |
| Open | (no box) | A 2 px top rule or a blue accent bar; `InsightCard`, `Lead` |
| Elevated | Drawer, tooltip | White drawer with a 3 px navy top rule; tooltip is `midnight` |
| Dark | `.surface-dark` | `midnight → night` gradient, `steel` border (Console deck, Periods timeline, value total) |
| Atmosphere | `.atmosphere` | The hero: `night → midnight`, one cool sky light top-right, a fine 44 px grid that fades out, and `ProcessLines` |
| Glass | `.surface-glass` | 5% white on dark, only inside a hero (core finding, ask items) |

`ProcessLines` (Brand.tsx) is the industrial motif: concentric arcs like a kiln shell in section, flow lines and node ticks. It is `aria-hidden`, at 25% opacity, behind the text, and never under body copy. There are no photographs.

## Type (2 families)

- **Inter** for UI, headings and numbers (tabular figures with `.num`).
- **JetBrains Mono** (latin 400/500 only) for eyebrows and technical metadata: caps, wide tracking.

| Class | Size / line | Role |
|---|---|---|
| `text-hero` | 46/50 | Executive Summary display statement |
| `text-numeral` | 56/56 | The core-finding numbers |
| `text-display` | 34/40 | Hero statement on narrow screens, verdict |
| `text-title` | 28/34 | Page H1, drawer title |
| `text-lead` | 22/30 | Lead statement |
| `text-section` | 18/25 | Section and chart-card titles |
| `text-kpi` | 38/42 | KPI numbers |
| `text-card` / `text-body` / `text-label` / `text-caption` | 16 / 15 / 13 / 12 | Card title, body, labels, metadata |
| `.eyebrow` / `.eyebrow-dark` (`text-eyebrow`) | 11/16, mono, caps, 0.14em | Kicker, KPI label, group heading |

## Page structure

`Page` (ui.tsx) = dark `atmosphere` band (eyebrow, H1, question, evidence badges) + content container. `PageBand` is the band alone (the Console memoises it). The Executive Summary and Validation have bespoke bands.

## Card levels

| Level | Components | Look |
|---|---|---|
| 1 Hero insight | Page band, Executive Summary hero + core finding, Validation verdict, closing ask (`HeroBand`), `Lead` | Dark atmosphere, or a statement against a blue rule |
| 2 Primary evidence | `.card`, `ChartCard`, `KpiTile` | White, bordered; KPI tiles have a left accent, mono label, optional micro chart, evidence line |
| 3 Supporting | `InsightCard` (open), `.panel`, `.inset`, `.card-dashed`, `Source`, `Badge` | No shadow; dashed = illustrative or not yet operational |

## Charts

All colour from `theme.ts → chart`: navy-slate axes (`#51607a`), muted grid (`#e9edf3`), **one blue primary** (`#2c5bc4`), slate comparison (`#6d819c`, dashed), Dalmia orange for period-start annotations only. Process systems keep their fixed categorical order.

- Tooltip: `midnight` shell, white title, mist rows, a short sky rule under the title, an evidence note. HTML is escaped.
- Gaps (`null`) stay gaps: shaded and labelled on charts; hatched and labelled "No data / Kiln stopped" in the Console. Never interpolated.
- Every `ChartCard` has "View data", the accessible table.

## Console

A dark deck (`.surface-dark`, sticky on large screens): the large historical stamp ("15 JUL 2025 · 21:00"), the Kiln Health Index with its state word, jump chips, play / speed / step / go-to, and the replay timeline. Beneath it, light analytical cards. On the timeline, stopped / no-data spans are hatched, high-severity periods are orange ticks, other periods sky ticks, the thumb is white with a faint glow.

## Motion

`theme.ts → motion`: fast 120, normal 180, slow 240 ms, ease `cubic-bezier(.2,.8,.2,1)`.

- Page change: fade + 6 px rise, 180 ms (`.anim-page` on `<main>`).
- Drawer: 24 px slide, 240 ms. Table toggle: 180 ms fade. Hover and press: 120 ms.
- Count-up: once, 300 ms, Executive Summary KPIs only.
- `prefers-reduced-motion` sets all animation and transition to 0.01 ms; charts turn animation off.

## Focus and interaction

- Light surfaces: 2 px navy ring, 2 px offset. Dark surfaces (`.on-dark`): sky ring with a `night` halo. Filled navy buttons: white ring.
- Buttons press down 1 px on `:active`.
- Shortcuts: Shift+P toggles presentation mode; ← → page through in presentation mode; Esc exits.

## Print

The dark bands print white with navy headings. `aside`, `header` and `.no-print` are hidden, so **content must not be an `<aside>`** (the core finding is a `<section>` for this reason).

## Documented one-offs

- Executive Summary micro charts (ticks, bars, severity strip) are inline and `aria-hidden`; their text carries the meaning, and they use only fields already in `summary.json`.
- The Console scrubber is a custom track over an opacity-0 range input. The track is memoised and only the thumb moves.
- Roadmap stage 1 uses an inset top rule (`shadow-[inset_0_3px_0_theme(colors.normal.DEFAULT)]`) so card heights stay aligned.
