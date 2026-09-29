# Phase 8 — Early Warning Validation: Specification (pre-declared)

**Status:** written at the CONTRACT stage, **before** any Phase 8 result was computed. Amendments made after results
exist are marked `AMENDMENT (post-result)` with the reason. Nothing below was chosen by looking at Phase 8 results.

Disclosure: during the contract audit, the risk score at each of the 12 onset buckets was printed once as part of a
data-availability check (window coverage per horizon). No pre-onset/control comparison, effect, or p-value had been
computed when this spec was written. The primary horizon is justified structurally (§4), not by those values.

---

## 1. Scientific position

- No coating / ring / deposit / cleaning / maintenance / failure / shutdown-reason ground truth exists
  (Phase 1 `EVENT GROUND TRUTH NOT FOUND`). **Deposit / ring / failure early-warning validation is BLOCKED.**
- Phase 8 validates a narrower, answerable question:
  > Does the frozen Phase 7 risk score (`p7-risk-1.1.0`) carry temporally useful information **before** the onset of
  > the 12 Phase 6 `EMPIRICAL_ABNORMAL_PERIODS`, relative to ordinary running, and does that survive load adjustment,
  > the O₂-excluded variant, temporal perturbation and negative controls?
- The 12 periods are `EMPIRICAL_ABNORMAL_PERIODS`: KPI-derived, not plant events. Severity and Phase 6 confidence are
  context metadata, never targets.
- Phase 8 is a falsification stage. Failure of the hypothesis is reported, never tuned away.

## 2. Frozen inputs (Phase 7 contract)

| Input | Use |
|---|---|
| `risk_scores.parquet` (`operational == True` only) | the score, confidence, status, load context, family count, DQ status |
| `risk_score_components.parquet` (`operational == True`) | family contributions (trajectories, W5 context) |
| `risk_score_confidence.parquet` | `o2_ambient_suspect` (analyser analysis) |
| `risk_score_reasons.parquet` | presence check only (G1) |
| `risk_score_reference.json`, `risk_score_variant_references.json` | frozen; hash-checked before and after the run |
| `risk_score_bands.csv`, `risk_score_feature_inventory.csv` | frozen; G1 / provenance |
| `risk_core.score_frame` (+ Phase 7 `common.load_refs / load_context`) | leakage tests; in-sample reference score distribution |
| Phase 7 `reference_builder.fit_reference` + `risk_core.score_core` | the `EXCLUDE_KILN_INLET_O2_ANALYSER` `VALIDATION_VARIANT` (Phase 7's own variant definition) |
| Phase 6 `abnormal_episodes.parquet` | onset / detection / end of the 12 final periods (+ all candidates for control exclusion); `onset_censored`, severity, confidence as metadata |
| Phase 7 cache `dq_windows.parquet` | Phase 1 long gaps / frozen window |

**Not used:** `risk_score_diagnostics.parquet` (non-operational); `afr_context` (retrospective labels; test L7);
any Phase 6 post-event field; the Phase 7 AUC 0.868 (circular coverage).

The Phase 7 score is **frozen**: no weight, feature, reference, band or scoring change. The O₂-excluded score is a
`VALIDATION_VARIANT`, never a replacement.

## 3. Anchors and windows

- **T0 = Phase 6 `onset_time`** (CUSUM onset). Grid timestamps are bucket ENDS; the bucket ending at T0 is the last
  bucket before the onset bucket, and by construction its D-CUSUM is 0 (unless `onset_censored`).
- **Pre-onset window of horizon h:** buckets with `timestamp ∈ (T0 − h, T0]`. Nothing after T0 is ever used to build
  a warning feature or an event metric (L2).
- Horizons h ∈ {15, 30, 60, 120, 240, 360, 720, 1440} min. A window statistic needs ≥ ⌈2/3 · n_buckets⌉ operational
  buckets (the Phase 7 4-of-6 smoothing rule), else the event is `INSUFFICIENT_DATA` at that horizon.
- **Detection anchor** (`detection_time`, KPI ≥ P90) is analysed only as a **circularity illustration**: the KPI is a
  6-h trailing median of the same components, so a "lead" before detection is mechanical.

## 4. Primary endpoint (pre-declared)

- **Signal:** `rank_ref(t)` = ECDF of the frozen Apr–May in-sample reference score distribution (Phase 7 VALID
  reference buckets, rebuilt with `score_frame`; must reproduce `reference_score_quantiles`) evaluated at
  `risk_score(t)`. Monotone, frozen, independent of Jun–Aug.
- **Statistic per anchor A:** `W̄(A)` = median `rank_ref` over (A − 60 min, A].
- **Primary endpoint PE:** median over evaluable events e of `[W̄(T0_e) − median_{c ∈ C_month(e)} W̄(c)]`, where
  `C_month(e)` = eligible ordinary-running control anchors in the same calendar month (§5).
- **Why 60 min:** (i) it equals the Phase 7 family smoothing window (trailing 1 h), so the score at T0 is built entirely
  from pre-onset data and the window spans one full score memory; (ii) Phase 4's only replicated lead scale is ≈ 60 min;
  (iii) all 12 onsets have a complete 60-min operational pre-window (contract audit), so no event is lost; (iv) it is the
  shortest window that is not a single-bucket snapshot. 60 min is therefore defensible without looking at results.
- **Inference:** p = one-sided randomisation p-value against **NC2** (month-stratified random pseudo-onsets drawn from
  eligible control anchors, N_NULL = 2000); 95 % CI by bootstrap: events resampled i.i.d. (each is a separate period),
  controls resampled in **12-h calendar blocks** within month (N_BOOT = 2000). Block length pre-declared as 2× the
  longest structural window (Phase 6 onset look-back 6 h; Phase 7 persistence 3 h + smoothing 1 h); 3 h, 6 h and 24 h
  are reported as sensitivity only.
- **Effect size:** month-stratified Cliff's δ = mean over events of `P(W̄_c < W̄_e) − P(W̄_c > W̄_e)`.
- **Decision rule (pre-declared):**
  - `INSUFFICIENT_DATA` if n_evaluable < 8;
  - `SUPPORTED` if PE > 0 AND CI low > 0 AND p < 0.05 AND every leave-one-event-out PE > 0;
  - `WEAK` if PE > 0 AND (p < 0.10 OR CI low > 0) but not SUPPORTED;
  - `NOT_SUPPORTED` otherwise.
- Even `SUPPORTED` means only: *the risk rank was elevated before X of 12 empirical abnormal-period onsets relative to
  ordinary running.* It is never a deposit / failure prediction claim.

## 5. Controls

- **Eligible control anchor A for horizon h:** A is operational; every bucket in (A − h, A] is *clean*; the window has
  ≥ ⌈2/3·n⌉ operational buckets; the window does not overlap a Phase 1 LONG_GAP / FROZEN_WINDOW.
- **Clean bucket:** not inside any Phase 6 candidate episode extent [onset, end + 6 h] (all 35 candidates, including
  ordinary-context ones: they are KPI ≥ P90 abnormal-like), and not inside the 24 h before any of the 12 final onsets.
- **Matched variants:** month (primary); month × load stratum (load_band × load_context, fallback to load stratum
  across months when < 30 anchors, flagged); post-restart-settling state; random pseudo-onsets (NC2); circularly
  shifted signal (NC1).
- Controls are never built from contaminated periods; counts are reported per month and horizon.

## 6. Secondary endpoints (exploratory; BH-adjusted across horizons)

1. PE at 15, 30, 120, 240, 360, 720, 1440 min (window statistic), BH q across the 8 horizons.
2. Aligned snapshot trajectory: `rank_ref(T0 − o) − control` at o ∈ {−24 h, −12 h, −6 h, −4 h, −2 h, −1 h, −30, −15, 0}
   with bootstrap CI; plus score, confidence, family contributions, KPI, persistence, feed.
3. Pre-onset rank change `rank_ref(T0) − rank_ref(T0 − 6 h)`.
4. Warning coverage / control-window warning rate / lead times for W1–W5 (§7).
5. Persistence (warning minutes in the 24-h window) and multi-family concurrence at T0.
6. O₂-excluded and load-adjusted repeats (§9, §10); month-level PE; leave-one-event-out.

## 7. Warning definitions (validation hypotheses; none is deployed)

All thresholds are frozen **before** evaluation and never use the evaluated periods.

| ID | Rule at bucket t (causal) | Threshold source |
|---|---|---|
| W1_RANK | `rank_ref ≥ 0.95` (frozen Apr–May P95 = 51.47 points) | frozen reference |
| W2_RISING | 60-min OLS slope of the score ≥ P95 of the Apr–May reference slope distribution | frozen reference population |
| W3_PERSISTENT | `rank_ref ≥ 0.75` (Apr–May P75 = ELEVATED edge) for ≥ 60 min consecutively | frozen reference |
| W4_ACCEL | slope(t) − slope(t − 60 min) ≥ P95 of the Apr–May reference distribution | frozen reference population |
| W5_MULTI_FAMILY | `family_count_abnormal ≥ 2` AND slope > 0 | fixed rule |

- **Month-holdout thresholds (secondary):** W2 / W4 re-derived from June controls → evaluated on July / August; June +
  July → August. June events have no prior out-of-sample month: `THRESHOLD_VALIDATION_INSUFFICIENT` for that split.
- **LOEO event-tuned threshold (validation only):** for each event, threshold = P25 of the other 11 events' W̄; the
  held-out event's coverage and the all-control exceedance rate are reported. Never deployable.
- **Episodes:** warning buckets merge across ≤ 20 min (2 buckets) of non-warning *operational* time; any
  non-operational gap > 20 min breaks an episode. Each episode records start, end, duration, max / median score,
  slope at start, contributing families, median confidence, operating state, load context and DQ status.

## 8. Lead-time metrics (per event, per warning, 24-h look-back)

`first_warning` (earliest warning bucket in (T0 − 24 h, T0]); `sustained_warning` (start of the warning episode in
force at T0, i.e. ending ≥ T0 − 20 min); `peak_pre_event` (argmax score); `trend_onset` (start of the final run of
positive slope ending at T0); `warning_duration` (warning minutes in the window). Reported per event, then median /
P25 / P75 / min / max. Coverage is always shown next to the **control-window warning rate** at the same horizon:
with high alert rates any window "contains a warning", so coverage alone is uninformative.

## 9. O₂-excluded sensitivity (mandatory)

The Phase 7 `EXCLUDE_KILN_INLET_O2_ANALYSER` variant (COMBUSTION / STABILITY rebuilt without `Kiln-I!X`, own frozen
Apr–May reference) is rescored and masked to the primary operational rows. Its own reference ECDF and reference
slope thresholds are used. Every key result is repeated. A conclusion is `ROBUST_TO_O2` if its status class is unchanged,
else `SENSITIVE_TO_O2`. Analyser behaviour (ambient-like readings, `o2_ambient_suspect`) is described as
`ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION`.

## 10. Load analyses

A raw; B load-adjusted (rank minus the control median rank of the same load stratum); C month × load matched
controls; D transition-excluded (events and controls whose 60-min window has any LOAD_ASSOCIATED, post-restart
settling or non-operational bucket are dropped). Low-load periods are never removed from A–C.

## 11. Negative controls and falsification

NC1 circular shift (≥ 7 days); NC2 random month-stratified pseudo-onsets; NC3 backward (post-end window) association;
NC4 time-reversed signal with fixed anchors (implemented as a mirrored-position draw, §16.5); NC5 future perturbation (post-T0 values randomised; pre-T0 metrics must be
identical). Falsification checks: load matching, O₂ exclusion, month dominance, single-event dominance (LOEO), low
feed, KPI persistence (Phase 3 KPI as a baseline signal), reference artefact (reference-free 7-day rolling rank),
censored onsets, reduced-confidence events.

## 12. Event data-quality status

Precedence (first match): `NOT_EVALUABLE` (no operational bucket in the primary window) → `INSUFFICIENT_DATA`
(< 4 of 6 operational) → `DATA_QUALITY_CONTAMINATED` (window overlaps a Phase 1 DQ window, or > 50 % POOR data
quality) → `TRANSITION_CONTAMINATED` (window contains a STOPPED / TRANSITION bucket) → `VALID_REDUCED_CONFIDENCE`
(onset censored, > 50 % LOW confidence, or any `o2_ambient_suspect` bucket) → `VALID`. Primary evaluable set = VALID +
VALID_REDUCED_CONFIDENCE; a sensitivity drops VALID_REDUCED_CONFIDENCE.

## 13. Multiple testing

One primary endpoint, unadjusted. Everything else is secondary / exploratory: horizons BH-adjusted; variants reported
with their status and never promoted to primary.

## 14. Circularity boundary

```
Phase 3 components (5 families) ──► Phase 3 KPI (D, 6-h median) ──► Phase 6 periods (KPI ≥ P90, CUSUM onset on D)
          │
          └──────────────────────► Phase 7 risk score (1-h medians of the SAME components, Apr–May reference)
                                              │
                                              ▼
                                  Phase 8: score BEFORE T0 vs ordinary running
```

- Shared information: the five family components (both the event definition and the score), the Apr–May reference
  window, the RUNNING state proxy.
- Not shared: no Phase 8 threshold uses the Jun–Aug periods (except the explicitly held-out LOEO diagnostic); no
  post-T0 data; no Phase 6 severity / confidence as target.
- Consequence: a pre-onset elevation is expected partly **by construction** (autocorrelated shared components). It
  is evidence of *temporal precedence of the score relative to the KPI-defined onset*, not independent validation. The
  KPI baseline (§11) measures how much of it the KPI itself already carries.

## 15. Blocked

No deposit / ring / coating / failure / maintenance early warning; no detector error rates of any kind (there is no
event ground truth to define them); no operational alert thresholds; no lead time to any plant event. All require plant
event logs (report §25).

## 16. Amendments

All were made after the first trial results existed (5–8 after the independent reviews). None changes the primary endpoint definition, horizon,
thresholds, controls or decision rule, and none changed the primary result (PE +0.051, NOT_SUPPORTED before and after).

1. `AMENDMENT (post-result)` — **event-window symmetry.** Controls had to be clean (§5), event windows did not: at
   ≥ 2 h, some pre-onset windows contained *other* candidate periods (e.g. P6-025's window contains P6-024 + 6 h).
   Event windows (T0 − h, T0] must now also lie outside every other candidate extent [onset, end + 6 h] and every
   Phase 1 DQ window (a period's own extent never overlaps its own pre-window). Reason: like-for-like comparison.
   Effect: 2 periods leave the ≥ 2-h horizons; none leaves 60 min.
2. `AMENDMENT (post-result)` — **O₂-excluded event set.** Two periods (P6-026, P6-029) are
   `DATA_QUALITY_CONTAMINATED` only because the Phase 7 data-quality confidence halves under `o2_ambient_suspect`
   (> 50 % POOR). The O₂-excluded variant does not use that analyser, so for the variant the event status is recomputed
   without the O₂ penalty (`data_quality_status_o2x`). The variant is reported on its own event set **and** on the
   primary's event set (like-for-like).
3. `AMENDMENT (post-result)` — **NC1 implementation.** The circular shift rolls the window statistic within the
   operational subsequence (Phase 7's NC1 convention) instead of the full grid, where ≈ 64 % of shifted positions were
   non-operational (NaN) and ~20 % of draws were lost. Same null hypothesis; complete draws.
4. Labelling only: the detection-anchored row is `CIRCULAR_BY_CONSTRUCTION`; the leave-one-event-out row carries the
   minimum PE in `pe` and the range in its note (no CI columns).
5. `AMENDMENT (post-result, review)` — **NC4 relabelled.** The implementation reads the reversed series' window
   statistic at fixed anchors, i.e. a single mirrored-position relocation, and its pass rule ("rev < observed") was
   almost always met. NC4 is now reported as `REPORTED_SINGLE_DRAW` and is not a G6 criterion; NC1 is the shift null.
6. `AMENDMENT (post-result, review)` — **finding rules are post hoc.** Only F1 (§8 rule), F5 (§8 rule on the variant)
   and F6 (§9 load verdict) were pre-declared. The F2–F20 rules in `run_phase8.findings` were written after the
   analyses and are post hoc. Changes at review: F3 WEAK now uses the same Bonferroni divisor as SUPPORTED
   (p < 0.10 / 5); F10 is NOT_SUPPORTED when the control median rolling rank is not neutral (|median − 0.5| > 0.05,
   the controls are selected low-KPI time); F2's label states that WEAK uses raw p.
7. `AMENDMENT (post-result, review)` — **two control sensitivities added** (F19, F20): controls held to the event
   data-quality rule (§12: POOR share ≤ 0.5, no STOPPED / TRANSITION_CONTEXT bucket), and controls that exclude only
   the 12 final periods (not the other KPI ≥ P90 candidates). The censored / uncensored split is reported at every
   horizon for both variants.
8. Deviations kept and disclosed: §5's month × load fallback to the load stratum is not implemented (events without
   ≥ 30 matched controls are dropped from MATCHED_LOAD); the warning-coverage binomial uses the pooled Jun–Aug
   control-window rate.
