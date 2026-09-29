"""Step 4 - Multivariate deviation: the smallest defensible set of two interpretable methods, compared.

  M1 (primary)   family agreement count - how many of the 5 process families have an episode median S_d above their own
                 frozen training P90 (the Phase 3 n_dims_elevated rule). Directly interpretable.
  M2 (secondary) the Phase 3 robust Mahalanobis KPI (MinCovDet on signed, capped tag z, fitted on Apr-May, same 6-h
                 persistence and 0-100 transform; 50 = its training P95) - NOT re-fitted here. Out of sample only.

Compared on method agreement (bucket level and episode level), episode overlap (M2-led candidate episodes vs the primary
KPI-led episodes) and ranking stability (Spearman of episode rankings). Writes cache/multivariate_comparison.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from abn_core import CACHE, PRIMARY, bucket_set, jaccard, load_inputs, load_stage, log, overlaps, run_pipeline, variant

lg = log("detect_multivariate_anomalies")


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    oos = ep[ep.reference_state.eq("OUT_OF_SAMPLE")]
    rows = []

    def add(metric, value, note=""):
        rows.append({"metric": metric, "value": value, "note": note})
    run_oos = g.state.eq("RUNNING") & ~g.in_sample & g.K.notna() & g.MAHA.notna()
    a = (g.K[run_oos] >= ref["thr"]).to_numpy()
    b = (g.MAHA[run_oos] >= PRIMARY.maha_thr).to_numpy()
    add("bucket_n (OOS RUNNING, both scores present)", int(run_oos.sum()))
    add("bucket_share_K_elevated", float(a.mean()), "K >= training P90 cut")
    add("bucket_share_MAHA_elevated", float(b.mean()), "Mahalanobis KPI >= 50 (its training P95)")
    add("bucket_agreement", float((a == b).mean()))
    add("bucket_phi", float(np.corrcoef(a, b)[0, 1]) if a.std() and b.std() else np.nan, "phi coefficient")
    add("bucket_spearman_K_MAHA", float(spearmanr(g.K[run_oos], g.MAHA[run_oos]).statistic))
    add("episode_n_oos", len(oos))
    add("episode_share_family_ge2", float((oos.family_count >= 2).mean()))
    add("episode_share_maha_supported", float(oos.multivariate_supported.mean()),
        f"share of episode buckets with MAHA >= {PRIMARY.maha_thr:.0f} is >= {PRIMARY.maha_share}")
    add("episode_agreement_family_ge2_vs_maha", float(((oos.family_count >= 2) == oos.multivariate_supported).mean()))
    rho = spearmanr(oos.family_count, oos.maha_median, nan_policy="omit").statistic if len(oos) > 2 else np.nan
    add("episode_rank_spearman_family_count_vs_maha_median", float(rho), "ranking stability between methods")
    rho2 = spearmanr(oos.peak_kpi, oos.maha_median, nan_policy="omit").statistic if len(oos) > 2 else np.nan
    add("episode_rank_spearman_peak_kpi_vs_maha_median", float(rho2))
    mv = run_pipeline(inp, variant(name="M2_MAHA_LED", kpi_col="MAHA"))
    mv = mv[mv.reference_state.eq("OUT_OF_SAMPLE")] if len(mv) else mv
    add("m2_led_candidate_episodes_oos", len(mv), "candidate episodes when the Mahalanobis KPI >= 50 leads detection")
    add("m2_led_share_overlapping_primary", float(overlaps(mv, oos).mean()) if len(mv) else np.nan)
    add("primary_share_overlapping_m2_led", float(overlaps(oos, mv).mean()) if len(oos) else np.nan)
    add("bucket_jaccard_primary_vs_m2_led", jaccard(bucket_set(oos), bucket_set(mv)) if len(mv) else np.nan)
    pd.DataFrame(rows).to_csv(CACHE / "multivariate_comparison.csv", index=False)
    lg.info("multivariate comparison: %s", {r["metric"]: r["value"] for r in rows})


if __name__ == "__main__":
    main()
