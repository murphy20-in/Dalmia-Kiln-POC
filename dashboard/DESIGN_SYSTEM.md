# Design system: Kiln Intelligence

**Direction:** industrial intelligence, engineering precision and Dalmia brand confidence.

The look is restrained:
- Navy carries structure.
- Cyan marks selection and the single accent rule.
- Status colours are used only for Health Index states.
- Every page spends its boldness in one place. On the Executive Summary that is the navy hero; on analytical pages it is the cyan-ruled lead statement.

## Where the tokens live

| File | Holds |
|---|---|
| `src/theme.ts` | The only source of colour: brand, status (N/W/A/C), system palette, severity and issue ramps, chart fills, and the ECharts theme. Plain TS; `tailwind.config.ts` imports it. |
| `tailwind.config.ts` | Maps theme.ts colours to Tailwind names, plus the type scale, radii, shadows and motion duration. |
| `src/index.css` | Type-role and component classes, focus ring, motion keyframes, reduced motion, print. |
| `src/charts/tooltip.ts` | The one tooltip layout (title, sub, rows, note). Escapes every string. |
| `src/copy.ts` | Every user-facing string. `tests/wording.test.ts` scans it. |

Rule: no hex or rgba literals outside `theme.ts`. One exception is the transparent stop in the gauge.

## Colour

| Token | Value | Use |
|---|---|---|
| `navy` | #2a469c | Primary actions, active icons, links |
| `navy-ink` | #1b2c63 | Headings, hero surface, KPI numbers |
| `navy-tint` | #eef1f8 | Active nav, panels, info callouts |
| `cyan` | #00a8ce | Active-nav rule, lead-statement rule, step numbers on dark |
| `ink` / `ink-body` / `ink-muted` | #2b2f36 / #414142 / #5f6368 | Text. Muted text is 6:1 on white. |
| `ink-faint` | #8a8f98 | Decorative icons only (3.2:1, never text) |
| `page` / `line` / `line-strong` | #f4f6f9 / #e3e6ec / #cfd5df | Canvas, hairlines, input borders |
| `normal` / `watch` / `warning` / `critical` | status palette | Health Index states only, always paired with the word |
| `systemColor.*` | 5 fixed hues + grey | Process systems, in a fixed order, never cycled |
| `severityColor`, `issueColor` | Navy ramps | Magnitude (period severity, data-issue severity), never alarm colours |

## Type scale (Inter, tabular figures for numbers)

| Class | Size / line | Role |
|---|---|---|
| `text-display` | 34/40 | Executive Summary H1 only |
| `text-title` | 26/32 | Page H1, drawer title, verdict |
| `text-lead` | 22/30 | Lead statement (Level 1 on analytical pages) |
| `text-section` / `.t-section` | 18/25 | Section and chart-card titles |
| `text-card` / `.t-card` | 16/22 | Card titles |
| `text-body` | 15/23 | Body copy, page question |
| `text-label` / `.t-label` | 13/18 | Labels, table text, most card body text |
| `text-caption` / `.t-caption` | 12/16 | Metadata, source lines, legends |
| `text-kpi` | 36/40 | KPI numbers |

Monospace (`font-mono`) is available for technical identifiers. Timestamps use Inter tabular figures (`.num`), which read better on a projector.

## Layout

- **Spacing:** 8 px-based Tailwind spacing.
- **Page width:** max-width 1280 px, padding 32 px (16 px on phones).
- **Section gap:** 24 px. The Console uses 20 px.
- **Card padding:** 24 px (20 px for compact cards).
- **Shell:** 240 px sidebar (64 px icon rail below 768 px, or when collapsed) and a 56 px top bar (`--header-h`).
- **Grids:** analytical rows use a 12-column grid. Typical splits are 5/7 (chart + chart) and 4/3/5 (Console score, state, drivers).

## Card hierarchy

| Level | Component | Look |
|---|---|---|
| 1 | `HeroBand` (one per page at most), `Lead` | Solid navy-ink with a 4 px cyan edge; or a 22 px statement with a 3 px cyan rule and no box |
| 2 | `.card`, `ChartCard`, `KpiTile` | White, 1 px line border, 10 px radius, 1 px shadow |
| 3 | `.panel`, `.inset`, `.card-dashed` | Tinted or bordered, no shadow; dashed = illustrative or future |
| 4 | `Source`, `.t-caption`, `Badge` | Metadata and evidence |

## Components (`src/components/ui.tsx` unless noted)

**Page structure**
- `PageHeader`: title, question, optional badges and actions.
- `Lead`, `HeroBand`, `SectionHeader`.

**Numbers and labels**
- `KpiTile`: label, then number (and unit), then context sentence, then evidence line.
- `Badge`: tones navy, tint, outline, dashed, caveat, positive. The word always carries the meaning.
- `PeriodEvidence`: the two mandatory labels, "KPI-derived abnormal period" and "Not a validated plant event".
- `StatusPill`: zone word plus icon plus status colour.

**Supporting pieces**
- `Callout`, `NumberDot` (sequences only), `Source`, `Legend`, `Stepper` (journey; states announced to screen readers), `Loading` (skeleton).

**Charts and containers**
- `ChartCard` (components/ChartCard.tsx): takeaway title, subtitle, actions, chart or data-table toggle, legend, source line.
- `Drawer` + `DrawerSection` (components/Drawer.tsx): modal side panel with inert background, Escape to close, and focus return.
- `Chart` (charts/Chart.tsx): memoised ECharts wrapper (SVG renderer, `useUTC`, reduced motion).
- Option builders in `charts/`: `zoneLine` (bands, shaded periods, labelled gap spans), `stackedColumns`, `hbars`, `monthBars`, `gantt`, `heatmap`.

## Charts

- Every chart sits in a card with a takeaway title. Every ChartCard offers "View data", the accessible table.
- Tooltips always go through `tip()`: a date or title first, then labelled rows with swatches, then an evidence note. Internal codes are never shown.
- Gaps (`null`) stay gaps. `zoneLine` shades them grey and labels wide ones "Kiln stopped / no data".
- Gridlines are value-axis only (#eef0f4), with no ticks. The crosshair is a dashed grey axis pointer.

## Motion

- Duration is 160 ms by default. The drawer slides 24 px in 200 ms, and the table toggle fades in 180 ms.
- Count-up runs once, 300 ms, on Executive Summary KPIs only.
- `prefers-reduced-motion` reduces all animation and transition to 0.01 ms, and the charts turn animation off.

## Focus and interaction

- Focus ring: 2 px navy outline with a 2 px offset. Inside navy surfaces the ring turns white with a navy halo.
- Buttons press down 1 px on `:active`.
- The selected period row is navy-tint with `aria-current`.
- Shortcuts: Shift+P toggles presentation mode; ← → page through in presentation mode; Esc exits.

## Documented one-offs

- Executive Summary mini-bars and the 12-square grid are inline (`aria-hidden`). Each card's text carries the meaning.
- The Console scrubber is a custom track over an opacity-0 range input. The track is memoised and only the thumb moves.
- The Roadmap stage cards use an inset top rule (`shadow-[inset_0_3px_0_theme(colors.*)]`) instead of a border, so card heights stay aligned.
