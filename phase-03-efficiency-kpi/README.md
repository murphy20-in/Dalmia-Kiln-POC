# Phase 3: Kiln Efficiency Deterioration KPI

Status: COMPLETE, awaiting review. KPI status: **PARTIAL**.

Objective:
Build a scientifically defensible, traceable **POC Kiln Efficiency Deterioration KPI**. It answers one question: *is the kiln's observed operating behaviour deteriorating relative to its own normal baseline?* It does that without equating statistical deviation with inefficiency, or KPI deterioration with deposit or ring formation.

The KPI is **not** a deposit, ring or coating detector. It is not a plant alarm or engineering limit, and it is not a failure predictor. No event ground truth exists, so validation is statistical only.

## Definition (short)

```text
KPI(t) = 100 · (1 − 2^(−e)),   e = max(0, P(t) − m) / (q95 − m)      0 = training median, 50 = training P95
P(t)   = trailing 6-h median of D (scored buckets, ≥ 50 % coverage)
D(t)   = 0.5 · S_EFFICIENCY + 0.5 · mean(S_COMBUSTION, S_THERMAL, S_DRAFT_PRESSURE, S_STABILITY)
```

- **Efficiency evidence:** Kiln-I Sp.Heat F and G, one-sided (higher than expected for the load). Both are used because the plant has not confirmed which is authoritative.
- **Supporting dimensions:** two-sided process-deviation context.
- **Refit:** every centre, scale and anchor is refitted on the training window **2025-04-01 → 2025-05-31**.
- **Reporting:** the KPI is reported only out of sample (2025-06-01 → last Kiln-I data, 2025-08-23).

Machine-readable definition: `outputs/kpi_definition.json`.

## Inputs

- **Minute data:** `data/processed/<dataset>.parquet` (Kiln-I, Kiln-IA, Kiln-II, Kiln-IIIA) and `data/processed/operating_state_timeline.parquet`, read-only.
- **Phase 2 CSVs:** `column_holds`, `baseline_confidence`, `tag_contract`, `frozen_windows`, `operating_state_events` and the other Phase 3 inputs. All are hashed in `kpi_version_manifest.csv` and never modified.
- **Not used for scoring:** Phase 2 full-period statistics, the curated baseline, the retrospective state and the retrospective flatline/frozen masks. They would leak future data, so they are replaced by causal equivalents in `kpi_core.py`.

## How to run

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-03-efficiency-kpi/scripts
../../.venv/bin/python run_phase3.py --clean                  # full clean reproduction (~70 s)
../../.venv/bin/python -m unittest discover -s ../tests -v    # unit tests only
```

## Pipeline

| Script | Purpose | Main outputs |
|---|---|---|
| `p3common.py` | Paths, labels, `KPIConfig` (every analytical choice), tag specification, exclusion reasons | — |
| `kpi_core.py` | **Pure KPI functions**: causal masks, causal state, bucketing, `fit_reference`, `score`, `run_kpi`. Used by every step, the leakage test and the unit tests | — |
| `load_phase2_inputs.py` | Hash the Phase 2 inputs; build the causal minute cache; per-tag data-quality accounting | `kpi_data_quality.csv`, `cache/minute_*.parquet` |
| `build_training_window.py` | Coverage analysis of the candidate windows; selection rule | `kpi_training_windows.csv` |
| `select_kpi_candidates.py` | Rules R1–R6 on the training window; inventory of all 203 tags | `kpi_candidate_inventory.csv`, `kpi_excluded_candidates.csv` |
| `calculate_component_scores.py` | Fit the frozen reference; per-tag z and scores | `kpi_reference.json`, `kpi_component_scores.parquet` |
| `calculate_persistence.py` | Scale anchors, POC analytical bands, day-block bootstrap CIs | `kpi_reference_bands.csv` |
| `calculate_efficiency_kpi.py` | Final KPI dataset with Sp.Heat F/G variants, traceability fields, version manifest | `efficiency_deterioration_kpi.parquet`, `kpi_version_manifest.csv` |
| `sensitivity_analysis.py` | 30 one-factor variants in groups A–H plus the secondary Mahalanobis KPI | `kpi_sensitivity_analysis.csv` |
| `validate_kpi.py` | Gates G1–G6, including the leakage test and synthetic injection | `kpi_validation.csv` |
| `generate_report.py` | MD + HTML report, 8 figures, KPI definition | `reports/PHASE_3_EFFICIENCY_DETERIORATION_KPI.*`, `outputs/kpi_definition.json` |
| `run_phase3.py` | Orchestration, unit tests, G7 determinism and source integrity | appends to `kpi_validation.csv` |

## Rules applied

- Source is read-only and hashed before and after every run. Phase 3 writes only under `phase-03-efficiency-kpi/`, and nothing leaves the machine.
- No held, INSUFFICIENT, unit-review, sentinel or duplicate column feeds the KPI (rule R1–R2; checked in G3).
- **No look-ahead:** each mask, state, bucket, rolling statistic and persistence value at time t uses data ≤ t. The reference is fitted once, on the training window.
- No unit conversions, no interpolation, and no imputation of Kiln-I September.
- Every output keeps the labels **POC PROXY — UNCONFIRMED** (state) and **POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED** (cross-dataset).
- Bands are labelled **POC ANALYTICAL REFERENCE BAND — NOT A PLANT ALARM / ENGINEERING LIMIT**.

## Reviews

See `reviews/REVIEW_LOG.md`: planner, product analyst, python reviewer and MLE reviewer, with the disposition of every finding.
