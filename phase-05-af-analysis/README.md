# Phase 5: Alternative Fuel (AFR) Analysis

**Status:** COMPLETE, awaiting review. The relationships are **AFR-associated, not AFR-caused**.

## Purpose

What measurable relationship, if any, exists between the supplied AFR signals and kiln process behaviour in April–August 2025?

The phase describes AFR availability, quality, operating range and firing patterns. It then measures, with association statistics only, how AFR co-varies with:
- load;
- combustion;
- thermal behaviour;
- the Phase 3 efficiency-deterioration KPI;
- the usable Phase 4 indicator.

> AFR firing is a control input set by the operator or controller. No fuel properties exist in the supplied data. Nothing here is a plant limit, a set-point or an operating recommendation. POC_EMPIRICAL_BANDs are descriptive. AFR TRANSITION EPISODES are empirical windows, not plant events.

Phase 5 builds **no** risk score, early warning, API or dashboard.

## Execution

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-05-af-analysis/scripts
../../.venv/bin/python run_phase5.py --clean      # ~4.5 min; run twice to verify determinism (G7)
../../.venv/bin/python -B -m unittest discover -s ../tests -v
```

## Data inputs (read-only; SHA-256 in `afr_version_manifest.csv`)

- **Source workbooks:** hashed before and after every run, never read directly.
- **`data/processed`:** `kiln_i`, `kiln_ia`, `kiln_ii`, `kiln_iiia` and `operating_state_timeline`, read through Phase 3 `load_dataset`.
- **Phase 1:** `process_tag_inventory`, `alternative_fuel_inventory`, `unit_consistency_review`, `dq_issue_register`.
- **Phase 2:** `column_holds`, `baseline_confidence`, `baseline_family_readiness`, `baseline_stability`, `baseline_reference_bands`.
- **Phase 3:**
  - `efficiency_deterioration_kpi.parquet`, `kpi_component_scores.parquet`, `kpi_reference.json`, `kpi_definition.json`, `kpi_validation.csv` (all PASS required);
  - `kpi_core`, `p3common` and `load_phase2_inputs`, imported read-only.
- **Phase 4:**
  - `leading_indicator_set.csv`: only `usable_downstream = True`, used per its `permitted_use`;
  - `indicator_feature_values.parquet`, `indicator_feature_reference.json`, `indicator_scores.csv`, `indicator_lag_analysis.csv`, `indicator_episodes.csv`, `indicator_data_quality.csv`, `indicator_validation.csv` (no FAIL required);
  - `indicator_core` and `p4common`, imported read-only.

## AFR signals

| Tag | Name | Unit | Status |
|---|---|---|---|
| `Kiln-I!K` | AFR \| Solid | TPH | **ANALYSED**. FUEL_CONTROL_INPUT; 100 % present, 19 % zero, integer-valued |
| `Kiln-I!L` | Liquid (AFR group) | LPH | **INSUFFICIENT_DATA** (`LIQUID_AFR_ANALYSIS = INSUFFICIENT_DATA`): 8.3 % present (1.7–22 % by month), bimodal, 9 values ≥ 9,999, Phase 2 SPARSE_COLUMN hold |
| `Kiln-I!H`, `Kiln-I!I` | Coal firing kiln / PC | TPH | Co-manipulated covariates and co-movement targets only, never outcomes |
| `Kiln-I!J`, `Kiln-I!M` | HAG / Diesel | TPH / LPH | Not analysed (mostly zero / near-constant) |
| CV, moisture, RDF, plastic, fuel mix, fuel % | — | — | **NOT_AVAILABLE**: no energy-based metric is computed |

- **Excluded targets:**
  - `Kiln-I!AA` (unit hold);
  - `Kiln-I!AE` (duplicate);
  - `Kiln-IA!F`, `CBS-Calculation!B` and `C` (constant columns);
  - `CBS-Calculation!D..G` (plant-calculated values, possibly computed from fuel rates).
- **Kiln-I!K:** reserved by Phase 4 and analysed here.

## Architecture

```text
data/processed --Phase 3 load_dataset--> minute frames --Phase 4 build_buckets--> RUNNING 10-min buckets (Phase 3 state)
AFR_P2 = Kiln-I!K (Phase 2 valid, negatives/frozen rows -> NaN, no flatline mask); AFR_P3MASKED / AFR_NOFLAT for sensitivity G
   -> bands (Apr-May P25/P75, frozen) -> transitions (START/STOP/RAMP) + feed-matched controls
   -> af_context engine: LAGGED_LEVEL / FUTURE_CHANGE / MOMENTUM x lags 0-360 min; partial Spearman + n_eff + 3-day block bootstrap
      + BH per family x type (Phase 4 ic.assoc); lag chosen on DISCOVERY; Jun-Jul replication; August holdout;
      circular-shift null; pre-declared evidence labels
   -> episode responses (paired vs controls, label permutation) -> matched ON/OFF -> sensitivity A-H -> confidence
```

| Script | Purpose |
|---|---|
| `af_core.py` | Paths, `P5Config`, labels; pure functions (value classes, bands, runs, transitions, eligibility, matching, shifts, evidence / confidence rules, wording scanner); safe read-only Phase 3/4 import |
| `af_context.py` | Analysis context, designs (features and controls using data ≤ t), relationship engine, negative control, band contrasts, episode responses |
| `load_phase5_inputs.py` | Upstream validation, input hashes, bucket / KPI / indicator cache |
| `build_afr_inventory.py` | `afr_inventory.csv`, `afr_data_requirements.csv` |
| `profile_afr_quality.py` | `afr_data_quality.csv` |
| `build_afr_operating_bands.py` | `afr_operating_bands.csv`, `afr_daily_summary.csv`, `afr_monthly_summary.csv` |
| `detect_afr_transitions.py` | `afr_transition_episodes.parquet` |
| `analyze_afr_{load,combustion,thermal,efficiency,leading_indicators}.py` | `afr_*_relationships.csv`. The thermal step adds the Sp.Heat derivation check; the efficiency step adds the Phase 4 KPI-episode precursors; the indicator step adds activation and attenuation |
| `matched_analysis.py` | `afr_matched_analysis.csv` |
| `sensitivity_analysis.py` | `afr_sensitivity_analysis.csv`; finalises `confidence` |
| `validate_af_analysis.py` | G1–G6 → `afr_validation.csv` |
| `generate_report.py` | Report, 4 figures, `afr_version_manifest.csv` |
| `run_phase5.py` | Orchestration (6 analysis steps in parallel), unit tests, G7 determinism, source / upstream snapshots |

## Major findings (evidence label, Apr–May / Jun–Jul / August)

1. **AFR tracks load (ASSOCIATED, MEDIUM).** Partial ρ of the AFR level with kiln feed: +0.35 / +0.34 / +0.50. AFR = 0 is mostly a kiln-stop state: 80 % of zero minutes fall in non-running time, and AFR is 0 in only 4.7 % of running minutes.
2. **AFR and PC coal are operated in opposite directions (ASSOCIATED, capped LOW: co-manipulation).** Level ρ −0.37 / −0.30 / −0.45; 1-h change ρ −0.23 / −0.31 / −0.41. PC coal is a median +6.0 TPH within 60 min after AFR stops, compared with controls.
3. **Preheater-outlet O₂ and NOx fall as AFR rises (ASSOCIATED, MEDIUM).** O₂ level ρ −0.16 / −0.44 / −0.19; NOx 1-h change ρ −0.20 / −0.14 / −0.11.
4. **Preheater, TAD, hood and clinker temperatures are lower after AFR stops and ramp-downs (ASSOCIATED episodes).** Examples: cyclone-3 −3.2 °C within 1 h of stops, TAD damper inlet −17 °C over 3 h after ramp-downs. These changes coincide with the PC-coal increase and feed cuts.
5. **Sp.Heat F / G co-vary with AFR (ρ +0.38 / +0.48; capped LOW).** Firing rates per ton of feed, including AFR, reproduce them with R² 0.92 (F) / 0.65 (G). This is consistent with Sp.Heat being calculated from the firing inputs, so the relationship may be largely arithmetic. The plant must confirm.
6. **No supported AFR–efficiency-KPI relationship beyond the fuel swap.**
   - The current-KPI association does not replicate (+0.32 → June +0.20, July −0.03).
   - The future-KPI change is NOT SUPPORTED.
   - There is no AFR precursor before the Phase 4 KPI episodes.
   - The KPI is +2.9 points after AFR stops.
7. **Phase 4 indicator (`Kiln-I!I|ROC_1H`).** Its activation rate is 56 percentage points higher in falling-AFR hours (Jun–Jul). Its KPI lead goes from ρ 0.056 to 0.039 with AFR controls. It is largely a coal-for-AFR swap signature.

## Evidence strength

- **Primary relationships:** 43 ASSOCIATED, 40 WEAK ASSOCIATION, 191 NOT SUPPORTED, 60 INSUFFICIENT DATA.
- **ASSOCIATED by kind:** 26 process-response, 8 co-manipulation, 9 Sp.Heat / KPI.
- **Confidence:** 21 MEDIUM (process / load rows only) and 22 LOW. **HIGH is never assigned.**
- **August holdout for the ASSOCIATED rows:** 27 CONFIRMED, 12 same direction but not significant, 4 opposite direction but not significant.
- **Validated relationships** (ASSOCIATED, MEDIUM, August CONFIRMED): AFR↔feed / bucket-elevator / clinker TPH level; AFR↔PH-outlet O₂ level and change; AFR↔NOx change; AFR↔cyclone-3 temperature change; TAD temperature after ramp-downs; cyclone-3 temperature after stops.
- **Unstable relationships:** 92 primary relationships have SIGN_FLIP across Apr–May / June / July. Examples: AFR↔current KPI, AFR↔burning-zone level, AFR↔CO (`Kiln-I!Y`) level, and AFR↔kiln speed level.
- **Matched analysis:** MATCHING_NOT_SUPPORTED everywhere. There are only 25 ON/OFF pairs (minimum 30) and 10 HIGH/LOW pairs, with speed imbalance.

## Limitations and missing data

- **Fuel properties.** No calorific value, moisture, ash, chlorine or composition: AFR mass ≠ AFR heat. No substitution rate or energy flow is computed.
- **Control inputs.** AFR, coal and PC are moved together, so their separate associations cannot be isolated. Coal / PC controls may act as mediators, which biases effects toward zero.
- **Tag semantics.** Whether `Kiln-I!K` is a set-point or a measurement is unknown. The Sp.Heat formula is unknown, and so is the reason AFR is changed.
- **Time drift.** AFR drifts down from April to August (HIGH_AFR is 22 % of discovery buckets and 0 % in August), so band contrasts are descriptive only.
- **Too few starts and ramp-ups.** Most AFR starts follow an interruption that began less than 2 h earlier, so only 12 AFR_START and 18 AFR_RAMP_UP episodes are eligible (129 eligible episodes in total).
- **Inherited from Phases 3–4:** the proxy operating state, the composite kiln-line assumption, the in-sample Apr–May KPI, no event ground truth, and no Kiln-I September data.
- **Prioritised plant data:** `outputs/afr_data_requirements.csv`. Priority 1 is the Sp.Heat formula, AFR set-point documentation, the AFR operating log, calorific value and moisture. The plant questions are in report §22a.

## Validation, review and reproducibility

- **Validation.** The last clean run has 61 rows: **56 PASS, 5 INFO, 0 FAIL**, across G1 source integrity, G2 schema, G3 temporal, G4 data quality, G5 statistics, G6 robustness and G7 reproducibility.
- **Checks worth noting:**
  - a leakage perturbation test, and an independent re-derivation of every lag choice and evidence label;
  - BH checked against scipy;
  - a null calibration;
  - misaligned-AFR and circular-shift negative controls;
  - the confidence cap re-derived from the flags.
- **Reproducibility (G7).** Two consecutive `--clean` runs gave byte-identical key outputs and reports (17/17 files). The source (60 files) and all Phase 1–4 files and directories were unchanged. 17 unit tests pass.
- **Reviews.** planner → product analyst, python-reviewer and mle-reviewer (PASS-WITH-CONDITIONS). All findings are resolved; see `reviews/REVIEW_LOG.md`.

## Phase 6 handoff

- **Phase 6-relevant outputs:**
  - `afr_transition_episodes.parquet` and `afr_*_relationships.csv`: use `evidence`, `confidence` and `confidence_cap_reason` exactly;
  - `afr_operating_bands.csv`;
  - `afr_daily_summary.csv`;
  - `afr_data_quality.csv`;
  - `afr_data_requirements.csv`.
- **AFR as context.** AFR stops and ramp-downs, with the simultaneous PC-coal increase and frequent feed cuts, should be checked as **context** whenever Phase 6 examines an abnormal period. They coincide with falling preheater / TAD temperatures and small KPI rises.
- **Two distinct concepts.** Keep *AFR-associated process behaviour* (Phase 5) separate from *historical abnormal events* (Phase 6). No AFR transition episode is an abnormal event, and no Phase 5 relationship is a deposit, ring or coating predictor.

**Phase 6 has NOT been started.**
