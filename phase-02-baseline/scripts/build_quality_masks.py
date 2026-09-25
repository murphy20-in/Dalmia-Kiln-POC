"""Step 3 - quality masks. Values are flagged, never deleted or changed.

Added columns (data/processed/<dataset>.parquet):
  value_valid     bool  - numeric source value usable as a measurement
  quality_flag    GOOD | SUSPECT | BAD | MISSING
  mask_reason     pipe-joined reasons (empty when GOOD)
  dup_status      UNIQUE | DUP_KEPT | DUP_IDENTICAL_COPY | DUP_CONFLICT
  row_repeat_prev source row identical to the previous source row in every column
  segment_id      contiguous 1-minute segment (breaks at every gap / resolution change)
  column_hold     Phase 1 derived column-level hold (baseline exclusion only)
  tag_flatline    inside a Phase 1 single-tag non-zero flatline period (>= 60 identical samples);
                  informational (quality_flag SUSPECT), NOT invalid - baseline sensitivity is reported
Informational reasons that do not invalidate a value: RESOLUTION_HOURLY (excluded from the
1-minute baseline later), SUSPECT_TAG_FLATLINE.

Duplicate-timestamp rule (deterministic): key = (source_column, ts) within a dataset,
ordered by (source_file, source_row). If all copies carry the same cell content the
first is kept (DUP_KEPT) and the others are DUP_IDENTICAL_COPY (value_valid=False).
If copies disagree, every copy is DUP_CONFLICT (value_valid=False): no winner is chosen.
Outputs: outputs/processed_dataset_manifest.csv, outputs/mask_summary.csv
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p2common import (processed_path, read_p1, read_out, write_csv, segments, log, H)

lg = log("build_quality_masks")
SENTINELS = [99999.0, 9999.0]
MASK_COLS = ["value_valid", "quality_flag", "mask_reason", "dup_status", "row_repeat_prev", "segment_id", "column_hold",
             "tag_flatline", "operating_state", "load_regime", "baseline_status", "baseline_reason", "state_basis"]


def main():
    contract = read_out("tag_contract.csv")
    holds = read_out("column_holds.csv")
    fw = read_out("frozen_windows.csv")
    sc = read_p1("sampling_changes.csv")
    hourly_days = sc[sc.day_mode_interval_min != 1][["dataset", "day"]]
    flat = read_p1("flatline_periods.csv")
    flat = flat[~flat.is_zero_value.astype(bool)]
    man, summ = [], []
    for eq in sorted(contract.dataset.unique()):
        p = processed_path(eq)
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        d = d.drop(columns=[c for c in MASK_COLS if c in d.columns])
        n = len(d)
        reasons = np.empty(n, dtype=object); reasons[:] = ""

        def add(mask, label):
            idx = np.flatnonzero(np.asarray(mask))
            for i in idx:
                reasons[i] = label if not reasons[i] else reasons[i] + "|" + label

        cc = d.cell_class.astype(str)
        missing = cc.isin(["EMPTY", "BLANK_STRING", "NONFINITE"]).to_numpy()
        add(missing, "MISSING")
        add(cc.eq("TEXT"), "TEXT_VALUE")
        add(cc.eq("NUMERIC_STRING"), "NUMERIC_STORED_AS_TEXT")
        add(d.ts.isna(), "TIMESTAMP_UNPARSED")
        for s in SENTINELS:
            add(d.value.eq(s), f"SENTINEL_{int(s)}")
        add(d.unit.astype(str).str.lower().eq("deg.c") & (d.value <= -273), "PHYSICALLY_IMPOSSIBLE_TEMP")
        for w in fw.itertuples():
            ds = json.loads(w.datasets)
            if eq in ds:
                add(d.ts.between(pd.Timestamp(w.window_start), pd.Timestamp(w.window_end)), "SUSPECTED_FROZEN_WINDOW")
        fp = flat[(flat.dataset == eq)]
        tf = np.zeros(n, dtype=bool)
        tsv = d.ts.to_numpy()
        colv = d.source_column.astype(str).to_numpy()
        for col, g in fp.groupby("tag"):
            idxs = np.flatnonzero(colv == col)
            order = np.argsort(tsv[idxs], kind="stable")      # NaT sorts last
            idxs = idxs[order]
            tcol = tsv[idxs]
            lo = np.searchsorted(tcol, pd.to_datetime(g.start).to_numpy(), side="left")
            hi = np.searchsorted(tcol, pd.to_datetime(g.end).to_numpy(), side="right")
            for a, b in zip(lo, hi):
                tf[idxs[a:b]] = True
        add(tf, "SUSPECT_TAG_FLATLINE")
        hd = pd.to_datetime(hourly_days[hourly_days.dataset == eq].day).dt.date
        if len(hd):
            add(d.ts.dt.date.isin(set(hd)), "RESOLUTION_HOURLY")

        # duplicates
        key = ["source_column", "ts"]
        dup_any = d.duplicated(key, keep=False) & d.ts.notna()
        dup_status = np.array(["UNIQUE"] * n, dtype=object)
        if dup_any.any():
            sub = d.loc[dup_any, key + ["value", "raw_value_text", "source_file", "source_row"]].copy()
            sub["sig"] = sub.value.astype(str).fillna("<NaN>") + "|" + sub.raw_value_text.astype(object).fillna("<none>").astype(str)
            assert sub.sig.notna().all()
            nun = sub.groupby(key, observed=True).sig.transform("nunique")
            sub = sub.sort_values(["source_column", "ts", "source_file", "source_row"])
            first = ~sub.duplicated(key, keep="first")
            st = np.where(nun.loc[sub.index] > 1, "DUP_CONFLICT", np.where(first, "DUP_KEPT", "DUP_IDENTICAL_COPY"))
            dup_status[sub.index.to_numpy()] = st
        add(dup_status == "DUP_CONFLICT", "DUPLICATE_TIMESTAMP_CONFLICT")
        add(dup_status == "DUP_IDENTICAL_COPY", "DUPLICATE_TIMESTAMP_COPY")

        # full-row repeats (every column equal to previous source row)
        w = d.pivot_table(index=["source_file", "source_row"], columns="source_column", values="value", observed=True,
                          dropna=False, aggfunc="first").sort_index()
        prev = w.groupby(level=0).shift(1)
        same = ((w == prev) | (w.isna() & prev.isna())).all(axis=1) & prev.notna().any(axis=1)
        rep = pd.Series(same.values, index=w.index).rename("row_repeat_prev").reset_index()
        d = d.merge(rep, on=["source_file", "source_row"], how="left", validate="many_to_one")

        # segments on distinct timestamps
        uts = pd.Series(np.sort(d.ts.dropna().unique()))
        seg = pd.DataFrame({"ts": uts, "segment_id": segments(uts).astype(np.int32).values})
        d = d.merge(seg, on="ts", how="left", validate="many_to_one")

        bad_tokens = ("TEXT_VALUE", "NUMERIC_STORED_AS_TEXT", "TIMESTAMP_UNPARSED", "SENTINEL_", "PHYSICALLY_IMPOSSIBLE",
                      "DUPLICATE_TIMESTAMP_CONFLICT")
        suspect_tokens = ("SUSPECTED_FROZEN_WINDOW", "DUPLICATE_TIMESTAMP_COPY", "SUSPECT_TAG_FLATLINE")
        r = pd.Series(reasons)
        is_bad = r.str.contains("|".join(bad_tokens), regex=True)
        is_susp = r.str.contains("|".join(suspect_tokens), regex=True)
        qf = np.where(missing, "MISSING", np.where(is_bad, "BAD", np.where(is_susp, "SUSPECT", "GOOD")))
        d["value_valid"] = d.value.notna().to_numpy() & ~is_bad.to_numpy() & ~r.str.contains("DUPLICATE_TIMESTAMP_COPY").to_numpy() \
            & ~r.str.contains("SUSPECTED_FROZEN_WINDOW").to_numpy()
        d["quality_flag"] = pd.Categorical(qf)
        d["mask_reason"] = pd.Categorical(r.values)
        d["dup_status"] = pd.Categorical(dup_status)
        hh = holds[holds.dataset == eq].groupby("source_column").hold.agg("|".join)
        d["column_hold"] = pd.Categorical(d.source_column.astype(str).map(hh).fillna(""))
        d["tag_flatline"] = tf
        d.to_parquet(p, index=False)
        # summaries
        for reason, cnt in pd.Series("|".join(x for x in r if x).split("|")).value_counts().items() if r.str.len().sum() else []:
            if reason:
                summ.append({"dataset": eq, "mask_reason": reason, "cells": int(cnt), "pct_of_cells": round(cnt / n * 100, 4)})
        man.append({
            "dataset": eq, "processed_file": str(p), "source_files": json.dumps(sorted(d.source_file.astype(str).unique())),
            "source_frequency": "1 minute (observed)" + ("; hourly on " + ", ".join(map(str, hd)) if len(hd) else ""),
            "analysis_frequency": "1 minute native; 10-minute medians for multivariate; daily/weekly/monthly for temporal",
            "resampling_required": "No (native grain kept)",
            "resampling_method": "none in processed layer; aggregation only in analysis outputs, never back-filled",
            "reason": "all approved files share the observed 1-minute grid" + ("; hourly rows kept as hourly and excluded from the minute baseline" if len(hd) else ""),
            "rows_long": n, "distinct_timestamps": int(uts.size), "columns": int(d.source_column.nunique()),
            "first_ts": uts.min(), "last_ts": uts.max(), "segments": int(seg.segment_id.nunique()),
            "cells_GOOD": int((qf == "GOOD").sum()), "cells_SUSPECT": int((qf == "SUSPECT").sum()),
            "cells_BAD": int((qf == "BAD").sum()), "cells_MISSING": int((qf == "MISSING").sum()),
            "dup_conflict_cells": int((dup_status == "DUP_CONFLICT").sum()),
            "dup_identical_copy_cells": int((dup_status == "DUP_IDENTICAL_COPY").sum()),
            "rows_repeating_previous_row_pct": round(float(rep.row_repeat_prev.mean() * 100), 3),
            "interpolated_values": 0, "unit_conversions": 0,
        })
        lg.info("%s: %d cells, GOOD %.2f%%", eq, n, (qf == "GOOD").mean() * 100)
    write_csv(pd.DataFrame(man), "processed_dataset_manifest.csv", lg)
    write_csv(pd.DataFrame(summ), "mask_summary.csv", lg)


if __name__ == "__main__":
    main()
