"""Step 3 - KPI candidate selection (training window only).

Reads  cache/minute_*.parquet, Phase 2 tag_contract / baseline_confidence / column_holds
Writes cache/buckets_primary_*.parquet (10-min buckets, causal masks + causal state)
       outputs/kpi_candidate_inventory.csv   every one of the 203 Phase 1/2 tags + derived KPI inputs
       outputs/kpi_excluded_candidates.csv   the excluded subset with reasons

Inclusion rules, applied in this order (first failing rule is the exclusion_reason):
  R1 Phase 2 column hold (unit review, sparse, constant, sentinel, duplicate, state indicator) -> HELD
  R2 Phase 2 BASELINE_RUNNING confidence INSUFFICIENT -> INSUFFICIENT BASELINE
  R3 tag not mapped to a KPI dimension -> explicit reason (EXPLICIT_EXCLUSIONS) or family-scope reason
  R4 training window: >= min_train_buckets valid running buckets and >= min_train_coverage of training running buckets
  R5 training window: robust scale > 0 (defined deviation scale)
  R6 within a dimension, training Spearman |rho| >= redundancy_rho with a higher-priority kept tag -> REDUNDANT
     (priority: Phase 2 confidence HIGH > MEDIUM > LOW, then specification order)
Phase 2 confidence C6 (drift) is NOT an exclusion reason: a drifting tag is exactly what a deterioration KPI must
see once the reference is refitted on the training window. LOW confidence tags stay in and are flagged; the
'drop LOW' sensitivity removes them. FUEL is evaluated but kept out of the primary KPI (see FUEL_NOTE).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p3common import (CONTEXT_TAGS, EXPLICIT_EXCLUSIONS, FAMILY_EXCLUSIONS, PRIMARY, TAG_SPECS, load_minutes, log,
                      read_p2, save_buckets, write_csv)
from kpi_core import minutes_to_buckets, robust_scale, training_mask, value_resolution

lg = log("select_kpi_candidates")
FUEL_NOTE = ("SENSITIVITY ONLY: coal firing per load duplicates the fuel-energy information already in Sp.Heat "
             "(training-window Spearman rho(coal, Sp.Heat F) = {rho:.2f} on 10-min buckets), and AFR substitution / fuel CV "
             "are unknown (ALTERNATIVE FUEL INSUFFICIENT), so a coal-rate deviation cannot be read as an efficiency change")
CONF_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INSUFFICIENT": 3}


def main():
    values, state = load_minutes()
    b = minutes_to_buckets(values, state, PRIMARY)
    save_buckets(b, "primary")
    tm = training_mask(b["meta"], PRIMARY)
    n_tr = int(tm.sum())
    lg.info("training running buckets: %d", n_tr)
    tc = read_p2("tag_contract.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column)
    conf = read_p2("baseline_confidence.csv").query("population == 'BASELINE_RUNNING'")
    conf = conf.assign(tag=conf.dataset + "!" + conf.tag).set_index("tag")
    holds = read_p2("column_holds.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column)
    hold_by = holds.groupby("tag").hold.apply(lambda s: "|".join(sorted(set(s))))
    spec = {s.tag: s for s in TAG_SPECS}

    def base_row(t: str) -> dict:
        r = tc[tc.tag == t].iloc[0] if (tc.tag == t).any() else None
        return {"tag": t, "dataset": t.split("!")[0] if "!" in t else "DERIVED",
                "source_column": t.split("!")[1] if "!" in t else "",
                "original_name": r.original_name if r is not None else "", "unit": r.detected_unit if r is not None else "",
                "family": r.likely_process_family if r is not None else "",
                "baseline_confidence": conf.baseline_confidence.get(t, ""),
                "p2_criteria_failed": conf.criteria_failed.get(t, ""),
                "quality_class": (f"{r.completeness_class} / {r.health_class}" if r is not None else "")}

    rows = []
    for t in tc.tag:
        row = base_row(t)
        if t in hold_by:
            row.update(status="EXCLUDED", exclusion_reason=f"R1 HELD: {hold_by[t]}")
        elif row["baseline_confidence"] == "INSUFFICIENT":
            row.update(status="EXCLUDED", exclusion_reason="R2 INSUFFICIENT BASELINE (Phase 2)")
        elif t in spec:
            row.update(status="CANDIDATE")
        elif t in CONTEXT_TAGS:
            row.update(status="CONTEXT_ONLY", exclusion_reason="R3 " + EXPLICIT_EXCLUSIONS.get(t, CONTEXT_TAGS[t]))
        elif t in EXPLICIT_EXCLUSIONS:
            row.update(status="EXCLUDED", exclusion_reason="R3 " + EXPLICIT_EXCLUSIONS[t])
        else:
            row.update(status="EXCLUDED", exclusion_reason="R3 " + FAMILY_EXCLUSIONS.get(row["family"], "OUT OF SCOPE"))
        rows.append(row)
    for s in TAG_SPECS:                                   # derived KPI inputs
        if s.tag.startswith(("STD60:", "DERIVED:")):
            src = [base_row(x) for x in s.derived_from]
            confs = [x["baseline_confidence"] for x in src]
            row = {"tag": s.tag, "dataset": "DERIVED", "source_column": "+".join(x["tag"] for x in src),
                   "original_name": " + ".join(x["original_name"] for x in src) if s.tag.startswith("DERIVED:")
                   else f"rolling 60-min std of {src[0]['original_name']}",
                   "unit": src[0]["unit"], "family": src[0]["family"],
                   "baseline_confidence": max(confs, key=lambda c: CONF_RANK.get(c, 3)),
                   "p2_criteria_failed": "", "quality_class": "derived", "status": "CANDIDATE"}
            rows.append(row)
    inv = pd.DataFrame(rows)
    # R4-R5 on the training window
    for i, r in inv[inv.status == "CANDIDATE"].iterrows():
        s = spec[r.tag]
        src = b["std60"] if r.tag.startswith("STD60:") else b["values"]
        x = src[r.tag][tm] if r.tag in src else pd.Series(dtype=float)
        n = int(x.notna().sum())
        sc = robust_scale(x.to_numpy(float), value_resolution(x.to_numpy(float)), 0.0) if n else np.nan
        inv.loc[i, ["dimension", "direction", "load_adjusted", "rationale"]] = [s.dimension, s.direction, s.load_adjusted, s.rationale]
        inv.loc[i, ["train_valid_buckets", "train_coverage", "train_median", "train_robust_scale"]] = [
            n, n / max(n_tr, 1), float(x.median()) if n else np.nan, sc]
        if n < PRIMARY.min_train_buckets or n / max(n_tr, 1) < PRIMARY.min_train_coverage:
            inv.loc[i, ["status", "exclusion_reason"]] = ["EXCLUDED", f"R4 TRAINING COVERAGE: {n} valid buckets ({n / max(n_tr, 1):.0%})"]
        elif not np.isfinite(sc) or sc <= 0:
            inv.loc[i, ["status", "exclusion_reason"]] = ["EXCLUDED", "R5 ZERO SCALE IN TRAINING WINDOW"]
    # R6 redundancy within dimension (training Spearman)
    cand = inv[inv.status == "CANDIDATE"].copy()
    cand["prio"] = cand.baseline_confidence.map(CONF_RANK).fillna(3)
    cand["order"] = cand.tag.map({s.tag: k for k, s in enumerate(TAG_SPECS)})
    for dim, g in cand.groupby("dimension"):
        g = g.sort_values(["prio", "order"])
        src = {t: (b["std60"] if t.startswith("STD60:") else b["values"])[t][tm] for t in g.tag}
        rho = pd.DataFrame(src).corr(method="spearman")
        kept = []
        for t in g.tag:
            hit = [(k, rho.loc[t, k]) for k in kept if abs(rho.loc[t, k]) >= PRIMARY.redundancy_rho]
            if hit:
                k, rr = hit[0]
                j = inv.index[inv.tag == t][0]
                inv.loc[j, ["status", "exclusion_reason"]] = ["EXCLUDED", f"R6 REDUNDANT IN TRAINING: rho={rr:.3f} with {k}"]
            else:
                kept.append(t)
    fuel = inv.dimension.eq("FUEL") & inv.status.eq("CANDIDATE")
    rho = b["values"].loc[tm, ["DERIVED:COAL_TOTAL", "Kiln-I!F"]].corr(method="spearman").iloc[0, 1]
    inv.loc[fuel, ["status", "exclusion_reason"]] = ["SENSITIVITY_ONLY", FUEL_NOTE.format(rho=rho)]
    inv.loc[inv.status == "CANDIDATE", "status"] = "INCLUDED"
    inv["included"] = inv.status.eq("INCLUDED")
    inv["low_confidence_flag"] = inv.included & inv.baseline_confidence.eq("LOW")
    inv["exclusion_reason"] = inv.exclusion_reason.fillna("")
    inv = inv.sort_values(["included", "dimension", "tag"], ascending=[False, True, True], na_position="last")
    cols = ["tag", "original_name", "family", "unit", "baseline_confidence", "quality_class", "included",
            "exclusion_reason", "status", "dataset", "source_column", "dimension", "direction", "load_adjusted",
            "low_confidence_flag", "p2_criteria_failed", "train_valid_buckets", "train_coverage", "train_median",
            "train_robust_scale", "rationale"]
    inv = inv[cols]
    write_csv(inv, "kpi_candidate_inventory.csv", lg)
    write_csv(inv[~inv.included], "kpi_excluded_candidates.csv", lg)
    lg.info("status: %s", inv.status.value_counts().to_dict())
    lg.info("included by dimension: %s", inv[inv.included].dimension.value_counts().to_dict())


if __name__ == "__main__":
    main()
