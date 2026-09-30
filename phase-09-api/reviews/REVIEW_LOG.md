# Phase 9 Review Log

Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO. Status: RESOLVED / ACCEPTED_WITH_REASON / DEFERRED_WITH_REASON.
Revalidation = what was re-run after the action. Order of work: planner → implementation → python-reviewer →
mle-reviewer → cs-product-analyst → database-reviewer → Ponytail audit (`PONYTAIL_AUDIT_REPORT.md`).

## Planner and self-found (during build)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| PL-01 | planner | HIGH | The O₂-excluded score exists only inside Phase 8's 12 event windows; serving it needs either a Phase 8 change or a verified materialisation | `early_warning_trajectories.parquet` has `o2x_risk_score` only in the windows | `build_artifacts.py` calls Phase 8's unchanged `o2_excluded_score` once, masks it to primary operational rows (Phase 8 `make_signals`), and refuses to write unless all persisted Phase 8 values and the rank correlation are reproduced | RESOLVED | 1,501 values, max diff 0.0; ρ diff 0.0 |
| PL-02 | planner | MEDIUM | Module-name clashes with Phase 7 / 8 (`common`, `validation`, …) and `p8common` import side effects | `p8common.py` header | Phase 9 names are unique (`p9common`, `artifact_store`, …). Phase 7 / 8 code is imported only by `build_artifacts.py` in a child process, and by the wording scan in tests / G12 | RESOLVED | tests pass; upstream hashes unchanged |
| PL-03 | planner | MEDIUM | Do not expose `afr_context`, diagnostics, W1–W5 flags / thresholds, lead-time / coverage columns | Phase 8 report §26 | explicit column allow-lists in `artifact_store`; `test_horizon_results_carry_no_coverage_or_lead_time`, `test_no_forbidden_field_names_and_no_live_flags` | RESOLVED | tests pass |
| PL-04 | planner | MEDIUM | A bare `/validation/early-warning` path implies alerting | spec §27 | route named `/api/v1/validation/early-warning-historical`; `result_type = HISTORICAL_VALIDATION_RESULT` | RESOLVED | `test_route_table_has_no_prohibited_semantics` |
| PL-05 | planner | LOW | Plant data requirements exist only as a markdown table (Phase 8 report §25) | report §25 | static `config/analytical_contract.json` citing §25, hashed in the manifest; the revalidation threshold is checked against Phase 8 `min_events_primary` at build | RESOLVED | build check |
| S-01 | self | MEDIUM | The response key `coverage` (data extent) collides with the Phase 8 meaning of coverage, which must not be shown | `test_safety` FAIL | renamed to `data_extent` | RESOLVED | 54 tests OK |
| S-02 | self | LOW | A deeply nested JSON array was expected to be a 400; Python 3.14 parses it, so 422 (not an object) is correct | `test_security` FAIL | test accepts 400 or 422 for valid-but-non-object JSON and checks no leak | RESOLVED | 54 tests OK |
| S-03 | self | LOW | The Phase 8 wording scanner flagged two "must not" list lines (negation only in the heading) | G12 FAIL, first run | negation put on the same line | RESOLVED | G12 re-run |
| S-04 | self | LOW | Rank-correlation gate first compared a 6-dp rounded value; the Phase 8 CSV holds full precision | `build_artifacts.py` | compare unrounded, tolerance 1e-12 | RESOLVED | diff 0.0 |

## python-reviewer (verdict APPROVE-WITH-CHANGES → changes applied)

The reviewer's test run showed 503s because `analytical_contract.json` had been edited (S-03) after the manifest was built. That was the hash gate working as intended. The manifest was rebuilt.

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-PY1 | python-reviewer | MEDIUM | `^…$` route regex matched a trailing newline (`/health%0A` → 200); regex rebuilt per request | `api_app.Route.regex` | regex compiled once in `__post_init__`, matched with `fullmatch` | RESOLVED | `test_path_traversal_and_file_access_are_404` (+ `\n` cases) |
| R-PY2 | python-reviewer | LOW | `\d` accepted non-ASCII digits (`limit=٣`) | `_parse_value`, `TS_RE` | `[0-9]` in both | RESOLVED | `test_malformed_query_parameters` (Arabic-Indic, full-width digits) |
| R-PY3 | python-reviewer | MEDIUM | A malformed manifest or corrupt artifact crashed App construction instead of returning 503; the manifest write was not atomic | `verify`, `load_store`, `write_json` | `verify` / `load_store` map read errors to `ArtifactUnavailable`; `write_json` writes a temp file then `os.replace` | RESOLVED | `test_503_when_manifest_is_garbage` |
| R-PY4 | python-reviewer | LOW | Hash-then-read window (TOCTOU) | `verify` vs adapters | frozen artifacts, loopback service; documented in LIMITATIONS | ACCEPTED_WITH_REASON | — |
| R-PY5 | python-reviewer | MEDIUM | `/ready` swallowed the event-store failure cause | `ready()` | structured `log.exception` before returning not-ready | RESOLVED | tests pass |
| R-PY6 | python-reviewer | LOW | ROLLBACK could mask the original error; DB-locked → 500 | `_tx` | `_session`: rollback under `suppress(sqlite3.Error)`; `OperationalError` → 503 `EVENT_STORE_UNAVAILABLE` | RESOLVED | tests pass |
| R-PY7 | python-reviewer | LOW | No-op PATCH bumped the version and wrote an audit row | `_mutate` | `validate` rejects a PATCH with no field change (422) | RESOLVED | `test_noop_patch_is_rejected` |
| R-PY8 | python-reviewer | LOW | Inconsistent overlap semantics across periods / events / context | `api_app`, `event_store` | one rule, `event_store.overlaps` + `SQL_OVERLAP` ([start, end); an open end is an instant) | RESOLVED | `test_one_overlap_rule_back_to_back_and_instants` |
| R-PY9 | python-reviewer | LOW | `SOURCE_ROOT` hard-coded | `p9common` | `DALMIA_KILN_SOURCE_ROOT` override, current path as default | RESOLVED | G1 |
| R-PY10 | python-reviewer | LOW | `ARTIFACT_KEYS` dead code | `p9common` | deleted | RESOLVED | tests pass |
| R-PY11 | python-reviewer | LOW | `_count`, the WSGI `call` helper and the quiet handler were duplicated | several | `p9common.count` (Counter) and `api_app.QuietHandler` shared; `run_phase9.call` (6 lines) kept so the orchestrator does not import test code | RESOLVED | tests pass |
| R-PY12 | python-reviewer | LOW | Handlers untyped | `api_app` | `req: Req -> tuple[int, dict]` on every handler | RESOLVED | — |
| R-PY13 | python-reviewer | LOW | `sys.path.insert` inside a test method | `test_safety` | moved to `setUpModule` | RESOLVED | tests pass |
| R-PY14 | python-reviewer | LOW | Hard-coded total 9557 | `test_contract` | derived from the parquet | RESOLVED | tests pass |
| R-PY15 | python-reviewer | LOW | "reads never create events" was near-tautological | `test_events` | now asserts that neither the event rows nor the audit rows change | RESOLVED | tests pass |
| R-PY16 | python-reviewer | LOW | Traversal test missed trailing-newline / encoded cases | `test_security` | added `/health\n`, `/ready\n`, `/api/v1/metadata\n`, `%0a` | RESOLVED | tests pass |
| R-PY17 | python-reviewer | INFO | Review tables parsed by position; a format change could make G13 vacuous | `review_check` | `p9common.review_rows`: fixed header required and the column count checked (raises otherwise); shared by `run_phase9` and `phase9_report` | RESOLVED | G13 / G14 |
| R-PY18 | python-reviewer | INFO | f-string SQL uses only server-built column names; connections closed; stable order | `event_store` | none needed | ACCEPTED_WITH_REASON | — |

## mle-reviewer (verdict PASS-WITH-CONDITIONS → conditions cleared)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-M1 | mle-reviewer | MEDIUM | Full-series level was checked only through 1,501 event-window rows plus a rank-only Spearman | `build_artifacts` | added gate: June / July / August medians of the rebuilt series equal Phase 8's persisted `median_score_*` values (≤ 5e-7); the manifest records the months covered by the trajectories. Rank excess needs Phase 8's rank transform and was not re-implemented | RESOLVED | medians diff 0.0 |
| R-M2 | mle-reviewer | MEDIUM | O₂x provenance incomplete (cache and code hashes) | manifest | `inputs_sha256` of the 5 Phase 7 cache files and 5 Phase 7/8 code files; `method` states "one-off offline refit"; `variant_reference_persisted_upstream = false` (no NO_O2X entry in `risk_score_variant_references.json` to compare against) | RESOLVED | manifest |
| R-M3 | mle-reviewer | MEDIUM | F3 evidence served coverage figures, contradicting the docs | `/findings` | same fix as R-P1 | RESOLVED | `test_no_coverage_or_lead_time_figures_in_any_served_value` |
| R-M4 | mle-reviewer | MEDIUM | Event schema lacks onset basis, time precision and knowledge / entry timing for leakage-safe revalidation | `event_store` | optional `time_basis` (OBSERVED / ESTIMATED_ONSET / REPORTED), `time_precision`, `entry_kind`, `annotator_viewed_risk_score`; `created_at` is the entry time; the audit keeps full history. A frozen snapshot export is left to the revalidation phase | RESOLVED | `test_revalidation_fields_are_optional_and_validated` |
| R-L1 | mle-reviewer | LOW | Event overlap boundary inclusive vs `[start, end)` elsewhere | `list()` | unified rule (R-PY8) | RESOLVED | tests pass |
| R-L2 | mle-reviewer | LOW | Build-only `p8_trajectories` required at API startup; hash-then-read | `verify` | `BUILD_VERIFICATION_ONLY` artifacts are skipped by the API (checked at build); TOCTOU accepted (R-PY4) | RESOLVED | tests pass |
| R-L3 | mle-reviewer | LOW | Duplicate trajectory timestamps dropped without checking | `build_artifacts` | asserts overlapping windows carry identical values before dropping | RESOLVED | build passes |
| R-L4 | mle-reviewer | LOW | Staleness / re-run order brittle and undocumented | build | fail-closed behaviour kept; re-run order documented in LIMITATIONS. A check of `p8_*` files against Phase 8's own output hashes is deferred: Phase 8's `run_manifest.json` records input hashes only | DEFERRED_WITH_REASON | — |

## cs-product-analyst (verdict CONDITIONAL PASS → conditions cleared)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-P1 | cs-product-analyst | HIGH | F3 evidence text served coverage percentages (Phase 8 §26 MUST NOT) | `/findings` | F3 rows become F3.W1_RANK … F3.W5_MULTI_FAMILY; coverage figures replaced by "coverage figures withheld (Phase 8 section 26)"; class and binomial p kept; `evidence_redacted = true`; the build fails if the F3 text format changes; a value-level scan test was added | RESOLVED | new safety test |
| R-P2 | cs-product-analyst | HIGH | The O₂-excluded endpoint block (p 0.0455, own event set) looked equivalent to the primary | `/validation/early-warning-historical` | `comparable_to_primary = false`, `like_for_like_p_value` 0.0625 (from Phase 8), `like_for_like_event_set`, and a note (post-result amendment, not multiplicity-adjusted, analyser-dependent, not preferred) | RESOLVED | `test_phase8_primary_endpoint_stays_not_supported` |
| R-P3 | cs-product-analyst | MEDIUM | `classification_counts` acted as an aggregate; F3 id repeated; F8 read as support | `/findings` | counts removed; unique sub-ids; F4 / F8 `context_only` with Phase 8 §23 reasons | RESOLVED | `test_findings_keep_their_classifications` |
| R-P4 | cs-product-analyst | MEDIUM | "43/43 pass" beside NOT_SUPPORTED; censored slices unexplained | validation | renamed `phase8_integrity_checks` with "not a favourable result"; censoring `meaning` states that CENSORED slices are not evidence of precedence (F18) | RESOLVED | integrity test |
| R-P5 | cs-product-analyst | MEDIUM | In-range gaps (stops) not discoverable, so charts would join across them | `data_extent` | `gap_rule` + `gaps_in_page` (every step > 10 min) on risk-scores and variant-comparison | RESOLVED | `test_gaps_are_not_filled` |
| R-P6 | cs-product-analyst | MEDIUM | Duplicate rule used exact free-text equipment and blocked a corroborating second source | `_conflicts` | case- and space-insensitive equipment; `source` is part of the duplicate key, so a second source is accepted | RESOLVED | conflict test |
| R-P7 | cs-product-analyst | MEDIUM | No time precision / onset-vs-observation fields | schema | same as R-M4 | RESOLVED | tests pass |
| R-P8 | cs-product-analyst | MEDIUM | README handoff list missed §26 items | README | §26 MAY / MUST NOT table copied verbatim, plus the O₂-not-preferred and gaps rules | RESOLVED | G12 wording scan |
| R-P9 | cs-product-analyst | LOW | KPI and plant severities share values; three period times | `/abnormal-periods` | `kpi_severity_class` (field and filter); `time_fields_note` says which time to plot | RESOLVED | tests pass |
| R-P10 | cs-product-analyst | LOW | Route label and `risk_status: VALID` / uncapped HIGH could be misread | api | `risk_status` served as `score_row_status`. The route keeps `early-warning-historical` because the phase spec names a validation/early-warning endpoint and the suffix plus `result_type` mark it historical. `band_uncapped` is kept because it explains the confidence cap | RESOLVED | tests pass |
| R-P11 | cs-product-analyst | INFO | X-Actor attribution-only; plant wall-clock vs historian clock | events | every stored annotation carries `timestamp_basis` (historian clock); documented in EVENT_ANNOTATION and LIMITATIONS L12 | ACCEPTED_WITH_REASON | — |

## database-reviewer (verdict ACCEPT WITH FIXES → fixes applied)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-D1 | database-reviewer | MEDIUM | `INSERT OR REPLACE` bypassed the no-hard-delete rule | reviewer snippet | `events_no_replace` BEFORE INSERT trigger | RESOLVED | trigger test |
| R-D2 | database-reviewer | MEDIUM | Raw SQL could change identity / creation fields, revive deleted rows or skip versions | reviewer snippet | `events_update_guard` BEFORE UPDATE trigger | RESOLVED | trigger test |
| R-D3 | database-reviewer | MEDIUM | Timestamp format not enforced by the DB (a space broke the lexicographic order) | reviewer snippet | `GLOB` CHECK on `start_time` / `end_time` | RESOLVED | trigger test |
| R-D4 | database-reviewer | MEDIUM | `user_version` written, never read | `__init__` | read at startup; newer than the code → refuse; 0 → create v1 | RESOLVED | tests pass |
| R-D5 | database-reviewer | LOW | Duplicate rule closed on both ends; `list()` boundary inconsistent | SQL | unified rule (R-PY8) | RESOLVED | overlap test |
| R-D6 | database-reviewer | LOW | Equipment match exact and case-sensitive; NULL behaviour undocumented | `_conflicts` | case / space-insensitive; NULL matches only NULL, documented | RESOLVED | conflict test |
| R-D7 | database-reviewer | LOW | Lock timeout → 500; rollback could mask errors | `_tx` | R-PY6 | RESOLVED | tests pass |
| R-D8 | database-reviewer | LOW | DELETE without `expected_version` | api | now required (422 when missing, 409 when stale) | RESOLVED | CRUD test |
| R-D9 | database-reviewer | LOW | Rollback journal; no backup note; count / page on separate connections | store | WAL; backup command documented; count and page read in one transaction | RESOLVED | tests pass |
| R-D10 | database-reviewer | LOW | No index for type filters | schema | `ix_plant_events_type (status, event_type, start_time)` | RESOLVED | — |
| R-D11 | database-reviewer | INFO | Independence fields for revalidation | schema | R-M4 fields, including `annotator_viewed_risk_score` | RESOLVED | tests pass |
