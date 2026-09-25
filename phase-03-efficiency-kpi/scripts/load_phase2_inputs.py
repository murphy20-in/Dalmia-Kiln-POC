"""Step 1 - Load Phase 2 inputs (read-only) and build the causal minute cache.

Reads  data/processed/<dataset>.parquet (Kiln-I, Kiln-IA, Kiln-II, Kiln-IIIA), operating_state_timeline.parquet and
       the Phase 2 output CSVs listed in p3common.P2_INPUTS (hashed, never modified).
Writes cache/minute_values.parquet  wide 1-minute values; NaN where a CAUSAL Phase 2 token invalidates the cell
       cache/minute_state.parquet   state_basic (Kiln MD composite) + Phase 2 operating_state per minute
       cache/p2_input_hashes.json   sha256 of every consumed Phase 2 file (G2 dependency integrity)
       outputs/kpi_data_quality.csv  per-tag causal-mask accounting vs Phase 2 retrospective flags

Retrospective Phase 2 flags (SUSPECTED_FROZEN_WINDOW, SUSPECT_TAG_FLATLINE, baseline_status, operating_state
ramp/pre-stop labels) are NOT used to mask scoring data; flatline / frozen masks are recomputed causally.
Columns with any Phase 2 column hold are dropped from the scoring cache (their training-window statistics
are still reported here, so full-period CONSTANT/SPARSE holds can be compared with the training window).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p3common import (CACHE, CAUSAL_INVALID_TOKENS, KPI_DATASETS, P2_INPUTS, P2_OUT, PRIMARY, PROCESSED,
                      RETROSPECTIVE_TOKENS, log, processed_path, read_p2, sha256, write_csv)
from kpi_core import prepare_minutes

lg = log("load_phase2_inputs")


def load_dataset(eq: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_parquet(processed_path(eq), columns=["ts", "source_column", "original_name", "unit", "value",
                                                      "mask_reason", "dup_status", "column_hold"])
    d = d[d.ts.notna() & d.dup_status.isin(["UNIQUE", "DUP_KEPT", "DUP_CONFLICT"])]
    reason = d.mask_reason.astype(str)
    bad = np.zeros(len(d), dtype=bool)
    for tok in CAUSAL_INVALID_TOKENS:
        bad |= reason.str.contains(tok, regex=False).to_numpy()
    bad |= d.dup_status.eq("DUP_CONFLICT").to_numpy()
    d = d.assign(tag=eq + "!" + d.source_column.astype(str), v=d.value.where(~bad),
                 retro_flat=reason.str.contains(RETROSPECTIVE_TOKENS[1], regex=False),
                 retro_frozen=reason.str.contains(RETROSPECTIVE_TOKENS[0], regex=False), causal_bad=bad)
    d = d.drop_duplicates(["tag", "ts"], keep="first")
    w = d.set_index(["ts", "tag"]).v.unstack("tag").sort_index()
    meta = d.groupby("tag", observed=True).agg(
        dataset=("tag", lambda s: eq), original_name=("original_name", "first"), unit=("unit", "first"),
        column_hold=("column_hold", lambda s: str(s.iloc[0]) if pd.notna(s.iloc[0]) else ""),
        minutes=("ts", "size"), causal_invalid_minutes=("causal_bad", "sum"),
        p2_retro_flatline_minutes=("retro_flat", "sum"), p2_retro_frozen_minutes=("retro_frozen", "sum")).reset_index()
    return w, meta


def main():
    hashes = {n: sha256(P2_OUT / n) for n in P2_INPUTS}
    for n in ["operating_state_timeline.parquet"] + [processed_path(e).name for e in KPI_DATASETS]:
        hashes[f"data/processed/{n}"] = sha256(PROCESSED / n)
    (CACHE / "p2_input_hashes.json").write_text(json.dumps(hashes, indent=1, sort_keys=True))
    frames, metas = [], []
    for eq in KPI_DATASETS:
        w, m = load_dataset(eq)
        frames.append(w)
        metas.append(m)
        lg.info("%s: %d minutes x %d tags", eq, *w.shape)
    st = pd.read_parquet(PROCESSED / "operating_state_timeline.parquet", columns=["ts", "state_basic", "operating_state"])
    st = st.set_index("ts").sort_index()
    idx = st.index
    for f in frames:
        idx = idx.union(f.index)
    values = pd.concat([f.reindex(idx) for f in frames], axis=1)
    values = values[sorted(values.columns)]
    state = st.reindex(idx)
    state["state_basic"] = state.state_basic.fillna("UNKNOWN")
    state["operating_state"] = state.operating_state.fillna("UNKNOWN")
    meta = pd.concat(metas, ignore_index=True)
    holds = read_p2("column_holds.csv").assign(tag=lambda h: h.dataset + "!" + h.source_column)
    held = sorted(set(holds.tag))
    # training-window re-check of full-period holds (reported only)
    tr = values.loc[PRIMARY.train_start:PRIMARY.train_end]
    meta["train_valid_share"] = meta.tag.map(tr.notna().mean())
    meta["train_distinct_values"] = meta.tag.map(tr.nunique())
    meta["p2_holds"] = meta.tag.map(holds.groupby("tag").hold.apply(lambda s: "|".join(sorted(set(s)))))
    meta["train_recheck"] = np.select(
        [meta.p2_holds.fillna("").str.contains("CONSTANT") & (meta.train_distinct_values > 1),
         meta.p2_holds.fillna("").str.contains("SPARSE") & (meta.train_valid_share >= 0.5)],
        ["CONSTANT on full period but varies in training window", "SPARSE on full period but >=50% valid in training window"], "")
    scoring = values.drop(columns=[c for c in values.columns if c in held])
    masked, flags = prepare_minutes(scoring, PRIMARY)
    causal_flat = (scoring.notna() & masked.isna()).sum()
    meta["causal_flatline_or_frozen_masked_minutes"] = meta.tag.map(causal_flat).fillna(0).astype(int)
    meta["in_scoring_cache"] = ~meta.tag.isin(held)
    meta["valid_minutes_after_causal_masks"] = meta.tag.map(masked.notna().sum()).fillna(0).astype(int)
    meta["pct_valid_after_causal_masks"] = (meta.valid_minutes_after_causal_masks / meta.minutes * 100).round(3)
    scoring.to_parquet(CACHE / "minute_values.parquet")
    state.to_parquet(CACHE / "minute_state.parquet")
    fz = flags.causal_frozen
    p2fw = read_p2("frozen_windows.csv")
    overlap = []
    for r in p2fw.itertuples():
        s0, s1 = pd.Timestamp(r.window_start), pd.Timestamp(r.window_end)
        seg = fz.loc[s0:s1]
        overlap.append({"dataset": "ALL", "tag": f"P2_FROZEN_WINDOW {s0}–{s1}", "minutes": len(seg),
                        "causal_frozen_minutes_inside": int(seg.sum()),
                        "first_causal_frozen_minute": str(seg[seg].index.min()) if seg.any() else ""})
    meta = meta.sort_values(["dataset", "tag"]).reset_index(drop=True)
    extra = pd.DataFrame(overlap + [{"dataset": "ALL", "tag": "CAUSAL_FROZEN_MINUTES_TOTAL", "minutes": len(fz),
                                     "causal_frozen_minutes_inside": int(fz.sum())}])
    write_csv(pd.concat([meta, extra], ignore_index=True), "kpi_data_quality.csv", lg)
    lg.info("scoring cache: %d minutes x %d tags (dropped %d held columns); causal frozen minutes %d",
            *scoring.shape, len([c for c in values.columns if c in held]), int(fz.sum()))


if __name__ == "__main__":
    main()
