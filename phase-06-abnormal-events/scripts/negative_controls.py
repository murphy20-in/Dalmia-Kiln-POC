"""Step 13 - Negative controls: does the detector find structure merely because the data are autocorrelated?

NC1 KPI_CIRCULAR_SHIFT      the KPI is rolled by 2..21 days within the out-of-sample window (autocorrelation and value
                            distribution kept, alignment with the process families destroyed); statistic = share of OOS
                            candidate episodes with >= 2 deviating families, and their mean family count.
NC2 RANDOM_WINDOWS          windows with the durations of the OOS final periods placed at random OOS RUNNING times outside
                            every candidate episode (+/- 6 h); statistic = mean deviating-family count.
NC3 AFR_CONTEXT_SHIFT       Phase 5 AFR transition times shifted by +/- 2..21 days; statistic = share of OOS candidate
                            episodes with an AFR stop / ramp-down near onset, and with any AFR transition in the window.
NC4 PHASE4_SHIFT            the Phase 4 indicator rolled by 2..21 days; statistic = share with an activation <= 2 h before
                            onset.
NC5 IN_SAMPLE_CALIBRATION   share of Apr-May RUNNING buckets above the cut (~0.10 expected: the cut is the training P90).
Families are the KPI's own inputs, so NC1 / NC2 test internal consistency beyond autocorrelation, not independent
confirmation. Do not over-interpret: the null keeps each series' autocorrelation, not the joint process dynamics.
Writes outputs/negative_control_results.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from abn_core import PRIMARY, TRAIN_END, family_arrays, family_stats, load_inputs, load_stage, log, run_pipeline, \
    write_csv

lg = log("negative_controls")
SHIFT_DAYS = tuple(range(2, 22))
N_RANDOM = 200


def roll_oos(g: pd.DataFrame, col: str, k: int) -> pd.DataFrame:
    g2 = g.copy()
    pos = np.flatnonzero(g.index > TRAIN_END)
    v = g2[col].to_numpy(float).copy()
    v[pos] = np.roll(v[pos], k)
    g2[col] = v
    return g2


def oos(ep: pd.DataFrame) -> pd.DataFrame:
    return ep[ep.reference_state.eq("OUT_OF_SAMPLE")] if len(ep) else ep


def row(control, statistic, observed, null, note):
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    p = float((1 + np.sum(null >= observed)) / (1 + null.size)) if null.size else np.nan
    p95 = float(np.quantile(null, 0.95)) if null.size else np.nan
    return {"control": control, "statistic": statistic, "observed": observed, "n_null": int(null.size),
            "null_median": float(np.median(null)) if null.size else np.nan, "null_p95": p95, "empirical_p": p,
            "result": ("OBSERVED_ABOVE_NULL_P95" if np.isfinite(p95) and observed > p95 else
                       "NOT_DISTINGUISHABLE_FROM_NULL"), "interpretation": note}


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    eo = oos(ep)
    fin = ep[ep.in_final_set]
    rows = []
    # NC1 --------------------------------------------------------------------------------------------------------
    s_multi, s_mean = [], []
    for d in SHIFT_DAYS:
        v = oos(run_pipeline({**inp, "grid": roll_oos(g, "K", d * 144)}, PRIMARY))
        s_multi.append(float((v.family_count >= 2).mean()) if len(v) else np.nan)
        s_mean.append(float(v.family_count.mean()) if len(v) else np.nan)
    note = ("families are KPI inputs: above-null = agreement is not an autocorrelation artefact (internal consistency, "
            "not independent confirmation)")
    rows.append(row("NC1_KPI_CIRCULAR_SHIFT", "share of OOS candidates with >= 2 deviating families",
                    float((eo.family_count >= 2).mean()), s_multi, note))
    rows.append(row("NC1_KPI_CIRCULAR_SHIFT", "mean deviating-family count of OOS candidates",
                    float(eo.family_count.mean()), s_mean, note))
    # NC2 --------------------------------------------------------------------------------------------------------
    rng = np.random.default_rng(PRIMARY.seed)
    fam = family_arrays(g)
    run = g.state.eq("RUNNING").to_numpy()
    blocked = np.zeros(len(g), bool)
    for s, e in zip(ep.pos_start, ep.pos_end):
        blocked[max(0, int(s) - 36):int(e) + 37] = True
    ok = run & ~blocked & (g.index > TRAIN_END)
    cs = np.r_[0, np.cumsum(ok)]
    lens = (fin.pos_end - fin.pos_start + 1).astype(int).to_numpy()
    null = []
    for _ in range(N_RANDOM):
        vals = []
        for L in lens:
            starts = np.flatnonzero(cs[L:] - cs[:-L] == L)
            if starts.size:
                s = int(rng.choice(starts))
                vals.append(family_stats(fam, ref, PRIMARY, slice(s, s + L))["family_count"])
        null.append(float(np.mean(vals)) if vals else np.nan)
    rows.append(row("NC2_RANDOM_WINDOWS", "mean deviating-family count (final periods vs same-length random RUNNING "
                    "windows outside candidates)", float(fin.family_count.mean()) if len(fin) else np.nan, null,
                    "above-null = final periods deviate across more families than ordinary running of the same length"))
    # NC3 --------------------------------------------------------------------------------------------------------
    ev = inp["events"]
    afr = ev.kind.str.startswith("AFR_")
    s_down, s_any = [], []
    for d in SHIFT_DAYS:
        for sign in (1, -1):
            e2 = ev.copy()
            e2.loc[afr, "event_time"] = e2.loc[afr, "event_time"] + pd.Timedelta(days=sign * d)
            v = oos(run_pipeline({**inp, "events": e2.sort_values("event_time").reset_index(drop=True)}, PRIMARY))
            s_down.append(float(v.afr_down_near_onset.mean()))
            s_any.append(float((v.afr_context != "NO_AFR_TRANSITION").mean()))
    note = "above-null = AFR transitions cluster around onsets beyond chance; still coincidence, never a cause"
    rows.append(row("NC3_AFR_CONTEXT_SHIFT", "share of OOS candidates with an AFR stop / ramp-down in [onset-3h, onset+1h]",
                    float(eo.afr_down_near_onset.mean()), s_down, note))
    rows.append(row("NC3_AFR_CONTEXT_SHIFT", "share of OOS candidates with any AFR transition in [onset-3h, end]",
                    float((eo.afr_context != "NO_AFR_TRANSITION").mean()), s_any, note))
    # NC4 --------------------------------------------------------------------------------------------------------
    s_p4 = []
    for d in SHIFT_DAYS:
        v = oos(run_pipeline({**inp, "grid": roll_oos(g, "p4", d * 144)}, PRIMARY))
        s_p4.append(float(v.phase4_indicator_overlap.mean()))
    rows.append(row("NC4_PHASE4_SHIFT", "share of OOS candidates with a Phase 4 activation <= 2 h before onset",
                    float(eo.phase4_indicator_overlap.mean()), s_p4,
                    "above-null = the LOW-confidence indicator is active before onsets beyond chance (supporting only)"))
    # NC5 --------------------------------------------------------------------------------------------------------
    tr = run & (g.index <= TRAIN_END) & g.K.notna().to_numpy()
    obs = float((g.K.to_numpy()[tr] >= ref["thr"]).mean())
    rows.append({"control": "NC5_IN_SAMPLE_CALIBRATION", "statistic": "share of Apr-May RUNNING KPI buckets >= cut",
                 "observed": obs, "n_null": 0, "null_median": 0.10, "null_p95": np.nan, "empirical_p": np.nan,
                 "result": "CONSISTENT" if abs(obs - 0.10) <= 0.03 else "INCONSISTENT",
                 "interpretation": "the cut is the training P90 of the persistent score: ~10 % expected by construction"})
    out = pd.DataFrame(rows)
    write_csv(out, "negative_control_results.csv", lg)
    lg.info("negative controls: %s", dict(zip(out.control + ":" + out.statistic.str[:30], out.result)))


if __name__ == "__main__":
    main()
