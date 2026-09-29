"""Pure, causal warning-signal functions: reference rank, slope, acceleration, rolling rank, W1-W5 flags, episodes.

Every value at bucket t uses buckets <= t only (trailing windows on the regular 10-min grid). No file I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p8common import CFG, P8Config, ic, min_valid, nb


def ecdf(ref_sorted: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Share of the frozen reference values <= x (right-continuous ECDF); NaN stays NaN."""
    x = np.asarray(x, float)
    r = np.searchsorted(ref_sorted, np.where(np.isfinite(x), x, 0.0), side="right") / max(len(ref_sorted), 1)
    return np.where(np.isfinite(x), r, np.nan)


def slope(score: np.ndarray, n: int = CFG.slope_buckets, min_valid: int = CFG.slope_min_valid) -> np.ndarray:
    """OLS slope (points per hour) of the score over the trailing n buckets [t - (n-1)*10 min, t]; NaN if < min_valid."""
    y = ic.trailing_stack(np.asarray(score, float), n)            # column j = value at t - j
    x = -np.arange(n) / 6.0                                        # hours relative to t
    m = np.isfinite(y)
    k = m.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        xm = (m * x).sum(axis=1) / k
        ym = np.where(m, y, 0.0).sum(axis=1) / k
        dx = np.where(m, x[None, :] - xm[:, None], 0.0)
        b = (dx * np.where(m, y - ym[:, None], 0.0)).sum(axis=1) / (dx ** 2).sum(axis=1)
    return np.where(k >= min_valid, b, np.nan)


def accel(sl: np.ndarray, lag: int = CFG.accel_lag) -> np.ndarray:
    return np.asarray(sl, float) - ic.lagged(np.asarray(sl, float), lag)


def rolling_rank(score: np.ndarray, cfg: P8Config = CFG) -> np.ndarray:
    """Reference-free percentile of score(t) among finite scores in (t - roll_days, t - roll_exclude_h] (mid-rank ties).
    Removes slow level drift (month effects) without any frozen reference."""
    s = np.asarray(score, float)
    lo_n, hi_n = cfg.roll_days * 144, cfg.roll_exclude_h * 6
    out = np.full(len(s), np.nan)
    for i in np.flatnonzero(np.isfinite(s)):
        w = s[max(0, i - lo_n + 1):max(0, i - hi_n + 1)]
        w = w[np.isfinite(w)]
        if w.size >= cfg.roll_min:
            out[i] = (np.sum(w < s[i]) + 0.5 * np.sum(w == s[i])) / w.size
    return out


def window_stat(x: np.ndarray, minutes: int) -> np.ndarray:
    """Median of x over (t - minutes, t] with >= 2/3 of the buckets finite (the Phase 7 4-of-6 rule)."""
    n = nb(minutes)
    return ic.trailing_median(np.asarray(x, float), n, min_valid(n))


def any_in_window(flag: np.ndarray, minutes: int) -> np.ndarray:
    """True if any bucket in (t - minutes, t] is flagged."""
    return ic.trailing_mean(np.asarray(flag, float), nb(minutes), 1) > 0


def signals_from(score: np.ndarray, thr: dict, fam_abn: np.ndarray, cfg: P8Config = CFG, roll: bool = False) -> dict:
    """The per-bucket signal bundle of one score series (the single construction used by the pipeline, NC5 and L1)."""
    sl = slope(score, cfg.slope_buckets, cfg.slope_min_valid)
    sig = {"score": score, "rank": ecdf(thr["ref_sorted"], score), "slope": sl, "accel": accel(sl, cfg.accel_lag),
           "thr": thr}
    if roll:
        sig["rank_roll"] = rolling_rank(score, cfg)
    sig["flags"] = warning_flags(sig, fam_abn, thr, cfg)
    return sig


# ============================================================================== warnings
def warning_flags(sig: dict, fam_abn: np.ndarray, thr: dict, cfg: P8Config = CFG) -> dict[str, np.ndarray]:
    """W1-W5 per bucket (False where the score is not operational). thr = frozen thresholds (calibration.py)."""
    rank, sl, ac_ = sig["rank"], sig["slope"], sig["accel"]
    ok = np.isfinite(sig["score"])
    fin = lambda a, t: np.where(np.isfinite(a), a >= t, False)     # noqa: E731
    elevated = fin(rank, cfg.w3_rank) & ok
    return {"W1_RANK": fin(rank, cfg.w1_rank) & ok,
            "W2_RISING": fin(sl, thr["slope"]) & ok,
            "W3_PERSISTENT": ic.run_lengths(elevated) >= cfg.w3_min_buckets,
            "W4_ACCEL": fin(ac_, thr["accel"]) & ok,
            "W5_MULTI_FAMILY": (np.nan_to_num(fam_abn) >= cfg.w5_families) & fin(sl, 1e-12) & ok}


def episodes(flag: np.ndarray, oper: np.ndarray, gap_tol: int = CFG.gap_tol_buckets) -> list[tuple[int, int]]:
    """Inclusive (start, end) positions of warning episodes. Flagged buckets merge across <= gap_tol non-flagged
    buckets only if every gap bucket is operational (a stop / gap breaks the episode)."""
    idx = np.flatnonzero(np.asarray(flag, bool))
    out: list[list[int]] = []
    for i in idx:
        if out:
            pe = out[-1][1]
            gap = i - pe - 1
            if gap == 0 or (gap <= gap_tol and oper[pe + 1:i].all()):
                out[-1][1] = i
                continue
        out.append([i, i])
    return [tuple(e) for e in out]


def episode_table(name: str, eps: list[tuple[int, int]], ix: pd.DatetimeIndex, s: pd.DataFrame, sig: dict,
                  clean: np.ndarray) -> pd.DataFrame:
    """One row per warning episode with its provenance (score, slope, families, confidence, state, load, DQ)."""
    rows = []
    for a, b in eps:
        seg = slice(a, b + 1)
        sc = sig["score"][seg]
        fams = sorted({f for v in s.contributing_families.iloc[seg] for f in str(v).split(";") if f and f != "NONE"})
        mode = lambda c: s[c].iloc[seg].mode().iat[0] if s[c].iloc[seg].notna().any() else ""   # noqa: E731
        rows.append({"warning_type": name, "start": ix[a] - pd.Timedelta(minutes=10), "end": ix[b],
                     "duration_minutes": (b - a + 1) * 10, "max_score": float(np.nanmax(sc)),
                     "median_score": float(np.nanmedian(sc)), "slope_at_start": float(sig["slope"][a]),
                     "contributing_families": ";".join(fams) or "NONE",
                     "median_confidence": float(np.nanmedian(s.confidence_score.to_numpy(float)[seg])),
                     "operating_state": mode("risk_status"), "load_context": mode("load_context"),
                     "data_quality_status": mode("data_quality_status"), "month": int(ix[a].month),
                     "ordinary_running": bool(clean[a])})
    return pd.DataFrame(rows)
