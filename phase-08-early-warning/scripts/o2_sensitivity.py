"""O2-excluded VALIDATION_VARIANT and the kiln-inlet O2 analyser (Kiln-I!X) behaviour (spec section 9).

The variant is Phase 7's EXCLUDE_KILN_INLET_O2_ANALYSER exactly (Phase 7 robustness.variant_grid / run_variant): the
COMBUSTION / STABILITY components are swapped for the cached *_EXCL_O2 rebuilds, a frozen Apr-May reference is fitted
with Phase 7's reference_builder, and Phase 7's score_core scores it. It never replaces the primary score.
Analyser readings are ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION: nothing here says the analyser is faulty.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import temporal_validation as tv
import warning_metrics as wm
from p8common import CFG, MONTHS, O2_TAG, P8Config, ic, p7c, reference_builder, risk_core

VARIANT = "EXCLUDE_KILN_INLET_O2_ANALYSER"
ANALYSER_LABEL = "ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION"


def o2_excluded_score(B: dict) -> tuple[np.ndarray, dict]:
    g = B["grid"].copy()
    for d in ("COMBUSTION", "STABILITY"):
        g[f"comp_{d}"] = g[f"comp_{d}_EXCL_O2"]
    cfg = p7c.variant(name="NO_O2X")
    ref = reference_builder.fit_reference(g, cfg, B["ctx"]["episodes"], B["ctx"])
    core = risk_core.score_core(g, ref, cfg, B["ctx"])
    return np.where(core["valid3"], core["R"], np.nan), ref


def _status(full, o2x) -> str:
    return "ROBUST_TO_O2" if full == o2x else "SENSITIVE_TO_O2"


def _num(metric: str, a: float, b: float, rho: float = np.nan, status: str = "DIFFERENCE_REPORTED") -> dict:
    return {"metric": metric, "full_score": a, "o2_excluded": b, "absolute_difference": b - a,
            "relative_difference": (b - a) / abs(a) if np.isfinite(a) and a != 0 else np.nan,
            "rank_correlation": rho, "status": status}


def comparison(P: dict, O: dict, res: dict, B: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    """res = {'PRIMARY': {...}, VARIANT: {...}} with keys primary / primary_status / horizon_df / load / months."""
    both = np.isfinite(P["score"]) & np.isfinite(O["score"])
    rho = float(stats.spearmanr(P["score"][both], O["score"][both]).statistic)
    a, b = res["PRIMARY"], res[VARIANT]
    rows = [_num("score_rank_correlation_operational_buckets", 1.0, rho, rho, "REPORTED"),
            _num("primary_endpoint_PE_60min", a["primary"]["pe"], b["primary"]["pe"], rho,
                 _status(a["primary_status"], b["primary_status"])),
            {"metric": "primary_endpoint_status", "full_score": a["primary_status"], "o2_excluded": b["primary_status"],
             "status": _status(a["primary_status"], b["primary_status"])},
            _num("primary_endpoint_PE_60min_same_event_set_as_primary", a["primary"]["pe"], b["same_set"]["pe"], rho),
            _num("primary_endpoint_p_same_event_set_as_primary", a["primary"]["p_value"], b["same_set"]["p_value"]),
            _num("n_evaluable_events", a["primary"]["n_evaluable"], b["primary"]["n_evaluable"]),
            _num("primary_endpoint_p", a["primary"]["p_value"], b["primary"]["p_value"]),
            _num("primary_endpoint_ci_low", a["primary"]["ci_low"], b["primary"]["ci_low"]),
            _num("primary_endpoint_cliffs_delta", a["primary"]["cliffs_delta"], b["primary"]["cliffs_delta"])]
    ha, hb = a["horizon_df"], b["horizon_df"]
    for h in cfg.horizons:
        ra = ha[(ha.horizon_minutes == h) & (ha.warning_type == "W1_RANK")].iloc[0]
        rb = hb[(hb.horizon_minutes == h) & (hb.warning_type == "W1_RANK")].iloc[0]
        rows.append(_num(f"rank_excess_{h}min", ra.median_rank_change, rb.median_rank_change, rho,
                         _status(ra.status, rb.status)))
    for w in P["flags"]:
        ra = ha[(ha.horizon_minutes == cfg.primary_h) & (ha.warning_type == w)].iloc[0]
        rb = hb[(hb.horizon_minutes == cfg.primary_h) & (hb.warning_type == w)].iloc[0]
        rows.append(_num(f"{w}_coverage_60min", ra.coverage, rb.coverage))
        rows.append(_num(f"{w}_control_window_rate_60min", ra.empirical_alert_rate, rb.empirical_alert_rate))
        rows.append(_num(f"{w}_empirical_alert_rate_time_share", a["alert_share"][w], b["alert_share"][w]))
    for m, name in MONTHS.items():
        mm = both & (B["month"] == m)
        rows.append(_num(f"median_score_{name}", float(np.median(P["score"][mm])), float(np.median(O["score"][mm]))))
        ma, mb = a["months"], b["months"]
        ra = ma[(ma.section == "MONTH") & (ma.slice == name)].iloc[0]
        rb = mb[(mb.section == "MONTH") & (mb.slice == name)].iloc[0]
        rows.append(_num(f"rank_excess_60min_{name}", ra.pe, rb.pe, rho, _status(ra.status, rb.status)))
    la = a["load"][cfg.primary_h]
    lb = b["load"][cfg.primary_h]
    for k in ("LOAD_ADJUSTED", "MATCHED_LOAD", "TRANSITION_EXCLUDED"):
        rows.append(_num(f"{k.lower()}_effect_60min", la[k]["pe"], lb[k]["pe"]))
    pa = a["pre_rank_change"]
    pb = b["pre_rank_change"]
    rows.append(_num("median_pre_onset_rank_change_6h", pa, pb))
    return pd.DataFrame(rows)


def analyser_behaviour(P: dict, B: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    """Where / when ambient-air-like kiln-inlet O2 readings (bucket median >= 15 %) occur and what they do to the score."""
    o2, oper = B["o2"] & B["oper"], B["oper"]
    comps = B["comps"]
    rows = []
    add = lambda m, v, note="": rows.append({"section": "O2_ANALYSER_BEHAVIOUR", "metric": m, "value": v,  # noqa: E731
                                             "status": ANALYSER_LABEL, "note": note})
    add("o2_ambient_suspect_share_operational", float(o2[oper].mean()), f"{O2_TAG} bucket median >= 15 % O2")
    for m, name in MONTHS.items():
        mm = oper & (B["month"] == m)
        add(f"o2_ambient_suspect_share_{name}", float(o2[mm].mean()))
    hi = oper & np.where(np.isfinite(P["rank"]), P["rank"] >= 0.90, False)
    add("share_of_rank_ge_p90_buckets_with_suspect_o2", float(o2[hi].mean()))
    add("share_of_rank_lt_p90_buckets_with_suspect_o2", float(o2[oper & ~hi].mean()))
    add("median_score_when_suspect", float(np.nanmedian(P["score"][o2])))
    add("median_score_when_not_suspect", float(np.nanmedian(P["score"][oper & ~o2])))
    for f in ("COMBUSTION", "STABILITY", "PERSISTENCE"):
        c = comps[f].to_numpy(float)
        add(f"mean_{f.lower()}_points_when_suspect", float(np.nanmean(c[o2])))
        add(f"mean_{f.lower()}_points_when_not_suspect", float(np.nanmean(c[oper & ~o2])))
    runs = ic.run_lengths(o2)
    ends = o2 & ~np.r_[o2[1:], False]
    add("median_suspect_run_minutes", float(np.median(runs[ends]) * 10) if ends.any() else np.nan)
    add("p90_suspect_run_minutes", float(np.quantile(runs[ends], 0.9) * 10) if ends.any() else np.nan)
    p0 = B["events"].pos_T0.to_numpy()
    in24 = wm.any_in_window(o2, cfg.lookback_min)
    in60 = wm.any_in_window(o2, cfg.primary_h)
    add("events_with_suspect_o2_in_60min_pre_window", int(in60[p0].sum()))
    add("events_with_suspect_o2_in_24h_pre_window", int(in24[p0].sum()))
    add("controls_with_suspect_o2_in_60min_window_share", float(in60[B["elig"][cfg.primary_h]].mean()))
    r = tv.endpoint(P["rank"], B, cfg.primary_h, "O2FREE_WINDOWS", cfg, ev_mask=~in60[p0], ctrl_mask=~in60)
    add("primary_endpoint_without_suspect_o2_windows", r["pe"],
        f"n_events {r['n_evaluable']}, p {r['p_value']:.4f}, CI [{r['ci_low']:.3f}, {r['ci_high']:.3f}]")
    return pd.DataFrame(rows)


def ordinary_alert_share(flags: dict, B: dict) -> dict:
    return {w: float(f[B["elig"][0]].mean()) for w, f in flags.items()}
