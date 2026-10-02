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

---

# UX pass (2026-10-01): presentation polish

This pass covered presentation only. The audit, scores and gates are in [UI_UX_AUDIT.md](UI_UX_AUDIT.md); the tokens and components are in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

**Analytical integrity:** these files have the same sha256 before and after the pass:
- `public/data/*.json` (7 files)
- `scripts/export_data.py`
- `src/lib/value.ts`

**Reviews:** ran in parallel after the build.

**Reviewer codes (UX pass):**
- **UM:** claims (mle-reviewer)
- **UA:** WCAG 2.2 AA (a11y-architect)
- **UR:** React / architecture (react-reviewer)
- **US:** security (security-reviewer)
- **UP:** ponytail audit
- **UB:** builder

## Claims (UM): 0 blockers, 3 major, 6 minor

| # | Sev | Finding | Disposition |
|---|---|---|---|
| UM1 | MAJOR | The hero thesis mentioned "12 abnormal periods" without the evidence labels. | FIXED: "12 KPI-derived abnormal periods … (not validated plant events)". |
| UM2 | MAJOR | Efficiency daily chart draws period markers with no "not validated" label. | FIXED: the legend reads "Abnormal period began (KPI-derived, not a validated plant event)". |
| UM3 | MAJOR | "Demonstrated" next to "Early detection · Delivered" could read as validated. | FIXED: "Demonstrated in this proof of concept, on historical data". The stage name "Early detection" stays (client wording, see K4/K5). |
| UM4 | MINOR | "Repeatable?" reads as validated. | FIXED: "Stable across settings?" and "… (a sensitivity check, not validation)". |
| UM5 | MINOR | "System evidence" can read as evidence of an event. | FIXED: "System deviation from April–May normal". |
| UM6 | MINOR | "pts" vs "percentile points". | FIXED: "percentile pts". |
| UM7 | MINOR | "every month" is hard-coded. | ACCEPTED: `data.test.ts` pins the shares 0.251 / 0.416 / 0.530, so a data change fails the test first. |
| UM8 | MINOR | "Each fixed, masked or set aside" is a blanket claim. | ACCEPTED: unchanged wording from the reviewed build (issuesSub). |
| UM9 | MINOR | Present tense ("at this moment", "right now") in a replay UI. | FIXED: "at the replayed moment". The decisions panel stays marked "Stage 3 · illustrative". |

## Accessibility (UA): 0 critical, 5 serious, 7 moderate, 5 minor

| # | Sev | Finding | Disposition |
|---|---|---|---|
| UA1 | SERIOUS | The skip link `href="#main"` rewrote the HashRouter route. This was pre-existing. | FIXED: onClick moves focus to `main`. |
| UA2 | SERIOUS | Bare `P` was a single-key shortcut (2.1.4). | FIXED: Shift+P. README and button hint updated. |
| UA3 | SERIOUS | The navy focus ring was invisible on navy-ink panels. | FIXED: white ring with a navy halo inside navy surfaces. |
| UA4 | SERIOUS | The sticky replay bar under the sticky header could fill a zoomed or small viewport. | FIXED: sticky only at `lg`, plus `scroll-padding-top`. |
| UA5 | SERIOUS | An expanded sidebar at 320 px left about 80 px for content. | FIXED: below `md` the expanded sidebar overlays (fixed). A matchMedia listener collapses it on resize. |
| UA6 | MODERATE | Changing label plus `aria-pressed` on Play/Pause and View data. | FIXED: `aria-pressed` removed; the label carries the state. |
| UA7 | MODERATE | The Present button had no visible-text name below `sm`. | FIXED: `sr-only sm:not-sr-only`. |
| UA8 | MODERATE | Stepper state conveyed by colour only. | FIXED: sr-only state text and `aria-current="step"`. |
| UA9 | MODERATE | Scrubber gap and tick contrast too low. | FIXED: gap fill `ink-muted/80`, ticks `navy/70`. |
| UA10 | MODERATE | aria-live on the whole calculator column; `aria-busy` on the skeleton. | FIXED: live region on the total only (atomic); `aria-busy` removed. |
| UA11 | MODERATE | Number inputs clamp silently. | ACCEPTED: units, including "%", are in every label. Clamping is unchanged from the reviewed build. |
| UA12 | MODERATE | Console trend chart had no text alternative. | FIXED: the label gives the current value, zone and 24 h range. The sparkline stays labelled; the Efficiency number is shown as text. |
| UA13 | MINOR | Nav group labels were aria-hidden. | FIXED: visible to assistive technology. |
| UA14 | MINOR | The status chip was hidden on phones and carried meaning only in `title`. | FIXED: icon chip at all widths, plus sr-only status and hint. |
| UA15 | MINOR | Selected period row is colour only. | FIXED: `aria-current` on its link. |
| UA16 | MINOR | Jump-chip names. | OK: the name starts with the visible "Period N" and date. |
| UA17 | MINOR | Tooltips are mouse-only. | ACCEPTED: every ChartCard has "View data". The Console charts carry text labels (UA12). |

## React / architecture (UR): 0 critical/high

| # | Sev | Finding | Disposition |
|---|---|---|---|
| UR1 | MEDIUM | `Chart` memo cannot skip the time-dependent Console charts. | ACCEPTED, and the comment was corrected. They must redraw each tick. Static Console parts (header, chips, decisions, scrubber track) are memoised. Measured: 4× playback at 59 fps, p95 frame 16.8 ms, 0 long tasks. |
| UR2 | MEDIUM | Logo hard-coded hex. | FIXED: `brand.navy` / `brand.cyan`. |
| UR3 | MEDIUM | Colour literals outside theme.ts. | FIXED: `heatLow`, `navyLine`, `cyanSoft`, `heading`, `hoverFill`, `periodFill`, `periodEdge`, `gapFill`, `zoomFill` tokens. Tailwind reads them from theme.ts. |
| UR4 | MEDIUM | ChartCard table toggle unmounts the chart, losing the zoom. | ACCEPTED: the table is the accessible view; resetting zoom on return is acceptable. |
| UR5 | MEDIUM | `charts/Chart` imports `reducedMotion` from `components/ui`. | ACCEPTED: one small import; moving it adds a file for no behaviour change. |
| UR6 | LOW | Play at the end of the data did nothing. | FIXED: restarts from the beginning. |
| UR7 | LOW | Drawer focus return when the opener had been detached. | FIXED: `prev.isConnected` check, falling back to `main`. |
| UR8 | LOW | Efficiency stacked-column options are built inline. | ACCEPTED: cheap, and only rebuilds on the O₂ toggle. |

## Security (US): 0 critical/high/medium

| # | Sev | Finding | Disposition |
|---|---|---|---|
| US1 | LOW | `pages.yml` actions are pinned to tags, and permissions are workflow-wide. | ACCEPTED for this pass: CI is out of UI scope. Recommended follow-up: SHA pins and job-level `pages`/`id-token` permissions. |
| US2 | LOW | No CSP meta. | ACCEPTED: optional hardening; GitHub Pages cannot set headers. Recommended follow-up, tested against the build. |

All tooltip formatters go through the escaping `tip()`. There is no `dangerouslySetInnerHTML`, no external scripts, fonts or telemetry, and no secrets.

## Ponytail audit (UP): no critical/high

| # | Finding | Disposition |
|---|---|---|
| UP1 | `ScatterChart` and `AriaComponent` registered but unused. | FIXED: removed (about −9 kB). |
| UP2 | `.mono` and `.btn-ghost` CSS classes unused; `CtaBand` unused after the hero redesign. | FIXED: removed. |
| UP3 | Copy keys `labels.with`, `summary.cta` and `brandLine.dalmia/plant/vendor` unused. | FIXED: removed. |

## Builder (UB)

| # | Finding | Disposition |
|---|---|---|
| UB1 | Charts kept their width on live resize (grid items `min-width: auto`). | FIXED: `.card` is `min-w-0`. No overflow at 375–1920 on fresh load or live resize. |
| UB2 | Periods index and matrix were too narrow side by side at 1280. | FIXED: stacked full width; matrix labels break onto two lines. |
| UB3 | Coverage heatmap gaps changed from alarm orange (G19) to dark navy. | DELIBERATE: the brief says not to make data quality look like a red-alert monitor. Gaps stay the loudest cells, with "✕ 0%" text and a legend. |
| UB4 | Nav order now groups Intelligence → Evidence → Roadmap, so Validation comes before Roadmap in presentation mode. | DELIBERATE: grouping requested in the brief; the pitch now ends on the ask. |
| UB5 | The native date input follows the browser locale (12-hour in en-US). | ACCEPTED: a large 24-hour "Replaying" stamp is now the primary readout. |

# Brand fusion pass (2026-10-01): Astrikos AI × Dalmia

Reviewers: ecc:react-reviewer (BR), ecc:a11y-architect (BA), ecc:security-reviewer (BS), ecc:mle-reviewer (BM), ponytail-audit (BP), and the builder (BB).

## React / TypeScript (BR): 0 critical

| # | Sev | Finding | Disposition |
|---|---|---|---|
| BR1 | HIGH | Print: dark surfaces would print white-on-white; no `print-color-adjust`. | FIXED: `* { print-color-adjust: exact }`; dark surfaces keep their colour (checked with print emulation). |
| BR2 | MED | Data Readiness heatmap rebuilt on every render (the "Copied" click redrew it). | FIXED: `useMemo`. |
| BR3 | MED | `StatusGauge` rebuilt its option on every Console tick. | FIXED: `memo`. |
| BR4 | MED | The drawer's portal was printed over the page. | FIXED: `no-print`. |
| BR5 | MED | The expanded sidebar overlay below 768 px stayed open after navigating. | FIXED: collapses on route change. |
| BR6 | LOW | Validation hero was a `div role=region`; `aria-current="true"` on timeline links. | FIXED: `section`; `"page"`. |
| BR7 | LOW | Dead CSS: `.chip`, `.chip-btn`, `.anim-settle`. | FIXED: removed. |
| BR8 | LOW | Render-time ref assignment in Drawer; hard-coded " to " in a screen-reader span; `reducedMotion` imported from `ui`; unneeded type exports. | ACCEPTED: all pre-existing, none a defect. |
| BR9 | n/a | Console playback memoisation. | VERIFIED intact (`ConsoleBand`, `JumpChips`, `Decisions`, `Track` memoised). |

## Accessibility (BA): 0 critical, 2 serious, 7 moderate

| # | Sev | Finding | Disposition |
|---|---|---|---|
| BA1 | SERIOUS | The sticky Console deck (about 300 px) could hide a focused control (2.4.11). | FIXED: sticky only at ≥1024 × ≥800 px, with `scroll-padding-top` that clears it. At 1280×720 it scrolls normally. |
| BA2 | SERIOUS | Route changes were silent: one static `<title>`, focus unmoved. | FIXED: per-page `document.title`; focus moves to `<main>` after a route change (not on first load). |
| BA3 | MOD | Scrubber gaps and ticks under 3:1 and differing by hue only. | FIXED: solid slate/70 gaps with a hatch; high-severity ticks are taller and orange; legend matches. |
| BA4 | MOD | Windows High Contrast drops fills. | FIXED: transparent outlines on thumb, ticks and gaps; `.hatch` gets a dashed edge in forced colours. |
| BA5 | MOD | Reduced motion shortened but did not stop looping animations (`animate-pulse`). | FIXED: `animation-iteration-count: 1`, `scroll-behavior: auto`. |
| BA6 | MOD | 11 px `haze` text over the hero glow was about 4.4–4.6:1. | FIXED: `mist` (8:1). |
| BA7 | MOD | The sidebar was a redundant `aside` landmark; the lockup name read "×" as "times". | FIXED: `div`; "and". |
| BA8 | MOD | Console status region plus `aria-valuetext` on every scrub; Shift+P / arrows (2.1.4); overlay menu has no Escape. | ACCEPTED: the region is silent while playing; Shift+P has a modifier and a visible Present button; arrows apply only in presentation mode. |
| BA9 | MINOR | LOW-severity Gantt bars about 2:1; hover-only tooltips; fixed px sizes. | ACCEPTED: bars are labelled with text; every chart has "View data"; unchanged from before. |

Lighthouse accessibility 100 on all 8 routes before and after these fixes. Contrast ratios in BA were hand-computed (about ±0.1).

## Security (BS): 0 critical/high/medium

| # | Sev | Finding | Disposition |
|---|---|---|---|
| BS1 | LOW | `npm audit --omit=dev`: 3 moderate advisories (echarts XSS, react-router open redirect and SSR). | PRE-EXISTING, identical at HEAD. The only new dependency, `@fontsource/jetbrains-mono`, has none. Recommended follow-up: echarts 6. |
| BS2 | n/a | Tooltip HTML, SVG logos, external loads, favicon, dangerous sinks. | VERIFIED: every tooltip string and swatch colour is escaped or a theme token; logos are `<img>` with no script, `foreignObject` or external href; no runtime external loads. |

## Claims and analytical integrity (BM): 0 blockers, 0 major, 2 minor

| # | Sev | Finding | Disposition |
|---|---|---|---|
| BM1 | MINOR | The hero foot said "(not validated plant events)" in lowercase. | FIXED: "Not validated plant events", matching the evidence label. |
| BM2 | MINOR | The Console scrubber legend and jump chips lacked the two period labels. | FIXED for the legend: it carries "KPI-derived abnormal periods · Not validated plant events". The chips are jump buttons for a moment, not period surfaces. |
| BM3 | n/a | Data, scripts, gaps, numbers. | VERIFIED: no diff under `public/` or `scripts/`; hero numbers come from `summary.json` via `fmtPct`; KPI micro charts use existing fields only; `connectNulls: false` intact. |

## Ponytail audit (BP): no critical/high

| # | Finding | Disposition |
|---|---|---|
| BP1 | `background.navy/hero/surfaceElevated/overlay`, `dalmia.blue/green/grey`, `fog` have no component uses. | ACCEPTED: named in the brief as the semantic token set. |
| BP2 | `motion.ease`, `elevation.*` and `gradient.*` are read only by `tailwind.config.ts`. | ACCEPTED: that is how they reach CSS. |

## Green pitch pass (BG), 2026-10-03

Scope: presentation only. Green token system, Console first, integrated Console timeline, Executive Summary hero and KPI names, green charts and surfaces on every page. Reviewers: React, security, analytical semantics, accessibility; Ponytail audit; Lighthouse (Accessibility, Best Practices, SEO 100 on `#/console` and `#/summary`, production build); Playwright journeys.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| BG1 | MEDIUM | The first Console state bar drew the *dominant* state per day. 37 of 75 days contained Warning rows but were drawn Normal or Watch, and 3 abnormal periods sat under days drawn with no Warning. | FIXED: each day is a stacked column of the recorded share of Normal / Watch / Warning (Warning on top). No dominance rule. The legend note says so. |
| BG2 | MEDIUM | The deck said "Kiln stopped" for every missing row, including `nodata` gaps. | FIXED: the label follows the gap kind ("Kiln stopped", "Data not recorded", or "Stopped or no data"). |
| BG3 | MEDIUM (a11y) | The state bar relied on colour alone; Eucalyptus (Normal) and the Warning orange have the same luminance (1.05:1). | FIXED: Warning carries a pinstripe texture (also in the legend) on top of its colour, and Warning stacks on top. |
| BG4 | MEDIUM (a11y) | Non-text contrast: gap hatch invisible on its slate fill (1.1:1); selected-speed state a faint tint (1.56:1); text-input borders 1.6–1.9:1; marker line 1.2–2.0:1 on the state fills. | FIXED: light hatch on dark; selected speed has an Emerald fill tint and inset ring; deck input border `sage/70`, Roadmap inputs Eucalyptus (3.8:1); the marker has a Deep Forest halo. |
| BG5 | LOW (a11y) | Label contrast: Watch bars (4.1:1) and the Draft series (3.8:1). Watch fill 2.45:1 on white. | FIXED: Watch labels Deep Forest (5.9:1), Watch fill `#c28700` (3.1:1 on white, labels 4.65:1), Draft series olive `#6b7a2e` with white labels (4.7:1). |
| BG6 | LOW (a11y) | The scrubber focus ring vanishes in forced-colors mode. The slider's value text carried only the time, and the status line then announced the state a second time on every key press. | FIXED: transparent outline fallback; `aria-valuetext` is "time: state, index"; the status line stays silent while the slider has focus; a screen-reader description of the bar is attached with `aria-describedby`. |
| BG7 | LOW | Marker lagged the scrub by 120 ms; the opacity-0 slider could fight touch scrolling; stale "navy" comments; a redundant `/` route; unused tokens; the Mist contrast comment said 10:1 (it is 8:1). | FIXED. |
| BG8 | LOW | The 375 px date scale collided. | FIXED: only month labels below 640 px. |
| BG9 | n/a | Playback re-renders three ECharts per tick (design from before this pass). | ACCEPTED: `animate={!playing}` is set; unchanged from the previous commit. |
| BG10 | n/a | Editing `?t=` by hand while the Console is mounted can be ignored, and Play may then not start. | PRE-EXISTING: reproduced on the previous commit. Fresh loads and deep links (the drawer's "Replay" link, jump chips, pasted URLs) work. Not fixed. |
| BG11 | n/a | "Efficiency deterioration index" rather than "Kiln Efficiency Index". | DELIBERATE: it is the index's real name and higher means worse; "Efficiency Index" alone could read as higher-is-better. |
| BG12 | n/a | Data, scripts, numbers, wording. | VERIFIED: SHA-256 of every `public/data/*.json` identical before and after; no diff under `public/` or `scripts/`; the wording and token tests pass; the security review found no new dependency, no unescaped data in tooltips, no external loads. |
| BG13 | n/a | Remaining advisories from the accessibility review: orange annotation line (2.3:1) and the Breadth bar (2.5:1) on white; `textFaint` Roadmap icons (2.8:1); `emeraldDeep` on the canvas (2.9:1). | ACCEPTED: each carries a text label or value beside it, or is decorative; no chart sits directly on the canvas. |
| BG14 | n/a | The brief lists ecc:planner and ecc:code-architect. | NOT SPAWNED: the plan came from reading the existing code. The React, accessibility, analytics and security reviewers and the Ponytail audit were run. |

## Builder (BB)

| # | Finding | Disposition |
|---|---|---|
| BB1 | The `aside` print rule hid the Executive Summary "Core finding" in print. | FIXED: it is a `section`. DESIGN_SYSTEM.md records the rule. |
| BB2 | The Dalmia logo's 652×652 canvas leaves large empty margins. | FIXED by cropping the `viewBox` only (`12 184 606 292`); all paths are identical to the supplied file. |
| BB3 | The seam chip overlapped the Dalmia "D". | FIXED: wider panels, smaller chip, smaller logo. |
| BB4 | The Efficiency KPI value overflowed its tile at 1280. | FIXED: smaller value, `whitespace-nowrap`. |
| BB5 | The wording test bans the literal token "POC". | The brief's "Historical Analytical POC" is rendered "Historical analytical proof of concept". |
| BB6 | Console playback after the redesign. | MEASURED against the previous commit on the same machine: 59.8 / 60.1 fps vs 60.1 / 60.1, 0 long tasks. |
| BB7 | The brief names `/mnt/data/...` for the logos and references. | The files were in the repo at `Astrikos and Dalmia logo SVG/`; used from there. That folder is left untracked; the logos used by the app are copied to `src/assets/brand/`. |
| BB8 | The brief lists ecc:planner and ecc:code-architect. | NOT SPAWNED: the design was planned in-session from the existing code. The React, accessibility, security and claims reviewers and the Ponytail audit were run. |

## Visual correction pass (VC): gradient depth, timeline rebuild, product name

A later pass with three objectives and nothing else: make the green gradient system visibly atmospheric, rebuild
the historical console bar, and raise "Kiln Intelligence" to product-title scale. No data, methodology or claim
changed; `public/`, `scripts/` and every analytical string are untouched.

| # | Finding | Disposition |
|---|---|---|
| VC1 | The palette was green but the surfaces were flat: two-stop linear washes read as "a blue dashboard recoloured green". | FIXED: every gradient is radial-first and travels Abyss → Deep Forest → Brunswick → an Emerald light, with dark edges. `abyss` #08201a added as the darkest Deep Forest step, for gradient anchors only. Strength is a hierarchy (hero/header → deck/sidebar → well → canvas → none on cards). |
| VC2 | The state bar read as a barcode: a `border-r` divider on each of 92 day-columns combed the ribbon into stripes. | FIXED: dividers removed, columns overlap by half a pixel, so the days read as one band. The encoding is unchanged — same per-day shares, Warning on top, no dominant-state rule. |
| VC3 | The Warning pinstripe (vertical, 1 px every 4 px) beat against the ~10 px columns into visual static. | FIXED: the texture now runs **horizontally**, across the columns, at lower contrast. State is still never colour alone, and the legend key carries the same weave. |
| VC4 | Data gaps were drawn as near-opaque light slate with a bright hatch — the loudest thing on the track, reading as alarm rather than absence. | FIXED: a recessive slate veil (`/45`) with a low-contrast hatch. A gap is now the quietest mark on the ribbon. |
| VC5 | The legend floated above the bar, and the period strip, scale and footnote each sat on their own row: five objects, not one control. | FIXED: one clipped well (`bg-track`, `shadow-inset`) with a fused internal header strip (title · recorded range · the four state keys), the lane, and a footer strip. Measured: zero pixels of any descendant escape the well at 375 / 768 / 1024 / 1280 / 1440 / 1920. |
| VC6 | The date scale used full-height left borders, cutting the object into table cells. | FIXED: a short tick at the mark with its label beside it. |
| VC7 | "Kiln Intelligence" read as a navigation label (22–46 px, semibold). | FIXED: 24 → 32 → 48 → 56 → 64 px, bold, `-0.045em`, Polar + Emerald, with a close and a wide Emerald halo and a short rule above the plant caption. `--header-h` steps with it. |
| VC8 | At 1024 px the enlarged name overflowed its shrunk flex box and ran under the history icon and status text. | FIXED: the status block's long line appears from 1280 px and the block itself from 1024 px; the name's steps are now bounded by measured clearance at every breakpoint (640: 18 px, 768: 116, 1024: 125, 1280: 81, 1440: 241, 1920: 649; name overflow 0 everywhere). |
| VC9 | The timeline well is ~196 px tall, above the 120–170 px the brief suggests. | ACCEPTED: the extra height is the evidence footer ("KPI-derived abnormal periods · Not validated plant events"), which the claims audit requires to stay inside the component. The whole deck still ends at y=651 on a 1280×720 fold. |
| VC10 | The brief sketches a six-component tree (TimelineHeader / TimelineTrack / StateSegments / GapSegments / PeriodMarkers / SelectedMarker / TimeScale). | NOT BUILT AS COMPONENTS: that is the visual structure, and it is what the rendered object now is. Six single-use components around 40 lines of markup would be abstraction for its own sake; `Track` and `Scrubber` remain the only two. |
| VC11 | Verification. | Lighthouse (desktop, production build): accessibility 100, best practices 100, SEO 100; the single failure is a missing `llms.txt`, irrelevant here. Performance trace: LCP 92 ms, CLS 0.00. Zero console errors or warnings. `npm test` 10/10, `npm run typecheck`, `npm run build` all pass. |
