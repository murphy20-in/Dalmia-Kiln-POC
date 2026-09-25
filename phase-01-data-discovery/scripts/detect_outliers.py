"""Objective H - DATA-QUALITY outlier scan (NOT the kiln anomaly model).

Methods (POC DATA-QUALITY HEURISTICS): IQR (1.5x and 3x), robust z-score via MAD
(|z| > 3.5), percentile tails (<p0.1 / >p99.9) and first-difference spikes
(robust z of |diff| > 10). Sentinel candidates are profiled separately and are
excluded from the statistical scans so they do not distort them.

Every flag is a "SUSPECTED OUTLIER". Statistically unusual is not the same as bad
data: shutdowns, start-ups and genuine process excursions will also be flagged.
Outputs: outputs/outlier_profile.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import dataset_frames, load_dataset, write_csv, HEURISTICS, SENTINEL_NUMERIC, jdump


def describe(eq, c, meta, method, mask, x, ts, runcol, extra=""):
    k = int(mask.sum())
    if k == 0:
        return None
    sel = x[mask]
    tsel = ts[mask]
    b0 = None
    if runcol is not None and c != "B":
        b0 = round(float(((runcol[mask] == 0) | runcol[mask].isna()).mean() * 100), 2)
    return {
        "dataset": eq, "column": c, "original_name": meta.original_name, "unit": meta.unit_raw, "method": method,
        "number_of_suspect_points": k, "percentage_of_points": round(k / int(x.notna().sum()) * 100, 4),
        "example_values": jdump([float(v) for v in sel.value_counts().head(5).index]),
        "suspect_min": float(sel.min()), "suspect_max": float(sel.max()),
        "time_range_start": tsel.min(), "time_range_end": tsel.max(),
        "pct_suspects_where_colB_is_0_or_missing": b0,
        "potential_issue": extra,
        "label": "SUSPECTED OUTLIER",
    }


def main():
    rows = []
    for eq, tables in dataset_frames().items():
        df, meta = load_dataset(tables)
        runcol = df["B"] if "B" in df else None
        for c in [c for c in df.columns if c not in ("ts", "src_file")]:
            raw = df[c]
            m = meta[c]
            sent = raw.isin(list(SENTINEL_NUMERIC))
            if sent.any():
                r = describe(eq, c, m, "SENTINEL_VALUE_MATCH", sent, raw, df.ts, runcol,
                             "value matches a common placeholder/sentinel (e.g. 99999); requires validation")
                rows.append(r)
            x = raw.where(~sent)
            v = x.dropna()
            if v.nunique() <= 2 or len(v) < 100:
                continue
            q1, q3 = v.quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr > 0:
                for k, lab in ((HEURISTICS["iqr_k"], "IQR_1.5"), (HEURISTICS["iqr_extreme_k"], "IQR_3.0")):
                    mask = (x < q1 - k * iqr) | (x > q3 + k * iqr)
                    rows.append(describe(eq, c, m, lab, mask, x, df.ts, runcol,
                                         f"outside [{q1 - k * iqr:.4g}, {q3 + k * iqr:.4g}]"))
            med = v.median()
            mad = (v - med).abs().median()
            if mad > 0:
                z = 0.6745 * (x - med) / mad
                rows.append(describe(eq, c, m, "ROBUST_Z_MAD_3.5", z.abs() > HEURISTICS["mad_z"], x, df.ts, runcol,
                                     f"median={med:.4g}, MAD={mad:.4g}"))
            lo, hi = v.quantile([0.001, 0.999])
            rows.append(describe(eq, c, m, "PERCENTILE_TAIL_0.1", (x < lo) | (x > hi), x, df.ts, runcol,
                                 f"below p0.1={lo:.4g} or above p99.9={hi:.4g}"))
            d = x.diff()
            # only consecutive 1-minute steps
            step = df.ts.diff().dt.total_seconds().eq(60)
            d = d.where(step)
            dv = d.dropna()
            dmad = (dv - dv.median()).abs().median()
            if dmad > 0:
                zd = 0.6745 * (d - dv.median()).abs() / dmad
                rows.append(describe(eq, c, m, "SPIKE_FIRST_DIFF_Z10", zd > HEURISTICS["spike_mad_z"], x, df.ts, runcol,
                                     "abrupt 1-minute step change; may be process event, start/stop or sensor issue"))
    out = pd.DataFrame([r for r in rows if r])
    write_csv(out, "outlier_profile.csv")


if __name__ == "__main__":
    main()
