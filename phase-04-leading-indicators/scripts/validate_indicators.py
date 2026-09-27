"""Step 9 - Validation gates G1-G6 (G7 reproducibility and the before/after upstream snapshots are in run_phase4.py).

Writes outputs/indicator_validation.csv (gate, check, result, evidence) and outputs/indicator_benchmarks.csv.

There is no event ground truth, so no precision / recall against plant events is computed. The gates check integrity,
schema, temporal causality (an explicit leakage test: every feature, control and alarm at t <= T is identical with and
without the data after T), statistical honesty (planted lead, circular-shift placebo, autocorrelated-null false-positive
rate, BH monotonicity), data quality, circularity and robustness. A robustness verdict that does not meet its
pre-declared materiality rule is REPORTED (result DISCLOSED), not hidden; the gate fails only when a check that the
method relies on fails.
"""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from scipy.special import ndtr

from p4common import (ALL_DATASETS, CACHE, FEATURES, OUT, P1_OUT, P2_OUT, P3_OUT, PRIMARY, PROCESSED, RAW, SOURCE_ROOT,
                      STATE_DATASETS, log, read_out, read_p1, read_p2, read_p3, sha256, write_csv)
import analysis_context as ac
import build_causal_features as bcf
import indicator_core as ic
from p3common import CAUSAL_INVALID_TOKENS, processed_path

lg = log("validate_indicators")
ROWS: list[dict] = []


def add(gate: str, check: str, ok, evidence, disclosed: bool = False, kind: str = "INDEPENDENT") -> None:
    """kind: INDEPENDENT (can fail on real defects), REGRESSION_GUARD (re-checks a construction rule; guards against
    future code changes, not independent evidence), INFO (reported quantity; result INFO).
    A robustness verdict that misses its pre-declared rule is NOT_MET_REPORTED (reported, not hidden, not a failure)."""
    res = "INFO" if kind == "INFO" else ("PASS" if ok else ("NOT_MET_REPORTED" if disclosed else "FAIL"))
    ROWS.append({"gate": gate, "check": check, "check_type": kind, "result": res, "evidence": str(evidence)[:700]})
    (lg.error if res == "FAIL" else lg.info)("%s | %s | %s", gate, check, res)


def load_minute_cache() -> tuple[dict, pd.DataFrame]:
    frames = {ds: pd.read_parquet(CACHE / f"minute_{ds.replace(' ', '_')}.parquet") for ds in ALL_DATASETS}
    return frames, pd.read_parquet(CACHE / "minute_state_inputs.parquet")


def features_window(frames: dict, state: pd.DataFrame, S: pd.Timestamp, E: pd.Timestamp, ref: dict,
                    tags: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Re-derive buckets and features from the minute inputs restricted to [S, E] (masks, causal state, buckets)."""
    fr = {ds: f.loc[S:E] for ds, f in frames.items()}
    b = ic.build_buckets(fr, state.loc[S:E], STATE_DATASETS)
    v = b["values"].reindex(columns=sorted(set(b["values"].columns) | set(tags)))
    return bcf.feature_frame(v, ref, tags, PRIMARY), b["meta"]


def leak_task(args) -> dict:
    name, T, tags = args
    frames, state = load_minute_cache()
    ref = json.loads((OUT / "indicator_feature_reference.json").read_text())
    S = T - pd.Timedelta("10D")
    A, ma = features_window(frames, state, S, T, ref, tags)
    B, mb = features_window(frames, state, S, T + pd.Timedelta("14D"), ref, tags)
    a = A[A.index <= T]
    b = B.reindex(a.index)
    diff = ~((a == b) | (a.isna() & b.isna()))
    sa, sb = ma.bucket_state[ma.index <= T], mb.bucket_state.reindex(ma.index[ma.index <= T])
    return {"cut": f"{name} @ {T}", "cells": int(a.size), "feature_mismatch": int(diff.to_numpy().sum()),
            "state_mismatch": int((sa != sb).sum()), "n_nonnull": int(a.notna().to_numpy().sum())}


def main():
    cfg = PRIMARY
    inv = read_out("indicator_candidate_inventory.csv")
    F = ac.load_features()
    lagdf = ac.load_lag_table()
    scores = read_out("indicator_scores.csv")
    lis = read_out("leading_indicator_set.csv")
    sens = read_out("indicator_sensitivity.csv")
    dq = read_out("indicator_data_quality.csv")
    ctx = ac.build_context(cfg)
    ref = json.loads((OUT / "indicator_feature_reference.json").read_text())
    tags = bcf.analysable_tags(inv)
    members = lis[lis.selection_status.eq("SELECTED")].indicator_id.tolist()

    # ================================================================ G1 source / dependency integrity
    man = pd.read_csv(RAW / "source_manifest.csv")
    mism = [r.relative_path for r in man.itertuples() if sha256(SOURCE_ROOT / r.relative_path) != r.sha256]
    add("G1 source integrity", "SHA-256 of every source file equals the Phase 1 source manifest", not mism,
        f"{len(man)} files; mismatches {mism}")
    h0 = json.loads((CACHE / "input_hashes.json").read_text())
    base = {"phase-03": P3_OUT, "phase-02": P2_OUT, "phase-01": P1_OUT, "data/processed": PROCESSED}
    changed = [k for k, v in h0.items() if sha256(base[k.rsplit("/", 1)[0]] / k.rsplit("/", 1)[1]) != v]
    add("G1 source integrity", "Phase 1 / 2 / 3 inputs and data/processed unchanged since they were read (sha256)",
        not changed, f"{len(h0)} files; changed {changed}")
    v3 = read_p3("kpi_validation.csv")
    add("G1 source integrity", "Phase 3 KPI passed all of its validation checks (input contract)",
        bool((v3.result == "PASS").all()), f"{int((v3.result == 'PASS').sum())}/{len(v3)} PASS")

    # ================================================================ G2 schema integrity
    pti = read_p1("process_tag_inventory.csv")
    name_col = "original_name" if "original_name" in pti else next(c for c in pti.columns if "name" in c)
    ds_col = next(c for c in ("dataset", "equipment") if c in pti)
    col_col = next(c for c in ("source_column", "column_letter", "column") if c in pti)
    p1 = {f"{r[ds_col]}!{r[col_col]}": r for r in pti.to_dict("records")}
    src = inv[inv.dataset.isin(ALL_DATASETS)]
    missing = [t for t in src.indicator_tag if t not in p1]
    add("G2 schema integrity", "Every inventoried source tag exists in the Phase 1 process tag inventory (no invented tags)",
        not missing, f"{len(src)} tags; missing {missing[:10]}")
    feat_tags = sorted({ac.split_id(c)[0] for c in F.columns})
    bad_feat = [t for t in feat_tags if t not in set(inv[inv.status.isin(["CANDIDATE", "CONTEXT_ONLY"])].indicator_tag)]
    add("G2 schema integrity", "Every feature column derives from an inventoried CANDIDATE / CONTEXT tag", not bad_feat,
        f"{len(feat_tags)} tags in features; unexpected {bad_feat}")
    ren = []
    for t in feat_tags:
        ds, col = t.split("!")
        d = pd.read_parquet(processed_path(ds), columns=["source_column", "original_name", "unit"]).drop_duplicates()
        d = d[d.source_column.astype(str) == col]
        r = inv.set_index("indicator_tag").loc[t]
        if d.empty or str(d.original_name.iloc[0]) != str(r.original_name) or str(d.unit.iloc[0]) != str(r.unit):
            ren.append(t)
    add("G2 schema integrity", "original_name and unit of every feature tag equal data/processed (no silent renaming, "
        "units traceable, no unit conversion)", not ren, f"{len(feat_tags)} tags checked against data/processed; mismatches {ren}")
    holds = read_p2("column_holds.csv").assign(tag=lambda h: h.dataset + "!" + h.source_column)
    held_in = sorted(set(holds.tag) & set(feat_tags))
    unit_rev = read_p1("unit_consistency_review.csv")
    single = unit_rev[~unit_rev.dataset.astype(str).str.startswith("[")]      # per-tag unit reviews
    ur_in = sorted({f"{r.dataset}!{r.source_column}" for r in single.itertuples()} & set(feat_tags))
    add("G2 schema integrity", "No Phase 2 held column (unit review, sentinel, sparse, constant, state indicator, duplicate) "
        "and no per-tag Phase 1 UNIT CONSISTENCY REVIEW column has a feature (cross-dataset unit-TEXT variants such as "
        "'A' / 'Amps' are analysed per tag in their own unit, never combined or converted)", not held_in and not ur_in,
        f"{len(holds)} holds; {len(single)} per-tag unit reviews; with features: held {held_in}, unit review {ur_in}")
    excl = set(inv[inv.status.eq("EXCLUDED")].indicator_tag)
    add("G2 schema integrity", "No EXCLUDED candidate (C1-C7) and no Phase 3 KPI output (C5) has a feature",
        not (excl & set(feat_tags)) and not any(c.startswith(("P3:", "STD60:", "DERIVED:")) for c in F.columns),
        f"{len(excl)} excluded rows")
    add("G2 schema integrity", "Every analysable tag has a unit, a Phase 2 family and an exclusion reason if excluded",
        bool(inv[inv.status.ne("EXCLUDED") & inv.dataset.isin(ALL_DATASETS)].unit.notna().all()
             and inv[inv.status.eq("EXCLUDED")].exclusion_reason.notna().all()),
        inv.status.value_counts().to_dict())

    # ================================================================ G3 temporal integrity
    grid = pd.read_parquet(CACHE / "kpi_grid.parquet")
    meta = pd.read_parquet(CACHE / "buckets_meta.parquet").reindex(grid.index)
    add("G3 temporal integrity", "Bucket operating state rebuilt by Phase 4 == Phase 3 operating_state (every bucket)",
        bool((meta.bucket_state.astype(str) == grid.bucket_state).all()), f"{len(grid)} buckets")
    ms = pd.read_parquet(CACHE / "buckets_minute_state.parquet").state
    stops = ms.index[ms.eq("STOPPED") & ~ms.shift().eq("STOPPED") & (ms.index > pd.Timestamp("2025-06-03"))]
    restarts = ms.index[ms.eq("TRANSITION") & ms.shift().eq("STOPPED") & (ms.index > pd.Timestamp("2025-06-03"))]
    Ts = {"discovery end": pd.Timestamp(cfg.disc_end), "30 min after a restart (ramp)": restarts[0] + pd.Timedelta("30min"),
          "30 min before a stop": stops[0] - pd.Timedelta("30min"), "7 min before a later stop": stops[min(3, len(stops) - 1)] - pd.Timedelta("7min"),
          "June / July boundary": pd.Timestamp("2025-06-30 23:57"), "mid-July, off-grid": pd.Timestamp("2025-07-14 09:43"),
          "month end July": pd.Timestamp("2025-07-31 23:50"), "late August": pd.Timestamp("2025-08-18 13:43"),
          "mid-June": pd.Timestamp("2025-06-15 09:30")}
    with ProcessPoolExecutor(max_workers=min(len(Ts), 9)) as ex:
        res = list(ex.map(leak_task, [(k, v, tags) for k, v in Ts.items()]))
    ok = all(r["feature_mismatch"] == 0 and r["state_mismatch"] == 0 and r["n_nonnull"] > 0 for r in res)
    add("G3 temporal integrity", f"LEAKAGE TEST: all {F.shape[1]} features (level, deviation, rate of change, volatility, "
        f"persistence; masks, causal state and buckets re-derived) at t <= T identical with and without 14 days of data after T "
        f"({len(Ts)} cut points, exact)", ok, [(r["cut"], r["feature_mismatch"], r["state_mismatch"]) for r in res])
    # the stored features equal a fresh derivation over the same span (the cut test compares like with like)
    Tchk = pd.Timestamp("2025-07-20 00:00")
    frames, state = load_minute_cache()
    Aw, _ = features_window(frames, state, Tchk - pd.Timedelta("10D"), Tchk, ref, tags)
    tail = Aw.index[Aw.index > Tchk - pd.Timedelta("7D")]       # past the 48-h ramp horizon and 6-h windows
    d = Aw.loc[tail] - F.loc[tail, Aw.columns]
    same = bool(((d.abs() < 1e-9) | (Aw.loc[tail].isna() & F.loc[tail, Aw.columns].isna())).to_numpy().all())
    add("G3 temporal integrity", "Features re-derived from a 10-day minute window equal the stored full-run features after "
        "warm-up (history beyond 7 days does not change features)", same, f"{tail.size} buckets x {Aw.shape[1]} features")
    # controls and alarms are causal
    K, D = ctx.K.copy(), ctx.D.copy()
    bad = 0
    for T in list(Ts.values())[1:]:
        i = int(np.searchsorted(ctx.index, T, side="right"))
        Kt, Dt = K.copy(), D.copy()
        Kt[i:], Dt[i:] = np.nan, np.nan
        for L in cfg.lags:
            h = L // 10
            a, b = ic.controls(K, D, h, ctx.m, ctx.q)[:i], ic.controls(Kt, Dt, h, ctx.m, ctx.q)[:i]
            bad += int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())
        for c in members:
            thr = scores.set_index("indicator_id").alarm_threshold[c]
            s = int(scores.set_index("indicator_id").sign[c])
            x = F[c].to_numpy(float)
            xt = x.copy()
            xt[i:] = np.nan
            a1, a2 = ic.alarm_onsets(x, s, thr, cfg), ic.alarm_onsets(xt, s, thr, cfg)
            bad += int(not np.array_equal(a1[a1 < i], a2[a2 < i]))
    add("G3 temporal integrity", "LEAKAGE TEST: controls (K, momentum, Kpend) at every lag and alarm onsets of the set are "
        "identical when the KPI / feature after T is removed", bad == 0, f"{len(Ts) - 1} cut points; mismatches {bad}")
    # reference refit on data truncated at discovery end
    vals_t = pd.read_parquet(CACHE / "buckets_values.parquet")
    vals_t, meta_t = bcf.align(vals_t, pd.read_parquet(CACHE / "buckets_meta.parquet"), grid.index)
    cut = grid.index <= pd.Timestamp(cfg.disc_end)
    ref_t = bcf.fit_reference(vals_t[cut], meta_t[cut], tags, cfg)
    same_ref = json.dumps(ref_t, sort_keys=True, default=float) == json.dumps(ref, sort_keys=True, default=float)
    add("G3 temporal integrity", "Feature reference refitted on buckets truncated at discovery end == stored reference",
        same_ref, "identical JSON" if same_ref else "differs")
    purge = []
    for L in cfg.lags:
        h = L // 10
        r = ac.window_rows(ctx, "DISCOVERY", h)
        end = ctx.index[r] + pd.Timedelta(minutes=L)
        purge.append(int((end > pd.Timestamp(cfg.disc_end)).sum()))
    add("G3 temporal integrity", "Discovery purge: every discovery row has t + H <= discovery end (no evaluation KPI "
        "enters discovery)", sum(purge) == 0, dict(zip(cfg.lags, purge)), kind="REGRESSION_GUARD")
    # discovery statistics with every post-discovery KPI value removed
    ctx_t = ac.build_context(cfg)
    after = ctx_t.index > pd.Timestamp(cfg.disc_end)
    ctx_t.K[after], ctx_t.D[after], ctx_t.K_primary[after] = np.nan, np.nan, np.nan
    rng = np.random.default_rng(cfg.seed)
    d = lagdf[lagdf.window.eq("DISCOVERY")]
    samp = d.iloc[np.sort(rng.choice(len(d), 150, replace=False))]
    mis = 0
    for r in samp.itertuples():
        h = r.lag_minutes // 10
        y = ic.future_target(ctx_t.K, ctx_t.running, h, cfg.target_smooth_buckets)
        Z = ic.controls(ctx_t.K, ctx_t.D, h, ctx_t.m, ctx_t.q)
        rows = ac.window_rows(ctx_t, "DISCOVERY", h)
        blk, _ = ac.blocks(ctx_t, rows)
        a = ic.assoc(F[r.indicator_id].to_numpy(float), y, Z, rows, blk, cfg.seed + ac.WINDOW_SEEDS["DISCOVERY"],
                     cfg.neff_maxlag, n_boot=cfg.n_boot)
        mis += int(not (np.isclose(a["rho_p"], r.rho_p, atol=1e-6, equal_nan=True)
                        and np.isclose(a["ci_lo"], r.ci_lo, atol=1e-6, equal_nan=True)))
    add("G3 temporal integrity", "Discovery statistics identical when every KPI value after discovery end is deleted "
        "(150 random discovery tests: rho_p and bootstrap CI)", mis == 0, f"mismatches {mis}")
    lag_mod = lagdf.copy()
    lag_mod.loc[~lag_mod.window.eq("DISCOVERY"), ["rho_p", "q_bh", "ci_lo", "ci_hi"]] = 0.0
    c1, c2 = ac.discovery_choice(lagdf), ac.discovery_choice(lag_mod)
    add("G3 temporal integrity", "Lag / sign selection uses discovery only (overwriting every evaluation statistic leaves "
        "the chosen lag, sign and support unchanged)", bool(c1.equals(c2)), f"{len(c1)} indicators", kind="REGRESSION_GUARD")
    add("G3 temporal integrity", "Feature columns contain no target, KPI or future-derived field (column contract)",
        all(ac.split_id(c)[1] in FEATURES for c in F.columns), f"{F.shape[1]} columns, types {sorted({ac.split_id(c)[1] for c in F.columns})}")

    # ================================================================ G4 statistical integrity
    dd = lagdf[lagdf.window.eq("DISCOVERY")]
    add("G4 statistical integrity", "Autocorrelation handled: n_eff <= n for every test (Bartlett / Pyper-Peterman)",
        bool((lagdf.n_eff.dropna() <= lagdf.n[lagdf.n_eff.notna()] + 1e-9).all()),
        f"median n_eff / n = {float((lagdf.n_eff / lagdf.n).median()):.3f}", kind="REGRESSION_GUARD")
    from scipy.stats import false_discovery_control
    o = dd.dropna(subset=["p_eff"])
    q_ref = false_discovery_control(o.p_eff.to_numpy(), method="bh")
    add("G4 statistical integrity", "Multiple comparisons: Benjamini-Hochberg q over all discovery tests equals an "
        "independent implementation (scipy.stats.false_discovery_control)", bool(np.allclose(o.q_bh, q_ref, atol=1e-9)),
        f"{len(o)} discovery tests; q <= 0.10: {int((o.q_bh <= 0.10).sum())}")
    # planted lead (sanity: the machinery can find a real lead at the right lag)
    h_pl = 18
    Kp = ctx.K
    rng = np.random.default_rng(cfg.seed + 1)
    xpl = np.r_[Kp[h_pl:], np.full(h_pl, np.nan)] + rng.normal(0, np.nanstd(Kp) * 1.0, len(Kp))
    prof = {}
    for L in cfg.lags:
        y, Z = ac.target_and_controls(ctx, L // cfg.bucket_min)
        prof[L] = ic.assoc(xpl, y, Z, ac.window_rows(ctx, "REPL", L // cfg.bucket_min), None, None, cfg.neff_maxlag)["rho_p"]
    best = max(prof, key=lambda k: prof[k])
    add("G4 statistical integrity", "Planted lead x(t) = K(t + 180 min) + noise is recovered: best lag within one grid step "
        "of 180 min (sanity check of the lag machinery)", best in (120, 180, 240), {k: round(v, 3) for k, v in prof.items()})
    # null calibration: every feature circularly shifted by 14 days (keeps each feature's autocorrelation, breaks alignment)
    y, Z = ac.target_and_controls(ctx, 6)
    rows = ac.window_rows(ctx, "DISCOVERY", 6)
    pn = np.array([ic.assoc(np.roll(F[c].to_numpy(float), 14 * 144), y, Z, rows, None, None, cfg.neff_maxlag)["p_eff"]
                   for c in F.columns])
    pn = pn[np.isfinite(pn)]
    share = float(np.mean(pn < 0.05))
    add("G4 statistical integrity", "Null calibration: all features circularly shifted by 14 days (discovery, 60-min lag): "
        "share with p < 0.05 <= 0.10 (nominal 0.05) and no BH discovery at q <= 0.10", share <= 0.10 and not (ic.bh(pn) <= 0.10).any(),
        f"{len(pn)} null tests; share p < 0.05 = {share:.3f}; BH q <= 0.10: {int((ic.bh(pn) <= 0.10).sum())}")
    # AR(1) nulls at several autocorrelation levels
    from scipy.signal import lfilter
    y, Z = ac.target_and_controls(ctx, 6)
    rows = ac.window_rows(ctx, "DISCOVERY", 6)
    rng = np.random.default_rng(cfg.seed + 2)
    ar = {}
    for phi in (0.90, 0.97, 0.995):
        fp, fp_naive = 0, 0
        for _ in range(60):
            x = lfilter([np.sqrt(1 - phi ** 2)], [1, -phi], rng.normal(size=len(y)))
            a = ic.assoc(x, y, Z, rows, None, None, cfg.neff_maxlag)
            fp += int(a["p_eff"] < 0.05)
            fp_naive += int(2 * (1 - ndtr(abs(np.arctanh(a["rho_p"])) * np.sqrt(a["n"] - 6))) < 0.05)
        ar[phi] = (fp, fp_naive)
    add("G4 statistical integrity", "AR(1) nulls (60 series each at phi 0.90 / 0.97 / 0.995): false-positive rate at "
        "p < 0.05 with n_eff <= 12 % at every phi", all(v[0] <= 7 for v in ar.values()),
        {f"phi {k}": f"n_eff {v[0]}/60 vs iid {v[1]}/60" for k, v in ar.items()})
    # placebo for the discovery-supported indicators (replication months)
    sup = scores[scores.disc_supported]
    sig = 0
    for r in sup.itertuples():
        y, Z = ac.target_and_controls(ctx, r.lag_minutes // cfg.bucket_min)
        a = ic.assoc(np.roll(F[r.indicator_id].to_numpy(float), 7 * 144), y, Z,
                     ac.window_rows(ctx, "REPL", r.lag_minutes // cfg.bucket_min), None, None, cfg.neff_maxlag)
        sig += int(np.isfinite(a["p_eff"]) and a["p_eff"] < 0.05)
    add("G4 statistical integrity", "Placebo: supported indicators shifted by 7 days (replication months): <= 20 % "
        "remain p < 0.05", sig <= max(1, 0.2 * len(sup)), f"{sig}/{len(sup)} placebo series with p < 0.05")
    # stored bootstrap CIs reproduce (20 random rows re-computed from scratch)
    rng = np.random.default_rng(cfg.seed + 3)
    samp = lagdf.dropna(subset=["ci_lo"]).iloc[np.sort(rng.choice(int(lagdf.ci_lo.notna().sum()), 20, replace=False))]
    bad = 0
    for rr in samp.itertuples():
        h = rr.lag_minutes // cfg.bucket_min
        y2, Z2 = ac.target_and_controls(ctx, h)
        rw = ac.window_rows(ctx, rr.window, h)
        blk, _ = ac.blocks(ctx, rw)
        a = ic.assoc(F[rr.indicator_id].to_numpy(float), y2, Z2, rw, blk, cfg.seed + ac.WINDOW_SEEDS[rr.window],
                     cfg.neff_maxlag, n_boot=cfg.n_boot)
        bad += int(not (np.isclose(a["ci_lo"], rr.ci_lo, atol=1e-9) and np.isclose(a["rho_p"], rr.rho_p, atol=1e-12)))
    add("G4 statistical integrity", "20 random stored statistics (rho_p, bootstrap CI) reproduce exactly when recomputed",
        bad == 0, f"mismatches {bad}", kind="REGRESSION_GUARD")
    add("G4 statistical integrity", "Correlation is not read as causation: empirical label on every set row; relationship "
        "classes reported", True, scores[scores.disc_supported].relationship_class.value_counts().to_dict(), kind="INFO")
    add("G4 statistical integrity", "Unstable relationships identified (discovery-supported, not replicated or failing the "
        "shift null)", True, int(scores.relationship_class.eq("UNSTABLE_OR_SPURIOUS").sum()), kind="INFO")
    fl_ok = bool(sup.n_alarms_repl.notna().all() and sup.false_lead_rate_repl.notna().all())
    add("G4 statistical integrity", "False leads measured for every discovery-supported indicator (rate, precision vs base "
        "rate on the same evaluability rule, categories)", fl_ok,
        sup[["indicator_id", "false_lead_rate_repl", "precision_lift_repl"]].round(3).values.tolist()[:8])

    # ================================================================ G5 data quality and circularity
    add("G5 data quality", "Data-quality accounting for every analysable tag (invalid tokens, flatline / frozen masks, "
        "coverage per window, Phase 2 confidence)", set(tags) <= set(dq.tag), f"{len(dq)} rows")
    tok_bad, n_tok = 0, 0
    for ds in ("Kiln-III", "Kiln-IIIB", "IKN Cooler-I", "CBS-I"):
        d = pd.read_parquet(processed_path(ds), columns=["ts", "source_column", "mask_reason", "dup_status"])
        reason = d.mask_reason.astype(str)
        bad = np.zeros(len(d), bool)
        for t in CAUSAL_INVALID_TOKENS:
            bad |= reason.str.contains(t, regex=False).to_numpy()
        bad |= d.dup_status.eq("DUP_CONFLICT").to_numpy()
        dd2 = d[bad & d.dup_status.isin(["UNIQUE", "DUP_KEPT", "DUP_CONFLICT"])]
        f = frames[ds]
        for col, g in dd2.groupby(dd2.source_column.astype(str)):
            t = f"{ds}!{col}"
            if t in f:
                n_tok += len(g)
                tok_bad += int(f[t].reindex(g.ts).notna().sum())
    add("G5 data quality", "Cells carrying a Phase 2 causal invalid token (missing, text, sentinel, impossible, duplicate "
        "conflict, hourly) are NaN in the Phase 4 minute cache (4 non-KPI datasets, cell by cell)", tok_bad == 0,
        f"{n_tok} token cells; {tok_bad} leaked")
    bv = pd.read_parquet(CACHE / "buckets_values.parquet")
    units = inv.set_index("indicator_tag").unit
    degc = [c for c in bv.columns if "deg" in str(units.get(c, "")).lower()]
    sent = int(((bv == 99999) | (bv == 9999)).to_numpy().sum())
    cold = int((bv[degc] <= -273).to_numpy().sum())
    add("G5 data quality", "No sentinel (99999 / 9999) in any bucket and no temperature (Deg.C) <= -273", sent == 0 and cold == 0,
        f"sentinel cells {sent}; Deg.C <= -273 cells {cold} ({len(degc)} Deg.C tags; negative mmWC drafts are physical)")
    flow = [c for c in bv.columns if str(units.get(c, "")).lower() in ("kg/h", "m3/m", "m3/hr", "tph")]
    negf = {c: int((bv[c] < 0).sum()) for c in flow if (bv[c] < 0).any()}
    add("G5 data quality", "Negative flow / rate buckets (not masked by Phase 2; reported for plant review, no value is "
        "altered)", True, negf or "none", kind="INFO")
    fw0, fw1 = pd.Timestamp("2025-05-06 11:50"), pd.Timestamp("2025-05-06 21:50")
    cov = {}
    for ds in ALL_DATASETS:
        cols = [c for c in bv.columns if c.startswith(ds + "!")]
        seg = bv.loc[fw0:fw1, cols]
        cov[ds] = round(float(seg.notna().to_numpy().mean()), 3) if seg.size else np.nan
    add("G5 data quality", "Frozen window 2025-05-06 11:50-21:50 (Phase 1): share of bucket cells still valid per dataset "
        "(reported; causal masks remove frozen rows only once frozen >= 10 min)", True, cov, kind="INFO")
    # independent scan: for every analysis row (t, lag) the bucket at t and every bucket in (t, t+H] are RUNNING
    st_arr = grid.bucket_state.to_numpy()
    viol = 0
    for L in cfg.lags:
        h = L // cfg.bucket_min
        y, _ = ac.target_and_controls(ctx, h)
        for w in ("DISCOVERY", "REPL", "HOLDOUT"):
            for i in np.flatnonzero(ac.window_rows(ctx, w, h) & np.isfinite(y)):
                viol += int((st_arr[i:i + h + 1] != "RUNNING").any())
    add("G5 data quality", "Operating-state mask (independent scan of the bucket grid): every analysis row is RUNNING at t "
        "and over the whole horizon (t, t+H]", viol == 0, f"violations {viol}")
    s_m = scores.set_index("indicator_id")
    add("G5 circularity", "No KPI_INPUT or KPI_PROXY tag in the leading set (circular precursors are listed separately)",
        not any(s_m.tier.get(m) in ("KPI_INPUT", "KPI_PROXY") for m in members), members, kind="REGRESSION_GUARD")
    add("G5 circularity", "August holdout result of every set member (never used for selection) - reported", True,
        {m: (s_m.holdout_result[m], round(s_m.holdout_rho_p[m], 3), round(s_m.holdout_ci_lo[m], 3),
             round(s_m.holdout_ci_hi[m], 3)) for m in members}, kind="INFO")
    # benchmarks: the KPI's own recent behaviour (never eligible; shows the scale of attainable association)
    bench = []
    Dl = ic.trailing_median(ctx.D, 6, 3)
    mom = ctx.K - ic.lagged(ctx.K, 6)
    for name, x in (("BENCHMARK:D_1H (Phase 3 raw deviation, trailing 1 h median)", Dl), ("BENCHMARK:KPI_MOMENTUM_1H", mom)):
        for L in cfg.lags:
            y, Z = ac.target_and_controls(ctx, L // 10)
            for w in ("DISCOVERY", "REPL", "HOLDOUT"):
                rows = ac.window_rows(ctx, w, L // 10)
                a = ic.assoc(x, y, None, rows, np.zeros(len(x), int), None, cfg.neff_maxlag)
                bench.append({"benchmark": name, "lag_minutes": L, "window": w, "rho_raw_no_controls": a["rho_raw"],
                              "n": a["n"], "n_eff": a["n_eff"], "note": "raw Spearman with the future KPI change; never a candidate"})
    write_csv(pd.DataFrame(bench), "indicator_benchmarks.csv", lg)
    add("G5 circularity", "KPI self-benchmarks (raw deviation D and KPI momentum) reported for comparison", True,
        "outputs/indicator_benchmarks.csv", kind="INFO")

    # ================================================================ G6 robustness
    for m in members:
        r = s_m.loc[m]
        add("G6 robustness", f"{m}: discovery sign in both replication months", r.repl_months_same_sign == 2,
            f"JUN {r.jun_rho_p:.3f} JUL {r.jul_rho_p:.3f}; holdout AUG {r.holdout_rho_p:.3f} ({r.holdout_result})",
            kind="REGRESSION_GUARD")
        ss = sens[sens.indicator_id.eq(m)].set_index("variant").consistent
        for grp, vs in {"lead time (neighbouring lags)": ["LAG_MINUS_1_STEP", "LAG_PLUS_1_STEP"],
                        "training window (split-half, April reference, alternative KPI reference)":
                            ["SPLIT_APR", "SPLIT_MAY", "REFERENCE_APRIL_ONLY", "ALT_KPI_REFERENCE_W_JUN_JUL15"],
                        "operating-state conditioning": ["EXCLUDE_6H_AFTER_TRANSITION", "EXCLUDE_2H_BEFORE_STOP"],
                        "load conditioning": ["LOAD_FEED_CONTROLS", "LOAD_BAND_STRATIFIED"],
                        "Sp.Heat F / G": ["SP_HEAT_F_TARGET", "SP_HEAT_G_TARGET"],
                        "persistence (target smoothing, band-occupancy target)": ["TARGET_SMOOTH_60MIN", "T2_BAND_OCCUPANCY_TARGET"],
                        "missing data (GOOD buckets only)": ["DQ_GOOD_BUCKETS_ONLY"],
                        "inference (1-day blocks, no controls)": ["BLOCK_1_DAY", "NO_CONTROLS_RAW_SPEARMAN"]}.items():
            vals = [ss.get(v, np.nan) for v in vs]
            ok_g = all(v == 1 for v in vals if np.isfinite(v))
            must = grp.startswith(("operating", "load", "Sp.Heat"))
            add("G6 robustness", f"{m}: consistent under {grp}", ok_g, dict(zip(vs, vals)), disclosed=not must)
    for r in sens[sens.group.isin(["I scoring weights", "H feature family", "E Sp.Heat"]) & sens.indicator_id.isin(["ALL_SUPPORTED", "SET"])].itertuples():
        add("G6 robustness", f"{r.variant}: pre-declared materiality rule", r.consistent == 1, f"{r.rho_variant:.3f}; {r.note}",
            disclosed=True)
    add("G6 robustness", "Temporal robustness evaluated for every indicator (discovery Apr-May; Jun, Jul replication; "
        "Aug holdout; pooled)", bool(lagdf.window.value_counts().nunique() == 1), lagdf.window.value_counts().to_dict())

    v = pd.DataFrame(ROWS)
    write_csv(v, "indicator_validation.csv", lg)
    lg.info("validation: %s", v.result.value_counts().to_dict())


if __name__ == "__main__":
    main()
