"""Shared paths, configuration, labels and PURE functions for Phase 6 (Historical Abnormal Events).

Phase 6 is READ-ONLY with respect to the source data and to Phases 1-5. It writes only to
  phase-06-abnormal-events/{outputs,reports,cache}

Phase 4 code (indicator_core, p4common) and, through it, Phase 3 code (kpi_core, p3common, load_phase2_inputs) are imported
read-only: bytecode writing is disabled first and the Phase 4 script directory is APPENDED to sys.path, so Phase 6 modules
with the same file name (sensitivity_analysis, generate_report) take precedence.

TERMINOLOGY. Everything detected here is a CANDIDATE ABNORMAL PERIOD or a HISTORICAL ABNORMAL PERIOD (an empirical process
deviation episode). ABNORMAL_PERIOD != CONFIRMED_PLANT_EVENT and DEVIATION != FAILURE. No supplied event ground truth
exists (coating, ring, deposit, maintenance, failure, cleaning or shutdown reasons), so event_ground_truth_status is
NOT_AVAILABLE for every episode and no plant event label is created.

Every number in P6Config is a POC ANALYTICAL HEURISTIC declared before the episodes were inspected, or a frozen Apr-May
training quantile read from Phase 3. None is a plant operating, alarm, safety or control limit.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
from dataclasses import asdict, dataclass, replace  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "phase-06-abnormal-events"
SCRIPTS = PHASE_DIR / "scripts"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
CACHE = PHASE_DIR / "cache"
P5_DIR = ROOT / "phase-05-af-analysis"
P5_OUT = P5_DIR / "outputs"
P4_DIR = ROOT / "phase-04-leading-indicators"
P4_OUT = P4_DIR / "outputs"
P4_SCRIPTS = P4_DIR / "scripts"
P3_DIR = ROOT / "phase-03-efficiency-kpi"
P3_OUT = P3_DIR / "outputs"
P2_OUT = ROOT / "phase-02-baseline" / "outputs"
P1_OUT = ROOT / "phase-01-data-discovery" / "outputs"
PROCESSED = ROOT / "data" / "processed"
CURATED = ROOT / "data" / "curated"
RAW = ROOT / "data" / "raw"
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")

for _d in (OUT, REPORTS, FIG, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

# Import precondition: p4common / p3common mkdir their own dirs at import; they must already exist (never created by us).
for _d in (P4_OUT, P4_DIR / "reports" / "figures", P4_DIR / "cache", P3_OUT, P3_DIR / "reports" / "figures",
           P3_DIR / "cache"):
    if not _d.is_dir():
        raise RuntimeError(f"upstream directory missing ({_d}); run Phases 3-4 first - Phase 6 never creates upstream files")
if str(P4_SCRIPTS) not in sys.path:
    sys.path.append(str(P4_SCRIPTS))

import p4common  # noqa: E402  (Phase 4, read-only; appends the Phase 3 scripts dir)
import indicator_core as ic  # noqa: E402  (Phase 4, read-only)
import p3common  # noqa: E402  (Phase 3, read-only)

METHOD_VERSION = "p6-abn-1.0.0"
CANDIDATE_LABEL = "CANDIDATE_ABNORMAL_PERIOD"
FINAL_LABEL = "HISTORICAL_ABNORMAL_PERIOD"
CALIBRATION_LABEL = "CALIBRATION_ONLY_ABNORMAL_LIKE"   # would qualify, but lies in the KPI's own Apr-May training window
PERIOD_NOTE = ("EMPIRICAL HISTORICAL ABNORMAL PERIOD (PROCESS DEVIATION EPISODE FROM THE PHASE 3 POC KPI) - NOT A "
               "VALIDATED PLANT EVENT")
GT_STATUS = "NOT_AVAILABLE"
FAMILIES = ("EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY")
FEED, SPEED, CLINKER = p3common.FEED_TAG, p3common.SPEED_TAG, "Kiln-IIIA!M"
COAL_KILN, COAL_PC, AFR = "Kiln-I!H", "Kiln-I!I", "Kiln-I!K"
LOAD_TAGS = {FEED: "feed", SPEED: "speed", CLINKER: "clinker"}
CONTEXT_TAGS = {**LOAD_TAGS, COAL_KILN: "coal_kiln", COAL_PC: "coal_pc", AFR: "afr"}
P4_INDICATOR = "Kiln-I!I|ROC_1H"
STATE_DATASETS = list(p3common.KPI_DATASETS)
LOAD_DATASETS = ["Kiln-I", "Kiln-IA", "Kiln-II", "Kiln-IIIA"]
TRAIN_END = pd.Timestamp(p3common.PRIMARY.train_end)
MONTHS = {4: "APR_MAY", 5: "APR_MAY", 6: "JUN", 7: "JUL", 8: "AUG"}
FP_CATEGORIES = ("DATA_QUALITY_ARTIFACT", "INSUFFICIENT_DATA", "STARTUP", "RESTART", "SHUTDOWN", "SHORT_TRANSIENT",
                 "NORMAL_LOAD_CHANGE", "AFR_TRANSITION", "CONTROL_ACTION")
PRECEDENCE = FP_CATEGORIES + ("NONE",)
FP_NOTE = {
    "DATA_QUALITY_ARTIFACT": "deviation dominated by masked / missing / frozen data",
    "INSUFFICIENT_DATA": "fewer than min_valid_families process families have data",
    "STARTUP": "onset inside a restart ramp (+ settle) after a stop >= 24 h",
    "RESTART": "onset inside a restart ramp (+ settle) after a shorter stop",
    "SHUTDOWN": "onset within shutdown_lead_h before a kiln stop that follows the episode",
    "SHORT_TRANSIENT": "shorter than the minimum duration",
    "NORMAL_LOAD_CHANGE": "load deviated and < 2 process families deviated",
    "AFR_TRANSITION": "AFR stop / ramp-down near onset and < 2 process families deviated (context, not cause)",
    "CONTROL_ACTION": "coal firing step near onset without a load change and < 2 families deviated (context, not cause)",
}


@dataclass(frozen=True)
class P6Config:
    """Every analytical choice of Phase 6. A variant = dataclasses.replace(PRIMARY, ...)."""
    name: str = "PRIMARY"
    kpi_col: str = "K"                   # K (Phase 3 shown KPI) | K_F | K_G | K_ALT | MAHA (sensitivity A / G / I)
    thr: float = float("nan")            # candidate cut; NaN = frozen Phase 3 band_lo (training P90 of P, KPI 41.82)
    hi: float = float("nan")             # NaN = frozen Phase 3 band_hi (training P99, KPI 60.52)
    min_dur_min: int = 60                # shorter episodes are SHORT_TRANSIENT (kept, never deleted)
    merge_gap_min: int = 60              # runs separated by <= 60 min of RUNNING buckets are one episode
    min_families: int = 1                # final period needs >= this many deviating process families (sensitivity D)
    min_valid_families: int = 3
    family_valid_share: float = 0.5
    cusum_k: float = float("nan")        # NaN = frozen training calibration (see fit_reference)
    cusum_h: float = float("nan")
    onset_lookback_min: int = 360        # onset searched in [detection - 6 h, detection] (the KPI persistence window)
    load_z: float = 3.0                  # |robust z| of speed / clinker vs training
    dq_artifact: float = 0.5
    dq_affected: float = 0.2
    restart_settle_h: float = 6.0        # KPI persistence window after the Phase 2 ramp end
    startup_stop_min: int = 1440
    shutdown_lead_h: float = 6.0
    shutdown_after_h: float = 2.0
    afr_pre_h: float = 3.0               # AFR context window [onset - 3 h, end]; the AFR_TRANSITION category needs an
    afr_post_onset_h: float = 1.0        # AFR stop / ramp-down in [onset - 3 h, onset + 1 h]
    maha_thr: float = 50.0               # Phase 3 secondary KPI = 50 at its training P95
    maha_share: float = 0.5
    state_mode: str = "context"          # context | exclude_post_restart | no_state_context   (sensitivity E)
    load_mode: str = "context"           # context | ignore | exclude_oor | independent_only    (sensitivity F)
    mv_mode: str = "family"              # family | maha | both                                  (sensitivity G)
    dq_mode: str = "standard"            # standard | strict | none                              (sensitivity H)
    seed: int = 20250601

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()[:12]


PRIMARY = P6Config()


def variant(**kw) -> P6Config:
    return replace(PRIMARY, **kw)


# ============================================================================== io helpers
def log(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stdout)
    return logging.getLogger(name)


sha256 = p4common.sha256
round_frame = p4common.round_frame


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_csv(p, index=False)
    (lg or log("p6")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def write_parquet(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_parquet(p, index=False)
    (lg or log("p6")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def load_inputs() -> dict:
    """The cache written by load_phase6_inputs.py (grid, events, DQ windows, frozen reference)."""
    return {"grid": pd.read_parquet(CACHE / "grid.parquet"),
            "events": pd.read_parquet(CACHE / "events.parquet"),
            "dq_windows": pd.read_parquet(CACHE / "dq_windows.parquet"),
            "ref": json.loads((CACHE / "p6_reference.json").read_text())}


def save_stage(df: pd.DataFrame, name: str) -> None:
    df.to_parquet(CACHE / f"stage_{name}.parquet", index=False)


def load_stage(name: str) -> pd.DataFrame:
    return pd.read_parquet(CACHE / f"stage_{name}.parquet")


# ============================================================================== frozen reference (Apr-May only)
def robust(v: np.ndarray) -> tuple[float, float]:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        raise ValueError("robust(): no finite training values - a reference would silently become NaN")
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med)) * p3common.MAD_SCALE)
    return med, max(mad, 1e-9)


def abs_change(x: np.ndarray, n: int) -> np.ndarray:
    """|median(x over [t-n+1, t]) - median(x over [t-2n+1, t-n])| - trailing, never looks forward."""
    m = ic.trailing_median(np.asarray(x, float), n, max(1, (2 * n) // 3))
    return np.abs(m - ic.lagged(m, n))


def fit_reference(grid: pd.DataFrame, bands: dict, kpi_ref: dict) -> dict:
    """Everything Phase 6 fits, on Apr-May RUNNING buckets only (the Phase 3 training window) - frozen afterwards."""
    tr = (grid.index <= TRAIN_END) & grid.state.eq("RUNNING").to_numpy()
    ref = {"train_end": str(TRAIN_END), "n_train_buckets": int(tr.sum()), "thr": bands["band_lo"],
           "hi": bands["band_hi"], "family_p90": {d: kpi_ref["dims"][d]["p90_window_S"] for d in FAMILIES},
           "D_q90": kpi_ref["D_q90"], "load": {}}
    ref["D_median"], ref["D_mad"] = robust(grid.D.to_numpy()[tr])
    for tag, col in LOAD_TAGS.items():
        ref["load"][col] = dict(zip(("median", "mad"), robust(grid[col].to_numpy()[tr])))
    for col, n in (("feed", 6), ("feed", 12), ("coal_total", 6)):
        x = grid.feed if col == "feed" else grid.coal_kiln + grid.coal_pc
        a = abs_change(x.to_numpy(), n)[tr]
        a = a[np.isfinite(a)]
        for q in (50, 75, 90):
            ref[f"{col}_d{n * 10}m_p{q}"] = float(np.quantile(a, q / 100))
    # CUSUM on the robust z of D: allowance k = half the shift from the training median to the training P90 of D (the
    # classical k = delta / 2); decision interval h = training P90 of the 6-h CUSUM rise S_t - min(S over the trailing
    # 6 h) - D is autocorrelated, so a textbook h = 5 would be exceeded most of the time in training.
    ref["cusum_k"] = 0.5 * (kpi_ref["D_q90"] - ref["D_median"]) / ref["D_mad"]
    S = cusum((grid.D.to_numpy(float) - ref["D_median"]) / ref["D_mad"], ~grid.state.eq("RUNNING").to_numpy(),
              ref["cusum_k"])
    rise = S - pd.Series(S).rolling(PRIMARY.onset_lookback_min // 10 + 1, min_periods=1).min().to_numpy()
    ref["cusum_h"] = float(np.quantile(rise[tr], 0.9))
    fr = grid.feed.to_numpy()[tr]
    ref["feed_p01"], ref["feed_p99"] = (float(np.nanquantile(fr, q)) for q in (0.01, 0.99))
    return ref


# ============================================================================== candidate runs and merging
def cut_of(cfg: P6Config, ref: dict) -> float:
    if not np.isnan(cfg.thr):
        return cfg.thr
    return cfg.maha_thr if cfg.kpi_col == "MAHA" else ref["thr"]


def candidate_flags(g: pd.DataFrame, cfg: P6Config, ref: dict, events: pd.DataFrame | None = None) -> np.ndarray:
    """Bucket-level candidate rule: KPI column >= frozen cut, RUNNING bucket (+ variant filters). Uses bucket t only."""
    k = g[cfg.kpi_col].to_numpy(float)
    f = np.where(np.isfinite(k), k >= cut_of(cfg, ref), False) & g.state.eq("RUNNING").to_numpy()
    if cfg.dq_mode == "strict":
        f &= g.dq.eq("GOOD").to_numpy()
    if cfg.load_mode == "exclude_oor":
        f &= ~g.oor.fillna(False).to_numpy(bool)
    if cfg.state_mode == "exclude_post_restart" and events is not None:
        f &= ~near_restart(g.index, events, cfg)
    return f


def near_restart(ix: pd.DatetimeIndex, events: pd.DataFrame, cfg: P6Config) -> np.ndarray:
    out = np.zeros(len(ix), bool)
    for _, e in events[events.kind == "RESTART"].iterrows():
        end = e.event_time + pd.Timedelta(minutes=float(np.nan_to_num(e.ramp_minutes))) + pd.Timedelta(hours=cfg.restart_settle_h)
        out |= (ix >= e.event_time) & (ix <= end)
    return out


def runs_of(flag: np.ndarray) -> list[tuple[int, int]]:
    """Maximal runs of True as inclusive (start, end) positions."""
    f = np.r_[False, np.asarray(flag, bool), False].astype(np.int8)
    d = np.diff(f)
    return list(zip(np.flatnonzero(d == 1).tolist(), (np.flatnonzero(d == -1) - 1).tolist()))


def merge_runs(runs: list[tuple[int, int]], running: np.ndarray, blocked: np.ndarray, gap_buckets: int
               ) -> list[tuple[int, int, int]]:
    """Gap-aware merging: consecutive runs join when the gap is <= gap_buckets buckets, every gap bucket is RUNNING
    and no gap bucket is `blocked` (Phase 1 long data gap / frozen window). Returns (start, end, n_runs_merged).
    Merging only ever extends an episode forward, so an episode's start never depends on later data."""
    out: list[list[int]] = []
    for s, e in runs:
        if out:
            ps, pe, n = out[-1]
            gap = s - pe - 1
            if gap <= gap_buckets and running[pe + 1:s].all() and not blocked[pe + 1:s].any():
                out[-1] = [ps, e, n + 1]
                continue
        out.append([s, e, 1])
    return [tuple(r) for r in out]


def cusum(x: np.ndarray, reset: np.ndarray, k: float) -> np.ndarray:
    # ponytail: pure-python O(n) loop (~26k buckets, ~120 pipeline runs, ~40 s total); vectorise / numba if the grid or
    # the number of variants grows materially.
    """One-sided upper CUSUM S_t = max(0, S_{t-1} + x_t - k); NaN x holds S; `reset` buckets set S = 0. Causal."""
    S = np.zeros(len(x))
    s = 0.0
    for i, v in enumerate(x):
        if reset[i]:
            s = 0.0
        elif np.isfinite(v):
            s = max(0.0, s + v - k)
        S[i] = s
    return S


def onset_from_cusum(S: np.ndarray, det: int, look: int, h: float) -> tuple[int, bool, bool]:
    """Onset for a detection at `det` using S[<= det] only: the bucket after the last S == 0 in [det - look, det].
    Returns (onset, change_point_supported (CUSUM rise S[det] - min S over the window > h), onset_censored (S > 0 over
    the whole window, i.e. the shift began earlier than the look-back))."""
    a = max(0, det - look)
    w = S[a:det + 1]
    supported = bool(S[det] - w.min() > h)
    zeros = np.flatnonzero(w == 0)
    if zeros.size == 0:
        return a, supported, True
    return min(a + int(zeros[-1]) + 1, det), supported, False


# ============================================================================== episode statistics
def slope_per_h(y: np.ndarray) -> float:
    y = np.asarray(y, float)
    ok = np.isfinite(y)
    if ok.sum() < 3:
        return float("nan")
    t = np.arange(len(y))[ok] / 6.0
    return float(np.polyfit(t, y[ok], 1)[0])


def nanmed(a) -> float:
    a = np.asarray(a, float)
    return float(np.median(a[np.isfinite(a)])) if np.isfinite(a).any() else float("nan")


def share(mask: np.ndarray) -> float:
    return float(np.mean(mask)) if len(mask) else float("nan")


def dq_window_mask(ix: pd.DatetimeIndex, dqw: pd.DataFrame, kinds: tuple) -> np.ndarray:
    """Bucket (t-10 min, t] overlaps any Phase 1 DQ window of the given kinds."""
    out = np.zeros(len(ix), bool)
    for _, w in dqw[dqw.kind.isin(kinds)].iterrows():
        out |= (ix > w.start) & (ix - pd.Timedelta(minutes=10) < w.end)
    return out


def family_stats(fam: dict, ref: dict, cfg: P6Config, seg: slice) -> dict:
    """Process-family deviation over a window: a family is VALID when >= family_valid_share of its buckets are scored
    and DEVIATING when its window median S_d exceeds its own frozen training P90 (the Phase 3 n_dims_elevated rule).
    <family>_deviation = median S_d / P90 (> 1 = deviating)."""
    r, n_valid, n_dev = {}, 0, 0
    for d in FAMILIES:
        v = fam[d][seg]
        valid = bool(len(v) and np.isfinite(v).mean() >= cfg.family_valid_share)
        p90 = ref["family_p90"][d]
        ratio = nanmed(v) / p90 if p90 > 0 else float("nan")
        r[f"{d.lower()}_deviation"] = ratio if valid else float("nan")
        r[f"{d.lower()}_deviating"] = bool(valid and ratio > 1)
        r[f"{d.lower()}_share_above"] = share(np.where(np.isfinite(v), v > ref["family_p90"][d], False))
        n_valid += valid
        n_dev += bool(valid and ratio > 1)
    r["number_of_valid_families"], r["family_count"] = n_valid, n_dev
    r["family_agreement"] = n_dev / n_valid if n_valid else float("nan")
    r["deviating_families"] = ";".join(d for d in FAMILIES if r[f"{d.lower()}_deviating"]) or "NONE"
    r["deviation_breadth"] = ("MULTI_FAMILY_DEVIATION" if n_dev >= 2 else "SINGLE_FAMILY_DEVIATION" if n_dev == 1
                              else "KPI_AGGREGATE_ONLY")
    return r


def family_arrays(g: pd.DataFrame) -> dict:
    return {d: g[f"S_{d}"].to_numpy(float) for d in FAMILIES}


def build_episodes(g: pd.DataFrame, cfg: P6Config, ref: dict, events: pd.DataFrame, dqw: pd.DataFrame) -> pd.DataFrame:
    """Candidate buckets -> runs -> gap-aware merge -> one row per candidate episode with KPI, CUSUM onset, family,
    multivariate and load statistics. Definition fields use data <= the detection bucket (onset, families_at_detection)
    or <= the episode end (extent statistics); nothing after the end."""
    ix = g.index
    n = len(g)
    running = g.state.eq("RUNNING").to_numpy()
    blocked = dq_window_mask(ix, dqw, kinds=("LONG_GAP", "FROZEN_WINDOW"))
    flag = candidate_flags(g, cfg, ref, events)
    eps = merge_runs(runs_of(flag), running, blocked, cfg.merge_gap_min // 10)
    thr = cut_of(cfg, ref)
    K = g[cfg.kpi_col].to_numpy(float)
    D = g.D.to_numpy(float)
    ck = ref["cusum_k"] if np.isnan(cfg.cusum_k) else cfg.cusum_k
    ch = ref["cusum_h"] if np.isnan(cfg.cusum_h) else cfg.cusum_h
    S = cusum((D - ref["D_median"]) / ref["D_mad"], ~running, ck)
    look = cfg.onset_lookback_min // 10
    fam = family_arrays(g)
    maha = g.MAHA.to_numpy(float)
    feed = g.feed.to_numpy(float)
    oor = g.oor.fillna(False).to_numpy(bool)
    in_sample = g.in_sample.to_numpy(bool)
    rows = []
    for s, e, nm in eps:
        onset, cp, cens = onset_from_cusum(S, s, look, ch)
        seg = slice(s, e + 1)
        k = K[seg]
        nxt = e + 1
        if nxt >= n:
            end_reason = "DATA_END"
        elif not running[nxt]:
            end_reason = "KILN_NOT_RUNNING"
        elif not np.isfinite(K[nxt]):
            end_reason = "KPI_UNAVAILABLE"
        else:
            end_reason = "KPI_BELOW_THRESHOLD"
        r = {"pos_start": s, "pos_end": e, "pos_onset": onset, "n_runs_merged": nm,
             "start_time": ix[s] - pd.Timedelta(minutes=10), "end_time": ix[e], "detection_time": ix[s],
             "onset_time": ix[onset] - pd.Timedelta(minutes=10), "duration_minutes": (e - s + 1) * 10,
             "candidate_buckets": int(flag[seg].sum()), "end_reason": end_reason,
             "right_censored": end_reason == "DATA_END",
             "reference_state": "IN_SAMPLE_REFERENCE" if in_sample[seg].mean() >= 0.5 else "OUT_OF_SAMPLE",
             "month": MONTHS.get(ix[s].month, "OTHER"),
             "peak_kpi": float(np.nanmax(k)), "median_kpi": nanmed(k),
             "kpi_integral": float(np.nansum(np.maximum(k - thr, 0)) / 6.0),     # KPI points x hours above the cut
             "kpi_slope": slope_per_h(k),
             "kpi_onset_slope": slope_per_h(K[onset:s + 1]) if s > onset else float("nan"),
             "change_point_supported": cp, "onset_censored": cens,
             "cusum_rise_6h": float(S[s] - S[max(0, s - look):s + 1].min()),
             "level_shift_d": nanmed(D[onset:s + 1]) - nanmed(D[max(0, onset - look):onset])}
        r.update(family_stats(fam, ref, cfg, seg))
        r["families_at_detection"] = sum(nanmed(fam[d][onset:s + 1]) > ref["family_p90"][d] for d in FAMILIES)
        mv = maha[seg]
        r["maha_median"] = nanmed(mv)
        r["maha_share_above"] = (share(np.where(np.isfinite(mv), mv >= cfg.maha_thr, False))
                                 if np.isfinite(mv).any() else float("nan"))
        r["multivariate_supported"] = bool(np.isfinite(r["maha_share_above"]) and r["maha_share_above"] >= cfg.maha_share)
        # load: episode level vs frozen training median / MAD, and feed change vs the 2 h before onset
        r["feed_median"] = nanmed(feed[seg])
        r["feed_change_vs_pre2h"] = r["feed_median"] - nanmed(feed[max(0, onset - 12):onset])
        for col in LOAD_TAGS.values():
            L = ref["load"][col]
            r[f"{col}_z"] = (nanmed(g[col].to_numpy(float)[seg]) - L["median"]) / L["mad"]
        r["oor_share"] = share(oor[seg])
        rows.append(r)
    return pd.DataFrame(rows)


# ============================================================================== context and data quality
def add_context(ep: pd.DataFrame, g: pd.DataFrame, cfg: P6Config, ref: dict, events: pd.DataFrame,
                dqw: pd.DataFrame) -> pd.DataFrame:
    """Operating-state, load, AFR, Phase 4, control-action and data-quality context. Context is NEVER a cause."""
    ix = g.index
    restarts = events[events.kind == "RESTART"]
    stops = events[events.kind == "STOP"]
    afr = events[events.kind.str.startswith("AFR_")]
    coal = (g.coal_kiln + g.coal_pc).to_numpy(float)
    feed = g.feed.to_numpy(float)
    p4 = g.p4.to_numpy(float)
    dq_good = g.dq.eq("GOOD").to_numpy()
    cov = g.tag_cov.to_numpy(float)
    win = dq_window_mask(ix, dqw, kinds=("LONG_GAP", "FROZEN_WINDOW"))
    masked = g.masked_share.to_numpy(float)
    out = []
    for r in ep.itertuples():
        on, s, e = int(r.pos_onset), int(r.pos_start), int(r.pos_end)
        t_on, t_end = r.onset_time, r.end_time
        c = {}
        # --- operating state. Phase 2 events are retrospective (full-period, non-real-time); they are context, but the
        #     STARTUP / RESTART / SHUTDOWN categories DO gate final-set membership (classify). SHUTDOWN looks up to
        #     shutdown_after_h past the end: it is a retrospective classification, covered by the leakage test only
        #     once end + shutdown_after_h is known.
        rs = restarts[restarts.event_time <= t_on].tail(1)
        ramp_end = (rs.event_time.iloc[0] + pd.Timedelta(minutes=float(np.nan_to_num(rs.ramp_minutes.iloc[0])))
                    + pd.Timedelta(hours=cfg.restart_settle_h)) if len(rs) else None
        in_ramp = bool(len(rs) and t_on <= ramp_end)
        long_stop = bool(len(rs) and np.nan_to_num(rs.stop_minutes_before.iloc[0]) >= cfg.startup_stop_min)
        c["startup_overlap"] = in_ramp and long_stop
        c["restart_overlap"] = in_ramp and not long_stop
        c["hours_since_restart"] = float((t_on - rs.event_time.iloc[0]) / pd.Timedelta(hours=1)) if len(rs) else float("nan")
        st = stops[(stops.event_time >= r.start_time) & (stops.event_time <= t_end + pd.Timedelta(hours=cfg.shutdown_after_h))]
        c["stop_follows_within_2h"] = bool(len(st))
        c["shutdown_overlap"] = bool(len(st) and (st.event_time.iloc[0] - t_on) <= pd.Timedelta(hours=cfg.shutdown_lead_h))
        # --- load
        fz = abs(r.feed_change_vs_pre2h)
        lz = np.abs([r.speed_z, r.clinker_z])
        lz_max = float(np.nanmax(lz)) if np.isfinite(lz).any() else float("nan")
        load_dev = bool((np.isfinite(fz) and fz >= ref["feed_d120m_p90"]) or r.oor_share >= 0.5
                        or (np.isfinite(lz_max) and lz_max >= cfg.load_z))
        indep = bool(np.isfinite(fz) and fz <= ref["feed_d120m_p75"] and r.oor_share < 0.1
                     and (not np.isfinite(lz_max) or lz_max < 2.0))
        c["load_change_overlap"] = load_dev
        c["load_context"] = "LOAD_ASSOCIATED" if load_dev else ("LOAD_INDEPENDENT" if indep else "UNCERTAIN")
        # --- AFR (Phase 5 transition episodes: context only)
        a = afr[(afr.event_time >= t_on - pd.Timedelta(hours=cfg.afr_pre_h)) & (afr.event_time <= t_end)]
        kinds = set(a.kind)
        c["afr_start_overlap"] = "AFR_START" in kinds
        c["afr_stop_overlap"] = "AFR_STOP" in kinds
        c["afr_ramp_overlap"] = bool(kinds & {"AFR_RAMP_UP", "AFR_RAMP_DOWN"})
        c["afr_rampdown_overlap"] = "AFR_RAMP_DOWN" in kinds
        c["afr_context"] = ";".join(sorted(kinds)) if kinds else "NO_AFR_TRANSITION"
        c["afr_episode_ids"] = ";".join(a.event_id)
        near = a[a.event_time <= t_on + pd.Timedelta(hours=cfg.afr_post_onset_h)]
        c["afr_near_onset"] = ";".join(sorted(set(near.kind))) or "NONE"
        afr_down = bool(set(near.kind) & {"AFR_STOP", "AFR_RAMP_DOWN"})
        c["afr_down_near_onset"] = afr_down
        # --- Phase 4 (supporting only; LOW confidence, not a confirmed predictor)
        pw = p4[max(0, on - 12):on + 1]
        n_act = int(np.sum(np.where(np.isfinite(pw), pw >= ref["p4_threshold"], False)))
        c["phase4_active_buckets_pre2h"] = n_act
        c["phase4_indicator_overlap"] = n_act > 0
        c["phase4_indicator_context"] = (
            "NOT_AVAILABLE" if not np.isfinite(pw).any() else "NOT_ACTIVE" if not n_act else
            f"ACTIVE_IN_2H_BEFORE_ONSET (n={n_act}; LOW confidence; "
            + ("coincides with AFR stop / ramp-down: coal-for-AFR swap signature)" if afr_down
               else "supporting context only)"))
        # --- control action: coal firing step around onset without a load step
        coal_step = nanmed(coal[on:on + 6]) - nanmed(coal[max(0, on - 6):on])
        feed_step = nanmed(feed[on:on + 6]) - nanmed(feed[max(0, on - 6):on])
        c["coal_step_at_onset"] = coal_step
        c["control_action_overlap"] = bool(np.isfinite(coal_step) and abs(coal_step) >= ref["coal_total_d60m_p90"]
                                           and np.isfinite(feed_step) and abs(feed_step) <= ref["feed_d60m_p75"])
        # --- data quality over the episode plus the hour before detection
        dsl = slice(max(0, s - 6), e + 1)
        nongood = 1 - share(dq_good[dsl])
        wshare = share(win[dsl])
        covloss = 1 - nanmed(cov[dsl]) if np.isfinite(cov[dsl]).any() else 1.0
        c["dq_nongood_share"], c["dq_window_share"], c["dq_coverage_loss"] = nongood, wshare, covloss
        c["dq_masked_cell_share"] = float(np.nanmean(masked[dsl])) if np.isfinite(masked[dsl]).any() else float("nan")
        c["data_quality_contamination"] = float(max(nongood, wshare, covloss))
        c["data_quality_overlap"] = c["data_quality_contamination"] >= cfg.dq_affected
        c["data_quality_context"] = ("DATA_QUALITY_ARTIFACT" if c["data_quality_contamination"] >= cfg.dq_artifact else
                                     "DQ_AFFECTED" if c["data_quality_overlap"] else "DQ_CLEAN")
        out.append(c)
    ep = pd.concat([ep.reset_index(drop=True), pd.DataFrame(out)], axis=1)
    return classify(ep, cfg)


def classify(ep: pd.DataFrame, cfg: P6Config) -> pd.DataFrame:
    """primary_context by fixed precedence (first match wins); every other matching context -> secondary_context."""
    ep = ep.copy()
    weak = ep.family_count < 2
    state_on = cfg.state_mode != "no_state_context"
    conds = {
        "DATA_QUALITY_ARTIFACT": ep.data_quality_context.eq("DATA_QUALITY_ARTIFACT") & (cfg.dq_mode != "none"),
        "INSUFFICIENT_DATA": ep.number_of_valid_families < cfg.min_valid_families,
        "STARTUP": ep.startup_overlap & state_on,
        "RESTART": ep.restart_overlap & state_on,
        "SHUTDOWN": ep.shutdown_overlap & state_on,
        "SHORT_TRANSIENT": ep.duration_minutes < cfg.min_dur_min,
        "NORMAL_LOAD_CHANGE": ep.load_change_overlap & weak & (cfg.load_mode != "ignore"),
        "AFR_TRANSITION": ep.afr_down_near_onset & weak,
        "CONTROL_ACTION": ep.control_action_overlap & weak,
    }
    M = pd.DataFrame(conds).astype(bool)
    ep["primary_context"] = [next((k for k in FP_CATEGORIES if M.at[i, k]), "NONE") for i in M.index]
    ep["secondary_context"] = [";".join(k for k in FP_CATEGORIES if M.at[i, k] and k != p) or "NONE"
                               for i, p in zip(M.index, ep.primary_context)]
    clean = ep.primary_context.eq("NONE")
    if cfg.mv_mode == "maha":
        abnormal = clean & ep.multivariate_supported
    else:
        abnormal = clean & (ep.family_count >= cfg.min_families)
        if cfg.mv_mode == "both":
            abnormal &= ep.multivariate_supported
    if cfg.load_mode == "independent_only":
        abnormal &= ep.load_context.eq("LOAD_INDEPENDENT")
    in_sample = ep.reference_state.eq("IN_SAMPLE_REFERENCE")
    ep["classification"] = np.where(abnormal & in_sample, CALIBRATION_LABEL,
                                    np.where(abnormal, FINAL_LABEL,
                                             np.where(clean, "UNCONFIRMED_KPI_ELEVATION", ep.primary_context)))
    ep["in_final_set"] = abnormal & ep.reference_state.eq("OUT_OF_SAMPLE")
    return ep


# ============================================================================== severity and confidence
def severity(ep: pd.DataFrame, ref: dict, cfg: P6Config) -> pd.DataFrame:
    """severity_score = 0.4 peak + 0.3 persistence + 0.3 breadth, each in [0, 1]:
         peak        = clip((peak_kpi - cut) / (band_hi - cut))          cut = training P90, band_hi = training P99
         persistence = clip(kpi_integral / ((band_hi - cut) x 6 h))      a 6-h stay at the P99 level = 1
         breadth     = family_count / 5
       severity_class: HIGH = peak >= band_hi AND duration >= 6 h (the KPI persistence window); MODERATE = one of the
       two; LOW = neither. A descriptive magnitude, never a probability of any plant condition."""
    ep = ep.copy()
    thr = cut_of(cfg, ref)
    hi = ref["hi"] if np.isnan(cfg.hi) else cfg.hi
    if cfg.kpi_col == "MAHA" and np.isnan(cfg.hi):
        hi = MAHA_SEVERITY_HI
    ep["sev_peak"] = ((ep.peak_kpi - thr) / (hi - thr)).clip(0, 1)
    ep["sev_persistence"] = (ep.kpi_integral / ((hi - thr) * 6.0)).clip(0, 1)
    ep["sev_breadth"] = ep.family_count / len(FAMILIES)
    ep["severity_score"] = 0.4 * ep.sev_peak + 0.3 * ep.sev_persistence + 0.3 * ep.sev_breadth
    a, b = ep.peak_kpi >= hi, ep.duration_minutes >= 360
    ep["severity_class"] = np.select([a & b, a | b], ["HIGH", "MODERATE"], "LOW")
    return ep


# Scored parts. Reported but NOT averaged: sp_heat_fg_agreement (the K cut is nominal for the F / G KPIs, which have
# their own anchors) and band_margin (Phase 3 kpi_confidence already contains near_band_boundary - no double count).
CONF_PARTS = ("conf_dq", "conf_family", "conf_multivariate", "conf_change_point", "conf_kpi_quality",
              "conf_robustness")
CONF_DESCRIPTIVE = ("sp_heat_fg_agreement", "band_margin")
MAHA_SEVERITY_HI = 60.0   # nominal P99-like anchor for the Mahalanobis-led SENSITIVITY variant only (never primary)
CONF_CAP = "CAPPED_MEDIUM: NO_EVENT_GROUND_TRUTH; STATE_PROXY_UNCONFIRMED; FAMILIES_ARE_KPI_INPUTS"


def confidence(ep: pd.DataFrame, g: pd.DataFrame, ref: dict) -> pd.DataFrame:
    """confidence_score = mean of the available parts (each in [0, 1]); separate from severity. Class HIGH needs
    score >= 0.75, robustness >= 0.7 and >= 2 families, LOW < 0.5, else MEDIUM - then CAPPED AT MEDIUM (no ground truth,
    unconfirmed state proxy, and the families are the KPI's own inputs, so agreement is partly internal consistency)."""
    ep = ep.copy()
    kc = g.kpi_conf.to_numpy()
    nb = g.near_bnd.fillna(False).to_numpy(bool)
    KF, KG = g.K_F.to_numpy(float), g.K_G.to_numpy(float)
    parts = {p: [] for p in CONF_PARTS + CONF_DESCRIPTIVE}
    for r in ep.itertuples():
        seg = slice(int(r.pos_start), int(r.pos_end) + 1)
        parts["conf_dq"].append(1 - r.data_quality_contamination)
        parts["conf_family"].append(r.family_agreement if np.isfinite(r.family_agreement) else 0.0)
        parts["conf_multivariate"].append(r.maha_share_above)
        parts["conf_change_point"].append(float(r.change_point_supported))
        parts["conf_kpi_quality"].append(share(kc[seg] == "HIGH"))
        if np.isfinite(KF[seg]).any() and np.isfinite(KG[seg]).any():
            parts["sp_heat_fg_agreement"].append(float(np.nanmax(KF[seg]) >= ref["thr"]
                                                       and np.nanmax(KG[seg]) >= ref["thr"]))
        else:
            parts["sp_heat_fg_agreement"].append(float("nan"))
        parts["band_margin"].append(1 - share(nb[seg]))
        parts["conf_robustness"].append(getattr(r, "robustness_score", float("nan")))
    for p, v in parts.items():
        ep[p] = v
    ep["confidence_score"] = ep[list(CONF_PARTS)].mean(axis=1, skipna=True)
    rob = ep["robustness_score"].fillna(0) if "robustness_score" in ep else pd.Series(0.0, index=ep.index)
    raw = np.select([(ep.confidence_score >= 0.75) & (rob >= 0.7) & (ep.family_count >= 2), ep.confidence_score < 0.5],
                    ["HIGH", "LOW"], "MEDIUM")
    ep["confidence_uncapped"] = raw
    ep["confidence"] = np.where(raw == "HIGH", "MEDIUM", raw)
    ep["confidence_cap_reason"] = np.where(raw == "HIGH", CONF_CAP, "")
    return ep


# ============================================================================== types
TYPE_BY_CONTEXT = {"STARTUP": "TRANSITIONAL", "RESTART": "TRANSITIONAL", "SHUTDOWN": "TRANSITIONAL",
                   "NORMAL_LOAD_CHANGE": "LOAD_ASSOCIATED", "DATA_QUALITY_ARTIFACT": "DATA_QUALITY",
                   "INSUFFICIENT_DATA": "DATA_QUALITY", "AFR_TRANSITION": "AFR_CONTEXT",
                   "CONTROL_ACTION": "CONTROL_CONTEXT", "SHORT_TRANSIENT": "SHORT_TRANSIENT"}


def episode_type(ep: pd.DataFrame) -> pd.DataFrame:
    """Rule-based empirical type (analytical category, never a plant failure mode). Dominance uses the family deviation
    RATIO (episode median S_d / its own training P90), so the 0.5 KPI weight of efficiency does not decide it.
    MULTI_FAMILY: >= 3 deviating families and the top two ratios within 0.25 of each other."""
    ep = ep.copy()
    R = ep[[f"{d.lower()}_deviation" for d in FAMILIES]].to_numpy(float)
    R = np.where(np.isfinite(R), R, -np.inf)
    top = np.argmax(R, axis=1)
    srt = np.sort(R, axis=1)
    types, dom = [], []
    for i, r in enumerate(ep.itertuples()):
        d = FAMILIES[top[i]] if np.isfinite(R[i, top[i]]) else "NONE"
        dom.append(d)
        if r.primary_context != "NONE":
            types.append(TYPE_BY_CONTEXT[r.primary_context])
        elif r.family_count >= 3 and srt[i, -1] - srt[i, -2] < 0.25:
            types.append("MULTI_FAMILY")
        elif r.family_count >= 1:
            types.append(f"{d}_DOMINANT")
        else:
            types.append("KPI_AGGREGATE_ONLY")
    ep["dominant_family"] = dom
    ep["episode_type"] = types
    return ep


# ============================================================================== pre-event windows (historical only)
PRE_OFFSETS = (("T-12h", 720), ("T-6h", 360), ("T-3h", 180), ("T-2h", 120), ("T-1h", 60), ("T-30m", 30), ("T", 0))


def signal_table(g: pd.DataFrame, ref: dict) -> dict:
    """name -> (values, family, exceed flags, rule). Every exceedance uses bucket t (or trailing windows) only."""
    coal = (g.coal_kiln + g.coal_pc).to_numpy(float)
    feed = g.feed.to_numpy(float)
    K, D, M = g.K.to_numpy(float), g.D.to_numpy(float), g.MAHA.to_numpy(float)
    t = {"KPI": (K, "KPI", K >= ref["thr"], f"KPI >= {ref['thr']:.2f} (training P90 cut)"),
         "D": (D, "KPI", D > ref["D_q90"], f"raw deviation D > {ref['D_q90']:.3f} (training P90)"),
         "MAHA": (M, "MULTIVARIATE", M >= 50.0, "Mahalanobis KPI >= 50 (training P95)")}
    for d in FAMILIES:
        v = g[f"S_{d}"].to_numpy(float)
        t[f"S_{d}"] = (v, d, v > ref["family_p90"][d], f"S_{d} > {ref['family_p90'][d]:.3f} (training P90 of window S)")
    fc, cc = abs_change(feed, 6), abs_change(coal, 6)
    t["FEED_CHANGE_1H"] = (fc, "LOAD", fc >= ref["feed_d60m_p90"],
                           f"|1-h feed change| >= {ref['feed_d60m_p90']:.1f} TPH (training P90)")
    t["COAL_CHANGE_1H"] = (cc, "FUEL_CONTROL", cc >= ref["coal_total_d60m_p90"],
                           f"|1-h coal kiln + PC change| >= {ref['coal_total_d60m_p90']:.2f} TPH (training P90)")
    for col in ("speed", "clinker"):
        v = g[col].to_numpy(float)
        z = (v - ref["load"][col]["median"]) / ref["load"][col]["mad"]
        t[col.upper()] = (v, "LOAD", np.abs(z) >= 3.0, f"|robust z of {col} vs training| >= 3")
    t["AFR"] = (g.afr.to_numpy(float), "AFR_CONTEXT", None, "level only (transitions reported as EVENT rows)")
    p4 = g.p4.to_numpy(float)
    t["P4_INDICATOR"] = (p4, "PHASE4_CONTEXT", p4 >= ref["p4_threshold"],
                         f"{ref['p4_indicator']} >= {ref['p4_threshold']:.3f} (Phase 4 discovery P90; LOW confidence)")
    return t


def pre_event(g: pd.DataFrame, ep: pd.DataFrame, ref: dict, events: pd.DataFrame) -> pd.DataFrame:
    """Per episode, T = onset_time. SNAPSHOT rows: the bucket ending at T - offset (strictly before the onset bucket).
    FIRST_EXCEEDANCE rows: earliest bucket in (T - 12 h, T] above the signal's frozen rule (lead = minutes before T).
    EVENT rows: Phase 5 AFR transitions and Phase 2 stops / restarts in [T - 12 h, T). KPI_TURNING_POINT: the minimum
    KPI bucket in the window. Only data up to T is used; nothing here defines the episode."""
    tab = signal_table(g, ref)
    ix = g.index
    rows = []
    for r in ep.itertuples():
        on = int(r.pos_onset)
        T = r.onset_time
        lo = max(0, on - 72)
        for name, (v, fam, ex, rule) in tab.items():
            p12 = on - 1 - 72
            base = v[p12] if p12 >= 0 else np.nan
            for lab, off in PRE_OFFSETS:
                p = on - 1 - off // 10
                if p < 0:
                    continue
                rows.append({"episode_id": r.episode_id, "row_type": "SNAPSHOT", "signal": name, "family": fam,
                             "offset_label": lab, "offset_minutes": -off, "bucket_end": ix[p], "value": v[p],
                             "exceeded": bool(ex[p]) if ex is not None else None,
                             "delta_vs_t12h": v[p] - base, "rule": rule})
            if ex is None or on - lo < 1:
                continue
            w = ex[lo:on]
            hit = np.flatnonzero(w)
            rows.append({"episode_id": r.episode_id, "row_type": "FIRST_EXCEEDANCE", "signal": name, "family": fam,
                         "offset_label": "T-12h..T",
                         "lead_minutes_before_onset": float((on - 1 - (lo + hit[0])) * 10) if hit.size else np.nan,
                         "exceeded": bool(hit.size), "share_exceeded_12h": float(w.mean()),
                         "active_at_T": bool(w[-1]), "rule": rule})
        k = g.K.to_numpy(float)[lo:on]
        if np.isfinite(k).any():
            p = lo + int(np.nanargmin(k))
            rows.append({"episode_id": r.episode_id, "row_type": "KPI_TURNING_POINT", "signal": "KPI", "family": "KPI",
                         "offset_label": "T-12h..T", "bucket_end": ix[p], "value": k[p - lo],
                         "lead_minutes_before_onset": float((on - 1 - p) * 10),
                         "rule": "minimum KPI bucket in the 12 h before onset (start of the rise)"})
        ev = events[(events.event_time >= T - pd.Timedelta(hours=12)) & (events.event_time < T)]
        for e in ev.itertuples():
            rows.append({"episode_id": r.episode_id, "row_type": "EVENT", "signal": e.kind,
                         "family": "AFR_CONTEXT" if e.kind.startswith("AFR_") else "OPERATING_STATE",
                         "offset_label": "T-12h..T", "bucket_end": e.event_time,
                         "lead_minutes_before_onset": float((T - e.event_time) / pd.Timedelta(minutes=1)),
                         "rule": f"{e.event_id} ({e.status}) - context only"})
    return pd.DataFrame(rows)


# ============================================================================== full pipeline (sensitivity / leakage)
def run_pipeline(inp: dict, cfg: P6Config = PRIMARY) -> pd.DataFrame:
    """grid + events + DQ windows + frozen reference -> classified, typed, severity-scored candidate episodes."""
    g, ref = inp["grid"], inp["ref"]
    ep = build_episodes(g, cfg, ref, inp["events"], inp["dq_windows"])
    if ep.empty:
        return ep
    ep = add_context(ep, g, cfg, ref, inp["events"], inp["dq_windows"])
    ep = severity(ep, ref, cfg)
    ep = episode_type(ep)
    ep.insert(0, "episode_id", [f"P6-{i + 1:03d}" for i in range(len(ep))])
    return ep


def truncate(inp: dict, t_cut: pd.Timestamp) -> dict:
    """Inputs as they would have existed at t_cut (grid rows <= t_cut; events and DQ windows known by t_cut)."""
    ev, w = inp["events"], inp["dq_windows"]
    return {"grid": inp["grid"][inp["grid"].index <= t_cut], "events": ev[ev.event_time <= t_cut].copy(),
            "dq_windows": w[w.start <= t_cut].copy(), "ref": inp["ref"]}


def overlaps(a: pd.DataFrame, b: pd.DataFrame) -> np.ndarray:
    """For each episode in a: True if any episode in b overlaps it in time."""
    if a.empty:
        return np.zeros(0, bool)
    if b.empty:
        return np.zeros(len(a), bool)
    bs, be = b.start_time.to_numpy(), b.end_time.to_numpy()
    return np.array([bool(np.any((bs < e) & (be > s))) for s, e in zip(a.start_time.to_numpy(), a.end_time.to_numpy())])


def bucket_set(ep: pd.DataFrame) -> set:
    return {p for s, e in zip(ep.pos_start, ep.pos_end) for p in range(int(s), int(e) + 1)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


# ============================================================================== plant event ground truth (future)
PLANT_EVENT_LOG = PHASE_DIR / "inputs" / "plant_event_log.csv"
PLANT_EVENT_COLUMNS = ("event_id", "event_type", "start_time", "end_time", "source", "description")


def load_plant_events(path: Path = PLANT_EVENT_LOG) -> pd.DataFrame | None:
    """Future integration point. Returns None (ground_truth_available = False) unless the plant supplies a real log with
    PLANT_EVENT_COLUMNS. No synthetic record is ever created by the pipeline."""
    if not path.exists():
        return None
    ev = pd.read_csv(path, parse_dates=["start_time", "end_time"])
    missing = set(PLANT_EVENT_COLUMNS) - set(ev.columns)
    if missing:
        raise ValueError(f"plant event log {path} lacks columns {sorted(missing)}")
    return ev


def match_plant_events(ep: pd.DataFrame, events: pd.DataFrame | None, min_overlap: float = 0.5) -> pd.DataFrame:
    """Per episode: MATCHED (>= min_overlap of the episode inside one plant event), PARTIAL_OVERLAP, NO_MATCH; every field
    NOT_AVAILABLE when no log exists. Supervised performance metrics are deliberately not computed here."""
    out = pd.DataFrame({"episode_id": ep.episode_id})
    if events is None:
        out["event_ground_truth_status"] = GT_STATUS
        for c in ("plant_event_type", "plant_event_start", "plant_event_end", "plant_event_source", "event_match_status"):
            out[c] = GT_STATUS
        return out
    rows = []
    for r in ep.itertuples():
        ov = events[(events.start_time < r.end_time) & (events.end_time > r.start_time)]
        if ov.empty:
            rows.append({"event_match_status": "NO_MATCH"})
            continue
        dur = (r.end_time - r.start_time) / pd.Timedelta(minutes=1)
        inter = [(min(r.end_time, e.end_time) - max(r.start_time, e.start_time)) / pd.Timedelta(minutes=1)
                 for e in ov.itertuples()]
        best = ov.iloc[int(np.argmax(inter))]
        rows.append({"plant_event_type": best.event_type, "plant_event_start": best.start_time,
                     "plant_event_end": best.end_time, "plant_event_source": best.source,
                     "event_match_status": "MATCHED" if max(inter) / dur >= min_overlap else "PARTIAL_OVERLAP"})
    out = pd.concat([out, pd.DataFrame(rows)], axis=1)
    out["event_ground_truth_status"] = "AVAILABLE"
    return out


def evidence_summary(r, ref: dict) -> str:
    """Plain-language, investigable line per episode: when, what moved (direction), how much, context, what to check.
    Investigation prompts only - never an operating or set-point recommendation."""
    f = "%d %b %H:%M"
    parts = [f"Onset {r.onset_time:{f}} (CUSUM), detected {r.detection_time:{f}}, {r.duration_minutes / 60:.1f} h",
             f"KPI peak {r.peak_kpi:.1f} vs cut {ref['thr']:.1f} (training P99 {ref['hi']:.1f})"]
    if isinstance(getattr(r, "top_tags", None), str) and r.top_tags:
        parts.append(f"largest deviations: {r.top_tags}")
    parts.append(f"{r.family_count}/{r.number_of_valid_families} process families above their training P90"
                 + (f" ({r.deviating_families})" if r.deviating_families != "NONE" else ""))
    load = f"load {r.load_context}"
    if np.isfinite(r.feed_change_vs_pre2h):
        load += f" (feed {r.feed_change_vs_pre2h:+.0f} TPH vs the 2 h before onset)"
    parts.append(load)
    if r.afr_context != "NO_AFR_TRANSITION":
        parts.append(f"AFR transitions in the window: {r.afr_context} (context; causal role not assessed)")
    parts.append(f"context rule: {r.primary_context}" if r.primary_context != "NONE"
                 else "no ordinary-transition rule matched")
    if isinstance(getattr(r, "post_event_outcome", None), str):
        parts.append(f"after the end: {r.post_event_outcome}")
    check = [f"shift / operating log {r.onset_time:{f}} - {r.end_time:{f}}"]
    if r.load_context == "LOAD_ASSOCIATED":
        check.append("whether the feed change was planned and whether it came before or after the process symptoms")
    if isinstance(getattr(r, "top_tags", None), str) and r.top_tags:
        check.append("analyser / instrument status of the largest-deviation tags")
    parts.append("to check against plant records: " + "; ".join(check))
    return "; ".join(parts) + ". Empirical POC period, not a validated plant event."


# ============================================================================== wording guard
FORBIDDEN = [r"\bconfirmed (deposit|ring|coating|failure|plant event)s?\b", r"\b(deposit|ring|failure) probability\b",
             r"\bprobability of (failure|deposit|ring)\b", r"\bcaus(e|es|ed|ing)\b", r"\bplant limit\b",
             r"\brecommend(ed)? (set-?point|operating)\b", r"\bdue to AFR\b"]
ALLOWED_CONTEXT = ("not ", "**not**", "no ", "never", "n't", "cannot", "not_available", "must not", "neither", "without",
                   "rather than", "≠")


def forbidden_hits(text: str) -> list[str]:
    """Unsupported-claim scanner: returns offending lines (lines that only negate / qualify the term are allowed)."""
    hits = []
    for line in text.splitlines():
        for pat in FORBIDDEN:
            if re.search(pat, line, flags=re.IGNORECASE) and not any(a in line.lower() for a in ALLOWED_CONTEXT):
                hits.append(line.strip()[:160])
                break
    return hits
