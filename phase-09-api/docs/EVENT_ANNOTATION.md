# Plant Event Annotation

The plant uses this store to record what actually happened: coating, rings, deposits, cleaning, maintenance,
stoppages, feed reductions and analyser calibrations. These records are plant-supplied ground-truth candidates. They
are kept apart from every analytical label so that the frozen Phase 8 protocol can later be re-run against them.

## Rules that keep labels separate

1. Only a person, through `POST` / `PATCH` / `DELETE /api/v1/events`, creates or changes an annotation. No score, band, Phase 6 period or background job ever writes one.
2. `label_origin` is always `PLANT_SUPPLIED`. A `CHECK` constraint enforces this, so a direct SQL update to anything else fails.
3. `analytical_label` is always `null`. Requests that send `analytical_label`, `label_origin`, `status`, `created_by`, `risk_score` or any other unknown field are rejected with `422`.
4. `analytical_context.overlapping_kpi_derived_abnormal_periods` lists the Phase 6 periods whose window overlaps the annotation. It is computed on every read, never stored, and never used to set `event_type`.

## Fields

| Field | Required | Rule |
|---|---|---|
| `event_id` | server | UUID4 |
| `event_type` | yes | `COATING`, `RING`, `DEPOSIT`, `CLEANING`, `MAINTENANCE`, `STOPPAGE`, `FEED_REDUCTION`, `ANALYSER_CALIBRATION`, `PROCESS_UPSET`, `OTHER` |
| `start_time` | yes | `YYYY-MM-DDTHH:MM:SS`, naive plant-local time (the historian clock) |
| `end_time` | no | same format, strictly after `start_time`; `null` = end unknown / instantaneous |
| `description` | yes | 1–2000 characters, not blank; newlines allowed; other control characters rejected |
| `source` | yes | `PLANT_LOG`, `SHIFT_REPORT`, `MAINTENANCE_RECORD`, `INSPECTION`, `OPERATOR_RECALL`, `OTHER` |
| `source_reference` | no | ≤ 200 characters (log book page, work-order number, document id) |
| `equipment` | no | ≤ 100 characters (for example "kiln inlet", "riser", "cooler") |
| `severity` | no | `MINOR`, `MODERATE`, `MAJOR` (the plant's judgement) |
| `plant_confirmation` | no | `CONFIRMED`, `PROBABLE`, `UNCONFIRMED` |
| `time_precision` | no | `EXACT`, `WITHIN_HOUR`, `WITHIN_SHIFT`, `WITHIN_DAY` (how precise the times are) |
| `time_basis` | no | `OBSERVED` (when seen), `ESTIMATED_ONSET` (when it is believed to have begun), `REPORTED` |
| `entry_kind` | no | `CONTEMPORANEOUS` (logged at the time) or `RETROSPECTIVE` (entered later, e.g. from recall) |
| `annotator_viewed_risk_score` | no | `true` / `false` / `null`: whether the person entering it had looked at the risk score (needed to judge independence) |
| `timestamp_basis`, `label_origin`, `status`, `version`, `created_at/by`, `updated_at/by` | server | set by the service |

Fields that plant users may not reliably know (end time, equipment, severity, confirmation) are optional.

## Timestamps

- Event times use the same timezone-naive clock as the historian export, which has no timezone.
- An offset or `Z` is rejected with `422`. It is never converted, and nothing is inferred.
- Invalid dates (for example 2025-02-30), a missing seconds field and `start >= end` are rejected. Nothing is corrected, rounded or interpolated.
- `created_at`, `updated_at` and audit times are server UTC with an explicit `Z`. They record when the entry was made, not when the event happened.

## Conflicts and concurrency

- `409 CONFLICT` if an ACTIVE annotation with the same `event_type`, `equipment` (compared case- and space-insensitively; no equipment matches only no equipment) and `source` overlaps it. That usually means a duplicate entry. A second source for the same event (for example an inspection confirming a shift report) and different event types are accepted.
- Overlap uses one rule everywhere: [start, end), and an annotation without an end is an instant (see ANALYTICAL_SEMANTICS.md). Back-to-back entries (one ends 10:00, the next starts 10:00) do not conflict.
- A `PATCH` that changes nothing is rejected (`422`), so the audit only records real changes.
- `PATCH` must carry `expected_version`. A stale version returns `409` with `current_version`.
- A deleted annotation cannot be modified (`409`).
- `DELETE` requires `?expected_version=N` (stale → `409`, missing → `422`). It is a soft delete (`status = DELETED`, version + 1). The row stays readable (`GET /events/{id}`, `GET /events?status=DELETED`). A trigger forbids a hard delete.

## Audit trail

`GET /api/v1/events/{id}/audit` returns every `CREATE`, `UPDATE` and `DELETE` with `at`, `actor`, and the full
`old_value` / `new_value` records. The audit table is append-only: triggers abort any `UPDATE` or `DELETE` on it, and
no API route changes it.

`X-Actor` (required for mutations; 1–100 characters from `[A-Za-z0-9 ._@-]`) records who made the change. It is
attribution, not authentication. See `LIMITATIONS.md`.

## Future revalidation (data contract only)

The schema is designed so that a later phase can answer these questions, and Phase 9 does not answer them itself:

- which plant events occurred, and when (`event_type`, `start_time`, `end_time`, `plant_confirmation`);
- which analytical conditions preceded them (join `start_time` to `/api/v1/risk-scores`);
- how many are evaluable (Phase 8 decides this; `/metadata/status` reports `evaluable_event_count = 0` and the minimum of 8);
- which overlap the Phase 6 periods (`analytical_context`);
- which are independent (the overlap and conflict rules, and `equipment`).

Phase 9 does not re-run Phase 8, retrain anything or modify Phase 7.

## Storage

SQLite (WAL journal) at `phase-09-api/state/events.sqlite3` (override: `DALMIA_KILN_EVENTS_DB`). The database itself also refuses: another format for times, a change to `event_id` / `created_at` / `created_by` / `timestamp_basis`, an update without version + 1, reviving a deleted row, `INSERT OR REPLACE` over an existing row, a hard delete, and any change to the audit table. `PRAGMA user_version` is checked at startup, and a database newer than the code is refused. Back up with `sqlite3 events.sqlite3 ".backup events-YYYYMMDD.sqlite3"`. A locked database returns `503 EVENT_STORE_UNAVAILABLE`. The file is gitignored and plant
data. `run_phase9.py --clean` never deletes it, and every test and validation run uses a throwaway database. Back it
up like any other plant record.
