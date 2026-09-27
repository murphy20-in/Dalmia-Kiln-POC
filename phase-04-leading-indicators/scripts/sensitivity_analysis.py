"""Step 7 - Sensitivity analysis (groups A-H) for every discovery-supported indicator at its discovery lag and sign.

Reads  outputs/indicator_lag_analysis.csv, cache/features.parquet, cache/kpi_grid.parquet, cache/buckets_*.parquet
Writes outputs/indicator_sensitivity.csv   one row per variant x indicator (+ summary rows added by score_indicators)
       cache/sensitivity_consistency.csv   per indicator: share of robustness variants consistent (criterion c8)

Every variant re-evaluates the SAME pre-declared (lag, sign) chosen on discovery. It is 'consistent' when its rho has the
discovery sign and |rho| >= 0.5 * |primary rho| (MATERIALITY.rho_ratio_min); CI-type variants need the CI to exclude 0.
  A lead time        neighbouring lags (one grid step either side)
  B training window  split-half discovery (Apr only, May only); feature reference refitted on April only;
                     alternative Phase 3 KPI reference (W_JUN_JUL15; K_ALT exists from 2025-07-16, so
                     evaluated 2025-07-16 .. 2025-07-31 inside the replication window)
  C operating state  exclude 6 h after a transition; exclude 2 h before a stop (analysis filter only)
  D load             feed level and feed rate-of-change added as controls; within tentative GMM feed bands
  E Sp.Heat          target = Sp.Heat F-only KPI; Sp.Heat G-only KPI
  F persistence      target smoothed over 60 min instead of 30 min; band-occupancy target (T2)
  G missing data     only buckets with Phase 3 data_quality == GOOD
  H inference        1-day blocks in the bootstrap (primary: 3-day); no controls (raw Spearman)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p4common import CACHE, FEED_TAG, MATERIALITY, PRIMARY, P4Config, log, variant, write_csv
import analysis_context as ac
import build_causal_features as bcf
import indicator_core as ic
import kpi_core

lg = log("sensitivity_analysis")

VARIANTS = {   # name: (group, config, window, kind)
    "SPLIT_APR": ("B training window", PRIMARY, "APR", "disc"),
    "SPLIT_MAY": ("B training window", PRIMARY, "MAY", "disc"),
    "ALT_KPI_REFERENCE_W_JUN_JUL15": ("B training window", variant(name="ALT_REF", target="alt_w_jun_jul15"), "REPL", "rho"),
    "EXCLUDE_6H_AFTER_TRANSITION": ("C operating state", variant(name="POST_RESTART", exclude_post_restart_h=6), "REPL", "rho"),
    "EXCLUDE_2H_BEFORE_STOP": ("C operating state", variant(name="PRE_STOP", exclude_pre_stop_h=2), "REPL", "rho"),
    "SP_HEAT_F_TARGET": ("E Sp.Heat", variant(name="SPF", target="F"), "REPL", "rho"),
    "SP_HEAT_G_TARGET": ("E Sp.Heat", variant(name="SPG", target="G"), "REPL", "rho"),
    "TARGET_SMOOTH_60MIN": ("F persistence", variant(name="SMOOTH60", target_smooth_buckets=6), "REPL", "rho"),
    "T2_BAND_OCCUPANCY_TARGET": ("F persistence", variant(name="T2", target_kind="band_occupancy"), "REPL", "rho"),
    "DQ_GOOD_BUCKETS_ONLY": ("G missing data", variant(name="DQ", dq_filter=True), "REPL", "rho"),
    "BLOCK_1_DAY": ("H inference", variant(name="BLOCK1", block_days=1), "REPL", "ci"),
    "NO_CONTROLS_RAW_SPEARMAN": ("H inference", variant(name="NOCTRL", use_controls=False), "REPL", "rho"),
}
ROBUSTNESS_SET = ["SPLIT_APR", "SPLIT_MAY", "REFERENCE_APRIL_ONLY", "EXCLUDE_6H_AFTER_TRANSITION", "EXCLUDE_2H_BEFORE_STOP",
                  "LOAD_FEED_CONTROLS", "LOAD_BAND_STRATIFIED", "SP_HEAT_F_TARGET", "SP_HEAT_G_TARGET",
                  "TARGET_SMOOTH_60MIN", "DQ_GOOD_BUCKETS_ONLY", "BLOCK_1_DAY"]


def eval_pairs(cfg: P4Config, pairs: pd.DataFrame, window: str, F: pd.DataFrame, extra=None, row_mask=None,
               with_ci: bool = True) -> pd.DataFrame:
    """assoc() of each (indicator_id, lag) pair in `window`. extra(h) -> additional control columns known at t."""
    ctx = ac.build_context(cfg)
    out = []
    for lag, g in pairs.groupby("lag", sort=True):
        h = int(lag) // cfg.bucket_min
        y, Z = ac.target_and_controls(ctx, h)
        if extra is not None:
            Z = np.column_stack([Z, extra(h)]) if Z is not None else extra(h)
        rows = ac.window_rows(ctx, window, h)
        if row_mask is not None:
            rows = rows & row_mask
        blk, _ = ac.blocks(ctx, rows)
        seed = cfg.seed + ac.WINDOW_SEEDS.get(window, 99) if with_ci else None
        for c in sorted(g.indicator_id):
            if c not in F:                      # e.g. no April data for the April-only reference (Kiln-IIIA)
                out.append({"indicator_id": c, "lag_minutes": int(lag), "n": 0, "rho_raw": np.nan, "rho_p": np.nan,
                            "n_eff": np.nan, "p_eff": np.nan, "ci_lo": np.nan, "ci_hi": np.nan})
                continue
            r = ic.assoc(F[c].to_numpy(float), y, Z, rows, blk, seed, cfg.neff_maxlag, n_boot=cfg.n_boot)
            r.update(indicator_id=c, lag_minutes=int(lag))
            out.append(r)
    return pd.DataFrame(out)


def fisher_combine(parts: list[dict]) -> float:
    z, w = [], []
    for p in parts:
        if np.isfinite(p.get("rho_p", np.nan)) and np.isfinite(p.get("n_eff", np.nan)) and p["n_eff"] > 4:
            z.append(np.arctanh(p["rho_p"]))
            w.append(p["n_eff"] - 4)
    return float(np.tanh(np.average(z, weights=w))) if w else np.nan


def main():
    cfg = PRIMARY
    lagdf = ac.load_lag_table()
    choice = ac.discovery_choice(lagdf)
    sup = choice[choice.disc_supported].copy()
    pairs = pd.DataFrame({"indicator_id": sup.index, "lag": sup.lag_minutes.to_numpy()})
    F = ac.load_features()
    oos = lagdf[lagdf.window.eq("REPL")].set_index(["indicator_id", "lag_minutes"])   # replication set (Jun-Jul)
    prim = {c: oos.loc[(c, int(sup.lag_minutes[c]))] for c in sup.index}
    rows = []

    def record(name, group, res, ref_kind="oos"):
        for r in res.itertuples():
            c = r.indicator_id
            s = int(sup.sign[c])
            base = float(sup.rho_p[c]) if ref_kind == "disc" else float(prim[c].rho_p)
            v = r.rho_p
            if not np.isfinite(v):
                ok = np.nan                      # NOT EVALUABLE: excluded from the robustness share
            elif ref_kind == "ci":
                ok = float(np.isfinite(r.ci_lo) and s * r.ci_lo > 0 and s * r.ci_hi > 0)
            else:
                ok = float(np.sign(v) == s and abs(v) >= MATERIALITY["rho_ratio_min"] * abs(base))
            rows.append({"variant": name, "group": group, "indicator_id": c, "lag_minutes": r.lag_minutes, "sign": s,
                         "rho_reference": base, "rho_variant": v, "ci_lo": getattr(r, "ci_lo", np.nan),
                         "ci_hi": getattr(r, "ci_hi", np.nan), "n": r.n, "consistent": ok})

    for name, (group, vcfg, win, kind) in VARIANTS.items():
        res = eval_pairs(vcfg, pairs, win, F)
        if kind == "rho" and name == "NO_CONTROLS_RAW_SPEARMAN":
            res["rho_p"] = res.rho_raw
        record(name, group, res, "disc" if kind == "disc" else ("ci" if kind == "ci" else "oos"))
        lg.info("variant %s done", name)

    # E - does the lead time change with the Sp.Heat definition? best OOS lag under F-only / G-only targets
    lags = list(cfg.lags)
    prim_best = {}
    for c in sup.index:
        g = oos.loc[c]
        v = int(sup.sign[c]) * g.rho_p
        prim_best[c] = int(v.idxmax()) if v.notna().any() else None
    for name, vcfg in (("SP_HEAT_F_BEST_LAG", VARIANTS["SP_HEAT_F_TARGET"][1]), ("SP_HEAT_G_BEST_LAG", VARIANTS["SP_HEAT_G_TARGET"][1])):
        allp = pd.DataFrame([(c, L) for c in sup.index for L in lags], columns=["indicator_id", "lag"])
        res = eval_pairs(vcfg, allp, "REPL", F, with_ci=False)
        for c, g in res.groupby("indicator_id"):
            v = int(sup.sign[c]) * g.set_index("lag_minutes").rho_p
            bl = int(v.idxmax()) if v.notna().any() else None
            pb = prim_best[c]
            ok = float(bl is not None and pb is not None and abs(lags.index(bl) - lags.index(pb)) <= 1)
            rows.append({"variant": name, "group": "E Sp.Heat", "indicator_id": c, "lag_minutes": bl, "sign": int(sup.sign[c]),
                         "rho_reference": pb, "rho_variant": bl, "n": np.nan, "consistent": ok,
                         "note": "rho_reference / rho_variant hold the best observed lag (minutes) under the primary / variant target"})

    # A - lead-time: neighbouring lags from the lag table (no refit)
    for c in sup.index:
        L = int(sup.lag_minutes[c])
        i = lags.index(L)
        for j, tag in ((i - 1, "LAG_MINUS_1_STEP"), (i + 1, "LAG_PLUS_1_STEP")):
            if 0 <= j < len(lags):
                r = oos.loc[(c, lags[j])]
                s = int(sup.sign[c])
                rows.append({"variant": tag, "group": "A lead time", "indicator_id": c, "lag_minutes": lags[j], "sign": s,
                             "rho_reference": float(prim[c].rho_p), "rho_variant": r.rho_p, "ci_lo": r.ci_lo,
                             "ci_hi": r.ci_hi, "n": r.n,
                             "consistent": float(np.sign(r.rho_p) == s and abs(r.rho_p) >= MATERIALITY["rho_ratio_min"] * abs(prim[c].rho_p))
                             if np.isfinite(r.rho_p) else np.nan})

    # B - feature reference refitted on April only (features recomputed for the supported tags)
    grid = pd.read_parquet(CACHE / "kpi_grid.parquet").index
    values, meta = bcf.align(pd.read_parquet(CACHE / "buckets_values.parquet"),
                             pd.read_parquet(CACHE / "buckets_meta.parquet"), grid)
    tags = sorted({ac.split_id(c)[0] for c in sup.index} | {FEED_TAG})
    tm = kpi_core.training_mask(meta, ic.P3CFG) & (meta.index.month == 4)
    ref_apr = ic.fit_feature_reference(values[tags], values[FEED_TAG], tm, cfg)
    F_apr = bcf.feature_frame(values, ref_apr, tags, cfg)
    record("REFERENCE_APRIL_ONLY", "B training window", eval_pairs(cfg, pairs, "REPL", F_apr))

    # D - load: feed level / rate-of-change as extra controls, and within tentative GMM feed bands
    fl = F[f"{FEED_TAG}|LEVEL_1H"].to_numpy(float)
    fr1, fr3 = F[f"{FEED_TAG}|ROC_1H"].to_numpy(float), F[f"{FEED_TAG}|ROC_3H"].to_numpy(float)
    feed_ctrl = np.column_stack([fl, fr1, fr3])
    res = eval_pairs(cfg, pairs[~pairs.indicator_id.str.startswith(FEED_TAG + "|")], "REPL", F, extra=lambda h: feed_ctrl)
    record("LOAD_FEED_CONTROLS", "D load", res)
    train = kpi_core.training_mask(meta, ic.P3CFG).to_numpy()
    bands = kpi_core._gmm_bands(values[FEED_TAG].to_numpy(float)[train & np.isfinite(values[FEED_TAG].to_numpy(float))], ic.P3CFG)
    lab = kpi_core.assign_band(fl, bands)
    parts = {c: [] for c in sup.index}
    for k in range(len(bands["means"])):
        r = eval_pairs(cfg, pairs, "REPL", F, row_mask=(lab == k), with_ci=False)
        for x in r.itertuples():
            parts[x.indicator_id].append({"rho_p": x.rho_p, "n_eff": x.n_eff})
    strat = pd.DataFrame({"indicator_id": list(parts), "rho_p": [fisher_combine(parts[c]) for c in parts],
                          "lag_minutes": [int(sup.lag_minutes[c]) for c in parts], "n": np.nan, "ci_lo": np.nan, "ci_hi": np.nan})
    record("LOAD_BAND_STRATIFIED", "D load", strat)
    for r in rows:
        if r["variant"] == "LOAD_BAND_STRATIFIED":
            r["note"] = f"GMM bands (TENTATIVE, Phase 2) fitted on discovery feed: means {np.round(bands['means'], 1).tolist()}"

    df = pd.DataFrame(rows).sort_values(["group", "variant", "indicator_id"], kind="mergesort").reset_index(drop=True)
    write_csv(df, "indicator_sensitivity.csv", lg)
    rob = df[df.variant.isin(ROBUSTNESS_SET)].groupby("indicator_id").consistent.agg(["mean", "count"])
    load = df[df.variant.eq("LOAD_FEED_CONTROLS")].set_index("indicator_id")
    # tri-state (PY-M1): True = confounded, False = survives feed controls, NaN = not evaluated (fails the gate)
    rob["load_confounded"] = [(bool(load.consistent[c] == 0) if np.isfinite(load.consistent[c]) else np.nan)
                              if c in load.index else np.nan for c in rob.index]
    rob["rho_with_feed_controls"] = [load.rho_variant.get(c, np.nan) for c in rob.index]
    fg = df[df.variant.isin(["SP_HEAT_F_TARGET", "SP_HEAT_G_TARGET"])].groupby("indicator_id").consistent.min().eq(1)
    rob["sp_heat_fg_consistent"] = fg
    st = df[df.variant.isin(["EXCLUDE_6H_AFTER_TRANSITION", "EXCLUDE_2H_BEFORE_STOP"])].groupby("indicator_id").consistent.min().eq(1)
    rob["state_robust"] = st
    rob = rob.rename(columns={"mean": "robust_share", "count": "n_robust_variants_evaluable"})
    rob.round(6).to_csv(CACHE / "sensitivity_consistency.csv")
    lg.info("sensitivity rows %d; consistent share by variant %s", len(df),
            df.groupby("variant").consistent.mean().round(2).to_dict())


if __name__ == "__main__":
    main()
