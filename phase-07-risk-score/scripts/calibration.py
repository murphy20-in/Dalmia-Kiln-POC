"""Step 3 - score every bucket with the frozen reference, calibration tables, empirical alert rate, period coverage.

Pure: alert_episodes (hysteresis), period_coverage, auc, block_auc_ci, block_share_ci (band fitting lives in risk_core).
Writes risk_scores.parquet (operational numbers only), risk_score_diagnostics.parquet (in-sample / non-operational),
       risk_score_components.parquet, risk_score_reasons.parquet, risk_score_confidence.parquet, risk_score_bands.csv,
       risk_score_calibration.csv, risk_score_event_similarity.csv, risk_score_summary.csv, risk_score_data_quality.csv

Terminology: EMPIRICAL_ALERT_RATE (never a false-positive rate), SUSTAINED_EXCEEDANCE_EPISODES (never alarms) and
EMPIRICAL_ABNORMAL_PERIOD_COVERAGE (never detection accuracy). The Phase 6 periods are EMPIRICAL_ABNORMAL_REFERENCE
conditions from the same components (circular); the Phase 3 KPI they were built from is reported as the baseline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from common import (BANDS, FAMILIES, MONTHS, PRIMARY, SCORE_LABEL, STATE_LABEL, P7Config, load_context,
                    load_refs, log, variant, write_csv, write_parquet)
from reference_builder import fit_reference
from risk_core import (HIGH_RANK, LOAD_BANDS, band_rank, block_ids, components_long, magnitude, score_core,
                       score_frame)

ELEVATED_RANK = BANDS.index("ELEVATED")
PUBLIC_COLUMNS = ["timestamp", "risk_score", "risk_band", "operational", "confidence_score", "confidence_band",
                  "confidence_band_uncapped", "confidence_cap_reason", "risk_status", "reference_state",
                  "operating_state", "operating_state_label", "load_band", "load_context", "feed_tph", "kpi_value",
                  "kpi_band", "family_count_abnormal", "family_count_usable", "persistence_minutes",
                  "historical_similarity", "magnitude_component", "concurrence_component", "persistence_component",
                  "data_quality_status", "primary_reason", "secondary_reasons", "contributing_families", "afr_context",
                  "phase4_context", "reference_version", "score_version", "score_label"]
DIAGNOSTIC_COLUMNS = ["timestamp", "reference_state", "risk_status", "risk_score_in_sample_reference",
                      "risk_band_in_sample_reference", "risk_score_diagnostic", "historical_similarity_diagnostic",
                      "diagnostic_label"]
DIAG_LABEL = ("NON-OPERATIONAL DIAGNOSTICS: in-sample reference scores (calibration only) and the formula value for "
              "any RUNNING bucket with >= 3 usable families - never an operational score")


# ============================================================================== alert burden and coverage (pure)
def alert_episodes(frame: pd.DataFrame, rank: np.ndarray, operational: np.ndarray) -> pd.DataFrame:
    """Sustained-exceedance episodes (hysteresis) on operational buckets: open at band >= HIGH, stay open while band >=
    ELEVATED, close on the first bucket below ELEVATED or the first non-operational bucket (no bridging stops / gaps)."""
    rows, cur = [], None
    for i in range(len(frame)):
        on = operational[i]
        if cur is None:
            if on and rank[i] >= HIGH_RANK:
                cur = i
            continue
        if not on or rank[i] < ELEVATED_RANK:
            rows.append((cur, i - 1))
            cur = None
            if on and rank[i] >= HIGH_RANK:
                cur = i
    if cur is not None:
        rows.append((cur, len(frame) - 1))
    ix = frame.index
    out = []
    for s, e in rows:
        seg = frame.iloc[s:e + 1]
        out.append({"start": ix[s] - pd.Timedelta(minutes=10), "end": ix[e], "duration_min": (e - s + 1) * 10,
                    "peak_score": float(seg.score_all.max()), "month": MONTHS.get(ix[s].month, "OTHER"),
                    "load_band": seg.load_band.mode().iloc[0], "post_restart": bool(seg.conf_operating_state.iloc[0] < 1),
                    "dq_affected": bool(seg.conf_data_quality.mean() < PRIMARY.conf_high),
                    "load_associated_share": float(seg.load_context.eq("LOAD_ASSOCIATED").mean())})
    return pd.DataFrame(out)


def period_mask(index: pd.DatetimeIndex, start, end) -> np.ndarray:
    return (index > start) & (index <= end)


def auc(x: np.ndarray, y: np.ndarray) -> float:
    """P(random x > random y) + 0.5 P(tie) (Mann-Whitney), NaN if either side is empty."""
    x, y = x[np.isfinite(x)], y[np.isfinite(y)]
    if not x.size or not y.size:
        return float("nan")
    return float(stats.mannwhitneyu(x, y, alternative="two-sided").statistic / (x.size * y.size))


def _block_groups(ts: pd.DatetimeIndex, cfg: P7Config) -> list[np.ndarray]:
    if not len(ts):
        return []
    start = (pd.Timestamp(cfg.ref_end) + pd.Timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
    blk = block_ids(ts, start, cfg.block_days)
    return [np.flatnonzero(blk == b) for b in range(blk.max() + 1)]


def block_auc_ci(score: np.ndarray, inside: np.ndarray, ts: pd.DatetimeIndex, cfg: P7Config, n_boot: int = 200
                 ) -> tuple[float, float]:
    groups = _block_groups(ts, cfg)
    rng = np.random.default_rng(cfg.seed)
    vals = []
    for _ in range(n_boot):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        vals.append(auc(score[idx][inside[idx]], score[idx][~inside[idx]]))
    v = np.asarray(vals)
    v = v[np.isfinite(v)]
    return (float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))) if v.size >= 20 else (np.nan, np.nan)


def block_share_ci(flag: np.ndarray, ts: pd.DatetimeIndex, cfg: P7Config, n_boot: int = 400) -> np.ndarray:
    """Bootstrap distribution (3-day blocks) of the share of True in `flag`."""
    groups = _block_groups(ts, cfg)
    if not groups:
        return np.array([np.nan])
    rng = np.random.default_rng(cfg.seed)
    return np.array([flag[np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])].mean()
                     for _ in range(n_boot)])


def spearman_ci(x, y) -> tuple[float, float, float, float]:
    """(rho, p, 95 % CI low, high) with the Fisher-z approximation (small n: approximate)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 4:
        return (np.nan,) * 4
    r, p = stats.spearmanr(x[ok], y[ok])
    z, se = np.arctanh(np.clip(r, -0.999999, 0.999999)), 1 / np.sqrt(n - 3)
    return float(r), float(p), float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))


def period_coverage(frame: pd.DataFrame, comp: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    """Per Phase 6 period: score during, just before onset (onset - 2 h .. onset) and family shares (uses score_all, so
    the in-sample calibration-only periods are covered too). Start / end / onset are event-start information
    (permitted); no post-event field is read. minutes_onset_to_first_high_lag is a LAG after onset, not a lead."""
    rows = []
    fam_pts = comp.pivot_table(index="timestamp", columns="family", values="family_contribution", aggfunc="sum")
    for r in episodes.sort_values("start_time").itertuples():
        m = period_mask(frame.index, r.start_time, r.end_time)
        pre = period_mask(frame.index, r.onset_time - pd.Timedelta(hours=2), r.onset_time)
        seg, pseg = frame[m], frame[pre]
        sc = seg.score_all
        ok = sc.notna().to_numpy()
        rk = band_rank(seg.band_all.to_numpy())
        since = frame[period_mask(frame.index, r.onset_time, r.end_time)]
        first_high = since.index[band_rank(since.band_all.to_numpy()) >= HIGH_RANK]
        fp = fam_pts.reindex(seg.index[ok])
        tot = fp.sum(axis=1).sum()
        row = {"episode_id": r.episode_id, "classification": r.classification, "start_time": r.start_time,
               "end_time": r.end_time, "onset_time": r.onset_time,
               "duration_h": (r.end_time - r.start_time) / pd.Timedelta(hours=1), "n_buckets": int(m.sum()),
               "valid_share": float(ok.mean()) if len(seg) else np.nan,
               "median_score": float(sc.median()) if ok.any() else np.nan,
               "peak_score": float(sc.max()) if ok.any() else np.nan,
               "share_ge_high": float((rk[ok] >= HIGH_RANK).mean()) if ok.any() else np.nan,
               "max_band": BANDS[int(rk.max())] if (rk >= 0).any() else "NOT_SCORED",
               "minutes_onset_to_first_high_lag": float((first_high[0] - r.onset_time) / pd.Timedelta(minutes=1))
               if len(first_high) else np.nan,
               "pre_onset_2h_mean_score": float(pseg.score_all.mean()) if pseg.score_all.notna().any() else np.nan,
               "median_confidence": float(seg.confidence_score.median()) if len(seg) else np.nan,
               "median_historical_similarity": float(seg.historical_similarity_diagnostic.median()) if len(seg) else np.nan,
               "phase6_severity_class": r.severity_class, "phase6_severity_score": r.severity_score,
               "phase6_confidence": r.confidence, "phase6_load_context": r.load_context,
               "phase6_afr_context": r.afr_context, "phase6_reference_robustness": r.reference_robustness_score,
               "phase6_deviating_families": r.deviating_families,
               "coverage_label": "EMPIRICAL_ABNORMAL_PERIOD_COVERAGE (not detection accuracy; no ground truth)"}
        for c in list(FAMILIES) + ["CONCURRENCE", "PERSISTENCE"]:
            row[f"share_points_{c.lower()}"] = float(fp[c].sum() / tot) if tot > 0 and c in fp else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def month_label(ix: pd.DatetimeIndex) -> np.ndarray:
    return np.select([ix <= pd.Timestamp(PRIMARY.ref_end), ix.month == 6, ix.month == 7, ix.month == 8, ix.month == 9],
                     ["REFERENCE_APR_MAY", "JUN", "JUL", "AUG", "SEP_NOT_SCORED"], "OTHER")


def summary(frame: pd.DataFrame, comp: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = []
    pts = comp.pivot_table(index="timestamp", columns="family", values="family_contribution", aggfunc="sum")
    for key, seg in frame.groupby(by, sort=True):
        s = seg.score_all.dropna()
        rk = band_rank(seg.band_all.to_numpy())
        p = pts.reindex(s.index)
        tot = p.sum(axis=1).sum()
        nconf = max(int(seg.confidence_band.ne("").sum()), 1)
        row = {"slice_type": by, "slice": key, "n_buckets": len(seg), "n_running": int(seg.operating_state.eq("RUNNING").sum()),
               "n_scored": int(s.size), "median": s.median(), "p75": s.quantile(0.75), "p90": s.quantile(0.90),
               "share_ge_high": float((rk >= HIGH_RANK).sum() / max(s.size, 1)),
               "share_confidence_medium": float(seg.confidence_band.eq("MEDIUM").sum() / nconf),
               "share_confidence_low": float(seg.confidence_band.eq("LOW").sum() / nconf),
               "median_confidence": seg.confidence_score.median()}
        for b in BANDS:
            row[f"share_{b.lower()}"] = float((seg.band_all == b).sum() / max(s.size, 1))
        for st in ("VALID", "VALID_REDUCED_CONFIDENCE", "INSUFFICIENT_DATA", "NOT_SCORABLE", "TRANSITION_CONTEXT",
                   "STOPPED"):
            row[f"n_status_{st.lower()}"] = int((seg.risk_status == st).sum())
        for c in list(FAMILIES) + ["CONCURRENCE", "PERSISTENCE"]:
            row[f"share_points_{c.lower()}"] = float(p[c].sum() / tot) if tot > 0 and c in p else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def data_quality_table(frame: pd.DataFrame, grid: pd.DataFrame, core: dict) -> pd.DataFrame:
    """How data quality moves status and confidence (never the score upwards)."""
    rows = []
    run = frame.operating_state.eq("RUNNING")
    for m, seg in frame.groupby("month", sort=True):
        for st, n in seg.risk_status.value_counts().sort_index().items():
            rows.append({"section": "STATUS_BY_MONTH", "slice": m, "metric": st, "value": int(n)})
    for q, seg in frame[run].groupby("data_quality_status", sort=True):
        rows.append({"section": "CONFIDENCE_BY_DQ_STATUS", "slice": q, "metric": "median_confidence",
                     "value": seg.confidence_score.median()})
        rows.append({"section": "CONFIDENCE_BY_DQ_STATUS", "slice": q, "metric": "n", "value": len(seg)})
    sent = grid[["n_mask_sentinel", "n_mask_text", "n_mask_impossible"]].fillna(0).sum(axis=1) > 0
    for lab, sel in (("with_sentinel_text_or_impossible_cells", sent & run), ("clean", ~sent & run)):
        s = frame[sel.to_numpy()]
        rows += [{"section": "INVALID_VALUE_BUCKETS", "slice": lab, "metric": "n", "value": len(s)},
                 {"section": "INVALID_VALUE_BUCKETS", "slice": lab, "metric": "median_confidence",
                  "value": s.confidence_score.median()},
                 {"section": "INVALID_VALUE_BUCKETS", "slice": lab, "metric": "share_ge_HIGH_of_scored",
                  "value": float((band_rank(s.band_all.to_numpy()) >= HIGH_RANK).sum() / max(s.score_all.notna().sum(), 1))}]
    o2 = frame.o2_ambient_suspect.astype(bool) & frame.operational
    for lab, sel in (("o2_bucket_ge_ambient_threshold", o2), ("o2_below_threshold", frame.operational & ~o2)):
        s = frame[sel]
        rows += [{"section": "O2_ANALYSER_AMBIENT (DQ-1)", "slice": lab, "metric": "operational_buckets", "value": len(s)},
                 {"section": "O2_ANALYSER_AMBIENT (DQ-1)", "slice": lab, "metric": "median_score",
                  "value": s.risk_score.median()},
                 {"section": "O2_ANALYSER_AMBIENT (DQ-1)", "slice": lab, "metric": "share_ge_HIGH",
                  "value": float((band_rank(s.risk_band.to_numpy()) >= HIGH_RANK).mean()) if len(s) else np.nan}]
    for m in ("JUN", "JUL", "AUG"):
        sel = frame.operational & frame.month.eq(m)
        rows.append({"section": "O2_ANALYSER_AMBIENT (DQ-1)", "slice": m, "metric": "share_operational_o2_suspect",
                     "value": float(frame.o2_ambient_suspect[sel].mean()) if sel.any() else np.nan})
    rows.append({"section": "DQ_WINDOWS", "slice": "after_window_6h", "metric": "running_buckets",
                 "value": int((frame.dq_window_after & run).sum())})
    rows.append({"section": "DQ_WINDOWS", "slice": "after_window_6h", "metric": "median_conf_data_quality",
                 "value": frame.loc[frame.dq_window_after & run, "conf_data_quality"].median()})
    sep = frame.month.eq("SEP_NOT_SCORED")
    rows.append({"section": "SEPTEMBER", "slice": "SEP", "metric": "numeric_scores_incl_diagnostic",
                 "value": int(frame.risk_score[sep].notna().sum() + frame.risk_score_diagnostic[sep].notna().sum())})
    rows.append({"section": "SEPTEMBER", "slice": "SEP", "metric": "running_buckets", "value": int((sep & run).sum())})
    # Missing-family injection: dropping usable families must never raise the score (fixed denominator).
    S = core["S"]
    rng = np.random.default_rng(PRIMARY.seed)
    ok = core["valid3"]
    S2 = np.where((rng.random(S.shape) < 0.3) & ok[:, None], np.nan, S)
    h1, h2 = magnitude(S, core["M"], core["Q"], PRIMARY), magnitude(S2, core["M"], core["Q"], PRIMARY)
    viol = int(((h2["H"] > h1["H"] + 1e-12) | (h2["C"] > h1["C"] + 1e-12))[ok].sum())
    rows.append({"section": "MISSING_FAMILY_INJECTION", "slice": "30% of usable family values set to NaN",
                 "metric": "buckets_where_H_or_C_increased", "value": viol})
    rows.append({"section": "MISSING_FAMILY_INJECTION", "slice": "30% of usable family values set to NaN",
                 "metric": "buckets_tested", "value": int(ok.sum())})
    return pd.DataFrame(rows)


# ============================================================================== step
def main():
    lg = log("calibration")
    ctx = load_context()
    refs = load_refs()
    ref = refs["PRIMARY"]
    grid = ctx["grid"]
    frame, core = score_frame(grid, refs, ctx)
    frame["operating_state_label"] = STATE_LABEL
    frame["score_label"] = SCORE_LABEL
    frame["diagnostic_label"] = DIAG_LABEL
    comp = components_long(frame, core)
    write_parquet(frame.reset_index()[PUBLIC_COLUMNS], "risk_scores.parquet", lg)
    write_parquet(frame.reset_index()[DIAGNOSTIC_COLUMNS], "risk_score_diagnostics.parquet", lg)
    write_parquet(comp, "risk_score_components.parquet", lg)
    write_parquet(core["reasons_long"], "risk_score_reasons.parquet", lg)
    cc = ["confidence_score", "confidence_band", "confidence_band_uncapped", "confidence_cap_reason",
          "conf_data_quality", "conf_family_coverage", "conf_baseline", "conf_operating_state", "conf_temporal",
          "conf_robustness", "causal_invalid_share", "dq_window_after", "o2_ambient_suspect", "risk_status"]
    write_parquet(frame.reset_index()[["timestamp"] + cc], "risk_score_confidence.parquet", lg)

    # ---------------------------------------------------------------- bands (+ April-fit / May-check stability)
    ix = frame.index
    oper = frame.operational.to_numpy(bool)
    rank = band_rank(frame.band_all.to_numpy())
    apr = variant(name="APRIL_FIT", ref_end="2025-04-30 23:59")
    ref_apr = fit_reference(grid, apr, ctx["episodes"], ctx)
    ca = score_core(grid, ref_apr, apr, ctx)
    may = (ix > pd.Timestamp("2025-05-01")) & (ix <= pd.Timestamp(PRIMARY.ref_end)) & ca["valid3"]
    sc_op = frame.risk_score[oper]
    bands_rows = [{"band": "LOW", "lower_edge": 0.0, "reference_quantile": 0.0, "supported": True,
                   "population": ref["bands"]["population"], "date_range": ref["bands"]["date_range"],
                   "n": ref["bands"]["n"], "reference_version": ref["reference_version"],
                   "oos_exceedance_jun_aug": 1.0, "nominal_exceedance": 1.0,
                   "rationale": "below the first supported edge: within the usual Apr-May range",
                   "calibration_status": ref["bands"]["status"]}]
    for e in ref["bands"]["candidates"]:
        ea = next((x for x in ref_apr["bands"]["candidates"] if x["band"] == e["band"]), None)
        pq = int(round(e["quantile"] * 100))
        bands_rows.append({"band": e["band"], "lower_edge": e["value"], "reference_quantile": e["quantile"],
                           "ci95_low": e["ci_low"], "ci95_high": e["ci_high"], "supported": e["supported"],
                           "merged_into": e["merged_into"], "population": ref["bands"]["population"],
                           "date_range": ref["bands"]["date_range"], "n": ref["bands"]["n"],
                           "n_blocks": ref["bands"]["n_blocks"], "reference_version": ref["reference_version"],
                           "april_fit_edge": ea["value"] if ea else np.nan,
                           "april_fit_may_exceedance": float((ca["R"][may] >= ea["value"]).mean()) if ea else np.nan,
                           "nominal_exceedance": 1 - e["quantile"],
                           "oos_exceedance_jun_aug": float((sc_op >= e["value"]).mean()),
                           "rationale": (f"reference P{pq} of risk_score (>= Apr-May P{pq}): resemblance relative to "
                                         "the Apr-May reference - NOT a plant limit, alarm or action threshold"),
                           "calibration_status": ref["bands"]["status"]})
    write_csv(pd.DataFrame(bands_rows), "risk_score_bands.csv", lg)

    # ---------------------------------------------------------------- empirical alert rate (+ uncertainty) + episodes
    ml = month_label(ix)
    frame["month"] = ml
    cal_rows = []
    hi_edge = next((e for e in ref["bands"]["edges"] if e["band"] == "HIGH"), None)
    boots = {}
    for m in ("JUN", "JUL", "AUG"):
        sel = oper & (ml == m)
        for b in BANDS:
            cal_rows.append({"section": "EMPIRICAL_ALERT_RATE", "slice": m, "metric": f"share_{b}",
                             "value": float((frame.band_all[sel] == b).mean()) if sel.any() else np.nan,
                             "n": int(sel.sum())})
        flag = rank[sel] >= HIGH_RANK
        boots[m] = block_share_ci(flag, ix[sel], PRIMARY)
        extra = {"share_ge_HIGH": float(flag.mean()), "share_ge_HIGH_block_ci95_low": float(np.quantile(boots[m], .025)),
                 "share_ge_HIGH_block_ci95_high": float(np.quantile(boots[m], .975)),
                 "n_blocks": len(_block_groups(ix[sel], PRIMARY))}
        if hi_edge:
            s = frame.risk_score[sel].to_numpy(float)
            extra["share_ge_HIGH_edge_at_ci_high"] = float((s >= hi_edge["ci_high"]).mean())
            extra["share_ge_HIGH_edge_at_ci_low"] = float((s >= hi_edge["ci_low"]).mean())
        for k, v in extra.items():
            cal_rows.append({"section": "EMPIRICAL_ALERT_RATE", "slice": m, "metric": k, "value": v, "n": int(sel.sum())})
    diff = boots["AUG"] - boots["JUN"]
    point = (rank[oper & (ml == "AUG")] >= HIGH_RANK).mean() - (rank[oper & (ml == "JUN")] >= HIGH_RANK).mean()
    for k, v in {"share_ge_HIGH_difference": float(point), "difference_block_ci95_low": float(np.quantile(diff, .025)),
                 "difference_block_ci95_high": float(np.quantile(diff, .975))}.items():
        cal_rows.append({"section": "EMPIRICAL_ALERT_RATE", "slice": "AUG_minus_JUN", "metric": k, "value": v,
                         "n": int((oper & np.isin(ml, ["JUN", "AUG"])).sum())})
    for lb in LOAD_BANDS:
        sel = oper & frame.load_band.eq(lb).to_numpy()
        cal_rows.append({"section": "EMPIRICAL_ALERT_RATE", "slice": lb, "metric": "share_ge_HIGH",
                         "value": float((rank[sel] >= HIGH_RANK).mean()) if sel.any() else np.nan, "n": int(sel.sum())})
    # load-standardised drift (SDS-3): each month's per-load-band HIGH share weighted by the pooled Jun-Aug load mix
    pool = oper & np.isin(ml, ["JUN", "JUL", "AUG"])
    wts = frame.load_band[pool].value_counts(normalize=True).sort_index()
    for m in ("JUN", "JUL", "AUG"):
        sel = oper & (ml == m)
        std = sum(w * (rank[sel & frame.load_band.eq(lb).to_numpy()] >= HIGH_RANK).mean()
                  for lb, w in wts.items() if (sel & frame.load_band.eq(lb).to_numpy()).any())
        steady = sel & frame.load_context.eq("STEADY_LOAD").to_numpy()
        for k, v in {"load_standardised_share_ge_HIGH": float(std),
                     "steady_load_only_share_ge_HIGH": float((rank[steady] >= HIGH_RANK).mean()) if steady.any() else np.nan,
                     "share_TENTATIVE_LOW_load": float(frame.load_band[sel].eq("TENTATIVE_LOW").mean()) if sel.any() else np.nan
                     }.items():
            cal_rows.append({"section": "LOAD_STANDARDISED_ALERT_RATE", "slice": m, "metric": k, "value": v,
                             "n": int(sel.sum())})
    ep = alert_episodes(frame, rank, oper)
    run_h = {m: float(((ml == m) & frame.operating_state.eq("RUNNING").to_numpy()).sum() / 6) for m in ("JUN", "JUL", "AUG")}
    for m in ("JUN", "JUL", "AUG", "ALL"):
        e = ep if m == "ALL" or ep.empty else ep[ep.month == m]
        hrs = sum(run_h.values()) if m == "ALL" else run_h[m]
        for k, v in {"episodes": len(e), "episodes_per_100_running_h": 100 * len(e) / hrs if hrs else np.nan,
                     "median_duration_min": e.duration_min.median() if len(e) else np.nan,
                     "mean_duration_min": e.duration_min.mean() if len(e) else np.nan,
                     "share_post_restart": e.post_restart.mean() if len(e) else np.nan,
                     "share_dq_affected": e.dq_affected.mean() if len(e) else np.nan,
                     "mean_load_associated_share": e.load_associated_share.mean() if len(e) else np.nan}.items():
            cal_rows.append({"section": "SUSTAINED_EXCEEDANCE_EPISODES", "slice": m, "metric": k, "value": v, "n": len(e)})

    # ---------------------------------------------------------------- empirical abnormal-period coverage (+ baselines)
    eps = ctx["episodes"]
    final = eps[eps.in_final_set]
    calib = eps[eps.classification.eq("CALIBRATION_ONLY_ABNORMAL_LIKE")]
    cov = pd.concat([period_coverage(frame, comp, final).assign(population="PHASE6_FINAL_OUT_OF_SAMPLE"),
                     period_coverage(frame, comp, calib).assign(population="PHASE6_CALIBRATION_ONLY_IN_SAMPLE")],
                    ignore_index=True)
    write_csv(cov, "risk_score_event_similarity.csv", lg)
    inside = np.zeros(len(frame), bool)
    for r in final.itertuples():
        inside |= period_mask(ix, r.start_time, r.end_time)
    sc = frame.risk_score.to_numpy(float)
    a = auc(sc[oper & inside], sc[oper & ~inside])
    lo, hi = block_auc_ci(sc[oper], inside[oper], ix[oper], PRIMARY)
    base = {k: auc(v[oper & inside], v[oper & ~inside]) for k, v in
            {"baseline_auc_phase3_kpi (the periods' own definition)": frame.kpi_value.to_numpy(float),
             "baseline_auc_magnitude_component_only": frame.magnitude_component.to_numpy(float),
             "baseline_auc_abnormal_family_count": frame.family_count_abnormal.to_numpy(float)}.items()}
    fcv = cov[cov.population.eq("PHASE6_FINAL_OUT_OF_SAMPLE")]
    for k, v in {"median_score_inside_periods": np.nanmedian(sc[oper & inside]),
                 "median_score_outside_periods": np.nanmedian(sc[oper & ~inside]),
                 "rank_separation_auc": a, "rank_separation_auc_ci95_low": lo, "rank_separation_auc_ci95_high": hi,
                 **base, "periods_with_max_band_ge_HIGH": int(fcv.max_band.isin(["HIGH", "VERY_HIGH"]).sum()),
                 "periods_total": len(final), "median_pre_onset_2h_score": float(fcv.pre_onset_2h_mean_score.median())
                 }.items():
        cal_rows.append({"section": "EMPIRICAL_ABNORMAL_PERIOD_COVERAGE", "slice": "JUN_AUG_FINAL_PERIODS",
                         "metric": k, "value": v, "n": int(oper.sum())})
    sev = {}
    for lab, col in (("peak", "peak_score"), ("median", "median_score"), ("share_ge_high", "share_ge_high")):
        r_, p_, l_, h_ = spearman_ci(fcv[col], fcv.phase6_severity_score)
        sev |= {f"spearman_{lab}_vs_severity": r_, f"spearman_{lab}_p": p_, f"spearman_{lab}_ci95_low": l_,
                f"spearman_{lab}_ci95_high": h_}
    sev["spearman_duration_vs_peak"] = spearman_ci(fcv.duration_h, fcv.peak_score)[0]
    med = fcv.groupby("phase6_severity_class").peak_score.median()
    sev |= {f"median_peak_{c}": med.get(c, np.nan) for c in ("HIGH", "MODERATE", "LOW")}
    sev["monotone_by_severity_class"] = float(all(c in med for c in ("HIGH", "MODERATE", "LOW"))
                                              and med["HIGH"] >= med["MODERATE"] >= med["LOW"])
    for k, v in sev.items():
        cal_rows.append({"section": "SEVERITY_RELATIONSHIP (context; severity is not a label; n=12 - inconclusive)",
                         "slice": "12 periods", "metric": k, "value": v, "n": len(fcv)})
    write_csv(pd.DataFrame(cal_rows), "risk_score_calibration.csv", lg)

    # ---------------------------------------------------------------- summaries + data quality
    summ = pd.concat([summary(frame, comp, "month"), summary(frame[oper], comp, "load_band"),
                      summary(frame[oper], comp, "load_context")], ignore_index=True)
    write_csv(summ, "risk_score_summary.csv", lg)
    write_csv(data_quality_table(frame, grid, core), "risk_score_data_quality.csv", lg)
    lg.info("bands %s; operational buckets %d; sustained-exceedance episodes %d; coverage AUC %.3f [%.3f, %.3f]; KPI "
            "baseline AUC %.3f", ref["bands"]["status"], int(oper.sum()), len(ep), a, lo, hi, list(base.values())[0])


if __name__ == "__main__":
    main()
