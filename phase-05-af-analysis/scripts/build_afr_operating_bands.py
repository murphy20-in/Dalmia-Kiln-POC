"""Step 4 - POC empirical AFR bands and firing-pattern summaries (DESCRIPTIVE, retrospective, non-causal).

Reads  cache/buckets.parquet, cache/minute_afr.parquet
Writes outputs/afr_operating_bands.csv    NO / LOW / MEDIUM / HIGH_AFR cuts fitted on DISCOVERY RUNNING buckets (frozen),
                                          with band occupancy and median kiln feed per analysis window
       outputs/afr_daily_summary.csv      per calendar day
       outputs/afr_monthly_summary.csv    per month, incl. ON / OFF run durations (persistence) and ramp variability
       cache/bands.json                   the frozen cuts (used by every later step)

Bands are POC_EMPIRICAL_BAND labels of the observed distribution - NOT plant operating limits or targets.
Duty cycle = share of valid RUNNING minutes with AFR > zero_cut (missing minutes are excluded, never counted as zero).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from af_core import BAND_LABEL, BANDS, CACHE, FEED_TAG, P4CFG, PRIMARY, assign_band, fit_bands, log, on_state, runs, write_csv
import p4common

lg = log("build_afr_operating_bands")
DESC = "DESCRIPTIVE HISTORICAL STATISTIC (RETROSPECTIVE, NON-CAUSAL) — NOT A FEATURE, LIMIT OR TARGET"


def bucket_frame(cfg=PRIMARY, series: str = "AFR_P2") -> pd.DataFrame:
    b = pd.read_parquet(CACHE / "buckets.parquet")
    run = b.bucket_state.eq("RUNNING").to_numpy()
    x = np.where(run, b[series].to_numpy(float), np.nan)
    f = pd.DataFrame({"afr": x, "running": run, "feed": np.where(run, b[FEED_TAG].to_numpy(float), np.nan),
                      "window": p4common.month_of(b.index, P4CFG)}, index=b.index)
    f["on"] = on_state(f.afr.to_numpy(), cfg.zero_cut)
    lv = pd.Series(f.afr).rolling(6, min_periods=4).median()          # trailing 1-h level (t-60, t]
    f["level_1h"] = lv.to_numpy()
    f["ramp_1h"] = (lv - lv.shift(6)).to_numpy()                       # 1-h ramp of the trailing level
    return f


def run_stats(on: np.ndarray, value: float) -> tuple[int, float, float]:
    r = runs(on)
    L = r[r.value == value].length.to_numpy() * 10
    return int(L.size), float(np.median(L)) if L.size else np.nan, float(np.quantile(L, 0.9)) if L.size else np.nan


def summarise(f: pd.DataFrame, m: pd.DataFrame, key_b: np.ndarray, key_m: np.ndarray, keys) -> pd.DataFrame:
    rows = []
    step = m.afr_p2.diff().abs()
    for k in keys:
        fb, mm = f[key_b == k], m[key_m == k]
        r = mm.state.eq("RUNNING").to_numpy()
        v = mm.afr_p2.to_numpy(float)[r]
        v = v[np.isfinite(v)]
        nz = v[v > PRIMARY.zero_cut]
        on = fb.on.to_numpy()
        sw = np.r_[False, (on[1:] != on[:-1]) & np.isfinite(on[1:]) & np.isfinite(on[:-1])]
        n_on, on_med, on_p90 = run_stats(on, 1.0)
        n_off, off_med, off_p90 = run_stats(on, 0.0)
        ramp = fb.ramp_1h.to_numpy()
        ramp = ramp[np.isfinite(ramp)]
        rows.append({"period": str(k), "minutes": len(mm), "running_minutes": int(r.sum()),
                     "afr_valid_running_minutes": int(v.size),
                     "afr_missing_running_minutes": int(r.sum() - v.size),
                     "zero_running_minutes": int((v <= PRIMARY.zero_cut).sum()),
                     "duty_cycle_running": float((v > PRIMARY.zero_cut).mean()) if v.size else np.nan,
                     "mean_afr_running_tph": float(v.mean()) if v.size else np.nan,
                     "median_nonzero_tph": float(np.median(nz)) if nz.size else np.nan,
                     "p05_nonzero_tph": float(np.quantile(nz, .05)) if nz.size else np.nan,
                     "p95_nonzero_tph": float(np.quantile(nz, .95)) if nz.size else np.nan,
                     "max_tph": float(v.max()) if v.size else np.nan,
                     "max_sustained_1h_tph": float(np.nanmax(fb.level_1h)) if np.isfinite(fb.level_1h).any() else np.nan,
                     "zero_to_nonzero_switches": int((sw & (on == 1.0)).sum()),
                     "nonzero_to_zero_switches": int((sw & (on == 0.0)).sum()),
                     "on_runs": n_on, "on_run_median_min": on_med, "on_run_p90_min": on_p90,
                     "off_runs": n_off, "off_run_median_min": off_med, "off_run_p90_min": off_p90,
                     "ramp_1h_abs_median_tph": float(np.median(np.abs(ramp))) if ramp.size else np.nan,
                     "ramp_1h_p05_tph": float(np.quantile(ramp, .05)) if ramp.size else np.nan,
                     "ramp_1h_p95_tph": float(np.quantile(ramp, .95)) if ramp.size else np.nan,
                     "minute_steps_ge_3tph": int((step[mm.index][mm.state.eq("RUNNING")] >= 3).sum()),
                     "median_feed_running_tph": float(np.nanmedian(fb.feed)) if np.isfinite(fb.feed).any() else np.nan})
    out = pd.DataFrame(rows)
    out["label"] = DESC
    return out


def main():
    cfg = PRIMARY
    f = bucket_frame(cfg)
    bands = fit_bands(f.afr[f.window.eq("DISCOVERY")].to_numpy(), cfg)
    (CACHE / "bands.json").write_text(json.dumps(bands, indent=1, sort_keys=True))
    band = assign_band(f.afr.to_numpy(), bands)
    lower = {"NO_AFR": 0.0, "LOW_AFR": bands["zero_cut"], "MEDIUM_AFR": bands["q_lo"], "HIGH_AFR": bands["q_hi"]}
    upper = {"NO_AFR": bands["zero_cut"], "LOW_AFR": bands["q_lo"], "MEDIUM_AFR": bands["q_hi"], "HIGH_AFR": np.inf}
    rule = {"NO_AFR": "0 <= AFR <= zero_cut (0.5 TPH; data are integer-valued)",
            "LOW_AFR": "zero_cut < AFR <= discovery non-zero P25", "MEDIUM_AFR": "P25 < AFR <= P75",
            "HIGH_AFR": "AFR > discovery non-zero P75"}
    rows = []
    for bn in BANDS:
        r = {"band": bn, "lower_tph": lower[bn], "upper_tph": upper[bn], "rule": rule[bn],
             "fitted_on": "DISCOVERY 2025-04-01..2025-05-31, RUNNING 10-min buckets, AFR_P2 non-zero",
             "n_fit_nonzero_buckets": bands["n_fit"], "label": BAND_LABEL,
             "not_a": "plant operating limit / target / set-point"}
        for w in ("DISCOVERY", "JUN", "JUL", "AUG"):
            sel = f.window.eq(w).to_numpy() & np.isfinite(f.afr.to_numpy())
            r[f"occupancy_{w.lower()}"] = float((band[sel] == bn).mean()) if sel.any() else np.nan
            r[f"median_feed_{w.lower()}_tph"] = float(np.nanmedian(f.feed[sel & (band == bn)])) \
                if (sel & (band == bn)).any() else np.nan
        rows.append(r)
    write_csv(pd.DataFrame(rows), "afr_operating_bands.csv", lg)

    m = pd.read_parquet(CACHE / "minute_afr.parquet")
    m = m[m.index <= pd.Timestamp("2025-08-31 23:59")]                 # Kiln-I has no September workbook
    f = f[f.index <= pd.Timestamp("2025-08-31 23:59:59")]
    # bucket labelled t covers (t-10 min, t]: assign it to the day / month of its last minute
    bday = (f.index - pd.Timedelta(minutes=1)).normalize().to_numpy()
    days = np.unique(m.index.normalize().to_numpy())
    daily = summarise(f, m, bday, m.index.normalize().to_numpy(), days)
    daily["period"] = pd.to_datetime(daily.period).dt.strftime("%Y-%m-%d")
    write_csv(daily.rename(columns={"period": "date"}), "afr_daily_summary.csv", lg)
    bmon = (f.index - pd.Timedelta(minutes=1)).month.to_numpy()
    monthly = summarise(f, m, bmon, m.index.month.to_numpy(), range(4, 9))
    monthly["period"] = monthly.period.map(lambda s: f"2025-{int(s):02d}")
    write_csv(monthly.rename(columns={"period": "month"}), "afr_monthly_summary.csv", lg)
    lg.info("bands: zero_cut %.1f, P25 %.1f, P75 %.1f (n=%d)", bands["zero_cut"], bands["q_lo"], bands["q_hi"], bands["n_fit"])


if __name__ == "__main__":
    main()
