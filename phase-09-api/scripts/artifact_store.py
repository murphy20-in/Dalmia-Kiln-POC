"""Read-only adapters over the frozen Phase 6-8 artifacts (and the verified Phase 9 O2-excluded materialisation).

load_store() verifies every file against outputs/artifact_manifest.json (SHA-256) and then reads explicit column
allow-lists into immutable in-memory views. Nothing is recomputed: no scoring, no reference fit, no threshold, no
resampling. Any missing or changed file raises ArtifactUnavailable, and the API answers 503 instead of serving it.

Never read here: afr_context, phase4_context, historical_similarity, risk_score_diagnostics.parquet, the Phase 6
post-event / AFR / plant_event_* placeholder fields, W1-W5 flags or thresholds, and any coverage / lead-time /
alert-rate column.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from p9common import ARTIFACTS, O2X_FILE, VERSION, artifact, fmt_ts, read_json, sha256

SCORE_COLS = ["timestamp", "risk_score", "risk_band", "operational", "confidence_score", "confidence_band",
              "confidence_band_uncapped", "confidence_cap_reason", "risk_status", "reference_state", "operating_state",
              "load_band", "load_context", "family_count_abnormal", "family_count_usable", "persistence_minutes",
              "magnitude_component", "concurrence_component", "persistence_component", "data_quality_status",
              "primary_reason", "secondary_reasons", "contributing_families", "reference_version", "score_version"]
CONF_COLS = ["timestamp", "conf_data_quality", "conf_family_coverage", "conf_baseline", "conf_operating_state",
             "conf_temporal", "conf_robustness", "o2_ambient_suspect"]
COMP_COLS = ["timestamp", "operational", "family", "raw_measure", "reference_measure", "normalized_deviation",
             "family_score", "family_weight", "family_contribution", "usable", "quality_flag", "reason_code"]
PERIOD_COLS = ["episode_id", "start_time", "end_time", "onset_time", "detection_time", "onset_censored",
               "duration_minutes", "episode_type", "classification", "severity_class", "confidence", "load_context",
               "primary_context", "deviating_families", "dominant_family", "family_count", "reference_state", "month",
               "label", "event_ground_truth_status", "method_version", "in_final_set"]
HORIZON_COLS = ["score_variant", "horizon_minutes", "is_primary", "n_events", "n_evaluable", "n_controls",
                "median_rank_change", "effect_size", "bootstrap_ci_low", "bootstrap_ci_high", "permutation_p", "bh_q",
                "median_event", "median_control", "status"]
O2_METRIC_EXCLUDE = ("coverage", "control_window_rate", "alert_rate")
VARIANT_NAME = {"PRIMARY": "primary", "EXCLUDE_KILN_INLET_O2_ANALYSER": "o2_excluded"}
LABEL_TYPE = "KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD"


class ArtifactUnavailable(Exception):
    """A consumed artifact is missing or differs from the manifest. The message never contains a filesystem path."""


def _split(s) -> list[str]:
    return [x for x in str(s or "").split(";") if x]


def _f(x):
    return None if pd.isna(x) else float(x)


@dataclass(frozen=True)
class Series:
    """Rows sorted by timestamp string (fixed-width ISO, so string order == time order)."""
    ts: tuple
    rows: tuple

    def window(self, start: str | None, end: str | None) -> tuple:
        """Rows with start <= timestamp < end (bucket-end labels). Pure slicing: no resampling or filling."""
        lo = bisect.bisect_left(self.ts, start) if start else 0
        hi = bisect.bisect_left(self.ts, end) if end else len(self.ts)
        return self.rows[lo:max(lo, hi)]


@dataclass(frozen=True)
class Store:
    manifest: dict
    contract: dict
    primary: Series
    o2x: Series
    periods: tuple
    validation: dict
    findings: tuple
    methodology: dict
    provenance: dict            # key -> provenance object


def verify(root: Path, manifest_path: Path) -> dict:
    """Every served artifact must match its manifest hash. Build-only artifacts are checked by build_artifacts.py."""
    if not manifest_path.is_file():
        raise ArtifactUnavailable("artifact manifest not built (run run_phase9.py)")
    try:
        man = read_json(manifest_path)
        listed = {a["key"]: a for a in man["artifacts"]}
    except (ValueError, KeyError, TypeError) as e:
        raise ArtifactUnavailable("artifact manifest is unreadable (rebuild with run_phase9.py)") from e
    for a in ARTIFACTS:
        if a["operational_status"] == "BUILD_VERIFICATION_ONLY":
            continue
        m = listed.get(a["key"])
        p = root / a["path"]
        if m is None or m["path"] != a["path"] or not p.is_file():
            raise ArtifactUnavailable(f"artifact '{a['key']}' missing")
        if sha256(p) != m["sha256"]:
            raise ArtifactUnavailable(f"artifact '{a['key']}' differs from the manifest hash")
    return man


def _provenance(man: dict) -> dict:
    out = {}
    for a in man["artifacts"]:
        out[a["key"]] = {"source_phase": a["source_phase"], "artifact": Path(a["path"]).name,
                         "artifact_version": a["version"], "artifact_sha256": a["sha256"],
                         "analytical_status": a["analytical_status"], "operational_status": a["operational_status"],
                         "empirical": a["analytical_status"] in ("EMPIRICAL_POC", "KPI_DERIVED_EMPIRICAL",
                                                                 "SENSITIVITY_ANALYSIS", "HISTORICAL_VALIDATION"),
                         "plant_supplied": False, "ground_truth_status": "NOT_AVAILABLE", "served_by": VERSION}
    return out


def _primary(root: Path) -> Series:
    s = pd.read_parquet(root / artifact("risk_scores")["path"], columns=SCORE_COLS)
    s = s[s.operational].sort_values("timestamp")
    conf = pd.read_parquet(root / artifact("risk_score_confidence")["path"], columns=CONF_COLS).set_index("timestamp")
    comp = pd.read_parquet(root / artifact("risk_score_components")["path"], columns=COMP_COLS)
    comp = comp[comp.operational].sort_values(["timestamp", "family"])
    fam = {}
    for r in comp.itertuples(index=False):
        fam.setdefault(r.timestamp, {})[r.family] = {
            "raw_measure": _f(r.raw_measure), "reference_measure": _f(r.reference_measure),
            "normalized_deviation": _f(r.normalized_deviation), "family_score": _f(r.family_score),
            "family_weight": _f(r.family_weight), "family_contribution": _f(r.family_contribution),
            "usable": bool(r.usable), "quality_flag": r.quality_flag, "reason_code": r.reason_code or None}
    rs = pd.read_parquet(root / artifact("risk_score_reasons")["path"]).sort_values(
        ["timestamp", "driver_rank", "reason_code"])
    codes = {}
    for r in rs.itertuples(index=False):
        codes.setdefault(r.timestamp, []).append({"code": r.reason_code, "type": r.reason_type,
                                                  "contribution_points": _f(r.contribution_points),
                                                  "driver_rank": int(r.driver_rank)})
    rows = []
    for r in s.itertuples(index=False):
        t = r.timestamp
        c = conf.loc[t]
        rows.append({
            "timestamp": fmt_ts(t), "variant": "primary", "empirical_risk_score": _f(r.risk_score),
            "reference_relative_band": r.risk_band, "score_row_status": r.risk_status,
            "confidence": {"band": r.confidence_band, "score": _f(r.confidence_score),
                           "band_uncapped": r.confidence_band_uncapped, "cap_reason": r.confidence_cap_reason or None,
                           "parts": {k[5:]: _f(c[k]) for k in CONF_COLS[1:-1]}},
            "data_quality": {"status": r.data_quality_status, "o2_ambient_suspect": bool(c["o2_ambient_suspect"])},
            "context": {"reference_state": r.reference_state, "operating_state": r.operating_state,
                        "load_band": r.load_band, "load_context": r.load_context},
            "reasons": {"primary": r.primary_reason or None, "secondary": _split(r.secondary_reasons),
                        "codes": codes.get(t, [])},
            "components": {"magnitude": _f(r.magnitude_component), "concurrence": _f(r.concurrence_component),
                           "persistence": _f(r.persistence_component),
                           "family_count_abnormal": int(r.family_count_abnormal),
                           "family_count_usable": int(r.family_count_usable),
                           "persistence_minutes": int(r.persistence_minutes),
                           "contributing_families": _split(r.contributing_families),
                           "families": fam.get(t, {})}})
    return Series(tuple(x["timestamp"] for x in rows), tuple(rows))


def _o2x(root: Path) -> Series:
    d = pd.read_parquet(root / O2X_FILE).sort_values("timestamp")
    rows = tuple({"timestamp": fmt_ts(r.timestamp), "variant": "o2_excluded",
                  "empirical_risk_score": _f(r.o2_excluded_risk_score), "reference_relative_band": None}
                 for r in d.itertuples(index=False))
    return Series(tuple(x["timestamp"] for x in rows), rows)


def _periods(root: Path) -> tuple:
    e = pd.read_parquet(root / artifact("abnormal_episodes")["path"], columns=PERIOD_COLS)
    e = e[e.in_final_set].sort_values(["start_time", "episode_id"])
    return tuple({
        "period_id": r.episode_id, "label_type": LABEL_TYPE, "phase6_label": r.label,
        "phase6_classification": r.classification, "start_time": fmt_ts(r.start_time),
        "end_time": fmt_ts(r.end_time), "onset_time": fmt_ts(r.onset_time), "detection_time": fmt_ts(r.detection_time),
        "onset_censored": bool(r.onset_censored), "duration_minutes": int(r.duration_minutes),
        "kpi_period_type": r.episode_type, "kpi_severity_class": r.severity_class, "confidence": r.confidence,
        "load_association": r.load_context, "primary_context": r.primary_context,
        "deviating_families": _split(r.deviating_families), "dominant_family": r.dominant_family,
        "family_count": int(r.family_count), "reference_state": r.reference_state, "month": r.month,
        "event_ground_truth_status": r.event_ground_truth_status, "method_version": r.method_version,
        "is_plant_event": False} for r in e.itertuples(index=False))


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]


COVERAGE_TEXT = re.compile(r"coverage [0-9.]+ \([0-9]+/[0-9]+\) vs control-window rate [0-9.]+; ")
CONTEXT_ONLY = {"F4": "month signs with n <= 4 (Phase 8 report section 23: context only)",
                "F8": "leave-one-out sign stability of a median of 10; not significance (Phase 8 section 23: context only)"}


def _finding(f: str, c: str, e: str, v: str) -> dict:
    """One Phase 8 finding, class unchanged. F3 rows get per-warning ids and their coverage figures withheld
    (Phase 8 section 26: coverage percentages are not shown); the test result that decided the class is kept."""
    fid, title = f.split(" ", 1)
    redacted = False
    if fid == "F3":
        fid = f"F3.{title.split(':', 1)[0]}"
        e, n = COVERAGE_TEXT.subn("coverage figures withheld (Phase 8 section 26); ", e)
        redacted = n == 1
        if not redacted:
            raise ArtifactUnavailable("Phase 8 F3 evidence text has an unexpected format")
    return {"finding_id": fid, "title": title, "classification": c, "evidence": e, "evidence_redacted": redacted,
            "context_only": fid in CONTEXT_ONLY, "context_only_reason": CONTEXT_ONLY.get(fid),
            "source_phase": 8, "phase8_version": v, "is_historical_validation": True}


def _validation(root: Path, periods: tuple) -> tuple[dict, tuple]:
    sm = pd.read_csv(root / artifact("p8_summary")["path"])
    pe = sm[sm.section.eq("PRIMARY_ENDPOINT") & ~sm.metric.str.startswith("loeo_")]
    endpoint = {}
    for v, g in pe.groupby("variant", sort=True):
        vals = dict(zip(g.metric, g.value))
        num = {k: float(x) for k, x in vals.items() if k != "status"}
        endpoint[VARIANT_NAME[v]] = {
            "phase8_variant": v, "historical_validation_status": vals["status"],
            "effect_estimate_median_rank_excess": num["pe"], "ci95_low": num["ci_low"], "ci95_high": num["ci_high"],
            "randomisation_p_value": num["p_value"], "cliffs_delta": num["cliffs_delta"],
            "n_periods": int(num["n_events"]), "n_evaluable_periods": int(num["n_evaluable"]),
            "n_controls": int(num["n_controls"]), "median_event_rank": num["median_event"],
            "median_control_rank": num["median_control"], "null_median": num["null_median"],
            "preferred": False, "comparable_to_primary": v == "PRIMARY"}
    cens = sm[sm.section.eq("CENSORED_SPLIT")][["variant", "horizon_minutes", "slice", "n_evaluable", "n_controls",
                                                "pe", "cliffs_delta", "p_value"]].sort_values(
        ["variant", "horizon_minutes", "slice"])
    fnd = sm[sm.section.eq("FINDING")]
    findings = tuple(_finding(f, c, e, v) for f, c, e, v in
                     zip(fnd.finding, fnd.classification, fnd.evidence, fnd.phase8_version))
    hz = pd.read_csv(root / artifact("p8_horizon")["path"], usecols=HORIZON_COLS)
    hz = hz.drop_duplicates(["score_variant", "horizon_minutes"]).sort_values(["score_variant", "horizon_minutes"])
    hz = hz.rename(columns={"status": "historical_validation_status", "median_rank_change": "median_rank_excess"})
    ctl = pd.read_csv(root / artifact("p8_controls")["path"])
    nc = pd.read_csv(root / artifact("p8_negative_controls")["path"],
                     usecols=["control_id", "method", "score_variant", "horizon_minutes", "observed_effect",
                              "null_effect", "p_value", "n_null", "status"])
    o2 = pd.read_csv(root / artifact("p8_o2_sensitivity")["path"])
    ll = o2.loc[o2.metric.eq("primary_endpoint_p_same_event_set_as_primary"), "o2_excluded"]
    endpoint["o2_excluded"].update(
        comparable_to_primary=False, like_for_like_p_value=float(ll.iloc[0]),
        like_for_like_event_set="the primary's 10 evaluable periods",
        note="own 12-period event set (post-result amendment, a second test of the same hypothesis, not "
             "multiplicity-adjusted); on the primary's own periods p is the like_for_like_p_value; WEAK and "
             "analyser-dependent; not preferred")
    o2 = o2[~o2.metric.str.contains("|".join(O2_METRIC_EXCLUDE))]
    load = pd.read_csv(root / artifact("p8_load_sensitivity")["path"])
    gates = pd.read_csv(root / artifact("p8_gates")["path"])
    f6 = next(f for f in findings if f["finding_id"] == "F6")
    body = {
        "result_type": "HISTORICAL_VALIDATION_RESULT",
        "historical_validation_status": endpoint["primary"]["historical_validation_status"],
        "early_warning_supported": False,
        "question": "Was the frozen Phase 7 risk rank elevated over (T0 - 60 min, T0] before the Phase 6 KPI-derived "
                    "abnormal-period onsets, relative to month-matched ordinary running?",
        "primary_endpoint": {"definition": "median rank excess over (T0 - 60 min, T0] vs month-matched ordinary "
                                           "running; T0 = Phase 6 CUSUM onset; randomisation p from month-stratified "
                                           "random pseudo-onsets (NC2)",
                             "by_variant": endpoint},
        "censoring": {"n_periods": len(periods), "n_onset_censored": sum(p["onset_censored"] for p in periods),
                      "meaning": "a censored onset is the look-back cap, so its window lies inside the KPI shift; the "
                                 "CENSORED slices are not evidence of precedence (Phase 8 F18); the UNCENSORED "
                                 "slices show no pre-onset excess",
                      "split": _records(cens)},
        "control_methodology": {"primary_control": "ORDINARY_RUNNING_MONTH_MATCHED",
                                "control_sensitivities": _records(ctl)},
        "horizon_results": _records(hz),
        "warning_definitions": [{"warning_definition": f["finding_id"].split(".", 1)[1],
                                 "historical_validation_status": f["classification"], "is_live_flag": False}
                                for f in findings if f["finding_id"].startswith("F3.")],
        "negative_controls": _records(nc),
        "o2_excluded_sensitivity": _records(o2),
        "load_adjustment": {"status": f6["classification"], "rows": _records(load)},
        "phase8_integrity_checks": {
            "total": len(gates), "pass": int(gates.result.eq("PASS").sum()),
            "meaning": "Phase 8 pipeline integrity checks (inputs, leakage, reproducibility); they confirm the "
                       "analysis ran correctly and are not a favourable result"},
    }
    return body, findings


def _methodology(root: Path, contract: dict) -> dict:
    ref = read_json(root / artifact("risk_score_reference")["path"])
    bands = pd.read_csv(root / artifact("risk_score_bands")["path"],
                        usecols=["band", "lower_edge", "reference_quantile", "supported", "merged_into", "rationale",
                                 "reference_version"])
    inv = pd.read_csv(root / artifact("risk_score_feature_inventory")["path"])
    return {
        "phase7_score": {
            "name": "empirical POC risk score (0-100)", "score_version": ref["score_version"],
            "reference_version": ref["reference_version"], "reference_window": [ref["ref_start"], ref["ref_end"]],
            "n_reference_buckets": ref["n_reference_buckets"],
            "formula": "risk_score = 100 * (0.5 * H + 0.25 * C + 0.25 * P): magnitude H, concurrence C and "
                       "persistence P of per-family deviations from the frozen Apr-May reference",
            "reference_relative_bands": _records(bands),
            "band_semantics": "reference-relative quantile bands of the Apr-May reference; not plant limits, alarm "
                              "levels or action thresholds",
            "feature_inventory": _records(inv)},
        "phase6_periods": {"definition": "RUNNING buckets with Phase 3 KPI >= frozen training P90, merged across gaps "
                                         "<= 60 min; final set = out of sample, no ordinary-context rule, >= 1 family "
                                         "above its training P90", "label_type": LABEL_TYPE},
        "phase8_validation": {"definition": "frozen pre-declared protocol; primary endpoint = median rank excess over "
                                            "(T0 - 60 min, T0] vs month-matched ordinary running"},
        "o2_excluded_variant": {"definition": "Phase 7 EXCLUDE_KILN_INLET_O2_ANALYSER variant as evaluated by Phase 8 "
                                              "(COMBUSTION / STABILITY rebuilt without Kiln-I!X)",
                                "status": "SENSITIVITY_ANALYSIS", "preferred": False},
        "disclaimers": contract["disclaimers"]}


def load_store(root: Path, manifest_path: Path) -> Store:
    man = verify(root, manifest_path)
    try:
        return _load(root, man)
    except (OSError, ValueError, KeyError, TypeError) as e:     # corrupt / unexpected artifact content
        raise ArtifactUnavailable("an artifact could not be read (see server log)") from e


def _load(root: Path, man: dict) -> Store:
    contract = read_json(root / artifact("analytical_contract")["path"])
    periods = _periods(root)
    validation, findings = _validation(root, periods)
    return Store(manifest=man, contract=contract, primary=_primary(root), o2x=_o2x(root), periods=periods,
                 validation=validation, findings=findings, methodology=_methodology(root, contract),
                 provenance=_provenance(man))
