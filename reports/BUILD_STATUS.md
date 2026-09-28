# Dalmia Kiln POC — Build Status

**As of:** 2026-09-28
**Branch:** `phase-05-af-analysis`, created from `phase-04-leading-indicators` (Phase 1 `b39d374`, Phase 2 `6e54477`, Phase 3 `a57c1b8`, Phase 4 `8325450`; Phase 5 not yet committed)
**Current state:** Phases 1–5 are COMPLETE and awaiting review. Phase 6 has not started.

This file is a handoff: it gives the next phase everything it needs in one place without re-reading the whole Phase 1 report.

---

## 1. Phase progress

| # | Phase | Status |
|---|---|---|
| 1 | Data Discovery | **COMPLETE, awaiting review** |
| 2 | Normal Operating Baseline | **COMPLETE, awaiting review — baseline PARTIAL** |
| 3 | Efficiency Deterioration KPI | **COMPLETE, awaiting review — KPI PARTIAL** |
| 4 | Leading Indicators | **COMPLETE, awaiting review — indicators weak / tentative** |
| 5 | Alternative Fuel Analysis | **COMPLETE, awaiting review — AFR-associated only (no fuel properties)** |
| 6 | Historical Abnormal Events | NOT STARTED |
| 7 | Deposit/Inefficiency Risk Score | NOT STARTED |
| 8 | Early Warning Validation | NOT STARTED |
| 9–12 | API, Dashboard, QA, Final Report | NOT STARTED |

Phase 1 completion checklist (all items verified): full recursive inventory, all workbooks and sheets inspected, column/tag inventory, timestamp structure, date coverage, sampling intervals, missingness, gaps, duplicates, outliers, flatlines, units, process families, equipment coverage, event and AF/RDF availability, readiness assessment, scripts created and rerun from a clean state, master report generated, no source data modified.

---

## 2. What was built

### Source data (read-only, never copied)
`/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)`: 60 monthly `.xlsx` process-log workbooks (277 MB), 10 equipment folders, April–September 2025.

### Phase 1 pipeline — `phase-01-data-discovery/scripts/`
| Script | Purpose |
|---|---|
| `run_phase1.py` | Orchestrates everything. `--clean` rebuilds from scratch (~7 min). Hashes the source before and after, then runs 48 validation checks |
| `common.py`, `taxonomy.py` | Read-only parsing, header detection, POC heuristics, classification rules |
| `inventory_files.py`, `inventory_workbooks.py` | Files, hashes, ZIP diagnostics, sheets, header structure |
| `profile_timestamps.py`, `detect_gaps.py` | Frequency, gaps, duplicates, overlaps |
| `profile_columns.py`, `profile_quality.py` | Tag inventory, datatypes, statistics, completeness, invalid-value candidates |
| `detect_outliers.py`, `detect_flatlines.py` | Data-quality outlier and flatline scans |
| `build_inventories.py` | Units, process families, equipment matrix, events, AF/RDF, cross-dataset alignment |
| `generate_report.py` | Issue register, readiness table, MD/HTML report |
| `export_data_manifest.py` | Writes `data/raw/source_manifest.csv` and `data/raw/dataset_registry.csv` |

Last clean run: **48/48 validation checks PASS, source unchanged** (SHA-256, size, mtime).

### Artifacts
| Location | Content | In git? |
|---|---|---|
| `phase-01-data-discovery/reports/PHASE_1_DATA_DISCOVERY_REPORT.md` / `.html` | Master Phase 1 report (14 sections + validation appendix) | No (gitignored; regenerate) |
| `phase-01-data-discovery/outputs/*.csv` | 32 CSVs, including `process_tag_inventory`, `column_inventory`, `dq_issue_register`, `phase1_data_readiness`, `gap_events`, `flatline_periods` | No (gitignored; regenerate) |
| `data/raw/source_manifest.csv` | Per-file path, month coverage, header layout, SHA-256, `status` USE/EXCLUDE | Yes |
| `data/raw/dataset_registry.csv` | Per-equipment availability and coverage | Yes |
| `data/{raw,processed,curated}/README.md` | Data-layer contract; `processed/` and `curated/` are empty until Phase 2 | Yes |

---

## 3. Key data facts (from Phase 1)

- **Structure:** one process-log sheet per workbook. Header is 2–4 rows (optional title, group, parameter, unit); group labels are not merged. The timestamp is text `dd.mm.yyyy HH:MM` in unlabelled column A, with no timezone. There are no formulas.
- **Volume:** 2,575,476 data rows (2,526,700 unique dataset-minutes) and 203 parameter columns across 10 datasets.
- **Frequency:** observed 1 minute in all files. Exception: CBS-II is hourly from 1 to 10 June 2025.
- **Coverage:** 2025-04-01 → 2025-09-30. **Kiln-I has no September** (truncated workbook). **Kiln-IIIA has no April** (its April file repeats May).
- **Where the kiln tags are:** Kiln-I holds all fuel (coal kiln/PC/HAG, diesel), AFR, O₂/CO/NOx, kiln feed, kiln drive, preheater fan, burning-zone and Sp.Heat tags. The other folders hold hood/TAD/PC, cyclones 1–5, cooler fans 1–10, cooler vent/ESP/clinker TPH/Sp.Heat, CBS, and cooler drive tags.
- **Equipment identity (unconfirmed):** the folders Kiln-IA…IIIB are titled `KILN PAGE-1A…3B`, and `Kiln MD` is identical across all datasets. They are likely display pages of **one kiln system**, not separate kilns.
- **AF/RDF:** only `AFR | Solid` (TPH, Apr–Aug) and `Liquid` (LPH, 92% empty). RDF split, plastic fraction, calorific value, moisture and fuel mix are **NOT FOUND**.
- **Events:** **EVENT GROUND TRUTH NOT FOUND IN SUPPLIED DATA** (no coating, ring, deposit, cleaning, shutdown or maintenance records).
- **Also not found:** kiln shell temperature, measured CO₂, clinker quality, explicit specific fuel consumption, and a labelled ID fan.

### Data-quality issue register (32 issues: 1 CRITICAL, 4 HIGH, 16 MEDIUM, 8 LOW, 3 INFO)
Critical / high:
1. No event ground truth, so detection, risk score and early warning cannot be validated.
2. Kiln-I (Sep) workbook truncated and unreadable.
3. Kiln-IIIA (April) file contains May data; April is absent.
4. Parameters named in the problem statement are absent (CV, moisture, RDF split, clinker quality, shell temperature).
5. Folder names vs content: probably one kiln system (needs plant confirmation).

Notable medium issues:
- Frozen window across 122 tags on **2025-05-06 11:50–21:50**.
- Sentinel `99999` in 35 columns, `-273` °C, and text `Error 6`.
- 9 label/unit mismatches.
- Out-of-range `%` values.
- 4,135 duplicate-timestamp rows.
- Gaps: Kiln-I 10–12 May (48 h) and 11 Jun (9 h); Kiln-IIIA 14–15 Aug (17 h).
- Identical columns Kiln-I AB/AE (CO).
- 15 columns RED on completeness.
- Missingness concentrated where column B `Kiln MD` = 0.

### Data readiness (data only, nothing attempted)
| Objective | Readiness |
|---|---|
| Normal baseline | PARTIAL |
| Efficiency KPI | PARTIAL |
| Leading indicators | PARTIAL |
| AF vs kiln behaviour | PARTIAL |
| Historical abnormal periods | PARTIAL |
| Risk score | PARTIAL |
| Early warning | BLOCKED |

---

## 4. Open questions for the plant (should be answered before or during Phase 2)

1. Are the Kiln-I / IA / II / III / IIIA / IIIB folders pages of **one** kiln line?
2. What does column B `Kiln MD` (hrs, values 0 / 0.02) mean? Does 0 mean the kiln is stopped?
3. What does `99999` / `9999` mean (bad quality / not configured)?
4. Can the plant supply a re-export of **Kiln-I September 2025** and **Kiln-IIIA April 2025**?
5. Can the plant supply event logs (coating/ring observations, stoppages with reasons, cleaning, maintenance)?
6. Can the plant supply fuel lab data (AF/RDF calorific value, moisture, ash/chlorine, RDF/plastic split) and clinker quality?
7. What is the historian timezone and export interpolation setting? 12–16% of rows repeat the previous row exactly.
8. Can the plant confirm the columns flagged UNIT CONSISTENCY REVIEW REQUIRED (`outputs/unit_consistency_review.csv`)?

---

## 5. Inputs available to Phase 2

Phase 2 should take these from `phase-01-data-discovery/outputs/` and `data/raw/`:

- `data/raw/source_manifest.csv`: which files to load (`status == USE`), header rows and data start row per file, SHA-256 to verify the source.
- `process_tag_inventory.csv`: tag list with `original_name`, unit, family, confidence, completeness and health class.
- `gap_events.csv`, `duplicate_records.csv`, `flatline_periods.csv`: windows to mask and duplicates to resolve.
- `data_quality_report.csv`, `outlier_profile.csv`: sentinel and invalid-value candidates.
- `unit_consistency_review.csv`: columns to hold back until confirmed.
- `dq_issue_register.csv`, `phase1_data_readiness.csv`: constraints.

Rules carried forward:
- Source is read-only.
- Keep `original_name` alongside any normalised name.
- Flag masked values rather than deleting them, and do not interpolate across gaps or missing months.
- No unit conversions without documented approval.
- No control or setpoint recommendations.
- Treat POC heuristics as heuristics, not plant limits.

---

## 6. How to reproduce

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-01-data-discovery/scripts
python3 run_phase1.py --clean     # regenerates outputs/, reports/, data/raw manifests; exits non-zero on any validation failure
```

Requirements: Python 3, pandas, numpy, openpyxl, markdown-it-py, and `pdftotext` (poppler).

---


---

## 7. Phase 2 — Normal Operating Baseline (COMPLETE, awaiting review)

**Baseline status: PARTIAL.** A traceable empirical baseline exists for every family with data. It is conditional on an unconfirmed operating-state proxy and the equipment mapping. It is **not** a set of plant limits and makes no claim about equipment health.

### What was built
- **Pipeline:** `phase-02-baseline/scripts/`. 14 scripts, run with `../../.venv/bin/python run_phase2.py --clean` (~9 min). The project `.venv` (created with `uv`) has pyarrow and matplotlib; `requirements.txt` was updated.
- **`data/processed/`:** 10 long-format Parquet files (50,823,996 source cells, one row per source cell) with masks, operating state, load band and baseline status, plus `operating_state_timeline.parquet` and `regime_timeline.parquet`.
- **`data/curated/`:** 10 `<dataset>_baseline.parquet` files holding only the INCLUDED cells (30,221,057, 59.5%).
- **Outputs:** `phase-02-baseline/outputs/`, all the required CSVs plus supporting ones (`baseline_sensitivity`, `baseline_current_reference`, `baseline_family_readiness`, `column_holds`, `operating_state_events` and others).
- **Report:** `phase-02-baseline/reports/PHASE_2_NORMAL_OPERATING_BASELINE.md` / `.html`, with 7 figures.
- **Reviews:** `phase-02-baseline/reviews/REVIEW_LOG.md`. Planner, product analyst, python reviewer and MLE reviewer were run, and every finding has a recorded disposition.

### Key results
- **Operating state (POC PROXY — UNCONFIRMED):**
  - `Kiln MD` = 0.02 co-occurs with feed ~415 TPH, speed ~5.2 RPM and burning zone ~1113 °C. `Kiln MD` = 0 co-occurs with no feed and no speed.
  - Composite minutes: RUNNING 202,558, STOPPED 44,798, transition 15,361, conflict 9.
  - Restart ramps are measured from each stop's own pre-stop level. The primary signal is Kiln-I feed; in September it is Kiln-IA hood temperature.
- **Load regimes:** there are 3 feed bands (≈294 / 375 / 422 TPH). They are **TENTATIVE**: only 40% of bootstrap resamples reproduce them. The single running baseline is primary.
- **Baseline confidence (primary population, 203 tags):** 68 HIGH, 5 MEDIUM, 85 LOW, 45 INSUFFICIENT (held columns).
- **Family readiness:** no family is READY. ALTERNATIVE FUEL is INSUFFICIENT. Every other family with data is PARTIAL.
- **Stability:** 106 tags LOW short-term variation, 25 MODERATE, 11 HIGH, 16 undefined (MAD = 0).
- **Drift:** 73 month/tag pairs show a notable level shift against the prior-only reference. This is descriptive and not a deterioration finding.
- **Validation:** 123/123 checks PASS across G1 (source), G2 (data), G3 (temporal/look-ahead), G4 (statistical) and G5 (reproducibility). Two consecutive `--clean` runs were byte-identical on the 10 key outputs.

### Open issues carried to Phase 3
- **Operating state:** `Kiln MD` meaning is unconfirmed and the equipment identity is unconfirmed (see the plant questions in section 4).
- **Specific heat:** there are two Sp.Heat definitions (Kiln-I F and G differ by ~60 kcal/kg), and Kiln-I G equals Kiln-IIIA X. The plant must say which is authoritative.
- **Fit window:** every band, label and statistic is fitted on the full supplied period. **Phase 3+ must refit on its own training window** before scoring any period.
- **Held columns:** 13 unit-review holds and other column holds stay in force (`phase-02-baseline/outputs/column_holds.csv`).

### Phase 3 can consume
`data/curated/*_baseline.parquet`, `data/processed/*.parquet`, the state and regime timelines, and these outputs: `baseline_reference_bands.csv`, `baseline_statistics.csv`, `baseline_stability.csv`, `baseline_temporal_analysis.csv`, `multivariate_baseline.csv`, `baseline_confidence.csv`, `baseline_family_readiness.csv`, `baseline_current_reference.csv`, `column_holds.csv`.

## 8. Phase 3 — Efficiency Deterioration KPI (COMPLETE, awaiting review)

**KPI status: PARTIAL.** It is a POC Kiln Efficiency Deterioration KPI: a 0–100 POC normalized score, not a plant limit and not a deposit or ring detector. It is conditional on the unconfirmed state proxy, the unconfirmed equipment mapping and the unresolved Sp.Heat definition, and it has no event validation.

- **Pipeline:** `phase-03-efficiency-kpi/scripts/`. Run `../../.venv/bin/python run_phase3.py --clean` (about 80 s).
  - The pure scoring code is `kpi_core.py`: causal masks, causal state, 10-min buckets, fit and score.
  - 23 unit tests are in `phase-03-efficiency-kpi/tests/`.
- **Definition:**
  - D = 0.5·S_EFFICIENCY (Sp.Heat F and G, one-sided, load-adjusted) + 0.5·mean(combustion, thermal, draft/pressure, stability).
  - P = trailing 6 h median of D.
  - KPI = 100·(1 − 2^−e), with 0 = the training median and 50 = the training P95.
  - 33 tags are included.
- **Windows:** training 2025-04-01 → 05-31, refitted on its own (the Phase 2 full-period stats are not used). Scoring runs 2025-06-01 → 2025-08-23; there is no September, because Kiln-I is missing.
- **Result:** out-of-sample median KPI 18.5, rising from 13.1 in June to 23.6 in August.
  - About 94% of buckets are PROCESS_DEVIATION_LED. The unadjusted Sp.Heat component is 0 in every month, so specific heat did not rise against a high-Sp.Heat April–May reference.
  - Beyond-reference readings (1%) are mostly SPECIFIC_HEAT_LED.
  - Levels depend on the window and the weights; the direction of change is robust. A held-out calibration shows much of June's level is fit optimism.
- **Gates:**
  - 55/55 validation checks PASS.
  - Leakage test PASS: 9 cut points, exact.
  - Sp.Heat F vs G: PASS (Spearman 0.96 / 0.98).
  - Two clean runs gave byte-identical outputs.
  - Source, Phase 2 outputs and `data/` are unchanged.
- **Reviews:** planner, product analyst, python reviewer and MLE reviewer (PASS-WITH-CONDITIONS, conditions cleared). See `phase-03-efficiency-kpi/reviews/REVIEW_LOG.md`.
- **Phase 4 inputs:**
  - `outputs/efficiency_deterioration_kpi.parquet`
  - `kpi_component_scores.parquet`
  - `kpi_reference.json` (the frozen reference)
  - `kpi_reference_bands.csv`, `kpi_definition.json`, `kpi_candidate_inventory.csv`
  - `kpi_core.run_kpi` (leakage-tested scorer)

## 9. Phase 4 — Leading Indicators (COMPLETE, awaiting review)

**Result: weak / tentative.** These are empirical leading indicators of the Phase 3 POC KPI. They are not validated predictors of deposits, rings, coating or failures, and there is no event ground truth.

- **Pipeline:** `phase-04-leading-indicators/scripts/`. Run `../../.venv/bin/python run_phase4.py --clean` (about 6.5 min).
  - The pure code is in `indicator_core.py`.
  - 32 unit tests are in `phase-04-leading-indicators/tests/`.
  - Phase 3's `kpi_core` is imported read-only, with no bytecode written.
- **Design:**
  - Candidates: 137 candidate tags plus 3 load-context tags, 7 causal features each, 10 lags from 10 min to 12 h.
  - Target: the future KPI change ΔK(t, H).
  - Statistic: partial Spearman controlling for K(t), momentum and Kpend, with n_eff, a 3-day-block bootstrap and BH.
  - Windows: discovery (Apr–May) chooses lag and sign; replication (Jun–Jul) drives gates, score and set; the **August holdout** is reported once.
  - Gates: replication, feed controls, forward ≥ backward, circular-shift null.
  - KPI inputs and proxies become component precursors and are never in the set.
- **Result:**
  - Screening: 54 of 9,800 discovery tests pass q ≤ 0.10, from 22 indicators.
  - **Selected set:** `Kiln-I!I|ROC_1H`, a rising PC coal-firing trend about 60 min before a KPI increase. Partial ρ is 0.056 in Jun–Jul; the August holdout has the same sign but is not significant. Confidence LOW. It is a manipulated variable, most plausibly an operator response.
  - **Component precursors:** the burning-zone temperature, Sp.Heat F and cyclone-4 temperature trends.
  - **Load proxies:** 12, including cooler fans, CBS gas flow and feed.
  - **Unstable:** 5, including kiln drive power and current. **Lagging:** 1.
  - The KPI's own momentum is far more informative.
- **Gates:**
  - Validation: 61 PASS, 0 FAIL, 7 INFO, 4 NOT_MET_REPORTED (robustness rules reported, including F-vs-G ranking 0.67).
  - Leakage: exact at 9 cut points.
  - Null calibration: 6.6 % of shifted nulls with p < 0.05, 0 BH discoveries.
  - Determinism: two clean runs byte-identical on 14 files.
  - Phases 1–3, `data/` and the source are unchanged.
- **Reviews:** planner, python-reviewer, mle-reviewer (PASS-WITH-CONDITIONS; resolved by the holdout redesign) and product analyst, plus a confirmatory re-review. See `phase-04-leading-indicators/reviews/REVIEW_LOG.md`.
- **Phase 5 may consume:**
  - `leading_indicator_set.csv`: use only rows with `usable_downstream = True`, following each row's `permitted_use`.
  - `indicator_feature_values.parquet` and `indicator_feature_reference.json`.
  - `indicator_scores.csv`: the load-proxy classes.
  - `indicator_lag_analysis.csv`, `indicator_episodes.csv`, `indicator_data_quality.csv`.
  - AFR `Kiln-I!K` was reserved and not analysed. Fuel firing tags are set-points, so in Phase 5 they are explanatory variables, not outcomes.
- **New plant questions:**
  - Is PC coal firing manual or controller-set, and what drives it?
  - What drives kiln drive power at constant feed?
  - What do negative bypass-gas-flow values mean?
  - Which tags are set-points?

## 10. Phase 5 — Alternative Fuel Analysis (COMPLETE, awaiting review)

**Result: AFR-associated process behaviour only.** Nothing here is AFR-caused. No fuel properties exist in the supplied data: no calorific value, moisture, RDF / plastic split or fuel mix. No energy-based metric (substitution rate, energy flow) is computed, and nothing is a plant limit, set-point or recommendation.

- **Pipeline:** `phase-05-af-analysis/scripts/`. Run `../../.venv/bin/python run_phase5.py --clean` (about 4.5 min; six analysis steps run in parallel).
  - The pure code is in `af_core.py`, and the relationship engine in `af_context.py`.
  - 17 unit tests are in `phase-05-af-analysis/tests/`.
  - Phase 4 `indicator_core` / `p4common` and Phase 3 `kpi_core` / `load_dataset` are imported read-only, with no bytecode written.
- **Signals:**
  - `Kiln-I!K` *AFR | Solid* (TPH) is analysed as a FUEL_CONTROL_INPUT.
  - `Kiln-I!L` *Liquid* is **INSUFFICIENT_DATA**: 8.3 % present, bimodal, 9 values ≥ 9,999.
  - Coal and PC firing are co-manipulated covariates only.
  - CV, moisture, RDF, plastic and fuel mix are NOT_AVAILABLE.
  - Excluded targets: the held `Kiln-I!AA` / `AE`, the constant `Kiln-IA!F` and `CBS-Calculation!B` / `C`, and the plant-calculated `CBS-Calculation!D..G`.
- **Design:**
  - RUNNING 10-min buckets.
  - The primary AFR series is Phase 2-valid with no single-tag flatline mask. Masked variants are in sensitivity G.
  - POC_EMPIRICAL_BANDs are NO / LOW / MEDIUM / HIGH_AFR (Apr–May non-zero P25 = 31 and P75 = 35.5 TPH, frozen).
  - The correlation engine (LAGGED_LEVEL / FUTURE_CHANGE / MOMENTUM, lags 0–360 min) uses partial Spearman with n_eff, a 3-day-block bootstrap and BH. Discovery (Apr–May) chooses lag and sign, Jun–Jul replicates, and August is the holdout.
  - AFR TRANSITION EPISODES (START / STOP / RAMP) are compared with feed-matched controls using a label-permutation test; 129 are eligible.
  - Matched ON/OFF comparisons were attempted.
  - Negative controls: circular shift, 30-day misalignment and randomised labels.
  - Sensitivity groups A–H.
  - Pre-declared evidence labels.
- **Findings** (Apr–May / Jun–Jul / Aug):
  - **Load:** AFR tracks feed (partial ρ +0.35 / +0.34 / +0.50). 80 % of AFR = 0 minutes are kiln stops.
  - **Coal swap (co-manipulation, capped LOW):** AFR and PC coal move in opposite directions (level ρ −0.37 / −0.30 / −0.45). PC coal rises a median +6 TPH within 1 h of AFR stops.
  - **Combustion:** higher AFR goes with lower preheater-outlet O₂ (−0.16 / −0.44 / −0.19) and falling NOx.
  - **Temperatures:** preheater, TAD and hood temperatures dip after AFR stops and ramp-downs, at the same time as the coal increase and feed cuts.
  - **Sp.Heat:** F and G co-vary with AFR. Firing rates per ton of feed, including AFR, reproduce them with R² 0.92 (F) / 0.65 (G), which is consistent with Sp.Heat being calculated from the firing inputs. The plant must confirm.
  - **Efficiency KPI:** no supported relationship. The current-KPI association does not replicate, the future change is NOT SUPPORTED, and there is no AFR precursor before the Phase 4 KPI episodes.
  - **Phase 4 indicator:** `Kiln-I!I|ROC_1H` fires +56 percentage points more often in falling-AFR hours. It is largely a coal-for-AFR swap signature.
  - **Matching:** MATCHING_NOT_SUPPORTED everywhere, because steady AFR-off running hours are too rare.
- **Evidence:**
  - 43 ASSOCIATED (26 process, 8 co-manipulation, 9 Sp.Heat / KPI), 40 WEAK, 191 NOT SUPPORTED, 60 INSUFFICIENT.
  - 21 MEDIUM (process / load only) and 22 LOW. HIGH is never assigned.
  - August CONFIRMED 27 of the 43 ASSOCIATED rows.
- **Gates:**
  - Validation: 56 PASS, 5 INFO, 0 FAIL (G1–G7). This covers a leakage perturbation test, an independent re-derivation of every lag choice and evidence label, BH vs scipy, a null calibration, and a check that the confidence cap was applied.
  - Determinism: two clean runs byte-identical on 17 files.
  - Phases 1–4, `data/` and the source are unchanged.
- **Reviews:** planner, product analyst, python-reviewer and mle-reviewer (PASS-WITH-CONDITIONS; no leakage found). All findings are resolved, plus revalidation fixes for the prior-transition rule and the confidence cap. See `phase-05-af-analysis/reviews/REVIEW_LOG.md`.
- **Phase 6 may consume:**
  - `afr_transition_episodes.parquet` and `afr_*_relationships.csv`: use `evidence`, `confidence` and `confidence_cap_reason` exactly.
  - `afr_operating_bands.csv`, `afr_daily_summary.csv`, `afr_data_quality.csv`, `afr_data_requirements.csv`.
  - Check AFR stops and ramp-downs (with the simultaneous PC-coal increase) as **context** for any abnormal period.
  - AFR transition episodes are not abnormal events.
- **New plant questions:**
  - Is `Kiln-I!K` a set-point, a feeder demand or a measurement?
  - What are the Sp.Heat F / G formulas, and what heat factor do they use for AFR?
  - Why are AFR stops and ramps initiated (is there an operating log)?
  - Is PC coal raised deliberately when AFR drops?
  - What do the Liquid AFR values (~4 LPH, 10,000) mean?
  - The priority list is in `outputs/afr_data_requirements.csv`, and the questions are in report §22a.

## 11. Next step

Waiting for review of Phase 5 and for the Phase 6 prompt (Historical Abnormal Events). Phase 6 has not been started. Phase 5 is not yet committed; its files are on branch `phase-05-af-analysis`.
