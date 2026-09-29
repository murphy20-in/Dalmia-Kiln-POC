"""Step 14 - Episode confidence, SEPARATE from severity (a severe-looking period with poor data gets LOW confidence).

confidence_score = mean of the available parts, each in [0, 1] (abn_core.confidence):
  conf_dq            1 - data_quality_contamination
  conf_family        deviating / valid process families
  conf_multivariate  share of episode buckets with the Phase 3 Mahalanobis KPI >= 50 (out of sample only)
  conf_change_point  CUSUM change point supported before detection (0 / 1)
  conf_kpi_quality   share of buckets with Phase 3 kpi_confidence = HIGH (includes the band-boundary margin)
  conf_robustness    sensitivity robustness_score (final periods only)
Reported, not averaged: sp_heat_fg_agreement (the K cut is only nominal for the F / G KPIs) and band_margin (already
inside Phase 3 kpi_confidence). Confidence = internal consistency of the evidence, NOT the likelihood of a real plant
event; MEDIUM is the ceiling by design.
Class HIGH = score >= 0.75 AND robustness >= 0.7 AND >= 2 families; LOW = score < 0.5; else MEDIUM. HIGH is then CAPPED
to MEDIUM (no event ground truth; unconfirmed state proxy; the families are the KPI's own inputs).
Writes outputs/abnormal_episode_confidence.csv and cache/stage_confidence.parquet.
"""
from __future__ import annotations

from abn_core import CACHE, CONF_DESCRIPTIVE, CONF_PARTS, confidence, load_inputs, load_stage, log, write_csv

lg = log("calculate_episode_confidence")


def main():
    inp = load_inputs()
    ep = load_stage("episodes").merge(load_stage("robustness"), on="episode_id", how="left")
    ep = confidence(ep, inp["grid"], inp["ref"])
    cols = ["episode_id", "reference_state", "classification", "severity_class", *CONF_PARTS, *CONF_DESCRIPTIVE, "confidence_score",
            "confidence_uncapped", "confidence", "confidence_cap_reason", "robustness_score", "reference_robustness_score",
            "robust"]
    out = ep[cols].copy()
    out["rule"] = ("mean of available parts; HIGH needs >= 0.75, robustness >= 0.7, >= 2 families (then capped to "
                   "MEDIUM); LOW < 0.5")
    write_csv(out, "abnormal_episode_confidence.csv", lg)
    out.to_parquet(CACHE / "stage_confidence.parquet", index=False)
    lg.info("confidence (final set): %s", out[ep.in_final_set].confidence.value_counts().to_dict())


if __name__ == "__main__":
    main()
