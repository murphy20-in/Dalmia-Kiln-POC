# processed/

Written by Phase 2 (`phase-02-baseline/scripts/`) and reproducible with `run_phase2.py --clean`. The Parquet files are git-ignored.

| File | Content |
|---|---|
| `<dataset>.parquet` (10 files) | One row per source cell (source file, source row, source column) from the manifest `USE` files. Nothing is resampled, interpolated, unit-converted or deleted. |
| `operating_state_timeline.parquet` | Per-minute operating state, labelled **POC PROXY — UNCONFIRMED** (composite view), plus `state_basis`. |
| `regime_timeline.parquet` | Per-minute load band from Kiln-I feed. The bands are **TENTATIVE**. |

Main columns in `<dataset>.parquet`:

- **Source trace:** `dataset`, `source_file`, `source_sheet`, `source_row`, `source_column`, `ts`, `ts_raw`
- **Names:** `original_name`, `normalized_name`, `unit`, `likely_process_family`
- **Values:** `value` (native numeric only), `raw_value_text` (verbatim non-numeric content), `cell_class`
- **Masks:** `value_valid`, `quality_flag` (GOOD/SUSPECT/BAD/MISSING), `mask_reason`, `dup_status`, `row_repeat_prev`, `segment_id`, `column_hold`, `tag_flatline`
- **State and population:** `operating_state`, `state_basis`, `load_regime`, `baseline_status` (INCLUDED / MASKED / EXCLUDED_COLUMN / EXCLUDED_STATE / EXCLUDED_RESOLUTION), `baseline_reason`

The rules are documented in the docstrings of `build_quality_masks.py`, `analyze_operating_state.py` and `calculate_baseline.py`.
