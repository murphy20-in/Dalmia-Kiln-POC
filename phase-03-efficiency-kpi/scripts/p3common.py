"""Shared paths, configuration, tag specification and helpers for Phase 3 (Efficiency Deterioration KPI).

Source data is READ-ONLY. Phase 3 reads Phase 2 outputs and data/processed; it writes only to
  phase-03-efficiency-kpi/{outputs,reports,cache}

Every number in KPI_CONFIG is a POC ANALYTICAL HEURISTIC or a design choice. None is a plant engineering,
alarm, safety or control limit. Nothing here leaves the local machine (no network, no telemetry).
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "phase-03-efficiency-kpi"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
CACHE = PHASE_DIR / "cache"
PROCESSED = ROOT / "data" / "processed"
CURATED = ROOT / "data" / "curated"
P2_OUT = ROOT / "phase-02-baseline" / "outputs"
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")

for _d in (OUT, REPORTS, FIG, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

KPI_NAME = "POC Kiln Efficiency Deterioration KPI"
KPI_VERSION = "p3-kpi-1.0.0"
PROXY_LABEL = "POC PROXY — UNCONFIRMED"
COMPOSITE_LABEL = "POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED"
BAND_LABEL = "POC ANALYTICAL REFERENCE BAND — NOT A PLANT ALARM / ENGINEERING LIMIT"
SCALE_LABEL = "POC NORMALIZED SCORE 0–100 — NOT A PLANT LIMIT, NOT A DEPOSIT / RING DETECTOR"
EQUIPMENT_VIEW = "COMPOSITE Kiln-I + Kiln-IA + Kiln-II (one kiln line assumed; UNCONFIRMED)"
MAD_SCALE = 1.4826

# Datasets whose minute values feed the KPI (tags are selected from these only).
KPI_DATASETS = ["Kiln-I", "Kiln-IA", "Kiln-II", "Kiln-IIIA"]
FEED_TAG = "Kiln-I!C"          # load context (Kiln Feed | Pfister, TPH)
HOOD_TAG = "Kiln-IA!C"         # secondary restart-ramp signal (Kiln Hood | Temp)
SPEED_TAG = "Kiln-I!O"         # kiln main drive speed (state-conflict check only; never scored)

# Mask tokens from Phase 2 that depend only on the cell itself (or on copies at the same timestamp) -> causal.
# SUSPECTED_FROZEN_WINDOW and SUSPECT_TAG_FLATLINE are detected retrospectively in Phase 2 and are IGNORED here;
# Phase 3 recomputes flatline / frozen masks causally inside kpi_core.prepare_minutes().
CAUSAL_INVALID_TOKENS = ("MISSING", "TEXT_VALUE", "TIMESTAMP_UNPARSED", "SENTINEL_", "PHYSICALLY_IMPOSSIBLE",
                         "DUPLICATE_TIMESTAMP_COPY", "DUPLICATE_TIMESTAMP_CONFLICT", "RESOLUTION_HOURLY")
RETROSPECTIVE_TOKENS = ("SUSPECTED_FROZEN_WINDOW", "SUSPECT_TAG_FLATLINE")

# Column holds that are fixed metadata (label/unit/semantics), not statistics of the full period.
METADATA_HOLDS = ("UNIT_REVIEW_HOLD", "STATE_INDICATOR_COLUMN", "REDUNDANT_DUPLICATE_COLUMN", "SENTINEL_DOMINATED")


@dataclass(frozen=True)
class TagSpec:
    tag: str                 # "<dataset>!<source_column>" or a derived id
    dimension: str           # EFFICIENCY | COMBUSTION | THERMAL | DRAFT_PRESSURE | STABILITY | FUEL | CONTEXT
    direction: str           # "up" (only increases count as deterioration) | "both" (|z|)
    load_adjusted: bool
    rationale: str
    derived_from: tuple = ()  # for derived tags (sum of same-unit tags; no unit conversion)


# ---------------------------------------------------------------- KPI tag specification (real Phase 1/2 tags)
_EFF = "specific thermal energy per kg clinker; higher = more heat per unit product (definitional direction)"
_PH = "preheater / calciner / kiln gas & material temperature"
_DR = "draft / pressure (mmWC) along the gas path"
TAG_SPECS: list[TagSpec] = [
    TagSpec("Kiln-I!F", "EFFICIENCY", "up", True, "Sp.Heat definition F — " + _EFF),
    TagSpec("Kiln-I!G", "EFFICIENCY", "up", True, "Sp.Heat definition G — " + _EFF),
    TagSpec("Kiln-I!X", "COMBUSTION", "both", True, "kiln inlet O2 (%)"),
    TagSpec("Kiln-I!Z", "COMBUSTION", "both", True, "NOx (PPM)"),
    TagSpec("Kiln-I!AC", "COMBUSTION", "both", True, "NOx second analyser (PPM)"),
    TagSpec("Kiln-I!Y", "COMBUSTION", "both", True, "CO (PPM); LOW confidence (heavy tails)"),
    TagSpec("Kiln-I!AD", "COMBUSTION", "both", True, "preheater outlet O2 (%); LOW confidence"),
    TagSpec("Kiln-I!AF", "THERMAL", "both", True, "burning zone temperature"),
    TagSpec("Kiln-I!U", "THERMAL", "both", True, "preheater fan inlet gas temperature"),
    TagSpec("Kiln-IA!C", "THERMAL", "both", True, "kiln hood temperature"),
    TagSpec("Kiln-IA!J", "THERMAL", "both", True, "pre-calciner outlet temperature"),
    TagSpec("Kiln-IA!G", "THERMAL", "both", True, "TAD damper inlet temperature; LOW confidence"),
    *[TagSpec(f"Kiln-II!{c}", "THERMAL", "both", True, _PH) for c in ["C", "D", "G", "H", "K", "L", "O", "P", "S", "T"]],
    TagSpec("Kiln-I!S", "DRAFT_PRESSURE", "both", True, "preheater fan inlet draft"),
    TagSpec("Kiln-I!T", "DRAFT_PRESSURE", "both", True, "preheater fan outlet draft"),
    TagSpec("Kiln-I!W", "DRAFT_PRESSURE", "both", True, "kiln inlet draft"),
    TagSpec("Kiln-IA!D", "DRAFT_PRESSURE", "both", True, "hood draft"),
    TagSpec("Kiln-IA!E", "DRAFT_PRESSURE", "both", True, "tertiary air duct draft"),
    TagSpec("Kiln-IA!I", "DRAFT_PRESSURE", "both", True, "pre-calciner inlet pressure"),
    *[TagSpec(f"Kiln-II!{c}", "DRAFT_PRESSURE", "both", True, _DR) for c in ["E", "F", "I", "J", "M", "N", "Q", "R", "U", "V"]],
    # Process stability: trailing 60-min rolling std (log) of key HIGH-confidence tags; higher variability = worse.
    *[TagSpec(f"STD60:{t}", "STABILITY", "up", False, f"trailing 60-min variability of {t}", (t,))
      for t in ["Kiln-I!AF", "Kiln-I!X", "Kiln-I!W", "Kiln-IA!C"]],
    # Fuel: evaluated in sensitivity only (see select_kpi_candidates.py for the reason).
    TagSpec("DERIVED:COAL_TOTAL", "FUEL", "up", True, "coal kiln + PC firing (TPH + TPH, no unit conversion)",
            ("Kiln-I!H", "Kiln-I!I")),
]
CONTEXT_TAGS = {FEED_TAG: "load context (kiln feed)", "Kiln-IIIA!M": "production context (clinker TPH)",
                "Kiln-I!K": "AFR solid rate context (ALTERNATIVE FUEL family INSUFFICIENT; never scored)"}
PRIMARY_DIMENSIONS = ["EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"]
SUPPORT_DIMENSIONS = ["COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"]

# Explicit, tag-level exclusion reasons for kiln-system tags that are NOT holds and NOT in TAG_SPECS.
EXPLICIT_EXCLUSIONS = {
    "Kiln-I!AB": "UNDEFINED SCALE: Phase 2 scaled MAD = 0 (C7 dispersion failure); duplicate CO analyser",
    "Kiln-I!E": "UNDEFINED SCALE: Coal Firing | Sp.Power has scaled MAD = 0 (C7)",
    "Kiln-I!J": "UNDEFINED SCALE: HAG firing scaled MAD = 0 (C7); mostly zero",
    "Kiln-I!M": "UNUSABLE FLATLINE: diesel flow C4/C7 failures (mostly zero)",
    "Kiln-I!D": "SEMANTICS UNCLEAR: 'SFM' (TPH) not confirmed; production auxiliary",
    "Kiln-I!H": "FUEL DIMENSION IN SENSITIVITY ONLY: used via DERIVED:COAL_TOTAL",
    "Kiln-I!I": "FUEL DIMENSION IN SENSITIVITY ONLY: used via DERIVED:COAL_TOTAL",
    "Kiln-I!K": "CONTEXT ONLY: ALTERNATIVE FUEL family INSUFFICIENT (no CV, moisture, RDF split)",
    "Kiln-I!C": "CONTEXT ONLY: kiln feed is the load covariate; low production is not deterioration",
    "Kiln-I!N": "CONTEXT ONLY: bucket-elevator current tracks feed (load proxy)",
    "Kiln-I!O": "OUT OF EFFICIENCY SCOPE: kiln drive speed (mechanical; Phase 4 candidate)",
    "Kiln-I!P": "OUT OF EFFICIENCY SCOPE: kiln drive power (mechanical; Phase 4 candidate)",
    "Kiln-I!Q": "OUT OF EFFICIENCY SCOPE: kiln drive current (mechanical; Phase 4 candidate)",
    "Kiln-I!R": "ACTUATOR: preheater fan speed is a manipulated variable (operator response, not process state)",
    "Kiln-I!V": "ACTUATOR: preheater fan power follows the manipulated fan speed",
    "Kiln-IA!T": "OUT OF SCOPE: swirl-air fan current (auxiliary)",
    "Kiln-IA!U": "OUT OF SCOPE: fan speed (auxiliary actuator)",
    "Kiln-IA!V": "OUT OF SCOPE: auxiliary fan outlet pressure (family OTHER)",
    "Kiln-IIIA!X": "REDUNDANT: identical to Kiln-I G 'Sp.Heat' (Phase 1/2: rho = 1)",
    "Kiln-IIIA!W": "OUT OF THERMAL-EFFICIENCY SCOPE: electrical specific power; LOW (C5); Ton basis unconfirmed",
    "Kiln-IIIA!V": "OUT OF THERMAL-EFFICIENCY SCOPE: electrical total power",
    "Kiln-IIIA!M": "CONTEXT ONLY: clinker production rate",
}
FAMILY_EXCLUSIONS = {
    "COOLER": "OUT OF KPI DIMENSION SET: cooler subsystem (not in the Phase 3 efficiency dimensions; later-phase candidate)",
    "OTHER": "OUT OF SCOPE: auxiliary / CBS / ESP equipment",
    "KILN": "OUT OF EFFICIENCY SCOPE: kiln-system auxiliary",
    "COMBUSTION": "OUT OF SCOPE: calculated CBS gas-flow quantities (not kiln combustion measurements)",
}


@dataclass(frozen=True)
class KPIConfig:
    """Every analytical choice of the KPI. A variant = dataclasses.replace(PRIMARY, ...)."""
    name: str = "PRIMARY"
    train_start: str = "2025-04-01 00:00"
    train_end: str = "2025-05-31 23:59"
    fit_end: str = ""                    # "" = anchors fitted on the whole training window (primary); else holdout calibration
    score_end: str = "2025-09-30 23:59"
    bucket_min: int = 10                 # KPI grain (10-min buckets, right-closed, labelled by bucket END)
    bucket_min_valid: int = 8            # a tag bucket needs >= 8 valid running minutes
    flat_run_n: int = 60                 # causal flatline: value masked from the 60th identical consecutive sample
    frozen_run_n: int = 10               # causal frozen row: >= frozen_min_tags tags each flat >= 10 samples ...
    frozen_min_tags: int = 20
    frozen_min_share: float = 0.8        # ... and >= 80 % of the dataset's non-missing tags
    ramp_ref_quantile: float = 0.25      # causal restart ramp (Phase 2 rule made causal)
    ramp_ref_minutes: int = 1440
    ramp_ref_lookback_min: int = 7 * 1440
    ramp_exclude_pre_stop_min: int = 60
    ramp_sustain_min: int = 60
    ramp_fallback_min: int = 240         # used only when no ramp signal/reference exists (POC heuristic)
    ramp_max_min: int = 48 * 60          # Phase 2 cap: a ramp not ended after 48 h is censored -> RUNNING
    restart_gap_min: int = 60            # RUNNING after > 60 min without a RUNNING minute (UNKNOWN / missing) = restart
    flatline_exempt: tuple = (FEED_TAG,) # load covariate exempt from the causal flatline mask (feeder at setpoint)
    state_mode: str = "causal"           # "causal" | "phase2_retrospective" (sensitivity only)
    use_causal_flatline: bool = True
    load_mode: str = "adjusted"          # "adjusted" (feed-conditional median) | "global" | "band"
    load_bins: int = 10
    load_bin_min_n: int = 200
    n_bands: int = 3
    z_cap: float = 10.0
    scale_floor_rel: float = 0.01        # scale floor: max(scaled MAD, IQR/1.349, resolution, 1% |median|)
    dim_scale_floor: float = 0.05
    stability_window_min: int = 60
    stability_min_periods: int = 45
    sp_heat: str = "both"                # "both" | "F" | "G"
    dimensions: tuple = tuple(PRIMARY_DIMENSIONS)
    drop_low_confidence: bool = False
    aggregation: str = "efficiency_anchored"   # | "equal_dimension" | "equal_tag" | "inverse_redundancy"
    w_efficiency: float = 0.5
    min_support_dims: int = 2
    persistence_window: str = "6h"
    persistence_stat: str = "median"     # "median" | "mean" | "none"
    persistence_min_coverage: float = 0.5
    ref_quantile_anchor: float = 0.95    # KPI = 50 at training P95 of the persistent score
    band_quantiles: tuple = (0.90, 0.99)
    min_train_buckets: int = 2000
    min_train_coverage: float = 0.5
    redundancy_rho: float = 0.95
    seed: int = 20250401
    bootstrap_reps: int = 400

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()[:12]


PRIMARY = KPIConfig()

# Training-window candidates (analysed in build_training_window.py; PRIMARY = W_APR_MAY).
TRAINING_WINDOWS = {
    "W_APR": ("2025-04-01 00:00", "2025-04-30 23:59", "sensitivity: April only (shortest; one feed band dominates)"),
    "W_APR_MAY": ("2025-04-01 00:00", "2025-05-31 23:59", "PRIMARY"),
    "W_APR_JUN": ("2025-04-01 00:00", "2025-06-30 23:59", "sensitivity: longer reference, shorter scoring window"),
    "W_JUN_JUL15": ("2025-06-01 00:00", "2025-07-15 23:59", "sensitivity: later-anchored reference (excludes high-Sp.Heat April)"),
}
COMMON_SCORING = ("2025-07-16 00:00", "2025-08-22 23:59")   # every window variant is out-of-sample here

# A-priori (pre-declared) materiality rules for sensitivity comparisons. Declared before looking at results.
MATERIALITY = {"spearman_min": 0.80, "band_agreement_min": 0.85, "median_abs_diff_max": 10.0}
COLLAPSE = {"spearman_min": 0.30, "scored_share_min": 0.50}


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
    return json.dumps(o, default=str, ensure_ascii=False, sort_keys=True)


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    df.to_csv(p, index=False)
    (lg or log("p3")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def read_out(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name, low_memory=False)


def read_p2(name: str) -> pd.DataFrame:
    return pd.read_csv(P2_OUT / name, low_memory=False)


def dataset_key(eq: str) -> str:
    return eq.lower().replace(" ", "_").replace("-", "_")


def processed_path(eq: str) -> Path:
    return PROCESSED / f"{dataset_key(eq)}.parquet"


def spec_by_tag() -> dict[str, TagSpec]:
    return {s.tag: s for s in TAG_SPECS}


def variant(**kw) -> KPIConfig:
    return replace(PRIMARY, **kw)


# Phase 2 inputs consumed by Phase 3 (hashed into kpi_version_manifest.csv; never modified).
P2_INPUTS = ["baseline_reference_bands.csv", "baseline_statistics.csv", "baseline_stability.csv",
             "baseline_temporal_analysis.csv", "multivariate_baseline.csv", "baseline_confidence.csv",
             "baseline_family_readiness.csv", "baseline_current_reference.csv", "column_holds.csv",
             "tag_contract.csv", "operating_state_events.csv", "frozen_windows.csv"]


# ---------------------------------------------------------------- bucket cache (derived data; regenerated by --clean)
def save_buckets(b: dict, name: str) -> None:
    for part in ("values", "std60", "meta"):
        b[part].to_parquet(CACHE / f"buckets_{name}_{part}.parquet")
    b["minute_state"].to_parquet(CACHE / f"buckets_{name}_minute_state.parquet")


def load_buckets(name: str) -> dict:
    return {part: pd.read_parquet(CACHE / f"buckets_{name}_{part}.parquet")
            for part in ("values", "std60", "meta", "minute_state")}


def load_minutes() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_parquet(CACHE / "minute_values.parquet"), pd.read_parquet(CACHE / "minute_state.parquet")
