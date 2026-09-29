"""Shared paths, configuration, labels and I/O helpers for Phase 8 (Early Warning Validation).

Named p8common (the p3common / p4common convention) because Phase 7 modules do `from common import ...`: a Phase 8
module called `common` would shadow Phase 7's. For the same reason Phase 8 never imports Phase 7's calibration /
robustness / validation / report_generation modules (Phase 8 has its own modules with those names).

Phase 8 is READ-ONLY with respect to the source workbooks and Phases 1-7. It writes only to
  phase-08-early-warning/{outputs,reports,cache}
Phase 7 code is imported read-only (bytecode writing disabled first; Phase 7's script dir is APPENDED to sys.path so
Phase 8 modules win a name clash). The Phase 7 score is FROZEN: nothing here changes weights, features, references,
bands or scoring. The O2-excluded score is a VALIDATION_VARIANT built with Phase 7's own variant definition.

TERMINOLOGY. The 12 Phase 6 periods are EMPIRICAL_ABNORMAL_PERIODS (not plant events). Coverage is
EMPIRICAL_ABNORMAL_PERIOD_COVERAGE; time flagged in ordinary running is EMPIRICAL_ALERT_RATE. There is no event
ground truth, so there are no error rates of a detector here.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import logging  # noqa: E402
import re  # noqa: E402
from dataclasses import asdict, dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "phase-08-early-warning"
SCRIPTS = PHASE_DIR / "scripts"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
DOCS = PHASE_DIR / "docs"
CACHE = PHASE_DIR / "cache"
P7_DIR = ROOT / "phase-07-risk-score"
P7_OUT = P7_DIR / "outputs"
P6_OUT = ROOT / "phase-06-abnormal-events" / "outputs"
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")

for _d in (OUT, REPORTS, FIG, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

if not (P7_DIR / "scripts" / "risk_core.py").is_file():
    raise RuntimeError("Phase 7 scripts missing - Phase 8 never creates upstream files")
if str(P7_DIR / "scripts") not in sys.path:
    sys.path.append(str(P7_DIR / "scripts"))

import common as p7c  # noqa: E402  (Phase 7, read-only; brings abn_core / indicator_core / p3common)
import reference_builder  # noqa: E402  (Phase 7, read-only: fit_reference for the O2-excluded VALIDATION_VARIANT)
import risk_core  # noqa: E402  (Phase 7, read-only: score_frame / score_core)

ac, ic = p7c.ac, p7c.ic

VERSION = "p8-ew-1.0.0"
SCORE_VERSION = p7c.SCORE_VERSION
O2_TAG = p7c.O2_TAG
FAMILIES = p7c.FAMILIES
MONTHS = p7c.MONTHS                                   # {6: JUN, 7: JUL, 8: AUG}
STATUSES = ("SUPPORTED", "WEAK", "NOT_SUPPORTED", "INSUFFICIENT_DATA", "BLOCKED")
EVENT_DQ = ("VALID", "VALID_REDUCED_CONFIDENCE", "NOT_EVALUABLE", "INSUFFICIENT_DATA", "TRANSITION_CONTAMINATED",
            "DATA_QUALITY_CONTAMINATED")
EVALUABLE = ("VALID", "VALID_REDUCED_CONFIDENCE")
WARNINGS = ("W1_RANK", "W2_RISING", "W3_PERSISTENT", "W4_ACCEL", "W5_MULTI_FAMILY")
POPULATION = "EMPIRICAL_ABNORMAL_PERIODS (Phase 6 final set; NOT plant events)"
# the only score columns Phase 8 reads. afr_context (RETROSPECTIVE labels) is deliberately absent (leakage test L7)
SCORE_COLUMNS = ("timestamp", "risk_score", "operational", "confidence_score", "confidence_band", "risk_status",
                 "reference_state", "load_band", "load_context", "feed_tph", "kpi_value", "family_count_abnormal",
                 "family_count_usable", "persistence_minutes", "data_quality_status", "secondary_reasons",
                 "contributing_families", "phase4_context", "score_version", "reference_version")
P7_FROZEN = ("risk_score_reference.json", "risk_score_variant_references.json", "risk_score_bands.csv",
             "risk_score_feature_inventory.csv")
P7_REQUIRED = ("risk_scores.parquet", "risk_score_components.parquet", "risk_score_confidence.parquet",
               "risk_score_reasons.parquet") + P7_FROZEN
P7_CACHE = P7_DIR / "cache"
P7_CACHE_INPUTS = ("grid.parquet", "episodes.parquet", "afr_events.parquet", "dq_windows.parquet", "context_meta.json")


@dataclass(frozen=True)
class P8Config:
    """Every analytical choice of Phase 8, pre-declared in docs/EARLY_WARNING_VALIDATION_SPEC.md."""
    horizons: tuple = (15, 30, 60, 120, 240, 360, 720, 1440)     # minutes
    primary_h: int = 60
    offsets: tuple = (1440, 720, 360, 240, 120, 60, 30, 15, 0)     # trajectory snapshots, minutes before T0
    lookback_min: int = 1440                                       # lead-time look-back
    ctrl_post_end_h: float = 6.0                                   # control exclusion after any candidate end
    ctrl_pre_onset_h: float = 24.0                                 # control exclusion before any final onset
    gap_tol_buckets: int = 2                                       # warning episodes merge across <= 20 min
    slope_buckets: int = 7                                         # OLS slope over [t - 60 min, t]
    slope_min_valid: int = 5
    accel_lag: int = 6
    w1_rank: float = 0.95
    w3_rank: float = 0.75
    w3_min_buckets: int = 6
    calib_q: float = 0.95
    w5_families: int = 2
    roll_days: int = 7                                             # reference-free rolling rank over (t-7d, t-1d]
    roll_exclude_h: int = 24
    roll_min: int = 144
    min_events_primary: int = 8
    min_events_secondary: int = 6
    min_controls: int = 30
    loeo_q: float = 0.25
    n_boot: int = 2000
    n_null: int = 2000
    block_hours: int = 12
    block_sensitivity: tuple = (3, 6, 12, 24)
    min_shift_days: int = 7
    seed: int = 20250801

    def as_dict(self) -> dict:
        return asdict(self)


CFG = P8Config()


def nb(minutes: int) -> int:
    """Buckets in the window (T - minutes, T] on the 10-min grid (bucket-end labels)."""
    return max(1, -(-int(minutes) // 10))


def min_valid(n: int) -> int:
    return max(1, -(-2 * n // 3))


# ============================================================================== I/O
def log(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stdout)
    return logging.getLogger(name)


sha256 = p7c.sha256
round_frame = p7c.round_frame


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_csv(p, index=False)
    (lg or log("p8")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def write_parquet(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_parquet(p, index=False)
    (lg or log("p8")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


# ============================================================================== wording guard (extends Phase 7)
FORBIDDEN = p7c.FORBIDDEN + [r"\bfalse[- ]?(positive|negative)s?\b", r"\btrue[- ]positive", r"\bspecificity\b",
                             r"\baccurate predictor\b", r"\bvalidated deposit detector\b", r"\bfailure predictor\b",
                             r"\bproven\b", r"\bpredict(s|ed|ing)? (deposit|ring|failure|coating)s?\b",
                             r"\bdetection sensitivity\b"]


def forbidden_hits(text: str) -> list[str]:
    """Unsupported-claim scanner; a line that only negates / qualifies the term is allowed (Phase 6 / 7 rule)."""
    hits = []
    for line in text.splitlines():
        for pat in FORBIDDEN:
            if re.search(pat, line, flags=re.IGNORECASE) and not any(a in line.lower() for a in ac.ALLOWED_CONTEXT):
                hits.append(line.strip()[:160])
                break
    return hits
