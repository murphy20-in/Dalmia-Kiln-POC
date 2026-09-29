"""Causal feature functions: smoothing, persistence (isolated spike, sustained, gap, stop/start), events, DQ windows."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import synthetic
from common import FAMILIES, PRIMARY
from feature_engineering import (after_window, hours_since_restart, invalid_share, load_change, masked_component,
                                 recent_event, run_minutes, running_mask, smooth, trailing_count_in_segment)
from risk_core import family_S


class TestSmoothing(unittest.TestCase):
    def test_causal_future_values_do_not_change_the_past(self):
        x = np.random.default_rng(0).random(200)
        y = x.copy()
        y[120:] = 1e6
        np.testing.assert_array_equal(smooth(x, 6, 4)[:120], smooth(y, 6, 4)[:120])

    def test_isolated_spike_does_not_raise_the_smoothed_value(self):
        x = np.zeros(30)
        x[15] = 50.0
        self.assertEqual(np.nanmax(smooth(x, 6, 4)), 0.0)

    def test_sustained_abnormality_raises_it(self):
        x = np.zeros(30)
        x[10:20] = 5.0
        s = smooth(x, 6, 4)
        self.assertEqual(s[13], 5.0)                     # 4 of the last 6 buckets elevated -> median elevated

    def test_min_valid_rule(self):
        x = np.array([1.0, np.nan, np.nan, np.nan, 1.0, 1.0])
        self.assertTrue(np.isnan(smooth(x, 6, 4)[-1]))

    def test_gap_bucket_is_not_scored_from_stale_values(self):
        g, _, _ = synthetic.fixture()
        S, _ = family_S(g, PRIMARY)
        gap = (g.index > synthetic.GAP[0]) & (g.index <= synthetic.GAP[1])
        self.assertTrue(np.isnan(S[gap]).all())
        before = g.index <= synthetic.GAP[0]
        self.assertTrue(np.isfinite(S[before & g.state.eq("RUNNING").to_numpy()][-1]).all())

    def test_non_running_buckets_never_enter_a_window(self):
        run = np.array([True, False, True])
        np.testing.assert_array_equal(np.isnan(masked_component(np.array([1.0, 9.0, 1.0]), run)), [False, True, False])


class TestPersistence(unittest.TestCase):
    def test_count_resets_at_stop_start_boundary(self):
        run = np.array([True] * 5 + [False] + [True] * 5)
        c = trailing_count_in_segment(np.ones(11, bool), run, 18)
        self.assertEqual(list(c), [1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5])

    def test_window_length(self):
        run = np.ones(30, bool)
        self.assertEqual(trailing_count_in_segment(np.ones(30, bool), run, 18)[-1], 18)

    def test_isolated_spike_gives_small_persistence(self):
        f = np.zeros(40, bool)
        f[20] = True
        self.assertEqual(trailing_count_in_segment(f, np.ones(40, bool), 18).max(), 1)

    def test_monotone_under_missing_flags(self):
        rng = np.random.default_rng(2)
        f = rng.random(300) < 0.6
        g = f & (rng.random(300) < 0.7)                  # dropping flags (missing data) can only lower the count
        run = np.ones(300, bool)
        self.assertTrue((trailing_count_in_segment(g, run, 18) <= trailing_count_in_segment(f, run, 18)).all())

    def test_run_minutes_and_restart_hours(self):
        self.assertEqual(list(run_minutes(np.array([1, 1, 0, 1], bool))), [10, 20, 0, 10])
        self.assertEqual(list(hours_since_restart(np.array([True, True, False, True]))), [10 / 60, 20 / 60, 0.0, 10 / 60])


class TestContextFeatures(unittest.TestCase):
    def test_recent_event_sees_only_the_past(self):
        ix = pd.date_range("2025-06-01 00:10", periods=48, freq="10min")
        ev = pd.Series([pd.Timestamp("2025-06-01 03:00")])
        r = recent_event(ix, ev, 3.0)
        self.assertFalse(r[ix < pd.Timestamp("2025-06-01 03:00")].any())
        self.assertTrue(r[(ix >= pd.Timestamp("2025-06-01 03:00")) & (ix < pd.Timestamp("2025-06-01 06:00"))].all())

    def test_dq_window_only_after_it_ended(self):
        ix = pd.date_range("2025-06-01 00:10", periods=48, freq="10min")
        w = pd.DataFrame({"start": [pd.Timestamp("2025-06-01 01:00")], "end": [pd.Timestamp("2025-06-01 02:00")]})
        a = after_window(ix, w, 1.0)
        self.assertFalse(a[ix <= pd.Timestamp("2025-06-01 02:00")].any())
        self.assertTrue(a[(ix > pd.Timestamp("2025-06-01 02:00")) & (ix <= pd.Timestamp("2025-06-01 03:00"))].all())

    def test_load_change_is_causal(self):
        f = np.full(100, 400.0)
        f2 = f.copy()
        f2[60:] = 200.0
        np.testing.assert_array_equal(np.nan_to_num(load_change(f, 6)[:60]), np.nan_to_num(load_change(f2, 6)[:60]))

    def test_invalid_share(self):
        g = pd.DataFrame({"n_cells": [100.0, 0.0], "n_mask_missing": [5.0, 0], "n_mask_sentinel": [5.0, 0],
                          "n_mask_text": [0, 0], "n_mask_impossible": [0, 0], "n_mask_dup_conflict": [0, 0]})
        s = invalid_share(g)
        self.assertAlmostEqual(s[0], 0.10)
        self.assertTrue(np.isnan(s[1]))

    def test_running_mask(self):
        self.assertEqual(list(running_mask(pd.Series(["RUNNING", "STOPPED", "TRANSITION"]))), [True, False, False])

    def test_families_are_the_five_phase3_dimensions(self):
        self.assertEqual(FAMILIES, ("EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"))


if __name__ == "__main__":
    unittest.main()
