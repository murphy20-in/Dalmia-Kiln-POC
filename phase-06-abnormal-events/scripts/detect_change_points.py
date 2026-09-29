"""Step 5 - Change-point evaluation of every candidate episode (causal one-sided CUSUM on the raw deviation D).

x_t = (D_t - training median) / training scaled MAD;  S_t = max(0, S_{t-1} + x_t - k), reset in non-RUNNING buckets.
k = half the shift from the training median to the training P90 of D (classical k = delta / 2); change point SUPPORTED when
the 6-h CUSUM rise S(detection) - min S over [detection - 6 h, detection] exceeds h = its training P90 (frozen). The
onset is the bucket after the last S = 0 in that window (censored if S never returned to 0). Uses data <= detection only.

A change point is NOT an abnormality by itself: startups, shutdowns, ramps and load changes also produce level shifts;
those are classified by the context step. Writes cache/change_points.csv (episode rows + the bucket-level alarm rates).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from abn_core import CACHE, PRIMARY, TRAIN_END, cusum, load_inputs, load_stage, log

lg = log("detect_change_points")


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    run = g.state.eq("RUNNING").to_numpy()
    S = cusum((g.D.to_numpy(float) - ref["D_median"]) / ref["D_mad"], ~run, ref["cusum_k"])
    look = PRIMARY.onset_lookback_min // 10 + 1
    rise = S - pd.Series(S).rolling(look, min_periods=1).min().to_numpy()
    oos = run & (g.index > TRAIN_END)
    tr = run & (g.index <= TRAIN_END)
    cols = ["episode_id", "reference_state", "detection_time", "onset_time", "onset_censored", "cusum_rise_6h",
            "change_point_supported", "level_shift_d", "kpi_onset_slope"]
    out = ep[cols].copy()
    out["onset_lead_minutes"] = (ep.detection_time - ep.onset_time).dt.total_seconds() / 60
    out["cusum_k"], out["cusum_h"] = ref["cusum_k"], ref["cusum_h"]
    for name, m in (("TRAINING (Apr-May RUNNING buckets)", tr), ("OUT_OF_SAMPLE (Jun-Aug RUNNING buckets)", oos)):
        out.loc[len(out)] = {"episode_id": "BUCKET_ALARM_RATE", "reference_state": name,
                             "change_point_supported": float(np.mean(rise[m] > ref["cusum_h"])),
                             "cusum_k": ref["cusum_k"], "cusum_h": ref["cusum_h"]}
    out.to_csv(CACHE / "change_points.csv", index=False)
    lg.info("change point supported in %d / %d episodes; bucket-level alarm rate train %.3f, OOS %.3f",
            int(ep.change_point_supported.sum()), len(ep), np.mean(rise[tr] > ref["cusum_h"]),
            np.mean(rise[oos] > ref["cusum_h"]))


if __name__ == "__main__":
    main()
