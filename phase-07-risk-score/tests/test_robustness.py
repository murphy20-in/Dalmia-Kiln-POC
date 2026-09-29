"""Robustness helpers: comparison metrics, materiality verdict, circular-shift / random-window nulls, variant coverage."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import synthetic
from common import PRIMARY
from robustness import (MIN_SHIFT_BUCKETS, circular_null, compare, jaccard, p_upper, random_windows_null, run_variant,
                        variant_set, verdict)

REQUIRED_DIMENSIONS = {"REFERENCE_WINDOW", "LOAD_NORMALIZATION", "FAMILY_WEIGHTS", "PERSISTENCE_WINDOW",
                       "ABNORMAL_THRESHOLD", "MISSING_VALUE_TREATMENT", "CORRELATED_SIGNAL_GROUPING", "AFR_INCLUSION",
                       "PHASE4_INCLUSION", "SMOOTHING_WINDOW"}


class TestCompare(unittest.TestCase):
    def test_identical_is_stable(self):
        r = np.random.default_rng(0).uniform(0, 100, 500)
        b = np.where(r > 50, "HIGH", "LOW").astype(object)
        m = compare(r, b, r.copy(), b.copy())
        self.assertEqual((m["spearman"], m["band_agreement"], m["median_abs_diff"]), (1.0, 1.0, 0.0))
        self.assertEqual(verdict(m), "STABLE")

    def test_scrambled_is_sensitive(self):
        rng = np.random.default_rng(1)
        r = rng.uniform(0, 100, 500)
        b = np.where(r > 50, "HIGH", "LOW").astype(object)
        r2 = rng.permutation(r)
        m = compare(r, b, r2, np.where(r2 > 50, "HIGH", "LOW").astype(object))
        self.assertEqual(verdict(m), "SENSITIVE")

    def test_too_few_rows_not_evaluable(self):
        self.assertEqual(verdict(compare(np.ones(5), np.array(["LOW"] * 5, dtype=object), np.ones(5),
                                         np.array(["LOW"] * 5, dtype=object))), "NOT_EVALUABLE")

    def test_jaccard(self):
        self.assertEqual(jaccard(np.array([1, 1, 0], bool), np.array([1, 0, 0], bool)), 0.5)
        self.assertEqual(jaccard(np.zeros(3, bool), np.zeros(3, bool)), 1.0)


class TestNulls(unittest.TestCase):
    def test_circular_null_breaks_alignment_but_not_marginals(self):
        L = 5000
        x = np.zeros(L)
        inside = np.zeros(L, bool)
        inside[1000:1200] = True
        x[inside] = 10.0
        null = circular_null(x, inside, lambda s, m: float(s[m].mean()), 100, 0, MIN_SHIFT_BUCKETS // 2)
        self.assertEqual(null.size, 100)
        self.assertLess(np.median(null), 10.0)
        self.assertLess(p_upper(10.0, null), 0.05)

    def test_random_windows_null_is_seeded(self):
        x = np.random.default_rng(2).random(3000)
        np.testing.assert_array_equal(random_windows_null(x, [30, 40], 20, 5), random_windows_null(x, [30, 40], 20, 5))

    def test_p_upper_bounds(self):
        self.assertAlmostEqual(p_upper(1.0, np.zeros(99)), 0.01)
        self.assertEqual(p_upper(0.0, np.ones(9)), 1.0)


class TestVariantSet(unittest.TestCase):
    def test_all_required_dimensions_present(self):
        _, _, refs = synthetic.fixture()
        dims = {d for d, *_ in variant_set(refs["PRIMARY"])}
        self.assertTrue(REQUIRED_DIMENSIONS <= dims, REQUIRED_DIMENSIONS - dims)

    def test_reference_windows_stay_inside_apr_may(self):
        _, _, refs = synthetic.fixture()
        for _, name, cfg, _ in variant_set(refs["PRIMARY"]):
            self.assertGreaterEqual(pd.Timestamp(cfg.ref_start), pd.Timestamp(PRIMARY.ref_start), name)
            self.assertLessEqual(pd.Timestamp(cfg.ref_end), pd.Timestamp(PRIMARY.ref_end), name)

    def test_merged_family_variant_runs(self):
        g, ctx, refs = synthetic.fixture()
        dim, name, cfg, opts = next(v for v in variant_set(refs["PRIMARY"]) if v[0] == "CORRELATED_SIGNAL_GROUPING")
        v = run_variant(g, cfg, ctx, opts)
        self.assertEqual(len(v["ref"]["families"]), 4)
        self.assertTrue(np.nanmax(v["R"]) <= 100)


if __name__ == "__main__":
    unittest.main()
