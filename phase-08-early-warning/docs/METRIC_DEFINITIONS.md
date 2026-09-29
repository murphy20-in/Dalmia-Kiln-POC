# Phase 8 — Metric Definitions

| Metric | Definition |
|---|---|
| `rank_ref(t)` | share of the frozen Apr–May in-sample reference scores ≤ risk_score(t) (right-continuous ECDF) |
| `rank_roll(t)` | mid-rank of risk_score(t) among finite scores in (t − 7 d, t − 24 h]; needs ≥ 144 values |
| window statistic W̄_h(A) | median of rank over (A − h, A] with ≥ ⌈2/3·n⌉ finite buckets |
| rank excess (per period) | W̄_h(T0) − median W̄_h over eligible month-matched controls |
| PE | median rank excess over evaluable periods (rank units, −1 … 1) |
| control percentile | mid-rank of W̄_h(T0) within its month's control distribution |
| Cliff's δ | mean over periods of (2 · control percentile − 1) = P(control < event) − P(control > event) |
| NC2 p | (1 + #{null PE ≥ observed}) / (1 + N_NULL), null = PE with each period replaced by a random control of its month |
| bootstrap CI | 2.5 / 97.5 % of PE with periods resampled i.i.d. and control medians from 12-h calendar-block resampling |
| BH q | Benjamini–Hochberg across the 8 horizons (per variant) |
| slope | OLS slope of the score over [t − 60 min, t] (7 buckets, ≥ 5 finite), points per hour |
| acceleration | slope(t) − slope(t − 60 min) |
| `EMPIRICAL_ABNORMAL_PERIOD_COVERAGE` | share of evaluable periods with the warning in (T0 − h, T0]; not accuracy |
| control-window warning rate | share of eligible ordinary-running windows (A − h, A] containing the warning |
| coverage binomial p | one-sided binomial test of covered periods against the control-window rate (Bonferroni over 5 warnings) |
| `EMPIRICAL_ALERT_RATE` | share of ordinary-running time flagged, and warning episodes per 100 running hours; not an error rate |
| warning episode | flagged buckets merged across ≤ 20 min of operational non-warning time |
| first-warning lead | T0 − earliest warning bucket in (T0 − 24 h, T0] |
| sustained lead | T0 − start of the warning episode in force at T0 (ends ≥ T0 − 20 min) |
| peak lead | T0 − bucket of the maximum score in the look-back |
| trend-onset lead | T0 − start of the final run of positive slope ending at T0 |
| warning duration | warning minutes in the look-back (persistence) |
| pre-onset rank change | rank_ref(T0) − rank_ref(T0 − 6 h) |
| load-adjusted rank | rank minus the median rank of ordinary-running buckets in the same load stratum (load_band × load_context) |

## Status vocabularies

- **Findings:** SUPPORTED, WEAK, NOT_SUPPORTED, INSUFFICIENT_DATA, BLOCKED (rules: spec §4 and `run_phase8.findings`).
- **Event data quality:** VALID, VALID_REDUCED_CONFIDENCE, NOT_EVALUABLE, INSUFFICIENT_DATA, TRANSITION_CONTAMINATED,
  DATA_QUALITY_CONTAMINATED (spec §12). Evaluable = VALID + VALID_REDUCED_CONFIDENCE.
- **Load verdict:** ROBUST_TO_LOAD, ATTENUATED, NOT_ROBUST, NOT_APPLICABLE, INSUFFICIENT_DATA.
- **O₂:** ROBUST_TO_O2 (class unchanged) / SENSITIVE_TO_O2; analyser statements are
  `ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION`.
- **Negative controls:** DEGRADES_TO_NULL (|null median| ≤ 0.05) + OBSERVED_EXCEEDS_NULL / OBSERVED_NOT_DISTINGUISHABLE_FROM_NULL;
  NC5 PASS_IDENTICAL; NC3 is a DIAGNOSTIC; NC4 is `REPORTED_SINGLE_DRAW: WITHIN_NULL_TOL / OUTSIDE_NULL_TOL`
  (one mirrored-position relocation, not a null distribution).
- **Circularity:** `CIRCULAR_BY_CONSTRUCTION` marks the detection-anchored analysis.

## Terminology

There is no event ground truth, so Phase 8 never reports detector error rates or their complements. It uses
empirical abnormal-period coverage, control-window warning rate, empirical alert rate and retrospective
discrimination only.
