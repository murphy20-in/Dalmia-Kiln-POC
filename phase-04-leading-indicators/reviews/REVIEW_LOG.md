# Phase 4 — Review Log

## Review process

- **Order.** The planner ran first. The first implementation was then validated and given one clean run. The three reviewers (python-reviewer, mle-reviewer, cs-product-analyst) reviewed that version. All valid findings were fixed, the pipeline was run from a clean state twice, and a confirmatory re-review checked the fixes.
- **Agents.** The environment has no agents named `planner`, `cs-product-analyst`, `python-reviewer` or `mle-reviewer`. As in Phases 2 and 3:
  - The planner role was run with the `Plan` agent.
  - The three reviewer roles were run with general-purpose agents, each briefed with its role's remit.
  - The three reviews ran in parallel, all read-only against the same version. Their fixes were applied in the contract's order: python, then MLE, then product.
- **Read-only.** All reviews were read-only, with no network access. Scratch probes went only to `/tmp/claude-1000/`.
- **Not invoked.** `database-reviewer` was not run, because Phase 4 adds no database (Parquet, CSV and JSON only).
- **Skills.** These were loaded before implementation: senior-data-scientist, statistical-analyst, data-quality-auditor, python-patterns, product-analytics, observability-designer and mle-workflow; dataviz was loaded for the figures.
- **Hooks and plugins.**
  - **gateguard:** its intent (every tag must exist, names and units preserved, holds excluded, nothing invented) is implemented as the G2 checks.
  - **security-guidance:** its intent is followed. Writes are confined to phase-04. Subprocesses use fixed argument lists with no shell. No network is used.
  - **ponytail:** the plugin is not installed, so its intent was followed manually.
- **Housekeeping.** An exploratory timing probe during planning, run before the bytecode guard existed, wrote `phase-03-efficiency-kpi/scripts/__pycache__/load_phase2_inputs.cpython-314.pyc`. That file is gitignored and is not a Phase 3 output. It was deleted, and no other Phase 3 file changed (verified by modification time). The pipeline now sets `sys.dont_write_bytecode` before importing Phase 3, and every run snapshots Phase 3's scripts, tests, cache and reports before and after (G7).

| Role | Verdict | Outcome |
|---|---|---|
| planner | Full plan: circularity, safe Phase 3 import, n_eff, BH, gating, episodes, gates | Adopted. Deviations are listed below. |
| python-reviewer | No CRITICAL. 2 HIGH, 6 MEDIUM, 8 LOW. The core time-series code and the leakage test were verified correct. | All fixed. |
| mle-reviewer | PASS-WITH-CONDITIONS. 3 HIGH, 4 MEDIUM, 4 LOW. No leakage. The statistics were reproduced exactly, and 2 extra leakage cuts matched exactly. | All conditions addressed by a change of design, not of wording only. |
| cs-product-analyst | 5 HIGH, 8 MEDIUM, 4 LOW | All fixed. |
| confirmatory re-review | See the last section | — |

## Planner (before implementation)

| # | Recommendation | Disposition |
|---|---|---|
| P1 | The target is the future KPI change with controls K(t), momentum and Kpend; KPI inputs are tiered | **Adopted** (the circularity design). |
| P2 | Import Phase 3 read-only without bytecode; append its path; rebuild the state on the exact Phase 3 subset | **Adopted.** The G3 check confirms the bucket state equals Phase 3's. |
| P3 | Small-dataset frozen rule | **Adopted**, only for datasets outside the Phase 3 KPI subset, so the Phase 3-subset masks stay identical. |
| P4 | Candidate rules C1–C8 on discovery; the CBS datasets are in the universe; AFR stays context | **Adopted.** AFR is reserved for Phase 5 rather than analysed. |
| P5 | Coverage rule on the discovery window | **Refined.** Coverage is judged on the dataset's available discovery months, because Kiln-IIIA has no April export. This was pre-declared before any evaluation result was seen. |
| P6 | n_eff, day-block bootstrap, BH, month replication, equal-weight criteria, confidence classes, complementary set | **Adopted.** The block length and temporal design were later changed (MLE-M1, MLE-H3). |
| P7 | Episodes E_BAND / E_RISE with controls | **Adopted.** Onsets less than 12 h apart are merged into independent episodes, because E_BAND and E_RISE flag the same events. Episodes are later anchored at the start of the rise (MLE-M2). |
| P8 | Gates G1–G7, including planted lead, placebo, AR(1) null and leakage cuts | **Adopted and strengthened** (PY-H2, MLE-M4). |

## Python reviewer

| # | Sev | Finding | Disposition |
|---|---|---|---|
| PY-H1 | HIGH | The episode lead was uninformative. Crossings are frequent, a condition already active before the window got the full 720 min, and control leads were not reported. | **Fixed.** `first_lead` counts only a *new* crossing that starts inside the window after ≥ 30 min clear. The control median lead is reported. The episode lead is suppressed when lift ≤ 0. |
| PY-H2 | HIGH | About 12 PASS rows could not fail. | **Fixed.** `indicator_validation.csv` has a `check_type` column: INDEPENDENT, REGRESSION_GUARD or INFO. Hard-coded checks became INFO. The state mask is now an independent grid scan. BH is compared against `scipy.stats.false_discovery_control`. The bootstrap check re-computes 20 random rows. A new null-calibration check shifts all 980 features. |
| PY-M1 | MED | Gate c passed when the load check was NaN. | **Fixed.** The flag is tri-state, and only an explicit "survives" passes. |
| PY-M2 | MED | Gate d passed on NaN and ignored sign. | **Fixed.** NaN fails. The forward association must have the discovery sign and be at least as strong as the backward one. |
| PY-M3 | MED | Missing criteria were handled inconsistently. | **Fixed.** The denominator is fixed at 9, and missing evidence scores 0. |
| PY-M4 | MED | Precision included post-restart KPI jumps and partial windows, and the base rate used different rows. | **Fixed.** `future_max_rise` requires RUNNING over the whole window and ≥ 2/3 coverage. Shutdown-adjacent alarms are SHUTDOWN_RELATED and not evaluable. The base rate uses exactly the same rule. |
| PY-M5 | MED | The published lead time was the OOS argmax. | **Fixed** (see MLE-H2). |
| PY-M6 | MED | The determinism check was vacuous on a first run and skipped files. | **Fixed.** All 14 key outputs must be compared; otherwise the result is FAIL or NOT_MET_REPORTED ("run twice"). The last run compared 14/14, all byte-identical. |
| PY-L1 | LOW | Empty blocks stayed in the bootstrap. | **Fixed.** `assoc` compacts blocks over the rows actually used and draws its weights from a seed. |
| PY-L2 | LOW | An unknown window name failed silently. | **Fixed.** It now raises `ValueError` (tested). |
| PY-L3 | LOW | Control exclusion used kept onsets only. | **Fixed.** It uses every raw onset and anchor (tested). |
| PY-L4 | LOW | Selection read 6-dp rounded CSVs. | **Fixed.** Internal hand-offs use an unrounded `cache/lag_analysis.parquet` and `cache/lead_time.parquet`. |
| PY-L5 | LOW | Dead code and unused imports. | **Fixed.** The AST scan is clean. The `DUPLICATES` global was removed. |
| PY-L6 | LOW | Hard-coded bucket counts. | **Partly fixed.** `min_valid` is derived from the window, and the lead-time and false-lead code uses `buckets_in`. The 6/36-bucket constants in `controls()` stay, because they are the Phase 3 definition (1 h and 6 h at 10 min) and are documented inline. |
| PY-L7 | LOW | BLAS oversubscription and a slow AR(1) loop. | **Fixed.** `OMP/OPENBLAS/MKL_NUM_THREADS=1` for all steps, and `scipy.signal.lfilter` for the AR(1) series. |
| PY-L8 | LOW | Missing unit tests. | **Fixed.** 32 tests now, up from 25: band target, `future_max_rise`, `rise_onsets` / `rise_start`, control exclusion, an already-active crossing, window guard and row filters, confidence caps and direction wording. |

## MLE reviewer

| # | Sev | Finding | Disposition |
|---|---|---|---|
| MLE-H1 | HIGH | The single external indicator (kiln drive power ROC) was over-claimed: June reversed, the episode lift was negative, and it was fragile. | **Resolved by the redesign.** Under the stricter design that indicator fails replication and the shift null, and is now UNSTABLE. The one indicator that now passes (PC coal firing ROC_1H) is presented as weak and tentative, with LOW confidence. The executive summary states its manipulated-variable caveat, the holdout result (same sign, not significant), the precision lift, and the negative episode lift. |
| MLE-H2 | HIGH | The lead time was chosen on evaluation data. | **Fixed.** `lead_time_minutes` equals the discovery-chosen lag. The best June–July lag and the stable range are labelled POST-HOC DESCRIPTIVE. |
| MLE-H3 | HIGH | No untouched test data: Jun–Aug selected and reported. | **Fixed by design.** Discovery (Apr–May) chooses lag and sign. Replication (Jun–Jul) drives every gate, criterion, score and the set. The **August holdout** is never used for gating, scoring, ranking or selection, and is reported once as `holdout_result`. The report states the winner's-curse bias of the replication estimates. The tautological G5 check was replaced by an INFO row with the holdout result. |
| MLE-M1 | MED | 1-day blocks were anti-conservative. | **Fixed.** 3-day blocks are the primary; 1-day blocks are a sensitivity variant. A circular-shift null (58 shifts of 2–59 days, one-sided) is a new **gate f**. |
| MLE-M2 | MED | Episode onsets fell after most of the rise, and controls were poorly matched. | **Fixed.** Episodes are anchored at the lowest KPI bucket within the 6 h before the detected onset. Controls are matched on K at the anchor and 12 h before, and exclude ±24 h around every raw onset. |
| MLE-M3 | MED | KPI_PROXY tags could enter the set. | **Fixed.** They are routed to KPI_PROXY_PRECURSOR and capped at LOW. The G5 guard covers both tiers. |
| MLE-M4 | MED | G4 checks were weak or placeholders. | **Fixed.** New checks: null calibration over all features (6.6 % with p < 0.05, 0 BH discoveries), AR(1) nulls at three φ values, and check types. |
| MLE-L1 | LOW | Results depend on the future RUNNING state. | **Documented.** The report states that results apply to RUNNING horizons only and are not deployable as-is. |
| MLE-L2 | LOW | In-sample discovery KPI and Phase 2 hindsight RUNNING mask. | **Kept and disclosed**, confined to Apr–May. |
| MLE-L3 | LOW | Coverage flags use evaluation months. | **Documented.** They affect evaluability, not lag or sign. The c6 criterion now uses replication coverage only. |
| MLE-L4 | LOW | "Rolling origin" was the wrong term; stale `__pycache__`. | **Fixed.** The design is called "fixed-origin monthly replication with a holdout", and the cache was removed. |

## Product analyst

| # | Sev | Finding | Disposition |
|---|---|---|---|
| PA-H1 | HIGH | The `flags` column was corrupt (pandas `DataFrame.flags`). | **Fixed.** It is now `s["flags"]` and contains real text. A `manipulated_variable` column was added. |
| PA-H2 | HIGH | The negative episode lift was not stated. | **Fixed.** The summary line of every selected indicator states its hit rate against controls. |
| PA-H3 | HIGH | Lead-time confidence was overstated. | **Fixed.** It is capped at the indicator's confidence and requires the discovery lag to lie inside the replication stable range. |
| PA-H4 | HIGH | "Passes every gate" hid fragility. | **Fixed.** The summary gives the months, the shift-null p, the holdout, precision and episode lift. The NOT_MET_REPORTED rows are in section 17. |
| PA-H5 | HIGH | Lead-time fields were filled for LAGGING and UNSTABLE rows. | **Fixed.** They are empty or "NOT_APPLICABLE" unless the relationship is LEADING. A `usable_downstream` column was added. |
| PA-M1 | MED | Names could not be read. | **Fixed.** A `display_name` column (dataset · group \| name (unit), e.g. "Kiln-I · Coal Firing \| PC (TPH)") and a `naming_confidence` column. |
| PA-M2 | MED | Direction wording did not match the feature type. | **Fixed.** FALLING/RISING TREND, LOWER/HIGHER LEVEL, VARIABILITY and TIME ABOVE/BELOW BAND wording. |
| PA-M3 | MED | Jargon. | **Fixed.** A glossary for plant users, a note on how the labels relate, positive gate names ("NOT survives feed controls"), and DISCLOSED renamed to NOT_MET_REPORTED. |
| PA-M4 | MED | Misleading precision range. | **Fixed.** The summary quotes the selected indicator's crossings per 7 days, its precision against the base rate, and the lift. |
| PA-M5 | MED | Taxonomy inconsistencies. | **Fixed.** LOAD_CONTEXT confidence is NOT_APPLICABLE, and the load column says "IS THE LOAD CONTEXT". `process_family` and `feature_category` are separate vocabularies. |
| PA-M6 | MED | Threshold units. | **Fixed.** New columns `alarm_threshold_unit`, `alarm_threshold_direction` and `threshold_label`. |
| PA-M7 | MED | Missing downstream fields. | **Fixed.** Monthly effects, significant months, n_eff, shift-null p, holdout effect, CI and result, alarms, precision, base rate, hit rates, `permitted_use`, and a Phase 7/8 consumer rules section. |
| PA-M8 | MED | Comparison with the KPI's own momentum. | **Fixed.** Stated in the summary (momentum raw ρ ≈ 0.47 at 60 min). |
| PA-L1 | LOW | Too many lead numbers. | **Fixed.** One headline lead (the discovery lag); the others are labelled post-hoc. |
| PA-L2 | LOW | No "what a user may do" line. | **Fixed.** "For discussion and review only; no operating action, alarm or limit is implied." |
| PA-L3 | LOW | Formatting of `exclusion_reason`. | **Fixed.** A single clean reason. |
| PA-L4 | LOW | Under-claimed null result. | **Fixed.** "Practical finding: very few process signals lead this KPI, and only weakly." |

## Not changed, with reasons

- **The in-sample Phase 3 KPI in discovery.** It is the only KPI available for April–May. It is disclosed and confined to discovery, and every gate is decided out of sample.
- **Sp.Heat F / G.** Neither definition is declared authoritative. The F-vs-G ranking materiality is NOT_MET_REPORTED (Spearman 0.67; 0.75 without KPI inputs). The plant must confirm which definition is authoritative.
- **Alternative KPI reference in sensitivity.** It is evaluated on 16–31 July only, to keep August untouched.

## Confirmatory re-review

A read-only re-review of the final code and outputs checked every earlier HIGH and MEDIUM finding. It also confirmed that the code hashes match the manifest.

- **Result:** every HIGH and MEDIUM finding is **RESOLVED**; PA-M5 was cosmetically partial. It found **no new CRITICAL or HIGH** issue.
- **Cross-check:** the report numbers (tests, episodes, validation counts, momentum ρ, lifts, classes) agree with the CSVs.

It raised four LOW findings, all fixed before the final two clean runs:

| # | Finding | Disposition |
|---|---|---|
| R-L1 | "N/A" was read back as NaN by pandas, so the load-context row dropped out of report tables. | **Fixed.** The value is now `NOT_APPLICABLE`, and the report fills text columns with "". |
| R-L2 | `indicator_lead_time.csv` held the uncapped lead-time confidence (HIGH vs LOW elsewhere). | **Fixed.** The column is renamed `lead_time_confidence_uncapped`. The published `lead_time_confidence` (scores and set) is the capped value. |
| R-L3 | Stale docstring: the alternative reference window. | **Fixed:** 16–31 July, inside the replication window. |
| R-L4 | The "load proxies lose the lead under feed controls" line counted feed itself. | **Fixed.** The report separates the load context itself from the signals that fail the feed-control gate. |
