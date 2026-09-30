# Browser journeys (v2)

Run on 2026-09-30 with Playwright (MCP, headless Chromium, 1440×900 unless stated) against `http://127.0.0.1:8010`, with Phase 9 on port 8009. Journey screenshots are in `screenshots/e2e/`; those full-page captures repeat the sticky header partway down, which is a capture artifact. The handoff screenshots in `screenshots/after/` were taken with `node tests/e2e/capture.mjs shots` (headless Chrome, with the viewport set to each page's height), so they don't have it.

| Journey | Steps | Result | Screenshots |
|---|---|---|---|
| (a) Overview → band → trend → overlay → back | Overview trend strip → click the P6-025 band → `/abnormal-periods/P6-025` detail opens → "View on trend" → `/history?from=…&to=…&period=P6-025` with the range pre-set and the period highlighted → O₂ overlay on (`overlay=o2_excluded`, labelled "Sensitivity analysis — not preferred") → back → reload | Pass. The URL state survives reload and back/forward. First run found that the imported `history` page module shadowed `window.history`, so `go()` threw; renamed to `historyPage` and re-run clean | `j-a1.png`, `j-a2.png`, `j-a3.png`, `j-a3-chart.png` |
| (a, keyboard only) | Tab to the band → Enter → detail panel with focus on its heading → Tab to "View on trend" → Enter → Space toggles the overlay | Pass. The band shows a 3 px navy focus stroke. Alt+Left is a browser-chrome shortcut that headless Chromium ignores, so that step used `history.back()` | — |
| (b) Annotate → diamond → audit → withdraw | Period detail → "Annotate this period" → `/events/new?start=…&end=…&ref=P6-031` pre-filled with `annotator_viewed_risk_score=true` → submit as `e2e.journey` → diamond appears on the history chart → `/events/<id>` detail and audit trail → edit → withdraw (confirm dialog) | Pass. Audit shows Create → Update → Delete. The stale-version PATCH was refused with 409, and the form reloaded at the new version and kept the other editor's change. Two withdrawn test records (`e2e.journey`) are left in the local event store; the active count is still 0 | `j-b1.png`, `j-b2.png` |
| (c) Insight → evidence anchor | Overview insight "See evidence" → `/validation#F…` and `/data-quality#L0…`; also verdict "Why not supported?" → `#censoring`, matrix cell → `#<dataset>-<yyyy-mm>`, "Copy request" → toast | Pass. The anchor scrolls to and focuses the row. The clipboard holds plain text | `j-c1.png`, `j-c2.png` |
| (d) GitHub Pages snapshot mode | `public/` served on port 8011 with the real `murphy20-in.github.io/Dalmia-Kiln-POC/` URL routed to it, so the hostname check runs against the real domain. Hash deep links, `404.html` fallback, every write action | Pass. The read-only banner shows, write buttons are disabled with the text "Read-only hosted copy — annotate on the local service", and writes return 405. The single 404 is the Pages fallback itself. Re-run after the step 9 fixes with `node tests/e2e/capture.mjs hosted`: every write control on Overview, Annotations and the form is `aria-disabled` and described by that reason, and no submit button is enabled | `j-d1.png`, `j-d2.png` |
| (e) 375 px mobile, and 720 px (200 % zoom of 1440) | Every page checked for `scrollWidth > clientWidth` | Pass after one fix. Validation overflowed by 113 px at 375 px because of long unbreakable tokens in finding cards; fixed with `overflow-wrap: anywhere` | `screenshots/after/mobile-*.png` |

Rendered page text is saved in `tests/fixtures/rendered/*.txt` by `node tests/e2e/capture.mjs rendered`, and was re-captured after the step 9 fixes. The honesty test scans it.

## Lighthouse (G7) and timings (G8)

| Page | Accessibility | Best practices | SEO |
|---|---|---|---|
| Overview, History (range + overlay), Abnormal periods (P6-025), Annotation form, Validation, Data quality, Methodology | 100 | 100 | 100 |

The first Lighthouse pass showed layout shift of about 0.73 on every page, caused by the script-inserted stylesheet. The body is now hidden until the stylesheet loads or fails, which brought Overview to 0.071. The same pass fixed a Label-in-Name issue (WCAG 2.5.3) on the timeline row links.

Timings on the local service: Overview KPIs in about 350 ms and the trend strip in about 410 ms (gate: interactive under 1.5 s). The full-range history chart renders in 28–69 ms (gate: under 300 ms). The console showed no errors apart from the deliberate stale PATCH in journey (b).
