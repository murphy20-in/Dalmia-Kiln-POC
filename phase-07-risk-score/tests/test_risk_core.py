"""Core score: empty / one / multiple families, max, zero, clipping, determinism, family-awareness, status, bands."""
from __future__ import annotations

import unittest

import numpy as np

import synthetic  # noqa: F401  (sets sys.path / bytecode)
from common import FAMILIES, PRIMARY, kpi_core, variant
from risk_core import (SCORING_GRID_COLUMNS, band_of, components_long, intensity, magnitude, score_core, score_frame,
                       status)

F = len(FAMILIES)


def mag(S, cfg=PRIMARY):
    return magnitude(np.atleast_2d(np.asarray(S, float)), np.zeros((1, len(S))), np.ones((1, len(S))), cfg)


class TestIntensity(unittest.TestCase):
    def test_matches_phase3_transform(self):
        S = np.array([[0.0, 0.5, 1.0, 3.0, 10.0]])
        _, a = intensity(S, np.zeros_like(S), np.ones_like(S))
        np.testing.assert_allclose(a[0], kpi_core.to_kpi(S[0], 0.0, 1.0) / 100)

    def test_zero_at_median_half_at_p90_and_clipped(self):
        e, a = intensity(np.array([[-5.0, 0.0, 1.0, 1e6]]), np.zeros((1, 4)), np.ones((1, 4)))
        self.assertEqual(e[0, 0], 0.0)                 # below the median is clipped to 0, never negative
        np.testing.assert_allclose(a[0, :3], [0.0, 0.0, 0.5])
        self.assertLessEqual(a[0, 3], 1.0)

    def test_nan_stays_nan(self):
        _, a = intensity(np.array([[np.nan]]), np.zeros((1, 1)), np.ones((1, 1)))
        self.assertTrue(np.isnan(a[0, 0]))


class TestMagnitude(unittest.TestCase):
    def test_empty_families(self):
        m = mag([np.nan] * F)
        self.assertEqual((m["H"][0], m["C"][0], m["n_use"][0]), (0.0, 0.0, 0))

    def test_zero_score(self):
        m = mag([0.0] * F)
        self.assertEqual((m["H"][0], m["C"][0], m["n_abn"][0]), (0.0, 0.0, 0))

    def test_one_family(self):
        m = mag([1.0] + [0.0] * (F - 1))               # a = 0.5 at the P90
        self.assertAlmostEqual(m["H"][0], 0.5 * 0.5 + 0.5 * 0.5 / F)
        self.assertEqual(m["C"][0], 0.0)               # a single family never earns concurrence

    def test_multiple_families_concurrence(self):
        m = mag([2.0, 2.0, 2.0, 0.0, 0.0])
        self.assertEqual(m["n_abn"][0], 3)
        self.assertAlmostEqual(m["C"][0], 2 / 4)

    def test_max_score_is_100(self):
        g, ctx, refs = synthetic.fixture()
        big = g.copy()
        for d in FAMILIES:
            big.loc[big.state.eq("RUNNING"), f"comp_{d}"] = 1e9
        c = score_core(big, refs["PRIMARY"], PRIMARY, ctx)
        self.assertAlmostEqual(np.nanmax(c["R"]), 100.0, places=6)
        self.assertLessEqual(np.nanmax(c["R"]), 100.0)

    def test_tie_break_is_fixed_family_order(self):
        m = mag([1.0] * F)
        self.assertEqual(m["top"][0], 0)

    def test_three_families_outweigh_one_saturated_family(self):
        """10 abnormal thermal tags are ONE family: a single saturated family must not outweigh 3 moderate ones."""
        cfg = variant(w_persistence=0.25)
        one = mag([1e6, 0, 0, 0, 0], cfg)
        three = mag([1.5, 1.5, 1.5, 0, 0], cfg)
        r1 = 0.5 * one["H"][0] + 0.25 * one["C"][0]
        r3 = 0.5 * three["H"][0] + 0.25 * three["C"][0]
        self.assertGreater(r3, r1)

    def test_fixed_denominator_missing_family_never_inflates(self):
        rng = np.random.default_rng(1)
        S = rng.gamma(1.0, 1.0, (500, F))
        S2 = np.where(rng.random(S.shape) < 0.3, np.nan, S)
        a, b = magnitude(S, np.zeros_like(S), np.ones_like(S), PRIMARY), magnitude(S2, np.zeros_like(S), np.ones_like(S), PRIMARY)
        self.assertTrue((b["H"] <= a["H"] + 1e-12).all() and (b["C"] <= a["C"] + 1e-12).all())


class TestScoreAndComponents(unittest.TestCase):
    def test_score_range_and_reconciliation(self):
        g, ctx, refs = synthetic.fixture()
        f, core = score_frame(g, refs, ctx)
        v = f.risk_score.dropna()
        self.assertTrue(v.between(0, 100).all())
        comp = components_long(f, core)
        tot = comp.groupby("timestamp").family_contribution.sum()
        np.testing.assert_allclose(tot.to_numpy(), f.score_all.reindex(tot.index).to_numpy(), atol=1e-9)
        self.assertEqual(set(comp.family), set(FAMILIES) | {"CONCURRENCE", "PERSISTENCE"})

    def test_deterministic(self):
        g, ctx, refs = synthetic.fixture()
        a, _ = score_frame(g, refs, ctx)
        b, _ = score_frame(g, refs, ctx)
        self.assertTrue(a.equals(b))

    def test_context_and_derived_columns_never_change_the_score(self):
        """The KPI (aggregate of the same families), AFR, coal and Phase 4 are not scoring inputs."""
        g, ctx, refs = synthetic.fixture()
        g2 = g.copy()
        g2["kpi_value"], g2["afr"], g2["coal_pc"], g2["p4"] = 99.0, 0.0, 50.0, 9.0
        self.assertNotIn("kpi_value", SCORING_GRID_COLUMNS)
        a = score_core(g, refs["PRIMARY"], PRIMARY, ctx)["R"]
        b = score_core(g2, refs["PRIMARY"], PRIMARY, ctx)["R"]
        np.testing.assert_array_equal(a, b)


class TestStatusAndBands(unittest.TestCase):
    def test_status_precedence(self):
        st = np.array(["STOPPED", "TRANSITION", "CONFLICT", "UNKNOWN", "RUNNING", "RUNNING", "RUNNING", "RUNNING"],
                      dtype=object)
        n = np.array([5, 5, 5, 5, 0, 2, 5, 5])
        cb = np.array(["MEDIUM"] * 6 + ["LOW", "MEDIUM"])
        self.assertEqual(list(status(st, n, cb, PRIMARY)),
                         ["STOPPED", "TRANSITION_CONTEXT", "TRANSITION_CONTEXT", "NOT_SCORABLE", "NOT_SCORABLE",
                          "INSUFFICIENT_DATA", "VALID_REDUCED_CONFIDENCE", "VALID"])

    def test_non_valid_buckets_have_no_numeric_score(self):
        g, ctx, refs = synthetic.fixture()
        f, _ = score_frame(g, refs, ctx)
        self.assertTrue(f.loc[~f.risk_status.str.startswith("VALID"), "risk_score"].isna().all())
        self.assertTrue(f.loc[f.risk_status.eq("STOPPED"), "risk_band"].eq("NOT_SCORED").all())

    def test_band_mapping_and_unbanded(self):
        bands = {"status": "BANDED", "edges": [{"band": "ELEVATED", "value": 20.0}, {"band": "HIGH", "value": 40.0}]}
        self.assertEqual(list(band_of(np.array([0, 19.9, 20, 39.9, 40, 100, np.nan]), bands)),
                         ["LOW", "LOW", "ELEVATED", "ELEVATED", "HIGH", "HIGH", ""])
        self.assertEqual(list(band_of(np.array([5.0, np.nan]), {"status": "CALIBRATION_INSUFFICIENT", "edges": []})),
                         ["UNBANDED", ""])


class TestReasons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g, cls.ctx, cls.refs = synthetic.fixture()
        cls.f, cls.core = score_frame(cls.g, cls.refs, cls.ctx)

    def test_primary_is_largest_contributor_with_below_threshold_suffix(self):
        from risk_core import driver_points
        pts, act, codes = driver_points(self.core, PRIMARY)
        scored = self.f.risk_status.str.startswith("VALID").to_numpy()
        for i in np.flatnonzero(scored)[:400]:
            j = int(pts[i].argmax())
            want = "NO_DEVIATION_FROM_REFERENCE" if pts[i, j] <= 0 else codes[j] + ("" if act[i, j] else "_BELOW_THRESHOLD")
            self.assertEqual(self.f.primary_reason.iloc[i], want)

    def test_secondary_reasons_ordered_by_points_then_context(self):
        from risk_core import driver_points
        pts, act, codes = driver_points(self.core, PRIMARY)
        i = int(np.flatnonzero(self.f.family_count_abnormal.to_numpy() >= 3)[0])
        drivers = [c for c in self.f.secondary_reasons.iloc[i].split(";") if c in codes]
        p = [pts[i, codes.index(c)] for c in drivers]
        self.assertEqual(p, sorted(p, reverse=True))

    def test_afr_and_phase4_never_in_reason_strings(self):
        txt = ";".join(self.f.secondary_reasons) + ";".join(self.f.primary_reason)
        self.assertNotIn("AFR", txt)
        self.assertNotIn("PHASE4", txt)


class TestVariantPaths(unittest.TestCase):
    def test_available_denominator_can_inflate_fixed_cannot(self):
        S = np.array([[3.0, np.nan, np.nan, np.nan, np.nan]])
        fixed = mag(S[0])
        avail = magnitude(S, np.zeros_like(S), np.ones_like(S), variant(denominator="available"))
        self.assertGreater(avail["H"][0], fixed["H"][0])

    def test_load_band_anchors(self):
        from reference_builder import fit_reference
        g, ctx, _ = synthetic.fixture()
        ref = fit_reference(g, variant(name="LB", load_mode="load_band"), ctx["episodes"], ctx)
        self.assertEqual(sorted(ref["anchors_by_band"]), ["0", "1", "2"])
        c = score_core(g, ref, variant(load_mode="load_band"), ctx)
        self.assertTrue(np.nanmax(c["R"]) <= 100)


if __name__ == "__main__":
    unittest.main()
