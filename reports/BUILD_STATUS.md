# Dalmia Kiln POC — Build Status

**As of:** 2026-09-30
**Branch:** `phase-10-dashboard`, created from `phase-09-api` (Phase 1 `b39d374`, Phase 2 `6e54477`, Phase 3 `a57c1b8`, Phase 4 `8325450`, Phase 5 `da5c932`, Phase 6 `2e3fa53`, Phase 7 `cfacf8e`, Phase 8 `ab1facc`, Phase 9 `d84244e`)
**Current state:** Phases 1–10 are COMPLETE and awaiting review. Phase 11 has not started.

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
| 6 | Historical Abnormal Events | **COMPLETE, awaiting review — 12 empirical abnormal periods (not plant events)** |
| 7 | Deposit/Inefficiency Risk Score | **COMPLETE, awaiting review — empirical POC risk score (not deposit-validated)** |
| 8 | Early Warning Validation | **COMPLETE, awaiting review — primary endpoint NOT_SUPPORTED (no early-warning claim)** |
| 9 | API / Analytical Service | **COMPLETE, awaiting review — read-only evidence API + plant event annotation store (no alerting, no prediction)** |
| 10 | Multi-Page Analytical Dashboard | **COMPLETE, awaiting review — retrospective dashboard on the Phase 9 API (no live monitoring)** |
| 11–12 | QA, Final Report | NOT STARTED |

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

## 11. Phase 6 — Historical Abnormal Events (COMPLETE, awaiting review)

**Result: 12 empirical HISTORICAL ABNORMAL PERIODS (Jun–Aug).** They are derived from the Phase 3 POC KPI and process measurements. They are **not** validated plant events: no coating, ring, deposit, maintenance, failure, cleaning or shutdown-reason ground truth exists (`event_ground_truth_status = NOT_AVAILABLE`).

- **Pipeline:** `phase-06-abnormal-events/scripts/`. Run `../../.venv/bin/python run_phase6.py --clean` (about 40 s).
  - The pure code is in `abn_core.py`, with 18 thin mandated steps.
  - 12 unit tests are in `tests/`.
- **Definition:**
  - Candidate: RUNNING buckets with KPI ≥ 41.82 (the frozen training P90), merged across gaps of ≤ 60 min. Stops, long gaps and the frozen window break an episode.
  - Final: out of sample, no ordinary-context rule matched, and ≥ 1 process family above its training P90.
  - Ordinary-context categories are kept, never deleted.
  - Apr–May periods are `CALIBRATION_ONLY_ABNORMAL_LIKE`.
- **Results:**
  - 35 candidates, of which 16 are out of sample.
  - 12 final periods: 3 HIGH, 4 MODERATE and 5 LOW severity; confidence 10 MEDIUM (capped) and 2 LOW.
  - 11 of the 12 are multi-family, most often thermal, combustion and draft.
  - COMBUSTION_DOMINANT is the only type that recurs across months.
- **Context:**
  - 8 of the 12 are LOAD_ASSOCIATED, and none is load-independent.
  - AFR transitions cluster near onsets above chance. This is context, and its causal role is not assessed.
  - The Phase 4 indicator is not distinguishable from chance.
- **Robustness:**
  - Every period is kept by ≥ 81 % of the robustness variants.
  - The alternative Jun–Jul15 KPI reference keeps only 8 % (NOT_MET, reported). The abnormal level depends on the reference period.
- **Gates:**
  - 47 PASS, 0 FAIL, 2 NOT_MET_REPORTED, 1 INFO.
  - The leakage test is identical at 13 cut points.
  - Two clean runs were byte-identical on 15 files.
  - Phases 1–5, `data/` and the source are unchanged.
- **Reviews:** planner, python-reviewer (Approve), mle-reviewer (PASS-WITH-CONDITIONS, resolved) and product analyst (resolved). See `phase-06-abnormal-events/reviews/REVIEW_LOG.md`.
- **Phase 7 may consume:**
  - `abnormal_episodes.parquet` (filter `in_final_set`);
  - the `_signals`, `_context`, `_severity`, `_confidence`, `_pre_event`, `_post_event` and `_types` outputs.
  - These are not confirmed events.
  - Never use the post-event fields as features.

## 12. Phase 7 — Deposit / Inefficiency Risk Score (COMPLETE, awaiting review)

**Result: an EMPIRICAL POC RISK SCORE (0–100, `p7-risk-1.1.0`).** It measures how strongly the current kiln condition resembles abnormal / inefficient process behaviour relative to the frozen Apr–May 2025 reference. It is **not** a deposit, ring or failure probability, a plant limit or a control recommendation. There is no event ground truth.

- **Pipeline:** `phase-07-risk-score/scripts/`. Run `../../.venv/bin/python run_phase7.py --clean` (about 1 min).
  - The pure scorer is `risk_core.score_frame`; config and paths are in `common.py`.
  - 83 unit tests are in `tests/` (`../../.venv/bin/python -B -m unittest discover -s ../tests -t ../tests`).
  - Phase 3–6 code is imported read-only.
- **Definition:**
  - Per family (efficiency / Sp.Heat, combustion, thermal, draft / pressure, stability): the trailing 1-h median of the RUNNING-masked Phase 3 component, mapped to `a_d = 1 − 2^(−excess)` against the Apr–May median and P90.
  - `risk_score = 100·(0.5·H + 0.25·C + 0.25·P)`: magnitude H (max and mean, fixed denominator 5), concurrence C and persistence P over the last 3 h.
  - Architecture `H_PRIMARY_HYBRID` was selected by a pre-declared rule, not by coverage of the Phase 6 periods.
  - Confidence is a separate six-part mean, capped at MEDIUM. There is an explicit status, reason codes and an `operational` flag.
- **Bands (empirical, reference-relative):** ELEVATED ≥ 21.1 (Apr–May P75) and HIGH ≥ 38.2 (P90). The P95 edge was not supported and was merged into HIGH.
- **Results (9,557 operational Jun–Aug buckets; September not scored):**
  - Share ≥ HIGH: June 25.1 %, July 41.6 %, August 53.0 %. Only August > June is separable (+0.28, block CI +0.10 to +0.42).
  - Excluding the kiln-inlet O₂ analyser (`Kiln-I!X`, frequent ambient-air readings) roughly halves the rise. This is a major caveat for the plant to confirm.
  - All 12 Phase 6 periods reach HIGH (AUC 0.868). This is circular coverage, not accuracy. Severity is inconclusive (ρ 0.33, n = 12).
  - AFR and the Phase 4 indicator add no gain, so they stay context only.
  - The score is not load-independent: it is higher at low feed and during load changes.
- **Robustness:** ranks are stable (median Spearman 0.97), band levels are not (14 of 25 variants SENSITIVE, reported as NOT_MET). August > June holds in 25 of 25 variants.
- **Gates:**
  - 48 PASS, 0 FAIL, 1 NOT_MET_REPORTED, 6 INFO (G1–G9).
  - Leakage is exact at 8 truncation cuts, under full post-T randomisation, under post-event perturbation of all 12 periods, and under reference refit.
  - NC1 / NC2 PASS (consistency controls).
  - Two clean runs were byte-identical on 16 files.
  - Phases 1–6, `data/` and the source are unchanged.
- **Reviews:** planner, python-reviewer, mle-reviewer (PASS-WITH-CONDITIONS), senior data scientist, statistical analyst, data-quality auditor (PASS-WITH-CONDITIONS), product, and a Ponytail audit. The log has 75 findings, all RESOLVED / ACCEPTED / DEFERRED and none OPEN. See `phase-07-risk-score/reviews/REVIEW_LOG.md`.
- **Phase 8 may consume** (schemas in `phase-07-risk-score/docs/FEATURE_CONTRACT.md`):
  - `risk_scores.parquet`, filtered on `operational == True`;
  - the `_components`, `_confidence` and `_reasons` parquets;
  - `risk_score_reference.json` and `risk_score_variant_references.json` (frozen, hash-checked), `risk_score_bands.csv` and `risk_score_feature_inventory.csv`;
  - `risk_core.score_frame`.
  - `risk_score_diagnostics.parquet` is not operational.
- **Guards for Phase 8:**
  - HIGH is not a rare-event flag (it covers about half of August).
  - Use ranks and trends, not band levels.
  - Report empirical rates only, never false-positive rates.
  - Do not use `afr_context` live (it holds retrospective labels).
  - Repeat key results with the O₂-excluded variant.
- **New plant questions:** the purge / calibration behaviour of the `Kiln-I!X` O₂ analyser, which period the plant regards as normal, and whether feed reductions are logged. The full priority list is in report §20.

## 13. Phase 8 — Early Warning Validation (COMPLETE, awaiting review)

**Result: the frozen Phase 7 score (`p7-risk-1.1.0`) is NOT shown to rise before the 12 Phase 6 empirical abnormal periods.** This is a validation / falsification stage only: nothing in Phase 7 was changed, and no deposit, ring, failure or maintenance claim is possible (no event ground truth).

- **Pipeline:** `phase-08-early-warning/scripts/`. Run `../../.venv/bin/python run_phase8.py --clean` (about 70 s; run twice for gate G11).
  - 48 unit tests in `tests/` (`../../.venv/bin/python -B -m unittest discover -s ../tests -t ../tests`).
  - Reads only Phase 6 / 7 outputs and the Phase 7 cache (`operational == True` scores; no `afr_context`, no `risk_score_diagnostics.parquet`). Writes a provenance manifest to `outputs/run_manifest.json`.
- **Primary endpoint (pre-declared):** median rank excess over (T0 − 60 min, T0] vs month-matched ordinary running, T0 = Phase 6 CUSUM onset.
  - PE +0.051 (about 5 percentile points), 95 % CI −0.087 to +0.119, randomisation p 0.118, Cliff's δ +0.21, 10 of 12 periods, 6,641 controls → **NOT_SUPPORTED**.
  - O₂-excluded variant (`Kiln-I!X` removed): like-for-like PE +0.088, p 0.063; on its own 12-period set p 0.045 → WEAK, analyser-dependent. Neither variant is preferred until the plant explains the analyser.
- **Why the small positive estimate is not precedence:** 6 of 12 onsets are censored (T0 = look-back cap, window inside the KPI shift). Censored onsets carry all of the excess at every horizon; the 5 uncensored ones give PE −0.072.
- **Other results:**
  - 2–6 h horizons WEAK on raw p only (BH q 0.088–0.097, n 8), carried by censored onsets; 12 h and 24 h NOT_SUPPORTED.
  - None of W1–W5 covers the periods more often than it fires in ordinary running. In ordinary August running they are on 9–79 % of the time; lead-time tables are capped by the 24-h look-back and are not lead times.
  - Negative controls: NC1 p 0.19 and NC2 p 0.12 (nulls centred on 0); the score is higher just after periods end (+0.099) than before they start; NC5 (future perturbation) identical.
  - Load: INSUFFICIENT_DATA (5 periods left after removing load transitions). Control-selection and control-DQ sensitivities (F19, F20) leave the primary unchanged.
- **Gates:** G1–G12, 43 checks, all PASS on the final double clean run (byte-identical; see `phase-08-early-warning/reviews/REVIEW_LOG.md`). Source (60 files) and Phase 1–7 artifacts (543 files) unchanged.
- **Reviews:** senior-data-scientist, statistical-analyst, data-quality-auditor, python-reviewer, mle-reviewer, product-analytics, cs-product-analyst, plus a Ponytail audit; 49 log entries, none open.
- **Phase 9 handoff** (report §26):
  - MAY show: the historical score trend with the O₂-excluded overlay and a "retrospective, not an early warning" disclaimer; the 12 periods labelled "KPI-derived abnormal periods (not plant events)"; the finding classes; an event-annotation tool for the plant.
  - MUST NOT show: live W1–W5 flags or alarms, band colours as alarms, lead-time or coverage numbers, the Phase 7 AUC, the word "prediction", `afr_context`.
  - Decision: no alerting in Phase 9; collect plant event labels; re-run this frozen protocol once ≥ 8 evaluable labelled events exist.
- **Plant data required (priority 1):** timestamped coating / ring / cleaning / maintenance / stoppage logs for Apr–Sep 2025, and the `Kiln-I!X` purge / calibration schedule. The three Phase 7 plant questions remain open.

## 14. Phase 9 — API / Analytical Service (COMPLETE, awaiting review)

**Result:** a read-only analytical evidence API over the frozen Phase 6–8 artifacts, plus a SQLite plant event annotation store. It is **not** an alerting or prediction service. The machine-readable contract (`config/analytical_contract.json`, served by `/api/v1/metadata/status`) sets `early_warning_supported`, `alerting_enabled`, `prediction_enabled` and `plant_event_ground_truth_available` to false. Every analytical response carries `provenance` and `interpretation` blocks (`is_prediction`, `is_alert` and `is_probability` are all false).

- **Pipeline:** `phase-09-api/scripts/`. Run `../../.venv/bin/python -B run_phase9.py --clean` (about 31 s; run it twice for G11). Serve with `../../.venv/bin/python -B api_app.py` (127.0.0.1:8009).
  - No framework and no new dependency: stdlib `wsgiref`, `sqlite3` and `json`, plus the pandas / pyarrow already installed.
  - Config: `DALMIA_KILN_POC_ROOT`, `DALMIA_KILN_SOURCE_ROOT`, `DALMIA_KILN_EVENTS_DB`, `DALMIA_KILN_API_HOST` / `_PORT`.
  - 59 unittest tests in `tests/`: contract 14, integrity / temporal 13, events 16, safety 7, security 9.
- **API (`/api/v1`):**
  - metadata (`/`, `/status`, `/provenance`, `/limitations`, `/methodology`, `/data-requirements`);
  - `risk-scores` (`variant=primary` default | `o2_excluded`; `operational_only` must be true);
  - `risk-scores/variant-comparison`;
  - `abnormal-periods` (`label_type = KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD`);
  - `validation/early-warning-historical` (historical results; primary `NOT_SUPPORTED`);
  - `findings` (Phase 8 classes, with the F3 coverage figures withheld);
  - `events` CRUD with soft delete, plus `events/{id}/audit`;
  - `/health` and `/ready`.
  - There are no alert, prediction, probability or live-warning routes; all of those return 404.
- **Artifacts:** `outputs/artifact_manifest.json` records SHA-256, version and schema for 19 artifacts. Every Phase 6/7 input equals the hash Phase 8 validated. The API re-verifies at startup and answers 503 on any mismatch.
- **O₂-excluded variant:** Phase 8 persisted it only inside its 12 event windows. `build_artifacts.py` ran Phase 8's unchanged `o2_excluded_score` once, offline: a refit and rescore by Phase 8's own code, logged as a declared exception.
  - It reproduces 1,501 persisted values (max diff 0.0), the rank correlation 0.9393 (diff 0.0) and the June / July / August medians (diff 0.0).
  - Served as `SENSITIVITY_ANALYSIS`, `preferred = false`, `comparable_to_primary = false` (like-for-like p 0.0625).
- **Event annotation:**
  - Fields: `event_type` (COATING / RING / DEPOSIT / CLEANING / MAINTENANCE / STOPPAGE / FEED_REDUCTION / ANALYSER_CALIBRATION / PROCESS_UPSET / OTHER), naive historian-clock start / end, source, and optional precision / onset basis / entry kind / `annotator_viewed_risk_score`.
  - `label_origin = PLANT_SUPPLIED` and `analytical_label = null`, both enforced by the database.
  - Enforced by triggers: append-only audit, soft delete only, no REPLACE, immutable identity fields, version + 1.
  - Writes: `X-Actor` attribution; `expected_version` required on PATCH and DELETE; 409 on a same-type / equipment / source overlap.
  - The store `phase-09-api/state/events.sqlite3` is gitignored and never deleted by `--clean`.
- **Gates:** G1–G15 all PASS on the final double clean run.
  - G1: 610 upstream files and 60 source workbooks unchanged.
  - G11: 17 files / query digests byte-identical.
  - Latency: metadata 0.1 ms, a one-day score window 12 ms, 1,000 full score rows 90 ms, event create 1 ms. Startup 1.8 s.
- **Reviews:** planner, python-reviewer (APPROVE-WITH-CHANGES), mle-reviewer (PASS-WITH-CONDITIONS), cs-product-analyst (CONDITIONAL PASS: two HIGH findings, F3 coverage text and O₂ comparability, both fixed) and database-reviewer (ACCEPT WITH FIXES), plus a Ponytail audit (17 findings, none CRITICAL / HIGH). 57 log rows, none open. See `phase-09-api/reviews/`.
- **Known limitations:**
  - no authentication (X-Actor is attribution only; loopback bind);
  - single-threaded wsgiref;
  - evaluable-event count stays 0 until the frozen Phase 8 protocol is re-run;
  - re-run order Phase 7 → 8 → 9;
  - all Phase 1–8 caveats remain (`/metadata/limitations`, L01–L13).
- **Phase 10 may consume:**
  - the historical score;
  - the O₂-excluded overlay (`variant-comparison`, with `gaps_in_page`);
  - the KPI-derived periods;
  - the Phase 8 findings;
  - plant annotations;
  - metadata, provenance and data-quality status.
- **Phase 10 MUST NOT:**
  - show live W1–W5 flags;
  - use alarm colours for bands;
  - show a prediction or probability;
  - state lead times;
  - show coverage percentages or the AUC;
  - present O₂-excluded as preferred;
  - treat the API as a live alerting source.

## 15. Phase 10 — Multi-page analytical dashboard (COMPLETE, awaiting review)

**Result:** a seven-page retrospective dashboard on the frozen Phase 9 API. It is not a live monitor, an alarm board, or a prediction view.

- **Branch:** `phase-10-dashboard` (from `phase-09-api`).
- **Commit:** `182ef71` (dashboard). Phase 9 remains `d84244e`.
- **Stack:** plain HTML, CSS, and ES modules. `phase-10-dashboard/serve.py` (stdlib) serves `public/` and proxies `/api`, `/health`, and `/ready` to Phase 9 at `127.0.0.1:8009`. No npm dependency and no chart library (inline SVG). Phase 9 code and artifacts are unchanged.
- **Pages:** `/` Overview, `/history` Historical Risk, `/abnormal-periods`, `/events`, `/validation`, `/data-quality`, `/methodology`.
- **API:** metadata and status, limitations, methodology, data-requirements, provenance, risk-scores, variant-comparison, abnormal-periods, validation/early-warning-historical, findings, events CRUD and audit.
- **Tests:** `cd phase-10-dashboard && node --test tests/*.mjs` — 9 tests (gaps, form, forbidden wording, live Phase 9 contract). Browser journeys in `phase-10-dashboard/reviews/E2E_LOG.md`. Playwright is not installed.
- **Accessibility:** semantic shell, focus ring, chart description plus table plus keyboard slider, stacked tables under 720px. No Lighthouse score and no screen-reader session (`reviews/ACCESSIBILITY_REVIEW.md`).
- **Security:** descriptions are text nodes. XSS payload did not execute. Same-origin proxy; no wildcard CORS (`reviews/SECURITY_REVIEW.md`).
- **Ponytail:** no critical or high finding (`reviews/PONYTAIL_AUDIT.md`).
- **Screenshots:** `phase-10-dashboard/screenshots/` (overview, historical-risk, abnormal-periods, plant-events, validation, data-quality, methodology, mobile-overview, mobile-historical-risk).
- **Known limitations:** no authentication; chart thinning above about 900 points; F16’s API title contains “Lead time” and is shown as BLOCKED with no lead-time number; one soft-deleted test annotation in the local gitignored event store.
- **Phase 11 handoff:** running dashboard, node tests, browser journey log, screenshots, and the three review notes above. Phase 11 is broader QA. Do not add live monitoring here.

## 16. Next step

Waiting for review of Phase 10. Phase 11 has not been started.

- To reproduce the dashboard: start Phase 9 (`cd phase-09-api/scripts && ../../.venv/bin/python -B api_app.py`), then `cd phase-10-dashboard && ../.venv/bin/python serve.py`, and open `http://127.0.0.1:8010/`.
- Phase 9 reproduction is unchanged: `cd phase-09-api/scripts && ../../.venv/bin/python -B run_phase9.py --clean` (twice).

