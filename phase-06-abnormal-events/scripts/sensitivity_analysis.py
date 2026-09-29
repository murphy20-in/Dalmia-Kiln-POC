"""Step 12 - Sensitivity analysis A-I, temporal robustness by month, and the per-episode robustness score.

Every variant = dataclasses.replace(PRIMARY, ...) re-run through abn_core.run_pipeline on the same frozen inputs.
ROBUSTNESS SET (declared in the plan, before results): the "reasonable alternative" variants - A: cut at the lower / upper
bootstrap CI of the P90 cut and the drift-check reference; B: 30 / 120 min minimum duration; C: 0 / 30 / 120 min merge
gap; E: both state treatments; F: load context ignored / out-of-range buckets excluded; H: strict / no DQ masking; I: Sp.Heat
F-only / G-only KPI. Deliberately STRICTER or DIFFERENT-METHOD variants (A: cut 50 / P99; B: 360 min; D: >= 2 / 3 families;
F: load-independent only; G: Mahalanobis-led or both methods) are reported but not in the robustness set.
robustness_score (per primary final period) = share of robustness-set variants with an overlapping final period;
robust = robustness_score >= 0.7; reference_robustness_score = the same share over the threshold / reference subset
(A_lo, A_hi, A_alt, I_F, I_G) only, reported separately. A variant is STABLE when it retains >= 70 % of the primary final periods and its final
bucket Jaccard with the primary is >= 0.5. Writes outputs/abnormal_episode_sensitivity.csv, cache/stage_robustness.parquet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from abn_core import (CACHE, CALIBRATION_LABEL, FINAL_LABEL, MONTHS, P3_OUT, PRIMARY, bucket_set, jaccard, load_inputs, load_stage, log, overlaps,
                      run_pipeline, variant, write_csv)

lg = log("sensitivity_analysis")
ROBUST_SHARE, STABLE_RETAIN, STABLE_JACCARD = 0.7, 0.7, 0.5
# threshold / reference uncertainty subset, reported separately so that many trivially stable variants cannot hide it
REFERENCE_VARIANTS = ("A_lo", "A_hi", "A_alt", "I_F", "I_G")


def variants(ci_lo: float, ci_hi: float, hi: float) -> list[tuple[str, str, bool, object]]:
    return [
        ("A_KPI_THRESHOLD", f"cut = lower bootstrap CI of P90 ({ci_lo:.1f})", True, variant(name="A_lo", thr=ci_lo)),
        ("A_KPI_THRESHOLD", f"cut = upper bootstrap CI of P90 ({ci_hi:.1f})", True, variant(name="A_hi", thr=ci_hi)),
        ("A_KPI_THRESHOLD", "cut = 50 (training P95 anchor)", False, variant(name="A_50", thr=50.0)),
        ("A_KPI_THRESHOLD", f"cut = training P99 ({hi:.1f})", False, variant(name="A_p99", thr=hi)),
        ("A_KPI_THRESHOLD", "drift check: Phase 3 alternative Jun-Jul15 reference KPI at the same cut", True,
         variant(name="A_alt", kpi_col="K_ALT")),
        ("B_MIN_DURATION", "minimum duration 30 min", True, variant(name="B_30", min_dur_min=30)),
        ("B_MIN_DURATION", "minimum duration 120 min", True, variant(name="B_120", min_dur_min=120)),
        ("B_MIN_DURATION", "minimum duration 360 min", False, variant(name="B_360", min_dur_min=360)),
        ("C_MERGE_GAP", "merge gap 0 min", True, variant(name="C_0", merge_gap_min=0)),
        ("C_MERGE_GAP", "merge gap 30 min", True, variant(name="C_30", merge_gap_min=30)),
        ("C_MERGE_GAP", "merge gap 120 min", True, variant(name="C_120", merge_gap_min=120)),
        ("D_FAMILY_AGREEMENT", ">= 2 deviating families (multi-family only)", False, variant(name="D_2", min_families=2)),
        ("D_FAMILY_AGREEMENT", ">= 3 deviating families", False, variant(name="D_3", min_families=3)),
        ("E_OPERATING_STATE", "candidate buckets within restart ramp + 6 h removed", True,
         variant(name="E_excl", state_mode="exclude_post_restart")),
        ("E_OPERATING_STATE", "no startup / restart / shutdown classification (broader valid state)", True,
         variant(name="E_none", state_mode="no_state_context")),
        ("F_LOAD", "load context ignored (no NORMAL_LOAD_CHANGE)", True, variant(name="F_ignore", load_mode="ignore")),
        ("F_LOAD", "buckets outside the training feed range removed", True, variant(name="F_oor", load_mode="exclude_oor")),
        ("F_LOAD", "final only when LOAD_INDEPENDENT", False, variant(name="F_indep", load_mode="independent_only")),
        ("G_MULTIVARIATE", "final requires Mahalanobis support instead of family agreement", False,
         variant(name="G_maha", mv_mode="maha")),
        ("G_MULTIVARIATE", "final requires both family agreement and Mahalanobis support", False,
         variant(name="G_both", mv_mode="both")),
        ("G_MULTIVARIATE", "Mahalanobis KPI >= 50 leads detection", False, variant(name="G_led", kpi_col="MAHA")),
        ("H_DQ_MASK", "strict: candidate buckets must have data_quality GOOD", True,
         variant(name="H_strict", dq_mode="strict")),
        ("H_DQ_MASK", "none: DATA_QUALITY_ARTIFACT classification off", True, variant(name="H_none", dq_mode="none")),
        ("I_SP_HEAT", "Sp.Heat F-only KPI at the same cut (own anchors: the cut is nominal)", True,
         variant(name="I_F", kpi_col="K_F")),
        ("I_SP_HEAT", "Sp.Heat G-only KPI at the same cut (own anchors: the cut is nominal)", True,
         variant(name="I_G", kpi_col="K_G"))]


def final_of(ep: pd.DataFrame) -> pd.DataFrame:
    return ep[ep.in_final_set] if len(ep) else ep


def temporal_rows(g: pd.DataFrame, ep: pd.DataFrame, ref: dict) -> list[dict]:
    """Chronological months (Apr-May = in-sample reference, reported for calibration only)."""
    run = g.state.eq("RUNNING")
    mon = pd.Series(g.index.month, index=g.index).map(MONTHS)
    rows = []
    for m in ("APR_MAY", "JUN", "JUL", "AUG"):
        e = ep[ep.month == m]
        f = e[e.classification.isin([FINAL_LABEL, CALIBRATION_LABEL])]   # Apr-May: calibration-only label
        hours = float(run[mon == m].sum() / 6)
        rows.append({"dimension": "TEMPORAL", "variant": m,
                     "description": ("in-sample reference window (KPI calibrated here: ~10 % elevated by construction)"
                                     if m == "APR_MAY" else "out of sample"),
                     "in_robustness_set": False, "running_hours": hours,
                     "candidate_bucket_share": float((g.K[(mon == m) & run] >= ref["thr"]).mean()),
                     "n_candidates": len(e), "n_final": len(f),
                     "final_per_100_running_h": 100 * len(f) / hours if hours else np.nan,
                     "median_severity_score": float(f.severity_score.median()) if len(f) else np.nan,
                     "n_severity_high": int((f.severity_class == "HIGH").sum()),
                     "share_multi_family": float((f.family_count >= 2).mean()) if len(f) else np.nan,
                     "dominant_families": ";".join(f"{k}:{v}" for k, v in
                                                   f.dominant_family.value_counts().sort_index().items()),
                     "share_load_associated": float((f.load_context == "LOAD_ASSOCIATED").mean()) if len(f) else np.nan,
                     "share_afr_context": float((f.afr_context != "NO_AFR_TRANSITION").mean()) if len(f) else np.nan,
                     "result": "IN_SAMPLE_CALIBRATION" if m == "APR_MAY" else "REPORTED"})
    return rows


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    pf = final_of(ep)
    b = pd.read_csv(P3_OUT / "kpi_reference_bands.csv")
    lo_row = b[b.quantity.str.startswith("band_lo")].iloc[0]
    rows, hits = [], {}
    pb = bucket_set(pf)
    for dim, desc, in_set, cfg in [("PRIMARY", "primary configuration", False, PRIMARY)] + \
            variants(float(lo_row.kpi_ci95_low), float(lo_row.kpi_ci95_high), ref["hi"]):
        v = run_pipeline(inp, cfg)
        vo = v[v.reference_state.eq("OUT_OF_SAMPLE")] if len(v) else v
        vf = final_of(v)
        ov = overlaps(pf, vf)
        if in_set:
            hits[cfg.name] = ov
        r = {"dimension": dim, "variant": cfg.name, "description": desc, "in_robustness_set": in_set,
             "config_key": cfg.key(), "n_candidates_oos": len(vo), "n_final": len(vf),
             "n_ordinary_context_category": int((vo.primary_context != "NONE").sum()) if len(vo) else 0,
             "n_unconfirmed": int((vo.classification == "UNCONFIRMED_KPI_ELEVATION").sum()) if len(vo) else 0,
             "bucket_jaccard_final_vs_primary": jaccard(pb, bucket_set(vf)),
             "primary_final_retained_share": float(ov.mean()) if len(ov) else np.nan}
        for m in ("JUN", "JUL", "AUG"):
            r[f"n_final_{m.lower()}"] = int((vf.month == m).sum()) if len(vf) else 0
        stable = (r["primary_final_retained_share"] >= STABLE_RETAIN
                  and r["bucket_jaccard_final_vs_primary"] >= STABLE_JACCARD)
        r["result"] = "REFERENCE" if dim == "PRIMARY" else ("STABLE" if stable else "CHANGED")
        rows.append(r)
    out = pd.DataFrame(rows + temporal_rows(g, ep, ref))
    write_csv(out, "abnormal_episode_sensitivity.csv", lg)
    rob = pd.DataFrame({"episode_id": ep.episode_id})
    if len(pf):
        H = pd.DataFrame(hits, index=pf.episode_id)
        refv = [c for c in H.columns if c in REFERENCE_VARIANTS]
        rob = rob.merge(pd.DataFrame({"robustness_score": H.mean(axis=1), "n_robustness_variants": H.shape[1],
                                      "reference_robustness_score": H[refv].mean(axis=1),
                                      "variants_not_retained": [";".join(c for c in H.columns if not H.at[i, c])
                                                                for i in H.index]}),
                        left_on="episode_id", right_index=True, how="left")
    else:
        rob["robustness_score"] = np.nan
    rob["robust"] = rob.robustness_score >= ROBUST_SHARE
    rob.to_parquet(CACHE / "stage_robustness.parquet", index=False)
    lg.info("variants: %s", out[out.dimension != "TEMPORAL"].set_index("variant").result.to_dict())
    lg.info("robust final periods: %d / %d", int(rob.robust.sum()), len(pf))


if __name__ == "__main__":
    main()
