"""Shared paths, configuration, labels and helpers for Phase 4 (Leading Indicators).

Phase 4 is READ-ONLY with respect to the source data and to Phases 1-3. It writes only to
  phase-04-leading-indicators/{outputs,reports,cache}

Phase 3 code (kpi_core, p3common, load_phase2_inputs.load_dataset) is imported read-only so that masks, operating
state and bucketing are exactly the leakage-tested Phase 3 behaviour. Importing it must not write anything into
phase-03-efficiency-kpi: bytecode writing is disabled before the import and the Phase 3 script directory is APPENDED
to sys.path (Phase 4 modules with the same file name - sensitivity_analysis, generate_report - take precedence).

Every number in P4Config is a POC ANALYTICAL HEURISTIC or a design choice, declared before looking at the evaluation
months. None is a plant engineering, alarm, safety or control limit. Nothing here leaves the local machine.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True                    # never write __pycache__ into phase-03 (or anywhere)

import hashlib  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
from dataclasses import asdict, dataclass, replace  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "phase-04-leading-indicators"
SCRIPTS = PHASE_DIR / "scripts"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
CACHE = PHASE_DIR / "cache"
P3_DIR = ROOT / "phase-03-efficiency-kpi"
P3_OUT = P3_DIR / "outputs"
P3_SCRIPTS = P3_DIR / "scripts"
P2_OUT = ROOT / "phase-02-baseline" / "outputs"
P1_OUT = ROOT / "phase-01-data-discovery" / "outputs"
PROCESSED = ROOT / "data" / "processed"
CURATED = ROOT / "data" / "curated"
RAW = ROOT / "data" / "raw"
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")

for _d in (OUT, REPORTS, FIG, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

# Phase 3 import precondition: p3common creates its own dirs with exist_ok at import; they must already exist so the
# import is a no-op on disk (checked again by the G1 before/after snapshot).
for _d in (P3_OUT, P3_DIR / "reports" / "figures", P3_DIR / "cache"):
    if not _d.is_dir():
        raise RuntimeError(f"Phase 3 directory missing ({_d}); run Phase 3 first - Phase 4 never creates Phase 3 files")
if str(P3_SCRIPTS) not in sys.path:
    sys.path.append(str(P3_SCRIPTS))

import kpi_core  # noqa: E402,F401  (Phase 3, read-only)
import p3common  # noqa: E402,F401  (Phase 3, read-only)

METHOD_VERSION = "p4-li-1.0.0"
INDICATOR_LABEL = ("EMPIRICAL LEADING INDICATOR OF THE PHASE 3 POC KPI — NOT A VALIDATED PREDICTOR OF DEPOSITS, "
                   "RINGS, COATING, EQUIPMENT FAILURE OR OTHER PLANT EVENTS")
EPISODE_LABEL = "KPI DETERIORATION EPISODE (SYNTHETIC, FROM THE PHASE 3 KPI) — NOT A PLANT-CONFIRMED EVENT"
THRESHOLD_LABEL = "POC ANALYTICAL THRESHOLD (DISCOVERY QUANTILE) — NOT A PLANT ALARM / ENGINEERING LIMIT"
PROXY_LABEL = p3common.PROXY_LABEL
COMPOSITE_LABEL = p3common.COMPOSITE_LABEL

ALL_DATASETS = ["Kiln-I", "Kiln-IA", "Kiln-II", "Kiln-III", "Kiln-IIIA", "Kiln-IIIB", "IKN Cooler-I",
                "CBS-I", "CBS-II", "CBS-Calculation"]
STATE_DATASETS = list(p3common.KPI_DATASETS)          # state is rebuilt on exactly the Phase 3 subset
FEED_TAG = p3common.FEED_TAG

FEATURES = ("LEVEL_1H", "DEV_1H", "ROC_1H", "ROC_3H", "VOL_2H", "PERSIST_HI_6H", "PERSIST_LO_6H")
FEATURE_DOC = {
    "LEVEL_1H": ("Level", "median of RUNNING 10-min bucket medians over (t-60 min, t]; no load conditioning"),
    "DEV_1H": ("Deviation", "(LEVEL_1H - feed-conditional expected level) / robust scale; reference fitted on the "
                            "discovery window only (kpi_core.fit_tag, adjusted mode) and frozen"),
    "ROC_1H": ("Rate of change", "(LEVEL_1H(t) - LEVEL_1H(t-60 min)) / robust scale"),
    "ROC_3H": ("Rate of change", "(LEVEL_1H(t) - LEVEL_1H(t-180 min)) / robust scale"),
    "VOL_2H": ("Volatility", "log(1.4826 * MAD of bucket medians over (t-120 min, t] + eps) minus its discovery median"),
    "PERSIST_HI_6H": ("Persistence", "share of buckets in (t-6 h, t] whose load-adjusted bucket z exceeds the discovery "
                                      "P95 (POC analytical band)"),
    "PERSIST_LO_6H": ("Persistence", "share of buckets in (t-6 h, t] whose load-adjusted bucket z is below the discovery "
                                      "P05 (POC analytical band)"),
}
FEATURE_INTERPRETABILITY = {"LEVEL_1H": 1.0, "DEV_1H": 1.0, "ROC_1H": 0.75, "ROC_3H": 0.75,
                            "PERSIST_HI_6H": 0.75, "PERSIST_LO_6H": 0.75, "VOL_2H": 0.5}
MONTHS = ("JUN", "JUL", "AUG")
# Temporal design (MLE-H3): discovery chooses lag + sign; June-July (REPLICATION) decides the gates, criteria, score and
# set; August (HOLDOUT) is never used for gating, scoring, ranking or selection - it is a one-shot forward test.
REPLICATION_MONTHS = ("JUN", "JUL")
HOLDOUT = "AUG"


@dataclass(frozen=True)
class P4Config:
    """Every analytical choice of Phase 4. A variant = dataclasses.replace(PRIMARY, ...)."""
    name: str = "PRIMARY"
    disc_start: str = "2025-04-01 00:00"          # discovery = Phase 3 training window (in-sample KPI)
    disc_end: str = "2025-05-31 23:59"
    eval_jun: tuple = ("2025-06-01 06:00", "2025-06-30 23:59")   # first 6 h of June overlap training (P3 MLE-9)
    eval_jul: tuple = ("2025-07-01 00:00", "2025-07-31 23:59")
    eval_aug: tuple = ("2025-08-01 00:00", "2025-08-31 23:59")   # KPI ends 2025-08-23 (no Kiln-I September)
    bucket_min: int = 10
    lags: tuple = (10, 20, 30, 60, 120, 180, 240, 360, 480, 720)   # minutes; spec minimum + 240 / 480
    feat_min_cov: float = 0.5                     # rolling feature needs >= 50 % valid buckets in its window
    level_win: int = 60
    roc_wins: tuple = (60, 180)
    vol_win: int = 120
    persist_win: int = 360
    persist_q: tuple = (0.05, 0.95)
    z_cap: float = 10.0
    target: str = "primary"                       # "primary" | "F" | "G" | "alt_w_jun_jul15"
    target_kind: str = "change"                   # "change" (T1, primary) | "band_occupancy" (T2, sensitivity)
    target_smooth_buckets: int = 3                # K_f(t, H) = median of K over (t+H-30 min, t+H], >= 2 of 3
    use_controls: bool = True                     # partial rank association controlling for K(t), momentum, Kpend
    exclude_post_restart_h: float = 0.0           # operating-state sensitivity: drop t within X h after a transition
    exclude_pre_stop_h: float = 0.0               # sensitivity (analysis filter only): drop t within X h before a stop
    dq_filter: bool = False                       # missing-data sensitivity: keep only Phase 3 data_quality == GOOD
    block_days: int = 3                           # >= the 3-day autocorrelation horizon (MLE-M1); 1 day in sensitivity
    n_boot: int = 1000
    neff_maxlag: int = 432                        # 3 days of 10-min buckets
    fdr_q: float = 0.10
    fdr_q_high: float = 0.05
    strength_ref: float = 0.30                    # |rho| mapped to criterion value 1.0
    proxy_rho: float = 0.80                       # discovery |rho| with a KPI input -> KPI_PROXY tier
    load_proxy_rho: float = 0.80                  # discovery |rho| of LEVEL_1H with feed -> load proxy flag
    cluster_rho: float = 0.70
    max_set: int = 6
    incr_min_rho: float = 0.03
    disc_min_cov: float = 0.5
    disc_min_days: int = 20
    month_min_cov: float = 0.3
    flatline_max_share: float = 0.5
    ep_min_buckets: int = 6                       # E_BAND: >= 1 h in band code >= 1 ...
    ep_clear_h: int = 12                          # ... after 12 h with no code >= 1 (>= 50 % scored)
    rise_q: float = 0.95                          # E_RISE: 6-h KPI rise >= discovery P95 of 6-h rises
    ep_refractory_h: int = 12
    ep_window_h: int = 12
    ctrl_per_ep: int = 3
    alarm_q: float = 0.90                         # directional discovery quantile of the feature
    alarm_persist_buckets: int = 3                # alarm = beyond threshold for >= 30 min ...
    alarm_refractory_h: int = 2                   # ... after >= 2 h not beyond
    follow_h: int = 12                            # a lead is 'true' if the KPI deteriorates within 12 h
    seed: int = 20250601

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()[:12]

    def windows(self) -> dict[str, tuple[str, str]]:
        return {"DISCOVERY": (self.disc_start, self.disc_end), "JUN": self.eval_jun, "JUL": self.eval_jul,
                "AUG": self.eval_aug}


PRIMARY = P4Config()

# Pre-declared materiality rules for sensitivity comparisons (declared before looking at evaluation results).
MATERIALITY = {"score_spearman_min": 0.70, "set_jaccard_min": 0.50, "fg_rank_rho_min": 0.80,
               "sign_agreement_min": 0.80, "rho_ratio_min": 0.50}


def variant(**kw) -> P4Config:
    return replace(PRIMARY, **kw)


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


def round_frame(df: pd.DataFrame, nd: int = 6) -> pd.DataFrame:
    """Round floats so CSV bytes are stable across runs (last-bit BLAS / summation-order noise)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(nd)
    return out


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_csv(p, index=False)
    (lg or log("p4")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def write_parquet(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    df.to_parquet(p, index=False)
    (lg or log("p4")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def read_out(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name, low_memory=False)


def read_p3(name: str) -> pd.DataFrame:
    return pd.read_csv(P3_OUT / name, low_memory=False)


def read_p2(name: str) -> pd.DataFrame:
    return pd.read_csv(P2_OUT / name, low_memory=False)


def read_p1(name: str) -> pd.DataFrame:
    return pd.read_csv(P1_OUT / name, low_memory=False)


def jdump(o) -> str:
    return json.dumps(o, default=str, ensure_ascii=False, sort_keys=True, allow_nan=False)


def month_of(ts: pd.DatetimeIndex, cfg: P4Config = PRIMARY) -> np.ndarray:
    """Analysis window label of every timestamp: DISCOVERY / JUN / JUL / AUG / '' (outside every window)."""
    out = np.full(len(ts), "", dtype=object)
    for name, (a, b) in cfg.windows().items():
        m = (ts >= pd.Timestamp(a)) & (ts <= pd.Timestamp(b))
        out[m] = name
    return out


# Phase 3 inputs consumed by Phase 4 (hashed into indicator_version_manifest.csv; never modified).
P3_INPUTS = ["efficiency_deterioration_kpi.parquet", "kpi_component_scores.parquet", "kpi_reference.json",
             "kpi_reference_bands.csv", "kpi_definition.json", "kpi_candidate_inventory.csv", "kpi_validation.csv",
             "kpi_version_manifest.csv"]
P2_INPUTS = ["column_holds.csv", "baseline_confidence.csv", "baseline_family_readiness.csv", "baseline_stability.csv"]
P1_INPUTS = ["cross_dataset_identical_signals.csv", "unit_consistency_review.csv", "process_tag_inventory.csv"]
