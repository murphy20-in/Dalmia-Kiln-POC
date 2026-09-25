# curated/

Holds only data **approved for baseline analysis**: the `baseline_status == INCLUDED` cells from `../processed/`. It is written by Phase 2 `calculate_baseline.py`. The Parquet files are git-ignored and reproducible.

| File | Content |
|---|---|
| `<dataset>_baseline.parquet` (10 files) | 1-minute values that passed every mask, are not column-held, fall in RUNNING_PROXY minutes and are not hourly-resolution. |

Every row keeps full traceability:
- **Source:** `source_file`, `source_row`, `source_column`, `ts`
- **Naming:** `original_name`, `unit`
- **Masks and labels:** `mask_reason`, `operating_state`, `state_basis`, `load_regime`

Constraints carried forward:
- Kiln-I has no September 2025 and Kiln-IIIA has no April 2025. Do not bridge those months.
- There are no event labels. Any label added later must come from plant records and be traceable to them.
- The operating state is a **POC PROXY — UNCONFIRMED**.
- Cross-dataset joins are a **POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED**.
- This baseline is fitted on the full supplied period. A phase that scores or validates periods must refit on its own training window.
