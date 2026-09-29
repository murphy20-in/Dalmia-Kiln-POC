import unittest

import numpy as np

import _synth
import load_sensitivity as ls


def r(pe, p=0.01, n=10):
    return {"pe": pe, "p_value": p, "n_evaluable": n}


class TestLoadSensitivity(unittest.TestCase):
    def test_load_adjusted_subtracts_stratum_median(self):
        x = np.array([1.0, 2.0, 3.0, 10.0, 20.0, 30.0])
        strat = np.array(["A", "A", "A", "B", "B", "B"], dtype=object)
        out = ls.load_adjusted(x, strat, np.array([True, True, True, True, True, False]))
        np.testing.assert_allclose(out, [-1, 0, 1, -5, 5, 15])

    def test_verdict_rules(self):
        base = {"RAW": r(0.1), "LOAD_ADJUSTED": r(0.1), "MATCHED_LOAD": r(0.1), "TRANSITION_EXCLUDED": r(0.1)}
        self.assertEqual(ls.verdict(base, _synth.CFG), "ROBUST_TO_LOAD")
        self.assertEqual(ls.verdict({**base, "MATCHED_LOAD": r(0.1, 0.3)}, _synth.CFG), "ATTENUATED")
        self.assertEqual(ls.verdict({**base, "LOAD_ADJUSTED": r(-0.01)}, _synth.CFG), "NOT_ROBUST")
        self.assertEqual(ls.verdict({**base, "RAW": r(-0.1)}, _synth.CFG), "NOT_APPLICABLE")
        self.assertEqual(ls.verdict({**base, "TRANSITION_EXCLUDED": r(0.1, n=5)}, _synth.CFG), "INSUFFICIENT_DATA")

    def test_transition_excluded_window(self):
        B, _ = _synth.base()
        p = 20 * 144
        B["s"].iloc[p - 2, B["s"].columns.get_loc("load_context")] = "LOAD_ASSOCIATED"
        st = ls.steady_window(B, 60)
        self.assertFalse(st[p])                      # a LOAD_ASSOCIATED bucket inside (p - 60, p]
        self.assertTrue(st[p + 6])

    def test_analyses_on_planted_effect(self):
        B, x = _synth.base(lift=0.5)
        res = ls.analyses(x, B, 60, "t", _synth.CFG, boot=False)
        self.assertEqual(set(res), {"RAW", "LOAD_ADJUSTED", "MATCHED_LOAD", "MATCHED_LOAD_ANY_MONTH",
                                    "TRANSITION_EXCLUDED", "LOW_FEED_EXCLUDED"})
        self.assertTrue(all(v["pe"] > 0.2 for v in res.values()))
        self.assertEqual(ls.verdict(res, _synth.CFG), "ROBUST_TO_LOAD")


if __name__ == "__main__":
    unittest.main()
