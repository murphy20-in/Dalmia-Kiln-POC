"""Step 8 - machine-readable baseline reference, confidence and family readiness.

Reference bands (POC BASELINE REFERENCE BAND — NOT AN ENGINEERING / ALARM / CONTROL LIMIT):
  lower_reference / upper_reference = empirical P05 / P95 of the baseline population
  robust_lower / robust_upper       = median -/+ band_mad_k * scaled MAD (NaN when MAD = 0)
Computed for BASELINE_RUNNING (primary), the TENTATIVE feed bands and BASELINE_UNBANDED.
Every row carries fit_window: bands are fitted on the full supplied period and must be refit
on a training window before any later phase uses them to score a period.

Baseline confidence - evaluated PER POPULATION from the INCLUDED values of that population
(POC ANALYTICAL HEURISTICS, documented):
  C1 volume        n >= 43,200 (30 days of 1-minute values)
  C2 coverage      >= 60 valid days (>= 60 minutes) and >= 4 months with >= 1,440 values
  C3 completeness  tag-level INCLUDED / eligible running minutes >= 90 %
  C4 continuity    < 20 % of population values inside single-tag flatlines and top value share < 95 %
  C5 contamination < 2 % of population values outside the IQR-3.0 fences of the population
  C6 drift         >= 2 evaluable months (>= 30 prior days) and every evaluable month within
                   1 floored prior scale of the prior median (prior-only comparison)
  C7 dispersion    scaled MAD > 0
  C8 semantics     Phase 1 classification confidence HIGH/MEDIUM and no unit review flag
  INSUFFICIENT  column held, or n < 1,440, or < 7 valid days
  HIGH          all criteria pass
  LOW           C5, C6 or C7 fails (non-stationary, contaminated or degenerate), or >= 3 fail
  MEDIUM        otherwise (<= 2 of C1, C2, C3, C4, C8 fail)
  Tentative feed-band populations are capped at MEDIUM.
  Every confidence is CONDITIONAL on the unconfirmed operating-state proxy and describes
  EVIDENCE for the baseline - it is not a statement about equipment health.
Family readiness (BASELINE_RUNNING): READY if >= 50 % of family tags HIGH and >= 75 % HIGH/MEDIUM;
  PARTIAL if >= 1 tag HIGH/MEDIUM; INSUFFICIENT otherwise.
Outputs: outputs/baseline_reference_bands.csv, outputs/baseline_confidence.csv,
         outputs/baseline_family_readiness.csv, outputs/baseline_current_reference.csv,
         reports/figures/distributions_key_tags.png
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p2common import (FIG, H, BAND_LABEL, PROXY_LABEL, KEY_TAGS, MAD_SCALE, datasets, load_processed, curated_path,
                      read_out, write_csv, log, prior_compare, value_resolution)

lg = log("build_baseline_reference")


NON_NEGATIVE_UNITS = {"a", "amps", "ma", "kv", "kw", "rpm", "tph", "lph", "m3/m", "m3/hr", "nm3/min", "kg/h", "ton", "tons", "ppm",
                      "kwh/t", "kw/ton", "kcal/kg", "kcla/kgclnkr"}


def band_caution(r) -> str:
    """Flags band values an operator could misread; they are data observations requiring plant review."""
    u = str(r.unit).strip().lower()
    notes = []
    if u in NON_NEGATIVE_UNITS and r.p05 < 0:
        notes.append(f"P05 is negative ({r.p05:.4g}) in a unit that is normally non-negative - possible offset/sensor artefact")
    if u == "%" and r.p95 >= 20.0 and "o2" in str(r.original_name).lower():
        notes.append("O2 P95 >= 20 % approaches atmospheric concentration - possible sampling/sensor condition; requires plant review")
    if r.scaled_mad == 0:
        notes.append("scaled MAD = 0 (value mostly constant) - band not informative")
    if u == "%" and (r.p05 < 0 or r.p95 > 100):
        notes.append("percent band outside 0-100")
    return "; ".join(notes)


def eligible_running(eq: str) -> pd.Series:
    d = load_processed(eq, ["source_column", "operating_state", "baseline_status", "mask_reason", "dup_status"])
    run = (d.operating_state == "RUNNING_PROXY") & ~d.mask_reason.astype(str).str.contains("RESOLUTION_HOURLY") \
        & ~d.dup_status.isin(["DUP_IDENTICAL_COPY"])
    g = d[run].groupby("source_column", observed=True)
    return (g.baseline_status.apply(lambda s: (s == "INCLUDED").mean()))


def population_evidence(v: np.ndarray, ts: np.ndarray, flat: np.ndarray) -> dict:
    """Evidence for one population, computed on its own INCLUDED values only."""
    days = pd.Series(1, index=pd.to_datetime(ts)).groupby(pd.to_datetime(ts).floor("D")).size()
    mon = pd.Series(1, index=pd.to_datetime(ts)).groupby(pd.to_datetime(ts).to_period("M")).size()
    q1, q3 = np.quantile(v, [0.25, 0.75])
    iqr = q3 - q1
    out3 = float(((v < q1 - 3 * iqr) | (v > q3 + 3 * iqr)).mean() * 100) if iqr > 0 else 0.0
    top = float(pd.Series(v).value_counts(normalize=True).iloc[0])
    med = float(np.median(v))
    smad = float(MAD_SCALE * np.median(np.abs(v - med)))
    res = value_resolution(v)
    order = np.argsort(ts, kind="stable")
    vs, tss = v[order], ts[order]
    shifts, evaluable = [], 0
    for per in pd.PeriodIndex(pd.to_datetime(tss), freq="M").unique():
        m = (tss >= np.datetime64(per.start_time)) & (tss <= np.datetime64(per.end_time))
        if m.sum() < 1440:
            continue
        pv = vs[m]
        pq = np.quantile(pv, [0.25, 0.75])
        r = prior_compare(vs, tss, per.start_time, float(np.median(pv)), float(pq[1] - pq[0]), res)
        if "shift_in_prior_scaled_mad" in r and np.isfinite(r["shift_in_prior_scaled_mad"]):
            evaluable += 1
            shifts.append(abs(r["shift_in_prior_scaled_mad"]))
    return {"n": int(v.size), "valid_days": int((days >= 60).sum()), "months": int((mon >= 1440).sum()),
            "flatline_share_pct": float(flat.mean() * 100), "top_value_share": top, "iqr3_outside_pct": out3,
            "scaled_mad": smad, "evaluable_months": evaluable, "max_monthly_shift": max(shifts) if shifts else np.nan}


def grade(e: dict, compl: float, c, tentative: bool) -> tuple[str, dict, list]:
    crit = {
        "C1_volume": e["n"] >= 43200,
        "C2_coverage": e["valid_days"] >= 60 and e["months"] >= 4,
        "C3_completeness": compl >= 0.90,
        "C4_continuity": e["flatline_share_pct"] < 20 and e["top_value_share"] < 0.95,
        "C5_contamination": e["iqr3_outside_pct"] < 2.0,
        "C6_drift": e["evaluable_months"] >= 2 and e["max_monthly_shift"] < H["drift_mad_units"],
        "C7_dispersion": e["scaled_mad"] > 0,
        "C8_semantics": c.confidence in ("HIGH", "MEDIUM") and not bool(c.unit_label_review_required),
    }
    fails = [k for k, v in crit.items() if not v]
    if e["n"] < 1440 or e["valid_days"] < 7:
        lvl = "INSUFFICIENT"
    elif not fails:
        lvl = "HIGH"
    elif set(fails) & {"C5_contamination", "C6_drift", "C7_dispersion"} or len(fails) >= 3:
        lvl = "LOW"
    else:
        lvl = "MEDIUM"
    if tentative and lvl == "HIGH":
        lvl = "MEDIUM"
    return lvl, crit, fails


def main():
    st = read_out("baseline_statistics.csv")
    pop = read_out("baseline_population.csv").set_index(["dataset", "tag"])
    stab = read_out("baseline_stability.csv").set_index(["dataset", "tag"])
    contract = read_out("tag_contract.csv").set_index(["dataset", "source_column"])
    rg = read_out("operating_regimes.csv")
    tentative = not (rg.query("test == 'REGIME_STATUS'").value.iloc[0] == 1.0)
    compl = {eq: eligible_running(eq) for eq in datasets()}

    conf = []
    for eq in datasets():
        cur = pd.read_parquet(curated_path(eq), columns=["ts", "source_column", "value", "load_regime", "tag_flatline", "state_basis"])
        for (dset, tag), p in pop.loc[[eq]].iterrows() if eq in pop.index.get_level_values(0) else []:
            c = contract.loc[(eq, tag)]
            base = {"dataset": eq, "tag": tag, "original_name": p.original_name, "normalized_name": p.normalized_name,
                    "process_family": p.process_family, "unit": p.unit,
                    "column_hold": p.column_hold if isinstance(p.column_hold, str) else ""}
            g = cur[cur.source_column == tag]
            if base["column_hold"] or g.empty:
                conf.append({**base, "population": "BASELINE_RUNNING", "baseline_confidence": "INSUFFICIENT",
                             "reason": f"column held: {base['column_hold']}" if base["column_hold"] else "no baseline values",
                             "condition": "conditional on POC PROXY — UNCONFIRMED operating state"})
                continue
            pops = {"BASELINE_RUNNING": g}
            for b_, gb in g.groupby("load_regime", observed=True):
                pops[f"BASELINE_{b_}"] = gb
            pops["BASELINE_UNBANDED"] = g[g.load_regime.isna()]
            for pname, gp in pops.items():
                if gp.empty:
                    continue
                e = population_evidence(gp.value.to_numpy(dtype=float), gp.ts.to_numpy(), gp.tag_flatline.to_numpy(dtype=bool))
                cp = float(compl[eq].get(tag, np.nan))
                lvl, crit, fails = grade(e, cp, c, tentative and pname.startswith("BASELINE_FEED_BAND"))
                conf.append({**base, "population": pname, **e, "running_completeness": round(cp, 4),
                             "pct_with_kiln_i_feed_state_evidence": round(float((gp.state_basis.astype(str) == "KILN_MD + KILN_I_FEED/SPEED").mean() * 100), 2),
                             **{k: bool(v) for k, v in crit.items()}, "criteria_failed": json.dumps(fails),
                             "baseline_confidence": lvl, "reason": "all criteria pass" if not fails else "failed " + ", ".join(fails),
                             "condition": "conditional on POC PROXY — UNCONFIRMED operating state; describes baseline evidence, not equipment health"})
    conf = pd.DataFrame(conf)

    bands = []
    cidx = conf.set_index(["dataset", "tag", "population"]).baseline_confidence
    for r in st[st.population != "REFERENCE_ALL_VALID"].itertuples():
        k = (r.dataset, r.tag)
        c = contract.loc[k]
        p = pop.loc[k]
        s = stab.loc[k] if k in stab.index else None
        robust_ok = r.scaled_mad > 0
        bands.append({
            "tag": r.tag, "dataset": r.dataset, "equipment": r.dataset, "original_name": r.original_name,
            "normalized_name": r.normalized_name, "process_family": r.process_family, "unit": r.unit,
            "baseline_population": r.population,
            "population_status": ("TENTATIVE LOAD BAND" if r.population.startswith("BASELINE_FEED_BAND") and tentative else
                                  "PRIMARY" if r.population == "BASELINE_RUNNING" else "SECONDARY"),
            "band_coverage_of_running_pct": r.band_coverage_of_running_pct,
            "n_observations": int(r.count), "valid_observations": int(r.valid_count),
            "centre": r.median, "median": r.median, "mean": r.mean, "scale": r.scaled_mad, "scale_definition": "1.4826 x MAD",
            "mad": r.mad, "p05": r.p05, "p25": r.p25, "p75": r.p75, "p95": r.p95,
            "lower_reference": r.p05, "upper_reference": r.p95,
            "robust_lower": r.median - H["band_mad_k"] * r.scaled_mad if robust_ok else np.nan,
            "robust_upper": r.median + H["band_mad_k"] * r.scaled_mad if robust_ok else np.nan,
            "stability_metric": s.stability_ratio if s is not None else np.nan,
            "stability_class": s.stability_class if s is not None else "",
            "data_quality_class": c.completeness_class, "outlier_sensitivity": r.outlier_sensitivity,
            "baseline_confidence": cidx.get((r.dataset, r.tag, r.population), ""),
            "first_ts": r.first_ts, "last_ts": r.last_ts, "fit_window": r.fit_window,
            "source_files": r.source_files, "source_sheet": p.source_sheet,
            "exclusion_notes": f"masked {p.masked}, excluded_state {p.excluded_state}, excluded_resolution {p.excluded_resolution} of {p.cells_total} cells",
            "band_label": BAND_LABEL, "state_basis": PROXY_LABEL,
            "band_caution": band_caution(r),
        })
    bands = pd.DataFrame(bands)
    write_csv(bands, "baseline_reference_bands.csv", lg)
    write_csv(conf, "baseline_confidence.csv", lg)
    conf = conf[conf.population == "BASELINE_RUNNING"]

    fr = []
    for fam, g in conf.groupby("process_family"):
        n = len(g); hi = (g.baseline_confidence == "HIGH").sum(); hm = g.baseline_confidence.isin(["HIGH", "MEDIUM"]).sum()
        lvl = "READY" if hi / n >= 0.5 and hm / n >= 0.75 else "PARTIAL" if hm >= 1 else "INSUFFICIENT"
        fr.append({"process_family": fam, "tags": n, "HIGH": int(hi), "MEDIUM": int((g.baseline_confidence == "MEDIUM").sum()),
                   "LOW": int((g.baseline_confidence == "LOW").sum()), "INSUFFICIENT": int((g.baseline_confidence == "INSUFFICIENT").sum()),
                   "baseline_readiness": lvl, "datasets": json.dumps(sorted(g.dataset.unique())),
                   "rule": "READY: >=50% HIGH and >=75% HIGH/MEDIUM; PARTIAL: >=1 HIGH/MEDIUM; else INSUFFICIENT",
                   "condition": "conditional on POC PROXY — UNCONFIRMED operating state"})
    write_csv(pd.DataFrame(fr), "baseline_family_readiness.csv", lg)
    current_reference(conf)
    plot(bands)


def current_reference(conf: pd.DataFrame):
    """Latest state vs baseline, per dataset 'as of' its own last INCLUDED minute.
    Window = last 7 days of INCLUDED values; reference = INCLUDED values strictly BEFORE the window
    (prior-only, so the latest data never shape their own reference). Descriptive only - not a health claim."""
    from p2common import curated_path, MAD_SCALE
    rows = []
    cmap = conf.set_index(["dataset", "tag"]).baseline_confidence
    for eq in datasets():
        c = pd.read_parquet(curated_path(eq), columns=["ts", "source_column", "original_name", "unit", "value"])
        if c.empty:
            continue
        as_of = c.ts.max()
        w0 = as_of - pd.Timedelta(days=7)
        for col, g in c.groupby("source_column", observed=True):
            win = g[g.ts > w0].value.to_numpy()
            ref = g[g.ts <= w0].value.to_numpy()
            if ref.size < 1440 or win.size == 0:
                continue
            rm = float(np.median(ref)); rs = float(MAD_SCALE * np.median(np.abs(ref - rm)))
            p05, p95 = np.quantile(ref, [0.05, 0.95])
            wm = float(np.median(win))
            rows.append({"dataset": eq, "tag": col, "original_name": g.original_name.iloc[0], "unit": g.unit.iloc[0],
                         "as_of": as_of, "window_start": w0, "window_minutes": int(win.size), "window_median": wm,
                         "reference_median": rm, "reference_p05": float(p05), "reference_p95": float(p95),
                         "shift_in_reference_scaled_mad": (wm - rm) / rs if rs else np.nan,
                         "window_median_inside_reference_p05_p95": bool(p05 <= wm <= p95),
                         "baseline_confidence": cmap.get((eq, col), ""),
                         "note": "descriptive comparison of the latest 7 days with the prior baseline; NOT a health or limit assessment"})
    write_csv(pd.DataFrame(rows), "baseline_current_reference.csv", lg)


def plot(bands):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(KEY_TAGS)
    fig, axes = plt.subplots(n, 2, figsize=(12, 1.9 * n))
    for i, (eq, col) in enumerate(KEY_TAGS):
        d = load_processed(eq, ["source_column", "value", "baseline_status", "value_valid"])
        d = d[d.source_column == col]
        inc = d.value[d.baseline_status == "INCLUDED"].dropna().to_numpy()
        allv = d.value[d.value_valid].dropna().to_numpy()
        b = bands[(bands.dataset == eq) & (bands.tag == col) & (bands.baseline_population == "BASELINE_RUNNING")]
        if b.empty or inc.size == 0:
            continue
        b = b.iloc[0]
        lo, hi = np.quantile(allv, [0.001, 0.999])
        ax = axes[i, 0]
        ax.hist(allv, bins=100, range=(lo, hi), color="#d9d9d9", label="all valid values")
        ax.hist(inc, bins=100, range=(lo, hi), color="#4292c6", alpha=0.8, label="baseline (INCLUDED)")
        ax.axvspan(b.lower_reference, b.upper_reference, color="#fdae6b", alpha=0.25, label="P05–P95 reference band")
        ax.axvline(b["median"], color="k", lw=0.8)
        ax.set_ylabel(f"{eq}!{col}\n{b.original_name[:22]}\n[{b.unit}]", fontsize=7); ax.tick_params(labelsize=6)
        ax2 = axes[i, 1]
        for arr, lab, colr in ((allv, "all valid", "#969696"), (inc, "baseline", "#08519c")):
            s = np.sort(arr); ax2.plot(s, np.arange(1, s.size + 1) / s.size, lw=0.9, color=colr, label=lab)
        ax2.set_xlim(lo, hi); ax2.tick_params(labelsize=6)
    axes[0, 0].legend(fontsize=6); axes[0, 1].legend(fontsize=6)
    axes[0, 0].set_title("Histogram (all valid vs baseline)", fontsize=9); axes[0, 1].set_title("ECDF", fontsize=9)
    fig.suptitle("Key-tag distributions — reference bands are POC baseline references, NOT limits", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.985]); fig.savefig(FIG / "distributions_key_tags.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
