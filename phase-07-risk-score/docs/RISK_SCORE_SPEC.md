# Phase 7 Risk-Score Specification (contract)

**Score:** `deposit_inefficiency_risk_score` (short name `risk_score`)
**Version:** `p7-risk-1.1.0`
**Status of this document:** written before implementation (DEFINE → CONTRACT), then amended after the review round. Numbers that come from data are *derived by the pipeline* and are published in `outputs/risk_score_reference.json`; they are not typed in here.

> **Amendments in 1.1.0 (review round 1; see `reviews/REVIEW_LOG.md`):**
>
> 1. **Operational rows.** An explicit `operational` column is added. `risk_score` and `risk_band` are populated only on operational rows. In-sample and diagnostic numbers move to `risk_score_diagnostics.parquet`.
> 2. **Primary reason.** It is always the largest point contributor, suffixed `_BELOW_THRESHOLD` when that part is not active. The old `NO_FAMILY_ABOVE_REFERENCE_P90` becomes `NO_DEVIATION_FROM_REFERENCE`, used only for a zero score.
> 3. **Reason strings.** AFR and Phase 4 context are removed from them and live in their own columns only.
> 4. **Confidence.**
>    - Family coverage is weighted by each family's own tag coverage.
>    - A kiln-inlet O₂ bucket ≥ 15 % (ambient-like, POC heuristic) halves data-quality confidence.
>    - `conf_data_quality ≤ 0.5` forces LOW.
>    - An incomplete family set below HIGH forces LOW.
> 5. **Stated bias.** Missing families bias the score *downward*.
> 6. **Uncertainty and baselines.**
>    - The drift is reported with block CIs and the HIGH-edge CI.
>    - Coverage is reported with the Phase 3 KPI baseline.
>    - Severity is reported as inconclusive (n = 12).
> 7. **New robustness variant.** An O₂-analyser-excluded variant (exact rebuild from the Phase 3 tag scores).
>
> The score formula itself (section 4) is unchanged.

---

## 0. What the score is — and is not

> The Phase 7 score is an **EMPIRICAL POC RISK SCORE**. It says how strongly the **current** kiln operating condition resembles the abnormal / inefficient process behaviour seen in the historical data, **relative to the frozen Apr–May 2025 reference**.

What it is not:
- not a deposit, ring or coating probability;
- not a failure probability;
- not a maintenance predictor;
- not a plant operating, alarm or safety limit;
- not a set-point or control recommendation;
- not a causal model;
- not a replacement for operator judgement.

**Why.** The supplied data contains no coating, ring, deposit, maintenance, cleaning or shutdown-reason observations. The 12 Phase 6 periods are `EMPIRICAL_ABNORMAL_REFERENCE` conditions derived from the same Phase 3 components. They are **not** `DEPOSIT_EVENT_LABEL`s.

The output question this score answers:

> "These current process conditions resemble historical abnormal inefficiency conditions to this degree, based on these signals, with this confidence, under this reference."

**Risk and confidence are separate outputs and are never combined.** `HIGH` risk with `LOW` confidence is a legitimate, representable state.

---

## 1. Grain, windows and populations

| Item | Definition |
|---|---|
| Grain | Phase 3 10-minute buckets, right-closed and labelled by the bucket END: bucket `t` covers minutes `(t−10 min, t]` |
| Operating state | Phase 3 causal `operating_state` (POC PROXY — UNCONFIRMED; `Kiln MD` meaning unconfirmed) |
| Reference / calibration window | RUNNING buckets with `2025-04-01 00:00 < t ≤ 2025-05-31 23:59`. This is the Phase 3 training window; the reference is frozen afterwards |
| Scoring window (operational) | `t > 2025-06-01 00:00`, reported **by month for Jun / Jul / Aug** |
| September | Kiln-I has no September data. Every family except STABILITY is missing, so each September bucket is `INSUFFICIENT_DATA` with no numeric score. September is **never** silently included in any statistic |
| Future / post-event data | Forbidden in every feature, reference, band and confidence value |

**`reference_state` per bucket:**
- `IN_SAMPLE_REFERENCE`: `t ≤ 2025-05-31 23:59`. These buckets are scored for calibration only and are **non-operational**.
- `OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE`: out of sample, but the persistence window `(t − 3 h, t]` still reaches back into May.
- `OUT_OF_SAMPLE`: everything else.

**In-sample caveat (disclosed).** Phase 3 fitted its tag curves and dimension scales on the same Apr–May buckets. Phase 7 reference quantiles and bands are therefore **in-sample and optimistic**, and no truly held-out calibration period exists. The April-fit / May-check comparison measures only within-reference stability.

---

## 2. Inputs (read-only)

| Input | Use |
|---|---|
| Phase 3 `efficiency_deterioration_kpi.parquet` | Family components (the only scoring inputs), operating state, `tag_coverage`, `n_causal_frozen_minutes`, `out_of_training_load_range`, `share_high_confidence_tags`, the KPI value and band (context) |
| Phase 3 `kpi_reference.json`, `kpi_reference_bands.csv`, `kpi_validation.csv` | Version check and the KPI band cut (context); validation must be all PASS |
| Phase 6 `abnormal_episodes.parquet` | `in_final_set == True` rows are the empirical abnormal reference for coverage evaluation only. `CALIBRATION_ONLY_ABNORMAL_LIKE` rows (Apr–May) form the descriptive signature library. Fields used: `episode_id`, `start_time`, `end_time`, `onset_time`, `severity_class`, `severity_score`, `confidence`, `load_context`, `afr_context`, `reference_robustness_score`, `classification`, `in_final_set` |
| Phase 6 `abnormal_episode_post_event.parquet` | **Never read by any scoring code.** It is hashed only, so that the post-event perturbation test can prove it has no influence |
| Phase 6 `load_phase6_inputs.context_buckets()` / `masked_counts()` (imported read-only) | Bucket AFR / PC-coal levels (context), and per-bucket counts of masked cells by reason: sentinel `99999` / `9999`, text `Error 6`, `-273`, missing, conflicting duplicates |
| Phase 5 `afr_transition_episodes.parquet` | AFR transition times: context only, labelled RETROSPECTIVE_LABEL |
| Phase 4 `leading_indicator_set.csv` / `indicator_feature_values.parquet` | `Kiln-I!I|ROC_1H` and its threshold: context only |
| Phase 1 `gap_events.csv` / `dq_issue_register.csv` | Long gaps and the DQ-016 frozen window: DQ context, used only **after** each window has ended |
| Phase 2 / 4 / 5 / 6 validation files | Upstream integrity (G1) |

---

## 3. Evidence families

| Family | Phase 3 component | Content |
|---|---|---|
| `EFFICIENCY` | `efficiency_component` | Sp.Heat F and G, one-sided, load-adjusted. The Sp.Heat definition is unresolved (plant question) |
| `COMBUSTION` | `combustion_component` | Kiln inlet O₂, NOx (two analysers), CO, preheater-outlet O₂ |
| `THERMAL` | `thermal_component` | Burning zone, preheater fan inlet, hood, calciner outlet, TAD, cyclone / preheater temperatures |
| `DRAFT_PRESSURE` | `draft_pressure_component` | Preheater fan inlet / outlet, kiln inlet, hood and TAD drafts, calciner inlet, cyclone pressures |
| `STABILITY` | `stability_component` | Trailing 60-min variability of burning zone, kiln-inlet O₂, kiln-inlet draft and hood temperature |

**Double-counting controls:**
1. **Within a family,** Phase 3 has already averaged the tag scores into one dimension score. Ten abnormal thermal tags therefore count as **one** family.
2. **The Phase 3 KPI is not a scored family.** It aggregates the same five components. It is reported as `kpi_value`, context only.
3. **Fuel firing is never scored.** Coal kiln / PC and AFR are manipulated variables and are co-manipulated (Phase 5). Sp.Heat may be calculated from them, so scoring firing next to Sp.Heat would double count.
4. **STABILITY is built from tags of other families.** It measures variability, not level. The dependency is disclosed, and a `drop_STABILITY` robustness variant quantifies it.
5. **Correlated families.** The reference Spearman matrix of family intensities is reported. Any pair with ρ > 0.7 triggers a merged-family robustness variant.

---

## 4. Score definition

For each family `d` and bucket `t`:

1. **Input.** `x_d(t)` = Phase 3 component if the bucket is RUNNING, else NaN. Stopped or transition buckets never enter a window.
2. **Smoothing.** `S̃_d(t)` = median of `x_d` over `(t − 60 min, t]`, requiring ≥ 4 of the 6 buckets finite **and** `x_d(t)` itself finite, else NaN. The family is **usable** iff `S̃_d(t)` is finite.

   The current-bucket condition means a bucket inside a data gap is never scored from stale pre-gap values. It was added after G7 found 4 such buckets in the first run.
3. **Frozen anchors** from the reference buckets:
   - `m_d` = median of `S̃_d`;
   - `q_d` = max(P90 of `S̃_d`, `m_d + 0.25`). The floor applies only to a degenerate reference, and `reference_degenerate_<d>` is recorded.
4. **Normalised deviation and intensity** (the Phase 3 saturating transform, reused):
   - `e_d = max(0, S̃_d − m_d) / (q_d − m_d)`
   - `a_d = 1 − 2^(−e_d)`

   `a_d` is 0 at or below the reference median and 0.5 at the reference P90. It rises smoothly towards 1 with no hard cap at the training maximum, and assumes no Gaussian distribution.
5. **Family abnormal** ⇔ `S̃_d > q_d` (⇔ `a_d > 0.5`). This is the Phase 3 / 6 P90 family rule.

Aggregation (a missing family contributes `a_d = 0`; the denominator is fixed at 5):

| Component | Definition | Weight |
|---|---|---|
| Magnitude `H` | `0.5 · max_d a_d + 0.5 · (1/5) Σ_d a_d` | 0.50 |
| Concurrence `C` | `max(0, n_abnormal − 1) / 4` (rewards independent families beyond the first) | 0.25 |
| Persistence `P` | Number of buckets `s` in `(t − 3 h, t]` that follow the last non-RUNNING bucket and have `H(s) ≥ H_ref90` and ≥ 3 usable families, divided by 18 (the clock-time bucket count) | 0.25 |

`H_ref90` is the reference P90 of `H`.

**`risk_score = 100 · (0.5 H + 0.25 C + 0.25 P)`**, which lies in [0, 100].

**Why these choices.**
- **Max + mean.** A single-family deviation is not diluted to one fifth, yet breadth still adds. The max term is attributed to the arg-max family (ties go to the fixed family order above), so components sum exactly.
- **Fixed denominator.** A missing *family* can only lower magnitude and concurrence, never raise them, so a missing family **cannot inflate** the score.
  - **The bias is downward.** Missing evidence scores as zero deviation. Reduced coverage therefore lowers confidence, and below HIGH it forces LOW.
  - **Scope.** The guarantee is family-level. Tag dropout inside a family (Phase 3 averages the available tags) and missing buckets inside the smoothing window can move the score either way. Both are quantified in G7, and tag coverage enters confidence.
- **Persistence on `H ≥ H_ref90`.** "≥ 1 family abnormal" is true in about a third of normal reference time and would not discriminate. A clock-time denominator keeps persistence monotone under missing data. Resetting at stops or starts stops persistence from carrying across a kiln stop.
- **Persistence ≠ the KPI.** Persistence is a count of exceedances in a 3-h window since the last restart, not the KPI's 6-h trailing median of D.
- **Weights 0.50 / 0.25 / 0.25** are a declared POC design choice, not fitted to any event. Robustness varies them.

**Components (auditable).** `risk_score_components.parquet` has, per scored bucket:
- five family rows with contribution `100 · 0.5 · (0.5 · a_d · 1[d = argmax] + 0.1 · a_d)`;
- a `CONCURRENCE` row, `25 · C`;
- a `PERSISTENCE` row, `25 · P`.

They sum to `risk_score` (G4, tolerance 1e-5; every value is serialised at 6 decimal places, so seven rounded parts can differ from the rounded total by up to about 4e-6).

**`historical_similarity` (diagnostic only, not in the score).** This is the maximum weighted-Jaccard similarity `Σ min(a, sig_j) / Σ max(a, sig_j)` between `a(t)` and the median intensity signatures of the Apr–May `CALIBRATION_ONLY_ABNORMAL_LIKE` periods. It is frozen and was known before scoring. The feasibility check shows these signatures are Sp.Heat-dominant and do not carry over to the combustion / draft-dominant Jun–Aug periods, so similarity is **not** scored and no similarity reason code is emitted.

---

## 5. Status (explicit; a numeric score is published only for VALID states)

Precedence (first match wins):

| `risk_status` | Condition | `risk_score` |
|---|---|---|
| `STOPPED` | Bucket state STOPPED | NaN |
| `TRANSITION_CONTEXT` | Bucket state TRANSITION (causal restart ramp) or CONFLICT | NaN |
| `NOT_SCORABLE` | Bucket state UNKNOWN / NO_DATA, or RUNNING with 0 usable families | NaN |
| `INSUFFICIENT_DATA` | RUNNING with 1–2 usable families | NaN |
| `VALID_REDUCED_CONFIDENCE` | RUNNING, ≥ 3 usable families, `confidence_band == LOW` | numeric |
| `VALID` | RUNNING, ≥ 3 usable families, confidence MEDIUM or higher | numeric |

**Diagnostics.** `risk_score_diagnostic` holds the formula value for every RUNNING bucket with ≥ 3 usable families. It is labelled **NON-OPERATIONAL**, is never banded, and lives only in `risk_score_diagnostics.parquet`, together with the in-sample reference scores.

**Operational rows for downstream use:** `operational == True`, meaning `reference_state` starts with `OUT_OF_SAMPLE` **and** `risk_status` starts with `VALID`. Only operational rows carry `risk_score`, `risk_band` and the component columns.

---

## 6. Confidence definition (separate from risk)

`confidence_score` is the mean of six parts, each in [0, 1]. Only causal, bucket-time information is used.

| Part | Definition |
|---|---|
| `conf_data_quality` | Phase 3 `tag_coverage` × (1 − causal-invalid share of scored-tag cells in the bucket: missing, sentinel, text, −273 / impossible, conflicting duplicates) × 0.5 if causal frozen minutes are present × 0.5 within 6 h after the end of a Phase 1 long gap or frozen window |
| `conf_family_coverage` | Mean over the 5 families of (usable × the family's own tag coverage). It responds to whole missing families **and** to tag dropout inside a family |
| `conf_baseline` | Phase 3 `share_high_confidence_tags`. This is **static** Phase 2 tag-level confidence metadata (a full-period, per-tag property, not a time-varying value), disclosed |
| `conf_operating_state` | min(1, hours since the last non-RUNNING bucket / 6) × 0.5 if outside the training load range |
| `conf_temporal` | Share of the trailing 6 buckets whose `H ≥ H_ref90` indicator equals the current one (signal agreement over time) |
| `conf_robustness` | Share of the confidence-variant scores that give the same band as the primary at `t`. Variants: window 30 min / 2 h; abnormal quantile P85 / P95; weights equal-thirds / 0.6-0.2-0.2. Each variant has its own frozen reference and bands |

**Band:** `HIGH` if score ≥ 0.75, `MEDIUM` if ≥ 0.50, else `LOW` (POC heuristic, as in Phase 6).

**Critical-part rules.** The band is `LOW` whatever the mean if either of these holds:
1. `conf_data_quality ≤ 0.50`. Any single ×0.5 penalty (causal frozen minutes, the 6 h after a gap or the frozen window, or a kiln-inlet O₂ bucket ≥ 15 %) is enough.
2. Fewer than 5 families are usable **and** the band is below HIGH. A missing family scores 0, so absence of evidence would otherwise read as normal.

History:
- The first rule was added during implementation, after POOR-data-quality buckets reached MEDIUM through the mean.
- It was tightened to `≤` and the O₂ penalty and second rule were added in review (DQ-1, DQ-4, SDS-4).

**Data-quality factor for the O₂ analyser.** `conf_data_quality` is also halved when the kiln-inlet O₂ bucket median is ≥ `o2_ambient_pct` = 15 %. That reads like ambient air (about 21 %), not kiln gas. This is a POC heuristic pending plant confirmation. It never changes the score.

**Cap:** `HIGH` is **capped to `MEDIUM`**, with `confidence_cap_reason = CAPPED_MEDIUM: NO_EVENT_GROUND_TRUTH; STATE_PROXY_UNCONFIRMED; EQUIPMENT_MAPPING_UNCONFIRMED`. The uncapped band is kept in `confidence_band_uncapped`.

---

## 7. Risk bands (empirical, conditional)

**Candidate edges:** reference-window P75 / P90 / P95 of `risk_score` over the VALID reference buckets. The planner's analysis suggested P99 would not be stable with about 20 independent 3-day blocks.

| Band | Condition |
|---|---|
| `LOW` | `< P75` |
| `ELEVATED` | `P75 … < P90` |
| `HIGH` | `P90 … < P95` |
| `VERY_HIGH` | `≥ P95` |

Each band means **resemblance relative to the Apr–May reference**. They are **not** plant limits.

**Support rule:**
- Each edge gets a 95 % CI from a 3-day block bootstrap (400 replicates, fixed seed).
- If the CI of an edge overlaps the CI of the next edge, the upper band is merged into the lower one.
- If no edge survives, the output is `CALIBRATION_INSUFFICIENT`, and `risk_band = UNBANDED` with score + confidence only.

Every edge is published with its rationale, population, date range, reference version, CI, April-fit / May-check result and sensitivity.

**Alert burden** is reported as `EMPIRICAL_ALERT_RATE`, never as a false-positive rate:
- the share of RUNNING time in each band, by month and by load band;
- episodes with hysteresis (open at ≥ HIGH, close below ELEVATED), their durations, and their stop / transition and data-quality contamination.

---

## 8. Reason codes (only those the calculation supports)

**Score drivers.** These add points to `risk_score`; `contribution` = points.

| Code | Active when |
|---|---|
| `EFFICIENCY_COMPONENT_DEVIATION` | `a_EFFICIENCY > 0.5` (Sp.Heat above the load-adjusted reference) |
| `COMBUSTION_DEVIATION` | `a_COMBUSTION > 0.5` |
| `THERMAL_DEVIATION` | `a_THERMAL > 0.5` |
| `DRAFT_PRESSURE_DEVIATION` | `a_DRAFT_PRESSURE > 0.5` |
| `PROCESS_VARIABILITY_DEVIATION` | `a_STABILITY > 0.5` |
| `MULTI_FAMILY_CONCURRENCE` | ≥ 2 families abnormal |
| `PERSISTENT_DEVIATION` | `P ≥ 0.5` (≥ 1.5 h of the last 3 h at or above `H_ref90`) |

**Context.** These never add points.

| Code | Active when |
|---|---|
| `LOAD_ASSOCIATED_CONDITION` | 1-h feed change ≥ reference P90, or outside the training load range |
| `POST_RESTART_SETTLING` | < 6 h since the last non-RUNNING bucket |

**Confidence.**

| Code | Active when |
|---|---|
| `DATA_QUALITY_REDUCED_CONFIDENCE` | `conf_data_quality < 0.75` |
| `REDUCED_FAMILY_COVERAGE` | < 5 usable families |

**Primary and secondary reasons.**
- `primary_reason` is the active score driver with the largest contribution. Ties are broken in the fixed code order.
- **Amended in 1.1.0.** `primary_reason` is always the part with the most points. If that part is not active (e.g. its family is below its reference P90, or persistence < 0.5), the code carries the suffix `_BELOW_THRESHOLD`. `NO_DEVIATION_FROM_REFERENCE` is used only when the score is 0.
- **AFR and Phase 4 are never reason codes.** AFR transitions come from retrospective labels, and the Phase 4 indicator has LOW confidence. They are reported only in the `afr_context` / `phase4_context` columns, so they cannot be read as drivers.
- **Confidence code `SUSPECT_ANALYSER_AMBIENT_O2`:** kiln-inlet O₂ bucket ≥ 15 %.
- `secondary_reasons` lists the remaining active codes (drivers by contribution, then context, then confidence), separated by `;`.

---

## 9. Load and operating-state treatment

- **Load adjustment.** Every scored level tag is already load-adjusted by Phase 3 (feed-conditional training medians), so high load is not, by itself, risk.
- **Load context.** `load_context` is `LOAD_ASSOCIATED` (as defined in §8), `STEADY_LOAD`, or `UNKNOWN` (no feed).
- **Load band.** `load_band` is `TENTATIVE_LOW` / `TENTATIVE_MID` / `TENTATIVE_HIGH`, from reference feed P33 / P67. It is context and slicing only. The Phase 2 bands are TENTATIVE (40 % bootstrap reproduction).
- **State transitions.** STOPPED and TRANSITION buckets get no score. Post-restart buckets are scored with reduced state confidence and the `POST_RESTART_SETTLING` context code.
- **Proxy uncertainty.** `Kiln MD` and the equipment identity stay unconfirmed. This is carried in the confidence cap and in `operating_state_label`.

---

## 10. AFR and Phase 4

- **AFR level and transitions** are context only. The AFR and Phase 4 inclusion tests add an optional 10 % component. Inclusion requires **all** of the following:
  - (a) a coverage-AUC gain of ≥ 0.02;
  - (b) a gain above the 95th percentile of a circular-shift null (≥ 7-day shifts);
  - (c) no loss of month-to-month stability.

  This gate can only add evidence and is conservative. Coverage is circular, so a pass would still be reported as tentative. The default is **exclusion**.
- **The Phase 4 indicator** (`Kiln-I!I|ROC_1H`, LOW confidence, not distinguishable from chance in Phase 6) is never given a dominant weight.

---

## 11. Architecture candidates (evaluated before selection)

| Candidate | Definition | Role |
|---|---|---|
| A | Weighted family score: `100 · mean_d a_d` | Simplest baseline |
| B | Concordance with "≥ 1 family abnormal" persistence: `100 · (0.5 · mean + 0.25 C + 0.25 P≥1)` | Draft design |
| H | This specification (max + mean magnitude, concurrence, persistence on `H_ref90`) | Proposed primary |
| C | Historical abnormal-profile similarity (weighted Jaccard vs the frozen library) | Descriptive only |

**Why C is descriptive only.** A "causal expanding" library built from Phase 6 final periods is not causal: `in_final_set` depends on full-period sensitivity analysis.

**Selection rule (pre-declared; the 12 periods are NOT a selection criterion):**
1. Meet the specification's requirements: family-aware, explicit persistence and concurrence, temporally safe.
2. Among the candidates that do, take the simplest, unless it is materially less stable. Material means reference-window perturbation Spearman < 0.80, or month-to-month band-agreement loss > 0.10, compared with a more complex candidate.

**Disclosure.** A feasibility prototype computed A / B / C coverage before this document was written. That exploration is why coverage is excluded from selection and why C was demoted.

---

## 12. Outputs (Phase 8 contract)

`risk_scores.parquet` columns:
- `timestamp`, `risk_score`, `risk_band`, `confidence_score`, `confidence_band`, `confidence_band_uncapped`, `confidence_cap_reason`, `risk_status`, `reference_state`;
- `operating_state`, `operating_state_label`, `load_band`, `load_context`, `feed_tph`, `kpi_value`, `kpi_band`;
- `family_count_abnormal`, `family_count_usable`, `persistence_minutes`, `historical_similarity`;
- `operational`, `magnitude_component`, `concurrence_component`, `persistence_component`;
- `data_quality_status`, `primary_reason`, `secondary_reasons`, `contributing_families`;
- `afr_context`, `phase4_context`, `reference_version`, `score_version`, `score_label`.

`persistence_minutes` is the length of the current run of consecutive buckets with `H ≥ H_ref90`.

Other outputs:
- `risk_score_components.parquet`: `timestamp, family, raw_measure, reference_measure, normalized_deviation, family_score, family_weight, family_contribution, usable, quality_flag, reason_code`.
- `risk_score_reasons.parquet`: one row per active reason.
- `risk_score_confidence.parquet`: the six parts, the score, the band and the cap.
- Plus the calibration, bands, feature inventory, robustness, data quality, validation, event similarity, summary and reference artifacts listed in `FEATURE_CONTRACT.md` / `VALIDATION_GATES.md`.

**Permitted downstream use:**
- ranking and trending of resemblance to reference-relative abnormal process conditions;
- prompts to check plant records.

**Prohibited interpretation:**
- deposit / ring / failure detection or probability;
- plant limits;
- set-points;
- control actions.
