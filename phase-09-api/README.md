# Phase 9 — API / Analytical Service

A read-only analytical evidence API over the frozen Phase 6–8 artifacts, plus a plant event annotation store.

- **Not included:** an alerting engine, a prediction service, probability outputs, live warning flags, a dashboard.
- **Phase 8 result:** the frozen Phase 7 score did **not** support an early-warning claim against the available KPI-derived abnormal periods (primary endpoint `NOT_SUPPORTED`). The service states this in machine-readable form (`/api/v1/metadata/status`) and in every analytical response.

## Layout

```text
phase-09-api/
├── README.md
├── config/analytical_contract.json    analytical state flags, limitations, plant data requirements (hashed)
├── docs/                              API_CONTRACT, API_USAGE, ANALYTICAL_SEMANTICS, EVENT_ANNOTATION, LIMITATIONS, DATA_LINEAGE
├── scripts/
│   ├── p9common.py                    paths, env config, artifact registry, deterministic JSON
│   ├── artifact_store.py              hash-verified, allow-listed read-only adapters
│   ├── event_store.py                 SQLite plant annotations + append-only audit
│   ├── api_app.py                     WSGI app and route table (run it to serve)
│   ├── build_artifacts.py             offline: O2-excluded materialisation + artifact manifest
│   ├── run_phase9.py                  orchestrator: build, service checks, tests, determinism, gates G1-G15
│   └── phase9_report.py               writes reports/PHASE_9_API_ANALYTICAL_SERVICE_REPORT.md
├── tests/                             contract, integrity / temporal, events, security, safety (unittest)
├── reviews/                           REVIEW_LOG.md, PONYTAIL_AUDIT_REPORT.md
├── outputs/  (gitignored, generated)  artifact_manifest.json, o2_excluded_scores.parquet, api_contract.json, validation_report.{json,md}
├── reports/  (gitignored, generated)  PHASE_9_API_ANALYTICAL_SERVICE_REPORT.md
└── state/    (gitignored, plant data) events.sqlite3 — never deleted by --clean
```

## Run

```bash
cd phase-09-api/scripts
../../.venv/bin/python -B run_phase9.py --clean     # twice: G11 compares with the previous clean run
../../.venv/bin/python -B api_app.py                # http://127.0.0.1:8009
```

## Dependencies

None added. The service uses the stdlib (`wsgiref`, `sqlite3`, `json`) and the pandas / pyarrow already in
`requirements.txt`. The offline build step imports Phase 7 / 8 code read-only, in a child process.

## Phase 10 handoff

Phase 10 may consume:
- the historical empirical risk score;
- the O₂-excluded overlay (`/risk-scores/variant-comparison`);
- the KPI-derived abnormal periods;
- the Phase 8 validation findings;
- plant event annotations;
- metadata, provenance and data-quality status.

Phase 9 is not a live alerting source. The Phase 8 report §26 table applies unchanged:

| Phase 9 / 10 MAY show | Phase 9 / 10 MUST NOT show |
|---|---|
| the historical score trend with the O₂-excluded overlay and a fixed 'retrospective, not an early warning' disclaimer | live W1–W5 flags or alarms of any kind |
| the 12 periods labelled 'KPI-derived abnormal periods (not plant events)' | Phase 7 band colours (ELEVATED / HIGH) styled as alarms |
| the finding classes with their evidence text | lead-time numbers or coverage percentages |
| an event-annotation tool so the plant can mark coating / ring / cleaning events on the timeline | the Phase 7 AUC 0.868, the word 'prediction', or `afr_context` in any live view |

Also carried from Phase 8 and this phase:
- no deposit, ring or failure probability is provided;
- the O₂-excluded series is never presented as preferred or as a replacement;
- `gaps_in_page` steps are drawn as gaps.
