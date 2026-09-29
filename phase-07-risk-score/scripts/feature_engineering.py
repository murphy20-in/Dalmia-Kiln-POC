"""Step 1 - causal feature functions (pure) and the Phase 7 input cache + feature provenance inventory.

Reads  phase-03 efficiency_deterioration_kpi.parquet / kpi_reference.json / kpi_validation.csv
       phase-06 abnormal_episodes.parquet (ALLOWED FIELDS ONLY - post-event columns are never loaded) / validation
       phase-05 afr_transition_episodes.parquet (event times; context only) / afr_validation.csv
       phase-04 leading_indicator_set.csv / indicator_feature_values.parquet (context only) / indicator_validation.csv
       phase-01 gap_events.csv / dq_issue_register.csv (DQ windows, used only after they have ended)
       data/processed via Phase 6 load_phase6_inputs.context_buckets() / masked_counts() (read-only)
Writes cache/grid.parquet, cache/episodes.parquet, cache/afr_events.parquet, cache/dq_windows.parquet,
       cache/input_hashes.json, outputs/risk_score_feature_inventory.csv

Every feature function uses bucket t and trailing buckets only (never t+1). A bucket labelled t covers (t-10 min, t].
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from common import (CACHE, COMPONENT_COL, FAMILIES, O2_TAG, P1_OUT, P3_OUT, P4_OUT, P5_OUT, P6_OUT, PRIMARY, PROCESSED,
                    P7Config, ac, ic, log, read_json, sha256, write_csv, write_json)

# Phase 6 episode fields Phase 7 may read. Post-event fields (post_event_outcome and everything in
# abnormal_episode_post_event.parquet) are FORBIDDEN and deliberately absent from this list.
EPISODE_FIELDS = ["episode_id", "start_time", "end_time", "onset_time", "classification", "in_final_set",
                  "reference_state", "severity_class", "severity_score", "confidence", "load_context", "afr_context",
                  "reference_robustness_score", "family_count", "deviating_families", "episode_type"]
POST_EVENT_FIELDS = ["post_event_outcome", "kpi_max_post_6h", "kpi_drop_peak_to_1h", "next_episode_within_6h",
                     "minutes_to_next_episode", "families_above_p90", "kpi_below_cut"]
KPI_TAG_DATASETS = ["Kiln-I", "Kiln-IA", "Kiln-II"]
CAUSAL_INVALID = ["n_mask_missing", "n_mask_sentinel", "n_mask_text", "n_mask_impossible", "n_mask_dup_conflict"]
RETRO_MASKS = ["n_mask_frozen", "n_mask_flatline"]      # Phase 2 retrospective detections: diagnostic only


# ============================================================================== pure causal feature functions
def running_mask(state: pd.Series | np.ndarray) -> np.ndarray:
    return np.asarray(state, dtype=object) == "RUNNING"


def masked_component(x: np.ndarray, running: np.ndarray) -> np.ndarray:
    """Phase 3 component where the bucket is RUNNING, else NaN (stopped / transition buckets never enter a window)."""
    return np.where(running, np.asarray(x, float), np.nan)


def smooth(x: np.ndarray, n: int, min_valid: int) -> np.ndarray:
    """Trailing median over (t - n buckets, t] with >= min_valid finite values (Phase 4 causal helper)."""
    return ic.trailing_median(np.asarray(x, float), n, min_valid)


def segment_start(running: np.ndarray) -> np.ndarray:
    """Position of the first bucket of the current RUNNING segment (the bucket after the last non-RUNNING one)."""
    idx = np.arange(len(running))
    return np.maximum.accumulate(np.where(~running, idx + 1, 0))


def trailing_count_in_segment(flag: np.ndarray, running: np.ndarray, n: int) -> np.ndarray:
    """Number of True buckets in (t - n, t] that lie after the last non-RUNNING bucket (0 when t is not RUNNING).
    A stop / start therefore resets the count - persistence never carries across a kiln stop."""
    f = np.asarray(flag, bool) & running
    cs = np.concatenate([[0], np.cumsum(f)])
    i = np.arange(len(f))
    start = np.maximum(i - n + 1, segment_start(running))
    return np.where(running, cs[i + 1] - cs[np.minimum(start, i + 1)], 0)


def hours_since_restart(running: np.ndarray, bucket_min: int = 10) -> np.ndarray:
    """Clock hours of the current RUNNING segment up to and including t (0 when not RUNNING)."""
    i = np.arange(len(running))
    return np.where(running, (i - segment_start(running) + 1) * bucket_min / 60.0, 0.0)


def run_minutes(flag: np.ndarray, bucket_min: int = 10) -> np.ndarray:
    """Length in minutes of the current run of consecutive True buckets ending at t."""
    return ic.run_lengths(np.asarray(flag, bool)) * bucket_min


def recent_event(index: pd.DatetimeIndex, times: pd.Series, hours: float) -> np.ndarray:
    """True if any event time lies in (t - hours, t]. Events after t are invisible at t."""
    ev = np.sort(pd.to_datetime(pd.Series(times)).dropna().to_numpy())
    if ev.size == 0:
        return np.zeros(len(index), bool)
    t = index.to_numpy()
    hi = np.searchsorted(ev, t, side="right")
    lo = np.searchsorted(ev, t - np.timedelta64(int(hours * 60), "m"), side="right")
    return hi > lo


def after_window(index: pd.DatetimeIndex, windows: pd.DataFrame, hours: float) -> np.ndarray:
    """True in (end, end + hours] of any DQ window: a gap / frozen window is only known once it has ended, so nothing
    before its end is ever affected (causal use of retrospectively detected windows)."""
    out = np.zeros(len(index), bool)
    t = index.to_numpy()
    for end in pd.to_datetime(windows.end).dropna():
        e = np.datetime64(end)
        out |= (t > e) & (t <= e + np.timedelta64(int(hours * 60), "m"))
    return out


def load_change(feed: np.ndarray, n: int) -> np.ndarray:
    """|trailing median of the last n buckets - the n before| (Phase 6 abs_change, never looks forward)."""
    return ac.abs_change(np.asarray(feed, float), n)


def components_from_tags(wide: pd.DataFrame, dim_of: dict, dims_ref: dict, exclude: tuple = ()) -> pd.DataFrame:
    """Phase 3 family components rebuilt from its tag scores: component = max(0, (mean of available tag scores in the
    family - frozen dimension median) / frozen dimension scale) - exactly kpi_core.dimension_raw + standardise_dims.
    `exclude` drops tags (robustness / dropout experiments); a family with no remaining tag is NaN."""
    out = {}
    for d in FAMILIES:
        cols = [t for t in wide.columns if dim_of.get(t) == d and t not in exclude]
        raw = wide[cols].mean(axis=1) if cols else pd.Series(np.nan, index=wide.index)
        out[d] = np.maximum(0.0, (raw - dims_ref[d]["median"]) / dims_ref[d]["scale"])
    return pd.DataFrame(out, index=wide.index)


def family_tag_coverage(wide: pd.DataFrame, dim_of: dict) -> pd.DataFrame:
    """Per family: available tag scores / tags in the family (tag-level dropout inside a family, DQ-2)."""
    return pd.DataFrame({d: wide[[t for t in wide.columns if dim_of.get(t) == d]].notna().mean(axis=1)
                         for d in FAMILIES}, index=wide.index)


def invalid_share(grid: pd.DataFrame) -> np.ndarray:
    """Causal-invalid share of scored-tag cells in the bucket (missing, sentinel 99999/9999, text 'Error 6',
    -273 / impossible, conflicting duplicates). These tokens depend only on the cell itself (Phase 3 causal tokens)."""
    cells = grid["n_cells"].to_numpy(float)
    bad = grid[CAUSAL_INVALID].fillna(0).to_numpy(float).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.clip(np.where(cells > 0, bad / cells, np.nan), 0, 1)


# ============================================================================== cache construction
def validate_upstream() -> dict:
    v3 = pd.read_csv(P3_OUT / "kpi_validation.csv")
    if (v3.result != "PASS").any():
        raise RuntimeError("Phase 3 kpi_validation.csv is not all PASS")
    for p in (P4_OUT / "indicator_validation.csv", P5_OUT / "afr_validation.csv", P6_OUT / "abnormal_episode_validation.csv"):
        if (pd.read_csv(p).result == "FAIL").any():
            raise RuntimeError(f"{p.name} has FAIL rows - Phase 7 requires validated upstream phases")
    files = {"phase-03": (P3_OUT, ["efficiency_deterioration_kpi.parquet", "kpi_reference.json", "kpi_reference_bands.csv",
                                   "kpi_validation.csv", "kpi_component_scores.parquet", "kpi_definition.json"]),
             "phase-04": (P4_OUT, ["leading_indicator_set.csv", "indicator_feature_values.parquet",
                                   "indicator_validation.csv"]),
             "phase-05": (P5_OUT, ["afr_transition_episodes.parquet", "afr_validation.csv"]),
             "phase-06": (P6_OUT, ["abnormal_episodes.parquet", "abnormal_episode_signals.parquet",
                                   "abnormal_episode_context.csv", "abnormal_episode_severity.csv",
                                   "abnormal_episode_confidence.csv", "abnormal_episode_pre_event.parquet",
                                   "abnormal_episode_post_event.parquet", "abnormal_episode_types.csv",
                                   "abnormal_episode_validation.csv"]),
             "phase-01": (P1_OUT, ["gap_events.csv", "dq_issue_register.csv"])}
    h = {f"{ph}/{n}": sha256(d / n) for ph, (d, names) in files.items() for n in names}
    for n in ["operating_state_timeline.parquet", "kiln_i.parquet", "kiln_ia.parquet", "kiln_ii.parquet",
              "kiln_iiia.parquet"]:
        h[f"data/processed/{n}"] = sha256(PROCESSED / n)
    return h


def dq_windows() -> pd.DataFrame:
    """Phase 1 long dataset gaps of the KPI-tag datasets and the DQ-016 suspected frozen window."""
    gaps = pd.read_csv(P1_OUT / "gap_events.csv", parse_dates=["gap_start_after", "gap_end_before"])
    gaps = gaps[gaps.long_gap & gaps.level.eq("DATASET") & gaps.dataset.isin(KPI_TAG_DATASETS)]
    rows = [{"kind": "LONG_GAP", "dataset": r.dataset, "start": r.gap_start_after, "end": r.gap_end_before,
             "source": "phase-01 gap_events.csv"} for r in gaps.itertuples()]
    reg = pd.read_csv(P1_OUT / "dq_issue_register.csv")
    for _, r in reg[reg.description.str.contains("frozen", case=False, na=False)].iterrows():
        t = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", str(r.location))
        if len(t) == 2:
            rows.append({"kind": "FROZEN_WINDOW", "dataset": str(r.source), "start": pd.Timestamp(t[0]),
                         "end": pd.Timestamp(t[1]), "source": f"phase-01 dq_issue_register {r.issue_id}"})
    if not any(r["kind"] == "FROZEN_WINDOW" for r in rows):
        raise SystemExit("DQ-016 frozen window not found in the Phase 1 issue register")
    return pd.DataFrame(rows).sort_values(["start", "kind"]).reset_index(drop=True)


def build_grid(kref: dict) -> tuple[pd.DataFrame, float]:
    import load_phase6_inputs as l6     # Phase 6, read-only (imports Phase 3 load_dataset; no I/O at import)
    k = pd.read_parquet(P3_OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp").sort_index()
    ic.check_grid(k.index)
    g = pd.DataFrame(index=k.index)
    g.index.name = "ts"
    g["state"] = k.operating_state.astype(str)
    for d in FAMILIES:
        g[f"comp_{d}"] = k[COMPONENT_COL[d]].astype(float)
    g["tag_coverage"] = k.tag_coverage.astype(float)
    g["n_causal_frozen"] = k.n_causal_frozen_minutes.astype(float)
    g["oor"] = k.out_of_training_load_range.astype(bool)
    g["share_high_conf"] = k.share_high_confidence_tags.astype(float)
    g["feed"] = k.load_context_feed_tph.astype(float)
    g["kpi_value"] = k.efficiency_deterioration_kpi.combine_first(k.kpi_in_sample_reference).astype(float)
    g["kpi_band"] = k.kpi_band.astype(str)
    g["kpi_reference_state"] = k.kpi_reference_state.astype(str)
    ctx = l6.context_buckets(g.index)
    g["afr"], g["coal_pc"] = ctx.afr.astype(float), ctx.coal_pc.astype(float)
    li = pd.read_csv(P4_OUT / "leading_indicator_set.csv")
    use = li[li.usable_downstream.astype(bool)]
    if list(use.indicator_id) != [ac.P4_INDICATOR]:
        raise SystemExit(f"Phase 4 usable_downstream set changed: {list(use.indicator_id)}")
    fv = pd.read_parquet(P4_OUT / "indicator_feature_values.parquet", columns=["timestamp", ac.P4_INDICATOR])
    g["p4"] = fv.set_index("timestamp")[ac.P4_INDICATOR].reindex(g.index).astype(float)
    tags = [t for t in kref["included_tags"] if not t.startswith("STD60:")]
    m = l6.masked_counts(g.index, tags)
    g["n_cells"] = m["cells"].astype(float)
    for c in CAUSAL_INVALID + RETRO_MASKS:
        g[c] = m[c].astype(float)
    # tag level (Phase 3 kpi_component_scores): per-family tag coverage, the kiln-inlet O2 bucket value, and the family
    # components rebuilt without the O2 analyser (robustness variant for DQ-1). The rebuild is checked to reproduce the
    # Phase 3 components exactly before anything is used.
    wide, dim_of, o2 = tag_scores(g.index)
    full = components_from_tags(wide, dim_of, kref["dims"])
    err = float(np.nanmax(np.abs(full.to_numpy() - g[[f"comp_{d}" for d in FAMILIES]].to_numpy())))
    if err > 1e-9 or (full.isna().to_numpy() != g[[f"comp_{d}" for d in FAMILIES]].isna().to_numpy()).any():
        raise RuntimeError(f"tag-score rebuild does not reproduce the Phase 3 components (max |diff| {err})")
    cov = family_tag_coverage(wide, dim_of)
    for d in FAMILIES:
        g[f"tagcov_{d}"] = cov[d].to_numpy()
    g["o2_bucket_pct"] = o2.to_numpy()
    excl = components_from_tags(wide, dim_of, kref["dims"], exclude=(O2_TAG, f"STD60:{O2_TAG}"))
    for d in ("COMBUSTION", "STABILITY"):
        g[f"comp_{d}_EXCL_O2"] = excl[d].to_numpy()
    return g, float(use.alarm_threshold.iloc[0]), err


def tag_scores(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict, pd.Series]:
    """(wide tag_score frame on the grid, tag -> family, kiln-inlet O2 bucket value) from Phase 3 kpi_component_scores."""
    cs = pd.read_parquet(P3_OUT / "kpi_component_scores.parquet", columns=["ts", "tag", "tag_score", "bucket_value",
                                                                            "dimension"])
    dim_of = dict(zip(cs.tag, cs.dimension))
    wide = cs.pivot_table(index="ts", columns="tag", values="tag_score", aggfunc="first").reindex(index)
    wide = wide.reindex(columns=sorted(wide.columns))
    o2 = cs[cs.tag.eq(O2_TAG)].set_index("ts").bucket_value.reindex(index).astype(float)
    return wide, dim_of, o2


def feature_inventory(kref: dict, cfg: P7Config = PRIMARY) -> pd.DataFrame:
    """Provenance of every feature. permitted_use SCORING rows are the only inputs of risk_score (G2 checks this)."""
    rw = f"{cfg.ref_start} .. {cfg.ref_end} RUNNING buckets (frozen)"
    k3 = "phase-03-efficiency-kpi/outputs/efficiency_deterioration_kpi.parquet"
    sp = ac.p3common.spec_by_tag()
    rows = []

    def add(name, ds, tag, ph, f, tr, win, lag, ref, use, q, leak):
        rows.append({"feature_name": name, "source_dataset": ds, "source_tag": tag, "source_phase": ph, "source_file": f,
                     "transformation": tr, "window": win, "lag": lag, "reference_window": ref, "permitted_use": use,
                     "quality_constraints": q, "leakage_status": leak})
    for d in FAMILIES:
        tags = [t for t in kref["included_tags"] if sp[t].dimension == d]
        ds = ";".join(sorted({t.replace("STD60:", "").split("!")[0] for t in tags}))
        add(f"S_{d}", ds, ";".join(tags), "Phase 3", k3,
            f"{COMPONENT_COL[d]} masked to RUNNING buckets, trailing median", f"{cfg.window_buckets * 10} min",
            "0 (bucket t and earlier)", "Phase 3 training Apr-May (component scale)", "SCORING",
            f">= {cfg.window_min_valid} of {cfg.window_buckets} buckets finite; Phase 3 causal masks, held columns excluded",
            "CAUSAL")
        add(f"a_{d}", ds, ";".join(tags), "Phase 7", "outputs/risk_score_reference.json",
            "a = 1 - 2^-(max(0, S - m_d) / (q_d - m_d))", "-", "0", rw, "SCORING", "usable only if S finite", "CAUSAL")
    add("H_magnitude", "all", "a_*", "Phase 7", "derived", "0.5 max_d a_d + 0.5 mean_d a_d (fixed denominator 5)", "-",
        "0", rw, "SCORING", "missing family contributes 0", "CAUSAL")
    add("C_concurrence", "all", "a_*", "Phase 7", "derived", "max(0, n_abnormal - 1) / 4", "-", "0", rw, "SCORING",
        "abnormal <=> S > reference P90", "CAUSAL")
    add("P_persistence", "all", "H_magnitude", "Phase 7", "derived",
        "count of buckets with H >= H_ref90 and >= 3 usable families since the last non-RUNNING bucket / 18",
        f"{cfg.persistence_buckets * 10} min", "0", rw, "SCORING", "clock-time denominator (monotone under NaN)",
        "CAUSAL")
    add("operating_state", "Kiln-I;Kiln-IA", "Kiln MD composite + feed / hood ramp", "Phase 3", k3,
        "causal POC state proxy", "minute", "0", "-", "STATUS", "POC PROXY - UNCONFIRMED", "CAUSAL")
    add("tag_coverage", "Kiln-I;Kiln-IA;Kiln-II", "33 KPI tags", "Phase 3", k3, "available / included tags", "bucket",
        "0", "-", "CONFIDENCE", "-", "CAUSAL")
    add("causal_invalid_share", "Kiln-I;Kiln-IA;Kiln-II", "scored KPI tags", "Phase 2 (via Phase 6 masked_counts)",
        "data/processed/kiln_i|kiln_ia|kiln_ii.parquet", "cells with MISSING/SENTINEL/TEXT/IMPOSSIBLE/DUP_CONFLICT tokens "
        "/ cells", "bucket", "0", "-", "CONFIDENCE", "per-cell tokens only", "CAUSAL")
    add("n_causal_frozen_minutes", "Kiln-I;Kiln-IA;Kiln-II", "dataset rows", "Phase 3", k3, "causal frozen-row mask",
        "bucket", "0", "-", "CONFIDENCE", "-", "CAUSAL")
    add("dq_window_after", "Kiln-I;Kiln-IA;Kiln-II", "-", "Phase 1", "phase-01 gap_events.csv; dq_issue_register.csv",
        f"t in (window end, end + {cfg.dq_after_window_hours:g} h]", "-", "0", "-", "CONFIDENCE",
        "only after the window has ended", "CAUSAL (window known once ended)")
    add("share_high_confidence_tags", "Kiln-I;Kiln-IA;Kiln-II", "33 KPI tags", "Phase 3 / Phase 2", k3,
        "share of available tags with Phase 2 HIGH baseline confidence", "bucket", "0", "Phase 2 full period (static)",
        "CONFIDENCE", "static per-tag metadata", "CAUSAL_STATIC_METADATA (disclosed)")
    add("hours_since_restart", "Kiln-I;Kiln-IA", "operating_state", "Phase 7", "derived", "RUNNING segment length",
        "-", "0", "-", "CONFIDENCE", "-", "CAUSAL")
    add("out_of_training_load_range", "Kiln-I", "Kiln-I!C", "Phase 3", k3, "feed outside training P01-P99", "bucket",
        "0", "Phase 3 training", "CONFIDENCE;CONTEXT", "-", "CAUSAL")
    add("feed_change_1h", "Kiln-I", "Kiln-I!C", "Phase 3", k3, "|trailing median 1 h - previous 1 h|", "120 min", "0",
        rw, "CONTEXT", "-", "CAUSAL")
    add("load_band", "Kiln-I", "Kiln-I!C", "Phase 7", k3, "reference feed P33 / P67", "bucket", "0", rw, "CONTEXT",
        "TENTATIVE (Phase 2 bands reproduce in 40 % of bootstraps)", "CAUSAL")
    add("afr_level", "Kiln-I", "Kiln-I!K", "Phase 6 context_buckets", "data/processed/kiln_i.parquet",
        "bucket median, Phase 2 causal tokens + frozen rows masked", "bucket", "0", "-", "CONTEXT",
        "AFR family INSUFFICIENT (no CV / moisture / RDF split)", "CAUSAL")
    add("coal_pc_level", "Kiln-I", "Kiln-I!I", "Phase 6 context_buckets", "data/processed/kiln_i.parquet",
        "bucket median", "bucket", "0", "-", "CONTEXT", "manipulated variable (never scored)", "CAUSAL")
    add("afr_transition_recent", "Kiln-I", "Kiln-I!K", "Phase 5", "phase-05 afr_transition_episodes.parquet",
        f"transition time in (t - {cfg.afr_context_hours:g} h, t]", f"{cfg.afr_context_hours:g} h", "0", "-",
        "CONTEXT (inclusion test only)", "RETROSPECTIVE_LABEL (episode classification uses the full series)",
        "RETROSPECTIVE_CONTEXT_ONLY")
    add("phase4_indicator", "Kiln-I", ac.P4_INDICATOR, "Phase 4", "phase-04 indicator_feature_values.parquet",
        f">= threshold in the trailing {cfg.p4_context_buckets * 10} min", f"{cfg.p4_context_buckets * 10} min", "0",
        "Phase 4 discovery P90", "CONTEXT (inclusion test only)", "LOW confidence; not distinguishable from chance (P6)",
        "CAUSAL")
    add("kpi_value", "all", "Phase 3 KPI", "Phase 3", k3, "efficiency_deterioration_kpi (in-sample kept separately)",
        "6 h (Phase 3)", "0", "Phase 3 training", "CONTEXT", "aggregates the scored families: never scored (double count)",
        "CAUSAL")
    add("historical_similarity", "all", "a_*", "Phase 7", "phase-06 abnormal_episodes.parquet (Apr-May periods)",
        "max weighted Jaccard vs frozen Apr-May CALIBRATION_ONLY signatures", "-", "0", rw, "DIAGNOSTIC",
        "signatures do not transfer to Jun-Aug", "CAUSAL (library frozen in the reference window)")
    add("phase6_final_periods", "-", "episode_id,start_time,end_time,onset_time", "Phase 6",
        "phase-06 abnormal_episodes.parquet", "in_final_set == True", "-", "-", "-", "EVALUATION_ONLY",
        "EMPIRICAL_ABNORMAL_REFERENCE, not ground truth; circular with the scored families", "NOT_A_FEATURE")
    add("phase6_severity_confidence", "-", "severity_class,severity_score,confidence", "Phase 6",
        "phase-06 abnormal_episodes.parquet", "-", "-", "-", "-", "EVALUATION_ONLY (context metadata)",
        "never a supervised target or label", "NOT_A_FEATURE")
    k3t = "phase-03-efficiency-kpi/outputs/kpi_component_scores.parquet"
    add("family_tag_coverage", "Kiln-I;Kiln-IA;Kiln-II", "33 KPI tags", "Phase 3", k3t,
        "available tag scores / tags per family", "bucket", "0", "-", "CONFIDENCE", "tag-level dropout (DQ-2)", "CAUSAL")
    add("o2_bucket_pct", "Kiln-I", O2_TAG, "Phase 3", k3t, f"bucket median of {O2_TAG} (kiln inlet O2 %)", "bucket", "0",
        "-", "CONFIDENCE", f">= {cfg.o2_ambient_pct:g} % reads like ambient air (POC heuristic; plant confirmation "
        "required)", "CAUSAL")
    add("components_excluding_O2_analyser", "Kiln-I", f"{O2_TAG}; STD60:{O2_TAG}", "Phase 3 (rebuilt)", k3t,
        "COMBUSTION / STABILITY rebuilt from the Phase 3 tag scores without the O2 analyser (exact rebuild checked)",
        "bucket", "0", "Phase 3 training", "ROBUSTNESS_VARIANT", "not in the primary score", "CAUSAL")
    for c in POST_EVENT_FIELDS:
        add(f"post_event:{c}", "-", c, "Phase 6", "phase-06 abnormal_episode_post_event.parquet", "-", "-", "-", "-",
            "FORBIDDEN", "retrospective post-episode context", "FORBIDDEN_POST_EVENT")
    for c in RETRO_MASKS:
        add(c, "Kiln-I;Kiln-IA;Kiln-II", "scored KPI tags", "Phase 2", "data/processed", "retrospective mask counts",
            "bucket", "-", "-", "DIAGNOSTIC", "detected with full-period hindsight", "RETROSPECTIVE_CONTEXT_ONLY")
    return pd.DataFrame(rows)


def check_inventory(inv: pd.DataFrame, scoring_features: tuple) -> list[str]:
    """Problems that must block scoring: a scoring feature without a SCORING / CAUSAL provenance row, or any FORBIDDEN,
    post-event, evaluation-only or retrospective feature marked SCORING. Empty list = clean."""
    sc = inv[inv.permitted_use.eq("SCORING")]
    probs = [f"no SCORING provenance for {f}" for f in scoring_features if f not in set(sc.feature_name)]
    probs += [f"non-causal scoring feature {r.feature_name} ({r.leakage_status})" for r in sc.itertuples()
              if r.leakage_status != "CAUSAL"]
    probs += [f"post-event / forbidden feature marked SCORING: {r.feature_name}" for r in sc.itertuples()
              if r.feature_name.startswith("post_event:") or "post_event" in str(r.source_file)]
    probs += [f"unexpected scoring feature {f}" for f in set(sc.feature_name) - set(scoring_features)]
    return probs


def main():
    lg = log("feature_engineering")
    hashes = validate_upstream()
    write_json(hashes, CACHE / "input_hashes.json")
    kref = read_json(P3_OUT / "kpi_reference.json")
    g, p4_thr, rebuild_err = build_grid(kref)
    g.to_parquet(CACHE / "grid.parquet")
    ep = pd.read_parquet(P6_OUT / "abnormal_episodes.parquet", columns=EPISODE_FIELDS)
    ep.to_parquet(CACHE / "episodes.parquet", index=False)
    afr = pd.read_parquet(P5_OUT / "afr_transition_episodes.parquet", columns=["episode_id", "afr_transition", "T"])
    afr = afr.drop_duplicates("episode_id").sort_values(["T", "episode_id"]).reset_index(drop=True)
    afr.to_parquet(CACHE / "afr_events.parquet", index=False)
    dq_windows().to_parquet(CACHE / "dq_windows.parquet", index=False)
    bands = pd.read_csv(P3_OUT / "kpi_reference_bands.csv")
    write_json({"p4_threshold": p4_thr, "p4_indicator": ac.P4_INDICATOR, "kpi_version": kref["kpi_version"],
                "component_rebuild_max_abs_diff": rebuild_err,
                "kpi_band_lo": float(bands[bands.quantity.str.startswith("band_lo")].kpi_value.iloc[0])},
               CACHE / "context_meta.json")
    write_csv(feature_inventory(kref), "risk_score_feature_inventory.csv", lg)
    lg.info("grid %d buckets (RUNNING %d); episodes %d (final %d); AFR events %d", len(g),
            int(g.state.eq("RUNNING").sum()), len(ep), int(ep.in_final_set.sum()), len(afr))


if __name__ == "__main__":
    main()
