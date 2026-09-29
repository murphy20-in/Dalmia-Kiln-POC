"""Synthetic Jun-Aug grid with 12 known onsets for fast, deterministic unit tests (no Phase 6 / 7 files needed)."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import build_controls as bc  # noqa: E402
import calibration  # noqa: E402
import warning_metrics as wm  # noqa: E402
from p8common import P8Config  # noqa: E402

CFG = P8Config(n_null=300, n_boot=300)


def base(lift: float = 0.0, seed: int = 0, cfg: P8Config = CFG) -> tuple[dict, np.ndarray]:
    """92 days from 2025-06-01; 12 onsets (4 per month); rank-like signal x ~ U(0, 1), + lift over (T0 - 60 min, T0]."""
    ix = pd.date_range("2025-06-01 00:10", periods=92 * 144, freq="10min")
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 1, len(ix))
    days = [3, 10, 17, 24, 33, 40, 47, 54, 64, 71, 78, 85]
    pos = np.array([d * 144 + 60 for d in days])
    for p in pos:
        x[p - 5:p + 1] = np.clip(x[p - 5:p + 1] + lift, 0, 1)
    eps = pd.DataFrame({"episode_id": [f"E{i:02d}" for i in range(12)], "onset_time": ix[pos], "end_time": ix[pos + 18]})
    ev = pd.DataFrame({"event_id": eps.episode_id, "T0": ix[pos], "pos_T0": pos, "pos_det": pos + 6, "pos_end": pos + 18,
                       "month": ix[pos].month, "evaluable": True, "onset_censored": False,
                       "data_quality_status": "VALID", "severity": "LOW"})
    n = len(ix)
    B = {"ix": ix, "oper": np.ones(n, bool), "dq": np.zeros(n, bool), "month": ix.month.to_numpy(), "eps": eps,
         "events": ev,
         "s": pd.DataFrame({"family_count_abnormal": 0.0, "load_band": "NORMAL", "load_context": "STEADY_LOAD",
                            "secondary_reasons": ""}, index=ix)}
    finish(B, cfg)
    return B, x


def finish(B: dict, cfg: P8Config = CFG) -> dict:
    B["cand_free"] = bc.candidate_free(B["ix"], B["eps"], cfg)
    B["clean"] = bc.clean_mask(B["ix"], B["eps"], B["events"], cfg)
    B["elig"] = bc.eligibility(B["clean"], B["oper"], B["dq"], cfg)
    return B


def signals(score: np.ndarray, B: dict, cfg: P8Config = CFG) -> dict:
    ref = np.random.default_rng(7).uniform(0, 100, 3000)
    thr = calibration.reference_thresholds(ref, cfg)
    return {"name": "SYN", **wm.signals_from(score, thr, B["s"].family_count_abnormal.to_numpy(float), cfg)}
