# Phase 5 — Review Log

## Review process

- **Order.** Work followed the execution contract in this order: Understand → Inspect → Plan → Define → Implement → Validate → Review → Fix → Revalidate.
  - The **planner** ran first, before any implementation.
  - The first implementation was validated and given one clean end-to-end run (`run_phase5.py --clean`).
  - Three reviewers then reviewed that version in parallel, all read-only: **cs-product-analyst**, **python-reviewer** and **mle-reviewer**.
  - All valid findings were fixed, and the pipeline was re-run from a clean state twice (G7).
- **Agents used.**
  - `ecc:planner` (Agent 1).
  - `cs-product-analyst` (Agent 2). There is no agent of that exact name, so a general-purpose agent was briefed with the cs-product-analyst / product-analytics remit.
  - `ecc:python-reviewer` (Agent 3).
  - `ecc:mle-reviewer` (Agent 4).
- **database-reviewer (Agent 5): not invoked.** Phase 5 adds no database; it uses Parquet, CSV and JSON only.
- **Skills applied:**
  - senior-data-scientist, statistical-analyst and data-quality-auditor as analytical practice;
  - python-patterns;
  - product-analytics, through the product-analyst review;
  - observability-designer, through the manifest, input hashes, lineage columns and flags;
  - mle-workflow, through temporal separation, leakage tests and frozen fits;
  - dataviz for the figures (validated reference palette slots 1–3, a one-hue ordinal ramp, small multiples, no dual axes).
- **Hooks.**
  - **gateguard** (ECC fact-forcing gate) was active and was answered before every new file and the first Bash command. Its intent is also coded as the G2 checks:
    - every AFR and target tag exists in the Phase 1 inventory with its exact `original_name` and unit;
    - no Phase 2 held column is used;
    - no AFR variable is invented.
  - The load step's tag check caught three held targets during implementation: `CBS-Calculation!B`, `CBS-Calculation!C` and `Kiln-IA!F`, all `CONSTANT_COLUMN`. They were removed and documented in `af_core.EXCLUDED_TARGETS`.
  - **security-guidance:**
    - writes are confined to `phase-05-af-analysis/{outputs,reports,cache}`;
    - subprocesses use fixed argument lists with no shell;
    - no network is used;
    - the source and Phases 1–4 are hashed before and after every run.
- **ponytail.** Active for the session:
  - Phase 5 reuses the Phase 4 statistics core (`indicator_core.assoc`, `bh`, `build_buckets`, `future_target`, `controls`) and the Phase 3 loader read-only instead of re-implementing them.
  - The spec's script layout was kept because it was explicitly requested.
- **Housekeeping.** Nothing was written upstream. G7 snapshots the file lists and directory listings of Phase 3 and 4 (no `__pycache__`, no recreated `cache/`).

| Role | Verdict | Outcome |
|---|---|---|
| planner | Full design: architecture, AFR series choice, definitions, statistics, matching, negative controls, gates, risks | Adopted; deviations listed below |
| cs-product-analyst | 5 HIGH, 7 MEDIUM, 4 LOW (communication, not statistics) | All HIGH/MEDIUM addressed (PA-M2 partly, as the spec fixes the band names); all LOW addressed |
| python-reviewer | 0 CRITICAL, 1 HIGH, 2 MEDIUM, 1 LOW | HIGH and MEDIUM fixed or documented; LOW deferred |
| mle-reviewer | PASS-WITH-CONDITIONS; 2 MEDIUM, 1 LOW; no leakage found | All addressed |

## Planner (before implementation)

| # | Recommendation | Disposition |
|---|---|---|
| P1 | Build a self-contained Phase 5 cache from `data/processed`. Read only official Phase 4 outputs, never the Phase 4 cache. | **Adopted.** |
| P2 | Guard the `p4common` import, which calls `mkdir`. Never use the Phase 4 writers. | **Adopted.** `af_core` checks that the upstream directories exist and aborts otherwise. Phase 5 has its own writers. |
| P3 | Primary AFR series: Phase 2-valid, negatives removed, dataset frozen rows removed, no single-tag flatline mask (constant integer firing is legitimate). The Phase 3-masked and no-P2-flatline versions go into sensitivity G. | **Adopted.** |
| P4 | Zero cut 0.5 TPH (integer data). Bands from discovery non-zero P25 / P75. | **Adopted.** Cuts: 31 / 35.5 TPH. |
| P5 | Transition definitions, eligibility, feed-matched controls, LOAD_COINCIDENT flag | **Adopted.** Pre-window cleanliness was later strengthened (PY-H1). |
| P6 | Analysis types LAGGED_LEVEL / FUTURE_CHANGE / MOMENTUM. `ic.assoc`, BH per family × type, lag chosen on discovery only, pre-declared evidence rules. | **Adopted, with one change.** The planner's FUTURE_CHANGE control on the concurrent *future* feed change was **not** used: controls use data ≤ t only, which is the cleaner leakage stance. |
| P7 | Matched ON/OFF with a balance gate, or MATCHING_NOT_SUPPORTED | **Adopted.** Minimum pairs / days are 30 / 5, pre-declared before matching was run; the planner suggested 200 / 10. Every comparison is still MATCHING_NOT_SUPPORTED. |
| P8 | Negative controls: circular shift, misaligned AFR, randomised transition labels | **Adopted.** Randomised labels are implemented as a within-matched-set label permutation. |
| P9 | Sp.Heat derivation check (flag if R² > 0.95) | **Adopted.** R² ≈ 0.92 (F) and 0.65 (G) on discovery buckets, below 0.95, so the rows are not flagged "derived". They are reported as "closely reproducible; consistent with being calculated; plant to confirm", and the confidence cap applies (PA-M5). |
| P10 | Confidence MEDIUM only if ≥ 6 of 8 groups agree | **Changed before any sensitivity result was seen.** Episode rows have at most 4 applicable groups, so the rule is now ≥ 4 groups evaluated with ≥ 80 % agreeing. HIGH is never assigned. |

## Python reviewer

| # | Sev | Finding | Disposition |
|---|---|---|---|
| PY-H1 | HIGH | `episode_status` checked only kiln-running status in the 6-h pre-window, not other AFR transitions. For example, an AFR_START 60 min after an AFR_STOP was ELIGIBLE with a contaminated [T−60, T) baseline. | **Fixed.** A new `EXCLUDED_PRIOR_TRANSITION` status applies when another detected transition falls in [T−120 min−6 h, T). Added a unit test and an independent G3 check. The post window may still contain the AFR restart, which is documented as part of the episode. |
| PY-M1 | MED | `buckets.reindex(g.index)` had no grid-equality check | **Fixed.** The run now fails hard if the Phase 3 KPI grid has buckets missing from the rebuilt grid, or if more than the leading partial bucket is dropped. |
| PY-M2 | MED | The `days` mask in `assoc_one` duplicates the mask inside `ic.assoc` | **Documented.** `ic.assoc` is Phase 4 code and must not be modified. An inline comment marks the coupling. |
| PY-L1 | LOW | `load_context` is called twice in the thermal and efficiency steps | **Deferred.** The files are small (< 1 MB) and there is no correctness impact. |
| — | — | Verified correct: `window_delta`, `detect_transitions`, `whole_last_hour`, `design` / `rows_for`, the idempotent `finalise`, non-vacuous validation checks, disjoint parallel outputs | — |

## MLE reviewer — PASS-WITH-CONDITIONS

| # | Sev | Finding | Disposition |
|---|---|---|---|
| MLE-M1 | MED | The G7 determinism row was FAIL for `afr_efficiency_relationships.csv` | **Root-caused.** The "previous run" was an earlier piecemeal manual run, made before a KPI flag string was renamed, so the file legitimately differed. It was not non-determinism: every RNG is seeded through SHA-256 and BLAS is single-threaded. The gate was **not** relaxed. After the fixes, two consecutive `--clean` runs were compared (see the README and `afr_validation.csv`). |
| MLE-M2 | MED | "Holdout not REVERSED" is a weak August bar for ASSOCIATED | **Addressed in reporting**; the rule itself is pre-declared and unchanged. The report now states how many ASSOCIATED rows August CONFIRMED versus SAME / OPPOSITE_DIRECTION_NS / NOT_EVALUABLE (§1 reviewer notes, §20). |
| MLE-L1 | LOW | Coal / PC controls may act as mediators as well as confounders | **Addressed.** An explicit methodology (§15) and limitations (§21) sentence was added: bias toward zero; sensitivity C removes the controls. |
| — | — | No leakage found. The G3 perturbation test, discovery-only lag / band fits, the permutation test's validity and MATCHING_NOT_SUPPORTED were all confirmed. Report counts were re-computed and match. | — |

## Product analyst

| # | Sev | Finding | Disposition |
|---|---|---|---|
| PA-H1 | HIGH | Tables show tag IDs without names | **Fixed.** A `name (unit)` column is in every relationship and episode table. |
| PA-H2 | HIGH | The summary called the PC post-stop rise "clearest" although that row has LOW confidence | **Fixed.** The summary now separates the ASSOCIATED correlations from the LOW-confidence post-stop rise. |
| PA-H3 | HIGH | Validation was shown as a raw dict, and the FAIL was not explained | **Fixed.** Counts are written out in words, and any FAIL is spelled out in §1. |
| PA-H4 | HIGH | Sp.Heat "arithmetic" was presented as a finding | **Fixed.** Now "closely reproducible … consistent with being calculated … may be largely arithmetic; plant to confirm". The collinearity caveat is stated and the F5 title reworded. |
| PA-H5 | HIGH | No plant-questions section, and a dangling "plant question 4" | **Fixed.** Added §22a with Q1–Q7, each mapped to the findings it resolves. The reference now points to §22a Q1. |
| PA-M1 | MED | Data-requirement priorities were inverted and `enables` was truncated | **Fixed.** The Sp.Heat definition, set-point documentation and AFR operating log are now priority 1. Added `unblocks_finding` and `effort` columns. The table is no longer truncated. |
| PA-M2 | MED | Band names read like operating windows | **Partly.** The spec names NO / LOW / MEDIUM / HIGH_AFR, so the names are kept. Added the caption "not a target range, operating window or plant limit" and the `not_a` column to the table. |
| PA-M3 | MED | No glossary | **Fixed.** A glossary follows §2. |
| PA-M4 | MED | "response" implied AFR produced the change | **Fixed.** The column is now `window_compared`, the interpretations say "in the window around … episodes", and the note that PC coal and feed change in the same window was added. |
| PA-M5 | MED | MEDIUM confidence on co-manipulation and Sp.Heat rows inflates the headline | **Fixed.** A `confidence_cap_reason` column caps co-manipulation, Sp.Heat and Sp.Heat-based KPI rows at LOW. ASSOCIATED rows are counted by kind (process / co-manipulation / Sp.Heat-KPI). |
| PA-M6 | MED | Indicator claim close to tautology; unclear units | **Fixed.** Units are now percentage points. The finding is reworded as "fires mostly when AFR is falling (expected: it is the PC-coal trend)". |
| PA-M7 | MED | NOT SUPPORTED interpretations said "co-varied" | **Fixed.** They now read "no supported co-variation …". |
| PA-L1 | LOW | Main tables were buried in NOT SUPPORTED rows | **Fixed.** §§9–11 show ASSOCIATED / WEAK rows only, with counts, and point to the CSVs. |
| PA-L2 | LOW | Two framings of zero share | **Fixed.** One framing is used: "% of AFR = 0 minutes occur while the kiln is not running". |
| PA-L3 | LOW | Plant-useful content buried | **Fixed.** §1 is now Operational takeaways → Evidence detail → Reviewer notes. |
| PA-L4 | LOW | Duty-cycle denominator | **Fixed.** A caption was added under §7. |

## Post-review revalidation (issues found while re-running after the fixes)

| # | Issue | Disposition |
|---|---|---|
| RV-1 | The first PY-H1 fix excluded any AFR transition in the 6 h before the episode window. That removed almost all AFR_START (28 → 1) and AFR_RAMP_UP (39 → 3) episodes. Most starts, and many ramp-ups, are recoveries from interruptions that began less than 2 h earlier. | **Rule narrowed.** The reviewer's concern was contamination of the displayed pre-window and its [T−60, T) baseline, so the primary rule now excludes another transition inside the pre-window [T−120, T). The strict 6-h version is reported as sensitivity **E / no_other_transition_6h_before_window**. This choice was made after seeing the counts, and it is disclosed here and in report §8. |
| RV-2 | The PA-M5 confidence cap never fired, because `r.flags` on a pandas row returns the built-in `Series.flags` object, not the column. Co-manipulation and Sp.Heat rows still showed MEDIUM. `KPI:D` also lacked the Sp.Heat flag (D is half efficiency, i.e. Sp.Heat). | **Fixed** (`r["flags"]`, KPI:D flagged). Added a unit test and an independent G6 check: no capped relationship may carry MEDIUM. The same `.flags` trap in `generate_report.py` was fixed earlier. |
| RV-3 | The report wording scanner flagged the negated caption "…is **not** … a plant limit". | Negated forms were added to the scanner's allowed context. The scanner still rejects un-negated uses (unit-tested). |
| RV-4 | G7 FAIL on intermediate runs | Each was a comparison against a run made before a code or report edit, so the difference was legitimate. The final two consecutive `--clean` runs, made with no edits between them, are the determinism evidence (README). |
