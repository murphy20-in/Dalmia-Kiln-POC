# processed/

Empty. It will be populated in Phase 2, after the Phase 1 findings are reviewed.

Intended content: parsed, typed, 1-minute time-indexed copies of the `USE` files listed in `../raw/source_manifest.csv`, one dataset per equipment folder.

Inputs Phase 2 must take from Phase 1 (`phase-01-data-discovery/outputs/`):

- `process_tag_inventory.csv`: column letters, `original_name`, units, families, confidence
- `sheet_inventory.csv`: header rows and data start row per file
- `duplicate_records.csv`, `gap_events.csv`, `flatline_periods.csv`: duplicates to resolve, gaps and frozen windows to mask
- `data_quality_report.csv`, `outlier_profile.csv`: sentinel and invalid-value candidates
- `unit_consistency_review.csv`: columns whose unit or label needs plant confirmation

Masking and de-duplication rules are **not decided yet**. Phase 2 must document each rule and its justification. Masked values are to be flagged, not deleted, and gaps are not interpolated across.
