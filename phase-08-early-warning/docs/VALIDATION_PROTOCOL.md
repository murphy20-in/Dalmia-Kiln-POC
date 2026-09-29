# Phase 8 — Validation Protocol

How a Phase 8 run is executed and judged. The analytical contract is `EARLY_WARNING_VALIDATION_SPEC.md`.

## Run

```bash
cd phase-08-early-warning/scripts
../../.venv/bin/python run_phase8.py --clean   # run 1 (deletes only phase-08 outputs/, reports/, cache/)
../../.venv/bin/python run_phase8.py --clean   # run 2: G11 compares its artifacts byte-for-byte with run 1
../../.venv/bin/python -B -m unittest discover -s ../tests -t ../tests
```

`run_phase8.py` records the key-output and first-pass-report hashes from the previous run, then:

1. snapshots the source workbooks (sha256 / size / mtime), all Phase 1–7 artifacts and the Phase 7 frozen files;
2. `analyse()` (pure: reads Phase 6 / 7 artifacts, returns tables) → `write()` → `outputs/`;
3. analysis-only gates → first-pass report (its bytes are what G11 compares; no run-dependent text);
4. unit tests in a subprocess; after-snapshots;
5. full gates G1–G12 (with run information) → `early_warning_validation.csv` → final report;
6. exit 1 if any gate FAILs.

## Stages

CONTRACT (spec, before results) → AUDIT (inputs, rescore, reference reproduction) → TEMPORALIZE (T0, windows,
controls) → TEST (primary + secondary endpoints) → NEGATIVE-CONTROL (NC1–NC5) → ROBUSTNESS (load, O₂, months, LOEO,
reference-free rank, KPI baseline, censored / valid-only, block length) → FALSIFY (§11 of the report) → REVIEW
(`reviews/REVIEW_LOG.md`) → FIX → REVALIDATE (two clean runs) → DOCUMENT → STOP.

## Judging results

- The **primary endpoint** is judged only by its pre-declared rule (spec §4). Everything else is secondary.
- **Gates test integrity, not favourable answers.** A NOT_SUPPORTED primary endpoint with all gates PASS is a
  complete, valid Phase 8 outcome.
- `PENDING` gate rows exist only in the first-pass report (run-dependent checks); the final table has none after the
  second clean run.
- Every major finding carries exactly one class: SUPPORTED / WEAK / NOT_SUPPORTED / INSUFFICIENT_DATA / BLOCKED.
- Amendments after results must be recorded in spec §16 with the reason and their effect on the primary result.

## Gates

| Gate | What is checked |
|---|---|
| G1 input contract | Phase 7 artifacts present, score version, 12 periods on the grid, operational-only, L6 (rescore + reference reproduction + frozen hashes), source / upstream unchanged |
| G2 temporal integrity | L1 (truncation of the Phase 7 score; randomised future for every Phase 8 signal), L2 (NC5), L5 (future grid perturbation), L7 (`afr_context`) |
| G3 event-window integrity | T0 = onset, windows end at T0, trajectories ≤ T0, DQ status set, event-window symmetry |
| G4 control integrity | independent interval-level re-check of every eligible control (60 min, 24 h); per-month pool size |
| G5 threshold integrity | L3 (reference and month-holdout chronology), L4 (leave-one-out invariance), threshold sources |
| G6 negative control | NC1 / NC2 nulls centred on 0, NC4 single draw reported (not a criterion), NC3 reported |
| G7 O₂ robustness | key results repeated for the O₂-excluded variant; primary never replaced |
| G8 load robustness | analyses A–D at every horizon for both variants |
| G9 month robustness | June / July / August and leave-one-month-out for both variants |
| G10 event leave-out | LOEO endpoint for every evaluable period; event-tuned thresholds leave-one-out only |
| G11 reproducibility | two clean runs byte-identical (10 outputs + first-pass report MD / HTML); unit tests pass |
| G12 claim integrity | finding classes; unsupported-claim scan of column names, findings, docs and report |
