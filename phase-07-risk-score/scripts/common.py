"""Shared paths, configuration, labels and I/O helpers for Phase 7 (Deposit / Inefficiency Risk Score).

Phase 7 is READ-ONLY with respect to the source workbooks and Phases 1-6. It writes only to
  phase-07-risk-score/{outputs,reports,cache}

Upstream code is imported read-only: bytecode writing is disabled first, then the Phase 6 script directory is APPENDED to
sys.path (abn_core appends Phase 4, which appends Phase 3), so Phase 7 modules always win on a name clash. Phase 7 never
creates or imports a module named generate_report or sensitivity_analysis (those names exist in several phases). Phase 6
path constants (OUT, CACHE, ...) are never imported by name - upstream modules are used through their namespace only.

TERMINOLOGY. The score is an EMPIRICAL POC RISK SCORE: how strongly the current condition resembles historical abnormal /
inefficient process behaviour relative to the frozen Apr-May reference. It is NOT a deposit, ring or failure probability,
NOT a plant limit and NOT a control or set-point recommendation. Every number in P7Config is a declared POC analytical
choice (docs/RISK_SCORE_SPEC.md), not a plant engineering, alarm or safety limit.
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

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "phase-07-risk-score"
SCRIPTS = PHASE_DIR / "scripts"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
DOCS = PHASE_DIR / "docs"
REVIEWS = PHASE_DIR / "reviews"
CACHE = PHASE_DIR / "cache"
P6_DIR = ROOT / "phase-06-abnormal-events"
P6_OUT = P6_DIR / "outputs"
P5_OUT = ROOT / "phase-05-af-analysis" / "outputs"
P4_DIR = ROOT / "phase-04-leading-indicators"
P4_OUT = P4_DIR / "outputs"
P3_DIR = ROOT / "phase-03-efficiency-kpi"
P3_OUT = P3_DIR / "outputs"
P2_OUT = ROOT / "phase-02-baseline" / "outputs"
P1_OUT = ROOT / "phase-01-data-discovery" / "outputs"
PROCESSED = ROOT / "data" / "processed"
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")

for _d in (OUT, REPORTS, FIG, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

# Import precondition: abn_core / p4common / p3common mkdir their own directories at import. They must already exist, so
# importing never creates anything upstream (checked by the G1 upstream snapshot).
for _d in (P6_OUT, P6_DIR / "reports" / "figures", P6_DIR / "cache", P4_OUT, P4_DIR / "reports" / "figures",
           P4_DIR / "cache", P3_OUT, P3_DIR / "reports" / "figures", P3_DIR / "cache"):
    if not _d.is_dir():
        raise RuntimeError(f"upstream directory missing ({_d}); run Phases 3-6 first - Phase 7 never creates upstream files")
if str(P6_DIR / "scripts") not in sys.path:
    sys.path.append(str(P6_DIR / "scripts"))

import abn_core as ac  # noqa: E402  (Phase 6, read-only; brings Phase 4 indicator_core / p4common and Phase 3 p3common)
import kpi_core  # noqa: E402  (Phase 3, read-only)

ic = ac.ic                      # Phase 4 indicator_core: causal trailing helpers, block-bootstrap weights
p3common = ac.p3common

SCORE_VERSION = "p7-risk-1.1.0"
SCORE_LABEL = ("EMPIRICAL POC RISK SCORE 0-100: RESEMBLANCE TO HISTORICAL ABNORMAL PROCESS CONDITIONS RELATIVE TO THE "
               "APR-MAY REFERENCE - NOT A DEPOSIT / RING / FAILURE PROBABILITY, NOT A PLANT LIMIT")
STATE_LABEL = f"{p3common.PROXY_LABEL} (Kiln MD meaning and equipment identity unconfirmed)"
O2_TAG = "Kiln-I!X"                                  # kiln inlet O2 analyser (DQ-1: ambient-air readings while RUNNING)
FAMILIES = ("EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY")
COMPONENT_COL = {d: f"{d.lower()}_component" for d in FAMILIES}
REASON_BY_FAMILY = {"EFFICIENCY": "EFFICIENCY_COMPONENT_DEVIATION", "COMBUSTION": "COMBUSTION_DEVIATION",
                    "THERMAL": "THERMAL_DEVIATION", "DRAFT_PRESSURE": "DRAFT_PRESSURE_DEVIATION",
                    "STABILITY": "PROCESS_VARIABILITY_DEVIATION"}
DRIVER_CODES = tuple(REASON_BY_FAMILY.values()) + ("MULTI_FAMILY_CONCURRENCE", "PERSISTENT_DEVIATION")
BELOW = "_BELOW_THRESHOLD"      # primary-reason suffix: largest point contributor that has not crossed its threshold
# AFR / Phase 4 context lives only in the afr_context / phase4_context columns (retrospective / LOW-confidence signals are
# kept out of the reason strings so they cannot be read as drivers).
CONTEXT_CODES = ("LOAD_ASSOCIATED_CONDITION", "POST_RESTART_SETTLING")
CONFIDENCE_CODES = ("DATA_QUALITY_REDUCED_CONFIDENCE", "REDUCED_FAMILY_COVERAGE", "SUSPECT_ANALYSER_AMBIENT_O2")
NO_DRIVER = "NO_DEVIATION_FROM_REFERENCE"             # only when the score is exactly 0
STATUSES = ("STOPPED", "TRANSITION_CONTEXT", "NOT_SCORABLE", "INSUFFICIENT_DATA", "VALID_REDUCED_CONFIDENCE", "VALID")
BANDS = ("LOW", "ELEVATED", "HIGH", "VERY_HIGH")
UNBANDED = "UNBANDED"
CONF_CAP = "CAPPED_MEDIUM: NO_EVENT_GROUND_TRUTH; STATE_PROXY_UNCONFIRMED; EQUIPMENT_MAPPING_UNCONFIRMED"
MONTHS = {6: "JUN", 7: "JUL", 8: "AUG"}          # operational months; September is never scored (Kiln-I missing)


@dataclass(frozen=True)
class P7Config:
    """Every analytical choice of Phase 7. A variant = dataclasses.replace(PRIMARY, ...). POC choices, not plant limits."""
    name: str = "PRIMARY"
    ref_start: str = "2025-04-01 00:00"        # reference / calibration window (Phase 3 training window), frozen
    ref_end: str = "2025-05-31 23:59"
    window_buckets: int = 6                   # family smoothing: trailing median over (t - 60 min, t]
    window_min_valid: int = 4
    abnormal_q: float = 0.90                  # family abnormal <=> S~ > reference P90 (Phase 3 / 6 rule)
    anchor_floor: float = 0.25                # q_d >= m_d + floor (degenerate reference guard)
    magnitude_mode: str = "hybrid"            # hybrid = 0.5 max + 0.5 mean | mean (candidate A / B)
    w_magnitude: float = 0.50
    w_concurrence: float = 0.25
    w_persistence: float = 0.25
    persistence_mode: str = "magnitude"       # magnitude = H >= H_ref90 | any_family (candidate B)
    persistence_buckets: int = 18             # (t - 3 h, t]
    min_usable_families: int = 3
    denominator: str = "fixed"                # fixed (/5, missing = 0) | available (sensitivity only: can inflate)
    families: tuple = FAMILIES
    load_mode: str = "global"                 # global | load_band (anchors per tentative feed band; sensitivity)
    afr_weight: float = 0.0                   # AFR / Phase 4 inclusion tests only (default: context, never scored)
    p4_weight: float = 0.0
    band_quantiles: tuple = (0.75, 0.90, 0.95)
    settle_hours: float = 6.0                 # post-restart confidence ramp (the Phase 3 persistence window)
    dq_after_window_hours: float = 6.0
    conf_high: float = 0.75
    conf_low: float = 0.50
    temporal_buckets: int = 6                 # confidence: signal agreement over the last hour
    o2_ambient_pct: float = 15.0              # POC heuristic: kiln-inlet O2 bucket median >= 15 % reads like ambient
                                              # air (21 %), not kiln gas - lowers data-quality confidence only
    load_change_buckets: int = 6              # 1-h feed change for LOAD_ASSOCIATED
    afr_context_hours: float = 3.0
    p4_context_buckets: int = 12
    n_boot: int = 400
    block_days: int = 3
    seed: int = 20250601

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()[:12]


PRIMARY = P7Config()


def variant(**kw) -> P7Config:
    return replace(PRIMARY, **kw)


# Confidence-robustness variants (spec section 6): every one has its own frozen reference and bands.
CONFIDENCE_VARIANTS = {
    "WINDOW_30MIN": variant(name="WINDOW_30MIN", window_buckets=3, window_min_valid=2),
    "WINDOW_2H": variant(name="WINDOW_2H", window_buckets=12, window_min_valid=8),
    "ABNORMAL_P85": variant(name="ABNORMAL_P85", abnormal_q=0.85),
    "ABNORMAL_P95": variant(name="ABNORMAL_P95", abnormal_q=0.95),
    "WEIGHTS_EQUAL": variant(name="WEIGHTS_EQUAL", w_magnitude=1 / 3, w_concurrence=1 / 3, w_persistence=1 / 3),
    "WEIGHTS_602020": variant(name="WEIGHTS_602020", w_magnitude=0.6, w_concurrence=0.2, w_persistence=0.2),
}


# ============================================================================== I/O helpers
def log(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stdout)
    return logging.getLogger(name)


sha256 = p3common.sha256
round_frame = ac.round_frame


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_csv(p, index=False)
    (lg or log("p7")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def write_parquet(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_parquet(p, index=False)
    (lg or log("p7")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def write_json(obj: dict, path: Path) -> None:
    """Strict JSON (allow_nan=False: a NaN in a reference is a bug, not a value), UTF-8, sorted keys."""
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str, allow_nan=False), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_context() -> dict:
    """Everything feature_engineering.py cached: grid, Phase 6 episodes (allowed fields only), AFR events, DQ windows."""
    ctx = {"grid": pd.read_parquet(CACHE / "grid.parquet"), "episodes": pd.read_parquet(CACHE / "episodes.parquet"),
           "afr_events": pd.read_parquet(CACHE / "afr_events.parquet"),
           "dq_windows": pd.read_parquet(CACHE / "dq_windows.parquet")}
    ctx["p4_threshold"] = read_json(CACHE / "context_meta.json")["p4_threshold"]
    return ctx


def load_refs() -> dict:
    """{'PRIMARY': frozen primary reference, <variant>: reference, ...} written by reference_builder.py. Refuses
    references from another score version or built on different upstream inputs than the primary."""
    refs = read_json(OUT / "risk_score_variant_references.json")
    refs["PRIMARY"] = read_json(OUT / "risk_score_reference.json")
    bad = [n for n, r in refs.items() if r.get("score_version") != SCORE_VERSION
           or r.get("input_hashes") != refs["PRIMARY"].get("input_hashes")]
    if bad:
        raise RuntimeError(f"references {bad} do not match score version {SCORE_VERSION} / the primary input hashes")
    return refs


# ============================================================================== wording guard (extends Phase 6)
FORBIDDEN = ac.FORBIDDEN + [r"\blikelihood of (deposit|ring|failure)", r"\bdeposits? (detected|present|confirmed)\b",
                            r"\bpredicts? (deposit|ring|failure)s?\b", r"\bfalse[- ]positive rate\b",
                            r"\bdetection accuracy\b"]


def forbidden_hits(text: str) -> list[str]:
    """Unsupported-claim scanner; a line that only negates / qualifies the term is allowed (Phase 6 rule)."""
    hits = []
    for line in text.splitlines():
        for pat in FORBIDDEN:
            if re.search(pat, line, flags=re.IGNORECASE) and not any(a in line.lower() for a in ac.ALLOWED_CONTEXT):
                hits.append(line.strip()[:160])
                break
    return hits
