"""Step 7 - Data-quality contamination of every candidate episode (episode buckets + the hour before detection).

data_quality_contamination = max(share of buckets with Phase 3 data_quality != GOOD,
                                 share of buckets overlapping a Phase 1 long gap / the DQ-016 frozen window,
                                 1 - median Phase 3 tag coverage)
>= 0.5 -> DATA_QUALITY_ARTIFACT (kept, never deleted, excluded from the final set); >= 0.2 -> DQ_AFFECTED (lowers
confidence). Masked-cell counts of the scored KPI tags by Phase 2 reason (sentinel 99999, text 'Error 6', -273 /
physically impossible, frozen window, tag flatline, conflicting duplicate timestamps, missing) are reported alongside.
Held columns: none is used (verified per tag in cache/tag_check.csv). Writes outputs/abnormal_episode_data_quality.csv.
"""
from __future__ import annotations

import pandas as pd

from abn_core import CACHE, load_inputs, load_stage, log, write_csv

lg = log("classify_data_quality")


def main():
    inp = load_inputs()
    g, dqw = inp["grid"], inp["dq_windows"]
    ep = load_stage("episodes")
    tc = pd.read_csv(CACHE / "tag_check.csv")
    mcols = [c for c in g.columns if c.startswith("n_mask_")]
    rows = []
    for r in ep.itertuples():
        seg = g.iloc[max(0, int(r.pos_start) - 6):int(r.pos_end) + 1]
        lo, hi = seg.index[0] - pd.Timedelta(minutes=10), seg.index[-1]
        w = dqw[(dqw.start < hi) & (dqw.end > lo)]
        d = {"episode_id": r.episode_id, "reference_state": r.reference_state,
             "dq_window_start": lo, "dq_window_end": hi,
             "share_buckets_not_good": r.dq_nongood_share, "share_buckets_in_phase1_dq_window": r.dq_window_share,
             "tag_coverage_loss": r.dq_coverage_loss, "masked_cell_share_kpi_tags": r.dq_masked_cell_share,
             "causal_frozen_minutes": int(seg.n_causal_frozen.fillna(0).sum()),
             "overlapping_phase1_windows": ";".join(w.kind + ":" + w.dataset.astype(str)) or "NONE",
             "held_columns_used": int((tc.column_hold.fillna("").astype(str) != "").sum()),
             "data_quality_contamination": r.data_quality_contamination,
             "data_quality_context": r.data_quality_context,
             "rule": "max(not-GOOD share, Phase 1 window share, 1 - median tag coverage); >= 0.5 ARTIFACT, >= 0.2 AFFECTED"}
        for c in mcols:
            d[c.replace("n_mask_", "masked_cells_")] = int(seg[c].fillna(0).sum())
        rows.append(d)
    out = pd.DataFrame(rows)
    write_csv(out, "abnormal_episode_data_quality.csv", lg)
    lg.info("DQ context: %s", out.data_quality_context.value_counts().to_dict())


if __name__ == "__main__":
    main()
