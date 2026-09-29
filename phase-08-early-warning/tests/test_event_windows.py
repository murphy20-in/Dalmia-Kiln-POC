import unittest

import numpy as np
import pandas as pd

import _synth
import build_event_windows as bew
import temporal_validation as tv
import warning_metrics as wm
from p8common import nb

S = bew.event_status


class TestEventWindows(unittest.TestCase):
    def test_status_precedence(self):
        self.assertEqual(S(0, 6, True, 1, True, True, 1, True), "NOT_EVALUABLE")
        self.assertEqual(S(3, 6, True, 1, True, True, 1, True), "INSUFFICIENT_DATA")
        self.assertEqual(S(4, 6, True, 0, True, True, 1, True), "DATA_QUALITY_CONTAMINATED")
        self.assertEqual(S(6, 6, False, 0.6, True, True, 1, True), "DATA_QUALITY_CONTAMINATED")
        self.assertEqual(S(6, 6, False, 0.5, True, True, 1, True), "TRANSITION_CONTAMINATED")
        self.assertEqual(S(6, 6, False, 0, False, True, 0, False), "VALID_REDUCED_CONFIDENCE")
        self.assertEqual(S(6, 6, False, 0, False, False, 0, True), "VALID_REDUCED_CONFIDENCE")
        self.assertEqual(S(6, 6, False, 0, False, False, 0.4, False), "VALID")

    def test_window_buckets(self):
        self.assertEqual(nb(60), 6)
        self.assertEqual(nb(15), 2)
        self.assertEqual(nb(1440), 144)

    def test_t0_boundary_and_post_event_exclusion(self):
        x = np.arange(100, dtype=float)
        y = x.copy()
        y[51:] = -1e9                                   # everything after T0 = 50
        for h in (15, 60, 240):
            self.assertEqual(wm.window_stat(x, h)[50], wm.window_stat(y, h)[50])
        self.assertEqual(wm.window_stat(x, 60)[50], np.median(x[45:51]))   # (T0 - 60, T0] = 6 buckets ending at T0

    def test_pre_event_exclusion_other_period_in_window(self):
        B, x = _synth.base()
        e = B["events"].iloc[5]
        extra = pd.DataFrame({"episode_id": ["X"], "onset_time": [e.T0 - pd.Timedelta(hours=20)],
                              "end_time": [e.T0 - pd.Timedelta(hours=19)]})       # extent + 6 h ends at T0 - 13 h
        B["eps"] = pd.concat([B["eps"], extra], ignore_index=True)
        _synth.finish(B)
        r60 = tv.endpoint(x, B, 60, "t", _synth.CFG, boot=False, null=False)
        r1440 = tv.endpoint(x, B, 1440, "t", _synth.CFG, boot=False, null=False)
        self.assertEqual(r60["n_excluded_other_period_in_window"], 0)
        self.assertEqual(r1440["n_excluded_other_period_in_window"], 1)
        self.assertFalse(r1440["ok"][5])

    def test_own_period_never_contaminates_own_window(self):
        B, x = _synth.base()
        r = tv.endpoint(x, B, 1440, "t", _synth.CFG, boot=False, null=False)
        self.assertEqual(r["n_excluded_other_period_in_window"], 0)
        self.assertEqual(r["n_evaluable"], 12)


if __name__ == "__main__":
    unittest.main()
