"""Pure KPI functions: causal masks, causal state, bucketing, reference fitting, scoring.

Everything that turns minute data into a KPI value lives here, so that the leakage test and the unit
tests exercise exactly the production code path:

    minutes (wide values + state inputs) --prepare_minutes--> causal masks
                                          --causal_state-----> RUNNING / STOPPED / TRANSITION / CONFLICT / UNKNOWN
                                          --bucketize--------> 10-min buckets (right-closed, labelled by END)
    buckets --fit_reference(training window only)--> reference (JSON-serialisable dict)
    buckets + reference --score--> tag z, dimension scores, raw deviation D, persistent score P, KPI 0-100

Temporal rules (no look-ahead):
  * every mask, state and rolling statistic at minute t uses minutes <= t only;
  * a bucket labelled t aggregates minutes (t-10 min, t];
  * persistence at bucket t uses buckets in (t-W, t];
  * the reference is fitted on the training window only and then frozen.
All thresholds are POC analytical heuristics (see p3common.KPIConfig), not plant limits.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p3common import (FEED_TAG, HOOD_TAG, SPEED_TAG, MAD_SCALE, SUPPORT_DIMENSIONS, KPIConfig, TagSpec, spec_by_tag)

BAND_NAMES = ("WITHIN_REFERENCE_VARIATION", "ELEVATED_POC_ANALYTICAL", "BEYOND_REFERENCE_P99")
STATES = ("RUNNING", "STOPPED", "TRANSITION", "CONFLICT", "UNKNOWN")
P2_STATE_MAP = {"RUNNING_PROXY": "RUNNING", "STOPPED_PROXY": "STOPPED", "TRANSITION_RAMP_PROXY": "TRANSITION",
                "TRANSITION_PRE_STOP_PROXY": "TRANSITION", "STATE_CONFLICT": "CONFLICT", "UNKNOWN": "UNKNOWN"}


# ------------------------------------------------------------------------------------------ robust helpers
def robust_scale(x: np.ndarray, resolution: float = 0.0, rel_floor: float = 0.01, abs_floor: float = 0.0) -> float:
    """Floored robust scale: max(scaled MAD, IQR/1.349, value resolution, rel_floor*|median|, abs_floor)."""
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.nan
    med = float(np.median(x))
    q1, q3 = np.quantile(x, [0.25, 0.75])
    return float(max(MAD_SCALE * np.median(np.abs(x - med)), (q3 - q1) / 1.349, resolution, rel_floor * abs(med), abs_floor))


def value_resolution(x: np.ndarray) -> float:
    u = np.unique(x[np.isfinite(x)])
    return float(np.min(np.diff(u))) if u.size > 1 else 0.0


def minute_int(index: pd.DatetimeIndex) -> np.ndarray:
    """Timestamps as integer minutes (independent of the index's datetime unit)."""
    return index.values.astype("datetime64[m]").astype(np.int64)


def run_length(values: pd.DataFrame) -> np.ndarray:
    """Causal run length: number of consecutive identical samples ending at each row (1 = value changed).
    A missing value, or a timestamp step other than 1 minute, restarts the run."""
    v = values.to_numpy(dtype=float)
    n, k = v.shape
    step_ok = np.r_[False, np.diff(minute_int(values.index)) == 1][:, None]
    same = np.zeros((n, k), dtype=bool)
    same[1:] = (v[1:] == v[:-1]) & np.isfinite(v[1:])
    same &= step_ok
    c = np.cumsum(same, axis=0)
    reset = np.where(~same, c, 0)
    return (c - np.maximum.accumulate(reset, axis=0) + 1).astype(np.int32)


# ------------------------------------------------------------------------------------------ causal masks
def prepare_minutes(values: pd.DataFrame, cfg: KPIConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply CAUSAL flatline and frozen-row masks (non-zero identical runs, as in Phase 1). `values` must already carry NaN for causally invalid cells
    (Phase 2 per-cell tokens). Returns (masked values, per-minute mask flags)."""
    values = values.sort_index()
    rl = run_length(values)
    nonzero = values.to_numpy(dtype=float) != 0      # Phase 1 rule: only NON-ZERO identical runs are flatlines
    flat = (rl >= cfg.flat_run_n) & nonzero if cfg.use_causal_flatline else np.zeros(rl.shape, dtype=bool)
    exempt = [i for i, c in enumerate(values.columns) if c in cfg.flatline_exempt]
    flat[:, exempt] = False                           # load covariate: a feeder held at setpoint is valid information
    frozen = np.zeros(len(values), dtype=bool)
    frozen_by_ds = {}
    for ds in sorted({c.split("!")[0] for c in values.columns}):
        idx = [i for i, c in enumerate(values.columns) if c.split("!")[0] == ds]
        present = np.isfinite(values.iloc[:, idx].to_numpy()).sum(axis=1)
        n_flat = ((rl[:, idx] >= cfg.frozen_run_n) & nonzero[:, idx]).sum(axis=1)
        f = (n_flat >= cfg.frozen_min_tags) & (n_flat >= cfg.frozen_min_share * np.maximum(present, 1))
        frozen_by_ds[ds] = f
        frozen |= f
    mask = flat.copy()
    for ds, f in frozen_by_ds.items():
        idx = [i for i, c in enumerate(values.columns) if c.split("!")[0] == ds]
        mask[np.ix_(f, idx)] = True
    out = values.mask(mask)
    flags = pd.DataFrame({"causal_frozen": frozen, "n_flatline_masked": flat.sum(axis=1)}, index=values.index)
    return out, flags


# ------------------------------------------------------------------------------------------ causal state
def causal_state(state: pd.DataFrame, values: pd.DataFrame, cfg: KPIConfig) -> pd.DataFrame:
    """Per-minute operating state known at that minute (POC PROXY — UNCONFIRMED).

    Inputs are causal only: state_basic (Kiln MD composite per minute) and the masked minute values. Phase 2's
    retrospective operating_state is used only in the 'phase2_retrospective' sensitivity mode.
      * CONFLICT (Phase 2 rule, evaluated per minute): Kiln MD running but Kiln-I feed or kiln speed == 0, or Kiln MD
        stopped but feed > 0.
      * Restart: first RUNNING minute after STOPPED, or after a gap (UNKNOWN / missing minutes) > restart_gap_min.
      * Restart ramp (Phase 2 rule made causal): TRANSITION until the ramp signal has been >= the P25 of its own last
        1440 RUNNING minutes before the stop (excluding the 60 min before the stop, searched <= 7 days back) for 60
        consecutive clock minutes, or until 48 h after the restart (censored ramp, as Phase 2's search cap; a kiln that
        settles at a new, lower level is then scored, not hidden as a permanent transition). Signal per minute: Kiln-I
        feed if present and referenced, else Kiln-IA hood temperature; no reference at all -> fixed fallback duration.
      * Pre-stop minutes cannot be known in advance and stay RUNNING."""
    st = state.reindex(values.index)
    if cfg.state_mode == "phase2_retrospective":
        s = st.operating_state.map(P2_STATE_MAP).fillna("UNKNOWN")
        return pd.DataFrame({"state": s.astype(str), "ramp_basis": ""}, index=values.index)
    ts = minute_int(values.index)
    n = len(ts)
    basic = st.state_basic.astype(str).to_numpy()
    col = lambda t: values[t].to_numpy(float) if t in values else np.full(n, np.nan)
    feed, speed = col(FEED_TAG), col(SPEED_TAG)
    run_basic = basic == "RUNNING_PROXY"
    conflict = (run_basic & ((feed == 0) | (speed == 0))) | ((basic == "STOPPED_PROXY") & (feed > 0))
    sigs = {"KILN_I_FEED": feed, "KILN_IA_HOOD_TEMP": col(HOOD_TAG)}
    out = np.empty(n, dtype=object)
    basis = np.full(n, "", dtype=object)
    last_known, stop_start, last_run = None, None, None
    in_ramp, refs, sustain, ramp_start, last_eval = False, {}, 0, 0, None
    for i in range(n):
        b = basic[i]
        if b == "STOPPED_PROXY":
            if last_known != "STOPPED_PROXY":
                stop_start = ts[i]
            out[i], in_ramp, last_known = ("CONFLICT" if conflict[i] else "STOPPED"), False, b
            continue
        if b != "RUNNING_PROXY":
            out[i] = "UNKNOWN"
            continue
        gap_restart = last_run is not None and ts[i] - last_run > cfg.restart_gap_min
        if last_known == "STOPPED_PROXY" or gap_restart:   # restart: fix the ramp references from the past only
            s0 = stop_start if last_known == "STOPPED_PROXY" else last_run + 1
            in_ramp, sustain, ramp_start, last_eval, refs = True, 0, ts[i], None, {}
            j0 = np.searchsorted(ts, s0 - cfg.ramp_ref_lookback_min)
            j1 = np.searchsorted(ts, s0 - cfg.ramp_exclude_pre_stop_min)
            for name, arr in sigs.items():
                seg = arr[j0:j1][run_basic[j0:j1]]
                seg = seg[np.isfinite(seg)][-cfg.ramp_ref_minutes:]
                if seg.size >= 60:
                    refs[name] = float(np.quantile(seg, cfg.ramp_ref_quantile))
        last_known, last_run = b, ts[i]
        if in_ramp:
            name = next((k for k in refs if np.isfinite(sigs[k][i])), None)
            if not refs:
                in_ramp = ts[i] - ramp_start < cfg.ramp_fallback_min
                basis[i] = "FALLBACK_FIXED"
            else:
                ok = name is not None and sigs[name][i] >= refs[name]
                contiguous = last_eval is not None and ts[i] - last_eval == 1
                sustain = (sustain + 1 if contiguous else 1) if ok else 0
                last_eval = ts[i]
                in_ramp = sustain < cfg.ramp_sustain_min and ts[i] - ramp_start < cfg.ramp_max_min
                basis[i] = name or "NO_SIGNAL_THIS_MINUTE"
        out[i] = "CONFLICT" if conflict[i] else ("TRANSITION" if in_ramp else "RUNNING")
    return pd.DataFrame({"state": out.astype(str), "ramp_basis": basis.astype(str)}, index=values.index)


# ------------------------------------------------------------------------------------------ bucketing
def _resample(obj, cfg: KPIConfig):
    return obj.resample(f"{cfg.bucket_min}min", closed="right", label="right")


def bucketize(values: pd.DataFrame, cstate: pd.DataFrame, p2_state: pd.Series, flags: pd.DataFrame,
              cfg: KPIConfig) -> dict:
    """10-minute buckets from RUNNING minutes only. Returns dict with:
    values (bucket medians; NaN if < bucket_min_valid valid running minutes), std60 (bucket median of the
    trailing 60-min rolling std), meta (bucket state, counts, flags)."""
    run = cstate.state.eq("RUNNING")
    vals = values.copy()
    for s in spec_by_tag().values():
        if s.tag.startswith("DERIVED:") and all(t in vals for t in s.derived_from):
            vals[s.tag] = vals[list(s.derived_from)].sum(axis=1, min_count=len(s.derived_from))
    vr = vals.where(run, axis=0)
    rs = _resample(vr, cfg)
    med, cnt = rs.median(), rs.count()
    med = med.where(cnt >= cfg.bucket_min_valid)
    std_cols = {}
    for s in spec_by_tag().values():
        if s.tag.startswith("STD60:") and s.derived_from[0] in vr:
            r = vr[s.derived_from[0]].rolling(f"{cfg.stability_window_min}min", min_periods=cfg.stability_min_periods).std()
            std_cols[s.tag] = r.where(run)
    std = pd.DataFrame(std_cols, index=vr.index)
    std_rs = _resample(std, cfg)
    std_b = std_rs.median().where(std_rs.count() >= cfg.bucket_min_valid)
    cnts = {k: _resample(cstate.state.eq(k), cfg).sum() for k in STATES}
    p2ok = _resample(p2_state.reindex(values.index).astype(str).eq("RUNNING_PROXY"), cfg).sum()
    meta = pd.DataFrame({f"n_{k.lower()}": v for k, v in cnts.items()})
    meta["n_minutes"] = _resample(cstate.state, cfg).count()
    meta["n_p2_running"] = p2ok
    meta["n_causal_frozen"] = _resample(flags.causal_frozen, cfg).sum()
    meta["n_flatline_masked"] = _resample(flags.n_flatline_masked, cfg).sum()
    bs = np.select([meta.n_running >= cfg.bucket_min_valid, meta.n_stopped >= 5, meta.n_conflict > 0,
                    meta.n_transition > 0, meta.n_minutes == 0], ["RUNNING", "STOPPED", "CONFLICT", "TRANSITION", "NO_DATA"],
                   "UNKNOWN")
    meta["bucket_state"] = bs
    idx = meta.index
    return {"values": med.reindex(idx), "std60": std_b.reindex(idx), "meta": meta}


def minutes_to_buckets(values: pd.DataFrame, state: pd.DataFrame, cfg: KPIConfig) -> dict:
    masked, flags = prepare_minutes(values, cfg)
    cst = causal_state(state, masked, cfg)
    b = bucketize(masked, cst, state.operating_state.reindex(masked.index), flags, cfg)
    b["minute_state"] = cst
    return b


# ------------------------------------------------------------------------------------------ reference fit
def _window_mask(meta: pd.DataFrame, start: str, end: str, cfg: KPIConfig) -> pd.Series:
    """RUNNING buckets with labels in (start, end]; training additionally requires Phase 2 (retrospective) RUNNING
    minutes - hindsight is allowed inside the past training window (disclosed train/score population difference)."""
    t = meta.index
    return ((t > pd.Timestamp(start)) & (t < pd.Timestamp(end) + pd.Timedelta(minutes=1))
            & meta.bucket_state.eq("RUNNING") & (meta.n_p2_running >= cfg.bucket_min_valid))


def training_mask(meta: pd.DataFrame, cfg: KPIConfig) -> pd.Series:
    return _window_mask(meta, cfg.train_start, cfg.train_end, cfg)


def fit_masks(meta: pd.DataFrame, cfg: KPIConfig) -> tuple[pd.Series, pd.Series]:
    """(fit mask, calibration mask). Default: both = the training window. With cfg.fit_end set, tag / dimension
    references are fitted on (train_start, fit_end] and the KPI anchors / bands on the held-out (fit_end, train_end]."""
    if not cfg.fit_end:
        tm = training_mask(meta, cfg)
        return tm, tm
    return _window_mask(meta, cfg.train_start, cfg.fit_end, cfg), _window_mask(meta, cfg.fit_end, cfg.train_end, cfg)


def _tag_series(b: dict, tag: str) -> pd.Series:
    src = b["std60"] if tag.startswith("STD60:") else b["values"]
    return src[tag] if tag in src else pd.Series(np.nan, index=b["meta"].index)


def _gmm_bands(feed: np.ndarray, cfg: KPIConfig) -> dict:
    from sklearn.mixture import GaussianMixture
    g = GaussianMixture(cfg.n_bands, random_state=cfg.seed, n_init=3).fit(feed.reshape(-1, 1))
    order = np.argsort(g.means_.ravel())
    return {"means": g.means_.ravel()[order].tolist(), "vars": g.covariances_.ravel()[order].tolist(),
            "weights": g.weights_[order].tolist()}


def assign_band(feed: np.ndarray, bands: dict) -> np.ndarray:
    m, v, w = (np.asarray(bands[k]) for k in ("means", "vars", "weights"))
    ll = np.log(w) - 0.5 * np.log(2 * np.pi * v) - 0.5 * (feed[:, None] - m) ** 2 / v
    out = np.argmax(ll, axis=1).astype(float)
    out[~np.isfinite(feed)] = np.nan
    return out


def _load_bins(feed: np.ndarray, cfg: KPIConfig) -> list[float]:
    edges = np.unique(np.quantile(feed, np.linspace(0, 1, cfg.load_bins + 1)))
    while len(edges) > 2:
        counts = np.histogram(feed, bins=edges)[0]
        small = np.where(counts < cfg.load_bin_min_n)[0]
        if small.size == 0:
            break
        k = small[0]
        edges = np.delete(edges, k + 1 if k + 1 < len(edges) - 1 else k)
    return edges.tolist()


def fit_tag(x: pd.Series, feed: pd.Series, spec: TagSpec, cfg: KPIConfig, bands: dict | None) -> dict:
    """Fit one tag's expected value and scale on training buckets only."""
    xv = x.to_numpy(float)
    ok = np.isfinite(xv)
    ref: dict = {"n_train": int(ok.sum())}
    if spec.dimension == "STABILITY":
        eps = 0.01 * float(np.median(xv[ok])) + 1e-9
        y = np.log(xv[ok] + eps)
        ref.update(mode="log_std", eps=eps, center=float(np.median(y)),
                   scale=robust_scale(y, 0.0, 0.0, 0.01))
        return ref
    mode = cfg.load_mode if spec.load_adjusted else "global"
    fv = feed.to_numpy(float)
    both = ok & np.isfinite(fv)
    if mode == "adjusted" and both.sum() >= cfg.load_bin_min_n:
        edges = _load_bins(fv[both], cfg)
        which = np.clip(np.searchsorted(edges, fv[both], side="right") - 1, 0, len(edges) - 2)
        centers = [float(np.median(fv[both][which == k])) for k in range(len(edges) - 1)]
        meds = [float(np.median(xv[both][which == k])) for k in range(len(edges) - 1)]
        expected = np.interp(fv[both], centers, meds)
        resid = xv[both] - expected
        ref.update(mode="adjusted", centers=centers, medians=meds, edges=edges,
                   feed_p01=float(np.quantile(fv[both], 0.01)), feed_p99=float(np.quantile(fv[both], 0.99)))
    elif mode == "band" and bands is not None and both.sum() >= cfg.load_bin_min_n:
        lab = assign_band(fv[both], bands)
        meds = [float(np.median(xv[both][lab == k])) if (lab == k).sum() >= 30 else float(np.median(xv[both]))
                for k in range(len(bands["means"]))]
        resid = xv[both] - np.asarray(meds)[lab.astype(int)]
        ref.update(mode="band", medians=meds)
    else:
        resid = xv[ok] - float(np.median(xv[ok]))
        ref.update(mode="global", center=float(np.median(xv[ok])))
    ref["scale"] = robust_scale(resid, value_resolution(xv[ok]), 0.0) if resid.size else np.nan
    ref["scale"] = max(ref["scale"], cfg.scale_floor_rel * abs(float(np.median(xv[ok])))) if ok.any() else np.nan
    return ref


def expected_and_z(x: pd.Series, feed: pd.Series, spec: TagSpec, tref: dict, cfg: KPIConfig,
                   bands: dict | None) -> tuple[np.ndarray, np.ndarray]:
    xv, fv = x.to_numpy(float), feed.to_numpy(float)
    if tref["mode"] == "log_std":
        y = np.log(xv + tref["eps"])
        return np.full(len(xv), np.exp(tref["center"]) - tref["eps"]), np.clip((y - tref["center"]) / tref["scale"], -cfg.z_cap, cfg.z_cap)
    if tref["mode"] == "adjusted":
        exp_ = np.interp(fv, tref["centers"], tref["medians"])
        exp_[~np.isfinite(fv)] = np.nan
    elif tref["mode"] == "band":
        lab = assign_band(fv, bands)
        exp_ = np.full(len(xv), np.nan)
        okl = np.isfinite(lab)
        exp_[okl] = np.asarray(tref["medians"])[lab[okl].astype(int)]
    else:
        exp_ = np.full(len(xv), tref["center"])
    z = np.clip((xv - exp_) / tref["scale"], -cfg.z_cap, cfg.z_cap)
    return exp_, z


def tag_score(z: np.ndarray, direction: str) -> np.ndarray:
    return np.maximum(z, 0.0) if direction == "up" else np.abs(z)


def active_tags(tags: list[str], cfg: KPIConfig) -> list[str]:
    sp = spec_by_tag()
    out = []
    for t in tags:
        d = sp[t].dimension
        if d not in cfg.dimensions:
            continue
        if d == "EFFICIENCY" and cfg.sp_heat != "both" and not t.endswith("!" + cfg.sp_heat):
            continue
        out.append(t)
    return out


def score_tags(b: dict, ref: dict, cfg: KPIConfig) -> dict:
    """Tag-level expected value, z and tag score for every bucket."""
    sp = spec_by_tag()
    feed = b["values"][FEED_TAG] if FEED_TAG in b["values"] else pd.Series(np.nan, index=b["meta"].index)
    z, s, e = {}, {}, {}
    for t in active_tags(ref["included_tags"], cfg):
        e[t], z[t] = expected_and_z(_tag_series(b, t), feed, sp[t], ref["tags"][t], cfg, ref.get("bands"))
        s[t] = tag_score(z[t], sp[t].direction)
    idx = b["meta"].index
    return {"z": pd.DataFrame(z, index=idx), "score": pd.DataFrame(s, index=idx), "expected": pd.DataFrame(e, index=idx)}


def dimension_raw(scores: pd.DataFrame, cfg: KPIConfig) -> pd.DataFrame:
    sp = spec_by_tag()
    dims = {}
    for d in cfg.dimensions:
        cols = [c for c in scores.columns if sp[c].dimension == d]
        dims[d] = scores[cols].mean(axis=1) if cols else pd.Series(np.nan, index=scores.index)
    return pd.DataFrame(dims, index=scores.index)


def standardise_dims(raw: pd.DataFrame, dref: dict) -> pd.DataFrame:
    return pd.DataFrame({d: np.maximum(0.0, (raw[d] - dref[d]["median"]) / dref[d]["scale"]) for d in raw.columns},
                        index=raw.index)


def aggregate(S: pd.DataFrame, tag_scores: pd.DataFrame, ref: dict, cfg: KPIConfig) -> pd.Series:
    """Raw deviation D. Requires the EFFICIENCY dimension and >= min_support_dims supporting dimensions."""
    support = [d for d in S.columns if d != "EFFICIENCY"]
    n_sup = S[support].notna().sum(axis=1)
    ok = S["EFFICIENCY"].notna() & (n_sup >= min(cfg.min_support_dims, len(support)))
    if cfg.aggregation == "efficiency_anchored":
        sup = S[support].mean(axis=1) if support else 0.0
        D = cfg.w_efficiency * S["EFFICIENCY"] + (1 - cfg.w_efficiency) * sup
    elif cfg.aggregation == "equal_dimension":
        D = S.mean(axis=1)
    elif cfg.aggregation == "equal_tag":
        D = tag_scores.mean(axis=1)
    elif cfg.aggregation == "inverse_redundancy":
        w = pd.Series(ref["dim_weights"])[S.columns]
        D = (S * w).sum(axis=1, min_count=1) / S.notna().mul(w).sum(axis=1)
    else:
        raise ValueError(f"unknown aggregation {cfg.aggregation}")
    return D.where(ok)


def persistence(D: pd.Series, cfg: KPIConfig, elevated_level: float | None = None) -> pd.DataFrame:
    """Trailing clock-time persistence over (t - W, t] of scored buckets only."""
    if cfg.persistence_stat == "none":
        return pd.DataFrame({"P": D, "coverage": D.notna().astype(float), "frac_elevated": np.nan}, index=D.index)
    r = D.rolling(cfg.persistence_window, min_periods=1)
    n_exp = pd.Timedelta(cfg.persistence_window) / pd.Timedelta(minutes=cfg.bucket_min)
    cov = r.count() / n_exp
    P = r.median() if cfg.persistence_stat == "median" else r.mean()
    ok = (cov >= cfg.persistence_min_coverage) & D.notna()      # a bucket that is not itself scored gets no P
    P = P.where(ok)
    fe = np.nan
    if elevated_level is not None:
        el = (D > elevated_level).astype(float).where(D.notna())
        fe = el.rolling(cfg.persistence_window, min_periods=1).mean().where(ok)
    return pd.DataFrame({"P": P, "coverage": cov, "frac_elevated": fe}, index=D.index)


def to_kpi(P: np.ndarray | pd.Series, m: float, q: float) -> np.ndarray:
    """KPI = 100 * (1 - 2^-e), e = max(0, P - m) / (q - m). Training median -> 0, training anchor quantile -> 50."""
    if not q > m:
        raise ValueError(f"KPI anchor quantile ({q}) must exceed the median anchor ({m})")
    e = np.maximum(0.0, np.asarray(P, float) - m) / (q - m)
    return 100.0 * (1.0 - np.power(2.0, -e))


def fit_reference(b: dict, cfg: KPIConfig, candidate_tags: list[str]) -> dict:
    """Fit everything on the training window only. `candidate_tags` = tags that passed candidate selection."""
    sp = spec_by_tag()
    tm, tcal = fit_masks(b["meta"], cfg)
    feed_tr = b["values"][FEED_TAG][tm] if FEED_TAG in b["values"] else pd.Series(dtype=float)
    bands = _gmm_bands(feed_tr.dropna().to_numpy(), cfg) if cfg.load_mode == "band" else None
    ref: dict = {"config": cfg.name, "config_key": cfg.key(), "train_start": cfg.train_start, "train_end": cfg.train_end,
                 "fit_end": cfg.fit_end or cfg.train_end, "n_train_buckets": int(tm.sum()), "n_calibration_buckets": int(tcal.sum()), "bands": bands, "tags": {}, "included_tags": []}
    for t in candidate_tags:
        x = _tag_series(b, t)[tm]
        if x.notna().sum() < 30:
            continue
        ref["tags"][t] = fit_tag(x, feed_tr, sp[t], cfg, bands)
        ref["included_tags"].append(t)
    ts = score_tags(b, ref, cfg)
    raw = dimension_raw(ts["score"], cfg)
    ref["dims"] = {}
    for d in raw.columns:
        v = raw[d][tm].to_numpy(float)
        v = v[np.isfinite(v)]
        ref["dims"][d] = {"median": float(np.median(v)) if v.size else np.nan,
                          "scale": robust_scale(v, 0.0, 0.0, cfg.dim_scale_floor) if v.size else np.nan}
    S = standardise_dims(raw, ref["dims"])
    corr = S[tm].corr(method="spearman").abs()
    ref["dim_weights"] = {d: float(1.0 / (1.0 + corr[d].drop(d).fillna(0).sum())) for d in S.columns}
    D = aggregate(S, ts["score"], ref, cfg)
    Dtr = D[tm].dropna()
    ref["D_q90"] = float(Dtr.quantile(0.90))
    pers = persistence(D, cfg, ref["D_q90"])
    Ptr = pers.P[tcal].dropna()
    qa, (qb1, qb2) = cfg.ref_quantile_anchor, cfg.band_quantiles
    ref["scale"] = {"m": float(Ptr.median()), "q_anchor": float(Ptr.quantile(qa)),
                    "q_band_lo": float(Ptr.quantile(qb1)), "q_band_hi": float(Ptr.quantile(qb2)),
                    "n_train_P": int(Ptr.size), "P_percentiles": [float(x) for x in Ptr.quantile(np.linspace(0, 1, 101))]}
    Sw = window_median(S.where(D.notna()), cfg)
    for d in S.columns:
        ref["dims"][d]["p90_window_S"] = float(Sw[d][tcal].dropna().quantile(0.90))
    ref["secondary"] = fit_secondary(ts["z"], tm, cfg)
    return ref


# ------------------------------------------------------------------------------------------ secondary KPI
def _secondary_cols(z: pd.DataFrame) -> list[str]:
    return [c for c in z.columns if not c.startswith("STD60:")]


def fit_secondary(z: pd.DataFrame, tm: pd.Series, cfg: KPIConfig) -> dict:
    """Robust Mahalanobis distance (MinCovDet) on training complete cases of signed, capped tag z."""
    from sklearn.covariance import MinCovDet
    cols = _secondary_cols(z)
    X = z.loc[tm, cols].dropna().to_numpy()
    if len(X) < 10 * max(len(cols), 1):
        return {"cols": cols, "available": False}
    mcd = MinCovDet(support_fraction=0.75, random_state=cfg.seed).fit(X)
    cond = float(np.linalg.cond(mcd.covariance_))
    prec = np.linalg.pinv(mcd.covariance_)
    d = np.sqrt(np.einsum("ij,jk,ik->i", X - mcd.location_, prec, X - mcd.location_))
    return {"cols": cols, "available": True, "location": mcd.location_.tolist(), "precision": prec.tolist(),
            "condition_number": cond, "n_fit": int(len(X)), "train_d_median": float(np.median(d))}


def secondary_distance(z: pd.DataFrame, sref: dict) -> pd.Series:
    if not sref.get("available"):
        return pd.Series(np.nan, index=z.index)
    X = z[sref["cols"]].to_numpy()
    dx = X - np.asarray(sref["location"])
    d = np.sqrt(np.einsum("ij,jk,ik->i", dx, np.asarray(sref["precision"]), dx))
    return pd.Series(d, index=z.index)


# ------------------------------------------------------------------------------------------ scoring
def window_median(df: pd.DataFrame, cfg: KPIConfig) -> pd.DataFrame:
    if cfg.persistence_stat == "none":
        return df
    return df.rolling(cfg.persistence_window, min_periods=1).median()


def contributions(S: pd.DataFrame, ref: dict, cfg: KPIConfig) -> pd.DataFrame:
    """Weighted contribution of each dimension to D (sums to D for every aggregation except equal_tag)."""
    sup = [c for c in S.columns if c != "EFFICIENCY"]
    if cfg.aggregation == "efficiency_anchored":
        n = S[sup].notna().sum(axis=1).replace(0, np.nan)
        c = S[sup].mul(1 - cfg.w_efficiency).div(n, axis=0)
        c.insert(0, "EFFICIENCY", cfg.w_efficiency * S["EFFICIENCY"])
        return c
    if cfg.aggregation == "inverse_redundancy":
        w = pd.Series(ref["dim_weights"])[S.columns]
        return S.mul(w).div(S.notna().mul(w).sum(axis=1), axis=0)
    return S.div(S.notna().sum(axis=1), axis=0)


def score(b: dict, ref: dict, cfg: KPIConfig) -> dict:
    """Score every bucket with a frozen reference. Returns {'kpi': bucket frame, 'tags': dict of tag frames}."""
    meta = b["meta"]
    idx = meta.index
    ts = score_tags(b, ref, cfg)
    raw = dimension_raw(ts["score"], cfg)
    S = standardise_dims(raw, ref["dims"])
    D = aggregate(S, ts["score"], ref, cfg)
    pers = persistence(D, cfg, ref["D_q90"])
    sc = ref["scale"]
    k = pd.Series(to_kpi(pers.P, sc["m"], sc["q_anchor"]), index=idx).where(pers.P.notna())
    out = pd.DataFrame(index=idx)
    out["bucket_state"] = meta.bucket_state
    feed = b["values"][FEED_TAG] if FEED_TAG in b["values"] else pd.Series(np.nan, index=idx)
    out["load_context_feed_tph"] = feed
    for d in S.columns:
        out[f"{d.lower()}_component"] = S[d]
        out[f"{d.lower()}_raw"] = raw[d]
    out["raw_deviation_score"] = D
    out["persistent_deviation_score"] = pers.P
    out["persistence_window_coverage"] = pers.coverage
    out["persistence_fraction_elevated"] = pers.frac_elevated
    out["kpi_value"] = k
    # secondary validation KPI: same persistence + scale transform on robust Mahalanobis distance
    d2 = secondary_distance(ts["z"], ref["secondary"]).where(meta.bucket_state.eq("RUNNING"))
    out["secondary_distance"] = d2
    if ref["secondary"].get("available"):
        p2 = persistence(d2, cfg)
        s2 = ref["secondary"].get("scale")
        out["secondary_persistent_distance"] = p2.P
        out["secondary_mahalanobis_kpi"] = (pd.Series(to_kpi(p2.P, s2["m"], s2["q_anchor"]), index=idx).where(p2.P.notna())
                                            if s2 else np.nan)
    # explanation: weighted contributions per bucket and over the persistence window
    contrib = contributions(S, ref, cfg).where(D.notna())
    for d in contrib.columns:
        out[f"contrib_{d.lower()}"] = contrib[d]
    tsc = ts["score"]
    out["top_dimension_bucket"] = contrib.fillna(-1).idxmax(axis=1).where(D.notna())
    cw = window_median(contrib, cfg)
    tot = cw.sum(axis=1, min_count=1)
    out["top_dimension"] = cw.fillna(-1).idxmax(axis=1).where(pers.P.notna() & (tot > 0))
    tw = tsc.where(D.notna(), axis=0).rolling(cfg.persistence_window if cfg.persistence_stat != "none" else "10min",
                                              min_periods=1).mean()
    sp = spec_by_tag()
    top_in_dim = {d: tw[[c for c in tw.columns if sp[c].dimension == d]].fillna(-1).idxmax(axis=1)
                  for d in contrib.columns if any(sp[c].dimension == d for c in tw.columns)}
    out["top_tag"] = pd.Series([top_in_dim[d][i] if isinstance(d, str) and d in top_in_dim else np.nan
                                for i, d in zip(idx, out["top_dimension"])], index=idx, dtype=object)
    share = (cw["EFFICIENCY"] / tot).where(tot > 0) if "EFFICIENCY" in cw else pd.Series(np.nan, index=idx)
    out["window_efficiency_share"] = share.where(pers.P.notna())
    out["kpi_driver_class"] = np.select(
        [pers.P.isna(), (tot <= 1e-12) | tot.isna(), share >= 0.6, share <= 0.4],
        ["", "NO_DEVIATION", "SPECIFIC_HEAT_LED", "PROCESS_DEVIATION_LED"], "MIXED")
    Sw = window_median(S.where(D.notna()), cfg)
    lim = pd.Series({d: ref["dims"][d].get("p90_window_S", np.inf) for d in Sw.columns})
    out["n_dims_elevated"] = Sw.gt(lim, axis=1).sum(axis=1).where(pers.P.notna())
    grid = ref["scale"].get("P_percentiles")
    out["kpi_training_percentile"] = (pd.Series(np.interp(pers.P, grid, np.arange(101.0)), index=idx).where(pers.P.notna())
                                      if grid else np.nan)
    out["n_tags_available"] = tsc.notna().sum(axis=1)
    out["n_tags_included"] = tsc.shape[1]
    out["n_dims_available"] = S.notna().sum(axis=1)
    fr = [ref["tags"][t] for t in ref["tags"] if ref["tags"][t].get("mode") == "adjusted"]
    if fr:
        lo, hi = min(r["feed_p01"] for r in fr), max(r["feed_p99"] for r in fr)
        out["out_of_training_load_range"] = (feed < lo) | (feed > hi)
    else:
        out["out_of_training_load_range"] = False
    out["n_causal_frozen_minutes"] = meta.n_causal_frozen
    return {"kpi": out, "tags": ts}


def attach_secondary_scale(b: dict, ref: dict, cfg: KPIConfig) -> None:
    """Fit the secondary KPI's own training median / anchor quantile (training window only)."""
    if not ref["secondary"].get("available"):
        return
    tm = fit_masks(b["meta"], cfg)[1]
    ts = score_tags(b, ref, cfg)
    d2 = secondary_distance(ts["z"], ref["secondary"]).where(b["meta"].bucket_state.eq("RUNNING"))
    P = persistence(d2, cfg).P[tm].dropna()
    ref["secondary"]["scale"] = {"m": float(P.median()), "q_anchor": float(P.quantile(cfg.ref_quantile_anchor))}


def label_rows(kpi: pd.DataFrame, ref: dict, cfg: KPIConfig) -> pd.DataFrame:
    """Reference state per bucket + primary KPI column (NaN in training: in-sample value kept separately)."""
    t = kpi.index
    te = pd.Timestamp(cfg.train_end) + pd.Timedelta(minutes=1)
    win = pd.Timedelta(cfg.persistence_window) if cfg.persistence_stat != "none" else pd.Timedelta(minutes=cfg.bucket_min)
    st = np.select(
        [kpi.bucket_state.ne("RUNNING"), kpi.efficiency_component.isna(),
         kpi.raw_deviation_score.isna(), kpi.persistent_deviation_score.isna(), t < te, (t - win) < te],
        ["NOT_SCORED_" + kpi.bucket_state.astype(str), "NO_EFFICIENCY_DATA", "INSUFFICIENT_COMPONENTS",
         "INSUFFICIENT_WINDOW", "IN_TRAINING_WINDOW (in-sample)", "OUT_OF_SAMPLE (window overlaps training)"],
        "OUT_OF_SAMPLE")
    kpi = kpi.copy()
    kpi["kpi_reference_state"] = st
    scored = pd.Series(st, index=t).str.startswith("OUT_OF_SAMPLE")
    kpi["efficiency_deterioration_kpi"] = kpi.kpi_value.where(scored)
    kpi["kpi_in_sample_reference"] = kpi.kpi_value.where(pd.Series(st, index=t).str.startswith("IN_TRAINING"))
    sc = ref["scale"]
    k_lo, k_hi = to_kpi([sc["q_band_lo"]], sc["m"], sc["q_anchor"])[0], to_kpi([sc["q_band_hi"]], sc["m"], sc["q_anchor"])[0]
    shown = kpi.efficiency_deterioration_kpi.combine_first(kpi.kpi_in_sample_reference)
    code = np.select([shown < k_lo, shown < k_hi, shown >= k_hi], [0, 1, 2], -1)
    kpi["kpi_band_code"] = code
    kpi["kpi_band"] = pd.Series(np.array(["", *BAND_NAMES])[code + 1], index=t)
    return kpi


def run_kpi(values: pd.DataFrame, state: pd.DataFrame, cfg: KPIConfig, ref: dict | None = None,
            candidate_tags: list[str] | None = None) -> tuple[dict, dict, dict]:
    """End-to-end: minutes -> buckets -> (fit if no reference) -> scored + labelled buckets."""
    b = minutes_to_buckets(values, state, cfg)
    if ref is None:
        ref = fit_reference(b, cfg, candidate_tags)
        attach_secondary_scale(b, ref, cfg)
    s = score(b, ref, cfg)
    s["kpi"] = label_rows(s["kpi"], ref, cfg)
    return b, ref, s


def fit_score(b: dict, cfg: KPIConfig, candidate_tags: list[str]) -> tuple[dict, dict]:
    """Fit on the training window, then score and label every bucket (used by the step scripts and variants)."""
    ref = fit_reference(b, cfg, candidate_tags)
    attach_secondary_scale(b, ref, cfg)
    s = score(b, ref, cfg)
    s["kpi"] = label_rows(s["kpi"], ref, cfg)
    return ref, s
