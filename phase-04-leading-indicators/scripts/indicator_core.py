"""Pure Phase 4 functions: causal buckets, causal features, future-only targets, controls, statistics, episodes, alarms.

Everything that turns data into a feature value, a target value or a statistic lives here, so the leakage test and the
unit tests exercise exactly the production code path:

    minutes (per dataset) --prepare_minutes (Phase 3) + small-dataset frozen mask--> causal masks
    Phase 3 state subset  --kpi_core.minutes_to_buckets----------------------------> causal state + bucket meta
    masked minutes + state --bucket_medians--> RUNNING 10-min bucket medians (right-closed, labelled by END)
    buckets --fit_feature_reference (discovery only, frozen)--> reference
    buckets + reference --compute_features--> LEVEL / DEV / ROC / VOL / PERSIST at t, using buckets <= t only
    KPI --future_target--> dK(t, H) = median K over (t+H-30 min, t+H] - K(t)      (FUTURE-ONLY, never a feature)
    KPI --controls--> K(t), momentum K(t) - K(t-1 h), Kpend(t, H)              (data <= t only)

Temporal rules (no look-ahead in features / controls):
  * a bucket labelled t aggregates minutes (t-10 min, t]; every trailing window at t uses buckets in (t-W, t];
  * the grid is regular (10 min), so trailing windows are exact positional shifts - no centred windows anywhere;
  * references (expected level, scale, quantile bands, volatility centre) are fitted on the discovery window only.
The target is the only object that looks forward, and it is only ever used as the dependent variable.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.special import ndtr
from scipy.stats import rankdata

from p4common import FEATURES, P4Config    # first: sets up the read-only Phase 3 import path

import kpi_core  # noqa: E402  (Phase 3)
import p3common  # noqa: E402  (Phase 3)

P3CFG = p3common.PRIMARY          # Phase 3 primary configuration (masks, state, bucketing, fit_tag settings)


# ============================================================================== buckets
def small_dataset_frozen(values: pd.DataFrame, min_tags: int = 5, share: float = 0.8, run_n: int = 10) -> np.ndarray:
    """Causal frozen-row mask for datasets with fewer tags than Phase 3's frozen_min_tags (20), where the Phase 3 rule
    can never fire: a minute is frozen when >= `share` of the dataset's present tags (and >= min_tags) have been
    identical and non-zero for >= run_n consecutive samples ending at that minute."""
    rl = kpi_core.run_length(values)
    v = values.to_numpy(dtype=float)
    present = np.isfinite(v).sum(axis=1)
    n_flat = ((rl >= run_n) & (v != 0) & np.isfinite(v)).sum(axis=1)
    return (n_flat >= min_tags) & (n_flat >= share * np.maximum(present, 1))


def mask_dataset(values: pd.DataFrame, small_rule: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Phase 3 causal flatline + frozen masks for ONE dataset's columns; plus (small_rule=True, datasets outside the
    Phase 3 KPI subset only) the small-dataset frozen rule where the Phase 3 rule cannot fire.
    Returns (masked values, flags with causal_frozen / small_frozen)."""
    masked, flags = kpi_core.prepare_minutes(values, P3CFG)
    small = np.zeros(len(values), dtype=bool)
    if small_rule and values.shape[1] < P3CFG.frozen_min_tags:
        small = small_dataset_frozen(values.sort_index())
        masked = masked.mask(np.repeat(small[:, None], values.shape[1], axis=1))
    flags = flags.assign(small_frozen=small)
    return masked, flags


def bucket_medians(masked: pd.DataFrame, minute_state: pd.Series, index: pd.DatetimeIndex) -> pd.DataFrame:
    """RUNNING-minute bucket medians exactly as kpi_core.bucketize (>= bucket_min_valid valid minutes)."""
    run = minute_state.reindex(masked.index).eq("RUNNING")
    rs = kpi_core._resample(masked.where(run, axis=0), P3CFG)
    med, cnt = rs.median(), rs.count()
    return med.where(cnt >= P3CFG.bucket_min_valid).reindex(index)


def build_buckets(frames: dict[str, pd.DataFrame], state: pd.DataFrame, state_datasets: list[str],
                  disc_end: str | None = None) -> dict:
    """Minute frames (one per dataset, held columns already dropped, all on the Phase 3 minute index) -> buckets.
    The operating state is rebuilt with kpi_core.minutes_to_buckets on EXACTLY the Phase 3 column subset, so bucket
    state equals Phase 3's. Every dataset is then masked on its own and bucketed on RUNNING minutes.
    Returns {values, meta, minute_state, dq} where dq has per-tag minute accounting (all minutes, and minutes up to
    disc_end when given)."""
    sv = pd.concat([frames[d] for d in state_datasets], axis=1)
    sv = sv[sorted(sv.columns)]
    b3 = kpi_core.minutes_to_buckets(sv, state, P3CFG)
    meta, mstate = b3["meta"], b3["minute_state"]
    del sv, b3
    parts, dq = [], []
    for ds, f in frames.items():
        masked, flags = mask_dataset(f, small_rule=ds not in state_datasets)
        parts.append(bucket_medians(masked, mstate.state, meta.index))
        pres, kept = f.notna(), masked.notna()
        row = pd.DataFrame({"tag": f.columns, "present_minutes": pres.sum().to_numpy(),
                            "valid_after_causal_masks": kept.sum().to_numpy(),
                            "small_dataset_frozen_minutes": int(flags.small_frozen.sum()),
                            "causal_frozen_minutes": int(flags.causal_frozen.sum())})
        if disc_end is not None:
            d = f.index <= pd.Timestamp(disc_end)
            row["disc_present_minutes"] = pres[d].sum().to_numpy()
            row["disc_valid_after_causal_masks"] = kept[d].sum().to_numpy()
        dq.append(row)
    values = pd.concat(parts, axis=1)
    return {"values": values[sorted(values.columns)], "meta": meta, "minute_state": mstate,
            "dq": pd.concat(dq, ignore_index=True)}


# ============================================================================== trailing-window helpers
def check_grid(index: pd.DatetimeIndex, bucket_min: int = 10) -> None:
    d = np.diff(index.values.astype("datetime64[m]").astype(np.int64))
    if d.size and not np.all(d == bucket_min):
        raise ValueError("bucket index is not a regular grid - positional trailing windows would be wrong")


def lagged(a: np.ndarray, k: int) -> np.ndarray:
    """a[t-k] aligned to t (NaN for the first k rows). k >= 0 only: never looks forward."""
    if k < 0:
        raise ValueError("lagged() only shifts into the past")
    out = np.full_like(a, np.nan, dtype=float)
    if k == 0:
        return a.astype(float).copy()
    out[k:] = a[:-k]
    return out


def trailing_stack(a: np.ndarray, n: int) -> np.ndarray:
    """(len(a), n) matrix whose column j holds a[t-j] - the window (t-n, t] in buckets."""
    return np.column_stack([lagged(a, j) for j in range(n)])


def trailing_median(a: np.ndarray, n: int, min_valid: int) -> np.ndarray:
    s = trailing_stack(a, n)
    cnt = np.isfinite(s).sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmedian(s, axis=1)
    return np.where(cnt >= min_valid, m, np.nan)


def trailing_mad(a: np.ndarray, n: int, min_valid: int) -> np.ndarray:
    s = trailing_stack(a, n)
    cnt = np.isfinite(s).sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(s, axis=1)
        mad = np.nanmedian(np.abs(s - med[:, None]), axis=1)
    return np.where(cnt >= min_valid, mad, np.nan)


def trailing_mean(a: np.ndarray, n: int, min_valid: int) -> np.ndarray:
    """Trailing mean over (t-n, t] via cumulative sums (NaN ignored)."""
    ok = np.isfinite(a)
    cs = np.concatenate([[0.0], np.cumsum(np.where(ok, a, 0.0))])
    cc = np.concatenate([[0], np.cumsum(ok)])
    i = np.arange(1, len(a) + 1)
    j = np.maximum(i - n, 0)
    s, c = cs[i] - cs[j], cc[i] - cc[j]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c >= min_valid, s / c, np.nan)


def buckets_in(minutes: int, cfg: P4Config) -> int:
    return int(minutes // cfg.bucket_min)


# ============================================================================== features
def tag_spec(tag: str) -> p3common.TagSpec:
    """Phase 3 TagSpec used only to call kpi_core.fit_tag / expected_and_z. The load covariate itself is global."""
    return p3common.TagSpec(tag, "THERMAL", "both", tag != p3common.FEED_TAG, "Phase 4 feature reference")


def level(b: np.ndarray, cfg: P4Config) -> np.ndarray:
    n = buckets_in(cfg.level_win, cfg)
    return trailing_median(b, n, int(np.ceil(cfg.feat_min_cov * n)))


def fit_feature_reference(b: pd.DataFrame, feed_b: pd.Series, train: pd.Series, cfg: P4Config) -> dict:
    """Fit every per-tag reference on DISCOVERY training buckets only. JSON-serialisable."""
    feed_l = pd.Series(level(feed_b.to_numpy(float), cfg), index=b.index)
    ref = {}
    tm = train.to_numpy(bool)
    for t in b.columns:
        x = b[t].to_numpy(float)
        lv = pd.Series(level(x, cfg), index=b.index)
        if np.isfinite(lv[tm]).sum() < 30:
            ref[t] = {"available": False}
            continue
        spec = tag_spec(t)
        tr = kpi_core.fit_tag(lv[tm], feed_l[tm], spec, P3CFG, None)
        _, zb = kpi_core.expected_and_z(b[t], feed_b, spec, tr, P3CFG, None)
        zt = zb[tm & np.isfinite(zb)]
        n_v = buckets_in(cfg.vol_win, cfg)
        mad = trailing_mad(x, n_v, int(np.ceil(2 * n_v / 3)))
        eps = 0.01 * tr["scale"] + 1e-9
        v = np.log(1.4826 * mad + eps)
        vt = v[tm & np.isfinite(v)]
        ref[t] = {"available": True, "level_ref": tr, "z_lo": float(np.quantile(zt, cfg.persist_q[0])) if zt.size else np.nan,
                  "z_hi": float(np.quantile(zt, cfg.persist_q[1])) if zt.size else np.nan, "vol_eps": float(eps),
                  "vol_center": float(np.median(vt)) if vt.size else np.nan, "n_train": int(np.isfinite(lv[tm]).sum())}
    return ref


def compute_features(b: pd.DataFrame, feed_b: pd.Series, ref: dict, cfg: P4Config) -> dict[str, pd.DataFrame]:
    """All causal features for every tag: {feature: DataFrame(index = bucket grid, columns = tags)}."""
    check_grid(b.index, cfg.bucket_min)
    idx = b.index
    feed_l = level(feed_b.to_numpy(float), cfg)
    out = {f: {} for f in FEATURES}
    n_p = buckets_in(cfg.persist_win, cfg)
    n_v = buckets_in(cfg.vol_win, cfg)
    for t in b.columns:
        r = ref.get(t, {})
        if not r.get("available"):
            continue
        x = b[t].to_numpy(float)
        lv = level(x, cfg)
        spec, tr = tag_spec(t), r["level_ref"]
        sc = tr["scale"]
        _, z = kpi_core.expected_and_z(pd.Series(lv, index=idx), pd.Series(feed_l, index=idx), spec, tr, P3CFG, None)
        _, zb = kpi_core.expected_and_z(b[t], feed_b, spec, tr, P3CFG, None)
        out["LEVEL_1H"][t] = lv
        out["DEV_1H"][t] = z
        for w, name in zip(cfg.roc_wins, ("ROC_1H", "ROC_3H")):
            out[name][t] = np.clip((lv - lagged(lv, buckets_in(w, cfg))) / sc, -cfg.z_cap, cfg.z_cap)
        mad = trailing_mad(x, n_v, int(np.ceil(2 * n_v / 3)))
        out["VOL_2H"][t] = np.log(1.4826 * mad + r["vol_eps"]) - r["vol_center"]
        hi = np.where(np.isfinite(zb), (zb > r["z_hi"]).astype(float), np.nan)
        lo = np.where(np.isfinite(zb), (zb < r["z_lo"]).astype(float), np.nan)
        mv = int(np.ceil(cfg.feat_min_cov * n_p))
        out["PERSIST_HI_6H"][t] = trailing_mean(hi, n_p, mv)
        out["PERSIST_LO_6H"][t] = trailing_mean(lo, n_p, mv)
    return {f: pd.DataFrame(v, index=idx) for f, v in out.items()}


# ============================================================================== targets and controls
def future_target(K: np.ndarray, running: np.ndarray, h: int, smooth: int = 3) -> np.ndarray:
    """dK(t, H) = median of K over buckets (t+h-s, t+h], s = min(smooth, h) (>= ceil(2 s / 3) valid) - K(t).
    NaN when K(t) is not scored or any bucket in (t, t+h] is not RUNNING (no stop / transition inside the horizon).
    FUTURE-ONLY by construction: used exclusively as the dependent variable."""
    n = len(K)
    s = min(smooth, h)                                  # the smoothing window never reaches back to t or earlier
    stack = np.column_stack([np.r_[K[h - j:], np.full(h - j, np.nan)] for j in range(s)])
    cnt = np.isfinite(stack).sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(stack, axis=1)
    kf = np.where(cnt >= int(np.ceil(2 * s / 3)), med, np.nan)
    nr = np.concatenate([[0], np.cumsum(~running)])
    i = np.arange(n)
    end = np.minimum(i + h, n - 1)
    ok = (nr[end + 1] - nr[i + 1] == 0) & (i + h < n)
    return np.where(ok & np.isfinite(K), kf - K, np.nan)


def future_band_target(code: np.ndarray, K: np.ndarray, running: np.ndarray, h: int) -> np.ndarray:
    """T2: 1 if >= 50 % of scored buckets in (t, t+h] are in band code >= 1, given code == 0 over the last hour.
    FUTURE-ONLY (dependent variable)."""
    n = len(code)
    el = np.where(np.isfinite(K), (code >= 1).astype(float), np.nan)
    fut = np.full(n, np.nan)
    m = trailing_mean(el, h, max(1, h // 2))            # mean over (s-h, s] -> aligned so s = t + h
    fut[: n - h] = m[h:]
    prior = trailing_mean(el, 6, 3)
    nr = np.concatenate([[0], np.cumsum(~running)])
    i = np.arange(n)
    end = np.minimum(i + h, n - 1)
    ok = (nr[end + 1] - nr[i + 1] == 0) & (i + h < n) & (prior == 0) & np.isfinite(K)
    return np.where(ok & np.isfinite(fut), (fut >= 0.5).astype(float), np.nan)


def controls(K: np.ndarray, D: np.ndarray, h: int, m: float, q: float) -> np.ndarray:
    """(n, 3) controls known at t: K(t); momentum K(t) - K(t-1 h); Kpend(t, H) = the part of the future persistent
    score already observed at t (to_kpi of the median raw deviation D over (t+H-6 h, t] for H < 6 h, else over the last
    hour). Removes the mechanical 'D leads its own trailing median P' effect for KPI-input tags."""
    mom = K - lagged(K, 6)                             # 1 h of 10-min buckets
    n_pend = 36 - h if h < 36 else 6                   # 6 h persistence window of Phase 3 (36 buckets)
    pend = trailing_median(D, n_pend, max(1, int(np.ceil(0.5 * n_pend))))
    kp = np.where(np.isfinite(pend), kpi_core.to_kpi(np.nan_to_num(pend), m, q), np.nan)
    return np.column_stack([K, mom, kp])


# ============================================================================== statistics
def residualise(r: np.ndarray, A: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(A, r, rcond=None)
    return r - A @ beta


def acf(x: np.ndarray, maxlag: int) -> np.ndarray:
    """NaN-aware autocorrelation r(1..maxlag) of a series on a regular grid (FFT; pairs with both ends present)."""
    ok = np.isfinite(x)
    if ok.sum() < 3:
        return np.zeros(maxlag)
    xc = np.where(ok, x - np.nanmean(x), 0.0)
    m = ok.astype(float)
    n = len(x)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    fx, fm = np.fft.rfft(xc, size), np.fft.rfft(m, size)
    num = np.fft.irfft(fx * np.conj(fx), size)[: maxlag + 1]
    cnt = np.fft.irfft(fm * np.conj(fm), size)[: maxlag + 1]
    var = num[0] / max(cnt[0], 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (num[1:] / np.maximum(np.round(cnt[1:]), 1)) / var
    r[np.round(cnt[1:]) < 10] = 0.0
    return np.nan_to_num(np.clip(r, -1, 1))


def n_effective(ex: np.ndarray, ey: np.ndarray, n: int, maxlag: int) -> float:
    """Bartlett / Pyper-Peterman effective sample size for the correlation of two autocorrelated series:
    N_eff = N / (1 + 2 * sum_k w_k r_x(k) r_y(k)), w_k = 1 - k/(maxlag+1). ex, ey on the regular grid (NaN gaps)."""
    L = min(maxlag, max(1, len(ex) // 5))
    rx, ry = acf(ex, L), acf(ey, L)
    w = 1.0 - np.arange(1, L + 1) / (L + 1)
    denom = 1.0 + 2.0 * float(np.sum(w * rx * ry))
    return float(np.clip(n / max(denom, 1e-9), 3.0, n))


def bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted q-values (NaN-aware, monotone)."""
    p = np.asarray(p, float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    if not ok.any():
        return q
    pv = p[ok]
    order = np.argsort(pv, kind="mergesort")
    m = pv.size
    adj = pv[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    q[ok] = out
    return q


def boot_weights(n_blocks: int, n_boot: int, seed: int) -> np.ndarray:
    """(n_boot, n_blocks) multinomial resampling counts of blocks (block bootstrap)."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_blocks, np.full(n_blocks, 1.0 / n_blocks), size=n_boot).astype(float)


def boot_corr_ci(ex: np.ndarray, ey: np.ndarray, block: np.ndarray, W: np.ndarray) -> tuple[float, float]:
    """95 % percentile CI of corr(ex, ey) under block resampling, via per-block sufficient statistics.
    `block` = block id (0..n_blocks-1) of every row; W = boot_weights(n_blocks, ...)."""
    nb = W.shape[1]
    S = np.zeros((nb, 6))
    for j, v in enumerate((np.ones_like(ex), ex, ey, ex * ex, ey * ey, ex * ey)):
        S[:, j] = np.bincount(block, weights=v, minlength=nb)
    T = W @ S
    n, sx, sy, sxx, syy, sxy = T.T
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (n * sxy - sx * sy) / np.sqrt((n * sxx - sx ** 2) * (n * syy - sy ** 2))
    r = r[np.isfinite(r)]
    if r.size < 10:
        return np.nan, np.nan
    return float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))


def assoc(x: np.ndarray, y: np.ndarray, Z: np.ndarray | None, rows: np.ndarray, block: np.ndarray,
          boot_seed: int | None, maxlag: int, min_n: int = 100, n_boot: int = 1000) -> dict:
    """Rank association of x(t) with y(t) on `rows` (bool mask on the grid):
       rho_raw  Spearman(x, y);  rho_p  partial Spearman controlling for Z (rank residuals on [1, rank Z]);
       n, n_eff (autocorrelation-adjusted), p_eff (Fisher z with n_eff), 95 % block-bootstrap CI of rho_p.
    Bootstrap: calendar blocks (`block` ids) present among the rows actually used are resampled (boot_seed None = no CI).
    The control regression is fitted once on the full sample (disclosed approximation; checked against a naive
    bootstrap in the unit tests)."""
    ok = rows & np.isfinite(x) & np.isfinite(y)
    if Z is not None:
        ok &= np.isfinite(Z).all(axis=1)
    n = int(ok.sum())
    res = {"n": n, "rho_raw": np.nan, "rho_p": np.nan, "n_eff": np.nan, "p_eff": np.nan, "ci_lo": np.nan, "ci_hi": np.nan}
    if n < min_n:
        return res
    rx, ry = rankdata(x[ok]), rankdata(y[ok])
    if np.ptp(rx) == 0 or np.ptp(ry) == 0:
        return res
    res["rho_raw"] = float(np.corrcoef(rx, ry)[0, 1])
    k = 0
    if Z is not None:
        A = np.column_stack([np.ones(n)] + [rankdata(Z[ok, j]) for j in range(Z.shape[1])])
        k = Z.shape[1]
        ex, ey = residualise(rx, A), residualise(ry, A)
    else:
        ex, ey = rx - rx.mean(), ry - ry.mean()
    sx, sy = ex.std(), ey.std()
    if sx < 1e-12 or sy < 1e-12:
        return res
    rho = float(np.clip(np.dot(ex, ey) / (n * sx * sy), -0.999999, 0.999999))
    gx, gy = np.full(len(x), np.nan), np.full(len(x), np.nan)
    gx[ok], gy[ok] = ex, ey
    ne = n_effective(gx, gy, n, maxlag)
    dof = max(ne - 3 - k, 1.0)
    res.update(rho_p=rho, n_eff=ne, p_eff=float(2 * (1 - ndtr(abs(np.arctanh(rho)) * np.sqrt(dof)))))
    if boot_seed is not None:
        u, blk = np.unique(block[ok], return_inverse=True)       # only blocks that contain used rows
        if u.size >= 5:
            res["ci_lo"], res["ci_hi"] = boot_corr_ci(ex, ey, blk, boot_weights(u.size, n_boot, boot_seed))
    return res


# ============================================================================== episodes
def run_lengths(flag: np.ndarray) -> np.ndarray:
    """Causal run length of True values ending at each row."""
    f = flag.astype(bool)
    c = np.cumsum(f)
    reset = np.where(~f, c, 0)
    return np.where(f, c - np.maximum.accumulate(reset), 0)


def band_onsets(K: np.ndarray, code: np.ndarray, cfg: P4Config) -> np.ndarray:
    """E_BAND: first bucket of a run of >= ep_min_buckets consecutive scored buckets with band code >= 1, preceded by
    ep_clear_h hours with no code >= 1 and >= 50 % scored buckets. (Episode definition: retrospective by design.)"""
    el = np.isfinite(K) & (code >= 1)
    n = len(K)
    out = []
    i = 0
    clear = cfg.ep_clear_h * 60 // cfg.bucket_min
    while i < n:
        if el[i] and (i == 0 or not el[i - 1]):
            j = i
            while j < n and el[j]:
                j += 1
            if j - i >= cfg.ep_min_buckets and i >= clear:
                prior = slice(i - clear, i)
                if not (np.isfinite(K[prior]) & (code[prior] >= 1)).any() and np.isfinite(K[prior]).mean() >= 0.5:
                    out.append(i)
            i = j
        else:
            i += 1
    return np.asarray(out, dtype=int)


def rise_onsets(K: np.ndarray, thr: float, cfg: P4Config) -> np.ndarray:
    """E_RISE: first bucket where K(t) - K(t-6 h) >= thr (discovery P95 of 6-h rises), refractory ep_refractory_h."""
    r6 = K - lagged(K, 6 * 60 // cfg.bucket_min)
    hit = np.where(np.isfinite(r6), r6 >= thr, False)
    out, last = [], -10 ** 9
    ref = cfg.ep_refractory_h * 60 // cfg.bucket_min
    for i in np.flatnonzero(hit & ~np.r_[False, hit[:-1]]):
        if i - last >= ref:
            out.append(i)
            last = i
    return np.asarray(out, dtype=int)


def rise_start(K: np.ndarray, T: int, cfg: P4Config) -> int:
    """Anchor of an episode: the lowest KPI bucket in [T-6 h, T] (the start of the rise that produced the onset T), so
    'before the episode' means before the deterioration began, not before it was already underway."""
    a = max(0, T - 36 * 10 // cfg.bucket_min)
    seg = K[a:T + 1]
    if not np.isfinite(seg).any():
        return T
    return int(a + np.nanargmin(seg))


def pick_controls(anchors: np.ndarray, K: np.ndarray, window_id: np.ndarray, cfg: P4Config, seed: int,
                  exclude: np.ndarray | None = None) -> list[tuple[int, int]]:
    """Up to ctrl_per_ep control times per episode anchor: same analysis window, K(c) scored, no onset (any raw onset in
    `exclude`, default the anchors) within +-24 h, matched on the KPI trajectory - K at the anchor and 12 h earlier
    (nearest in both, equal weight) - with a seeded tie-break. Returns [(episode_index, control_row)]."""
    rng = np.random.default_rng(seed)
    n = len(K)
    far = np.ones(n, dtype=bool)
    day = 24 * 60 // cfg.bucket_min
    for o in (anchors if exclude is None else np.r_[anchors, exclude]).astype(int):
        far[max(0, o - day): o + day + 1] = False
    back = 12 * 60 // cfg.bucket_min
    k12 = lagged(K, back)
    out, used = [], set()
    for e, o in enumerate(anchors):
        cand = np.flatnonzero(far & (window_id == window_id[o]) & np.isfinite(K) & np.isfinite(k12))
        cand = np.array([c for c in cand if c not in used and c >= back], dtype=int)
        if cand.size == 0:
            continue
        cand = cand[rng.permutation(cand.size)]
        r12 = k12[o] if np.isfinite(k12[o]) else np.nanmedian(K)
        dist = np.abs(K[cand] - K[o]) + np.abs(k12[cand] - r12)
        order = np.argsort(dist, kind="mergesort")
        for c in cand[order[: cfg.ctrl_per_ep]]:
            out.append((e, int(c)))
            used.add(int(c))
    return out


def first_lead(x: np.ndarray, sign: int, thr: float, T: int, cfg: P4Config, min_cov: float = 0.5) -> float:
    """Minutes between the first NEW sustained threshold crossing inside [T-12 h, T) and T. A crossing counts only if
    its run starts inside the window after >= alarm_persist_buckets clear buckets (a condition already active when
    the window opens is not a lead) and reaches alarm_persist_buckets before T.
    NaN = evaluable but no new crossing; -1.0 = NOT EVALUABLE (feature coverage in the window < min_cov), so missing
    data can never count as a 'miss' for episodes or controls."""
    w = cfg.ep_window_h * 60 // cfg.bucket_min
    a = max(0, T - w)
    seg = x[a:T]
    if seg.size == 0 or np.isfinite(seg).mean() < min_cov:
        return -1.0
    p = cfg.alarm_persist_buckets
    beyond = np.where(np.isfinite(seg), sign * seg >= sign * thr, False)
    rl = run_lengths(beyond)
    for h in np.flatnonzero(rl == p):
        start = h - p + 1
        if start >= p and not beyond[start - p:start].any():
            return float((T - (a + start)) * cfg.bucket_min)
    return np.nan


# ============================================================================== alarms / false leads
def alarm_onsets(x: np.ndarray, sign: int, thr: float, cfg: P4Config) -> np.ndarray:
    """Causal alarm onsets: the bucket at which the feature has been beyond the directional threshold for
    alarm_persist_buckets consecutive buckets, with no beyond-threshold bucket in the alarm_refractory_h before the
    run started. Known at t (uses x <= t only)."""
    beyond = np.where(np.isfinite(x), sign * x >= sign * thr, False)
    rl = run_lengths(beyond)
    ref = cfg.alarm_refractory_h * 60 // cfg.bucket_min
    recent = trailing_mean(beyond.astype(float), ref, 1)          # share beyond over (t-ref, t]
    out = []
    for i in np.flatnonzero(rl == cfg.alarm_persist_buckets):
        s = i - cfg.alarm_persist_buckets + 1                     # run start
        if s == 0 or recent[s - 1] == 0:
            out.append(i)
    return np.asarray(out, dtype=int)


def future_max_rise(K: np.ndarray, running: np.ndarray, h: int) -> np.ndarray:
    """max K over (t, t+h] - K(t) (FUTURE-ONLY evaluation quantity). Defined only when every bucket in (t, t+h] is
    RUNNING and >= 2/3 of them carry a KPI value (no post-restart KPI jumps, no partial windows)."""
    n = len(K)
    s = np.column_stack([np.r_[K[j:], np.full(j, np.nan)] for j in range(1, h + 1)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mx = np.nanmax(s, axis=1)
    nr = np.concatenate([[0], np.cumsum(~running)])
    i = np.arange(n)
    end = np.minimum(i + h, n - 1)
    ok = (nr[end + 1] - nr[i + 1] == 0) & (i + h < n)
    return np.where(ok & np.isfinite(K) & (np.isfinite(s).sum(axis=1) >= int(np.ceil(2 * h / 3))), mx - K, np.nan)
