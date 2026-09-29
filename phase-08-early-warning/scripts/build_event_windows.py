"""Inputs, the empirical abnormal-period table (T0 = Phase 6 CUSUM onset), event data-quality status, signal bundles and
the aligned pre-onset trajectories.

Only allow-listed columns are read (SCORE_COLUMNS: no afr_context). Only operational == True scores carry a value.
Phase 6 fields used: identifiers, onset / detection / start / end times, onset_censored, severity / confidence
(metadata only). No Phase 6 post-event field is read. Episode END times are used only to keep controls away from
abnormal periods and for the backward diagnostic NC3 - never to build a warning feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import calibration
import warning_metrics as wm
from p8common import (CFG, EVALUABLE, FAMILIES, P6_OUT, P7_OUT, SCORE_COLUMNS, SCORE_VERSION, P8Config, ac, ic, nb,
                      p7c, risk_core)

EPISODE_FIELDS = ("episode_id", "onset_time", "detection_time", "start_time", "end_time", "in_final_set",
                  "reference_state", "month", "severity_class", "confidence", "onset_censored")
COMPONENT_FAMILIES = FAMILIES + ("CONCURRENCE", "PERSISTENCE")


def load_scores(path=P7_OUT / "risk_scores.parquet") -> pd.DataFrame:
    s = pd.read_parquet(path, columns=list(SCORE_COLUMNS)).set_index("timestamp")
    if set(s.score_version.dropna().unique()) != {SCORE_VERSION}:
        raise RuntimeError(f"risk_scores.parquet is not {SCORE_VERSION}")
    return s


def load_components(ix: pd.DatetimeIndex) -> pd.DataFrame:
    c = pd.read_parquet(P7_OUT / "risk_score_components.parquet",
                        columns=["timestamp", "operational", "family", "family_contribution"])
    c = c[c.operational]
    return c.pivot(index="timestamp", columns="family", values="family_contribution").reindex(ix)[
        list(COMPONENT_FAMILIES)]


def load_episodes() -> pd.DataFrame:
    return pd.read_parquet(P6_OUT / "abnormal_episodes.parquet", columns=list(EPISODE_FIELDS))


def event_status(n_oper: int, n: int, dq_overlap: bool, poor_share: float, stop_or_transition: bool, censored: bool,
                 low_conf_share: float, o2_any: bool) -> str:
    """Event data-quality status by fixed precedence (spec section 12)."""
    if n_oper == 0:
        return "NOT_EVALUABLE"
    if n_oper < -(-2 * n // 3):
        return "INSUFFICIENT_DATA"
    if dq_overlap or poor_share > 0.5:
        return "DATA_QUALITY_CONTAMINATED"
    if stop_or_transition:
        return "TRANSITION_CONTAMINATED"
    if censored or low_conf_share > 0.5 or o2_any:
        return "VALID_REDUCED_CONFIDENCE"
    return "VALID"


def events_table(eps: pd.DataFrame, ix: pd.DatetimeIndex, s: pd.DataFrame, dq: np.ndarray, o2: np.ndarray,
                 conf_dq: np.ndarray, cfg: P8Config = CFG) -> pd.DataFrame:
    """The 12 final periods with grid positions and the primary-window (T0 - 60 min, T0] data-quality status.
    `*_o2x` = the same status for the O2-excluded variant: the ambient-O2 penalty of the Phase 7 data-quality
    confidence (x 0.5 when o2_ambient_suspect, hard-coded in Phase 7 risk_core) and the O2 flag are removed, because
    that variant does not use the analyser. The LOW-confidence share is kept (it cannot be split by cause), which can
    only lower the label to VALID_REDUCED_CONFIDENCE, never change evaluability."""
    fin = eps[eps.in_final_set & eps.reference_state.eq("OUT_OF_SAMPLE")].sort_values("onset_time").reset_index(drop=True)
    pos = {t: i for i, t in enumerate(ix)}
    n = nb(cfg.primary_h)
    poor_no_o2 = np.where(o2, conf_dq * 2, conf_dq) <= p7c.PRIMARY.conf_low
    rows = []
    for r in fin.itertuples():
        p0 = pos[r.onset_time]
        seg = slice(p0 - n + 1, p0 + 1)
        w = s.iloc[seg]
        n_op, dq_hit = int(w.operational.sum()), bool(dq[seg].any())
        stop = bool(w.risk_status.isin(["STOPPED", "TRANSITION_CONTEXT"]).any())
        poor, low = float(w.data_quality_status.eq("POOR").mean()), float(w.confidence_band.eq("LOW").mean())
        reasons = [k for k, f in (("PHASE1_DQ_WINDOW", dq_hit), (f"POOR_DQ_SHARE_{poor:.2f}", poor > 0.5),
                                  ("STOP_OR_TRANSITION", stop), ("ONSET_CENSORED", bool(r.onset_censored)),
                                  (f"LOW_CONFIDENCE_SHARE_{low:.2f}", low > 0.5),
                                  ("O2_AMBIENT_SUSPECT", bool(o2[seg].any()))) if f]
        rows.append({"event_id": r.episode_id, "T0": r.onset_time, "event_start": r.start_time,
                     "event_end": r.end_time, "detection_time": r.detection_time, "month": int(r.onset_time.month),
                     "severity": r.severity_class, "phase6_confidence": r.confidence,
                     "onset_censored": bool(r.onset_censored), "pos_T0": p0,
                     "pos_det": pos[r.detection_time], "pos_end": pos[r.end_time],
                     "data_quality_status": event_status(n_op, n, dq_hit, poor, stop, bool(r.onset_censored), low,
                                                         bool(o2[seg].any())),
                     "data_quality_reason": ";".join(reasons) or "NONE",
                     "data_quality_status_o2x": event_status(n_op, n, dq_hit, float(poor_no_o2[seg].mean()), stop,
                                                             bool(r.onset_censored), low, False)})
    ev = pd.DataFrame(rows)
    ev["evaluable"] = ev.data_quality_status.isin(EVALUABLE)
    ev["evaluable_o2x"] = ev.data_quality_status_o2x.isin(EVALUABLE)
    return ev


def load_base(cfg: P8Config = CFG) -> dict:
    """Everything the analyses share. Rescoring with the frozen references (score_frame) gives the Apr-May in-sample
    reference score distribution (the rank transform) and the L6 check that the stored score is reproduced."""
    ctx = p7c.load_context()
    refs = p7c.load_refs()
    ix = ctx["grid"].index
    ic.check_grid(ix)
    s = load_scores().reindex(ix)
    frame, _ = risk_core.score_frame(ctx["grid"], refs, ctx)
    a, b = frame.risk_score.to_numpy(float), s.risk_score.to_numpy(float)
    rescore = {"nan_pattern_equal": bool(np.array_equal(np.isnan(a), np.isnan(b))),
               "max_abs_diff": float(np.nanmax(np.abs(a - b)))}
    ref_mask = frame.risk_score_in_sample_reference.notna().to_numpy()
    conf = pd.read_parquet(P7_OUT / "risk_score_confidence.parquet",
                           columns=["timestamp", "o2_ambient_suspect", "conf_data_quality"]
                           ).set_index("timestamp").reindex(ix)
    o2 = conf.o2_ambient_suspect.fillna(False).to_numpy(bool)
    dq = ac.dq_window_mask(ix, ctx["dq_windows"], kinds=("LONG_GAP", "FROZEN_WINDOW"))
    eps = load_episodes()
    ev = events_table(eps, ix, s, dq, o2, conf.conf_data_quality.to_numpy(float), cfg)
    oper = s.operational.fillna(False).to_numpy(bool)
    return {"ix": ix, "s": s, "oper": oper, "ctx": ctx, "refs": refs, "grid": ctx["grid"], "eps": eps, "events": ev,
            "dq": dq, "o2": o2, "comps": load_components(ix), "ref_mask": ref_mask, "rescore": rescore,
            "core_R": frame.risk_score_diagnostic.to_numpy(float), "month": ix.month.to_numpy()}


def make_signals(score_all: np.ndarray, B: dict, name: str, cfg: P8Config = CFG) -> dict:
    """Signal bundle for one score (PRIMARY or a VALIDATION_VARIANT). score_all = the score formula on every bucket;
    it is masked to the PRIMARY operational rows (same population for every variant) and to the Apr-May in-sample
    reference rows for the frozen rank / slope references."""
    score = np.where(B["oper"], score_all, np.nan)
    ref_series = np.where(B["ref_mask"], score_all, np.nan)
    thr = calibration.reference_thresholds(ref_series, cfg)
    return {"name": name, **wm.signals_from(score, thr, B["s"].family_count_abnormal.to_numpy(float), cfg, roll=True)}


def trajectories(B: dict, sigs: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    """10-min aligned pre-onset trajectories (T0 - 24 h .. T0) of every period. Only buckets <= T0."""
    s, comps, ix = B["s"], B["comps"], B["ix"]
    P, O = sigs["PRIMARY"], sigs.get("EXCLUDE_KILN_INLET_O2_ANALYSER")
    n = nb(cfg.lookback_min)
    rows = []
    for e in B["events"].itertuples():
        for k in range(n + 1):
            p = e.pos_T0 - k
            if p < 0:
                continue
            r = {"event_id": e.event_id, "month": e.month, "severity": e.severity, "offset_minutes": -10 * k,
                 "timestamp": ix[p], "is_key_offset": 10 * k in cfg.offsets, "operational": bool(B["oper"][p]),
                 "risk_score": P["score"][p], "risk_rank_ref": P["rank"][p], "risk_rank_rolling": P["rank_roll"][p],
                 "slope_points_per_h": P["slope"][p], "confidence_score": s.confidence_score.iat[p],
                 "kpi_value": s.kpi_value.iat[p], "persistence_minutes": s.persistence_minutes.iat[p],
                 "family_count_abnormal": s.family_count_abnormal.iat[p], "feed_tph": s.feed_tph.iat[p],
                 "load_context": s.load_context.iat[p], "o2_ambient_suspect": bool(B["o2"][p])}
            r.update({f"contrib_{f.lower()}": comps[f].iat[p] for f in comps.columns})
            if O is not None:
                r["o2x_risk_score"], r["o2x_risk_rank_ref"] = O["score"][p], O["rank"][p]
            rows.append(r)
    return pd.DataFrame(rows).sort_values(["event_id", "offset_minutes"], kind="mergesort").reset_index(drop=True)
