# Testing

`node --test tests/*.mjs` runs 20 tests. The contract test needs Phase 9 running on port 8009.

| File | What it checks |
|---|---|
| `tests/pure.test.mjs` (5) | Gaps stay gaps and a zero score stays a point; thinning keeps segment ends and invents nothing; timestamp rules; the event form, including PATCH sending `null` to clear a field; withheld figures are not passed through |
| `tests/honesty.test.mjs` (9) | Forbidden wording in client copy and in the rendered pages, allowing denials only; the static shell carries the `copy.js` disclaimer, wordmark and banner; write actions go through the read-only helpers, which show the reason; no client-side statistics; no alarm or brand-accent colour on data states; no HTML assignment of untrusted text; the O₂ overlay is off by default and never styled as primary |
| `tests/route.test.mjs` (5) | Click map (every in-app link resolves to a route and anchor); deep links, with unknown paths falling back to the overview; URL state round-trips in path and hash mode; enums shown in plain English; warning-rule findings collapse to one F3 row |
| `tests/contract.test.mjs` (1) | The live Phase 9 fields the dashboard reads are present |

## Browser capture

`node tests/e2e/capture.mjs <mode>` drives the system Google Chrome headless over CDP. It needs no npm package. The local service must be running on port 8010.

| Mode | Output |
|---|---|
| `shots` | Full-page desktop (1440) and mobile (375) screenshots of every page into `screenshots/after/`, plus the page-level horizontal overflow of each |
| `rendered` | Visible text of every page into `tests/fixtures/rendered/*.txt`, which the honesty test scans. Re-run this after any copy change |
| `hosted` | Maps `kiln.github.io` to a static server of `public/` on port 8011 (`python3 -m http.server 8011 -d public`), so snapshot mode runs, then prints each read-only control and its stated reason |

The journeys (a)–(e), Lighthouse and timings are recorded in `reviews/E2E_LOG.md`.
