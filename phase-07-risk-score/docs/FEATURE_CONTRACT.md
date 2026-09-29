# Phase 7 Feature & Output Contract (Phase 8 handoff)

**Score version:** `p7-risk-1.1.0`
**Reference:** Apr–May 2025 RUNNING buckets, frozen. The exact string is in `risk_score_reference.json → reference_version`.
**Grain:** 10-minute buckets, right-closed, labelled by the END: `timestamp` = `t` covers `(t − 10 min, t]`. The grid equals the Phase 3 KPI grid (2025-04-01 00:10 … 2025-10-01 00:00).

Phase 8 must not reverse-engineer Phase 7. Everything it needs is below and in `RISK_SCORE_SPEC.md`.

---

## 1. Which rows are operational

```
operational == True      # (the column) = reference_state starts OUT_OF_SAMPLE AND risk_status starts VALID
```

Only operational rows carry `risk_score`, a real `risk_band`, the component columns and `historical_similarity`.
- The 18 `OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE` rows are operational.
- In-sample reference rows show `risk_band = IN_SAMPLE_REFERENCE`. Their scores are only in `risk_score_diagnostics.parquet`.
- Confidence on a non-VALID RUNNING row describes the data, not a score.

The other rows are kept on purpose:
- in-sample reference buckets (calibration only);
- stopped / transition / not-scorable / insufficient-data buckets;
- September (Kiln-I missing, so never scored).

**Never** fill, interpolate or forward-fill a missing `risk_score`.

## 2. `risk_scores.parquet` (one row per bucket)

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | datetime64 | bucket end |
| `risk_score` | float, 0–100, NaN unless `risk_status` VALID* | empirical POC risk score (spec §4) |
| `risk_band` | str | `LOW` / `ELEVATED` / `HIGH` (supported bands, see `risk_score_bands.csv`), `UNBANDED` if calibration is insufficient, `NOT_SCORED` otherwise |
| `confidence_score` | float, 0–1, NaN if not RUNNING | mean of the six confidence parts (spec §6) |
| `confidence_band` | str | `MEDIUM` / `LOW` (HIGH is capped to MEDIUM) |
| `confidence_band_uncapped`, `confidence_cap_reason` | str | the band before the cap, and why it was capped |
| `risk_status` | str | `VALID`, `VALID_REDUCED_CONFIDENCE`, `INSUFFICIENT_DATA`, `NOT_SCORABLE`, `TRANSITION_CONTEXT`, `STOPPED` |
| `reference_state` | str | `IN_SAMPLE_REFERENCE`, `OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE`, `OUT_OF_SAMPLE` |
| `operating_state`, `operating_state_label` | str | Phase 3 causal POC state proxy (UNCONFIRMED) |
| `load_band` | str | `TENTATIVE_LOW/MID/HIGH` by reference feed P33 / P67, `UNKNOWN` |
| `load_context` | str | `LOAD_ASSOCIATED` (1-h feed change ≥ reference P90, or outside the training load range), `STEADY_LOAD`, `UNKNOWN` |
| `feed_tph` | float | Kiln-I feed (context) |
| `kpi_value`, `kpi_band` | float, str | Phase 3 KPI. Context only, never scored (it aggregates the same families) |
| `family_count_abnormal` | int | families with `S̃ > reference P90` |
| `family_count_usable` | int | families with a valid `S̃` (0–5) |
| `persistence_minutes` | int | current run of consecutive buckets with `H ≥ H_ref90` |
| `historical_similarity` | float, 0–1 | diagnostic only: similarity to the Apr–May calibration-only signatures. Not scored |
| `magnitude_component`, `concurrence_component`, `persistence_component` | float (points) | the three score components; they sum to `risk_score` |
| `operational` | bool | the only filter Phase 8 needs |
| `data_quality_status` | str | `GOOD` / `DEGRADED` / `POOR` from `conf_data_quality`, or `NOT_APPLICABLE` |
| `primary_reason`, `secondary_reasons` | str | spec §8. Secondary reasons are `;`-separated |
| `contributing_families` | str | abnormal families, `;`-separated, or `NONE` |
| `afr_context` | str | Phase 5 AFR transitions in `(t − 3 h, t]` (RETROSPECTIVE_LABEL; context only) |
| `phase4_context` | str | Phase 4 indicator activation in the trailing 2 h (LOW confidence; context only) |
| `reference_version`, `score_version`, `score_label` | str | provenance and the mandatory interpretation label |

## 3. Other outputs

| File | Schema / content |
|---|---|
| `risk_score_components.parquet` | `timestamp, family (5 families + CONCURRENCE + PERSISTENCE), raw_measure (S̃, n_abnormal, or persistence count), reference_measure (q_d, 1, or 18), normalized_deviation (e_d), family_score (a_d, C or P), family_weight, family_contribution (points), usable, quality_flag, reason_code`. The contributions sum per bucket to `risk_score` |
| `risk_score_reasons.parquet` | `timestamp, reason_code, reason_type (SCORE_DRIVER / CONTEXT / CONFIDENCE), contribution_points (0 for context and confidence), driver_rank` |
| `risk_score_confidence.parquet` | `timestamp, confidence_score, confidence_band(_uncapped), confidence_cap_reason, conf_data_quality, conf_family_coverage, conf_baseline, conf_operating_state, conf_temporal, conf_robustness, causal_invalid_share, dq_window_after, o2_ambient_suspect, risk_status` |
| `risk_score_diagnostics.parquet` | **NON-OPERATIONAL.** `timestamp, reference_state, risk_status, risk_score_in_sample_reference, risk_band_in_sample_reference, risk_score_diagnostic (RUNNING, ≥ 3 usable families), historical_similarity_diagnostic, diagnostic_label` |
| `risk_score_variant_references.json` | Frozen references of the six confidence-robustness variants, with the same `input_hashes` / `code_sha256` / `score_version` as the primary. `common.load_refs` refuses mismatches |
| `risk_score_reference.json` | Frozen anchors `m` / `q` per family, `H_ref90`, bands (edges, CIs, candidates, support / merge), load quantiles, signatures, the family Spearman matrix, reference score quantiles, the full config and its key, and upstream input hashes |
| `risk_score_bands.csv` | One row per band: lower edge, reference quantile, 95 % CI, supported / merged, population, date range, reference version, April-fit / May-check exceedance, Jun–Aug exceedance, rationale |
| `risk_score_feature_inventory.csv` | Provenance of every feature (`permitted_use`, `leakage_status`) |
| `risk_score_calibration.csv` | Contents:<br>• EMPIRICAL_ALERT_RATE by month and load band, with 3-day block CIs, HIGH-edge-CI ranges and the Aug − Jun difference CI<br>• LOAD_STANDARDISED_ALERT_RATE<br>• SUSTAINED_EXCEEDANCE_EPISODES (hysteresis)<br>• EMPIRICAL_ABNORMAL_PERIOD_COVERAGE, with the Phase 3 KPI / magnitude / family-count baselines<br>• severity relationship (Spearman with CIs; n = 12, inconclusive) |
| `risk_score_event_similarity.csv` | Per Phase 6 period (12 final + 10 in-sample calibration-only): score during and before onset, max band, onset-to-first-HIGH, family point shares, and the Phase 6 context columns |
| `risk_score_robustness.csv` | Variants (`spearman`, `band_agreement`, top-decile / HIGH Jaccard, median diff, coverage, monthly HIGH shares, family-share correlation, `result`), candidates, negative controls, inclusion tests |
| `risk_score_data_quality.csv` | Status by month, confidence by DQ status, invalid-value buckets, DQ windows, September, missing-family injection |
| `risk_score_validation.csv` | Gates G1–G9 (`gate, check, check_type, result, evidence`) |
| `risk_score_summary.csv` | Median / P75 / P90, band shares, confidence shares, status counts and point shares, by month, load band and load context |

## 4. Feature provenance rules

- **Scoring inputs.** The only inputs of `risk_score` are the five Phase 3 family components, via `S_d → a_d → H, C, P`. Each has a `SCORING` / `CAUSAL` inventory row, and a feature without provenance cannot enter (G2).
- **Confidence inputs** are causal bucket-time fields. The one static exception, Phase 2 tag confidence, is disclosed.
- **Context** covers AFR, the Phase 4 indicator, the KPI, load and similarity. These never add points; the AFR / Phase 4 inclusion tests excluded both.
- **Evaluation only:** the Phase 6 final periods, and Phase 6 severity / confidence.
- **FORBIDDEN:** every Phase 6 post-event field.

## 5. Allowed downstream use

- Ranking and trending of resemblance to reference-relative abnormal process conditions.
- Prompts to check plant records.
- Early-warning evaluation in Phase 8 against the same frozen reference, reported as empirical rates.

**Guards for Phase 8 (from the review):**
- `HIGH` is **not** a rare-event flag. It is at or above the Apr–May P90, and it covers about half of August.
- Band levels depend on the reference window and are not stationary out of sample. Prefer `risk_score` ranks and trends.
- A large part of the June → August rise depends on the kiln-inlet O₂ analyser's ambient-like readings (DQ-1). Repeat key results with the `EXCLUDE_KILN_INLET_O2_ANALYSER` variant, and wait for plant confirmation of the analyser behaviour.
- Do not use `afr_context` in live evaluation: its labels are retrospective.
- Treat `confidence_band == LOW` as the informative state. MEDIUM is the cap and means no known problem, not positive evidence.

## 6. Prohibited interpretation

- Deposit, ring, coating or failure detection or probability.
- Plant operating, alarm or safety limits.
- Set-point or control recommendations.
- Treating the Phase 6 periods as confirmed events.
- Treating band levels as independent of the reference window.
- Treating AFR or the Phase 4 indicator as causal.

## 7. How to rescore (e.g. Phase 8)

```python
import common, risk_core
refs = common.load_refs()                    # frozen primary + confidence-variant references
ctx = common.load_context()                  # grid, episodes (allowed fields), AFR events, DQ windows, Phase 4 threshold
frame, core = risk_core.score_frame(ctx["grid"], refs, ctx)
```

`score_frame` is leakage-tested: it is identical under truncation at any cut point, under future-data randomisation and under post-event perturbation (G3). Never refit the reference on the period being scored.
