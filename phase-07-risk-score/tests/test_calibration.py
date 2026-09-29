"""Calibration: insufficient sample, stable distribution, support / merge rule, threshold generation, hysteresis."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import synthetic
from calibration import alert_episodes, auc
from risk_core import block_ids, boot_quantiles, fit_bands
from common import PRIMARY
from risk_core import band_of

TS = pd.date_range("2025-04-01 00:10", "2025-05-31 23:50", freq="10min")


class TestBands(unittest.TestCase):
    def test_insufficient_sample(self):
        b = fit_bands(np.random.default_rng(0).random(500) * 100, TS[:500], PRIMARY)
        self.assertEqual(b["status"], "CALIBRATION_INSUFFICIENT")
        self.assertEqual(list(band_of(np.array([10.0]), b)), ["UNBANDED"])

    def test_too_few_blocks(self):
        ts = pd.date_range("2025-04-01", periods=3000, freq="1min")      # ~2 days = 1 block
        self.assertEqual(fit_bands(np.random.default_rng(0).random(3000), ts, PRIMARY)["status"],
                         "CALIBRATION_INSUFFICIENT")

    def test_stable_distribution_gives_all_bands(self):
        R = np.random.default_rng(1).uniform(0, 100, len(TS))
        b = fit_bands(R, TS, PRIMARY)
        self.assertEqual(b["status"], "BANDED")
        np.testing.assert_allclose([e["value"] for e in b["edges"]], [75, 90, 95], atol=2.0)
        for e in b["edges"]:
            self.assertLessEqual(e["ci_low"], e["value"])
            self.assertGreaterEqual(e["ci_high"], e["value"])

    def test_merge_when_cis_overlap(self):
        rng = np.random.default_rng(2)
        R = np.where(rng.random(len(TS)) < 0.85, rng.uniform(0, 50, len(TS)), 60.0)   # P90 = P95: CIs coincide
        b = fit_bands(R, TS, PRIMARY)
        self.assertEqual(b["status"], "BANDED_WITH_MERGES")
        vh = next(e for e in b["candidates"] if e["band"] == "VERY_HIGH")
        self.assertFalse(vh["supported"])
        self.assertEqual(vh["merged_into"], "HIGH")
        self.assertEqual([e["band"] for e in b["edges"]], ["ELEVATED", "HIGH"])

    def test_threshold_generation_matches_band_of(self):
        _, _, refs = synthetic.fixture()
        b = refs["PRIMARY"]["bands"]
        e = {x["band"]: x["value"] for x in b["edges"]}
        self.assertEqual(band_of(np.array([e["HIGH"]]), b)[0], "HIGH")
        self.assertEqual(band_of(np.array([e["HIGH"] - 1e-9]), b)[0], "ELEVATED" if "ELEVATED" in e else "LOW")

    def test_bootstrap_is_seeded(self):
        R = np.random.default_rng(3).random(2000)
        blk = block_ids(TS[:2000], PRIMARY.ref_start, 3)
        np.testing.assert_array_equal(boot_quantiles(R, blk, (0.9,), 50, 7), boot_quantiles(R, blk, (0.9,), 50, 7))


class TestAlertBurden(unittest.TestCase):
    def test_hysteresis_episodes(self):
        ix = pd.date_range("2025-06-01 00:10", periods=10, freq="10min")
        f = pd.DataFrame({"score_all": np.arange(10.0), "load_band": "TENTATIVE_HIGH", "conf_operating_state": 1.0,
                          "conf_data_quality": 1.0, "load_context": "STEADY_LOAD"}, index=ix)
        rank = np.array([0, 2, 2, 1, 1, 0, 2, 1, 2, 2])
        oper = np.array([True] * 8 + [False, True])
        ep = alert_episodes(f, rank, oper)
        self.assertEqual(list(ep.duration_min), [40, 20, 10])     # never bridges the non-operational bucket

    def test_auc(self):
        self.assertEqual(auc(np.array([2.0, 3.0]), np.array([0.0, 1.0])), 1.0)
        self.assertEqual(auc(np.array([1.0]), np.array([1.0])), 0.5)
        self.assertTrue(np.isnan(auc(np.array([]), np.array([1.0]))))


class TestCoverage(unittest.TestCase):
    def test_period_coverage_handles_unscored_period(self):
        from calibration import period_coverage
        from risk_core import components_long, score_frame
        g, ctx, refs = synthetic.fixture()
        f, core = score_frame(g, refs, ctx)
        ep = ctx["episodes"].copy()
        ep.loc[0, ["start_time", "end_time", "onset_time"]] = [synthetic.STOP[0], synthetic.STOP[0] + pd.Timedelta(hours=6),
                                                              synthetic.STOP[0]]                     # a stopped period
        cov = period_coverage(f, components_long(f, core), ep)
        row = cov.set_index("episode_id").loc[ep.episode_id.iloc[0]]
        self.assertEqual(row.max_band, "NOT_SCORED")
        self.assertTrue(np.isnan(row.median_score))
        self.assertTrue(cov.coverage_label.str.startswith("EMPIRICAL_ABNORMAL_PERIOD_COVERAGE").all())


if __name__ == "__main__":
    unittest.main()
