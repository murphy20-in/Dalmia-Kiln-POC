"""Step 5 - Persistence scale anchors, POC analytical reference bands and their uncertainty.

Reads  cache/scored_primary.parquet, outputs/kpi_reference.json
Writes outputs/kpi_reference_bands.csv

Persistence (implemented in kpi_core.persistence): P(t) = trailing clock-time MEDIAN of the raw deviation D over
(t - 6 h, t], using scored (RUNNING) buckets only, reported only when >= 50 % of the 36 buckets are scored.
A median needs more than half the window elevated before it follows a change: a short spike can shift P only to
an adjacent order statistic of the window, by the same amount whatever the spike's magnitude (bounded influence),
and the effect disappears once the spike leaves the 6 h window. The price is a response latency of about half the
window (~3 h) to a genuine step.
The window is fixed a priori (6 h); the training autocorrelation of D is reported descriptively only.

Bands are quantiles of the IN-SAMPLE training distribution of P (an autocorrelated series: the effective
sample size is far below the bucket count). Uncertainty: day-block bootstrap (400 reps, fixed seed).
They are POC ANALYTICAL REFERENCE BANDS, not plant alarm or engineering limits.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p3common import BAND_LABEL, CACHE, OUT, PRIMARY, log, write_csv
from kpi_core import to_kpi, training_mask

lg = log("calculate_persistence")


def main():
    k = pd.read_parquet(CACHE / "scored_primary.parquet")
    ref = json.loads((OUT / "kpi_reference.json").read_text())
    meta = pd.read_parquet(CACHE / "buckets_primary_meta.parquet")
    tm = training_mask(meta, PRIMARY)
    P = k.persistent_deviation_score[tm].dropna()
    D = k.raw_deviation_score[tm]
    sc = ref["scale"]
    qs = {"m (training median of P; KPI = 0)": 0.5, f"q_anchor (training P{int(PRIMARY.ref_quantile_anchor * 100)} of P; KPI = 50)": PRIMARY.ref_quantile_anchor,
          f"band_lo (training P{int(PRIMARY.band_quantiles[0] * 100)} of P)": PRIMARY.band_quantiles[0],
          f"band_hi (training P{int(PRIMARY.band_quantiles[1] * 100)} of P)": PRIMARY.band_quantiles[1]}
    rng = np.random.default_rng(PRIMARY.seed)
    days = P.index.floor("D")
    ud = np.unique(days)
    groups = {d: P.to_numpy()[days == d] for d in ud}
    boot = []
    for _ in range(PRIMARY.bootstrap_reps):
        pick = rng.choice(ud, size=len(ud), replace=True)
        x = np.concatenate([groups[d] for d in pick])
        boot.append(np.quantile(x, list(qs.values())))
    boot = np.asarray(boot)
    rows = []
    for j, (name, q) in enumerate(qs.items()):
        val = float(P.quantile(q))
        lo, hi = np.quantile(boot[:, j], [0.025, 0.975])
        kb = to_kpi(np.array([val, lo, hi]), sc["m"], sc["q_anchor"])
        rows.append({"quantity": name, "quantile": q, "persistent_score_value": val, "ci95_low": lo, "ci95_high": hi,
                     "kpi_value": kb[0], "kpi_ci95_low": kb[1], "kpi_ci95_high": kb[2],
                     "method": "in-sample quantile of training P; CI = day-block bootstrap (400 reps)",
                     "n_training_buckets": int(P.size), "n_training_days": int(len(ud))})
    k_lo, k_hi = to_kpi([sc["q_band_lo"]], sc["m"], sc["q_anchor"])[0], to_kpi([sc["q_band_hi"]], sc["m"], sc["q_anchor"])[0]
    bands = [("WITHIN_REFERENCE_VARIATION", 0.0, k_lo, "persistent score below training P90"),
             ("ELEVATED_POC_ANALYTICAL", k_lo, k_hi, "persistent score between training P90 and P99"),
             ("BEYOND_REFERENCE_P99", k_hi, 100.0, "persistent score at or above training P99")]
    for name, a, b, rule in bands:
        in_tr = ((k.kpi_in_sample_reference >= a) & (k.kpi_in_sample_reference < b)).sum() / max(k.kpi_in_sample_reference.notna().sum(), 1)
        rows.append({"quantity": f"BAND: {name}", "kpi_value": a, "kpi_upper": b, "method": rule,
                     "training_share": float(in_tr), "label": BAND_LABEL})
    full = D.asfreq("10min") if D.index.freq is None else D
    for lag_h in [1, 3, 6, 12, 24, 48]:
        rows.append({"quantity": f"DESCRIPTIVE: training ACF of raw deviation D at lag {lag_h} h",
                     "persistent_score_value": float(full.autocorr(lag_h * 6)),
                     "method": "descriptive only; persistence window fixed a priori at 6 h"})
    rows.append({"quantity": "D_q90 (training P90 of raw deviation; 'elevated bucket' level for fraction_elevated)",
                 "persistent_score_value": ref["D_q90"], "method": "in-sample quantile"})
    df = pd.DataFrame(rows)
    df["label"] = df.get("label", pd.Series(dtype=str)).fillna(BAND_LABEL)
    write_csv(df, "kpi_reference_bands.csv", lg)


if __name__ == "__main__":
    main()
