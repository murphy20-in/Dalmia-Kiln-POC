"""Step 10 - Post-event windows T_end + 30m .. + 6h (T_end = episode end; retrospective, never used to define episodes).

At each offset: KPI, D, the number of process families still above their training P90, the Mahalanobis KPI, feed and
the bucket state. Episode outcome (first match): DATA_END_CENSORED | FOLLOWED_BY_STOP (kiln not RUNNING within 6 h;
sequence only, not a consequence) | RECURRED_WITHIN_6H (another candidate episode starts within 6 h) | NO_KPI_AFTER (KPI unavailable over the 6 h) |
PROCESS_DEVIATION_PERSISTS (KPI back below the cut but >= 2 families still above P90 at +1 h) | RECOVERED.
Writes outputs/abnormal_episode_post_event.parquet and cache/stage_post_outcome.parquet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from abn_core import CACHE, FAMILIES, load_inputs, load_stage, log, write_parquet

lg = log("analyze_post_event_windows")
POST_OFFSETS = (("T+30m", 30), ("T+1h", 60), ("T+2h", 120), ("T+3h", 180), ("T+6h", 360))


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    ix, n = g.index, len(g)
    K, D, M, feed = (g[c].to_numpy(float) for c in ("K", "D", "MAHA", "feed"))
    state = g.state.to_numpy()
    fam_above = np.sum([g[f"S_{d}"].to_numpy(float) > ref["family_p90"][d] for d in FAMILIES], axis=0)
    starts = ep.pos_start.to_numpy()
    rows, outc = [], []
    for r in ep.itertuples():
        e = int(r.pos_end)
        w = slice(e + 1, min(n, e + 37))
        for lab, off in POST_OFFSETS:
            p = e + off // 10
            if p >= n:
                rows.append({"episode_id": r.episode_id, "offset_label": lab, "offset_minutes": off,
                             "bucket_end": pd.NaT, "censored": True})
                continue
            rows.append({"episode_id": r.episode_id, "offset_label": lab, "offset_minutes": off, "bucket_end": ix[p],
                         "censored": False, "state": state[p], "kpi": K[p], "d": D[p], "maha_kpi": M[p],
                         "feed": feed[p], "families_above_p90": int(fam_above[p]),
                         "kpi_below_cut": bool(K[p] < ref["thr"]) if np.isfinite(K[p]) else None})
        nxt = starts[(starts > e) & (starts <= e + 36)]
        k6 = K[w]
        p1 = e + 6
        if e + 36 >= n:
            o = "DATA_END_CENSORED"
        elif (state[w] != "RUNNING").any():
            o = "FOLLOWED_BY_STOP"
        elif nxt.size:
            o = "RECURRED_WITHIN_6H"
        elif not np.isfinite(k6).any():
            o = "NO_KPI_AFTER"
        elif fam_above[p1] >= 2:
            o = "PROCESS_DEVIATION_PERSISTS"
        else:
            o = "RECOVERED"
        outc.append({"episode_id": r.episode_id, "post_event_outcome": o,
                     "kpi_max_post_6h": float(np.nanmax(k6)) if np.isfinite(k6).any() else np.nan,
                     "kpi_drop_peak_to_1h": r.peak_kpi - K[p1] if p1 < n and np.isfinite(K[p1]) else np.nan,
                     "next_episode_within_6h": bool(nxt.size),
                     "minutes_to_next_episode": (float((ix[nxt[0]] - r.end_time) / pd.Timedelta(minutes=1))
                                                 if nxt.size else np.nan)})
    post = pd.DataFrame(rows).merge(pd.DataFrame(outc), on="episode_id", how="left")
    post["label"] = "RETROSPECTIVE POST-EPISODE CONTEXT - NOT USED TO DEFINE THE EPISODE"
    write_parquet(post, "abnormal_episode_post_event.parquet", lg)
    pd.DataFrame(outc).to_parquet(CACHE / "stage_post_outcome.parquet", index=False)
    lg.info("post-event outcomes: %s", pd.DataFrame(outc).post_event_outcome.value_counts().to_dict())


if __name__ == "__main__":
    main()
