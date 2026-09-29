"""Ordinary-running control anchors (spec section 5).

A bucket is CLEAN when it lies outside every Phase 6 candidate extent [onset, end + 6 h] (all candidates, including
ordinary-context ones: they are KPI >= P90 abnormal-like) and outside the 24 h before every final onset. A control
anchor A is ELIGIBLE for horizon h when A is operational, every bucket of (A - h, A] is clean and outside the Phase 1
long-gap / frozen windows, and >= 2/3 of the window is operational. Controls are never built from contaminated time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p8common import CFG, P8Config, ic, min_valid, nb


def overlaps(ix: pd.DatetimeIndex, start, end) -> np.ndarray:
    """Bucket (t - 10 min, t] overlaps [start, end]."""
    return (ix > start) & (ix - pd.Timedelta(minutes=10) < end)


def candidate_free(ix: pd.DatetimeIndex, eps: pd.DataFrame, cfg: P8Config = CFG) -> np.ndarray:
    """Outside every Phase 6 candidate extent [onset, end + 6 h]. A period's own extent never overlaps its own
    pre-onset window (the bucket ending at T0 = onset does not overlap [onset, ...]), so the same mask keeps EVENT
    windows free of OTHER abnormal-like periods (symmetry with the controls)."""
    bad = np.zeros(len(ix), bool)
    for r in eps.itertuples():
        bad |= overlaps(ix, r.onset_time, r.end_time + pd.Timedelta(hours=cfg.ctrl_post_end_h))
    return ~bad


def clean_mask(ix: pd.DatetimeIndex, eps: pd.DataFrame, events: pd.DataFrame, cfg: P8Config = CFG) -> np.ndarray:
    bad = ~candidate_free(ix, eps, cfg)
    for r in events.itertuples():
        bad |= overlaps(ix, r.T0 - pd.Timedelta(hours=cfg.ctrl_pre_onset_h), r.T0)
    return ~bad


def final_only_clean(ix: pd.DatetimeIndex, events: pd.DataFrame, cfg: P8Config = CFG) -> np.ndarray:
    """Sensitivity: exclude only the final periods [T0, end + 6 h] and their 24-h pre-onset zones (not the other
    KPI >= P90 candidates, whose exclusion selects the low-KPI part of running as controls)."""
    bad = np.zeros(len(ix), bool)
    for r in events.itertuples():
        bad |= overlaps(ix, r.T0 - pd.Timedelta(hours=cfg.ctrl_pre_onset_h),
                        r.event_end + pd.Timedelta(hours=cfg.ctrl_post_end_h))
    return ~bad


def event_dq_rule(s: pd.DataFrame, minutes: int) -> np.ndarray:
    """The event data-quality exclusion rule applied to any window (A - minutes, A]: POOR share <= 0.5 and no
    STOPPED / TRANSITION_CONTEXT bucket."""
    n = nb(minutes)
    poor = ic.trailing_mean(s.data_quality_status.eq("POOR").to_numpy(float), n, n)
    stop = s.risk_status.isin(["STOPPED", "TRANSITION_CONTEXT"]).to_numpy()
    return (np.nan_to_num(poor, nan=1.0) <= 0.5) & all_in_window(~stop, n)


def all_in_window(flag: np.ndarray, n: int) -> np.ndarray:
    return ic.trailing_mean(np.asarray(flag, float), n, n) == 1.0


def eligible(clean: np.ndarray, oper: np.ndarray, dq: np.ndarray, minutes: int) -> np.ndarray:
    n = nb(minutes)
    cnt = ic.trailing_mean(oper.astype(float), n, n) * n
    return oper & all_in_window(clean, n) & all_in_window(~dq, n) & (np.nan_to_num(cnt) >= min_valid(n))


def eligibility(clean: np.ndarray, oper: np.ndarray, dq: np.ndarray, cfg: P8Config = CFG) -> dict[int, np.ndarray]:
    return {h: eligible(clean, oper, dq, h) for h in sorted(set(cfg.horizons) | set(cfg.offsets) - {0})} | \
        {0: oper & clean & ~dq}


def load_stratum(s: pd.DataFrame) -> np.ndarray:
    return (s.load_band.fillna("UNKNOWN") + "|" + s.load_context.fillna("UNKNOWN")).to_numpy(object)


def settling(s: pd.DataFrame) -> np.ndarray:
    return s.secondary_reasons.fillna("").str.contains("POST_RESTART_SETTLING").to_numpy(bool)


def block_ids(ix: pd.DatetimeIndex, hours: int) -> np.ndarray:
    """Calendar blocks of `hours` from the grid start (blocks of 3/6/12/24 h never straddle a month boundary)."""
    return np.floor((ix - ix[0].normalize()) / pd.Timedelta(hours=hours)).astype(int).to_numpy()
