"""L1 / L2 / L4 / L5 / L7 on synthetic data plus one real-data truncation check of the frozen Phase 7 score."""
import unittest

import numpy as np

import _synth
import build_event_windows as bew
import calibration
import negative_controls as nc
import warning_metrics as wm
from p8common import CFG, SCORE_COLUMNS, p7c, risk_core


class TestTemporalLeakage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.B, x = _synth.base(lift=0.3)
        cls.score = 100 * x

    def test_l1_l5_signals_ignore_the_future(self):
        B, sc = self.B, self.score
        a = _synth.signals(sc, B)
        a["roll"] = wm.rolling_rank(sc, _synth.CFG)
        for cut in (2000, 6000, 11000):
            y = sc.copy()
            y[cut + 1:] = np.random.default_rng(cut).uniform(0, 100, y.size - cut - 1)
            b = _synth.signals(y, B)
            b["roll"] = wm.rolling_rank(y, _synth.CFG)
            s = slice(0, cut + 1)
            for k in ("rank", "slope", "accel", "roll"):
                np.testing.assert_array_equal(a[k][s], b[k][s], err_msg=k)
            for w in a["flags"]:
                np.testing.assert_array_equal(a["flags"][w][s], b["flags"][w][s], err_msg=w)
            for h in CFG.horizons:
                np.testing.assert_array_equal(wm.window_stat(a["rank"], h)[s], wm.window_stat(b["rank"], h)[s])

    def test_l2_future_perturbation_nc5(self):
        sig = _synth.signals(self.score, self.B)
        ok, bad = nc.nc5_future_perturbation(sig, self.B, _synth.CFG)
        self.assertTrue(ok, bad)

    def test_l4_loeo_threshold_excludes_target(self):
        v = np.array([0.2, 0.3, 0.5, 0.55, 0.8, np.nan, 0.9])
        t = calibration.loeo_thresholds(v, 0.25)
        for i in range(v.size):
            w = v.copy()
            w[i] = -50.0
            self.assertTrue(np.isnan(t[i]) and np.isnan(calibration.loeo_thresholds(w, 0.25)[i])
                            or calibration.loeo_thresholds(w, 0.25)[i] == t[i])

    def test_l7_afr_context_not_read(self):
        self.assertNotIn("afr_context", SCORE_COLUMNS)
        self.assertNotIn("afr_context", bew.load_scores().columns)
        self.assertEqual(p7c.PRIMARY.afr_weight, 0.0)

    def test_l1_frozen_phase7_score_truncation(self):
        ctx, refs = p7c.load_context(), p7c.load_refs()
        g, ref = ctx["grid"], refs["PRIMARY"]
        full = risk_core.score_core(g, ref, p7c.PRIMARY, ctx)["R"]
        cut = int(np.searchsorted(g.index, np.datetime64("2025-07-15 21:00")))
        part = risk_core.score_core(g.iloc[:cut + 1], ref, p7c.PRIMARY, ctx)["R"]
        np.testing.assert_allclose(part, full[:cut + 1], rtol=0, atol=1e-12, equal_nan=True)
        no_afr = {**ctx, "afr_events": ctx["afr_events"].iloc[0:0]}
        np.testing.assert_array_equal(risk_core.score_core(g, ref, p7c.PRIMARY, no_afr)["R"], full)


if __name__ == "__main__":
    unittest.main()
