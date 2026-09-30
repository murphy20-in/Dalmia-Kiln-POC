# PLAN: Kiln Intelligence pitch dashboard

Static Vite + React 18 + TS app. It reads `public/data/*.json` and only formats, filters and draws; the browser computes no statistics. It uses HashRouter, and all user-facing text lives in `src/copy.ts`.

## Pages (pitch order = nav order)
| # | Route | Question | Main pieces | Tier |
|---|---|---|---|---|
| 1 | `/` Executive Summary | Is this worth funding? | HeroBand, Stepper, 4 KpiTiles, 3 finding cards, 7-objective scorecard, CtaBand | P0 |
| 2 | `/console?t=` Kiln Health Console | What will operators see? | Ribbon, StatusGauge (Critical locked), status card, index tile + sparkline, driver bars, top-3 reasons, 24-h trend, decision cards (Stage 3 · illustrative), replay controls | P0 |
| 3 | `/efficiency` | Is my kiln getting less efficient? | Hero stat, 100%-stacked months, daily line + brush + O₂ toggle, drivers by month, 3 insights | P0 |
| 4 | `/periods`, `/periods/:id` | What went wrong, when, which systems? | Tiles, Gantt, periods × systems heatmap, Drawer + ±24 h chart + "Replay in Console" | P0 |
| 5 | `/alternative-fuel` | How is co-processing affecting my kiln? | Domino, AFR/feed small multiples, relationship cards, "To go deeper" | P1 |
| 6 | `/data` | Can we trust this, and what do you need? | Coverage heatmap, issues, rigour strip, data asks + copy | P1 |
| 7 | `/roadmap` | What do we get, and what does it take? | Stage timeline, value calculator (`lib/value.ts`), final ask, print | P0 |
| 8 | `/validation` | Does it really work? | Plain-English method, the straight result, trust signals, tech reference | P0 |

## Components
Shell (sidebar, top bar, footer, present mode), ui blocks (HeroBand, KpiTile, InsightCard, CtaBand, Stepper, Ribbon, StatusPill), ChartCard (takeaway title + "View data" table), StatusGauge, Drawer. Charts are ECharts option builders in `charts/`, rendered through one `Chart` wrapper on `echarts/core`.

## Data file → page
summary → Exec Summary, Periods, Validation · console → Console · efficiency → Efficiency, Exec Summary · periods → Periods, Console jump chips · afr → Alt Fuel, Exec Summary · data → Data Readiness, Roadmap asks · validation → Validation.

## Risks
| Risk | Mitigation |
|---|---|
| Console replay jank (9.5k rows) | Index rows once (`Map` + sorted times, binary search); memoise the 24-h slice on `t`; `replaceState` for `?t=` |
| Wording overclaims | All text in `copy.ts`; `wording.test.ts` via edit hook; mle-reviewer claims audit is a blocker |
| 6 contribution entries (5 systems + breadth/persistence) | Show 5 systems; breadth/persistence as a muted extra bar |
| First load (Lighthouse ≥ 90) | `React.lazy` pages; `echarts/core` modular imports; console.json only on Console |
| Projector legibility | Status tokens validated; colour always with a word; 1280×720 screenshots |

## Tests
`data.test.ts` (contract), `wording.test.ts` (banned phrases), `value.test.ts` (ROI model); Playwright journeys for G4.
