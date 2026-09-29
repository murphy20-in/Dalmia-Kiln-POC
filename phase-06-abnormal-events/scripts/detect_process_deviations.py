"""Step 3 - Process-family and tag-level deviation evidence for every candidate episode.

Family deviation reuses the Phase 3 causal, frozen-reference family scores S_d (training median / robust scale, load-
conditional tag medians) - no baseline is re-fitted on full-period data. The tag-level table answers "why was this period
considered abnormal?": every Phase 3 scored tag in every episode bucket with its raw bucket value, its load-conditional
training reference, its signed robust z and its share of the bucket's total tag score. LOAD context tags (feed, kiln
speed, clinker TPH) are added with their Apr-May RUNNING median / MAD reference.

Writes outputs/abnormal_episode_signals.parquet and cache/stage_top_tags.parquet (per-episode top tags).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from abn_core import CACHE, LOAD_TAGS, P3_OUT, load_inputs, load_stage, log, write_parquet

lg = log("detect_process_deviations")
ABNORMAL_TAG_SCORE = 3.0   # POC heuristic: tag score (robust z; one-sided for Sp.Heat / variability) >= 3


def episode_buckets(ep: pd.DataFrame, ix: pd.DatetimeIndex) -> pd.DataFrame:
    rows = [(r.episode_id, ix[p]) for r in ep.itertuples() for p in range(int(r.pos_start), int(r.pos_end) + 1)]
    return pd.DataFrame(rows, columns=["episode_id", "timestamp"])


def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = load_stage("episodes")
    eb = episode_buckets(ep, g.index)
    cs = pd.read_parquet(P3_OUT / "kpi_component_scores.parquet",
                         columns=["ts", "tag", "bucket_value", "expected_value", "z", "tag_score", "dimension",
                                  "direction", "original_name", "unit", "dataset"])
    cs = cs[cs.ts.isin(set(eb.timestamp))].rename(columns={"ts": "timestamp"})
    cs["bucket_total"] = cs.groupby("timestamp").tag_score.transform("sum")
    sig = eb.merge(cs, on="timestamp", how="left")
    sig["contribution_score"] = sig.tag_score / sig.bucket_total.replace(0, np.nan)
    sig["process_family"] = sig.dimension
    sig["deviation_score"] = sig.z
    sig["direction"] = np.select([sig.z > 0, sig.z < 0], ["ABOVE_REFERENCE", "BELOW_REFERENCE"], "AT_REFERENCE")
    sig.loc[sig.z.isna(), "direction"] = "NOT_SCORED"
    sig["abnormal_flag"] = sig.tag_score >= ABNORMAL_TAG_SCORE
    sig["reference_type"] = "Phase 3 frozen load-conditional training median (Apr-May)"
    sig = sig.rename(columns={"bucket_value": "raw_value", "expected_value": "reference_value"})
    # load context tags: Apr-May RUNNING median / MAD (context family; never counted as process abnormality)
    tc = pd.read_csv(CACHE / "tag_check.csv").set_index("tag")
    load_rows = []
    for tag, col in LOAD_TAGS.items():
        L = ref["load"][col]
        v = g[col].reindex(eb.timestamp).to_numpy(float)
        z = (v - L["median"]) / L["mad"]
        load_rows.append(pd.DataFrame({
            "episode_id": eb.episode_id, "timestamp": eb.timestamp, "tag": tag, "raw_value": v,
            "reference_value": L["median"], "z": z, "deviation_score": z, "tag_score": np.abs(z),
            "dimension": "LOAD", "process_family": "LOAD",
            "direction": np.where(np.isnan(z), "NOT_SCORED", np.where(z > 0, "ABOVE_REFERENCE", "BELOW_REFERENCE")),
            "original_name": tc.at[tag, "original_name"], "unit": tc.at[tag, "unit"], "dataset": tag.split("!")[0],
            "abnormal_flag": np.abs(z) >= 3.0, "contribution_score": np.nan,
            "reference_type": "Phase 6 Apr-May RUNNING median / scaled MAD (load context only)"}))
    sig = pd.concat([sig, *load_rows], ignore_index=True)
    dq = g.dq.reindex(sig.timestamp).to_numpy()
    sig["quality_flag"] = np.where(pd.isna(sig.raw_value), "VALUE_MASKED_OR_MISSING", dq)
    cols = ["episode_id", "timestamp", "dataset", "tag", "original_name", "process_family", "unit", "raw_value",
            "reference_value", "reference_type", "deviation_score", "direction", "abnormal_flag", "quality_flag",
            "contribution_score", "tag_score"]
    sig = sig[cols].sort_values(["episode_id", "timestamp", "process_family", "tag"]).reset_index(drop=True)
    write_parquet(sig, "abnormal_episode_signals.parquet", lg)
    # top 3 contributing process tags per episode (median tag score over the episode)
    proc = sig[sig.process_family != "LOAD"]
    med = proc.groupby(["episode_id", "tag", "original_name", "process_family"], observed=True).agg(
        tag_score=("tag_score", "median"), z=("deviation_score", "median"))
    top = (med.reset_index().sort_values(["episode_id", "tag_score", "tag"], ascending=[True, False, True])
           .groupby("episode_id").head(3))
    word = np.where(top.z > 0, "above", "below")
    top["label"] = (top.original_name.astype(str) + " [" + top.tag + ", " + top.process_family.str.lower() + "] "
                    + word + " reference (median robust z " + top.z.round(1).map("{:+.1f}".format)
                    + "; scores capped at 10)")
    top.groupby("episode_id").label.agg("; ".join).rename("top_tags").reset_index() \
        .to_parquet(CACHE / "stage_top_tags.parquet", index=False)
    lg.info("%d signal rows for %d episodes; %.1f %% of process tag-buckets flagged abnormal (score >= %.0f)",
            len(sig), ep.shape[0], 100 * proc.abnormal_flag.mean(), ABNORMAL_TAG_SCORE)


if __name__ == "__main__":
    main()
