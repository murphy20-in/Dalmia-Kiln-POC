# Review log (Phase 10 v2, step 9)

Every finding from the seven step 9 reviews, with its disposition. **FIXED** means the code changed and the change was checked, using the evidence named. **ACCEPTED** means it was not changed, for the reason given. No finding is OPEN (gate G10).

Evidence is recorded as follows:
- **test:** a `node --test tests/*.mjs` check. There are 20 tests, and all pass.
- **browser:** checked in the IDE browser, or in headless Chrome using `tests/e2e/capture.mjs`.
- **curl:** a request to `serve.py`.
- **fixture:** the text now appears in `tests/fixtures/rendered/*.txt`, which were re-captured after the fixes.

## 1. JavaScript code review (`typescript-reviewer`: 3 HIGH, 6 MEDIUM, 7 LOW)

| # | Sev | Finding | Disposition | Evidence |
|---|---|---|---|---|
| J1 | HIGH | A slow page can overwrite the page the user has since navigated to | FIXED. `app.js` gives each render a guarded root whose `replaceChildren` does nothing once that render's signal has been aborted | browser: open Periods then Validation quickly; the result is Validation |
| J2 | HIGH | The hosted copy caches aborted or failed snapshot fetches forever | FIXED. `snapshot.js` `load()` fetches without a signal and deletes the cache entry when the fetch rejects | code review; the hosted run (d) loads every page |
| J3 | HIGH | Editing can't clear optional fields, because PATCH merges | FIXED. `eventPayload(input, version, previous)` sends `null` for a field that was set and is now empty | test: "PATCH sends null to clear a field" |
| J4 | MED | Double submit creates duplicate annotations | FIXED. The submit and Withdraw buttons are disabled while their request is running | browser |
| J5 | MED | Withdrawing without a saved name leads to a dead end | FIXED. Withdraw asks for the name (`MSG.actorPrompt`) when none is saved | browser |
| J6 | MED | The server's validation details are thrown away | FIXED. `ApiError.details` is kept, and each problem is shown with its field name; the first invalid field gets focus | browser: a 422 marks the field `aria-invalid` |
| J7 | MED | The skip link breaks routing | FIXED. A click on `#main` calls `preventDefault()` and focuses `main` | browser: no history entry is added and the route is unchanged |
| J8 | MED | The annotation list and counts are capped at 100 rows | FIXED. `getAll("/api/v1/events", {status: "ALL"}, {pageLimit: 100})` pages through everything | code review |
| J9 | MED | A 409 conflict discards what the user typed | ACCEPTED. The form reloads the other editor's version and a toast says so. Merging two versions field by field is more than a single-analyst POC needs | E2E journey (b) |
| J10 | LOW | Unknown routes silently show Overview | FIXED. A `role="status"` notice reads "That page does not exist. Showing the overview." | browser: `/foo` |
| J11 | LOW | Dead code | FIXED: removed `setQuery`, the `loadSeries(range)` branch, `dom.js` `clear`/`text`, and the `<base>` comment. ACCEPTED: `linkTarget` returning an object, because callers test it for truthiness and route tests cover it | test: route |
| J12 | LOW | Series data can be truncated without notice, and paging can loop | FIXED: the loop stops when `next_offset` does not advance. ACCEPTED: the 12,000-row cap has no on-screen flag, because the full series is 9,557 rows and the table note states the row count shown | code review |
| J13 | LOW | A cancelled drag swallows the next click | FIXED. `pointercancel` resets `dragged` | code review |
| J14 | LOW | A narrow brush can produce an invalid range | FIXED. The brush is skipped when both ends snap to the same bucket | code review |
| J15 | LOW | Leaving the page mid-save hides the outcome | FIXED. Write requests don't take the route signal, so they finish and still show their toast | code review |
| J16 | LOW | History misses annotations that start before the range | FIXED. It now uses an overlap test, the same as periods | code review |

## 2. Accessibility (`a11y-architect`: 3 HIGH, 6 MEDIUM, 5 LOW)

| # | Sev | Finding | Disposition | Evidence |
|---|---|---|---|---|
| A1 | HIGH | 2.4.3: a preset, the overlay checkbox or Apply re-renders `main` and focus is lost | FIXED. A same-page render restores focus to the id of the control that triggered it, and all of these controls have stable ids | browser: after "Jun 2025", `activeElement` is `#h-2025-06` |
| A2 | HIGH | 2.4.11: the sticky disclaimer covers the nav and the focused element | FIXED. A `ResizeObserver` sets `--sticky` from the disclaimer's real height, `scroll-padding-top` uses it, and the nav is not sticky at 900 px and below | browser: 720 px |
| A3 | HIGH | 2.5.8: chart targets are too small | FIXED through the equivalent-control exception: every trend chart has "List the periods and annotations in this chart", a list of ordinary links. Below 720 px the chart keeps a 600 px minimum width inside a scrolling frame | fixture: overview, history, events |
| A4 | MED | 2.4.7: focus looks the same as highlight | FIXED. The band focus stroke is 5 (the highlight is 3), `.row-focus` has its own rule, and a focused diamond scales ×1.6 | browser |
| A5 | MED | 1.4.10 / 1.4.4: SVG text becomes tiny at 320 px and strokes become sub-pixel | FIXED. The chart frame is `overflow-x: auto`, `tabindex=0`, `role=region` and named. The chart has a 600 px minimum width at 720 px and below, and strokes use `vector-effect: non-scaling-stroke` | browser: 375 px, page overflow 0 |
| A6 | MED | 1.1.1 / 1.3.1: the chart table is thinned, has no marks and no summary, and the readout floods screen readers | FIXED: the readout is no longer `aria-live`; a native range input ("Step through the plotted scores") steps through every plotted point and announces it with `aria-valuetext`; the marks list links every period and annotation. ACCEPTED: no computed min/max/median summary, because the rebuild forbids client-side statistics. The table says how many points it shows and that every value is served | browser: the slider at 925 reads "23 Aug 2025 00:40 · primary score 92.78" |
| A7 | MED | 4.1.3: the toast is set while hidden, and a repeated message isn't announced | FIXED. The region is always present; the text is cleared, set again on the next animation frame, then emptied | browser |
| A8 | MED | Disabled write buttons can't be reached and their reason isn't linked | FIXED. `roButton` uses `aria-disabled` with `aria-describedby` pointing to the `.ro-reason`, and activation is blocked. The form fieldset references `#form-ro` | test: honesty "write actions go through roButton"; browser: hosted run (d) lists every disabled control with its reason |
| A9 | MED | 3.3.1: form errors are one line with no `aria-invalid`, orphan hints and no required marker | FIXED. The status is `role="alert"`, invalid fields get `aria-invalid` and point to it, focus moves to the first one, `field()` links every hint, and labels say "(required)". ACCEPTED: one summary line rather than one error element per field, because each message names its field | browser |
| A10 | LOW | 3.3.1: the history range error isn't linked to the inputs | FIXED. Both inputs have `aria-describedby="h-error"` and `aria-invalid`, and an invalid range focuses `#h-from` | browser |
| A11 | LOW | 1.4.1: one legend swatch covers three severities | FIXED. There are now three severity swatches | fixture: overview |
| A12 | LOW | 2.4.7: rows and sections reached by an anchor have a weak or missing focus indicator | FIXED. `tr[tabindex=-1]:focus` and `.page-section:focus` get an outline | browser |
| A13 | LOW | 2.4.3: Close on the period panel focuses the `h1` | FIXED. It links to `#timeline` | browser |
| A14 | LOW | SVG links are named twice, and `ACCESSIBILITY.md` is inaccurate | FIXED. SVG links are named by `<title>` only, and `docs/ACCESSIBILITY.md` is rewritten for v2 | code review |

## 3. Security (`security-reviewer`: 1 MEDIUM, 5 LOW; all 8 required checks pass)

| # | Sev | Finding | Disposition | Evidence |
|---|---|---|---|---|
| S1 | MED | DNS rebinding reaches the write proxy | FIXED. A Host outside `ALLOWED_HOSTS` gets 421, and a write whose `Origin` is not allowed gets 403 | curl: `Host: evil.test` → 421; `Origin: http://evil.test` POST → 403 |
| S2 | LOW | A malformed `Content-Length` or a bad path crashes the handler | FIXED. A bad or negative length gets 400, over 16 KB gets 413 (both close the connection), and a `ValueError` from `urlopen` gets 400 | curl / nc |
| S3 | LOW | No CSP or anti-framing headers | FIXED on `serve.py`: CSP with the sha256 of the inline script, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. ACCEPTED on GitHub Pages: no `<meta>` CSP, because its hash would have to be kept in step with the inline script by hand, and every data path is already text-only | browser: no CSP violations and no JS errors |
| S4 | LOW | `h()` would accept a string `on*` or an unsafe `href`/`src` | FIXED. String `on*` values are dropped, and `UNSAFE_URL` (`javascript:`, `data:`, `vbscript:`) is refused in `dom.js` and in chart `el()` | code review |
| S5 | LOW | The `/health` prefix match is loose | FIXED. `/health` and `/ready` must match exactly, and other proxied paths must start with `/api/` | curl: `/healthz` → 404 |
| S6 | LOW | The exported transcript under `public/js` would be served and published | ACCEPTED as out of scope: it is the user's file. It is not committed, and the user has been asked to move it out of `public/` | `git status` |

## 4. Analytical honesty (`mle-reviewer`: 3 MEDIUM, 10 LOW; all 9 checks pass)

| # | Sev | Finding | Disposition | Evidence |
|---|---|---|---|---|
| M1 | MED | Negative controls have no Variant column and statuses are cut short | FIXED. There is a Variant column and the full served status is shown | fixture: validation |
| M2 | MED | Only O₂ is called "not preferred", which implies the primary is preferred | FIXED. The served `variant_preference` ("Neither variant is preferred until the plant explains…") is shown on the validation verdicts, the O₂ card and the L07 advisory | fixture: overview, validation |
| M3 | MED | The snapshot ships test annotations | FIXED. `export_snapshot.py` leaves out `TEST_ACTORS` (`e2e.journey`, `poc.analyst`). The re-export has 0 events and `events-audit.json` is `{}`; the analytical JSON is unchanged | `public/snapshot/events.json` |
| M4 | LOW | Hosted mode rebuilds gaps and cites "Phase 9 · gaps_in_page"; a gap on a page boundary would be missed | ACCEPTED. Hosted mode uses the same published 10-minute rule on the same served rows. No gap sits on a 5,000-row boundary today (41 gaps both locally and hosted) | E2E journey (d) |
| M5 | LOW | A single-point segment draws nothing | FIXED. It is drawn as `circle.point` | code review |
| M6 | LOW | The validation footnote hard-codes the score version | FIXED. It is read from `/metadata` `artifact_versions.risk_scores` | fixture: validation |
| M7 | LOW | The copy hard-codes "12", the date span, "Twelve", "Two" and "Five" | ACCEPTED. Each is correct for the frozen Phase 6–9 artifacts, and those phases can't change. The hero copy was reworded where it could drift | test: honesty |
| M8 | LOW | Garbled like-for-like sentence | FIXED | fixture: validation |
| M9 | LOW | "each mixed" if the F3 classes differ | FIXED. There is an explicit `MIXED` case | code review |
| M10 | LOW | The dot plot says crossing zero means "no difference", yet dots are Weak | FIXED. `MSG.weakCaveat` is appended to the description | fixture: validation |
| M11 | LOW | The WEAK gloss claims an effect size | FIXED. It now uses the Phase 8 wording: "Passed only a looser test; not enough to count as supported" | test: honesty |
| M12 | LOW | F13 "0.40 vs 0.43" and NC5 "lead metrics" sit at the edge of what Phase 8 withholds | ACCEPTED. They are served Phase 8 evidence text, shown as served, and they aren't coverage figures for the score | — |
| M13 | LOW | The ground-truth card hard-codes `NOT_AVAILABLE` | FIXED. It shows the served `ground_truth_status`, or "—" | fixture: events |

## 5. Wording against Phase 8 §26 and the Narrowing list (`cs-product-analyst`: 6 HIGH, 11 MEDIUM, 9 LOW)

| # | Sev | Finding | Disposition | Evidence |
|---|---|---|---|---|
| W1 | HIGH | "not a prediction / alarm system" | FIXED. It now reads "does not anticipate plant events" and "does not raise warnings or alarms". ACCEPTED: the served Phase 9 risk-score text ("It is not a prediction…"), because it is a denial and Phase 9 is frozen | test: honesty; fixture: methodology |
| W2 | HIGH | Garbled like-for-like sentence and a raw field name | FIXED | fixture: validation |
| W3 | HIGH | Weak at 2–6 h reads as a lead time | FIXED. `MSG.weakCaveat` (Phase 8 F2, F18) | fixture: validation |
| W4 | HIGH | Test annotations in the hosted copy | FIXED (see M3). With no active rows, the table caption is "Withdrawn annotations — kept in the audit trail" | fixture: events |
| W5 | HIGH | The read-only reason is never checked | FIXED. A source test requires every write action to go through `roButton`/`writeLink`, and `events.js` to render the reason. Headless Chrome on a `github.io` hostname lists every write control as `aria-disabled` with "Read-only hosted copy — annotate on the local service", and no submit button is enabled | test: honesty; `node tests/e2e/capture.mjs hosted` |
| W6 | HIGH | "None of the rules is a live flag" / "warning-rule" | FIXED. The F3 group copy no longer says "live" or "warning-rule". ACCEPTED: the served methodology line "Nothing here is a live warning", because it is a denial in frozen Phase 9 text | test: honesty |
| W7 | MED | Blocked cards read like a switched-off capability | FIXED. Blocked cards show "Cannot be tested until plant event records exist" | fixture: events, validation |
| W8 | MED | The WEAK gloss claims an effect size | FIXED (see M11) | — |
| W9 | MED | The events hero overstates and hard-codes a count | FIXED. It is reworded without a count | fixture: events |
| W10 | MED | The validation hero omits "neither variant is preferred" | FIXED | fixture: validation |
| W11 | MED | "the true start is earlier" stated as fact | FIXED. `MSG.cappedOnset` ("may have started earlier") | fixture: periods |
| W12 | MED | Raw enums leak | FIXED. Period facts, the events footnote and methodology bands use `enumText`/`PLAIN`. ACCEPTED: enums inside served advisory sentences (for example "INSUFFICIENT_DATA"), which are Phase 9 text; the O₂ advisory carries a plain sub-line | fixture: periods, methodology |
| W13 | MED | Limitation topics are mangled | FIXED. `PLAIN.limitationTopic` for L01–L13 | fixture: quality |
| W14 | MED | "censored" / "look-back cap" jargon | FIXED. "Many period start times are capped", plus `MSG.cappedMeaning`; the Validation section is titled "Capped start times — Phase 8 censored onsets" | fixture: overview, validation |
| W15 | MED | Developer instructions in the error messages | FIXED. `MSG.unavailable` and `MSG.mismatch` are reworded for plant staff | code review |
| W16 | MED | "Unblocks: F14…; circularity" | FIXED: the label now reads "Needed to review:". ACCEPTED: the F-codes and "circularity" come from served Phase 9 data-requirement text | fixture: overview |
| W17 | MED | Copy outside `copy.js`; disclaimer and banner duplicated | FIXED: a test requires the static shell to carry the `copy.js` `DISCLAIMER`, `BRAND` and `READ_ONLY.banner` text, so the two can't drift. ACCEPTED: some page-local labels stay in page modules; moving them doesn't change what the user reads | test: honesty |
| W18 | LOW | Inconsistent terms ("plant-labelled events", three meanings of "primary") | FIXED: "Operating context", "1 h window (main test)", "plant annotations" in `STEP_TEXT` and the cards. ACCEPTED: "plant-labelled events" inside served Phase 9 threshold text | fixture |
| W19 | LOW | The periods hero wording | FIXED. It uses "at or above the 90th percentile of its reference period… not plant events" | fixture: periods |
| W20 | LOW | "rows are never filled in" | FIXED. The quality hero is reworded | fixture: quality |
| W21 | LOW | "Medium confidence (capped)" and the MASKED_UPSTREAM gloss | FIXED | test: honesty |
| W22 | LOW | "2 · 52 missing…" numbers run together | FIXED. The meaning carries no numbers | fixture: overview |
| W23 | LOW | Bands and gaps are both described as "hatched" | FIXED on Overview and History ("outlined, diagonal-hatched" bands vs "light grey hatching with no outline") | fixture: overview, history |
| W24 | LOW | "labelled events are needed to revalidate" | FIXED. It reads "plant annotations are needed before Phase 8 can be re-run" | fixture: overview |
| W25 | LOW | The events calendar shows a score gap legend and a Score table | FIXED. A chart with no score series omits both; its marks list is the data equivalent | fixture: events |
| W26 | LOW | Unclear form labels; "To (end excluded)" | FIXED. There are hints for Plant confirmation, Time basis and Entry kind, and the history field reads "To (up to, not including)" | fixture: events-new, history |

## 6. Python (`python-reviewer`, `serve.py`: 4 MEDIUM, 3 LOW, 2 OK)

| # | Sev | Finding | Disposition | Evidence |
|---|---|---|---|---|
| P1 | MED | `\d` matches Unicode digits, unlike the JS router | FIXED. `re.ASCII` on `DEEP` | code review |
| P2 | — | Route patterns mirror `route.js` | OK | — |
| P3 | — | No traversal introduced | OK | — |
| P4 | MED | A malformed or negative `Content-Length` | FIXED (see S2) | curl |
| P5 | MED | The 413 leaves an unread body on a keep-alive connection | FIXED. `close_connection = True` on 400 and 413 | nc |
| P6 | LOW | `/health` prefix match | FIXED (see S5) | curl |
| P7 | LOW | A NUL byte in the path makes `resolve()` raise | FIXED. `_safe_file` catches `(ValueError, OSError)` | curl |
| P8 | LOW | `log_message` raises `IndexError` on a single argument | FIXED. Guard `len(args) < 2` | code review |

## 7. Ponytail audit

| # | Finding | Disposition |
|---|---|---|
| T1 | Unused exports: `GAP_SECONDS` (`series.js`), `logClientError` (`api.js`), `stepItem` (`common.js`), `clear`/`text` (`dom.js`), `setQuery` (`app.js`) | FIXED. All removed |
| T2 | The dead `loadSeries(range)` branch | FIXED. Removed |
| T3 | Two capture tools: a Playwright-MCP snippet for fixtures and ad-hoc screenshot steps | FIXED. One script, `tests/e2e/capture.mjs` (`shots`, `rendered`, `hosted`), runs headless Chrome over CDP with no dependency |
| T4 | No second server, chart library, npm, score formula in JS, new database or Phase 9 edit | OK |
