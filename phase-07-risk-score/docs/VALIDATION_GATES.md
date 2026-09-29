# Phase 7 Validation Gates

The gates are implemented in `scripts/validation.py` (G1–G7, G9) and `scripts/run_phase7.py` (G8, plus the run-time G1 snapshots). The results are in `outputs/risk_score_validation.csv` with columns `gate, check, check_type, result, evidence`.

**Result values:**

| Result | Meaning |
|---|---|
| `PASS` / `FAIL` | the check passed or failed |
| `NOT_MET_REPORTED` | a pre-declared expectation the data did not meet; reported, never hidden, and not a pipeline failure |
| `NOT_MET_PENDING_REVIEW` | G9 before the review log is complete |
| `INFO` | descriptive only |

The pipeline exits non-zero on any `FAIL`.

**Check types:**
- `INDEPENDENT`: re-derives a result with separate code or a perturbation experiment.
- `CONSISTENCY`: compares outputs with each other.

| Gate | Checks |
|---|---|
| **G1 Source integrity** | All 60 manifest workbooks exist with their Phase 1 SHA-256. Upstream validation files have no FAIL (Phase 3 all PASS). Every consumed upstream file hashes as recorded in the frozen reference. The 12 final periods are present. *Run-time:* the source is hashed before and after the run (SHA-256, size, mtime). Phase 1–6 outputs, the Phase 3–6 scripts / tests / cache / reports (including directory listings) and `data/` are snapshotted before and after |
| **G2 Schema integrity** | Required outputs and columns exist. Timestamps are datetime, unique, sorted and on the regular 10-min Phase 3 grid. Datatypes are correct. Feature provenance is complete: every scoring feature has a SCORING / CAUSAL inventory row, and no FORBIDDEN, EVALUATION_ONLY or RETROSPECTIVE feature is scored |
| **G3 Temporal integrity** | See the leakage tests below, plus the in-process recomputation matching `risk_scores.parquet` and the Phase 3 upstream leakage rows |
| **G4 Score integrity** | `operational` == out of sample AND VALID\*. `risk_score` is in [0, 100] exactly on operational rows and NaN elsewhere; in-sample scores appear only in the diagnostics file. Confidence is in [0, 1] and never HIGH. Bands and statuses come from the allowed sets. Components sum to the score (1e-5). The primary reason is the largest contributor (suffixed `_BELOW_THRESHOLD` if inactive). Secondary reasons contain no AFR / Phase 4 codes. Reasons and scores are deterministic. The reason table is consistent with the components |
| **G5 Statistical integrity** | Robust quantile anchors. Bands with block-bootstrap CIs and the support rule. April-fit / May-check exceedance. Rank stability (median Spearman ≥ 0.80). Pre-declared materiality for every variant (NOT_MET_REPORTED if any is SENSITIVE). Negative controls NC1 / NC2 (p < 0.05). AFR / Phase 4 inclusion decisions re-derived. Family correlation reported. Candidate selection follows the rule. Calibration assumptions disclosed |
| **G6 Empirical period coverage** | All 12 final periods are scored and labelled `EMPIRICAL_ABNORMAL_PERIOD_COVERAGE`. Coverage is reported and never called accuracy or a false-positive rate. Phase 6 severity / confidence are evaluation metadata only. The unsupported-claim scanner is clean over the docs, key CSVs and labels; the report is scanned by `report_generation.py` and by the run |
| **G7 Data-quality integrity** | No 99999 / 9999 (any tag) or −273 (°C tags) reaches a scored tag. Missing families never raise H or C. Within-window missingness is quantified (INFO). 1–2 usable families give INSUFFICIENT_DATA with no score. No score for any bucket entirely inside a Phase 1 long gap or the frozen window. Persistence resets at every segment start. September gets no score, operational or diagnostic. `conf_data_quality ≤ 0.5` forces LOW confidence. Tag-level dropout (applied before the Phase 3 family averaging) is quantified (INFO). The suspect ambient-O₂ readings are quantified (INFO). The references were built by the current code (G1) |
| **G8 Reproducibility** | All steps complete from `--clean`. Unit tests pass. Every key output and the first-pass report are byte-identical to the previous clean run |
| **G9 Review** | `reviews/REVIEW_LOG.md` records the planner, senior data scientist, statistical, data-quality, Python, MLE, product and Ponytail reviews, with no OPEN finding |

## Mandatory leakage tests (G3 and `tests/test_temporal_leakage.py`)

| # | Requirement | Implementation |
|---|---|---|
| 1 | No future timestamp contributes to a score | Truncation at 8 cut points gives identical scores, bands, confidence, status and reasons |
| 2 | No post-event field contributes | Post-event columns are absent from the grid and episodes. The inventory marks them FORBIDDEN. Injecting random post-event fields leaves the reference and scores unchanged |
| 3 | No future calibration / reference value contributes | The reference refit is identical with all post-reference data randomised or removed |
| 4 | Changing future data does not alter historical scores | Random data after T leaves every score ≤ T identical (7 cuts) |
| 5 | Changing post-event rows does not alter pre-event scores | Randomising the 6 h after each Phase 6 period leaves every score up to the period end identical (12 periods) |
| 6 | Changing the scoring period does not modify the frozen reference | Same experiment as 3, and the result equals the saved reference |
| 7 | Changing data after T does not modify the score at T | Covered by 1 and 4, plus unit-level boundary tests |

The tests fail if a post-event feature enters the scoring feature set: G2 and `test_temporal_leakage` assert the inventory, the grid columns and the scorer inputs.
