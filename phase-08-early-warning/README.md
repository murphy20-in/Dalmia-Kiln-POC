# Phase 8: Early Warning Validation

Status: COMPLETE (awaiting review)

Objective: test, as a falsification exercise, whether the frozen Phase 7 risk score (`p7-risk-1.1.0`) is elevated
**before** the onsets of the 12 Phase 6 `EMPIRICAL_ABNORMAL_PERIODS`, relative to ordinary running. There is no plant
event ground truth, so deposit / ring / failure early warning is BLOCKED; nothing here validates it.

Run:

```bash
cd scripts
../../.venv/bin/python run_phase8.py --clean                         # ~70 s; writes outputs/, reports/, cache/
../../.venv/bin/python -B -m unittest discover -s ../tests -t ../tests
```

Inputs (read-only): Phase 7 `outputs/` (`risk_scores.parquet` with `operational == True`, components, confidence,
reasons, frozen references) and cache; Phase 7 `risk_core` / `reference_builder` code; Phase 6
`abnormal_episodes.parquet`. No workbook is reloaded.

Outputs: `outputs/early_warning_*.{csv,parquet}` (event, horizon, control, negative-control, O₂, load, trajectories,
summary, data quality, episodes, validation gates), `reports/PHASE_8_EARLY_WARNING_VALIDATION_REPORT.{md,html}`.

Docs: `docs/EARLY_WARNING_VALIDATION_SPEC.md` (pre-declared contract), `VALIDATION_PROTOCOL.md`,
`LEAKAGE_CONTRACT.md`, `METRIC_DEFINITIONS.md`, `LIMITATIONS.md`. Reviews: `reviews/REVIEW_LOG.md`.

Results and finding classes: report §1 and §3 (generated from the outputs).
