"""Step 8 - Transparent episode severity (a descriptive magnitude; never a probability of any plant condition).

severity_score = 0.4 x peak + 0.3 x persistence + 0.3 x breadth   (each part in [0, 1]; abn_core.severity)
  peak        (peak KPI - training P90 cut) / (training P99 - P90 cut), clipped
  persistence KPI-hours above the cut / ((P99 - P90) x 6 h), clipped   (a 6-h stay at the P99 level = 1)
  breadth     deviating process families / 5
severity_class  HIGH = peak >= training P99 AND duration >= 6 h (the KPI persistence window); MODERATE = one of the two;
                LOW = neither. Data quality does not change severity - it lowers CONFIDENCE (separate step).
Writes outputs/abnormal_episode_severity.csv.
"""
from __future__ import annotations

from abn_core import load_inputs, load_stage, log, write_csv

lg = log("calculate_episode_severity")


def main():
    ref = load_inputs()["ref"]
    ep = load_stage("episodes")
    out = ep[["episode_id", "reference_state", "classification", "duration_minutes", "peak_kpi", "median_kpi",
              "kpi_integral", "family_count", "sev_peak", "sev_persistence", "sev_breadth", "severity_score",
              "severity_class", "maha_median"]].copy()
    out["kpi_cut_p90"], out["kpi_band_hi_p99"] = ref["thr"], ref["hi"]
    out["rule"] = ("score = 0.4 peak + 0.3 persistence + 0.3 breadth; HIGH = peak >= P99 and duration >= 6 h, MODERATE = "
                   "one, LOW = neither")
    out["label"] = "DESCRIPTIVE SEVERITY OF A POC KPI EXCURSION - NOT A FAILURE / DEPOSIT / RING PROBABILITY"
    write_csv(out, "abnormal_episode_severity.csv", lg)
    lg.info("severity classes (all candidates): %s", out.severity_class.value_counts().to_dict())


if __name__ == "__main__":
    main()
