"""Confidence (separate from risk): complete data, missing family, poor data quality, transition / post-restart,
insufficient reference, and the HIGH-risk + LOW-confidence state."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import synthetic
from common import CONF_CAP, variant
from reference_builder import fit_reference
from risk_core import score_frame

STEADY = (pd.Timestamp("2025-05-10"), pd.Timestamp("2025-05-20"))


def rescore(g):
    _, ctx, refs = synthetic.fixture()
    return score_frame(g, refs, {**ctx, "grid": g})[0]


class TestConfidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g, cls.ctx, cls.refs = synthetic.fixture()
        cls.f, _ = score_frame(cls.g, cls.refs, cls.ctx)

    def test_complete_data_is_capped_at_medium(self):
        s = self.f[(self.f.index > STEADY[0]) & (self.f.index <= STEADY[1])]
        self.assertTrue(s.confidence_band_uncapped.eq("HIGH").any())
        self.assertFalse(self.f.confidence_band.eq("HIGH").any())
        self.assertTrue(s.loc[s.confidence_band_uncapped.eq("HIGH"), "confidence_cap_reason"].eq(CONF_CAP).all())

    def test_confidence_in_unit_interval_and_nan_when_not_running(self):
        c = self.f.confidence_score
        self.assertTrue(c.dropna().between(0, 1).all())
        self.assertTrue(c[self.f.operating_state.ne("RUNNING")].isna().all())

    def test_missing_family_lowers_confidence(self):
        g2 = self.g.copy()
        g2["comp_EFFICIENCY"] = np.nan
        f2 = rescore(g2)
        sel = (self.f.index > STEADY[0]) & (self.f.index <= STEADY[1])
        self.assertTrue((f2.loc[sel, "conf_family_coverage"].dropna() == 0.8).all())
        # the coverage part always drops; the temporal / robustness parts can move either way bucket by bucket
        self.assertLess(f2.loc[sel, "confidence_score"].mean(), self.f.loc[sel, "confidence_score"].mean())
        self.assertTrue(f2.loc[sel, "secondary_reasons"].str.contains("REDUCED_FAMILY_COVERAGE").all())

    def test_poor_data_quality_forces_low(self):
        g2 = self.g.copy()
        g2["tag_coverage"] = 0.3
        f2 = rescore(g2)
        run = f2.operating_state.eq("RUNNING") & f2.family_count_usable.ge(3)
        self.assertTrue(f2.loc[run, "confidence_band"].eq("LOW").all())
        self.assertTrue(f2.loc[run, "risk_status"].eq("VALID_REDUCED_CONFIDENCE").all())

    def test_invalid_cells_reduce_data_quality_part(self):
        g2 = self.g.copy()
        g2["n_mask_sentinel"] = 150.0                      # half of the scored-tag cells are sentinels (masked upstream)
        f2 = rescore(g2)
        sel = (f2.index > STEADY[0]) & (f2.index <= STEADY[1])
        np.testing.assert_allclose(f2.loc[sel, "conf_data_quality"].dropna(), 0.5)
        np.testing.assert_array_equal(f2.loc[sel, "risk_score"].to_numpy(), self.f.loc[sel, "risk_score"].to_numpy())

    def test_transition_and_post_restart(self):
        tr = self.f.operating_state.eq("TRANSITION")
        self.assertTrue(self.f.loc[tr, "risk_status"].eq("TRANSITION_CONTEXT").all())
        end = synthetic.STOP[1] + pd.Timedelta(hours=2)
        after = (self.f.index > end) & (self.f.index <= end + pd.Timedelta(hours=5))
        self.assertTrue((self.f.loc[after, "conf_operating_state"] < 1).all())
        self.assertTrue(self.f.loc[after & self.f.risk_status.str.startswith("VALID"), "secondary_reasons"]
                        .str.contains("POST_RESTART_SETTLING").all())

    def test_insufficient_reference_raises(self):
        cfg = variant(name="TINY", ref_start="2025-04-01 00:00", ref_end="2025-04-01 12:00")
        with self.assertRaises(ValueError):
            fit_reference(self.g, cfg, self.ctx["episodes"], self.ctx)

    def test_high_risk_low_confidence_is_representable(self):
        g2 = self.g.copy()
        sel = (g2.index > synthetic.FINAL[0]) & (g2.index <= synthetic.FINAL[1])
        g2.loc[sel, "tag_coverage"] = 0.3
        f2 = rescore(g2)
        s = f2[sel]
        both = s.risk_band.isin(["HIGH", "VERY_HIGH"]) & s.confidence_band.eq("LOW")
        self.assertTrue(both.any())
        self.assertTrue(s.loc[both, "risk_status"].eq("VALID_REDUCED_CONFIDENCE").all())
        self.assertTrue(s.loc[both, "risk_score"].notna().all())


if __name__ == "__main__":
    unittest.main()
