# Phase 2: Normal Operating Baseline

Status: COMPLETE, awaiting review before Phase 3 starts. Baseline status: **PARTIAL**.

Objective:
Turn the Phase 1 metadata contract into a clean, traceable, analysis-ready picture of normal kiln operation. That means documenting what normal looks like, over which operating regimes, and how stable it is. The baseline is an **empirical POC reference**. It is not a set of plant, engineering, alarm or control limits, and it makes no claim about equipment health.

## Inputs (the Phase 1 contract)

- `data/raw/source_manifest.csv`: only files with `status == USE` are loaded (58 of 60). Hashes are verified before and after every run.
- The Phase 1 outputs `process_tag_inventory`, `data_quality_report`, `unit_consistency_review`, `flatline_periods`/`flatline_profile`, `identical_column_pairs`, `gap_events`, `sampling_changes`, `outlier_profile` and `file_inventory`.
- The header parser `phase-01-data-discovery/scripts/common.py`, used read-only.

## How to run

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-02-baseline/scripts
../../.venv/bin/python run_phase2.py --clean     # full clean reproduction (~15 min)
```

Environment: the project virtual environment `.venv/` (created with `uv`; packages from `requirements.txt`). The system Python has no pyarrow or matplotlib.

## Pipeline

| Script | Purpose | Main outputs |
|---|---|---|
| `load_phase1_manifest.py` | Verify source hashes; tag contract; column holds; frozen windows | `source_verification`, `tag_contract`, `column_holds`, `frozen_windows` |
| `build_processed_data.py` | Long-format Parquet, one row per source cell (no resampling or filling) | `data/processed/<ds>.parquet`, `parse_log` |
| `build_quality_masks.py` | `value_valid`, `quality_flag`, `mask_reason`, duplicates, repeats, segments, holds, tag flatlines | `processed_dataset_manifest`, `mask_summary` |
| `analyze_operating_state.py` | Kiln MD evidence and the POC PROXY state timeline (running / stopped / transition / conflict) | `operating_state_analysis`, `operating_state_events`, `data/processed/operating_state_timeline.parquet` |
| `identify_regimes.py` | Load-band investigation (GMM on 10-min medians + bootstrap); AFR mode | `operating_regimes`, `data/processed/regime_timeline.parquet` |
| `calculate_baseline.py` | Baseline population; univariate and robust statistics; sensitivity | `baseline_population`, `baseline_statistics`, `baseline_sensitivity`, `data/curated/<ds>_baseline.parquet` |
| `calculate_stability.py` | Trailing rolling std/IQR, rate of change, stability class | `baseline_stability` |
| `analyze_temporal_baseline.py` | Daily/weekly/monthly/diurnal statistics; prior-only drift | `baseline_temporal_analysis` |
| `analyze_multivariate_baseline.py` | Pearson/Spearman correlation and rank PCA (within Kiln-I and composite) | `multivariate_baseline` |
| `build_baseline_reference.py` | Reference bands, per-population confidence, family readiness, current reference | `baseline_reference_bands`, `baseline_confidence`, `baseline_family_readiness`, `baseline_current_reference` |
| `validate_phase2.py` | Gates G1–G4 | `phase2_validation` |
| `generate_report.py` | MD + HTML report | `reports/PHASE_2_NORMAL_OPERATING_BASELINE.md/.html` |
| `run_phase2.py` | Orchestration, gate G5 (reproducibility and determinism), source-integrity re-check | appends to `phase2_validation` |

## Rules applied

- Source is read-only. Original header text (`original_name`) is kept next to every normalised name.
- Values are masked, never deleted. There is no interpolation, resampling of the processed layer, or unit conversion.
- CBS-II hourly rows stay hourly and are excluded from the 1-minute baseline.
- Kiln-I September is MISSING / UNAVAILABLE. Kiln-IIIA April is missing; its May-repeat file is not loaded or relabelled.
- The operating state and any cross-dataset view are labelled **POC PROXY — UNCONFIRMED** and **POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED**.
- **Fit-window rule for later phases:** every band, label and statistic here is fitted on the full supplied period. It is descriptive only. A later phase that scores or validates a period must refit on its own training window.

## Reviews

See `reviews/REVIEW_LOG.md` (planner, product-analyst, python and MLE reviews, with the disposition of each finding).
