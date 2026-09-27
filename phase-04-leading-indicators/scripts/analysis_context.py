"""Shared, read-only analysis context for Steps 4-9: KPI grid, features, targets, controls, windows and row filters.

All analysis rows are RUNNING buckets with a scored KPI at t and no stop / transition inside (t, t+H] (target rule).
Evaluation-window rows additionally require t + H to stay inside the same window, so discovery never sees a KPI value
after 2025-05-31 23:59 (purge) and each evaluation month is self-contained.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from p4common import CACHE, HOLDOUT, MONTHS, REPLICATION_MONTHS, P4Config, month_of
import indicator_core as ic

TARGET_COLUMN = {"primary": "K", "F": "K_F", "G": "K_G", "alt_w_jun_jul15": "K_ALT"}
WINDOW_SEEDS = {"DISCOVERY": 11, "JUN": 12, "JUL": 13, "AUG": 14, "OOS": 15, "APR": 16, "MAY": 17, "REPL": 18}
WINDOW_MONTHS = {"OOS": MONTHS, "REPL": REPLICATION_MONTHS, "HOLDOUT": (HOLDOUT,)}


@dataclass
class Context:
    cfg: P4Config
    index: pd.DatetimeIndex
    K: np.ndarray            # target KPI series for this configuration
    K_primary: np.ndarray    # primary shown KPI (episodes / controls benchmark)
    band_code: np.ndarray
    D: np.ndarray
    running: np.ndarray
    window: np.ndarray       # DISCOVERY / JUN / JUL / AUG / ''
    filt: np.ndarray         # configuration row filter (state / data-quality sensitivity)
    m: float
    q: float
    grid: pd.DataFrame


def load_grid() -> tuple[pd.DataFrame, dict]:
    return pd.read_parquet(CACHE / "kpi_grid.parquet"), json.loads((CACHE / "kpi_scale.json").read_text())


def row_filter(grid: pd.DataFrame, cfg: P4Config) -> np.ndarray:
    st = grid.bucket_state.to_numpy()
    ok = np.ones(len(grid), dtype=bool)
    if cfg.exclude_post_restart_h > 0:              # drop t within X h after a TRANSITION bucket (causal: past only)
        n = int(cfg.exclude_post_restart_h * 6)
        tr = (st == "TRANSITION").astype(float)
        ok &= ~(ic.trailing_mean(tr, n, 1) > 0)
    if cfg.exclude_pre_stop_h > 0:                  # ANALYSIS FILTER ONLY (uses the future stop time; never a feature)
        n = int(cfg.exclude_pre_stop_h * 6)
        stop = (st == "STOPPED").astype(float)
        fut = np.r_[ic.trailing_mean(stop, n, 1)[n:], np.zeros(n)]
        ok &= ~(fut > 0)
    if cfg.dq_filter:
        ok &= grid.data_quality.to_numpy() == "GOOD"
    return ok


def build_context(cfg: P4Config, grid: pd.DataFrame | None = None, scale: dict | None = None) -> Context:
    if grid is None:
        grid, scale = load_grid()
    return Context(cfg=cfg, index=grid.index, K=grid[TARGET_COLUMN[cfg.target]].to_numpy(float, copy=True),
                   K_primary=grid.K.to_numpy(float, copy=True), band_code=grid.band_code.to_numpy(int, copy=True),
                   D=grid.D.to_numpy(float, copy=True),
                   running=grid.bucket_state.eq("RUNNING").to_numpy(), window=month_of(grid.index, cfg),
                   filt=row_filter(grid, cfg), m=scale["m"], q=scale["q_anchor"], grid=grid)


def window_rows(ctx: Context, name: str, h: int) -> np.ndarray:
    """Rows of analysis window `name` whose horizon (t, t+h] ends inside the same window."""
    cfg = ctx.cfg
    t = ctx.index
    end_ok = np.zeros(len(t), dtype=bool)
    wins = cfg.windows()
    if name not in wins and name not in WINDOW_MONTHS and name not in ("APR", "MAY"):
        raise ValueError(f"unknown analysis window {name!r}")
    names = WINDOW_MONTHS.get(name, (name,) if name in wins else ())
    for w in names:
        a, b = (pd.Timestamp(x) for x in wins[w])
        end_ok |= (t >= a) & (t + pd.Timedelta(minutes=h * cfg.bucket_min) <= b)
    if name in ("APR", "MAY"):                      # split-half discovery (training-window sensitivity)
        a, b = pd.Timestamp(cfg.disc_start), pd.Timestamp(cfg.disc_end)
        mth = 4 if name == "APR" else 5
        end_ok = (t >= a) & (t + pd.Timedelta(minutes=h * cfg.bucket_min) <= b) & (t.month == mth) & \
                 ((t + pd.Timedelta(minutes=h * cfg.bucket_min)).month == mth)
    return end_ok & ctx.running & ctx.filt


def blocks(ctx: Context, rows: np.ndarray) -> tuple[np.ndarray, int]:
    """Block id per row (calendar-day blocks of cfg.block_days), compacted to 0..n_blocks-1 over `rows`."""
    day = (ctx.index.normalize() - pd.Timestamp("2025-04-01")).days.to_numpy() // ctx.cfg.block_days
    u, inv = np.unique(day[rows], return_inverse=True)
    out = np.zeros(len(day), dtype=int)
    out[rows] = inv
    return out, len(u)


def target_and_controls(ctx: Context, h: int) -> tuple[np.ndarray, np.ndarray | None]:
    if ctx.cfg.target_kind == "band_occupancy":
        y = ic.future_band_target(ctx.band_code, ctx.K, ctx.running, h)
    else:
        y = ic.future_target(ctx.K, ctx.running, h, ctx.cfg.target_smooth_buckets)
    Z = ic.controls(ctx.K, ctx.D, h, ctx.m, ctx.q) if ctx.cfg.use_controls else None
    return y, Z


def load_features() -> pd.DataFrame:
    return pd.read_parquet(CACHE / "features.parquet")


def split_id(col: str) -> tuple[str, str]:
    t, f = col.rsplit("|", 1)
    return t, f


def load_lag_table() -> pd.DataFrame:
    """Unrounded lag table (cache) for internal selection; the published CSV is rounded to 6 dp."""
    return pd.read_parquet(CACHE / "lag_analysis.parquet")


def discovery_choice(lag_df: pd.DataFrame) -> pd.DataFrame:
    """Per indicator, the lag chosen on DISCOVERY only: smallest BH q, ties -> largest |rho_p|, then shortest lag.
    The sign of that discovery rho_p is the pre-declared direction used in every evaluation window."""
    d = lag_df[lag_df.window.eq("DISCOVERY") & lag_df.rho_p.notna()].copy()
    d["abs_rho"] = d.rho_p.abs()
    d = d.sort_values(["indicator_id", "q_bh", "abs_rho", "lag_minutes"], ascending=[True, True, False, True],
                      kind="mergesort")
    c = d.groupby("indicator_id", sort=True).head(1).set_index("indicator_id")
    c["sign"] = np.sign(c.rho_p).astype(int)
    c["disc_supported"] = (c.q_bh <= 0.10) & (c.ci_lo * c.ci_hi > 0)       # BH q and bootstrap CI excluding 0
    return c[["lag_minutes", "sign", "rho_p", "q_bh", "p_eff", "ci_lo", "ci_hi", "n", "n_eff", "disc_supported"]]


def discovery_rows(ctx: Context) -> np.ndarray:
    return (ctx.window == "DISCOVERY") & ctx.running


def thresholds(F: pd.DataFrame, ctx: Context, choice: pd.DataFrame) -> pd.Series:
    """Directional POC analytical threshold per indicator: discovery P90 (sign +) or P10 (sign -) of the feature over
    RUNNING discovery buckets. Fitted on discovery only; NOT a plant alarm limit."""
    rows = discovery_rows(ctx)
    q = ctx.cfg.alarm_q
    out = {}
    for c, r in choice.iterrows():
        x = F[c].to_numpy(float)[rows]
        x = x[np.isfinite(x)]
        out[c] = float(np.quantile(x, q if r.sign > 0 else 1 - q)) if x.size else np.nan
    return pd.Series(out)
