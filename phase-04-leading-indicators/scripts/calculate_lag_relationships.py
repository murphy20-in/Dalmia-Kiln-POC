"""Step 4 - Lag relationships: every causal feature x(t) against the future KPI change dK(t, H), every lag H.

Reads  cache/features.parquet, cache/kpi_grid.parquet, outputs/indicator_candidate_inventory.csv
Writes outputs/indicator_lag_analysis.csv   one row per indicator (tag|feature) x lag x window:
         window  DISCOVERY (Apr-May, in-sample KPI) | JUN | JUL | AUG | REPL (pooled Jun-Jul: replication set used for
                 gates / scores / selection) | OOS (pooled Jun-Aug, descriptive only). AUG is the untouched holdout.
         rho_raw       Spearman(x(t), dK(t, H))
         rho_p         partial Spearman controlling for K(t), K momentum (1 h) and Kpend(t, H)  <- primary statistic
         n, n_eff      rows used / autocorrelation-adjusted effective sample size (Bartlett, Pyper-Peterman)
         p_eff, q_bh   Fisher-z p-value with n_eff / Benjamini-Hochberg q over ALL discovery tests
         ci_lo, ci_hi  95 % 3-day-block bootstrap CI of rho_p (1,000 resamples)
         rho_backward  Spearman(x(t), K(t) - K(t-H))  (lagging check)
         rho_contemp   Spearman(x(t), K(t))           (contemporaneous check)

Interpretation of a lag: x at time t (data <= t) vs the KPI change over (t, t+H]; i.e. signal(t' - H) -> KPI(t').
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from p4common import CACHE, PRIMARY, P4Config, log, read_out, write_csv
import analysis_context as ac
import indicator_core as ic

lg = log("calculate_lag_relationships")
WINDOWS = ("DISCOVERY", "JUN", "JUL", "AUG", "REPL", "OOS")


def spearman(x: np.ndarray, y: np.ndarray, rows: np.ndarray, min_n: int = 100) -> float:
    ok = rows & np.isfinite(x) & np.isfinite(y)
    if ok.sum() < min_n:
        return np.nan
    rx, ry = rankdata(x[ok]), rankdata(y[ok])
    if np.ptp(rx) == 0 or np.ptp(ry) == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def lag_task(args) -> list[dict]:
    """All tests for one lag (run in a worker process). Deterministic: fixed seeds per window."""
    cfg, cols, lag_min, windows, with_ci = args
    ctx = ac.build_context(cfg)
    F = ac.load_features()[cols]
    h = lag_min // cfg.bucket_min
    y, Z = ac.target_and_controls(ctx, h)
    back = ctx.K - ic.lagged(ctx.K, h)
    out = []
    for w in windows:
        rows = ac.window_rows(ctx, w, h)
        blk, _ = ac.blocks(ctx, rows)
        seed = cfg.seed + ac.WINDOW_SEEDS[w] if with_ci else None
        for c in cols:
            x = F[c].to_numpy(float)
            r = ic.assoc(x, y, Z, rows, blk, seed, cfg.neff_maxlag, n_boot=cfg.n_boot)
            r.update(indicator_id=c, lag_minutes=lag_min, window=w,
                     rho_backward=spearman(x, back, rows), rho_contemp=spearman(x, ctx.K, rows))
            out.append(r)
    return out


def lag_table(cfg: P4Config, cols: list[str], lags=None, windows=WINDOWS, with_ci: bool = True,
              workers: int | None = None) -> pd.DataFrame:
    lags = tuple(lags or cfg.lags)
    tasks = [(cfg, cols, L, windows, with_ci) for L in lags]
    workers = workers or min(len(tasks), max(1, (os.cpu_count() or 2) - 2))
    if workers == 1:
        res = [lag_task(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(lag_task, tasks))
    df = pd.DataFrame([r for part in res for r in part])
    df["q_bh"] = np.nan
    d = df.window.eq("DISCOVERY")
    df.loc[d, "q_bh"] = ic.bh(df.loc[d, "p_eff"].to_numpy())
    return df.sort_values(["indicator_id", "lag_minutes", "window"], kind="mergesort").reset_index(drop=True)


def main():
    cfg = PRIMARY
    inv = read_out("indicator_candidate_inventory.csv").set_index("indicator_tag")
    F = ac.load_features()
    cols = list(F.columns)
    del F
    df = lag_table(cfg, cols)
    t = df.indicator_id.str.rsplit("|", n=1)
    df["tag"], df["feature_type"] = t.str[0], t.str[1]
    for c in ("original_name", "dataset", "unit", "process_family", "tier", "status"):
        df[c] = df.tag.map(inv[c])
    order = ["indicator_id", "tag", "original_name", "dataset", "unit", "process_family", "tier", "status", "feature_type",
             "lag_minutes", "window", "n", "n_eff", "rho_raw", "rho_p", "p_eff", "q_bh", "ci_lo", "ci_hi",
             "rho_backward", "rho_contemp"]
    df = df[order]
    df.to_parquet(CACHE / "lag_analysis.parquet", index=False)      # unrounded, for internal selection (PY-L4)
    write_csv(df, "indicator_lag_analysis.csv", lg)
    d = df[df.window.eq("DISCOVERY")]
    lg.info("%d tests (%d discovery); discovery q<=%.2f: %d; |n_eff/n| median %.3f", len(df), len(d), cfg.fdr_q,
            int((d.q_bh <= cfg.fdr_q).sum()), float((d.n_eff / d.n).median()))


if __name__ == "__main__":
    main()
