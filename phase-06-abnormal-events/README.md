# Phase 6: Historical Abnormal Events (Historical Abnormal Periods)

**Status:** COMPLETE, awaiting review.

> The detected episodes are empirical historical abnormal periods derived from process measurements and the Phase 3 POC
> efficiency-deterioration KPI. They are not validated plant events.
>
> No supplied event ground truth was available for coating, ring, deposit, maintenance, failure, cleaning, or shutdown
> reasons. `ABNORMAL_PERIOD ≠ CONFIRMED_PLANT_EVENT` and `DEVIATION ≠ FAILURE`.

Phase 6 builds **no** risk score, early warning, API or dashboard. **Phase 7 has NOT been started.**

## Execution

```bash
cd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-06-abnormal-events/scripts
../../.venv/bin/python run_phase6.py --clean      # ~40 s; run twice: G7 compares every key output byte-for-byte
../../.venv/bin/python -B -m unittest discover -s ../tests -v
```

## Input artifacts (read-only; SHA-256 in `outputs/abnormal_events_version_manifest.csv`)

- **Phase 3:**
  - `efficiency_deterioration_kpi.parquet`
  - `kpi_component_scores.parquet`
  - `kpi_reference.json`
  - `kpi_reference_bands.csv`
  - `kpi_definition.json`
  - `kpi_validation.csv` (must be all PASS)
- **Phase 4:**
  - `leading_indicator_set.csv`: only the `usable_downstream = True` row `Kiln-I!I|ROC_1H`, used per its `permitted_use` as supporting context
  - `indicator_feature_values.parquet`
  - the other Phase 4 outputs (hashed)
  - `indicator_validation.csv` (must have no FAIL)
- **Phase 5:**
  - `afr_transition_episodes.parquet` (187 AFR transition episodes, context only)
  - the `afr_*` outputs (hashed)
  - `afr_validation.csv` (must have no FAIL)
- **Phase 2:**
  - `operating_state_events.csv` (37 stops / 37 restarts, retrospective)
  - `column_holds.csv`
  - `data/processed/{kiln_i, kiln_ia, kiln_ii, kiln_iiia, operating_state_timeline}.parquet`, read through Phase 3 `load_dataset` for the feed, kiln speed, clinker TPH, coal and AFR buckets and the mask reasons
- **Phase 1:**
  - `gap_events.csv` (long gaps)
  - `dq_issue_register.csv` (DQ-016 frozen window)
  - `process_tag_inventory.csv` (tag / unit / original-name check: 37 tags, none held)

## Abnormality definition

1. **Candidate (`CANDIDATE_ABNORMAL_PERIOD`).** A RUNNING 10-min bucket is a candidate when the Phase 3 KPI is ≥ **41.82**, the frozen training P90 band cut. Runs of candidate buckets are merged when:
   - they are separated by ≤ 60 min of RUNNING buckets;
   - no Phase 1 long gap or frozen window lies in the gap;
   - no stop lies in the gap.
2. **Final set (`HISTORICAL_ABNORMAL_PERIOD`).** A candidate enters the final set when all three hold:
   - it is out of sample (Jun–Aug);
   - no ordinary-context rule matched;
   - ≥ 1 process family's episode median S_d is above its own training P90.

   With ≥ 2 such families it is MULTI_FAMILY_DEVIATION; with one it is SINGLE_FAMILY_DEVIATION.
3. **Other outcomes.**
   - Apr–May periods lie in the KPI's own training window. They are labelled `CALIBRATION_ONLY_ABNORMAL_LIKE` and are never in the final set.
   - Candidates with no family above P90 are `UNCONFIRMED_KPI_ELEVATION`.
4. **Ordinary-context (false-positive) categories.** These are kept and never deleted. Precedence is fixed, and the first match wins:
   - DATA_QUALITY_ARTIFACT
   - INSUFFICIENT_DATA
   - STARTUP
   - RESTART
   - SHUTDOWN
   - SHORT_TRANSIENT
   - NORMAL_LOAD_CHANGE
   - AFR_TRANSITION
   - CONTROL_ACTION

   The last three apply only when fewer than 2 families deviate.
5. **References.** Every reference is frozen on Apr–May RUNNING data:
   - the KPI cut and P99;
   - the family P90s;
   - CUSUM k and h;
   - load medians and MADs;
   - feed and coal change quantiles.

## Episode construction and characterisation

- **Onset.** A causal CUSUM on the robust z of D gives the onset:
  - k = 1.17, half the training shift from the median to P90;
  - h = the training P90 of the 6-h CUSUM rise;
  - the look-back is 6 h, and only data at or before detection is used.
- **Multivariate evidence.** The primary method is the family agreement count. The secondary method is the Phase 3 robust Mahalanobis KPI (≥ 50), which is not refitted.
- **Context, never cause.** Every period records:
  - startup / restart / shutdown overlap;
  - load context: LOAD_ASSOCIATED, LOAD_INDEPENDENT or UNCERTAIN;
  - AFR transitions in [onset − 3 h, end];
  - Phase 4 activation in the 2 h before onset;
  - coal-step control action;
  - data-quality contamination.
- **Pre-event window (T = onset).** It covers T−12 h … T:
  - snapshots of each signal;
  - the first exceedance of each frozen rule, with its out-of-sample base rate;
  - the KPI turning point;
  - AFR, stop and restart events.

  It is descriptive only, not a predictive result.
- **Post-event window (T_end = end).** It covers T_end + 30 min … + 6 h and assigns an outcome: RECOVERED, PROCESS_DEVIATION_PERSISTS, RECURRED_WITHIN_6H, FOLLOWED_BY_STOP (sequence only), NO_KPI_AFTER or DATA_END_CENSORED. It is never used to define the episode.

## Severity methodology

- **Score.** `severity_score` = 0.4·peak + 0.3·persistence + 0.3·breadth, each part in [0, 1]:
  - peak = (peak − cut) / (P99 − cut);
  - persistence = KPI-hours above the cut / ((P99 − cut) × 6 h);
  - breadth = deviating families / 5.
- **Class.**
  - HIGH: peak ≥ training P99 **and** duration ≥ 6 h.
  - MODERATE: one of the two.
  - LOW: neither.
- **Meaning.** It is a deviation magnitude, not a failure, deposit or ring probability.

## Confidence methodology (separate from severity)

- **Score.** `confidence_score` is the mean of six parts:
  - 1 − DQ contamination;
  - family agreement;
  - Mahalanobis support share;
  - change-point support;
  - share of Phase 3 `kpi_confidence` HIGH;
  - sensitivity robustness.
- **Reported but not averaged.**
  - Sp.Heat F/G agreement: the cut is nominal for those KPIs.
  - Band margin: it is already inside `kpi_confidence`.
- **Class.**
  - HIGH needs ≥ 0.75, robustness ≥ 0.7 and ≥ 2 families. It is **capped to MEDIUM** (`CAPPED_MEDIUM: NO_EVENT_GROUND_TRUTH; STATE_PROXY_UNCONFIRMED; FAMILIES_ARE_KPI_INPUTS`).
  - LOW is < 0.5.
- **Meaning.** Confidence measures the internal consistency of the evidence, not the likelihood of a real plant event.

## Results (last clean run)

- **Candidates:** 35 in Apr–Aug.
  - 19 in Apr–May: 10 `CALIBRATION_ONLY_ABNORMAL_LIKE` and 9 ordinary-context or unconfirmed.
  - 16 out of sample in Jun–Aug.
- **Final historical abnormal periods:** **12**, split 4 in June, 5 in July and 3 in August.
- **Out-of-sample ordinary context:** 2 AFR_TRANSITION, 1 RESTART and 1 SHORT_TRANSIENT.
  - `P6-021` (1–2 Jun, 18.5 h, peak 69) was excluded by the AFR_TRANSITION rule because only one family deviated. It is worth reviewing.
- **Severity:** 3 HIGH, 4 MODERATE and 5 LOW.
- **Confidence:** 10 MEDIUM (1 of them capped from HIGH) and 2 LOW.
- **Deviating families** (counts across the 12 periods):
  - thermal 9
  - combustion 8
  - draft / pressure 8
  - stability 6
  - efficiency (Sp.Heat) 3

  11 of the 12 periods are multi-family.

| Period | Start | Hours | Peak KPI | Severity | Confidence | Families | Type | Load |
|---|---|---|---|---|---|---|---|---|
| P6-020 | 01 Jun 04:20 | 6.7 | 60.3 | MODERATE | LOW | EFF, THERM | EFFICIENCY_DOMINANT | LOAD_ASSOCIATED |
| P6-024 | 14 Jun 20:00 | 7.7 | 53.7 | MODERATE | LOW | COMB, THERM, DRAFT, STAB | STABILITY_DOMINANT | LOAD_ASSOCIATED |
| P6-025 | 15 Jun 17:30 | 6.8 | 65.1 | HIGH | MEDIUM | COMB, THERM, DRAFT, STAB | COMBUSTION_DOMINANT | LOAD_ASSOCIATED |
| P6-026 | 27 Jun 21:40 | 3.3 | 47.6 | LOW | MEDIUM | COMB | COMBUSTION_DOMINANT | UNCERTAIN |
| P6-027 | 04 Jul 13:40 | 3.7 | 51.0 | LOW | MEDIUM | THERM, DRAFT | THERMAL_DOMINANT | LOAD_ASSOCIATED |
| P6-028 | 09 Jul 11:50 | 4.8 | 48.2 | LOW | MEDIUM | COMB, THERM, DRAFT, STAB | STABILITY_DOMINANT | LOAD_ASSOCIATED |
| P6-029 | 11 Jul 23:10 | 13.7 | 51.7 | MODERATE | MEDIUM | COMB, DRAFT | COMBUSTION_DOMINANT | LOAD_ASSOCIATED |
| P6-030 | 13 Jul 13:20 | 7.2 | 50.8 | MODERATE | MEDIUM | COMB, THERM, DRAFT | DRAFT_PRESSURE_DOMINANT | LOAD_ASSOCIATED |
| P6-031 | 16 Jul 03:00 | 7.5 | 76.9 | HIGH | MEDIUM | EFF, THERM, DRAFT | THERMAL_DOMINANT | LOAD_ASSOCIATED |
| P6-032 | 04 Aug 21:50 | 4.7 | 50.8 | LOW | MEDIUM | COMB, THERM, DRAFT, STAB | COMBUSTION_DOMINANT | UNCERTAIN |
| P6-033 | 11 Aug 03:20 | 4.5 | 42.4 | LOW | MEDIUM | COMB, THERM, STAB | COMBUSTION_DOMINANT | UNCERTAIN |
| P6-035 | 17 Aug 19:20 | 8.8 | 62.8 | HIGH | MEDIUM | EFF, STAB | EFFICIENCY_DOMINANT | UNCERTAIN |

## Episode types

These are rule-based analytical categories, not plant failure modes.
- **Recurring type.** Only **COMBUSTION_DOMINANT** meets the pre-declared recurrence rule (≥ 5 episodes in ≥ 2 months): 5 episodes across 3 months. It is labelled `RECURS_ACROSS_MONTHS`.
- **Other types.** All others are `INSUFFICIENT_SUPPORT`.
- **Clustering.** It was not run, because 12 periods are too few for a stable clustering.

## Context findings

- **Load.**
  - 8 of the 12 periods are LOAD_ASSOCIATED, and none is LOAD_INDEPENDENT (`F_indep` leaves 0).
  - The large feed cuts before P6-025, -029 and -031 (−121, −105 and −150 TPH vs the 2 h before onset) may be part of the process response.
- **AFR (context, causal role not assessed).**
  - 10 of the 12 periods overlap an AFR transition.
  - Stops and ramp-downs cluster near candidate onsets beyond time-shifted chance (NC3 p = 0.024, exploratory). This matches the Phase 5 coal-for-AFR swap.
- **Phase 4 indicator.** Activation before onsets is **not distinguishable from chance** (NC4 p = 0.57).
- **Data quality.** All 35 candidates are DQ_CLEAN, because the KPI is produced only with adequate coverage. The DQ-016 frozen window and the 10–12 May gap fall where the KPI is not scored.

## Robustness

- **Sensitivity (A–I).**
  - Minimum duration, merge gap, state treatment, load treatment and the DQ mask are STABLE: 100 % of the final periods are retained.
  - Every final period is retained by ≥ 81 % of the 16 robustness-set variants.
  - Requiring ≥ 2 / ≥ 3 families keeps 92 % / 58 %.
- **Reference dependence (NOT_MET, reported).**
  - The Phase 3 alternative Jun–Jul15 reference keeps only **8 %** of the periods, so the abnormal level depends on which period is taken as normal.
  - The cut CI bounds and the Sp.Heat F/G KPIs change the episode extent (Jaccard < 0.5) while keeping 67–100 % of the periods.
  - `reference_robustness_score` carries this per period.
- **Negative controls.**
  - Family agreement exceeds the KPI circular shifts (NC1) and random same-length running windows (NC2, p = 0.005). Because the families are KPI inputs, this shows internal consistency beyond autocorrelation, not independent confirmation.
  - The in-sample calibration is 9.98 % above the P90 cut, as expected.
- **Temporal.** Final periods per 100 running hours are 0.71 (Jun), 0.85 (Jul) and 0.64 (Aug). The candidate-bucket share falls from June to August.

## Validation and reviews

- **Gates.** The last two clean runs each gave **47 PASS, 0 FAIL, 2 NOT_MET_REPORTED (the reference robustness above), 1 INFO**, across G1–G7:
  - **Leakage test:** 13 truncation cut points, all identical. It covers candidates, starts, detection, onset, change points, families at detection, closed extents, pre-event rows, and (after the 2-h SHUTDOWN look-ahead) context, classification and final-set fields.
  - **Reference check:** refitting on data up to 20 Jun reproduces the reference exactly.
  - **Independent re-derivations:** candidates, merging, contamination, severity, confidence and precedence.
  - **Determinism:** 15/15 key files are byte-identical.
  - **Integrity:** the source (60 files), Phases 1–5 and `data/` are unchanged.
  - **Unit tests:** 12 pass.
- **Reviews.** The planner, python-reviewer (Approve), mle-reviewer (PASS-WITH-CONDITIONS, conditions resolved) and product analyst were run. All findings are resolved; see `reviews/REVIEW_LOG.md`.

## Limitations

- **Circularity:** the KPI defines the candidates, and the families are its inputs.
- **Reference dependence:** see Robustness.
- **Small sample:** 12 periods over ≈ 2.7 months.
- **Load:** load and process deviation cannot be separated.
- **Control inputs:** AFR, coal and feed are co-manipulated.
- **Proxies:** the state is a POC proxy, and the Phase 2 events are retrospective.
- **Sp.Heat:** the F/G definition is unresolved.
- **Missing data:** there is no September, and the Kiln-IIIA gap on 14–15 Aug affects the clinker load context.

## Event ground truth status

- **Current status:** `event_ground_truth_status = event_match_status = plant_event_type = NOT_AVAILABLE` for every episode.
- **Future integration point:** a real plant log at `phase-06-abnormal-events/inputs/plant_event_log.csv` with columns `event_id, event_type, start_time, end_time, source, description`. Rerunning then fills MATCHED / PARTIAL_OVERLAP / NO_MATCH via `abn_core.match_plant_events`.
- **What is not done:** no synthetic event is ever created, and no supervised metric is computed until real labels exist.

## Outputs available to Phase 7

Phase 7 may consume:
- `outputs/abnormal_episodes.parquet`: all candidates. **Filter `in_final_set == True`** for the 12 periods.
- `outputs/abnormal_episode_signals.parquet`: tag-level evidence (why each period is abnormal).
- `outputs/abnormal_episode_context.csv`
- `outputs/abnormal_episode_severity.csv`
- `outputs/abnormal_episode_confidence.csv`
- `outputs/abnormal_episode_pre_event.parquet`: T = onset, historical only.
- `outputs/abnormal_episode_post_event.parquet`: retrospective. **Never use it as a feature.**
- `outputs/abnormal_episode_types.csv`

Rules for Phase 7:
- Phase 7 must **not** assume these are confirmed plant events.
- Carry `confidence`, `load_context`, `afr_context` and `reference_robustness_score` with every period.
- Treat the Phase 4 indicator as unsupported context.

Other outputs:
- `abnormal_candidate_windows.parquet`
- `abnormal_episode_data_quality.csv`
- `abnormal_episode_sensitivity.csv`
- `abnormal_episode_validation.csv`
- `negative_control_results.csv`
- `abnormal_events_version_manifest.csv`
- the report `reports/PHASE_6_HISTORICAL_ABNORMAL_EVENTS.{md,html}`

## Scripts

| Script | Purpose |
|---|---|
| `abn_core.py` | Paths, `P6Config`, labels; pure functions (reference fit, candidates, runs / merge, CUSUM onset, family stats, context, classification, severity, confidence, types, pre-event, truncation, ground-truth matching, wording scanner) |
| `run_phase6.py` | Orchestration, unit tests, G7 determinism, source / upstream snapshots |
| `load_phase6_inputs.py` | Upstream validation and hashes, grid / events / DQ windows cache, gateguard tag check, frozen reference |
| `build_kpi_candidates.py` … `build_abnormal_episodes.py` | One mandated step each (candidates, deviations, multivariate, change points, context, DQ, severity, pre / post windows, types, sensitivity, negative controls, confidence, catalogue) |
| `validate_abnormal_events.py` | G1–G6, including the mandatory leakage test |
| `generate_report.py` | Report, 3 figures, version manifest |
