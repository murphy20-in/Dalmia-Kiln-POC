"""Step 8 - Transparent indicator scoring, relationship class, confidence, and the small complementary leading set.

Reads  cache/lag_analysis.parquet, cache/lead_time.parquet, cache/sensitivity_consistency.csv, cache/features.parquet,
       outputs/indicator_candidate_inventory.csv, indicator_data_quality.csv, indicator_sensitivity.csv
Writes outputs/indicator_scores.csv        every indicator (tag|feature): gates, criteria c1-c9, score, class, confidence
       outputs/leading_indicator_set.csv   discovery-supported indicators with selection status (SELECTED = the set) -
                                           the downstream contract (Phase 5 now; Phase 7 / 8 later)
       outputs/indicator_sensitivity.csv   + ranking / set summary rows (leave-one-criterion-out, family removal, F/G)

Temporal design (pre-declared): DISCOVERY (Apr-May) chooses lag + sign; REPLICATION (Jun-Jul) decides every gate,
criterion, score and the set; the AUGUST HOLDOUT is never used for gating, scoring, ranking or selection and is reported
once, as a forward test (holdout_result). No weights are fitted (there is no event ground truth to fit them to).
  GATES (all required for ELIGIBLE):
    a  supported in discovery: BH q <= 0.10 over all discovery tests and the 3-day-block bootstrap CI excludes 0
    b  replicates in Jun-Jul at the SAME lag and sign: pooled CI excludes 0 with the discovery sign, and both months
       have the discovery sign
    c  survives feed controls (feed level + 1-h / 3-h feed rate of change); not evaluated = fails
    d  forward association (with the future KPI change, discovery sign) >= backward association (with the past change)
    e  evaluable (>= 100 rows) in both replication months
    f  beats a circular-shift null in the replication months (one-sided empirical p < 0.05, 58 shifts of 2-59 days)
    KPI_INPUT tags -> COMPONENT_PRECURSOR and KPI_PROXY tags -> KPI_PROXY_PRECURSOR (circular; never in the set);
    context tags -> LOAD_CONTEXT
  SCORE = mean of 9 criteria in [0, 1], fixed denominator (missing evidence scores 0):
    c1 lead strength        min(1, sign * rho_p(REPL) / 0.30)
    c2 directional consistency  replication months with the discovery sign and CI excluding 0, / 2
    c3 lead-time stability  share of lags whose REPL rho_p has the discovery sign
    c4 episode lift         clip(hit rate before episodes - before matched controls, 0, 1) (needs >= 5 episodes)
    c5 false-lead control   clip((precision - base rate) / (1 - base rate), 0, 1)
    c6 coverage             mean replication RUNNING-bucket coverage
    c7 data quality         Phase 4 data_quality_score of the tag
    c8 robustness           share of consistent sensitivity variants (state, load, Sp.Heat, window, DQ, inference)
    c9 interpretability     level/deviation 1.0, rate/persistence 0.75, volatility 0.5; x0.5 for manipulated variables
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from p4common import (CACHE, FEATURE_DOC, FEATURE_INTERPRETABILITY, HOLDOUT, INDICATOR_LABEL, MATERIALITY,
                      METHOD_VERSION, PRIMARY, PROXY_LABEL, REPLICATION_MONTHS, THRESHOLD_LABEL, log, read_out, read_p1,
                      write_csv)
import analysis_context as ac
import indicator_core as ic

lg = log("score_indicators")
CRITERIA = ["c1_lead_strength", "c2_directional_consistency", "c3_lead_time_stability", "c4_episode_lift",
            "c5_false_lead_control", "c6_coverage", "c7_data_quality", "c8_robustness", "c9_interpretability"]
GATES = {"gate_a_discovery_supported": "supported in discovery", "gate_b_replicates_jun_jul": "replicates in Jun-Jul",
         "gate_c_survives_feed_controls": "survives feed controls", "gate_d_forward_ge_backward": "forward >= backward",
         "gate_e_evaluable_jun_jul": "evaluable in Jun and Jul", "gate_f_beats_shift_null": "beats circular-shift null"}
CONF_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INSUFFICIENT": 0, "NOT_APPLICABLE": 0}
SHIFT_DAYS = range(2, 60)
P_FLOOR = 1 / (1 + len(SHIFT_DAYS))       # smallest attainable shift-null p (the observed rho beats every shift)


def tb(x) -> bool:
    """Truthiness for values that may be bool, numpy bool, 1.0 / 0.0 or NaN (NaN -> False)."""
    try:
        return bool(x) and not (isinstance(x, float) and np.isnan(x))
    except (TypeError, ValueError):
        return False


def shift_null_p(F: pd.DataFrame, ids: pd.DataFrame, cfg=PRIMARY) -> dict:
    """One-sided empirical p of the replication rho_p against circular shifts of the feature (2-59 days): keeps the
    feature's own autocorrelation and the KPI intact, destroys their alignment. p = (1 + #null >= obs) / (1 + N)."""
    ctx = ac.build_context(cfg)
    out = {}
    for c, r in ids.iterrows():
        h = int(r.lag_minutes) // cfg.bucket_min
        y, Z = ac.target_and_controls(ctx, h)
        rows = ac.window_rows(ctx, "REPL", h)
        x = F[c].to_numpy(float)
        s = int(r.sign)
        obs = ic.assoc(x, y, Z, rows, None, None, cfg.neff_maxlag)["rho_p"]
        null = [ic.assoc(np.roll(x, d * 1440 // cfg.bucket_min), y, Z, rows, None, None, cfg.neff_maxlag)["rho_p"]
                for d in SHIFT_DAYS]
        null = np.array([v for v in null if np.isfinite(v)])
        out[c] = (float((1 + np.sum(s * null >= s * obs)) / (1 + null.size)) if np.isfinite(obs) and null.size else np.nan,
                  float(np.std(null)) if null.size else np.nan)
    return out


def build_scores(F: pd.DataFrame, cfg=PRIMARY) -> pd.DataFrame:
    lagdf = ac.load_lag_table()
    lt = pd.read_parquet(CACHE / "lead_time.parquet").set_index("indicator_id")
    inv = read_out("indicator_candidate_inventory.csv").set_index("indicator_tag")
    dq = read_out("indicator_data_quality.csv").set_index("tag")
    rob = pd.read_csv(CACHE / "sensitivity_consistency.csv").set_index("indicator_id")
    L = lagdf.set_index(["indicator_id", "lag_minutes", "window"])
    nullp = shift_null_p(F, lt[lt.disc_supported].rename(columns={"discovery_lag_minutes": "lag_minutes"}), cfg)
    rows = []
    for c, r in lt.iterrows():
        tag, feat = ac.split_id(c)
        s, lag = int(r.sign), int(r.discovery_lag_minutes)
        get = lambda w, k: L[k].get((c, lag, w), np.nan)
        rec = {"indicator_id": c, "tag": tag, "feature_type": feat, "sign": s, "lag_minutes": lag}
        for k in ("original_name", "dataset", "unit", "process_family", "tier", "status", "flags", "manipulated_variable",
                  "p2_baseline_confidence"):
            rec[k] = inv[k].get(tag, "")
        rec.update(disc_rho_p=r.disc_rho_p, disc_q_bh=r.disc_q_bh, disc_ci_lo=r.disc_ci_lo, disc_ci_hi=r.disc_ci_hi,
                   disc_n_eff=r.disc_n_eff, disc_supported=bool(r.disc_supported))
        for w, pre in (("REPL", "repl"), (HOLDOUT, "holdout"), ("OOS", "oos_all")):
            rec.update({f"{pre}_rho_p": get(w, "rho_p"), f"{pre}_ci_lo": get(w, "ci_lo"), f"{pre}_ci_hi": get(w, "ci_hi"),
                        f"{pre}_n": get(w, "n"), f"{pre}_n_eff": get(w, "n_eff"), f"{pre}_rho_raw": get(w, "rho_raw"),
                        f"{pre}_rho_backward": get(w, "rho_backward"), f"{pre}_rho_contemp": get(w, "rho_contemp")})
        same, sig, ev = 0, 0, 0
        for m in REPLICATION_MONTHS:
            rp, lo, hi, n = get(m, "rho_p"), get(m, "ci_lo"), get(m, "ci_hi"), get(m, "n")
            rec[f"{m.lower()}_rho_p"], rec[f"{m.lower()}_ci_lo"], rec[f"{m.lower()}_ci_hi"] = rp, lo, hi
            if np.isfinite(rp) and n >= 100:
                ev += 1
                same += int(np.sign(rp) == s)
                sig += int(s * lo > 0 and s * hi > 0)
        rec.update(repl_months_evaluable=ev, repl_months_same_sign=same, repl_months_sig_same_sign=sig)
        ro = rob.loc[c] if c in rob.index else None
        rec["load_confounded"] = ro.load_confounded if ro is not None else np.nan
        rec["rho_with_feed_controls"] = ro.rho_with_feed_controls if ro is not None else np.nan
        rec["sp_heat_fg_consistent"] = ro.sp_heat_fg_consistent if ro is not None else np.nan
        rec["state_robust"] = ro.state_robust if ro is not None else np.nan
        rec["shift_null_p_repl"], rec["shift_null_sd_repl"] = nullp.get(c, (np.nan, np.nan))
        for k in lt.columns:
            if k.startswith(("posthoc_", "month_best", "lead_time_conf", "lags_same", "median_", "lead_p", "n_episodes",
                             "n_controls", "hit_rate", "lift_", "n_alarms", "alarms_per", "false_lead", "precision",
                             "base_rate", "alarm_threshold", "n_true", "n_shutdown", "n_load", "n_short", "n_directional",
                             "n_unexplained", "n_not_evaluable", "stable_range", "n_stable")):
                rec[k] = r[k]
        # gates (NaN evidence always fails)
        rp, lo, hi = rec["repl_rho_p"], rec["repl_ci_lo"], rec["repl_ci_hi"]
        fwd, bwd = rec["repl_rho_raw"], rec["repl_rho_backward"]
        rec["gate_a_discovery_supported"] = bool(r.disc_supported)
        rec["gate_b_replicates_jun_jul"] = bool(np.isfinite(lo) and s * lo > 0 and s * hi > 0 and same == len(REPLICATION_MONTHS))
        # tri-state flag read back from CSV: only an explicit False passes (NaN / not evaluated fails - PY-M1)
        rec["gate_c_survives_feed_controls"] = ro is not None and str(ro.load_confounded) == "False"
        rec["gate_d_forward_ge_backward"] = bool(np.isfinite(fwd) and np.isfinite(bwd) and s * fwd > 0 and abs(fwd) >= abs(bwd))
        rec["gate_e_evaluable_jun_jul"] = ev == len(REPLICATION_MONTHS)
        rec["gate_f_beats_shift_null"] = bool(np.isfinite(rec["shift_null_p_repl"]) and rec["shift_null_p_repl"] < 0.05)
        # criteria (fixed denominator; missing evidence = 0)
        cov = dq.loc[tag, [f"coverage_{m.lower()}" for m in REPLICATION_MONTHS]].mean() if tag in dq.index else np.nan
        prec, base = rec.get("precision_repl", np.nan), rec.get("base_rate_repl", np.nan)
        interp = FEATURE_INTERPRETABILITY[feat] * (0.5 if tb(rec["manipulated_variable"]) else 1.0)
        crit = {"c1_lead_strength": s * rp / cfg.strength_ref if np.isfinite(rp) else 0.0,
                "c2_directional_consistency": sig / len(REPLICATION_MONTHS),
                "c3_lead_time_stability": rec.get("lags_same_sign_share", np.nan),
                "c4_episode_lift": rec.get("lift_repl", np.nan) if rec.get("n_episodes_repl", 0) >= 5 else 0.0,
                "c5_false_lead_control": (prec - base) / (1 - base) if np.isfinite(prec) and np.isfinite(base) and base < 1 else 0.0,
                "c6_coverage": cov, "c7_data_quality": dq.data_quality_score.get(tag, np.nan),
                "c8_robustness": ro.robust_share if ro is not None else 0.0, "c9_interpretability": interp}
        rec.update({k: float(np.clip(np.nan_to_num(v, nan=0.0), 0, 1)) for k, v in crit.items()})
        # holdout: reported once, never used above
        hlo, hhi, hr = rec["holdout_ci_lo"], rec["holdout_ci_hi"], rec["holdout_rho_p"]
        rec["holdout_result"] = ("NOT_EVALUABLE" if not np.isfinite(hr) else
                                 "CONFIRMED (same sign, CI excludes 0)" if s * hlo > 0 and s * hhi > 0 else
                                 "SAME_SIGN_NOT_SIGNIFICANT" if np.sign(hr) == s else "REVERSED")
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["phase4_score"] = df[CRITERIA].mean(axis=1)
    df["all_gates_pass"] = df[list(GATES)].all(axis=1)
    df["failed_gates"] = df[list(GATES)].apply(lambda r: "; ".join(f"NOT {GATES[g]}" for g in GATES if not r[g]), axis=1)
    df["relationship_class"] = [classify(r) for r in df.itertuples()]
    df["eligibility"] = np.select(
        [df.status.eq("CONTEXT_ONLY"), ~df.all_gates_pass, df.tier.eq("KPI_INPUT"), df.tier.eq("KPI_PROXY")],
        ["LOAD_CONTEXT", "NOT_ELIGIBLE", "COMPONENT_PRECURSOR", "KPI_PROXY_PRECURSOR"], "ELIGIBLE")
    df["confidence"] = [confidence(r) for r in df.itertuples()]
    lc = df.lead_time_confidence_uncapped.fillna("LOW")
    df["lead_time_confidence"] = [min(a, b, key=lambda k: CONF_ORDER.get(k, 0)) for a, b in zip(lc, df.confidence)]
    return df.sort_values("indicator_id", kind="mergesort").reset_index(drop=True)


def classify(r) -> str:
    """Relationship taxonomy (precedence order). Correlation is never read as causation."""
    if r.status == "CONTEXT_ONLY":
        return "OPERATING_STATE_OR_LOAD_PROXY"
    if r.repl_months_evaluable < len(REPLICATION_MONTHS) or r.c6_coverage < 0.3:
        return "DATA_QUALITY_LIMITED"
    if r.disc_supported and tb(r.load_confounded):
        return "OPERATING_STATE_OR_LOAD_PROXY"
    if r.gate_a_discovery_supported and r.gate_b_replicates_jun_jul and r.gate_c_survives_feed_controls \
            and r.gate_d_forward_ge_backward and r.gate_f_beats_shift_null:
        return "LEADING"
    if r.gate_a_discovery_supported and r.gate_b_replicates_jun_jul and not r.gate_d_forward_ge_backward:
        return "LAGGING"
    if r.gate_a_discovery_supported:
        return "UNSTABLE_OR_SPURIOUS"
    if np.isfinite(r.repl_rho_contemp) and abs(r.repl_rho_contemp) >= 0.30 and np.isfinite(r.repl_rho_backward) \
            and abs(r.repl_rho_backward) > abs(np.nan_to_num(r.repl_rho_raw)):
        return "LAGGING"
    if np.isfinite(r.repl_rho_contemp) and abs(r.repl_rho_contemp) >= 0.30:
        return "CONTEMPORANEOUS"
    return "NO_SUPPORTED_RELATIONSHIP"


def confidence(r) -> str:
    """Evidence quality from discovery + replication only (the holdout is reported separately, never used here).
    LOAD_CONTEXT -> NOT_APPLICABLE; failing any gate -> INSUFFICIENT; KPI inputs / proxies never above LOW; manipulated,
    May-only and Phase 2 LOW-confidence tags capped at MEDIUM.
    HIGH: EXTERNAL, q <= 0.05, both replication months individually significant, Sp.Heat F / G and state robust, beats
    every circular shift, positive episode lift with >= 8 episodes. MEDIUM: >= 1 replication month individually
    significant and shift-null p < 0.05. LOW: otherwise."""
    if r.status == "CONTEXT_ONLY":
        return "NOT_APPLICABLE"
    if not r.all_gates_pass:
        return "INSUFFICIENT"
    if r.tier in ("KPI_INPUT", "KPI_PROXY"):
        return "LOW"
    capped = any(f in str(r.flags) for f in ("MANIPULATED_VARIABLE", "DISCOVERY_MAY_ONLY", "P2_LOW_BASELINE_CONFIDENCE"))
    high = (r.tier == "EXTERNAL" and r.disc_q_bh <= PRIMARY.fdr_q_high and r.repl_months_sig_same_sign == len(REPLICATION_MONTHS)
            and tb(r.sp_heat_fg_consistent) and tb(r.state_robust) and r.shift_null_p_repl <= P_FLOOR + 1e-12
            and np.isfinite(r.lift_repl) and r.lift_repl > 0 and r.n_episodes_repl >= 8)
    if high and not capped:
        return "HIGH"
    if r.repl_months_sig_same_sign >= 1 and r.shift_null_p_repl < 0.05:
        return "MEDIUM"
    return "LOW"


def select_set(df: pd.DataFrame, F: pd.DataFrame, cfg=PRIMARY, exclude_family: str | None = None) -> pd.DataFrame:
    """Complementary set: ELIGIBLE indicators by score, one per tag, discovery |rho| < cluster_rho with every member,
    and an incremental partial rho (controls + members) on DISCOVERY with CI excluding 0. Returns status per candidate."""
    ctx = ac.build_context(cfg)
    el = df[df.eligibility.eq("ELIGIBLE")]
    if exclude_family:
        el = el[el.process_family != exclude_family]
    el = el.sort_values(["phase4_score", "indicator_id"], ascending=[False, True], kind="mergesort")
    drows = ac.discovery_rows(ctx)
    members, status = [], {}
    for r in el.itertuples():
        c = r.indicator_id
        if any(ac.split_id(m)[0] == r.tag for m in members):
            status[c] = ("ELIGIBLE_REDUNDANT", "another feature of the same tag is already in the set")
            continue
        red = None
        for m in members:
            ok = drows & np.isfinite(F[c].to_numpy()) & np.isfinite(F[m].to_numpy())
            if ok.sum() > 100:
                rho = np.corrcoef(rankdata(F[c].to_numpy()[ok]), rankdata(F[m].to_numpy()[ok]))[0, 1]
                if abs(rho) >= cfg.cluster_rho:
                    red = (m, rho)
                    break
        if red:
            status[c] = ("ELIGIBLE_REDUNDANT", f"discovery |rho| {abs(red[1]):.2f} >= {cfg.cluster_rho} with {red[0]}")
            continue
        if len(members) >= cfg.max_set:
            status[c] = ("ELIGIBLE_NOT_SELECTED", f"set size cap {cfg.max_set}")
            continue
        h = int(r.lag_minutes) // cfg.bucket_min
        y, Z = ac.target_and_controls(ctx, h)
        if members:
            Z = np.column_stack([Z] + [F[m].to_numpy(float) for m in members])
        rows = ac.window_rows(ctx, "DISCOVERY", h)
        blk, _ = ac.blocks(ctx, rows)
        a = ic.assoc(F[c].to_numpy(float), y, Z, rows, blk, cfg.seed + 7, cfg.neff_maxlag, n_boot=cfg.n_boot)
        s = int(r.sign)
        if np.isfinite(a["rho_p"]) and s * a["rho_p"] >= cfg.incr_min_rho and s * a["ci_lo"] > 0 and s * a["ci_hi"] > 0:
            members.append(c)
            status[c] = ("SELECTED", f"incremental discovery rho_p {a['rho_p']:.3f} [{a['ci_lo']:.3f}, {a['ci_hi']:.3f}] "
                                     f"given controls + {len(members) - 1} earlier member(s)")
        else:
            status[c] = ("ELIGIBLE_NOT_INCREMENTAL", f"incremental discovery rho_p {a['rho_p']:.3f} (CI {a['ci_lo']:.3f}, "
                                                     f"{a['ci_hi']:.3f}) below {cfg.incr_min_rho} or CI includes 0")
    return pd.DataFrame([(k, *v) for k, v in status.items()], columns=["indicator_id", "selection_status", "selection_note"])


def incremental(members: list[str], df: pd.DataFrame, F: pd.DataFrame, window: str, cfg=PRIMARY) -> dict:
    ctx = ac.build_context(cfg)
    out = {}
    d = df.set_index("indicator_id")
    for i, c in enumerate(members):
        h = int(d.lag_minutes[c]) // cfg.bucket_min
        y, Z = ac.target_and_controls(ctx, h)
        if i:
            Z = np.column_stack([Z] + [F[m].to_numpy(float) for m in members[:i]])
        rows = ac.window_rows(ctx, window, h)
        blk, _ = ac.blocks(ctx, rows)
        out[c] = ic.assoc(F[c].to_numpy(float), y, Z, rows, blk, cfg.seed + 8, cfg.neff_maxlag, n_boot=cfg.n_boot)
    return out


def direction_text(feat: str, sign: int) -> str:
    if feat.startswith("ROC"):
        return "FALLING_TREND_PRECEDES_KPI_INCREASE" if sign < 0 else "RISING_TREND_PRECEDES_KPI_INCREASE"
    if feat == "VOL_2H":
        return "LOWER_VARIABILITY_PRECEDES_KPI_INCREASE" if sign < 0 else "HIGHER_VARIABILITY_PRECEDES_KPI_INCREASE"
    if feat.startswith("PERSIST"):
        band = "above" if feat.endswith("HI_6H") else "below"
        return (f"MORE_TIME_{band.upper()}_BAND_PRECEDES_KPI_INCREASE" if sign > 0
                else f"LESS_TIME_{band.upper()}_BAND_PRECEDES_KPI_INCREASE")
    return "LOWER_LEVEL_PRECEDES_KPI_INCREASE" if sign < 0 else "HIGHER_LEVEL_PRECEDES_KPI_INCREASE"


FEATURE_CATEGORY = {"LEVEL_1H": "LEVEL", "DEV_1H": "LOAD-ADJUSTED DEVIATION", "ROC_1H": "RATE OF CHANGE (1 h)",
                    "ROC_3H": "RATE OF CHANGE (3 h)", "VOL_2H": "VOLATILITY", "PERSIST_HI_6H": "PERSISTENCE ABOVE BAND",
                    "PERSIST_LO_6H": "PERSISTENCE BELOW BAND"}
THRESHOLD_UNIT = {"LEVEL_1H": "tag unit", "DEV_1H": "robust z (load-adjusted)", "ROC_1H": "robust z per 1 h",
                  "ROC_3H": "robust z per 3 h", "VOL_2H": "log-MAD relative to discovery median",
                  "PERSIST_HI_6H": "share of 6 h (0-1)", "PERSIST_LO_6H": "share of 6 h (0-1)"}


def contract(df: pd.DataFrame, cfg=PRIMARY) -> pd.DataFrame:
    """leading_indicator_set.csv: discovery-supported + selected indicators with everything Phase 5 / 7 / 8 need."""
    pti = read_p1("process_tag_inventory.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column).set_index("tag")
    s = df[df.disc_supported | df.selection_status.eq("SELECTED")].copy()
    grp = s.tag.map(pti.group_header_ffill_candidate).fillna("")
    name = s["original_name"].astype(str)
    disp = [f"{d} · {g + ' | ' if g and g not in n else ''}{n} ({u})" for d, g, n, u in zip(s.dataset, grp, name, s.unit)]
    usable = s.selection_status.eq("SELECTED") & s.relationship_class.eq("LEADING")
    lead_ok = s.relationship_class.eq("LEADING")
    out = pd.DataFrame({
        "indicator_id": s.indicator_id, "display_name": disp,
        "naming_confidence": "AS EXPORTED; Phase 1 label confidence " + s.tag.map(pti.confidence).fillna("?").astype(str)
                             + " - plant confirmation of the tag meaning required",
        "original_name": s["original_name"], "dataset": s.dataset, "source_tag": s.tag, "unit": s.unit,
        "process_family": s.process_family, "feature_type": s.feature_type,
        "feature_category": s.feature_type.map(FEATURE_CATEGORY),
        "feature_definition": s.feature_type.map(lambda f: FEATURE_DOC[f][1]), "tier": s.tier,
        "manipulated_variable": s.manipulated_variable, "flags": s["flags"].fillna("").astype(str),
        "lag_minutes": s.lag_minutes,
        "lead_time_minutes": np.where(lead_ok, s.lag_minutes, np.nan),
        "lead_time_definition": "discovery-chosen lag (pre-declared); feature at t vs KPI change over (t, t+lead]",
        "lead_time_range": np.where(lead_ok, s.posthoc_stable_lag_range, ""),
        "lead_time_range_note": "POST-HOC DESCRIPTIVE (replication Jun-Jul lags with >= half the best effect and CI excluding 0)",
        "lead_time_confidence": np.where(lead_ok, s.lead_time_confidence, "NOT_APPLICABLE (not a leading relationship)"),
        "month_best_lags": s.month_best_lags,
        "median_episode_lead_minutes": np.where(lead_ok, s.median_episode_lead_minutes, np.nan),
        "relationship_direction": [direction_text(f, g) for f, g in zip(s.feature_type, s.sign)],
        "relationship_class": s.relationship_class,
        "effect_size": s.repl_rho_p,
        "effect_size_ci": s.repl_ci_lo.round(3).astype(str) + " .. " + s.repl_ci_hi.round(3).astype(str),
        "effect_size_metric": "partial Spearman rho vs future KPI change beyond the KPI's own level / momentum / known "
                              "persistence (Jun-Jul replication)",
        "discovery_effect_size": s.disc_rho_p, "discovery_q_bh": s.disc_q_bh,
        "jun_effect_size": s.jun_rho_p, "jul_effect_size": s.jul_rho_p,
        "replication_months_same_sign": s.repl_months_same_sign, "replication_months_significant": s.repl_months_sig_same_sign,
        "replication_n_eff": s.repl_n_eff, "shift_null_p": s.shift_null_p_repl,
        "holdout_aug_effect_size": s.holdout_rho_p,
        "holdout_aug_ci": s.holdout_ci_lo.round(3).astype(str) + " .. " + s.holdout_ci_hi.round(3).astype(str),
        "holdout_result": s.holdout_result,
        "stability_score": s[["c2_directional_consistency", "c3_lead_time_stability", "c8_robustness"]].mean(axis=1),
        "coverage": s.c6_coverage, "data_quality_score": s.c7_data_quality,
        "operating_state_conditioned": "RUNNING buckets only; no stop/transition inside the horizon (" + PROXY_LABEL + ")",
        "load_conditioned": s.feature_type.map({"DEV_1H": "FEED-CONDITIONAL REFERENCE"}).fillna("GLOBAL") + np.where(
            s.status.eq("CONTEXT_ONLY"), "; IS THE LOAD CONTEXT", np.where(s.gate_c_survives_feed_controls,
                                                                            "; survives feed controls", "; LOAD-CONFOUNDED")),
        "confidence": s.confidence,
        "n_alarms_jun_jul": s.n_alarms_repl, "alarms_per_7_running_days": s.alarms_per_7_running_days_repl,
        "false_lead_rate": s.false_lead_rate_repl, "precision": s.precision_repl, "base_rate": s.base_rate_repl,
        "precision_lift": s.precision_lift_repl, "episode_hit_rate": s.hit_rate_episode_repl,
        "control_hit_rate": s.hit_rate_control_repl, "episode_lift": s.lift_repl, "n_episodes": s.n_episodes_repl,
        "holdout_false_lead_rate": s.false_lead_rate_holdout, "holdout_precision_lift": s.precision_lift_holdout,
        "interpretability": s.c9_interpretability, "phase4_score": s.phase4_score, "selection_status": s.selection_status,
        "selection_note": s.selection_note.fillna(""),
        "exclusion_reason": np.where(s.selection_status.eq("SELECTED"), "",
                                     np.where(s.failed_gates.ne(""), s.failed_gates,
                                              s.selection_status.str.split(" \\(").str[0] + np.where(
                                                  s.selection_note.fillna("").ne(""), ": " + s.selection_note.fillna(""), ""))),
        "usable_downstream": usable,
        "permitted_use": np.where(usable, "Empirical context feature for later POC phases, with its label; discussion / "
                                          "review only; no operating action, alarm or limit is implied",
                                  "Reference only - do not use as a leading feature"),
        "alarm_threshold": s.alarm_threshold, "alarm_threshold_unit": s.feature_type.map(THRESHOLD_UNIT),
        "alarm_threshold_direction": np.where(s.sign > 0, "at or above", "at or below"),
        "alarm_threshold_rule": f"discovery P{int(cfg.alarm_q * 100)} / P{int(100 - cfg.alarm_q * 100)} of the feature",
        "threshold_label": THRESHOLD_LABEL,
        "quality_mask": "Phase 2 causal cell tokens; Phase 3 causal flatline/frozen masks (+ small-dataset frozen rule outside the KPI subset)",
        "operating_state_filter": "kpi_core.causal_state (Phase 3, causal) -> RUNNING",
        "load_filter": "none (primary); feed controls and GMM feed bands in sensitivity",
        "reference": "outputs/indicator_feature_reference.json[" + s.tag + "]",
        "training_window": f"{cfg.disc_start} .. {cfg.disc_end}",
        "evaluation_window": f"replication {cfg.eval_jun[0]} .. {cfg.eval_jul[1]}; holdout {cfg.eval_aug[0]} .. 2025-08-23",
        "method_version": METHOD_VERSION, "config_key": cfg.key(), "label": INDICATOR_LABEL})
    out["_o"] = out.selection_status.eq("SELECTED").map({True: 0, False: 1})
    return out.sort_values(["_o", "phase4_score", "indicator_id"], ascending=[True, False, True], kind="mergesort").drop(columns="_o")


def main():
    cfg = PRIMARY
    F = ac.load_features()
    df = build_scores(F, cfg)
    sel = select_set(df, F, cfg)
    df = df.merge(sel, on="indicator_id", how="left")
    df["selection_status"] = df.selection_status.fillna(df.eligibility.map({
        "COMPONENT_PRECURSOR": "COMPONENT_PRECURSOR (KPI input; never in the set)",
        "KPI_PROXY_PRECURSOR": "KPI_PROXY_PRECURSOR (near-duplicate of a KPI input; never in the set)",
        "LOAD_CONTEXT": "LOAD_CONTEXT (never eligible)"})).fillna("NOT_SELECTED")
    members = df[df.selection_status.eq("SELECTED")].sort_values(["phase4_score", "indicator_id"], ascending=[False, True]).indicator_id.tolist()
    for w, pre in (("REPL", "repl"), (HOLDOUT, "holdout")):
        inc = incremental(members, df, F, w, cfg)
        df[f"incremental_{pre}_rho_p"] = df.indicator_id.map({k: v["rho_p"] for k, v in inc.items()})
        df[f"incremental_{pre}_ci"] = df.indicator_id.map({k: f"[{v['ci_lo']:.3f}, {v['ci_hi']:.3f}]" for k, v in inc.items()})
    write_csv(df, "indicator_scores.csv", lg)

    # ---------------------------------------------------------------- ranking / set sensitivity summary rows
    sens = read_out("indicator_sensitivity.csv")
    summ = []
    pool = df[df.disc_supported]
    for crit in CRITERIA:
        alt = pool[[c for c in CRITERIA if c != crit]].mean(axis=1)
        rho = float(np.corrcoef(rankdata(pool.phase4_score), rankdata(alt))[0, 1]) if len(pool) > 2 else np.nan
        summ.append({"variant": f"LEAVE_OUT_{crit}", "group": "I scoring weights", "indicator_id": "ALL_SUPPORTED",
                     "rho_variant": rho, "consistent": float(rho >= MATERIALITY["score_spearman_min"]),
                     "note": f"Spearman of phase4_score vs score without {crit} over {len(pool)} discovery-supported indicators"})
    prim = set(members)
    fams = sorted(set(df[df.eligibility.eq("ELIGIBLE")].process_family) | set(pool.process_family))
    for fam in fams:
        s2 = select_set(df.drop(columns=["selection_status", "selection_note"]), F, cfg, exclude_family=fam)
        alt = set(s2[s2.selection_status.eq("SELECTED")].indicator_id)
        base = {m for m in prim if df.set_index("indicator_id").process_family[m] != fam}
        jac = len(alt & base) / len(alt | base) if alt | base else 1.0
        summ.append({"variant": f"FAMILY_REMOVED_{fam}", "group": "H feature family", "indicator_id": "SET",
                     "rho_variant": jac, "consistent": float(jac >= MATERIALITY["set_jaccard_min"]),
                     "note": f"set without {fam}: {sorted(alt)}; primary set minus {fam}: {sorted(base)} "
                             f"(Jaccard = 1 when both are empty)"})
    fg = sens[sens.variant.isin(["SP_HEAT_F_TARGET", "SP_HEAT_G_TARGET"])].pivot(index="indicator_id", columns="variant",
                                                                                values="rho_variant").dropna()
    tier = df.set_index("indicator_id").tier
    for label, sub in (("ALL_SUPPORTED", fg), ("NON_KPI_INPUT", fg[tier.reindex(fg.index).ne("KPI_INPUT")])):
        if len(sub) > 2:
            rho = float(np.corrcoef(rankdata(sub.iloc[:, 0].abs()), rankdata(sub.iloc[:, 1].abs()))[0, 1])
            summ.append({"variant": f"SP_HEAT_F_VS_G_RANKING_{label}", "group": "E Sp.Heat", "indicator_id": "ALL_SUPPORTED",
                         "rho_variant": rho, "consistent": float(rho >= MATERIALITY["fg_rank_rho_min"]),
                         "note": f"Spearman of |rho| under the F-only vs G-only KPI target over {len(sub)} supported "
                                 f"indicators ({label.replace('_', ' ').lower()})"})
    sens = pd.concat([sens[~sens.group.isin(["I scoring weights", "H feature family"])
                           & ~sens.variant.str.startswith("SP_HEAT_F_VS_G_RANKING")], pd.DataFrame(summ)], ignore_index=True)
    write_csv(sens, "indicator_sensitivity.csv", lg)
    write_csv(contract(df, cfg), "leading_indicator_set.csv", lg)
    lg.info("eligible %d; set %s; classes %s; confidence %s", int(df.eligibility.eq("ELIGIBLE").sum()), members,
            df[df.disc_supported].relationship_class.value_counts().to_dict(),
            df[df.disc_supported].confidence.value_counts().to_dict())


if __name__ == "__main__":
    main()
