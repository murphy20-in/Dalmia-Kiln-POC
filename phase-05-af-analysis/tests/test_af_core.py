"""Unit tests for the Phase 5 pure functions (synthetic data only; no plant data needed).

Run:  ../../.venv/bin/python -B -m unittest discover -s ../tests -v      (from phase-05-af-analysis/scripts)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import af_core as ac  # noqa: E402
from af_core import PRIMARY, variant  # noqa: E402


class ValueClasses(unittest.TestCase):
    def test_missing_is_never_zero(self):
        c = ac.classify(np.array([np.nan, 0.0, 0.4, 1.0, -2.0, 31.0]))
        self.assertEqual(list(c), ["MISSING", "ZERO", "ZERO", "NONZERO", "INVALID", "NONZERO"])
        on = ac.on_state(np.array([np.nan, 0.0, 30.0]), 0.5)
        self.assertTrue(np.isnan(on[0]))
        self.assertEqual(list(on[1:]), [0.0, 1.0])


class Bands(unittest.TestCase):
    def test_cuts_from_nonzero_quantiles_and_assignment(self):
        x = np.r_[np.zeros(50), np.arange(1, 101, dtype=float)]
        b = ac.fit_bands(x, PRIMARY)
        self.assertAlmostEqual(b["q_lo"], np.quantile(np.arange(1, 101), 0.25))
        self.assertEqual(b["n_fit"], 100)
        self.assertEqual(b["label"], "POC_EMPIRICAL_BAND")
        a = ac.assign_band(np.array([0.0, 5.0, 50.0, 99.0, np.nan, -1.0]), b)
        self.assertEqual(list(a), ["NO_AFR", "LOW_AFR", "MEDIUM_AFR", "HIGH_AFR", "", ""])


class Runs(unittest.TestCase):
    def test_nan_breaks_runs(self):
        r = ac.runs(np.array([1, 1, np.nan, 1, 0, 0, 0], float))
        self.assertEqual(r.length.tolist(), [2, 1, 3])
        self.assertEqual(r.value.tolist(), [1.0, 1.0, 0.0])


class Transitions(unittest.TestCase):
    def test_start_stop_ramp_detected_once(self):
        x = np.r_[np.full(40, 30.0), np.zeros(10), np.full(40, 30.0), np.full(80, 40.0)]
        ev = ac.detect_transitions(x, PRIMARY)
        types = [t for _, t in ev]
        pos = {t: p for p, t in ev}
        self.assertEqual(pos["AFR_STOP"], 40)
        self.assertEqual(pos["AFR_START"], 50)
        self.assertEqual(types.count("AFR_RAMP_UP"), 1)            # refractory: one per cluster
        self.assertNotIn("AFR_RAMP_DOWN", types)

    def test_short_off_gap_is_not_a_start(self):
        x = np.r_[np.full(40, 30.0), np.zeros(3), np.full(40, 30.0)]      # 30 min off < 60 min rule
        self.assertNotIn("AFR_START", [t for _, t in ac.detect_transitions(x, PRIMARY)])

    def test_missing_is_not_off(self):
        x = np.r_[np.full(40, 30.0), np.full(10, np.nan), np.full(40, 30.0)]
        self.assertEqual(ac.detect_transitions(x, PRIMARY), [])

    def test_episode_status_excludes_stops_restarts_and_gaps(self):
        run, valid = np.ones(200, bool), np.ones(200, bool)
        self.assertEqual(ac.episode_status(100, run, valid, PRIMARY), "ELIGIBLE")
        r2 = run.copy()
        r2[110] = False
        self.assertEqual(ac.episode_status(100, r2, valid, PRIMARY), "EXCLUDED_KILN_STOP_AFTER")
        r3 = run.copy()
        r3[60] = False                                            # within 6 h before the window start (T-120)
        self.assertEqual(ac.episode_status(100, r3, valid, PRIMARY), "EXCLUDED_POST_RESTART")
        v2 = valid.copy()
        v2[80:100] = False
        self.assertEqual(ac.episode_status(100, run, v2, PRIMARY), "EXCLUDED_AFR_COVERAGE")
        others = np.array([94, 100])                              # another transition 60 min before T (in pre-window)
        self.assertEqual(ac.episode_status(100, run, valid, PRIMARY, others), "EXCLUDED_PRIOR_TRANSITION")
        early = np.array([70, 100])                               # 5 h before T: outside the pre-window ...
        self.assertEqual(ac.episode_status(100, run, valid, PRIMARY, early), "ELIGIBLE")
        self.assertEqual(ac.episode_status(100, run, valid, variant(prior_transition_h=6.0), early),
                         "EXCLUDED_PRIOR_TRANSITION")             # ... but inside the strict sensitivity zone
        self.assertEqual(ac.episode_status(100, run, valid, PRIMARY, np.array([100, 110])), "ELIGIBLE")

    def test_window_delta_alignment(self):
        y = np.r_[np.zeros(100), np.full(100, 10.0)]              # step at position 100
        d = ac.window_delta(y, 0, 6)                              # median (t, t+60] - median [t-60, t)
        self.assertEqual(d[99], 10.0)                             # anchor just before the step
        self.assertEqual(d[50], 0.0)
        self.assertEqual(d[150], 0.0)


class Matching(unittest.TestCase):
    def test_exact_strata_caliper_no_reuse_deterministic(self):
        feed = np.array([400, 401, 400.5, 420, 399, 400], float)
        strata = np.array(["a", "a", "a", "a", "b", "a"])
        hours = np.array([0, 1, 2, 3, 4, 200], float)
        t, c = np.array([0, 1]), np.array([2, 3, 4, 5])
        p1 = ac.match_pairs(t, c, strata, feed, hours, PRIMARY)
        self.assertEqual(p1, [(0, 2)])      # 3 outside feed caliper; 4 other stratum; 5 outside time caliper; 2 used
        self.assertEqual(p1, ac.match_pairs(t, c, strata, feed, hours, PRIMARY))

    def test_smd(self):
        self.assertAlmostEqual(ac.smd(np.array([1.0, 2, 3]), np.array([1.0, 2, 3])), 0.0)


class Shifts(unittest.TestCase):
    def test_circular_shift_preserves_window_multiset(self):
        x = np.arange(20, dtype=float)
        rows = np.zeros(20, bool)
        rows[5:15] = True
        s = ac.circular_shift(x, rows, 3)
        self.assertEqual(sorted(s[rows]), sorted(x[rows]))
        self.assertTrue(np.isnan(s[~rows]).all())
        self.assertFalse(np.array_equal(s[rows], x[rows]))


class Evidence(unittest.TestCase):
    base = dict(n=5000, n_eff=200, days=40, rho=0.2, q=0.01, ci_lo=0.1, ci_hi=0.3, repl_rho=0.15, repl_p=0.01,
                holdout="SAME_DIRECTION_NS", null_pass=True)

    def test_truth_table(self):
        self.assertEqual(ac.evidence_label(self.base), "ASSOCIATED")
        self.assertEqual(ac.evidence_label({**self.base, "null_pass": False}), "WEAK ASSOCIATION")
        self.assertEqual(ac.evidence_label({**self.base, "holdout": "REVERSED"}), "WEAK ASSOCIATION")
        self.assertEqual(ac.evidence_label({**self.base, "repl_rho": -0.1}), "WEAK ASSOCIATION")
        self.assertEqual(ac.evidence_label({**self.base, "rho": 0.05, "ci_lo": 0.01}), "WEAK ASSOCIATION")
        self.assertEqual(ac.evidence_label({**self.base, "q": 0.2}), "NOT SUPPORTED")
        self.assertEqual(ac.evidence_label({**self.base, "ci_lo": -0.01}), "NOT SUPPORTED")
        self.assertEqual(ac.evidence_label({**self.base, "n_eff": 10}), "INSUFFICIENT DATA")
        self.assertEqual(ac.evidence_label({**self.base, "rho": np.nan, "n": 50}), "INSUFFICIENT DATA")

    def test_stability_holdout_confidence(self):
        self.assertEqual(ac.stability_label(0.1, 0.2, 0.05), "STABLE_SIGN")
        self.assertEqual(ac.stability_label(0.1, -0.2, 0.05), "SIGN_FLIP")
        self.assertEqual(ac.stability_label(0.1, np.nan, 0.05), "INSUFFICIENT")
        self.assertEqual(ac.holdout_label(0.2, 0.1, 0.01), "CONFIRMED")
        self.assertEqual(ac.holdout_label(0.2, -0.1, 0.01), "REVERSED")
        self.assertEqual(ac.holdout_label(0.2, -0.1, 0.5), "OPPOSITE_DIRECTION_NS")
        self.assertEqual(ac.confidence_label("ASSOCIATED", 5, 5), "MEDIUM")
        self.assertEqual(ac.confidence_label("ASSOCIATED", 3, 5), "LOW")
        self.assertEqual(ac.confidence_label("ASSOCIATED", 3, 3), "LOW")           # < 4 groups evaluated
        self.assertEqual(ac.confidence_label("NOT SUPPORTED", 8, 8), "NOT_APPLICABLE")
        self.assertNotIn("HIGH", {ac.confidence_label(e, 8, 8) for e in ac.EVIDENCE})
        self.assertEqual(ac.confidence_label("ASSOCIATED", 5, 5, capped=True), "LOW")
        self.assertTrue(ac.confidence_cap("CO_MANIPULATION_OF_CONTROL_INPUTS"))
        self.assertTrue(ac.confidence_cap("KPI_INPUT|SP_HEAT_DERIVATION_R2=0.925"))
        self.assertEqual(ac.confidence_cap("KPI_INPUT"), "")


class Wording(unittest.TestCase):
    def test_forbidden_scanner(self):
        self.assertTrue(ac.forbidden_hits("Increasing AFR causes higher O2."))
        self.assertTrue(ac.forbidden_hits("We recommend AFR set-point of 30 TPH."))
        self.assertTrue(ac.forbidden_hits("Thermal substitution rate was 20 %."))
        self.assertFalse(ac.forbidden_hits("AFR-associated, not AFR-caused."))
        self.assertFalse(ac.forbidden_hits("Higher AFR was associated with lower O2."))


class Leakage(unittest.TestCase):
    def test_design_features_and_controls_are_causal(self):
        import af_context as ax
        n = 3000
        rng = np.random.default_rng(0)
        idx = pd.date_range("2025-04-01 00:10", periods=n, freq="10min")
        b = pd.DataFrame({t: rng.normal(100, 5, n) for t in ["Kiln-I!C", "Kiln-I!H", "Kiln-I!I", "Kiln-I!AF"]}, index=idx)
        b["bucket_state"] = "RUNNING"
        g = pd.DataFrame({"K": rng.uniform(0, 50, n), "D": rng.normal(0, 1, n)}, index=idx)

        def mk(afr, bb):
            return ax.Context(PRIMARY, idx, np.ones(n, bool), np.full(n, "DISCOVERY", object), np.ones(n, bool), afr,
                              bb, g.copy(), ac.block_ids(idx, 3), np.arange(n) * 10.0, [0.0, 1.0])
        afr = rng.uniform(0, 40, n)
        t0 = 2000
        afr2, b2 = afr.copy(), b.copy()
        afr2[t0 + 1:] = 999.0
        b2.iloc[t0 + 1:, :4] = -5.0
        c1, c2 = mk(afr.copy(), b.copy()), mk(afr2, b2)
        for atype, lag in (("LAGGED_LEVEL", 60), ("FUTURE_CHANGE", 60), ("MOMENTUM", 0)):
            x1, _, Z1 = ax.design(c1, "THERMAL", "Kiln-I!AF", atype, lag)
            x2, _, Z2 = ax.design(c2, "THERMAL", "Kiln-I!AF", atype, lag)
            np.testing.assert_allclose(x1[:t0 + 1], x2[:t0 + 1])
            np.testing.assert_allclose(Z1[:t0 + 1], Z2[:t0 + 1])


class Imports(unittest.TestCase):
    def test_phase5_names_shadow_upstream_modules(self):
        import generate_report
        import indicator_core
        import sensitivity_analysis
        here = str(Path(__file__).resolve().parents[1] / "scripts")
        self.assertTrue(sensitivity_analysis.__file__.startswith(here))
        self.assertTrue(generate_report.__file__.startswith(here))
        self.assertIn("phase-04-leading-indicators", indicator_core.__file__)

    def test_variant_is_frozen_copy(self):
        v = variant(zero_cut=2.0)
        self.assertEqual(v.zero_cut, 2.0)
        self.assertEqual(PRIMARY.zero_cut, 0.5)
        self.assertNotEqual(v.key(), PRIMARY.key())


if __name__ == "__main__":
    unittest.main()
