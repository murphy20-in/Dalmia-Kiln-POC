# Phase 9 Ponytail Audit

Audit: `ponytail:ponytail-audit`, run by a read-only review agent. Scope: `phase-09-api/` only (scripts, tests, config, docs, README).
Areas covered: API security, path handling, schema validation, error handling, logging, event persistence, analytical
artifact integrity, configuration, tests, documentation. There were no CRITICAL or HIGH findings. The Status and
Resolution columns were added after the fixes were applied.

| ID | Severity | Area | Location | Finding | Recommendation | Status | Resolution |
|---|---|---|---|---|---|---|---|
| PT-01 | MEDIUM | Configuration | p9common.py SOURCE_ROOT | Source path hard-coded; G1 fails on another checkout | env override | RESOLVED | `DALMIA_KILN_SOURCE_ROOT` (R-PY9) |
| PT-02 | LOW | Configuration / boundary | run_phase9.build docstring | Docstring says the orchestrator never imports Phase 7/8, yet `docs_check` imports `p8common` | reword or move | RESOLVED | docstring states the wording-scanner exception |
| PT-03 | LOW | Event persistence | event_store PATCH | Version-only PATCH bumps the version and writes audit | reject no-op | RESOLVED | 422 on no-op (R-PY7) |
| PT-04 | LOW | Event persistence / tests | DELETE | `expected_version` optional; no stale-DELETE test | test | RESOLVED | required; stale → 409 tested (R-D8) |
| PT-05 | LOW | Error handling | event_store | DB locked → 500 | map to 503 | RESOLVED | `EVENT_STORE_UNAVAILABLE` (R-PY6) |
| PT-06 | LOW | Schema / semantics | overlap | Three different interval rules | one rule | RESOLVED | `overlaps` / `SQL_OVERLAP` (R-PY8) |
| PT-07 | LOW | API security | serve() | No socket timeout on single-threaded wsgiref | handler timeout | RESOLVED | `QuietHandler.timeout = 30` |
| PT-08 | LOW | Analytical integrity | verify vs adapters | Hash-then-read TOCTOU | accept or hash parsed bytes | ACCEPTED_WITH_REASON | frozen artifacts, loopback service; documented |
| PT-09 | LOW | Tests / orchestration | review parsing | Regex + positional parsing duplicated | shared helper | RESOLVED | `p9common.review_rows` with header check |
| PT-10 | LOW | Over-engineering | `_count` ×2 | duplicate of Counter | Counter once | RESOLVED | `p9common.count` |
| PT-11 | LOW | Over-engineering | `call`, quiet handler ×2 | duplication | share | RESOLVED | `api_app.QuietHandler` shared; `run_phase9.call` kept so the orchestrator does not import test code |
| PT-12 | LOW | Over-engineering | Route.regex | recompiled per request | compile once | RESOLVED | `__post_init__` (R-PY1) |
| PT-13 | INFO | Over-engineering | ARTIFACT_KEYS | unused | delete | RESOLVED | deleted |
| PT-14 | INFO | Over-engineering | update() | duplicate dict check | delete | RESOLVED | removed; `validate` checks |
| PT-15 | INFO | Over-engineering | render_md | duplicates JSON / report | consider dropping | ACCEPTED_WITH_REASON | the phase spec §75 requires `outputs/validation_report.md` |
| PT-16 | INFO | API security | X-Actor | no authentication | accept, proxy for shared use | ACCEPTED_WITH_REASON | POC scope; loopback default; LIMITATIONS |
| PT-17 | INFO | Documentation | docs/ | all docs present, route table test-synced | none | ACCEPTED_WITH_REASON | no change needed |

**Summary (from the audit).** Phase 9 is already lean: stdlib WSGI and sqlite3, no framework and no new dependency.
One route table drives dispatch, the 404 / 405 responses and the contract, and the database enforces its invariants.
Possible cut: about 30–45 lines, taken in PT-10 to PT-14.

**Must not be removed (audit):**
- the SHA-256 manifest, `verify()` and 503;
- the O₂x gates;
- the column allow-lists;
- the error / provenance / interpretation envelopes;
- strict query and body validation;
- the CHECK constraints and triggers, and `BEGIN IMMEDIATE`;
- `expected_version`;
- JSON logging, `/health` and `/ready`, and pagination;
- the O₂-excluded endpoint and the comparison endpoint;
- the five test modules and the six docs;
- G1–G15 and the generated report.
