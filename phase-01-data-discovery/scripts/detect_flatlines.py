"""Objective I - flatline / sensor-health profiling.

A flatline period is >= flatline_min_samples consecutive, time-contiguous
(1-step) samples with an identical non-null value (POC DATA-QUALITY HEURISTIC).
Zero-value flatlines are reported separately because they may reflect equipment
that is stopped (not necessarily a sensor fault).
Outputs: outputs/flatline_profile.csv (per tag), outputs/flatline_periods.csv (each period)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import dataset_frames, load_dataset, write_csv, HEURISTICS, jdump


def runs(x: pd.Series, ts: pd.Series):
    """Yield (start_idx, end_idx, value) for runs of identical values across contiguous timestamps."""
    step = ts.diff().dt.total_seconds()
    mode = step.mode().iloc[0]
    brk = (x != x.shift(1)) | x.isna() | x.shift(1).isna() | (step != mode)
    gid = brk.cumsum()
    g = pd.DataFrame({"g": gid, "x": x, "i": np.arange(len(x))}).dropna(subset=["x"])
    agg = g.groupby("g").agg(start=("i", "first"), end=("i", "last"), n=("i", "size"), value=("x", "first"))
    return agg


def main():
    prof, periods = [], []
    minlen = HEURISTICS["flatline_min_samples"]
    for eq, tables in dataset_frames().items():
        df, meta = load_dataset(tables)
        df = df.drop_duplicates(subset="ts", keep="first").reset_index(drop=True)
        for c in [c for c in df.columns if c not in ("ts", "src_file")]:
            x = df[c]
            m = meta[c]
            v = x.dropna()
            if v.empty:
                prof.append({"dataset": eq, "tag": c, "original_name": m.original_name, "unit": m.unit_raw,
                             "health_class": "NO NUMERIC VALUES"})
                continue
            r = runs(x, df.ts)
            fl = r[r.n >= minlen]
            recov = 0
            for _, p in fl.iterrows():
                nxt = int(p.end) + 1
                jump = None
                if nxt < len(x) and pd.notna(x.iloc[nxt]):
                    jump = float(x.iloc[nxt] - p.value)
                scale = float(v.std()) or 1.0
                abrupt = jump is not None and abs(jump) > 3 * scale
                recov += int(abrupt)
                periods.append({"dataset": eq, "tag": c, "original_name": m.original_name, "value": p.value,
                                "start": df.ts.iloc[int(p.start)], "end": df.ts.iloc[int(p.end)],
                                "duration_min": int(p.n), "is_zero_value": p.value == 0,
                                "step_after_flatline": jump, "abrupt_recovery_candidate": abrupt})
            top_share = float(v.value_counts().iloc[0] / len(v))
            nz = fl[fl.value != 0]
            z = fl[fl.value == 0]
            if v.nunique() == 1:
                cls = "CONSTANT (single value)"
            elif top_share >= HEURISTICS["near_constant_top_share"]:
                cls = "NEAR-CONSTANT"
            elif fl.n.sum() / len(v) > 0.2:
                cls = "FREQUENT FLATLINES"
            elif len(fl):
                cls = "SOME FLATLINES"
            else:
                cls = "NO FLATLINE >= threshold"
            longest = fl.loc[fl.n.idxmax()] if len(fl) else None
            prof.append({
                "dataset": eq, "tag": c, "original_name": m.original_name, "unit": m.unit_raw,
                "health_class": cls, "unique_values": int(v.nunique()),
                "most_common_value": float(v.value_counts().index[0]), "most_common_value_share_pct": round(top_share * 100, 3),
                "flatline_threshold_samples": minlen,
                "number_of_flatline_periods": int(len(fl)),
                "number_of_nonzero_flatline_periods": int(len(nz)), "number_of_zero_flatline_periods": int(len(z)),
                "total_flatline_duration_min": int(fl.n.sum()),
                "longest_flatline_min": int(longest.n) if longest is not None else 0,
                "longest_flatline_value": float(longest.value) if longest is not None else None,
                "longest_flatline_start": df.ts.iloc[int(longest.start)] if longest is not None else None,
                "longest_flatline_end": df.ts.iloc[int(longest.end)] if longest is not None else None,
                "longest_nonzero_flatline_min": int(nz.n.max()) if len(nz) else 0,
                "longest_zero_flatline_min": int(z.n.max()) if len(z) else 0,
                "percentage_affected": round(float(fl.n.sum() / len(v) * 100), 3),
                "abrupt_recovery_candidates": recov,
            })
    write_csv(pd.DataFrame(prof), "flatline_profile.csv")
    write_csv(pd.DataFrame(periods), "flatline_periods.csv")


if __name__ == "__main__":
    main()
