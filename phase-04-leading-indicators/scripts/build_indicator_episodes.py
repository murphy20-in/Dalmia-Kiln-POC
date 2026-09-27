"""Step 5 - KPI deterioration episodes (synthetic, from the Phase 3 KPI) and indicator behaviour before them.

Reads  cache/features.parquet, cache/kpi_grid.parquet, outputs/indicator_lag_analysis.csv
Writes outputs/indicator_episodes.csv            one row per episode / matched control time
       outputs/indicator_episode_analysis.parquet long: episode x relative time (-12 h .. 0) x indicator
       cache/episode_metrics.csv                 per indicator: hit rates, lift, lead before episodes

Each episode is ANCHORED at the start of its rise (lowest KPI bucket in the 6 h before the detected onset), so
'before the episode' means before the deterioration began; controls are matched on the KPI at the anchor and 12 h
earlier, and exclude +-24 h around every raw onset.
Episode types (KPI DETERIORATION EPISODES - NOT PLANT-CONFIRMED EVENTS):
  E_BAND  the shown KPI enters band code >= 1 (training P90 of the persistent score) for >= 1 h after 12 h clear;
  E_RISE  the 6-h KPI rise K(t) - K(t-6 h) reaches the DISCOVERY P95 of 6-h rises (12 h refractory).
E_BAND / E_RISE onsets closer than 12 h are one INDEPENDENT episode (the earlier onset is kept).
Controls: 3 per episode, same window, no onset within +-24 h, matched on the KPI 12 h earlier (seeded).
An indicator 'hits' an episode when a NEW crossing of its directional discovery threshold (>= 30 min, starting inside
[T-12 h, T) after >= 30 min clear) occurs. The median lead is suppressed when hits are not more frequent than before
matched controls (lift <= 0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p4common import (CACHE, EPISODE_LABEL, HOLDOUT, PRIMARY, REPLICATION_MONTHS, P4Config, log, write_csv,
                      write_parquet)
import analysis_context as ac
import indicator_core as ic

lg = log("build_indicator_episodes")
REL_MIN = np.arange(-720, 1, 10)
SUMMARY_OFFSETS = (-720, -360, -180, -120, -60, -30, 0)


def rise_threshold(ctx: ac.Context, cfg: P4Config) -> float:
    r6 = ctx.K_primary - ic.lagged(ctx.K_primary, 36)
    d = ac.discovery_rows(ctx) & np.isfinite(r6)
    return float(np.quantile(r6[d], cfg.rise_q))


def raw_onsets(ctx: ac.Context, cfg: P4Config, thr: float) -> list[tuple[int, str]]:
    on = [(int(o), "E_BAND") for o in ic.band_onsets(ctx.K_primary, ctx.band_code, cfg)]
    on += [(int(o), "E_RISE") for o in ic.rise_onsets(ctx.K_primary, thr, cfg)]
    return sorted(on, key=lambda x: (x[0], x[1]))


def independent_onsets(ctx: ac.Context, cfg: P4Config, thr: float) -> list[tuple[int, str]]:
    """E_BAND and E_RISE onsets merged into INDEPENDENT episodes: an onset less than ep_refractory_h after an already
    kept onset (of either type) is the same deterioration and is dropped. Onsets outside every window are dropped."""
    on = [o for o in raw_onsets(ctx, cfg, thr) if ctx.window[o[0]] != ""]
    ref = cfg.ep_refractory_h * 60 // cfg.bucket_min
    kept: list[tuple[int, str]] = []
    for o, typ in on:
        if not kept or o - kept[-1][0] >= ref:
            kept.append((o, typ))
    return kept


def episode_table(ctx: ac.Context, cfg: P4Config) -> pd.DataFrame:
    K = ctx.K_primary
    thr = rise_threshold(ctx, cfg)
    kept = independent_onsets(ctx, cfg, thr)
    anchors = np.asarray([ic.rise_start(K, o, cfg) for o, _ in kept], dtype=int)      # start of the rise (MLE-M2)
    every = np.asarray([o for o, _ in raw_onsets(ctx, cfg, thr)], dtype=int)            # exclusion from all onsets (PY-L3)
    ctrl = ic.pick_controls(anchors, K, ctx.window, cfg, cfg.seed + 1, exclude=np.r_[every, anchors])
    rows = []
    for e, ((o, etype), a) in enumerate(zip(kept, anchors)):
        eid = f"EP-{e + 1:03d}"
        base = {"episode_id": eid, "episode_type": etype}
        rows.append({**base, "role": "EPISODE", "row": int(a), "T": ctx.index[a], "onset_detected_at": ctx.index[o],
                     "window": ctx.window[a], "kpi_at_T": K[a], "kpi_at_detection": K[o],
                     "kpi_T_minus_12h": K[a - 72] if a >= 72 else np.nan})
        for j, (_, c) in enumerate([x for x in ctrl if x[0] == e]):
            rows.append({**base, "role": f"CONTROL_{j + 1}", "row": int(c), "T": ctx.index[c], "onset_detected_at": pd.NaT,
                         "window": ctx.window[c], "kpi_at_T": K[c], "kpi_at_detection": np.nan,
                         "kpi_T_minus_12h": K[c - 72] if c >= 72 else np.nan})
    ep = pd.DataFrame(rows)
    ep["rise_threshold_6h"] = thr
    ep["label"] = EPISODE_LABEL
    return ep


def episode_metrics(F: pd.DataFrame, ep: pd.DataFrame, choice: pd.DataFrame, thr: pd.Series, cfg: P4Config) -> pd.DataFrame:
    out = []
    for c, r in choice.iterrows():
        x = F[c].to_numpy(float)
        rec = {"indicator_id": c}
        for scope, wins in (("repl", REPLICATION_MONTHS), ("holdout", (HOLDOUT,)), ("disc", ("DISCOVERY",))):
            e = ep[ep.window.isin(wins)]
            lead = np.array([ic.first_lead(x, int(r.sign), thr[c], int(rw), cfg) for rw in e.row])
            ev = lead != -1.0                                       # evaluable (feature coverage >= 50 %)
            is_ep = e.role.eq("EPISODE").to_numpy()
            rec[f"n_episodes_total_{scope}"] = int(is_ep.sum())
            is_ep, lead = is_ep[ev], lead[ev]
            rec[f"n_episodes_{scope}"] = int(is_ep.sum())
            rec[f"n_controls_{scope}"] = int((~is_ep).sum())
            rec[f"hit_rate_episode_{scope}"] = float(np.isfinite(lead[is_ep]).mean()) if is_ep.any() else np.nan
            rec[f"hit_rate_control_{scope}"] = float(np.isfinite(lead[~is_ep]).mean()) if (~is_ep).any() else np.nan
            rec[f"lift_{scope}"] = rec[f"hit_rate_episode_{scope}"] - rec[f"hit_rate_control_{scope}"]
            le = lead[is_ep][np.isfinite(lead[is_ep])]
            lc = lead[~is_ep][np.isfinite(lead[~is_ep])]
            informative = np.isfinite(rec[f"lift_{scope}"]) and rec[f"lift_{scope}"] > 0
            # the episode lead is meaningful only if crossings are more frequent before episodes than before controls
            rec[f"median_lead_min_{scope}"] = float(np.median(le)) if le.size and informative else np.nan
            rec[f"median_control_lead_min_{scope}"] = float(np.median(lc)) if lc.size else np.nan
            rec[f"lead_p25_min_{scope}"] = float(np.quantile(le, 0.25)) if le.size and informative else np.nan
            rec[f"lead_p75_min_{scope}"] = float(np.quantile(le, 0.75)) if le.size and informative else np.nan
        out.append(rec)
    return pd.DataFrame(out)


def episode_long(F: pd.DataFrame, ctx: ac.Context, ep: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Values of the selected indicators (and the KPI) at T-12 h .. T for every episode and control."""
    rows = ac.discovery_rows(ctx)
    parts = []
    series = {"KPI|PHASE3": ctx.K_primary, **{c: F[c].to_numpy(float) for c in cols}}
    for name, x in series.items():
        xd = x[rows & np.isfinite(x)]
        med = float(np.median(xd)) if xd.size else np.nan
        sc = float(np.subtract(*np.quantile(xd, [0.75, 0.25])) / 1.349) if xd.size else np.nan
        sc = sc if sc and np.isfinite(sc) and sc > 0 else np.nan
        for e in ep.itertuples():
            pos = e.row + REL_MIN // PRIMARY.bucket_min
            ok = pos >= 0
            v = np.full(len(pos), np.nan)
            v[ok] = x[pos[ok]]
            parts.append(pd.DataFrame({"episode_id": e.episode_id, "episode_type": e.episode_type, "role": e.role,
                                       "window": e.window, "T": e.T, "rel_minutes": REL_MIN, "indicator_id": name,
                                       "value": v, "z_vs_discovery": (v - med) / sc}))
    out = pd.concat(parts, ignore_index=True)
    out["label"] = EPISODE_LABEL
    return out


def main():
    cfg = PRIMARY
    ctx = ac.build_context(cfg)
    F = ac.load_features()
    lagdf = ac.load_lag_table()
    choice = ac.discovery_choice(lagdf)
    thr = ac.thresholds(F, ctx, choice)
    ep = episode_table(ctx, cfg)
    write_csv(ep.drop(columns="row"), "indicator_episodes.csv", lg)
    ep.to_csv(CACHE / "episodes_with_rows.csv", index=False)
    m = episode_metrics(F, ep, choice, thr, cfg)
    m = m.merge(thr.rename("threshold").rename_axis("indicator_id").reset_index(), on="indicator_id")
    m.round(6).to_csv(CACHE / "episode_metrics.csv", index=False)
    sel = choice[choice.disc_supported].index.tolist()
    top = choice.sort_values(["q_bh", "indicator_id"], kind="mergesort").index[:30].tolist()
    cols = sorted(set(sel) | set(top))
    write_parquet(episode_long(F, ctx, ep, cols), "indicator_episode_analysis.parquet", lg)
    e = ep[ep.role.eq("EPISODE")]
    lg.info("episodes: %s; controls %d; long-format indicators %d", e.groupby(["episode_type", "window"]).size().to_dict(),
            int((ep.role != "EPISODE").sum()), len(cols))


if __name__ == "__main__":
    main()
