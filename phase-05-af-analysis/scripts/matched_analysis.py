"""Step - Matched-control comparison of AFR states under comparable load (or MATCHING_NOT_SUPPORTED).

Reads  cache/buckets.parquet, cache/kpi_grid.parquet, cache/bands.json
Writes outputs/afr_matched_analysis.csv

Units: steady RUNNING buckets thinned to one per hour (top of the hour). Comparisons
  ON_VS_OFF     AFR on (every bucket of the last hour on) vs AFR off (every bucket of the last hour NO_AFR)
  HIGH_VS_LOW   last hour entirely HIGH_AFR vs entirely LOW_AFR (both on)
Matching: exact on window (DISCOVERY / JUN / JUL / AUG), discovery feed quintile and discovery kiln-speed tercile; calipers
|feed level difference| <= 2 TPH and |time difference| <= 72 h (limits drift); greedy 1:1 without replacement, nearest in
time first (af_core.match_pairs). Coal / PC firing are NOT matched in the primary design (they are co-manipulated with
AFR, so matching on them would condition on a consequence of the same operator decision); sensitivity C adds them.
Balance gate: >= 30 pairs, >= 5 distinct days and |SMD| < 0.1 on feed level and kiln speed; otherwise the row is
MATCHING_NOT_SUPPORTED with the reason. Effect: median paired difference (treated - control), day-block bootstrap CI.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from af_context import L, load_context, seed_of, tag_meta, target_series, window_span
from af_core import BANDS, CACHE, FAMILIES, FEED_TAG, PRIMARY, assign_band, block_ids, boot_median, log, match_pairs, \
    smd, write_csv

lg = log("matched_analysis")
SPEED = "Kiln-I!O"
WINDOWS = {"POOLED_APR_JUL": ("DISCOVERY", "JUN", "JUL"), "HOLDOUT_AUG": ("AUG",)}
TARGET_FAMILIES = ("LOAD", "FUEL_CO_MANIPULATION", "COMBUSTION", "THERMAL", "EFFICIENCY")


def whole_last_hour(cond: np.ndarray) -> np.ndarray:
    """True at t when cond holds for every bucket in (t-60 min, t] (past only)."""
    return ic_trailing_all(cond, 6)


def ic_trailing_all(cond: np.ndarray, n: int) -> np.ndarray:
    c = np.concatenate([[0], np.cumsum(cond.astype(int))])
    i = np.arange(1, len(cond) + 1)
    return (i >= n) & (c[i] - c[np.maximum(i - n, 0)] == n)


def matched(cfg=PRIMARY, match_fuel: bool = False, zero_cut: float | None = None) -> pd.DataFrame:
    ctx = load_context(cfg)
    meta = tag_meta()
    bands = json.loads((CACHE / "bands.json").read_text())
    if zero_cut is not None:
        bands = {**bands, "zero_cut": zero_cut}
    band = assign_band(ctx.afr, bands)
    feed_l = L(target_series(ctx, FEED_TAG))
    speed_l = L(target_series(ctx, SPEED))
    disc = window_span(ctx, "DISCOVERY") & ctx.running
    fq = np.quantile(feed_l[disc & np.isfinite(feed_l)], [0.2, 0.4, 0.6, 0.8])
    sq = np.quantile(speed_l[disc & np.isfinite(speed_l)], [1 / 3, 2 / 3])
    on_all, off_all = whole_last_hour(np.isin(band, BANDS[1:])), whole_last_hour(band == "NO_AFR")
    hi_all, lo_all = whole_last_hour(band == "HIGH_AFR"), whole_last_hour(band == "LOW_AFR")
    hourly = (ctx.index.minute == 0) & ctx.running & ctx.filt & np.isfinite(feed_l) & np.isfinite(speed_l)
    strata = (pd.Series(ctx.window).astype(str) + "|" + pd.Series(np.searchsorted(fq, feed_l)).astype(str) + "|"
              + pd.Series(np.searchsorted(sq, speed_l)).astype(str))
    if match_fuel:          # sensitivity C: also stratify on coal-kiln and PC-coal discovery terciles
        for t in ("Kiln-I!H", "Kiln-I!I"):
            v = L(target_series(ctx, t))
            q = np.quantile(v[disc & np.isfinite(v)], [1 / 3, 2 / 3])
            strata = strata + "|" + pd.Series(np.where(np.isfinite(v), np.searchsorted(q, v), -1)).astype(str)
    strata = strata.to_numpy()
    hours = ctx.t_min / 60.0
    tags = [t for f in TARGET_FAMILIES for t in FAMILIES[f]]
    days = block_ids(ctx.index, 1)
    rows = []
    for comp, treat, ctrl in (("ON_VS_OFF", on_all, off_all), ("HIGH_VS_LOW", hi_all, lo_all)):
        for wn, members in WINDOWS.items():
            inw = np.isin(ctx.window, members) & hourly
            pairs = match_pairs(np.flatnonzero(inw & treat), np.flatnonzero(inw & ctrl), strata, feed_l, hours, cfg)
            t_i = np.array([p[0] for p in pairs], dtype=int)
            c_i = np.array([p[1] for p in pairs], dtype=int)
            n_days = int(np.unique(days[t_i]).size)
            bal = {k: (smd(v[t_i], v[c_i]) if t_i.size else np.nan)
                   for k, v in (("smd_feed", feed_l), ("smd_speed", speed_l), ("smd_time_h", hours))}
            reason = []
            if t_i.size < cfg.match_min_pairs:
                reason.append(f"{t_i.size} pairs < {cfg.match_min_pairs}")
            if n_days < cfg.match_min_days:
                reason.append(f"{n_days} days < {cfg.match_min_days}")
            for k in ("smd_feed", "smd_speed"):
                if np.isfinite(bal[k]) and abs(bal[k]) >= cfg.match_smd_max:
                    reason.append(f"|{k}| {abs(bal[k]):.2f} >= {cfg.match_smd_max}")
            status = "MATCHED" if not reason else "MATCHING_NOT_SUPPORTED"
            n_t, n_c = int((inw & treat).sum()), int((inw & ctrl).sum())
            for tag in tags:
                y = target_series(ctx, tag)
                ok = np.isfinite(y[t_i]) & np.isfinite(y[c_i])
                dif = y[t_i][ok] - y[c_i][ok]
                good = status == "MATCHED" and dif.size >= 10
                med = float(np.median(dif)) if good else np.nan
                lo, hi = boot_median(dif, days[t_i][ok], cfg.n_boot, seed_of(cfg.seed, comp, wn, tag)) if good \
                    else (np.nan, np.nan)
                ci = np.isfinite(lo) and lo * hi > 0
                m = meta.loc[tag] if tag in meta.index else None
                if good:
                    txt = (f"OBSERVED ({comp}, {wn}): median matched difference {med:+.3g} (95 % day-block CI "
                           f"{'excludes' if ci else 'includes'} 0). Comparable-load comparison; operator co-intervention "
                           "and fuel properties are unmatched. AFR-associated, not AFR-caused.")
                elif status != "MATCHED":
                    txt = f"MATCHING_NOT_SUPPORTED: {'; '.join(reason)}"
                else:
                    txt = "INSUFFICIENT DATA: < 10 matched pairs with this target present"
                rows.append({"afr_signal": "Kiln-I!K", "comparison": comp, "target_signal": tag,
                             "target_original_name": m.original_name if m is not None else tag,
                             "target_unit": m.unit if m is not None else "",
                             "target_family": next(f for f in TARGET_FAMILIES if tag in FAMILIES[f]), "window": wn,
                             "matching_status": status, "not_supported_reason": "; ".join(reason),
                             "treated_candidates": n_t, "control_candidates": n_c, "sample_count": int(dif.size),
                             "matched_pairs": int(t_i.size), "effective_sample_size": n_days, **bal,
                             "effect_size": med, "effect_metric": "median paired difference treated - control (target units)",
                             "confidence_interval_low": lo, "confidence_interval_high": hi,
                             "direction": ("POSITIVE" if med > 0 else "NEGATIVE") if np.isfinite(med) and med != 0 else "",
                             "evidence": "OBSERVED" if good else ("NOT COMPUTABLE" if status != "MATCHED"
                                                                  else "INSUFFICIENT DATA"),
                             "match_on": "window, feed quintile, kiln-speed tercile, |dfeed|<=2 TPH, |dt|<=72 h"
                                         + (", coal / PC terciles" if match_fuel else ""),
                             "interpretation": txt})
            lg.info("%s %s: %d treated, %d control candidates, %d pairs, %s %s", comp, wn, n_t, n_c, t_i.size, status,
                    "; ".join(reason))
    return pd.DataFrame(rows)


def main():
    write_csv(matched(), "afr_matched_analysis.csv", lg)


if __name__ == "__main__":
    main()
