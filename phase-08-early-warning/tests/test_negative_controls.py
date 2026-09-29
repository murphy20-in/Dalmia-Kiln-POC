"""Negative controls and the statistics behind them (permutation, block bootstrap, seeds, insufficient samples)."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import _synth
import negative_controls as nc
import temporal_validation as tv
import validation
import warning_metrics as wm
from p8common import nb

CFG = _synth.CFG


class TestNegativeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.B0, cls.x0 = _synth.base(lift=0.0, seed=1)
        cls.B1, cls.x1 = _synth.base(lift=0.5, seed=1)

    def test_permutation_detects_planted_effect_and_not_noise(self):
        r1 = tv.endpoint(self.x1, self.B1, 60, "p1", CFG)
        r0 = tv.endpoint(self.x0, self.B0, 60, "p0", CFG)
        self.assertLess(r1["p_value"], 0.01)
        self.assertGreater(r1["ci_low"], 0)
        self.assertGreater(r0["p_value"], 0.01)
        self.assertLess(abs(r0["null_median"]), nc.NULL_TOL)

    def test_nc1_circular_shift_degrades(self):
        r = tv.endpoint(self.x1, self.B1, 60, "p1", CFG, boot=False)
        null = nc.nc1_circular(self.x1, self.B1, CFG)
        self.assertEqual(np.isfinite(null).sum(), CFG.n_null // 4)
        self.assertLess(abs(np.median(null)), nc.NULL_TOL)
        self.assertLess(np.median(null), r["pe"])

    def test_nc4_reads_the_mirrored_position(self):
        x = self.x1
        R = wm.window_stat(x[::-1], 60)
        for p in self.B1["events"].pos_T0:
            q = x.size - 1 - p
            self.assertEqual(R[p], np.median(x[q:q + nb(60)]))

    def test_nc5_and_l1_catch_a_centred_window(self):
        centred = lambda x, m: pd.Series(np.asarray(x, float)).rolling(nb(m), center=True, min_periods=1).median(
        ).to_numpy()  # noqa: E731
        sig = _synth.signals(100 * self.x1, self.B1)
        with mock.patch.object(wm, "window_stat", centred):
            ok, bad = nc.nc5_future_perturbation(sig, self.B1, CFG)
            p = int(self.B1["events"].pos_T0.iat[0])
            y = sig["score"].copy()
            y[p + 1:] = 0.0
            diff = validation._signal_prefix_equal(validation._signals(sig["score"], sig, np.zeros(y.size), CFG),
                                                   validation._signals(y, sig, np.zeros(y.size), CFG), p)
        self.assertFalse(ok)
        self.assertTrue(any(d.startswith("W") for d in diff), diff)

    def test_nc3_backward_uses_post_end_window(self):
        b = nc.nc3_backward(self.x1, self.B1, CFG)
        self.assertEqual(b["post_end"]["n_evaluable"], 12)
        self.assertLess(b["post_end"]["pe"], 0.2)          # the planted lift is only before T0

    def test_block_bootstrap(self):
        v = np.random.default_rng(0).normal(size=600)
        blocks = np.repeat(np.arange(50), 12)
        a = tv.boot_medians(v, blocks, 200, 5)
        self.assertEqual(a.shape, (200,))
        np.testing.assert_array_equal(a, tv.boot_medians(v, blocks, 200, 5))
        self.assertTrue(np.quantile(a, 0.025) < np.median(v) < np.quantile(a, 0.975))

    def test_deterministic_seeds(self):
        a = tv.endpoint(self.x1, self.B1, 60, "same", CFG)
        b = tv.endpoint(self.x1, self.B1, 60, "same", CFG)
        self.assertEqual((a["p_value"], a["ci_low"], a["ci_high"]), (b["p_value"], b["ci_low"], b["ci_high"]))
        self.assertEqual(tv.seed_of("PRIMARY|h60"), tv.seed_of("PRIMARY|h60"))

    def test_insufficient_sample(self):
        B = dict(self.B1)
        B["elig"] = {k: np.zeros_like(v) for k, v in self.B1["elig"].items()}
        r = tv.endpoint(self.x1, B, 60, "none", CFG)
        self.assertEqual(r["n_evaluable"], 0)
        self.assertTrue(np.isnan(r["pe"]) and np.isnan(r["p_value"]))
        few = tv.endpoint(self.x1, self.B1, 60, "few", CFG, ev_mask=np.arange(12) < 5)
        self.assertEqual(tv.primary_status(few, 1.0, CFG), "INSUFFICIENT_DATA")
        self.assertEqual(tv.secondary_status(few, 0.0, CFG), "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
