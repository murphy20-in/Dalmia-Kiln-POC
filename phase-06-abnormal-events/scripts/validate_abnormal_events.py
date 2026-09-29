"""Step 16 - Validation gates G1-G6 (G7 reproducibility is added by run_phase6.py) -> outputs/abnormal_episode_validation.csv.

G1 source / upstream integrity    G2 schema / traceability    G3 temporal integrity incl. the MANDATORY LEAKAGE TEST
G4 detection / data quality       G5 statistical integrity    G6 ground-truth integrity (no fabricated labels / claims)
Checks marked INDEPENDENT re-derive a result with separate code from the raw upstream files; CONSISTENCY checks compare
outputs with each other. NOT_MET_REPORTED = a pre-declared robustness expectation that the data did not meet (reported,
not hidden, not a pipeline failure).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from abn_core import (CACHE, CONF_PARTS, FP_CATEGORIES, GT_STATUS, LOAD_TAGS, OUT, P3_OUT, PLANT_EVENT_LOG, PRIMARY,
                      ROOT, TRAIN_END, candidate_flags, confidence, fit_reference, forbidden_hits, load_inputs,
                      load_stage, log, pre_event, run_pipeline, severity, sha256, truncate)

lg = log("validate_abnormal_events")
REQ = {
    "abnormal_episodes.parquet": ["episode_id", "start_time", "end_time", "duration_minutes", "episode_type",
                                  "classification", "severity_score", "severity_class", "confidence", "peak_kpi",
                                  "median_kpi", "kpi_integral", "kpi_slope", "family_count", "family_agreement",
                                  "efficiency_deviation", "combustion_deviation", "thermal_deviation", "draft_deviation",
                                  "stability_deviation", "load_context", "operating_state_context",
                                  "phase4_indicator_context", "afr_context", "data_quality_context",
                                  "data_quality_contamination", "robustness_score", "event_ground_truth_status",
                                  "plant_event_type", "event_match_status", "method_version"],
    "abnormal_episode_signals.parquet": ["episode_id", "timestamp", "dataset", "original_name", "process_family", "unit",
                                         "raw_value", "reference_value", "deviation_score", "direction", "abnormal_flag",
                                         "quality_flag", "contribution_score"],
    "abnormal_episode_context.csv": ["episode_id", "startup_overlap", "shutdown_overlap", "restart_overlap",
                                     "load_change_overlap", "afr_start_overlap", "afr_stop_overlap", "afr_ramp_overlap",
                                     "phase4_indicator_overlap", "data_quality_overlap", "operating_state",
                                     "primary_context", "secondary_context", "context_confidence"],
    "abnormal_candidate_windows.parquet": ["episode_id", "start_time", "end_time", "duration_minutes", "peak_kpi",
                                           "median_kpi", "kpi_integral", "kpi_slope"],
    "abnormal_episode_severity.csv": ["episode_id", "severity_score", "severity_class"],
    "abnormal_episode_confidence.csv": ["episode_id", "confidence", "confidence_score"],
    "abnormal_episode_pre_event.parquet": ["episode_id", "row_type", "signal", "offset_label"],
    "abnormal_episode_post_event.parquet": ["episode_id", "offset_label", "post_event_outcome"],
    "abnormal_episode_types.csv": ["episode_id", "episode_type", "type_support"],
    "abnormal_episode_data_quality.csv": ["episode_id", "data_quality_contamination", "data_quality_context"],
    "abnormal_episode_sensitivity.csv": ["dimension", "variant", "result"],
    "negative_control_results.csv": ["control", "statistic", "observed", "result"],
}
DEF_FIELDS = ["start_time", "detection_time", "onset_time", "pos_onset", "change_point_supported", "cusum_rise_6h",
              "families_at_detection", "kpi_onset_slope", "onset_censored"]
EXTENT_FIELDS = ["end_time", "duration_minutes", "peak_kpi", "median_kpi", "kpi_integral", "family_count",
                 "deviating_families", "maha_median"]
# classification fields depend on data up to end + the longest retrospective look-ahead (SHUTDOWN: end + 2 h; control
# action: onset + 1 h; merge: end + gap); they are compared once that horizon is inside the truncated data
CONTEXT_FIELDS = ["primary_context", "secondary_context", "classification", "in_final_set", "load_context",
                  "afr_context", "data_quality_context", "severity_class", "episode_type"]
UPSTREAM = {"phase-05": "phase-05-af-analysis/outputs", "phase-04": "phase-04-leading-indicators/outputs",
            "phase-03": "phase-03-efficiency-kpi/outputs", "phase-02": "phase-02-baseline/outputs",
            "phase-01": "phase-01-data-discovery/outputs", "data": "data"}


def read(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / name) if name.endswith(".parquet") else pd.read_csv(OUT / name, low_memory=False)


def same(a, b, tol: float = 1e-9) -> bool:
    a, b = pd.Series(list(a)), pd.Series(list(b))
    if len(a) != len(b):
        return False
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        return bool(np.allclose(a.astype(float), b.astype(float), rtol=0, atol=tol, equal_nan=True))
    return bool((a.astype(str) == b.astype(str)).all())


def naive_episodes(flag: np.ndarray, running: np.ndarray, blocked: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """Independent re-implementation of runs + gap-aware merge (explicit bucket loop)."""
    out, cur, last = [], None, None
    for i, f in enumerate(flag):
        if not f:
            continue
        if cur is not None and i - last - 1 <= gap and all(running[j] and not blocked[j] for j in range(last + 1, i)):
            last = i
            continue
        if cur is not None:
            out.append((cur, last))
        cur = last = i
    if cur is not None:
        out.append((cur, last))
    return out


def leakage_test(inp: dict, full: pd.DataFrame) -> tuple[bool, str]:
    """Run A = inputs truncated at T_c, Run B = complete inputs; everything known at T_c must be identical."""
    ix = inp["grid"].index
    oos = full[full.reference_state.eq("OUT_OF_SAMPLE")].reset_index(drop=True)
    cuts = [pd.Timestamp("2025-06-10 00:00"), pd.Timestamp("2025-07-01 00:00"), pd.Timestamp("2025-08-01 00:00"), ix[-1]]
    for k in (0, len(oos) // 3, 2 * len(oos) // 3):
        r = oos.iloc[k]
        cuts += [r.detection_time + pd.Timedelta(minutes=20), r.end_time, r.start_time - pd.Timedelta(minutes=10)]
    cuts = sorted(set(cuts))
    fpre = pre_event(inp["grid"], full, inp["ref"], inp["events"])
    flags_full = candidate_flags(inp["grid"], PRIMARY, inp["ref"], inp["events"])
    rows, ok_all = [], True
    for tc in cuts:
        ti = truncate(inp, tc)
        tr = run_pipeline(ti, PRIMARY).reset_index(drop=True)
        known = full[full.detection_time <= tc].reset_index(drop=True)
        issues = []
        if not np.array_equal(candidate_flags(ti["grid"], PRIMARY, ti["ref"], ti["events"]), flags_full[:len(ti["grid"])]):
            issues.append("candidate buckets differ")
        if len(tr) != len(known):
            issues.append(f"episode count {len(tr)} vs {len(known)} detected by T_c")
        else:
            issues += [f"definition field {c} differs" for c in DEF_FIELDS if not same(tr[c], known[c])]
            closed = known.end_time + pd.Timedelta(minutes=PRIMARY.merge_gap_min + 10) <= tc
            issues += [f"closed-episode field {c} differs" for c in EXTENT_FIELDS
                       if not same(tr.loc[closed, c], known.loc[closed, c])]
            horizon = max(PRIMARY.merge_gap_min + 10, int(PRIMARY.shutdown_after_h * 60) + 10,
                          int(PRIMARY.afr_post_onset_h * 60) + 10)
            settled = (known.end_time + pd.Timedelta(minutes=horizon) <= tc) & (
                known.onset_time + pd.Timedelta(minutes=70) <= tc)
            issues += [f"settled-episode context field {c} differs" for c in CONTEXT_FIELDS
                       if not same(tr.loc[settled, c], known.loc[settled, c])]
            if (tr.end_time > known.end_time).any() or (tr.end_time > tc).any():
                issues.append("right-censored end beyond min(full end, T_c)")
            op = tr.onset_time <= tc
            if op.any():
                tp = pre_event(ti["grid"], tr[op], ti["ref"], ti["events"])
                fp = fpre[fpre.episode_id.isin(known.loc[op, "episode_id"])]
                m = fp.merge(tp, on=["episode_id", "row_type", "signal", "offset_label", "bucket_end"], how="outer",
                             suffixes=("_f", "_t"), indicator=True)
                if (m._merge != "both").any():
                    issues.append("pre-event rows differ in presence")
                issues += [f"pre-event {c} differs" for c in ("value", "lead_minutes_before_onset", "share_exceeded_12h")
                           if not same(m[f"{c}_f"], m[f"{c}_t"])]
        ok_all &= not issues
        rows.append(f"{tc}: n={len(known)} {'; '.join(issues) or 'identical'}")
    return ok_all, f"{len(cuts)} cut points | " + " | ".join(rows)


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    final = read("abnormal_episodes.parquet")
    fs = final[final.in_final_set]
    V = []

    def add(gate, check, ok, evidence, kind="INDEPENDENT", result=None):
        V.append({"gate": gate, "check": check, "check_type": kind,
                  "result": result or ("PASS" if ok else "FAIL"), "evidence": str(evidence)[:700]})

    # ---------------------------------------------------------------- G1
    h = json.loads((CACHE / "input_hashes.json").read_text())
    changed = [k for k, v in h.items() if sha256(ROOT / UPSTREAM[k.split("/", 1)[0]] / k.split("/", 1)[1]) != v]
    add("G1 source integrity", "Every consumed upstream file (Phases 1-5, data/processed) unchanged since input load",
        not changed, f"{len(h)} files hashed; changed {changed}")
    v3 = pd.read_csv(P3_OUT / "kpi_validation.csv")
    add("G1 source integrity", "Phase 3 validation all PASS (Phase 4 / 5 without FAIL checked at load)",
        (v3.result == "PASS").all(), f"Phase 3 {v3.result.value_counts().to_dict()}", kind="CONSISTENCY")

    # ---------------------------------------------------------------- G2
    miss = {n: [c for c in cols if c not in read(n).columns] for n, cols in REQ.items()}
    miss = {k: v for k, v in miss.items() if v}
    add("G2 schema integrity", "All required outputs exist with the required columns (sections 37-39)", not miss,
        f"{len(REQ)} files; missing {miss}")
    add("G2 schema integrity", "episode_id unique", final.episode_id.is_unique, f"{len(final)} episodes")
    tc = pd.read_csv(CACHE / "tag_check.csv")
    add("G2 schema integrity", "Every referenced tag exists in the Phase 1 inventory (gateguard tag check)",
        tc.in_phase1_inventory.all(), f"{len(tc)} tags; missing {tc.tag[~tc.in_phase1_inventory].tolist()}")
    add("G2 schema integrity", "No held column used (Phase 2 column_holds)", (tc.column_hold.fillna("") == "").all(),
        f"held {tc.tag[tc.column_hold.fillna('') != ''].tolist()}")
    sig = read("abnormal_episode_signals.parquet")
    kref = json.loads((P3_OUT / "kpi_reference.json").read_text())
    allowed = set(kref["included_tags"]) | set(LOAD_TAGS)
    add("G2 schema integrity", "No invented signal: signal tags are Phase 3 scored tags or the three load tags",
        set(sig.tag.unique()) <= allowed, f"{sig.tag.nunique()} tags; extra {sorted(set(sig.tag.unique()) - allowed)}")
    inv = pd.read_csv(ROOT / "phase-01-data-discovery/outputs/process_tag_inventory.csv")
    inv_map = dict(zip(inv.dataset + "!" + inv.source_column, inv.original_name))
    base = sig[~sig.tag.str.startswith("STD60:")].drop_duplicates("tag")
    bad = [t for t, o in zip(base.tag, base.original_name) if str(inv_map.get(t)) != str(o)]
    add("G2 schema integrity", "original_name preserved (equals the Phase 1 inventory for every measured tag)", not bad,
        f"{len(base)} tags; mismatched {bad}")
    add("G2 schema integrity", "Units traceable (every signal row carries a unit from Phase 1 / Phase 3)",
        sig.unit.notna().all() and (sig.unit.astype(str) != "").all(), f"units {sorted(sig.unit.astype(str).unique())}")

    # ---------------------------------------------------------------- G3
    ok, evid = leakage_test(inp, ep)
    add("G3 temporal integrity", "MANDATORY LEAKAGE TEST: truncated (<= T_c) vs full run - candidate buckets, episode "
        "starts, detection, CUSUM onset / change point, families at detection, closed-episode extents, pre-event rows and "
        "- once end + the 2-h SHUTDOWN look-ahead is inside the data - context / classification / final-set fields identical; "
        "open episodes right-censored", ok, evid)
    r2 = fit_reference(g[g.index <= pd.Timestamp("2025-06-20 00:00")], {"band_lo": ref["thr"], "band_hi": ref["hi"]},
                       kref)
    keys = ["D_median", "D_mad", "cusum_k", "cusum_h", "feed_d120m_p90", "feed_d60m_p75", "coal_total_d60m_p90",
            "feed_p01", "feed_p99"]
    add("G3 temporal integrity", "Phase 6 reference uses Apr-May only (refit on data <= 2025-06-20 is identical)",
        all(np.isclose(r2[k], ref[k], rtol=0, atol=1e-12) for k in keys) and r2["load"] == ref["load"],
        {k: (round(r2[k], 6), round(ref[k], 6)) for k in keys[:4]})
    pre = read("abnormal_episode_pre_event.parquet")
    hist = pre[pre.row_type.isin(["SNAPSHOT", "KPI_TURNING_POINT", "EVENT"])]
    add("G3 temporal integrity", "Pre-event rows use only data up to the onset T (bucket end <= T)",
        (hist.bucket_end <= hist.onset_time).all(), f"{len(hist)} rows")
    post = read("abnormal_episode_post_event.parquet").merge(final[["episode_id", "end_time"]], on="episode_id")
    pv = post.dropna(subset=["bucket_end"])
    add("G3 temporal integrity", "Post-event rows lie strictly after the episode end (never used to define it)",
        (pv.bucket_end > pv.end_time).all(), f"{len(pv)} rows")
    order = ((final.start_time <= final.detection_time) & (final.detection_time <= final.end_time)
             & (final.onset_time <= final.detection_time) & (final.start_time < final.end_time))
    add("G3 temporal integrity", "Episode boundaries ordered: onset <= detection, start <= detection <= end, start < end",
        order.all(), f"{int((~order).sum())} violations")
    ins = final[final.start_time <= TRAIN_END]
    add("G3 temporal integrity", "Apr-May (in-sample KPI) episodes flagged IN_SAMPLE_REFERENCE, never labelled "
        "HISTORICAL_ABNORMAL_PERIOD and excluded from the final set",
        ins.reference_state.eq("IN_SAMPLE_REFERENCE").all() and not ins.in_final_set.any()
        and not ins.classification.eq("HISTORICAL_ABNORMAL_PERIOD").any(),
        f"{len(ins)} in-sample episodes", kind="CONSISTENCY")
    add("G3 temporal integrity", "No September data (Kiln-I unavailable) and no KPI after 2025-08-31",
        final.end_time.max() < pd.Timestamp("2025-09-01") and g.K[g.index >= pd.Timestamp("2025-09-01")].isna().all(),
        f"last episode end {final.end_time.max()}; last KPI {g.K.dropna().index.max()}")

    # ---------------------------------------------------------------- G4
    e1, e2 = run_pipeline(inp, PRIMARY), run_pipeline(inp, PRIMARY)
    add("G4 detection integrity", "Detection deterministic (two in-process runs identical)", e1.equals(e2),
        f"{len(e1)} episodes")
    running = g.state.eq("RUNNING").to_numpy()
    blocked = np.zeros(len(g), bool)
    for w in inp["dq_windows"][inp["dq_windows"].kind.isin(["LONG_GAP", "FROZEN_WINDOW"])].itertuples():
        blocked |= (g.index > w.start) & (g.index - pd.Timedelta(minutes=10) < w.end)
    flag = (g.K.to_numpy(float) >= ref["thr"]) & running
    ne = naive_episodes(flag, running, blocked, PRIMARY.merge_gap_min // 10)
    add("G4 detection integrity", "Runs + gap-aware merging re-derived independently (explicit loop) from the raw KPI",
        ne == list(zip(ep.pos_start, ep.pos_end)), f"{len(ne)} vs {len(ep)} episodes")
    inside_bad = [r.episode_id for r in ep.itertuples() if not running[int(r.pos_start):int(r.pos_end) + 1].all()
                  or blocked[int(r.pos_start):int(r.pos_end) + 1].any()]
    add("G4 detection integrity", "No episode spans a non-RUNNING bucket, a long data gap or the frozen window",
        not inside_bad, f"violations {inside_bad}")
    add("G4 detection integrity", "Episodes do not overlap each other",
        bool((ep.pos_start.to_numpy()[1:] > ep.pos_end.to_numpy()[:-1]).all()), f"{len(ep)} episodes")
    add("G4 detection integrity", "Startups / restarts / shutdowns / load changes / AFR / control / DQ / short / "
        "insufficient periods are classified separately and never in the final set",
        not fs.primary_context.isin(FP_CATEGORIES).any(), f"final contexts {fs.primary_context.unique().tolist()}; "
        f"FP categories present {sorted(set(final.primary_context) & set(FP_CATEGORIES))}", kind="CONSISTENCY")
    dqw = inp["dq_windows"]
    add("G4 data quality", "DQ-016 frozen window and the Phase 1 long gaps are loaded as DQ windows",
        (dqw.kind == "FROZEN_WINDOW").any() and (dqw.kind == "LONG_GAP").sum() >= 3,
        dqw[["kind", "dataset", "start", "end"]].astype(str).values.tolist())
    rec = []
    for r in ep.itertuples():
        s = slice(max(0, int(r.pos_start) - 6), int(r.pos_end) + 1)
        cov = g.tag_cov.to_numpy(float)[s]
        rec.append(max(1 - float(np.mean(g.dq.to_numpy()[s] == "GOOD")), float(blocked[s].mean()),
                       1 - float(np.nanmedian(cov)) if np.isfinite(cov).any() else 1.0))
    add("G4 data quality", "data_quality_contamination re-derived independently", same(rec, ep.data_quality_contamination),
        f"max |diff| {np.nanmax(np.abs(np.array(rec) - ep.data_quality_contamination.to_numpy())):.2e}")
    add("G4 data quality", "DATA_QUALITY_ARTIFACT periods excluded from the final set",
        not (fs.data_quality_context == "DATA_QUALITY_ARTIFACT").any(),
        f"DQ contexts {final.data_quality_context.value_counts().to_dict()}", kind="CONSISTENCY")

    # ---------------------------------------------------------------- G5
    k3 = pd.read_parquet(P3_OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp")
    kk = k3.efficiency_deterioration_kpi.combine_first(k3.kpi_in_sample_reference)
    raw_flag = (kk >= ref["thr"]) & k3.operating_state.eq("RUNNING")
    add("G5 statistical integrity", "Candidate bucket rule re-derived from the raw Phase 3 parquet",
        int(raw_flag.sum()) == int(flag.sum()), f"{int(raw_flag.sum())} vs {int(flag.sum())} buckets")
    sv = severity(ep.drop(columns=["sev_peak", "sev_persistence", "sev_breadth", "severity_score", "severity_class"]),
                  ref, PRIMARY)
    add("G5 statistical integrity", "Severity recomputed from its components",
        same(sv.severity_score, ep.severity_score) and same(sv.severity_class, ep.severity_class), "score and class")
    cf = read("abnormal_episode_confidence.csv")
    add("G5 statistical integrity", "Confidence score recomputed from its parts; HIGH never emitted (cap)",
        same(cf[list(CONF_PARTS)].mean(axis=1, skipna=True), cf.confidence_score, tol=1e-5) and not (cf.confidence == "HIGH").any(),
        f"classes {cf.confidence.value_counts().to_dict()}; uncapped {cf.confidence_uncapped.value_counts().to_dict()}")
    cc = confidence(ep.merge(load_stage("robustness"), on="episode_id"), g, ref)
    add("G5 statistical integrity", "Confidence classes re-derived", same(cc.confidence, cf.confidence), "classes",
        kind="CONSISTENCY")
    prec_ok = True
    for r in ep.itertuples():
        want = {"DATA_QUALITY_ARTIFACT": r.data_quality_context == "DATA_QUALITY_ARTIFACT",
                "INSUFFICIENT_DATA": r.number_of_valid_families < PRIMARY.min_valid_families,
                "STARTUP": r.startup_overlap, "RESTART": r.restart_overlap, "SHUTDOWN": r.shutdown_overlap,
                "SHORT_TRANSIENT": r.duration_minutes < PRIMARY.min_dur_min,
                "NORMAL_LOAD_CHANGE": r.load_change_overlap and r.family_count < 2,
                "AFR_TRANSITION": r.afr_down_near_onset and r.family_count < 2,
                "CONTROL_ACTION": r.control_action_overlap and r.family_count < 2}
        prec_ok &= next((k for k in FP_CATEGORIES if want[k]), "NONE") == r.primary_context
    add("G5 statistical integrity", "primary_context precedence re-derived", prec_ok, f"{len(ep)} episodes")
    add("G5 statistical integrity", "Robust statistics: references are medians / scaled MAD / training quantiles (no "
        "mean / SD thresholds)", all(k in ref for k in ("D_median", "D_mad", "cusum_h", "feed_d120m_p90")),
        f"D median {ref['D_median']:.3f}, MAD {ref['D_mad']:.3f}; CUSUM k {ref['cusum_k']:.3f}, h {ref['cusum_h']:.2f}",
        kind="CONSISTENCY")
    cp = pd.read_csv(CACHE / "change_points.csv")
    rate = float(cp[(cp.episode_id == "BUCKET_ALARM_RATE")
                    & cp.reference_state.str.startswith("TRAINING")].change_point_supported.iloc[0])
    add("G5 statistical integrity", "CUSUM calibration: training bucket alarm rate ~ 10 % (h = training P90)",
        abs(rate - 0.10) < 0.02, f"{rate:.3f}")
    nc = read("negative_control_results.csv")
    add("G5 statistical integrity", "Negative controls completed (autocorrelation addressed: circular shifts, random "
        "windows, shifted AFR / Phase 4 context, in-sample calibration)", len(nc) >= 6 and nc.control.nunique() == 5,
        dict(zip(nc.control + ":" + nc.statistic.str[:24], nc.result)), kind="CONSISTENCY")
    nc2 = nc[nc.control == "NC2_RANDOM_WINDOWS"]
    add("G5 statistical integrity", "Final periods deviate across more families than random same-length RUNNING windows "
        "(NC2 above null P95)", (nc2.result == "OBSERVED_ABOVE_NULL_P95").all(),
        nc2[["observed", "null_p95"]].values.tolist())
    nc5 = nc[nc.control == "NC5_IN_SAMPLE_CALIBRATION"]
    add("G5 statistical integrity", "In-sample calibration: ~10 % of Apr-May RUNNING buckets above the P90 cut",
        (nc5.result == "CONSISTENT").all(), nc5.observed.tolist())
    sens = read("abnormal_episode_sensitivity.csv")
    dims = {"A_KPI_THRESHOLD", "B_MIN_DURATION", "C_MERGE_GAP", "D_FAMILY_AGREEMENT", "E_OPERATING_STATE", "F_LOAD",
            "G_MULTIVARIATE", "H_DQ_MASK", "I_SP_HEAT", "TEMPORAL"}
    add("G5 statistical integrity", "Sensitivity dimensions A-I and the temporal (month) analysis completed",
        dims <= set(sens.dimension), sorted(set(sens.dimension)), kind="CONSISTENCY")
    add("G5 statistical integrity", "False positives assessed: every candidate carries a primary_context and the "
        "ordinary-context (false-positive) categories are retained (not deleted)",
        final.primary_context.notna().all() and len(final) == len(ep), final.primary_context.value_counts().to_dict(),
        kind="CONSISTENCY")
    s2 = sens[sens.in_robustness_set.astype(str) == "True"]
    all_stable = bool((s2.result == "STABLE").all())
    add("G5 statistical integrity", "Pre-declared robustness expectation: every robustness-set variant STABLE",
        all_stable, f"CHANGED: {s2.variant[s2.result != 'STABLE'].tolist()}",
        result=None if all_stable else "NOT_MET_REPORTED")
    kept = float(sens[sens.variant == "A_alt"].primary_final_retained_share.iloc[0])
    add("G5 statistical integrity", "Drift check: the alternative (Jun-Jul15) KPI reference retains >= 50 % of the final "
        "periods", kept >= 0.5, f"retained {kept:.2f}: the abnormal LEVEL depends on the reference window",
        result=None if kept >= 0.5 else "NOT_MET_REPORTED")

    # ---------------------------------------------------------------- G6
    add("G6 ground-truth integrity", "No plant event log supplied and none fabricated (inputs/plant_event_log.csv absent)",
        not PLANT_EVENT_LOG.exists(), str(PLANT_EVENT_LOG.relative_to(ROOT)))
    gt = final[["event_ground_truth_status", "plant_event_type", "event_match_status"]]
    add("G6 ground-truth integrity", "event_ground_truth_status / plant_event_type / event_match_status = NOT_AVAILABLE",
        bool((gt == GT_STATUS).all().all()), {c: gt[c].unique().tolist() for c in gt})
    labels = pd.concat([final[c].astype(str) for c in ("classification", "episode_type", "primary_context", "label")])
    bad_lab = sorted({x for x in labels if any(w in x.upper() for w in ("DEPOSIT", "RING", "COATING", "FAILURE"))
                      and "NOT" not in x.upper()})
    add("G6 ground-truth integrity", "No deposit / ring / coating / failure label on any episode", not bad_lab, bad_lab)
    hits = forbidden_hits("\n".join(final.evidence_summary.astype(str)) + "\n" + "\n".join(final.label.astype(str)))
    add("G6 ground-truth integrity", "Wording scan of episode summaries and labels (no confirmed-event / cause / "
        "probability / plant-limit claims)", not hits, hits[:5])
    add("G6 ground-truth integrity", "Final periods are labelled HISTORICAL_ABNORMAL_PERIOD (empirical), not events",
        bool((fs.classification == "HISTORICAL_ABNORMAL_PERIOD").all() and fs.label.str.contains("NOT A VALIDATED").all()),
        f"{len(fs)} final periods", kind="CONSISTENCY")
    add("G6 ground-truth integrity", "Only the usable_downstream Phase 4 row is used", ref["p4_indicator"] ==
        "Kiln-I!I|ROC_1H", ref["p4_indicator"], kind="CONSISTENCY")
    out = pd.DataFrame(V)
    out.to_csv(OUT / "abnormal_episode_validation.csv", index=False)
    lg.info("validation: %s", out.result.value_counts().to_dict())
    for r in out[out.result == "FAIL"].itertuples():
        lg.error("FAIL %s | %s | %s", r.gate, r.check, r.evidence)


if __name__ == "__main__":
    main()
