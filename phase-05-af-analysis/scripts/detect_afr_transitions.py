"""Step 5 - AFR TRANSITION EPISODES (empirical, from the AFR signal; NOT plant events) and their matched control anchors.

Reads  cache/buckets.parquet, cache/kpi_grid.parquet
Writes outputs/afr_transition_episodes.parquet  long table: one row per episode x signal x relative time
         (episode_id, afr_transition, T, window, status, load_coincident, rel_min -120..+180, signal, value,
          baseline = median over [T-60, T), delta = value - baseline)
       cache/episodes.csv          one row per detected episode (status, flags, bucket position)
       cache/episode_controls.csv  up to ctrl_per_ep control anchors per ELIGIBLE episode

Detection (af_core.detect_transitions) runs on RUNNING 10-min AFR buckets. Episodes are RETROSPECTIVE and descriptive by
design; nothing here is used as a feature. Episodes whose [T-120, T+180] window contains a non-RUNNING bucket (shutdown,
restart, gap), or a kiln stop / transition or another AFR transition within 6 h before the window start (or inside the
pre-window), or < 70 % valid AFR, are kept in the table with the exclusion reason and are not analysed. The post window may
contain the AFR restart / reversal (interruptions last ~30-60 min): that is part of the episode. AFR stops followed by a kiln stop are counted separately (EXCLUDED_KILN_STOP_AFTER).
Control anchors: eligible buckets of the same window with no AFR transition of any type within +-6 h, the episode's AFR
pre-state held unchanged over [T-60, T+30] (AFR stayed off / on, no ramp), nearest in 1-h feed level, seeded tie-break.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from af_core import CACHE, EPISODE_LABEL, FAMILIES, FEED_TAG, P4CFG, PRIMARY, detect_transitions, episode_status, ic, log, \
    on_state, write_parquet
import p4common

lg = log("detect_afr_transitions")
PRE_STATE = {"AFR_START": 0.0, "AFR_STOP": 1.0, "AFR_RAMP_UP": 1.0, "AFR_RAMP_DOWN": 1.0}


def episodes_table(b: pd.DataFrame, cfg=PRIMARY) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    run = b.bucket_state.eq("RUNNING").to_numpy()
    x = np.where(run, b[cfg.afr_series].to_numpy(float), np.nan)
    feed = np.where(run, b[FEED_TAG].to_numpy(float), np.nan)
    feed_l = ic.trailing_median(feed, 6, 3)
    win = p4common.month_of(b.index, P4CFG)
    ev = detect_transitions(x, cfg)
    all_pos = np.array([t for t, _ in ev], dtype=int)
    dfeed = np.abs(np.r_[feed_l[3:], [np.nan] * 3] - ic.lagged(feed_l, 3))       # |feed(T+30) - feed(T-30)|
    thr = float(np.quantile(dfeed[np.isfinite(dfeed) & (win == "DISCOVERY")], 0.9))
    rows = []
    for i, (t, typ) in enumerate(ev):
        pre, post = x[max(0, t - 6):t], x[t + 1:t + 7]
        rows.append({"episode_id": f"AFR-{i + 1:04d}", "afr_transition": typ, "pos": t, "T": b.index[t], "window": win[t],
                     "status": episode_status(t, run, np.isfinite(x), cfg, all_pos),
                     "load_coincident": bool(np.isfinite(dfeed[t]) and dfeed[t] >= thr),
                     "afr_before_tph": float(np.nanmedian(pre)) if np.isfinite(pre).any() else np.nan,
                     "afr_after_tph": float(np.nanmedian(post)) if np.isfinite(post).any() else np.nan,
                     "feed_level_tph": feed_l[t], "label": EPISODE_LABEL})
    ep = pd.DataFrame(rows)
    outside = ep.window.eq("") & ep.status.eq("ELIGIBLE")
    ep.loc[outside, "status"] = "EXCLUDED_OUTSIDE_WINDOWS"
    return ep, x, feed_l


def pick_controls(ep: pd.DataFrame, x: np.ndarray, run: np.ndarray, feed_l: np.ndarray, win: np.ndarray,
                  cfg=PRIMARY) -> pd.DataFrame:
    on = on_state(x, cfg.zero_cut)
    n = len(x)
    near = np.zeros(n, dtype=bool)
    for t in ep.pos:
        near[max(0, t - 36): t + 37] = True
    valid = np.isfinite(x)
    elig = np.array([not near[t] and episode_status(t, run, valid, cfg) == "ELIGIBLE" for t in range(n)])
    lvl = ic.trailing_median(x, 6, 3)
    steady = np.abs(np.r_[lvl[3:], [np.nan] * 3] - ic.lagged(lvl, 6)) < cfg.ramp_tph   # no ramp across [T-60, T+30]
    rng = np.random.default_rng(cfg.seed)
    rows, used = [], set()
    for r in ep[ep.status.eq("ELIGIBLE")].itertuples():
        s = PRE_STATE[r.afr_transition]
        cand = np.flatnonzero(elig & (win == r.window) & np.isfinite(feed_l) & steady)
        cand = np.array([c for c in cand if c not in used and np.all(on[c - 6:c + 4] == s)], dtype=int)
        if cand.size == 0:
            continue
        cand = cand[rng.permutation(cand.size)]
        order = np.argsort(np.abs(feed_l[cand] - r.feed_level_tph), kind="mergesort")
        for c in cand[order[: cfg.ctrl_per_ep]]:
            rows.append({"episode_id": r.episode_id, "control_pos": int(c)})
            used.add(int(c))
    return pd.DataFrame(rows, columns=["episode_id", "control_pos"])


def main():
    cfg = PRIMARY
    b = pd.read_parquet(CACHE / "buckets.parquet")
    g = pd.read_parquet(CACHE / "kpi_grid.parquet")
    run = b.bucket_state.eq("RUNNING").to_numpy()
    win = p4common.month_of(b.index, P4CFG)
    ep, x, feed_l = episodes_table(b, cfg)
    ctrl = pick_controls(ep, x, run, feed_l, win, cfg)
    ep.to_csv(CACHE / "episodes.csv", index=False)
    ctrl.to_csv(CACHE / "episode_controls.csv", index=False)
    sig = {"AFR (Kiln-I!K)": x}
    for tags in FAMILIES.values():
        for t in tags:
            sig[t] = g[t.split(":")[1]].to_numpy(float) if t.startswith("KPI:") else \
                np.where(run, b[t].to_numpy(float), np.nan)
    rel = np.arange(-cfg.ep_pre_min // 10, cfg.ep_post_min // 10 + 1)
    parts = []
    for r in ep.itertuples():
        p = r.pos + rel
        okp = (p >= 0) & (p < len(x))
        for name, y in sig.items():
            v = np.full(rel.size, np.nan)
            v[okp] = y[p[okp]]
            base = y[max(0, r.pos - 6):r.pos]
            bl = float(np.nanmedian(base)) if np.isfinite(base).any() else np.nan
            parts.append(pd.DataFrame({"episode_id": r.episode_id, "afr_transition": r.afr_transition, "T": r.T,
                                       "window": r.window, "status": r.status, "load_coincident": r.load_coincident,
                                       "rel_min": rel * 10, "signal": name, "value": v, "baseline": bl,
                                       "delta": v - bl}))
    long = pd.concat(parts, ignore_index=True)
    long["label"] = EPISODE_LABEL
    write_parquet(long, "afr_transition_episodes.parquet", lg)
    lg.info("episodes by type x status:\n%s", ep.groupby(["afr_transition", "status"]).size().unstack(fill_value=0))
    lg.info("eligible by window:\n%s", ep[ep.status.eq("ELIGIBLE")].groupby(["afr_transition", "window"]).size()
            .unstack(fill_value=0))
    lg.info("controls: %d for %d episodes", len(ctrl), ctrl.episode_id.nunique())
    (CACHE / "episode_summary.json").write_text(json.dumps(
        {"n_detected": int(len(ep)), "n_eligible": int(ep.status.eq("ELIGIBLE").sum()),
         "n_with_controls": int(ctrl.episode_id.nunique())}, sort_keys=True))


if __name__ == "__main__":
    main()
