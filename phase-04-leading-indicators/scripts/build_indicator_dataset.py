"""Step 2 - Candidate inventory, exclusions, causal minute cache, operating state and RUNNING 10-min buckets.

Reads  data/processed/<dataset>.parquet (all 10 datasets, read-only, via Phase 3's load_dataset),
       data/processed/operating_state_timeline.parquet, Phase 3 kpi_candidate_inventory.csv,
       Phase 2 column_holds.csv / baseline_confidence.csv / baseline_stability.csv,
       Phase 1 cross_dataset_identical_signals.csv
Writes cache/minute_<dataset>.parquet   wide 1-min values, held columns dropped, Phase 2 causal tokens -> NaN
       cache/minute_state_inputs.parquet  state_basic + Phase 2 operating_state per minute (Phase 3 index)
       cache/buckets_values.parquet, cache/buckets_meta.parquet, cache/buckets_minute_state.parquet
       outputs/indicator_candidate_inventory.csv  every source tag + Phase 3 KPI-output rows, status and reason
       outputs/indicator_excluded_candidates.csv  the excluded rows only
       outputs/indicator_data_quality.csv         per-tag quality accounting (discovery and per evaluation month)

Candidate rules (C1-C8) are evaluated on the DISCOVERY window only (2025-04-01 .. 2025-05-31), except the Phase 2
column holds, which are fixed metadata (label / unit / semantics) and are applied as design constants.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p4common import (ALL_DATASETS, CACHE, FEED_TAG, P3_OUT, MONTHS, PRIMARY, STATE_DATASETS, log, month_of, read_p1, read_p2,
                      read_p3, write_csv)
import indicator_core as ic
import kpi_core
from load_phase2_inputs import load_dataset          # Phase 3, pure read of data/processed
from p3common import PROCESSED

lg = log("build_indicator_dataset")

CONTEXT_ONLY = {FEED_TAG: "CONTEXT CONFOUNDER: kiln feed is the load covariate (analysed, never eligible)",
                "Kiln-IIIA!M": "CONTEXT CONFOUNDER: clinker production rate tracks load (analysed, never eligible)",
                "Kiln-I!N": "CONTEXT CONFOUNDER: bucket-elevator current tracks feed (analysed, never eligible)"}
RESERVED = {"Kiln-I!K": "RESERVED FOR PHASE 5: AFR solid rate; ALTERNATIVE FUEL family INSUFFICIENT (no CV, moisture, "
                        "RDF split) - not analysed as a Phase 4 indicator",
            "Kiln-I!L": "RESERVED FOR PHASE 5: AFR liquid"}


def process_family(fam: str, unit: str, name: str, dataset: str) -> str:
    """Phase 4 indicator taxonomy (spec section 12) from the Phase 1/2 family, unit and label. Category membership is
    descriptive only - it implies no physical causality."""
    u, n = str(unit).lower(), str(name).lower()
    if dataset.startswith("CBS"):
        return "BYPASS_AUXILIARY"
    if fam == "COMBUSTION":
        return "COMBUSTION"
    if fam in ("FUEL", "ALTERNATIVE FUEL"):
        return "FUEL"
    if fam == "PRODUCTION":
        return "PROCESS_LOAD"
    if fam == "EFFICIENCY":
        return "EFFICIENCY" if "heat" in n else "ELECTRICAL"
    if fam == "COOLER":
        return "COOLER_PROCESS"
    if fam == "KILN" and any(w in n for w in ("drive", "kw", "current")) or u in ("rpm",) and fam == "KILN":
        return "KILN_DRIVE"
    if "deg" in u:
        return "THERMAL"
    if u in ("mmwc", "mbar"):
        return "DRAFT_PRESSURE"
    if fam == "DRAFT / ID FAN":
        return "DRAFT_PRESSURE"
    return "OTHER_AUXILIARY"


def manipulated(tag: str, name: str, unit: str) -> bool:
    """Operator / controller-manipulated variables (a lead may reflect a control action, not a process state)."""
    n, u = str(name).lower(), str(unit).lower()
    if tag in ("Kiln-I!H", "Kiln-I!I"):          # coal firing rates are set by the operator / controller
        return True
    return u == "rpm" or any(w in n for w in ("speed", "damper", "throttle", "valve", "position", "pos", "spray"))


def main():
    cfg = PRIMARY
    inv3 = read_p3("kpi_candidate_inventory.csv")
    holds = read_p2("column_holds.csv").assign(tag=lambda h: h.dataset + "!" + h.source_column)
    held = holds.groupby("tag").hold.apply(lambda s: "|".join(sorted(set(s)))).to_dict()
    conf = read_p2("baseline_confidence.csv")
    conf = conf[conf.population == "BASELINE_RUNNING"].set_index("tag")
    stab = read_p2("baseline_stability.csv").set_index("tag")
    ident = read_p1("cross_dataset_identical_signals.csv")
    duplicates = {}                      # Phase 1 identical rate >= 0.99: the second-listed copy is excluded
    for r in ident[ident.identical_value_rate >= 0.99].itertuples():
        duplicates[f"{r.dataset_b}!{r.column_b}"] = (f"DUPLICATE: identical to {r.dataset_a}!{r.column_a} "
                                                     f"(Phase 1 identical rate {r.identical_value_rate:.4f})")

    # ---------------------------------------------------------------- minute cache (same construction as Phase 3)
    st = pd.read_parquet(PROCESSED / "operating_state_timeline.parquet", columns=["ts", "state_basic", "operating_state"])
    st = st.set_index("ts").sort_index()
    raw, lmeta = {}, []
    for ds in ALL_DATASETS:
        w, m = load_dataset(ds)
        raw[ds] = w.drop(columns=[c for c in w.columns if c in held])
        lmeta.append(m)
        lg.info("%s: %d minutes x %d tags (%d held dropped)", ds, len(w), raw[ds].shape[1], w.shape[1] - raw[ds].shape[1])
    idx = st.index
    for ds in STATE_DATASETS:                   # Phase 3 minute index: state timeline U the 4 KPI datasets
        idx = idx.union(raw[ds].index)
    state = st.reindex(idx)
    state["state_basic"] = state.state_basic.fillna("UNKNOWN")
    state["operating_state"] = state.operating_state.fillna("UNKNOWN")
    frames = {ds: raw[ds].reindex(idx) for ds in ALL_DATASETS}
    dropped = {ds: int((~raw[ds].index.isin(idx)).sum()) for ds in ALL_DATASETS}
    del raw
    for ds, f in frames.items():
        f.to_parquet(CACHE / f"minute_{ds.replace(' ', '_')}.parquet")
    state.to_parquet(CACHE / "minute_state_inputs.parquet")
    b = ic.build_buckets(frames, state, STATE_DATASETS, disc_end=cfg.disc_end)
    b["values"].to_parquet(CACHE / "buckets_values.parquet")
    b["meta"].to_parquet(CACHE / "buckets_meta.parquet")
    b["minute_state"].to_parquet(CACHE / "buckets_minute_state.parquet")
    lg.info("buckets %s; bucket states %s", b["values"].shape, b["meta"].bucket_state.value_counts().to_dict())

    # ---------------------------------------------------------------- discovery statistics for the candidate rules
    vals, meta = b["values"], b["meta"]
    train = kpi_core.training_mask(meta, ic.P3CFG)      # Phase 3 training population (discovery window)
    win = month_of(meta.index, cfg)
    running = meta.bucket_state.eq("RUNNING").to_numpy()
    tr = vals[train.to_numpy()]
    lm = pd.concat(lmeta, ignore_index=True).set_index("tag")
    dq = b["dq"].set_index("tag")
    kpi_inputs = set(inv3[inv3.included & ~inv3.tag.str.contains(":")].tag)
    kpi_inputs |= {s.split(":", 1)[1] for s in inv3[inv3.included & inv3.tag.str.startswith("STD60:")].tag}
    # dataset availability in discovery: calendar months in which the dataset has any valid bucket (Kiln-IIIA has no
    # April export) - coverage rule C7 is judged on the months the dataset actually exists
    tr_month = tr.index.month
    avail = {ds: np.isin(tr_month, np.unique(tr_month[tr[[c for c in tr.columns if c.startswith(ds + "!")]].notna().any(axis=1)]))
             for ds in ALL_DATASETS}
    rho_in = tr.rank().corr()                    # discovery Spearman between bucket series (tier / proxy rules)
    rows = []
    for r in inv3[~inv3.tag.str.contains(":")].itertuples():
        t = r.tag
        x = tr[t] if t in tr else pd.Series(dtype=float)
        xv = x.dropna().to_numpy()
        days = int((x.dropna().groupby(x.dropna().index.date).size() >= 6).sum()) if xv.size else 0
        mad = float(np.median(np.abs(xv - np.median(xv)))) if xv.size else np.nan
        iqr = float(np.subtract(*np.quantile(xv, [0.75, 0.25]))) if xv.size else np.nan
        dpres = dq.disc_present_minutes.get(t, 0)
        dflat = (dpres - dq.disc_valid_after_causal_masks.get(t, 0)) / dpres if dpres else np.nan
        row = {"indicator_tag": t, "original_name": r.original_name, "dataset": r.dataset, "source_column": r.source_column,
               "unit": r.unit, "p2_family": r.family, "process_family": process_family(r.family, r.unit, r.original_name, r.dataset),
               "p2_baseline_confidence": conf.baseline_confidence.get(t, "NOT_IN_P2"),
               "p2_stability_class": stab.stability_class.get(t, "") if "stability_class" in stab else "",
               "p2_column_hold": held.get(t, ""), "p3_status": r.status,
               "kpi_input": t in kpi_inputs,
               "disc_coverage": float(x.notna().mean()) if len(x) else 0.0,
               "disc_coverage_available_months": float(x[avail[r.dataset]].notna().mean()) if len(x) and avail[r.dataset].any() else 0.0,
               "disc_valid_days": days,
               "disc_distinct_values": int(np.unique(xv).size), "disc_mad": mad, "disc_iqr": iqr,
               "disc_causal_flatline_share": dflat,
               "manipulated_variable": manipulated(t, r.original_name, r.unit)}
        for mth in MONTHS:
            mm = (win == mth) & running
            row[f"coverage_{mth.lower()}"] = float(vals[t][mm].notna().mean()) if t in vals and mm.any() else 0.0
        # candidate rules C1-C8 (first failing rule is the reason; order is the priority)
        reason = ""
        if t in held:
            reason = f"C1 HELD (Phase 2 column hold): {held[t]}"
        elif row["p2_baseline_confidence"] == "INSUFFICIENT":
            reason = "C2 INSUFFICIENT Phase 2 baseline confidence"
        elif t in duplicates:
            reason = "C3 " + duplicates[t]
        elif str(r.unit).lower() == "hrs" or "run hrs" in str(r.original_name).lower():
            reason = "C4 CUMULATIVE RUN-HOUR COUNTER (not a process measurement)"
        elif t in RESERVED:
            reason = "C5 " + RESERVED[t]
        elif not xv.size or (mad == 0 and iqr == 0) or row["disc_distinct_values"] < 10:
            reason = "C6 UNDEFINED SCALE in discovery (MAD = IQR = 0 or < 10 distinct bucket values)"
        elif row["disc_coverage_available_months"] < cfg.disc_min_cov:
            reason = (f"C7 INSUFFICIENT DISCOVERY COVERAGE ({row['disc_coverage_available_months']:.2f} of RUNNING "
                      f"buckets in the dataset's available discovery months < {cfg.disc_min_cov})")
        elif days < cfg.disc_min_days:
            reason = f"C7 INSUFFICIENT DISCOVERY DAYS ({days} days with >= 1 h of valid buckets < {cfg.disc_min_days})"
        elif np.isfinite(dflat) and dflat > cfg.flatline_max_share:
            reason = f"C7 UNUSABLE FLATLINE ({dflat:.2f} of discovery minutes causally masked > {cfg.flatline_max_share})"
        if reason:
            status = "EXCLUDED"
        elif t in CONTEXT_ONLY:
            status, reason = "CONTEXT_ONLY", "C8 " + CONTEXT_ONLY[t]
        else:
            status = "CANDIDATE"
        row["status"], row["exclusion_reason"] = status, reason
        rows.append(row)
    inv = pd.DataFrame(rows)
    # tiers (eligible and context tags): KPI_INPUT / KPI_PROXY / EXTERNAL
    cand = inv[inv.status != "EXCLUDED"].indicator_tag.tolist()
    ins = [t for t in kpi_inputs if t in rho_in]
    tier, proxy_of, load_rho = {}, {}, {}
    for t in cand:
        load_rho[t] = float(rho_in.loc[t, FEED_TAG]) if FEED_TAG in rho_in and t != FEED_TAG else np.nan
        if t in kpi_inputs:
            tier[t] = "KPI_INPUT"
            continue
        c = rho_in.loc[t, ins].abs().drop(t, errors="ignore") if t in rho_in else pd.Series(dtype=float)
        if len(c) and c.max() >= cfg.proxy_rho:
            tier[t], proxy_of[t] = "KPI_PROXY", f"{c.idxmax()} (|rho| {c.max():.3f})"
        else:
            tier[t] = "EXTERNAL"
    inv["tier"] = inv.indicator_tag.map(tier).fillna("")
    inv["kpi_proxy_of"] = inv.indicator_tag.map(proxy_of).fillna("")
    inv["disc_rho_with_feed"] = inv.indicator_tag.map(load_rho)
    flags = []
    for r in inv.itertuples():
        f = []
        if r.manipulated_variable:
            f.append("MANIPULATED_VARIABLE")
        if r.dataset == "Kiln-IIIA":
            f.append("DISCOVERY_MAY_ONLY (Kiln-IIIA April missing)")
        if r.dataset == "CBS-II":
            f.append("CBS_II_HOURLY_2025-06-01..10")
        if np.isfinite(r.disc_rho_with_feed) and abs(r.disc_rho_with_feed) >= cfg.load_proxy_rho:
            f.append("LOAD_TRACKING (|rho| with feed >= 0.8 in discovery)")
        if r.p2_baseline_confidence == "LOW":
            f.append("P2_LOW_BASELINE_CONFIDENCE")
        for mth in MONTHS:
            if r.status != "EXCLUDED" and getattr(r, f"coverage_{mth.lower()}") < cfg.month_min_cov:
                f.append(f"NOT_EVALUABLE_{mth}")
        flags.append("|".join(f))
    inv["flags"] = flags
    # Phase 3 KPI outputs and derived constructs: never candidates (C5)
    extra = [{"indicator_tag": t, "original_name": "Phase 3 derived construct", "dataset": "Phase 3", "source_column": t,
              "unit": "", "status": "EXCLUDED",
              "exclusion_reason": "C5 KPI OUTPUT / DERIVED CONSTRUCT: Phase 3 KPI component (sources analysed directly)"}
             for t in inv3[inv3.tag.str.contains(":")].tag]
    k3 = pd.read_parquet(P3_OUT / "efficiency_deterioration_kpi.parquet").columns
    extra += [{"indicator_tag": f"P3:{c}", "original_name": "Phase 3 KPI output column", "dataset": "Phase 3",
               "source_column": c, "unit": "", "status": "EXCLUDED",
               "exclusion_reason": "C5 KPI OUTPUT: Phase 3 KPI output (target / control / benchmark only, never a predictor)"}
              for c in k3 if c != "timestamp"]
    inv = pd.concat([inv, pd.DataFrame(extra)], ignore_index=True)
    inv = inv.sort_values(["status", "dataset", "indicator_tag"], kind="mergesort").reset_index(drop=True)
    write_csv(inv, "indicator_candidate_inventory.csv", lg)
    write_csv(inv[inv.status == "EXCLUDED"][["indicator_tag", "original_name", "dataset", "unit", "exclusion_reason"]],
              "indicator_excluded_candidates.csv", lg)

    # ---------------------------------------------------------------- data-quality accounting
    q = dq.join(lm[["original_name", "unit", "minutes", "causal_invalid_minutes"]], how="left").reset_index()
    q["dataset"] = q.tag.str.split("!").str[0]
    q["minutes_dropped_outside_phase3_index"] = q.dataset.map(dropped)
    q["pct_causal_invalid"] = 100 * q.causal_invalid_minutes / q.minutes
    q["pct_flatline_or_frozen_masked"] = 100 * (q.present_minutes - q.valid_after_causal_masks) / q.present_minutes.replace(0, np.nan)
    q = q.merge(inv[["indicator_tag", "status", "tier", "disc_coverage", "coverage_jun", "coverage_jul", "coverage_aug",
                     "p2_baseline_confidence", "flags"]], left_on="tag", right_on="indicator_tag", how="left").drop(columns="indicator_tag")
    cmap = {"HIGH": 1.0, "MEDIUM": 0.75, "LOW": 0.5}
    oos_cov = q[["coverage_jun", "coverage_jul", "coverage_aug"]].mean(axis=1)
    q["data_quality_score"] = (oos_cov + (1 - q.pct_flatline_or_frozen_masked.fillna(100) / 100)
                               + q.p2_baseline_confidence.map(cmap).fillna(0.0)) / 3
    q = q.sort_values("tag", kind="mergesort")
    write_csv(q, "indicator_data_quality.csv", lg)
    lg.info("inventory: %s; tiers %s; Phase 3 causal-frozen minutes %d", inv.status.value_counts().to_dict(),
            inv.tier.value_counts().to_dict(), int(b["meta"].n_causal_frozen.sum()))


if __name__ == "__main__":
    main()
