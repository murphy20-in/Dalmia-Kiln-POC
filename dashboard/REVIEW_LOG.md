# Review log: pitch dashboard

Build step 9: six reviews in parallel, plus the step 8 evaluator. Every finding has a disposition, and none is OPEN.

**Dispositions:**
- **FIXED:** changed in code or copy.
- **ACCEPTED:** kept as is, with the reason given.
- **REJECTED:** conflicts with the spec, reason given.

**Reviewer codes:**
- **M:** claims audit (mle-reviewer)
- **K:** buyer language (marketing-agent)
- **R:** React / TypeScript (react-reviewer)
- **P:** Python (python-reviewer)
- **A:** WCAG 2.2 AA (a11y-architect)
- **G:** live evaluation (gan-evaluator)
- **B:** found by the builder

## Claims audit (M): 0 blockers, 5 major, 7 minor

| # | Sev | Finding | Disposition |
|---|---|---|---|
| M1 | MAJOR | Efficiency drivers title "Combustion and draft carried most of the drift". Their share actually fell; "several systems, sustained" is the largest bucket. | FIXED: "Each month, combustion or draft was the biggest single-system source". The subtitle now names the multi-system share. |
| M2 | MAJOR | "Heat-efficiency view moved the same way". Specific heat did not rise (§8). | FIXED: the insight now says the rise is process drift, not a measured fuel-efficiency loss. The page question is kept (spec R-4), and this insight answers it honestly. |
| M3 | MAJOR | Leading indicators note "tends to come first" overclaims (§9, §11). | FIXED: "One weak candidate … likely an operator response, not usable yet". Status is now "Weak signal only". |
| M4 | MAJOR | AFR "Strong" pills on ρ −0.14 / +0.34. Phase 5 never assigned HIGH. | FIXED: labels are now Consistent / Lower confidence / Emerging (`export_data.py::strength`). The hint says the label is consistency, not size. |
| M5 | MAJOR | The O₂-excluded line was drawn on the primary zone bands. It has its own reference and is not comparable. | FIXED: zone bands are hidden while the toggle is on, with a "compare the shape, not the zones" note and a legend. |
| M6 | MINOR | "Part of the August rise traces to the O₂ analyser" was stated too firmly. | FIXED: "may trace … leaving it out roughly halves the rise". |
| M7 | MINOR | "Direction held in 25 method variants" was attached to the median. | FIXED: now tied to August-vs-June time in Warning. |
| M8 | MINOR | Warning "worth acting on" and decision cards imply alarm or prevention. | FIXED: "Well above your April–May normal". The cleaning card says "once your event logs confirm the link". The shutdown card has no prevention claim. |
| M9 | MINOR | "Average rise", but PE is a median. | FIXED: "median rise". |
| M10 | MINOR | The Why bullets omitted that uncensored onsets show no rise. The fix text needed "evaluable". | FIXED: bullet added; the fix now reads "recorded events … that the test can use". |
| M11 | MINOR | Coverage title, "statistics reviews" and leakage scope were overstated. | FIXED: title names both missing months. Reviewers are "independent engineering reviewers". Leakage wording is scoped to baseline-to-scoring stages. |
| M12 | MINOR | Load context wording was causal. Roadmap said "six months received". | FIXED: "load may have contributed" / "load link uncertain". Roadmap says "five complete months, two re-exports needed". |
| M13 | note | "8–12 weeks" is not in BUILD_STATUS. | ACCEPTED: taken from the pitch brief. Flagged to the presenter in the final handoff. |
| M14 | note | The domino reads causal. | ACCEPTED: the caveat "links seen in the data … operator's reasons not in the logs" is on the page. The hood card shows "not yet firm" for August. |
| M15 | note | The heatmap scale saturates at 3 while values reach 6.4. | ACCEPTED: every cell prints its value, and the table is available. |
| M16 | note | The 1% efficiency-gain placeholder is not supported by §8. | ACCEPTED: the calculator is labelled "Illustrative: your inputs, not a measured result", and the value is shown grey as a placeholder. The demo script says to type the plant's own numbers. |
| M17 | note | "Doubled" is true (2.11×), but only Aug vs Jun is statistically separable. | FIXED: Efficiency hero sub-line says so. |

## Buyer language (K)

| # | Finding | Disposition |
|---|---|---|
| K1 | Hero title "deposit-risk intelligence" implies detection. | REJECTED: spec R-4 mandates the title. It matches the client's use-case name, and no on-page claim says deposits are detected. |
| K2 | Objective "Preliminary risk score" uses the banned term. | FIXED: "Preliminary score: Kiln Health Index". |
| K3 | Leading-indicator note reads as lead time. | FIXED (see M3). |
| K4, K5 | "Early detection" / "Prediction" journey labels. | REJECTED: the client's own journey wording (problem statement), mandated by spec R-4. Prediction is shown as the next stage. |
| K6 | Issue sub-line sums to 21, not 32. | FIXED: "· 11 low / info" added. |
| K7, K8 | Validation page statistics. | ACCEPTED: this is the engineers' page (spec R-4 §8). Wording is simplified, but the numbers stay. |
| K9–K11 | Validation method / why jargon. | FIXED. |
| K12–K15 | "Method variants", "leakage", "byte-identical". | FIXED: "alternative settings", "tested against hindsight", "exactly the same numbers". |
| K16 | "Correlation" on fuel cards. | ACCEPTED: process heads expect the figure, and the strength hint explains the label. |
| K17, K18 | "Links held up"; undefined AFR / TAD. | FIXED: "patterns repeated"; AFR and TAD expanded. |
| K19 | O₂ card title. | REJECTED: spec asks for the "question only your team can answer" framing. |
| K20 | "Seven patterns" card title. | ACCEPTED: current title kept. |
| K21 | Fuel card titles read causal. | FIXED: strength hint says "patterns seen together, not proven causes". |
| K22 | Rigour strip has no takeaway. | FIXED: region label "How the work was checked". |
| K23, K24 | CTA and ask clarity. | FIXED: "See the Stage 2 ask", "See what Stage 2 needs from Dalmia". The CTA body names the four things. |
| K25 | Print button label. | ACCEPTED: spec text "Download summary (PDF)". |

## React / TypeScript (R)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| R1 | HIGH | Chart animations restart every 75 ms during 4× play. | FIXED: `Chart animate={!playing}`. |
| R2 | HIGH | `aria-live` card floods screen readers during play. | FIXED: one sr-only status line, updated only while paused. |
| R3 | HIGH | Scroll-to-top on drawer open/close. | FIXED: keyed on the first path segment. |
| R4 | MED | `onEvents` recreated every render; unnecessary casts. | FIXED: `useMemo`, casts removed. |
| R5 | MED | A failed fetch was cached forever. | FIXED: cache entry deleted on failure. Runtime shape check ACCEPTED: `tests/data.test.ts` locks the shape. |
| R6 | MED | `useData` keeps state across a name change. | ACCEPTED: every caller passes a constant. |
| R7 | MED | Error boundary never resets. | FIXED: keyed per route section. |
| R8 | MED | Blank page while data loads. | FIXED: a `Loading` state on every page. |
| R9 | MED | Drawer: no focus trap; effect depends on `onClose`. | FIXED: portal to body, `#root` inert, `onClose` in a ref, focus returns to `#main` as fallback. |
| R10 | MED | `setPlaying` inside the `setMs` updater. | FIXED: separate end-of-data effect. |
| R11 | MED | `?t=` sync mutated params; URL edits were overwritten. | FIXED: URL edits drive the replay; the writer runs on `ms` only (params via ref). Verified with Playwright. |
| R12 | LOW | `inState` backwards walk per tick. | FIXED: `runStart` precomputed once. |
| R13 | LOW | Key repeat; ←/→ under an open drawer. | FIXED: `e.repeat`, `defaultPrevented` and dialog guards. |
| R14 | LOW | `reduce` without an initial value. | FIXED. |
| R15 | LOW | Hard-coded scrubber months and Gantt range. | FIXED: derived from data. |
| R16 | LOW | `ConsoleData` missing `columns`. | FIXED. |

## Python (P)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| P1 | MED | Frames load at import time. | ACCEPTED: one-shot script. |
| P2 | MED | `ZONE[...]` KeyError risk. | FIXED: subset assert. |
| P3 | MED | Gap merging assumes a contiguous grid. | FIXED: contiguity assert. |
| P4 | MED | The stopped/nodata 50% vote. | ACCEPTED: the UI shows the same "Kiln stopped / no data" text for both. |
| P5 | MED | Pivot NaN not defaulted to 0. | FIXED: `fillna(0.0)`. Output unchanged. |
| P6 | MED | Hard-coded BUILD_STATUS numbers. | FIXED: commented as manual copies with their section. |
| P7 | MED | Fragile filename split. | FIXED: strict regex. |
| P8–P12 | LOW | Style and robustness nits. | ACCEPTED. |

## Accessibility (A)

| # | SC | Finding | Disposition |
|---|---|---|---|
| A1 | 2.1.4 | Single-key `P` shortcut. | ACCEPTED: required by spec (presenter). It is ignored in inputs, with modifiers, on key repeat and under dialogs. The visible Present button does the same thing. |
| A2 | 2.4.7 | Invisible focus on the scrubber. | FIXED: `focus-within` ring on the strip. |
| A3 | 4.1.3 | Live-region flood. | FIXED (see R2). |
| A4 | 2.4.3 | Drawer focus trap. | FIXED (see R9); `aria-labelledby` added. |
| A5 | 1.4.3 | Normal and Warning ink below 4.5:1 for small text. | FIXED: text inks `#177058` / `#b04515`; fills unchanged. |
| A6 | 1.4.11 | Watch fill `#d99a00` is 2.4:1. | ACCEPTED: spec colour, always paired with the word, and every chart has a table (dataviz rule). Breadth grey darkened: FIXED. |
| A7 | 1.1.1 | Console charts have no data alternative. | FIXED: the trend label carries the current value and zone. The sparkline is decorative next to the big number: ACCEPTED. |
| A8 | 4.1.2 | `aria-pressed` combined with a changing label. | FIXED: `aria-pressed` removed. |
| A9 | 2.1.1 | Table scroll container not focusable. | FIXED: `tabIndex=0`, `role=region`. |
| A10 | 2.4.11 | Sticky replay bar can obscure focus. | FIXED: sticky only at `lg`. |
| A11 | 3.3.1 | `datetime-local` snaps while typing. | ACCEPTED: native control; it snaps to the 10-minute grid by design. |
| A12 | 1.3.1 | `aside` wrapper; skip target not focusable. | FIXED. |
| A13 | 3.1.1 | Raw enum in an sr-only span. | FIXED: removed. |

## Live evaluation (G): round 1 scores ranged 5 to 10

| # | Finding | Disposition |
|---|---|---|
| G1 | Charts time-shifted against cursor and period shading. | FIXED: root cause was ECharts formatting time axes in browser local time (IST). `useUTC: true` in the Chart wrapper. |
| G2 | Gauge vs 24-h chart mismatch. | FIXED (same root cause as G1). |
| G3 | Pasted `?t=` ignored. | FIXED (see R11). |
| G4 | URL not updated during Play. | ACCEPTED: written on pause by design, to avoid history and render churn. |
| G5 | Empty 24-h chart in a long gap. | FIXED: shows the "Kiln stopped / no data" notice. |
| G6 | Calculator clamping silent; 250% accepted. | FIXED: % inputs clamp to 0–100 with a max attribute. |
| G7 | Exec and Console content below the fold. | FIXED: tighter hero and header spacing. |
| G8 | "Define early detection vs prediction". | REJECTED: spec wording (see K4). |
| G9 | Objectives card long. | ACCEPTED: spec requires the 7-objective scorecard. |
| G10 | Stepper says "Stage 3" but Roadmap puts intervention at Stage 4. | FIXED: "Stages 3–4". |
| G11 | Efficiency title mismatch; O₂ legend missing. | FIXED (M1, M5). |
| G12 | Period markers #2/#3 collide. | ACCEPTED: adjacent days; the table has exact dates. |
| G13 | Periods subtitle orphaned. | FIXED: moved into the Gantt subtitle. |
| G14 | Small Gantt targets. | ACCEPTED: bars have a 10 px minimum, heatmap rows are clickable, and sr-only links exist. |
| G15 | Period 12 High but pale heatmap row. | ACCEPTED: severity comes from peak and duration; the heatmap shows per-system deviation, a different measure. Covered in the demo script. |
| G16 | "Strong" pills. | FIXED (M4). |
| G17 | Lone last card. | FIXED: 4-column grid. |
| G18 | "Feed held steady" despite the May dip. | FIXED: title gives the 380–420 TPH range. |
| G19 | Coverage heatmap all navy. | FIXED: healthy cells pale, gaps loud orange. |
| G20 | Copy button gives no feedback. | ACCEPTED: already shows "Copied" (the evaluator could not test the clipboard). |
| G21 | No Stage 2 investment line. | FIXED: "Stage 2 investment: to be scoped with you." |
| G22 | "Placeholder" repeated under every input. | FIXED: one hint line, with placeholder values in grey. |
| G23 | Validation footer shows repo paths. | ACCEPTED: spec asks for a technical-reference footer. |

## Builder findings (B)

| # | Finding | Disposition |
|---|---|---|
| B1 | Validation framed NC1/NC2 as "controls behave". They actually show the pre-period rise cannot be told apart from chance. | FIXED: moved into the result text; the trust card is now hindsight testing. |
| B2 | Coverage cells at 99.87% showed as "100%". | FIXED: one decimal below 99.95%. |
| B3 | `echarts-for-react/lib/core` resolved to a CJS object and crashed the Console. | FIXED: ESM entry. |
| B4 | Gantt used deprecated `api.style` (console warning). | FIXED: literal style. |
| B5 | Wording rule deviation: "Prediction" (the client's journey-stage noun) is allowed; every other form of "predict" is banned. "aria-live" is exempt from the live rule. | ACCEPTED: documented in `tests/wording.test.ts`. |

## Live evaluation, round 2 (G2): every P0 page scored ≥ 8 except the items below, all now FIXED

| # | Finding | Disposition |
|---|---|---|
| G2-1 | Jump chips and "Replay in Console" land on the drift onset (6 h before the period start) without saying so. | FIXED: the chip heading says "where a high-severity period began drifting"; the drawer shows a "Drift began" row; the button reads "Replay from where the drift began". |
| G2-2 | Roadmap honesty 6/10: the 1% efficiency-gain placeholder drove 82% of the total, contradicting the Efficiency page. | FIXED: default is 0% ("enter your own"), so the total starts from stoppages only. Also resolves M16. |
| G2-3 | y-axis ticks 90/100 crowded. | FIXED: fixed 25-point interval. |
| G2-4 | Unexplained gaps in the daily line. | FIXED: subtitle says gaps are stopped or no-data days. |
| G2-5 | Gantt gridline near 29 Jun does not match a label. | ACCEPTED: ECharts time-axis minor split; labels are correct. |
| G2-6 | Captures caught intro animations mid-way. | ACCEPTED: 300 ms animation by spec. The demo script opens tabs before the meeting. |
| G2-7 | Lighthouse contrast: white text on a green badge (Roadmap, stepper) and on a cyan chip (Exec). | FIXED: darker `normal-ink` fill; the chip is navy. |
