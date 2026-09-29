# Phase 6 — Review Log

| Order | Agent | Scope | Verdict |
|---|---|---|---|
| 1 | `planner` (ecc:planner) | Phase 1–5 outputs, signals, detection / merge / severity / confidence / validation design | Plan adopted (deviations below) |
| 2 | `python-reviewer` (ecc:python-reviewer) | All 19 scripts + tests | **Approve**: 0 CRITICAL, 0 HIGH |
| 3 | `mle-reviewer` (ecc:mle-reviewer) | Leakage, thresholds, temporal separation, robustness, reproducibility | **PASS-WITH-CONDITIONS**: 1 HIGH, conditions resolved |
| 4 | `cs-product-analyst` (product review agent) | Report, summaries, labels, wording | 5 HIGH / 7 MEDIUM / 4 LOW, all resolved |
| — | `database-reviewer` | Not run | No database introduced |

The python, MLE and product reviews ran in parallel on the same build (each is read-only and independent). All findings were then resolved in one pass. The pipeline was re-run from a clean state twice, and all gates were re-run: **47 PASS, 0 FAIL, 2 NOT_MET_REPORTED, 1 INFO**, with 15/15 key files byte-identical.

## 1. Planner

**Adopted:**
- KPI-led candidates at the frozen Phase 3 P90 cut (41.82), with a 60-min merge gap and a 60-min minimum (short periods kept as SHORT_TRANSIENT).
- Apr–May flagged in-sample and excluded.
- Family deviation from the Phase 3 S_d against the frozen family P90s, with no baseline refit.
- Mahalanobis KPI as the secondary multivariate method.
- CUSUM onset.
- The context precedence list.
- The 0.4 / 0.3 / 0.3 severity weights, with the P99 / 6-h severity classes.
- Confidence capped at MEDIUM.
- Sensitivity A–I, negative controls NC1–NC5, and the truncation leakage test.
- A shared pure core (`abn_core.py`) behind thin mandated scripts.

**Deviations, each with its reason:**
- **CUSUM k / h.** The textbook k = 0.5 / h = 5 on the autocorrelated D never reset: the training P50 of S was about 98, and every episode was flagged. The CUSUM was re-calibrated on training data: k is half the median-to-P90 shift, and h is the training P90 of the 6-h CUSUM rise, giving a training alarm rate of 10.0 % (a G5 check).
- **Feed "small change" thresholds.** They use the training P75, because the P50 of the feed change is exactly 0.
- **AFR_TRANSITION category.** It requires an AFR stop / ramp-down near the onset ([onset − 3 h, onset + 1 h]), not anywhere in a long episode.
- **Pre / post windows.** The pre-window is anchored at the onset and the post-window at the episode end. Both were planner-open decisions.
- **Pre-event controls.** Feed-matched pre-event controls were replaced by an out-of-sample base rate per signal, plus NC2 random windows.
- **Mahalanobis KPI.** It is not recomputed for Apr–May. It is NaN in-sample, and Apr–May is calibration-only.

## 2. python-reviewer — Approve

| # | Sev | Finding | Resolution |
|---|---|---|---|
| P1 | MEDIUM | `robust()` silently returns NaN on an empty training array (`max(nan, 1e-9)` is NaN) | **Fixed**: raises `ValueError` |
| P2 | LOW | `hi = 60.0` literal for the Mahalanobis-led variant | **Fixed**: named constant `MAHA_SEVERITY_HI`, documented as sensitivity-only |
| P3 | LOW | Family ratio divides by a P90 that could be 0 | **Fixed**: guarded (NaN if P90 ≤ 0) |
| P4 | INFO | Pure-Python CUSUM loop is a scaling ceiling | **Documented**: `ponytail:` comment with the upgrade path. No change at 26 k buckets / 40 s |

## 3. mle-reviewer — PASS-WITH-CONDITIONS

| # | Sev | Finding | Resolution |
|---|---|---|---|
| M1 | HIGH | The leakage test and unit test do not compare context / classification / `in_final_set` under truncation, although SHUTDOWN looks 2 h past the end | **Fixed.** The leakage test now also compares `primary_context`, `secondary_context`, `classification`, `in_final_set`, `load_context`, `afr_context`, `data_quality_context`, `severity_class` and `episode_type` for every episode whose end + max(merge gap, SHUTDOWN, AFR) look-ahead lies inside the truncated data. The unit test does the same, and the report states which fields are causal and which are retrospective. Result: 13/13 cut points identical |
| M2 | MEDIUM | `conf_sp_heat_fg` uses the K cut, which is nominal for the F / G KPIs | **Fixed**: removed from the averaged score and reported as `sp_heat_fg_agreement` |
| M3 | MEDIUM | Comment calls the Phase 2 events "context only", but they gate the final set | **Fixed**: the comment now states they are retrospective but gate membership, and that SHUTDOWN looks ahead |
| M4 | LOW | Stricter family-count variants are missing from the headline robustness | **Fixed**: D_2 / D_3 retention (92 % / 58 %) added to the executive summary and README |
| M5 | LOW | NC3 p-value comes from several related statistics / shifts | **Fixed**: the report labels it exploratory and states the number of statistics / shifts |

## 4. cs-product-analyst

| # | Sev | Finding | Resolution |
|---|---|---|---|
| U1 | HIGH | Apr–May periods carry the `HISTORICAL_ABNORMAL_PERIOD` label | **Fixed**: new label `CALIBRATION_ONLY_ABNORMAL_LIKE`, with a G3 check that no in-sample period has the final label |
| U2 | HIGH | "Event" wording; `SUPPORTED` type reads as a validated mode | **Fixed**: report title "Historical Abnormal Periods"; §18 / §19 subtitled "before onset" / "after the end"; `SUPPORTED` renamed `RECURS_ACROSS_MONTHS`. The mandated file and section names are kept |
| U3 | HIGH | Reference-dependence caveat is buried | **Fixed**: third banner line at the top of the report |
| U4 | HIGH | 18.5-h P6-021 is filed as "ordinary context" under an AFR-named category | **Partly changed.** The category name AFR_TRANSITION is mandated, so it is kept. The report now explains it as a rule outcome, not an explanation, names P6-021 in the executive summary and §12, and adds it to plant question 2 |
| U5 | HIGH | "Coincidence, never a cause" is contradictory | **Fixed**: now "more often than chance; this analysis cannot tell whether AFR changes contributed or were a response". The summary says "(context; causal role not assessed)", and the suffix is dropped when there is no AFR transition |
| U6 | MEDIUM | `evidence_summary` is not investigable | **Fixed**: onset / detection time, top tags with direction and median robust z, feed change, context, post-end outcome, a "to check against plant records" list, and "Empirical POC period, not a validated plant event" |
| U7 | MEDIUM | Load cut may itself be the abnormality | **Fixed**: `feed_change_vs_pre2h` column in §24, with guidance to check whether the feed cut came before or after the symptoms |
| U8 | MEDIUM | Confidence meaning unclear; parts may double-count | **Fixed**: confidence defined as internal consistency, with MEDIUM as the ceiling. `band_margin` (already inside Phase 3 `kpi_confidence`) was removed from the score. Checked: `conf_kpi_quality` and `conf_band_margin` were not numerically identical (ρ = −0.32), but they overlap conceptually |
| U9 | MEDIUM | Severity cliff; could read as risk | **Fixed**: read as "deviation magnitude"; HIGH is defined in plain words, with a boundary note. The field name is mandated and kept |
| U10 | MEDIUM | KPI scale not explained | **Fixed**: plain sentence in §1 ("exceeded in 10 % of Apr–May running operation, not a plant limit"). The cap of tag scores at 10 is stated in `top_tags` |
| U11 | MEDIUM | Long tables drown the 12 periods | **Fixed**: candidate, change-point, context, DQ, multivariate, tag and full-validation tables moved to an appendix (A1–A7), with one-line summaries in the body and a "How to read this table" key in §24 |
| U12 | MEDIUM | Executive summary uses raw dicts and jargon | **Fixed**: rewritten as prose |
| U13 | LOW | "False positive" naming | **Fixed**: `n_ordinary_context_category`; the validation text says "ordinary-context (false-positive)" |
| U14 | LOW | Type-level columns repeat on episode rows | **Fixed**: prefixed `type_` |
| U15 | LOW | `TRANSITIONED_TO_STOP` implies a consequence | **Fixed**: `FOLLOWED_BY_STOP (sequence only, not a consequence)` |
| U16 | LOW | Phase 5 background line reads as a finding | **Fixed**: "Phase 5 observation, not re-tested here" |

## 5. Open items (not defects)

- **NOT_MET_REPORTED, pre-declared robustness expectation.** The threshold and reference variants (A_lo, A_hi, A_alt, I_F, I_G) change the episode extent, and the alternative Jun–Jul15 reference keeps only 8 % of the final periods. This is a data property, reported and not hidden.
- **No unresolved CRITICAL or HIGH finding remains.**
