"""Step 4 - Fit the PRIMARY reference on the training window and compute component scores.

Reads  cache/buckets_primary_*.parquet, outputs/kpi_candidate_inventory.csv
Writes outputs/kpi_reference.json          frozen reference (tag expected-value curves and scales, dimension
                                           standardisers, persistence scale anchors, secondary MCD) - training only
       outputs/kpi_component_scores.parquet long format: one row per (bucket, included tag) with the bucket value,
                                           load-conditional expected value, scale, z and tag score (traceability)
       cache/scored_primary.parquet        bucket-level scored frame for the next steps
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from p3common import CACHE, FEED_TAG, KPI_VERSION, OUT, PRIMARY, load_buckets, log, read_out, spec_by_tag
from kpi_core import fit_score

lg = log("calculate_component_scores")


def included_tags(inv: pd.DataFrame, cfg=PRIMARY) -> list[str]:
    return inv[inv.included].tag.tolist()


def main():
    b = load_buckets("primary")
    inv = read_out("kpi_candidate_inventory.csv")
    tags = included_tags(inv)
    ref, s = fit_score(b, PRIMARY, tags)
    ref["kpi_version"] = KPI_VERSION
    (OUT / "kpi_reference.json").write_text(json.dumps(ref, indent=1, sort_keys=True, default=float, allow_nan=False))
    s["kpi"].to_parquet(CACHE / "scored_primary.parquet")
    names = inv.set_index("tag")[["original_name", "unit", "dataset", "source_column"]]
    sp = spec_by_tag()
    feed = b["values"][FEED_TAG]
    parts = []
    for t in s["tags"]["z"].columns:
        src = b["std60"] if t.startswith("STD60:") else b["values"]
        d = pd.DataFrame({"ts": src.index, "tag": t, "bucket_value": src[t].to_numpy(),
                          "expected_value": s["tags"]["expected"][t].to_numpy(),
                          "scale": ref["tags"][t]["scale"], "z": s["tags"]["z"][t].to_numpy(),
                          "tag_score": s["tags"]["score"][t].to_numpy(), "load_context_feed_tph": feed.to_numpy()})
        parts.append(d[np.isfinite(d.bucket_value)])
    long = pd.concat(parts, ignore_index=True)
    long["dimension"] = long.tag.map(lambda t: sp[t].dimension)
    long["direction"] = long.tag.map(lambda t: sp[t].direction)
    long["reference_mode"] = long.tag.map(lambda t: ref["tags"][t]["mode"])
    for c in names.columns:
        long[c] = long.tag.map(names[c])
    long["bucket_state"] = long.ts.map(s["kpi"].bucket_state)
    long["kpi_version"] = KPI_VERSION
    long = long.sort_values(["ts", "tag"]).reset_index(drop=True)
    long.to_parquet(OUT / "kpi_component_scores.parquet", index=False)
    lg.info("reference fitted on %d training buckets; %d included tags; component rows %d",
            ref["n_train_buckets"], len(ref["included_tags"]), len(long))


if __name__ == "__main__":
    main()
