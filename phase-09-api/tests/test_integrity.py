"""Analytical integrity + temporal tests: served values equal the frozen artifacts, the O2-excluded variant is never
substituted, Phase 6 labels stay KPI-derived, Phase 8 stays NOT_SUPPORTED, windows / boundaries / missing months."""
import unittest

import numpy as np
import pandas as pd

import _client as c
from p9common import O2X_FILE, ROOT

APP = TMP = None
P7 = ROOT / "phase-07-risk-score/outputs"


def setUpModule():
    global APP, TMP
    APP, TMP = c.make_app()


def tearDownModule():
    TMP.cleanup()


def all_rows(query: str = "") -> list[dict]:
    out, off = [], 0
    while True:
        r = c.call(APP, "GET", "/api/v1/risk-scores", f"limit=5000&offset={off}" + (f"&{query}" if query else ""))
        out += r.json["data"]
        if not r.json["pagination"]["has_more"]:
            return out
        off = r.json["pagination"]["next_offset"]


class TestScoresMatchArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = pd.read_parquet(P7 / "risk_scores.parquet")
        cls.ref = s[s.operational].sort_values("timestamp")
        cls.primary = all_rows()
        cls.o2x = all_rows("variant=o2_excluded")

    def test_primary_values_timestamps_bands_equal_phase7(self):
        self.assertEqual(len(self.primary), len(self.ref))
        self.assertEqual([r["timestamp"] for r in self.primary],
                         self.ref.timestamp.dt.strftime("%Y-%m-%dT%H:%M:%S").tolist())
        np.testing.assert_array_equal(np.array([r["empirical_risk_score"] for r in self.primary], float),
                                      self.ref.risk_score.to_numpy(float))
        self.assertEqual([r["reference_relative_band"] for r in self.primary], self.ref.risk_band.tolist())
        self.assertEqual([r["confidence"]["band"] for r in self.primary], self.ref.confidence_band.tolist())
        self.assertEqual([r["score_row_status"] for r in self.primary], self.ref.risk_status.tolist())

    def test_only_operational_rows_are_served(self):
        self.assertEqual(len(self.primary), int(pd.read_parquet(P7 / "risk_scores.parquet").operational.sum()))
        self.assertEqual(c.call(APP, "GET", "/api/v1/risk-scores", "operational_only=false").status, 422)

    def test_o2x_values_equal_materialisation_and_are_never_substituted(self):
        o = pd.read_parquet(ROOT / O2X_FILE)
        np.testing.assert_array_equal(np.array([r["empirical_risk_score"] for r in self.o2x], float),
                                      o.o2_excluded_risk_score.to_numpy(float))
        self.assertTrue(all(r["variant"] == "o2_excluded" and r["reference_relative_band"] is None for r in self.o2x))
        self.assertTrue(all(r["variant"] == "primary" for r in self.primary))
        a = np.array([r["empirical_risk_score"] for r in self.primary], float)
        b = np.array([r["empirical_risk_score"] for r in self.o2x], float)
        self.assertGreater(np.mean(a != b), 0.5)       # the two series really differ; default stays primary

    def test_default_variant_is_primary_and_not_preferred(self):
        v = c.call(APP, "GET", "/api/v1/risk-scores", "limit=1").json["variant"]
        self.assertEqual((v["variant"], v["is_default"], v["preferred"]), ("primary", True, False))
        v = c.call(APP, "GET", "/api/v1/risk-scores", "variant=o2_excluded&limit=1").json["variant"]
        self.assertEqual((v["variant_status"], v["preferred"]), ("SENSITIVITY_ANALYSIS", False))

    def test_variant_comparison_labels_both_columns(self):
        r = c.call(APP, "GET", "/api/v1/risk-scores/variant-comparison", "limit=3").json
        self.assertEqual(set(r["data"][0]), {"timestamp", "primary_empirical_risk_score",
                                             "o2_excluded_empirical_risk_score"})
        self.assertEqual(r["data"][0]["primary_empirical_risk_score"], self.primary[0]["empirical_risk_score"])
        self.assertEqual(r["data"][0]["o2_excluded_empirical_risk_score"], self.o2x[0]["empirical_risk_score"])


class TestTemporal(unittest.TestCase):
    def test_window_is_start_inclusive_end_exclusive(self):
        d = c.call(APP, "GET", "/api/v1/risk-scores", "start=2025-07-01T00:00:00&end=2025-07-01T01:00:00").json["data"]
        self.assertEqual([x["timestamp"] for x in d], [f"2025-07-01T00:{m:02d}:00" for m in range(0, 60, 10)])

    def test_no_row_outside_the_scored_period_and_september_stays_missing(self):
        r = c.call(APP, "GET", "/api/v1/risk-scores", "start=2025-08-23T01:00:00").json
        self.assertEqual(r["data"], [])
        self.assertEqual(r["data_extent"]["last_timestamp"], "2025-08-23T00:40:00")
        self.assertEqual(c.call(APP, "GET", "/api/v1/risk-scores",
                                "start=2025-09-01T00:00:00&end=2025-10-01T00:00:00").json["pagination"]["total"], 0)
        self.assertIn("2025-09", [m["month"] for m in r["data_extent"]["not_scored"]])

    def test_gaps_are_not_filled(self):
        ts = pd.to_datetime([x["timestamp"] for x in all_rows("start=2025-06-01T00:00:00&end=2025-09-01T00:00:00")])
        steps = pd.Series(ts).diff().dropna()
        self.assertTrue((steps >= pd.Timedelta("10min")).all())
        self.assertGreater((steps > pd.Timedelta("10min")).sum(), 0)    # real gaps (stops) remain gaps

    def test_timestamps_are_naive_and_unconverted(self):
        for x in c.call(APP, "GET", "/api/v1/risk-scores", "limit=50").json["data"]:
            self.assertRegex(x["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertEqual(c.call(APP, "GET", "/api/v1/risk-scores", "start=2025-07-01T00:00:00Z").status, 400)
        self.assertEqual(c.call(APP, "GET", "/api/v1/risk-scores", "start=2025-07-01T00:00:00%2B05:30").status, 400)


class TestLabelsAndValidation(unittest.TestCase):
    def test_phase6_periods_are_kpi_derived_and_final_only(self):
        r = c.call(APP, "GET", "/api/v1/abnormal-periods").json
        e = pd.read_parquet(ROOT / "phase-06-abnormal-events/outputs/abnormal_episodes.parquet")
        self.assertEqual(sorted(p["period_id"] for p in r["data"]), sorted(e[e.in_final_set].episode_id))
        for p in r["data"]:
            self.assertEqual(p["label_type"], "KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD")
            self.assertFalse(p["is_plant_event"])
            self.assertEqual(p["event_ground_truth_status"], "NOT_AVAILABLE")
            self.assertNotIn("post_event_outcome", p)
            self.assertNotIn("afr_context", p)

    def test_phase8_primary_endpoint_stays_not_supported(self):
        v = c.call(APP, "GET", "/api/v1/validation/early-warning-historical").json["data"]
        self.assertEqual(v["historical_validation_status"], "NOT_SUPPORTED")
        self.assertFalse(v["early_warning_supported"])
        p, o = v["primary_endpoint"]["by_variant"]["primary"], v["primary_endpoint"]["by_variant"]["o2_excluded"]
        self.assertEqual((p["historical_validation_status"], round(p["effect_estimate_median_rank_excess"], 3),
                          round(p["ci95_low"], 3), round(p["ci95_high"], 3), round(p["randomisation_p_value"], 3),
                          round(p["cliffs_delta"], 2), p["n_evaluable_periods"], p["n_periods"], p["n_controls"]),
                         ("NOT_SUPPORTED", 0.051, -0.087, 0.119, 0.118, 0.21, 10, 12, 6641))
        self.assertEqual((o["historical_validation_status"], o["preferred"], o["comparable_to_primary"]),
                         ("WEAK", False, False))
        self.assertEqual(round(o["like_for_like_p_value"], 4), 0.0625)
        self.assertIn("not a favourable result", v["phase8_integrity_checks"]["meaning"])
        self.assertEqual(v["censoring"]["n_onset_censored"], 6)
        self.assertTrue(all(w["is_live_flag"] is False and w["historical_validation_status"] == "NOT_SUPPORTED"
                            for w in v["warning_definitions"]))

    def test_horizon_results_carry_no_coverage_or_lead_time(self):
        v = c.call(APP, "GET", "/api/v1/validation/early-warning-historical").json["data"]
        self.assertEqual(len(v["horizon_results"]), 16)
        for h in v["horizon_results"]:
            self.assertFalse({k for k in h if "coverage" in k or "lead" in k or "alert" in k}, h)
        self.assertFalse([x for x in v["o2_excluded_sensitivity"] if "coverage" in x["metric"]
                          or "alert_rate" in x["metric"]])

    def test_findings_keep_their_classifications(self):
        r = c.call(APP, "GET", "/api/v1/findings").json
        csv = pd.read_csv(ROOT / "phase-08-early-warning/outputs/early_warning_summary.csv")
        csv = csv[csv.section.eq("FINDING")]
        self.assertEqual([f["classification"] for f in r["data"]], csv.classification.tolist())
        self.assertIsNone(r["aggregate_score"])
        self.assertEqual((r["data"][0]["finding_id"], r["data"][0]["classification"]), ("F1", "NOT_SUPPORTED"))
        ids = [f["finding_id"] for f in r["data"]]
        self.assertEqual(len(ids), len(set(ids)))                      # F3 rows carry per-warning ids
        f3 = [f for f in r["data"] if f["finding_id"].startswith("F3.")]
        self.assertEqual(len(f3), 5)
        self.assertTrue(all(f["evidence_redacted"] and "binomial p" in f["evidence"] for f in f3))
        self.assertEqual({f["finding_id"] for f in r["data"] if f["context_only"]}, {"F4", "F8"})
        self.assertNotIn("classification_counts", r)


if __name__ == "__main__":
    unittest.main()
