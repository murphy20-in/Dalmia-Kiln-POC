# API Usage

## Build, validate, serve

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-09-api/scripts
../../.venv/bin/python -B run_phase9.py --clean     # build manifest + O2x, tests, gates, reports (run twice for G11)
../../.venv/bin/python -B api_app.py                # serve on http://127.0.0.1:8009
```

The service needs `outputs/artifact_manifest.json`, which `run_phase9.py` or `build_artifacts.py` creates. Without
it, the service still starts, but `/ready` and every analytical route return 503.

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `DALMIA_KILN_POC_ROOT` | repository root | where the phase folders are |
| `DALMIA_KILN_EVENTS_DB` | `phase-09-api/state/events.sqlite3` | plant event store |
| `DALMIA_KILN_API_HOST` | `127.0.0.1` | bind address (keep loopback unless an authenticating proxy is in front) |
| `DALMIA_KILN_API_PORT` | `8009` | port |

Tests alone:

```bash
cd phase-09-api/tests && ../../.venv/bin/python -B -m unittest discover -s . -t .
```

## Examples

```bash
B=http://127.0.0.1:8009
curl -s $B/ready
curl -s $B/api/v1/metadata/status                  # analytical state flags, evidence status, revalidation readiness

# one day of the primary score (start inclusive, end exclusive, naive plant-local time)
curl -s "$B/api/v1/risk-scores?start=2025-08-15T00:00:00&end=2025-08-16T00:00:00"

# the O2-excluded sensitivity variant must be asked for explicitly
curl -s "$B/api/v1/risk-scores?variant=o2_excluded&start=2025-08-15T00:00:00&end=2025-08-16T00:00:00"

# compact trend with both variants side by side (use this for charts)
curl -s "$B/api/v1/risk-scores/variant-comparison?limit=5000"

curl -s $B/api/v1/abnormal-periods                 # 12 KPI-derived periods (not plant events)
curl -s $B/api/v1/validation/early-warning-historical
curl -s "$B/api/v1/findings?classification=WEAK"

# plant annotation
curl -s -X POST $B/api/v1/events -H 'Content-Type: application/json' -H 'X-Actor: process.engineer' \
  -d '{"event_type":"COATING","start_time":"2025-08-15T08:00:00","end_time":"2025-08-15T14:00:00",
       "equipment":"kiln inlet","description":"coating seen during shift inspection","source":"SHIFT_REPORT",
       "source_reference":"shift log B, p.14","plant_confirmation":"CONFIRMED"}'
curl -s -X PATCH $B/api/v1/events/<event_id> -H 'Content-Type: application/json' -H 'X-Actor: process.engineer' \
  -d '{"severity":"MODERATE","expected_version":1}'
curl -s -X DELETE "$B/api/v1/events/<event_id>?expected_version=2" -H 'X-Actor: process.engineer'
curl -s $B/api/v1/events/<event_id>/audit
```

## Paging through a full series

Keep requesting with `offset = pagination.next_offset` until `has_more` is false. Order is by timestamp, so paging is
stable and repeatable. Results are never cut off silently: `pagination.total` always gives the full count.

## Reading a response correctly

- `interpretation` is the same on every analytical response: not a prediction, not an alert, not a probability, retrospective only.
- `variant.preferred` is false for both variants. Show the O₂-excluded series only as a labelled overlay.
- `reference_relative_band` is a quantile band of the Apr–May reference. Do not style it as an alarm.
- `data_extent.not_scored` lists the missing months. Draw gaps as gaps; never interpolate across them.
- Abnormal periods carry `label_type = KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD` and `is_plant_event = false`. Plant annotations carry `label_origin = PLANT_SUPPLIED`.
- Every analytical response carries `provenance.artifact_version` and `artifact_sha256`. Keep them with anything you export.
