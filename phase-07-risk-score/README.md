# Phase 7: Deposit / Inefficiency Risk Score

**Status:** implemented. Pipeline gates G1–G8 pass, and the G9 review status is in `reviews/REVIEW_LOG.md`. The score is **not validated against any plant event**: no event ground truth exists. Phase 8 consumers filter `operational == True` (see `docs/FEATURE_CONTRACT.md`).

> An **EMPIRICAL POC RISK SCORE (0–100)**. It measures how strongly the current kiln condition resembles historical abnormal / inefficient process behaviour **relative to the frozen Apr–May 2025 reference**. It is based on five independent process-family evidence streams, and confidence is reported separately.
>
> It is **not**:
> - a deposit, ring or failure probability;
> - a plant limit;
> - a control or set-point recommendation.
>
> There is no event ground truth. The 12 Phase 6 periods are `EMPIRICAL_ABNORMAL_REFERENCE`, not labels.

Phase 7 builds no API, dashboard or early-warning evaluation. **Phase 8 has not been started.**

## Execution

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-07-risk-score/scripts
../../.venv/bin/python run_phase7.py --clean     # ~1 min; run twice: G8 compares every key output byte-for-byte
../../.venv/bin/python -B -m unittest discover -s ../tests -t ../tests     # 83 unit tests (pytest also works)
```

Prerequisite: Phases 1–6 have been run, so their outputs exist.

- **Read-only:** the source workbooks and every upstream file. Hashes are re-checked on every run.
- **Writes:** only `phase-07-risk-score/{outputs,reports,cache}`.

## Pipeline

| Step | Script | Writes |
|---|---|---|
| 1 | `feature_engineering.py` | Pure causal feature functions, and a cache of Phase 3 components, context, DQ counts, Phase 6 episodes (allowed fields only), AFR events and DQ windows. Also `risk_score_feature_inventory.csv` |
| 2 | `reference_builder.py` | Frozen Apr–May reference (`risk_score_reference.json`) and the confidence-variant references |
| 3 | `calibration.py` | Scores and components, reasons, confidence, bands, calibration, coverage, summary and data quality |
| 4 | `robustness.py` | 24 variants, 4 architecture candidates, negative controls, AFR / Phase 4 inclusion tests |
| 5 | `validation.py` | Gates G1–G7 and G9, including the mandatory leakage tests |
| 6 | `report_generation.py` | `reports/PHASE_7_RISK_SCORE_REPORT.{md,html}` and 4 figures |
| — | `run_phase7.py` | Orchestration, unit tests, G8 determinism, source / upstream snapshots |
| — | `risk_core.py`, `common.py` | Pure scorer (score, components, status, confidence, bands, reasons); config and paths |

## Score (docs/RISK_SCORE_SPEC.md)

**Per family** `d` (efficiency / Sp.Heat, combustion, thermal, draft / pressure, process variability):
- `S̃_d` is the trailing 1-h median of the RUNNING-masked Phase 3 component, and requires the current bucket to be valid.
- `a_d = 1 − 2^(−max(0, S̃_d − m_d)/(q_d − m_d))`, where `m_d` and `q_d` are the Apr–May median and P90.

**Score:** `risk_score = 100·(0.5·H + 0.25·C + 0.25·P)`, where:
- `H = 0.5·max a + 0.5·mean a` (fixed denominator 5, so a missing family can never inflate the score);
- `C = (n_abnormal − 1)/4`;
- `P` = share of the last 3 h since the last stop with `H ≥` its reference P90.

**Confidence** is a separate six-part mean (data quality, family coverage, baseline, operating state, temporal agreement, variant agreement). HIGH is capped to MEDIUM.

**Status** is `VALID`, `VALID_REDUCED_CONFIDENCE`, `INSUFFICIENT_DATA`, `NOT_SCORABLE`, `TRANSITION_CONTEXT` or `STOPPED`. There is no numeric score unless the status is VALID\*.

## Key results, bands and handoff

These are generated into the report (sections 1, 7, 8, 13) and `outputs/`. They are not repeated here, so they cannot go stale. Phase 8 consumes the files listed in `docs/FEATURE_CONTRACT.md`.

## Docs

| File | Content |
|---|---|
| `docs/RISK_SCORE_SPEC.md` | Contract (written before implementation, amendments marked) |
| `docs/FEATURE_CONTRACT.md` | Output schemas and allowed / prohibited use for Phase 8 |
| `docs/CALIBRATION_METHOD.md` | Bands, support rule, alert burden, coverage |
| `docs/VALIDATION_GATES.md` | G1–G9 and the leakage tests |
| `docs/LIMITATIONS.md` | Limitations |
