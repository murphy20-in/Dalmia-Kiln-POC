"""Synthetic fixture shared by the Phase 7 unit tests (not collected by unittest discovery: no test_ prefix).

A 70-day 10-min grid (2025-04-01 .. 2025-06-09) with the cached-grid schema: RUNNING buckets with random one-sided
family components, a stop and a restart transition in April, a Kiln-I data gap in June, an injected multi-family
abnormal period in June (the synthetic 'final' period) and an in-sample calibration-only period in April.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import CONFIDENCE_VARIANTS, FAMILIES, PRIMARY  # noqa: E402
from feature_engineering import CAUSAL_INVALID, EPISODE_FIELDS, RETRO_MASKS  # noqa: E402

STOP = (pd.Timestamp("2025-04-20 00:00"), pd.Timestamp("2025-04-21 00:00"))
GAP = (pd.Timestamp("2025-06-05 10:00"), pd.Timestamp("2025-06-05 14:00"))
FINAL = (pd.Timestamp("2025-06-03 10:00"), pd.Timestamp("2025-06-03 16:00"))
CALIB = (pd.Timestamp("2025-04-10 00:00"), pd.Timestamp("2025-04-10 06:00"))


def make_grid(days: int = 70, seed: int = 0) -> pd.DataFrame:
    ix = pd.date_range("2025-04-01 00:10", periods=days * 144, freq="10min")
    ix.name = "ts"
    rng = np.random.default_rng(seed)
    state = np.full(len(ix), "RUNNING", dtype=object)
    state[(ix > STOP[0]) & (ix <= STOP[1])] = "STOPPED"
    state[(ix > STOP[1]) & (ix <= STOP[1] + pd.Timedelta(hours=2))] = "TRANSITION"
    g = pd.DataFrame(index=ix)
    g["state"] = state
    for d in FAMILIES:
        x = np.maximum(0.0, rng.gamma(1.0, 0.8, len(ix)) - 0.4)
        for a, b in (FINAL, CALIB):
            x[(ix > a) & (ix <= b)] += 3.0
        g[f"comp_{d}"] = np.where(state == "RUNNING", x, np.nan)
    gap = (ix > GAP[0]) & (ix <= GAP[1])
    g.loc[gap, [f"comp_{d}" for d in FAMILIES]] = np.nan
    g["tag_coverage"] = np.where(gap, 0.0, 1.0)
    g["n_causal_frozen"] = 0.0
    g["oor"] = False
    g["share_high_conf"] = 0.8
    g["feed"] = 400 + rng.normal(0, 10, len(ix))
    g["kpi_value"] = np.nan
    g["kpi_band"] = ""
    g["kpi_reference_state"] = ""
    g["afr"], g["coal_pc"] = 30.0, 9.0
    g["p4"] = rng.normal(0, 1, len(ix))
    g["n_cells"] = 300.0
    for c in CAUSAL_INVALID + RETRO_MASKS:
        g[c] = 0.0
    for d in FAMILIES:
        g[f"tagcov_{d}"] = np.where(gap, 0.0, 1.0)
    g["o2_bucket_pct"] = 5.0
    for d in ("COMBUSTION", "STABILITY"):
        g[f"comp_{d}_EXCL_O2"] = g[f"comp_{d}"]
    return g


def make_context(g: pd.DataFrame) -> dict:
    rows = []
    for eid, (a, b), cls, fin in (("S-001", CALIB, "CALIBRATION_ONLY_ABNORMAL_LIKE", False),
                                  ("S-002", FINAL, "HISTORICAL_ABNORMAL_PERIOD", True)):
        rows.append({"episode_id": eid, "start_time": a, "end_time": b, "onset_time": a - pd.Timedelta(hours=1),
                     "classification": cls, "in_final_set": fin,
                     "reference_state": "OUT_OF_SAMPLE" if fin else "IN_SAMPLE_REFERENCE", "severity_class": "LOW",
                     "severity_score": 0.3, "confidence": "MEDIUM", "load_context": "UNCERTAIN",
                     "afr_context": "NO_AFR_TRANSITION", "reference_robustness_score": 1.0, "family_count": 5,
                     "deviating_families": ";".join(FAMILIES), "episode_type": "MULTI_FAMILY"})
    ep = pd.DataFrame(rows)[EPISODE_FIELDS]
    afr = pd.DataFrame({"episode_id": ["A1", "A2"], "afr_transition": ["AFR_STOP", "AFR_START"],
                        "T": [pd.Timestamp("2025-06-03 09:00"), pd.Timestamp("2025-06-07 12:00")]})
    dq = pd.DataFrame({"kind": ["LONG_GAP"], "dataset": ["Kiln-I"], "start": [GAP[0]], "end": [GAP[1]],
                       "source": ["synthetic"]})
    return {"grid": g, "episodes": ep, "afr_events": afr, "dq_windows": dq, "p4_threshold": 1.0}


def fit_refs(ctx: dict) -> dict:
    from reference_builder import fit_reference
    refs = {n: fit_reference(ctx["grid"], c, ctx["episodes"], ctx) for n, c in CONFIDENCE_VARIANTS.items()}
    refs["PRIMARY"] = fit_reference(ctx["grid"], PRIMARY, ctx["episodes"], ctx)
    return refs


@lru_cache(maxsize=1)
def fixture() -> tuple[pd.DataFrame, dict, dict]:
    """(grid, ctx, refs) for the default seed; tests must not mutate them."""
    g = make_grid()
    ctx = make_context(g)
    return g, ctx, fit_refs(ctx)
