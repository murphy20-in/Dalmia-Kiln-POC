"""Step 7b - temporal behaviour of the baseline (INCLUDED values only).

Levels: DAY, WEEK (ISO, Monday start), MONTH, plus HOUR_OF_DAY (pooled diurnal profile).
Drift (WEEK and MONTH): each period is compared ONLY with the pooled values strictly
BEFORE the period start (expanding prior reference) - no future data is used.
  shift_in_prior_scale = (period median - prior median) / prior_scale
  prior_scale = max(prior scaled MAD, prior IQR / 1.349, value resolution, 1 % of |prior median|)
                (floored so near-constant or integer-valued priors cannot inflate the shift)
  iqr_ratio_vs_prior        = period IQR / prior IQR
A prior reference needs >= 30 distinct days of prior INCLUDED data; otherwise NOT EVALUABLE.
A period with |shift| >= drift_mad_units is labelled 'NOTABLE LEVEL SHIFT (descriptive)'.
This documents observed behaviour only; it is NOT a deterioration/degradation finding.
Outputs: outputs/baseline_temporal_analysis.csv, reports/figures/temporal_daily_baseline.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p2common import (FIG, H, MAD_SCALE, KEY_TAGS, datasets, read_out, wide_included, write_csv, log, prior_compare,
                      value_resolution)

lg = log("analyze_temporal_baseline")


def agg(x: pd.Series) -> dict:
    v = x.dropna().to_numpy()
    if v.size == 0:
        return {"n": 0}
    q05, q25, q50, q75, q95 = np.quantile(v, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {"n": int(v.size), "median": float(q50), "mean": float(v.mean()), "p05": float(q05), "p95": float(q95),
            "iqr": float(q75 - q25), "scaled_mad": float(MAD_SCALE * np.median(np.abs(v - q50)))}


def main():
    bs = read_out("baseline_statistics.csv")
    bs = bs[bs.population == "BASELINE_RUNNING"].set_index(["dataset", "tag"])
    rows, plot_data = [], {}
    for eq in datasets():
        w, seg, names, _ = wide_included(eq)
        for col in w.columns:
            if (eq, col) not in bs.index:
                continue
            x = w[col].dropna()
            if x.size < 120:
                continue
            base = {"dataset": eq, "tag": col, "original_name": names.get(col), "unit": bs.loc[(eq, col), "unit"],
                    "process_family": bs.loc[(eq, col), "process_family"]}
            vals = x.to_numpy()
            tsv = x.index.to_numpy()
            resolution = value_resolution(vals)   # smallest step between distinct values
            for lvl, key in (("DAY", x.index.floor("D")), ("WEEK", x.index.to_period("W-SUN").start_time),
                             ("MONTH", x.index.to_period("M").start_time)):
                for per, g in x.groupby(key):
                    r = {**base, "level": lvl, "period_start": per, **agg(g)}
                    if lvl in ("WEEK", "MONTH"):
                        r.update(prior_compare(vals, tsv, per, r["median"], r["iqr"], resolution))
                    rows.append(r)
            hod = x.groupby(x.index.hour).median()
            smad = bs.loc[(eq, col), "scaled_mad"]
            for h, v in hod.items():
                rows.append({**base, "level": "HOUR_OF_DAY", "period_start": int(h), "n": int((x.index.hour == h).sum()), "median": float(v),
                             "diurnal_amplitude_in_scaled_mad": float((hod.max() - hod.min()) / smad) if smad else np.nan})
            if (eq, col) in KEY_TAGS:
                plot_data[(eq, col)] = (x.resample("D").median(), x.resample("D").quantile(0.05), x.resample("D").quantile(0.95),
                                        bs.loc[(eq, col)], names.get(col))
    out = pd.DataFrame(rows)
    write_csv(out, "baseline_temporal_analysis.csv", lg)
    plot(plot_data)


def plot(pdict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(pdict)
    fig, axes = plt.subplots(n, 1, figsize=(13, 1.7 * n), sharex=True)
    for ax, ((eq, col), (md, lo, hi, b, name)) in zip(np.atleast_1d(axes), pdict.items()):
        ax.fill_between(md.index, lo.values, hi.values, color="#c6dbef", step="mid", label="daily P05–P95")
        ax.plot(md.index, md.values, lw=0.9, color="#08519c", label="daily median")
        ax.axhline(b["median"], color="#636363", lw=0.8, ls="--", label="baseline median")
        ax.axhspan(b.p05, b.p95, color="#fdae6b", alpha=0.15, label="baseline P05–P95 (POC reference band)")
        ax.set_ylabel(f"{eq}!{col}\n{name[:22]}\n[{b.unit}]", fontsize=7); ax.tick_params(labelsize=7)
    np.atleast_1d(axes)[0].legend(fontsize=6, ncol=4, loc="upper right")
    fig.suptitle("Daily baseline evolution (INCLUDED values; gaps and excluded periods left empty) — reference bands are NOT limits", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.985]); fig.savefig(FIG / "temporal_daily_baseline.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
