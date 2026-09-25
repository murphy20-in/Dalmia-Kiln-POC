"""Shared configuration and helpers for Phase 2 (Normal Operating Baseline).

Source data is READ-ONLY. Phase 2 writes only to:
  phase-02-baseline/{outputs,reports,cache}, data/processed, data/curated

All thresholds below are POC ANALYTICAL HEURISTICS. They are NOT plant
engineering, alarm, safety or control limits.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "phase-02-baseline"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
CACHE = PHASE_DIR / "cache"
PROCESSED = ROOT / "data" / "processed"
CURATED = ROOT / "data" / "curated"
RAW = ROOT / "data" / "raw"
P1_OUT = ROOT / "phase-01-data-discovery" / "outputs"
P1_SCRIPTS = ROOT / "phase-01-data-discovery" / "scripts"
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")

for _d in (OUT, REPORTS, FIG, CACHE, PROCESSED, CURATED):
    _d.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------- POC ANALYTICAL HEURISTICS
H = {
    "running_B_value": 0.02,          # observed 'Kiln MD' value co-occurring with feed/speed (POC PROXY)
    "stopped_B_value": 0.0,
    "pre_stop_window_min": 60,        # minutes before a RUNNING->STOPPED change treated as transition
    "ramp_ref_quantile": 0.25,        # restart ramp ends when the signal regains the P25 of its own
    "ramp_ref_minutes": 1440,         #   last 1440 RUNNING minutes before that stop (excl. pre-stop window,
    "ramp_ref_lookback_days": 7,      #   searched up to 7 days back) ...
    "ramp_sustain_min": 60,           # ... for 60 consecutive minutes
    "ramp_max_search_h": 48,          # search never crosses the next stop; capped at 48 h
    "rolling_windows_min": [15, 60],
    "mv_bucket_min": 10,              # multivariate grain (10-minute medians)
    "mv_bucket_min_valid": 8,         # >= 8 of 10 minutes valid
    "band_mad_k": 3.0,                # robust band = median +/- k * 1.4826 * MAD
    "outlier_sensitivity_ratio": 1.5, # std / (1.4826*MAD) above this => mean/std sensitive to extremes
    "drift_mad_units": 1.0,           # |month median - prior median| / prior scaled MAD
    "bootstrap_reps": 400,
    "seed": 20250401,
    "regime_min_dwell_min": 60,
    "regime_ashman_d": 2.0,
    "regime_bootstrap_min_share": 0.6, # bands are ROBUST only if >= 60 % of resamples reproduce the band count
}
PROXY_LABEL = "POC PROXY — UNCONFIRMED"
COMPOSITE_LABEL = "POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED"
BAND_LABEL = "POC BASELINE REFERENCE BAND — NOT AN ENGINEERING / ALARM / CONTROL LIMIT"
MAD_SCALE = 1.4826


def log(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        stream=sys.stdout, force=False)
    return logging.getLogger(name)


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def jdump(o) -> str:
    return json.dumps(o, default=str, ensure_ascii=False)


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    df.to_csv(p, index=False)
    (lg or log("p2")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def read_p1(name: str) -> pd.DataFrame:
    return pd.read_csv(P1_OUT / name, low_memory=False)


def read_out(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name, low_memory=False)


def dataset_key(eq: str) -> str:
    return eq.lower().replace(" ", "_").replace("-", "_")


def processed_path(eq: str) -> Path:
    return PROCESSED / f"{dataset_key(eq)}.parquet"


def curated_path(eq: str) -> Path:
    return CURATED / f"{dataset_key(eq)}_baseline.parquet"


def load_processed(eq: str, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(processed_path(eq), columns=columns)


def datasets() -> list[str]:
    m = pd.read_csv(OUT / "processed_dataset_manifest.csv")
    return sorted(m.dataset.unique())


def mad(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    if x.size == 0:
        return np.nan
    return float(np.median(np.abs(x - np.median(x))))


def segments(ts: pd.Series, step_s: float = 60.0) -> pd.Series:
    """Contiguous segment id: increments whenever the step between consecutive distinct
    timestamps differs from step_s. Rolling windows must never cross a segment boundary."""
    d = ts.diff().dt.total_seconds()
    return (d.ne(step_s)).cumsum()


# Key tags for figures (real Phase 1 columns; verified against tag_contract at runtime)
KEY_TAGS = [("Kiln-I", "C"), ("Kiln-I", "O"), ("Kiln-I", "AF"), ("Kiln-I", "H"), ("Kiln-I", "K"), ("Kiln-I", "X"),
            ("Kiln-I", "G"), ("Kiln-I", "R"), ("Kiln-IA", "C"), ("Kiln-II", "S"), ("Kiln-IIIA", "M"), ("IKN Cooler-I", "C")]


def wide_included(eq: str) -> tuple[pd.DataFrame, pd.Series, dict, pd.Series]:
    """Wide 1-minute frame of INCLUDED values only (others NaN), one row per distinct kept timestamp.
    Returns (values, segment_id per ts, {col: original_name}, row_repeat_prev per ts)."""
    d = load_processed(eq, ["ts", "source_column", "original_name", "value", "baseline_status", "dup_status", "segment_id",
                            "row_repeat_prev"])
    d = d[d.ts.notna() & d.dup_status.isin(["UNIQUE", "DUP_KEPT", "DUP_CONFLICT"])]
    names = d.drop_duplicates("source_column").set_index("source_column").original_name.astype(str).to_dict()
    v = d.value.where(d.baseline_status == "INCLUDED")
    w = pd.DataFrame({"ts": d.ts, "c": d.source_column.astype(str), "v": v}).pivot_table(
        index="ts", columns="c", values="v", aggfunc="first", dropna=False)
    seg = d.drop_duplicates("ts").set_index("ts").segment_id.reindex(w.index)
    rep = d.drop_duplicates("ts").set_index("ts").row_repeat_prev.reindex(w.index).fillna(False).astype(bool)
    return w.sort_index(), seg.sort_index(), names, rep.sort_index()


def prior_compare(vals: np.ndarray, tsv: np.ndarray, period_start, period_median: float, period_iqr: float,
                  resolution: float) -> dict:
    """Compare one period with ALL values strictly before period_start (no look-ahead).
    Scale floor: max(scaled MAD, IQR/1.349, value resolution, 1 % of |prior median|).
    Needs >= 30 distinct prior days, otherwise NOT EVALUABLE."""
    pmask = tsv < np.datetime64(period_start)
    prior = vals[pmask]
    prior_days = int(pd.unique(tsv[pmask].astype("datetime64[D]")).size)
    if prior_days < 30:
        return {"prior_days": prior_days, "observation": f"NOT EVALUABLE (prior reference < 30 days: {prior_days})"}
    pm = float(np.median(prior))
    ps = float(MAD_SCALE * np.median(np.abs(prior - pm)))
    pq = np.quantile(prior, [0.25, 0.75])
    scale = max(ps, float(pq[1] - pq[0]) / 1.349, resolution, 0.01 * abs(pm))
    sh = (period_median - pm) / scale if scale > 0 else np.nan
    return {"prior_reference": "all INCLUDED values strictly before period_start", "prior_n": int(prior.size),
            "prior_days": prior_days, "prior_median": pm, "prior_scaled_mad": ps, "prior_scale_floored": scale,
            "shift_in_prior_scaled_mad": sh,
            "iqr_ratio_vs_prior": period_iqr / float(pq[1] - pq[0]) if pq[1] > pq[0] else np.nan,
            "observation": ("NOTABLE LEVEL SHIFT (descriptive)" if np.isfinite(sh) and abs(sh) >= H["drift_mad_units"]
                            else "WITHIN 1 PRIOR SCALE" if np.isfinite(sh) else "NOT EVALUABLE (prior scale = 0)")}


def value_resolution(vals: np.ndarray) -> float:
    u = np.unique(vals[~np.isnan(vals)])
    return float(np.min(np.diff(u))) if u.size > 1 else 0.0
