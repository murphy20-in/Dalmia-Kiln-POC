"""Step 6 - baseline population and univariate + robust baseline statistics.

Baseline population rule (every cell gets baseline_status + baseline_reason):
  MASKED            value_valid is False (missing, sentinel, text, impossible, duplicate copy/conflict,
                    suspected frozen window, unparsed timestamp) -> reason = mask_reason
  EXCLUDED_COLUMN   column-level hold from Phase 1 evidence (unit review, constant, sparse,
                    sentinel-dominated, redundant duplicate, state-indicator)
  EXCLUDED_STATE    composite operating state is not RUNNING_PROXY (stopped, transition, conflict, unknown)
  EXCLUDED_RESOLUTION  hourly-sampled rows (CBS-II 1-10 June) - not a 1-minute measurement
  INCLUDED          everything else
Precedence is the order above. Nothing is deleted from data/processed; data/curated holds
INCLUDED rows only.

Statistics populations:
  BASELINE_RUNNING       all INCLUDED values (primary baseline)
  BASELINE_FEED_BAND_k   INCLUDED values within each load band (TENTATIVE stratification, see operating_regimes.csv)
  BASELINE_UNBANDED      INCLUDED values without a band label (no Kiln-I feed: September, trailing warm-up)
  REFERENCE_ALL_VALID    every valid value regardless of state (for contamination sensitivity ONLY)
Uncertainty: week-block bootstrap of the median of daily medians (days within a week are
resampled together) plus the observed min/max of monthly medians. Both assume that the
supplied months are representative; the monthly spread shows the non-stationarity directly.
Sensitivity (outputs/baseline_sensitivity.csv): BASELINE_RUNNING median / P05 / P95 / scale
recomputed without single-tag flatlines, without repeated rows, without 6/12/24 h after each
restart-ramp end, and without minutes whose state rests on Kiln MD without Kiln-I feed evidence.
fit_window: every statistic is fitted on the full supplied period (descriptive). Later phases
must refit on their own training window before scoring any period.
Outputs: outputs/baseline_population.csv, outputs/baseline_statistics.csv, outputs/baseline_sensitivity.csv,
         data/processed/<ds>.parquet (+ operating_state, load_regime, baseline_status, baseline_reason),
         data/curated/<ds>_baseline.parquet
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p2common import (PROCESSED, H, MAD_SCALE, processed_path, curated_path, read_out, datasets, write_csv, log)

lg = log("calculate_baseline")
ADDED = ["operating_state", "load_regime", "baseline_status", "baseline_reason", "state_basis"]
QUANTS = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]


def stats(x: np.ndarray, days: np.ndarray, rng, months: np.ndarray | None = None) -> dict:
    keep = ~np.isnan(x)
    x, days = x[keep], days[keep]
    if x.size == 0:
        return {"valid_count": 0}
    q = np.quantile(x, QUANTS)
    med = float(q[4])
    mad = float(np.median(np.abs(x - med)))
    smad = MAD_SCALE * mad
    mean, std = float(x.mean()), float(x.std(ddof=1)) if x.size > 1 else 0.0
    d = {"valid_count": int(x.size), "mean": mean, "median": med, "std": std, "min": float(x.min()), "max": float(x.max()),
         **{f"p{int(round(qq * 100)):02d}": float(v) for qq, v in zip(QUANTS, q)},
         "iqr": float(q[5] - q[3]), "mad": mad, "scaled_mad": smad,
         "cv": std / abs(mean) if mean else np.nan, "robust_cv": smad / abs(med) if med else np.nan,
         "trimmed_mean_5pct": float(np.mean(np.sort(x)[int(0.05 * x.size): max(int(0.95 * x.size), int(0.05 * x.size) + 1)])),
         "mean_minus_median_in_scaled_mad": (mean - med) / smad if smad else np.nan,
         "std_to_scaled_mad_ratio": std / smad if smad else np.nan}
    d["outlier_sensitivity"] = ("UNDEFINED (MAD=0)" if not smad else
                                "SENSITIVE (mean/std inflated by extremes)" if d["std_to_scaled_mad_ratio"] > H["outlier_sensitivity_ratio"]
                                or abs(d["mean_minus_median_in_scaled_mad"]) > 0.5 else "ROBUST (mean/std close to median/MAD)")
    # day-block bootstrap CI of the median of daily medians (1-minute values are autocorrelated,
    # so a naive i.i.d. CI would be far too narrow)
    dser = pd.Series(x).groupby(days).median()
    dm = dser.to_numpy()
    if dm.size >= 5:
        wk = pd.to_datetime(pd.Series(dser.index)).dt.to_period("W-SUN").to_numpy()
        blocks = [dm[wk == w] for w in pd.unique(wk)]
        nb = len(blocks)
        bs = np.array([np.median(np.concatenate([blocks[j] for j in rng.integers(0, nb, nb)])) for _ in range(H["bootstrap_reps"])])
        d.update({"n_days": int(dm.size), "n_weeks": nb, "median_of_daily_medians": float(np.median(dm)),
                  "median_of_daily_medians_ci95_low": float(np.quantile(bs, 0.025)),
                  "median_of_daily_medians_ci95_high": float(np.quantile(bs, 0.975)),
                  "ci_method": "week-block bootstrap of daily medians (assumes representative weeks)"})
    if months is not None:
        mm = pd.Series(x).groupby(months).median()
        mm = mm[pd.Series(x).groupby(months).size() >= 1440]
        if len(mm):
            d.update({"monthly_median_min": float(mm.min()), "monthly_median_max": float(mm.max()), "n_months": int(len(mm))})
    return d


def main():
    tl = pd.read_parquet(PROCESSED / "operating_state_timeline.parquet", columns=["ts", "operating_state", "state_basis"])
    evs = read_out("operating_state_events.csv")
    rs = evs[evs.event == "RESTART"]
    ramp_ends = (pd.to_datetime(rs["at"]) + pd.to_timedelta(rs.ramp_minutes_applied, unit="min")).sort_values().to_numpy()
    rg = pd.read_parquet(PROCESSED / "regime_timeline.parquet", columns=["ts", "load_regime"])
    regimes_supported = read_out("operating_regimes.csv").query("test == 'SUPPORT_DECISION' and dimension == 'LOAD'").value.iloc[0] == 1.0
    rng = np.random.default_rng(H["seed"])
    pop_rows, stat_rows, sens_rows = [], [], []
    for eq in datasets():
        p = processed_path(eq)
        d = pd.read_parquet(p)
        d = d.drop(columns=[c for c in ADDED if c in d.columns])
        d = d.merge(tl, on="ts", how="left", validate="many_to_one").merge(rg, on="ts", how="left", validate="many_to_one")
        d["operating_state"] = d.operating_state.fillna("UNKNOWN")
        mr = d.mask_reason.astype(str)
        hourly = mr.str.contains("RESOLUTION_HOURLY").to_numpy()
        hold = d.column_hold.astype(str).to_numpy()
        valid = d.value_valid.to_numpy()
        st = d.operating_state.to_numpy()
        status = np.where(~valid, "MASKED", np.where(hold != "", "EXCLUDED_COLUMN",
                          np.where(st != "RUNNING_PROXY", "EXCLUDED_STATE", np.where(hourly, "EXCLUDED_RESOLUTION", "INCLUDED"))))
        reason = np.where(status == "MASKED", np.where(mr.to_numpy() == "", "NO_NUMERIC_VALUE", mr.to_numpy()),
                          np.where(status == "EXCLUDED_COLUMN", hold, np.where(status == "EXCLUDED_STATE", st,
                                   np.where(status == "EXCLUDED_RESOLUTION", "RESOLUTION_HOURLY", "BASELINE_RUNNING"))))
        d["baseline_status"] = pd.Categorical(status)
        d["baseline_reason"] = pd.Categorical(reason)
        for c in ("operating_state", "load_regime", "state_basis"):
            d[c] = d[c].astype("category")
        d.to_parquet(p, index=False)
        inc = d[d.baseline_status == "INCLUDED"]
        inc.to_parquet(curated_path(eq), index=False)
        lg.info("%s: %d cells, %d INCLUDED (%.1f%%)", eq, len(d), len(inc), len(inc) / len(d) * 100)

        for col, g in d.groupby("source_column", observed=True):
            meta = g.iloc[0]
            cnt = g.groupby(["baseline_status", "baseline_reason"], observed=True).size()
            gi = g[g.baseline_status == "INCLUDED"]
            pop_rows.append({
                "dataset": eq, "tag": col, "original_name": meta.original_name, "normalized_name": meta.normalized_name,
                "unit": meta.unit, "process_family": meta.likely_process_family,
                "source_files": json.dumps(sorted(g.source_file.astype(str).unique())), "source_sheet": meta.source_sheet,
                "cells_total": len(g), "included": int((g.baseline_status == "INCLUDED").sum()),
                "masked": int((g.baseline_status == "MASKED").sum()),
                "excluded_column": int((g.baseline_status == "EXCLUDED_COLUMN").sum()),
                "excluded_state": int((g.baseline_status == "EXCLUDED_STATE").sum()),
                "excluded_resolution": int((g.baseline_status == "EXCLUDED_RESOLUTION").sum()),
                "included_pct": round(len(gi) / len(g) * 100, 3),
                "first_included_ts": gi.ts.min() if len(gi) else None, "last_included_ts": gi.ts.max() if len(gi) else None,
                "column_hold": meta.column_hold,
                "counts_by_status_reason": json.dumps({f"{a}:{b}": int(v) for (a, b), v in cnt.items() if v}),
                "population_rule": "INCLUDED = value_valid & no column hold & operating_state==RUNNING_PROXY & not hourly",
            })
            if meta.column_hold:
                continue
            pops = {"BASELINE_RUNNING": gi}
            if regimes_supported:
                for b, gb in gi.groupby("load_regime", observed=True):
                    pops[f"BASELINE_{b}"] = gb
                pops["BASELINE_UNBANDED"] = gi[gi.load_regime.isna()]
            pops["REFERENCE_ALL_VALID"] = g[g.value_valid]
            sens_rows.extend(sensitivity(eq, col, meta, gi, ramp_ends))
            for pname, gp in pops.items():
                if gp.empty:
                    continue
                x = gp.value.to_numpy(dtype=float)
                s = stats(x, gp.ts.dt.date.to_numpy(), rng, gp.ts.dt.to_period("M").astype(str).to_numpy())
                nr = gp[~gp.row_repeat_prev.fillna(False)].value.to_numpy(dtype=float)
                s["median_excl_repeated_rows"] = float(np.median(nr)) if nr.size else np.nan
                s["scaled_mad_excl_repeated_rows"] = float(MAD_SCALE * np.median(np.abs(nr - np.median(nr)))) if nr.size else np.nan
                stat_rows.append({"dataset": eq, "tag": col, "original_name": meta.original_name,
                                  "normalized_name": meta.normalized_name, "unit": meta.unit,
                                  "process_family": meta.likely_process_family, "population": pname,
                                  "count": len(gp), "tag_cells_total": len(g), "tag_missing_cells": int(g.value.isna().sum()),
                                  "band_coverage_of_running_pct": round(len(gp) / len(gi) * 100, 3) if len(gi) and pname.startswith("BASELINE_") else None,
                                  **s,
                                  "first_ts": gp.ts.min(), "last_ts": gp.ts.max(),
                                  "fit_window": f"{gp.ts.min()} .. {gp.ts.max()} (full supplied period; refit before scoring use)",
                                  "source_files": json.dumps(sorted(gp.source_file.astype(str).unique()))})
    write_csv(pd.DataFrame(pop_rows), "baseline_population.csv", lg)
    write_csv(pd.DataFrame(stat_rows), "baseline_statistics.csv", lg)
    write_csv(pd.DataFrame(sens_rows), "baseline_sensitivity.csv", lg)


def _summ(v: np.ndarray) -> tuple:
    if v.size == 0:
        return (np.nan,) * 4
    m = float(np.median(v))
    return m, float(np.quantile(v, 0.05)), float(np.quantile(v, 0.95)), float(MAD_SCALE * np.median(np.abs(v - m)))


def sensitivity(eq, col, meta, gi: pd.DataFrame, ramp_ends: np.ndarray) -> list[dict]:
    base = _summ(gi.value.to_numpy(dtype=float))
    t = gi.ts.to_numpy()
    k = np.searchsorted(ramp_ends, t, side="right") - 1
    since = np.where(k >= 0, (t - ramp_ends[np.clip(k, 0, None)]) / np.timedelta64(1, "h"), np.inf)
    variants = {
        "excl_single_tag_flatlines": ~gi.tag_flatline.to_numpy(dtype=bool),
        "excl_repeated_rows": ~gi.row_repeat_prev.fillna(False).to_numpy(dtype=bool),
        "excl_6h_after_ramp_end": since >= 6, "excl_12h_after_ramp_end": since >= 12, "excl_24h_after_ramp_end": since >= 24,
        "excl_state_without_kiln_i_feed_evidence": (gi.state_basis.astype(str) == "KILN_MD + KILN_I_FEED/SPEED").to_numpy(),
    }
    out = []
    for name, keep in variants.items():
        v = gi.value.to_numpy(dtype=float)[keep]
        s_ = _summ(v)
        out.append({"dataset": eq, "tag": col, "original_name": meta.original_name, "unit": meta.unit, "variant": name,
                    "n_primary": len(gi), "n_variant": int(keep.sum()),
                    "median_primary": base[0], "median_variant": s_[0], "p05_variant": s_[1], "p95_variant": s_[2],
                    "scaled_mad_variant": s_[3],
                    "median_shift_in_primary_scaled_mad": (s_[0] - base[0]) / base[3] if base[3] else np.nan})
    return out


if __name__ == "__main__":
    main()
