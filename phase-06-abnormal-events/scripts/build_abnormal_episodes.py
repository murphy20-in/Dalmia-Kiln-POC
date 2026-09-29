"""Step 15 - Assemble the historical abnormal-period catalogue (outputs/abnormal_episodes.parquet).

One row per CANDIDATE episode - false-positive categories are kept, never deleted. in_final_set = True marks the
out-of-sample HISTORICAL_ABNORMAL_PERIODs (what Phase 7 may consume). Ground truth: the optional plant event log
(abn_core.PLANT_EVENT_LOG, columns event_id, event_type, start_time, end_time, source, description) is matched when it
exists; it does not exist for this run, so event_ground_truth_status = event_match_status = NOT_AVAILABLE. No plant event
label is created or inferred.
"""
from __future__ import annotations

import pandas as pd

from abn_core import (CACHE, METHOD_VERSION, PERIOD_NOTE, PRIMARY, evidence_summary, load_inputs, load_plant_events,
                      load_stage, log, match_plant_events, write_parquet)

lg = log("build_abnormal_episodes")
SCHEMA = ["episode_id", "start_time", "end_time", "duration_minutes", "episode_type", "classification", "severity_score",
          "severity_class", "confidence", "peak_kpi", "median_kpi", "kpi_integral", "kpi_slope", "family_count",
          "family_agreement", "efficiency_deviation", "combustion_deviation", "thermal_deviation", "draft_deviation",
          "stability_deviation", "load_context", "operating_state_context", "phase4_indicator_context", "afr_context",
          "data_quality_context", "data_quality_contamination", "robustness_score", "event_ground_truth_status",
          "plant_event_type", "event_match_status", "method_version"]
EXTRA = ["in_final_set", "reference_state", "month", "detection_time", "onset_time", "onset_censored", "end_reason",
         "right_censored", "primary_context", "secondary_context", "deviating_families", "deviation_breadth",
         "number_of_valid_families", "families_at_detection", "dominant_family", "maha_median", "maha_share_above",
         "multivariate_supported", "change_point_supported", "cusum_rise_6h", "level_shift_d", "kpi_onset_slope",
         "feed_change_vs_pre2h", "afr_near_onset", "afr_episode_ids", "robust", "reference_robustness_score",
         "confidence_score",
         "confidence_cap_reason", "post_event_outcome", "top_tags", "evidence_summary", "plant_event_start",
         "plant_event_end", "plant_event_source", "label", "config_key"]


def main():
    ref = load_inputs()["ref"]
    ep = load_stage("episodes")
    conf = load_stage("confidence")[["episode_id", "confidence", "confidence_score", "confidence_cap_reason",
                                     "robustness_score", "reference_robustness_score", "robust"]]
    ep = (ep.merge(conf, on="episode_id", how="left").merge(load_stage("post_outcome"), on="episode_id", how="left")
          .merge(pd.read_parquet(CACHE / "stage_top_tags.parquet"), on="episode_id", how="left"))
    ep = ep.merge(match_plant_events(ep, load_plant_events()), on="episode_id", how="left")
    ep["draft_deviation"] = ep.draft_pressure_deviation
    ep["operating_state_context"] = ep.primary_context.where(
        ep.primary_context.isin(["STARTUP", "RESTART", "SHUTDOWN"]), "RUNNING (POC PROXY - UNCONFIRMED)")
    ep["evidence_summary"] = [evidence_summary(r, ref) for r in ep.itertuples()]
    ep["method_version"], ep["config_key"] = METHOD_VERSION, PRIMARY.key()
    ep["label"] = PERIOD_NOTE
    out = ep[SCHEMA + EXTRA]
    write_parquet(out, "abnormal_episodes.parquet", lg)
    lg.info("%d candidate episodes; %d final historical abnormal periods; classes %s", len(out),
            int(out.in_final_set.sum()), out.classification.value_counts().to_dict())


if __name__ == "__main__":
    main()
