"""Step 2 - KPI-led CANDIDATE_ABNORMAL_PERIOD detection (primary configuration).

Candidate bucket: Phase 3 KPI (out-of-sample Jun-Aug; the in-sample Apr-May reference value is shown but flagged
IN_SAMPLE_REFERENCE) >= the frozen training P90 band cut (41.82) in a RUNNING bucket. Runs of candidate buckets are merged
across <= 60 min of RUNNING buckets unless a Phase 1 long gap / frozen window lies in the gap; nothing is deleted.
Writes outputs/abnormal_candidate_windows.parquet and cache/stage_episodes.parquet (the full primary episode frame that
the later steps slice).
"""
from __future__ import annotations

import numpy as np

from abn_core import CANDIDATE_LABEL, METHOD_VERSION, PRIMARY, candidate_flags, load_inputs, log, run_pipeline, \
    save_stage, write_parquet

lg = log("build_kpi_candidates")
COLS = ["episode_id", "start_time", "end_time", "detection_time", "onset_time", "duration_minutes", "candidate_buckets",
        "n_runs_merged", "end_reason", "right_censored", "reference_state", "month", "peak_kpi", "median_kpi",
        "kpi_integral", "kpi_slope", "kpi_onset_slope"]


def main():
    inp = load_inputs()
    ep = run_pipeline(inp, PRIMARY)
    save_stage(ep, "episodes")
    out = ep[COLS].copy()
    out.insert(1, "label", CANDIDATE_LABEL)
    out["kpi_column"] = "Phase 3 efficiency_deterioration_kpi (OOS) | kpi_in_sample_reference (Apr-May, in-sample)"
    out["candidate_rule"] = f"KPI >= {inp['ref']['thr']:.2f} (frozen training P90 band cut) in a RUNNING bucket"
    out["method_version"], out["config_key"] = METHOD_VERSION, PRIMARY.key()
    write_parquet(out, "abnormal_candidate_windows.parquet", lg)
    f = candidate_flags(inp["grid"], PRIMARY, inp["ref"])
    lg.info("%d candidate buckets -> %d candidate episodes (%d out of sample)", int(np.sum(f)), len(ep),
            int(ep.reference_state.eq("OUT_OF_SAMPLE").sum()))


if __name__ == "__main__":
    main()
