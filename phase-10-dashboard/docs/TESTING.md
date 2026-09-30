# Testing

`node --test tests/*.mjs`

| File | What it checks |
|---|---|
| `tests/pure.test.mjs` | Gaps vs zero, decimation does not invent points, timestamp rules, event form, withheld evidence |
| `tests/semantics.test.mjs` | Forbidden words only on lines that deny the claim; CSS has no alarm band classes; no `innerHTML` assignment |
| `tests/contract.test.mjs` | Live Phase 9 fields: score, variant, provenance, interpretation, `gaps_in_page`, period `label_type`, validation `NOT_SUPPORTED`, event `label` origin via `provenance.source` |

Browser journeys (Cursor browser, desktop 1280 and the layout CSS at 720/900):

1. Overview loads disclaimer, `NOT_SUPPORTED`, `NOT_AVAILABLE`, 9,557 rows, 12 periods.
2. Historical risk draws the series, two gaps in the default 14-day window, `preferred = false`.
3. O₂ toggle adds `.series-sensitivity` and the sensitivity sentence.
4. Abnormal periods lists 12 ids and opens P6-020 with the KPI-derived disclaimer.
5. Plant event create with `<script>alert(1)</script><img…>` renders as text (one page script, zero images), edit saves, stale `expected_version` returns 409 and does not change the text, soft delete shows DELETED.
6. Validation shows `NOT_SUPPORTED` and the sensitivity label. No AUC or coverage figure in the page text. F16’s title is the Phase 8 finding name.
7. Data quality shows Kiln-I September, Kiln-IIIA April, and the O₂ question.
8. Methodology states the boundary in words.

Playwright is not installed. These journeys were run in the IDE browser and recorded in `reviews/E2E_LOG.md`.
