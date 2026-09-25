# Phase 1: Data Discovery

Status: COMPLETE, awaiting review before Phase 2 starts

Objective:
Build an evidence-based inventory of the supplied historical process-log data: its structure, temporal coverage, quality, units, process families, equipment coverage, event history and AF/RDF availability. The result decides whether the data can support the later POC objectives. No modelling, KPI, risk scoring or dashboard work happens in this phase.

## Inputs

| Input | Location | Use |
|---|---|---|
| Process-log workbooks (60 `.xlsx`) | `/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)` | Primary data, **read-only** |
| Problem statement, notes, archive | `/home/admin1/POPOS-DATA/Codebases/Dalmia/` (`Dalmia/Dalmia Problem Statement.pdf`, `Dalmia/kiln-poc-dashboard.md`, `Dalmia.txt`, `Dalmia.zip`) | Inventoried as supporting material; never used as data |

The source is never modified. `run_phase1.py` hashes every source file (SHA-256, size, mtime) before and after the run and fails if anything changed.

## How to run

```bash
cd phase-01-data-discovery/scripts
python3 run_phase1.py --clean     # clean execution: deletes outputs/, reports/, cache/ and regenerates (~8 min)
python3 run_phase1.py             # reuses the parse cache
```

Requirements: Python 3, pandas, numpy, openpyxl, markdown-it-py (for the HTML report), and `pdftotext` (poppler) for the supporting-document keyword search.

## Scripts (run in this order by `run_phase1.py`)

| Script | Objective | Main outputs |
|---|---|---|
| `common.py` | shared paths, header detection, cached read-only parsing, POC heuristics | `cache/*.pkl` |
| `taxonomy.py` | evidence-based process-family, measurement-type and label/unit rules | used by the profilers |
| `inventory_files.py` | A: recursive file inventory, hashes, ZIP diagnostics, archive cross-check | `file_inventory.csv`, `archive_member_crosscheck.csv` |
| `inventory_workbooks.py` | B: workbooks, sheets, header structure, merges, formulas, hidden rows | `workbook_inventory.csv`, `sheet_inventory.csv`, `header_consistency.csv` |
| `profile_timestamps.py` | D: timestamp format, parse rate, ordering, intervals, frequency | `timestamp_inventory.csv`, `sampling_changes.csv` |
| `detect_gaps.py` | F: gaps, duplicates, file overlaps | `gap_analysis.csv`, `gap_events.csv`, `duplicate_records.csv`, `file_overlaps.csv` |
| `profile_columns.py` | C + G: column/tag inventory, datatypes, value statistics | `column_inventory.csv`, `categorical_profile.csv` |
| `profile_quality.py` | E + G: completeness (RAG), sentinel / invalid-value candidates | `data_quality_report.csv`, `completeness_by_month.csv`, `identical_column_pairs.csv` |
| `detect_outliers.py` | H: IQR, MAD robust-z, percentile tails, spikes, sentinel match | `outlier_profile.csv` |
| `detect_flatlines.py` | I: constant, near-constant and flatline periods | `flatline_profile.csv`, `flatline_periods.csv` |
| `build_inventories.py` | J, K, L, M, N + cross-dataset alignment | `unit_inventory.csv`, `unit_consistency_review.csv`, `process_tag_inventory.csv`, `equipment_data_matrix.csv`, `equipment_month_coverage.csv`, `event_data_inventory.csv`, `alternative_fuel_inventory.csv`, `cross_dataset_alignment.csv`, `cross_dataset_identical_signals.csv` |
| `generate_report.py` | O + master report | `dq_issue_register.csv`, `phase1_data_readiness.csv`, `expected_parameter_presence.csv`, `reports/PHASE_1_DATA_DISCOVERY_REPORT.md` / `.html` |
| `export_data_manifest.py` | publishes the source manifest to the project data layer | `../data/raw/source_manifest.csv`, `../data/raw/dataset_registry.csv` |
| `run_phase1.py` | orchestration + validation | `pipeline_validation.csv` |

## Conventions

- `original_name` is the verbatim header text, with parts joined by ` | `. `normalized_name` is an added key and never replaces it.
- Group headers in the source are **not merged cells**. `group_header_ffill_candidate` assigns a group label to neighbouring columns by position, which is an inference, and is labelled as one.
- "Missing" means an empty cell or a whitespace-only string. Numeric statistics use native numeric cells only.
- Thresholds (completeness RAG, gap, flatline, outlier) are **POC DATA-QUALITY HEURISTICS** defined in `common.HEURISTICS`. They are not plant engineering limits.
- Statistical flags are **SUSPECTED OUTLIER** or **candidate** values. Nothing is declared invalid without source evidence.
- Anything not established by the source is recorded as `UNKNOWN` or `NOT FOUND IN SUPPLIED DATA`.

## Where to start reading

1. `reports/PHASE_1_DATA_DISCOVERY_REPORT.md` (or `.html`)
2. `outputs/dq_issue_register.csv` and `outputs/phase1_data_readiness.csv`
3. `outputs/process_tag_inventory.csv` for the tag list

Note: the repository `.gitignore` excludes `phase-*/outputs/*` and `phase-*/reports/*`, so the generated artifacts are reproducible but not committed by default.
