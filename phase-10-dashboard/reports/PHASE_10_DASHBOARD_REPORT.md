# Phase 10 — Multi-page analytical dashboard

## 1. Executive summary

A seven-page retrospective dashboard for the Ariyalur kiln POC, served beside the frozen Phase 9 API. It draws historical scores, KPI-derived periods, plant annotations, the Phase 8 `NOT_SUPPORTED` result, and data-quality metadata. It does not compute a score and it does not add alerting.

## 2. Dashboard objective

Give an analyst the Phase 9 evidence in one place: what the POC measured, what Phase 8 did not support, and a way to record plant events for a later validation. It is not a live monitor.

## 3. Stack decision

Plain HTML, CSS, and ES modules. `serve.py` is a stdlib HTTP server. It serves `public/` and proxies `/api`, `/health`, and `/ready` to Phase 9. Phase 9’s route table was not changed, so a second analytical service was not added and CORS was not opened.

Charts are inline SVG. The repository had no chart library, and the series, gaps, and overlays did not need one.

## 4. Dalmia design reference

Colour and tone follow the public Dalmia Cement site: deep green `#003a1e`, green `#006838`, charcoal, and a thin orange header stripe. No logo file, markup, or script was copied. Green on the score line means the primary series, not a safe state.

## 5. Information architecture

Persistent header, disclaimer, and nav. Pages: Overview, Historical Risk, Abnormal Periods, Plant Events, Validation, Data Quality, Methodology.

## 6. Page inventory

| Path | Role |
|---|---|
| `/` | Evidence counts and the negative validation status |
| `/history` | Score trend, gaps, optional O₂ overlay, optional period and event marks |
| `/abnormal-periods` | The 12 KPI-derived periods and one trajectory |
| `/events` | Plant annotation list, create, edit, soft delete, audit |
| `/validation` | Phase 8 primary endpoint and the O₂ sensitivity block |
| `/data-quality` | Coverage, limitations, open plant questions |
| `/methodology` | Phase chain and the analytical boundary |

## 7. API integration

See `docs/API_INTEGRATION.md`. Windows use API `start`, `end`, `limit`, and `offset`. The raw historian extract is not downloaded.

## 8. Analytical semantics

See `docs/UX_SEMANTICS.md` and `reviews/ANALYTICAL_REVIEW.md`. `preferred` stays false. Periods stay KPI-derived. Bands are not painted. Horizon tables, coverage figures, and AUC are not shown. F16’s API title includes “Lead time”; the class is BLOCKED and no lead-time number is shown.

## 9. Event annotation workflow

Actor (attribution only), type, times, equipment, source, description, and the optional Phase 9 fields. PATCH and DELETE send `expected_version`. HTTP 409 tells the user the row changed and reloads it.

## 10. Accessibility

See `docs/ACCESSIBILITY.md`. Charts have a description, a legend, a table, and a keyboard slider.

## 11. Security

See `reviews/SECURITY_REVIEW.md`. A script payload in a description was stored and shown as text.

## 12. Browser / E2E testing

See `reviews/E2E_LOG.md`. Nine node tests pass (`tests/*.mjs`), including a live Phase 9 contract check. Playwright is not installed; the journeys were run in the IDE browser.

## 13. Visual QA

Screenshots in `screenshots/`: overview, historical-risk, abnormal-periods, plant-events, validation, data-quality, methodology, mobile-overview, mobile-historical-risk. Desktop chart shows gaps as empty spans. Mobile page width does not overflow.

## 14. Performance

Default history window is 14 days, not the full 9,557-row series. “Operational window” loads the full operational series through the API in pages of 5,000. Drawing keeps at most about 900 real points.

## 15. Ponytail audit

See `reviews/PONYTAIL_AUDIT.md`. No critical or high finding open.

## 16. Known limitations

- No login. `X-Actor` is not authentication.
- Playwright and Lighthouse were not run.
- No screen-reader session.
- A long score window is thinned for drawing.
- F16’s finding title contains the words “Lead time”.
- The local event store has one soft-deleted test annotation from the browser review.
- Phase 9 remains single-threaded. A full operational window is a large JSON payload because the API returns full primary rows.

## 17. Phase 11 handoff

Running dashboard: `phase-10-dashboard/serve.py` with Phase 9 on port 8009. Tests: `node --test tests/*.mjs`. Browser notes: `reviews/E2E_LOG.md`. Screenshots, security notes, accessibility notes, and the Ponytail note are in this directory. Phase 11 should do broader QA. This phase does not add live monitoring, alerts, or a prediction.
