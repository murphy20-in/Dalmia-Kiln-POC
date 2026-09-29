"""Per-period lead-time metrics over the look-back (T0 - 24 h, T0] (spec section 8). Uses buckets <= T0 only.

first_warning     earliest warning bucket in the look-back          lead = T0 - its bucket end
sustained_warning start of the warning episode in force at T0 (ends >= T0 - gap tolerance)
peak_pre_event    bucket of the maximum score in the look-back
trend_onset       start of the final run of positive 60-min slope ending at T0
warning_duration  warning minutes in the look-back (persistence)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warning_metrics as wm
from p8common import CFG, P8Config, ic, nb


def minutes_before(p0: int, p: int) -> float:
    return float(10 * (p0 - p))


def event_lead(flag: np.ndarray, sig: dict, oper: np.ndarray, p0: int, cfg: P8Config = CFG) -> dict:
    lo = max(0, p0 - nb(cfg.lookback_min) + 1)
    seg = np.asarray(flag[lo:p0 + 1], bool)
    out = {"warning_detected": bool(seg.any()), "first_warning_pos": np.nan, "lead_time_minutes": np.nan,
           "sustained_lead_minutes": np.nan, "warning_duration_minutes": float(10 * seg.sum()),
           "warning_in_force_at_T0": False}
    if seg.any():
        first = lo + int(np.flatnonzero(seg)[0])
        out["first_warning_pos"], out["lead_time_minutes"] = first, minutes_before(p0, first)
        eps = wm.episodes(seg, oper[lo:p0 + 1], cfg.gap_tol_buckets)
        a, b = eps[-1]
        if lo + b >= p0 - cfg.gap_tol_buckets:
            out["warning_in_force_at_T0"] = True
            out["sustained_lead_minutes"] = minutes_before(p0, lo + a)
    sc = sig["score"][lo:p0 + 1]
    if np.isfinite(sc).any():
        pk = lo + int(np.nanargmax(sc))
        out.update(peak_pre_event_score=float(sig["score"][pk]), peak_pre_event_rank=float(sig["rank"][pk]),
                   peak_lead_minutes=minutes_before(p0, pk))
    else:
        out.update(peak_pre_event_score=np.nan, peak_pre_event_rank=np.nan, peak_lead_minutes=np.nan)
    sl = sig["slope"][lo:p0 + 1]
    pos = np.where(np.isfinite(sl), sl > 0, False)
    out["trend_onset_lead_minutes"] = (minutes_before(p0, lo + len(pos) - int(ic.run_lengths(pos)[-1]))
                                       if pos[-1] else np.nan)
    return out


def event_table(B: dict, sigs: dict, primary_res: dict, o2_res: dict | None, cfg: P8Config = CFG) -> pd.DataFrame:
    """early_warning_event_validation: one row per period x warning definition (severity / Phase 6 confidence are
    context metadata, never a target)."""
    P = sigs["PRIMARY"]
    s, ix = B["s"], B["ix"]
    n = nb(cfg.primary_h)
    rows = []
    for i, e in enumerate(B["events"].itertuples()):
        p0 = e.pos_T0
        seg = slice(p0 - n + 1, p0 + 1)
        r6 = p0 - nb(360)
        base = {"event_id": e.event_id, "T0_onset": e.T0, "event_start": e.event_start, "event_end": e.event_end,
                "month": e.month, "severity": e.severity, "phase6_confidence": e.phase6_confidence,
                "onset_censored": e.onset_censored, "evaluable": bool(primary_res["ok"][i]),
                "data_quality_status": e.data_quality_status, "data_quality_reason": e.data_quality_reason,
                "data_quality_status_o2x": e.data_quality_status_o2x,
                "pre_event_median_score": float(np.nanmedian(P["score"][seg])) if np.isfinite(P["score"][seg]).any()
                else np.nan,
                "pre_event_window_rank": primary_res["event_value"][i], "pre_event_rank_excess": primary_res["excess"][i],
                "control_percentile": primary_res["control_pct"][i],
                "pre_event_rank_change": float(P["rank"][p0] - P["rank"][r6]) if r6 >= 0 else np.nan,
                "family_count": float(s.family_count_abnormal.iat[p0]),
                "confidence": float(np.nanmedian(s.confidence_score.to_numpy(float)[seg])),
                "load_context": s.load_context.iat[p0], "load_band": s.load_band.iat[p0],
                "load_associated_share": float(s.load_context.iloc[seg].eq("LOAD_ASSOCIATED").mean()),
                "o2_excluded_result": o2_res["excess"][i] if o2_res is not None else np.nan}
        for w in P["flags"]:
            L = event_lead(P["flags"][w], P, B["oper"], p0, cfg)
            fp = L.pop("first_warning_pos")
            rows.append({**base, "warning_type": w, **L,
                         "first_warning_time": ix[int(fp)] if np.isfinite(fp) else pd.NaT})
    cols = ["event_id", "T0_onset", "event_start", "event_end", "month", "severity", "phase6_confidence", "evaluable",
            "warning_detected", "warning_type", "first_warning_time", "lead_time_minutes", "sustained_lead_minutes",
            "warning_in_force_at_T0", "peak_pre_event_score", "peak_pre_event_rank", "peak_lead_minutes",
            "trend_onset_lead_minutes", "pre_event_median_score", "pre_event_window_rank", "pre_event_rank_excess",
            "control_percentile", "pre_event_rank_change", "warning_duration_minutes", "family_count", "confidence",
            "load_context", "load_band", "load_associated_share", "o2_excluded_result", "onset_censored",
            "data_quality_status", "data_quality_reason", "data_quality_status_o2x"]
    return pd.DataFrame(rows)[cols]


def lead_summary(ev_table: pd.DataFrame) -> pd.DataFrame:
    """Median / P25 / P75 / min / max of every lead metric per warning over evaluable periods with a warning."""
    rows = []
    for w, g in ev_table[ev_table.evaluable].groupby("warning_type", sort=True):
        for m in ("lead_time_minutes", "sustained_lead_minutes", "peak_lead_minutes", "trend_onset_lead_minutes",
                  "warning_duration_minutes"):
            v = g[m].dropna().to_numpy(float)
            rows.append({"section": "LEAD_TIME", "warning_type": w, "metric": m, "n": int(v.size),
                         "n_evaluable": len(g), "median": np.median(v) if v.size else np.nan,
                         "p25": np.quantile(v, .25) if v.size else np.nan,
                         "p75": np.quantile(v, .75) if v.size else np.nan,
                         "min": v.min() if v.size else np.nan, "max": v.max() if v.size else np.nan})
    return pd.DataFrame(rows)
