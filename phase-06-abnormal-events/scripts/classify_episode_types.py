"""Step 11 - Empirical episode types (analytical categories, NOT plant failure modes).

Rule-based (abn_core.episode_type): the ordinary-transition / data contexts map to TRANSITIONAL, LOAD_ASSOCIATED,
DATA_QUALITY, AFR_CONTEXT, CONTROL_CONTEXT, SHORT_TRANSIENT; otherwise MULTI_FAMILY (>= 3 deviating families and the top
two family ratios within 0.25) or <FAMILY>_DOMINANT (largest ratio of episode median S_d to its training P90), or
KPI_AGGREGATE_ONLY. A type is RECURS_ACROSS_MONTHS (a descriptive recurrence, not a validated mode) only with >= 5
out-of-sample episodes in >= 2 of Jun / Jul / Aug (declared in the plan before the episodes were seen); otherwise it is listed but marked INSUFFICIENT_SUPPORT. Clustering was not run: the
out-of-sample final set is too small for a stable clustering (see the report).
Writes outputs/abnormal_episode_types.csv.
"""
from __future__ import annotations

from abn_core import FAMILIES, load_stage, log, write_csv

lg = log("classify_episode_types")
MIN_EPISODES, MIN_MONTHS = 5, 2


def main():
    ep = load_stage("episodes")
    oos = ep[ep.reference_state.eq("OUT_OF_SAMPLE")]
    sup = oos.groupby("episode_type").agg(type_n_oos=("episode_id", "size"), type_months=("month", "nunique"),
                                          type_month_list=("month", lambda m: ";".join(sorted(set(m)))))
    out = ep[["episode_id", "reference_state", "month", "classification", "primary_context", "episode_type",
              "dominant_family", "family_count", "deviating_families", "load_context", "afr_context",
              "severity_class"] + [f"{d.lower()}_deviation" for d in FAMILIES]].copy()
    out = out.merge(sup, left_on="episode_type", right_index=True, how="left")
    out[["type_n_oos", "type_months"]] = out[["type_n_oos", "type_months"]].fillna(0).astype(int)
    out["type_support"] = ((out.type_n_oos >= MIN_EPISODES) & (out.type_months >= MIN_MONTHS)).map(
        {True: "RECURS_ACROSS_MONTHS", False: "INSUFFICIENT_SUPPORT"})
    out["label"] = "EMPIRICAL ANALYTICAL CATEGORY - NOT A PLANT FAILURE MODE"
    write_csv(out, "abnormal_episode_types.csv", lg)
    lg.info("types (OOS): %s", sup.type_n_oos.to_dict())


if __name__ == "__main__":
    main()
