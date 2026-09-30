# Data Lineage

For each endpoint, the table traces the chain: API endpoint → adapter (`scripts/artifact_store.py`) → artifact →
producing phase and version → upstream lineage. Hashes are not repeated here because they change whenever a phase is
re-run. The live values are in `outputs/artifact_manifest.json` and `GET /api/v1/metadata/provenance`, and every
response carries `provenance.artifact_sha256`.

| Endpoint | Adapter | Artifact(s) | Phase / version | Upstream lineage |
|---|---|---|---|---|
| `/api/v1/risk-scores` (`variant=primary`) | `_primary` | `phase-07-risk-score/outputs/risk_scores.parquet` (+ `_components`, `_confidence`, `_reasons`) | 7 / `p7-risk-1.1.0`, reference `p7-risk-1.1.0/PRIMARY/42768113b86f/2025-04-01..2025-05-31` | Phase 3 KPI components ← Phase 2 masked / curated data ← Phase 1 manifest ← source workbooks |
| `/api/v1/risk-scores` (`variant=o2_excluded`) | `_o2x` | `phase-09-api/outputs/o2_excluded_scores.parquet` | 9: one-off offline refit and rescore by Phase 8's own code of the `EXCLUDE_KILN_INLET_O2_ANALYSER` variant (score version `p7-risk-1.1.0`); code and cache SHA-256 in the manifest | `build_artifacts.py` → Phase 8 `o2_sensitivity.o2_excluded_score` → Phase 7 `reference_builder` / `risk_core` on the Phase 7 cache grid; checked against Phase 8 `early_warning_trajectories.parquet` (1,501 values, Jun–Aug) and `early_warning_o2_sensitivity.csv` (rank correlation over all rows; June / July / August medians) |
| `/api/v1/risk-scores/variant-comparison` | `_primary`, `_o2x` | both of the above | 7 and 9 | as above |
| `/api/v1/abnormal-periods` | `_periods` | `phase-06-abnormal-events/outputs/abnormal_episodes.parquet` (`in_final_set` only) | 6 / `p6-abn-1.0.0` | Phase 3 KPI ≥ training P90 + process families ← Phase 2 ← Phase 1 |
| `/api/v1/validation/early-warning-historical` | `_validation` | Phase 8 `early_warning_summary.csv`, `_horizon_validation.csv`, `_control_validation.csv`, `_negative_controls.csv`, `_o2_sensitivity.csv`, `_load_sensitivity.csv`, `early_warning_validation.csv` | 8 / `p8-ew-1.0.0` | frozen Phase 7 score + Phase 6 periods |
| `/api/v1/findings` | `_validation` / `_finding` | Phase 8 `early_warning_summary.csv` (`section == FINDING`); F3 split per warning, coverage figures withheld | 8 / `p8-ew-1.0.0` | as above |
| `/api/v1/metadata/methodology` | `_methodology` | Phase 7 `risk_score_reference.json`, `risk_score_bands.csv`, `risk_score_feature_inventory.csv` | 7 / `p7-risk-1.1.0` | Apr–May 2025 reference |
| `/api/v1/metadata/provenance` | `verify` / `_provenance` | `phase-09-api/outputs/artifact_manifest.json` (+ Phase 8 `run_manifest.json`) | 9 | hashes generated from the files by `build_artifacts.py` |
| `/api/v1/metadata`, `/status`, `/limitations`, `/data-requirements` | `load_store` | `phase-09-api/config/analytical_contract.json` + the artifacts above | 9 contract (`p9-api-1.0.0`) | Build Status §3, §4, §12, §13; Phase 8 report §22, §25, §26 |
| `/api/v1/events*` | `event_store.EventStore` | SQLite `plant_events`, `plant_event_audit` | 9 (plant-supplied) | the plant; not derived from any artifact |

## Integrity chain

1. `build_artifacts.py` hashes every consumed file and writes the manifest. It stops if any Phase 6/7 file differs from the SHA-256 that Phase 8 recorded as its validated input (`phase-08-early-warning/outputs/run_manifest.json`).
2. On startup, `artifact_store.verify` re-hashes every file against the manifest. Any mismatch leaves the service not ready: `/ready` returns 503 and analytical routes return 503 `ANALYTICAL_ARTIFACT_UNAVAILABLE`.
3. The adapters read explicit column allow-lists and never compute scores, references, thresholds or resamples.
4. `run_phase9.py` hashes all Phase 1–8 files, `data/` and the 60 source workbooks (against `data/raw/source_manifest.csv`) before and after the run (gate G1).

## Columns deliberately not read

- Phase 7:
  - `afr_context` (retrospective labels);
  - `phase4_context`;
  - `historical_similarity` (circular with the Phase 6 periods);
  - `risk_score_diagnostics.parquet`;
  - non-operational rows.
- Phase 6:
  - post-event outcome, AFR and Phase 4 fields;
  - `plant_event_*` placeholders;
  - non-final candidates.
- Phase 8:
  - `early_warning_episodes.parquet` (W1–W5 episodes);
  - W1–W5 thresholds;
  - `LEAD_TIME` and `EMPIRICAL_ALERT_RATE` rows;
  - coverage, lead-time and alert-rate columns;
  - trajectories (used only to verify the build, never served).
