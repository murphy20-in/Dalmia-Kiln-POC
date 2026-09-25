"""Unit tests for the Phase 3 KPI core (synthetic data only; no plant data needed).

Run:  ../../.venv/bin/python -m unittest discover -s ../tests -v      (from phase-03-efficiency-kpi/scripts)
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from p3common import variant  # noqa: E402
import kpi_core as kc  # noqa: E402

TAGS = ["Kiln-I!F", "Kiln-I!G", "Kiln-I!X", "Kiln-I!AF", "Kiln-I!S", "STD60:Kiln-I!AF"]
CFG = variant(name="TEST", train_start="2025-04-01 00:00", train_end="2025-04-08 23:59", load_bin_min_n=50,
              load_bins=5, bootstrap_reps=10)


def synthetic(days: int = 16, stop: tuple | None = ("2025-04-12 06:00", "2025-04-12 09:00"), seed: int = 1):
    """Minute data for the KPI tags. Feed drives draft; noise is Gaussian (no flatlines)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-04-01 00:00", periods=days * 1440, freq="min")
    n = len(idx)
    feed = 410 + 20 * np.sin(np.arange(n) / 2000) + rng.normal(0, 3, n)
    v = pd.DataFrame(index=idx)
    v["Kiln-I!C"] = feed
    v["Kiln-I!F"] = 830 + rng.normal(0, 20, n)
    v["Kiln-I!G"] = 770 + rng.normal(0, 20, n)
    v["Kiln-I!X"] = 6 + rng.normal(0, 1, n)
    v["Kiln-I!AF"] = 1110 + rng.normal(0, 15, n)
    v["Kiln-I!S"] = -742 - 3.0 * (feed - 410) + rng.normal(0, 10, n)
    v["Kiln-IA!C"] = 1020 + rng.normal(0, 15, n)
    st = pd.DataFrame({"state_basic": "RUNNING_PROXY", "operating_state": "RUNNING_PROXY"}, index=idx)
    if stop:
        s0, s1 = pd.Timestamp(stop[0]), pd.Timestamp(stop[1])
        m = (idx >= s0) & (idx <= s1)
        st.loc[m, ["state_basic", "operating_state"]] = ["STOPPED_PROXY", "STOPPED_PROXY"]
        v.loc[m, "Kiln-I!C"] = 0.0
        ramp = (idx > s1) & (idx <= s1 + pd.Timedelta("90min"))    # feed recovers over 90 min after restart
        v.loc[ramp, "Kiln-I!C"] = np.linspace(100, 400, ramp.sum())
        settle = (idx > s1 + pd.Timedelta("90min")) & (idx <= s1 + pd.Timedelta("12h"))  # settles above the pre-stop P25
        v.loc[settle, "Kiln-I!C"] = 445 + rng.normal(0, 3, settle.sum())
    return v, st


class RobustHelpers(unittest.TestCase):
    def test_robust_scale_matches_sigma_and_floors(self):
        x = np.random.default_rng(0).normal(0, 2.0, 50_000)
        self.assertAlmostEqual(kc.robust_scale(x, 0, 0), 2.0, delta=0.05)
        self.assertEqual(kc.robust_scale(np.ones(100) * 5, 0.0, 0.01), 0.05)      # 1 % of |median| floor
        self.assertEqual(kc.robust_scale(np.ones(100), resolution=0.5), 0.5)       # resolution floor

    def test_tag_score_direction_and_cap(self):
        z = np.array([-3.0, 0.0, 2.0])
        np.testing.assert_array_equal(kc.tag_score(z, "up"), [0.0, 0.0, 2.0])
        np.testing.assert_array_equal(kc.tag_score(z, "both"), [3.0, 0.0, 2.0])


class Masking(unittest.TestCase):
    def test_causal_flatline_from_nth_identical_nonzero_sample(self):
        idx = pd.date_range("2025-04-01", periods=200, freq="min")
        v = pd.DataFrame({"Kiln-I!F": np.r_[np.arange(10.0), np.full(80, 7.0), np.arange(110.0)],
                          "Kiln-I!G": np.r_[np.zeros(100), np.arange(100.0)]}, index=idx)
        out, _ = kc.prepare_minutes(v, CFG)
        masked = out["Kiln-I!F"].isna()
        self.assertEqual(int(masked.sum()), 80 - 60 + 1)   # 80-sample run of 7.0: masked from its 60th sample
        self.assertFalse(masked.iloc[:10 + 58].any())           # nothing before the 60th identical sample
        self.assertFalse(out["Kiln-I!G"].isna().any())          # runs of zeros are not flatlines (Phase 1 rule)

    def test_timestamp_gap_restarts_the_run(self):
        idx = pd.date_range("2025-04-01", periods=50, freq="min").append(pd.date_range("2025-04-01 02:00", periods=50, freq="min"))
        v = pd.DataFrame({"Kiln-I!F": np.full(100, 3.0)}, index=idx)
        self.assertEqual(int(kc.run_length(v).max()), 50)

    def test_causal_frozen_row_masks_whole_dataset(self):
        idx = pd.date_range("2025-04-01", periods=40, freq="min")
        rng = np.random.default_rng(3)
        data = {f"Kiln-II!T{i}": np.r_[rng.normal(10, 1, 20), np.full(20, 5.0 + i)] for i in range(22)}
        data["Kiln-II!MOVING"] = rng.normal(0, 1, 40)
        out, flags = kc.prepare_minutes(pd.DataFrame(data, index=idx), CFG)
        self.assertEqual(int(flags.causal_frozen.sum()), 20 - CFG.frozen_run_n + 1)  # from the 10th identical sample on
        self.assertTrue(out.loc[flags.causal_frozen, "Kiln-II!MOVING"].isna().all())
        self.assertFalse(flags.causal_frozen.iloc[:28].any())


class StateAndBuckets(unittest.TestCase):
    def test_bucket_is_right_closed_median_with_min_valid(self):
        v, st = synthetic(days=1, stop=None)
        v.iloc[5:8, v.columns.get_loc("Kiln-I!X")] = np.nan          # bucket 00:10 keeps 7 valid minutes -> NaN
        b = kc.minutes_to_buckets(v, st, CFG)
        t = pd.Timestamp("2025-04-01 00:20")
        exp = v.loc[(v.index > t - pd.Timedelta("10min")) & (v.index <= t), "Kiln-I!F"].median()
        self.assertAlmostEqual(b["values"].loc[t, "Kiln-I!F"], exp)
        self.assertTrue(np.isnan(b["values"].loc[pd.Timestamp("2025-04-01 00:10"), "Kiln-I!X"]))

    def test_stopped_minutes_are_stopped_buckets(self):
        v, st = synthetic()
        b = kc.minutes_to_buckets(v, st, CFG)
        self.assertEqual(b["meta"].loc["2025-04-12 07:00", "bucket_state"], "STOPPED")

    def test_causal_ramp_transition_then_running(self):
        v, st = synthetic()
        cs = kc.causal_state(st, v, CFG).state
        s1 = pd.Timestamp("2025-04-12 09:00")
        self.assertEqual(cs[s1 + pd.Timedelta("1min")], "TRANSITION")
        # the P25 pre-stop reference (~400) is regained ~90 min after restart; +60 min sustained -> RUNNING
        first_run = cs[(cs.index > s1) & cs.eq("RUNNING")].index[0]
        self.assertGreater(first_run, s1 + pd.Timedelta("100min"))
        self.assertLess(first_run, s1 + pd.Timedelta("170min"))
        # decided causally: the same labels without the data after first_run
        cs2 = kc.causal_state(st.loc[:first_run], v.loc[:first_run], CFG).state
        pd.testing.assert_series_equal(cs.loc[:first_run], cs2)


    def test_ramp_is_censored_after_48h(self):
        v, st = synthetic(days=16)
        s1 = pd.Timestamp("2025-04-12 09:00")
        v.loc[v.index > s1 + pd.Timedelta("90min"), "Kiln-I!C"] = 300.0 + np.random.default_rng(5).normal(0, 3, int((v.index > s1 + pd.Timedelta("90min")).sum()))
        cs = kc.causal_state(st, v, CFG).state
        self.assertEqual(cs[s1 + pd.Timedelta("47h")], "TRANSITION")    # never regains the pre-stop level ...
        self.assertEqual(cs[s1 + pd.Timedelta("48h") + pd.Timedelta("2min")], "RUNNING")  # ... censored at 48 h

    def test_unknown_gap_triggers_restart_and_contiguity_is_by_clock(self):
        v, st = synthetic(days=4, stop=None)
        g0, g1 = pd.Timestamp("2025-04-03 00:00"), pd.Timestamp("2025-04-03 02:00")
        st.loc[(st.index >= g0) & (st.index < g1), "state_basic"] = "UNKNOWN"
        cs = kc.causal_state(st, v, CFG).state
        self.assertEqual(cs[g1], "TRANSITION")                            # > 60 min without RUNNING -> ramp
        self.assertEqual(cs[g1 - pd.Timedelta("1min")], "UNKNOWN")
        # alternating RUNNING / UNKNOWN minutes never count as 60 consecutive clock minutes
        st2 = st.copy()
        alt = (st2.index >= g1) & (st2.index < g1 + pd.Timedelta("3h")) & (np.arange(len(st2)) % 2 == 1)
        st2.loc[alt, "state_basic"] = "UNKNOWN"
        cs2 = kc.causal_state(st2, v, CFG).state
        self.assertTrue(cs2[(cs2.index > g1) & (cs2.index < g1 + pd.Timedelta("3h")) & ~alt].eq("TRANSITION").all())

    def test_conflict_is_causal_from_feed_and_speed(self):
        v, st = synthetic(days=2, stop=None)
        v["Kiln-I!O"] = 5.2
        t0 = pd.Timestamp("2025-04-01 12:00")
        v.loc[t0, "Kiln-I!C"] = 0.0
        cs = kc.causal_state(st, v, CFG).state
        self.assertEqual(cs[t0], "CONFLICT")
        self.assertEqual(cs[t0 + pd.Timedelta("1min")], "RUNNING")
        self.assertEqual(kc.causal_state(st.loc[:t0], v.loc[:t0], CFG).state[t0], "CONFLICT")



class Scoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v, cls.st = synthetic()
        cls.b, cls.ref, cls.s = kc.run_kpi(cls.v, cls.st, CFG, None, TAGS)
        cls.k = cls.s["kpi"]

    def test_persistence_trailing_median_ignores_spike_and_needs_coverage(self):
        idx = pd.date_range("2025-04-01", periods=72, freq="10min")
        D = pd.Series(1.0, index=idx)
        D.iloc[40:42] = 100.0
        P = kc.persistence(D, CFG).P
        self.assertTrue((P.iloc[36:] == 1.0).all())
        D2 = D.copy()
        D2.iloc[20:60] = np.nan
        P2 = kc.persistence(D2, CFG)
        self.assertTrue(P2.P[P2.coverage < 0.5].isna().all())

    def test_kpi_scaling(self):
        m, q = 0.4, 1.6
        self.assertAlmostEqual(kc.to_kpi([m], m, q)[0], 0.0)
        self.assertAlmostEqual(kc.to_kpi([q], m, q)[0], 50.0)
        k = kc.to_kpi(np.linspace(-1, 50, 1000), m, q)
        self.assertTrue(np.all(np.diff(k) >= 0) and k.min() == 0 and k.max() < 100)

    def test_aggregation_efficiency_anchored(self):
        S = pd.DataFrame({"EFFICIENCY": [2.0, np.nan, 1.0], "COMBUSTION": [1.0, 1.0, np.nan],
                          "THERMAL": [3.0, 1.0, np.nan], "DRAFT_PRESSURE": [np.nan, 1.0, 5.0], "STABILITY": [0.0, 1.0, np.nan]})
        D = kc.aggregate(S, pd.DataFrame(index=S.index), {}, CFG)
        self.assertAlmostEqual(D.iloc[0], 0.5 * 2.0 + 0.5 * (4.0 / 3))
        self.assertTrue(np.isnan(D.iloc[1]))     # efficiency required
        self.assertTrue(np.isnan(D.iloc[2]))     # only 1 supporting dimension < min_support_dims

    def test_component_scores_and_normalisation(self):
        z = self.s["tags"]["z"]
        tm = kc.training_mask(self.b["meta"], CFG)
        self.assertAlmostEqual(float(np.median(z.loc[tm, "Kiln-I!F"].dropna())), 0.0, delta=0.05)
        # load adjustment removes the feed-driven part of the draft
        self.assertLess(abs(z.loc[tm, "Kiln-I!S"].corr(self.b["values"].loc[tm, "Kiln-I!C"])), 0.2)
        self.assertTrue((self.k.efficiency_component.dropna() >= 0).all())

    def test_training_window_separation(self):
        v2 = self.v.copy()
        after = v2.index > pd.Timestamp(CFG.train_end) + pd.Timedelta("1D")
        v2.loc[after, "Kiln-I!F"] += 500.0                        # wild change after training
        _, ref2, s2 = kc.run_kpi(v2, self.st, CFG, None, TAGS)
        self.assertEqual(json.dumps(ref2, sort_keys=True, default=float), json.dumps(self.ref, sort_keys=True, default=float))
        self.assertTrue(self.k.loc[: CFG.train_end, "efficiency_deterioration_kpi"].isna().all())
        self.assertGreater(s2["kpi"].efficiency_deterioration_kpi.loc["2025-04-14":].median(),
                           self.k.efficiency_deterioration_kpi.loc["2025-04-14":].median())

    def test_stopped_and_transition_buckets_not_scored(self):
        for stt in ("STOPPED", "TRANSITION"):
            sub = self.k[self.k.bucket_state == stt]
            self.assertGreater(len(sub), 0)
            self.assertTrue(sub.efficiency_deterioration_kpi.isna().all())
            self.assertTrue(sub.kpi_reference_state.str.startswith("NOT_SCORED").all())

    def test_missing_data(self):
        v2 = self.v.copy()
        v2.loc["2025-04-13":, "Kiln-I!X"] = np.nan                # one supporting tag lost: still scored
        v2.loc["2025-04-15":, ["Kiln-I!F", "Kiln-I!G"]] = np.nan  # efficiency lost: not scored
        k2 = kc.run_kpi(v2, self.st, CFG, self.ref)[2]["kpi"]
        self.assertTrue(k2.loc["2025-04-13 12:00":"2025-04-14 23:50", "efficiency_deterioration_kpi"].notna().any())
        self.assertTrue(k2.loc["2025-04-15 01:00":, "efficiency_deterioration_kpi"].isna().all())
        self.assertTrue((k2.loc["2025-04-15 01:00":, "kpi_reference_state"] == "NO_EFFICIENCY_DATA").all())

    def test_band_is_empty_when_not_reported(self):
        blank = self.k.efficiency_deterioration_kpi.isna() & self.k.kpi_in_sample_reference.isna()
        self.assertTrue(self.k.loc[blank, "kpi_band"].eq("").all())
        self.assertTrue((self.k.loc[blank, "kpi_band_code"] == -1).all())
        self.assertTrue(self.k.persistent_deviation_score[self.k.raw_deviation_score.isna()].isna().all())

    def test_band_mode_and_inverse_redundancy(self):
        cfg = variant(name="TB", train_start=CFG.train_start, train_end=CFG.train_end, load_bin_min_n=50, load_bins=5,
                      load_mode="band", aggregation="inverse_redundancy")
        _, ref, s = kc.run_kpi(self.v, self.st, cfg, None, TAGS)
        self.assertEqual(len(ref["bands"]["means"]), cfg.n_bands)
        self.assertTrue(np.all(np.diff(ref["bands"]["means"]) > 0))
        w = pd.Series(ref["dim_weights"])
        self.assertTrue(((w > 0) & (w <= 1)).all())
        self.assertTrue(s["kpi"].efficiency_deterioration_kpi.notna().any())

    def test_holdout_calibration_uses_disjoint_windows(self):
        cfg = variant(name="HO", train_start=CFG.train_start, train_end=CFG.train_end, load_bin_min_n=50, load_bins=5,
                      fit_end="2025-04-06 23:59")
        b = kc.minutes_to_buckets(self.v, self.st, cfg)
        fit, cal = kc.fit_masks(b["meta"], cfg)
        self.assertFalse((fit & cal).any())
        self.assertTrue(fit.any() and cal.any())
        self.assertLessEqual(fit[fit].index.max(), pd.Timestamp(cfg.fit_end) + pd.Timedelta("1min"))

    def test_window_attribution_top_tag_belongs_to_top_dimension(self):
        from p3common import spec_by_tag
        sp = spec_by_tag()
        r = self.k.dropna(subset=["top_dimension", "top_tag"])
        self.assertGreater(len(r), 0)
        self.assertTrue(all(sp[t].dimension == d for t, d in zip(r.top_tag, r.top_dimension)))

    def test_future_data_cannot_affect_past_kpi(self):
        for T in [pd.Timestamp("2025-04-11 13:07"), pd.Timestamp("2025-04-12 09:30"), pd.Timestamp("2025-04-14 00:00")]:
            a = kc.run_kpi(self.v.loc[:T], self.st.loc[:T], CFG, self.ref)[2]["kpi"]
            b = self.k.loc[: T]
            a = a.loc[a.index <= T]
            for c in ["bucket_state", "raw_deviation_score", "persistent_deviation_score", "efficiency_deterioration_kpi",
                      "kpi_reference_state"]:
                pd.testing.assert_series_equal(a[c], b.loc[a.index, c], check_names=False, obj=f"{c} @ {T}")


if __name__ == "__main__":
    unittest.main()
