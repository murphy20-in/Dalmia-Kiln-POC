# Phase 3 — Review Log

## Review process

Phase 3 was planned first and then reviewed three times.

- **Agents:** the environment has no agents named `planner`, `cs-product-analyst`, `python-reviewer` or `mle-reviewer`. As in Phase 2, the planner role was run with the `Plan` agent, and the three reviewer roles with general-purpose agents briefed with each role's remit.
- **Read-only:** all reviews were read-only, with no network access. Scratch probes went only to `/tmp/claude-1000/`.
- **Not invoked:** `database-reviewer`, because Phase 3 adds no database (Parquet + CSV + JSON only).
- **Skills:** the required skills were loaded before implementation: senior-data-scientist, statistical-analyst, product-analytics, data-quality-auditor, python-patterns, observability-designer, mle-workflow, gateguard and security-guidance. The `ponytail` plugin is not installed, so its intent (keep the implementation thin) was followed manually.

| Role | Verdict | Outcome |
|---|---|---|
| planner | Draft critiqued; 3 real defects (A1–A3) plus 7 refinements | Adopted. The KPI is efficiency-anchored and dimensions are standardised. Masks and state are causal and recomputed inside the scorer. The 6 h window is fixed a priori. |
| cs-product-analyst | 9 questions: 1 YES, 1 NO (not redundant), 6 PARTIAL, 1 YES-with-risks; 3 HIGH, 4 MEDIUM, 2 LOW | All addressed with new row-level fields and reporting changes. The name is kept, as mandated. |
| python-reviewer | No CRITICAL; 1 HIGH, 5 MEDIUM, 9 LOW | All fixed or documented. |
| mle-reviewer | PASS-WITH-CONDITIONS; 1 HIGH, 4 MEDIUM, 4 LOW/MEDIUM. An independent leakage probe at 8 extra cut points matched exactly | Conditions cleared. The calibration-optimism finding is quantified by a new sensitivity variant, not by changing the primary. |

## Planner (before implementation)

| # | Finding | Disposition |
|---|---|---|
| P-A1 | All-two-sided dimensions measure deviation, not deterioration. | **Adopted.** D = 0.5·S_EFFICIENCY (one-sided Sp.Heat) + 0.5·mean(supporting). The supporting half is labelled process-deviation context. |
| P-A2 | Dimension scores sit on different null scales. | **Adopted.** Each dimension is standardised by its training median and robust scale, floored at 0. |
| P-A3 | Phase 2 masks leak: retrospective flatline/frozen detection, `baseline_status`, retrospective state. | **Adopted.** Only causal tokens are used. Causal flatline (Phase 1 non-zero rule) and causal frozen-row masks are recomputed inside `kpi_core.prepare_minutes`. The curated layer is not used for scoring. |
| P-A4 | A fixed ramp length fails on censored ramps and micro-stops. | **Adopted.** Phase 2's ramp rule is made causal. Pre-stop minutes are scored. A 48 h censoring cap was added after a first run showed an 8-day "transition". |
| P-A5 | Training-window caveats: few effective samples; April has high Sp.Heat. | **Adopted.** Day-block bootstrap CIs on the anchors and bands. The April caveat is a headline. A Jun–Jul15 window was added. |
| P-A6 | Load adjustment: clamp outside the training range, flag it, show the unadjusted efficiency, ≥ 200 buckets per bin. | **Adopted.** |
| P-A7 | Fix W = 6 h a priori; ACF descriptive only. | **Adopted.** |
| P-A8/9/10 | Show bands on the KPI scale; the half-split check must be the Apr-only variant; exclude low-coverage tags. | **Adopted.** |

## Product analyst (after implementation)

| # | Finding | Disposition |
|---|---|---|
| PA-H1 | The name overstates what the typical score measures. The median rise is process deviation while Sp.Heat is below reference; the few extreme periods are Sp.Heat-led. | **Fixed (name kept, as mandated).** Added the row fields `kpi_driver_class` (SPECIFIC_HEAT_LED / PROCESS_DEVIATION_LED / MIXED / NO_DEVIATION) and `window_efficiency_share`. Figure 1 is coloured by driver class. The executive summary states the driver split for all, elevated and beyond-reference buckets. |
| PA-H2 | `top_dimension` / `top_tag` described the current bucket, not the 6 h score; `top_tag` could sit outside `top_dimension`. | **Fixed.** Attribution now comes from the 6 h window median of weighted contributions, and `top_tag` is taken inside `top_dimension`. A unit test enforces this. The bucket-level value is kept as `top_dimension_bucket`. |
| PA-H3 | The reference period has high Sp.Heat, so the efficiency half rarely fires. | **Fixed.** Added `sp_heat_{f,g}_actual` and `*_expected_for_load` to the main parquet, and the shadow column `kpi_alt_reference_w_jun_jul15`. |
| PA-Q1 | No growth/trend field. | **Fixed.** Added causal `kpi_7d_median`, `kpi_trend_7d`, `band_episode_id` and `hours_in_current_band`. |
| PA-Q2 | Direction: two-sided dimensions rise for any departure. | **Fixed.** The definition now reads "higher = further from normal". "Worse" is asserted only for the efficiency half and for variability. |
| PA-Q5/M4 | No multi-dimension agreement; "PERSISTENT" episodes can be short. | **Fixed.** Added `n_dims_elevated` (dimensions above their training P90 over the 6 h window). The top band is renamed `BEYOND_REFERENCE_P99`, and `hours_in_current_band` exposes duration. Episode tables show duration, driver and dims. |
| PA-Q6 | Too many layers; the band cuts mean nothing to an operator. | **Fixed.** Added `kpi_training_percentile`. The secondary KPI is renamed `secondary_validation_mahalanobis_kpi` and documented as a cross-check only. |
| PA-Q7 | Missing fields for later phases. | **Fixed.** Added `contrib_*`, `kpi_band_code` (0/1/2), `kpi_confidence`, `near_band_boundary`, the Sp.Heat actual/expected columns and the trend and episode fields. |
| PA-M1 | `baseline_confidence` is misreadable. | **Fixed.** The name is kept (mandated data model), but its values read `INPUT_TAGS_*_P2_CONFIDENCE`. It is documented as the input-tag mix, and a real `kpi_confidence` was added. |
| PA-M2 | Band membership is fragile near the cuts. | **Fixed.** `near_band_boundary` = KPI inside the bootstrap CI of a cut; it feeds `kpi_confidence`. |
| PA-M3 | The 0.5 weight sets the absolute level. | **Fixed (reporting).** "Level vs direction" is stated in the summary, in Section 12 and in the interpretation rules. |
| PA-L1 | G7 determinism failed on the manifest. | **Fixed** (see PY-M2). |
| PA-L2 | Rows whose window overlaps training. | **Fixed.** Headline statistics use `OUT_OF_SAMPLE` rows only. |

## Python reviewer

| # | Finding | Disposition |
|---|---|---|
| PY-H1 | `kpi_band` was filled on unscored rows (stopped / transition / no-efficiency), because P carried forward with `min_periods=1`. | **Fixed.** P and `fraction_elevated` are defined only where the bucket itself has a D. The band is computed only from reported or in-sample KPI values. New G5 check and unit test: the band is empty wherever no KPI is shown. |
| PY-M1 | Hourly 0.0 placeholders (23–31 Aug) inflated "days with Sp.Heat"; hard-coded "2025-08-22". | **Fixed.** A day counts only with ≥ 6 h of RUNNING minutes carrying Sp.Heat, so W_APR_JUN now correctly fails C3; the primary selection is unchanged. The scoring end and the September check use the last RUNNING Kiln-I minute. |
| PY-M2 | Determinism failed on code hashes, and a first run compared nothing. | **Fixed.** The `code_sha256` rows are excluded from the determinism hash. Completion is evidenced by two consecutive clean runs with identical code. |
| PY-M3 | Several validation checks were tautologies. | **Fixed.** The write-path check is replaced by a before/after snapshot of Phase 2 outputs and `data/` in `run_phase3.py`. The literal-True token check is replaced by a cell-by-cell check of 131k token cells. An independent z recomputation from `kpi_reference.json` was added. The remaining construction checks are labelled REGRESSION GUARD. |
| PY-M4 | A NaN comparison metric gave the verdict CONSISTENT. | **Fixed.** Undefined metrics give `INSUFFICIENT_OVERLAP`, which G6 counts as a failure. |
| PY-M5 | Anchors used P at buckets without D. | **Fixed** by PY-H1. |
| PY-L | UNKNOWN gaps never restarted; sustain counted across UNKNOWN; the ramp signal never fell back; STD60 used non-running minutes; the bucket check read unmasked values; the +10/+30 spike saturated the cap; `to_kpi` silently used 1e-9; JSON allowed NaN; missing tests. | **Fixed.** Gap > 60 min is a restart; contiguity is by last evaluated clock minute; per-minute feed → hood fallback; `std.where(run)`; the bucket check uses `prepare_minutes`; the spike test uses +5 vs +8 (below the cap, above the window median); `to_kpi` raises if q ≤ m; `allow_nan=False`. Seven new unit tests: 48 h cap, UNKNOWN gap, causal conflict, band mode, inverse redundancy, empty band, holdout masks, window attribution. |

## MLE reviewer

| # | Finding | Disposition |
|---|---|---|
| MLE-H1 | CONFLICT came from Phase 2's retrospective `operating_state`, which the leakage test cannot see. | **Fixed.** CONFLICT is computed inside `causal_state` from the masked Kiln-I feed and kiln speed, using the Phase 2 rule evaluated per minute. Scoring no longer reads Phase 2 `operating_state` at all; it is used only for the training population and the retrospective sensitivity. Leakage cut points added: 30 min before a stop, 7 min before a later stop, late August (9 cut points in total). |
| MLE-M2 | Robustness was over-claimed. | **Fixed.** The summary and Section 12 now state that level and band shares depend on the window and weights, and that only the direction of change is robust: Jun → Aug is non-negative in every non-window variant, checked in G6. Verdicts carry a `near_threshold` flag (W_APR_JUN's 10.1 against 10 is flagged), and the reading is generated from the verdict table. |
| MLE-M3 | In-sample calibration inflates out-of-sample levels. | **Quantified, primary kept.** New variant CALIBRATION_HOLDOUT (fit 1 Apr–15 May, anchors on 16–31 May): the June median falls from ~13 to ~3, while the ranking stays consistent. The report says June is the no-change benchmark and that much of June's level is fit optimism. The primary stays on the full window because a 16-day calibration sample would widen the already wide anchor CIs. |
| MLE-M4 | "Reproducible" contradicted G7. | **Fixed** (PY-M2) and re-run twice. |
| MLE-M5 | Full-period Phase 2 confidence labels shape the drop-LOW variant. | **Documented.** The variant is labelled "future-informed", and the limitations list Phase 2 labels as design constants. R6 priority had no realised effect (the reviewer's re-run gave the same tag set). |
| MLE-6 | The feed flatline mask drops steady periods (informative missingness). | **Fixed.** Feed, the load covariate, is exempt from the flatline mask. The previous behaviour is kept as the FEED_FLATLINE_MASKED sensitivity, which is consistent. |
| MLE-7 | `FUEL_NOTE` ρ came from the full period; small full-period design inputs. | **Fixed / documented.** ρ is now computed on the training window. The feed bands in the window rule, the materiality thresholds and the holds are documented as design constants. The `W_APR_MAY` assertion is documented as a consistency guard, not a selection step. |
| MLE-8 | Training uses retrospective Phase 2 RUNNING minutes (train/score population mismatch). | **Documented** in the code (`_window_mask`) and in the limitations. |
| MLE-9 | The first 6 h of June overlap training in the persistence window. | **Fixed.** Excluded from the headline statistics; labelled in the dataset. |

## Not changed, with reasons

- **KPI name:** "Kiln Efficiency Deterioration KPI" is mandated. What the number measures is now shown on every row (`kpi_driver_class`) and stated in the summary.
- **Primary calibration:** it stays on the full training window (MLE-M3 above).
- **`baseline_confidence` field name:** kept from the mandated data model; its values are clarified (PA-M1).
