"""Step 7a - stability of baseline (INCLUDED) signals.

All rolling statistics are TRAILING windows (right-aligned: value at t uses t-w+1..t only),
computed within contiguous segments (never across gaps) and only on INCLUDED values,
with min_periods = 80 % of the window. No look-ahead.

Per tag:
  rolling std (15 / 60 min), rolling IQR (60 min, robust), |1-min rate of change|,
  stability_ratio = median rolling-60 std / baseline scaled MAD  (short-term vs overall variation)
  % of included minutes inside the robust band (median +/- k*scaled MAD)
  % of days whose daily median lies inside the P05-P95 band
  highest / lowest variation days (daily median of rolling-60 std)
  sensitivity: rolling-60 std with rows that repeat the previous row removed
Stability class (POC ANALYTICAL HEURISTIC on stability_ratio):
  < 0.5 LOW SHORT-TERM VARIATION | 0.5-1.0 MODERATE | > 1.0 HIGH SHORT-TERM VARIATION
Outputs: outputs/baseline_stability.csv, reports/figures/stability_rolling_std.png
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p2common import FIG, H, KEY_TAGS, datasets, read_out, wide_included, write_csv, log

lg = log("calculate_stability")


def trailing(x: pd.Series, seg: pd.Series, w: int, fn: str) -> pd.Series:
    mp = int(0.8 * w)
    g = x.groupby(seg.values)
    if fn == "std":
        return g.transform(lambda s: s.rolling(w, min_periods=mp).std())
    if fn == "iqr":
        return g.transform(lambda s: s.rolling(w, min_periods=mp).quantile(0.75) - s.rolling(w, min_periods=mp).quantile(0.25))
    if fn == "mean":
        return g.transform(lambda s: s.rolling(w, min_periods=mp).mean())
    raise ValueError(fn)


def main():
    bs = read_out("baseline_statistics.csv")
    bs = bs[bs.population == "BASELINE_RUNNING"].set_index(["dataset", "tag"])
    rows, keep_for_plot = [], {}
    for eq in datasets():
        w, seg, names, rep = wide_included(eq)
        for col in w.columns:
            if (eq, col) not in bs.index:
                continue
            b = bs.loc[(eq, col)]
            x = w[col]
            if x.notna().sum() < 120:
                continue
            r15 = trailing(x, seg, 15, "std")
            r60 = trailing(x, seg, 60, "std")
            q60 = trailing(x, seg, 60, "iqr")
            r60_norep = trailing(x.where(~rep), seg, 60, "std")
            same_seg = seg.eq(seg.shift(1))
            roc = x.diff().where(same_seg).abs()
            smad = b.scaled_mad
            k = H["band_mad_k"]
            inband = ((x >= b["median"] - k * smad) & (x <= b["median"] + k * smad))[x.notna()]
            day_med = x.groupby(x.index.date).median().dropna()
            in_p = ((day_med >= b.p05) & (day_med <= b.p95)).mean() if len(day_med) else np.nan
            dv = r60.groupby(r60.index.date).median().dropna()
            ratio = float(np.nanmedian(r60) / smad) if smad and np.isfinite(np.nanmedian(r60)) else np.nan
            cls = ("UNDEFINED (scaled MAD = 0)" if not np.isfinite(ratio) else
                   "LOW SHORT-TERM VARIATION" if ratio < 0.5 else "MODERATE" if ratio <= 1.0 else "HIGH SHORT-TERM VARIATION")
            rows.append({
                "dataset": eq, "tag": col, "original_name": names.get(col), "unit": b.unit, "process_family": b.process_family,
                "baseline_centre_median": b["median"], "baseline_scaled_mad": smad, "cv": b.cv, "robust_cv": b.robust_cv,
                "rolling_std_15_median": float(np.nanmedian(r15)), "rolling_std_60_median": float(np.nanmedian(r60)),
                "rolling_std_60_p90": float(np.nanquantile(r60.dropna(), 0.9)) if r60.notna().any() else np.nan,
                "rolling_iqr_60_median": float(np.nanmedian(q60)),
                "rolling_std_60_median_excl_repeated_rows": float(np.nanmedian(r60_norep)),
                "abs_rate_of_change_1min_median": float(np.nanmedian(roc)), "abs_rate_of_change_1min_p95": float(np.nanquantile(roc.dropna(), 0.95)) if roc.notna().any() else np.nan,
                "stability_ratio": ratio, "stability_class": cls,
                "pct_minutes_within_robust_band": round(float(inband.mean() * 100), 3) if len(inband) else np.nan,
                "pct_days_median_within_p05_p95": round(float(in_p * 100), 2) if np.isfinite(in_p) else np.nan,
                "high_variation_days": json.dumps({str(k2): round(float(v), 4) for k2, v in dv.nlargest(3).items()}),
                "low_variation_days": json.dumps({str(k2): round(float(v), 4) for k2, v in dv.nsmallest(3).items()}),
                "window_rule": "trailing, within segment, INCLUDED values only, min_periods=80%",
            })
            if (eq, col) in KEY_TAGS:
                keep_for_plot[(eq, col)] = (r60, names.get(col), b.unit)
    write_csv(pd.DataFrame(rows), "baseline_stability.csv", lg)
    plot(keep_for_plot)


def plot(kp):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(kp)
    fig, axes = plt.subplots(n, 1, figsize=(13, 1.6 * n), sharex=True)
    for ax, ((eq, col), (r, name, unit)) in zip(np.atleast_1d(axes), kp.items()):
        daily = r.resample("D").median()
        ax.plot(daily.index, daily.values, lw=0.9, color="#8c2d04")
        ax.set_ylabel(f"{eq}!{col}\n{name[:22]}\n[{unit}]", fontsize=7)
        ax.tick_params(labelsize=7)
    fig.suptitle("Daily median of trailing 60-min rolling std (INCLUDED baseline values)", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.985]); fig.savefig(FIG / "stability_rolling_std.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
