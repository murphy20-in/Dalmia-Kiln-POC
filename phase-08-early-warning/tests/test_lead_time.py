import unittest

import numpy as np

import _synth
import lead_time
import temporal_validation as tv
from p8common import CFG

N, P0 = 300, 250


def sig(score, slope):
    return {"score": np.asarray(score, float), "rank": np.asarray(score, float) / 100, "slope": np.asarray(slope, float)}


class TestLeadTime(unittest.TestCase):
    def test_warning_coverage_and_lead(self):
        B, _ = _synth.base()
        p = B["events"].pos_T0.to_numpy()
        flag = np.zeros(len(B["ix"]), bool)
        flag[p[0] - 3] = True                    # 30 min before the first onset
        flag[p[1] + 1] = True                    # after T0: must not count
        c = tv.warning_coverage(flag, B, 60, np.ones(12, bool))
        self.assertEqual(c["n_covered"], 1)
        self.assertAlmostEqual(c["coverage"], 1 / 12)
        self.assertEqual(c["median_lead_time"], 30.0)
        self.assertTrue(0 <= c["control_window_rate"] < 0.01)

    def test_no_warning(self):
        L = lead_time.event_lead(np.zeros(N, bool), sig(np.ones(N), np.zeros(N)), np.ones(N, bool), P0, CFG)
        self.assertFalse(L["warning_detected"])
        self.assertTrue(np.isnan(L["lead_time_minutes"]) and np.isnan(L["sustained_lead_minutes"]))
        self.assertEqual(L["warning_duration_minutes"], 0.0)
        self.assertTrue(np.isnan(L["trend_onset_lead_minutes"]))

    def test_first_and_sustained_warning(self):
        f = np.zeros(N, bool)
        f[P0 - 30] = True                     # isolated warning 300 min before T0
        f[P0 - 12:P0 + 1] = True              # episode in force at T0, started 120 min before
        f[P0 + 5:] = True                     # after T0: must be ignored
        sc = np.ones(N)
        sc[P0 - 40] = 90
        sc[P0 + 10] = 1000                    # post-T0 peak ignored
        sl = np.full(N, -1.0)
        sl[P0 - 8:] = 2.0                     # positive slope for the last 80 min
        L = lead_time.event_lead(f, sig(sc, sl), np.ones(N, bool), P0, CFG)
        self.assertEqual(L["lead_time_minutes"], 300.0)
        self.assertTrue(L["warning_in_force_at_T0"])
        self.assertEqual(L["sustained_lead_minutes"], 120.0)
        self.assertEqual(L["warning_duration_minutes"], 140.0)
        self.assertEqual(L["peak_lead_minutes"], 400.0)
        self.assertEqual(L["peak_pre_event_score"], 90.0)
        self.assertEqual(L["trend_onset_lead_minutes"], 80.0)

    def test_lookback_is_24h(self):
        f = np.zeros(N, bool)
        f[P0 - 144] = True                    # exactly 24 h before: outside (T0 - 24 h, T0]
        L = lead_time.event_lead(f, sig(np.ones(N), np.zeros(N)), np.ones(N, bool), P0, CFG)
        self.assertFalse(L["warning_detected"])
        f[P0 - 143] = True
        L = lead_time.event_lead(f, sig(np.ones(N), np.zeros(N)), np.ones(N, bool), P0, CFG)
        self.assertEqual(L["lead_time_minutes"], 1430.0)

    def test_warning_ended_before_t0_is_not_in_force(self):
        f = np.zeros(N, bool)
        f[P0 - 10:P0 - 4] = True              # ends 40 min before T0 (> 20 min tolerance)
        L = lead_time.event_lead(f, sig(np.ones(N), np.zeros(N)), np.ones(N, bool), P0, CFG)
        self.assertFalse(L["warning_in_force_at_T0"])
        self.assertTrue(np.isnan(L["sustained_lead_minutes"]))


if __name__ == "__main__":
    unittest.main()
