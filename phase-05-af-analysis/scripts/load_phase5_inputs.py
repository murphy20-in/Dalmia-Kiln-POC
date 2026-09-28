"""Step 1 - Validate upstream phases and build the Phase 5 cache (read-only with respect to everything upstream).

Reads  data/processed/{kiln_i, kiln_ia, kiln_ii, kiln_iiia, cbs_calculation, operating_state_timeline}.parquet
       (via Phase 3 load_dataset: Phase 2 causal tokens -> NaN, conflicting duplicate timestamps dropped)
       phase-03 efficiency_deterioration_kpi.parquet / kpi_reference.json / kpi_validation.csv
       phase-04 indicator_feature_values.parquet / leading_indicator_set.csv / indicator_validation.csv
Writes cache/input_hashes.json  sha256 of every consumed upstream file
       cache/buckets.parquet     RUNNING 10-min bucket medians on the Phase 3 KPI grid:
         target / context tags  Phase 3 causal flatline + frozen masks (exactly the Phase 4 construction)
         AFR_P2                 AFR | Solid after Phase 2 causal tokens, negatives -> NaN, dataset frozen rows -> NaN; the
                                single-tag flatline mask is NOT applied (constant integer firing is legitimate)
         AFR_P3MASKED           AFR with the Phase 3 single-tag flatline mask too (sensitivity G)
         AFR_NOFLAT             AFR_P2 without Phase 2 SUSPECT_TAG_FLATLINE minutes (sensitivity G)
         afr_on_share           share of valid RUNNING minutes with AFR > zero_cut in the bucket
         bucket_state           causal Phase 3 state (RUNNING / STOPPED / TRANSITION / ...)
       cache/minute_afr.parquet  minute AFR (Phase 2 values, negatives kept for accounting) + minute state
       cache/kpi_grid.parquet    Phase 3 KPI (K shown, K_F, K_G, K_ALT, D, band_code, data_quality) on the grid
       cache/p4_indicator.parquet  Phase 4 feature Kiln-I!I|ROC_1H (the only usable_downstream row)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from af_core import (AFR, CACHE, FAMILIES, FEED_TAG, LOAD_DATASETS, P1_OUT, P2_OUT, P3_OUT, P4_INDICATOR, P4_OUT,
                     PRIMARY, PROCESSED, STATE_DATASETS, ic, log, sha256)
import kpi_core
from load_phase2_inputs import load_dataset          # Phase 3, pure read of data/processed
from p3common import processed_path

lg = log("load_phase5_inputs")

P4_INPUTS = ["leading_indicator_set.csv", "indicator_feature_values.parquet", "indicator_feature_reference.json",
             "indicator_scores.csv", "indicator_lag_analysis.csv", "indicator_episodes.csv", "indicator_data_quality.csv",
             "indicator_validation.csv"]
P3_INPUTS = ["efficiency_deterioration_kpi.parquet", "kpi_component_scores.parquet", "kpi_reference.json",
             "kpi_definition.json", "kpi_validation.csv"]
P2_INPUTS = ["column_holds.csv", "baseline_confidence.csv", "baseline_family_readiness.csv", "baseline_stability.csv",
             "baseline_reference_bands.csv"]
P1_INPUTS = ["process_tag_inventory.csv", "unit_consistency_review.csv", "dq_issue_register.csv",
             "alternative_fuel_inventory.csv"]
CONTEXT = ["Kiln-I!H", "Kiln-I!I", "Kiln-I!J", "Kiln-I!M"]


def main():
    cfg = PRIMARY
    v3 = pd.read_csv(P3_OUT / "kpi_validation.csv")
    v4 = pd.read_csv(P4_OUT / "indicator_validation.csv")
    if (v3.result != "PASS").any():
        raise SystemExit("Phase 3 validation is not all PASS - Phase 5 requires a validated KPI")
    if (v4.result == "FAIL").any():
        raise SystemExit("Phase 4 validation has FAIL rows - Phase 5 requires a validated Phase 4")
    hashes = {f"phase-04/{n}": sha256(P4_OUT / n) for n in P4_INPUTS}
    hashes.update({f"phase-03/{n}": sha256(P3_OUT / n) for n in P3_INPUTS})
    hashes.update({f"phase-02/{n}": sha256(P2_OUT / n) for n in P2_INPUTS})
    hashes.update({f"phase-01/{n}": sha256(P1_OUT / n) for n in P1_INPUTS})
    for n in ["operating_state_timeline.parquet"] + [processed_path(e).name for e in LOAD_DATASETS]:
        hashes[f"data/processed/{n}"] = sha256(PROCESSED / n)
    (CACHE / "input_hashes.json").write_text(json.dumps(hashes, indent=1, sort_keys=True))

    # ------------------------------------------------------------------ minute frames (Phase 4 construction)
    holds = pd.read_csv(P2_OUT / "column_holds.csv")
    held = set(holds.dataset + "!" + holds.source_column)
    st = pd.read_parquet(PROCESSED / "operating_state_timeline.parquet", columns=["ts", "state_basic", "operating_state"])
    st = st.set_index("ts").sort_index()
    raw = {}
    for ds in LOAD_DATASETS:
        w, _ = load_dataset(ds)
        raw[ds] = w.drop(columns=[c for c in w.columns if c in held])
    idx = st.index
    for ds in STATE_DATASETS:
        idx = idx.union(raw[ds].index)
    state = st.reindex(idx)
    state["state_basic"] = state.state_basic.fillna("UNKNOWN")
    state["operating_state"] = state.operating_state.fillna("UNKNOWN")
    frames = {ds: raw[ds].reindex(idx) for ds in LOAD_DATASETS}
    del raw
    b = ic.build_buckets(frames, state, STATE_DATASETS)
    meta, mstate = b["meta"], b["minute_state"]

    # ------------------------------------------------------------------ AFR series
    k1 = frames["Kiln-I"]
    afr_min = k1[AFR].copy()
    _, flags = kpi_core.prepare_minutes(k1, ic.P3CFG)          # dataset-level causal frozen rows (logger fault)
    frozen = flags.causal_frozen.reindex(afr_min.index).fillna(False).to_numpy(bool)
    p2 = afr_min.where(afr_min >= 0).mask(frozen)
    pr = pd.read_parquet(processed_path("Kiln-I"), columns=["ts", "source_column", "mask_reason", "dup_status"],
                         filters=[("source_column", "==", "K")])
    pr = pr[pr.dup_status.isin(["UNIQUE", "DUP_KEPT", "DUP_CONFLICT"])].drop_duplicates("ts").set_index("ts")
    flat = pr.mask_reason.astype(str).str.contains("SUSPECT_TAG_FLATLINE", regex=False).reindex(p2.index)
    flat = flat.fillna(False).to_numpy(bool)
    series = pd.DataFrame({"AFR_P2": p2, "AFR_NOFLAT": p2.mask(flat)})
    grid_ix = meta.index
    ab = ic.bucket_medians(series, mstate.state, grid_ix)
    on = pd.DataFrame({"afr_on_share": np.where(p2.notna(), (p2 > cfg.zero_cut).astype(float), np.nan)}, index=p2.index)
    run = mstate.state.reindex(on.index).eq("RUNNING")
    rs = kpi_core._resample(on.where(run, axis=0), ic.P3CFG)   # mean of the 0/1 minute flag (same bucketing rule)
    ab["afr_on_share"] = rs.mean().where(rs.count() >= ic.P3CFG.bucket_min_valid).reindex(grid_ix).afr_on_share
    vals = b["values"]
    ab["AFR_P3MASKED"] = vals[AFR]
    tags = sorted({t for f in FAMILIES.values() for t in f if not t.startswith("KPI:")} | set(CONTEXT) | {FEED_TAG})
    missing = [t for t in tags if t not in vals]
    if missing:
        raise SystemExit(f"target tags missing after load (held or absent): {missing}")
    buckets = pd.concat([vals[tags], ab], axis=1)
    buckets["bucket_state"] = meta.bucket_state

    # ------------------------------------------------------------------ KPI grid (Phase 4 load_phase3_inputs logic)
    k = pd.read_parquet(P3_OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp").sort_index()
    ref = json.loads((P3_OUT / "kpi_reference.json").read_text())
    g = pd.DataFrame(index=k.index)
    g["K"] = k.efficiency_deterioration_kpi.combine_first(k.kpi_in_sample_reference)
    g["K_OOS"] = k.efficiency_deterioration_kpi
    g["K_F"], g["K_G"], g["K_ALT"] = k.kpi_sp_heat_f_only, k.kpi_sp_heat_g_only, k.kpi_alt_reference_w_jun_jul15
    g["band_code"] = k.kpi_band_code.astype(int)
    g["D"] = k.raw_deviation_score
    g["kpi_state"] = k.operating_state.astype(str)
    g["data_quality"] = k.data_quality.astype(str)
    g.index.name = "ts"
    ic.check_grid(g.index)
    extra = g.index.difference(buckets.index)
    if len(extra):
        raise SystemExit(f"Phase 3 KPI grid has {len(extra)} buckets absent from the rebuilt bucket grid - grids diverged")
    dropped = buckets.index.difference(g.index)          # expected: only the leading partial bucket (2025-04-01 00:00)
    if len(dropped) > 1:
        raise SystemExit(f"rebuilt bucket grid has {len(dropped)} buckets outside the Phase 3 KPI grid")
    buckets = buckets.reindex(g.index)
    buckets.index.name = "ts"
    buckets.to_parquet(CACHE / "buckets.parquet")
    g.to_parquet(CACHE / "kpi_grid.parquet")
    (CACHE / "kpi_scale.json").write_text(json.dumps({"m": ref["scale"]["m"], "q_anchor": ref["scale"]["q_anchor"]}))
    pd.DataFrame({"afr_raw": afr_min, "afr_p2": p2, "frozen_row": frozen, "p2_flatline": flat,
                  "state": mstate.state.reindex(afr_min.index).fillna("UNKNOWN")}).rename_axis("ts") \
        .to_parquet(CACHE / "minute_afr.parquet")
    fv = pd.read_parquet(P4_OUT / "indicator_feature_values.parquet", columns=["timestamp", P4_INDICATOR])
    fv.set_index("timestamp").reindex(g.index).rename_axis("ts").to_parquet(CACHE / "p4_indicator.parquet")
    run_b = buckets.bucket_state.eq("RUNNING")
    lg.info("grid %d buckets; RUNNING %d; bucket state RUNNING agrees with Phase 3 KPI state on %.4f of buckets",
            len(g), int(run_b.sum()), (run_b == g.kpi_state.eq("RUNNING")).mean())
    lg.info("AFR_P2 valid RUNNING buckets %.3f; AFR_P3MASKED %.3f", buckets.AFR_P2[run_b].notna().mean(),
            buckets.AFR_P3MASKED[run_b].notna().mean())


if __name__ == "__main__":
    main()
