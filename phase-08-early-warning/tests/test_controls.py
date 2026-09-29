import unittest

import numpy as np
import pandas as pd

import _synth
import build_controls as bc
import temporal_validation as tv
import validation


class TestControls(unittest.TestCase):
    def test_overlap_detection(self):
        ix = pd.date_range("2025-06-01 00:10", periods=10, freq="10min")
        m = bc.overlaps(ix, pd.Timestamp("2025-06-01 00:30"), pd.Timestamp("2025-06-01 00:50"))
        # bucket (t-10, t] overlaps [00:30, 00:50] for t = 00:40, 00:50; buckets ending at 00:30 / 01:00 only touch it
        self.assertEqual(ix[m].strftime("%H:%M").tolist(), ["00:40", "00:50"])

    def test_clean_mask_excludes_periods_and_pre_onset_zone(self):
        B, _ = _synth.base()
        e = B["events"].iloc[3]
        ix = B["ix"]
        t = lambda **k: ix.get_loc(e.T0 + pd.Timedelta(**k))  # noqa: E731
        self.assertFalse(B["clean"][t(hours=-23)])            # inside the 24 h before the onset
        self.assertFalse(B["clean"][t(hours=8)])              # end (T0 + 3 h) + 6 h buffer
        self.assertTrue(B["clean"][t(hours=10)])
        self.assertTrue(B["clean"][t(hours=-25)])

    def test_invalid_control_rejection(self):
        B, _ = _synth.base()
        p = 20 * 144
        self.assertTrue(B["elig"][60][p])
        B["dq"][p - 3] = True
        B["oper"][p - 40:p - 37] = False
        _synth.finish(B)
        self.assertFalse(B["elig"][60][p])                   # window touches a DQ window
        self.assertFalse(B["elig"][360][p])
        self.assertTrue(B["elig"][60][p + 10])
        B["oper"][p + 100:p + 103] = False                   # 3 of 6 operational -> rejected
        _synth.finish(B)
        self.assertFalse(B["elig"][60][p + 105])
        self.assertEqual(validation.control_recheck(B, 60), [])

    def test_independent_recheck_finds_contamination(self):
        B, _ = _synth.base()
        B["elig"][60][B["events"].pos_T0.iloc[0]] = True      # inject a contaminated control
        self.assertTrue(validation.control_recheck(B, 60))

    def test_matched_load_controls(self):
        B, x = _synth.base()
        strat = np.where(np.arange(len(x)) % 3, "LOW", "HIGH").astype(object)     # 1/3 HIGH: month median 0.1
        p0 = B["events"].pos_T0.to_numpy()
        strat[p0] = "HIGH"
        x = np.where(strat == "HIGH", 0.9, 0.1)
        # with month-only controls the events look elevated; matched on stratum the excess vanishes
        W = x
        r_month = tv.endpoint(x, B, 60, "m", _synth.CFG, W=W, boot=False, null=False)
        r_match = tv.endpoint(x, B, 60, "s", _synth.CFG, W=W, key=strat, boot=False, null=False)
        self.assertGreater(r_month["pe"], 0.3)
        self.assertAlmostEqual(r_match["pe"], 0.0)


if __name__ == "__main__":
    unittest.main()
