"""Pure Phase 7 scoring functions: family intensity, risk score, components, bands, status, confidence, reasons.

No file I/O. The same functions fit the reference (reference_builder), score every bucket (calibration), score the
robustness variants (robustness) and run the leakage gates (validation / tests), so there is a single code path.

Temporal rules: every value at bucket t uses buckets <= t only (trailing windows, trailing counts, events with time <= t,
DQ windows only after they have ended) and a reference frozen on the Apr-May window. Definitions: docs/RISK_SCORE_SPEC.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (BANDS, BELOW, CONF_CAP, CONFIDENCE_VARIANTS, FAMILIES, NO_DRIVER, PRIMARY, REASON_BY_FAMILY,
                    UNBANDED, P7Config, ic)
from feature_engineering import (after_window, hours_since_restart, invalid_share, load_change, masked_component,
                                 recent_event, run_minutes, running_mask, smooth, trailing_count_in_segment)

AFR_DOWN = ("AFR_STOP", "AFR_RAMP_DOWN")
AFR_KINDS = ("AFR_START", "AFR_STOP", "AFR_RAMP_UP", "AFR_RAMP_DOWN")
CONF_PARTS = ("conf_data_quality", "conf_family_coverage", "conf_baseline", "conf_operating_state", "conf_temporal",
              "conf_robustness")
LOAD_BANDS = ("TENTATIVE_LOW", "TENTATIVE_MID", "TENTATIVE_HIGH")
HIGH_RANK = BANDS.index("HIGH")
# Inputs of risk_score. G2 / tests require each to have a SCORING row with CAUSAL leakage status in the inventory.
SCORING_FEATURES = tuple(f"S_{d}" for d in FAMILIES) + tuple(f"a_{d}" for d in FAMILIES) + \
    ("H_magnitude", "C_concurrence", "P_persistence")
SCORING_GRID_COLUMNS = ("state",) + tuple(f"comp_{d}" for d in FAMILIES) + ("feed",)


# ============================================================================== family features and intensity
def family_S(grid: pd.DataFrame, cfg: P7Config) -> tuple[np.ndarray, np.ndarray]:
    """(S~ matrix n x families, RUNNING mask). S~ = trailing median of the RUNNING-masked Phase 3 component, defined
    only when the CURRENT bucket's component is valid: a gap bucket is never scored from stale pre-gap values."""
    run = running_mask(grid["state"])
    cols = []
    for d in cfg.families:
        x = masked_component(grid[f"comp_{d}"].to_numpy(float), run)
        cols.append(np.where(np.isfinite(x), smooth(x, cfg.window_buckets, cfg.window_min_valid), np.nan))
    return np.column_stack(cols), run


def intensity(S: np.ndarray, M: np.ndarray, Q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """e = max(0, S - m) / (q - m); a = 1 - 2^-e (= Phase 3 kpi_core.to_kpi / 100): 0 at the reference median, 0.5 at
    the reference P90, saturating towards 1. NaN S stays NaN."""
    with np.errstate(invalid="ignore"):
        e = np.maximum(0.0, S - M) / (Q - M)
    return e, 1.0 - np.power(2.0, -e)


def load_band_index(feed: np.ndarray, ref: dict) -> np.ndarray:
    """0 / 1 / 2 = TENTATIVE_LOW / MID / HIGH by the reference feed P33 / P67; -1 = unknown feed."""
    f = np.asarray(feed, float)
    idx = np.searchsorted([ref["load"]["feed_p33"], ref["load"]["feed_p67"]], f, side="right")
    return np.where(np.isfinite(f), idx, -1)


def anchor_arrays(ref: dict, n: int, band_idx: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Per-row frozen anchors (m, q). load_band variants use per-band anchors where the band is known."""
    fams = ref["families"]
    M = np.tile([ref["anchors"][d]["m"] for d in fams], (n, 1)).astype(float)
    Q = np.tile([ref["anchors"][d]["q"] for d in fams], (n, 1)).astype(float)
    for b, anc in (ref.get("anchors_by_band") or {}).items():
        rows = band_idx == int(b)
        M[rows] = [anc[d]["m"] for d in fams]
        Q[rows] = [anc[d]["q"] for d in fams]
    return M, Q


def magnitude(S: np.ndarray, M: np.ndarray, Q: np.ndarray, cfg: P7Config) -> dict:
    """Family intensities, abnormal flags, magnitude H, concurrence C and the per-family share of H.
    A missing family contributes 0 with the fixed denominator, so a missing family can never raise H or C (it biases
    the score DOWN - disclosed; confidence carries the reduced coverage)."""
    e, a = intensity(S, M, Q)
    usable = np.isfinite(S)
    af = np.where(usable, a, 0.0)
    with np.errstate(invalid="ignore"):
        abn = S > Q                                   # NaN compares False
    n_use, n_abn = usable.sum(axis=1), abn.sum(axis=1)
    F = S.shape[1]
    if cfg.denominator == "fixed":
        share = af / F
    elif cfg.denominator == "available":
        share = af / np.maximum(n_use, 1)[:, None]
    else:
        raise ValueError(f"unknown denominator {cfg.denominator}")
    top = af.argmax(axis=1)                      # ties -> first family in the fixed order (deterministic)
    if cfg.magnitude_mode == "hybrid":
        onehot = np.zeros_like(af)
        onehot[np.arange(len(af)), top] = 1.0
        part = 0.5 * onehot * af + 0.5 * share
    elif cfg.magnitude_mode == "mean":
        part = share
    else:
        raise ValueError(f"unknown magnitude_mode {cfg.magnitude_mode}")
    H = part.sum(axis=1)
    C = np.maximum(0, n_abn - 1) / max(F - 1, 1)
    return {"e": e, "a": a, "af": af, "usable": usable, "abn": abn, "n_use": n_use, "n_abn": n_abn, "H": H, "C": C,
            "part": part, "top": top}


# ============================================================================== score
def extras(grid: pd.DataFrame, ctx: dict, cfg: P7Config) -> tuple[np.ndarray, np.ndarray]:
    """AFR-down transition in the trailing window and Phase 4 activation in the trailing 2 h (0/1). Only used by the
    AFR / Phase 4 inclusion tests (weights 0 in the primary score)."""
    ix = grid.index
    ev = ctx["afr_events"]
    x_afr = recent_event(ix, ev.loc[ev.afr_transition.isin(AFR_DOWN), "T"], cfg.afr_context_hours).astype(float)
    p4 = grid["p4"].to_numpy(float)
    act = np.where(np.isfinite(p4), p4 >= ctx["p4_threshold"], False)
    x_p4 = (ic.trailing_mean(act.astype(float), cfg.p4_context_buckets, 1) > 0).astype(float)
    return x_afr, x_p4


def score_core(grid: pd.DataFrame, ref: dict, cfg: P7Config, ctx: dict | None = None) -> dict:
    """Risk score and every intermediate for all buckets (status masking happens in score_frame)."""
    S, run = family_S(grid, cfg)
    bidx = load_band_index(grid["feed"].to_numpy(float), ref)
    M, Q = anchor_arrays(ref, len(grid), bidx)
    mg = magnitude(S, M, Q, cfg)
    valid3 = run & (mg["n_use"] >= cfg.min_usable_families)
    if cfg.persistence_mode == "magnitude":
        pflag = valid3 & (mg["H"] >= ref["H_ref90"])
    elif cfg.persistence_mode == "any_family":
        pflag = valid3 & (mg["n_abn"] >= 1)
    else:
        raise ValueError(f"unknown persistence_mode {cfg.persistence_mode}")
    P = trailing_count_in_segment(pflag, run, cfg.persistence_buckets) / cfg.persistence_buckets
    x_afr = x_p4 = np.zeros(len(grid))
    if cfg.afr_weight or cfg.p4_weight:
        x_afr, x_p4 = extras(grid, ctx, cfg)
    scale = 1.0 - cfg.afr_weight - cfg.p4_weight
    wm, wc, wp = (w * scale for w in (cfg.w_magnitude, cfg.w_concurrence, cfg.w_persistence))
    contrib = {d: 100 * wm * mg["part"][:, j] for j, d in enumerate(cfg.families)}
    contrib["CONCURRENCE"] = 100 * wc * mg["C"]
    contrib["PERSISTENCE"] = 100 * wp * P
    if cfg.afr_weight:
        contrib["AFR_CONTEXT_TEST"] = 100 * cfg.afr_weight * x_afr
    if cfg.p4_weight:
        contrib["PHASE4_CONTEXT_TEST"] = 100 * cfg.p4_weight * x_p4
    R = np.sum(list(contrib.values()), axis=0)
    return {**mg, "S": S, "M": M, "Q": Q, "running": run, "valid3": valid3, "pflag": pflag, "P": P, "R": R,
            "contrib": contrib, "load_band_idx": bidx, "weights": (wm, wc, wp), "x_afr": x_afr, "x_p4": x_p4}


# ============================================================================== bands (pure calibration helpers)
def block_ids(ts: pd.DatetimeIndex | np.ndarray, start: str, days: int) -> np.ndarray:
    """Consecutive 0..k-1 ids of the `days`-long blocks the timestamps fall into (block bootstrap unit)."""
    t = pd.DatetimeIndex(ts)
    raw = np.floor((t - pd.Timestamp(start)) / pd.Timedelta(days=days)).astype(int)
    return np.unique(raw, return_inverse=True)[1]


def boot_quantiles(values: np.ndarray, block: np.ndarray, qs: tuple, n_boot: int, seed: int) -> np.ndarray:
    """(n_boot, len(qs)) quantiles under block resampling (multinomial block weights, Phase 4 boot_weights)."""
    order = np.argsort(values, kind="mergesort")
    v, b = values[order], block[order]
    W = ic.boot_weights(int(block.max()) + 1, n_boot, seed)
    cw = np.cumsum(W[:, b], axis=1)
    tot = cw[:, -1:]
    out = np.empty((n_boot, len(qs)))
    for k, q in enumerate(qs):
        out[:, k] = v[np.argmax(cw >= q * tot, axis=1)]
    return out


def fit_bands(R: np.ndarray, ts: pd.DatetimeIndex, cfg: P7Config, min_n: int = 1000, min_blocks: int = 10) -> dict:
    """Band edges = reference quantiles of the score (cfg.band_quantiles), each with a 95 % block-bootstrap CI.
    Support rule (a conservative POC heuristic, not a formal test of distinct edges): walk the edges upwards and keep an
    edge only if its CI lies entirely above the CI of the last kept edge; otherwise its upper band is merged into the
    band below. Too few values / blocks -> CALIBRATION_INSUFFICIENT."""
    R = np.asarray(R, float)
    ok = np.isfinite(R)
    R, ts = R[ok], pd.DatetimeIndex(ts)[ok]
    base = {"population": "VALID reference buckets (RUNNING, >= 3 usable families)", "n": int(R.size),
            "date_range": f"{ts.min()} .. {ts.max()}" if R.size else "", "quantiles": list(cfg.band_quantiles),
            "block_days": cfg.block_days, "n_boot": cfg.n_boot}
    blk = block_ids(ts, cfg.ref_start, cfg.block_days) if R.size else np.zeros(0, int)
    base["n_blocks"] = int(blk.max()) + 1 if R.size else 0
    if R.size < min_n or base["n_blocks"] < min_blocks:
        return {**base, "status": "CALIBRATION_INSUFFICIENT", "edges": [], "candidates": [],
                "reason": f"n={R.size} (< {min_n}) or blocks={base['n_blocks']} (< {min_blocks})"}
    point = np.quantile(R, cfg.band_quantiles)
    bq = boot_quantiles(R, blk, cfg.band_quantiles, cfg.n_boot, cfg.seed)
    lo, hi = np.quantile(bq, 0.025, axis=0), np.quantile(bq, 0.975, axis=0)
    cands, kept = [], []
    for k, (q, band) in enumerate(zip(cfg.band_quantiles, BANDS[1:])):
        e = {"band": band, "quantile": float(q), "value": float(point[k]), "ci_low": float(lo[k]),
             "ci_high": float(hi[k])}
        if not kept or (e["ci_low"] > kept[-1]["ci_high"] and e["value"] > kept[-1]["value"]):
            e["supported"], e["merged_into"] = True, ""
        else:
            e["supported"], e["merged_into"] = False, kept[-1]["band"]
        cands.append(e)
        if e["supported"]:
            kept.append(e)
    status = "BANDED" if len(kept) == len(cands) else "BANDED_WITH_MERGES"
    return {**base, "status": status, "edges": [{k: e[k] for k in ("band", "quantile", "value", "ci_low", "ci_high")}
                                                for e in kept], "candidates": cands}


def band_of(R: np.ndarray, bands: dict) -> np.ndarray:
    """Band label per value ('' for NaN). CALIBRATION_INSUFFICIENT -> UNBANDED."""
    R = np.asarray(R, float)
    ok = np.isfinite(R)
    if bands["status"] == "CALIBRATION_INSUFFICIENT":
        return np.where(ok, UNBANDED, "")
    names = np.array(["LOW"] + [e["band"] for e in bands["edges"]], dtype=object)
    vals = [e["value"] for e in bands["edges"]]
    idx = np.searchsorted(vals, np.where(ok, R, 0.0), side="right")
    return np.where(ok, names[idx], "").astype(object)


def band_rank(band: np.ndarray) -> np.ndarray:
    """0..3 for LOW..VERY_HIGH, -1 for anything else (not scored / unbanded)."""
    order = {b: i for i, b in enumerate(BANDS)}
    return np.array([order.get(b, -1) for b in band])


# ============================================================================== confidence and status
def reference_state(index: pd.DatetimeIndex, cfg: P7Config) -> np.ndarray:
    end = pd.Timestamp(cfg.ref_end) + pd.Timedelta(minutes=1)
    win = pd.Timedelta(minutes=10 * max(cfg.persistence_buckets, cfg.window_buckets))
    return np.select([index < end, (index - win) < end], ["IN_SAMPLE_REFERENCE", "OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE"],
                     "OUT_OF_SAMPLE")


def confidence(grid: pd.DataFrame, core: dict, band: np.ndarray, variant_bands: list[np.ndarray], cfg: P7Config,
               ctx: dict) -> pd.DataFrame:
    """Six causal confidence parts in [0, 1], their mean, the band and the MEDIUM cap. NaN when not RUNNING.
    Confidence on a non-VALID RUNNING row describes the data, not a score."""
    run = core["running"]
    n = len(grid)
    inv = np.nan_to_num(invalid_share(grid), nan=1.0)
    after = after_window(grid.index, ctx["dq_windows"], cfg.dq_after_window_hours)
    o2 = grid["o2_bucket_pct"].to_numpy(float) if "o2_bucket_pct" in grid else np.full(n, np.nan)
    o2_suspect = np.where(np.isfinite(o2), o2 >= cfg.o2_ambient_pct, False)
    dq = (grid["tag_coverage"].fillna(0).to_numpy(float) * (1 - inv)
          * np.where(grid["n_causal_frozen"].to_numpy(float) > 0, 0.5, 1.0) * np.where(after, 0.5, 1.0)
          * np.where(o2_suspect, 0.5, 1.0))
    tc = np.column_stack([grid[f"tagcov_{d}"].fillna(0).to_numpy(float) if f"tagcov_{d}" in grid else np.ones(n)
                          for d in cfg.families])
    cov = (core["usable"] * tc).mean(axis=1)          # whole families AND tag dropout inside a family (DQ-2)
    base = grid["share_high_conf"].fillna(0).to_numpy(float)
    st = (np.minimum(1.0, hours_since_restart(run) / cfg.settle_hours)
          * np.where(grid["oor"].to_numpy(bool), 0.5, 1.0))
    w = cfg.temporal_buckets
    k = ic.trailing_mean(core["pflag"].astype(float), w, 1) * np.minimum(np.arange(1, n + 1), w)
    temporal = np.where(core["pflag"], k / w, (w - k) / w)
    agree = np.zeros(n)
    if variant_bands:
        V = np.column_stack(variant_bands)
        has = V != ""
        same = (V == band[:, None]) & has
        agree = np.where(band != "", same.sum(axis=1) / np.maximum(has.sum(axis=1), 1), 0.0)
    out = pd.DataFrame({"conf_data_quality": dq, "conf_family_coverage": cov, "conf_baseline": base,
                        "conf_operating_state": st, "conf_temporal": temporal, "conf_robustness": agree},
                       index=grid.index)
    out.loc[~run] = np.nan
    out["confidence_score"] = out[list(CONF_PARTS)].mean(axis=1)
    s = out.confidence_score.to_numpy(float)
    raw = np.select([s >= cfg.conf_high, s >= cfg.conf_low, s < cfg.conf_low], ["HIGH", "MEDIUM", "LOW"], "")
    # critical-part rules: poor data quality cannot be averaged away, and an incomplete family set cannot vouch for a
    # below-HIGH score (a missing family scores 0, so absence of evidence would read as normal)
    low = (dq <= cfg.conf_low) | ((core["n_use"] < len(cfg.families)) & (band_rank(band) < HIGH_RANK))
    raw = np.where((raw != "") & low, "LOW", raw)
    out["confidence_band_uncapped"] = raw
    out["confidence_band"] = np.where(raw == "HIGH", "MEDIUM", raw)
    out["confidence_cap_reason"] = np.where(raw == "HIGH", CONF_CAP, "")
    out["dq_window_after"] = after
    out["causal_invalid_share"] = invalid_share(grid)
    out["o2_ambient_suspect"] = o2_suspect & run
    return out


def status(state: np.ndarray, n_use: np.ndarray, conf_band: np.ndarray, cfg: P7Config) -> np.ndarray:
    """Explicit status by fixed precedence (first match wins)."""
    st = np.asarray(state, dtype=object)
    return np.select([st == "STOPPED", np.isin(st, ["TRANSITION", "CONFLICT"]), st != "RUNNING", n_use == 0,
                      n_use < cfg.min_usable_families, conf_band == "LOW"],
                     ["STOPPED", "TRANSITION_CONTEXT", "NOT_SCORABLE", "NOT_SCORABLE", "INSUFFICIENT_DATA",
                      "VALID_REDUCED_CONFIDENCE"], "VALID").astype(object)


# ============================================================================== reasons
def driver_points(core: dict, cfg: P7Config) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """(n x 7) points of every score part, (n x 7) active flags (family abnormal / >= 2 families / P >= 0.5), codes."""
    fams = list(cfg.families)
    pts = np.column_stack([core["contrib"][d] for d in fams] + [core["contrib"]["CONCURRENCE"],
                                                                 core["contrib"]["PERSISTENCE"]])
    act = np.column_stack([core["abn"][:, j] for j in range(len(fams))] + [core["n_abn"] >= 2, core["P"] >= 0.5])
    codes = [REASON_BY_FAMILY.get(d, f"{d}_DEVIATION") for d in fams] + ["MULTI_FAMILY_CONCURRENCE",
                                                                         "PERSISTENT_DEVIATION"]
    return pts, act, codes


def reasons(frame: pd.DataFrame, core: dict, cfg: P7Config) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """primary_reason = the largest point contributor (ties: fixed order), suffixed _BELOW_THRESHOLD when that part is
    not itself active (e.g. a family below its reference P90); NO_DEVIATION_FROM_REFERENCE only for a zero score.
    secondary_reasons = the other ACTIVE drivers by points, then context codes, then confidence codes (fixed order)."""
    pts, act, codes = driver_points(core, cfg)
    scored = frame["risk_status"].str.startswith("VALID").to_numpy()
    flags = {"LOAD_ASSOCIATED_CONDITION": ("CONTEXT", frame["load_context"].eq("LOAD_ASSOCIATED").to_numpy()),
             "POST_RESTART_SETTLING": ("CONTEXT", frame["_hours_since_restart"].to_numpy(float) < cfg.settle_hours),
             "DATA_QUALITY_REDUCED_CONFIDENCE": ("CONFIDENCE", frame["conf_data_quality"].to_numpy(float) < cfg.conf_high),
             "REDUCED_FAMILY_COVERAGE": ("CONFIDENCE", frame["family_count_usable"].to_numpy() < len(cfg.families)),
             "SUSPECT_ANALYSER_AMBIENT_O2": ("CONFIDENCE", frame["o2_ambient_suspect"].to_numpy(bool))}
    top = pts.argmax(axis=1)
    rows_i = np.arange(len(pts))
    top_active = act[rows_i, top]
    code_arr = np.array(codes, dtype=object)
    primary = np.where(pts[rows_i, top] > 0, np.where(top_active, code_arr[top], code_arr[top] + BELOW), NO_DRIVER)
    primary = np.where(scored, primary, "").astype(object)
    secondary = np.full(len(frame), "", dtype=object)
    rows = []
    ts = frame.index
    for i in np.flatnonzero(scored):
        a = np.flatnonzero(act[i])
        order = a[np.lexsort((a, -pts[i, a]))] if a.size else a
        drv = [codes[j] for j in order if codes[j] != primary[i]]
        extra = [c for c, (_, f) in flags.items() if f[i]]
        secondary[i] = ";".join(drv + extra)
        for r, j in enumerate(order):
            rows.append((ts[i], codes[j], "SCORE_DRIVER", float(pts[i, j]), r + 1))
        if primary[i].endswith(BELOW):
            rows.append((ts[i], primary[i], "SCORE_DRIVER_BELOW_THRESHOLD", float(pts[i, top[i]]), 0))
        for c in extra:
            rows.append((ts[i], c, flags[c][0], 0.0, 0))
    long = pd.DataFrame(rows, columns=["timestamp", "reason_code", "reason_type", "contribution_points", "driver_rank"])
    return primary, secondary, long


# ============================================================================== context strings
def afr_context(index: pd.DatetimeIndex, ev: pd.DataFrame, hours: float) -> np.ndarray:
    """Phase 5 AFR transition kinds in (t - hours, t] (RETROSPECTIVE labels; context only)."""
    out = np.full(len(index), "", dtype=object)
    for k in AFR_KINDS:
        f = recent_event(index, ev.loc[ev.afr_transition == k, "T"], hours)
        out = np.where(f, np.where(out == "", k, out + ";" + k), out)
    return np.where(out == "", "NO_AFR_TRANSITION", out).astype(object)


def phase4_context(p4: np.ndarray, thr: float, n: int) -> np.ndarray:
    p4 = np.asarray(p4, float)
    fin = ic.trailing_mean(np.isfinite(p4).astype(float), n, 1) > 0
    act = ic.trailing_mean(np.where(np.isfinite(p4), p4 >= thr, False).astype(float), n, 1) > 0
    return np.select([~fin, act], ["NOT_AVAILABLE", "ACTIVE_TRAILING_2H (LOW confidence; context only)"], "NOT_ACTIVE")


def family_list(abn: np.ndarray, families: tuple) -> np.ndarray:
    out = np.full(len(abn), "", dtype=object)
    for j, d in enumerate(families):
        out = np.where(abn[:, j], np.where(out == "", d, out + ";" + d), out)
    return np.where(out == "", "NONE", out).astype(object)


def similarity(af: np.ndarray, signatures: list[dict]) -> np.ndarray:
    """Max weighted-Jaccard sum(min) / sum(max) of the intensity vector vs the frozen Apr-May signatures (diagnostic)."""
    if not signatures:
        return np.full(len(af), np.nan)
    sims = []
    for s in signatures:
        sig = np.asarray(s["signature"], float)
        mx = np.maximum(af, sig).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            sims.append(np.where(mx > 0, np.minimum(af, sig).sum(axis=1) / mx, 0.0))
    return np.max(sims, axis=0)


# ============================================================================== full frame
def score_frame(grid: pd.DataFrame, refs: dict, ctx: dict, cfg: P7Config = PRIMARY,
                variants: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Score every bucket with the frozen references. Returns (per-bucket frame, primary core dict).
    `refs` = {'PRIMARY': ref, <confidence variant>: ref, ...}; variants default to CONFIDENCE_VARIANTS.
    Public numbers (risk_score, risk_band, components, similarity) are set only on OPERATIONAL rows (out of sample and
    VALID*); in-sample reference scores and the non-operational diagnostic score live in separate columns that the
    writer routes to risk_score_diagnostics.parquet."""
    ref = refs["PRIMARY"]
    variants = CONFIDENCE_VARIANTS if variants is None else variants
    core = score_core(grid, ref, cfg, ctx)
    run, valid3 = core["running"], core["valid3"]
    band_all = band_of(np.where(valid3, core["R"], np.nan), ref["bands"])
    vb = []
    for name, vcfg in variants.items():
        vc = score_core(grid, refs[name], vcfg, ctx)
        vb.append(band_of(np.where(vc["valid3"], vc["R"], np.nan), refs[name]["bands"]))
    conf = confidence(grid, core, band_all, vb, cfg, ctx)
    stat = status(grid["state"].to_numpy(), core["n_use"], conf["confidence_band"].to_numpy(), cfg)
    scored = np.char.startswith(stat.astype(str), "VALID")
    rstate = reference_state(grid.index, cfg)
    oos = np.char.startswith(rstate.astype(str), "OUT_OF_SAMPLE")
    oper = scored & oos
    insample = scored & ~oos
    f = pd.DataFrame(index=grid.index)
    f.index.name = "timestamp"
    f["risk_score"] = np.where(oper, core["R"], np.nan)
    f["risk_band"] = np.select([oper, insample], [band_all, "IN_SAMPLE_REFERENCE"], "NOT_SCORED")
    f["operational"] = oper
    for c in ("confidence_score", "confidence_band", "confidence_band_uncapped", "confidence_cap_reason"):
        f[c] = conf[c].to_numpy()
    f["risk_status"] = stat
    f["reference_state"] = rstate
    f["operating_state"] = grid["state"].to_numpy()
    feed = grid["feed"].to_numpy(float)
    lb = core["load_band_idx"]
    f["load_band"] = np.where(lb >= 0, np.array(LOAD_BANDS, dtype=object)[np.clip(lb, 0, 2)], "UNKNOWN")
    chg = load_change(feed, cfg.load_change_buckets)
    assoc = (np.where(np.isfinite(chg), chg >= ref["load"]["feed_change_p90"], False)) | grid["oor"].to_numpy(bool)
    f["load_context"] = np.select([~np.isfinite(feed), assoc], ["UNKNOWN", "LOAD_ASSOCIATED"], "STEADY_LOAD")
    f["feed_tph"] = feed
    f["kpi_value"] = grid["kpi_value"].to_numpy(float)
    f["kpi_band"] = grid["kpi_band"].to_numpy()
    f["family_count_abnormal"] = np.where(run, core["n_abn"], 0)
    f["family_count_usable"] = np.where(run, core["n_use"], 0)
    f["persistence_minutes"] = run_minutes(core["pflag"])
    sim = similarity(core["af"], ref["signatures"])
    f["historical_similarity"] = np.where(oper, sim, np.nan)
    f["magnitude_component"] = np.where(oper, 100 * core["weights"][0] * core["H"], np.nan)
    f["concurrence_component"] = np.where(oper, core["contrib"]["CONCURRENCE"], np.nan)
    f["persistence_component"] = np.where(oper, core["contrib"]["PERSISTENCE"], np.nan)
    dqs = conf["conf_data_quality"].to_numpy(float)
    f["data_quality_status"] = np.select([~run, dqs >= cfg.conf_high, dqs > cfg.conf_low],
                                         ["NOT_APPLICABLE", "GOOD", "DEGRADED"], "POOR")
    f["contributing_families"] = family_list(core["abn"] & run[:, None], cfg.families)
    f["afr_context"] = afr_context(grid.index, ctx["afr_events"], cfg.afr_context_hours)
    f["phase4_context"] = phase4_context(grid["p4"].to_numpy(float), ctx["p4_threshold"], cfg.p4_context_buckets)
    f["_hours_since_restart"] = hours_since_restart(run)
    for c in CONF_PARTS + ("dq_window_after", "causal_invalid_share", "o2_ambient_suspect"):
        f[c] = conf[c].to_numpy()
    prim, sec, long = reasons(f, core, cfg)
    f["primary_reason"], f["secondary_reasons"] = prim, sec
    f["reference_version"] = ref["reference_version"]
    f["score_version"] = ref["score_version"]
    # diagnostics (never operational): in-sample reference scores / bands, and the formula value for any RUNNING bucket
    # with >= 3 usable families (e.g. for reduced-confidence inspection)
    f["risk_score_in_sample_reference"] = np.where(insample, core["R"], np.nan)
    f["risk_band_in_sample_reference"] = np.where(insample, band_all, "")
    f["risk_score_diagnostic"] = np.where(valid3, core["R"], np.nan)
    f["historical_similarity_diagnostic"] = np.where(valid3, sim, np.nan)
    f["score_all"] = np.where(scored, core["R"], np.nan)          # internal: every VALID* bucket (calibration only)
    f["band_all"] = np.where(scored, band_all, "")
    core["reasons_long"] = long
    return f.drop(columns=["_hours_since_restart"]), core


def components_long(frame: pd.DataFrame, core: dict, cfg: P7Config = PRIMARY) -> pd.DataFrame:
    """Auditable components of every VALID* bucket (operational AND in-sample, flagged): 5 family rows + CONCURRENCE +
    PERSISTENCE; family_contribution sums to risk_score (operational) / risk_score_in_sample_reference (G4)."""
    scored = frame["risk_status"].str.startswith("VALID").to_numpy()
    ix = frame.index[scored]
    oper = frame["operational"].to_numpy(bool)[scored]
    wm, wc, wp = core["weights"]
    F = len(cfg.families)
    parts = []
    for j, d in enumerate(cfg.families):
        af = core["af"][scored, j]
        with np.errstate(invalid="ignore", divide="ignore"):
            w = np.where(af > 0, wm * core["part"][scored, j] / af, wm / F)   # weight when the family scores 0: wm / F
        parts.append(pd.DataFrame({
            "timestamp": ix, "operational": oper, "family": d, "raw_measure": core["S"][scored, j],
            "reference_measure": core["Q"][scored, j], "normalized_deviation": core["e"][scored, j],
            "family_score": af, "family_weight": w, "family_contribution": core["contrib"][d][scored],
            "usable": core["usable"][scored, j],
            "quality_flag": np.where(core["usable"][scored, j], "USABLE", "MISSING_OR_MASKED"),
            "reason_code": np.where(core["abn"][scored, j], REASON_BY_FAMILY.get(d, f"{d}_DEVIATION"), "")}))
    n_abn, P = core["n_abn"][scored], core["P"][scored]
    parts.append(pd.DataFrame({
        "timestamp": ix, "operational": oper, "family": "CONCURRENCE", "raw_measure": n_abn.astype(float),
        "reference_measure": 1.0, "normalized_deviation": np.maximum(0, n_abn - 1).astype(float),
        "family_score": core["C"][scored], "family_weight": wc,
        "family_contribution": core["contrib"]["CONCURRENCE"][scored], "usable": True, "quality_flag": "DERIVED",
        "reason_code": np.where(n_abn >= 2, "MULTI_FAMILY_CONCURRENCE", "")}))
    parts.append(pd.DataFrame({
        "timestamp": ix, "operational": oper, "family": "PERSISTENCE", "raw_measure": P * cfg.persistence_buckets,
        "reference_measure": float(cfg.persistence_buckets), "normalized_deviation": P, "family_score": P,
        "family_weight": wp, "family_contribution": core["contrib"]["PERSISTENCE"][scored], "usable": True,
        "quality_flag": "DERIVED", "reason_code": np.where(P >= 0.5, "PERSISTENT_DEVIATION", "")}))
    out = pd.concat(parts, ignore_index=True)
    order = {k: i for i, k in enumerate(list(cfg.families) + ["CONCURRENCE", "PERSISTENCE"])}
    out["_o"] = out.family.map(order)
    return out.sort_values(["timestamp", "_o"], kind="mergesort").drop(columns="_o").reset_index(drop=True)
