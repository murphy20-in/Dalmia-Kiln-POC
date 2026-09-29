"""Step 9 - Pre-event windows T-12h .. T (T = CUSUM onset time; historical data only, descriptive - NOT predictive).

For every candidate episode: snapshots of the KPI, D, the five family scores, the Mahalanobis KPI, feed / coal changes,
kiln speed, clinker TPH, AFR and the Phase 4 indicator at T-12h, -6h, -3h, -2h, -1h, -30m and T (the bucket ending at T),
the first frozen-rule exceedance of each signal in the 12 h before T, the KPI turning point, and the Phase 5 AFR
transitions / Phase 2 stops and restarts in the window. base_rate_oos = share of out-of-sample RUNNING buckets outside
every candidate episode where the same signal rule is exceeded (context for reading the lead rows; full-period
descriptive, so it is not part of the causal leakage invariants). Input to Phase 7/8; no predictive claim is made.
Writes outputs/abnormal_episode_pre_event.parquet.
"""
from __future__ import annotations

import numpy as np

from abn_core import TRAIN_END, bucket_set, load_inputs, load_stage, log, pre_event, signal_table, write_parquet

lg = log("analyze_pre_event_windows")


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    pre = pre_event(g, ep, ref, inp["events"])
    inside = np.zeros(len(g), bool)
    inside[list(bucket_set(ep))] = True
    refm = g.state.eq("RUNNING").to_numpy() & (g.index > TRAIN_END) & ~inside
    base = {n: float(np.mean(ex[refm])) for n, (_, _, ex, _) in signal_table(g, ref).items() if ex is not None}
    pre["base_rate_oos"] = pre.signal.map(base).where(pre.row_type.eq("FIRST_EXCEEDANCE"))
    pre = pre.merge(ep[["episode_id", "onset_time", "reference_state"]], on="episode_id", how="left")
    pre["label"] = "HISTORICAL PRE-ONSET CONTEXT - DESCRIPTIVE, NOT A PREDICTIVE RESULT"
    write_parquet(pre, "abnormal_episode_pre_event.parquet", lg)
    fe = pre[pre.row_type.eq("FIRST_EXCEEDANCE") & pre.reference_state.eq("OUT_OF_SAMPLE")]
    lg.info("OOS share of episodes with a first exceedance in the 12 h before onset: %s",
            fe.groupby("signal").exceeded.mean().round(2).to_dict())


if __name__ == "__main__":
    main()
