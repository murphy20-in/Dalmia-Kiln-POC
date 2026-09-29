"""Negative controls NC1-NC5 on the primary endpoint (spec section 11).

NC1 circular shift of the window statistic (>= 7 days)   expected: effect degrades toward 0
NC2 month-stratified random pseudo-onsets                 expected: null centred on 0 (it is the primary p-value)
NC3 backward: the window just AFTER the period end        diagnostic: persistence of the trailing-window score
NC4 mirrored-position relocation (reversed series)       reported single draw; not a gate criterion
NC5 randomise everything after T0                         expected: every pre-T0 metric identical
A null is 'DEGRADES_TO_NULL' when its median |effect| <= NULL_TOL (0.05 rank units); separately the observed effect is
compared with the null (one-sided p).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import lead_time
import temporal_validation as tv
import warning_metrics as wm
from p8common import CFG, P8Config, nb

NULL_TOL = 0.05


def _row(cid, method, h, obs, null, p=None, status=None) -> dict:
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    p = p if p is not None else (float((1 + np.sum(null >= obs)) / (1 + null.size)) if null.size else np.nan)
    nm = float(np.median(null)) if null.size else np.nan
    if status is None:
        status = ("DEGRADES_TO_NULL" if abs(nm) <= NULL_TOL else "NULL_NOT_CENTRED") + \
            ("; OBSERVED_EXCEEDS_NULL" if p < 0.05 else "; OBSERVED_NOT_DISTINGUISHABLE_FROM_NULL")
    return {"control_id": cid, "method": method, "horizon_minutes": h, "observed_effect": obs, "null_effect": nm,
            "p_value": p, "empirical_null_rate": float(np.mean(null >= obs)) if null.size else np.nan,
            "n_null": int(null.size), "status": status}


def nc1_circular(x: np.ndarray, B: dict, cfg: P8Config = CFG, h: int = CFG.primary_h) -> np.ndarray:
    """Shift within the OPERATIONAL subsequence (Phase 7 NC1 convention): keeps every anchor populated, preserves the
    marginal distribution and autocorrelation, breaks the alignment with the onsets."""
    W = wm.window_stat(x, h)
    op = np.flatnonzero(B["oper"])
    k_min = cfg.min_shift_days * 144
    rng = np.random.default_rng(tv.seed_of(f"NC1|{h}", cfg))
    out = []
    for k in rng.integers(k_min, op.size - k_min, cfg.n_null // 4):
        Wk = np.full(len(W), np.nan)
        Wk[op] = np.roll(W[op], int(k))
        out.append(tv.endpoint(x, B, h, "NC1", cfg, W=Wk, boot=False, null=False)["pe"])
    return np.array(out)


def nc4_mirrored(x: np.ndarray, B: dict, cfg: P8Config = CFG, h: int = CFG.primary_h) -> float:
    """Window statistic of the reversed series read at the fixed anchors: each anchor p gets the value of the
    mirrored position N-1-p. One deterministic relocation, not a null distribution (NC1 is the shift null)."""
    return tv.endpoint(x, B, h, "NC4", cfg, W=wm.window_stat(np.asarray(x)[::-1], h), boot=False, null=False)["pe"]


def nc3_backward(x: np.ndarray, B: dict, cfg: P8Config = CFG, h: int = CFG.primary_h) -> dict:
    """Window (end, end + h] after each period (and (T0, T0 + h] inside it, for scale) vs the same controls. Windows
    are clipped at the grid end (count reported); they are not checked for other periods (diagnostic only)."""
    ev = B["events"].copy()
    last = len(B["ix"]) - 1
    ev["pos_post"] = np.minimum(ev.pos_end + nb(h), last)
    ev["pos_in"] = np.minimum(ev.pos_T0 + nb(h), last)
    B2 = {**B, "events": ev}
    return {"post_end": tv.endpoint(x, B2, h, "NC3post", cfg, anchor="pos_post", boot=False),
            "within": tv.endpoint(x, B2, h, "NC3in", cfg, anchor="pos_in", boot=False),
            "n_clipped": int((ev.pos_end + nb(h) > last).sum() + (ev.pos_T0 + nb(h) > last).sum())}


def pre_t0_metrics(sig: dict, B: dict, p0: int, cfg: P8Config = CFG) -> dict:
    """Every pre-T0 quantity Phase 8 reports for one period (window statistics at all horizons + lead metrics)."""
    m = {f"W{h}": wm.window_stat(sig["rank"], h)[p0] for h in cfg.horizons}
    for w, f in sig["flags"].items():
        m.update({f"{w}.{k}": v for k, v in lead_time.event_lead(f, sig, B["oper"], p0, cfg).items()})
    return m


def perturb_after(sig: dict, B: dict, p0: int, seed: int, cfg: P8Config = CFG) -> dict:
    """Signal bundle recomputed from a score whose values after p0 are randomly permuted and rescaled."""
    rng = np.random.default_rng(seed)
    sc = sig["score"].copy()
    tail = sc[p0 + 1:]
    sc[p0 + 1:] = rng.permutation(tail) * rng.uniform(0.2, 3.0)
    return wm.signals_from(sc, sig["thr"], B["s"].family_count_abnormal.to_numpy(float), cfg)


def nc5_future_perturbation(sig: dict, B: dict, cfg: P8Config = CFG) -> tuple[bool, list[str]]:
    bad = []
    for i, e in enumerate(B["events"].itertuples()):
        a = pre_t0_metrics(sig, B, e.pos_T0, cfg)
        b = pre_t0_metrics(perturb_after(sig, B, e.pos_T0, cfg.seed + i, cfg), B, e.pos_T0, cfg)
        diff = [k for k in a if not (a[k] == b[k] or (pd.isna(a[k]) and pd.isna(b[k])))]
        if diff:
            bad.append(f"{e.event_id}: {diff[:3]}")
    return not bad, bad


def run(sig: dict, B: dict, primary: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    x, h, obs = sig["rank"], cfg.primary_h, primary["pe"]
    rows = [_row("NC1", "circular shift of the 60-min window statistic by >= 7 days (events / controls fixed)", h, obs,
                 nc1_circular(x, B, cfg)),
            _row("NC2", "month-stratified random pseudo-onsets from eligible controls (the primary p-value)", h, obs,
                 primary["null"], p=primary["p_value"])]
    b = nc3_backward(x, B, cfg)
    post, within = b["post_end"]["pe"], b["within"]["pe"]
    rows.append({"control_id": "NC3", "method": "backward: window (end, end + 60 min] after each period vs controls "
                 f"(validation test, never a feature; {b['n_clipped']} windows clipped at the grid end; not checked "
                 "for other periods)", "horizon_minutes": h, "observed_effect": obs,
                 "null_effect": post, "p_value": b["post_end"]["p_value"], "empirical_null_rate": np.nan,
                 "n_null": b["post_end"]["n_evaluable"],
                 "status": ("DIAGNOSTIC: POST_END_ASSOCIATION_STRONGER_THAN_PRE_ONSET (trailing-window persistence)"
                            if post > obs else "DIAGNOSTIC: PRE_ONSET_ASSOCIATION_AT_LEAST_AS_STRONG_AS_POST_END")})
    rows.append({"control_id": "NC3b", "method": "scale reference: window (T0, T0 + 60 min] inside the period",
                 "horizon_minutes": h, "observed_effect": obs, "null_effect": within,
                 "p_value": b["within"]["p_value"], "empirical_null_rate": np.nan,
                 "n_null": b["within"]["n_evaluable"], "status": "DIAGNOSTIC: WITHIN_PERIOD_ELEVATION"})
    rev = nc4_mirrored(x, B, cfg)
    rows.append(_row("NC4", "mirrored-position relocation: reversed-series window statistic read at the fixed anchors "
                     "(one deterministic draw, not a null distribution; NC1 is the shift null)", h, obs, [rev],
                     p=float("nan"), status="REPORTED_SINGLE_DRAW: " + ("WITHIN_NULL_TOL" if abs(rev) <= NULL_TOL
                                                                       else "OUTSIDE_NULL_TOL")))
    ok, bad = nc5_future_perturbation(sig, B, cfg)
    rows.append({"control_id": "NC5", "method": "all values after each T0 permuted and rescaled; every pre-T0 metric "
                 "(8 window statistics, 5 x lead metrics) recomputed", "horizon_minutes": h, "observed_effect": obs,
                 "null_effect": np.nan, "p_value": np.nan, "empirical_null_rate": np.nan,
                 "n_null": len(B["events"]), "status": "PASS_IDENTICAL" if ok else f"FAIL {bad[:3]}"})
    return pd.DataFrame(rows)
