"""Step 1 - Validate upstream phases and build the Phase 6 cache (read-only with respect to everything upstream).

Reads  phase-03 efficiency_deterioration_kpi.parquet / kpi_reference.json / kpi_reference_bands.csv / kpi_validation.csv
       phase-04 leading_indicator_set.csv (usable_downstream rows only) / indicator_feature_values.parquet
       phase-05 afr_transition_episodes.parquet / afr_validation.csv
       phase-02 operating_state_events.csv / column_holds.csv
       phase-01 gap_events.csv / dq_issue_register.csv / process_tag_inventory.csv
       data/processed/{kiln_i, kiln_ia, kiln_ii, kiln_iiia, operating_state_timeline}.parquet (via Phase 3 load_dataset)
Writes cache/input_hashes.json   sha256 of every consumed upstream file
       cache/grid.parquet         Phase 3 10-min KPI grid + load / fuel context buckets + Phase 4 indicator + DQ counts
       cache/events.parquet       Phase 2 STOP / RESTART and Phase 5 AFR transition episodes (context only)
       cache/dq_windows.parquet   Phase 1 long data gaps and the DQ-016 suspected frozen window
       cache/tag_check.csv        gateguard: every referenced tag verified against the Phase 1 inventory and holds
       cache/p6_reference.json    frozen Phase 6 reference (Apr-May RUNNING buckets only)
"""
from __future__ import annotations

import json
import re
from functools import reduce

import numpy as np
import pandas as pd

from abn_core import (AFR, CACHE, CONTEXT_TAGS, FAMILIES, LOAD_DATASETS, P1_OUT, P2_OUT, P3_OUT, P4_INDICATOR, P4_OUT,
                      P5_OUT, PROCESSED, STATE_DATASETS, fit_reference, ic, log, sha256)
import kpi_core
from load_phase2_inputs import load_dataset          # Phase 3, pure read of data/processed
from p3common import processed_path

lg = log("load_phase6_inputs")

P3_INPUTS = ["efficiency_deterioration_kpi.parquet", "kpi_component_scores.parquet", "kpi_reference.json",
             "kpi_reference_bands.csv", "kpi_definition.json", "kpi_validation.csv"]
P4_INPUTS = ["leading_indicator_set.csv", "indicator_feature_values.parquet", "indicator_feature_reference.json",
             "indicator_scores.csv", "indicator_lag_analysis.csv", "indicator_episodes.csv", "indicator_data_quality.csv",
             "indicator_validation.csv"]
P5_INPUTS = ["afr_transition_episodes.parquet", "afr_operating_bands.csv", "afr_daily_summary.csv",
             "afr_data_quality.csv", "afr_data_requirements.csv", "afr_validation.csv", "afr_load_relationships.csv",
             "afr_combustion_relationships.csv", "afr_thermal_relationships.csv", "afr_efficiency_relationships.csv",
             "afr_indicator_relationships.csv"]
P2_INPUTS = ["operating_state_events.csv", "column_holds.csv", "baseline_family_readiness.csv"]
P1_INPUTS = ["gap_events.csv", "dq_issue_register.csv", "process_tag_inventory.csv"]
KPI_TAG_DATASETS = ["Kiln-I", "Kiln-IA", "Kiln-II"]      # every scored KPI tag lives in these (Kiln-IIIA: clinker only)
MASK_CATEGORIES = {"MISSING": "MISSING", "SENTINEL": "SENTINEL_", "TEXT": "TEXT_VALUE",
                   "IMPOSSIBLE": "PHYSICALLY_IMPOSSIBLE", "FROZEN": "SUSPECTED_FROZEN_WINDOW",
                   "FLATLINE": "SUSPECT_TAG_FLATLINE", "DUP_CONFLICT": "DUPLICATE_TIMESTAMP_CONFLICT"}


def validate_upstream() -> dict:
    v3 = pd.read_csv(P3_OUT / "kpi_validation.csv")
    v4 = pd.read_csv(P4_OUT / "indicator_validation.csv")
    v5 = pd.read_csv(P5_OUT / "afr_validation.csv")
    if (v3.result != "PASS").any():
        raise SystemExit("Phase 3 validation is not all PASS - Phase 6 requires a validated KPI")
    if (v4.result == "FAIL").any() or (v5.result == "FAIL").any():
        raise SystemExit("Phase 4 / Phase 5 validation has FAIL rows - Phase 6 requires validated upstream phases")
    h = {f"phase-05/{n}": sha256(P5_OUT / n) for n in P5_INPUTS}
    h.update({f"phase-04/{n}": sha256(P4_OUT / n) for n in P4_INPUTS})
    h.update({f"phase-03/{n}": sha256(P3_OUT / n) for n in P3_INPUTS})
    h.update({f"phase-02/{n}": sha256(P2_OUT / n) for n in P2_INPUTS})
    h.update({f"phase-01/{n}": sha256(P1_OUT / n) for n in P1_INPUTS})
    for n in ["operating_state_timeline.parquet"] + [processed_path(e).name for e in LOAD_DATASETS]:
        h[f"data/processed/{n}"] = sha256(PROCESSED / n)
    return h


def context_buckets(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Load / fuel context tags on the Phase 3 grid. Speed and clinker: exactly the Phase 4 bucket construction (Phase 3
    causal masks). Coal and AFR firing: Phase 2 causal tokens + dataset frozen rows only (constant firing is legitimate,
    so the single-tag flatline mask is not applied - the Phase 5 AFR_P2 rule)."""
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
    vals, mstate = b["values"], b["minute_state"]
    k1 = frames["Kiln-I"]
    _, flags = kpi_core.prepare_minutes(k1, ic.P3CFG)
    frozen = flags.causal_frozen.reindex(k1.index).fillna(False).to_numpy(bool)
    fcols = ["Kiln-I!H", "Kiln-I!I", AFR]
    fuel = k1[fcols].where(k1[fcols] >= 0).mask(np.repeat(frozen[:, None], len(fcols), axis=1))
    fb = ic.bucket_medians(fuel, mstate.state, vals.index)
    out = pd.DataFrame(index=vals.index)
    for tag, col in CONTEXT_TAGS.items():
        if tag in fb:
            out[col] = fb[tag]
        elif tag in vals:
            out[col] = vals[tag]
        else:
            raise SystemExit(f"context tag {tag} missing after load (held or absent)")
    out["state_rebuilt"] = b["meta"].bucket_state
    return out.reindex(index)


def masked_counts(index: pd.DatetimeIndex, kpi_tags: list[str]) -> pd.DataFrame:
    """Per 10-min bucket (right-closed, labelled by end - the Phase 3 rule): masked cells of the scored KPI tags by
    Phase 2 mask reason (sentinel 99999, text 'Error 6', -273 / impossible, frozen window, tag flatline, conflicting
    duplicate timestamps, missing). Counted on every minute; used only as data-quality context."""
    parts = []
    for ds in KPI_TAG_DATASETS:
        cols = [t.split("!")[1] for t in kpi_tags if t.startswith(ds + "!")]
        d = pd.read_parquet(processed_path(ds), columns=["ts", "source_column", "mask_reason", "dup_status"],
                            filters=[("source_column", "in", cols)])
        d = d[d.ts.notna() & d.dup_status.isin(["UNIQUE", "DUP_KEPT", "DUP_CONFLICT"])]
        reason = d.mask_reason.astype(str).replace({"nan": "", "None": ""})
        f = pd.DataFrame({"bucket": d.ts.dt.ceil("10min").to_numpy(), "cells": 1,
                          "masked": (reason != "").astype(int).to_numpy()})
        for k, tok in MASK_CATEGORIES.items():
            f[f"n_mask_{k.lower()}"] = reason.str.contains(tok, regex=False).astype(int).to_numpy()
        f.loc[d.dup_status.eq("DUP_CONFLICT").to_numpy(), "n_mask_dup_conflict"] = 1
        parts.append(f.groupby("bucket").sum())
    m = reduce(lambda a, b: a.add(b, fill_value=0), parts)
    m["masked_share"] = m.masked / m.cells
    return m.reindex(index)


def tag_check(kpi_tags: list[str]) -> pd.DataFrame:
    """Gateguard: exact tag names, units, families and holds for every tag Phase 6 references."""
    inv = pd.read_csv(P1_OUT / "process_tag_inventory.csv")
    inv["tag"] = inv.dataset + "!" + inv.source_column
    holds = pd.read_csv(P2_OUT / "column_holds.csv")
    held = dict(zip(holds.dataset + "!" + holds.source_column, holds.hold))
    rows = []
    base = sorted({t.replace("STD60:", "") for t in kpi_tags})
    for tag, role in [(t, "KPI_INPUT (Phase 3 scored tag)") for t in base] + \
                     [(t, f"CONTEXT ({c})") for t, c in CONTEXT_TAGS.items()]:
        r = inv[inv.tag == tag]
        rows.append({"tag": tag, "role": role, "in_phase1_inventory": len(r) == 1,
                     "original_name": r.original_name.iloc[0] if len(r) else "",
                     "unit": r.detected_unit.iloc[0] if len(r) else "",
                     "phase1_family": r.likely_process_family.iloc[0] if len(r) else "",
                     "column_hold": held.get(tag, "")})
    return pd.DataFrame(rows)


def main():
    hashes = validate_upstream()
    (CACHE / "input_hashes.json").write_text(json.dumps(hashes, indent=1, sort_keys=True))
    kref = json.loads((P3_OUT / "kpi_reference.json").read_text())
    k = pd.read_parquet(P3_OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp").sort_index()
    ic.check_grid(k.index)
    g = pd.DataFrame(index=k.index)
    g.index.name = "ts"
    g["K"] = k.efficiency_deterioration_kpi.combine_first(k.kpi_in_sample_reference)
    g["in_sample"] = k.kpi_in_sample_reference.notna() | k.kpi_reference_state.str.startswith("IN_TRAINING")
    g["K_F"], g["K_G"], g["K_ALT"] = k.kpi_sp_heat_f_only, k.kpi_sp_heat_g_only, k.kpi_alt_reference_w_jun_jul15
    g["MAHA"] = k.secondary_validation_mahalanobis_kpi
    g["band_code"] = k.kpi_band_code.astype(int)
    g["D"], g["P"] = k.raw_deviation_score, k.persistent_deviation_score
    for d in FAMILIES:
        g[f"S_{d}"] = k[f"{d.lower()}_component"]
        g[f"C_{d}"] = k[f"contrib_{d.lower()}"]
    g["state"] = k.operating_state.astype(str)
    g["ref_state"] = k.kpi_reference_state.astype(str)
    g["dq"] = k.data_quality.astype(str)
    g["tag_cov"] = k.tag_coverage
    g["kpi_conf"] = k.kpi_confidence.astype(str)
    g["near_bnd"] = k.near_band_boundary.astype(bool)
    g["oor"] = k.out_of_training_load_range.astype(bool)
    g["driver"] = k.kpi_driver_class.astype(str)
    g["top_dimension"], g["top_tag"] = k.top_dimension.astype(str), k.top_tag.astype(str)
    g["n_causal_frozen"] = k.n_causal_frozen_minutes
    ctx = context_buckets(g.index)
    agree = float((ctx.state_rebuilt == g.state).mean())
    if agree < 0.999:
        raise SystemExit(f"rebuilt bucket state agrees with the Phase 3 KPI state on only {agree:.4f} of buckets")
    ctx = ctx.drop(columns="state_rebuilt")
    fd = (ctx.feed - k.load_context_feed_tph).abs()
    if fd.max() > 1e-9 or (ctx.feed.isna() != k.load_context_feed_tph.isna()).any():
        raise SystemExit(f"rebuilt feed buckets differ from Phase 3 load_context_feed_tph (max |diff| {fd.max()})")
    g = g.join(ctx)
    li = pd.read_csv(P4_OUT / "leading_indicator_set.csv")
    use = li[li.usable_downstream.astype(bool)]
    if list(use.indicator_id) != [P4_INDICATOR]:
        raise SystemExit(f"Phase 4 usable_downstream set changed: {list(use.indicator_id)}")
    fv = pd.read_parquet(P4_OUT / "indicator_feature_values.parquet", columns=["timestamp", P4_INDICATOR])
    g["p4"] = fv.set_index("timestamp")[P4_INDICATOR].reindex(g.index).astype(float)
    kpi_tags = list(kref["included_tags"])
    m = masked_counts(g.index, [t for t in kpi_tags if not t.startswith("STD60:")])
    g = g.join(m[[c for c in m.columns if c.startswith("n_mask_")] + ["masked_share"]])
    g.to_parquet(CACHE / "grid.parquet")

    # ------------------------------------------------------------------ events (context only)
    se = pd.read_csv(P2_OUT / "operating_state_events.csv", parse_dates=["at", "stop_end"])
    stops, rst = se[se.event == "STOP"], se[se.event == "RESTART"]
    ev = pd.concat([
        pd.DataFrame({"kind": "STOP", "event_time": stops["at"], "end": stops.stop_end, "ramp_minutes": np.nan,
                      "stop_minutes_before": np.nan, "event_id": [f"P2-STOP-{i:03d}" for i in range(len(stops))],
                      "status": "PHASE2_RETROSPECTIVE"}),
        pd.DataFrame({"kind": "RESTART", "event_time": rst["at"], "end": pd.NaT, "ramp_minutes": rst.ramp_minutes_applied,
                      "stop_minutes_before": rst.after_stop_minutes,
                      "event_id": [f"P2-RESTART-{i:03d}" for i in range(len(rst))],
                      "status": np.where(rst.censored.astype(bool), "RAMP_CENSORED", "PHASE2_RETROSPECTIVE")})])
    afr = pd.read_parquet(P5_OUT / "afr_transition_episodes.parquet",
                          columns=["episode_id", "afr_transition", "T", "status"]).drop_duplicates("episode_id")
    ev = pd.concat([ev, pd.DataFrame({"kind": afr.afr_transition.astype(str), "event_time": afr["T"], "end": pd.NaT,
                                      "ramp_minutes": np.nan, "stop_minutes_before": np.nan,
                                      "event_id": afr.episode_id.astype(str), "status": afr.status.astype(str)})],
                   ignore_index=True)
    ev = ev.sort_values(["event_time", "kind", "event_id"]).reset_index(drop=True)
    ev.to_parquet(CACHE / "events.parquet")

    # ------------------------------------------------------------------ Phase 1 DQ windows
    gaps = pd.read_csv(P1_OUT / "gap_events.csv", parse_dates=["gap_start_after", "gap_end_before"])
    gaps = gaps[gaps.long_gap & gaps.level.eq("DATASET") & gaps.dataset.isin(LOAD_DATASETS)]
    w = pd.DataFrame({"kind": np.where(gaps.dataset.isin(KPI_TAG_DATASETS), "LONG_GAP", "LOAD_TAG_GAP"),
                      "dataset": gaps.dataset, "start": gaps.gap_start_after, "end": gaps.gap_end_before,
                      "source": "phase-01 gap_events.csv (long_gap, DATASET level)"})
    reg = pd.read_csv(P1_OUT / "dq_issue_register.csv")
    rows = []
    for _, r in reg[reg.description.str.contains("frozen", case=False, na=False)].iterrows():
        t = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", str(r.location))
        if len(t) == 2:
            rows.append({"kind": "FROZEN_WINDOW", "dataset": str(r.source), "start": pd.Timestamp(t[0]),
                         "end": pd.Timestamp(t[1]), "source": f"phase-01 dq_issue_register {r.issue_id}"})
    if not rows:
        raise SystemExit("DQ-016 frozen window not found in the Phase 1 issue register")
    dqw = pd.concat([w, pd.DataFrame(rows)], ignore_index=True).sort_values(["start", "kind"]).reset_index(drop=True)
    dqw.to_parquet(CACHE / "dq_windows.parquet")

    # ------------------------------------------------------------------ gateguard tag check + frozen reference
    tc = tag_check(kpi_tags)
    tc.to_csv(CACHE / "tag_check.csv", index=False)
    if not tc.in_phase1_inventory.all() or (tc.column_hold.astype(str) != "").any():
        raise SystemExit(f"tag check failed:\n{tc}")
    bands = pd.read_csv(P3_OUT / "kpi_reference_bands.csv")
    kv = dict(zip(bands.quantity.str.split(" ").str[0], bands.kpi_value))
    ref = fit_reference(g, {"band_lo": float(kv["band_lo"]), "band_hi": float(kv["band_hi"])}, kref)
    ref["p4_indicator"] = P4_INDICATOR
    ref["p4_threshold"] = float(use.alarm_threshold.iloc[0])
    ref["p4_threshold_rule"] = str(use.alarm_threshold_rule.iloc[0])
    ref["kpi_version"] = kref["kpi_version"]
    (CACHE / "p6_reference.json").write_text(json.dumps(ref, indent=1, sort_keys=True))
    lg.info("grid %d buckets (RUNNING %d); state agreement %.4f; events %s; DQ windows %d; KPI cut %.2f / hi %.2f",
            len(g), int(g.state.eq("RUNNING").sum()), agree, ev.kind.value_counts().to_dict(), len(dqw), ref["thr"],
            ref["hi"])


if __name__ == "__main__":
    main()
