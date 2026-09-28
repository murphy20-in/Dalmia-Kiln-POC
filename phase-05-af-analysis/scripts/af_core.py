"""Shared paths, configuration, labels and PURE functions for Phase 5 (Alternative Fuel Analysis).

Phase 5 is READ-ONLY with respect to the source data and to Phases 1-4. It writes only to
  phase-05-af-analysis/{outputs,reports,cache}

Phase 4 code (indicator_core, p4common) and, through it, Phase 3 code (kpi_core, p3common, load_phase2_inputs) are imported
read-only: bytecode writing is disabled first and both script directories are APPENDED to sys.path, so Phase 5 modules with
the same file name (sensitivity_analysis, generate_report) take precedence. p4common creates its own directories with
exist_ok on import; they must already exist, so the import is a no-op on disk (checked again by the G1 snapshot).

Every number in P5Config is a POC ANALYTICAL HEURISTIC declared before the evaluation months were analysed. None is a plant
operating, alarm, safety or control limit, and no AFR set-point or firing recommendation is made or implied anywhere.
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
PHASE_DIR = ROOT / "phase-05-af-analysis"
SCRIPTS = PHASE_DIR / "scripts"
OUT = PHASE_DIR / "outputs"
REPORTS = PHASE_DIR / "reports"
FIG = REPORTS / "figures"
CACHE = PHASE_DIR / "cache"
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
        raise RuntimeError(f"upstream directory missing ({_d}); run Phases 3-4 first - Phase 5 never creates upstream files")
if str(P4_SCRIPTS) not in sys.path:
    sys.path.append(str(P4_SCRIPTS))

import p4common  # noqa: E402  (Phase 4, read-only; appends the Phase 3 scripts dir)
import indicator_core as ic  # noqa: E402  (Phase 4, read-only)
import p3common  # noqa: E402  (Phase 3, read-only)

METHOD_VERSION = "p5-afr-1.0.0"
BAND_LABEL = "POC_EMPIRICAL_BAND"
EPISODE_LABEL = "AFR TRANSITION EPISODE (EMPIRICAL, FROM THE AFR SIGNAL) — NOT A PLANT EVENT"
ASSOC_LABEL = "AFR-ASSOCIATED (NOT AFR-CAUSED)"
FEED_TAG = p3common.FEED_TAG
AFR = "Kiln-I!K"                 # AFR | Solid (TPH)
AFR_LIQUID = "Kiln-I!L"          # Liquid (LPH), group header AFR (inferred)
STATE_DATASETS = list(p3common.KPI_DATASETS)
LOAD_DATASETS = ["Kiln-I", "Kiln-IA", "Kiln-II", "Kiln-IIIA"]
P4_INDICATOR = "Kiln-I!I|ROC_1H"

# Target families (every tag is verified against the Phase 1 inventory and the Phase 2 holds in G2).
FAMILIES = {
    "LOAD": ["Kiln-I!C", "Kiln-I!D", "Kiln-I!O", "Kiln-I!N", "Kiln-IIIA!M"],
    "FUEL_CO_MANIPULATION": ["Kiln-I!H", "Kiln-I!I"],
    "COMBUSTION": ["Kiln-I!X", "Kiln-I!Y", "Kiln-I!Z", "Kiln-I!AB", "Kiln-I!AC", "Kiln-I!AD"],
    "THERMAL": ["Kiln-I!AF", "Kiln-I!F", "Kiln-I!G", "Kiln-I!U", "Kiln-IA!C", "Kiln-IA!G", "Kiln-IA!J",
                "Kiln-II!C", "Kiln-II!G", "Kiln-II!K", "Kiln-II!O", "Kiln-II!S", "Kiln-IIIA!H", "Kiln-IIIA!L"],
    "EFFICIENCY": ["KPI:K", "KPI:D"],
}
# Considered and set aside (G2 verifies the reason against Phase 2 holds / Phase 1 inventory).
EXCLUDED_TARGETS = {
    "Kiln-I!AA": "Phase 2 UNIT_REVIEW_HOLD (PC O/L O2: 8 % of values outside 0-100)",
    "Kiln-I!AE": "Phase 2 REDUNDANT_DUPLICATE_COLUMN (identical to Kiln-I!AB CO)",
    "Kiln-IA!F": "Phase 2 CONSTANT_COLUMN (TA Duct Temp single value 0)",
    "CBS-Calculation!B": "Phase 2 CONSTANT_COLUMN (Excess Air based on O2, single value)",
    "CBS-Calculation!C": "Phase 2 CONSTANT_COLUMN (Excess Air based on CO2, single value)",
    "CBS-Calculation!D..G": "plant CALCULATED combustion-air / gas-flow values; formula unknown and possibly computed "
                            "from fuel firing rates (circular with AFR) - not used as process responses",
}
KPI_INPUT_NOTE = "KPI input (Sp.Heat / burning zone / cyclone): not independent evidence of a KPI relationship"
# Set-point / manipulated fuel and load inputs (Phase 4 handoff: explanatory variables, never outcomes).
CONTROL_INPUTS = {"Kiln-I!K": "FUEL_CONTROL_INPUT", "Kiln-I!L": "FUEL_CONTROL_INPUT", "Kiln-I!H": "FUEL_CONTROL_INPUT",
                  "Kiln-I!I": "FUEL_CONTROL_INPUT", "Kiln-I!J": "FUEL_CONTROL_INPUT", "Kiln-I!M": "FUEL_CONTROL_INPUT",
                  "Kiln-I!C": "LOAD_CONTROL_INPUT", "Kiln-I!O": "LOAD_CONTROL_INPUT"}
WINDOWS = ("DISCOVERY", "JUN", "JUL", "REPLICATION", "HOLDOUT_AUG")
EVIDENCE = ("OBSERVED", "ASSOCIATED", "WEAK ASSOCIATION", "NOT SUPPORTED", "INSUFFICIENT DATA", "NOT COMPUTABLE")
REL_COLUMNS = ["afr_signal", "target_signal", "target_original_name", "target_unit", "target_family", "analysis_type",
               "lag_minutes", "window", "row_role", "operating_state", "load_condition", "sample_count",
               "effective_sample_size", "effect_size", "effect_metric", "confidence_interval_low",
               "confidence_interval_high", "p_value", "adjusted_p_value", "direction", "stability", "holdout_result",
               "evidence", "confidence", "flags", "interpretation"]


@dataclass(frozen=True)
class P5Config:
    """Every analytical choice of Phase 5. A variant = dataclasses.replace(PRIMARY, ...)."""
    name: str = "PRIMARY"
    zero_cut: float = 0.5               # AFR <= 0.5 TPH is NO_AFR (data are integer-valued; nothing lies in (0, 1))
    band_q: tuple = (0.25, 0.75)        # LOW / MEDIUM / HIGH cuts: discovery RUNNING non-zero quantiles
    level_lags: tuple = (0, 10, 20, 30, 60, 120, 180, 360)
    horizons: tuple = (10, 20, 30, 60, 120, 180, 360)
    start_off_buckets: int = 6          # AFR_START: >= 60 min valid OFF before T ...
    start_on_buckets: int = 3           # ... and >= 30 min ON from T (mirror for AFR_STOP)
    ramp_tph: float = 5.0               # AFR_RAMP_*: 1-h median after minus 1-h median before >= 5 TPH (~ discovery IQR)
    ramp_half_buckets: int = 6
    refractory_h: int = 6
    ep_pre_min: int = 120
    ep_post_min: int = 180
    ep_clean_pre_h: int = 6             # no kiln stop / transition bucket within 6 h before the episode window
    prior_transition_h: float = 0.0     # no other AFR transition in [T-120 min - this, T); 0 = the pre-window itself
    ep_min_cov: float = 0.7
    post_windows: tuple = ((0, 60), (60, 180))
    ctrl_per_ep: int = 3
    min_episodes: int = 8
    n_perm: int = 200
    match_feed_caliper: float = 2.0     # TPH
    match_time_caliper_h: int = 72
    match_min_pairs: int = 30
    match_min_days: int = 5
    match_smd_max: float = 0.1
    steady_buckets: int = 6
    min_n: int = 100
    min_neff: float = 30.0
    min_days: int = 10
    assoc_rho: float = 0.10             # |partial rho| materiality for ASSOCIATED
    q_assoc: float = 0.05
    q_weak: float = 0.10
    n_boot: int = 1000
    block_days: int = 3
    neff_maxlag: int = 432
    shift_days: tuple = tuple(range(2, 22))
    exclude_post_restart_h: float = 0.0
    exclude_pre_stop_h: float = 0.0
    dq_good_only: bool = False
    feed_tercile: int = -1              # -1 = all load; 1 = middle discovery feed tercile only (sensitivity C)
    use_feed_controls: bool = True
    afr_series: str = "AFR_P2"          # AFR_P2 | AFR_P3MASKED | AFR_NOFLAT (sensitivity G)
    fixed_lag: int = -1                 # -1 = discovery-selected lag; >= 0 = fixed (sensitivity D)
    target_smooth: int = 3
    seed: int = 20250501

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()[:12]


PRIMARY = P5Config()
P4CFG = p4common.PRIMARY          # windows (DISCOVERY Apr-May; JUN from 06:00; JUL; AUG)


def variant(**kw) -> P5Config:
    return replace(PRIMARY, **kw)


# ============================================================================== io helpers
def log(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stdout)
    return logging.getLogger(name)


sha256 = p4common.sha256
round_frame = p4common.round_frame
jdump = p4common.jdump


def write_csv(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_csv(p, index=False)
    (lg or log("p5")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def write_parquet(df: pd.DataFrame, name: str, lg: logging.Logger | None = None) -> Path:
    p = OUT / name
    round_frame(df).to_parquet(p, index=False)
    (lg or log("p5")).info("wrote outputs/%s (%d rows)", name, len(df))
    return p


def read_out(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name, low_memory=False)


# ============================================================================== AFR value classes, bands, runs
def classify(v: np.ndarray, zero_cut: float = 0.5) -> np.ndarray:
    """MISSING (NaN) / INVALID (negative) / ZERO (0 <= v <= cut) / NONZERO. Missing is NEVER treated as zero."""
    v = np.asarray(v, float)
    out = np.full(v.shape, "MISSING", dtype=object)
    ok = np.isfinite(v)
    out[ok & (v < 0)] = "INVALID"
    out[ok & (v >= 0) & (v <= zero_cut)] = "ZERO"
    out[ok & (v > zero_cut)] = "NONZERO"
    return out


def on_state(x: np.ndarray, zero_cut: float) -> np.ndarray:
    """1.0 = AFR on, 0.0 = off, NaN = missing (never coerced to off)."""
    x = np.asarray(x, float)
    return np.where(np.isfinite(x), (x > zero_cut).astype(float), np.nan)


def fit_bands(x_disc: np.ndarray, cfg: P5Config) -> dict:
    """POC_EMPIRICAL_BAND cuts from DISCOVERY RUNNING non-zero buckets; frozen for every later window."""
    nz = x_disc[np.isfinite(x_disc) & (x_disc > cfg.zero_cut)]
    lo, hi = (float(np.quantile(nz, q)) for q in cfg.band_q)
    return {"zero_cut": cfg.zero_cut, "q_lo": lo, "q_hi": hi, "n_fit": int(nz.size), "label": BAND_LABEL}


BANDS = ("NO_AFR", "LOW_AFR", "MEDIUM_AFR", "HIGH_AFR")


def assign_band(x: np.ndarray, bands: dict) -> np.ndarray:
    x = np.asarray(x, float)
    out = np.full(x.shape, "", dtype=object)
    ok = np.isfinite(x) & (x >= 0)
    out[ok & (x <= bands["zero_cut"])] = "NO_AFR"
    out[ok & (x > bands["zero_cut"]) & (x <= bands["q_lo"])] = "LOW_AFR"
    out[ok & (x > bands["q_lo"]) & (x <= bands["q_hi"])] = "MEDIUM_AFR"
    out[ok & (x > bands["q_hi"])] = "HIGH_AFR"
    return out


def runs(flag: np.ndarray) -> pd.DataFrame:
    """Maximal runs of equal finite values in `flag` (NaN breaks a run). Columns start, length, value."""
    f = np.asarray(flag, float)
    rows, i, n = [], 0, len(f)
    while i < n:
        if not np.isfinite(f[i]):
            i += 1
            continue
        j = i
        while j + 1 < n and f[j + 1] == f[i]:
            j += 1
        rows.append((i, j - i + 1, f[i]))
        i = j + 1
    return pd.DataFrame(rows, columns=["start", "length", "value"])


# ============================================================================== transitions
def _refractory(idx: np.ndarray, n: int) -> list[int]:
    out, last = [], -10 ** 9
    for i in idx:
        if i - last >= n:
            out.append(int(i))
            last = i
    return out


def detect_transitions(x: np.ndarray, cfg: P5Config) -> list[tuple[int, str]]:
    """AFR TRANSITION EPISODES on the 10-min bucket AFR series (retrospective, descriptive by design; never a feature).
       AFR_START at T: >= start_off_buckets valid OFF buckets immediately before T, then >= start_on_buckets ON from T.
       AFR_STOP : the mirror image.
       AFR_RAMP_UP / DOWN at T: every bucket in [T-h, T+h] ON and valid, median(T+1..T+h) - median(T-h+1..T) >= +/- ramp;
                  T is the first bucket of a qualifying cluster. Refractory period per type."""
    on = on_state(x, cfg.zero_cut)
    n = len(x)
    a, b = cfg.start_off_buckets, cfg.start_on_buckets
    ref = cfg.refractory_h * 6
    out = []
    for typ, pre, post in (("AFR_START", 0.0, 1.0), ("AFR_STOP", 1.0, 0.0)):
        cand = [t for t in range(a, n - b + 1)
                if np.all(on[t - a:t] == pre) and np.all(on[t:t + b] == post)]
        out += [(t, typ) for t in _refractory(np.asarray(cand, int), ref)]
    h = cfg.ramp_half_buckets
    d = np.full(n, np.nan)
    for t in range(h, n - h):
        seg_on = on[t - h:t + h + 1]
        if np.all(seg_on == 1.0):
            d[t] = np.median(x[t + 1:t + h + 1]) - np.median(x[t - h + 1:t + 1])
    for typ, s in (("AFR_RAMP_UP", 1), ("AFR_RAMP_DOWN", -1)):
        hit = np.where(np.isfinite(d), s * d >= cfg.ramp_tph, False)
        first = np.flatnonzero(hit & ~np.r_[False, hit[:-1]])
        out += [(t, typ) for t in _refractory(first, ref)]
    return sorted(out)


def episode_status(t: int, running: np.ndarray, afr_valid: np.ndarray, cfg: P5Config,
                   other_pos: np.ndarray | None = None) -> str:
    """ELIGIBLE, or the reason the episode is set aside (shutdown / restart / gap / coverage / earlier AFR transition).
    `other_pos` = bucket positions of all detected AFR transitions; another transition in [T-120 min - prior_transition_h,
    T) makes the pre-window (and so the [T-60, T) baseline) unclean (primary: the pre-window only; 6 h in sensitivity E). The post window may legitimately contain the AFR restart /
    reversal (AFR interruptions last ~30-60 min) - that is part of the episode, not a contamination."""
    pre, post = cfg.ep_pre_min // 10, cfg.ep_post_min // 10
    a, b = t - pre, t + post
    if a < 0 or b >= len(running):
        return "EXCLUDED_EDGE"
    if not running[a:b + 1].all():
        nxt = running[t:b + 1]
        return "EXCLUDED_KILN_STOP_AFTER" if running[a:t].all() and not nxt.all() else "EXCLUDED_NOT_RUNNING"
    c = max(0, a - cfg.ep_clean_pre_h * 6)
    if not running[c:a].all():
        return "EXCLUDED_POST_RESTART"
    c2 = max(0, a - int(cfg.prior_transition_h * 6))
    if other_pos is not None and np.any((other_pos >= c2) & (other_pos < t)):
        return "EXCLUDED_PRIOR_TRANSITION"
    if afr_valid[a:b + 1].mean() < cfg.ep_min_cov:
        return "EXCLUDED_AFR_COVERAGE"
    return "ELIGIBLE"


def window_delta(y: np.ndarray, a: int, b: int) -> np.ndarray:
    """For every anchor t: median(y over (t+a, t+b]) - median(y over [t-6, t)) in buckets (a, b in buckets).
    Anchor-relative response (retrospective episode statistic, never a feature). NaN if < 2/3 coverage."""
    n = len(y)
    post = ic.trailing_median(y, b - a, int(np.ceil(2 * (b - a) / 3)))      # median over (s-(b-a), s]
    post = np.r_[post[b:], np.full(b, np.nan)] if b > 0 else post           # s = t + b
    base = ic.lagged(ic.trailing_median(y, 6, 4), 1)                         # [t-6, t-1] == [t-60 min, t)
    return (post - base)[:n]


# ============================================================================== statistics
def block_ids(index: pd.DatetimeIndex, block_days: int) -> np.ndarray:
    return ((index.normalize() - pd.Timestamp("2025-04-01")).days.to_numpy() // block_days).astype(int)


def boot_median(v: np.ndarray, blocks: np.ndarray, n_boot: int, seed: int) -> tuple[float, float]:
    """95 % percentile CI of the median of v under block resampling (whole blocks drawn with replacement)."""
    ok = np.isfinite(v)
    v, blocks = v[ok], blocks[ok]
    u, inv = np.unique(blocks, return_inverse=True)
    if u.size < 5:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    groups = [v[inv == k] for k in range(u.size)]
    meds = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, u.size, u.size)
        meds[i] = np.median(np.concatenate([groups[k] for k in pick]))
    return float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))


def smd(a: np.ndarray, b: np.ndarray) -> float:
    s = np.sqrt((np.nanvar(a) + np.nanvar(b)) / 2)
    return float((np.nanmean(a) - np.nanmean(b)) / s) if s > 0 else 0.0


def match_pairs(t_idx: np.ndarray, c_idx: np.ndarray, strata: np.ndarray, feed: np.ndarray, hours: np.ndarray,
                cfg: P5Config) -> list[tuple[int, int]]:
    """Greedy 1:1 matching without replacement: exact on `strata`, |feed| <= caliper, |dt| <= time caliper; the nearest
    in time wins, ties -> smaller feed distance -> earlier control (deterministic)."""
    used, out = set(), []
    for t in t_idx:
        c = c_idx[(strata[c_idx] == strata[t]) & (np.abs(feed[c_idx] - feed[t]) <= cfg.match_feed_caliper)
                  & (np.abs(hours[c_idx] - hours[t]) <= cfg.match_time_caliper_h)]
        c = np.array([k for k in c if k not in used], dtype=int)
        if c.size == 0:
            continue
        order = np.lexsort((c, np.abs(feed[c] - feed[t]), np.abs(hours[c] - hours[t])))
        out.append((int(t), int(c[order[0]])))
        used.add(int(c[order[0]]))
    return out


def circular_shift(x: np.ndarray, rows: np.ndarray, k: int) -> np.ndarray:
    """Roll x by k positions WITHIN the positions of `rows` (the analysis window); other positions keep NaN.
    Preserves the multiset of window values and their autocorrelation, destroys the alignment with the target."""
    out = np.full(len(x), np.nan)
    pos = np.flatnonzero(rows)
    out[pos] = np.roll(x[pos], k)
    return out


# ============================================================================== evidence rules (pre-declared)
def stability_label(disc: float, jun: float, jul: float) -> str:
    s = [np.sign(v) for v in (disc, jun, jul) if np.isfinite(v)]
    if len(s) < 3:
        return "INSUFFICIENT"
    return "STABLE_SIGN" if len(set(s)) == 1 else "SIGN_FLIP"


def holdout_label(disc: float, aug: float, p_aug: float) -> str:
    if not (np.isfinite(disc) and np.isfinite(aug)):
        return "NOT_EVALUABLE"
    same = np.sign(disc) == np.sign(aug)
    sig = np.isfinite(p_aug) and p_aug < 0.05
    if same:
        return "CONFIRMED" if sig else "SAME_DIRECTION_NS"
    return "REVERSED" if sig else "OPPOSITE_DIRECTION_NS"


def evidence_label(d: dict, cfg: P5Config = PRIMARY) -> str:
    """d: n, n_eff, days, rho, q, ci_lo, ci_hi, repl_rho, repl_p, holdout, null_pass (True / False / None)."""
    if not np.isfinite(d.get("rho", np.nan)):
        return "NOT COMPUTABLE" if d.get("n", 0) >= cfg.min_n else "INSUFFICIENT DATA"
    if d["n"] < cfg.min_n or d["n_eff"] < cfg.min_neff or d.get("days", cfg.min_days) < cfg.min_days:
        return "INSUFFICIENT DATA"
    ci_ok = np.isfinite(d["ci_lo"]) and d["ci_lo"] * d["ci_hi"] > 0
    repl_ok = (np.isfinite(d["repl_rho"]) and np.sign(d["repl_rho"]) == np.sign(d["rho"])
               and np.isfinite(d["repl_p"]) and d["repl_p"] < 0.05)
    if (d["q"] < cfg.q_assoc and abs(d["rho"]) >= cfg.assoc_rho and ci_ok and repl_ok
            and d["holdout"] != "REVERSED" and d.get("null_pass") is True):
        return "ASSOCIATED"
    if d["q"] < cfg.q_weak and ci_ok:
        return "WEAK ASSOCIATION"
    return "NOT SUPPORTED"


CAP_FLAGS = ("CO_MANIPULATION_OF_CONTROL_INPUTS", "SP_HEAT_DERIVATION_R2", "KPI_EFFICIENCY_HALF_IS_SP_HEAT")


def confidence_cap(flags: str) -> str:
    """Relationships that are not process effects (two control inputs moved together) or that are largely reproducible
    from the firing inputs (Sp.Heat, and the KPI whose efficiency half is Sp.Heat) are capped at LOW confidence."""
    f = str(flags)
    if "CO_MANIPULATION_OF_CONTROL_INPUTS" in f:
        return "CAPPED_LOW: co-manipulation of control inputs, not a process effect"
    if "SP_HEAT_DERIVATION_R2" in f or "KPI_EFFICIENCY_HALF_IS_SP_HEAT" in f:
        return "CAPPED_LOW: Sp.Heat (or the Sp.Heat-based KPI) is largely reproducible from the firing inputs incl. AFR"
    return ""


def confidence_label(evidence: str, n_agree: int, n_groups: int, capped: bool = False) -> str:
    """Never HIGH: AFR mass flow without fuel properties cannot carry high-confidence process evidence."""
    if evidence == "ASSOCIATED" and n_groups >= 4 and n_agree / n_groups >= 0.8 and not capped:
        return "MEDIUM"
    if evidence in ("ASSOCIATED", "WEAK ASSOCIATION"):
        return "LOW"
    return "NOT_APPLICABLE"


# ============================================================================== wording guard
FORBIDDEN = [r"\bcaus(e|es|ed|ing)\b", r"\bdrives?\b", r"\bdue to AFR\b", r"\bthermal substitution rate\b",
             r"\bTSR\b", r"\bMJ/h\b", r"\bcalorific value of\b", r"\bequivalent coal replacement\b",
             r"\brecommend(ed)? (AFR|set-?point)", r"\bplant limit\b(?! )"]
ALLOWED_CONTEXT = ("**not**", "not a plant", "not plant", "not a target", "not caused", "NOT AFR-CAUSED", "AFR-caused", "does not cause", "cannot establish", "not establish",
                   "causal", "no caus", "not a caus", "never caus", "Do not", "drives kiln drive", "what drives",
                   "kiln drive", "main drive", "Drive")


def forbidden_hits(text: str) -> list[str]:
    """Unsupported-claim scanner: returns offending lines (lines that only negate / qualify the term are allowed)."""
    hits = []
    for line in text.splitlines():
        for pat in FORBIDDEN:
            if re.search(pat, line, flags=re.IGNORECASE) and not any(a.lower() in line.lower() for a in ALLOWED_CONTEXT):
                hits.append(line.strip()[:160])
                break
    return hits
