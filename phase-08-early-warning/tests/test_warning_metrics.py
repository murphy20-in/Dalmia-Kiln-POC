import unittest

import numpy as np

import warning_metrics as wm
from p8common import CFG


def flags_for(rank: np.ndarray, slope=None) -> dict:
    n = rank.size
    sig = {"score": np.ones(n), "rank": rank, "slope": np.zeros(n) if slope is None else slope, "accel": np.zeros(n)}
    return wm.warning_flags(sig, np.zeros(n), {"slope": 10.0, "accel": 10.0}, CFG)


class TestWarningMetrics(unittest.TestCase):
    def test_no_warning(self):
        f = flags_for(np.full(50, 0.5))
        self.assertFalse(any(v.any() for v in f.values()))
        self.assertEqual(wm.episodes(f["W1_RANK"], np.ones(50, bool)), [])

    def test_one_warning(self):
        r = np.full(50, 0.5)
        r[20] = 0.97
        f = flags_for(r)
        self.assertEqual(int(f["W1_RANK"].sum()), 1)
        self.assertEqual(wm.episodes(f["W1_RANK"], np.ones(50, bool)), [(20, 20)])

    def test_repeated_warning(self):
        r = np.full(60, 0.5)
        r[[10, 11, 30, 50]] = 0.99
        self.assertEqual(wm.episodes(flags_for(r)["W1_RANK"], np.ones(60, bool)), [(10, 11), (30, 30), (50, 50)])

    def test_persistent_warning_needs_60_min(self):
        r = np.full(40, 0.5)
        r[5:10] = 0.8                                   # 50 min
        r[20:26] = 0.8                                  # 60 min
        w3 = flags_for(r)["W3_PERSISTENT"]
        self.assertFalse(w3[5:10].any())
        self.assertEqual(np.flatnonzero(w3).tolist(), [25])

    def test_gap_splitting(self):
        f = np.zeros(30, bool)
        f[[2, 5, 9]] = True                             # gaps of 2 and 3 buckets
        oper = np.ones(30, bool)
        self.assertEqual(wm.episodes(f, oper, 2), [(2, 5), (9, 9)])
        oper[3] = False                                 # a non-operational gap bucket breaks the episode
        self.assertEqual(wm.episodes(f, oper, 2), [(2, 2), (5, 5), (9, 9)])

    def test_slope_points_per_hour(self):
        y = 3.0 * np.arange(30)                         # +3 points per 10 min = 18 per hour
        np.testing.assert_allclose(wm.slope(y)[10:], 18.0)
        self.assertTrue(np.isnan(wm.slope(y)[3]))       # < 5 valid buckets
        np.testing.assert_allclose(wm.accel(wm.slope(y))[20:], 0.0, atol=1e-9)

    def test_ecdf_and_nan(self):
        ref = np.array([1.0, 2.0, 3.0, 4.0])
        np.testing.assert_allclose(wm.ecdf(ref, np.array([0.5, 2.0, 9.0])), [0, 0.5, 1.0])
        self.assertTrue(np.isnan(wm.ecdf(ref, np.array([np.nan]))[0]))

    def test_window_stat_min_valid(self):
        x = np.ones(12)
        x[6:8] = np.nan                                 # 4 of 6 finite in (t - 60, t] at t = 11 -> value
        self.assertEqual(wm.window_stat(x, 60)[11], 1.0)
        x[8] = np.nan                                   # 3 of 6 -> NaN (the 4-of-6 rule)
        self.assertTrue(np.isnan(wm.window_stat(x, 60)[11]))


if __name__ == "__main__":
    unittest.main()
