"""Run the complete Phase 8 pipeline (Early Warning Validation of the frozen Phase 7 score).

  ../../.venv/bin/python run_phase8.py            # run; the previous outputs are used for the determinism check
  ../../.venv/bin/python run_phase8.py --clean    # delete Phase 8 outputs/, reports/, cache/ first

analyse() is pure with respect to the filesystem (reads Phase 6 / 7 artifacts, returns DataFrames); write() writes
outputs/; validation.gates() evaluates G1-G12; report_generation writes reports/. The source directory, Phase 1-7
outputs / scripts / tests / cache / reports and the Phase 7 frozen references are snapshotted before and after
(Phase 8 writes nothing upstream). Unit tests run in a subprocess (fixed argument list, no shell). Only
phase-08-early-warning/{outputs,reports,cache} are ever deleted.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

import build_controls as bc  # noqa: E402
import build_event_windows as bew  # noqa: E402
import lead_time  # noqa: E402
import load_sensitivity as ls  # noqa: E402
import negative_controls as nc  # noqa: E402
import o2_sensitivity as o2s  # noqa: E402
import robustness as rb  # noqa: E402
import temporal_validation as tv  # noqa: E402
import warning_metrics as wm  # noqa: E402
from p8common import (CACHE, CFG, MONTHS, OUT, P6_OUT, P7_CACHE, P7_CACHE_INPUTS, P7_FROZEN, P7_OUT,  # noqa: E402
                      P7_REQUIRED, PHASE_DIR, REPORTS, ROOT, SOURCE_ROOT, VERSION, WARNINGS, P8Config, log, sha256,
                      write_csv, write_parquet)

lg = log("run_phase8")
HERE = Path(__file__).parent
KEY_OUTPUTS = ["early_warning_event_validation.parquet", "early_warning_horizon_validation.csv",
               "early_warning_control_validation.csv", "early_warning_negative_controls.csv",
               "early_warning_o2_sensitivity.csv", "early_warning_load_sensitivity.csv",
               "early_warning_trajectories.parquet", "early_warning_summary.csv", "early_warning_data_quality.csv",
               "early_warning_episodes.parquet"]
REPORT_FILES = ["PHASE_8_EARLY_WARNING_VALIDATION_REPORT.md", "PHASE_8_EARLY_WARNING_VALIDATION_REPORT.html"]
FIRST_PASS = CACHE / "report_first_pass.sha256.json"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
       "MKL_NUM_THREADS": "1"}
OWNED = (OUT, REPORTS, CACHE)
VARIANT = o2s.VARIANT


# ============================================================================== analysis
def prepare(cfg: P8Config = CFG) -> tuple[dict, dict]:
    B = bew.load_base(cfg)
    B["cand_free"] = bc.candidate_free(B["ix"], B["eps"], cfg)
    B["clean"] = bc.clean_mask(B["ix"], B["eps"], B["events"], cfg)
    B["elig"] = bc.eligibility(B["clean"], B["oper"], B["dq"], cfg)
    stored = B["s"].risk_score.to_numpy(float)
    P = bew.make_signals(np.where(B["oper"], stored, B["core_R"]), B, "PRIMARY", cfg)
    o2_all, o2_ref = o2s.o2_excluded_score(B)
    O = bew.make_signals(o2_all, B, VARIANT, cfg)
    O["ref_quantiles_phase7"] = o2_ref["reference_score_quantiles"]
    return B, {"PRIMARY": P, VARIANT: O}


def variant_base(B: dict) -> dict:
    """The O2-excluded variant is evaluated on its own event set: the analyser it excludes cannot contaminate it."""
    return {**B, "events": B["events"].assign(evaluable=B["events"].evaluable_o2x)}


def alert_rows(sig: dict, B: dict, cfg: P8Config = CFG) -> tuple[list[dict], pd.DataFrame]:
    """EMPIRICAL_ALERT_RATE over ordinary running (never a detector error rate) + the warning-episode table."""
    rows, tabs = [], []
    ordinary = B["elig"][0]
    for w, f in sig["flags"].items():
        eps = wm.episodes(f, B["oper"], cfg.gap_tol_buckets)
        tab = wm.episode_table(w, eps, B["ix"], B["s"], sig, B["clean"])
        tab.insert(0, "score_variant", sig["name"])
        tabs.append(tab)
        for m, name in [(0, "JUN-AUG")] + list(MONTHS.items()):
            mm = ordinary & ((B["month"] == m) if m else True)
            t = tab[tab.ordinary_running & ((tab.month == m) if m else True)] if len(tab) else tab
            d = t.duration_minutes.to_numpy(float) if len(t) else np.array([])
            hours = mm.sum() / 6
            rows.append({"section": "EMPIRICAL_ALERT_RATE", "variant": sig["name"], "warning_type": w, "slice": name,
                         "ordinary_running_hours": hours, "share_of_running_time_flagged": float(f[mm].mean()),
                         "n_episodes": len(t), "episodes_per_100h": 100 * len(t) / hours if hours else np.nan,
                         "median_duration_minutes": float(np.median(d)) if d.size else np.nan,
                         "p90_duration_minutes": float(np.quantile(d, 0.9)) if d.size else np.nan})
    return rows, pd.concat(tabs, ignore_index=True)


def per_variant(sig: dict, B: dict, cfg: P8Config = CFG) -> dict:
    name = sig["name"]
    hz, hres = tv.horizon_rows(sig, B, cfg, name)
    primary = hres[cfg.primary_h]
    lo = tv.loeo(sig["rank"], B, cfg.primary_h, name, cfg)
    load_df, load_keep = ls.table(sig["rank"], B, name, cfg)
    ev = B["events"]
    p0, p6 = ev.pos_T0.to_numpy(), ev.pos_T0.to_numpy() - 36
    chg = sig["rank"][p0] - np.where(p6 >= 0, sig["rank"][np.maximum(p6, 0)], np.nan)
    arows, eps = alert_rows(sig, B, cfg)
    ok = primary["ok"]
    return {"horizon_df": hz, "hres": hres, "primary": primary, "loeo": lo,
            "primary_status": tv.primary_status(primary, float(np.nanmin(lo)) if np.isfinite(lo).any() else np.nan,
                                                cfg),
            "load_df": load_df, "load": load_keep, "months": tv.month_rows(sig["rank"], B, cfg, name),
            "snap": tv.snapshot_effects(sig["rank"], B, cfg, name), "alert_rows": arows, "episodes": eps,
            "alert_share": o2s.ordinary_alert_share(sig["flags"], B),
            "pre_rank_change": float(np.nanmedian(chg[ok])) if ok.any() else np.nan,
            "neg": nc.run(sig, B, primary, cfg).assign(score_variant=name)}


def horizon_table(res: dict, B: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    P, O = res["PRIMARY"], res[VARIANT]
    out = []
    for name, r in (("PRIMARY", P), (VARIANT, O)):
        h = r["horizon_df"].copy()
        load = r["load_df"].set_index("horizon_minutes")
        h["load_adjusted_effect"] = h.horizon_minutes.map(load.load_adjusted_effect)
        h["load_status"] = h.horizon_minutes.map(load.status)
        h["coverage_binom_p"] = [stats.binomtest(int(k), int(n), float(p), alternative="greater").pvalue
                                 if n and np.isfinite(p) and 0 < p < 1 else np.nan
                                 for k, n, p in zip(h.n_covered, h.n_evaluable, h.empirical_alert_rate)]
        out.append(h)
    h = pd.concat(out, ignore_index=True)
    o2cov = h[h.score_variant == VARIANT].set_index(["warning_type", "horizon_minutes"]).coverage
    h["o2_excluded_coverage"] = [o2cov.get((w, m), np.nan) for w, m in zip(h.warning_type, h.horizon_minutes)]
    cols = ["score_variant", "warning_type", "horizon_minutes", "is_primary", "n_events", "n_evaluable", "n_controls",
            "coverage", "n_covered", "median_lead_time", "p25_lead_time", "p75_lead_time", "median_rank_change",
            "effect_size", "bootstrap_ci_low", "bootstrap_ci_high", "permutation_p", "bh_q", "empirical_alert_rate",
            "coverage_binom_p", "o2_excluded_coverage", "load_adjusted_effect", "load_status", "median_event",
            "median_control", "status"]
    return h[cols]


def control_table(res: dict, B: dict, sig: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    rows = []
    add = lambda t, r, st=None: rows.append({  # noqa: E731
        "control_type": t, "horizon_minutes": r["horizon_minutes"], "n_controls": r["n_controls"],
        "n_events": r["n_evaluable"], "risk_rank_effect": r["pe"], "effect_size": r["cliffs_delta"],
        "p_value": r["p_value"], "bootstrap_ci_low": r["ci_low"], "bootstrap_ci_high": r["ci_high"],
        "status": st or tv.secondary_status(r, r["p_value"], cfg)})
    P = res["PRIMARY"]
    state_key = np.array([f"{m}|{s}" for m, s in zip(B["month"], bc.settling(B["s"]))], dtype=object)
    for h in cfg.horizons:
        add("ORDINARY_RUNNING_MONTH_MATCHED (primary)", P["hres"][h])
        for k, t in (("MATCHED_LOAD", "MONTH_X_LOAD_STRATUM_MATCHED"), ("MATCHED_LOAD_ANY_MONTH", "LOAD_STRATUM_MATCHED"),
                     ("TRANSITION_EXCLUDED", "STEADY_LOAD_TRANSITION_EXCLUDED"), ("LOW_FEED_EXCLUDED",
                                                                                   "LOW_FEED_EXCLUDED")):
            add(t, P["load"][h][k])
        add("OPERATING_STATE_MATCHED (month x post-restart settling)",
            tv.endpoint(sig["rank"], B, h, f"STATE|h{h}", cfg, key=state_key, boot=h == cfg.primary_h))
    neg = P["neg"].set_index("control_id")
    for cid, t in (("NC2", "RANDOM_PSEUDO_ONSETS (NC2)"), ("NC1", "CIRCULAR_SHIFT (NC1)")):
        rows.append({"control_type": t, "horizon_minutes": cfg.primary_h, "n_controls": int(neg.at[cid, "n_null"]),
                     "risk_rank_effect": neg.at[cid, "null_effect"], "p_value": neg.at[cid, "p_value"],
                     "status": neg.at[cid, "status"]})
    return pd.DataFrame(rows)


def dq_table(B: dict, P: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    rows = [{"section": "INPUT", "metric": "rescore_max_abs_diff_vs_stored_risk_score", "value": B["rescore"]["max_abs_diff"],
             "note": f"nan pattern equal: {B['rescore']['nan_pattern_equal']}"}]
    for e in B["events"].itertuples():
        rows.append({"section": "EVENT_WINDOW_DQ", "metric": e.event_id, "value": e.data_quality_status,
                     "note": f"T0 {e.T0}; reason {e.data_quality_reason}; evaluable {e.evaluable}; O2-excluded "
                             f"variant status {e.data_quality_status_o2x}"})
    s = B["s"]
    for m in (4, 5, 6, 7, 8, 9):
        mm = B["month"] == m
        rows.append({"section": "MONTH_COVERAGE", "metric": f"month_{m:02d}", "value": int(B["oper"][mm].sum()),
                     "note": "operational buckets; " + ", ".join(f"{k} {v}" for k, v in
                                                               s.risk_status[mm].value_counts().sort_index().items())})
    for h in sorted(B["elig"]):
        for m, name in MONTHS.items():
            rows.append({"section": "CONTROL_POOL", "metric": f"eligible_controls_h{h}_{name}",
                         "value": int((B["elig"][h] & (B["month"] == m)).sum()), "note": ""})
    rows.append({"section": "CONTROL_POOL", "metric": "clean_operational_share_jun_aug",
                 "value": float(B["clean"][B["oper"]].mean()), "note": "share of operational buckets outside all "
                 "Phase 6 candidate extents (+6 h) and the 24 h before every final onset"})
    out = pd.concat([pd.DataFrame(rows), o2s.analyser_behaviour(P, B, cfg)], ignore_index=True)
    out["value"] = out["value"].astype(str)
    return out


def findings(res: dict, rob: pd.DataFrame, hz: pd.DataFrame, cs: pd.DataFrame, cfg: P8Config = CFG) -> list[dict]:
    """Section 55: every major finding in exactly one class. Only F1 (primary rule), F5 (same rule on the variant) and
    F6 (load verdict) apply rules pre-declared in the spec; the F2-F20 rules were written after the analyses were
    built and are post hoc (spec section 16)."""
    P, O = res["PRIMARY"], res[VARIANT]
    pr, st = P["primary"], P["primary_status"]
    hp = hz[(hz.score_variant == "PRIMARY") & (hz.warning_type == "W1_RANK")].set_index("horizon_minutes")
    rb_ = rob.set_index("check")
    neg = P["neg"].set_index("control_id")
    mo = P["months"]
    mon = mo[mo.section == "MONTH"]
    lomo = mo[mo.section == "LEAVE_ONE_MONTH_OUT"]
    lv = P["load_df"].set_index("horizon_minutes").status[cfg.primary_h]
    F = []
    add = lambda k, c, ev: F.append({"section": "FINDING", "finding": k, "classification": c, "evidence": ev})  # noqa
    add("F1 Risk rank elevated in the 60 min before empirical abnormal-period onsets vs month-matched ordinary running "
        "(PRIMARY ENDPOINT)", st,
        f"PE {pr['pe']:+.3f} rank units, 95% CI [{pr['ci_low']:+.3f}, {pr['ci_high']:+.3f}], NC2 p {pr['p_value']:.4f}, "
        f"Cliff's delta {pr['cliffs_delta']:+.2f}, n {pr['n_evaluable']}/{pr['n_events']}")
    hs = [h for h in cfg.horizons if h > cfg.primary_h]
    longer = [hp.status.get(h) for h in hs]
    csp = cs[cs.variant == "PRIMARY"].set_index(["slice", "horizon_minutes"])
    add("F2 Rank elevation at horizons beyond 1 h (2-24 h windows; WEAK uses raw p < 0.10, SUPPORTED needs BH q < 0.05)",
        "SUPPORTED" if longer[0] == "SUPPORTED" and longer[1] == "SUPPORTED" else
        "WEAK" if any(s in ("SUPPORTED", "WEAK") for s in longer) else
        "INSUFFICIENT_DATA" if all(s == "INSUFFICIENT_DATA" for s in longer) else "NOT_SUPPORTED",
        "; ".join(f"{h} min {s} (p {hp.permutation_p[h]:.3f}, q {hp.bh_q[h]:.3f}, n {int(hp.n_evaluable[h])}; "
                  f"censored PE {csp.pe.get(('CENSORED', h), np.nan):+.3f} vs uncensored "
                  f"{csp.pe.get(('UNCENSORED', h), np.nan):+.3f})" for h, s in zip(hs, longer)) +
        f"; about {0.10 * len(hs):.1f} of {len(hs)} horizons are expected below raw p 0.10 under the null; the excess "
        "is consistent with within-shift persistence of censored onsets")
    wr = hz[(hz.score_variant == "PRIMARY") & (hz.horizon_minutes == cfg.primary_h)].set_index("warning_type")
    for w in WARNINGS:
        r = wr.loc[w]
        c = ("INSUFFICIENT_DATA" if r.n_evaluable < cfg.min_events_secondary else
             "SUPPORTED" if r.coverage_binom_p < 0.05 / len(WARNINGS) else
             "WEAK" if r.coverage_binom_p < 0.10 / len(WARNINGS) else "NOT_SUPPORTED")
        add(f"F3 {w}: coverage in the 60-min pre-onset window exceeds the control-window warning rate", c,
            f"coverage {r.coverage:.2f} ({int(r.n_covered)}/{int(r.n_evaluable)}) vs control-window rate "
            f"{r.empirical_alert_rate:.2f}; binomial p {r.coverage_binom_p:.4f} (Bonferroni over 5 warnings)")
    add("F4 Direction of the point estimate consistent across June / July / August (each month too small to test)",
        "WEAK" if (mon.pe > 0).all() and (lomo.pe > 0).all() else "NOT_SUPPORTED",
        "; ".join(f"{r.slice} PE {r.pe:+.3f} (n {r.n_evaluable})" for r in mon.itertuples()) +
        "; leave-one-month-out: " + "; ".join(f"{r.slice} {r.pe:+.3f} p {r.p_value:.3f}" for r in lomo.itertuples()) +
        " (per-month n < 6: month-level SUPPORTED impossible by design)")
    o, os_, ss = O["primary"], O["primary_status"], O["same_set"]
    add("F5 60-min pre-onset rank elevation with the kiln-inlet O2 analyser (Kiln-I!X) excluded (primary decision rule "
        f"applied to the O2-excluded VALIDATION_VARIANT; {o2s._status(st, os_)})", os_,
        f"like-for-like (the primary's {ss['n_evaluable']} periods): PE {ss['pe']:+.3f} vs primary {pr['pe']:+.3f} "
        f"(difference {ss['pe'] - pr['pe']:+.3f}), p {ss['p_value']:.4f} - same direction, not significant at 0.05; "
        f"own event set (post-result amendment): PE {o['pe']:+.3f}, CI [{o['ci_low']:+.3f}, {o['ci_high']:+.3f}], "
        f"p {o['p_value']:.4f}, n {o['n_evaluable']}; a second test of the same hypothesis, not multiplicity-adjusted")
    add("F6 Primary result survives load adjustment / matching / transition exclusion",
        {"ROBUST_TO_LOAD": "SUPPORTED", "ATTENUATED": "WEAK", "NOT_ROBUST": "NOT_SUPPORTED",
         "NOT_APPLICABLE": "NOT_SUPPORTED"}.get(lv, "INSUFFICIENT_DATA"),
        f"load verdict {lv}: " + ", ".join(f"{k} {P['load'][cfg.primary_h][k]['pe']:+.3f} "
                                           f"(p {P['load'][cfg.primary_h][k]['p_value']:.3f}, "
                                           f"n {P['load'][cfg.primary_h][k]['n_evaluable']})"
                                           for k in ("LOAD_ADJUSTED", "MATCHED_LOAD", "TRANSITION_EXCLUDED",
                                                     "LOW_FEED_EXCLUDED")))
    p1, p2 = neg.at["NC1", "p_value"], neg.at["NC2", "p_value"]
    add("F7 Effect distinguishable from circular-shift (NC1) and random-onset (NC2) nulls",
        "SUPPORTED" if p1 < 0.05 and p2 < 0.05 else "WEAK" if min(p1, p2) < 0.05 else "NOT_SUPPORTED",
        f"NC1 p {p1:.4f} (null median {neg.at['NC1', 'null_effect']:+.3f}); NC2 p {p2:.4f} "
        f"(null median {neg.at['NC2', 'null_effect']:+.3f})")
    lo = P["loeo"][np.isfinite(P["loeo"])]
    add("F8 Sign of the primary point estimate not driven by a single abnormal period (leave-one-event-out; sign "
        "stability only, not significance)", "SUPPORTED" if lo.size and lo.min() > 0 else "NOT_SUPPORTED",
        f"LOEO PE range [{lo.min():+.3f}, {lo.max():+.3f}] over {lo.size} fits; primary endpoint itself {st}")
    k, r0 = rb_.loc["KPI_BASELINE"], rb_.loc[f"BLOCK_LENGTH_{cfg.block_hours}H"]
    add("F9 Risk score carries pre-onset information beyond the Phase 3 KPI itself (KPI persistence)",
        "WEAK" if r0.cliffs_delta - k.cliffs_delta > 0.10 else "NOT_SUPPORTED",
        f"Cliff's delta risk {r0.cliffs_delta:+.2f} vs KPI {k.cliffs_delta:+.2f} (KPI PE {k.pe:+.3f}, p "
        f"{k.p_value:.4f}); no formal test of the difference (n = 12)")
    rr = rb_.loc["REFERENCE_FREE_ROLLING_RANK"]
    neutral = abs(rr.median_control - 0.5) <= nc.NULL_TOL
    add("F10 Pre-onset rank elevation relative to the preceding 7 days (reference-free rolling rank; checks for a "
        "Phase 7 reference artefact, not independent of the KPI onset)",
        ("NOT_SUPPORTED" if not neutral else rr.status) if rr.status != "REPORTED" else "INSUFFICIENT_DATA",
        f"rolling-rank PE {rr.pe:+.3f}, CI [{rr.ci_low:+.3f}, {rr.ci_high:+.3f}], p {rr.p_value:.4f}; control median "
        f"rolling rank {rr.median_control:.2f} (0.50 expected for neutral controls"
        + ("" if neutral else "; the controls are selected low-KPI time, so the comparison is biased and cannot "
           "support the claim") + "); a rise relative to the preceding week is also what a KPI CUSUM onset implies")
    post = neg.at["NC3", "null_effect"]
    add("F11 Pre-onset association at least as strong as the post-period (backward) association",
        "SUPPORTED" if pr["pe"] >= post else "NOT_SUPPORTED",
        f"pre-onset PE {pr['pe']:+.3f} vs post-end PE {post:+.3f} (trailing-window persistence expected)")
    det = rb_.loc["DETECTION_ANCHOR (CIRCULARITY_ILLUSTRATION)"]
    add("F12 'Lead' before Phase 6 detection (KPI >= P90) as independent evidence", "NOT_SUPPORTED",
        f"detection-anchored PE {det.pe:+.3f}: mechanical - the KPI is a 6-h median of the same components")
    p4 = rb_.loc["PHASE4_INDICATOR_CONTEXT (historical sensitivity only)"]
    add("F13 Phase 4 indicator Kiln-I!I|ROC_1H adds pre-onset information",
        "WEAK" if p4.p_value < 0.05 else "NOT_SUPPORTED",
        f"active at T0 in {p4.median_event:.2f} of periods vs {p4.median_control:.2f} of controls, p {p4.p_value:.3f}")
    add("F14 A deployable early-warning alert threshold", "BLOCKED",
        "thresholds were frozen from independent populations and evaluated, but an alert threshold needs event ground "
        "truth (costs of missed / unnecessary alerts); month-holdout and LOEO results are validation diagnostics only")
    add("F15 Deposit / ring / coating / failure / maintenance early warning", "BLOCKED",
        "no plant event ground truth in the supplied data (Phase 1 EVENT GROUND TRUTH NOT FOUND)")
    add("F16 Lead time to plant events", "BLOCKED", "no plant event timestamps")
    add("F17 Origin of the ambient-like kiln-inlet O2 readings", "BLOCKED",
        "ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION (purge / calibration behaviour of Kiln-I!X)")
    cen = rb_.loc["EXCLUDE_CENSORED_ONSETS"]
    add("F18 Pre-onset rank elevation present among uncensored onsets (the shift had not begun before the 6-h "
        "look-back)", cen.status,
        f"uncensored onsets only: PE {cen.pe:+.3f} ({'negative' if cen.pe < 0 else 'positive'} direction), p "
        f"{cen.p_value:.4f}, n {int(cen.n_evaluable)} (all evaluable: PE {pr['pe']:+.3f}, n {pr['n_evaluable']}); "
        f"censored-only PE {csp.pe.get(('CENSORED', cfg.primary_h), np.nan):+.3f}. A censored T0 is the look-back cap, "
        "so its window lies inside the KPI shift; an uncensored T0 is the CUSUM zero, a local low - the 60-min endpoint "
        "cannot measure precedence for either group")
    for chk, fid, what in (("CONTROLS_SAME_DQ_RULE_AS_EVENTS", "F19", "with the event data-quality rule (POOR share, "
                            "stop / transition) applied to control windows too"),
                           ("CONTROLS_EXCLUDE_FINAL_PERIODS_ONLY", "F20", "with controls that exclude only the 12 "
                            "final periods (not the other KPI >= P90 candidates)")):
        r = rb_.loc[chk]
        add(f"{fid} 60-min pre-onset rank elevation {what}", r.status,
            f"PE {r.pe:+.3f}, CI [{r.ci_low:+.3f}, {r.ci_high:+.3f}], p {r.p_value:.4f}, n {int(r.n_evaluable)}, "
            f"{int(r.n_controls)} controls, control median {r.median_control:.3f} (primary {pr['median_control']:.3f})")
    return F


def analyse(cfg: P8Config = CFG) -> dict:
    t = time.time()
    B, sigs = prepare(cfg)
    lg.info("prepared base + signals in %.1fs (%d events, %d operational buckets)", time.time() - t,
            len(B["events"]), int(B["oper"].sum()))
    B_o2x = variant_base(B)
    res = {"PRIMARY": per_variant(sigs["PRIMARY"], B, cfg), VARIANT: per_variant(sigs[VARIANT], B_o2x, cfg)}
    res[VARIANT]["same_set"] = tv.endpoint(sigs[VARIANT]["rank"], B, cfg.primary_h, f"{VARIANT}|SAME_SET", cfg)
    lg.info("per-variant analyses done in %.1fs", time.time() - t)
    P = sigs["PRIMARY"]
    rob, _ = rb.run(P, B, cfg)
    cs = pd.concat([rb.censored_split(P, B, cfg), rb.censored_split(sigs[VARIANT], B_o2x, cfg)], ignore_index=True)
    hz = horizon_table(res, B, cfg)
    ev_tab = lead_time.event_table(B, sigs, res["PRIMARY"]["primary"], res[VARIANT]["primary"], cfg)
    snaps = [res[n]["snap"] for n in res]
    for m, name in MONTHS.items():
        snaps.append(tv.snapshot_effects(P["rank"], B, cfg, f"PRIMARY|MONTH_{name}",
                                         ev_mask=B["events"].month.eq(m).to_numpy()).assign(section="TRAJECTORY_BY_MONTH"))
    for sev in ("HIGH", "MODERATE", "LOW"):
        snaps.append(tv.snapshot_effects(P["rank"], B, cfg, f"PRIMARY|SEVERITY_{sev}",
                                         ev_mask=B["events"].severity.eq(sev).to_numpy()).assign(
            section="TRAJECTORY_BY_SEVERITY (context only)"))
    pr = res["PRIMARY"]["primary"]
    thr_rows = [{"section": "THRESHOLDS", "variant": n, "metric": k, "value": v, "note": sg["thr"]["source"]}
                for n, sg in sigs.items() for k, v in sg["thr"].items() if k not in ("ref_sorted", "source",
                                                                                   "ref_quantiles")]
    thr_rows += [{"section": "THRESHOLDS", "variant": n, "metric": f"reference_{k}", "value": v,
                  "note": "rebuilt Apr-May reference ECDF (must equal risk_score_reference.json for PRIMARY)"}
                 for n, sg in sigs.items() for k, v in sg["thr"]["ref_quantiles"].items()]
    prim = [{"section": "PRIMARY_ENDPOINT", "variant": n, "metric": k, "value": res[n]["primary"][k]}
            for n in res for k in ("pe", "ci_low", "ci_high", "p_value", "cliffs_delta", "n_evaluable", "n_events",
                                   "n_controls", "median_event", "median_control", "null_median")]
    prim += [{"section": "PRIMARY_ENDPOINT", "variant": n, "metric": "status", "value": res[n]["primary_status"]}
             for n in res]
    prim += [{"section": "PRIMARY_ENDPOINT", "variant": n, "metric": f"loeo_{e}", "value": v}
             for n in res for e, v in zip(B["events"].event_id, res[n]["loeo"])]
    summary = pd.concat([pd.DataFrame(prim), pd.DataFrame(thr_rows), pd.concat(snaps, ignore_index=True),
                         lead_time.lead_summary(ev_tab), pd.DataFrame(res["PRIMARY"]["alert_rows"]),
                         pd.DataFrame(res[VARIANT]["alert_rows"]), res["PRIMARY"]["months"],
                         res[VARIANT]["months"], tv.month_holdout(P, B, cfg), tv.loeo_threshold_rows(P, B, cfg), rob,
                         cs, pd.DataFrame(findings(res, rob, hz, cs, cfg))], ignore_index=True)
    summary.insert(0, "phase8_version", VERSION)
    out = {"early_warning_event_validation.parquet": ev_tab,
           "early_warning_horizon_validation.csv": hz,
           "early_warning_control_validation.csv": control_table(res, B, P, cfg),
           "early_warning_negative_controls.csv": pd.concat([res[n]["neg"] for n in res], ignore_index=True),
           "early_warning_o2_sensitivity.csv": o2s.comparison(P, sigs[VARIANT], res, B, cfg),
           "early_warning_load_sensitivity.csv": pd.concat([res[n]["load_df"] for n in res], ignore_index=True),
           "early_warning_trajectories.parquet": bew.trajectories(B, sigs, cfg),
           "early_warning_summary.csv": summary,
           "early_warning_data_quality.csv": dq_table(B, P, cfg),
           "early_warning_episodes.parquet": pd.concat([res[n]["episodes"] for n in res], ignore_index=True)}
    lg.info("analysis done in %.1fs: PE %+.3f p %.4f -> %s", time.time() - t, pr["pe"], pr["p_value"],
            res["PRIMARY"]["primary_status"])
    return {"outputs": out, "B": B, "sigs": sigs, "res": res}


def write(outputs: dict) -> None:
    for name, df in outputs.items():
        (write_parquet if name.endswith(".parquet") else write_csv)(df, name, lg)


# ============================================================================== integrity / orchestration
def file_hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def upstream_snapshot() -> dict:
    snap = {}
    for base in sorted(ROOT.glob("phase-0[1-7]-*")):
        for sub in ("outputs", "scripts", "tests", "cache", "reports", "docs"):
            d = base / sub
            if d.exists():
                snap.update({str(p.relative_to(ROOT)): (p.stat().st_size, p.stat().st_mtime_ns)
                             for p in sorted(d.rglob("*")) if p.is_file()})
    for d in (ROOT / "data" / "processed", ROOT / "data" / "curated", ROOT / "data" / "raw"):
        snap.update({str(p.relative_to(ROOT)): (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.glob("*"))
                     if p.is_file()})
    return snap


def frozen_hashes() -> dict:
    return {n: sha256(P7_OUT / n) for n in P7_FROZEN}


def source_snapshot() -> dict:
    return {str(p.relative_to(SOURCE_ROOT)): (sha256(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(SOURCE_ROOT.rglob("*")) if p.is_file()}


def clean() -> None:
    for d in OWNED:
        if d.resolve().parent != PHASE_DIR.resolve():
            raise RuntimeError(f"refusing to delete {d}")
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        if d != CACHE:
            (d / ".gitkeep").touch()
    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)
    lg.info("[clean] removed Phase 8 outputs/, reports/, cache/")


def write_manifest(run_info: dict, is_clean: bool) -> None:
    """outputs/run_manifest.json: provenance of this run (not part of the determinism comparison)."""
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()  # noqa: E731
    inputs = [P7_OUT / n for n in P7_REQUIRED] + [P7_CACHE / n for n in P7_CACHE_INPUTS] + \
             [P6_OUT / "abnormal_episodes.parquet"]
    m = {"phase8_version": VERSION, "clean_run": is_clean, "git_commit": git("rev-parse", "HEAD"),
         "git_dirty": bool(git("status", "--porcelain", "--", str(PHASE_DIR))),
         "python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
         "scipy": __import__("scipy").__version__, "config": CFG.as_dict(),
         "inputs_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
         "n_source_files": run_info["n_src"], "n_upstream_files": run_info["n_upstream"],
         "determinism": run_info["determinism"], "tests_rc": run_info["tests_rc"]}
    (OUT / "run_manifest.json").write_text(json.dumps(m, indent=1, sort_keys=True, default=str), encoding="utf-8")


def run_tests() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(PHASE_DIR / "tests"), "-t",
                        str(PHASE_DIR / "tests")], cwd=HERE, env=ENV, check=False, capture_output=True, text=True)
    tail = (r.stderr or r.stdout).strip().splitlines()
    return r.returncode, " | ".join(tail[-3:])


def main():
    import report_generation
    import validation
    if not SOURCE_ROOT.is_dir():
        raise SystemExit(f"source directory not found: {SOURCE_ROOT} (the read-only source check needs it)")
    is_clean = "--clean" in sys.argv
    prev = {n: file_hash(OUT / n) for n in KEY_OUTPUTS}
    prev.update(json.loads(FIRST_PASS.read_text(encoding="utf-8")) if FIRST_PASS.exists() else {})
    prev_clean = bool(prev.pop("_clean", False))
    if is_clean:
        clean()
    t0 = time.time()
    src_before, up_before, fz_before = source_snapshot(), upstream_snapshot(), frozen_hashes()
    A = analyse(CFG)
    write(A["outputs"])
    # first pass: analysis-only gates (no run-dependent rows) -> a report whose bytes are comparable across runs
    write_csv(validation.gates(A, None, CFG), "early_warning_validation.csv", lg)
    report_generation.main()
    first = {n: file_hash(REPORTS / n) for n in REPORT_FILES}
    FIRST_PASS.write_text(json.dumps({**first, "_clean": is_clean}, indent=1, sort_keys=True), encoding="utf-8")
    report_text = (REPORTS / REPORT_FILES[0]).read_text(encoding="utf-8")
    rc, test_tail = run_tests()
    src_after, up_after, fz_after = source_snapshot(), upstream_snapshot(), frozen_hashes()
    run_info = {"src_unchanged": src_before == src_after, "n_src": len(src_before),
                "upstream_changed": [k for k in up_before if up_before[k] != up_after.get(k)] +
                sorted(set(up_after) - set(up_before)), "n_upstream": len(up_before),
                "frozen_unchanged": fz_before == fz_after, "frozen": fz_after,
                "tests_rc": rc, "tests_tail": test_tail}
    compared = {n: (prev[n], file_hash(OUT / n)) for n in KEY_OUTPUTS if prev.get(n)}
    compared.update({n: (prev[n], first[n]) for n in REPORT_FILES if prev.get(n)})
    run_info["determinism"] = {"compared": len(compared), "expected": len(KEY_OUTPUTS) + len(REPORT_FILES),
                               "differing": [n for n, (a, b) in compared.items() if a != b],
                               "both_clean": prev_clean and is_clean}
    write_manifest(run_info, is_clean)
    gates = validation.gates(A, run_info, CFG, report_text=report_text)
    write_csv(gates, "early_warning_validation.csv", lg)
    report_generation.main()
    fails = int((gates.result == "FAIL").sum())
    lg.info("[done] %.0fs; %d gate checks: %s", time.time() - t0, len(gates), gates.result.value_counts().to_dict())
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
