# Phase 8 Review Log

Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO. Status: FIXED / ACCEPTED (documented, no code change) / REJECTED (with reason).
Revalidation = what was re-run after the action. No fix changed the primary result (PE +0.051, NOT_SUPPORTED).

## Self-found (during build, before external review)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| S-01 | self | HIGH | NC1 circular shift rolled the whole grid, so shifted scores landed in non-operational Apr–May / gap rows | `negative_controls.nc1_circular` | roll within operational positions only; spec §16 amendment 3 | FIXED | NC1 p 0.19, null median −0.012; G6 PASS |
| S-02 | self | HIGH | Event windows could contain another candidate period or a DQ window while controls could not (asymmetric) | `temporal_validation.endpoint` | event windows must lie in `cand_free & ~dq`; spec §16 amendment 1; test `test_other_period_excluded` | FIXED | primary unchanged at 60 min; long-horizon n drops, reported |
| S-03 | self | HIGH | O₂-excluded variant inherited the primary's DQ status, which is halved by the O₂ penalty it excludes | P6-026 / P6-029 contaminated only via O₂ | `data_quality_status_o2x` / `evaluable_o2x`; variant also reported on the primary's event set; spec §16 amendment 2 | FIXED | variant n 12 (own set), n 10 same-set p 0.0625 |
| S-04 | self | MEDIUM | Detection-anchored "lead" shown as a robustness row with a status | `robustness.py` | status `CIRCULAR_BY_CONSTRUCTION`; F12 NOT_SUPPORTED | FIXED | report §3.1 / §20 |
| S-05 | self | LOW | LOEO robustness row carried CI columns that are not a CI | `robustness.py` | CI columns blank; range in note | FIXED | §20 |
| S-06 | self | HIGH | Gate L3 premise wrong: P6-020's ≥ 2-h windows reach into late May | L3 FAIL | redefined: reference rows precede every onset and never carry an operational score (May rows non-operational, so P6-020 drops out of ≥ 2-h horizons) | FIXED | G5 PASS |
| S-07 | self | MEDIUM | Forbidden wording: "Cause" in F17 title; spec §15 phrase | G12 FAIL | F17 renamed "Origin of…"; spec §15 reworded | FIXED | G12 PASS |
| S-08 | self | HIGH | Some report conclusions were fixed sentences, not derived from outputs | `report_generation.py` | all conclusions computed from output tables | FIXED | report regenerated; scanner clean |
| S-09 | self | HIGH | Half of the onsets are censored; not surfaced as a finding | robustness `EXCLUDE_CENSORED_ONSETS` PE −0.072, n 5 | new finding F18 (INSUFFICIENT_DATA), exec summary, §11 | FIXED | F18 in §1 / §3 |
| S-10 | self | MEDIUM | F8 read as an effect claim | F8 title | retitled "sign stability only, not significance" | FIXED | §3 |
| S-11 | self | MEDIUM | `loeo` computed eligibility separately from `endpoint` | `temporal_validation.loeo` | uses `endpoint(...)["ok"]` | FIXED | G10 consistency PASS |
| S-12 | self (Ponytail) | LOW | Dead code: `write_json`, `read_json`, `LABEL`, `REVIEWS`, `json` import | `p8common.py` | removed | FIXED | tests pass |
| S-13 | self (Ponytail) | LOW | `phase-08-early-warning/scripts/__pycache__` created by ad-hoc imports | `find` | deleted; pipeline and tests run with `-B` | FIXED | upstream `__pycache__` dirs predate Phase 8, untouched |

## Analytical review (senior-data-scientist, statistical-analyst, data-quality-auditor)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-A1 | senior-data-scientist | HIGH | All positive PE comes from censored onsets, whose window is inside the shift | censored +0.082 vs uncensored −0.072 at 60 min | `robustness.censored_split` at every horizon, both variants (report §20); F2 / F18 evidence states censored vs uncensored PE and that the endpoint cannot measure precedence; §23 note derived from the split | FIXED | censored > uncensored at all 8 horizons, both variants |
| R-A2 | senior-data-scientist | HIGH | Controls selected by the KPI (all candidates excluded); missing from §3.1 | rolling-rank control median 0.40 | sensitivity `CONTROLS_EXCLUDE_FINAL_PERIODS_ONLY` (F20); §3.1 row added; "PASS = disclosed and bounded" | FIXED | F20 PE +0.051 (change +0.000), NOT_SUPPORTED — primary unaffected |
| R-A3 | data-quality-auditor | MEDIUM | Event DQ rule not applied to controls | `build_controls` vs `build_event_windows` | sensitivity `CONTROLS_SAME_DQ_RULE_AS_EVENTS` (F19); §3.1 row; spec §16.7 | FIXED | F19 PE +0.057, NOT_SUPPORTED |
| R-A4 | statistical-analyst | MEDIUM | O₂-variant WEAK over-read | own-set p 0.0455 vs like-for-like 0.0625 | F5 evidence leads with like-for-like PE, difference +0.037, "same direction, not significant", "second test, not multiplicity-adjusted"; §1 / §11 already reworded (R-B4). Class kept: it is the pre-declared rule applied to the variant | FIXED | F5 text |
| R-A5 | statistical-analyst | MEDIUM | F2 labelled BH-adjusted but WEAK uses raw p | `secondary_status` | label now says WEAK = raw p, SUPPORTED = BH q; p / q per horizon and null expectation (0.5 of 5) in evidence. Rule not changed after the result | FIXED | F2 text |
| R-A6 | senior-data-scientist | MEDIUM | §23 inflates F4 / F8; finding rules not pre-declared | LOEO of a median of 10 | F4 / F8 moved to "context only" in §23 with the order-statistic explanation; `findings()` docstring and spec §16.6 declare F2–F20 rules post hoc | FIXED | §23 |
| R-A7 | senior-data-scientist | MEDIUM | F10 is not a valid drift test | control rolling rank 0.40 | F10 NOT_SUPPORTED when the control median rolling rank is not neutral (> 0.05 from 0.5); spec §16.6 | FIXED | F10 WEAK → NOT_SUPPORTED |
| R-A8 | senior-data-scientist | MEDIUM | Rank ceiling not discussed | control median rank 0.83 | §22 bullet (max excess ≈ 1 − control median) and LIMITATIONS 12; score-point PE not added (rank is the declared scale) | FIXED | §22 |
| R-A9 | data-quality-auditor | MEDIUM | G11 FAIL downplayed | report §1 | same as R-B1; G11 now also requires both runs `--clean` (R-P9) | FIXED | final double clean run |
| R-A10 | statistical-analyst | LOW | NC4 not a reversal and near-automatic pass; NC3 windows not freedom-checked | `negative_controls.py` | NC4 relabelled mirrored-position single draw, removed as a G6 criterion (spec §16.5); NC3 documented as diagnostic, clipped-window count reported | FIXED | G6 PASS on NC1 / NC2 / NC3 / NC5 |
| R-A11 | statistical-analyst / data-quality-auditor | LOW | Month × load fallback missing; o2x zeroes LOW share; pooled binomial; inconsistent F3 thresholds | spec §5, `build_event_windows` | o2x keeps the LOW share (labels only); F3 WEAK uses p < 0.10 / 5; fallback and pooled rate disclosed as deviations (spec §16.8, §22, LIMITATIONS 14) | FIXED / ACCEPTED | F3 all NOT_SUPPORTED either way |
| R-A12 | data-quality-auditor | LOW | P6-020 onset at the reference boundary | T0 2025-06-01 01:00 | §22 bullet (computed, emitted when T0 < 24 h after the reference) and LIMITATIONS 13 | FIXED | §22 |

## Python / MLE review (python-reviewer, mle-reviewer)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-P1 | mle-reviewer | HIGH | Source / upstream gates pass vacuously when nothing is found | `rglob` on a missing root | run aborts if `SOURCE_ROOT` is missing; G1 requires `n_src > 0` and `n_upstream > 0` | FIXED | G1: 60 source files, 543 upstream files |
| R-P2 | mle-reviewer | MEDIUM | G3 event-window freedom hard-coded True | `validation.py` | new `event_recheck`: interval-level check of every evaluable (period, horizon, variant) against other candidate extents and DQ buckets | FIXED | G3 PASS |
| R-P3 | mle-reviewer | MEDIUM | NC4 mislabelled, near-automatic pass | `negative_controls.py` | see R-A10; test now asserts the mirrored-position semantics | FIXED | tests |
| R-P4 | mle-reviewer | MEDIUM | Event vs control selection asymmetry | DQ / transition rule | see R-A3 (F19) | FIXED | F19 |
| R-P5 | python-reviewer | MEDIUM | Config not threaded; signal construction copied 4× | NC5, L1, `_synth`, `make_signals` | single `warning_metrics.signals_from(score, thr, fam, cfg)` used everywhere; `control_recheck` / `event_recheck` take `cfg` | FIXED | outputs unchanged; tests pass |
| R-P6 | python-reviewer | MEDIUM | Tests would miss regressions; vacuous byte test | `test_reproducibility` | mutation test: a centred window makes NC5 fail and L1 show a difference; `warning_coverage` coverage / lead test; byte test replaced with a float-noise test that can fail. `gates()` on doctored inputs not added (needs the full real-data bundle) | FIXED / ACCEPTED | 48 tests pass |
| R-P7 | python-reviewer | MEDIUM | Redundant computation | loeo nulls, rb.run recompute | inner LOEO fits `null=False`; other reuse skipped (runtime ~70 s is acceptable) | FIXED / ACCEPTED | outputs identical |
| R-P8 | mle-reviewer | MEDIUM | No provenance; Phase 7 cache not in the input contract | — | `outputs/run_manifest.json` (git commit / dirty, versions, config, input sha256, determinism; excluded from G11); G1 checks the 5 Phase 7 cache inputs | FIXED | manifest written |
| R-P9 | mle-reviewer | LOW | G11 compares with any previous run | `run_phase8.main` | first-pass file records `--clean`; G11 requires both runs clean | FIXED | final double clean run |
| R-P10 | python-reviewer | LOW | `eval` on own output | `validation.py` | `ast.literal_eval` | FIXED | G5 PASS |
| R-P11 | python-reviewer | LOW | Dead code / hard-coded values / weak G8 | various | removed `nc1_circular` `obs`, dead bootstrap fallback, `np.vectorize` → `searchsorted`; `BLOCK_LENGTH_{cfg.block_hours}H` and horizons from cfg; G8 requires raw / adjusted on every row. 6-h change duplication and `event_status` min-valid kept (identical results) | FIXED / ACCEPTED | G8 PASS |
| R-P12 | python-reviewer | LOW | Edge-case guards | `lead_time`, NC3 | `family_count` float (NaN-safe); NC3 `pos_in` clipped with count; O₂ ×0.5 penalty is hard-coded in Phase 7 `risk_core`, so mirrored and documented | FIXED / ACCEPTED | — |

## Product review (product-analytics, cs-product-analyst)

| ID | Reviewer | Severity | Finding | Evidence | Action | Status | Revalidation |
|---|---|---|---|---|---|---|---|
| R-B1 | cs-product-analyst | CRITICAL | G11 FAIL while §26 says "reproducible" | §1, §20, §26 | the FAIL compared runs before / after a code change (F18), not nondeterminism; §1 / §26 wording now derived from the G11 result; final two clean runs required | FIXED | final double clean run (see bottom) |
| R-B2 | product-analytics | HIGH | No plain-language bottom line | §1 | answer / clear-starts / what-it-means / what-would-change box + plain-terms glossary, all derived | FIXED | §1 regenerated |
| R-B3 | product-analytics | HIGH | WEAK items read as supported | §23, F4, F10, F8 | §23 retitled "weak / exploratory — not decision-grade"; F4 / F10 retitled; F8 marked a robustness check; "no WEAK result may justify an alert" | FIXED | §3 / §23 |
| R-B4 | product-analytics | HIGH | O₂ result invites "remove analyser and it works" | §1, §11 | §1 leads with same-set comparison, flags the amendment, states neither variant preferred, adds 17 % / 26 % Aug ambient share and Aug median 39.8 → 28.1; §11 answer reworded | FIXED | §1 / §11 |
| R-B5 | cs-product-analyst | HIGH | August, alert burden, load not in §1; 3-vs-8 load counts | §1, §12 | §1 August alert-burden line and plain load line; §12 note: Phase 7 T0-bucket label vs Phase 6 whole-period class | FIXED | §1 / §12 |
| R-B6 | product-analytics | HIGH | Lead-time tables look like ~23 h warning | §9, §12 | caveat above both; values at the 1,430-min cap shown "≥ window"; evaluable column; lead times on the Phase 9 MUST NOT list | FIXED | §9 / §12 / §26 |
| R-B7 | cs-product-analyst | HIGH | Handoff not an explicit allow / deny list | §26 | "Validated" → integrity checks only; primary moved to Not validated; MAY / MUST NOT table; audience; sign-off owner left as an open plant question (not invented) | FIXED | §26 |
| R-B8 | cs-product-analyst | MEDIUM | Plant data not prioritised; Phase 1 asks missing | §25 | priority / unblocks columns, date range, format, ≥ 8-event minimum, Phase 1 open asks added; three Phase 7 questions kept | FIXED | §25 |
| R-B9 | cs-product-analyst | MEDIUM | No detectable-effect statement or next steps | §22, §26 | CI half-width sentence in §22; "Decision and next steps" in §26 | FIXED | §22 / §26 |
| R-B10 | product-analytics | MEDIUM | Censored-onset reversal understated | §1 | plain sentence in the §1 box | FIXED | §1 |
| R-B11 | product-analytics | LOW | Jargon, gate-PASS confusion, truncated cells, finding order | §1, §3 | glossary incl. "Gate PASS = check ran correctly"; finding tables no longer truncated; F18 moved last | FIXED | §3 |
| R-B12 | both | INFO | Guardrails met | — | none | ACCEPTED | — |

## Ponytail audit (after all reviews)

| Area | Check | Result |
|---|---|---|
| temporal leakage | every window / slope / flag is trailing; L1 truncation, L5 grid perturbation, NC5 future permutation; mutation test proves NC5 / L1 catch a centred window | PASS |
| circular validation | §3.1 lists every reuse incl. KPI-based control selection; detection anchor `CIRCULAR_BY_CONSTRUCTION`; Phase 7 AUC not used | PASS (disclosed, bounded) |
| target leakage | no Phase 6 severity / confidence / end time in any feature; end times only for control exclusion and NC3 | PASS |
| retrospective labels | `afr_context` not in the column allow-list; AFR events removed / shifted leave the score unchanged (L7) | PASS |
| threshold tuning | W1 / W3 fixed ranks, W2 / W4 reference P95, W5 fixed rule; only the leave-one-out diagnostic uses events | PASS |
| misuse of Phase 6 | periods labelled EMPIRICAL_ABNORMAL_PERIODS, never events; severity context only | PASS |
| misuse of O₂ | variant never replaces the primary; like-for-like comparison leads; analyser labelled `ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION` | PASS |
| unsupported predictive claims | wording scanner (G12) over outputs, docs and report; handoff MUST NOT list | PASS |
| invalid statistical assumptions | block bootstrap for controls; randomisation p; post hoc finding rules declared; rank ceiling and censoring disclosed | PASS (disclosed) |
| false-positive terminology | "empirical alert rate", "control-window warning rate" only | PASS |
| hardcoded conclusions | every report conclusion derived from outputs; conditional sentences for the censored split, boundary, reproducibility | PASS |
| dead code / duplication | removed `write_json`, `read_json`, `LABEL`, `REVIEWS`, NC1 `obs`, bootstrap fallback; signal construction unified in `signals_from` | PASS |

No abstraction was added beyond `signals_from` (which replaced four copies) and two small masks in `build_controls`.

## Final revalidation

Two consecutive `run_phase8.py --clean` runs on frozen code; results recorded in the commit message and `outputs/run_manifest.json`.
