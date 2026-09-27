"""Step 3 - Causal features for every analysable tag (candidates + context confounders).

Reads  cache/buckets_values.parquet, cache/buckets_meta.parquet, cache/kpi_grid.parquet,
       outputs/indicator_candidate_inventory.csv
Writes outputs/indicator_feature_reference.json   frozen per-tag references (discovery window only)
       outputs/indicator_feature_values.parquet   wide float32: timestamp + '<tag>|<feature>' columns (traceable)
       cache/features.parquet                     the same values in float64 (used by all statistics)

Features at bucket t use buckets <= t only (see indicator_core). References are fitted once on the Phase 3 training
population (RUNNING buckets 2025-04-01 .. 2025-05-31) and frozen.
"""
from __future__ import annotations

import json

import pandas as pd

from p4common import CACHE, FEATURES, FEED_TAG, OUT, PRIMARY, P4Config, log, read_out, write_parquet
import indicator_core as ic
import kpi_core

lg = log("build_causal_features")


def analysable_tags(inv: pd.DataFrame) -> list[str]:
    return sorted(inv[inv.status.isin(["CANDIDATE", "CONTEXT_ONLY"])].indicator_tag)


def align(values: pd.DataFrame, meta: pd.DataFrame, grid: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Restrict buckets to the Phase 3 KPI grid (the KPI parquet starts at the first bucket after train_start)."""
    return values.reindex(grid), meta.reindex(grid)


def fit_reference(values: pd.DataFrame, meta: pd.DataFrame, tags: list[str], cfg: P4Config) -> dict:
    train = kpi_core.training_mask(meta, ic.P3CFG)
    return ic.fit_feature_reference(values[tags], values[FEED_TAG], train, cfg)


def feature_frame(values: pd.DataFrame, ref: dict, tags: list[str], cfg: P4Config) -> pd.DataFrame:
    """Wide frame of all features, columns '<tag>|<feature>' in a fixed (sorted tag, FEATURES) order."""
    f = ic.compute_features(values[tags], values[FEED_TAG], ref, cfg)
    cols = {f"{t}|{name}": f[name][t] for t in tags for name in FEATURES if t in f[name]}
    return pd.DataFrame(cols, index=values.index)


def main():
    cfg = PRIMARY
    inv = read_out("indicator_candidate_inventory.csv")
    tags = analysable_tags(inv)
    grid = pd.read_parquet(CACHE / "kpi_grid.parquet").index
    values, meta = align(pd.read_parquet(CACHE / "buckets_values.parquet"), pd.read_parquet(CACHE / "buckets_meta.parquet"), grid)
    ref = fit_reference(values, meta, tags, cfg)
    txt = json.dumps(ref, sort_keys=True, indent=1, allow_nan=True, default=float)
    (OUT / "indicator_feature_reference.json").write_text(txt)
    F = feature_frame(values, ref, tags, cfg)
    F.to_parquet(CACHE / "features.parquet")
    out = F.astype("float32")
    out.insert(0, "timestamp", F.index)
    write_parquet(out, "indicator_feature_values.parquet", lg)
    na = [t for t in tags if not ref[t].get("available")]
    lg.info("%d tags x %d features = %d feature series; references unavailable for %s", len(tags), len(FEATURES),
            F.shape[1], na)


if __name__ == "__main__":
    main()
