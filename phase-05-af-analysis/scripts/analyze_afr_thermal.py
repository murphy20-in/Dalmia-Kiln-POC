"""Step - AFR vs thermal / process behaviour (family THERMAL, incl. Sp.Heat F and G - both kept, neither authoritative).

Reads  cache/buckets.parquet, cache/kpi_grid.parquet, cache/bands.json, cache/episodes.csv, cache/episode_controls.csv
Writes outputs/afr_thermal_relationships.csv  (schema af_core.REL_COLUMNS + negative-control / diagnostic columns)

Correlation engine, band contrasts and transition-episode responses: see af_context. Every row is AFR-ASSOCIATED
evidence at most - never AFR-caused - and implies no set-point, limit or operating action.

Sp.Heat derivation check (pre-declared, planner P-risk): on DISCOVERY RUNNING buckets, each Sp.Heat definition is
regressed (no intercept) on [coal-kiln, PC-coal, AFR] / kiln feed, and on [coal-kiln, PC-coal] / kiln feed. R^2 >= 0.95
with AFR marks the Sp.Heat rows POSSIBLY_DERIVED_FROM_FIRING_RATES: the plant value may be computed from the firing
inputs, so an AFR-Sp.Heat association can be arithmetic rather than process evidence. Only R^2 is published - the fitted
coefficients would amount to an inferred fuel heat value, which Phase 5 never produces.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from af_context import load_context, rows_for, run_families, target_series
from af_core import AFR, FEED_TAG, REL_COLUMNS, log, write_csv

lg = log("analyze_afr_thermal")
DERIVED_R2 = 0.95


def r2(y: np.ndarray, X: np.ndarray) -> float:
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(1 - np.var(y - X @ b) / np.var(y))


def derivation_rows(ctx) -> pd.DataFrame:
    feed = target_series(ctx, FEED_TAG)
    H, I = target_series(ctx, "Kiln-I!H"), target_series(ctx, "Kiln-I!I")
    rows = []
    for tag in ("Kiln-I!F", "Kiln-I!G"):
        y = target_series(ctx, tag)
        for w in ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG"):
            ok = rows_for(ctx, w) & np.isfinite(y) & np.isfinite(feed) & (feed > 100) & np.isfinite(H) & np.isfinite(I) \
                & np.isfinite(ctx.afr)
            with_afr = r2(y[ok], np.column_stack([H[ok] / feed[ok], I[ok] / feed[ok], ctx.afr[ok] / feed[ok]]))
            without = r2(y[ok], np.column_stack([H[ok] / feed[ok], I[ok] / feed[ok]]))
            rows.append({"afr_signal": AFR, "target_signal": tag, "target_original_name": "Sp.Heat derivation check",
                         "target_unit": "R^2", "target_family": "THERMAL", "analysis_type": "SP_HEAT_DERIVATION_CHECK",
                         "lag_minutes": 0, "window": w, "row_role": "DIAGNOSTIC", "operating_state": "RUNNING",
                         "load_condition": "RATIO_TO_FEED", "sample_count": int(ok.sum()), "effect_size": with_afr,
                         "effect_metric": "R^2 of Sp.Heat on [coal-kiln, PC, AFR]/feed (no intercept)",
                         "r2_without_afr": without, "evidence": "OBSERVED", "confidence": "NOT_APPLICABLE",
                         "flags": "POSSIBLY_DERIVED_FROM_FIRING_RATES" if with_afr >= DERIVED_R2 else "",
                         "interpretation": (f"OBSERVED: {tag} is reproduced with R^2 {with_afr:.3f} by fuel firing rates "
                                            f"(incl. AFR) per ton of feed, {without:.3f} without AFR. "
                                            + ("It is POSSIBLY DERIVED from the firing inputs: AFR-Sp.Heat co-movement is "
                                               "at least partly arithmetic, not independent process evidence."
                                               if with_afr >= DERIVED_R2 else
                                               "Firing inputs explain much, but not all, of its variation."))})
    return pd.DataFrame(rows)


def main():
    df = run_families(["THERMAL"], "afr_thermal_relationships.csv", lg)
    d = derivation_rows(load_context())
    disc = d[d.window.eq("DISCOVERY")].set_index("target_signal").effect_size
    for tag, v in disc.items():
        sel = df.target_signal.eq(tag) & df.row_role.ne("DIAGNOSTIC")
        note = (f"SP_HEAT_DERIVATION_R2={v:.3f}" + ("|POSSIBLY_DERIVED_FROM_FIRING_RATES" if v >= DERIVED_R2 else ""))
        df.loc[sel, "flags"] = df.loc[sel, "flags"].fillna("").astype(str).str.strip("|") + "|" + note
        txt = df.loc[sel, "interpretation"].fillna("")
        df.loc[sel, "interpretation"] = np.where(txt.ne(""), txt + f" Sp.Heat derivation check R^2 {v:.3f} "
                                                 "(firing rates per ton of feed): treat as partly arithmetic.", txt)
    df = pd.concat([df, d], ignore_index=True)
    cols = REL_COLUMNS + [c for c in df.columns if c not in REL_COLUMNS]
    write_csv(df[cols], "afr_thermal_relationships.csv", lg)


if __name__ == "__main__":
    main()
