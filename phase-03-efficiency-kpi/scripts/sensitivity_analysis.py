"""Step 7 - KPI sensitivity analysis.

Reads  cache/minute_*.parquet, cache/buckets_primary_*.parquet, cache/scored_primary.parquet,
       outputs/kpi_candidate_inventory.csv
Writes outputs/kpi_sensitivity_analysis.csv   one row per variant: agreement with the primary KPI
       cache/sensitivity_series.parquet       per-variant KPI time series (for the report figures)

Every variant changes ONE methodological choice (dataclasses.replace of PRIMARY), refits its own reference on its
own training window and is compared with the primary on buckets that both score OUT OF SAMPLE. Training-window
variants are compared on the common scoring period COMMON_SCORING, where every window is out of sample. The tag
set is held at the primary selection so each comparison isolates one factor.
Pre-declared rules (p3common.MATERIALITY / COLLAPSE), fixed before results were inspected:
  MATERIAL DIFFERENCE if Spearman < 0.80, band agreement < 85 % or median |dKPI| > 10 points;
  COLLAPSE if Spearman < 0.30 or the variant scores < 50 % of the primary's buckets;
  INSUFFICIENT_OVERLAP if a comparison metric is undefined (counted as a failure by G6).
near_threshold flags results within a small margin of a materiality threshold (knife-edge verdicts).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p3common import (CACHE, COLLAPSE, COMMON_SCORING, MATERIALITY, PRIMARY, SUPPORT_DIMENSIONS, TRAINING_WINDOWS,
                      load_buckets, load_minutes, log, read_out, variant, write_csv)
from kpi_core import fit_score, minutes_to_buckets

lg = log("sensitivity_analysis")


def variants() -> list[tuple[str, str, object, str]]:
    """(group, variant, config, bucket-set) tuples."""
    v = []
    for wid, (ts, te, role) in TRAINING_WINDOWS.items():
        if wid != "W_APR_MAY":
            v.append(("A training window", wid, variant(name=wid, train_start=ts, train_end=te), "primary"))
    v.append(("B operating state", "PHASE2_RETROSPECTIVE_STATE", variant(name="P2STATE", state_mode="phase2_retrospective"), "p2state"))
    v.append(("C specific heat", "SP_HEAT_F_ONLY", variant(name="F", sp_heat="F"), "primary"))
    v.append(("C specific heat", "SP_HEAT_G_ONLY", variant(name="G", sp_heat="G"), "primary"))
    v.append(("D load conditioning", "GLOBAL_UNADJUSTED", variant(name="GLOBAL", load_mode="global"), "primary"))
    v.append(("D load conditioning", "TENTATIVE_BAND_CONDITIONED (GMM k=3 refit on training)", variant(name="BAND", load_mode="band"), "primary"))
    for w in ["1h", "3h", "12h", "24h"]:
        v.append(("E persistence", f"MEDIAN_{w}", variant(name=f"P{w}", persistence_window=w), "primary"))
    v.append(("E persistence", "MEAN_6h", variant(name="MEAN6", persistence_stat="mean"), "primary"))
    v.append(("E persistence", "NO_PERSISTENCE (raw 10-min deviation)", variant(name="NOPERS", persistence_stat="none"), "primary"))
    v.append(("F component inclusion", "DROP_LOW_CONFIDENCE_TAGS (future-informed: Phase 2 full-period labels)",
              variant(name="NOLOW", drop_low_confidence=True), "primary"))
    v.append(("F component inclusion", "ADD_FUEL_DIMENSION", variant(name="FUEL", dimensions=PRIMARY.dimensions + ("FUEL",)), "primary"))
    for d in SUPPORT_DIMENSIONS:
        v.append(("F component inclusion", f"DROP_{d}", variant(name=f"NO{d}", dimensions=tuple(x for x in PRIMARY.dimensions if x != d)), "primary"))
    v.append(("F component inclusion", "EFFICIENCY_ONLY (w_efficiency = 1)", variant(name="EFFONLY", w_efficiency=1.0), "primary"))
    v.append(("G weighting", "EQUAL_PER_DIMENSION (1/5 each)", variant(name="EQDIM", aggregation="equal_dimension"), "primary"))
    v.append(("G weighting", "EQUAL_PER_TAG", variant(name="EQTAG", aggregation="equal_tag"), "primary"))
    v.append(("G weighting", "INVERSE_REDUNDANCY (data-derived)", variant(name="INVRED", aggregation="inverse_redundancy"), "primary"))
    v.append(("G weighting", "W_EFFICIENCY_0.33", variant(name="W033", w_efficiency=1 / 3), "primary"))
    v.append(("G weighting", "W_EFFICIENCY_0.67", variant(name="W067", w_efficiency=2 / 3), "primary"))
    v.append(("H robustness", "Z_CAP_5", variant(name="CAP5", z_cap=5.0), "primary"))
    v.append(("H robustness", "NO_Z_CAP", variant(name="NOCAP", z_cap=1e9), "primary"))
    v.append(("H robustness", "NO_CAUSAL_FLATLINE_MASK", variant(name="NOFLAT", use_causal_flatline=False), "noflat"))
    v.append(("H robustness", "FEED_FLATLINE_MASKED (no covariate exemption)", variant(name="FEEDFLAT", flatline_exempt=()), "feedflat"))
    v.append(("I calibration", "CALIBRATION_HOLDOUT (fit Apr 1-May 15, anchors on May 16-31)",
              variant(name="HOLDOUT", fit_end="2025-05-15 23:59"), "primary"))
    return v


def episodes(k: pd.Series, level: float) -> tuple[int, float]:
    """Distinct contiguous (10-min grid) episodes with KPI >= level, and their median duration in hours."""
    e = (k >= level).astype(int)
    starts = (e.diff().fillna(e) == 1)
    lab = starts.cumsum().where(e == 1)
    d = lab.dropna().value_counts()
    return int(d.size), float(d.median() * 10 / 60) if d.size else 0.0


def compare(p: pd.DataFrame, q: pd.DataFrame, period: tuple | None, k_lo: float, k_hi: float) -> dict:
    a, b = p.efficiency_deterioration_kpi, q.efficiency_deterioration_kpi
    if period:
        s, e = pd.Timestamp(period[0]), pd.Timestamp(period[1])
        a, b = a[(a.index > s) & (a.index <= e)], b[(b.index > s) & (b.index <= e)]
    both = a.notna() & b.notna()
    x, y = a[both], b[both]
    band = lambda z: np.digitize(z, [k_lo, k_hi])
    n_ep, dur = episodes(b, k_hi)
    r = {"n_primary_scored": int(a.notna().sum()), "n_variant_scored": int(b.notna().sum()), "n_common": int(both.sum()),
         "spearman": float(x.corr(y, method="spearman")) if both.sum() > 10 else np.nan,
         "pearson": float(x.corr(y)) if both.sum() > 10 else np.nan,
         "median_abs_diff": float((x - y).abs().median()) if both.any() else np.nan,
         "band_agreement": float((band(x) == band(y)).mean()) if both.any() else np.nan,
         "primary_median_kpi": float(x.median()), "variant_median_kpi": float(y.median()),
         "primary_share_elevated_or_above": float((x >= k_lo).mean()), "variant_share_elevated_or_above": float((y >= k_lo).mean()),
         "variant_episodes_beyond_reference": n_ep, "variant_median_episode_h": dur}
    r["scored_share_vs_primary"] = r["n_variant_scored"] / max(r["n_primary_scored"], 1)
    for mth in ("2025-06", "2025-07", "2025-08"):
        r[f"variant_median_{mth}"] = float(b[b.index.to_period("M").astype(str) == mth].median())
    r["variant_trend_jun_to_aug"] = r["variant_median_2025-08"] - r["variant_median_2025-06"]
    metrics = [r["spearman"], r["band_agreement"], r["median_abs_diff"]]
    if not all(np.isfinite(metrics)):
        r["verdict"], r["near_threshold"] = "INSUFFICIENT_OVERLAP", False
        return r
    mat = (r["spearman"] < MATERIALITY["spearman_min"] or r["band_agreement"] < MATERIALITY["band_agreement_min"]
           or r["median_abs_diff"] > MATERIALITY["median_abs_diff_max"])
    col = r["spearman"] < COLLAPSE["spearman_min"] or r["scored_share_vs_primary"] < COLLAPSE["scored_share_min"]
    r["verdict"] = "COLLAPSE" if col else ("MATERIAL DIFFERENCE" if mat else "CONSISTENT")
    r["near_threshold"] = bool(abs(r["spearman"] - MATERIALITY["spearman_min"]) < 0.03
                               or abs(r["band_agreement"] - MATERIALITY["band_agreement_min"]) < 0.02
                               or abs(r["median_abs_diff"] - MATERIALITY["median_abs_diff_max"]) < 1.0)
    return r


def main():
    inv = read_out("kpi_candidate_inventory.csv")
    tags = inv[inv.included].tag.tolist()
    low = set(inv[inv.low_confidence_flag].tag)
    buckets = {"primary": load_buckets("primary")}
    values, state = load_minutes()
    buckets["p2state"] = minutes_to_buckets(values, state, variant(state_mode="phase2_retrospective"))
    buckets["noflat"] = minutes_to_buckets(values, state, variant(use_causal_flatline=False))
    buckets["feedflat"] = minutes_to_buckets(values, state, variant(flatline_exempt=()))
    ref_p, sp = fit_score(buckets["primary"], PRIMARY, tags)
    prim = sp["kpi"]
    sc = ref_p["scale"]
    from kpi_core import to_kpi
    k_lo, k_hi = (to_kpi([sc[q]], sc["m"], sc["q_anchor"])[0] for q in ("q_band_lo", "q_band_hi"))
    series = {"PRIMARY": prim.efficiency_deterioration_kpi, "PRIMARY_IN_SAMPLE": prim.kpi_in_sample_reference}
    rows = []
    n_ep, dur = episodes(prim.efficiency_deterioration_kpi, k_hi)
    rows.append({"group": "0 primary", "variant": "PRIMARY", "comparison_period": "all out-of-sample", **compare(prim, prim, None, k_lo, k_hi)})
    for grp, name, cfg, bset in variants():
        t = [x for x in tags if x not in low] if cfg.drop_low_confidence else tags
        if "FUEL" in cfg.dimensions:
            t = t + ["DERIVED:COAL_TOTAL"]
        ref, s = fit_score(buckets[bset], cfg, t)
        q = s["kpi"]
        series[name] = q.efficiency_deterioration_kpi
        period = COMMON_SCORING if grp.startswith("A") else None
        r = {"group": grp, "variant": name, "comparison_period": f"{period[0]} .. {period[1]}" if period else "common out-of-sample",
             "train_window": f"{cfg.train_start} .. {cfg.train_end}", "n_tags": len(ref["included_tags"]),
             "config_key": cfg.key(), **compare(prim, q, period, k_lo, k_hi)}
        if grp.startswith("A"):
            r["primary_spearman_note"] = "compared only where every training window is out of sample"
        rows.append(r)
        lg.info("%-28s %-50s rho=%.3f band=%.3f d=%.1f %s", grp, name, r["spearman"], r["band_agreement"], r["median_abs_diff"], r["verdict"])
    # secondary validation KPI vs primary, and vs the process-deviation (support) part only
    sec = prim.secondary_mahalanobis_kpi.where(prim.efficiency_deterioration_kpi.notna())
    sup = prim[[f"{d.lower()}_component" for d in SUPPORT_DIMENSIONS]].mean(axis=1).where(prim.efficiency_deterioration_kpi.notna())
    both = sec.notna() & prim.efficiency_deterioration_kpi.notna()
    rows.append({"group": "S secondary validation KPI", "variant": "ROBUST_MAHALANOBIS (MinCovDet) vs PRIMARY",
                 "comparison_period": "common out-of-sample", "n_common": int(both.sum()),
                 "spearman": float(sec[both].corr(prim.efficiency_deterioration_kpi[both], method="spearman")),
                 "verdict": "DESCRIPTIVE (not a competing KPI)"})
    rows.append({"group": "S secondary validation KPI", "variant": "ROBUST_MAHALANOBIS vs mean supporting-dimension score",
                 "comparison_period": "common out-of-sample", "n_common": int((both & sup.notna()).sum()),
                 "spearman": float(sec[both].corr(sup[both], method="spearman")),
                 "verdict": "DESCRIPTIVE (Mahalanobis is two-sided and not efficiency-anchored)"})
    series["SECONDARY_MAHALANOBIS"] = prim.secondary_mahalanobis_kpi.where(prim.kpi_reference_state.str.startswith("OUT_OF_SAMPLE"))
    df = pd.DataFrame(rows)
    df["band_cutpoints_kpi"] = f"{k_lo:.2f} / {k_hi:.2f}"
    write_csv(df, "kpi_sensitivity_analysis.csv", lg)
    pd.DataFrame(series).to_parquet(CACHE / "sensitivity_series.parquet")


if __name__ == "__main__":
    main()
