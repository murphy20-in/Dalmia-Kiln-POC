"""Step - AFR vs the Phase 4 leading-indicator set (usable_downstream rows only, used exactly as permitted).

Reads  phase-04 outputs/leading_indicator_set.csv, cache/p4_indicator.parquet (Kiln-I!I|ROC_1H, Phase 4 official output),
       cache/* (grid, buckets, episodes)
Writes outputs/afr_indicator_relationships.csv

The only usable_downstream row is Kiln-I!I|ROC_1H (1-h rate of change of PC coal firing, confidence LOW, August holdout
not significant). Its permitted use is 'empirical context feature ... discussion / review only'. Phase 5 therefore does
NOT treat it as established evidence; it asks only whether AFR behaviour co-moves with it:
  1. correlation engine (LAGGED_LEVEL / FUTURE_CHANGE / MOMENTUM) with the indicator as the dependent series; fuel
     controls are dropped because the indicator is itself a fuel control-input trend (co-manipulation);
  2. indicator activation (at or above its Phase 4 POC analytical threshold) during falling-AFR vs steady-AFR hours;
  3. the indicator's own Phase 4 association with the future KPI change (60 min, controls K, momentum, Kpend) with and
     without AFR terms added to the controls - how much of it co-moves with AFR.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from af_context import L, band_contrast, d1h, episode_response, load_context, relate_family, rows_for, seed_of, tag_meta
from af_core import CACHE, P4_INDICATOR, P4_OUT, REL_COLUMNS, ic, log, write_csv

lg = log("analyze_afr_leading_indicators")
TAG = "P4:" + P4_INDICATOR


def usable_set() -> pd.DataFrame:
    s = pd.read_csv(P4_OUT / "leading_indicator_set.csv")
    u = s[s.usable_downstream.astype(str).str.lower().eq("true")]
    if list(u.indicator_id) != [P4_INDICATOR]:
        raise SystemExit(f"unexpected usable_downstream set {list(u.indicator_id)} - review the Phase 4 contract")
    return u


def boot_rate_diff(active, a_mask, b_mask, blocks, n_boot, seed) -> tuple[float, float]:
    """95 % CI of mean(active | a) - mean(active | b) resampling calendar blocks (weights = block draw counts)."""
    u = np.unique(blocks[a_mask | b_mask])
    rng = np.random.default_rng(seed)
    pos = np.searchsorted(u, blocks)
    inside = (pos < u.size) & (u[np.minimum(pos, u.size - 1)] == blocks)
    sims = []
    for _ in range(n_boot):
        cnt = np.bincount(rng.integers(0, u.size, u.size), minlength=u.size)
        w = np.where(inside, cnt[np.minimum(pos, u.size - 1)], 0)
        wa, wb = w * a_mask, w * b_mask
        if wa.sum() and wb.sum():
            sims.append(np.nansum(active * wa) / wa.sum() - np.nansum(active * wb) / wb.sum())
    return float(np.quantile(sims, 0.025)), float(np.quantile(sims, 0.975))


def activation_rows(ctx, ind, u, meta) -> pd.DataFrame:
    cfg = ctx.cfg
    thr = float(u.alarm_threshold)
    active = np.where(np.isfinite(ind), (ind >= thr).astype(float), np.nan)
    da = d1h(ctx.afr)
    rows = []
    for w in ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG"):
        r = rows_for(ctx, w) & np.isfinite(active) & np.isfinite(da)
        fall, steady = r & (da <= -cfg.ramp_tph), r & (np.abs(da) < 1.0)
        ok = fall.sum() >= 30 and steady.sum() >= 30
        eff = float(active[fall].mean() - active[steady].mean()) if ok else np.nan
        lo, hi = boot_rate_diff(active, fall, steady, ctx.blocks, cfg.n_boot, seed_of(cfg.seed, "act", w)) if ok \
            else (np.nan, np.nan)
        rows.append({"afr_signal": "Kiln-I!K", "target_signal": TAG, "target_original_name": meta.loc[TAG, "original_name"],
                     "target_unit": "activation rate", "target_family": "INDICATOR",
                     "analysis_type": "INDICATOR_ACTIVATION_FALLING_VS_STEADY_AFR", "lag_minutes": 0, "window": w,
                     "row_role": "DESCRIPTIVE", "operating_state": "RUNNING", "load_condition": "NOT_FEED_ADJUSTED",
                     "sample_count": int(fall.sum()), "effective_sample_size": int(np.unique(ctx.blocks[fall]).size),
                     "effect_size": eff,
                     "effect_metric": (f"activation rate (indicator >= {thr:g} {u.alarm_threshold_unit}) when AFR 1-h "
                                       f"change <= -{cfg.ramp_tph:g} TPH minus when |change| < 1 TPH"),
                     "confidence_interval_low": lo, "confidence_interval_high": hi, "p_value": np.nan,
                     "adjusted_p_value": np.nan,
                     "direction": ("POSITIVE" if eff > 0 else "NEGATIVE") if np.isfinite(eff) else "",
                     "stability": "", "holdout_result": "", "evidence": "OBSERVED" if ok else "INSUFFICIENT DATA",
                     "confidence": "NOT_APPLICABLE", "flags": "CO_MANIPULATION_OF_CONTROL_INPUTS|POC_ANALYTICAL_THRESHOLD",
                     "interpretation": (f"OBSERVED: the Phase 4 indicator was active {eff:+.1%} more often (rate difference) "
                                        "in hours of falling AFR than in steady-AFR hours; both are fuel control inputs "
                                        "(co-manipulation). Descriptive only.") if ok else "INSUFFICIENT DATA"})
    return pd.DataFrame(rows)


def attenuation_rows(ctx, ind, u) -> pd.DataFrame:
    cfg = ctx.cfg
    m = json.loads((CACHE / "kpi_scale.json").read_text())
    K, D = ctx.g.K.to_numpy(float), ctx.g.D.to_numpy(float)
    h = int(u.lag_minutes) // 10
    y = ic.future_target(K, ctx.running, h, cfg.target_smooth)
    da, lv = d1h(ctx.afr), L(ctx.afr)
    Z0 = ic.controls(K, D, h, m["m"], m["q_anchor"])
    Z1 = np.column_stack([Z0, da, lv])
    rows = []
    for w in ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG"):
        rr = rows_for(ctx, w, h) & np.isfinite(da) & np.isfinite(lv)          # same rows for both fits
        res = {k: ic.assoc(ind, y, Z, rr, ctx.blocks, seed_of(cfg.seed, "p4lead", k, w), cfg.neff_maxlag, cfg.min_n,
                           cfg.n_boot) for k, Z in (("WITHOUT_AFR", Z0), ("WITH_AFR_CONTROLS", Z1))}
        base = res["WITHOUT_AFR"]["rho_p"]
        ratio = res["WITH_AFR_CONTROLS"]["rho_p"] / base if np.isfinite(base) and base != 0 else np.nan
        for k, r in res.items():
            rows.append({"afr_signal": "Kiln-I!K", "target_signal": "KPI:K future change (60 min)",
                         "target_original_name": "Phase 4 indicator -> future KPI change", "target_unit": "",
                         "target_family": "INDICATOR", "analysis_type": f"INDICATOR_KPI_LEAD_{k}",
                         "lag_minutes": int(u.lag_minutes), "window": w, "row_role": "ATTENUATION_CHECK",
                         "operating_state": "RUNNING",
                         "load_condition": "PHASE4_CONTROLS" if k == "WITHOUT_AFR" else "PHASE4_CONTROLS+AFR_LEVEL+AFR_CHANGE",
                         "sample_count": r["n"], "effective_sample_size": r["n_eff"], "effect_size": r["rho_p"],
                         "effect_metric": "partial Spearman rho (Phase 4 indicator vs future KPI change)",
                         "confidence_interval_low": r["ci_lo"], "confidence_interval_high": r["ci_hi"],
                         "p_value": r["p_eff"], "adjusted_p_value": np.nan,
                         "direction": ("POSITIVE" if r["rho_p"] > 0 else "NEGATIVE") if np.isfinite(r["rho_p"]) else "",
                         "stability": "", "holdout_result": "", "evidence": "OBSERVED", "confidence": "NOT_APPLICABLE",
                         "flags": "PHASE4_INDICATOR_LOW_CONFIDENCE", "attenuation_ratio_with_afr": ratio,
                         "interpretation": (f"OBSERVED: the Phase 4 indicator's partial rho with the 60-min future KPI "
                                            f"change is {base:+.3f} without and {res['WITH_AFR_CONTROLS']['rho_p']:+.3f} with "
                                            f"AFR level / change added to the controls (ratio {ratio:.2f}).")
                         if k == "WITHOUT_AFR" else ""})
    return pd.DataFrame(rows)


def main():
    u = usable_set().iloc[0]
    ctx = load_context()
    ind = pd.read_parquet(CACHE / "p4_indicator.parquet")[P4_INDICATOR].to_numpy(float)
    ctx.b[TAG] = ind
    meta = pd.concat([tag_meta(), pd.DataFrame({"original_name": [f"{u.display_name} (Phase 4 feature)"],
                                                "unit": [u.alarm_threshold_unit]}, index=[TAG])])
    bands = json.loads((CACHE / "bands.json").read_text())
    df = pd.concat([relate_family(ctx, "INDICATOR", [TAG], meta, lg), band_contrast(ctx, "INDICATOR", [TAG], meta, bands),
                    episode_response(ctx, "INDICATOR", [TAG], meta), activation_rows(ctx, ind, u, meta),
                    attenuation_rows(ctx, ind, u)], ignore_index=True)
    df["permitted_use"] = u.permitted_use
    cols = REL_COLUMNS + [c for c in df.columns if c not in REL_COLUMNS]
    write_csv(df[cols], "afr_indicator_relationships.csv", lg)


if __name__ == "__main__":
    main()
