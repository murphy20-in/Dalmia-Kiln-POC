# Phase 8 — Leakage Contract

Grid timestamps are bucket ENDS: bucket `t` covers (t − 10 min, t]. A value "at t" may use buckets ≤ t only.

## Rules

1. **Causality.** Every warning signal (reference rank, 60-min slope, acceleration, 7-day rolling rank, W1–W5,
   window statistics, lead metrics) at bucket t uses buckets ≤ t (`warning_metrics.py`, trailing windows only).
2. **T0 boundary.** Pre-onset windows are (T0 − h, T0]. Nothing after T0 enters an event metric.
3. **No post-event features.** Phase 6 period END times are used only to keep controls away from periods and for the
   backward diagnostic NC3 (a validation test, never a feature). No Phase 6 post-event field is read.
4. **Thresholds** come from the Apr–May reference population (before every evaluation window), from earlier months'
   ordinary running (month holdout), or leave-one-event-out (diagnostic only). None uses the evaluated period.
5. **`afr_context` is never used live.** It holds RETROSPECTIVE Phase 5 labels. It is not in the column allow-list
   (`p8common.SCORE_COLUMNS`), the Phase 7 AFR weight is 0, and the score does not change when AFR events are removed
   or shifted.
6. **Frozen Phase 7.** The score, references, bands and weights are not modified; the stored score is reproduced by
   rescoring (max |diff| ≤ 1e-6) and the frozen files are byte-identical before and after the run.
7. **Operational only.** Only `operational == True` rows carry a score; `risk_score_diagnostics.parquet` is not an
   operational input.
8. **No interpolation.** Windows with too few operational buckets are INSUFFICIENT_DATA / NOT_EVALUABLE; windows that
   touch a Phase 1 long-gap / frozen window are excluded (events and controls alike).

## Automated tests

| ID | Requirement | Where |
|---|---|---|
| L1 | no score at t depends on t + 1 or later | gate G2 (grid truncated at 3 event onsets; Phase 8 signals with randomised future), `tests/test_temporal_leakage.py` |
| L2 | no warning metric uses post-T0 values | NC5 (every period, both variants), `tests/test_temporal_leakage.py` |
| L3 | no calibration uses the target period | gate G5 (reference / month-holdout chronology) |
| L4 | no threshold selected using the evaluation event | gate G5, `tests/test_temporal_leakage.py` |
| L5 | future-period modifications do not change past metrics | gate G2 (every grid column after the cut randomised), `tests/test_temporal_leakage.py` |
| L6 | Phase 7 frozen references unchanged | gate G1 (hashes before / after, rescore, reference quantiles) |
| L7 | `afr_context` not used live | gate G2, `tests/test_temporal_leakage.py` |
