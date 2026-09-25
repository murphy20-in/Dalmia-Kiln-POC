"""Step 8 - KPI validation gates G1-G6 (G7 reproducibility is recorded by run_phase3.py).

Writes outputs/kpi_validation.csv (gate, check, result, evidence).

The KPI cannot be validated against deposit / ring events (none exist). It is validated for internal statistical
consistency: source and dependency integrity, data-quality exclusions, temporal integrity (a deliberate leakage
test: KPI(T) must not change when data after T is appended), traceability, scale properties, behaviour in stopped
and transition periods, and synthetic-injection behaviour (a persistent shift must raise the KPI; a short spike
must not). No accuracy / precision / recall / AUC is computed.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p3common import (BAND_LABEL, CACHE, CAUSAL_INVALID_TOKENS, OUT, PRIMARY, ROOT, SOURCE_ROOT, P2_OUT, load_buckets,
                      load_minutes, log, read_out, read_p2, sha256, spec_by_tag, write_csv)
from kpi_core import (aggregate, dimension_raw, fit_score, prepare_minutes, run_kpi, standardise_dims, to_kpi)

lg = log("validate_kpi")
ROWS: list[dict] = []
KPI_COLS = ["bucket_state", "raw_deviation_score", "persistent_deviation_score", "kpi_value", "efficiency_deterioration_kpi",
            "kpi_reference_state", "kpi_band", "top_dimension", "top_tag", "kpi_driver_class", "n_dims_elevated",
            "kpi_training_percentile", "secondary_mahalanobis_kpi"]


def add(gate: str, check: str, ok: bool, evidence) -> None:
    ROWS.append({"gate": gate, "check": check, "result": "PASS" if ok else "FAIL", "evidence": str(evidence)[:600]})
    (lg.info if ok else lg.error)("%s | %s | %s", gate, check, "PASS" if ok else "FAIL")


def frames_equal(a: pd.DataFrame, b: pd.DataFrame, cols: list[str]) -> tuple[bool, int]:
    bad = 0
    for c in cols:
        x, y = a[c], b[c]
        if x.dtype.kind in "fc":
            bad += int((~((x == y) | (x.isna() & y.isna()))).sum())
        else:                                   # text columns: equal, or missing in both (None / NaN)
            bad += int((~((x.astype(str) == y.astype(str)) | (x.isna() & y.isna()))).sum())
    return bad == 0, bad


def main():
    values, state = load_minutes()
    b = load_buckets("primary")
    inv = read_out("kpi_candidate_inventory.csv")
    tags = inv[inv.included].tag.tolist()
    ref = json.loads((OUT / "kpi_reference.json").read_text())
    kpi = pd.read_parquet(OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp")
    comp = pd.read_parquet(OUT / "kpi_component_scores.parquet")
    sens = read_out("kpi_sensitivity_analysis.csv")

    # ---------------------------------------------------------------- G1 source integrity
    man = pd.read_csv(ROOT / "data" / "raw" / "source_manifest.csv")
    pcol = next(c for c in man.columns if c in ("relative_path", "path", "file_path", "rel_path"))
    hcol = next(c for c in man.columns if "sha256" in c)
    mism = [r[pcol] for r in man.to_dict("records") if sha256(SOURCE_ROOT / r[pcol]) != r[hcol]]
    add("G1 source integrity", "SHA-256 of every source file equals the Phase 1 manifest", not mism, f"{len(man)} files; mismatches {mism}")

    # ---------------------------------------------------------------- G2 Phase 2 dependency integrity
    rec = json.loads((CACHE / "p2_input_hashes.json").read_text())
    now = {n: sha256(P2_OUT / n) if not n.startswith("data/") else sha256(ROOT / n) for n in rec}
    changed = [n for n in rec if rec[n] != now[n]]
    add("G2 Phase 2 dependency", "Phase 2 inputs unchanged since load (sha256)", not changed, f"{len(rec)} files; changed {changed}")
    p2v = read_p2("phase2_validation.csv")
    add("G2 Phase 2 dependency", "Phase 2 validation all PASS (dependency is sound)", (p2v.result == "PASS").all(),
        f"{int((p2v.result == 'PASS').sum())}/{len(p2v)} PASS")

    # ---------------------------------------------------------------- G3 data quality
    holds = read_p2("column_holds.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column)
    sources = set()
    for t in tags:
        s = spec_by_tag()[t]
        sources.update(s.derived_from or (t,))
    held_used = sorted(sources & set(holds.tag))
    add("G3 data quality", "No held column (unit review, sparse, constant, sentinel, duplicate, state) feeds the KPI", not held_used, held_used)
    conf = read_p2("baseline_confidence.csv").query("population == 'BASELINE_RUNNING'")
    insuff = set(conf[conf.baseline_confidence == "INSUFFICIENT"].pipe(lambda d: d.dataset + "!" + d.tag))
    add("G3 data quality", "No INSUFFICIENT-baseline column feeds the KPI", not (sources & insuff), sorted(sources & insuff))
    add("G3 data quality", "Held columns are absent from the scoring minute cache", not (set(values.columns) & set(holds.tag)),
        sorted(set(values.columns) & set(holds.tag)))
    sent = int(values.isin([99999.0, 9999.0]).sum().sum())
    add("G3 data quality", "No sentinel value (99999 / 9999) in the scoring cache", sent == 0, f"{sent} cells")
    tc = read_p2("tag_contract.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column)
    degc = [t for t in tc[tc.detected_unit.astype(str).str.lower() == "deg.c"].tag if t in values]
    imp = int((values[degc] <= -273).sum().sum())
    add("G3 data quality", "No physically impossible temperature (<= -273 degC) in the scoring cache", imp == 0, f"{imp} cells")
    raw = pd.read_parquet(ROOT / "data" / "processed" / "kiln_i.parquet", columns=["ts", "source_column", "mask_reason", "dup_status"])
    raw = raw[raw.dup_status.isin(["UNIQUE", "DUP_KEPT"]) & raw.source_column.astype(str).isin(["F", "G", "X", "AF", "S", "C"])]
    tok = raw.mask_reason.astype(str)
    badc = raw[np.logical_or.reduce([tok.str.contains(t, regex=False) for t in CAUSAL_INVALID_TOKENS])]
    leaked = sum(int(values[f"Kiln-I!{c}"].reindex(g.ts).notna().sum()) for c, g in badc.groupby(badc.source_column.astype(str)))
    add("G3 data quality", "Every Kiln-I cell carrying a causal invalid token (MISSING/TEXT/SENTINEL/IMPOSSIBLE/DUPLICATE/HOURLY) "
        "is NaN in the scoring cache (6 tags checked cell by cell)", leaked == 0, f"{len(badc)} token cells; {leaked} leaked")
    dq = read_out("kpi_data_quality.csv")
    fz = dq[dq.tag.astype(str).str.startswith("P2_FROZEN_WINDOW")]
    cov = float(fz.causal_frozen_minutes_inside.sum() / max(fz.minutes.sum(), 1))
    add("G3 data quality", "Causal frozen-row mask covers >= 95 % of the Phase 2 frozen window (2025-05-06)", cov >= 0.95,
        f"coverage {cov:.3f}; first causal frozen minute {fz.first_causal_frozen_minute.tolist()}")
    fw = read_p2("frozen_windows.csv")
    s0, s1 = pd.Timestamp(fw.window_start.iloc[0]), pd.Timestamp(fw.window_end.iloc[0])
    inside = kpi.loc[(kpi.index > s0 + pd.Timedelta(minutes=20)) & (kpi.index <= s1)]
    add("G3 data quality", "No bucket fully inside the frozen window is scored from frozen values",
        inside.raw_deviation_score.isna().all() or inside.data_quality.str.startswith("CAUSAL_FROZEN").all(),
        f"{len(inside)} buckets; scored {int(inside.raw_deviation_score.notna().sum())}")
    sep = kpi.loc["2025-09-01":]
    runF = values["Kiln-I!F"].where(b["minute_state"].state.eq("RUNNING"))
    last_f = runF.last_valid_index()
    after = kpi[kpi.index > last_f.ceil("10min")]
    add("G3 data quality", "Kiln-I September (MISSING) is not scored: no KPI after the last RUNNING Kiln-I Sp.Heat minute",
        sep.efficiency_deterioration_kpi.notna().sum() == 0 and after.raw_deviation_score.notna().sum() == 0,
        f"last RUNNING Kiln-I F minute {last_f}; September states {sep.kpi_reference_state.value_counts().to_dict()}")
    add("G3 data quality", "Every one of the 203 Phase 1/2 tags appears in the candidate inventory",
        set(tc.tag) <= set(inv.tag), f"{len(set(tc.tag) - set(inv.tag))} missing")
    add("G3 data quality", "Every excluded / context / sensitivity-only tag carries a reason",
        inv[~inv.included].exclusion_reason.fillna("").str.len().gt(0).all(), f"{int((~inv.included).sum())} tags")

    # ---------------------------------------------------------------- G4 temporal integrity
    tr_end = pd.Timestamp(PRIMARY.train_end)
    add("G4 temporal integrity", "REGRESSION GUARD: primary KPI is empty inside the training window (in-sample kept separately)",
        kpi.loc[kpi.index <= tr_end, "efficiency_deterioration_kpi"].isna().all(),
        f"in-sample rows {int(kpi.kpi_in_sample_reference.notna().sum())}")
    add("G4 temporal integrity", "REGRESSION GUARD: every OUT_OF_SAMPLE row is after the training window",
        (kpi.index[kpi.kpi_reference_state.str.startswith("OUT_OF_SAMPLE")] > tr_end).all(), "")
    ms = b["minute_state"]
    run = ms.state.eq("RUNNING")
    restarts = ms.index[(ms.state.eq("TRANSITION")) & ~ms.state.shift().eq("TRANSITION") & (ms.index > tr_end + pd.Timedelta("3D"))
                        & (ms.index < pd.Timestamp("2025-08-20"))]
    ramp_end = ms.index[run & ms.state.shift().eq("TRANSITION") & (ms.index > tr_end + pd.Timedelta("3D"))]
    stops = ms.index[ms.state.eq("STOPPED") & ~ms.state.shift().eq("STOPPED") & (ms.index > tr_end + pd.Timedelta("3D"))]
    kmax = kpi.efficiency_deterioration_kpi.idxmax()
    Ts = {"3 days after training end": tr_end + pd.Timedelta("3D"),
          "30 min after a restart (inside ramp)": restarts[0] + pd.Timedelta(minutes=30),
          "5 min after a causal ramp end": ramp_end[0] + pd.Timedelta(minutes=5),
          "20 min into a stop": stops[0] + pd.Timedelta(minutes=20),
          "30 min before a stop (pre-stop minutes)": stops[0] - pd.Timedelta(minutes=30),
          "7 min before a later stop": stops[min(3, len(stops) - 1)] - pd.Timedelta(minutes=7),
          "late August": pd.Timestamp("2025-08-18 13:43"),
          "maximum out-of-sample KPI": kmax,
          "mid-bucket timestamp (T not on the 10-min grid)": kmax + pd.Timedelta(minutes=137)}
    leak_bad = {}
    for name, T in Ts.items():
        S = T - pd.Timedelta("10D")
        A = run_kpi(values.loc[S:T], state.loc[S:T], PRIMARY, ref)[2]["kpi"]
        B = run_kpi(values.loc[S:T + pd.Timedelta("14D")], state.loc[S:T + pd.Timedelta("14D")], PRIMARY, ref)[2]["kpi"]
        a, bb = A[A.index <= T], B[B.index <= T]
        ok, n = frames_equal(a, bb.reindex(a.index), KPI_COLS)
        leak_bad[f"{name} @ {T}"] = n
    add("G4 temporal integrity", f"LEAKAGE TEST: KPI(t <= T) identical with and without 14 days of data after T ({len(Ts)} cut points, "
        "exact; masks, causal state incl. CONFLICT and buckets re-derived from the truncated minute inputs)",
        all(v == 0 for v in leak_bad.values()), leak_bad)
    Tf = tr_end + pd.Timedelta("1D")
    _, ref_trunc, _ = run_kpi(values.loc[:Tf], state.loc[:Tf], PRIMARY, None, tags)
    ref_trunc["kpi_version"] = ref["kpi_version"]
    same = json.dumps(ref_trunc, sort_keys=True, default=float) == json.dumps(ref, sort_keys=True, default=float)
    add("G4 temporal integrity", "Reference fitted on data truncated 1 day after training end == reference fitted with all data",
        same, "reference JSON identical" if same else "reference differs")
    rng = np.random.default_rng(PRIMARY.seed)
    k = pd.read_parquet(CACHE / "scored_primary.parquet")
    pts = rng.choice(k.index[k.persistent_deviation_score.notna()], 200, replace=False)
    bad = 0
    for t in pts:
        w = k.raw_deviation_score[(k.index > t - pd.Timedelta(PRIMARY.persistence_window)) & (k.index <= t)].dropna()
        bad += int(abs(w.median() - k.persistent_deviation_score[t]) > 1e-12)
    add("G4 temporal integrity", "Persistence = trailing median over (t-6h, t] recomputed at 200 random buckets", bad == 0, f"{bad} mismatches")
    masked, _ = prepare_minutes(values, PRIMARY)
    bad = 0
    for t in rng.choice(k.index[k.bucket_state.eq("RUNNING")], 100, replace=False):
        seg = masked.loc[(masked.index > t - pd.Timedelta(minutes=10)) & (masked.index <= t), "Kiln-I!F"]
        seg = seg[run.reindex(seg.index, fill_value=False)]
        exp = seg.median() if seg.notna().sum() >= PRIMARY.bucket_min_valid else np.nan
        got = b["values"]["Kiln-I!F"].get(t, np.nan)
        bad += int(not ((np.isnan(exp) and np.isnan(got)) or abs(exp - got) < 1e-9)) if not (np.isnan(exp) and np.isnan(got)) else 0
    add("G4 temporal integrity", "Bucket = median of RUNNING minutes in (t-10 min, t] (Kiln-I F, 100 random buckets)", bad == 0, f"{bad} mismatches")

    # ---------------------------------------------------------------- G5 statistical integrity
    kv = kpi.efficiency_deterioration_kpi.dropna()
    add("G5 statistical integrity", "REGRESSION GUARD: KPI within [0, 100]", kv.between(0, 100).all(), f"min {kv.min():.3f} max {kv.max():.3f}")
    sc = ref["scale"]
    grid = np.linspace(0, 10, 500)
    kk = to_kpi(grid, sc["m"], sc["q_anchor"])
    add("G5 statistical integrity", "REGRESSION GUARD: scale monotone; training median -> 0; training P95 -> 50",
        np.all(np.diff(kk) >= 0) and abs(to_kpi([sc["m"]], sc["m"], sc["q_anchor"])[0]) < 1e-9
        and abs(to_kpi([sc["q_anchor"]], sc["m"], sc["q_anchor"])[0] - 50) < 1e-9, sc)
    ins = kpi.kpi_in_sample_reference.dropna()
    k_lo, k_hi = (to_kpi([sc[q]], sc["m"], sc["q_anchor"])[0] for q in ("q_band_lo", "q_band_hi"))
    shares = [(ins < k_lo).mean(), ((ins >= k_lo) & (ins < k_hi)).mean(), (ins >= k_hi).mean()]
    add("G5 statistical integrity", "In-sample band shares reproduce the training quantiles (~90 / 9 / 1 %)",
        abs(shares[0] - 0.90) < 0.02 and abs(shares[2] - 0.01) < 0.01, [round(x, 4) for x in shares])
    bands = read_out("kpi_reference_bands.csv")
    add("G5 statistical integrity", "Every reference band is labelled as NOT a plant alarm / engineering limit",
        bands.label.eq(BAND_LABEL).all(), BAND_LABEL)
    # traceability: rebuild D and KPI for 300 scored buckets from the component parquet + reference
    samp = rng.choice(kv.index, 300, replace=False)
    c = comp[comp.ts.isin(samp)].pivot(index="ts", columns="tag", values="tag_score").reindex(samp)
    for t in tags:
        if t not in c:
            c[t] = np.nan
    raw = dimension_raw(c[tags], PRIMARY)
    S = standardise_dims(raw, ref["dims"])
    D = aggregate(S, c[tags], ref, PRIMARY)
    dd = (D - kpi.raw_deviation_score.reindex(samp)).abs().max()
    kd = (pd.Series(to_kpi(kpi.persistent_deviation_score.reindex(samp), sc["m"], sc["q_anchor"]), index=samp)
          - kpi.efficiency_deterioration_kpi.reindex(samp)).abs().max()
    add("G5 statistical integrity", "TRACEABILITY (round trip): D rebuilt from the stored kpi_component_scores + reference, KPI from P (300 buckets)",
        dd < 1e-9 and kd < 1e-9, f"max |dD| {dd:.2e}; max |dKPI| {kd:.2e}")
    blank = kpi[kpi.efficiency_deterioration_kpi.isna() & kpi.kpi_in_sample_reference.isna()]
    add("G5 statistical integrity", "kpi_band is empty on every row without a reported or in-sample KPI",
        blank.kpi_band.fillna("").eq("").all(), f"{len(blank)} rows; non-empty {int(blank.kpi_band.fillna('').ne('').sum())}")
    # independent z recomputation straight from the reference JSON (no kpi_core scoring code)
    zs = comp[comp.tag.isin(["Kiln-I!F", "Kiln-I!S", "Kiln-II!C"]) & comp.ts.isin(samp)]
    zmax = 0.0
    for r_ in zs.itertuples():
        tr = ref["tags"][r_.tag]
        f_ = b["values"]["Kiln-I!C"].get(r_.ts, np.nan)
        if not np.isfinite(f_):
            continue
        z_ = np.clip((r_.bucket_value - np.interp(f_, tr["centers"], tr["medians"])) / tr["scale"], -PRIMARY.z_cap, PRIMARY.z_cap)
        zmax = max(zmax, abs(z_ - r_.z))
    add("G5 statistical integrity", "TRACEABILITY (independent): tag z recomputed by hand from kpi_reference.json load curves",
        zmax < 1e-9, f"{len(zs)} tag-buckets; max |dz| {zmax:.2e}")
    for stt in ["STOPPED", "TRANSITION", "CONFLICT", "UNKNOWN"]:
        sub = kpi[kpi.operating_state == stt]
        add("G5 statistical integrity", f"No KPI value in {stt} buckets", sub.efficiency_deterioration_kpi.isna().all()
            and sub.kpi_in_sample_reference.isna().all(), f"{len(sub)} buckets")
    ref2, _ = fit_score(b, PRIMARY, tags)
    ref2["kpi_version"] = ref["kpi_version"]
    add("G5 statistical integrity", "Refit is deterministic (identical reference JSON)",
        json.dumps(ref2, sort_keys=True, default=float) == json.dumps(ref, sort_keys=True, default=float), "")
    add("G5 statistical integrity", "Secondary MCD covariance well conditioned (< 1e6)",
        ref["secondary"].get("condition_number", np.inf) < 1e6, ref["secondary"].get("condition_number"))
    # synthetic injection on a steady out-of-sample running stretch
    bs = b["meta"].bucket_state.eq("RUNNING")
    steady = bs.rolling("5D").mean()
    t_end = steady[(steady.index > tr_end + pd.Timedelta("6D")) & (steady >= 0.999)].index[0]
    T0 = t_end - pd.Timedelta("2D")
    S, E = T0 - pd.Timedelta("3D"), T0 + pd.Timedelta("2D")
    base = run_kpi(values.loc[S:E], state.loc[S:E], PRIMARY, ref)[2]["kpi"].kpi_value
    def inject(amp: float, dur: str) -> pd.Series:
        v2 = values.loc[S:E].copy()
        w = (v2.index > T0) & (v2.index <= T0 + pd.Timedelta(dur))
        for t in ["Kiln-I!F", "Kiln-I!G"]:
            v2.loc[w, t] = v2.loc[w, t] + amp * ref["tags"][t]["scale"]
        return run_kpi(v2, state.loc[S:E], PRIMARY, ref)[2]["kpi"].kpi_value - base

    d = inject(3.0, "24h")
    late = d[(d.index > T0 + pd.Timedelta("12h")) & (d.index <= T0 + pd.Timedelta("24h"))]
    add("G5 statistical integrity", "INJECTION: persistent +3 scale step on Sp.Heat F and G for 24 h raises the KPI "
        "(median rise in hours 12-24 >= 10 points)", late.median() >= 10,
        f"median rise {late.median():.1f}; max {d.max():.1f}; step start {T0}")
    before = d[d.index <= T0].abs().max()
    add("G5 statistical integrity", "INJECTION: KPI before the injected step is unchanged (no look-ahead)",
        before == 0 or np.isnan(before), f"max |dKPI| before step {before}")
    s10, s30 = inject(5.0, "20min"), inject(8.0, "20min")     # both above the window median, below the z cap
    after_win = s10[s10.index > T0 + pd.Timedelta("20min") + pd.Timedelta(PRIMARY.persistence_window)].abs().max()
    add("G5 statistical integrity", "INJECTION: a 20-min spike has BOUNDED influence - identical KPI change for a +5 and a "
        "+8 scale spike (both far above the window median and below the z cap: the median ignores their magnitude)", ((s10 - s30).abs().max() < 1e-9), f"max |d10 - d30| {(s10 - s30).abs().max():.2e}")
    add("G5 statistical integrity", "INJECTION: 20-min spike effect < half of the 24 h step effect and gone once the 6 h window passes",
        s10.abs().max() < 0.5 * late.median() and after_win == 0,
        f"spike max |dKPI| {s10.abs().max():.2f} vs step {late.median():.2f}; after window {after_win}")

    # ---------------------------------------------------------------- G6 sensitivity
    coll = sens[sens.verdict.isin(["COLLAPSE", "INSUFFICIENT_OVERLAP"])]
    add("G6 sensitivity", "No sensitivity variant collapses the KPI or lacks overlap (Spearman >= 0.30, >= 50 % scored, metrics defined)",
        coll.empty, coll.variant.tolist())
    tr_ = sens[~sens.group.str.startswith(("0", "S", "A")) & sens.variant_trend_jun_to_aug.notna()]
    add("G6 sensitivity", "Direction of the Jun -> Aug change is non-negative in every non-window variant (descriptive robustness)",
        (tr_.variant_trend_jun_to_aug >= 0).all(),
        f"{len(tr_)} variants; min {tr_.variant_trend_jun_to_aug.min():.1f}, max {tr_.variant_trend_jun_to_aug.max():.1f}")
    spv = sens[sens.group == "C specific heat"]
    add("G6 sensitivity", "Sp.Heat F vs G sensitivity completed (verdict recorded)", len(spv) == 2,
        dict(zip(spv.variant, spv.verdict)))
    for g in ["A training window", "B operating state", "D load conditioning", "E persistence", "F component inclusion", "G weighting",
              "I calibration"]:
        add("G6 sensitivity", f"Sensitivity group completed: {g}", (sens.group == g).any(),
            dict(zip(sens[sens.group == g].variant, sens[sens.group == g].verdict)))
    write_csv(pd.DataFrame(ROWS), "kpi_validation.csv", lg)
    lg.info("%d checks, %d FAIL", len(ROWS), sum(r["result"] == "FAIL" for r in ROWS))


if __name__ == "__main__":
    main()
