"""The pre-declared endpoint engine (spec sections 4, 6, 13) and the temporal analyses built on it.

endpoint(): per event, the window statistic W(T0) minus the median W of its matched eligible controls; PE = the median
excess over evaluable events. Inference: one-sided randomisation p against NC2 (matched random pseudo-onsets drawn
from eligible controls); 95 % CI by bootstrap (events i.i.d., controls in calendar blocks within their match group).
Effect size: matched Cliff's delta. All randomness is seeded with a stable CRC32 of the analysis label.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

import build_controls as bc
import calibration
import warning_metrics as wm
from p8common import CFG, MONTHS, WARNINGS, P8Config, ic, nb, risk_core


def seed_of(label: str, cfg: P8Config = CFG) -> int:
    return (cfg.seed + zlib.crc32(label.encode())) % (2 ** 32)


def boot_medians(vals: np.ndarray, blocks: np.ndarray, n_boot: int, seed: int) -> np.ndarray:
    """(n_boot,) medians of `vals` under calendar-block resampling (Phase 7 weighted-quantile bootstrap)."""
    b = np.unique(blocks, return_inverse=True)[1]
    return risk_core.boot_quantiles(np.asarray(vals, float), b, (0.5,), n_boot, seed)[:, 0]


def endpoint(x: np.ndarray, B: dict, h: int, label: str, cfg: P8Config = CFG, key: np.ndarray | None = None,
             ev_mask: np.ndarray | None = None, ctrl_mask: np.ndarray | None = None, anchor: str = "pos_T0",
             block_hours: int | None = None, boot: bool = True, W: np.ndarray | None = None,
             elig: np.ndarray | None = None, null: bool = True, ev_window: int | None = None) -> dict:
    """ev_window: minutes of (T0 - ev_window, T0] that must be free of other candidate periods and Phase 1 DQ
    windows (default h; only for the onset anchor - the post-end / detection diagnostics lie inside the period)."""
    ev = B["events"]
    W = wm.window_stat(x, h) if W is None else W
    key = B["month"] if key is None else key
    elig = (B["elig"][h] if elig is None else elig) & np.isfinite(W) & (True if ctrl_mask is None else ctrl_mask)
    pos_c = np.flatnonzero(elig)
    block_hours = block_hours or cfg.block_hours
    blocks = bc.block_ids(B["ix"], block_hours)
    p_e = ev[anchor].to_numpy()
    v_e = W[p_e]
    k_e = key[p_e]
    ok = ev.evaluable.to_numpy() & np.isfinite(v_e) & (True if ev_mask is None else np.asarray(ev_mask, bool))
    n_prior = 0
    if anchor == "pos_T0":
        free = bc.all_in_window(B["cand_free"] & ~B["dq"], nb(h if ev_window is None else ev_window))[p_e]
        n_prior = int((ok & ~free).sum())
        ok &= free
    groups = {}
    for g in sorted(set(k_e[ok].tolist())):
        pc = pos_c[key[pos_c] == g]
        if pc.size >= cfg.min_controls:
            groups[g] = (np.sort(W[pc]), W[pc], blocks[pc])
    ok &= np.array([k in groups for k in k_e])
    n_ok = int(ok.sum())
    excess = np.full(len(ev), np.nan)
    pct = np.full(len(ev), np.nan)
    for i in np.flatnonzero(ok):
        srt = groups[k_e[i]][0]
        excess[i] = v_e[i] - np.median(srt)
        lo, hi = np.searchsorted(srt, v_e[i], "left"), np.searchsorted(srt, v_e[i], "right")
        pct[i] = (lo + 0.5 * (hi - lo)) / srt.size
    res = {"label": label, "horizon_minutes": h, "n_events": len(ev), "n_evaluable": n_ok,
           "n_controls": int(sum(g[0].size for g in groups.values())), "event_value": v_e, "excess": excess,
           "control_pct": pct, "ok": ok, "pe": float(np.median(excess[ok])) if n_ok else np.nan,
           "median_event": float(np.median(v_e[ok])) if n_ok else np.nan,
           "median_control": float(np.median(np.concatenate([groups[k][0] for k in groups]))) if groups else np.nan,
           "cliffs_delta": float(np.mean(2 * pct[ok] - 1)) if n_ok else np.nan,
           "n_excluded_other_period_in_window": n_prior}
    if not n_ok or not null:
        return {**res, "p_value": np.nan, "ci_low": np.nan, "ci_high": np.nan, "null_median": np.nan}
    rng = np.random.default_rng(seed_of(label + "|null", cfg))
    idx = np.flatnonzero(ok)
    null_ex = np.empty((cfg.n_null, n_ok))
    for j, i in enumerate(idx):
        srt = groups[k_e[i]][0]
        null_ex[:, j] = srt[rng.integers(0, srt.size, cfg.n_null)] - np.median(srt)
    null = np.median(null_ex, axis=1)
    res["null"] = null
    res["null_median"] = float(np.median(null))
    res["p_value"] = float((1 + np.sum(null >= res["pe"])) / (1 + cfg.n_null))
    if boot:
        meds = {g: boot_medians(v[1], v[2], cfg.n_boot, seed_of(f"{label}|boot|{g}|{block_hours}", cfg))
                for g, v in groups.items()}
        rb = np.random.default_rng(seed_of(label + "|events", cfg))
        pick = idx[rb.integers(0, n_ok, (cfg.n_boot, n_ok))]
        M = np.column_stack([meds[k_e[i]] for i in idx])
        bs = np.median(v_e[pick] - M[np.arange(cfg.n_boot)[:, None], np.searchsorted(idx, pick)], axis=1)
        res["ci_low"], res["ci_high"] = (float(q) for q in np.quantile(bs, [0.025, 0.975]))
    else:
        res["ci_low"] = res["ci_high"] = np.nan
    return res


def primary_status(r: dict, loeo_min: float, cfg: P8Config = CFG) -> str:
    if r["n_evaluable"] < cfg.min_events_primary:
        return "INSUFFICIENT_DATA"
    if r["pe"] > 0 and r["ci_low"] > 0 and r["p_value"] < 0.05 and loeo_min > 0:
        return "SUPPORTED"
    if r["pe"] > 0 and (r["p_value"] < 0.10 or r["ci_low"] > 0):
        return "WEAK"
    return "NOT_SUPPORTED"


def secondary_status(r: dict, q: float, cfg: P8Config = CFG) -> str:
    if r["n_evaluable"] < cfg.min_events_secondary or r["n_controls"] < cfg.min_controls:
        return "INSUFFICIENT_DATA"
    if r["pe"] > 0 and r["ci_low"] > 0 and q < 0.05:
        return "SUPPORTED"
    if r["pe"] > 0 and (r["p_value"] < 0.10 or r["ci_low"] > 0):
        return "WEAK"
    return "NOT_SUPPORTED"


def loeo(x: np.ndarray, B: dict, h: int, label: str, cfg: P8Config = CFG, ev_mask: np.ndarray | None = None,
         **kw) -> np.ndarray:
    """PE with each event left out (no bootstrap); NaN for an event that is not evaluable."""
    W = wm.window_stat(x, h)
    ok = endpoint(x, B, h, f"{label}|loeo", cfg, ev_mask=ev_mask, boot=False, W=W, null=False, **kw)["ok"]
    out = np.full(len(ok), np.nan)
    for i in np.flatnonzero(ok):
        m = ok.copy()
        m[i] = False
        out[i] = endpoint(x, B, h, f"{label}|loeo{i}", cfg, ev_mask=m, boot=False, W=W, null=False, **kw)["pe"]
    return out


def summarise(r: dict) -> dict:
    return {k: r[k] for k in ("horizon_minutes", "n_events", "n_evaluable", "n_excluded_other_period_in_window",
                              "n_controls", "pe", "median_event", "median_control", "cliffs_delta", "ci_low",
                              "ci_high", "p_value", "null_median")}


# ============================================================================== warnings: coverage vs control rate
def warning_coverage(flag: np.ndarray, B: dict, h: int, ok: np.ndarray) -> dict:
    """EMPIRICAL_ABNORMAL_PERIOD_COVERAGE (share of evaluable events with a warning in (T0 - h, T0]) next to the
    control-window warning rate (share of eligible controls with a warning in (A - h, A]) and lead times."""
    anyw = wm.any_in_window(flag, h)
    p_e = B["events"].pos_T0.to_numpy()
    cov = anyw[p_e] & ok
    n = nb(h)
    leads = []
    for i in np.flatnonzero(cov):
        seg = flag[p_e[i] - n + 1:p_e[i] + 1]
        leads.append(10 * (n - 1 - int(np.flatnonzero(seg)[0])))
    rate = float(anyw[B["elig"][h]].mean()) if B["elig"][h].any() else np.nan
    lead = np.array(leads, float)
    q = (lambda p: float(np.quantile(lead, p)) if lead.size else np.nan)
    return {"n_covered": int(cov.sum()), "coverage": float(cov.sum() / max(ok.sum(), 1)), "control_window_rate": rate,
            "median_lead_time": q(0.5), "p25_lead_time": q(0.25), "p75_lead_time": q(0.75), "covered": cov}


def horizon_rows(sig: dict, B: dict, cfg: P8Config = CFG, label: str = "PRIMARY") -> tuple[pd.DataFrame, dict]:
    """Rank endpoint at every horizon (BH across horizons) + coverage / control rate / lead per warning."""
    res = {h: endpoint(sig["rank"], B, h, f"{label}|h{h}", cfg) for h in cfg.horizons}
    q = ic.bh(np.array([res[h]["p_value"] for h in cfg.horizons]))
    rows = []
    for (h, r), qq in zip(res.items(), q):
        st = secondary_status(r, qq, cfg)
        for w in WARNINGS:
            c = warning_coverage(sig["flags"][w], B, h, r["ok"])
            rows.append({"score_variant": label, "warning_type": w, **summarise(r), "bh_q": qq,
                         "median_rank_change": r["pe"], "effect_size": r["cliffs_delta"],
                         "bootstrap_ci_low": r["ci_low"], "bootstrap_ci_high": r["ci_high"],
                         "permutation_p": r["p_value"], "coverage": c["coverage"], "n_covered": c["n_covered"],
                         "median_lead_time": c["median_lead_time"], "p25_lead_time": c["p25_lead_time"],
                         "p75_lead_time": c["p75_lead_time"], "empirical_alert_rate": c["control_window_rate"],
                         "status": st, "is_primary": h == cfg.primary_h})
    return pd.DataFrame(rows), res


# ============================================================================== trajectories, months, holdout
def snapshot_effects(x: np.ndarray, B: dict, cfg: P8Config = CFG, label: str = "PRIMARY",
                     ev_mask: np.ndarray | None = None) -> pd.DataFrame:
    """Aligned snapshot x(T0 - o) minus the month-matched control median x(A - o), with bootstrap CI."""
    rows = []
    for o in cfg.offsets:
        lagx = ic.lagged(np.asarray(x, float), o // 10)
        el = bc.eligible(B["clean"], B["oper"], B["dq"], o + 10)       # clean up to and including the snapshot bucket
        r = endpoint(lagx, B, o, f"{label}|snap{o}", cfg, ev_mask=ev_mask, W=lagx, elig=el, ev_window=o + 10)
        rows.append({"section": "TRAJECTORY_SNAPSHOT", "variant": label, "offset_minutes": -o, **summarise(r)})
    return pd.DataFrame(rows)


def month_rows(x: np.ndarray, B: dict, cfg: P8Config = CFG, label: str = "PRIMARY") -> pd.DataFrame:
    rows = []
    ev = B["events"]
    for m, name in MONTHS.items():
        r = endpoint(x, B, cfg.primary_h, f"{label}|month{m}", cfg, ev_mask=ev.month.eq(m).to_numpy())
        rows.append({"section": "MONTH", "variant": label, "slice": name, **summarise(r),
                     "status": secondary_status(r, r["p_value"], cfg)})
    lomo = []
    for m, name in MONTHS.items():
        r = endpoint(x, B, cfg.primary_h, f"{label}|lomo{m}", cfg, ev_mask=ev.month.ne(m).to_numpy())
        lomo.append({"section": "LEAVE_ONE_MONTH_OUT", "variant": label, "slice": f"without {name}", **summarise(r),
                     "status": secondary_status(r, r["p_value"], cfg)})
    return pd.DataFrame(rows + lomo)


def month_holdout(sig: dict, B: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    """W2 / W4 with thresholds from earlier months' ordinary running only; evaluated on later months' events and
    later months' controls (coverage at the primary horizon next to the control-window rate)."""
    rows = []
    ordinary = B["elig"][0]
    fam = B["s"].family_count_abnormal.to_numpy(float)
    ok_all = endpoint(sig["rank"], B, cfg.primary_h, "HOLDOUT", cfg, boot=False, null=False)["ok"]
    for train, test in (((6,), (7, 8)), ((6,), (7,)), ((6, 7), (8,))):
        thr = calibration.prior_month_thresholds(sig, ordinary, B["month"], train, cfg)
        if thr["status"] != "OK":
            rows.append({"section": "MONTH_HOLDOUT", "train_months": str(train), "test_months": str(test),
                         "status": thr["status"]})
            continue
        flags = wm.warning_flags(sig, fam, {"slope": thr["slope"], "accel": thr["accel"]}, cfg)
        ev_m = B["events"].month.isin(test).to_numpy()
        test_ctrl = np.isin(B["month"], test)
        Bt = {**B, "elig": {k: v & test_ctrl for k, v in B["elig"].items()}}
        for w in ("W2_RISING", "W4_ACCEL"):
            c = warning_coverage(flags[w], Bt, cfg.primary_h, ok_all & ev_m)
            rows.append({"section": "MONTH_HOLDOUT", "warning_type": w, "train_months": str(train),
                         "test_months": str(test), "threshold_slope": thr["slope"], "threshold_accel": thr["accel"],
                         "n_evaluable": int((ok_all & ev_m).sum()), "coverage": c["coverage"],
                         "control_window_rate": c["control_window_rate"],
                         "coverage_minus_control_rate": c["coverage"] - c["control_window_rate"],
                         "status": "INSUFFICIENT_DATA" if (ok_all & ev_m).sum() < cfg.min_events_secondary
                         else "REPORTED"})
    rows.append({"section": "MONTH_HOLDOUT", "train_months": "none (Apr-May is in-sample reference)",
                 "test_months": "(6,)", "status": "THRESHOLD_VALIDATION_INSUFFICIENT",
                 "note": "June has no earlier out-of-sample month; only REF_APR_MAY thresholds apply to June"})
    return pd.DataFrame(rows)


def loeo_threshold_rows(sig: dict, B: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    """Held-out event-tuned threshold (P25 of the other events' W): target coverage vs all-control exceedance."""
    W = wm.window_stat(sig["rank"], cfg.primary_h)
    ev = B["events"]
    ok = endpoint(sig["rank"], B, cfg.primary_h, "LOEO_THR", cfg, W=W, boot=False, null=False)["ok"]
    v = np.where(ok, W[ev.pos_T0.to_numpy()], np.nan)
    thr = calibration.loeo_thresholds(v, cfg.loeo_q)
    ctrl = W[B["elig"][cfg.primary_h] & np.isfinite(W)]
    rows = []
    for i, e in enumerate(ev.itertuples()):
        rows.append({"section": "LOEO_EVENT_TUNED_THRESHOLD", "event_id": e.event_id, "event_value": v[i],
                     "threshold_from_other_events": thr[i], "held_out_covered": bool(v[i] >= thr[i])
                     if np.isfinite(v[i]) and np.isfinite(thr[i]) else np.nan,
                     "control_exceedance_rate": float(np.mean(ctrl >= thr[i])) if np.isfinite(thr[i]) else np.nan})
    return pd.DataFrame(rows)
