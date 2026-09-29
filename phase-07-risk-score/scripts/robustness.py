"""Step 4 - robustness variants, architecture candidates, consistency controls and the AFR / Phase 4 inclusion tests.

Every variant refits its own frozen reference (Apr-May, or a shifted window inside Apr-May) and its own bands, then is
compared with the primary on the primary's operational buckets (out of sample, VALID). Pre-declared materiality (the
Phase 3 rule): Spearman >= 0.80, band agreement >= 0.85, median |difference| <= 10 points -> STABLE, else SENSITIVE.
SENSITIVE results are reported, never hidden.

Coverage of the 12 Phase 6 periods is reported for every variant and is NOT an architecture-selection criterion
(circular: the periods were found from the same components). It IS used by the AFR / Phase 4 inclusion tests, which can
only ADD a signal and are therefore biased toward exclusion - an exclusion is "no gain on circular coverage", not
evidence that the signal is irrelevant. The circular-shift / random-placement controls are CONSISTENCY controls.

Writes outputs/risk_score_robustness.csv
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy import stats

from calibration import auc, period_mask
from common import (BANDS, CONFIDENCE_VARIANTS, ac, ic, FAMILIES, MONTHS, OUT, PRIMARY, P7Config, load_context, log,
                    read_json, variant, write_csv)
from reference_builder import fit_reference
from risk_core import band_of, score_core, similarity

MATERIALITY = ac.p3common.MATERIALITY          # the pre-declared Phase 3 materiality rule, reused
MIN_SHIFT_BUCKETS = 7 * 144          # circular shifts of at least 7 days
N_NULL = 200
INCLUSION_MIN_GAIN = 0.02
INCLUSION_MAX_MONTH_CHANGE = 0.10
CONFIDENCE_DIMENSION = {"WINDOW_30MIN": "SMOOTHING_WINDOW", "WINDOW_2H": "SMOOTHING_WINDOW",
                        "ABNORMAL_P85": "ABNORMAL_THRESHOLD", "ABNORMAL_P95": "ABNORMAL_THRESHOLD",
                        "WEIGHTS_EQUAL": "FAMILY_WEIGHTS", "WEIGHTS_602020": "FAMILY_WEIGHTS"}


# ============================================================================== pure comparison helpers
def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def compare(r0: np.ndarray, b0: np.ndarray, r1: np.ndarray, b1: np.ndarray) -> dict:
    """Agreement of a variant (r1, b1) with the primary (r0, b0) on rows where both are finite."""
    ok = np.isfinite(r0) & np.isfinite(r1)
    if ok.sum() < 30:
        return {"n": int(ok.sum()), "spearman": np.nan, "band_agreement": np.nan, "top_decile_jaccard": np.nan,
                "high_jaccard": np.nan, "median_abs_diff": np.nan}
    x, y = r0[ok], r1[ok]
    return {"n": int(ok.sum()), "spearman": float(stats.spearmanr(x, y).statistic),
            "band_agreement": float(np.mean(b0[ok] == b1[ok])),
            "top_decile_jaccard": jaccard(x >= np.quantile(x, 0.9), y >= np.quantile(y, 0.9)),
            "high_jaccard": jaccard(np.isin(b0[ok], BANDS[2:]), np.isin(b1[ok], BANDS[2:])),
            "median_abs_diff": float(np.median(np.abs(x - y)))}


def verdict(m: dict) -> str:
    if not np.isfinite(m.get("spearman", np.nan)):
        return "NOT_EVALUABLE"
    ok = (m["spearman"] >= MATERIALITY["spearman_min"] and m["band_agreement"] >= MATERIALITY["band_agreement_min"]
          and m["median_abs_diff"] <= MATERIALITY["median_abs_diff_max"])
    return "STABLE" if ok else "SENSITIVE"


def circular_null(score: np.ndarray, inside: np.ndarray, stat, n: int, seed: int, min_shift: int) -> np.ndarray:
    """stat(score rolled by k, inside) for n random shifts k in [min_shift, len - min_shift] (preserves the marginal
    distribution and autocorrelation, breaks the alignment with the periods). All-NaN if the series is too short."""
    rng = np.random.default_rng(seed)
    L = len(score)
    if L <= 2 * min_shift:
        return np.full(n, np.nan)
    return np.array([stat(np.roll(score, int(k)), inside) for k in rng.integers(min_shift, L - min_shift, n)])


def random_windows_null(score: np.ndarray, durations: list[int], n: int, seed: int) -> np.ndarray:
    """Median score inside len(durations) randomly placed windows of the same lengths (randomised labels)."""
    rng = np.random.default_rng(seed)
    L = len(score)
    out = []
    for _ in range(n):
        m = np.zeros(L, bool)
        for d in durations:
            s = int(rng.integers(0, max(L - d, 1)))
            m[s:s + d] = True
        out.append(np.nanmedian(score[m]))
    return np.asarray(out)


def p_upper(obs: float, null: np.ndarray) -> float:
    null = null[np.isfinite(null)]
    return float((1 + np.sum(null >= obs)) / (1 + null.size)) if null.size else np.nan


# ============================================================================== variants
def most_correlated_pair(ref: dict) -> tuple[float, str, str]:
    rho = ref["family_spearman"]
    pairs = [(abs(rho[a][b]), a, b) for i, a in enumerate(FAMILIES) for b in FAMILIES[i + 1:]
             if rho[a][b] is not None and np.isfinite(rho[a][b])]
    return max(pairs) if pairs else (np.nan, FAMILIES[2], FAMILIES[3])


def variant_set(ref: dict) -> list[tuple[str, str, P7Config, dict]]:
    """(dimension, name, config, options). options: {'merge': (a, b)} builds a merged-family grid column;
    {'exclude_o2': True} swaps in the COMBUSTION / STABILITY components rebuilt without the O2 analyser (DQ-1)."""
    r, a, b = most_correlated_pair(ref)
    v = [("REFERENCE_WINDOW", "REF_APR_ONLY", variant(name="REF_APR_ONLY", ref_end="2025-04-30 23:59"), {}),
         ("REFERENCE_WINDOW", "REF_MAY_ONLY", variant(name="REF_MAY_ONLY", ref_start="2025-05-01 00:00"), {}),
         ("REFERENCE_WINDOW", "REF_APR08_MAY31", variant(name="REF_APR08_MAY31", ref_start="2025-04-08 00:00"), {}),
         ("REFERENCE_WINDOW", "REF_APR01_MAY24", variant(name="REF_APR01_MAY24", ref_end="2025-05-24 23:59"), {}),
         ("LOAD_NORMALIZATION", "ANCHORS_PER_TENTATIVE_LOAD_BAND", variant(name="LOAD_BAND", load_mode="load_band"), {}),
         ("FAMILY_WEIGHTS", "MAGNITUDE_ONLY", variant(name="W_MAG", w_magnitude=1.0, w_concurrence=0.0,
                                                     w_persistence=0.0), {})]
    v += [(CONFIDENCE_DIMENSION[n], n, c, {}) for n, c in CONFIDENCE_VARIANTS.items()]
    v += [("FAMILY_WEIGHTS", f"DROP_{d}", variant(name=f"DROP_{d}", families=tuple(f for f in FAMILIES if f != d)), {})
          for d in FAMILIES]
    v += [("PERSISTENCE_WINDOW", "PERSIST_2H", variant(name="P2H", persistence_buckets=12), {}),
          ("PERSISTENCE_WINDOW", "PERSIST_6H", variant(name="P6H", persistence_buckets=36), {}),
          ("SMOOTHING_WINDOW", "WINDOW_6H", variant(name="W6H", window_buckets=36, window_min_valid=24), {}),
          ("MISSING_VALUE_TREATMENT", "DENOMINATOR_AVAILABLE_FAMILIES",
           variant(name="DEN_AVAIL", denominator="available"), {}),
          ("CORRELATED_SIGNAL_GROUPING", f"MERGE_{a}+{b} (reference rho {r:.2f})",
           variant(name="MERGE", families=tuple(f for f in FAMILIES if f not in (a, b)) + (f"{a}+{b}",)),
           {"merge": (a, b)}),
          ("DATA_QUALITY_SENSOR (DQ-1)", "EXCLUDE_KILN_INLET_O2_ANALYSER", variant(name="NO_O2X"), {"exclude_o2": True}),
          ("AFR_INCLUSION", "AFR_DOWN_TRANSITION_10PCT", variant(name="AFR10", afr_weight=0.10), {}),
          ("PHASE4_INCLUSION", "PHASE4_INDICATOR_10PCT", variant(name="P4_10", p4_weight=0.10), {})]
    return v


def variant_grid(grid: pd.DataFrame, opts: dict) -> pd.DataFrame:
    if "merge" in opts:
        a, b = opts["merge"]
        g = grid.copy()
        g[f"comp_{a}+{b}"] = g[[f"comp_{a}", f"comp_{b}"]].mean(axis=1, skipna=False)
        return g
    if opts.get("exclude_o2"):
        g = grid.copy()
        for d in ("COMBUSTION", "STABILITY"):
            g[f"comp_{d}"] = g[f"comp_{d}_EXCL_O2"]
        return g
    return grid


def run_variant(grid: pd.DataFrame, cfg: P7Config, ctx: dict, opts: dict) -> dict:
    g = variant_grid(grid, opts)
    ref = fit_reference(g, cfg, ctx["episodes"], ctx)
    core = score_core(g, ref, cfg, ctx)
    R = np.where(core["valid3"], core["R"], np.nan)
    return {"R": R, "band": band_of(R, ref["bands"]), "core": core, "ref": ref}


def family_share_corr(c0: dict, c1: dict, rows: np.ndarray) -> float:
    common = [d for d in FAMILIES if d in c0["contrib"] and d in c1["contrib"]]
    if len(common) < 3:
        return np.nan
    s0 = np.array([np.nanmean(c0["contrib"][d][rows]) for d in common])
    s1 = np.array([np.nanmean(c1["contrib"][d][rows]) for d in common])
    return float(stats.spearmanr(s0, s1).statistic)


def month_high(band: np.ndarray, ix: pd.DatetimeIndex, rows: np.ndarray) -> dict:
    return {f"share_ge_high_{MONTHS[m].lower()}": float(np.isin(band[rows & (ix.month == m)], BANDS[2:]).mean())
            if (rows & (ix.month == m)).any() else np.nan for m in MONTHS}


def episodes_per_100h(band: np.ndarray, rows: np.ndarray) -> tuple[float, int]:
    hi = np.isin(band, BANDS[2:]) & rows
    starts = ic.run_lengths(hi) == 1
    single = starts & ~np.r_[hi[1:], False]
    return 100 * starts.sum() / max(rows.sum() / 6, 1e-9), int(single.sum())


# ============================================================================== step
def main():
    lg = log("robustness")
    ctx = load_context()
    grid, eps = ctx["grid"], ctx["episodes"]
    ix = grid.index
    s = pd.read_parquet(OUT / "risk_scores.parquet").set_index("timestamp").reindex(ix)
    ref0 = read_json(OUT / "risk_score_reference.json")
    oper = s.operational.to_numpy(bool)
    r0 = np.where(oper, s.risk_score.to_numpy(float), np.nan)
    b0 = np.where(oper, s.risk_band.to_numpy(object), "")
    core0 = score_core(grid, ref0, PRIMARY, ctx)
    inside = np.zeros(len(ix), bool)
    for r in eps[eps.in_final_set].itertuples():
        inside |= period_mask(ix, r.start_time, r.end_time)
    auc0 = auc(r0[oper & inside], r0[oper & ~inside])
    base_mh = month_high(b0, ix, oper)
    rows = [{"section": "PRIMARY", "dimension": "PRIMARY", "variant": "PRIMARY", "n": int(oper.sum()),
             "coverage_auc": auc0, **base_mh, "result": "REFERENCE"}]
    vset = variant_set(ref0)
    results = {}
    for dim, name, cfg, opts in vset:
        v = run_variant(grid, cfg, ctx, opts)
        results[name] = (v, cfg)
        rv = np.where(oper, v["R"], np.nan)
        bv = np.where(oper, v["band"], "")
        m = compare(r0, b0, rv, bv)
        rows.append({"section": "ROBUSTNESS", "dimension": dim, "variant": name, **m,
                     "coverage_auc": auc(rv[oper & inside], rv[oper & ~inside]),
                     "family_share_corr": family_share_corr(core0, v["core"], oper),
                     "bands_status": v["ref"]["bands"]["status"], **month_high(bv, ix, oper), "result": verdict(m)})
        lg.info("%-26s %-45s rho %.3f band %.3f -> %s", dim, name, m["spearman"], m["band_agreement"], rows[-1]["result"])

    # ---------------------------------------------------------------- architecture candidates (pre-declared rule)
    cands = {"A_WEIGHTED_FAMILY_MEAN": variant(name="CAND_A", magnitude_mode="mean", w_magnitude=1.0, w_concurrence=0.0,
                                               w_persistence=0.0),
             "B_CONCORDANCE_ANY_FAMILY_PERSISTENCE": variant(name="CAND_B", magnitude_mode="mean",
                                                             persistence_mode="any_family"),
             "H_PRIMARY_HYBRID": PRIMARY}
    cand_rows = {}
    for name, cfg in cands.items():
        va = run_variant(grid, cfg, ctx, {})
        vr = run_variant(grid, replace(cfg, name=cfg.name + "_APR", ref_end="2025-04-30 23:59"), ctx, {})
        ra, rr = np.where(oper, va["R"], np.nan), np.where(oper, vr["R"], np.nan)
        ba, br = np.where(oper, va["band"], ""), np.where(oper, vr["band"], "")
        m = compare(ra, ba, rr, br)
        mh, mh_r = month_high(ba, ix, oper), month_high(br, ix, oper)
        loss = float(np.nanmax(np.abs(np.array(list(mh.values())) - np.array(list(mh_r.values())))))
        epi, single = episodes_per_100h(ba, oper)
        cand_rows[name] = {"section": "CANDIDATE", "dimension": "ARCHITECTURE", "variant": name,
                           "ref_window_spearman": m["spearman"], "ref_window_band_agreement": m["band_agreement"],
                           "month_high_share_max_change_under_ref_shift": loss, "episodes_per_100h_ge_high": epi,
                           "single_bucket_episodes": single, "coverage_auc": auc(ra[oper & inside], ra[oper & ~inside]),
                           "meets_requirements": name != "A_WEIGHTED_FAMILY_MEAN", "n": m["n"]}
    ce = np.where(oper, similarity(core0["af"], ref0["signatures"]) * 100, np.nan)
    cand_rows["C_HISTORICAL_SIMILARITY"] = {"section": "CANDIDATE", "dimension": "ARCHITECTURE",
                                            "variant": "C_HISTORICAL_SIMILARITY", "meets_requirements": False,
                                            "coverage_auc": auc(ce[oper & inside], ce[oper & ~inside]),
                                            "n": int(np.isfinite(ce).sum()),
                                            "note": "descriptive only: frozen Apr-May signatures (Sp.Heat-dominant) vs "
                                                    "combustion / draft-dominant Jun-Aug periods; expanding library "
                                                    "not causal (in_final_set uses full-period sensitivity)"}
    h, b = cand_rows["H_PRIMARY_HYBRID"], cand_rows["B_CONCORDANCE_ANY_FAMILY_PERSISTENCE"]
    smin = MATERIALITY["spearman_min"]
    h_worse = ((h["ref_window_spearman"] < smin <= b["ref_window_spearman"])
               or (h["month_high_share_max_change_under_ref_shift"] - b["month_high_share_max_change_under_ref_shift"]
                   > INCLUSION_MAX_MONTH_CHANGE))
    chosen = "B_CONCORDANCE_ANY_FAMILY_PERSISTENCE" if h_worse else "H_PRIMARY_HYBRID"
    for k, r in cand_rows.items():
        r["result"] = "SELECTED" if k == chosen else ("NOT_SELECTED" if r["meets_requirements"] else
                                                      "FAILS_REQUIREMENTS" if k.startswith("A_") else "DESCRIPTIVE_ONLY")
        rows.append(r)

    # ---------------------------------------------------------------- consistency controls (NC1 / NC2 / NC5)
    so, io = r0[oper], inside[oper]
    null1 = circular_null(so, io, lambda x, m: auc(x[m], x[~m]), N_NULL, PRIMARY.seed, MIN_SHIFT_BUCKETS)
    p1 = p_upper(auc0, null1)
    rows.append({"section": "NEGATIVE_CONTROL", "dimension": "NC1_CIRCULAR_SHIFT", "variant": "score shifted >= 7 days",
                 "observed": auc0, "null_median": float(np.nanmedian(null1)),
                 "null_p95": float(np.nanquantile(null1, 0.95)), "p_value": p1, "n": N_NULL,
                 "result": "PASS" if p1 < 0.05 else "NOT_DISTINGUISHABLE_FROM_SHIFTED_NULL",
                 "note": f"CONSISTENCY control only (p <= {1 / (N_NULL + 1):.4f} is the floor for {N_NULL} draws): the "
                         "periods share the scored components, so passing is expected by construction"})
    fin = eps[eps.in_final_set]
    durs = [int(d // 10) for d in (fin.end_time - fin.start_time) / pd.Timedelta(minutes=1)]
    obs2 = float(np.nanmedian(so[io]))
    null2 = random_windows_null(so, durs, N_NULL, PRIMARY.seed + 1)
    p2 = p_upper(obs2, null2)
    rows.append({"section": "NEGATIVE_CONTROL", "dimension": "NC2_RANDOMISED_PERIOD_PLACEMENT",
                 "variant": "12 same-length windows placed at random in operational time", "observed": obs2,
                 "null_median": float(np.nanmedian(null2)), "null_p95": float(np.nanquantile(null2, 0.95)),
                 "p_value": p2, "n": N_NULL, "result": "PASS" if p2 < 0.05 else "NOT_DISTINGUISHABLE_FROM_RANDOM_PLACEMENT",
                 "note": "CONSISTENCY control only (randomised labels); expected to pass by construction"})
    refw = [r for r in rows if r.get("dimension") == "REFERENCE_WINDOW"]
    rows.append({"section": "NEGATIVE_CONTROL", "dimension": "NC5_REFERENCE_WINDOW_PERTURBATION",
                 "variant": "; ".join(r["variant"] for r in refw),
                 "observed": float(np.nanmin([r["spearman"] for r in refw])), "n": len(refw),
                 "result": "STABLE" if all(r["result"] == "STABLE" for r in refw) else "SENSITIVE",
                 "note": "minimum Spearman vs primary; levels / band shares under each window are in ROBUSTNESS rows"})

    # ---------------------------------------------------------------- AFR / Phase 4 inclusion tests
    for dim, name, key, wfield in (("AFR_INCLUSION", "AFR_DOWN_TRANSITION_10PCT", "x_afr", "afr_weight"),
                                   ("PHASE4_INCLUSION", "PHASE4_INDICATOR_10PCT", "x_p4", "p4_weight")):
        v, cfg = results[name]
        w = getattr(cfg, wfield)
        x = v["core"][key]
        base = (1 - w) * r0
        y = base + 100 * w * x
        gain = auc(y[oper & inside], y[oper & ~inside]) - auc0
        bo = base[oper]
        null = circular_null(x[oper], io, lambda xs, m: auc((bo + 100 * w * xs)[m], (bo + 100 * w * xs)[~m]) - auc0,
                             N_NULL, PRIMARY.seed + 7, MIN_SHIFT_BUCKETS)
        p95 = float(np.nanquantile(null, 0.95))
        mh_v = month_high(np.where(oper, v["band"], ""), ix, oper)
        stab_ok = max(abs(mh_v[k] - base_mh[k]) for k in base_mh) <= INCLUSION_MAX_MONTH_CHANGE
        include = bool(gain >= INCLUSION_MIN_GAIN and gain > p95 and stab_ok)
        rows.append({"section": "INCLUSION_TEST", "dimension": dim, "variant": name, "observed": gain,
                     "null_median": float(np.nanmedian(null)), "null_p95": p95, "p_value": p_upper(gain, null),
                     "stability_kept": stab_ok, "n": N_NULL,
                     "result": "INCLUDE (tentative)" if include else "EXCLUDE_CONTEXT_ONLY",
                     "note": f"coverage-AUC gain {gain:+.4f} on CIRCULAR coverage (test biased toward exclusion); rule: "
                             f"gain >= {INCLUSION_MIN_GAIN} AND > shifted-null P95 AND month HIGH-share change <= "
                             f"{INCLUSION_MAX_MONTH_CHANGE}"})
    write_csv(pd.DataFrame(rows), "risk_score_robustness.csv", lg)
    lg.info("candidate selected: %s; NC1 p %.3f; NC2 p %.3f", chosen, p1, p2)


if __name__ == "__main__":
    main()
