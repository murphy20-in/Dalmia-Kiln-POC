# Phase 10 Rebuild Prompt — Dalmia Kiln Analytical Dashboard (v2)

Framework: **RISEN** (Role · Instructions · Steps · End goal · Narrowing), extended with a **Context** block up front and **Acceptance gates** at the end. RISEN fits because this is a multi-step agentic build with hard constraints; the Context block stops the agent re-deriving facts, and the gates make "done" checkable.

Paste everything below the line into the build session.

---

## C — CONTEXT

You are working in `/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC` on branch `phase-10-dashboard` (from `phase-09-api`, `d84244e`). Read `reports/BUILD_STATUS.md` §12–§15 before touching code. Phases 1–9 are frozen: do not edit anything outside `phase-10-dashboard/`.

**What exists (v1, commit `182ef71` + uncommitted work):**
- Plain HTML/CSS/ES modules in `phase-10-dashboard/public/`, served by stdlib `serve.py` on `127.0.0.1:8010`, which proxies `/api`, `/health`, `/ready` to Phase 9 on `127.0.0.1:8009`.
- Seven routes: `/`, `/history`, `/abnormal-periods`, `/events`, `/validation`, `/data-quality`, `/methodology`.
- Inline-SVG chart (`public/js/chart.js`, ~220 lines), pure helpers in `public/js/pure/`, 9 node tests in `tests/*.mjs`.
- **Uncommitted, must be preserved:** a GitHub Pages read-only mode — `public/js/snapshot.js` (serves `public/snapshot/*.json` when `hostname` ends in `github.io`; refuses writes with 405), `scripts/export_snapshot.py` (exports Phase 9 responses), `public/404.html` (SPA fallback), plus edits to `index.html`, `api.js`, `app.js`, `serve.py`.

**Why it is being rebuilt:** v1 is compliant but unusable. The Overview is a grid of raw enum strings (`NOT_SUPPORTED`, `NOT_AVAILABLE`, `p9-api-1.0.0`), there is no visual hierarchy, no story, no clear "what do I do next", cards are not clickable, and it does not look like a Dalmia Cement product. See `phase-10-dashboard/screenshots/overview.png`.

**The analytical truth the dashboard must tell (do not soften, do not inflate):**
- An empirical POC risk score (0–100, `p7-risk-1.1.0`) over 9,557 operational 10-min buckets, 2025-06-01 → 2025-08-23. It is reference-relative, not a probability, and not deposit-validated.
- 12 KPI-derived abnormal periods (Phase 6, `P6-xxx`), severity 3 HIGH / 4 MODERATE / 5 LOW, confidence MEDIUM (capped) or LOW, 8 of 12 load-associated. **Not plant events.**
- Phase 8: the score is **NOT shown to rise before** those periods (primary endpoint `NOT_SUPPORTED`). The O₂-excluded variant is WEAK and analyser-dependent. Neither variant is preferred.
- Event ground truth: `NOT_AVAILABLE`. Plant annotations: 0. Revalidation needs ≥ 8 evaluable labelled events.
- Data gaps: Kiln-I 2025-09 and Kiln-IIIA 2025-04 missing; open plant questions (O₂ analyser `Kiln-I!X` purge schedule, Sp.Heat F vs G, `Kiln MD` meaning, equipment identity).

**Phase 9 API fields you will consume (verified against `public/snapshot/`):**
- `/metadata/status` → `data.analytical_state`, `evidence_status`, `ground_truth`, `artifacts`
- `/abnormal-periods` → rows: `period_id`, `start_time`, `end_time`, `onset_time`, `onset_censored`, `duration_minutes`, `kpi_severity_class`, `confidence`, `dominant_family`, `deviating_families`, `load_association`, `primary_context`, `month`, `is_plant_event`, `label_type`
- `/findings` → 24 rows: `finding_id` (F1…F20, F3.W1_RANK…), `title`, `classification`, `evidence`, `evidence_redacted`, `context_only`
- `/validation/early-warning-historical` → `primary_endpoint`, `horizon_results`, `negative_controls`, `o2_excluded_sensitivity`, `censoring`, `load_adjustment`
- `/metadata/limitations` → `limitations` (L01–L13), `missing_months`, `operational_row_quality`
- `/metadata/data-requirements` → `plant_data_requirements`, `plant_questions_open`, `prohibited_uses`, `revalidation`
- `/risk-scores?variant=primary`, `/risk-scores/variant-comparison` (with `gaps_in_page`), `/events` CRUD + `/events/{id}/audit` (writes need `X-Actor`, PATCH/DELETE need `expected_version`)

---

## R — ROLE

Act as a **senior frontend engineer and data-visualisation designer**. You have built industrial analytics tools for plant engineers, and you stay disciplined about analytical honesty. You care about three things, in this order:
1. **Never overstating evidence.** A negative result reads as a result, not a failure to hide.
2. **Clarity for a plant process engineer** who has 90 seconds and needs to know what the data says and what to do next.
3. **Visual quality** that looks like a Dalmia Cement product.

Operate in Ponytail mode: plain HTML/CSS/JS, reuse `public/js/pure/*`, `chart.js`, `api.js`, `dom.js` before writing anything new, no npm runtime dependency, no chart library.

---

## I — INSTRUCTIONS

### I-1. Resolved decisions (do not reopen)
- **Stack:** keep plain HTML + CSS + ES modules served by `serve.py`. No React, no build step, no Node toolchain at runtime (`node --test` for tests only).
- **Charts:** hand-drawn inline SVG, extending the existing `chart.js`. No CDN library. It must work offline and on GitHub Pages.
- **Hosting:** both modes must work. Local mode uses the live Phase 9 proxy with annotation writes. GitHub Pages mode uses the snapshot and is read-only, and it must say so in the UI.

### I-2. Dalmia Cement theme
1. Open `https://www.dalmiacement.com/` in the browser (Playwright / Chrome DevTools MCP). Sample and record: primary green, secondary / accent colours, neutrals, font families and weights, header pattern, button style, card radius and shadow, and spacing rhythm. Save these as CSS custom properties in `public/css/app.css` and document them in `docs/DESIGN_SYSTEM.md`, noting the source of each value.
2. If the site cannot be reached, use the existing tokens (`--green #006838`, `--green-deep #003a1e`, `--orange #c4511a`, `--charcoal #414042`) and record that as the fallback.
3. Do **not** copy the Dalmia logo image or any site imagery (trademark). Use a text wordmark: "DALMIA CEMENT | Kiln Analytical POC".
4. **Colour rule that overrides brand:** the brand orange and any red, amber or "traffic-light" hues are for **brand accents and primary CTAs only**. They must never encode score bands, severity or validation status. Data states use a neutral ramp (charcoal / slate / green-tint), always paired with a **text label** and a **pattern or weight** so that colour is never the only cue.
5. Check the chosen palette with the `dataviz` skill's palette and colour rules: at least 3:1 contrast for chart marks and 4.5:1 for text. The primary series and the O₂-excluded overlay must be distinguishable in greyscale (solid line vs dashed line).

### I-3. Information architecture — dashboard sections
Every page follows the same vertical rhythm: **Page hero (title + one-sentence plain-English answer) → KPI cards → Graph(s) → Insights → Advisory → Recommended next steps → Action bar.** The retrospective disclaimer stays sticky at the top of every page.

**KPI cards.** Each card is a real `<a>` link to a deep target (see the click map). A card shows a label, a large value, a one-line plain-English meaning, and a small "Source: Phase N · endpoint" footnote. Translate enums into plain English. For example, show "Not supported" with the sub-line "Score did not rise before abnormal periods", not the raw `NOT_SUPPORTED`. Keep the raw enum in a tooltip or `<abbr>` for traceability. Overview cards:

| Card | Value (from API) | Target |
|---|---|---|
| Scored history | 9,557 ten-minute buckets · 1 Jun – 23 Aug 2025 | `/history` |
| KPI-derived abnormal periods | 12 (3 high · 4 moderate · 5 low severity) | `/abnormal-periods` |
| Early-warning validation | Not supported | `/validation#primary` |
| O₂-analyser sensitivity | Weak, analyser-dependent, not preferred | `/validation#o2` |
| Plant annotations | 0 of ≥ 8 needed to revalidate | `/events/new` |
| Data gaps and open questions | 2 missing months · N open plant questions | `/data-quality` |

Counting served rows is allowed. Computing any statistic (medians, rates, shares, correlations) on the client is not. If a number is not served by the API, do not show it.

**Graphs** (inline SVG, each with a `<figcaption>`, a text summary, and a "view as table" toggle):
- Overview: a compact score-trend strip for Jun–Aug with the 12 period bands and hatched gaps. Clicking a band opens that period.
- History: the full trend with a brush or date-range control, an "O₂-excluded overlay" toggle (off by default and labelled "Sensitivity analysis — not preferred"), period bands, event diamonds, and gaps drawn as gaps from `gaps_in_page` (never interpolated).
- Abnormal periods: a Jun–Aug timeline (Gantt-style) of the 12 periods, with severity encoded by pattern and weight, plus a small bar chart of periods by dominant family (served-row counts).
- Validation: a verdict panel, plus horizon results as a dot-and-CI plot (from `horizon_results`) with a zero reference line. **No lead-time axis, no coverage percentages, no AUC.**
- Data quality: a dataset × month coverage matrix (available / partial / missing, patterned).

**Insights** ("What the evidence shows"): three to five cards per page. Each insight is a sentence drawn from a served field (`findings.title` + `classification`, `validation.primary_endpoint`, `limitations`) and cites its `finding_id` or `L0x`, linking to it. All client-authored copy lives in **one file**, `public/js/copy.js`, so it can be reviewed and tested in one place.

**Advisory** ("How to read this"): the interpretation cautions that change what a reader should conclude. These include: the score is reference-relative and higher at low feed; half the onsets are censored; the O₂ analyser may be reading ambient air; the periods depend on the reference period; there is no ground truth. Source these from `limitations` and `validation.censoring` / `o2_excluded_sensitivity`. Use a neutral "info" style, not a warning style.

**Recommended next steps** (label exactly "Recommended next steps — data and review"): these are **data, annotation and review actions only**, sourced from `plant_data_requirements`, `plant_questions_open` and `revalidation`. Examples: "Supply timestamped coating, ring, cleaning and stoppage logs for Apr–Sep 2025", "Confirm the `Kiln-I!X` purge and calibration schedule", "Annotate what happened around period P6-020". **Never** a process, set-point, fuel, feed or control recommendation.

**Action bar / buttons.** One primary CTA per page (brand accent), with secondary actions as outlined buttons. Every button goes to a specific, pre-filled place:

### I-4. Click map (every click lands somewhere logical, and each target is deep-linkable)

| From | Action | Goes to |
|---|---|---|
| Overview KPI card | click | the target in the table above |
| Trend band / timeline bar | click | `/abnormal-periods/P6-xxx` (detail panel opens, URL updates) |
| Period detail | "View on trend" | `/history?from=<start−24h>&to=<end+24h>&period=P6-xxx` (range pre-set, period highlighted) |
| Period detail | "Annotate this period" (primary) | `/events/new?start=<start_time>&end=<end_time>&ref=P6-xxx` (form pre-filled, `annotator_viewed_risk_score=true`) |
| Event diamond on chart | click | `/events/<id>` (detail + audit trail) |
| Event detail | "Edit" / "Withdraw" | `/events/<id>/edit`, soft delete with `expected_version` and a confirm dialog |
| Insight card | "See evidence" | `/validation#F<n>` or `/data-quality#L0<n>` (anchor scrolls to and focuses the row) |
| Validation verdict | "Why not supported?" | `/validation#censoring` |
| Validation O₂ card | "Compare variants" | `/history?overlay=o2_excluded` |
| Next-step item (data request) | "Copy request" | copies the plain-text request to the clipboard, with a toast confirmation |
| Next-step item (annotate) | "Start annotation" | `/events/new?...` pre-filled |
| Data-quality matrix cell | click | `/data-quality#<dataset>-<yyyy-mm>` (detail row) |
| Any page | "Methodology" link in the hero | `/methodology#<section>` for that page's method |
| GitHub Pages mode | any write action | disabled button with the reason "Read-only hosted copy — annotate on the local service" |

URL state (`from`, `to`, `period`, `overlay`, anchors) must survive reload and back/forward, and it must work under the `404.html` SPA fallback on GitHub Pages.

---

## S — STEPS (with the skill or agent to use at each step)

1. **Plan** (`ecc:planner`, skills `frontend-patterns`, `api-and-interface-design`): read v1 code, the snapshot mode and the Phase 9 contract. Produce `docs/DASHBOARD_ARCHITECTURE.md` v2: routes, deep-link scheme, the endpoints each section consumes, and which v1 modules are reused, changed or deleted. Commit the uncommitted snapshot work first as its own commit so the rebuild diff is clean.
2. **Architect** (`ecc:code-architect`): component and data-flow plan. One fetch layer (`api.js` + `snapshot.js`), pure presenters in `pure/present.js` (enum → plain English, served-row counts), rendering in `pages/*.js`, and all copy in `copy.js`. No state library.
3. **Theme** (skills `frontend-design:frontend-design`, `dataviz`, `senior-frontend`): sample dalmiacement.com in the browser (I-2), write tokens, then build the shell: header with wordmark, sticky disclaimer, left nav (collapsing to top tabs under 900px), page hero, card, chip, button, callout and table components. Take a screenshot and compare it against the Dalmia site before moving on.
4. **Overview page** (`dashboard-builder`, `frontend-ui-engineering`): hero answer ("Retrospective analysis of Jun–Aug 2025. The risk score did not rise before the 12 KPI-derived abnormal periods; plant event logs are needed to go further."), the six KPI cards, the trend strip, and the insights, advisory, next-steps and action bar sections.
5. **History, Abnormal periods, Events, Validation, Data quality, Methodology** pages, in that order. Each follows the I-3 rhythm and wires the I-4 click map.
6. **Charts** (`dataviz`): extend `chart.js` with the brush / range control, band click targets, the timeline, the dot-and-CI plot and the coverage matrix. Keep the existing thinning above about 900 points, but draw gaps as gaps.
7. **Accessibility** (`ecc:a11y-architect`, skills `a11y-audit`, `frontend-a11y`): WCAG 2.2 AA. Every chart has a text alternative and a table; cards and bands are keyboard reachable with visible focus; the brush is keyboard-operable; colour is never the only cue; `prefers-reduced-motion` is respected. Run a Lighthouse audit and record the score.
8. **Tests** (`ecc:e2e-runner`, skills `e2e-testing`, `browser-qa`):
   - Extend `node --test` with: a click-map test (every `href` or `data-action` resolves to a real route or anchor), URL-state round-trip, enum-to-plain-English mapping, a forbidden-wording scan over `copy.js` + all `pages/*.js` + rendered HTML, and "no client statistic" (a grep for `median|mean|percent|rate` computations outside `pure/series.js` thinning).
   - Browser journeys, recorded in `reviews/E2E_LOG.md`: (a) Overview → period band → View on trend → overlay on → back; (b) period → Annotate → submit → diamond appears → audit trail → withdraw; (c) insight → evidence anchor; (d) GitHub Pages snapshot mode: writes disabled with the reason shown; (e) 375px mobile pass.
9. **Reviews, in order.** Log every finding with its disposition in `reviews/REVIEW_LOG.md`:
   - `ecc:typescript-reviewer` (JS code review)
   - `ecc:a11y-architect`
   - `ecc:security-reviewer` (plant-entered descriptions rendered as text nodes only, `X-Actor` handling, no wildcard CORS, clipboard content is plain text, no `innerHTML` with API data)
   - `ecc:mle-reviewer` (nothing recomputed or relabelled on the client, O₂ variant never preferred)
   - `cs-product-analyst` (all wording against Phase 8 §26 and the Narrowing list)
   - `ecc:python-reviewer` (only if `serve.py` or `export_snapshot.py` change)
   - `ponytail:ponytail-audit`
10. **Handoff** (`handoff`, `agent-memory`): re-export the snapshot (`scripts/export_snapshot.py`), refresh all screenshots (desktop + mobile, every page) as before/after pairs, update `reports/PHASE_10_DASHBOARD_REPORT.md` and `reports/BUILD_STATUS.md` §15, and commit.

---

## E — END GOAL (acceptance gates; all must pass)

- **G1 Scope:** `git diff phase-09-api -- ':!phase-10-dashboard' ':!reports'` is empty. Phase 9 artifact hashes are unchanged and the API starts clean.
- **G2 Honesty:** the forbidden-wording scan passes, and there is no client-side statistic. The O₂ overlay is off by default, labelled as sensitivity, and never styled as primary.
- **G3 Theme:** the tokens are documented with their source, and a side-by-side screenshot with dalmiacement.com is in `screenshots/`. No brand orange, red or amber appears on any data state.
- **G4 Sections:** every page has hero, KPI cards, graph, insights, advisory, next steps and an action bar (Methodology may skip KPI cards).
- **G5 Click map:** every row of the I-4 table works in the browser and survives reload; the click-map node test passes.
- **G6 Both modes:** the local proxy supports annotation create / edit / withdraw with `expected_version`, and the GitHub Pages snapshot mode is read-only with a visible reason.
- **G7 Accessibility:** Lighthouse Accessibility ≥ 95, keyboard-only journey (a) completes, and 200% zoom has no loss of content.
- **G8 Performance:** Overview is interactive in under 1.5 s locally, the full-range history chart renders in under 300 ms, and the console has no errors.
- **G9 Tests:** `node --test tests/*.mjs` is green, and E2E journeys (a)–(e) are logged with screenshots.
- **G10 Reviews:** every reviewer in step 9 has run, and no finding is left OPEN.

Deliver: the working dashboard, before/after screenshots of every page, the updated reports, and a short summary of what changed and which v1 code was deleted.

---

## N — NARROWING (hard constraints; a violation fails G2)

**MUST NOT show or say:**
- live, current, real-time, "now", monitoring, or alert language; any W1–W5 flag state;
- "prediction", "predict", "forecast", "probability", "likelihood", "chance of", "early warning" (except inside the disclaimer "retrospective, not an early warning" and the verdict "early-warning validation: not supported");
- lead-time numbers, coverage percentages, the Phase 7 AUC, or `afr_context`;
- band colours as alarms (LOW / ELEVATED / HIGH get neutral styling plus a text label);
- O₂-excluded presented as preferred, primary, "corrected" or "better";
- the 12 periods called events, incidents, failures, deposits, rings or coating. Their label is always "KPI-derived abnormal periods (not plant events)";
- any process, set-point, fuel, feed or operating recommendation;
- interpolation across gaps or missing months.

**MUST:**
- keep the disclaimer "Retrospective, not an early warning" visible on every page (sticky);
- draw gaps as gaps, using `gaps_in_page`;
- show the provenance version (`p7-risk-1.1.0`, `p6-abn-1.0.0`, API version) in each chart footnote;
- render plant-entered text with `textContent` only;
- show an honest empty state for annotations: "No plant annotations yet. Annotations are how this analysis can be revalidated." with an "Add the first annotation" CTA;
- show loading, error (503 on artifact mismatch) and read-only states with plain-English messages.

**Out of scope:** authentication, new API endpoints, React or any build step, chart or UI libraries, dark mode, i18n, and anything live.
