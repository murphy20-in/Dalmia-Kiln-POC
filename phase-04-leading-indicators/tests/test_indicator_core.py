"""Unit tests for the Phase 4 core (synthetic data only; no plant data needed).

Run:  ../../.venv/bin/python -m unittest discover -s ../tests -v      (from phase-04-leading-indicators/scripts)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from p4common import PRIMARY, P3_SCRIPTS, SCRIPTS, variant  # noqa: E402
import indicator_core as ic  # noqa: E402

CFG = PRIMARY


def grid(n: int, start: str = "2025-04-01 00:10") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="10min")


def synthetic_buckets(n: int = 3000, seed: int = 0) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    idx = grid(n)
    feed = pd.Series(410 + 10 * np.sin(np.arange(n) / 200) + rng.normal(0, 2, n), index=idx)
    b = pd.DataFrame({"Kiln-I!C": feed, "Kiln-I!P": 300 + 0.5 * (feed - 410) + rng.normal(0, 3, n),
                      "Kiln-III!D": 1000 + rng.normal(0, 20, n)}, index=idx)
    train = pd.Series(np.arange(n) < n // 2, index=idx)
    return b, feed, train


class Imports(unittest.TestCase):
    def test_phase3_modules_resolve_to_phase3_and_phase4_names_to_phase4(self):
        import kpi_core
        import sensitivity_analysis
        import generate_report
        self.assertEqual(Path(kpi_core.__file__).resolve().parent, P3_SCRIPTS.resolve())
        self.assertEqual(Path(sensitivity_analysis.__file__).resolve().parent, SCRIPTS.resolve())
        self.assertEqual(Path(generate_report.__file__).resolve().parent, SCRIPTS.resolve())
        self.assertTrue(sys.dont_write_bytecode)


class TrailingWindows(unittest.TestCase):
    def test_lagged_never_looks_forward(self):
        a = np.arange(5.0)
        np.testing.assert_array_equal(ic.lagged(a, 2), [np.nan, np.nan, 0, 1, 2])
        with self.assertRaises(ValueError):
            ic.lagged(a, -1)

    def test_trailing_median_right_closed_with_min_coverage(self):
        a = np.array([1, 2, np.nan, 4, 5, 6.0])
        m = ic.trailing_median(a, 3, 2)
        self.assertTrue(np.isnan(m[0]))                     # 1 valid < 2
        self.assertEqual(m[1], 1.5)                         # window (t-3, t] = {1, 2}
        self.assertEqual(m[3], 3.0)                         # {2, nan, 4}
        self.assertEqual(m[5], 5.0)                         # {4, 5, 6}

    def test_trailing_mean_matches_pandas(self):
        a = np.random.default_rng(1).normal(size=200)
        a[::7] = np.nan
        ref = pd.Series(a).rolling(12, min_periods=6).mean().to_numpy()
        np.testing.assert_allclose(ic.trailing_mean(a, 12, 6), ref, equal_nan=True)

    def test_trailing_mad_known_value(self):
        a = np.array([1, 2, 3, 4, 100.0])
        self.assertEqual(ic.trailing_mad(a, 5, 5)[-1], 1.0)   # median 3, |dev| = 2,1,0,1,97 -> 1

    def test_irregular_grid_rejected(self):
        idx = grid(5).delete(2)
        with self.assertRaises(ValueError):
            ic.check_grid(idx)


class Features(unittest.TestCase):
    def setUp(self):
        self.b, self.feed, self.train = synthetic_buckets()
        self.ref = ic.fit_feature_reference(self.b, self.feed, self.train, CFG)
        self.F = ic.compute_features(self.b, self.feed, self.ref, CFG)

    def test_features_are_causal_appending_future_changes_nothing(self):
        cut = 2000
        bt = self.b.iloc[:cut]
        Ft = ic.compute_features(bt, self.feed.iloc[:cut], self.ref, CFG)
        for f in self.F:
            pd.testing.assert_frame_equal(Ft[f], self.F[f].iloc[:cut])

    def test_perturbing_the_future_changes_nothing_in_the_past(self):
        b2 = self.b.copy()
        b2.iloc[2500:] += 1000.0
        F2 = ic.compute_features(b2, self.feed, self.ref, CFG)
        for f in self.F:
            pd.testing.assert_frame_equal(F2[f].iloc[:2500], self.F[f].iloc[:2500])

    def test_reference_is_frozen_after_discovery(self):
        b2 = self.b.copy()
        b2.loc[~self.train] *= 3.0
        ref2 = ic.fit_feature_reference(b2, self.feed, self.train, CFG)
        self.assertEqual(ref2["Kiln-III!D"]["level_ref"], self.ref["Kiln-III!D"]["level_ref"])

    def test_roc_sign_and_scale(self):
        b2 = self.b.copy()
        b2.iloc[2000:, 2] += 200.0                           # step up in Kiln-III!D
        F2 = ic.compute_features(b2, self.feed, self.ref, CFG)
        self.assertGreater(F2["ROC_1H"]["Kiln-III!D"].iloc[2004], 3.0)
        self.assertLess(abs(F2["ROC_1H"]["Kiln-III!D"].iloc[1990]), 3.0)

    def test_persistence_exact_on_constructed_pattern(self):
        b2 = self.b.copy()
        b2.iloc[2000:2018, 2] = 5000.0                      # 18 of 36 buckets far above the band
        F2 = ic.compute_features(b2, self.feed, self.ref, CFG)
        v = F2["PERSIST_HI_6H"]["Kiln-III!D"].iloc[2035]
        base = self.F["PERSIST_HI_6H"]["Kiln-III!D"].iloc[2035]
        self.assertGreaterEqual(v, 0.5)
        self.assertLessEqual(v - base, 18 / 36 + 1e-9)


class Targets(unittest.TestCase):
    def test_future_target_alignment_and_stop_inside_horizon(self):
        K = np.arange(20.0)
        run = np.ones(20, bool)
        y = ic.future_target(K, run, 6, 3)
        self.assertEqual(y[0], 5.0)                         # median(K[4..6]) = 5 minus K[0] = 0
        run[3] = False
        y2 = ic.future_target(K, run, 6, 3)
        self.assertTrue(np.isnan(y2[0]) and np.isnan(y2[2]))
        self.assertEqual(y2[3], 5.0)                        # (3, 9] clean
        self.assertTrue(np.isnan(y[-1]))                    # horizon beyond the data

    def test_target_uses_only_the_future_window(self):
        K = np.random.default_rng(0).normal(size=100)
        run = np.ones(100, bool)
        y = ic.future_target(K, run, 6, 3)
        K2 = K.copy()
        K2[:40] += 50                                       # change the past of t = 50 (not K(50) itself)
        y2 = ic.future_target(K2, run, 6, 3)
        self.assertEqual(y[50], y2[50])

    def test_short_horizon_smoothing_stays_in_the_future(self):
        K = np.arange(10.0)
        y = ic.future_target(K, np.ones(10, bool), 1, 3)
        self.assertEqual(y[0], 1.0)                         # H = 10 min -> K(t+1) - K(t)

    def test_controls_are_causal(self):
        rng = np.random.default_rng(3)
        K, D = rng.uniform(0, 60, 400), rng.uniform(0, 2, 400)
        Z = ic.controls(K, D, 6, 0.4, 1.6)
        K2, D2 = K.copy(), D.copy()
        K2[300:], D2[300:] = np.nan, np.nan
        Z2 = ic.controls(K2, D2, 6, 0.4, 1.6)
        np.testing.assert_array_equal(Z[:300], Z2[:300])


class Statistics(unittest.TestCase):
    def test_partial_rho_removes_dependence_through_the_control(self):
        rng = np.random.default_rng(0)
        n = 5000
        k = rng.normal(size=n)
        x = k + rng.normal(scale=0.5, size=n)
        y = k + rng.normal(scale=0.5, size=n)
        rows = np.ones(n, bool)
        a = ic.assoc(x, y, k[:, None], rows, np.zeros(n, int), None, 50)
        self.assertGreater(a["rho_raw"], 0.6)
        self.assertLess(abs(a["rho_p"]), 0.05)
        y2 = k + x + rng.normal(scale=0.5, size=n)          # genuine extra information in x
        self.assertGreater(ic.assoc(x, y2, k[:, None], rows, np.zeros(n, int), None, 50)["rho_p"], 0.3)

    def test_neff_iid_and_ar1(self):
        rng = np.random.default_rng(1)
        n = 20000
        e1, e2 = rng.normal(size=n), rng.normal(size=n)
        self.assertGreater(ic.n_effective(e1, e2, n, 100) / n, 0.9)
        phi = 0.9
        x, y = np.empty(n), np.empty(n)
        x[0], y[0] = e1[0], e2[0]
        for i in range(1, n):
            x[i], y[i] = phi * x[i - 1] + e1[i], phi * y[i - 1] + e2[i]
        expect = (1 - phi ** 2) / (1 + phi ** 2)
        self.assertAlmostEqual(ic.n_effective(x, y, n, 400) / n, expect, delta=0.04)

    def test_sufficient_statistic_bootstrap_equals_naive(self):
        rng = np.random.default_rng(2)
        blocks = np.repeat(np.arange(20), 50)
        ex, ey = rng.normal(size=1000), rng.normal(size=1000)
        W = ic.boot_weights(20, 200, 5)
        lo, hi = ic.boot_corr_ci(ex, ey, blocks, W)
        rs = []
        for w in W:
            idx = np.concatenate([np.flatnonzero(blocks == b) for b in range(20) for _ in range(int(w[b]))])
            rs.append(np.corrcoef(ex[idx], ey[idx])[0, 1])
        self.assertAlmostEqual(lo, np.quantile(rs, 0.025), places=10)
        self.assertAlmostEqual(hi, np.quantile(rs, 0.975), places=10)

    def test_bh_known_example(self):
        p = np.array([0.01, 0.04, 0.03, 0.2])
        np.testing.assert_allclose(ic.bh(p), [0.04, 0.0533333, 0.0533333, 0.2], rtol=1e-5)

    def test_planted_lead_and_placebo(self):
        rng = np.random.default_rng(4)
        n = 6000
        K = np.cumsum(rng.normal(size=n)) * 0.5
        run = np.ones(n, bool)
        x = np.r_[K[12:], np.full(12, np.nan)] + rng.normal(scale=1.0, size=n)
        prof = {h: ic.assoc(x, ic.future_target(K, run, h, 3), K[:, None], run, np.zeros(n, int), None, 200)["rho_p"]
                for h in (1, 3, 6, 12, 18, 36)}
        self.assertEqual(max(prof, key=prof.get), 12)
        xp = np.roll(x, 1008)
        a = ic.assoc(xp, ic.future_target(K, run, 12, 3), K[:, None], run, np.zeros(n, int), None, 200)
        self.assertLess(abs(a["rho_p"]), 0.1)


class Episodes(unittest.TestCase):
    def test_band_onset_rules(self):
        cfg = variant(ep_min_buckets=3, ep_clear_h=1)       # 6 clear buckets
        K = np.full(40, 10.0)
        code = np.zeros(40, int)
        code[10:14] = 1                                     # run of 4 after 10 clear -> onset at 10
        code[16:17] = 1                                     # too short
        code[30:34] = 1                                     # after 13 clear -> onset at 30
        np.testing.assert_array_equal(ic.band_onsets(K, code, cfg), [10, 30])
        K2 = K.copy()
        K2[4:10] = np.nan                                   # prior window < 50 % scored
        self.assertNotIn(10, ic.band_onsets(K2, code, cfg).tolist())

    def test_first_lead_and_not_evaluable(self):
        x = np.zeros(200)
        x[150:160] = 5.0
        self.assertEqual(ic.first_lead(x, 1, 1.0, 170, CFG), 200.0)   # crossing at 150, T = 170 -> 20 buckets
        xn = np.full(200, np.nan)
        self.assertEqual(ic.first_lead(xn, 1, 1.0, 170, CFG), -1.0)

    def test_alarm_onsets_causal_persistence_and_refractory(self):
        x = np.zeros(100)
        x[10:15] = 2.0                                      # alarm at 12 (3rd bucket beyond)
        x[17:20] = 2.0                                      # < 2 h after the previous run -> suppressed
        x[50:53] = 2.0                                      # alarm at 52
        on = ic.alarm_onsets(x, 1, 1.0, CFG)
        np.testing.assert_array_equal(on, [12, 52])
        on2 = ic.alarm_onsets(np.r_[x[:30], np.full(70, np.nan)], 1, 1.0, CFG)
        np.testing.assert_array_equal(on2, [12])


class CandidateRules(unittest.TestCase):
    def test_family_and_manipulated_rules(self):
        import build_indicator_dataset as bid
        self.assertEqual(bid.process_family("DRAFT / ID FAN", "mmWC", "I/L Draft", "Kiln-I"), "DRAFT_PRESSURE")
        self.assertEqual(bid.process_family("OTHER", "Amps", "Current", "CBS-I"), "BYPASS_AUXILIARY")
        self.assertEqual(bid.process_family("KILN", "KW", "KW", "Kiln-I"), "KILN_DRIVE")
        self.assertTrue(bid.manipulated("Kiln-III!C", "Cooler Fan 1 | Speed", "RPM"))
        self.assertTrue(bid.manipulated("Kiln-I!I", "PC", "TPH"))
        self.assertFalse(bid.manipulated("Kiln-I!P", "KW", "KW"))

    def test_confidence_caps(self):
        import score_indicators as si
        from types import SimpleNamespace as NS
        base = dict(status="CANDIDATE", all_gates_pass=True, tier="KPI_INPUT", flags="", disc_q_bh=0.01,
                    repl_months_sig_same_sign=2, sp_heat_fg_consistent=True, state_robust=True, lift_repl=0.3,
                    n_episodes_repl=15, shift_null_p_repl=si.P_FLOOR)
        self.assertEqual(si.confidence(NS(**base)), "LOW")
        self.assertEqual(si.confidence(NS(**{**base, "tier": "KPI_PROXY"})), "LOW")
        self.assertEqual(si.confidence(NS(**{**base, "tier": "EXTERNAL"})), "HIGH")
        self.assertEqual(si.confidence(NS(**{**base, "tier": "EXTERNAL", "flags": "MANIPULATED_VARIABLE"})), "MEDIUM")
        self.assertEqual(si.confidence(NS(**{**base, "tier": "EXTERNAL", "shift_null_p_repl": 0.2})), "LOW")
        self.assertEqual(si.confidence(NS(**{**base, "all_gates_pass": False})), "INSUFFICIENT")
        self.assertEqual(si.confidence(NS(**{**base, "status": "CONTEXT_ONLY"})), "NOT_APPLICABLE")

    def test_direction_wording_follows_feature_type(self):
        import score_indicators as si
        self.assertEqual(si.direction_text("ROC_1H", -1), "FALLING_TREND_PRECEDES_KPI_INCREASE")
        self.assertEqual(si.direction_text("LEVEL_1H", 1), "HIGHER_LEVEL_PRECEDES_KPI_INCREASE")
        self.assertEqual(si.direction_text("VOL_2H", 1), "HIGHER_VARIABILITY_PRECEDES_KPI_INCREASE")


class MoreTargetsAndEpisodes(unittest.TestCase):
    def test_band_target_future_only_and_prior_clear(self):
        code = np.zeros(40, int)
        code[20:30] = 1
        K = np.ones(40)
        y = ic.future_band_target(code, K, np.ones(40, bool), 6)
        self.assertEqual(y[16], 1.0)                        # (16, 22]: buckets 20-22 in band = 3 of 6 >= 0.5
        self.assertTrue(np.isnan(y[25]))                    # prior hour not clear
        self.assertEqual(y[5], 0.0)

    def test_future_max_rise_requires_running_and_coverage(self):
        K = np.arange(30.0)
        run = np.ones(30, bool)
        self.assertEqual(ic.future_max_rise(K, run, 3)[0], 3.0)
        run[2] = False
        self.assertTrue(np.isnan(ic.future_max_rise(K, run, 3)[0]))
        K2 = K.copy()
        K2[1:3] = np.nan
        self.assertTrue(np.isnan(ic.future_max_rise(K2, np.ones(30, bool), 3)[0]))   # 1 of 3 < 2/3

    def test_rise_onsets_and_rise_start(self):
        K = np.r_[np.zeros(50), np.linspace(0, 40, 20), np.full(30, 40.0)]
        on = ic.rise_onsets(K, 30.0, CFG)
        self.assertEqual(len(on), 1)
        self.assertEqual(ic.rise_start(K, int(on[0]), CFG) <= 50, True)

    def test_controls_exclude_every_raw_onset(self):
        K = np.random.default_rng(0).uniform(0, 10, 2000)
        win = np.full(2000, "JUN", dtype=object)
        ctrl = ic.pick_controls(np.array([500]), K, win, CFG, 1, exclude=np.array([1500]))
        for _, c in ctrl:
            self.assertTrue(abs(c - 500) > 144 and abs(c - 1500) > 144)

    def test_first_lead_ignores_condition_already_active(self):
        x = np.full(200, 5.0)                               # beyond threshold for the whole window
        self.assertTrue(np.isnan(ic.first_lead(x, 1, 1.0, 170, CFG)))


class Context(unittest.TestCase):
    def test_unknown_window_raises_and_filters(self):
        import analysis_context as ac
        idx = grid(300, "2025-06-01 00:10")
        g = pd.DataFrame({"K": 1.0, "K_F": 1.0, "K_G": 1.0, "K_ALT": 1.0, "band_code": 0, "D": 0.5,
                          "bucket_state": "RUNNING", "data_quality": "GOOD"}, index=idx)
        g.loc[idx[100:103], "bucket_state"] = "TRANSITION"
        g.loc[idx[200:203], "bucket_state"] = "STOPPED"
        ctx = ac.build_context(variant(exclude_post_restart_h=1, exclude_pre_stop_h=1), g, {"m": 0.4, "q_anchor": 1.6})
        with self.assertRaises(ValueError):
            ac.window_rows(ctx, "SEPTEMBER", 6)
        self.assertFalse(ctx.filt[100:108].any())           # within 1 h after the transition
        self.assertFalse(ctx.filt[194:200].any())           # within 1 h before the stop
        self.assertTrue(ctx.filt[150])


if __name__ == "__main__":
    unittest.main()
