# UI/UX audit: Kiln Intelligence dashboard

**Date:** 2026-10-01
**Branch:** `pitch-dashboard`
**Scope:** presentation only. No analytical output, data file, score, period definition or validation result was changed. The data files are byte-identical to the baseline, verified with sha256 (see REVIEW_LOG.md, UX pass).

**Method:**
- Screenshots of every page were taken at 1280×720 and 1440×900 before any change.
- Each page was scored on 14 criteria.
- The pages were refined, then re-scored on the final production build (`vite preview`).

**Score scale:** 0 unacceptable · 1 poor · 2 needs work · 3 acceptable · 4 strong · 5 presentation-ready.

## 1. What the "before" state got wrong (evidence from screenshots)

**Header stack**
- At 720 px tall, the content started about 190 px down. A 64 px top bar, 32 px of padding, a 36 px H1 and a question line came first.
- On Console, the first viewport showed only the title, a ribbon and the controls. The gauge started below the fold.

**Top bar**
- The cyan-dot chip ("Ariyalur Kiln · Historical data") read like a live indicator.
- The brand appeared twice, in the sidebar and in the top bar, but no historical-status treatment appeared anywhere.

**Sidebar**
- Eight flat links with no grouping.
- Active state was a solid navy block.
- "How we validated" was separated by a magic margin.

**Gradient hero bands with a decorative ring**
- These were on Summary, Efficiency and Alt Fuel, and on Roadmap as a copy.
- They are the template look the brief rules out.

**KPI tiles**
- Each was a number plus a label, with no evidence or source line.
- Units were baked into the value ("2.58 M").

**Validation**
- The primary conclusion sat below the fold, under a five-step method card.

**Abnormal periods**
- They were never labelled "KPI-derived" or "Not a validated plant event" in the UI.
- The tooltips used raw ECharts HTML strings.

**Console**
- The native date input rendered in US 12-hour format and was the only visible timestamp.
- Gaps showed only as breaks in the line.

**Roadmap**
- Four uneven cards.
- No distinction between what was demonstrated and what needs plant data.

**Data readiness**
- Missing data was drawn in alarm orange.
- The issue examples could not be expanded.

**Accessibility**
- The skip link was broken under HashRouter: it rewrote the route hash.
- Bare `P` was a global single-key shortcut (WCAG 2.1.4).

## 2. Scores: before → after

Page keys:

| Key | Page |
|---|---|
| ES | Executive Summary |
| CO | Console |
| EF | Efficiency |
| AP | Abnormal Periods |
| AF | Alternative Fuel |
| DR | Data Readiness |
| VA | Validation |
| RM | Roadmap |

| Criterion | ES | CO | EF | AP | AF | DR | VA | RM |
|---|---|---|---|---|---|---|---|---|
| 1 Visual hierarchy | 3→5 | 2→4 | 3→4 | 2→4 | 3→4 | 3→4 | 2→5 | 2→4 |
| 2 Typography | 3→5 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→5 | 3→4 |
| 3 Spacing | 3→4 | 2→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 2→4 |
| 4 Alignment | 3→4 | 3→4 | 3→4 | 2→4 | 3→4 | 3→4 | 3→4 | 2→4 |
| 5 Navigation | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 |
| 6 Information density | 2→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 |
| 7 Chart readability | 3→4 | 3→4 | 3→4 | 2→4 | 3→4 | 3→4 | – | – |
| 8 Interaction clarity | 3→4 | 3→5 | 3→4 | 3→5 | 3→4 | 2→4 | 3→4 | 3→4 |
| 9 Accessibility | 3→5 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→5 | 3→4 |
| 10 Responsive | 3→4 | 2→4 | 3→4 | 2→4 | 3→4 | 3→4 | 3→4 | 3→4 |
| 11 Consistency | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 | 3→5 |
| 12 Industrial credibility | 2→4 | 3→4 | 3→4 | 3→4 | 2→4 | 2→4 | 3→5 | 3→4 |
| 13 Dalmia brand alignment | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 | 3→4 |
| 14 Presentation quality | 3→5 | 3→4 | 3→4 | 2→4 | 3→4 | 3→4 | 2→5 | 3→4 |

Scores of 4 rather than 5 are deliberate. The remaining gaps are:
- **Console:** the native date picker still follows the browser locale (12-hour in en-US browsers). The large "Replaying" stamp is the primary readout.
- **Efficiency:** period markers #2/#3 and #6–#8 sit close together, and their labels overlap at 1280 px.
- **Data Readiness:** the severity card has empty space next to the taller coverage heatmap.
- **Brand:** Dalmia photography and the logo are not used. This is a proof of concept, not an official Dalmia system, so the brand is evoked through colour only.

## 3. Stakeholder read (10 s / 30 s / 2 min)

| Viewer | 10 seconds | 30 seconds | 2 minutes |
|---|---|---|---|
| Plant Head | Hero thesis: Warning 25% → 53%, 12 KPI-derived periods | 4 evidence KPIs, each with a source line | What Dalmia provides next (hero panel), journey stepper |
| Process Engineer | Console: replayed timestamp, state, contributing systems | Trend with explicit stopped/no-data spans, top reasons | Periods drawer: facts, what changed, system deviation, replay |
| Digital Transformation Lead | Top bar: "Historical analytical view", grouped nav | Data Readiness: coverage, issues by severity | Roadmap: demonstrated vs requires plant data |
| Dalmia management | "Not supported" verdict is first on Validation | Roadmap stages and Illustrative calculator | The Stage 2 ask (4 items) |
| Astrikos technical leadership | Design system, consistent chart cards with data tables | Validation statistics panel | REVIEW_LOG dispositions, Lighthouse and journey evidence |

## 4. Gate results

| Gate | Result | Evidence |
|---|---|---|
| G1 Analytical integrity | PASS | `public/data/*.json`, `scripts/export_data.py` and `src/lib/value.ts` match their pre-pass sha256; `tests/data.test.ts` passes |
| G2 No claims regression | PASS | `tests/wording.test.ts` passes; mle-reviewer: 0 blockers, 3 major fixed |
| G3 Visual system | PASS | One colour source (`theme.ts`, imported by Tailwind); hex literals remain only in `theme.ts` and the ECharts gauge's transparent stop |
| G4 Navigation | PASS | All 8 routes and `/periods/:id`; no dead buttons (journeys J1–J12) |
| G5 Console | PASS | J2, J3, J4 and J11; gaps shaded and labelled, never interpolated |
| G6 Responsive | PASS | No horizontal overflow at 375 / 768 / 1024 / 1280 / 1440 / 1920 on any page or the drawer (after fresh reload and after live resize) |
| G7 Accessibility | PASS | Lighthouse accessibility 100 on all 5 audited pages; a11y-architect serious findings fixed |
| G8 Performance | PASS | Lighthouse desktop performance 99–100, CLS 0, TBT ≤ 20 ms; Console 4× playback 59 fps, p95 frame 16.8 ms, 0 long tasks |
| G9 Browser | PASS | 12/12 Playwright journeys |
| G10 Security | PASS | No critical, high or medium findings; 2 low findings recorded |
| G11 Code quality | PASS | `npm run build`, `tsc --noEmit` and `vitest` (9/9) |
| G12 Ponytail | PASS | No critical or high findings; 4 cuts applied |
| G13 Screenshots | PASS | `screenshots/*.png`, all at 1280×720 |
| G14 Human review | PASS | Section 3 |
