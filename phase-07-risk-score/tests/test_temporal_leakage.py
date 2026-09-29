"""Mandatory temporal-leakage tests 1-7 (synthetic data; the same checks run on the real data in validation G3).

1 no future timestamp contributes          2 no post-event field contributes      3 no future reference value
4 changing future data leaves the past     5 post-event rows leave pre-event      6 scoring period vs frozen reference
7 data after T leaves the score at T (+ timestamp boundaries)
"""
from __future__ import annotations

import json
import unittest

import pandas as pd

import synthetic
from common import PRIMARY
from feature_engineering import POST_EVENT_FIELDS, check_inventory, feature_inventory
from reference_builder import fit_reference, reference_mask
from risk_core import SCORING_FEATURES, SCORING_GRID_COLUMNS, reference_state, score_frame
from validation import frame_equal, perturb_context, truncate

CUTS = ["2025-04-15 12:00", "2025-05-31 23:50", "2025-06-01 00:00", "2025-06-03 12:00", "2025-06-06 00:00"]


def jdump(d: dict) -> str:
    return json.dumps(d, sort_keys=True, default=str)


def kref() -> dict:
    sp = synthetic.SCRIPTS.parent.parent / "phase-03-efficiency-kpi" / "outputs" / "kpi_reference.json"
    return json.loads(sp.read_text())


class TestLeakage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g, cls.ctx, cls.refs = synthetic.fixture()
        cls.full, _ = score_frame(cls.g, cls.refs, cls.ctx)

    def test_1_7_truncation_invariance(self):
        for c in CUTS:
            T = pd.Timestamp(c)
            t = truncate(self.ctx, T)
            tr, _ = score_frame(t["grid"], self.refs, t)
            self.assertEqual(frame_equal(tr, self.full[self.full.index <= T]), [], msg=c)

    def test_4_future_perturbation(self):
        """Every grid column, the AFR events and the DQ windows after T are randomised."""
        for i, c in enumerate(CUTS):
            T = pd.Timestamp(c)
            c2 = perturb_context(self.ctx, T, i)
            pf, _ = score_frame(c2["grid"], self.refs, c2)
            self.assertEqual(frame_equal(pf[pf.index <= T], self.full[self.full.index <= T]), [], msg=c)

    def test_5_post_event_rows_do_not_change_pre_event_scores(self):
        end = synthetic.FINAL[1]
        c2 = perturb_context(self.ctx, end, 5, until=end + pd.Timedelta(hours=6))
        pf, _ = score_frame(c2["grid"], self.refs, c2)
        self.assertEqual(frame_equal(pf[pf.index <= end], self.full[self.full.index <= end]), [])

    def test_harness_detects_an_injected_leak(self):
        """Mutation test: a scorer whose feature reads one bucket AHEAD (comp.shift(-1), applied to whatever data is
        available) MUST be caught by the truncation test - proves the harness can fail."""
        def leaky_score(ctx):
            g = ctx["grid"].copy()
            for d in ("COMBUSTION", "THERMAL"):
                g[f"comp_{d}"] = g[f"comp_{d}"].shift(-1)
            return score_frame(g, self.refs, {**ctx, "grid": g})[0]
        full = leaky_score(self.ctx)
        T = pd.Timestamp("2025-06-03 12:00")
        tr = leaky_score(truncate(self.ctx, T))
        self.assertNotEqual(frame_equal(tr, full[full.index <= T]), [])

    def test_truncate_hides_future_window_end(self):
        T = synthetic.GAP[0] + pd.Timedelta(hours=1)          # inside the synthetic gap window
        w = truncate(self.ctx, T)["dq_windows"]
        self.assertTrue(w["end"].isna().all())

    def test_2_post_event_fields_never_enter(self):
        self.assertFalse(set(POST_EVENT_FIELDS) & set(SCORING_GRID_COLUMNS))
        self.assertFalse(set(POST_EVENT_FIELDS) & set(self.ctx["episodes"].columns))
        ep = self.ctx["episodes"].assign(post_event_outcome="RANDOM", kpi_max_post_6h=123.0)
        a = fit_reference(self.g, PRIMARY, ep, self.ctx)
        self.assertEqual(jdump(a), jdump(self.refs["PRIMARY"]))
        pf, _ = score_frame(self.g, {**self.refs, "PRIMARY": a}, {**self.ctx, "episodes": ep})
        self.assertEqual(frame_equal(pf, self.full), [])

    def test_2_inventory_blocks_post_event_scoring(self):
        inv = feature_inventory(kref())
        self.assertEqual(check_inventory(inv, SCORING_FEATURES), [])
        bad = inv.copy()
        bad.loc[bad.feature_name.str.startswith("post_event:"), "permitted_use"] = "SCORING"
        self.assertTrue(any("post-event" in p for p in check_inventory(bad, SCORING_FEATURES)))
        bad2 = inv.copy()
        bad2.loc[bad2.feature_name.eq("afr_transition_recent"), "permitted_use"] = "SCORING"
        self.assertTrue(check_inventory(bad2, SCORING_FEATURES))

    def test_3_6_reference_is_frozen(self):
        T = pd.Timestamp(PRIMARY.ref_end)
        ra = fit_reference(perturb_context(self.ctx, T, 11)["grid"], PRIMARY, self.ctx["episodes"], self.ctx)
        rb = fit_reference(self.g[self.g.index <= T], PRIMARY, self.ctx["episodes"], self.ctx)
        self.assertEqual(jdump(ra), jdump(self.refs["PRIMARY"]))
        self.assertEqual(jdump(rb), jdump(self.refs["PRIMARY"]))

    def test_7_timestamp_boundaries(self):
        m = reference_mask(self.g, PRIMARY)
        self.assertEqual(self.g.index[m].max(), pd.Timestamp("2025-05-31 23:50"))
        self.assertFalse(m[self.g.index == pd.Timestamp("2025-06-01 00:00")].any())
        rs = pd.Series(reference_state(self.g.index, PRIMARY), index=self.g.index)
        self.assertEqual(rs[pd.Timestamp("2025-05-31 23:50")], "IN_SAMPLE_REFERENCE")
        self.assertEqual(rs[pd.Timestamp("2025-06-01 00:00")], "OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE")
        self.assertEqual(rs[pd.Timestamp("2025-06-01 03:00")], "OUT_OF_SAMPLE")

    def test_future_afr_event_invisible(self):
        T = pd.Timestamp("2025-06-03 08:50")                # the synthetic AFR stop is at 09:00
        self.assertEqual(self.full.loc[T, "afr_context"], "NO_AFR_TRANSITION")
        self.assertIn("AFR_STOP", self.full.loc[pd.Timestamp("2025-06-03 09:00"), "afr_context"])


if __name__ == "__main__":
    unittest.main()
