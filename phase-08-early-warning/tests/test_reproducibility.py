"""Determinism of the building blocks. Byte-identity of two full clean runs is gate G11 (run_phase8.py compares every
key output and the first-pass report with the previous run)."""
import unittest
import zlib

import numpy as np
import pandas as pd

import _synth
import temporal_validation as tv
from p8common import CFG, round_frame


class TestReproducibility(unittest.TestCase):
    def test_seed_is_a_stable_function_of_the_label(self):
        self.assertEqual(tv.seed_of("PRIMARY|h60"), (CFG.seed + zlib.crc32(b"PRIMARY|h60")) % 2 ** 32)
        self.assertNotEqual(tv.seed_of("PRIMARY|h60"), tv.seed_of("PRIMARY|h120"))

    def test_endpoint_identical_across_calls(self):
        B, x = _synth.base(lift=0.2, seed=3)
        a = tv.endpoint(x, B, 60, "rep", _synth.CFG)
        b = tv.endpoint(x.copy(), B, 60, "rep", _synth.CFG)
        for k in ("pe", "p_value", "ci_low", "ci_high", "cliffs_delta"):
            self.assertEqual(a[k], b[k], k)
        np.testing.assert_array_equal(a["null"], b["null"])

    def test_last_bit_float_noise_does_not_change_csv_bytes(self):
        a = pd.DataFrame({"a": [0.3, np.nan, 1 / 3], "b": ["x", "y", "z"]})
        b = a.assign(a=[0.1 + 0.2, np.nan, 1 / 3 + 1e-15])
        self.assertNotEqual(a.a.iat[0], b.a.iat[0])
        self.assertEqual(*[round_frame(d).to_csv(index=False) for d in (a, b)])


if __name__ == "__main__":
    unittest.main()
