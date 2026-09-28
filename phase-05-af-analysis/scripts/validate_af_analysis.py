"""Step - Validation gates G1-G6 (G7 reproducibility and the source / upstream snapshots are added by run_phase5.py).

Writes outputs/afr_validation.csv  (gate, check, check_type, result, evidence)
check_type: INDEPENDENT (re-derived here from inputs, can fail), REGRESSION_GUARD (re-runs production code on a sample),
INFO (reported, not pass/fail). result: PASS / FAIL / INFO / NOT_MET_REPORTED.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control

import af_context as ax
from af_core import (AFR, AFR_LIQUID, BAND_LABEL, CACHE, CONTROL_INPUTS, EVIDENCE, EXCLUDED_TARGETS, FAMILIES, OUT, P1_OUT,
                     P2_OUT, P3_OUT, P4_OUT, PRIMARY, PROCESSED, REL_COLUMNS, circular_shift, fit_bands, forbidden_hits, ic,
                     log, read_out, sha256, write_csv)
from p3common import processed_path

lg = log("validate_af_analysis")
REL_FILES = ["afr_load_relationships.csv", "afr_combustion_relationships.csv", "afr_thermal_relationships.csv",
             "afr_efficiency_relationships.csv", "afr_indicator_relationships.csv"]
REQUIRED_OUTPUTS = ["afr_inventory.csv", "afr_data_quality.csv", "afr_operating_bands.csv", "afr_daily_summary.csv",
                    "afr_monthly_summary.csv", "afr_transition_episodes.parquet", *REL_FILES, "afr_matched_analysis.csv",
                    "afr_sensitivity_analysis.csv", "afr_data_requirements.csv"]
INV_COLS = ["indicator_id", "original_name", "dataset", "unit", "fuel_category", "signal_type", "control_or_measurement",
            "coverage_start", "coverage_end", "valid_observations", "missing_fraction", "zero_fraction", "nonzero_fraction",
            "health_class", "unit_confidence", "analysis_status", "exclusion_reason"]
UPSTREAM = {"phase-04": P4_OUT, "phase-03": P3_OUT, "phase-02": P2_OUT, "phase-01": P1_OUT}
ROWS: list[dict] = []


def add(gate, check, ok, ev, kind="INDEPENDENT", result=None):
    ROWS.append({"gate": gate, "check": check, "check_type": kind,
                 "result": result or ("PASS" if ok else "FAIL"), "evidence": str(ev)[:900]})


def upstream_path(key: str):
    prefix, name = key.split("/", 1)
    return PROCESSED / name.split("/")[-1] if prefix == "data" else UPSTREAM[prefix] / name


def g1():
    h = json.loads((CACHE / "input_hashes.json").read_text())
    bad = [k for k, v in h.items() if sha256(upstream_path(k)) != v]
    add("G1 source integrity", "Every consumed upstream file (Phases 1-4 outputs, data/processed) has the SHA-256 recorded "
        "when Phase 5 started", not bad, f"{len(h)} files re-hashed; changed: {bad}")
    v3, v4 = pd.read_csv(P3_OUT / "kpi_validation.csv"), pd.read_csv(P4_OUT / "indicator_validation.csv")
    add("G1 source integrity", "Upstream validation: Phase 3 all PASS, Phase 4 no FAIL",
        (v3.result == "PASS").all() and not (v4.result == "FAIL").any(),
        f"P3 {v3.result.value_counts().to_dict()}; P4 {v4.result.value_counts().to_dict()}")


def g2(rel: pd.DataFrame):
    inv1 = pd.read_csv(P1_OUT / "process_tag_inventory.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column)
    inv1 = inv1.set_index("tag")
    holds = pd.read_csv(P2_OUT / "column_holds.csv").assign(tag=lambda h: h.dataset + "!" + h.source_column)
    held = set(holds.tag)
    missing = [o for o in REQUIRED_OUTPUTS if not (OUT / o).exists()]
    add("G2 schema", "All required Phase 5 outputs exist", not missing, f"missing {missing}")
    inv = read_out("afr_inventory.csv")
    add("G2 schema", "afr_inventory.csv has every required column", set(INV_COLS) <= set(inv.columns),
        f"missing {sorted(set(INV_COLS) - set(inv.columns))}")
    ok, ev = True, []
    iv = inv.set_index("indicator_id")
    for t in (AFR, AFR_LIQUID):
        match = t in inv1.index and inv1.loc[t, "original_name"] == iv.loc[t, "original_name"] \
            and inv1.loc[t, "detected_unit"] == iv.loc[t, "unit"]
        ok &= bool(match)
        ev.append(f"{t} '{iv.loc[t, 'original_name']}' {iv.loc[t, 'unit']} matches Phase 1: {match}")
    add("G2 schema", "AFR tags exist in the Phase 1 inventory with the exact original_name and unit", ok, "; ".join(ev))
    targets = sorted({t for f in FAMILIES.values() for t in f if not t.startswith("KPI:")})
    absent = [t for t in targets if t not in inv1.index]
    add("G2 schema", "Every process target / covariate tag exists in the Phase 1 inventory", not absent,
        f"{len(targets)} tags; absent {absent}")
    hl = [t for t in targets if t in held]
    add("G2 schema", "No Phase 2 held column is used as a target or covariate", not hl, f"held used: {hl}")
    bad_ex = [t for t in EXCLUDED_TARGETS if ".." not in t and t not in held]
    add("G2 schema", "Every excluded-target reason citing a Phase 2 hold matches an actual hold", not bad_ex,
        f"{len(EXCLUDED_TARGETS)} exclusions; unmatched {bad_ex}")
    sigs = set(rel.afr_signal.dropna())
    add("G2 schema", "No invented AFR variable: every relationship row uses afr_signal Kiln-I!K", sigs == {AFR}, f"{sigs}")
    p4inv = pd.read_csv(P4_OUT / "indicator_candidate_inventory.csv")
    k4 = p4inv[p4inv.indicator_tag.eq(AFR)]
    add("G2 schema", "Reserved Kiln-I!K handling documented: Phase 4 reserved it (not analysed); Phase 5 analyses it",
        len(k4) == 1 and "RESERVED FOR PHASE 5" in str(k4.exclusion_reason.iloc[0])
        and iv.loc[AFR, "analysis_status"] == "ANALYSED",
        f"Phase 4: {k4.exclusion_reason.iloc[0] if len(k4) else 'absent'}")
    fuel = inv[inv.indicator_id.isin(CONTROL_INPUTS)]
    add("G2 schema", "All fuel firing tags are classified FUEL_CONTROL_INPUT (set-points, never outcomes)",
        fuel.control_or_measurement.eq("FUEL_CONTROL_INPUT").all(), f"{len(fuel)} fuel tags")
    fuel_tags = {t for t, c in CONTROL_INPUTS.items() if c == "FUEL_CONTROL_INPUT"}
    misuse = rel[rel.target_signal.isin(fuel_tags) & ~rel.target_family.eq("FUEL_CO_MANIPULATION")]
    add("G2 schema", "Fuel control inputs appear as targets only in the co-manipulation family (never as process outcomes)",
        misuse.empty, f"{len(misuse)} misuse rows")
    liq = iv.loc[AFR_LIQUID]
    add("G2 schema", "Liquid AFR formally assessed: INSUFFICIENT_DATA with a quantitative reason",
        liq.analysis_status == "INSUFFICIENT_DATA" and "LIQUID_AFR_ANALYSIS = INSUFFICIENT_DATA" in liq.exclusion_reason,
        liq.exclusion_reason)
    miss_cols = [c for c in REL_COLUMNS if c not in rel.columns]
    add("G2 schema", "Relationship outputs carry every required relationship column", not miss_cols, f"missing {miss_cols}")
    ev_bad = sorted(set(rel.evidence.fillna("")) - set(EVIDENCE) - {""})
    add("G2 schema", "Evidence labels are from the allowed set only", not ev_bad, f"unexpected {ev_bad}")
    pv = pd.concat([rel.p_value, rel.adjusted_p_value]).dropna()
    ci = rel.dropna(subset=["confidence_interval_low", "confidence_interval_high"])
    add("G2 schema", "p / q values lie in [0, 1] and every CI has low <= high",
        pv.between(0, 1).all() and (ci.confidence_interval_low <= ci.confidence_interval_high + 1e-12).all(),
        f"{len(pv)} p/q values; {len(ci)} CIs")
    names = " ".join(c.lower() for o in REQUIRED_OUTPUTS if o.endswith(".csv") for c in read_out(o).columns)
    bad_metric = [w for w in ("tsr", "substitution_rate", "mj_", "calorific", "cv_") if w in names]
    add("G2 schema", "No fuel-energy metric (substitution rate, energy flow, heat value) is computed in any output", not bad_metric,
        f"flagged column fragments {bad_metric}")
    na = inv[inv.analysis_status.eq("NOT_AVAILABLE")].indicator_id.tolist()
    add("G2 schema", "Unavailable fuel properties are listed NOT_AVAILABLE, never estimated", len(na) >= 5, f"{na}")
    hits = forbidden_hits("\n".join(rel.interpretation.fillna("").astype(str)))
    add("G2 schema", "Wording scan of every interpretation: no causal or control-recommendation language", not hits,
        f"{len(hits)} hits: {hits[:3]}")


def perturbed_ctx(t0: int, rng) -> ax.Context:
    c = ax.load_context(PRIMARY)
    n = len(c.afr) - t0 - 1
    c.afr[t0 + 1:] = rng.uniform(0, 60, n)
    for col in c.b.columns:
        if col != "bucket_state":
            c.b.iloc[t0 + 1:, c.b.columns.get_loc(col)] = rng.normal(0, 1, n)
    c.g.iloc[t0 + 1:, [c.g.columns.get_loc("K"), c.g.columns.get_loc("D")]] = rng.uniform(0, 100, (n, 2))
    return c


def g3(rel: pd.DataFrame):
    ctx = ax.load_context(PRIMARY)
    try:
        ic.check_grid(ctx.index)
        grid_ok = True
    except ValueError as e:
        grid_ok = str(e)
    add("G3 temporal", "Analysis grid is a regular 10-min grid (positional trailing windows are exact)", grid_ok is True,
        grid_ok)
    sep = ctx.index >= pd.Timestamp("2025-09-01")
    inwin = np.zeros(len(ctx.index), bool)
    for w in ax.WIN_DEF:
        inwin |= ax.window_span(ctx, w)
    add("G3 temporal", "No September bucket belongs to any analysis window (Kiln-I September unavailable)",
        not (inwin & sep).any(), f"{int(sep.sum())} September buckets, {int((inwin & sep).sum())} inside windows")
    jun = ax.window_span(ctx, "JUN")
    add("G3 temporal", "June evaluation starts 06:00 (first 6 h overlap the Phase 3 training window)",
        ctx.index[jun].min() == pd.Timestamp("2025-06-01 06:00"), f"first JUN bucket {ctx.index[jun].min()}")
    rng = np.random.default_rng(7)
    fails = []
    designs = (("THERMAL", "Kiln-II!O", "LAGGED_LEVEL", 60), ("COMBUSTION", "Kiln-I!AD", "FUTURE_CHANGE", 60),
               ("EFFICIENCY", "KPI:K", "FUTURE_CHANGE", 120), ("LOAD", "Kiln-I!C", "MOMENTUM", 0))
    for t0 in rng.choice(np.flatnonzero(ctx.running), 6, replace=False):
        c2 = perturbed_ctx(int(t0), rng)
        for fam, tag, atype, lag in designs:
            x0, _, Z0 = ax.design(ctx, fam, tag, atype, lag)
            x1, _, Z1 = ax.design(c2, fam, tag, atype, lag)
            if not (np.allclose(x0[:t0 + 1], x1[:t0 + 1], equal_nan=True)
                    and np.allclose(Z0[:t0 + 1], Z1[:t0 + 1], equal_nan=True)):
                fails.append((int(t0), tag, atype))
    add("G3 temporal", "Leakage test: every AFR feature and control at t <= t0 is unchanged when AFR and all targets after "
        "t0 are replaced by noise (6 cut points x 4 designs)", not fails, f"fails {fails[:5]}")
    bands = json.loads((CACHE / "bands.json").read_text())
    refit = fit_bands(ctx.afr[ax.window_span(ctx, "DISCOVERY")], PRIMARY)
    add("G3 temporal", "AFR band cuts re-derive from DISCOVERY data only (frozen for later months)",
        abs(refit["q_lo"] - bands["q_lo"]) < 1e-9 and abs(refit["q_hi"] - bands["q_hi"]) < 1e-9
        and bands["label"] == BAND_LABEL, f"cuts {bands['q_lo']}, {bands['q_hi']} ({bands['label']})")
    sel = rel[rel.row_role.eq("SELECTED_LAG") & rel.window.eq("DISCOVERY")]
    prof = rel[rel.row_role.isin(["SELECTED_LAG", "LAG_PROFILE"]) & rel.window.eq("DISCOVERY")]
    wrong = []
    for r in sel.itertuples():
        g = prof[(prof.target_family == r.target_family) & (prof.target_signal == r.target_signal)
                 & (prof.analysis_type == r.analysis_type) & prof.effect_size.notna()]
        if g.empty:
            continue
        g = g.assign(a=g.effect_size.abs()).sort_values(["adjusted_p_value", "a", "lag_minutes"],
                                                         ascending=[True, False, True], kind="mergesort")
        if int(g.lag_minutes.iloc[0]) != int(r.lag_minutes):
            wrong.append((r.target_signal, r.analysis_type))
    add("G3 temporal", "Lag and sign chosen on DISCOVERY only (re-derived from the published discovery lag profile)",
        not wrong, f"{len(sel)} selections; mismatches {wrong[:5]}")
    ep = pd.read_csv(CACHE / "episodes.csv")
    pre, post = PRIMARY.ep_pre_min // 10, PRIMARY.ep_post_min // 10
    bad = [e.episode_id for e in ep[ep.status.eq("ELIGIBLE")].itertuples()
           if not ctx.running[e.pos - pre: e.pos + post + 1].all()]
    add("G3 temporal", "Every ELIGIBLE AFR transition episode window [T-120, T+180] is entirely RUNNING (shutdown / restart "
        "/ gap windows set aside)", not bad, f"{int(ep.status.eq('ELIGIBLE').sum())} eligible; violations {bad[:5]}")
    clean = pre + int(PRIMARY.prior_transition_h * 6)
    dirty = [e.episode_id for e in ep[ep.status.eq("ELIGIBLE")].itertuples()
             if ((ep.pos >= e.pos - clean) & (ep.pos < e.pos)).any()]
    add("G3 temporal", "No ELIGIBLE episode has another AFR transition in its pre-window [T-120, T) (clean [T-60, T) "
        "baseline)", not dirty, f"violations {dirty[:5]}")
    long = pd.read_parquet(OUT / "afr_transition_episodes.parquet", columns=["episode_id", "signal", "rel_min"])
    order_ok = long.groupby(["episode_id", "signal"]).rel_min.apply(
        lambda s: s.is_monotonic_increasing and s.iloc[0] == -120 and s.iloc[-1] == 180).all()
    add("G3 temporal", "Episode windows are ordered T-120 .. T+180 for every episode and signal", bool(order_ok),
        f"{long.episode_id.nunique()} episodes")
    from analyze_afr_efficiency import precursor_features
    ts = pd.read_csv(P4_OUT / "indicator_episodes.csv", parse_dates=["T"])["T"]
    pos = pd.Series(np.arange(len(ctx.index)), index=ctx.index).reindex(ts).dropna().astype(int).to_numpy()[:8]
    base = precursor_features(ctx, pos, ep.pos.to_numpy())
    leak = []
    for i, t in enumerate(pos):
        c2 = ax.load_context(PRIMARY)
        c2.afr[t + 1:] = rng.uniform(0, 60, len(c2.afr) - t - 1)
        pert = precursor_features(c2, np.array([t]), ep.pos[ep.pos <= t].to_numpy())
        if not all(np.allclose(base[k][i], pert[k][0], equal_nan=True) for k in base):
            leak.append(int(t))
    add("G3 temporal", "KPI-episode AFR precursor features use AFR <= T only (future AFR perturbed: unchanged)", not leak,
        f"{len(pos)} anchors; changed {leak}")


def g4():
    dq = read_out("afr_data_quality.csv")
    add("G4 data quality", "Accounting identity minutes = missing + invalid + zero + nonzero for every signal x scope",
        bool((dq.minutes == dq.missing + dq.invalid + dq.zero + dq.nonzero).all()), f"{len(dq)} rows")
    raw = pd.read_parquet(processed_path("Kiln-I"), columns=["ts", "source_column", "value", "dup_status"],
                          filters=[("source_column", "in", ["K", "L"])])
    raw = raw[~raw.dup_status.eq("DUP_IDENTICAL_COPY")].drop_duplicates(["source_column", "ts"])
    a = dq[dq.scope.eq("ALL_SUPPLIED")].set_index("afr_signal")
    chk = {}
    for t, c in ((AFR, "K"), (AFR_LIQUID, "L")):
        v = raw[raw.source_column.eq(c)].value
        chk[t] = (int(v.isna().sum()), int(a.loc[t, "missing"]), int((v == 0).sum()), int(a.loc[t, "zero"]))
    # exact zeros are ZERO unless Phase 2 marks them invalid (then INVALID): reported zero <= raw zeros <= zero + invalid
    ok = all(x[0] == x[1] and x[3] <= x[2] <= x[3] + int(a.loc[t, "invalid"]) for t, x in chk.items())
    add("G4 data quality", "Zero and missing are distinct: independently re-counted NaN minutes equal the reported missing; "
        "exact zeros are reported as ZERO (or INVALID when Phase 2 marks them invalid), never as missing", ok,
        f"(nan, reported missing, ==0, reported zero): {chk}; invalid {a.invalid.to_dict()}")
    dup = pd.read_parquet(processed_path("Kiln-I"), columns=["source_column", "dup_status"],
                          filters=[("source_column", "==", "K")])
    nd = int(dup.dup_status.isin(["DUP_KEPT", "DUP_IDENTICAL_COPY", "DUP_CONFLICT"]).sum())
    add("G4 data quality", "Duplicate timestamps accounted for", nd == int(a.loc[AFR, "duplicate_timestamp_rows"]),
        f"processed {nd}, profile {a.loc[AFR, 'duplicate_timestamp_rows']}")
    m = pd.read_parquet(CACHE / "minute_afr.parquet")
    add("G4 data quality", "Negative (invalid) AFR values are excluded from the analysed series and counted",
        not (m.afr_p2 < 0).any() and int(a.loc[AFR, "negative"]) >= int((m.afr_raw < 0).sum()),
        f"negatives raw {int((m.afr_raw < 0).sum())}, profile {int(a.loc[AFR, 'negative'])}")
    b = pd.read_parquet(CACHE / "buckets.parquet")
    cnt = m.afr_p2.where(m.state.eq("RUNNING")).resample("10min", label="right", closed="right").count().reindex(b.index)
    viol = int((b.AFR_P2.notna() & (cnt < 8)).sum())
    add("G4 data quality", "No interpolation: every valid AFR bucket has >= 8 valid RUNNING minutes", viol == 0,
        f"{viol} violations")
    run = b.bucket_state.eq("RUNNING")
    add("G4 data quality", "Flatline handling reported: AFR_P2 (no single-tag flatline mask) vs AFR_P3MASKED coverage", True,
        f"RUNNING valid share P2 {b.AFR_P2[run].notna().mean():.3f}, P3-masked {b.AFR_P3MASKED[run].notna().mean():.3f}, "
        f"no-P2-flatline {b.AFR_NOFLAT[run].notna().mean():.3f}", kind="INFO", result="INFO")
    add("G4 data quality", "Liquid AFR sentinel candidates (>= 9,999) counted", True,
        f"{int(a.loc[AFR_LIQUID, 'sentinel_candidates_ge_9999'])} values", kind="INFO", result="INFO")


def g5(rel: pd.DataFrame):
    r = rel[rel.effect_metric.eq("partial Spearman rho")].dropna(subset=["effective_sample_size"])
    add("G5 statistics", "Autocorrelation considered: n_eff <= n on every correlation row (Bartlett / Pyper-Peterman)",
        bool((r.effective_sample_size <= r.sample_count + 1e-9).all()),
        f"{len(r)} rows; median n/n_eff {np.nanmedian(r.sample_count / r.effective_sample_size):.1f}")
    disc = rel[rel.row_role.isin(["SELECTED_LAG", "LAG_PROFILE"]) & rel.window.eq("DISCOVERY")
               & rel.effect_metric.eq("partial Spearman rho")]
    mism = 0
    for _, g in disc.groupby(["target_family", "analysis_type"]):
        g = g.dropna(subset=["p_value"])
        if len(g):            # published p are rounded to 6 dp: q must lie between BH(p - 5e-7) and BH(p + 5e-7)
            p = g.p_value.to_numpy()
            lo = false_discovery_control(np.clip(p - 5e-7, 0, 1))
            hi = false_discovery_control(np.clip(p + 5e-7, 0, 1))
            q = g.adjusted_p_value.to_numpy()
            mism += int(np.sum((q < lo - 1e-6) | (q > hi + 1e-6)))
    add("G5 statistics", "Multiple testing: BH q per family x analysis type equals scipy.stats.false_discovery_control "
        "(within the 6-dp rounding of the published p)", mism == 0, f"{len(disc)} discovery tests; mismatches {mism}")
    sel = rel[rel.row_role.eq("SELECTED_LAG")]
    key = ["target_family", "target_signal", "analysis_type"]
    w = {wn: sel[sel.window.eq(wn)].set_index(key) for wn in ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG")}
    d = w["DISCOVERY"]
    mism = []
    for k, row in d.iterrows():
        rho, q, lo, hi = row.effect_size, row.adjusted_p_value, row.confidence_interval_low, row.confidence_interval_high
        rr, rp = w["REPLICATION"].loc[k, "effect_size"], w["REPLICATION"].loc[k, "p_value"]
        au, pa = w["HOLDOUT_AUG"].loc[k, "effect_size"], w["HOLDOUT_AUG"].loc[k, "p_value"]
        rev = bool(np.isfinite(au) and np.isfinite(rho) and np.sign(au) != np.sign(rho) and pa < 0.05)
        ci_ok = bool(np.isfinite(lo) and lo * hi > 0)
        if not np.isfinite(rho):
            exp = "NOT COMPUTABLE" if row.sample_count >= 100 else "INSUFFICIENT DATA"
        elif row.sample_count < 100 or row.effective_sample_size < 30 or row.days < 10:
            exp = "INSUFFICIENT DATA"
        elif (q < 0.05 and abs(rho) >= 0.10 and ci_ok and np.isfinite(rr) and np.sign(rr) == np.sign(rho) and rp < 0.05
              and not rev and str(row.negative_control_pass) == "True"):
            exp = "ASSOCIATED"
        elif q < 0.10 and ci_ok:
            exp = "WEAK ASSOCIATION"
        else:
            exp = "NOT SUPPORTED"
        if exp != row.evidence:
            mism.append((k, row.evidence, exp))
    add("G5 statistics", "Evidence labels re-derived independently from the published statistics (pre-declared rules)",
        not mism, f"{len(d)} relationships; mismatches {mism[:4]}")
    ctx = ax.load_context(PRIMARY)
    s = d.reset_index()
    s = s[~s.target_signal.str.startswith("P4:")].iloc[[0, len(s) // 2, -2]]
    diffs = []
    for r0 in s.itertuples():
        res = ax.assoc_one(ctx, r0.target_family, r0.target_signal, r0.analysis_type, int(r0.lag_minutes), "DISCOVERY")
        diffs.append(abs(res["ci_lo"] - r0.confidence_interval_low) if np.isfinite(res["ci_lo"]) else 0.0)
    add("G5 statistics", "3-day calendar-block bootstrap CIs reproduce from production code (sample re-run)",
        max(diffs, default=0) < 1e-5, f"{len(diffs)} rows; max |dCI| {max(diffs, default=0):.2e}", kind="REGRESSION_GUARD")
    comp = d[["effect_size", "effective_sample_size", "adjusted_p_value"]].notna().all(axis=1).mean()
    add("G5 statistics", "Effect size, n, n_eff, CI and adjusted p reported for >= 95 % of selected discovery rows",
        comp >= 0.95, f"{len(d)} rows; complete share {comp:.3f}")
    add("G5 statistics", "Unstable relationships identified (stability label on every selected relationship)",
        d.stability.isin(["STABLE_SIGN", "SIGN_FLIP", "INSUFFICIENT"]).all(), d.stability.value_counts().to_dict())
    assoc = d[d.evidence.eq("ASSOCIATED")]
    add("G5 statistics", "Every ASSOCIATED correlation beats the circular-shift null (2-21 day shifts) in DISCOVERY and "
        "REPLICATION", assoc.negative_control_pass.astype(str).eq("True").all(),
        f"{len(assoc)} ASSOCIATED; null-pass share over all selected {d.negative_control_pass.astype(str).eq('True').mean():.2f}")
    p = []
    span = ax.window_span(ctx, "DISCOVERY")
    for r0 in d.reset_index().itertuples():
        if not r0.target_signal.startswith("P4:"):
            p.append(ax.assoc_one(ctx, r0.target_family, r0.target_signal, r0.analysis_type, int(r0.lag_minutes),
                                  "DISCOVERY", False, circular_shift(ctx.afr, span, 7 * 144))["p_eff"])
    p = np.asarray(p, float)
    frac = float(np.nanmean(p < 0.05))
    add("G5 statistics", "Null calibration: share of 7-day-shifted AFR tests with n_eff p < 0.05 is <= 0.15 (pre-declared)",
        frac <= 0.15, f"{int(np.isfinite(p).sum())} shifted tests; share p<0.05 = {frac:.3f}",
        result=None if frac <= 0.15 else "NOT_MET_REPORTED")
    sens = read_out("afr_sensitivity_analysis.csv")
    nc = sens[sens.group.eq("NC_MISALIGNED_30D")]
    add("G5 statistics", "Negative control (AFR misaligned by 30 days): median |rho| below the primary median |rho|",
        nc.effect_size.abs().median() < nc.primary_window_effect.abs().median(),
        f"misaligned {nc.effect_size.abs().median():.3f} vs primary {nc.primary_window_effect.abs().median():.3f}")
    ep = rel[rel.row_role.eq("EPISODE_PRIMARY") & rel.p_value.notna()]
    add("G5 statistics", "Randomised transition-label permutation p reported and BH-adjusted for every evaluable episode row",
        ep.adjusted_p_value.notna().all(), f"{len(ep)} rows")


def g6(rel: pd.DataFrame):
    sens = read_out("afr_sensitivity_analysis.csv")
    groups = sorted(set(sens.group) - {"NC_MISALIGNED_30D"})
    add("G6 robustness", "Sensitivity groups A-H all ran", groups == list("ABCDEFGH"), f"{groups}")
    prim = rel[rel.row_role.isin(["SELECTED_LAG", "EPISODE_PRIMARY"]) & rel.window.isin(["DISCOVERY", "POOLED_APR_JUL"])]
    pend = int(prim.confidence.eq("PENDING_SENSITIVITY").sum())
    add("G6 robustness", "Confidence finalised for every primary relationship (none pending)", pend == 0, f"{pend} pending")
    a = prim[prim.evidence.eq("ASSOCIATED")]
    add("G6 robustness", "Every ASSOCIATED relationship lists how many sensitivity groups were evaluated and agree",
        a.sensitivity_groups_evaluated.notna().all(),
        f"{len(a)} ASSOCIATED; median agree/evaluated {a.sensitivity_groups_agree.median()}/"
        f"{a.sensitivity_groups_evaluated.median()}")
    add("G6 robustness", "Confidence is never HIGH (no fuel properties)", not prim.confidence.eq("HIGH").any(),
        prim.confidence.value_counts().to_dict())
    from af_core import confidence_cap
    leak = prim[prim.confidence.eq("MEDIUM") & prim["flags"].fillna("").map(confidence_cap).ne("")]
    add("G6 robustness", "No co-manipulation, Sp.Heat or Sp.Heat-based KPI relationship carries MEDIUM confidence "
        "(cap re-derived from flags)", leak.empty, f"{len(leak)} violations: "
        f"{leak[['target_signal', 'analysis_type']].head(4).to_dict('records')}")
    fg = sens[sens.variant.eq("sp_heat_other_definition")]
    add("G6 robustness", "Sp.Heat F and G both analysed; sign agreement between the definitions reported", len(fg) > 0,
        f"{len(fg)} rows; same-sign share {fg.same_sign_as_primary.mean():.2f}", kind="INFO", result="INFO")
    months = sorted(sens[sens.variant.str.startswith("month_")].variant.unique())
    add("G6 robustness", "Month sensitivity covers APR, MAY, JUN, JUL, AUG", len(months) == 5, f"{months}")
    m = read_out("afr_matched_analysis.csv")
    st = m.drop_duplicates(["comparison", "window"])
    add("G6 robustness", "Matched-control status reported for every comparison (MATCHING_NOT_SUPPORTED carries its reason)",
        (st.matching_status.eq("MATCHED") | st.not_supported_reason.fillna("").ne("")).all(),
        "; ".join(f"{r.comparison}/{r.window}: {r.matching_status}" for r in st.itertuples()))
    counted = sens[sens.counted_in_agreement & sens.same_sign_as_primary.notna()]
    add("G6 robustness", "Share of sensitivity variants keeping the primary sign (all relationships)", True,
        f"{counted.same_sign_as_primary.astype(bool).mean():.2f} over {len(counted)} variant rows", kind="INFO", result="INFO")


def main():
    rel = pd.concat([read_out(f) for f in REL_FILES], ignore_index=True)
    g1()
    g2(rel)
    g3(rel)
    g4()
    g5(rel)
    g6(rel)
    v = pd.DataFrame(ROWS)
    write_csv(v, "afr_validation.csv", lg)
    lg.info("validation: %s", v.result.value_counts().to_dict())
    for r in v[v.result.eq("FAIL")].itertuples():
        lg.error("FAIL %s | %s | %s", r.gate, r.check, r.evidence)


if __name__ == "__main__":
    main()
