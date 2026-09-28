"""Shared, read-only analysis context and the relationship engine used by the analyze_afr_* steps and sensitivity.

Temporal design
  * Explanatory AFR features at t use AFR buckets <= t only (trailing 1-h level, its lag k, its 1-h change).
  * Controls use data <= t only. The dependent variable is the only forward-looking object (FUTURE_CHANGE).
  * DISCOVERY (Apr-May) selects the lag per (target, analysis type) and its sign; JUN, JUL, REPLICATION (Jun+Jul) and the
    AUGUST HOLDOUT are evaluated at that lag only. A FUTURE_CHANGE row's horizon must end inside its window.
Analysis types (RUNNING 10-min buckets)
  LAGGED_LEVEL(k)   x = AFR 1-h level at t-k; y = target bucket at t;
                    Z = feed level (t), feed level (t-k), coal-kiln and PC-coal levels (t-k), elapsed time.
  FUTURE_CHANGE(h)  x = AFR 1-h change ending at t; y = median target over (t+h-30 min, t+h] - target(t) (Phase 4
                    future_target); Z = target(t), target 1-h momentum, feed level, 1-h feed / coal / PC changes (<= t).
                    For the KPI the Phase 4 controls (K, momentum, Kpend) replace target(t) / momentum.
  MOMENTUM(0)       x = AFR 1-h change; y = target 1-h change over the same hour (contemporaneous co-movement);
                    Z = 1-h feed / coal / PC changes, elapsed time.
For LOAD targets feed controls are dropped (feed is the target family); for the co-manipulated fuel targets (coal, PC)
the other fuel control is kept but the target itself is never a control.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from af_core import (CACHE, FEED_TAG, KPI_INPUT_NOTE, P1_OUT, P4CFG, PRIMARY, P5Config, block_ids, circular_shift, ic,
                     evidence_label, holdout_label, stability_label)
import p4common

KPI_INPUTS = {"Kiln-I!F", "Kiln-I!G", "Kiln-I!AF", "Kiln-II!G"}   # Phase 3 KPI inputs among the targets (checked in G2)
FUEL_CTRL = ("Kiln-I!H", "Kiln-I!I")
WIN_DEF = {"DISCOVERY": ("DISCOVERY",), "JUN": ("JUN",), "JUL": ("JUL",), "REPLICATION": ("JUN", "JUL"),
           "HOLDOUT_AUG": ("AUG",)}
LAGS = {"LAGGED_LEVEL": PRIMARY.level_lags, "FUTURE_CHANGE": PRIMARY.horizons, "MOMENTUM": (0,)}


@dataclass
class Context:
    cfg: P5Config
    index: pd.DatetimeIndex
    running: np.ndarray
    window: np.ndarray
    filt: np.ndarray
    afr: np.ndarray
    b: pd.DataFrame
    g: pd.DataFrame
    blocks: np.ndarray
    t_min: np.ndarray
    terciles: list


def L(x: np.ndarray) -> np.ndarray:
    """Trailing 1-h level: median of buckets in (t-60 min, t], >= 3 of 6 valid (Phase 4 LEVEL_1H rule)."""
    return ic.trailing_median(x, 6, 3)


def d1h(x: np.ndarray) -> np.ndarray:
    lv = L(x)
    return lv - ic.lagged(lv, 6)


def seed_of(*parts) -> int:
    """Process-independent seed (Python's hash() is salted per process)."""
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def load_context(cfg: P5Config = PRIMARY) -> Context:
    b = pd.read_parquet(CACHE / "buckets.parquet")
    g = pd.read_parquet(CACHE / "kpi_grid.parquet")
    run = b.bucket_state.eq("RUNNING").to_numpy()
    st = b.bucket_state.to_numpy()
    filt = np.ones(len(b), dtype=bool)
    if cfg.exclude_post_restart_h > 0:          # past-only filter
        n = int(cfg.exclude_post_restart_h * 6)
        filt &= ~(ic.trailing_mean((st != "RUNNING").astype(float), n, 1) > 0)
    if cfg.exclude_pre_stop_h > 0:              # ANALYSIS FILTER ONLY (uses the future stop time; never a feature)
        n = int(cfg.exclude_pre_stop_h * 6)
        stop = (st != "RUNNING").astype(float)
        filt &= ~(np.r_[ic.trailing_mean(stop, n, 1)[n:], np.zeros(n)] > 0)
    if cfg.dq_good_only:
        filt &= g.data_quality.to_numpy() == "GOOD"
    win = p4common.month_of(b.index, P4CFG)
    feed_l = L(np.where(run, b[FEED_TAG].to_numpy(float), np.nan))
    d = feed_l[(win == "DISCOVERY") & run & np.isfinite(feed_l)]
    terc = [float(np.quantile(d, 1 / 3)), float(np.quantile(d, 2 / 3))]     # discovery-only, frozen
    if cfg.feed_tercile == 1:
        filt &= (feed_l > terc[0]) & (feed_l <= terc[1])
    afr = np.where(run, b[cfg.afr_series].to_numpy(float), np.nan)
    t_min = (b.index - b.index[0]).total_seconds().to_numpy() / 60.0
    return Context(cfg, b.index, run, win, filt, afr, b, g, block_ids(b.index, cfg.block_days), t_min, terc)


def target_series(ctx: Context, tag: str) -> np.ndarray:
    if tag.startswith("KPI:"):
        return ctx.g[tag.split(":")[1]].to_numpy(float)
    return np.where(ctx.running, ctx.b[tag].to_numpy(float), np.nan)


def window_span(ctx: Context, name: str) -> np.ndarray:
    ok = np.zeros(len(ctx.index), dtype=bool)
    for w in WIN_DEF[name]:
        a, b = (pd.Timestamp(s) for s in P4CFG.windows()[w])
        ok |= (ctx.index >= a) & (ctx.index <= b)
    return ok


def rows_for(ctx: Context, name: str, h: int = 0) -> np.ndarray:
    """RUNNING, filtered rows of analysis window `name`; with h > 0 the horizon (t, t+h] must end inside the window."""
    ok = np.zeros(len(ctx.index), dtype=bool)
    for w in WIN_DEF[name]:
        a, b = (pd.Timestamp(s) for s in P4CFG.windows()[w])
        ok |= (ctx.index >= a) & (ctx.index + pd.Timedelta(minutes=10 * h) <= b)
    return ok & ctx.running & ctx.filt


def design(ctx: Context, family: str, tag: str, atype: str, lag: int, afr: np.ndarray | None = None
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """(x, y, Z) for one relationship; lag in minutes. `afr` overrides the AFR series (negative controls)."""
    cfg = ctx.cfg
    a = ctx.afr if afr is None else afr
    y0 = target_series(ctx, tag)
    k = lag // 10
    feed = target_series(ctx, FEED_TAG)
    fuel = [target_series(ctx, t) for t in FUEL_CTRL if t != tag]
    use_feed = cfg.use_feed_controls and family != "LOAD"
    use_fuel = cfg.use_feed_controls and family != "INDICATOR"   # the Phase 4 indicator IS the PC-coal trend
    Z = []
    if atype == "LAGGED_LEVEL":
        x, y = ic.lagged(L(a), k), y0
        if use_feed:
            Z += [L(feed), ic.lagged(L(feed), k)]
        if use_fuel:
            Z += [ic.lagged(L(f), k) for f in fuel]
        Z.append(ctx.t_min)
    elif atype == "FUTURE_CHANGE":
        x = d1h(a)
        y = ic.future_target(y0, ctx.running, k, cfg.target_smooth)
        if tag == "KPI:K":
            m = json.loads((CACHE / "kpi_scale.json").read_text())
            Z = list(ic.controls(y0, ctx.g.D.to_numpy(float), k, m["m"], m["q_anchor"]).T)
        else:
            Z = [y0, y0 - ic.lagged(y0, 6)]
        if use_feed:
            Z += [L(feed), d1h(feed)]
        if use_fuel:
            Z += [d1h(f) for f in fuel]
    elif atype == "MOMENTUM":
        x, y = d1h(a), d1h(y0)
        if use_feed:
            Z.append(d1h(feed))
        if use_fuel:
            Z += [d1h(f) for f in fuel]
        Z.append(ctx.t_min)
    else:
        raise ValueError(atype)
    return x, y, np.column_stack(Z) if Z else None


def assoc_one(ctx: Context, family: str, tag: str, atype: str, lag: int, w: str, boot: bool = True,
              afr: np.ndarray | None = None) -> dict:
    x, y, Z = design(ctx, family, tag, atype, lag, afr)
    rows = rows_for(ctx, w, lag // 10 if atype == "FUTURE_CHANGE" else 0)
    cfg = ctx.cfg
    r = ic.assoc(x, y, Z, rows, ctx.blocks, seed_of(cfg.seed, tag, atype, lag, w) if boot else None,
                 cfg.neff_maxlag, cfg.min_n, cfg.n_boot)
    ok = rows & np.isfinite(x) & np.isfinite(y)            # same row mask as indicator_core.assoc (Phase 4, not
    if Z is not None:                                      # modifiable here); keep in sync if assoc ever changes
        ok &= np.isfinite(Z).all(axis=1)
    r["days"] = int(np.unique(ctx.index[ok].normalize()).size)
    return r


def select_lag(d: pd.DataFrame, lags, fixed: int) -> int:
    """Discovery lag choice: smallest BH q, ties -> largest |rho|, then shortest lag (Phase 4 rule)."""
    if fixed >= 0 and fixed in lags:
        return fixed
    dt = d[d.rho_p.notna()]
    if dt.empty:
        return lags[0]
    dt = dt.assign(a=dt.rho_p.abs())
    return int(dt.sort_values(["q", "a", "lag"], ascending=[True, False, True], kind="mergesort").lag.iloc[0])


def relate_family(ctx: Context, family: str, tags: list[str], meta: pd.DataFrame, lg=None,
                  with_null: bool = True, boot: bool = True) -> pd.DataFrame:
    """Full lag grid in DISCOVERY -> BH (family x type) -> discovery lag choice -> evaluation windows at that lag ->
    circular-shift negative control -> pre-declared evidence labels."""
    out = []
    for atype, lags in LAGS.items():
        d = pd.DataFrame([{"tag": t, "lag": lag, **assoc_one(ctx, family, t, atype, lag, "DISCOVERY", boot)}
                          for t in tags for lag in lags])
        d["q"] = ic.bh(d.p_eff.to_numpy())
        for tag in tags:
            dt = d[d.tag.eq(tag)]
            sel = select_lag(dt, lags, ctx.cfg.fixed_lag)
            res = {"DISCOVERY": dt[dt.lag.eq(sel)].iloc[0].to_dict()}
            for w in ("JUN", "JUL", "REPLICATION", "HOLDOUT_AUG"):
                res[w] = assoc_one(ctx, family, tag, atype, sel, w, boot)
            null = negative_control(ctx, family, tag, atype, sel, res) if with_null else {"null_pass": None}
            r0 = res["DISCOVERY"]
            ev = {"n": r0["n"], "n_eff": r0["n_eff"], "days": r0["days"], "rho": r0["rho_p"], "q": r0["q"],
                  "ci_lo": r0["ci_lo"], "ci_hi": r0["ci_hi"], "repl_rho": res["REPLICATION"]["rho_p"],
                  "repl_p": res["REPLICATION"]["p_eff"],
                  "holdout": holdout_label(r0["rho_p"], res["HOLDOUT_AUG"]["rho_p"], res["HOLDOUT_AUG"]["p_eff"]),
                  "null_pass": null["null_pass"]}
            evidence = evidence_label(ev, ctx.cfg)
            stab = stability_label(r0["rho_p"], res["JUN"]["rho_p"], res["JUL"]["rho_p"])
            flags = flags_for(tag, family)
            for w, r in res.items():
                out.append(make_row(family, tag, atype, sel, w, "SELECTED_LAG", r, r0["q"] if w == "DISCOVERY" else np.nan,
                                    stab, ev["holdout"], evidence, flags, null, meta, ev))
            for _, r in dt[~dt.lag.eq(sel)].iterrows():
                out.append(make_row(family, tag, atype, int(r.lag), "DISCOVERY", "LAG_PROFILE", r.to_dict(), r.q, "", "",
                                    "", flags, None, meta, None))
        if lg:
            lg.info("%s %s: %d targets done", family, atype, len(tags))
    return pd.DataFrame(out)


def negative_control(ctx: Context, family: str, tag: str, atype: str, lag: int, res: dict) -> dict:
    """Circular shift of AFR by 2..21 days within DISCOVERY and within REPLICATION (window-contiguous positions).
    null_pass: observed |rho| above the 95th percentile of shifted |rho| in BOTH windows (None if not evaluable)."""
    out = {"null_pass": None}
    for w in ("DISCOVERY", "REPLICATION"):
        obs = res[w]["rho_p"]
        out[f"null_q95_{w.lower()}"] = np.nan
        if not np.isfinite(obs):
            out["null_pass"] = False if out["null_pass"] is not None else None
            continue
        span = window_span(ctx, w)
        vals = np.array([abs(assoc_one(ctx, family, tag, atype, lag, w, False,
                                       circular_shift(ctx.afr, span, dd * 144))["rho_p"])
                         for dd in ctx.cfg.shift_days])
        if not np.isfinite(vals).any():
            continue
        q95 = float(np.nanquantile(vals, 0.95))
        out[f"null_q95_{w.lower()}"] = q95
        ok = bool(abs(obs) > q95)
        out["null_pass"] = ok if out["null_pass"] is None else (out["null_pass"] and ok)
    return out


def flags_for(tag: str, family: str) -> str:
    f = []
    if tag in KPI_INPUTS:
        f.append("KPI_INPUT")
    if family in ("FUEL_CO_MANIPULATION", "INDICATOR"):
        f.append("CO_MANIPULATION_OF_CONTROL_INPUTS")
    if tag in ("Kiln-I!F", "Kiln-I!G"):
        f.append("SP_HEAT_DEFINITION_UNCONFIRMED")
    if tag == "Kiln-IIIA!M":
        f.append("NO_APRIL_DATA")
    if tag == "KPI:K":
        f.append("DISCOVERY_KPI_IS_IN_SAMPLE_REFERENCE")
    if tag in ("KPI:K", "KPI:D"):
        f.append("KPI_EFFICIENCY_HALF_IS_SP_HEAT_(LARGELY_EXPLAINED_BY_FIRING_RATES)")
    return "|".join(f)


def make_row(family, tag, atype, lag, w, role, r, q, stab, hold, evidence, flags, null, meta, ev) -> dict:
    rho = r.get("rho_p", np.nan)
    m = meta.loc[tag] if tag in meta.index else None
    row = {"afr_signal": "Kiln-I!K", "target_signal": tag,
           "target_original_name": m.original_name if m is not None else tag,
           "target_unit": m.unit if m is not None else "", "target_family": family, "analysis_type": atype,
           "lag_minutes": lag, "window": w, "row_role": role, "operating_state": "RUNNING",
           "load_condition": "ALL_FEED_ADJUSTED" if family != "LOAD" else "ALL_NOT_FEED_ADJUSTED",
           "sample_count": r.get("n", 0), "effective_sample_size": r.get("n_eff", np.nan), "effect_size": rho,
           "effect_metric": "partial Spearman rho", "confidence_interval_low": r.get("ci_lo", np.nan),
           "confidence_interval_high": r.get("ci_hi", np.nan), "p_value": r.get("p_eff", np.nan),
           "adjusted_p_value": q, "direction": ("POSITIVE" if rho > 0 else "NEGATIVE") if np.isfinite(rho) else "",
           "stability": stab, "holdout_result": hold, "evidence": evidence if role == "SELECTED_LAG" else "",
           "confidence": "PENDING_SENSITIVITY" if role == "SELECTED_LAG" else "", "flags": flags,
           "interpretation": interpret(family, tag, atype, lag, w, role, rho, evidence, hold, stab, flags, ev),
           "raw_spearman": r.get("rho_raw", np.nan), "days": r.get("days", np.nan)}
    if null is not None:
        row.update({k: v for k, v in null.items() if k != "null_pass"})
        row["negative_control_pass"] = null["null_pass"]
    return row


PHRASE = {"LAGGED_LEVEL": "the 1-h AFR level {lag} min earlier",
          "FUTURE_CHANGE": "the 1-h AFR change ending at t, against the target change over the next {lag} min,",
          "MOMENTUM": "the 1-h AFR change, against the same-hour target change,"}


def interpret(family, tag, atype, lag, w, role, rho, evidence, hold, stab, flags, ev) -> str:
    if role != "SELECTED_LAG" or w != "DISCOVERY":
        return ""
    if not np.isfinite(rho):
        return f"{evidence}: not evaluable ({tag}; RUNNING buckets insufficient or constant)."
    if evidence not in ("ASSOCIATED", "WEAK ASSOCIATION"):
        return (f"{evidence}: no supported co-variation between {PHRASE[atype].format(lag=lag).rstrip(',')} and {tag} "
                f"(discovery partial rho {rho:+.3f}, BH q {ev['q']:.3g}; Jun-Jul rho {ev['repl_rho']:+.3f}; stability "
                f"{stab}; August {hold}).")
    sgn = "higher" if rho > 0 else "lower"
    txt = (f"{evidence}: in DISCOVERY (Apr-May, RUNNING buckets) {PHRASE[atype].format(lag=lag)} co-varied with {sgn} "
           f"{tag} (partial rho {rho:+.3f}, BH q {ev['q']:.3g}); replication Jun-Jul rho {ev['repl_rho']:+.3f}; "
           f"stability {stab}; August holdout {hold}. ")
    if family in ("FUEL_CO_MANIPULATION", "INDICATOR"):
        txt += "Both variables are fuel control inputs: concurrent co-manipulation, not a process response. "
    else:
        txt += ("Adjusted for feed, coal / PC firing and time trend; operator co-intervention and unmeasured fuel "
                "properties (CV, moisture, composition) remain uncontrolled. ")
    if "KPI_INPUT" in flags:
        txt += KPI_INPUT_NOTE + ". "
    return txt + "AFR-associated, not AFR-caused; no set-point or operating action is implied."


def tag_meta() -> pd.DataFrame:
    t = pd.read_csv(P1_OUT / "process_tag_inventory.csv")
    t["tag"] = t.dataset + "!" + t.source_column
    m = t.set_index("tag")[["original_name", "detected_unit"]].rename(columns={"detected_unit": "unit"})
    extra = pd.DataFrame({"original_name": ["POC efficiency-deterioration KPI (Phase 3)", "Phase 3 raw deviation score D"],
                          "unit": ["0-100 POC score", "robust-z composite"]}, index=["KPI:K", "KPI:D"])
    return pd.concat([m, extra])


# ============================================================================== band contrasts (descriptive)
BAND_WINDOWS = ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG")


def boot_diff_median(a: np.ndarray, ba: np.ndarray, b: np.ndarray, bb: np.ndarray, n_boot: int, seed: int
                     ) -> tuple[float, float]:
    """95 % CI of median(a) - median(b) resampling calendar blocks jointly (a block contributes all its a and b rows)."""
    u = np.unique(np.r_[ba, bb])
    if u.size < 5:
        return np.nan, np.nan
    ga = {k: a[ba == k] for k in u}
    gb = {k: b[bb == k] for k in u}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        pick = u[rng.integers(0, u.size, u.size)]
        xa = np.concatenate([ga[k] for k in pick])
        xb = np.concatenate([gb[k] for k in pick])
        if xa.size and xb.size:
            out.append(np.median(xa) - np.median(xb))
    if len(out) < 10:
        return np.nan, np.nan
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def band_contrast(ctx: Context, family: str, tags: list[str], meta: pd.DataFrame, bands: dict, n_boot: int = 500
                  ) -> pd.DataFrame:
    """Median load-adjusted target in each AFR band minus the MEDIUM_AFR median (same window). Load adjustment: target
    minus its DISCOVERY median within the discovery feed decile (not applied to LOAD targets). OBSERVED, descriptive:
    band membership is strongly time-confounded (HIGH_AFR is almost absent after May)."""
    from af_core import BANDS, assign_band
    band = assign_band(ctx.afr, bands)
    feed = target_series(ctx, FEED_TAG)
    disc = rows_for(ctx, "DISCOVERY") & np.isfinite(feed)
    edges = np.unique(np.quantile(feed[disc], np.linspace(0, 1, 11)))
    fbin = np.clip(np.searchsorted(edges, feed, side="right") - 1, 0, len(edges) - 2)
    out = []
    for tag in tags:
        y = target_series(ctx, tag)
        if family != "LOAD":
            ok = disc & np.isfinite(y)
            med = pd.Series(y[ok]).groupby(fbin[ok]).median()
            y = y - med.reindex(fbin).to_numpy()
        for w in BAND_WINDOWS:
            rows = rows_for(ctx, w) & np.isfinite(y)
            ref = rows & (band == "MEDIUM_AFR")
            for bn in BANDS:
                if bn == "MEDIUM_AFR":
                    continue
                sel = rows & (band == bn)
                eff = float(np.median(y[sel]) - np.median(y[ref])) if sel.sum() >= 30 and ref.sum() >= 30 else np.nan
                lo, hi = (boot_diff_median(y[sel], ctx.blocks[sel], y[ref], ctx.blocks[ref], n_boot,
                                           seed_of(ctx.cfg.seed, tag, bn, w)) if np.isfinite(eff) else (np.nan, np.nan))
                m = meta.loc[tag] if tag in meta.index else None
                ci_ok = np.isfinite(lo) and lo * hi > 0
                out.append({"afr_signal": "Kiln-I!K", "target_signal": tag,
                            "target_original_name": m.original_name if m is not None else tag,
                            "target_unit": m.unit if m is not None else "", "target_family": family,
                            "analysis_type": f"BAND_CONTRAST_{bn}_VS_MEDIUM", "lag_minutes": 0, "window": w,
                            "row_role": "DESCRIPTIVE", "operating_state": "RUNNING",
                            "load_condition": "FEED_DECILE_ADJUSTED" if family != "LOAD" else "NOT_FEED_ADJUSTED",
                            "sample_count": int(sel.sum()), "effective_sample_size": int(np.unique(ctx.blocks[sel]).size),
                            "effect_size": eff, "effect_metric": "median difference vs MEDIUM_AFR (target units)",
                            "confidence_interval_low": lo, "confidence_interval_high": hi, "p_value": np.nan,
                            "adjusted_p_value": np.nan,
                            "direction": ("POSITIVE" if eff > 0 else "NEGATIVE") if np.isfinite(eff) else "",
                            "stability": "", "holdout_result": "",
                            "evidence": "OBSERVED" if np.isfinite(eff) else "INSUFFICIENT DATA",
                            "confidence": "NOT_APPLICABLE", "flags": flags_for(tag, family) + "|TIME_CONFOUNDED_BANDS",
                            "interpretation": (f"OBSERVED: {bn} buckets differ from MEDIUM_AFR buckets by {eff:+.3g} "
                                               f"(95 % block CI {'excludes' if ci_ok else 'includes'} 0). Descriptive; band "
                                               "occupancy drifts over time, so this is not an AFR-level effect.")
                            if np.isfinite(eff) else "INSUFFICIENT DATA: < 30 buckets in the band or in MEDIUM_AFR."})
    return pd.DataFrame(out)


# ============================================================================== AFR transition-episode responses
EP_WINDOWS = {"POOLED_APR_JUL": ("DISCOVERY", "JUN", "JUL"), "DISCOVERY": ("DISCOVERY",), "REPLICATION": ("JUN", "JUL"),
              "HOLDOUT_AUG": ("AUG",)}


def load_episodes() -> tuple[pd.DataFrame, pd.DataFrame]:
    ep = pd.read_csv(CACHE / "episodes.csv", parse_dates=["T"])
    ctrl = pd.read_csv(CACHE / "episode_controls.csv")
    return ep, ctrl


def paired_stats(dif: np.ndarray, blocks: np.ndarray, n_boot: int, seed: int) -> tuple[float, float, float]:
    from af_core import boot_median
    if dif.size == 0:
        return np.nan, np.nan, np.nan
    lo, hi = boot_median(dif, blocks, n_boot, seed)
    return float(np.median(dif)), lo, hi


def label_permutation_p(de: np.ndarray, dc: list[np.ndarray], n_perm: int, seed: int) -> float:
    """Randomised transition labels: within each matched set {episode, its controls} the 'episode' label is re-assigned
    at random; statistic = median over sets of (labelled delta - mean of the others). Two-sided empirical p."""
    sets = [np.r_[e, c] for e, c in zip(de, dc)]
    obs = np.median([s[0] - s[1:].mean() for s in sets])
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for i in range(n_perm):
        vals = []
        for s in sets:
            j = rng.integers(0, s.size)
            vals.append(s[j] - np.delete(s, j).mean())
        null[i] = np.median(vals)
    return float((1 + np.sum(np.abs(null) >= abs(obs))) / (1 + n_perm))


def episode_response(ctx: Context, family: str, tags: list[str], meta: pd.DataFrame, ep: pd.DataFrame | None = None,
                     ctrl: pd.DataFrame | None = None, post_windows=None, drop_load_coincident: bool = False
                     ) -> pd.DataFrame:
    """Per AFR transition type x post window x target: paired difference of the anchor-relative response
    (median over (T+a, T+b] - median over [T-60, T)) between each ELIGIBLE episode and the mean of its controls.
    POOLED_APR_JUL is the primary test (August never enters it); DISCOVERY / REPLICATION / HOLDOUT_AUG are reported."""
    from af_core import window_delta
    cfg = ctx.cfg
    if ep is None:
        ep, ctrl = load_episodes()
    post_windows = post_windows or cfg.post_windows
    e = ep[ep.status.eq("ELIGIBLE")]
    if drop_load_coincident:
        e = e[~e.load_coincident.astype(bool)]
    cmap = ctrl.groupby("episode_id").control_pos.apply(list).to_dict()
    e = e[e.episode_id.isin(cmap)]
    out = []
    for tag in tags:
        y = target_series(ctx, tag)
        for a, b in post_windows:
            dl = window_delta(y, a // 10, b // 10)
            for typ, et in e.groupby("afr_transition", sort=True):
                de = dl[et.pos.to_numpy()]
                dc = [dl[np.asarray(cmap[i])] for i in et.episode_id]
                keep = np.isfinite(de) & np.array([np.isfinite(c).sum() >= 1 for c in dc])
                wins = et.window.to_numpy()
                res = {}
                for wn, members in EP_WINDOWS.items():
                    k = keep & np.isin(wins, members)
                    dif = np.array([de[i] - np.nanmean(dc[i]) for i in np.flatnonzero(k)])
                    blk = ctx.blocks[et.pos.to_numpy()[k]]
                    med, lo, hi = paired_stats(dif, blk, cfg.n_boot, seed_of(cfg.seed, tag, typ, a, b, wn))
                    p = (label_permutation_p(de[k], [c[np.isfinite(c)] for c, kk in zip(dc, k) if kk], cfg.n_perm,
                                             seed_of(cfg.seed, "perm", tag, typ, a, b, wn))
                         if wn == "POOLED_APR_JUL" and k.sum() >= cfg.min_episodes and cfg.n_perm > 0 else np.nan)
                    res[wn] = {"n": int(k.sum()), "eff": med, "lo": lo, "hi": hi, "p": p,
                               "days": int(np.unique(ctx.index[et.pos.to_numpy()[k]].normalize()).size)}
                for wn, r in res.items():
                    m = meta.loc[tag] if tag in meta.index else None
                    out.append({"afr_signal": "Kiln-I!K", "target_signal": tag,
                                "target_original_name": m.original_name if m is not None else tag,
                                "target_unit": m.unit if m is not None else "", "target_family": family,
                                "analysis_type": f"EPISODE_{typ}", "lag_minutes": b,
                                "window_compared": f"(T+{a}, T+{b}] vs [T-60, T)", "window": wn,
                                "row_role": "EPISODE_PRIMARY" if wn == "POOLED_APR_JUL" else "EPISODE_WINDOW",
                                "operating_state": "RUNNING (whole episode window)",
                                "load_condition": "CONTROLS_MATCHED_ON_FEED_LEVEL", "sample_count": r["n"],
                                "effective_sample_size": r["days"], "effect_size": r["eff"],
                                "effect_metric": "median paired difference episode - matched controls (target units)",
                                "confidence_interval_low": r["lo"], "confidence_interval_high": r["hi"],
                                "p_value": r["p"], "adjusted_p_value": np.nan,
                                "direction": ("POSITIVE" if r["eff"] > 0 else "NEGATIVE") if np.isfinite(r["eff"]) else "",
                                "flags": flags_for(tag, family), "res_": res})
    df = pd.DataFrame(out)
    if df.empty:
        return df
    prim = df.row_role.eq("EPISODE_PRIMARY")
    df.loc[prim, "adjusted_p_value"] = ic.bh(df.loc[prim, "p_value"].to_numpy())
    labels = []
    for r in df.itertuples():
        labels.append(episode_labels(r, cfg))
    df["stability"], df["holdout_result"], df["evidence"], df["interpretation"] = zip(*labels)
    df["confidence"] = np.where(df.row_role.eq("EPISODE_PRIMARY"), "PENDING_SENSITIVITY", "")
    return df.drop(columns=["res_"])


def episode_labels(r, cfg) -> tuple[str, str, str, str]:
    res = r.res_
    d, rp, ho, pool = res["DISCOVERY"], res["REPLICATION"], res["HOLDOUT_AUG"], res["POOLED_APR_JUL"]
    s = [np.sign(x["eff"]) for x in (d, rp) if x["n"] >= 5 and np.isfinite(x["eff"])]
    stab = "INSUFFICIENT" if len(s) < 2 else ("STABLE_SIGN" if s[0] == s[1] else "SIGN_FLIP")
    if ho["n"] < 3 or not np.isfinite(ho["eff"]) or not np.isfinite(pool["eff"]):
        hold = "NOT_EVALUABLE"
    else:
        same = np.sign(ho["eff"]) == np.sign(pool["eff"])
        sig = np.isfinite(ho["lo"]) and ho["lo"] * ho["hi"] > 0
        hold = ("CONFIRMED" if sig else "SAME_DIRECTION_NS") if same else ("REVERSED" if sig else "OPPOSITE_DIRECTION_NS")
    if r.row_role != "EPISODE_PRIMARY":
        return stab, hold, "", ""
    ci = np.isfinite(pool["lo"]) and pool["lo"] * pool["hi"] > 0
    q = r.adjusted_p_value
    if pool["n"] < cfg.min_episodes:
        ev = "INSUFFICIENT DATA"
    elif q < cfg.q_assoc and ci and stab == "STABLE_SIGN" and hold != "REVERSED":
        ev = "ASSOCIATED"
    elif q < cfg.q_weak and ci:
        ev = "WEAK ASSOCIATION"
    else:
        ev = "NOT SUPPORTED"
    txt = (f"{ev}: in the window {r.window_compared} around {pool['n']} eligible {r.analysis_type[8:]} episodes (Apr-Jul), "
           f"the change of {r.target_signal} differed from feed-matched no-transition controls by a median {pool['eff']:+.3g} "
           f"[{pool['lo']:+.3g}, {pool['hi']:+.3g}] (label-permutation p {r.p_value:.3g}, BH q {q:.3g}); stability {stab}; "
           f"August {hold}. Episode windows exclude stops / restarts; PC coal and feed can change in the same window and the "
           "operator's reason for the AFR change is unknown. "
           "AFR-associated, not AFR-caused.") if np.isfinite(pool["eff"]) else f"{ev}: too few eligible episodes."
    return stab, hold, ev, txt


def run_families(families: list[str], out_name: str, lg) -> pd.DataFrame:
    """Driver shared by the analyze_afr_* steps: correlation engine + band contrasts + transition episodes."""
    from af_core import FAMILIES, REL_COLUMNS, write_csv
    ctx = load_context()
    meta = tag_meta()
    bands = json.loads((CACHE / "bands.json").read_text())
    parts = []
    for fam in families:
        tags = FAMILIES[fam]
        parts += [relate_family(ctx, fam, tags, meta, lg), band_contrast(ctx, fam, tags, meta, bands),
                  episode_response(ctx, fam, tags, meta)]
        lg.info("%s done", fam)
    df = pd.concat(parts, ignore_index=True)
    cols = REL_COLUMNS + [c for c in df.columns if c not in REL_COLUMNS]
    write_csv(df[cols], out_name, lg)
    return df
