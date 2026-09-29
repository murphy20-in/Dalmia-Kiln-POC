# Phase 7 Review Log

**Scope:** Phase 7 Deposit / Inefficiency Risk Score (`p7-risk-1.1.0`). Every finding is recorded with its disposition.

**Status values:**

| Status | Meaning |
|---|---|
| `RESOLVED` | fixed and re-validated |
| `ACCEPTED` | a documented limitation or a deliberate decision, with the reason |
| `DEFERRED` | documented debt with no effect on results |

No finding is left OPEN.

**Rounds:**

| Round | Reviewers | Verdict |
|---|---|---|
| Planning | planner (before implementation) | — |
| Round 1 | python-reviewer | Approve-with-changes |
| | mle-reviewer | PASS-WITH-CONDITIONS |
| | senior-data-scientist | APPROVE-WITH-CHANGES |
| | statistical-analyst | APPROVE-WITH-CHANGES |
| | data-quality-auditor | PASS-WITH-CONDITIONS |
| | product (cs-product-analyst + product-analytics) | APPROVE-WITH-CHANGES |
| After round 1 | Ponytail audit | — |

Implementation-time findings raised by the validation gates themselves are listed as reviewer "implementation gates".

**"Re-run" in the table** means the full pipeline after the fixes (`run_phase7.py --clean`, twice):
- 0 FAIL across G1–G8;
- 83 / 83 unit tests pass;
- two clean runs byte-identical (G8).

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Validation after fix |
|---|---|---|---|---|---|---|---|
| R01 | planner | HIGH | Selecting the architecture by separation on the 12 Phase 6 periods is selection on the evaluation set; they come from the same components and P90 rule | planner report; `abn_core.family_stats` | Coverage removed from the selection rule. Selection is on pre-declared requirements and stability (spec §11) | RESOLVED | G5 candidate-rule row PASS; robustness `CANDIDATE` rows |
| R02 | planner | HIGH | Retrospective upstream inputs (Phase 1 DQ windows, Phase 2 frozen / flatline masks and holds, static tag confidence) could leak into status or confidence | planner report | Confidence uses causal fields only. DQ windows are applied only after they end. Retrospective masks are diagnostic only. Static tag confidence is disclosed | RESOLVED | G3 truncation (DQ window end hidden at T) PASS; G2 INFO row |
| R03 | planner | HIGH | Non-RUNNING buckets would contaminate the trailing windows | `kpi_core.score` scores every bucket | Components are masked to RUNNING before smoothing | RESOLVED | `test_non_running_buckets_never_enter_a_window` |
| R04 | planner | MEDIUM | A "causal expanding" similarity library is not causal: `in_final_set` uses full-period sensitivity | Phase 6 README | Candidate C made descriptive only; the library is frozen to Apr–May calibration-only periods | RESOLVED | robustness `C_HISTORICAL_SIMILARITY` = DESCRIPTIVE_ONLY |
| R05 | planner | MEDIUM | Apr–May components are in-sample for Phase 3, so the edges are optimistic and no true holdout exists | `kpi_core.fit_masks` | Disclosed in the spec, the calibration method, the limitations and the report | ACCEPTED | report §7, LIMITATIONS 9 |
| R06 | planner | MEDIUM | The 1 June boundary windows draw on May data | — | `reference_state = OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE` | RESOLVED | `test_7_timestamp_boundaries` |
| R07 | planner | MEDIUM | The truncation test only covers the Phase 7 layer | — | The Phase 3 leakage rows are cited as a G3 consistency check | RESOLVED | G3 Phase 3 row PASS |
| R08 | planner | MEDIUM | A degenerate anchor (q ≤ m) would make `to_kpi` raise | components ~45 % zeros | Floor `q ≥ m + 0.25`, flagged | RESOLVED | reference anchors: 0 degenerate |
| R09 | planner | MEDIUM | A plain mean dilutes a single-family deviation to 1/5 | — | Magnitude changed to 0.5·max + 0.5·mean, declared before evaluation | RESOLVED | `test_three_families_outweigh_one_saturated_family` |
| R10 | planner | MEDIUM | "≥ 1 family abnormal" persistence is not discriminative (35 % of reference time) | prototype | Persistence defined on H ≥ H_ref90 | RESOLVED | spec §4; persistence tests |
| R11 | planner | LOW | A P99 edge is unstable with about 20 blocks | — | Candidate edges P75 / P90 / P95; P95 merged by the support rule | RESOLVED | bands BANDED_WITH_MERGES |
| R12 | planner | LOW | Module-name collisions (`generate_report`, `sensitivity_analysis`); Phase 6 import side effects | directory listing | Names avoided; upstream modules used through their namespace; directories required to exist before import | RESOLVED | G1 upstream-unchanged row PASS |
| R13 | implementation gates | HIGH | Buckets inside a Kiln-I data gap were scored from stale pre-gap values (the trailing median had ≥ 4 of 6) | G7 first run: 4 scored buckets inside long gaps | Family usable only when the current bucket is valid | RESOLVED | G7 gap row PASS; `test_gap_bucket_is_not_scored_from_stale_values` |
| R14 | implementation gates | HIGH | The confidence mean let POOR data quality reach MEDIUM | first run: POOR median 0.54 → MEDIUM | Critical-part rule (data quality ≤ 0.5 → LOW) | RESOLVED | G7 gating row PASS |
| R15 | implementation gates | MEDIUM | The G7 sentinel check flagged −273 in draft tags, where it is a legal mmWC value | Kiln-II!F normal range −297 … 0 | −273 checked on Deg.C tags only; 99999 / 9999 on all tags | RESOLVED | G7 sentinel row PASS (0 leaked) |
| R16 | implementation gates | LOW | The wording scanner hit a spec line whose negation sat on the heading line | G6 first run | Each list line carries its own "not" | RESOLVED | G6 scan PASS |
| R17 | implementation gates | LOW | `minutes_onset_to_first_high` searched only inside the period (370-min artefact) | coverage CSV | Measured from onset; renamed `…_lag` | RESOLVED | coverage CSV |
| R18 | mle-reviewer | HIGH | Phase 8 could misuse in-sample and diagnostic rows: no `is_operational` column, and in-sample rows carried score and band | 7,467 in-sample scored rows; diagnostic column public | `operational` column added. `risk_score`, `risk_band` and components only on operational rows. In-sample and diagnostic numbers moved to `risk_score_diagnostics.parquet` | RESOLVED | G4 operational row PASS |
| R19 | mle-reviewer | HIGH | Bands are not stationary out of sample, and HIGH is load-confounded; `oos_exceedance_jun_aug` was blank for LOW | 25 → 53 % HIGH; low-load 71 % | Guards in the contract and handoff (HIGH is not a rare-event flag; use ranks). Column filled for every band | RESOLVED | FEATURE_CONTRACT guards; bands CSV |
| R20 | mle-reviewer | MEDIUM | The leakage tests did not perturb AFR events or DQ windows, left the future window end visible, perturbed only some columns, and had no mutation test | `validation.perturb_after` | `perturb_context` randomises every column plus AFR and DQ events. `truncate` hides a future window end. Injected-leak mutation test added | RESOLVED | G3 rows PASS; `test_harness_detects_an_injected_leak` |
| R21 | mle-reviewer | MEDIUM | The inclusion tests use circular coverage-AUC while the text said coverage was "not a criterion" | `robustness.py` docstring | Wording: coverage is used by the inclusion tests (exclusion-biased), never by architecture selection | RESOLVED | robustness docstring; report §11 |
| R22 | mle-reviewer | MEDIUM | 12 of 25 variants SENSITIVE | robustness CSV | Reported as NOT_MET_REPORTED; the contract says to use ranks for trends | ACCEPTED | G5 materiality row NOT_MET_REPORTED (by design) |
| R23 | mle-reviewer | MEDIUM | Weak provenance: no code hash; variant references in a gitignored cache with no checks | `load_refs` | `code_sha256` in the references. Variant references moved to `outputs/`. `load_refs` checks version and hashes. Committed to git | RESOLVED | G1 code-hash row PASS |
| R24 | mle-reviewer | LOW | Static Phase 2 tag confidence feeds `conf_baseline` | inventory | G2 INFO disclosure row | RESOLVED | G2 INFO row |
| R25 | mle-reviewer | LOW | Similarity is exposed from retrospective episode boundaries | — | Diagnostic only, operational rows only, never scored; full series in the diagnostics file | RESOLVED | G4 |
| R26 | mle-reviewer | LOW | G9 review log missing | — | This log | RESOLVED | G9 |
| R27 | python-reviewer | MEDIUM | Circular import between `calibration` and `reference_builder` | lazy import in `main()` | `fit_bands`, `block_ids` and `boot_quantiles` moved to `risk_core`; all imports top-level | RESOLVED | unit tests |
| R28 | python-reviewer | MEDIUM | Duplicated or unused labels (`PRIMARY_LABELS` vs `SCORE_LABEL`; unused `SCORE_NAME`, `REFERENCE_LABEL`, `load_grid`) | grep | `SCORE_LABEL` / `STATE_LABEL` used; unused names deleted | RESOLVED | AST unused-name scan clean |
| R29 | python-reviewer | MEDIUM | Monolithic `main()` functions in validation, report and calibration | line counts | Not split: every check is one `add` row over pure, unit-tested functions, and a split would add indirection with no behaviour change | DEFERRED | — |
| R30 | python-reviewer | MEDIUM | `perturb_after` left most columns unperturbed | column list | Same fix as R20 | RESOLVED | G3 |
| R31 | python-reviewer | MEDIUM | Inclusion re-derivation duplicated 0.02, parsed "kept" from free text, and hard-coded 10 / 0.10 | `validation.py`, `robustness.py` | `INCLUSION_MIN_GAIN` / `INCLUSION_MAX_MONTH_CHANGE` imported; `stability_kept` column; weights from the config | RESOLVED | G5 inclusion row PASS |
| R32 | python-reviewer | MEDIUM | Text I/O without `encoding="utf-8"` (G8 bytes locale-dependent); `SystemExit` raised in library code | grep | UTF-8 everywhere; `RuntimeError` in `validate_upstream` | RESOLVED | G8 byte-identical |
| R33 | python-reviewer | MEDIUM | G9 substring match over the whole log | `review_status` | Parses the Reviewer and Status columns of the `R##` rows | RESOLVED | G9 |
| R34 | python-reviewer | MEDIUM | Untested: `clean()` guard, `reasons()` ordering, `period_coverage`, `forbidden_hits`, load-band anchors, available denominator | grep | Tests added | RESOLVED | 83 tests pass |
| R35 | python-reviewer | LOW | Unused imports (`DRIVER_CODES`, test imports) | AST | Removed (`kpi_core` in `common` is a deliberate re-export used by tests) | RESOLVED | AST scan |
| R36 | python-reviewer | LOW | `reference_mask` assertion could never fail | code | Removed | RESOLVED | — |
| R37 | python-reviewer | LOW | Magic numbers (temporal window 6, 0.75), unused `ref` parameter, redundant `abn` expression | `risk_core` | `temporal_buckets` and `conf_high` from the config; parameter dropped; `abn = S > Q` | RESOLVED | unit tests |
| R38 | python-reviewer | LOW | Confidence variants redefined by hand in `variant_set`; 0.80 hard-coded | `robustness.py` | Built from `CONFIDENCE_VARIANTS`; `MATERIALITY` used | RESOLVED | — |
| R39 | python-reviewer | LOW | Band rank map rebuilt three times | `calibration.py` | `band_rank` reused | RESOLVED | — |
| R40 | python-reviewer | LOW | The inclusion null could raise on a short series; `block_auc_ci` hard-coded its start date | `robustness.py`, `calibration.py` | `circular_null` (guarded) reused; start derived from the config | RESOLVED | — |
| R41 | python-reviewer | LOW | A NaN Spearman would emit non-standard JSON; `max(pairs)` depends on order | `reference_builder` | NaN → null; strict `allow_nan=False`; NaN pairs skipped | RESOLVED | — |
| R42 | python-reviewer | LOW | Python row loops (`contributing_families`, `afr_context`) | `risk_core` | Vectorised; the `reasons()` loop is kept (≈ 1 s) | RESOLVED | runtime about 1 min |
| R43 | python-reviewer | LOW | `month_label` mapped every month ≥ 9 to SEP | `calibration.py` | `== 9` | RESOLVED | — |
| R44 | senior-data-scientist | HIGH | Coverage AUC and the negative controls had no baseline; the KPI the periods were defined from separates them almost perfectly | KPI AUC 0.990 | KPI, magnitude-only and family-count AUCs reported beside 0.868; NC1 / NC2 relabelled consistency controls | RESOLVED | G6 baseline row PASS; report §8 / §14 |
| R45 | senior-data-scientist | MEDIUM | "AFR / Phase 4 do not improve the score" overstated a test biased toward exclusion | inclusion design | Reworded: "no gain on circular coverage; not evidence of irrelevance" | RESOLVED | report §1, §11 |
| R46 | senior-data-scientist | MEDIUM | Load confounding vs drift was not analysed | low-load share 12 / 33 / 5 % | Load-standardised and steady-load-only HIGH shares added; load mix does not explain the drift | RESOLVED | calibration `LOAD_STANDARDISED_ALERT_RATE` |
| R47 | senior-data-scientist | MEDIUM | Missing data scores as zero deviation (downward bias, false reassurance) | G7 NaN injection | Bias stated; LOW confidence for an incomplete family set below HIGH | RESOLVED | spec §4 / §6 |
| R48 | statistical-analyst | HIGH | The drift headline had no uncertainty; month steps are not separable | block CIs overlap | Monthly block CIs, HIGH-edge-CI ranges and the Aug − Jun difference CI; claim limited to August > June | RESOLVED | calibration `EMPIRICAL_ALERT_RATE`; report §1 |
| R49 | statistical-analyst | HIGH | "Does not track severity" overstated a non-significant result (n = 12) | ρ 0.33, CI −0.30 to 0.76 | Reworded "inconclusive"; CIs plus duration-neutral metrics | RESOLVED | report §8; LIMITATIONS 6 |
| R50 | statistical-analyst | MEDIUM | The April-fit / May-check tolerance max(0.05, nominal) could not fail | — | Fixed ±0.05 | RESOLVED | G5 row PASS (0.259 vs 0.25; 0.065 vs 0.10) |
| R51 | statistical-analyst | MEDIUM | 10 % → 25 % mixes in-sample optimism with the reference choice | Apr-only June 9 % | Headline leads with the within-Jun–Aug trend, with the caveat stated | RESOLVED | report §1 |
| R52 | statistical-analyst | LOW | The support rule is a conservative heuristic, not a test of distinct edges | — | Called a heuristic in the code, the calibration method and the report | RESOLVED | CALIBRATION_METHOD §4 |
| R53 | statistical-analyst | LOW | p = 0.005 is the floor for 200 draws | — | Reported as p ≤ 0.005 | RESOLVED | report §14 |
| R54 | statistical-analyst | LOW | "Rise holds in every variant" is true only for August vs June | 2 non-monotone variants | Reworded, with computed counts | RESOLVED | report §1 / §13 |
| R55 | data-quality-auditor | HIGH | The kiln-inlet O₂ analyser reads near ambient air (up to 21 %) while running; these valid-flagged readings inflate COMBUSTION and STABILITY | 10,517 running minutes at 20–21 %; Aug 33 % of minutes > 15 % | Not masked in the primary score: no plant-confirmed threshold, and upstream is not modified. Confidence penalty for buckets ≥ 15 % (`SUSPECT_ANALYSER_AMBIENT_O2`). Exact no-analyser robustness variant (it roughly halves the Jun → Aug rise). Headline caveat. Plant question 2. Phase 8 guard | RESOLVED | G7 O₂ INFO row; robustness `EXCLUDE_KILN_INLET_O2_ANALYSER` |
| R56 | data-quality-auditor | MEDIUM | Tag-level dropout inside a family can raise the family average (MNAR), and the G7 family test could not catch it | `Kiln-I!X` dropout +0.93 median | G7 tag-level dropout test (before averaging); per-family tag coverage in confidence; MNAR disclosed | RESOLVED | G7 tag-dropout INFO row |
| R57 | data-quality-auditor | LOW | A missing bucket inside the smoothing window can raise the score slightly | +5 in about 1 % | Kept as INFO; stated in the limitations | ACCEPTED | G7 INFO row |
| R58 | data-quality-auditor | LOW | A single ×0.5 penalty (gap, frozen, and now O₂) left confidence at MEDIUM at exactly 0.5 | 126 buckets | `≤ 0.5` forces LOW | RESOLVED | G7 gating row PASS |
| R59 | data-quality-auditor | LOW | The diagnostic score was filled in September | 2,704 buckets | Diagnostic only with ≥ 3 usable families, and only in the diagnostics file | RESOLVED | G7 September row PASS |
| R60 | data-quality-auditor | INFO | The text-mask count is 0 because "Error 6" occurs only in CBS-Calculation (not scored) | grid totals | G7 wording states it | RESOLVED | G7 sentinel row |
| R61 | product (cs-product-analyst) | HIGH | "Deposit" in the title and the long name contradicts the disclaimers | README, spec, report | Name kept: `deposit_inefficiency_risk_score` is the user-mandated phase name and preferred terminology. A non-detection subtitle and an explicit sentence were added wherever the name appears | ACCEPTED | report title / subtitle; README |
| R62 | product (cs-product-analyst) | HIGH | ELEVATED buckets got the primary reason NO_FAMILY_ABOVE_REFERENCE_P90 ("elevated because nothing") | 305 buckets | Primary reason = largest contributor, `_BELOW_THRESHOLD` suffix; NO_DEVIATION only for score 0 | RESOLVED | `test_primary_is_largest_contributor_with_below_threshold_suffix` |
| R63 | product (product-analytics) | MEDIUM | HIGH plus "alert" wording implies an alarm or limit | Aug HIGH 53 % | Bands annotated "≥ Apr–May P90" everywhere; "alert episodes" renamed "sustained-exceedance episodes". Band names kept (the prompt's own band vocabulary) | RESOLVED | report §1 / §7 |
| R64 | product (product-analytics) | MEDIUM | PHASE4 / AFR context codes (LOW-confidence / retrospective) cluttered the reason strings | most frequent code | Removed from the reason strings; column-only | RESOLVED | `test_afr_and_phase4_never_in_reason_strings` |
| R65 | product (product-analytics) | MEDIUM | Confidence was nearly constant (99 % MEDIUM) | — | Guidance added; after the DQ fixes, 82 % MEDIUM / 18 % LOW, and LOW is the informative state | RESOLVED | report §6 |
| R66 | product (cs-product-analyst) | MEDIUM | The operational filter relied on string prefixes; diagnostic score public; confidence on non-VALID rows unexplained | — | Same fix as R18; contract note on confidence semantics | RESOLVED | FEATURE_CONTRACT §1 |
| R67 | product (cs-product-analyst) | MEDIUM | "Implemented and validated" reads as scientific validation | README | Reworded: gates G1–G8 pass; not validated against plant events | RESOLVED | README |
| R68 | product (product-analytics) | LOW | Monotone-rise wording | — | Same fix as R54 | RESOLVED | report |
| R69 | product (product-analytics) | LOW | The §6 cross-tab mixed in-sample and non-scored rows | — | Restricted to operational rows | RESOLVED | report §6 |
| R70 | product (product-analytics) | LOW | Onset-to-HIGH could read as a lead time | — | Renamed `…_lag`, with an explicit lag note | RESOLVED | report §8 |
| R71 | product (cs-product-analyst) | LOW | Plant data requests lacked specifics and priority | — | Prioritised list with required fields, including the O₂ analyser and the reference period | RESOLVED | report §20 |
| R72 | ponytail | LOW | Dead write: `cache/alert_episodes.parquet` had no consumer | grep | Deleted | RESOLVED | — |
| R73 | ponytail | LOW | `MATERIALITY` re-declared (identical to `p3common.MATERIALITY`) | `robustness.py` | Reused from Phase 3 | RESOLVED | — |
| R74 | ponytail | LOW | `LOAD_BANDS` / `HIGH_RANK` re-declared in calibration | `calibration.py` | Imported from `risk_core` | RESOLVED | — |
| R75 | ponytail | LOW | Hand-rolled run-start detection in `episodes_per_100h` | `robustness.py` | `ic.run_lengths(hi) == 1` | RESOLVED | — |

## Ponytail audit — other checks (no action needed)

| Check | Result |
|---|---|
| Leakage | Covered by G3 (8 cuts, full-column / event perturbation, post-event, refit) and the mutation test |
| Post-event fields | Never loaded; the inventory marks them FORBIDDEN |
| Phase 6 severity | Used only in the coverage / severity-context table, never a feature or label |
| Hard-coded thresholds | Score and confidence thresholds live in `P7Config` / named constants |
| Data-quality bypasses | Gated in G7 |
| Non-determinism | G8 byte-identical; the no-hidden-time test |
| Score semantics | Scanned by the wording guard |

No over-engineered abstraction found beyond R72–R75. The AST unused-definition scan is clean.
