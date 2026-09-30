# API integration

The UI calls only these Phase 9 routes, through the same-origin proxy:

| Page | Routes |
|---|---|
| Overview | `/api/v1/metadata`, `/metadata/status`, `/metadata/data-requirements`, `/abnormal-periods?limit=1`, `/events?limit=1`, `/risk-scores?limit=1` |
| Historical risk | `/risk-scores` or `/risk-scores/variant-comparison`, `/abnormal-periods`, `/events` |
| Abnormal periods | `/abnormal-periods`, `/risk-scores` for one period |
| Plant events | `/events`, `/events/{id}`, `/events/{id}/audit` |
| Validation | `/validation/early-warning-historical`, `/findings` |
| Data quality | `/metadata/limitations`, `/metadata`, `/metadata/data-requirements`, `/metadata/provenance` |
| Methodology | `/metadata/methodology`, `/metadata` |

`/health` and `/ready` are proxied and not used as a live status lamp.

Not requested, and not drawn: horizon result tables, warning-definition flags, coverage figures, lead-time figures, AUC. Finding evidence that matches those patterns is replaced with “Evidence text withheld in this view.” Finding titles from the API are shown with their Phase 8 class, including F16 (“Lead time to plant events”, class BLOCKED).

`preferred` is read from the response and shown as `false`. The O₂ series is labelled sensitivity.

Event enums are the Phase 9 contract lists. There is no enum route. Unknown fields are not sent.

Errors use the API `error.message` unless it contains a traceback, a home path, sqlite, or parquet. The fallback text is “Analytical service unavailable” or “could not be loaded”.
