"""Warning-threshold discipline. Every threshold is frozen BEFORE evaluation and never uses the evaluated periods.

  REF_APR_MAY           the frozen Apr-May in-sample reference population of the Phase 7 score (primary source)
  PRIOR_MONTH_CONTROLS  month holdout: ordinary-running controls of earlier months only (Jun -> Jul/Aug, Jun+Jul -> Aug)
  LOEO_EVENT_TUNED      held-out diagnostic: P25 of the OTHER events' pre-onset statistic (never deployable)
"""
from __future__ import annotations

import numpy as np

import warning_metrics as wm
from p8common import CFG, P8Config

REF_QUANTILES = (0.50, 0.75, 0.90, 0.95, 0.99)


def reference_thresholds(ref_series: np.ndarray, cfg: P8Config = CFG) -> dict:
    """Rank reference (sorted Apr-May scores) and the P95 of the Apr-May slope / acceleration distributions."""
    ref = np.sort(ref_series[np.isfinite(ref_series)])
    if ref.size < 1000:
        raise RuntimeError(f"reference population too small ({ref.size}) - THRESHOLD_VALIDATION_INSUFFICIENT")
    sl = wm.slope(ref_series, cfg.slope_buckets, cfg.slope_min_valid)
    acc = wm.accel(sl, cfg.accel_lag)
    return {"source": "REF_APR_MAY", "ref_sorted": ref, "n_ref": int(ref.size),
            "ref_quantiles": {f"p{int(q * 100)}": float(np.quantile(ref, q)) for q in REF_QUANTILES},
            "w1_score_edge": float(np.quantile(ref, cfg.w1_rank)), "w3_score_edge": float(np.quantile(ref, cfg.w3_rank)),
            "slope": float(np.nanquantile(sl, cfg.calib_q)), "accel": float(np.nanquantile(acc, cfg.calib_q)),
            "n_slope": int(np.isfinite(sl).sum())}


def prior_month_thresholds(sig: dict, ordinary: np.ndarray, month: np.ndarray, train_months: tuple,
                           cfg: P8Config = CFG) -> dict:
    """P95 of slope / acceleration over ordinary-running buckets of `train_months` only (month holdout)."""
    m = ordinary & np.isin(month, train_months)
    sl, acc = sig["slope"][m], sig["accel"][m]
    if np.isfinite(sl).sum() < 1000:
        return {"source": f"PRIOR_MONTH_CONTROLS{train_months}", "status": "THRESHOLD_VALIDATION_INSUFFICIENT"}
    return {"source": f"PRIOR_MONTH_CONTROLS{train_months}", "status": "OK",
            "slope": float(np.nanquantile(sl, cfg.calib_q)), "accel": float(np.nanquantile(acc, cfg.calib_q)),
            "n": int(np.isfinite(sl).sum()), "max_train_month": int(max(train_months))}


def loeo_thresholds(values: np.ndarray, q: float = CFG.loeo_q) -> np.ndarray:
    """For each event i: the q-quantile of the other events' finite values (the target never enters its threshold)."""
    v = np.asarray(values, float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        o = np.delete(v, i)
        o = o[np.isfinite(o)]
        if o.size >= 3:
            out[i] = float(np.quantile(o, q))
    return out
