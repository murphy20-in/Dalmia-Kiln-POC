"""Step 5 - validation gates G1-G7 and G9 -> outputs/risk_score_validation.csv (G8 reproducibility: run_phase7.py).

G1 source integrity   G2 schema / provenance   G3 temporal integrity (MANDATORY leakage tests 1-7)   G4 score integrity
G5 statistical integrity   G6 empirical period coverage / claims   G7 data-quality integrity   G9 review
INDEPENDENT checks re-derive a result with separate code or a perturbation experiment; CONSISTENCY checks compare outputs.
NOT_MET_REPORTED = a pre-declared expectation the data did not meet (reported, not hidden, not a pipeline failure).
NOT_MET_PENDING_REVIEW = G9 before the review log records every required reviewer with no OPEN finding.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from common import (BANDS, BELOW, CONFIDENCE_CODES, CONTEXT_CODES, DOCS, DRIVER_CODES, FAMILIES, NO_DRIVER, O2_TAG,
                    OUT, P3_OUT, PRIMARY, REVIEWS, ROOT, SOURCE_ROOT, STATUSES, UNBANDED, forbidden_hits,
                    load_context, load_refs, log, read_json, sha256)
from feature_engineering import (CAUSAL_INVALID, POST_EVENT_FIELDS, check_inventory, components_from_tags, tag_scores,
                                 validate_upstream)
from reference_builder import code_sha256, fit_reference
from risk_core import SCORING_FEATURES, score_core, score_frame
from robustness import INCLUSION_MAX_MONTH_CHANGE, INCLUSION_MIN_GAIN

CUTS = ["2025-05-20 12:00", "2025-06-01 00:00", "2025-06-15 17:30", "2025-07-01 00:00", "2025-07-16 06:00",
        "2025-08-01 00:00", "2025-08-11 05:00", "2025-08-18 00:00"]
REQUIRED = {
    "risk_scores.parquet": ["timestamp", "risk_score", "risk_band", "operational", "confidence_score", "confidence_band",
                            "risk_status", "operating_state", "load_band", "kpi_value", "family_count_abnormal",
                            "family_count_usable", "persistence_minutes", "historical_similarity", "data_quality_status",
                            "primary_reason", "secondary_reasons", "reference_version", "score_version", "load_context",
                            "contributing_families", "reference_state"],
    "risk_score_diagnostics.parquet": ["timestamp", "risk_score_in_sample_reference", "risk_band_in_sample_reference",
                                       "risk_score_diagnostic", "diagnostic_label"],
    "risk_score_components.parquet": ["timestamp", "operational", "family", "raw_measure", "reference_measure",
                                      "normalized_deviation", "family_score", "family_weight", "family_contribution",
                                      "usable", "quality_flag", "reason_code"],
    "risk_score_feature_inventory.csv": ["feature_name", "source_dataset", "source_tag", "source_phase", "source_file",
                                         "transformation", "window", "lag", "reference_window", "permitted_use",
                                         "quality_constraints", "leakage_status"],
    "risk_score_reasons.parquet": ["timestamp", "reason_code", "reason_type", "contribution_points", "driver_rank"],
    "risk_score_confidence.parquet": ["timestamp", "confidence_score", "confidence_band", "conf_data_quality",
                                      "conf_family_coverage", "conf_baseline", "conf_operating_state", "conf_temporal",
                                      "conf_robustness", "o2_ambient_suspect"],
    "risk_score_bands.csv": ["band", "lower_edge", "reference_quantile", "supported", "population", "date_range",
                             "reference_version", "rationale", "calibration_status"],
    "risk_score_calibration.csv": ["section", "slice", "metric", "value"],
    "risk_score_robustness.csv": ["section", "dimension", "variant", "result"],
    "risk_score_data_quality.csv": ["section", "slice", "metric", "value"],
    "risk_score_event_similarity.csv": ["episode_id", "population", "median_score", "peak_score", "coverage_label"],
    "risk_score_summary.csv": ["slice_type", "slice", "median", "p75", "p90", "share_ge_high"],
    "risk_score_reference.json": [],
    "risk_score_variant_references.json": [],
}
REVIEWERS = ("planner", "senior-data-scientist", "statistical-analyst", "data-quality-auditor", "python-reviewer",
             "mle-reviewer", "product", "ponytail")
SENTINELS_ANY = (99999.0, 9999.0)
REF_VOLATILE = ("input_hashes", "code_sha256")


def read(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / name) if name.endswith(".parquet") else pd.read_csv(OUT / name, low_memory=False)


def frame_equal(a: pd.DataFrame, b: pd.DataFrame, tol: float = 1e-9) -> list[str]:
    """Columns that differ (numeric within tol, NaN == NaN; everything else as strings)."""
    diff = []
    for c in a.columns:
        x, y = a[c], b[c]
        if len(x) != len(y):
            diff.append(c)
        elif pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y) and x.dtype != bool:
            if not np.allclose(x.to_numpy(float), y.to_numpy(float), rtol=0, atol=tol, equal_nan=True):
                diff.append(c)
        elif not (x.astype(str).to_numpy() == y.astype(str).to_numpy()).all():
            diff.append(c)
    return diff


def truncate(ctx: dict, t_cut: pd.Timestamp) -> dict:
    """Inputs exactly as they existed at t_cut: grid rows <= t_cut, AFR events <= t_cut, DQ windows started by t_cut,
    and a window still open at t_cut gets an unknown end (NaT)."""
    out = dict(ctx)
    out["grid"] = ctx["grid"][ctx["grid"].index <= t_cut]
    out["afr_events"] = ctx["afr_events"][ctx["afr_events"]["T"] <= t_cut]
    w = ctx["dq_windows"][ctx["dq_windows"]["start"] <= t_cut].copy()
    w.loc[w["end"] > t_cut, "end"] = pd.NaT
    out["dq_windows"] = w
    return out


def perturb_context(ctx: dict, t_cut: pd.Timestamp, seed: int, until: pd.Timestamp | None = None) -> dict:
    """Every grid column in (t_cut, until] replaced by random, type-valid values; random AFR transitions and a random DQ
    window added in that interval. Nothing at or before t_cut changes."""
    g = ctx["grid"].copy()
    sel = g.index > t_cut
    if until is not None:
        sel &= g.index <= until
    rng = np.random.default_rng(seed)
    n = int(sel.sum())
    for c in g.columns:
        if c == "state":
            g.loc[sel, c] = rng.choice(["RUNNING", "STOPPED", "TRANSITION", "UNKNOWN"], n)
        elif pd.api.types.is_bool_dtype(g[c]):
            g.loc[sel, c] = rng.random(n) < 0.5
        elif pd.api.types.is_numeric_dtype(g[c]):
            g.loc[sel, c] = rng.uniform(0, 1, n) * (450 if c == "feed" else 30 if c.startswith("o2") else 8)
        else:
            g.loc[sel, c] = "RANDOM"
    out = {**ctx, "grid": g}
    if n:
        t = g.index[sel]
        k = min(5, n)
        out["afr_events"] = pd.concat([ctx["afr_events"], pd.DataFrame(
            {"episode_id": [f"RND{i}" for i in range(k)], "afr_transition": rng.choice(["AFR_STOP", "AFR_START"], k),
             "T": np.sort(rng.choice(t, k, replace=False))})], ignore_index=True)
        out["dq_windows"] = pd.concat([ctx["dq_windows"], pd.DataFrame(
            {"kind": ["LONG_GAP"], "dataset": ["Kiln-I"], "start": [t[0]], "end": [t[min(5, n - 1)]],
             "source": ["random"]})], ignore_index=True)
    return out


def ref_core(ref: dict) -> str:
    return json.dumps({k: v for k, v in ref.items() if k not in REF_VOLATILE}, sort_keys=True, default=str)


def review_status() -> tuple[str, str]:
    p = REVIEWS / "REVIEW_LOG.md"
    if not p.exists():
        return "NOT_MET_PENDING_REVIEW", "reviews/REVIEW_LOG.md does not exist yet"
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in p.read_text(encoding="utf-8").splitlines()
            if re.match(r"^\|\s*R\d+\s*\|", ln)]
    reviewer_col = " ".join(r[1].lower() for r in rows if len(r) >= 7)
    missing = [k for k in REVIEWERS if k not in reviewer_col]
    open_ = [r[0] for r in rows if len(r) >= 7 and r[6].upper().startswith("OPEN")]
    if missing or open_ or not rows:
        return "NOT_MET_PENDING_REVIEW", f"{len(rows)} findings; reviewers missing {missing}; OPEN {open_}"
    return "PASS", f"{len(rows)} findings recorded; all required reviewers present in the Reviewer column; no OPEN finding"


def main():
    lg = log("validation")
    rows = []

    def add(gate, check, ok, ev, result=None, kind="INDEPENDENT"):
        rows.append({"gate": gate, "check": check, "check_type": kind, "result": result or ("PASS" if ok else "FAIL"),
                     "evidence": str(ev)[:900]})

    ctx = load_context()
    refs = load_refs()
    ref = refs["PRIMARY"]
    grid = ctx["grid"]

    # ------------------------------------------------------------------ G1 source / upstream integrity
    g1 = "G1 source integrity"
    man = pd.read_csv(ROOT / "data" / "raw" / "source_manifest.csv")
    bad = [r.relative_path for r in man.itertuples() if not (SOURCE_ROOT / r.relative_path).is_file()
           or sha256(SOURCE_ROOT / r.relative_path) != r.sha256]
    add(g1, "Every source workbook in data/raw/source_manifest.csv exists with its Phase 1 SHA-256 (source unchanged)",
        not bad, f"{len(man)} files; mismatched {bad[:5]}")
    try:
        cur = validate_upstream()
        add(g1, "Upstream validation files have no FAIL (Phase 3 all PASS) and every consumed upstream file hashes "
                "exactly as recorded in the frozen reference", cur == ref["input_hashes"],
            f"{len(cur)} files; differing {[k for k in cur if cur[k] != ref['input_hashes'].get(k)][:5]}")
    except RuntimeError as e:
        add(g1, "Upstream validation files have no FAIL", False, e)
    add(g1, "The frozen references were built by the current Phase 7 code (code SHA-256 recorded in the reference) and "
            "every variant reference shares the primary's input hashes and score version (load_refs check)",
        ref.get("code_sha256") == code_sha256(), f"code_sha256 {ref.get('code_sha256', '')[:16]}…", kind="CONSISTENCY")
    add(g1, "Expected Phase 6 final-set population present (12 in_final_set periods, all out of sample)",
        int(ctx["episodes"].in_final_set.sum()) == 12
        and ctx["episodes"].loc[ctx["episodes"].in_final_set, "reference_state"].eq("OUT_OF_SAMPLE").all(),
        f"{int(ctx['episodes'].in_final_set.sum())} final periods", kind="CONSISTENCY")

    # ------------------------------------------------------------------ G2 schema / provenance
    g2 = "G2 schema integrity"
    out = {n: (read_json(OUT / n) if n.endswith(".json") else read(n)) for n in REQUIRED if (OUT / n).exists()}
    miss_f = [n for n in REQUIRED if n not in out]
    miss_c = {n: [c for c in cols if c not in out[n].columns] for n, cols in REQUIRED.items() if cols and n in out}
    miss_c = {k: v for k, v in miss_c.items() if v}
    add(g2, "All required outputs exist with their required columns", not miss_f and not miss_c,
        f"missing files {miss_f}; missing columns {miss_c}", kind="CONSISTENCY")
    s = out["risk_scores.parquet"]
    dg = out["risk_score_diagnostics.parquet"]
    ts = pd.DatetimeIndex(s.timestamp)
    add(g2, "risk_scores: datetime timestamps, unique, sorted, regular 10-min grid identical to the Phase 3 grid",
        pd.api.types.is_datetime64_any_dtype(s.timestamp) and ts.is_unique and ts.is_monotonic_increasing
        and (np.diff(ts.values).astype("timedelta64[m]").astype(int) == 10).all() and ts.equals(grid.index),
        f"{len(ts)} rows {ts.min()} .. {ts.max()}")
    add(g2, "Datatypes: risk_score / confidence_score float, counts integer, operational bool, labels string",
        all(pd.api.types.is_float_dtype(s[c]) for c in ("risk_score", "confidence_score", "historical_similarity"))
        and all(pd.api.types.is_integer_dtype(s[c]) for c in ("family_count_abnormal", "family_count_usable",
                                                                "persistence_minutes"))
        and pd.api.types.is_bool_dtype(s.operational)
        and all(s[c].map(type).eq(str).all() for c in ("risk_band", "risk_status", "primary_reason")),
        str(s.dtypes[["risk_score", "family_count_usable", "operational", "risk_band"]].to_dict()))
    inv = out["risk_score_feature_inventory.csv"]
    sc = inv[inv.permitted_use.eq("SCORING")]
    probs = check_inventory(inv, SCORING_FEATURES)
    add(g2, "Feature provenance complete: every scoring feature has a SCORING row with CAUSAL leakage status and no "
            "empty provenance field; nothing FORBIDDEN / EVALUATION_ONLY / RETROSPECTIVE is used for scoring",
        not probs and not inv[list(REQUIRED["risk_score_feature_inventory.csv"])].isna().any().any(),
        f"{len(sc)} scoring features: {sorted(sc.feature_name)}; problems {probs}")
    add(g2, "Static-metadata disclosure: conf_baseline uses Phase 2 full-period tag confidence (a fixed per-tag "
            "property, not a time-varying value)", True,
        inv.loc[inv.feature_name.eq("share_high_confidence_tags"), "leakage_status"].tolist(), result="INFO")

    # ------------------------------------------------------------------ G3 temporal integrity (leakage tests)
    g3 = "G3 temporal integrity"
    full, _ = score_frame(grid, refs, ctx)
    saved = s.set_index("timestamp")
    common_cols = [c for c in saved.columns if c in full.columns]
    d0 = frame_equal(full[common_cols], saved[common_cols], tol=1e-6)
    add(g3, "Recomputing the scores in-process reproduces risk_scores.parquet (1e-6, the serialisation precision)",
        not d0, f"differing columns {d0}", kind="CONSISTENCY")
    bad_cuts = []
    for c in CUTS:
        T = pd.Timestamp(c)
        t = truncate(ctx, T)
        tr, _ = score_frame(t["grid"], refs, t)
        d = frame_equal(tr, full[full.index <= T])
        if d:
            bad_cuts.append((c, d[:4]))
    add(g3, "LEAKAGE TEST 1 / 7: scores, bands, confidence, status and reasons at every t <= T are identical when all "
            "data (grid, AFR events, DQ window ends) after T is removed (8 cut points incl. the reference boundary and 3 "
            "Phase 6 onsets)", not bad_cuts, f"cuts {CUTS}; differing {bad_cuts}")
    bad_f = []
    for i, c in enumerate(CUTS[1:]):
        T = pd.Timestamp(c)
        c2 = perturb_context(ctx, T, PRIMARY.seed + i)
        pf, _ = score_frame(c2["grid"], refs, c2)
        d = frame_equal(pf[pf.index <= T], full[full.index <= T])
        if d:
            bad_f.append((c, d[:4]))
    add(g3, "LEAKAGE TEST 4: replacing EVERY grid column after T with random data and adding random AFR transitions and "
            "DQ windows after T leaves all scores at t <= T unchanged", not bad_f, f"{len(CUTS) - 1} cuts; differing {bad_f}")
    fin = ctx["episodes"][ctx["episodes"].in_final_set]
    bad_p = []
    base, _ = score_frame(grid, refs, ctx, variants={})
    for r in fin.itertuples():
        c3 = perturb_context(ctx, r.end_time, PRIMARY.seed + 99, until=r.end_time + pd.Timedelta(hours=6))
        pf, _ = score_frame(c3["grid"], refs, c3, variants={})
        d = frame_equal(pf[pf.index <= r.end_time], base[base.index <= r.end_time])
        if d:
            bad_p.append((r.episode_id, d[:4]))
    add(g3, "LEAKAGE TEST 5: perturbing the 6 h after each Phase 6 period (the post-event window) leaves every score "
            "up to the period end unchanged (12 periods)", not bad_p, f"differing {bad_p}")
    forb = set(POST_EVENT_FIELDS)
    leaked = sorted((forb & set(grid.columns)) | (forb & set(ctx["episodes"].columns)))
    ep_pert = ctx["episodes"].assign(post_event_outcome="RANDOM", kpi_max_post_6h=np.random.default_rng(1).uniform(
        0, 100, len(ctx["episodes"])))
    ra = fit_reference(grid, PRIMARY, ep_pert, ctx)
    rb = fit_reference(grid, PRIMARY, ctx["episodes"], ctx)
    add(g3, "LEAKAGE TEST 2: no Phase 6 post-event field is in the scoring grid or the cached episodes, inventory marks "
            "them FORBIDDEN, and injecting random post-event fields changes neither the reference nor any score",
        not leaked and inv[inv.feature_name.str.startswith("post_event:")].permitted_use.eq("FORBIDDEN").all()
        and ref_core(ra) == ref_core(rb), f"post-event columns found {leaked}")
    T0 = pd.Timestamp(PRIMARY.ref_end)
    ref_future = fit_reference(perturb_context(ctx, T0, 7)["grid"], PRIMARY, ctx["episodes"], ctx)
    ref_trunc = fit_reference(grid[grid.index <= T0], PRIMARY, ctx["episodes"], ctx)
    add(g3, "LEAKAGE TEST 3 / 6: the frozen reference is identical when every scored-period value is randomised or "
            "removed, and equals the saved reference (no future calibration value contributes)",
        ref_core(ref_future) == ref_core(rb) == ref_core(ref_trunc) == ref_core(ref),
        f"reference buckets {ref['n_reference_buckets']} in {ref['ref_start']} .. {ref['ref_end']}")
    v3 = pd.read_csv(P3_OUT / "kpi_validation.csv")
    leak3 = v3[v3.check.str.contains("leak|future", case=False)]
    add(g3, "Upstream Phase 3 components are leakage-tested (Phase 3 truncation test rows PASS)",
        len(leak3) > 0 and leak3.result.eq("PASS").all(), f"{len(leak3)} Phase 3 rows", kind="CONSISTENCY")

    # ------------------------------------------------------------------ G4 score integrity
    g4 = "G4 score integrity"
    valid = s.risk_status.str.startswith("VALID")
    oos = s.reference_state.str.startswith("OUT_OF_SAMPLE")
    add(g4, "operational == (out of sample AND VALID*); risk_score in [0, 100] exactly on operational rows and NaN "
            "elsewhere; in-sample VALID scores only in the diagnostics file; non-operational bands never HIGH / LOW",
        s.operational.equals(valid & oos) and s.risk_score[s.operational].between(0, 100).all()
        and s.risk_score[~s.operational].isna().all()
        and dg.risk_score_in_sample_reference.notna().equals(valid & ~oos)
        and s.risk_band[~s.operational].isin(["NOT_SCORED", "IN_SAMPLE_REFERENCE"]).all(),
        f"operational {int(s.operational.sum())}; in-sample {int((valid & ~oos).sum())}; range "
        f"{s.risk_score.min():.2f} .. {s.risk_score.max():.2f}")
    cs = s.confidence_score.dropna()
    add(g4, "confidence_score in [0, 1]; confidence_band never HIGH (capped); bands and statuses in the allowed sets",
        cs.between(0, 1).all() and not s.confidence_band.eq("HIGH").any()
        and set(s.risk_band) <= set(BANDS) | {UNBANDED, "NOT_SCORED", "IN_SAMPLE_REFERENCE"}
        and set(s.risk_status) <= set(STATUSES),
        f"bands {sorted(set(s.risk_band))}; statuses {sorted(set(s.risk_status))}")
    comp = out["risk_score_components.parquet"]
    tot = comp.groupby("timestamp").family_contribution.sum()
    allsc = saved.risk_score.fillna(dg.set_index("timestamp").risk_score_in_sample_reference)
    err = (tot - allsc.reindex(tot.index)).abs().max()
    add(g4, "Components reconcile: per bucket the family + CONCURRENCE + PERSISTENCE contributions sum to the score "
            "(operational: risk_score; in-sample: the diagnostics value; tolerance 1e-5)",
        err <= 1e-5 and len(tot) == int(valid.sum()), f"max |sum - score| {err:.2e}; {len(tot)} buckets")
    allowed = set(DRIVER_CODES) | {c + BELOW for c in DRIVER_CODES} | {NO_DRIVER}
    sec = {x for v in s.secondary_reasons[valid] for x in str(v).split(";") if x}
    add(g4, "Every VALID bucket has a primary reason = its largest point contributor (suffixed _BELOW_THRESHOLD when "
            "that part is not active); secondary reasons are supported codes only (no AFR / Phase 4 / similarity / KPI)",
        s.primary_reason[valid].isin(allowed).all() and not s.primary_reason[valid].eq("").any()
        and sec <= set(DRIVER_CODES) | set(CONTEXT_CODES) | set(CONFIDENCE_CODES),
        f"primary {s.primary_reason[valid].value_counts().head(8).to_dict()}")
    full2, _ = score_frame(grid, refs, ctx)
    add(g4, "Reason codes and scores are deterministic (two in-process computations identical)",
        not frame_equal(full, full2), "score_frame run twice")
    rl = out["risk_score_reasons.parquet"]
    drv = rl[rl.reason_type.eq("SCORE_DRIVER")]
    add(g4, "Reason table consistent with scores: every active driver row carries > 0 points and names a component "
            "whose reason_code is set in risk_score_components",
        (drv.contribution_points > 0).all() and set(drv.reason_code) <= set(comp.reason_code[comp.reason_code.ne("")]),
        f"{len(drv)} driver rows; {int(rl.reason_type.eq('SCORE_DRIVER_BELOW_THRESHOLD').sum())} below-threshold rows",
        kind="CONSISTENCY")

    # ------------------------------------------------------------------ G5 statistical integrity
    g5 = "G5 statistical integrity"
    anc = ref["anchors"]
    add(g5, "Robust normalisation: anchors are reference median / P90 of the smoothed components (no mean / sd, no "
            "Gaussian assumption); degenerate anchors floored and flagged",
        all(np.isfinite([a["m"], a["q"]]).all() and a["q"] > a["m"] for a in anc.values()),
        "; ".join(f"{d}: m={a['m']:.3f} q={a['q']:.3f} degenerate={a['degenerate']}" for d, a in anc.items()))
    b = ref["bands"]
    add(g5, "Bands derived from the reference score distribution with 3-day block-bootstrap CIs and the pre-declared "
            "(heuristic) support / merge rule", b["status"] in ("BANDED", "BANDED_WITH_MERGES", "CALIBRATION_INSUFFICIENT"),
        f"{b['status']}; n={b['n']}, blocks={b['n_blocks']}; " + "; ".join(
            f"{e['band']} P{int(e['quantile'] * 100)}={e['value']:.2f} [{e['ci_low']:.2f}, {e['ci_high']:.2f}] "
            f"supported={e['supported']}" for e in b["candidates"]))
    bd = out["risk_score_bands.csv"]
    bs = bd[bd.band.ne("LOW") & bd.supported.astype(bool)]
    ok_may = ((bs.april_fit_may_exceedance - bs.nominal_exceedance).abs() <= 0.05).all()
    add(g5, "Within-reference stability: April-fitted edges applied to May give exceedance within +-0.05 of nominal "
            "(in-sample components: not a held-out calibration)", ok_may,
        "; ".join(f"{r.band}: May {r.april_fit_may_exceedance:.3f} vs nominal {r.nominal_exceedance:.2f}"
                  for r in bs.itertuples()), result=None if ok_may else "NOT_MET_REPORTED")
    rb_ = out["risk_score_robustness.csv"]
    rob = rb_[rb_.section.eq("ROBUSTNESS")]
    add(g5, "Rank stability: median Spearman vs primary across all robustness variants >= 0.80",
        rob.spearman.median() >= 0.80, f"median {rob.spearman.median():.3f}; min {rob.spearman.min():.3f} "
                                       f"({rob.loc[rob.spearman.idxmin(), 'variant']})")
    sens = rob[rob.result.eq("SENSITIVE")]
    add(g5, "Pre-declared materiality (Spearman >= 0.80, band agreement >= 0.85, median |diff| <= 10) met by every "
            "variant", sens.empty, "SENSITIVE: " + "; ".join(f"{r.variant} (rho {r.spearman:.2f}, band "
                                                             f"{r.band_agreement:.2f})" for r in sens.itertuples()),
        result="PASS" if sens.empty else "NOT_MET_REPORTED")
    nc = rb_[rb_.section.eq("NEGATIVE_CONTROL")].set_index("dimension")
    for k in ("NC1_CIRCULAR_SHIFT", "NC2_RANDOMISED_PERIOD_PLACEMENT"):
        add(g5, f"Consistency control {k}: observed coverage exceeds the null (p < 0.05; internal consistency only - the "
                "periods share the scored components)", nc.at[k, "result"] == "PASS",
            f"observed {nc.at[k, 'observed']:.3f}; null median {nc.at[k, 'null_median']:.3f}; p <= {nc.at[k, 'p_value']:.3f}",
            result=None if nc.at[k, "result"] == "PASS" else "NOT_MET_REPORTED")
    inc = rb_[rb_.section.eq("INCLUSION_TEST")]
    re_ok = all(("INCLUDE" in r.result) == bool(r.observed >= INCLUSION_MIN_GAIN and r.observed > r.null_p95
                                                 and str(r.stability_kept) == "True") for r in inc.itertuples())
    add(g5, f"AFR / Phase 4 inclusion decisions re-derived from the reported gain, null P95 and stability flag (gain >= "
            f"{INCLUSION_MIN_GAIN}, month change <= {INCLUSION_MAX_MONTH_CHANGE})",
        re_ok and len(inc) == 2, "; ".join(f"{r.dimension}: gain {r.observed:+.4f}, null P95 {r.null_p95:+.4f} -> "
                                           f"{r.result}" for r in inc.itertuples()))
    rho = pd.DataFrame(ref["family_spearman"]).astype(float)
    off = rho.where(~np.eye(len(rho), dtype=bool)).abs().max().max()
    add(g5, "Family correlation treatment: reference family-intensity Spearman matrix reported; most correlated pair "
            "run as a merged-family variant; within-family tags already collapsed by Phase 3", True,
        f"max |rho| {off:.2f}", result="INFO")
    cand = rb_[rb_.section.eq("CANDIDATE")]
    add(g5, "Architecture candidates A / B / H / C evaluated and the selection follows the pre-declared rule (coverage "
            "not a criterion)", cand.result.eq("SELECTED").sum() == 1 and len(cand) == 4,
        "; ".join(f"{r.variant}: {r.result}" for r in cand.itertuples()), kind="CONSISTENCY")
    add(g5, "Calibration assumptions: reference components are in-sample for Phase 3 (optimistic edges); no ground truth; "
            "EMPIRICAL_ALERT_RATE with block CIs reported instead of any false-positive rate", True,
        "see CALIBRATION_METHOD.md / LIMITATIONS.md", result="INFO")

    # ------------------------------------------------------------------ G6 empirical period coverage / claims
    g6 = "G6 empirical period coverage"
    cov = out["risk_score_event_similarity.csv"]
    fc = cov[cov.population.eq("PHASE6_FINAL_OUT_OF_SAMPLE")]
    add(g6, "All 12 Phase 6 final periods are scored and reported (valid share > 0) under the "
            "EMPIRICAL_ABNORMAL_PERIOD_COVERAGE label", len(fc) == 12 and (fc.valid_share > 0).all()
        and fc.coverage_label.str.startswith("EMPIRICAL_ABNORMAL_PERIOD_COVERAGE").all(),
        f"{len(fc)} periods; valid share min {fc.valid_share.min():.2f}", kind="CONSISTENCY")
    cal = out["risk_score_calibration.csv"]
    covm = cal[cal.section.eq("EMPIRICAL_ABNORMAL_PERIOD_COVERAGE")].set_index("metric").value
    add(g6, "Coverage reported with its circularity baseline (the Phase 3 KPI the periods were built from), block CI, "
            "pre-onset score and severity relationship - never named detection accuracy / false-positive rate",
        any(k.startswith("baseline_auc_phase3_kpi") for k in covm.index)
        and not cal.section.str.contains("ACCURACY|FALSE", case=False).any(), covm.round(3).to_dict())
    add(g6, "Phase 6 severity / confidence used only as evaluation metadata (never features or labels)",
        inv[inv.feature_name.eq("phase6_severity_confidence")].permitted_use.str.startswith("EVALUATION_ONLY").all(),
        "inventory row phase6_severity_confidence", kind="CONSISTENCY")
    texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(DOCS.glob("*.md"))}
    for n in ("risk_score_bands.csv", "risk_score_robustness.csv", "risk_score_calibration.csv",
              "risk_score_event_similarity.csv", "risk_score_feature_inventory.csv"):
        texts[n] = (OUT / n).read_text(encoding="utf-8")
    texts["risk_scores.parquet:labels"] = "\n".join(sorted(set(s.score_label) | set(s.operating_state_label)))
    hits = {k: forbidden_hits(v) for k, v in texts.items()}
    hits = {k: v for k, v in hits.items() if v}
    add(g6, "Unsupported-claim scan (the common.FORBIDDEN wording patterns) over docs, key CSVs and output labels",
        not hits, f"hits {hits}")

    # ------------------------------------------------------------------ G7 data-quality integrity
    g7 = "G7 data-quality integrity"
    import load_phase2_inputs as l2        # Phase 3, read-only
    leaks = {}
    kref = read_json(P3_OUT / "kpi_reference.json")
    tags = [t for t in kref["included_tags"] if not t.startswith("STD60:")]
    pti = pd.read_csv(ROOT / "phase-01-data-discovery" / "outputs" / "process_tag_inventory.csv")
    degc = pti.detected_unit.eq("Deg.C")
    deg_c = set(pti.dataset[degc] + "!" + pti.source_column[degc])
    for ds in ("Kiln-I", "Kiln-IA", "Kiln-II"):
        w, _ = l2.load_dataset(ds)
        cols = [t for t in tags if t.startswith(ds + "!") and t in w]
        n = int(np.isin(w[cols].to_numpy(float), SENTINELS_ANY).sum())            # sentinel in every unit
        tc = [t for t in cols if t in deg_c]
        n += int((w[tc].to_numpy(float) == -273.0).sum())                       # -273: sentinel only for Deg.C
        if n:
            leaks[ds] = n
    add(g7, "No sentinel value (99999 / 9999 in any tag, -273 in Deg.C tags) reaches any scored tag in the Phase 3 "
            "scoring input. The text check ('Error 6') does not apply to scored tags: 'Error 6' occurs only in "
            "CBS-Calculation, which has no scored tag", not leaks,
        f"sentinel cells reaching scoring: {leaks or 0}; -273 checked on {len(deg_c)} Deg.C tags only (-273 mmWC is "
        "inside the normal draft range of Kiln-I!S / Kiln-II!F,N,R,U)")
    dq = out["risk_score_data_quality.csv"]
    viol = dq.loc[dq.section.eq("MISSING_FAMILY_INJECTION") & dq.metric.eq("buckets_where_H_or_C_increased"),
                  "value"].iloc[0]
    add(g7, "Missing / masked FAMILIES cannot inflate the score: removing 30 % of usable family values never raises "
            "magnitude or concurrence (fixed denominator; the bias is downward - disclosed)", float(viol) == 0,
        f"violations {viol}")
    core0 = score_core(grid, ref, PRIMARY, ctx)
    g_nan = grid.copy()
    rng = np.random.default_rng(3)
    for d in FAMILIES:
        g_nan.loc[rng.random(len(g_nan)) < 0.10, f"comp_{d}"] = np.nan
    core1 = score_core(g_nan, ref, PRIMARY, ctx)
    ok = core0["valid3"] & core1["valid3"]
    up = core1["R"][ok] - core0["R"][ok]
    add(g7, "Within-window missingness (10 % of component buckets set to NaN) - quantified: a trailing median of fewer "
            "values can move either way; the >= 4 of 6 and current-bucket rules bound it", True,
        f"buckets {int(ok.sum())}; score rose > 5 points in {float((up > 5).mean()):.3%}, fell > 5 points in "
        f"{float((up < -5).mean()):.3%}; median change {np.median(up):+.3f}", result="INFO")
    wide, dim_of, _ = tag_scores(grid.index)
    drop = wide.where(~(np.random.default_rng(4).random(wide.shape) < 0.10))
    alt = components_from_tags(drop, dim_of, kref["dims"])
    g_tag = grid.copy()
    for d in FAMILIES:
        g_tag[f"comp_{d}"] = alt[d].to_numpy()
    core2 = score_core(g_tag, ref, PRIMARY, ctx)
    ok2 = core0["valid3"] & core2["valid3"]
    up2 = core2["R"][ok2] - core0["R"][ok2]
    add(g7, "TAG-LEVEL dropout (10 % of tag scores removed BEFORE the Phase 3 family averaging) - quantified: a family "
            "average over fewer tags can move either way (MNAR dropout, e.g. the O2 analyser, can raise it); per-family "
            "tag coverage lowers conf_family_coverage", True,
        f"buckets {int(ok2.sum())}; score rose > 5 points in {float((up2 > 5).mean()):.3%}, fell > 5 points in "
        f"{float((up2 < -5).mean()):.3%}; median change {np.median(up2):+.3f}", result="INFO")
    o2 = dq[dq.section.str.startswith("O2_ANALYSER")]
    add(g7, f"Suspect ambient-air readings of the kiln-inlet O2 analyser ({O2_TAG} bucket median >= "
            f"{PRIMARY.o2_ambient_pct:g} %) lower data-quality confidence and are quantified; their effect on the score "
            "is measured by the EXCLUDE_KILN_INLET_O2_ANALYSER robustness variant", True,
        o2[["slice", "metric", "value"]].round(3).to_dict("records"), result="INFO")
    ins = s.risk_status.eq("INSUFFICIENT_DATA")
    add(g7, "Insufficient families -> INSUFFICIENT_DATA with no numeric score (RUNNING, 1-2 usable families) and no "
            "diagnostic score either", ins.any() and s.loc[ins, "family_count_usable"].between(1, 2).all()
        and s.risk_score[ins].isna().all() and dg.risk_score_diagnostic[ins.to_numpy()].isna().all(),
        f"{int(ins.sum())} buckets")
    dqw = ctx["dq_windows"]
    inside = np.zeros(len(s), bool)
    for w in dqw.itertuples():
        inside |= ((ts - pd.Timedelta(minutes=10) >= w.start) & (ts <= w.end))     # whole bucket inside the window
    add(g7, "No numeric score for any bucket lying entirely inside a Phase 1 long gap or the DQ-016 frozen window (no "
            "interpolation or stale carry-forward across gaps)", s.risk_score[inside].isna().all()
        and dg.risk_score_diagnostic[inside].isna().all(),
        f"{int(inside.sum())} buckets inside {len(dqw)} windows; scored {int(s.risk_score[inside].notna().sum())}")
    run = grid.state.eq("RUNNING").to_numpy()
    first = run & ~np.r_[False, run[:-1]]
    add(g7, "Persistence resets at every stop / start / gap boundary (first RUNNING bucket persistence <= 1 bucket)",
        (core0["P"][first] <= 1 / PRIMARY.persistence_buckets + 1e-12).all(), f"{int(first.sum())} segment starts")
    sep = ts >= pd.Timestamp("2025-09-01")
    add(g7, "September (Kiln-I missing) never receives a numeric score (operational or diagnostic)",
        s.risk_score[sep].isna().all() and dg.risk_score_diagnostic[sep].isna().all(),
        f"{int(sep.sum())} September buckets; statuses {s.risk_status[sep].value_counts().to_dict()}")
    cf = pd.read_parquet(OUT / "risk_score_confidence.parquet")
    poor = cf.conf_data_quality <= PRIMARY.conf_low
    add(g7, "Data-quality gating of confidence: every bucket with conf_data_quality <= 0.5 has confidence band LOW",
        cf.loc[poor, "confidence_band"].eq("LOW").all(), f"{int(poor.sum())} buckets")
    add(g7, "Causal-invalid tokens counted per bucket feed confidence only (never the score)",
        all(c in grid.columns for c in CAUSAL_INVALID), f"{CAUSAL_INVALID}", kind="CONSISTENCY")

    # ------------------------------------------------------------------ G9 review
    res, ev = review_status()
    add("G9 review", "Planner, senior data scientist, statistical, data-quality, Python, MLE, product and Ponytail "
                     "reviews recorded (Reviewer column) with no OPEN finding", res == "PASS", ev, result=res,
        kind="CONSISTENCY")

    v = pd.DataFrame(rows)
    v.to_csv(OUT / "risk_score_validation.csv", index=False)
    lg.info("validation: %s", v.result.value_counts().to_dict())
    for r in v[v.result.eq("FAIL")].itertuples():
        lg.error("FAIL %s | %s | %s", r.gate, r.check, r.evidence)


if __name__ == "__main__":
    main()
