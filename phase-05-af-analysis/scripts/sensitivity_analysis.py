"""Step - Sensitivity groups A-H, the misaligned-AFR negative control, and the final confidence labels.

Reads  outputs/afr_{load,combustion,thermal,efficiency,indicator}_relationships.csv (primary rows), cache/*
Writes outputs/afr_sensitivity_analysis.csv   one row per variant x primary relationship (x window)
       outputs/afr_*_relationships.csv        confidence finalised (PENDING_SENSITIVITY -> LOW / MEDIUM / NOT_APPLICABLE)
                                              + sensitivity_groups_evaluated / sensitivity_groups_agree

Groups (pre-declared). Correlation rows are re-evaluated at the PRIMARY discovery-selected lag (except D) in DISCOVERY and
REPLICATION; transition-episode rows are re-detected / re-matched and compared on the POOLED_APR_JUL effect.
  A AFR thresholds      zero cut 2 / 5 TPH (episodes re-detected); band tertiles (band contrasts); matched ON/OFF
  B operating state     exclude 6 h after a restart; exclude 2 h before a stop (analysis filter only)
  C load                middle discovery feed tercile only; no feed / fuel controls; LOAD_COINCIDENT episodes removed;
                        matching also on coal / PC terciles
  D lag                 fixed 60-min lag; 60-min target smoothing (FUTURE_CHANGE)
  E transition window   response windows (T, T+120] and (T+180, T+360]; ramp threshold 3 / 8 TPH; no other AFR
                        transition in the 6 h before the episode window (strict clean pre-state)
  F Sp.Heat F / G       Kiln-I!F <-> Kiln-I!G at the same lag; KPI:K vs single-definition KPI_F / KPI_G (Jun-Aug)
  G data quality        Phase 3 data_quality == GOOD rows; AFR with the Phase 3 flatline mask; AFR without Phase 2
                        SUSPECT_TAG_FLATLINE minutes
  H month               APR, MAY, JUN, JUL, AUG separately (>= 4 evaluable months, at most one against the sign);
                        KPI alternative reference K_ALT
A variant AGREES when its effect has the primary DISCOVERY sign; a group agrees when all its evaluable variants agree
(month rule above for H). Negative control NC_MISALIGNED_30D (AFR shifted 30 days, non-circular) is reported, not counted.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import af_context as ax
from af_core import (CACHE, FAMILIES, P4_INDICATOR, PRIMARY, confidence_cap, confidence_label, ic, log, read_out,
                     variant, write_csv)
from detect_afr_transitions import episodes_table, pick_controls
from matched_analysis import matched
import p4common

lg = log("sensitivity_analysis")
REL_FILES = ["afr_load_relationships.csv", "afr_combustion_relationships.csv", "afr_thermal_relationships.csv",
             "afr_efficiency_relationships.csv", "afr_indicator_relationships.csv"]
IND = "P4:" + P4_INDICATOR
EP_FAMS = ["LOAD", "FUEL_CO_MANIPULATION", "COMBUSTION", "THERMAL", "EFFICIENCY", "INDICATOR"]


def ctx_for(cfg) -> ax.Context:
    ctx = ax.load_context(cfg)
    ctx.b[IND] = pd.read_parquet(CACHE / "p4_indicator.parquet")[P4_INDICATOR].to_numpy(float)
    return ctx


def fam_tags(fam: str) -> list[str]:
    return [IND] if fam == "INDICATOR" else FAMILIES[fam]


def sign(v: float) -> float:
    return float(np.sign(v)) if np.isfinite(v) and v != 0 else np.nan


def corr_variant(ctx, prim: pd.DataFrame, group: str, name: str, lag_override=None, tag_map=None,
                 windows=("DISCOVERY", "REPLICATION"), rows_extra=None) -> list[dict]:
    out = []
    for r in prim.itertuples():
        if tag_map is not None and r.target_signal not in tag_map:
            continue
        if lag_override is not None and r.analysis_type == "MOMENTUM":
            continue
        tag = (tag_map or {}).get(r.target_signal, r.target_signal)
        lag = int(r.lag_minutes if lag_override is None else lag_override)
        for w in windows:
            if rows_extra is None:
                res = ax.assoc_one(ctx, r.target_family, tag, r.analysis_type, lag, w, boot=False)
            else:
                x, y, Z = ax.design(ctx, r.target_family, tag, r.analysis_type, lag)
                rw = rows_extra[w](lag // 10 if r.analysis_type == "FUTURE_CHANGE" else 0)
                res = ic.assoc(x, y, Z, rw, ctx.blocks, None, ctx.cfg.neff_maxlag, ctx.cfg.min_n)
            out.append({"group": group, "variant": name, "target_family": r.target_family,
                        "target_signal": r.target_signal, "variant_target": tag, "analysis_type": r.analysis_type,
                        "lag_minutes": lag, "window": w, "sample_count": res["n"], "effect_size": res["rho_p"],
                        "primary_discovery_effect": r.effect_size})
    return out


def episode_variant(cfg, group: str, name: str, prim: pd.DataFrame, post_windows=None, drop_lc=False) -> list[dict]:
    ctx = ctx_for(cfg)
    b = pd.read_parquet(CACHE / "buckets.parquet")
    ep, x, feed_l = episodes_table(b, cfg)
    ctrl = pick_controls(ep, x, ctx.running, feed_l, p4common.month_of(b.index, ax.P4CFG), cfg)
    meta = ax.tag_meta()
    res = pd.concat([ax.episode_response(ctx, f, fam_tags(f), meta, ep, ctrl, post_windows, drop_lc) for f in EP_FAMS],
                    ignore_index=True)
    res = res[res.row_role.eq("EPISODE_PRIMARY")]
    short_end = PRIMARY.post_windows[0][1]
    out = []
    for r in prim.itertuples():
        # map primary response windows onto the variant's windows by position (first = short, last = long)
        lag = r.lag_minutes if post_windows is None else post_windows[0 if r.lag_minutes == short_end else -1][1]
        v = res[(res.target_signal == r.target_signal) & (res.analysis_type == r.analysis_type) & (res.lag_minutes == lag)
                & (res.target_family == r.target_family)]
        out.append({"group": group, "variant": name, "target_family": r.target_family, "target_signal": r.target_signal,
                    "variant_target": r.target_signal, "analysis_type": r.analysis_type, "lag_minutes": int(r.lag_minutes),
                    "variant_lag_minutes": int(lag), "window": "POOLED_APR_JUL",
                    "sample_count": int(v.sample_count.iloc[0]) if len(v) else 0,
                    "effect_size": float(v.effect_size.iloc[0]) if len(v) else np.nan,
                    "primary_discovery_effect": r.effect_size})
    lg.info("episodes %s/%s: %d detected, %d eligible", group, name, len(ep), int(ep.status.eq("ELIGIBLE").sum()))
    return out


def main():
    rel = {f: read_out(f) for f in REL_FILES}
    allrel = pd.concat(rel.values(), ignore_index=True)
    prim_c = allrel[allrel.row_role.eq("SELECTED_LAG") & allrel.window.eq("DISCOVERY")]
    prim_e = allrel[allrel.row_role.eq("EPISODE_PRIMARY") & allrel.analysis_type.str.startswith("EPISODE_AFR")]
    rows = []
    # ---------------------------------------------------------------- correlation groups
    for group, name, cfg in (("B", "exclude_6h_post_restart", variant(exclude_post_restart_h=6.0)),
                             ("B", "exclude_2h_pre_stop", variant(exclude_pre_stop_h=2.0)),
                             ("C", "middle_feed_tercile", variant(feed_tercile=1)),
                             ("C", "no_feed_fuel_controls", variant(use_feed_controls=False)),
                             ("D", "target_smoothing_60min", variant(target_smooth=6)),
                             ("G", "dq_good_only", variant(dq_good_only=True)),
                             ("G", "afr_p3_flatline_masked", variant(afr_series="AFR_P3MASKED")),
                             ("G", "afr_without_p2_flatline_minutes", variant(afr_series="AFR_NOFLAT"))):
        p = prim_c[prim_c.analysis_type.eq("FUTURE_CHANGE")] if name == "target_smoothing_60min" else prim_c
        rows += corr_variant(ctx_for(cfg), p, group, name)
        lg.info("correlation variant %s/%s done", group, name)
    ctx = ctx_for(PRIMARY)
    rows += corr_variant(ctx, prim_c, "D", "fixed_lag_60", lag_override=60)
    rows += corr_variant(ctx, prim_c, "F", "sp_heat_other_definition", tag_map={"Kiln-I!F": "Kiln-I!G", "Kiln-I!G": "Kiln-I!F"})
    kpi = prim_c[prim_c.target_signal.eq("KPI:K")]
    for nm, t in (("kpi_sp_heat_f_only", "KPI:K_F"), ("kpi_sp_heat_g_only", "KPI:K_G")):
        rows += corr_variant(ctx, kpi, "F", nm, tag_map={"KPI:K": t}, windows=("REPLICATION", "HOLDOUT_AUG"))
    rows += corr_variant(ctx, kpi, "H", "kpi_alt_reference_w_jun_jul15", tag_map={"KPI:K": "KPI:K_ALT"},
                         windows=("REPLICATION",))

    def month_rows(wn: str, mth: int):
        return lambda h: ax.rows_for(ctx, wn, h) & (ctx.index.month == mth)
    for mth, wn in ((4, "DISCOVERY"), (5, "DISCOVERY"), (6, "JUN"), (7, "JUL"), (8, "HOLDOUT_AUG")):
        key = f"M{mth:02d}"
        rows += corr_variant(ctx, prim_c, "H", f"month_{key}", windows=(key,), rows_extra={key: month_rows(wn, mth)})
    lg.info("D / F / H done")
    # ---------------------------------------------------------------- negative control: misaligned AFR (30 days)
    mis = ic.lagged(ctx.afr, 30 * 144)
    for r in prim_c.itertuples():
        for w in ("REPLICATION", "HOLDOUT_AUG"):
            res = ax.assoc_one(ctx, r.target_family, r.target_signal, r.analysis_type, int(r.lag_minutes), w, False, mis)
            pw = allrel[(allrel.target_signal == r.target_signal) & (allrel.analysis_type == r.analysis_type)
                        & (allrel.target_family == r.target_family) & allrel.row_role.eq("SELECTED_LAG")
                        & allrel.window.eq(w)].effect_size
            rows.append({"group": "NC_MISALIGNED_30D", "variant": "afr_shifted_30_days", "target_family": r.target_family,
                         "target_signal": r.target_signal, "variant_target": r.target_signal,
                         "analysis_type": r.analysis_type, "lag_minutes": int(r.lag_minutes), "window": w,
                         "sample_count": res["n"], "effect_size": res["rho_p"], "primary_discovery_effect": r.effect_size,
                         "primary_window_effect": float(pw.iloc[0]) if len(pw) else np.nan})
    # ---------------------------------------------------------------- episode groups
    fast = dict(n_boot=200, n_perm=0)
    for group, name, cfg, kw in (("A", "zero_cut_2tph", variant(zero_cut=2.0, **fast), {}),
                                 ("A", "zero_cut_5tph", variant(zero_cut=5.0, **fast), {}),
                                 ("C", "drop_load_coincident", variant(**fast), {"drop_lc": True}),
                                 ("E", "response_windows_0_120_and_180_360", variant(**fast),
                                  {"post_windows": ((0, 120), (180, 360))}),
                                 ("E", "no_other_transition_6h_before_window", variant(prior_transition_h=6.0, **fast), {}),
                                 ("E", "ramp_threshold_3tph", variant(ramp_tph=3.0, **fast), {}),
                                 ("E", "ramp_threshold_8tph", variant(ramp_tph=8.0, **fast), {}),
                                 ("G", "afr_p3_flatline_masked", variant(afr_series="AFR_P3MASKED", **fast), {}),
                                 ("G", "afr_without_p2_flatline_minutes", variant(afr_series="AFR_NOFLAT", **fast), {})):
        rows += episode_variant(cfg, group, name, prim_e, **kw)
    # ---------------------------------------------------------------- band tertiles (A) and matching (A / C)
    bands = json.loads((CACHE / "bands.json").read_text())
    disc = ctx.afr[ax.rows_for(ctx, "DISCOVERY") & (ctx.afr > bands["zero_cut"])]
    tert = {**bands, "q_lo": float(np.quantile(disc, 1 / 3)), "q_hi": float(np.quantile(disc, 2 / 3))}
    meta = ax.tag_meta()
    prim_b = allrel[allrel.analysis_type.str.startswith("BAND_CONTRAST") & allrel.window.eq("DISCOVERY")]
    bt = pd.concat([ax.band_contrast(ctx, f, fam_tags(f), meta, tert, n_boot=50) for f in EP_FAMS if f != "INDICATOR"],
                   ignore_index=True)
    for r in prim_b.itertuples():
        v = bt[(bt.target_signal == r.target_signal) & (bt.analysis_type == r.analysis_type) & bt.window.eq("DISCOVERY")]
        rows.append({"group": "A", "variant": "band_tertiles", "target_family": r.target_family,
                     "target_signal": r.target_signal, "variant_target": r.target_signal, "analysis_type": r.analysis_type,
                     "lag_minutes": 0, "window": "DISCOVERY", "sample_count": int(v.sample_count.iloc[0]) if len(v) else 0,
                     "effect_size": float(v.effect_size.iloc[0]) if len(v) else np.nan,
                     "primary_discovery_effect": r.effect_size})
    for group, name, kw in (("A", "matched_zero_cut_2tph", {"zero_cut": 2.0}),
                            ("A", "matched_zero_cut_5tph", {"zero_cut": 5.0}),
                            ("C", "matched_also_on_coal_pc", {"match_fuel": True})):
        for r in matched(**kw).drop_duplicates(["comparison", "window"]).itertuples():
            rows.append({"group": group, "variant": name, "target_family": "ALL", "target_signal": r.comparison,
                         "variant_target": r.comparison, "analysis_type": "MATCHED_" + r.comparison, "lag_minutes": 0,
                         "window": r.window, "sample_count": r.matched_pairs, "effect_size": np.nan,
                         "primary_discovery_effect": np.nan, "matching_status": r.matching_status,
                         "not_supported_reason": r.not_supported_reason})
    sens = pd.DataFrame(rows)
    sens["same_sign_as_primary"] = [(sign(a) == sign(b)) if np.isfinite(sign(a)) and np.isfinite(sign(b)) else np.nan
                                    for a, b in zip(sens.effect_size, sens.primary_discovery_effect)]
    sens["effect_ratio_to_primary"] = sens.effect_size / sens.primary_discovery_effect.replace(0, np.nan)
    sens["counted_in_agreement"] = (~sens.group.eq("NC_MISALIGNED_30D")
                                    & ~sens.analysis_type.str.startswith(("BAND_CONTRAST", "MATCHED_")))
    write_csv(sens, "afr_sensitivity_analysis.csv", lg)
    finalise(rel, sens)


def group_agreement(sens: pd.DataFrame, fam: str, tag: str, atype: str) -> tuple[int, int]:
    s = sens[sens.counted_in_agreement & (sens.target_signal == tag) & (sens.analysis_type == atype)
             & (sens.target_family == fam)]
    n_eval = n_agree = 0
    for g, gs in s.groupby("group", sort=True):
        ev = gs[gs.same_sign_as_primary.notna()]
        if ev.empty:
            continue
        if g == "H":
            mm = ev[ev.variant.str.startswith("month_")]
            other = ev[~ev.variant.str.startswith("month_")]
            if len(mm) < 4:
                continue
            ok = int((~mm.same_sign_as_primary.astype(bool)).sum()) <= 1 and bool(other.same_sign_as_primary.astype(bool).all())
        else:
            ok = bool(ev.same_sign_as_primary.astype(bool).all())
        n_eval += 1
        n_agree += int(ok)
    return n_eval, n_agree


def finalise(rel: dict, sens: pd.DataFrame) -> None:
    key = ["target_family", "target_signal", "analysis_type", "lag_minutes"]
    for f, df in rel.items():
        df["sensitivity_groups_evaluated"] = np.nan
        df["sensitivity_groups_agree"] = np.nan
        df["confidence_cap_reason"] = ""
        # primary rows (idempotent: recomputed on every run, whatever their current confidence value)
        pend = (df.row_role.eq("SELECTED_LAG") & df.window.eq("DISCOVERY")) | df.row_role.eq("EPISODE_PRIMARY")
        for i in df.index[pend]:
            r = df.loc[i]
            n_eval, n_agree = group_agreement(sens, r.target_family, r.target_signal, r.analysis_type)
            df.loc[i, ["sensitivity_groups_evaluated", "sensitivity_groups_agree"]] = [n_eval, n_agree]
            cap = confidence_cap(r["flags"]) if r.evidence in ("ASSOCIATED", "WEAK ASSOCIATION") else ""
            df.loc[i, "confidence"] = confidence_label(r.evidence, n_agree, n_eval, capped=bool(cap))
            df.loc[i, "confidence_cap_reason"] = cap
        fin = df.loc[pend, key + ["confidence", "sensitivity_groups_evaluated", "sensitivity_groups_agree",
                                  "confidence_cap_reason"]]
        other = df.row_role.isin(["SELECTED_LAG", "EPISODE_WINDOW"]) & ~pend
        merged = df.loc[other, key].merge(fin, on=key, how="left")
        df.loc[other, "confidence"] = merged.confidence.fillna("").to_numpy()
        df.loc[other, ["sensitivity_groups_evaluated", "sensitivity_groups_agree"]] = \
            merged[["sensitivity_groups_evaluated", "sensitivity_groups_agree"]].to_numpy()
        df.loc[other, "confidence_cap_reason"] = merged.confidence_cap_reason.fillna("").to_numpy()
        write_csv(df, f, lg)


if __name__ == "__main__":
    main()
