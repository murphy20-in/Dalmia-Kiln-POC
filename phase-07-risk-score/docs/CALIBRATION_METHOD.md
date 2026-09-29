# Phase 7 Calibration Method

Numbers are produced by the pipeline (`outputs/risk_score_bands.csv`, `risk_score_calibration.csv`, `risk_score_reference.json`) and quoted in the report. This document fixes the **method**, declared before the bands were computed.

## 1. What is calibrated — and what cannot be

With no event ground truth, the score **cannot** be calibrated to a probability of any plant condition.

Two things *can* be calibrated:
1. the **position** of a value within the frozen reference distribution;
2. the **empirical burden** of each band out of sample.

The published bands are therefore **reference-relative resemblance bands**. They are not risk probabilities and not plant limits.

## 2. Reference population

- **Buckets.** RUNNING buckets with `2025-04-01 00:00 < t ≤ 2025-05-31 23:59`, at least 3 usable families, and the current bucket valid.
- **Same window as Phase 3.** It is the Phase 3 training window, so the reference is **in-sample for Phase 3**: Phase 3 fitted tag curves and dimension scales on the same buckets.
- **Consequence.** The edges are optimistic. No truly held-out calibration window exists before June.

## 3. Family anchors

- `m_d` = reference median of `S̃_d`; `q_d` = reference P90 of `S̃_d`.
- **Floor.** `q_d ≥ m_d + 0.25` (component units) is applied only if the reference is degenerate, and is flagged as `degenerate` in the reference JSON.
- **No distributional assumption.** Quantiles are used and no mean / sd is computed. The saturating transform `a = 1 − 2^(−e)` bounds heavy tails without a hard cap at the training maximum.

## 4. Band edges and support rule

1. **Candidate edges** are the reference P75, P90 and P95 of `risk_score`. P99 was not proposed: with about 20 independent 3-day blocks it cannot be estimated stably.
2. **Uncertainty.** Each edge gets a 95 % percentile CI from a **3-day block bootstrap**: 400 replicates, seed 20250601, with multinomial block weights from Phase 4 `boot_weights`. Blocks preserve the strong within-day autocorrelation.
3. **Support rule.** Walk the edges upwards and keep an edge only if its CI lies entirely above the CI of the last kept edge. Otherwise its band is merged into the band below, and `merged_into` is recorded.

   This is a deliberately conservative **heuristic**, not a formal test that two edges differ (quantiles are ordered by definition). A paired bootstrap of the edge difference would be a sharper alternative.
4. **Insufficiency.** Fewer than 1,000 reference values or fewer than 10 blocks gives `CALIBRATION_INSUFFICIENT` → `risk_band = UNBANDED`, with score and confidence still published.

## 5. Stability checks per edge

| Check | What it measures | Where |
|---|---|---|
| Block-bootstrap CI | Sampling uncertainty of the edge | `risk_score_bands.csv` `ci95_*` |
| April-fit / May-check | Anchors, `H_ref90` and edges refitted on April only, then May exceedance compared with nominal. Pass tolerance is ±0.05 absolute (fixed, so it can fail). This is within-reference stability, **not** held-out validation | `april_fit_edge`, `april_fit_may_exceedance` |
| Reference-window variants | Apr-only, May-only, Apr08–May31, Apr01–May24 | `risk_score_robustness.csv` |
| Out-of-sample exceedance | Share of Jun–Aug operational time at or above each edge | `oos_exceedance_jun_aug` |

## 6. Empirical alert burden (no false-positive rate)

- **`EMPIRICAL_ALERT_RATE`:** the share of operational time in each band, by month (Jun / Jul / Aug) and by tentative load band.
- **Uncertainty.** Each monthly share ≥ HIGH has a 3-day block-bootstrap CI (8–11 blocks per month). There is also the range obtained by moving the HIGH edge across its own CI, and the August − June difference with its block CI.
  - Month-to-month steps are **not** separable.
  - Only August > June is claimed.
- **Load standardisation.** Each month's per-load-band share, weighted by the pooled Jun–Aug load mix, plus a steady-load-only share.
- **Sustained-exceedance episodes (hysteresis).** An episode opens at ≥ HIGH, stays open while ≥ ELEVATED, and closes at the first bucket below ELEVATED or the first non-operational bucket (never bridging stops or gaps). These are descriptive burden counts, not alarms.
- **Episode statistics:** count, rate per 100 running hours, median and mean duration, and the share starting < 6 h after a restart (stop / transition contamination).
- **Contamination:** the share with mean data-quality confidence < 0.75 (DQ contamination), and the mean load-associated share.

## 7. Coverage of the Phase 6 periods

- **Label.** This is `EMPIRICAL_ABNORMAL_PERIOD_COVERAGE`, never detection accuracy.
- **Measures:** score during each period, in the 2 h before onset, and outside the periods; rank separation (Mann-Whitney AUC) with a 3-day block-bootstrap CI; minutes from onset to the first HIGH bucket.
- **Nulls:** circular shift (≥ 7 days) and randomised same-length placements.
  - These are **consistency checks**, expected to pass by construction.
  - p = 0.005 is the floor for 200 draws.
- **Baselines reported alongside coverage:** the Phase 3 KPI the periods were defined from (the circularity ceiling), the magnitude component alone, and the abnormal-family count.
- **Severity.** The relationship with Phase 6 severity is reported as context: Spearman, class medians and monotonicity.
- **Not used for selection.** Coverage was **not** used to choose the architecture, weights or edges. The periods come from the same components, so good coverage is expected by construction.

## 8. What a band means

| Band | Meaning |
|---|---|
| `LOW` | below the reference P75: within the usual Apr–May range |
| `ELEVATED` | reference P75 … P90: less common than 3 in 4 reference buckets |
| `HIGH` | ≥ reference P90 (plus P95 if it had been supported): as unusual as the top 10 % of the reference |

None of these is an operating, alarm or safety limit, and none implies an action.
