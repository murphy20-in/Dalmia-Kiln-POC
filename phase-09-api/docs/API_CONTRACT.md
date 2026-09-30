# Phase 9 API Contract (v1)

Read-only analytical evidence access layer and plant event annotation store. There is no live alerting, no prediction
and no probability output. The route table below must match `scripts/api_app.py::ROUTES`: `tests/test_contract.py`
fails if a route is added, removed or renamed without updating this file. The machine-readable form of the same table
(with every query parameter, type, default and enum) is generated from the implementation on every run as
`outputs/api_contract.json`. It is not typed by hand.

Base URL: `http://127.0.0.1:8009` (loopback by default; `DALMIA_KILN_API_HOST` / `DALMIA_KILN_API_PORT`).

## Endpoints

| Route | Kind | Purpose |
|---|---|---|
| `GET /health` | ops | Process liveness only. Says nothing about analytical artifacts |
| `GET /ready` | ops | 200 only when every artifact matches the manifest hash and the event store is reachable; otherwise 503 with the reason |
| `GET /api/v1/metadata` | analytical | Project, phase, artifact versions, periods, missing months, analytical state flags, validation state, major caveats, endpoint list |
| `GET /api/v1/metadata/status` | analytical | Analytical state flags, evidence status (contract and Phase 8 artifact), ground-truth / revalidation readiness |
| `GET /api/v1/metadata/provenance` | analytical | Artifact manifest (phase, version, SHA-256, bytes, status) and the O₂-excluded materialisation check |
| `GET /api/v1/metadata/limitations` | analytical | Data-quality and analytical limitations, missing months, timestamp semantics, operational-row quality counts |
| `GET /api/v1/metadata/methodology` | analytical | Phase 7 score definition, reference-relative bands, feature inventory; Phase 6 and Phase 8 definitions |
| `GET /api/v1/metadata/data-requirements` | analytical | Plant data required for validation, open plant questions, prohibited uses, revalidation threshold |
| `GET /api/v1/risk-scores` | analytical | Historical empirical POC risk score for one explicit variant (`primary` default, or `o2_excluded`) |
| `GET /api/v1/risk-scores/variant-comparison` | analytical | Primary and O₂-excluded scores side by side, each column labelled |
| `GET /api/v1/abnormal-periods` | analytical | The 12 Phase 6 KPI-derived empirical abnormal periods (`label_type = KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD`) |
| `GET /api/v1/validation/early-warning-historical` | analytical | Phase 8 historical validation results: primary endpoint `NOT_SUPPORTED`, horizons, controls, negative controls, O₂ sensitivity, load, censoring |
| `GET /api/v1/findings` | analytical | Phase 8 findings F1–F20 with their original evidence classes (F3 split per warning, coverage figures withheld) |
| `GET /api/v1/events` | event | List plant event annotations |
| `POST /api/v1/events` | event | Create an annotation (`X-Actor` header) |
| `GET /api/v1/events/{event_id}` | event | One annotation (deleted ones stay readable) |
| `PATCH /api/v1/events/{event_id}` | event | Update; body must carry `expected_version` (`X-Actor` header) |
| `DELETE /api/v1/events/{event_id}` | event | Soft delete (`X-Actor` header; `expected_version` query required) |
| `GET /api/v1/events/{event_id}/audit` | event | Append-only audit history |

No route accepts a file path. Anything not in this table returns `404 NOT_FOUND`. That includes `/alerts`,
`/predictions`, `/failure-probability`, `/deposit-probability` and `/early-warning`. A known path called with the wrong
method returns `405` with an `Allow` header.

## Query parameters

Parameters are strict:
- An unknown, repeated or empty parameter is rejected with `400`. It is never read as "all".
- `start` and `end` must be exactly `YYYY-MM-DDTHH:MM:SS`, naive plant-local time. An offset or `Z` is rejected, never converted.
- The window is `start <= timestamp < end`. For abnormal periods and events it is an overlap test.
- `start >= end` returns `422`.
- `limit` and `offset` are bounded integers. The defaults are 1000 / 5000 max for scores and 100 / 1000 max elsewhere.

`GET /api/v1/risk-scores` also takes:
- `variant`: `primary` or `o2_excluded`.
- `operational_only`: only `true` is served. `false` returns `422`, because non-operational rows and the Phase 7 diagnostics are not operational measurements.
- `reference_relative_band`, `confidence_band` and `score_row_status`: primary only. Combining them with `o2_excluded` returns `400`.

`GET /api/v1/abnormal-periods` takes `kpi_severity_class` (KPI-derived severity, not a plant judgement).

## Response envelope (analytical)

```json
{
  "api_version": "v1",
  "service_version": "p9-api-1.0.0",
  "data": "...",
  "pagination": {"limit": 1000, "offset": 0, "total": 9557, "returned": 1000, "has_more": true, "next_offset": 1000},
  "provenance": {"source_phase": 7, "artifact": "risk_scores.parquet", "artifact_version": "p7-risk-1.1.0",
                 "artifact_sha256": "…", "analytical_status": "EMPIRICAL_POC", "operational_status": "OPERATIONAL_ROWS_ONLY",
                 "empirical": true, "plant_supplied": false, "ground_truth_status": "NOT_AVAILABLE", "variant": "primary"},
  "interpretation": {"is_prediction": false, "is_alert": false, "is_probability": false, "is_live": false,
                     "is_retrospective": true, "early_warning_supported": false, "event_ground_truth_available": false},
  "disclaimer": "…",
  "query": {"…": "the validated parameters actually applied"}
}
```

- `provenance` is a list when several artifacts feed the response.
- Risk-score responses also carry:
  - `variant`: `variant_status`, `is_default`, `preferred: false` and the preference note;
  - `window_semantics`;
  - `data_extent`: first and last timestamp, row count, the months not scored, the `gap_rule`, and `gaps_in_page` (every step of more than 10 min within the page; break lines there).
- A risk-score row carries:
  - `timestamp`, `variant`, `empirical_risk_score`, `reference_relative_band`, `score_row_status` (Phase 7 `risk_status`: whether the row is valid, not a statement about risk);
  - `confidence` (`band`, `score`, `band_uncapped`, `cap_reason`, six `parts`);
  - `data_quality`;
  - `context` (reference state, operating state, load band and context);
  - `reasons` (primary, secondary, coded drivers);
  - `components` (magnitude / concurrence / persistence and per-family scores).
- An O₂-excluded row carries only `timestamp`, `variant`, `empirical_risk_score` and `reference_relative_band: null`. Bands, confidence and reasons belong to the primary score and are not defined for the variant.

The event responses use the same envelope with `interpretation = {is_plant_supplied: true, is_analytical_label:
false, is_prediction: false, is_alert: false}` and `provenance.source = PLANT_SUPPLIED_ANNOTATION`.

## Error envelope

```json
{"error": {"code": "VALIDATION_ERROR", "message": "…", "request_id": "…", "details": [{"field": "end_time", "issue": "…"}]}}
```

| HTTP | code | when |
|---|---|---|
| 400 | `INVALID_REQUEST` | unknown / repeated / malformed parameter, bad timestamp, malformed JSON, duplicate JSON keys, missing `X-Actor` or `Content-Length` |
| 404 | `NOT_FOUND` | unknown route or event id |
| 405 | `METHOD_NOT_ALLOWED` | known route, wrong method (`Allow` header) |
| 409 | `CONFLICT` | overlapping annotation with the same type, equipment and source; stale `expected_version`; change to a deleted annotation |
| 413 | `PAYLOAD_TOO_LARGE` | body > 16 384 bytes |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | body not `application/json` |
| 422 | `VALIDATION_ERROR` | semantically invalid body or window, `operational_only=false`, PATCH with no changes, DELETE without `expected_version` |
| 500 | `INTERNAL_ERROR` | unexpected server error (generic message; details only in the server log) |
| 503 | `ANALYTICAL_ARTIFACT_UNAVAILABLE` | an artifact or the manifest is missing, unreadable or fails its hash |
| 503 | `EVENT_STORE_UNAVAILABLE` | the event database is locked or unreachable (retry) |

Responses never contain a stack trace or an absolute filesystem path. `request_id` matches the `X-Request-ID`
response header and the server log line.

## Versioning

- Every data route is under `/api/v1`, and `/health` and `/ready` are operational.
- An additive change (a new field or a new optional parameter) stays in v1 and bumps `service_version`.
- Renaming or removing a field, changing a meaning or changing a default needs `/api/v2` next to v1, with v1 kept until Phase 10 has moved over.
- A change to the analytical artifacts (a new Phase 7 score version, a Phase 8 re-run) changes `artifact_version` and `artifact_sha256` in `provenance`, and the manifest must be rebuilt. The API refuses to serve files that differ from the manifest.
