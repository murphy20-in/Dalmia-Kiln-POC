"""Step - AFR vs the Phase 3 efficiency-deterioration KPI.

Reads  cache/* (grid, buckets, episodes), phase-04 outputs/indicator_episodes.csv
Writes outputs/afr_efficiency_relationships.csv

1. Correlation engine on KPI:K (current KPI = LAGGED_LEVEL, future KPI change = FUTURE_CHANGE with the Phase 4 controls
   K(t), momentum, Kpend, KPI momentum = MOMENTUM) and KPI:D (raw deviation score), band contrasts, AFR transition
   episodes. DISCOVERY uses the in-sample KPI reference (flagged); JUN-AUG use the out-of-sample KPI.
2. KPI DETERIORATION EPISODES (Phase 4, synthetic, not plant events): AFR behaviour in (T-6 h, T] before each episode
   anchor T (the start of the KPI rise) versus Phase 4's own matched control times. Only AFR buckets <= T are used, so no
   future KPI information enters an AFR feature. Paired difference episode - mean(controls); block-bootstrap CI;
   sign-flip permutation p (randomised episode / control labels).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from af_context import EP_WINDOWS, L, load_context, load_episodes, paired_stats, run_families, seed_of
from af_core import P4_OUT, PRIMARY, REL_COLUMNS, ic, log, on_state, read_out, write_csv
import p4common

lg = log("analyze_afr_efficiency")
P4_EPISODE_LABEL = p4common.EPISODE_LABEL
FEATURES = {"AFR_LEVEL_6H": "median AFR over (T-6 h, T] (TPH)",
            "AFR_CHANGE_6H": "AFR 1-h level at T minus at T-6 h (TPH)",
            "AFR_ON_SHARE_6H": "share of valid RUNNING buckets with AFR on in (T-6 h, T]",
            "AFR_TRANSITIONS_6H": "number of detected AFR transitions (any type) in (T-6 h, T]"}


def precursor_features(ctx, pos: np.ndarray, trans_pos: np.ndarray) -> dict[str, np.ndarray]:
    a = ctx.afr
    lv = L(a)
    on = on_state(a, PRIMARY.zero_cut)
    out = {k: np.full(pos.size, np.nan) for k in FEATURES}
    for i, t in enumerate(pos):
        seg = slice(max(0, t - 35), t + 1)                # (T-6 h, T]
        if np.isfinite(a[seg]).mean() < 0.5:
            continue                                      # not evaluable (never counted as zero AFR)
        out["AFR_LEVEL_6H"][i] = np.nanmedian(a[seg])
        out["AFR_CHANGE_6H"][i] = lv[t] - lv[t - 36] if t >= 36 else np.nan
        out["AFR_ON_SHARE_6H"][i] = np.nanmean(on[seg])
        out["AFR_TRANSITIONS_6H"][i] = float(((trans_pos > t - 36) & (trans_pos <= t)).sum())
    return out


def signflip_p(dif: np.ndarray, n_perm: int, seed: int) -> float:
    if dif.size < 3:
        return np.nan
    rng = np.random.default_rng(seed)
    obs = np.median(dif)
    null = np.array([np.median(dif * rng.choice([-1.0, 1.0], dif.size)) for _ in range(n_perm)])
    return float((1 + np.sum(np.abs(null) >= abs(obs))) / (1 + n_perm))


def hold_label(pool, ho) -> str:
    if ho[0] < 3 or not np.isfinite(ho[1]) or not np.isfinite(pool[1]):
        return "NOT_EVALUABLE"
    same = np.sign(ho[1]) == np.sign(pool[1])
    sig = np.isfinite(ho[2]) and ho[2] * ho[3] > 0
    return ("CONFIRMED" if sig else "SAME_DIRECTION_NS") if same else ("REVERSED" if sig else "OPPOSITE_DIRECTION_NS")


def kpi_episode_rows(ctx) -> pd.DataFrame:
    cfg = ctx.cfg
    e4 = pd.read_csv(P4_OUT / "indicator_episodes.csv", parse_dates=["T"])
    pos_of = pd.Series(np.arange(len(ctx.index)), index=ctx.index)
    e4["pos"] = pos_of.reindex(e4["T"]).to_numpy()
    e4 = e4.dropna(subset=["pos"]).astype({"pos": int})
    ep, _ = load_episodes()
    for k, v in precursor_features(ctx, e4.pos.to_numpy(), ep.pos.to_numpy()).items():
        e4[k] = v
    rows = []
    for k, desc in FEATURES.items():
        res = {}
        for wn, members in EP_WINDOWS.items():
            dif, blk = [], []
            for _, g in e4[e4.window.isin(members)].groupby("episode_id", sort=True):
                e = g[g.role.eq("EPISODE")]
                c = g[g.role.str.startswith("CONTROL")][k].to_numpy()
                c = c[np.isfinite(c)]
                if len(e) and np.isfinite(e[k].iloc[0]) and c.size:
                    dif.append(e[k].iloc[0] - c.mean())
                    blk.append(ctx.blocks[e.pos.iloc[0]])
            dif, blk = np.asarray(dif, float), np.asarray(blk, int)
            med, lo, hi = paired_stats(dif, blk, cfg.n_boot, seed_of(cfg.seed, "kpiep", k, wn))
            p = signflip_p(dif, cfg.n_perm, seed_of(cfg.seed, "flip", k, wn)) if wn == "POOLED_APR_JUL" else np.nan
            res[wn] = (dif.size, med, lo, hi, p)
        for wn, (n, med, lo, hi, p) in res.items():
            rows.append({"afr_signal": "Kiln-I!K", "target_signal": "KPI_DETERIORATION_EPISODE (Phase 4)",
                         "target_original_name": P4_EPISODE_LABEL, "target_unit": "", "target_family": "EFFICIENCY",
                         "analysis_type": f"KPI_EPISODE_PRECURSOR_{k}", "lag_minutes": 360, "window": wn,
                         "row_role": "EPISODE_PRIMARY" if wn == "POOLED_APR_JUL" else "EPISODE_WINDOW",
                         "operating_state": "Phase 4 episode / control anchors",
                         "load_condition": "PHASE4_CONTROLS_MATCHED_ON_KPI_TRAJECTORY", "sample_count": n,
                         "effective_sample_size": n, "effect_size": med,
                         "effect_metric": f"median paired difference episode - controls: {desc}",
                         "confidence_interval_low": lo, "confidence_interval_high": hi, "p_value": p,
                         "direction": ("POSITIVE" if med > 0 else "NEGATIVE") if np.isfinite(med) and med != 0 else "",
                         "flags": "SYNTHETIC_KPI_EPISODES|DISCOVERY_KPI_IS_IN_SAMPLE_REFERENCE", "res_": res})
    df = pd.DataFrame(rows)
    prim = df.row_role.eq("EPISODE_PRIMARY").to_numpy()
    df["adjusted_p_value"] = np.nan
    df.loc[prim, "adjusted_p_value"] = ic.bh(df.loc[prim, "p_value"].to_numpy())
    lab = []
    for r in df.itertuples():
        d, rp, ho, pool = (r.res_[w] for w in ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG", "POOLED_APR_JUL"))
        s = [np.sign(x[1]) for x in (d, rp) if x[0] >= 5 and np.isfinite(x[1]) and x[1] != 0]
        stab = "INSUFFICIENT" if len(s) < 2 else ("STABLE_SIGN" if s[0] == s[1] else "SIGN_FLIP")
        hold = hold_label(pool, ho)
        ev, txt = "", ""
        if r.row_role == "EPISODE_PRIMARY":
            ci = np.isfinite(pool[2]) and pool[2] * pool[3] > 0
            q = r.adjusted_p_value
            ev = ("INSUFFICIENT DATA" if pool[0] < PRIMARY.min_episodes else
                  "ASSOCIATED" if q < PRIMARY.q_assoc and ci and stab == "STABLE_SIGN" and hold != "REVERSED" else
                  "WEAK ASSOCIATION" if q < PRIMARY.q_weak and ci else "NOT SUPPORTED")
            txt = (f"{ev}: over {pool[0]} Phase 4 KPI deterioration episodes (Apr-Jul, synthetic), "
                   f"{FEATURES[r.analysis_type[22:]]} before the KPI rise differed from matched control times by a median "
                   f"{pool[1]:+.3g} [{pool[2]:+.3g}, {pool[3]:+.3g}] (sign-flip p {r.p_value:.3g}, BH q {q:.3g}); "
                   f"stability {stab}; August {hold}. Episodes are KPI windows, not plant events. AFR-associated at most.")
        lab.append((stab, hold, ev, txt))
    df["stability"], df["holdout_result"], df["evidence"], df["interpretation"] = zip(*lab)
    df["confidence"] = np.where(prim, "PENDING_SENSITIVITY", "")
    return df.drop(columns=["res_"])


def main():
    run_families(["EFFICIENCY"], "afr_efficiency_relationships.csv", lg)
    extra = kpi_episode_rows(load_context())
    df = pd.concat([read_out("afr_efficiency_relationships.csv"), extra], ignore_index=True)
    cols = REL_COLUMNS + [c for c in df.columns if c not in REL_COLUMNS]
    write_csv(df[cols], "afr_efficiency_relationships.csv", lg)


if __name__ == "__main__":
    main()
