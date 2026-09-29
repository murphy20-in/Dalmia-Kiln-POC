"""Validation gates G1-G12 and leakage tests L1-L7 -> outputs/early_warning_validation.csv.

INDEPENDENT checks re-derive a property with a separate code path or a perturbation / truncation experiment;
CONSISTENCY checks compare outputs with each other; RUN checks use the orchestrator's before / after snapshots.
gates(A, None) = analysis-only rows (run-dependent rows PENDING) so the first-pass report is comparable across runs.
A result the data did not support is never a gate failure: gates test integrity, not favourable answers.
"""
from __future__ import annotations

import ast

import numpy as np
import pandas as pd

import build_controls as bc
import calibration
import negative_controls as nc
import warning_metrics as wm
from p8common import (CFG, DOCS, EVENT_DQ, MONTHS, OUT, P7_CACHE, P7_CACHE_INPUTS, P7_OUT, P7_REQUIRED, SCORE_COLUMNS, SCORE_VERSION, STATUSES,
                      P8Config, forbidden_hits, nb, p7c, risk_core)

L_CUTS = 3                     # truncation / perturbation cuts per event list (first, middle, last event onset)


def _eq(a: np.ndarray, b: np.ndarray, tol: float = 1e-9) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.allclose(a, b, rtol=0, atol=tol, equal_nan=True))


def _signals(score: np.ndarray, sig: dict, fam: np.ndarray, cfg: P8Config) -> dict:
    """Every Phase 8 per-bucket signal recomputed from a score series (same functions as make_signals)."""
    out = wm.signals_from(score, sig["thr"], fam, cfg, roll=True)
    out["W"] = {h: wm.window_stat(out["rank"], h) for h in cfg.horizons}
    return out


def _signal_prefix_equal(a: dict, b: dict, p: int) -> list[str]:
    s = slice(0, p + 1)
    bad = [k for k in ("rank", "slope", "accel", "rank_roll") if not _eq(a[k][s], b[k][s])]
    bad += [w for w in a["flags"] if not np.array_equal(a["flags"][w][s], b["flags"][w][s])]
    return bad + [f"W{h}" for h in a["W"] if not _eq(a["W"][h][s], b["W"][h][s])]


def _perturb_grid(g: pd.DataFrame, t_cut: pd.Timestamp, seed: int) -> pd.DataFrame:
    """Every grid column after t_cut replaced by random type-valid values (Phase 7 perturbation convention)."""
    g = g.copy()
    sel = g.index > t_cut
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
    return g


def control_recheck(B: dict, h: int, cfg: P8Config = CFG) -> list[str]:
    """Independent interval-level re-derivation of control cleanliness: window (A - h, A] vs every candidate extent
    [onset, end + 6 h], every 24-h pre-onset zone, DQ buckets, and the operational share, bucket by bucket."""
    pos = np.flatnonzero(B["elig"][h])
    A = B["ix"][pos]
    lo = A - pd.Timedelta(minutes=10 * nb(h))
    ivs = [(r.onset_time, r.end_time + pd.Timedelta(hours=cfg.ctrl_post_end_h)) for r in B["eps"].itertuples()]
    ivs += [(r.T0 - pd.Timedelta(hours=cfg.ctrl_pre_onset_h), r.T0) for r in B["events"].itertuples()]
    bad = []
    for a, b in ivs:
        hit = (A > a) & (lo < b)
        if hit.any():
            bad.append(f"{int(hit.sum())} controls overlap [{a}, {b}]")
    n = nb(h)
    win = pos[:, None] - np.arange(n)[None, :]
    if (win < 0).any():
        bad.append("window before grid start")
    win = np.maximum(win, 0)
    if B["dq"][win].any():
        bad.append(f"{int(B['dq'][win].any(axis=1).sum())} controls touch a Phase 1 DQ window")
    if (B["oper"][win].sum(axis=1) < -(-2 * n // 3)).any() or not B["oper"][pos].all():
        bad.append("operational share / anchor state violated")
    return bad


def event_recheck(B: dict, ok: np.ndarray, h: int, cfg: P8Config = CFG) -> list[str]:
    """Independent interval-level re-check that each evaluable event window (T0 - h, T0] touches no OTHER candidate
    extent [onset, end + 6 h] and no Phase 1 DQ bucket (a period's own extent starts at T0 and cannot overlap)."""
    ev = B["events"][ok]
    ivs = [(r.onset_time, r.end_time + pd.Timedelta(hours=cfg.ctrl_post_end_h)) for r in B["eps"].itertuples()]
    bad = []
    for e in ev.itertuples():
        lo = e.T0 - pd.Timedelta(minutes=10 * nb(h))
        hits = [a for a, b in ivs if e.T0 > a and lo < b]
        if hits:
            bad.append(f"{e.event_id} h{h} overlaps candidate(s) starting {hits[:2]}")
        if B["dq"][max(e.pos_T0 - nb(h) + 1, 0):e.pos_T0 + 1].any():
            bad.append(f"{e.event_id} h{h} touches a Phase 1 DQ window")
    return bad


def gates(A: dict, run_info: dict | None, cfg: P8Config = CFG, report_text: str | None = None) -> pd.DataFrame:
    B, sigs, res, out = A["B"], A["sigs"], A["res"], A["outputs"]
    P, VAR = sigs["PRIMARY"], [n for n in sigs if n != "PRIMARY"][0]
    ev, ix, fam = B["events"], B["ix"], B["s"].family_count_abnormal.to_numpy(float)
    rows = []

    def add(gate, check, ok, evidence, kind="INDEPENDENT", result=None):
        rows.append({"gate": gate, "check": check, "check_type": kind,
                     "result": result or ("PASS" if ok else "FAIL"), "evidence": str(evidence)[:900]})

    def pending(gate, check, why="run-dependent: evaluated after tests / snapshots"):
        add(gate, check, False, why, "RUN", "PENDING")

    # ------------------------------------------------------------------ G1 input contract (+ L6)
    g = "G1 INPUT CONTRACT"
    miss = [n for n in P7_REQUIRED if not (P7_OUT / n).is_file()]
    add(g, "all Phase 7 required artifacts present", not miss, f"missing {miss}" if miss else
        f"{len(P7_REQUIRED)} files present", "CONSISTENCY")
    miss = [n for n in P7_CACHE_INPUTS if not (P7_CACHE / n).is_file()]
    add(g, "Phase 7 cache inputs present (grid drives the rescore and the O2-excluded variant)", not miss,
        f"missing {miss}" if miss else f"{len(P7_CACHE_INPUTS)} files present", "CONSISTENCY")
    vers = set(B["s"].score_version.dropna().unique())
    add(g, "score version frozen", vers == {SCORE_VERSION}, f"score_version {sorted(vers)}", "CONSISTENCY")
    add(g, "12 final out-of-sample empirical abnormal periods, T0 on the grid",
        len(ev) == 12 and bool((ix[ev.pos_T0] == ev.T0).all()), f"{len(ev)} periods; months "
        f"{ev.month.value_counts().sort_index().to_dict()}", "CONSISTENCY")
    add(g, "only operational == True scores carry a value (primary and variant)",
        all(bool(np.isnan(s["score"][~B["oper"]]).all()) for s in sigs.values()),
        f"{int(B['oper'].sum())} operational buckets", "CONSISTENCY")
    rq, stored = P["thr"]["ref_quantiles"], p7c.load_refs()["PRIMARY"]["reference_score_quantiles"]
    dq_ = max(abs(rq[k] - stored[k]) for k in stored)
    add(g, "L6 frozen reference reproduced: rescore == stored risk_score; rebuilt reference quantiles == stored",
        B["rescore"]["max_abs_diff"] <= 1e-6 and B["rescore"]["nan_pattern_equal"] and dq_ <= 1e-9,
        f"rescore max |diff| {B['rescore']['max_abs_diff']:.2e}, NaN pattern equal {B['rescore']['nan_pattern_equal']};"
        f" max quantile diff {dq_:.2e}")
    if run_info is None:
        for c in ("L6 Phase 7 frozen reference files byte-identical before / after", "source workbooks unchanged",
                  "Phase 1-7 artifacts unchanged"):
            pending(g, c)
    else:
        add(g, "L6 Phase 7 frozen reference files byte-identical before / after", run_info["frozen_unchanged"],
            "; ".join(f"{k} {v[:12]}" for k, v in sorted(run_info["frozen"].items())), "RUN")
        add(g, "source workbooks unchanged", run_info["src_unchanged"] and run_info["n_src"] > 0,
            f"{run_info['n_src']} source files: sha256 / size / mtime equal (0 files = source not mounted = FAIL)", "RUN")
        add(g, "Phase 1-7 artifacts unchanged", not run_info["upstream_changed"] and run_info["n_upstream"] > 0,
            f"{run_info['n_upstream']} files; changed {run_info['upstream_changed'][:5]}", "RUN")

    # ------------------------------------------------------------------ G2 temporal integrity (L1, L2, L5, L7)
    g = "G2 TEMPORAL INTEGRITY"
    grid, ref, ctx = B["grid"], B["refs"]["PRIMARY"], B["ctx"]
    full = risk_core.score_core(grid, ref, p7c.PRIMARY, ctx)["R"]
    cuts = sorted({int(ev.pos_T0.iloc[i]) for i in (0, len(ev) // 2, len(ev) - 1)})[:L_CUTS]
    bad = [str(ix[p]) for p in cuts
           if not _eq(risk_core.score_core(grid.iloc[:p + 1], ref, p7c.PRIMARY, ctx)["R"], full[:p + 1])]
    add(g, "L1 Phase 7 score at t uses nothing after t (score_core on the grid truncated at event onsets)", not bad,
        f"cuts {[str(ix[p]) for p in cuts]}; differing {bad}")
    base = _signals(P["score"], P, fam, cfg)
    bad = []
    for p in cuts:
        sc = P["score"].copy()
        rng = np.random.default_rng(cfg.seed + p)
        sc[p + 1:] = np.where(np.isfinite(sc[p + 1:]), rng.uniform(0, 100, sc.size - p - 1), np.nan)
        bad += [f"{ix[p]}:{k}" for k in _signal_prefix_equal(base, _signals(sc, P, fam, cfg), p)]
    add(g, "L1 Phase 8 signals (rank, slope, acceleration, rolling rank, W1-W5, window statistics) at t use nothing "
        "after t", not bad, f"score after each cut randomised; differing {bad[:5]}")
    neg = out["early_warning_negative_controls.csv"]
    n5 = neg[neg.control_id == "NC5"]
    add(g, "L2 no warning / lead metric uses post-T0 values (NC5, every period, both variants)",
        len(n5) == len(sigs) and n5.status.eq("PASS_IDENTICAL").all(), "; ".join(
            f"{r.score_variant} {r.status}" for r in n5.itertuples()))
    bad = [str(ix[p]) for p in cuts if not _eq(risk_core.score_core(
        _perturb_grid(grid, ix[p], cfg.seed + p), ref, p7c.PRIMARY, ctx)["R"][:p + 1], full[:p + 1])]
    add(g, "L5 future-period modification (every grid column after the cut randomised) leaves past scores unchanged",
        not bad, f"cuts {[str(ix[p]) for p in cuts]}; differing {bad}")
    no_afr = {**ctx, "afr_events": ctx["afr_events"].iloc[0:0]}
    shifted = {**ctx, "afr_events": ctx["afr_events"].assign(T=ctx["afr_events"]["T"] + pd.Timedelta(days=3))}
    afr_ok = all(_eq(risk_core.score_core(grid, ref, p7c.PRIMARY, c)["R"], full) for c in (no_afr, shifted))
    add(g, "L7 afr_context not used live: not read (column allow-list), zero AFR weight, AFR events removed / shifted "
        "leave the score unchanged",
        "afr_context" not in SCORE_COLUMNS and "afr_context" not in B["s"].columns and p7c.PRIMARY.afr_weight == 0
        and afr_ok, f"allow-list {len(SCORE_COLUMNS)} columns without afr_context; afr_weight "
        f"{p7c.PRIMARY.afr_weight}; score unchanged under AFR removal / 3-day shift {afr_ok}")
    add(g, "risk_score_diagnostics.parquet is not an operational input",
        "risk_score_diagnostics.parquet" not in P7_REQUIRED, "Phase 8 reads the in-sample reference only by "
        "rescoring with the frozen references (L6)", "CONSISTENCY")

    # ------------------------------------------------------------------ G3 event-window integrity
    g = "G3 EVENT-WINDOW INTEGRITY"
    eps6 = B["eps"].set_index("episode_id")
    add(g, "T0 = Phase 6 onset_time; T0 <= detection time; windows end at the T0 bucket",
        bool((ev.T0.to_numpy() == eps6.loc[ev.event_id, "onset_time"].to_numpy()).all()
             and (ev.pos_T0 <= ev.pos_det).all()),
        f"detection - T0 minutes: {sorted(((ev.pos_det - ev.pos_T0) * 10).tolist())}", "CONSISTENCY")
    tr = out["early_warning_trajectories.parquet"]
    t0 = tr.event_id.map(ev.set_index("event_id").T0)
    add(g, "pre-onset trajectories contain only buckets <= T0", bool((tr.timestamp <= t0).all() and
                                                                       (tr.offset_minutes <= 0).all()),
        f"{len(tr)} rows; max offset {tr.offset_minutes.max()} min", "CONSISTENCY")
    x = np.arange(40, dtype=float)
    y = x.copy()
    y[30:] = 1e6
    add(g, "window statistic at T0 ignores every bucket after T0 (synthetic)",
        all(wm.window_stat(x, h)[29] == wm.window_stat(y, h)[29] for h in (15, 60, 120)), "values after T0 set to 1e6")
    add(g, "every period has exactly one data-quality status from the declared set",
        ev.data_quality_status.isin(EVENT_DQ).all() and ev.data_quality_status_o2x.isin(EVENT_DQ).all(),
        ev.data_quality_status.value_counts().to_dict(), "CONSISTENCY")
    bad = [f"{v}: {b}" for v in res for h in cfg.horizons for b in event_recheck(B, res[v]["hres"][h]["ok"], h, cfg)]
    add(g, "event windows free of OTHER candidate periods and Phase 1 DQ windows (symmetry with controls)", not bad,
        bad[:3] or "interval-level re-check of every evaluable (period, horizon, variant): " + ", ".join(
            f"{h}m {int(res['PRIMARY']['hres'][h]['ok'].sum())}" for h in cfg.horizons))

    # ------------------------------------------------------------------ G4 control integrity
    g = "G4 CONTROL INTEGRITY"
    for h in (cfg.primary_h, max(cfg.horizons)):
        bad = control_recheck(B, h, cfg)
        add(g, f"controls (h = {h} min) do not overlap any candidate period / pre-onset zone / DQ window",
            not bad, bad[:3] or f"{int(B['elig'][h].sum())} eligible anchors re-checked at interval level")
    pr = res["PRIMARY"]["primary"]
    per_m = {MONTHS[m]: int((B["elig"][cfg.primary_h] & (B["month"] == m)).sum()) for m in MONTHS}
    add(g, "every month has >= min_controls eligible controls at the primary horizon",
        min(per_m.values()) >= cfg.min_controls, f"{per_m}; primary endpoint uses {pr['n_controls']}", "CONSISTENCY")

    # ------------------------------------------------------------------ G5 threshold integrity (L3, L4)
    g = "G5 THRESHOLD INTEGRITY"
    rt = ix[B["ref_mask"]]
    shared = int((B["ref_mask"] & B["oper"]).sum())
    add(g, "L3 reference / warning thresholds use only Apr-May reference rows, which precede every onset and never "
        "carry an evaluated (operational) score", set(rt.month) <= {4, 5} and rt.max() < ev.T0.min() and shared == 0,
        f"reference rows {rt.min()} .. {rt.max()} ({len(rt)}); first onset {ev.T0.min()}; reference rows that are "
        f"also operational: {shared} (pre-onset windows reaching into May have no score there and lose validity)")
    s = out["early_warning_summary.csv"]
    mh = s[(s.section == "MONTH_HOLDOUT") & s.threshold_slope.notna()]
    chron = all(max(ast.literal_eval(r.train_months)) < min(ast.literal_eval(r.test_months)) for r in mh.itertuples())
    add(g, "L3 month-holdout thresholds come from earlier months only", chron and len(mh) > 0,
        "; ".join(f"{r.train_months}->{r.test_months}" for r in mh.drop_duplicates("train_months").itertuples()),
        "CONSISTENCY")
    v = np.array([0.1, 0.4, 0.5, 0.6, 0.7, 0.9])
    t_a = calibration.loeo_thresholds(v)
    inv = all(calibration.loeo_thresholds(np.where(np.arange(v.size) == i, 99.0, v))[i] == t_a[i]
              for i in range(v.size))
    add(g, "L4 leave-one-event-out threshold never uses the evaluated event", inv,
        "target value replaced by 99 -> its own threshold unchanged")
    add(g, "no threshold selected on the evaluation periods: W1/W3 fixed ranks, W2/W4 from the reference slope "
        "distribution, W5 fixed family count", P["thr"]["source"] == "REF_APR_MAY",
        f"W2 slope P95 {P['thr']['slope']:.2f} pts/h, W4 accel P95 {P['thr']['accel']:.2f}", "CONSISTENCY")

    # ------------------------------------------------------------------ G6 negative controls
    g = "G6 NEGATIVE CONTROL"
    for cid in ("NC1", "NC2"):
        r = neg[neg.control_id == cid]
        add(g, f"{cid} null centred on zero (|median| <= {nc.NULL_TOL})", (r.null_effect.abs() <= nc.NULL_TOL).all(),
            "; ".join(f"{q.score_variant} null median {q.null_effect:+.3f}, n {q.n_null}" for q in r.itertuples()),
            "CONSISTENCY")
    r = neg[neg.control_id == "NC4"]
    add(g, "NC4 mirrored-position draw reported (single deterministic draw; not a pass criterion - NC1 is the shift "
        "null)", len(r) == len(sigs), "; ".join(f"{q.score_variant} mirrored {q.null_effect:+.3f} vs observed "
                                               f"{q.observed_effect:+.3f} ({q.status})" for q in r.itertuples()),
        "CONSISTENCY")
    r = neg[neg.control_id == "NC3"]
    add(g, "NC3 backward diagnostic reported", len(r) == len(sigs), "; ".join(
        f"{q.score_variant}: post-end {q.null_effect:+.3f} vs pre-onset {q.observed_effect:+.3f}" for q in r.itertuples()),
        "CONSISTENCY")

    # ------------------------------------------------------------------ G7 O2 robustness
    g = "G7 O2 ROBUSTNESS"
    o2, hz = out["early_warning_o2_sensitivity.csv"], out["early_warning_horizon_validation.csv"]
    need = ["primary_endpoint_PE_60min", "primary_endpoint_status", "rank_excess_60min_JUN", "rank_excess_60min_AUG",
            "load_adjusted_effect_60min", "W1_RANK_coverage_60min"]
    add(g, "key conclusions repeated without Kiln-I!X (endpoint, horizons, months, load, warnings)",
        set(need) <= set(o2.metric) and (hz.score_variant == VAR).any(), f"{len(o2)} comparison rows; "
        f"status {o2.set_index('metric').status.get('primary_endpoint_status')}", "CONSISTENCY")
    add(g, "O2 variant never replaces the primary score", not _eq(sigs[VAR]["score"], P["score"]) and
        _eq(P["score"][B["oper"]], B["s"].risk_score.to_numpy(float)[B["oper"]]),
        "primary = stored Phase 7 risk_score on operational rows", "CONSISTENCY")

    # ------------------------------------------------------------------ G8 load robustness
    g = "G8 LOAD ROBUSTNESS"
    ld = out["early_warning_load_sensitivity.csv"]
    add(g, "analyses A-D (raw, load-adjusted, matched-load, transition-excluded) at every horizon, both variants",
        len(ld) == len(cfg.horizons) * len(sigs) and ld[["raw_effect", "load_adjusted_effect"]].notna().all().all()
        and ld.groupby("score_variant")[["matched_load_effect", "transition_excluded_effect"]].apply(
            lambda d: d.notna().any().all()).all(),
        ld[ld.horizon_minutes == cfg.primary_h][["score_variant", "status"]].to_dict("records"), "CONSISTENCY")

    # ------------------------------------------------------------------ G9 month robustness
    g = "G9 MONTH ROBUSTNESS"
    mo = s[s.section.isin(["MONTH", "LEAVE_ONE_MONTH_OUT"])]
    add(g, "June / July / August examined independently and left out one at a time (both variants)",
        len(mo) == 2 * len(MONTHS) * len(sigs), "; ".join(
            f"{r.variant[:8]} {r.slice} {r.pe:+.3f} (n {int(r.n_evaluable)})" for r in mo.itertuples()), "CONSISTENCY")

    # ------------------------------------------------------------------ G10 event leave-out
    g = "G10 EVENT LEAVE-OUT"
    lo = res["PRIMARY"]["loeo"]
    add(g, "leave-one-event-out primary endpoint for every evaluable period",
        int(np.isfinite(lo).sum()) == int(pr["ok"].sum()), f"{int(np.isfinite(lo).sum())} fits; range "
        f"[{np.nanmin(lo):+.3f}, {np.nanmax(lo):+.3f}]", "CONSISTENCY")
    lt = s[s.section == "LOEO_EVENT_TUNED_THRESHOLD"]
    add(g, "event-tuned thresholds are leave-one-out only (diagnostic, never deployed)", len(lt) == len(ev),
        f"{int(lt.held_out_covered.eq(True).sum())} held-out periods at / above their threshold", "CONSISTENCY")

    # ------------------------------------------------------------------ G11 reproducibility
    g = "G11 REPRODUCIBILITY"
    if run_info is None:
        pending(g, "two clean runs byte-identical")
        pending(g, "unit tests pass")
    else:
        d = run_info["determinism"]
        if d["compared"] < d["expected"]:
            add(g, "two clean runs byte-identical", False, f"only {d['compared']}/{d['expected']} artifacts had a "
                "previous run (first run: re-run run_phase8.py --clean)", "RUN", "PENDING")
        else:
            add(g, "two clean runs byte-identical", not d["differing"] and d["both_clean"],
                f"{d['compared']} artifacts compared (10 outputs + first-pass report MD / HTML) with the previous run; "
                f"both runs --clean: {d['both_clean']}; differing {d['differing']}", "RUN")
        add(g, "unit tests pass", run_info["tests_rc"] == 0, run_info["tests_tail"], "RUN")

    # ------------------------------------------------------------------ G12 claim integrity
    g = "G12 CLAIM INTEGRITY"
    fd = s[s.section == "FINDING"]
    add(g, "every major finding has exactly one of the five classes; plant-event claims BLOCKED",
        fd.classification.isin(STATUSES).all() and fd[fd.finding.str.startswith("F15")].classification.eq(
            "BLOCKED").all(), fd.classification.value_counts().to_dict(), "CONSISTENCY")
    cols = sorted({c for n, df in out.items() for c in df.columns})
    hits = forbidden_hits("\n".join(cols) + "\n" + "\n".join(str(v) for v in fd.finding))
    add(g, "no forbidden terminology in output column names / finding statements", not hits, hits[:3] or
        f"{len(cols)} column names scanned")
    doc_hits = {p.name: forbidden_hits(p.read_text(encoding="utf-8")) for p in sorted(DOCS.glob("*.md"))}
    doc_hits = {k: v for k, v in doc_hits.items() if v}
    add(g, "no unsupported deposit / failure / error-rate claims in docs", not doc_hits, doc_hits or
        f"{len(list(DOCS.glob('*.md')))} docs scanned")
    if report_text is None:
        pending(g, "no unsupported claims in the report", "evaluated on the first-pass report")
    else:
        h = forbidden_hits(report_text)
        add(g, "no unsupported claims in the report", not h, h[:3] or f"{len(report_text.splitlines())} lines scanned")
    return pd.DataFrame(rows)
