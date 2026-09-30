# Limitations

The machine-readable list lives in `config/analytical_contract.json` and is served by
`GET /api/v1/metadata/limitations`, together with live counts of operational-row data quality (POOR rows, suspect-O₂
rows, confidence bands). None of these is hidden.

## Analytical and data limitations (L01–L13)

| ID | Topic | Status | Summary |
|---|---|---|---|
| L01 | Event ground truth | OPEN | No coating / ring / deposit / cleaning / maintenance / stoppage records exist, so nothing can be validated against plant events |
| L02 | Kiln-I September 2025 | OPEN | Truncated workbook; the score ends 2025-08-23 00:40 and September is not scored (not imputed) |
| L03 | Kiln-IIIA April 2025 | OPEN | The April file repeats May; April is absent for that dataset |
| L04 | Frozen window | MASKED UPSTREAM | 122 tags frozen on 2025-05-06 11:50–21:50 |
| L05 | Sentinel values | MASKED UPSTREAM | 99999, −273 °C and "Error 6" are masked, not repaired |
| L06 | Unit-review holds | OPEN | 13 columns held pending plant unit confirmation; excluded from the score |
| L07 | O₂ analyser `Kiln-I!X` | OPEN | Ambient-air-like readings; excluding the analyser roughly halves the Jun–Aug rise and turns Phase 8 NOT_SUPPORTED into WEAK |
| L08 | Load dependence | OPEN | The score is higher at low feed and during load changes; Phase 8 load adjustment INSUFFICIENT_DATA |
| L09 | Operating-state proxy | OPEN | RUNNING / STOPPED comes from Kiln MD and feed; its meaning and the equipment identity are unconfirmed |
| L10 | Reference dependence | OPEN | Band levels and abnormal-period membership depend on the Apr–May reference |
| L11 | Censored onsets | OPEN | 6 of 12 Phase 6 onsets are censored; the small positive pre-onset estimate comes from them |
| L12 | Timezone | OPEN | The historian has no timezone; the API serves naive timestamps unchanged and requires naive plant-local annotations |
| L13 | HIGH band not rare | INFO | HIGH covers about half of August operational time; it is not an alarm level |

## Service limitations (Phase 9)

- **No authentication.** `X-Actor` records who made a change but does not prove it. The default bind is `127.0.0.1`. Any shared deployment needs an authenticating reverse proxy first. This is deliberately out of POC scope.
- **Single-threaded stdlib server.** `wsgiref` serves one request at a time. That is enough for an analyst tool. For concurrent users, run the same WSGI `App` under a production WSGI server; no code change is needed.
- **Large score pages.** A full primary risk-score row carries confidence parts, reasons and per-family components (about 2.7 KB each). Trend views should use `/risk-scores/variant-comparison` (timestamp plus both scores) and fetch full rows only for a selected window.
- **O₂-excluded series is a Phase 9 materialisation (declared exception).** Phase 8 persisted the variant only inside its 12 event windows. Phase 9 ran Phase 8's unchanged `o2_excluded_score` once, offline. That is a refit of the variant's Apr–May reference and a rescore, which is exactly what Phase 8 does on every run. The build refuses to write the file unless it reproduces every persisted Phase 8 value (1,501), the full-series rank correlation and the June / July / August medians exactly. The variant's reference quantiles were never persisted upstream, so they cannot be checked. No Phase 7 or Phase 8 file was changed, and the API never recomputes.
- **In-memory artifacts.** About 9.6k operational rows are loaded once at startup (a few seconds). Files are hashed, then parsed (a narrow check-then-read window, accepted because the artifacts are frozen and the service is local). A changed artifact is detected at startup, not while running: restart after any rebuild.
- **Re-run order.** If Phase 7 is re-run, Phase 8 must be re-run before Phase 9: the build refuses Phase 6/7 files that differ from Phase 8's validated inputs. After any upstream re-run: `run_phase9.py --clean` (twice), then restart the service. Until then the API answers 503, by design.
- **The evaluable-event count is always 0.** Phase 9 records plant annotations but never judges whether they are evaluable. Only a re-run of the frozen Phase 8 protocol can do that.
