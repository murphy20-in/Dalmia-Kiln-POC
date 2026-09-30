# Analytical Semantics

This service exposes four kinds of content that must stay separate. Every response says which one it carries:
`provenance.analytical_status`, `label_type` or `label_origin`, and the `interpretation` block.

## Phase 7 — empirical POC risk score

- It is the frozen score `p7-risk-1.1.0`, 0–100.
- It measures how strongly the current kiln condition resembles abnormal or inefficient process behaviour, relative to the Apr–May 2025 reference.
- It is **not** a probability, a prediction, or a deposit, ring or failure likelihood. It is not a plant limit.
- The API exposes it as a historical trend of `operational == True` rows only. Non-operational rows and `risk_score_diagnostics.parquet` are never served.
- `reference_relative_band`:
  - LOW, ELEVATED (≥ the Apr–May P75) and HIGH (≥ the P90).
  - It is an empirical quantile band, **not** an alarm level.
  - HIGH covers about half of August operational time, so it is not a rare-event flag.
- Confidence is a separate six-part measure, capped at MEDIUM because there is no event ground truth.

**O₂-excluded variant** (`variant=o2_excluded`, `variant_status = SENSITIVITY_ANALYSIS`):
- It is the Phase 8 validation variant with the `Kiln-I!X` analyser removed.
- It is returned only when you ask for it, or in the labelled `variant-comparison`.
- It never replaces the primary score. `preferred = false` for both variants until the plant explains the analyser.
- Bands, confidence and reasons are properties of the primary score only.

## Phase 8 — early-warning validation: NOT_SUPPORTED

Phase 8 did not support an early-warning claim against the available KPI-derived abnormal periods.

- **Primary endpoint:** the median rank excess over (T0 − 60 min, T0] vs month-matched ordinary running.
  - PE +0.051, 95 % CI −0.087 to +0.119, p 0.118.
  - 10 of 12 periods evaluable, 6,641 controls.
  - Status `NOT_SUPPORTED`.
- **O₂-excluded variant:** `WEAK`, and dependent on the analyser.

Classifications (SUPPORTED, WEAK, NOT_SUPPORTED, INSUFFICIENT_DATA, BLOCKED) are served exactly as Phase 8 wrote them. There is no aggregate score, and horizons are not ranked.

W1–W5 appear only as historical validation classifications with `is_live_flag = false`. Nothing in the API computes a warning flag for any timestamp. Coverage, lead-time and alert-rate columns are not served. The F3 findings are served as F3.W1_RANK … F3.W5_MULTI_FAMILY with the class and binomial test kept and the coverage figures withheld (`evidence_redacted = true`, Phase 8 §26); a test scans every served string for coverage or lead-time figures.

The O₂-excluded primary-endpoint block carries `comparable_to_primary = false`: its p 0.045 is on its own 12-period set (a post-result amendment, not multiplicity-adjusted); on the primary's 10 periods it is `like_for_like_p_value` 0.0625. `phase8_integrity_checks` (43/43) are pipeline integrity checks, not a favourable result. F4 and F8 carry `context_only = true` (Phase 8 §23), and the findings response has no class counts.

The validation route is named `/validation/early-warning-historical` so that the path itself says "historical results".

## Phase 6 — KPI-derived empirical abnormal periods

- These are 12 periods (Jun–Aug) derived from the Phase 3 POC KPI and process measurements.
- `label_type = KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD`, `is_plant_event = false`, `event_ground_truth_status = NOT_AVAILABLE`.
- They are **not** plant events, incidents, deposits, rings or failures, and no endpoint name implies that they are.
- `onset_time` is the Phase 8 T0 (CUSUM onset). 6 of the 12 onsets are censored.
- `kpi_severity_class` and `kpi_period_type` are KPI-derived context, not plant judgements (plant annotations have their own `severity`).

## One interval rule

A period or annotation with an end is the half-open interval [start, end); an annotation without an end is the instant start. Two intervals overlap if each starts before the other ends; an instant overlaps an interval if start ≤ t < end, and another instant if equal (`event_store.overlaps`, used for query windows, duplicate detection and the analytical context).

## Plant annotations — plant-supplied event labels

- These are records the plant enters: coating, ring, cleaning, maintenance, stoppage and other events.
- `label_origin = PLANT_SUPPLIED`, and the database enforces it.
- They are independent ground-truth candidates for a future re-run of the frozen Phase 8 protocol.
- Nothing analytical writes them:
  - no score, band or Phase 6 period ever creates or changes an annotation;
  - `analytical_label` is always null;
  - `analytical_context` (which KPI-derived periods overlap the annotation) is computed on read and never stored.

## The interpretation block

Every analytical response has:

```json
{"is_prediction": false, "is_alert": false, "is_probability": false, "is_live": false, "is_retrospective": true,
 "early_warning_supported": false, "event_ground_truth_available": false}
```

`GET /api/v1/metadata/status` exposes the same state in machine-readable form, from `config/analytical_contract.json`:
`early_warning_supported`, `alerting_enabled`, `prediction_enabled` and `plant_event_ground_truth_available`, all
false.
