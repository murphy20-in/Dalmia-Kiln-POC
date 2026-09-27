"""Step 1 - Validate and load the Phase 3 KPI (the Phase 4 target) without modifying anything upstream.

Reads  phase-03-efficiency-kpi/outputs/{efficiency_deterioration_kpi.parquet, kpi_reference.json, kpi_validation.csv, ...}
       phase-02-baseline/outputs/{column_holds, baseline_confidence, ...}.csv, phase-01 outputs (hashed only)
Writes cache/input_hashes.json   sha256 of every consumed upstream file (G1 dependency integrity)
       cache/kpi_grid.parquet    the Phase 3 KPI on the 10-min bucket grid, reduced to what Phase 4 needs:
         K          shown KPI: kpi_in_sample_reference in the training window, efficiency_deterioration_kpi after it
         K_F, K_G   single-Sp.Heat-definition KPIs (out of sample only)
         K_ALT      shadow KPI with the later-anchored W_JUN_JUL15 reference (out of sample from 2025-07-16)
         band_code  0 / 1 / 2 (-1 = no KPI shown); D = raw deviation score; bucket_state; data_quality
The Phase 3 scorer is not bypassed: the target is exactly the leakage-tested Phase 3 output. Phase 3 must have passed all
of its validation checks; otherwise Phase 4 stops.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p4common import (CACHE, P1_INPUTS, P1_OUT, P2_INPUTS, P2_OUT, P3_INPUTS, P3_OUT, PROCESSED, ALL_DATASETS, log,
                      read_p3, sha256)
from p3common import processed_path

lg = log("load_phase3_inputs")


def main():
    v = read_p3("kpi_validation.csv")
    n_fail = int((v.result != "PASS").sum())
    if n_fail:
        raise SystemExit(f"Phase 3 validation has {n_fail} non-PASS checks - Phase 4 requires a validated KPI")
    hashes = {f"phase-03/{n}": sha256(P3_OUT / n) for n in P3_INPUTS}
    hashes.update({f"phase-02/{n}": sha256(P2_OUT / n) for n in P2_INPUTS})
    hashes.update({f"phase-01/{n}": sha256(P1_OUT / n) for n in P1_INPUTS})
    for n in ["operating_state_timeline.parquet"] + [processed_path(e).name for e in ALL_DATASETS]:
        hashes[f"data/processed/{n}"] = sha256(PROCESSED / n)
    (CACHE / "input_hashes.json").write_text(json.dumps(hashes, indent=1, sort_keys=True))

    k = pd.read_parquet(P3_OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp").sort_index()
    ref = json.loads((P3_OUT / "kpi_reference.json").read_text())
    g = pd.DataFrame(index=k.index)
    g["K"] = k.efficiency_deterioration_kpi.combine_first(k.kpi_in_sample_reference)
    g["K_F"] = k.kpi_sp_heat_f_only
    g["K_G"] = k.kpi_sp_heat_g_only
    g["K_ALT"] = k.kpi_alt_reference_w_jun_jul15
    g["band_code"] = k.kpi_band_code.astype(int)
    g["D"] = k.raw_deviation_score
    g["bucket_state"] = k.operating_state.astype(str)
    g["data_quality"] = k.data_quality.astype(str)
    g["kpi_reference_state"] = k.kpi_reference_state.astype(str)
    g["feed_tph"] = k.load_context_feed_tph
    g.index.name = "ts"
    g.to_parquet(CACHE / "kpi_grid.parquet")
    (CACHE / "kpi_scale.json").write_text(json.dumps({"m": ref["scale"]["m"], "q_anchor": ref["scale"]["q_anchor"]}))
    lg.info("Phase 3 validation: %d/%d PASS; KPI grid %d buckets (%s .. %s); K shown %d; K_F %d; K_G %d; K_ALT %d",
            len(v), len(v), len(g), g.index.min(), g.index.max(), int(g.K.notna().sum()), int(g.K_F.notna().sum()),
            int(g.K_G.notna().sum()), int(g.K_ALT.notna().sum()))
    lg.info("band codes %s", g.band_code.value_counts().sort_index().to_dict())
    assert np.all(np.diff(g.index.values).astype("timedelta64[m]").astype(int) == 10), "KPI grid must be regular"


if __name__ == "__main__":
    main()
