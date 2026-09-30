# Remediation Prompt: Clean-Slate Kiln Intelligence Dashboard (pitch build)

**Framework: CO-STAR + Steps + Gates.** CO-STAR (Context · Objective · Style · Tone · Audience · Response) is used because the old dashboard failed on *audience and tone*, not on code. It was an analyst's validation report shown to buyers, and CO-STAR forces those decisions up front. It is extended with **S**teps (a time-boxed agentic build order with the skill or agent for each step) and **G**ates (checkable "done"), because this is a multi-hour autonomous build.

**Pitch:** Dalmia Cement, **2026-10-01**. **Build window:** tonight.

Paste everything below the line into a fresh Claude Code session opened in `/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC`.

---

## C: CONTEXT

### The client problem (source: `/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia Problem Statement.pdf`; read it)
- **Plant:** Dalmia Cement Ariyalur (Dalmiapuram). It is increasing alternative fuel (RDF, plastic-derived) co-processing, and fuel variability drives coating, deposit and ring build-up. That leads to efficiency loss, instability and **unplanned kiln stoppages**.
- **Their desired journey:** **Reactive detection → Early detection → Prediction → Planned intervention.**
- **Their desired output:** a Kiln Efficiency / Deposit Risk Score with the states **Normal → Watch → Warning → Critical**. It shows the current condition, emerging trends, contributing parameters, risk of further deterioration and the intervention window.
- **Their decisions:** operational optimisation / planned cleaning or ring removal / planned shutdown.
- **The seven first-phase objectives:**
  1. normal baseline;
  2. deterioration KPI;
  3. leading indicators;
  4. AF vs kiln behaviour;
  5. historical abnormal periods;
  6. preliminary risk score;
  7. demonstrate potential for early warning.
- **The vendor is Astrikos AI.** The use case title is "AI-Powered Early Warning & Predictive Intelligence for Cement Kiln Efficiency and Deposit Build-Up".

### What exists in the repo
- Phases 1–9 are complete, frozen analytics (Python). Outputs are in `phase-0N-*/outputs/`, and a summary is in `reports/BUILD_STATUS.md` §3, §7–§13. **Read those sections before designing anything.**
- `phase-10-dashboard/` is the old technical dashboard (plain JS on a Phase 9 API proxy). **It is being replaced, not reused.** Do not import, copy or adapt its code, CSS, copy or page structure. You may read its `public/css/app.css` header only for the brand tokens sampled from dalmiacement.com, and `screenshots/after/overview.png` to see what *not* to do.
- `dashboard/` is an empty placeholder (`README.md`, `.gitkeep`). **The new app lives here.**
- Toolchain: Node 22, npm 10, Python venv at `.venv/` (pandas + pyarrow available there, not in system Python).
- GitHub remote: `murphy20-in/Dalmia-Kiln-POC`. The old read-only copy was served on GitHub Pages.

### The verified facts the dashboard sells (use these numbers; each traces to a source)

| Capability | Evidence (plain English) | Source |
|---|---|---|
| Ingests messy plant SCADA at scale | 10 datasets, **2.58 M rows** (2,575,476), **203 process tags**, 1-minute data, Apr–Sep 2025 | BUILD_STATUS §3 |
| Automatic data-health audit | **32 issues** caught before modelling (1 critical, 4 high, 16 medium, 8 low, 3 info). Examples: a truncated Sept workbook, an April file that duplicates May, a 10-h frozen window across 122 tags, `99999` sentinels, 4,135 duplicate timestamps | §3 |
| Learns the kiln's "normal" | Baseline for 203 tags (68 high-confidence); 3 feed regimes (~294 / 375 / 422 TPH); running vs stopped detected automatically (202,558 running minutes) | §7 |
| One efficiency health number | Kiln Efficiency Deterioration Index (0–100) from 33 tags across 5 systems. Monthly median **13.1 (Jun) → 23.6 (Aug)**. Show the two values; **never** "+80%", because June is partly fit optimism | §8 |
| Detects drift | Share of running time in the high-deviation zone: **25.1% Jun → 41.6% Jul → 53.0% Aug**. August > June is statistically separable. Caveat: excluding the kiln-inlet O₂ analyser roughly halves the rise, so the plant must confirm the analyser | §12, `phase-07-risk-score/outputs/risk_score_summary.csv` |
| Finds abnormal periods automatically | **12** abnormal operating periods Jun–Aug (3 high / 4 moderate / 5 low severity). **11 of 12 multi-system** (thermal + combustion + draft most common). Each is robust in ≥ 81% of variants | §11, `phase-06-abnormal-events/outputs/` |
| Explains drivers | For each 10-min interval: the contribution of 5 systems (efficiency, combustion, thermal, draft/pressure, stability) plus ranked reasons | `phase-07-risk-score/outputs/risk_score_components.parquet` (`timestamp, family, family_contribution, …`), `risk_score_reasons.parquet` (`timestamp, reason_code, driver_rank, contribution_points`), `risk_scores.parquet` (`timestamp, risk_score, risk_band, operational, kpi_value, feed_tph, primary_reason, contributing_families, …`) |
| Alternative-fuel intelligence | AFR tracks feed (ρ ≈ +0.35 to +0.50). **PC coal rises a median +6 TPH within 1 h of AFR stops** (coal-for-AFR swap). Higher AFR → lower preheater O₂ and NOx. Preheater/TAD/hood temps dip after AFR stops. **27 of 43** associations were confirmed on held-out August data | §10, `phase-05-af-analysis/outputs/afr_*.csv` |
| Engineering rigour | Every stage is leakage-tested, reproducible (byte-identical reruns) and independently reviewed; hundreds of automated checks pass | §7–§13 |

### What is NOT true (overclaiming kills the pitch)
- **No prediction yet.** Phase 8: the score did **not** reliably rise *before* the abnormal periods (primary endpoint NOT_SUPPORTED). The root cause is that there are **zero plant event logs** (coating, ring, cleaning, stoppage) to learn from.
- **Nothing is deposit-validated.** The 12 periods are process-derived, not confirmed plant events.
- **No fuel-quality data** (CV, moisture, RDF/plastic split), so no fuel-quality → deposit conclusions are possible.
- Band edges are empirical: Apr–May P75 = **21.1** and P90 = **38.2** on the 0–100 index.

**Sales position:** "Early detection is delivered on your data. Prediction is the next stage, and it needs your event logs." Every gap becomes a roadmap item and a data ask.

---

## O: OBJECTIVE

Build, from zero, a **multi-page, presentation-grade product demo** in `dashboard/` that gets Dalmia leadership to fund **Stage 2** (event-log calibration → early warning). It must:
1. show **capability** (what Astrikos built on their data);
2. show **findings** (what their kiln data revealed);
3. show the **product vision** (what operators will use), as an interactive historical replay;
4. make a clear **ask** (the data and pilot commitment needed).

It must be **static** (no backend), deployable to GitHub Pages, fast, and flawless on a projector at 1280×720. When done, remove `phase-10-dashboard/` from the new branch (it remains in git history on `phase-10-dashboard`).

---

## S: STYLE

- **Visual:** a modern industrial SaaS product (think Siemens Insights Hub or AVEVA PI Vision, cleaner), co-branded with Dalmia.
  - Brand tokens: navy `#2a469c`, navy-deep `#233d8e`, cyan accent `#00a8ce`, charcoal text `#414142`, page `#f5f6f8`, card white.
  - Font: Inter (self-hosted via `@fontsource/inter`), tabular numerals for all numbers.
  - Text wordmark only: **"DALMIA CEMENT × Astrikos AI"**. Never use the Dalmia logo image.
- **Status palette** (Health Index states only, always paired with the word):
  - Normal = `#1f8a70`
  - Watch = `#d99a00`
  - Warning = `#c4511a`
  - Critical = `#8a8f98` + lock icon ("activates after calibration")
  - Validate with the `dataviz` skill's palette validator: text ≥ 4.5:1, marks ≥ 3:1.
- **Layout:**
  - 12-column grid, max-width 1280px, 8px spacing scale, cards with 12px radius, soft shadow, 24px padding.
  - One idea per section, generous whitespace.
  - Left sidebar nav (collapsible) + top bar with the chip "Ariyalur Kiln · Historical data Jun–Aug 2025".
- **Charts:**
  - Every chart title **states the takeaway** ("Time in Warning doubled from June to August"), not the metric name.
  - Direct labels over legends, units on axes, hover tooltips, and a "View data" toggle showing a table.
  - Gaps (kiln stopped / no data) are drawn as gaps, never interpolated.
- **Motion:** 300 ms count-up on hero numbers and gauge needle easing; everything is off under `prefers-reduced-motion`.
- **Presentation mode:** key `P` or `?present=1` hides the nav, scales type 1.15×, and makes ←/→ go to the previous/next page in pitch order.

## T: TONE

Confident, plain, outcome-first, never hype. Speak in plant language (uptime, fuel, tonnes, planned vs unplanned), not statistics.

| Never on screen | Use instead |
|---|---|
| POC, Phase N, version strings, API | "Stage 1 · delivered on your data" |
| Risk score, reference-relative, P90 | **Kiln Health Index** (0 = your Apr–May normal) |
| KPI-derived empirical abnormal period | **Abnormal operating period** ("found automatically from process data") |
| NOT_SUPPORTED, WEAK, INSUFFICIENT_DATA, enums | "Next stage: needs event logs" |
| `Kiln-I!X`, tag IDs, finding IDs | "Kiln-inlet O₂ analyser", "Combustion system" |
| predicts, forecasts, lead time, AUC, accuracy %, detects deposits/rings/coating, prevents shutdowns, real-time/live (outside the Roadmap's future stages) | describe what *was* found; put future capability on the Roadmap, labelled as a future stage |

Honesty is shown as **rigour and a clear ask**, never as a wall of caveats. There is one dedicated page ("How we validated") for the full truth.

## A: AUDIENCE

1. **Primary:** plant head / unit head. They have 60 seconds and want to know "Is this worth funding?"
2. **Secondary:** process and energy heads. They will probe "Does it predict? Are these real events?", so answers must survive them.
3. **Tertiary:** the digital/IT team. They will ask "Can this run on our data and infra?"
4. **Presenter:** the user, a data scientist, screen-sharing live. Their design sense is limited, so the app must look finished without any tuning.

---

## R: RESPONSE (what to build)

### R-1. Stack (decided; do not reopen)
- **Vite + React 18 + TypeScript**, **Tailwind CSS**, **Apache ECharts** via `echarts-for-react` (gauge, heatmap, Gantt/custom, stacked bars, lines with brush), **react-router `HashRouter`** (works on GitHub Pages with no 404 trick), `lucide-react` icons, `@fontsource/inter`.
- No UI kit beyond these. No state library: use React state plus URL params.
- **Tests:** `vitest` for pure logic and data contracts, and Playwright (via MCP) for visual journeys.
- **Data:** static JSON in `dashboard/public/data/`, produced by one Python export script. The browser **never computes statistics**; it formats, filters and draws.

### R-2. Folder layout
```
dashboard/
  package.json  vite.config.ts  tailwind.config.ts  tsconfig.json  index.html
  scripts/export_data.py          # reads frozen phase outputs → public/data/*.json
  public/data/*.json              # generated, committed
  src/
    main.tsx  App.tsx  routes.tsx
    theme.ts                      # tokens, status palette, ECharts theme object
    copy.ts                       # ALL user-facing text (one place to review)
    data.ts                       # typed loaders + types for each JSON
    lib/value.ts                  # pure ROI model
    lib/format.ts                 # number/date formatting
    components/                   # Shell, Sidebar, TopBar, HeroBand, KpiTile, Stepper,
                                  # InsightCard, StatusGauge, StatusPill, ChartCard,
                                  # Drawer, CtaBand, Ribbon, PresentMode
    charts/                       # one file per chart type, each takes typed data
    pages/                        # one file per page below
  tests/                          # vitest: data contract, wording scan, value model
```

### R-3. Data export (`dashboard/scripts/export_data.py`, run with `.venv/bin/python`)
It reads frozen outputs **read-only** and writes the files below. Every file has a `_sources` map (`field → repo path`) so any number can be traced live in Q&A. Output must be deterministic (two runs byte-identical).

| File | Contents |
|---|---|
| `summary.json` | rows, tags, datasets, issue counts by severity, period counts by severity, multi-system count, KPI monthly medians, monthly zone shares, band edges 21.1 / 38.2 |
| `console.json` | per operational 10-min bucket (from `risk_scores.parquet` with `operational == True`): `t`, `s` (score, 1 dp), `z` (zone N/W/A), `k` (kpi_value), `f` (5 family contributions from `risk_score_components.parquet`), `r` (top-3 reason codes from `risk_score_reasons.parquet`). Target < 2.5 MB; if larger, split by month and lazy-load |
| `efficiency.json` | daily median index (primary + O₂-excluded variant, from Phase 7 outputs), monthly zone shares, monthly `share_points_*` by system (`risk_score_summary.csv`) |
| `periods.json` | 12 final periods (`phase-06-abnormal-events/outputs`, `in_final_set`): id, start, end, onset, duration, severity, dominant system, systems involved, load context, plus a ±24 h index mini-series |
| `afr.json` | `afr_monthly_summary.csv` (mean AFR, median feed by month), relationship cards from `afr_*_relationships.csv` (map `evidence`/`confidence` → Strong / Moderate / Emerging, with an August-confirmed flag), the AFR-stop coal step (+6 TPH within 1 h). An event-aligned average (−60 to +120 min) of PC coal / preheater O₂ / preheater temp around AFR stops is a P1 addition |
| `data.json` | dataset × month coverage matrix, issue register grouped by severity with 5 plain-English examples, prioritised data asks (from `phase-0N/outputs/*data_requirements*` and BUILD_STATUS §4) |
| `validation.json` | the honest-truth facts for the "How we validated" page: Phase 8 verdict in plain English, censoring explanation, O₂ sensitivity, negative controls summary, revalidation rule (≥ 8 labelled events) |

Reason-code → plain-English mapping lives in `src/copy.ts`, not in the JSON.

### R-4. Pages (pitch order = nav order)

**1. Executive Summary (`/`)**: "Is this worth funding?" in 60 s.
- **Hero band** (navy, full width): "Kiln efficiency and deposit-risk intelligence for Ariyalur". Sub-line: "Built on 2.58 million rows of your own SCADA data." CTAs: **"Open the Kiln Health Console"** (primary), "What we need from you" (secondary).
- **Journey stepper** (the pitch in one graphic): Reactive → **Early detection ✓ Delivered on your data** → Prediction (next: needs event logs) → Planned intervention (Stage 3).
- **4 KPI tiles:**
  - 2.58 M rows analysed · 203 tags
  - 12 abnormal periods found automatically
  - Efficiency Index 13.1 → 23.6, Jun → Aug
  - 32 data issues caught before modelling
- **3 finding cards**, each with a mini chart and a link: drift (25 → 42 → 53%), multi-system periods (11 of 12), AFR coal swap (+6 TPH within 1 h).
- **7-objective scorecard:** Delivered ×5 (baseline, KPI, AF analysis, abnormal periods, risk score), "Early signals found" (leading indicators), "Next stage: needs event logs" (early warning).
- **CTA band** → Roadmap.

**2. Kiln Health Console (`/console?t=`)**: the product preview and demo centrepiece. Persistent ribbon: **"Replay of historical data · {timestamp}. Live mode arrives with SCADA integration."**
- **Row 1:**
  - **Status gauge** 0–100 with zones Normal < 21.1 ≤ Watch < 38.2 ≤ Warning, and a greyed, locked **Critical** arc labelled "activates after calibration with your event logs";
  - **Status card** (big word, time in state, 3-h trend arrow);
  - **Efficiency Index tile** + 24-h sparkline.
- **Row 2:**
  - **"What's driving it"**: horizontal bars of the 5 system contributions, sorted;
  - **Top 3 reasons** in plain English.
- **Row 3:**
  - **24-h Health Index trend** with soft zone bands and shaded abnormal periods;
  - **Decision-support panel**: 3 cards (Optimise operation · Planned cleaning / ring removal · Planned shutdown for inspection) with "when this applies", labelled **"Stage 3 · illustrative"** and never tied to the replayed data point.
- **Replay controls:** datetime input bounded to the data; "Jump to" chips for the 3 high-severity periods; Play/Pause (10-min step per 300 ms, speed 1×/4×); a full-range scrubber mini-strip.
- Opens by default at the onset of the highest-severity period. Gaps show **"Kiln stopped / no data"** in grey. `t` lives in the URL.

**3. Efficiency Story (`/efficiency`)**: "Is my kiln getting less efficient?"
- **Hero stat:** "Time in Warning: 25% in June → 53% in August."
- **Charts:**
  - 100%-stacked monthly columns (Normal/Watch/Warning);
  - daily Health Index line with zone bands, period markers and a brush, plus a toggle "Sensitivity check: O₂ analyser excluded";
  - which systems drive the drift, by month (stacked bars).
- **3 insight cards.** One says: "Part of the August rise traces to the kiln-inlet O₂ analyser. Its calibration schedule will tell us how much is process vs instrument." Frame it as "a question only your team can answer".

**4. Abnormal Periods (`/periods`, `/periods/:id`)**: "What went wrong, when, which systems?"
- **Tiles:** 12 periods · 3 high · 11 multi-system · longest duration.
- **Timeline (Gantt)** Jun–Aug, severity on a navy ramp with text labels.
- **Heatmap**: periods × 5 systems.
- **Detail drawer:** times, duration, severity, dominant system, systems involved, load context in plain English, ±24 h mini chart, and a **"Replay in Console"** deep link.
- **Subtitle once:** "Found automatically from process data; next step is matching them to your plant logs."

**5. Alternative Fuel (`/alternative-fuel`)**: "How is co-processing affecting my kiln?"
- **Hero:** "When alternative fuel stops, PC coal steps in within the hour."
- **Domino graphic:** AFR stops → PC coal +6 TPH within 1 h → preheater/TAD/hood temps dip.
- **Monthly panels:** AFR TPH and feed TPH, small multiples, no dual axis.
- **Relationship cards** with strength pills and an "Confirmed on August hold-out" badge.
- **"To go deeper"** panel: CV, moisture, RDF/plastic split, fuel mix → "unlocks fuel-quality → deposit-risk modelling".

**6. Data Readiness (`/data`)**: "Can we trust this, and what do you need?"
- **Coverage heatmap** (datasets × Apr–Sep; shade + icon).
- **Issues caught** (severity bars + 5 example cards).
- **Rigour strip:** Leakage-tested · Reproducible · Independently reviewed · Versioned.
- **Data asks**, each with a "Copy request" button.

**7. Roadmap & Value (`/roadmap`)**: "What do we get, and what does it take?"
- **Stage timeline:**
  - **Stage 1 ✓** (data audit, baseline, efficiency index, abnormal-period finder, AF analysis, historical console);
  - **Stage 2, 8–12 weeks** (event-log labelling, early-warning calibration, Critical state, validation with your engineers);
  - **Stage 3** (live SCADA/historian integration, operator console, alerts, shift reports);
  - **Stage 4** (intervention recommendations, fuel-mix optimisation).
  - Each stage has "You get" / "We need from you".
- **Value calculator:** inputs pre-filled with round **placeholder** values marked "placeholder" in the hint. The inputs are:
  - clinker TPD, contribution ₹/t;
  - unplanned stoppage h/yr, % deposit/ring-related, % convertible to planned;
  - heat consumption kcal/kg, fuel ₹/Mkcal, efficiency gain %.
  - Outputs: avoided production loss ₹/yr, fuel saving ₹/yr, total.
  - Permanent label: **"Illustrative: your inputs, not a measured result."** The logic is the pure `lib/value.ts`, with a unit test.
- **Final ask band:** Stage 2 pilot needs (1) coating/ring/cleaning/stoppage logs Apr–Sep 2025, (2) O₂ analyser calibration schedule, (3) fuel-quality logs, (4) a process-engineering point of contact. Add a "Download summary (PDF)" button via `window.print()` + print CSS.

**8. How We Validated (`/validation`)**: last in nav, muted. The honest page for the engineer who asks.
- Plain-English method (baseline → index → periods → score → test).
- The Phase 8 result stated straight: "On Jun–Aug data, the index did not reliably rise before the abnormal periods." Then why (half of onsets censored, no event labels, O₂ analyser dependence) and what fixes it (≥ 8 labelled events → re-run the frozen test).
- Negative controls and reproducibility as trust signals.
- No enums or IDs. A small "Technical reference" footer lists model versions and repo paths.

### R-5. Also write
- `reports/PITCH_DEMO_SCRIPT.md`: a 10-minute click-by-click script.
  - Exec Summary 2 min → Console 3 min (open on the severe period, press Play, narrate the gauge and drivers) → Efficiency 1.5 → Periods 1 → Alt Fuel 1 → Roadmap & Value 1.5 (type their numbers live) → the ask.
  - **Objection handling:**
    - "Does it predict?" → "Not yet. We had no event logs to learn from; that's Stage 2."
    - "Are these real deposits?" → "Abnormal operating periods from process data; matching to your logs is Stage 2 task one."
    - "Why is August so high?" → "Partly drift, partly the O₂ analyser; its calibration schedule separates the two."
    - "Can it run on our infra?" → "Static export today; Stage 3 connects to your historian."
- `dashboard/README.md`: how to regenerate the data, run the app, build and deploy.

---

## STEPS (build order, with skills and agents)

**P0: must be done before the pitch**
1. **Branch + plan.** Create branch `pitch-dashboard` from `phase-10-dashboard`. Load the skills `planning-and-task-breakdown` and `ponytail:ponytail` (lite: minimal code, but new deps in R-1 are approved). Agent **`ecc:planner`** writes `dashboard/PLAN.md` (≤ 1 page: pages, components, data files, P0/P1).
2. **Data export.** Skill `python-patterns`. Write `export_data.py` and generate the JSONs. Add the vitest `tests/data.test.ts`, which asserts: 9,557 operational buckets, 12 periods (3/4/5), monthly zone shares ≈ 0.251 / 0.416 / 0.530, 32 issues, 203 tags, band edges 21.1 / 38.2, and that every file has `_sources`.
3. **Scaffold + design system.** Skills `frontend-design:frontend-design`, `dataviz`, `ui-design-system`, `vite-patterns`, `react-patterns`.
   - Vite app, Tailwind tokens, ECharts theme in `theme.ts`, the shell (sidebar, top bar, footer "Built by Astrikos AI for Dalmia Cement, Ariyalur"), all components in R-2, and present mode.
   - Take a Playwright screenshot of the empty shell and check it against the style section before building pages.
4. **Executive Summary.** Skills `dashboard-builder`, `copywriting`, `sales-engineer`.
5. **Kiln Health Console.** Skills `dataviz`, `react-performance` (the 9.5k-point replay must stay smooth; memoise per-timestamp lookups).
6. **Efficiency Story**, then **Abnormal Periods**.
7. **Roadmap & Value** (skill `financial-analyst` to sanity-check the value formula) and **How We Validated**.
8. **First evaluation loop.** Run `npm run dev`. Agent **`ecc:gan-evaluator`** drives the app with Playwright at 1280×720 and 1440×900 and scores each page 1–10 on: *clarity for a plant head, visual polish, story flow, honesty*. Fix and re-run until every P0 page scores ≥ 8.
9. **Review wave** (launch in parallel, in one message). Log every finding and its disposition in `dashboard/REVIEW_LOG.md`.
   - **`ecc:mle-reviewer`**: **claims audit**. Every number and sentence is checked against the Context facts table and BUILD_STATUS. Any overclaim is a blocker.
   - **`ecc:marketing-agent`**: buyer language, jargon leaks, headline strength.
   - **`ecc:react-reviewer`** + **`ecc:typescript-reviewer`**: hooks, render performance, types.
   - **`ecc:python-reviewer`**: `export_data.py`.
   - **`ecc:a11y-architect`**: WCAG 2.2 AA (gauge text alternative, chart tables, focus, contrast).
10. **Retire the old dashboard.** `git rm -r phase-10-dashboard` on this branch. Update `README.md` and `reports/BUILD_STATUS.md` (add §16 "Pitch dashboard") to point at `dashboard/`.
11. **Build + deploy.** `npm run build` (base `./`). Prepare a GitHub Actions Pages workflow (`.github/workflows/pages.yml`) that builds `dashboard/`. **Ask the user before pushing or enabling Pages**, because it is outward-facing.

**P1: if time allows**
12. Alternative Fuel page (domino first, event-aligned chart second).
13. Data Readiness page.
14. Print CSS + PDF summary, and a 375px mobile pass.
15. Skill `ponytail:ponytail-audit` → remove dead code; agent **`ecc:code-simplifier`** on `src/`.
16. Skills `verification-loop`, then `handoff`.

If a build error blocks progress, use agent **`ecc:react-build-resolver`**.

---

## TOOLING SUMMARY

**Skills:**
- `frontend-design:frontend-design`, `dataviz`, `ui-design-system`, `dashboard-builder`, `make-interfaces-feel-better`
- `react-patterns`, `react-performance`, `vite-patterns`, `python-patterns`
- `copywriting`, `content-humanizer`, `sales-engineer`, `marketing-strategy-pmm`, `financial-analyst`
- `browser-qa`, `full-page-screenshot`, `a11y-audit`
- `planning-and-task-breakdown`, `verification-loop`, `handoff`, `ponytail:ponytail`, `ponytail:ponytail-audit`

**Agents:** `ecc:planner`, `ecc:gan-evaluator`, `ecc:mle-reviewer`, `ecc:marketing-agent`, `ecc:react-reviewer`, `ecc:typescript-reviewer`, `ecc:python-reviewer`, `ecc:a11y-architect`, `ecc:react-build-resolver`, `ecc:code-simplifier`.

**Hooks** (add to the project `.claude/settings.json` via the `update-config` skill; show the JSON to the user and get approval first):
1. **PostToolUse** on `Edit|Write` matching `dashboard/src/**` runs `cd dashboard && npx vitest run tests/wording.test.ts`.
   - The test scans `src/**/*.{ts,tsx}` (including `copy.ts`) for: `\bPOC\b`, `Phase \d`, `p\d-(risk|abn)`, `NOT_SUPPORTED|INSUFFICIENT_DATA`, `predict`, `forecast`, `lead[- ]time`, `\bAUC\b`, `accuracy`, `detects? (deposit|ring|coating)`, `prevent(s)? shutdown`, `Kiln-I!`.
   - `real-time|live` is allowed only in `pages/Roadmap.tsx` and the Console ribbon string.
   - `pages/Validation.tsx` is exempt only from the `predict` rule.
   - A failure prints the file and line.
2. **Stop** runs `cd dashboard && npx vitest run && npx tsc --noEmit`, so the session cannot end red.
3. Keep the existing GateGuard hook.

**Plugins / MCP:**
- **Playwright MCP**: screenshots and journeys (driven by gan-evaluator).
- **Chrome DevTools MCP**: `lighthouse_audit` and a performance trace on the Console.
- **ecc plugin**: agents.
- **frontend-design plugin**.
- **ponytail plugin**.

---

## GATES (all must pass before reporting done)

- **G1 Clean slate:** no file under `dashboard/` imports, copies or adapts `phase-10-dashboard/` code. `phase-10-dashboard/` is removed on this branch. Phases 1–9 are untouched (`git diff phase-10-dashboard -- 'phase-0*'` is empty).
- **G2 Claims:** the wording test is green. The mle-reviewer claims audit has 0 open blockers. Every number on screen maps to a `_sources` entry.
- **G3 Story:** from the Executive Summary alone, a first-time viewer can say in under 60 s what was built, what was found, what's next and what's needed from Dalmia. gan-evaluator scores ≥ 8/10 on every P0 page.
- **G4 Console:** any Jun–Aug timestamp replays correctly. Gaps show "Kiln stopped / no data". Jump chips and Play work. `?t=` survives reload.
- **G5 Honesty preserved:** the How We Validated page states the Phase 8 result plainly. The value calculator's "illustrative" label is always visible. Critical is locked.
- **G6 Quality:**
  - no console errors or warnings;
  - Lighthouse Performance ≥ 90 and Accessibility ≥ 95;
  - no horizontal scroll at 1280×720;
  - Console interaction (scrub/play) stays at 60 fps with no jank visible in the trace.
- **G7 Build:** `npm run build` is clean, `tsc --noEmit` is clean, and `vitest` is green (data contract, wording, value model). `export_data.py` runs twice with byte-identical output.
- **G8 Artefacts:**
  - screenshots of every page at 1280×720 in `dashboard/screenshots/`;
  - `reports/PITCH_DEMO_SCRIPT.md`;
  - `dashboard/REVIEW_LOG.md` with nothing OPEN;
  - an updated `README.md` and `BUILD_STATUS.md`.

**Final message to the user:** local URL, how to start (`cd dashboard && npm run dev`), whether deploy is pending approval, the gate results (pass/fail with evidence), and the 3 riskiest demo moments with how to handle them.
