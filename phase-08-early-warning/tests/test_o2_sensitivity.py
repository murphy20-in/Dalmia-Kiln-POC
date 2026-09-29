import unittest

import numpy as np
import pandas as pd

import build_event_windows as bew
import o2_sensitivity as o2s
import run_phase8


def one_event(o2_flag: np.ndarray, conf_dq: np.ndarray):
    ix = pd.date_range("2025-06-01 00:10", periods=40, freq="10min")
    t0 = ix[20]
    eps = pd.DataFrame({"episode_id": ["E1"], "onset_time": [t0], "detection_time": [ix[25]], "start_time": [ix[21]],
                        "end_time": [ix[30]], "in_final_set": [True], "reference_state": ["OUT_OF_SAMPLE"],
                        "severity_class": ["LOW"], "confidence": ["LOW"], "onset_censored": [False]})
    s = pd.DataFrame({"operational": True, "risk_status": "SCORED", "confidence_band": "MEDIUM",
                      "data_quality_status": np.where(conf_dq <= 0.5, "POOR", "GOOD")}, index=ix)
    return bew.events_table(eps, ix, s, np.zeros(40, bool), o2_flag, conf_dq).iloc[0]


class TestO2Sensitivity(unittest.TestCase):
    def test_missing_o2_flag_gives_equal_status(self):
        e = one_event(np.zeros(40, bool), np.full(40, 0.9))
        self.assertEqual(e.data_quality_status, "VALID")
        self.assertEqual(e.data_quality_status_o2x, "VALID")
        self.assertEqual(e.data_quality_reason, "NONE")

    def test_o2_penalty_only_affects_the_full_variant(self):
        o2 = np.zeros(40, bool)
        o2[15:21] = True
        dq = np.where(o2, 0.45, 0.9)                     # halved by the O2 penalty -> POOR
        e = one_event(o2, dq)
        self.assertEqual(e.data_quality_status, "DATA_QUALITY_CONTAMINATED")
        self.assertIn("O2_AMBIENT_SUSPECT", e.data_quality_reason)
        self.assertEqual(e.data_quality_status_o2x, "VALID")

    def test_genuine_poor_quality_stays_contaminated_without_o2(self):
        e = one_event(np.zeros(40, bool), np.full(40, 0.3))
        self.assertEqual(e.data_quality_status_o2x, "DATA_QUALITY_CONTAMINATED")

    def test_variant_uses_its_own_event_set(self):
        ev = pd.DataFrame({"evaluable": [True, False], "evaluable_o2x": [True, True]})
        B = {"events": ev, "x": 1}
        Bv = run_phase8.variant_base(B)
        self.assertEqual(Bv["events"].evaluable.tolist(), [True, True])
        self.assertEqual(B["events"].evaluable.tolist(), [True, False])     # full variant untouched

    def test_status_labels(self):
        self.assertEqual(o2s._status("WEAK", "WEAK"), "ROBUST_TO_O2")
        self.assertEqual(o2s._status("NOT_SUPPORTED", "WEAK"), "SENSITIVE_TO_O2")
        r = o2s._num("m", 0.05, 0.08)
        self.assertAlmostEqual(r["absolute_difference"], 0.03)
        self.assertTrue(np.isnan(o2s._num("m", 0.0, 0.1)["relative_difference"]))


if __name__ == "__main__":
    unittest.main()
