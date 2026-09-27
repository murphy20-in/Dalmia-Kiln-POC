# Phase 4: Leading Indicators

**Status:** COMPLETE, awaiting review. Indicator status: **weak / tentative**.

## Purpose

Phase 4 identifies process signals whose causal features change *before* the Phase 3 POC Efficiency-Deterioration KPI increases, beyond what the KPI's own level, trend and already-known persistence predict. It separates leading, lagging, unstable, load/state-proxy and data-quality-limited associations.

> These are empirical leading indicators of the Phase 3 efficiency-deterioration KPI. They are not validated predictors of deposits, rings, coating, equipment failure, or other plant events. They are for discussion and review only; no operating action, alarm or limit is implied.

Phase 4 builds **no** dashboard, API, risk score or early-warning system.

## Result (last clean run)

- **Screening.** 137 candidate tags plus 3 load-context tags, 7 causal features each and 10 lags (10 min to 12 h): 9,800 discovery tests. 54 of them pass BH q ≤ 0.10 with autocorrelation-adjusted inference, from 22 indicators.
- **Selected set: 1 external indicator, `Kiln-I!I|ROC_1H`** (Kiln-I · Coal Firing | PC, 1-h rate of change):
  - A **rising** PC coal firing trend tends to come before a KPI increase over the next 60 min.
  - Replication partial ρ is 0.056 [0.003, 0.101]. Neither replication month is individually significant. Shift-null p = 0.034.
  - **August holdout: same sign, not significant.**
  - Precision lift is 1.16 (holdout 0.89), and episode lift is negative.
  - Confidence **LOW**. It is a manipulated variable, so the lead most plausibly reflects operator response.
- **KPI-component precursors (circular; never in the set):**
  - Burning-zone temperature trend (`Kiln-I!AF|ROC_3H`)
  - Sp.Heat F trend (`Kiln-I!F|ROC_1H`)
  - Cyclone-4 material temperature trend (`Kiln-II!G|ROC_1H`)
- **Load proxies.** 12 discovery-supported signals lose their lead once feed level and feed changes are controlled: cooler fans, CBS gas flow, kiln feed, and Sp.Heat level/deviation.
- **Unstable.** 5 signals do not replicate or do not beat the shift null, including the kiln drive power and current trends.
- **Lagging.** 1 signal lags the KPI.
- **Practical finding.** Very few process signals lead this KPI, and only weakly. The KPI's own momentum is far more informative: raw ρ ≈ 0.47 at 60 min.

## Architecture

```text
data/processed (10 datasets) --load_dataset (P3)--> minute frames --prepare_minutes + causal_state (P3 kpi_core)
   --> RUNNING 10-min buckets --frozen discovery references--> 7 causal features per tag (indicator_core)
Phase 3 KPI parquet --> K(t); future-only target dK(t,H); controls K(t), momentum, Kpend (data <= t)
   --> partial Spearman + n_eff + 3-day-block bootstrap + BH (DISCOVERY)  -> lag + sign per indicator
   --> REPLICATION Jun-Jul: gates a-f, criteria c1-c9, score, set          -> AUGUST HOLDOUT: reported once
```

| Script | Purpose | Main outputs |
|---|---|---|
| `p4common.py` | Paths, `P4Config` (every analytical choice), labels, and the safe read-only Phase 3 import (no bytecode, appended path) | — |
| `indicator_core.py` | **Pure functions:** buckets, trailing windows, features, targets, controls, `assoc` (partial ρ, n_eff, bootstrap), BH, episodes, alarms | — |
| `analysis_context.py` | KPI grid, windows (DISCOVERY / JUN / JUL / AUG / REPL / OOS), row filters, discovery lag choice, thresholds | — |
| `load_phase3_inputs.py` | Requires Phase 3 validation to be all PASS; hashes inputs; builds the KPI grid | `cache/kpi_grid.parquet` |
| `build_indicator_dataset.py` | Minute cache, state, buckets, candidate rules C1–C8, tiers, flags, data quality | `indicator_candidate_inventory.csv`, `indicator_excluded_candidates.csv`, `indicator_data_quality.csv` |
| `build_causal_features.py` | Frozen references and features | `indicator_feature_reference.json`, `indicator_feature_values.parquet` |
| `calculate_lag_relationships.py` | 58,800 association tests (6 windows × 10 lags × 980 features), run in parallel | `indicator_lag_analysis.csv` |
| `build_indicator_episodes.py` | Independent KPI deterioration episodes (anchored at the start of the rise) and matched controls | `indicator_episodes.csv`, `indicator_episode_analysis.parquet` |
| `evaluate_lead_time.py` | Discovery lead time, post-hoc lag descriptives, false-lead analysis | `indicator_lead_time.csv` |
| `sensitivity_analysis.py` | Groups A–H on the replication months | `indicator_sensitivity.csv` |
| `score_indicators.py` | Gates, criteria, class, confidence, shift null, complementary set, downstream contract | `indicator_scores.csv`, `leading_indicator_set.csv` |
| `validate_indicators.py` | G1–G6, including the truncation leakage test and null calibration | `indicator_validation.csv`, `indicator_benchmarks.csv` |
| `generate_report.py` | Report, 5 figures, version manifest | `reports/PHASE_4_LEADING_INDICATORS.{md,html}`, `indicator_version_manifest.csv` |
| `run_phase4.py` | Orchestration, unit tests, G7 determinism, source and upstream snapshots | appends G7 rows |

## Execution

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-04-leading-indicators/scripts
../../.venv/bin/python run_phase4.py --clean      # ~6.5 min; run twice to verify determinism
../../.venv/bin/python -B -m unittest discover -s ../tests -v
```

## Inputs (read-only; hashed in `indicator_version_manifest.csv`)

- **Phase 3:**
  - `efficiency_deterioration_kpi.parquet`, `kpi_component_scores.parquet`, `kpi_reference.json`, `kpi_reference_bands.csv`, `kpi_definition.json`, `kpi_candidate_inventory.csv`, `kpi_validation.csv`, `kpi_version_manifest.csv`
  - `kpi_core.py` / `p3common.py` / `load_phase2_inputs.load_dataset` (imported, never modified)
- **Phase 2:** `column_holds.csv`, `baseline_confidence.csv`, `baseline_family_readiness.csv`, `baseline_stability.csv`
- **Phase 1:** `cross_dataset_identical_signals.csv`, `unit_consistency_review.csv`, `process_tag_inventory.csv`
- **data/processed:** 10 dataset parquets and `operating_state_timeline.parquet`

## Outputs

These are all in `outputs/`:

- `indicator_candidate_inventory.csv` and `indicator_excluded_candidates.csv`
- `indicator_lag_analysis.csv`
- `indicator_lead_time.csv`
- `indicator_scores.csv` and `leading_indicator_set.csv`
- `indicator_episode_analysis.parquet` and `indicator_episodes.csv`
- `indicator_feature_values.parquet` and `indicator_feature_reference.json`
- `indicator_sensitivity.csv`
- `indicator_validation.csv` and `indicator_benchmarks.csv`
- `indicator_data_quality.csv`
- `indicator_version_manifest.csv`

## Indicator methodology (short)

- **Features.**
  - All features at t use buckets ≤ t: LEVEL_1H, DEV_1H (feed-adjusted), ROC_1H and ROC_3H, VOL_2H, PERSIST_HI/LO_6H.
  - References are fitted on the Phase 3 training population (Apr–May) and frozen.
- **Target.** ΔK(t, H) = median K over (t+H−30 min, t+H] − K(t), for RUNNING horizons only.
- **Statistic.**
  - Partial Spearman controlling for K(t), 1-h momentum and Kpend.
  - n_eff (Bartlett / Pyper–Peterman) with a Fisher-z p-value.
  - 3-day-block bootstrap CI.
  - BH over all discovery tests.
- **Temporal design.** Discovery chooses lag and sign. Jun–Jul replication drives all gates, the score and the set. The August holdout is reported once.
- **Gates.**
  - a: discovery support
  - b: Jun–Jul replication (pooled CI and both months with the same sign)
  - c: survives feed controls
  - d: forward ≥ backward association
  - e: evaluable in both months
  - f: beats the circular-shift null
  - KPI inputs and proxies are component precursors, never in the set.
- **Score.** Mean of 9 pre-declared criteria in [0, 1], equal weights, fixed denominator. Leave-one-criterion-out rank stability ranges from 0.89 to 1.00.
- **Confidence.** HIGH / MEDIUM / LOW / INSUFFICIENT (NOT_APPLICABLE for load context), measuring evidence quality, with caps for KPI inputs and manipulated variables.

## Limitations

- **No event ground truth.** Episodes are synthetic KPI windows.
- **Inherited from Phase 3:** the KPI is mostly process-deviation-led, and the discovery KPI is compressed (in-sample).
- **Small sample.** Effects are small, with 12 replication episodes and 3 holdout episodes, and the replication estimates carry winner's-curse bias.
- **Operator response.** The selected indicator is a manipulated variable.
- **Fragile set.** The set is a single FUEL-family indicator: removing the FUEL family leaves it empty, so the family-removal Jaccard of 1.0 compares two empty sets.
- **Scope.** Results apply only to RUNNING horizons.
- **Plant confirmations pending:** the one-kiln assumption, the state proxy and Sp.Heat F/G.

## Validation, review and reproducibility

- **Validation.** The last clean run has 72 rows: **61 PASS, 0 FAIL**, 7 INFO and 4 NOT_MET_REPORTED. The NOT_MET_REPORTED rows are robustness rules reported, not hidden:
  - The alternative-reference and band-occupancy variants for the set member.
  - F-vs-G ranking Spearman of 0.67 overall and 0.75 without KPI inputs, below the pre-declared 0.8.
- **Leakage test.** Exact at 9 cut points (all 980 features, state and buckets re-derived). Controls and alarms are also causal.
- **Null calibration.** 6.6 % of shifted nulls have p < 0.05, with 0 BH discoveries. AR(1) nulls give ≤ 4/60 false positives, against 22–29/60 without n_eff.
- **Reproducibility (G7).** Two consecutive `--clean` runs gave byte-identical outputs on all 14 key files. Phase 1–3, `data/` and the source are unchanged.
- **Reviews.** Planner, python-reviewer, mle-reviewer (PASS-WITH-CONDITIONS; conditions resolved) and product analyst, plus a confirmatory re-review. See `reviews/REVIEW_LOG.md`.

## Known unresolved plant questions

1. Are the Kiln-I … IIIB folders one kiln line?
2. What does `Kiln MD` mean?
3. Which Sp.Heat definition, F or G, is authoritative?
4. Is PC coal firing adjusted manually or by a controller, and in response to what?
5. What drives kiln drive power at constant feed?
6. Can event logs (coating/ring observations, cleaning, stoppage reasons) be supplied?
7. Can Kiln-I September and Kiln-IIIA April be re-exported?
8. What do negative bypass-gas-flow values mean?
9. Which tags are set-points and which are measurements?

## Phase 5 handoff

**Phase 5 (Alternative Fuel Analysis) may consume:**

- `leading_indicator_set.csv`. Use only rows with `usable_downstream = True` as leading features, and follow each row's `permitted_use`.
- `indicator_feature_values.parquet` and `indicator_feature_reference.json`.
- `indicator_scores.csv`: use its load-proxy classes to avoid attributing load effects to fuel.
- `indicator_lag_analysis.csv`
- `indicator_episodes.csv`
- `indicator_data_quality.csv`

**Rules for Phase 5:**

- Fuel firing tags are set-points. In Phase 5 they are candidate explanatory variables, not outcomes.
- AFR (`Kiln-I!K`) was reserved and not analysed.
- Episodes are not events, and thresholds are not limits.

**Phase 5 has not been started.**
