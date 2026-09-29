"""Unit tests for the Phase 6 pure functions (synthetic data only; no plant data needed).

Run:  ../../.venv/bin/python -B -m unittest discover -s ../tests -v      (from phase-06-abnormal-events/scripts)
The synthetic plant-event rows below exist only inside this test to exercise the matcher; the pipeline never creates any.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import abn_core as ac  # noqa: E402
from abn_core import FAMILIES, PRIMARY  # noqa: E402

EVENT_COLS = ["kind", "event_time", "end", "ramp_minutes", "stop_minutes_before", "event_id", "status"]


def synthetic(n: int = 600, seed: int = 1) -> dict:
    """A regular 10-min grid with two injected KPI excursions and a stop in between."""
    rng = np.random.default_rng(seed)
    ix = pd.date_range("2025-06-01 00:10", periods=n, freq="10min")
    K = np.clip(rng.normal(20, 5, n), 0, None)
    K[100:130] = 55
    K[134:150] = 50          # 30-min gap -> merged with the run above
    K[300:320] = 70
    D = np.where(K > 40, 2.5, 0.4) + rng.normal(0, 0.05, n)
    state = np.array(["RUNNING"] * n, dtype=object)
    state[200:210] = "STOPPED"
    g = pd.DataFrame(index=ix)
    g["K"], g["D"], g["state"] = K, D, state
    for c in ("K_F", "K_G", "K_ALT", "MAHA"):
        g[c] = K
    g["in_sample"] = False
    for d in FAMILIES:
        g[f"S_{d}"] = np.where(K > 40, 3.0, 0.2)
    g["dq"], g["tag_cov"], g["kpi_conf"] = "GOOD", 1.0, "HIGH"
    g["near_bnd"], g["oor"] = False, False
    g["feed"], g["speed"], g["clinker"] = 400.0, 5.0, 230.0
    g["coal_kiln"], g["coal_pc"], g["afr"], g["p4"], g["masked_share"] = 5.0, 10.0, 30.0, 0.0, 0.0
    ref = {"thr": 41.8, "hi": 60.5, "family_p90": {d: 1.0 for d in FAMILIES}, "D_q90": 1.5, "D_median": 0.4,
           "D_mad": 0.2, "cusum_k": 1.0, "cusum_h": 5.0, "p4_threshold": 0.8, "p4_indicator": "X",
           "feed_d120m_p50": 0.0, "feed_d120m_p75": 3.0, "feed_d120m_p90": 14.0, "feed_d60m_p50": 0.0,
           "feed_d60m_p75": 1.5, "feed_d60m_p90": 8.0, "coal_total_d60m_p90": 2.0,
           "load": {c: {"median": m, "mad": 10.0} for c, m in (("feed", 400.0), ("speed", 5.0), ("clinker", 230.0))}}
    return {"grid": g, "events": pd.DataFrame(columns=EVENT_COLS).astype({"event_time": "datetime64[ns]"}),
            "dq_windows": pd.DataFrame(columns=["kind", "dataset", "start", "end"]).astype(
                {"start": "datetime64[ns]", "end": "datetime64[ns]"}), "ref": ref}


class RunsAndMerging(unittest.TestCase):
    def test_runs(self):
        self.assertEqual(ac.runs_of(np.array([0, 1, 1, 0, 1, 0, 0, 1], bool)), [(1, 2), (4, 4), (7, 7)])
        self.assertEqual(ac.runs_of(np.zeros(3, bool)), [])

    def test_merge_rules(self):
        runs = [(0, 2), (5, 6), (20, 21)]
        run = np.ones(30, bool)
        blk = np.zeros(30, bool)
        self.assertEqual(ac.merge_runs(runs, run, blk, 6), [(0, 6, 2), (20, 21, 1)])
        run2 = run.copy()
        run2[3] = False                      # a non-RUNNING bucket in the gap breaks the merge
        self.assertEqual(ac.merge_runs(runs, run2, blk, 6), [(0, 2, 1), (5, 6, 1), (20, 21, 1)])
        blk2 = blk.copy()
        blk2[4] = True                       # a Phase 1 long gap / frozen window in the gap breaks the merge
        self.assertEqual(ac.merge_runs(runs, run, blk2, 6)[0], (0, 2, 1))
        self.assertEqual(ac.merge_runs(runs, run, blk, 1), [(0, 2, 1), (5, 6, 1), (20, 21, 1)])


class Cusum(unittest.TestCase):
    def test_cusum_reset_nan_and_onset(self):
        x = np.array([0, 0, 3, 3, np.nan, 3, 0, 0], float)
        S = ac.cusum(x, np.array([0, 0, 0, 0, 0, 0, 1, 0], bool), 1.0)
        self.assertEqual(list(S), [0, 0, 2, 4, 4, 6, 0, 0])
        self.assertEqual(ac.onset_from_cusum(S, 5, 5, 5.0), (2, True, False))
        self.assertEqual(ac.onset_from_cusum(np.array([1.0, 2, 3, 4]), 3, 2, 10.0), (1, False, True))


class Pipeline(unittest.TestCase):
    def test_episodes_merge_and_stop_break(self):
        ep = ac.run_pipeline(synthetic())
        self.assertEqual(list(zip(ep.pos_start, ep.pos_end)), [(100, 149), (300, 319)])
        self.assertEqual(int(ep.n_runs_merged.iloc[0]), 2)
        self.assertTrue((ep.family_count == 5).all())
        self.assertTrue((ep.classification == ac.FINAL_LABEL).all())
        self.assertTrue((ep.onset_time <= ep.detection_time).all())

    def test_truncation_invariance(self):
        inp = synthetic()
        full = ac.run_pipeline(inp)
        for cut in (inp["grid"].index[110], inp["grid"].index[160], inp["grid"].index[310]):
            ti = ac.truncate(inp, cut)
            tr = ac.run_pipeline(ti).reset_index(drop=True)
            known = full[full.detection_time <= cut].reset_index(drop=True)
            self.assertEqual(len(tr), len(known))
            for c in ("start_time", "detection_time", "onset_time", "families_at_detection", "change_point_supported"):
                self.assertTrue((tr[c].to_numpy() == known[c].to_numpy()).all(), c)
            self.assertTrue((tr.end_time <= known.end_time).all())
            settled = known.end_time + pd.Timedelta(minutes=130) <= cut
            for c in ("primary_context", "classification", "in_final_set", "severity_class"):
                self.assertTrue((tr.loc[settled, c].to_numpy() == known.loc[settled, c].to_numpy()).all(), c)
            pre_t = ac.pre_event(ti["grid"], tr, inp["ref"], inp["events"])
            pre_f = ac.pre_event(inp["grid"], known, inp["ref"], inp["events"])
            pd.testing.assert_frame_equal(pre_t.reset_index(drop=True), pre_f.reset_index(drop=True))

    def test_short_transient_kept_not_deleted(self):
        inp = synthetic()
        inp["grid"].iloc[450:453, inp["grid"].columns.get_loc("K")] = 60
        ep = ac.run_pipeline(inp)
        short = ep[ep.pos_start == 450]
        self.assertEqual(short.primary_context.iloc[0], "SHORT_TRANSIENT")
        self.assertFalse(short.in_final_set.iloc[0])


class Classification(unittest.TestCase):
    def base(self, **kw):
        d = {"data_quality_context": "DQ_CLEAN", "number_of_valid_families": 5, "startup_overlap": False,
             "restart_overlap": False, "shutdown_overlap": False, "duration_minutes": 120, "load_change_overlap": False,
             "family_count": 1, "afr_down_near_onset": False, "control_action_overlap": False,
             "multivariate_supported": False, "load_context": "UNCERTAIN", "reference_state": "OUT_OF_SAMPLE"}
        d.update(kw)
        return pd.DataFrame([d])

    def test_precedence(self):
        e = ac.classify(self.base(data_quality_context="DATA_QUALITY_ARTIFACT", restart_overlap=True,
                                  duration_minutes=10), PRIMARY)
        self.assertEqual(e.primary_context.iloc[0], "DATA_QUALITY_ARTIFACT")
        self.assertIn("RESTART", e.secondary_context.iloc[0])
        e = ac.classify(self.base(restart_overlap=True, load_change_overlap=True), PRIMARY)
        self.assertEqual(e.primary_context.iloc[0], "RESTART")
        e = ac.classify(self.base(load_change_overlap=True, family_count=3), PRIMARY)
        self.assertEqual(e.primary_context.iloc[0], "NONE")          # load-associated but multi-family -> abnormal
        self.assertTrue(e.in_final_set.iloc[0])
        e = ac.classify(self.base(afr_down_near_onset=True), PRIMARY)
        self.assertEqual(e.classification.iloc[0], "AFR_TRANSITION")
        e = ac.classify(self.base(family_count=0), PRIMARY)
        self.assertEqual(e.classification.iloc[0], "UNCONFIRMED_KPI_ELEVATION")

    def test_severity_classes(self):
        ep = pd.DataFrame({"peak_kpi": [65, 65, 45], "duration_minutes": [400, 100, 100], "kpi_integral": [100, 5, 1],
                           "family_count": [5, 2, 0]})
        s = ac.severity(ep, {"thr": 40.0, "hi": 60.0}, PRIMARY)
        self.assertEqual(list(s.severity_class), ["HIGH", "MODERATE", "LOW"])
        self.assertTrue(((s.severity_score >= 0) & (s.severity_score <= 1)).all())

    def test_confidence_cap(self):
        inp = synthetic()
        ep = ac.run_pipeline(inp)
        ep["robustness_score"] = 1.0
        c = ac.confidence(ep, inp["grid"], inp["ref"])
        self.assertTrue((c.confidence_uncapped == "HIGH").any())
        self.assertFalse((c.confidence == "HIGH").any())
        self.assertTrue(c.confidence_cap_reason[c.confidence_uncapped == "HIGH"].str.startswith("CAPPED_MEDIUM").all())


class GroundTruth(unittest.TestCase):
    def test_not_available_without_log(self):
        ep = pd.DataFrame({"episode_id": ["P6-001"], "start_time": [pd.Timestamp("2025-06-01")],
                           "end_time": [pd.Timestamp("2025-06-01 06:00")]})
        m = ac.match_plant_events(ep, None)
        self.assertTrue((m.drop(columns="episode_id") == ac.GT_STATUS).all().all())
        self.assertIsNone(ac.load_plant_events(Path("/nonexistent/plant_event_log.csv")))

    def test_matching_statuses(self):
        t = pd.Timestamp("2025-06-01")
        h = pd.Timedelta(hours=1)
        ep = pd.DataFrame({"episode_id": ["a", "b", "c"], "start_time": [t, t + 24 * h, t + 48 * h],
                           "end_time": [t + 6 * h, t + 30 * h, t + 54 * h]})
        ev = pd.DataFrame({"event_id": ["x", "y"], "event_type": ["TEST", "TEST"],
                           "start_time": [t - h, t + 29 * h], "end_time": [t + 7 * h, t + 32 * h],
                           "source": ["unit-test", "unit-test"], "description": ["", ""]})
        m = ac.match_plant_events(ep, ev)
        self.assertEqual(list(m.event_match_status), ["MATCHED", "PARTIAL_OVERLAP", "NO_MATCH"])


class Wording(unittest.TestCase):
    def test_scanner(self):
        self.assertTrue(ac.forbidden_hits("This is a confirmed deposit event."))
        self.assertTrue(ac.forbidden_hits("AFR ramp-down caused the excursion."))
        self.assertFalse(ac.forbidden_hits("These are not confirmed deposits."))
        self.assertFalse(ac.forbidden_hits("AFR context is a coincidence, never a cause."))


if __name__ == "__main__":
    unittest.main()
