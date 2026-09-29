"""Step 2 - fit the frozen Phase 7 reference on the Apr-May reference window only.

Writes outputs/risk_score_reference.json            primary reference (anchors, H_ref90, bands + CIs, load quantiles,
                                                    signatures, family correlation, config, input + code hashes)
       outputs/risk_score_variant_references.json   references of the confidence-robustness variants (spec section 6)

fit_reference() only ever reads buckets with ref_start < t <= ref_end, plus trailing windows that end inside the reference
window, so no scored-period value can enter the reference (G3 refit-invariance check).
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict

import numpy as np
import pandas as pd
from scipy import stats

from common import (CACHE, CONFIDENCE_VARIANTS, OUT, PRIMARY, SCORE_VERSION, SCRIPTS, P7Config, load_context, log,
                    read_json, write_json)
from feature_engineering import load_change
from risk_core import anchor_arrays, family_S, fit_bands, load_band_index, magnitude, score_core

MIN_REF_VALUES = 200


def reference_mask(grid: pd.DataFrame, cfg: P7Config) -> np.ndarray:
    ix = grid.index
    return ((ix > pd.Timestamp(cfg.ref_start)) & (ix <= pd.Timestamp(cfg.ref_end))
            & (grid["state"].to_numpy(dtype=object) == "RUNNING"))


def anchor(v: np.ndarray, cfg: P7Config) -> dict:
    v = v[np.isfinite(v)]
    if v.size < MIN_REF_VALUES:
        raise ValueError(f"only {v.size} finite reference values (< {MIN_REF_VALUES}) - anchors would be unstable")
    m, q_raw = float(np.median(v)), float(np.quantile(v, cfg.abnormal_q))
    return {"m": m, "q": max(q_raw, m + cfg.anchor_floor), "q_raw": q_raw,
            "degenerate": bool(q_raw < m + cfg.anchor_floor), "n": int(v.size)}


def code_sha256() -> str:
    """Hash of the Phase 7 scoring code (every scripts/*.py, sorted) - pins a reference to the code that built it."""
    h = hashlib.sha256()
    for p in sorted(SCRIPTS.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def fit_reference(grid: pd.DataFrame, cfg: P7Config, episodes: pd.DataFrame, ctx: dict | None = None) -> dict:
    ix = grid.index
    rm = reference_mask(grid, cfg)
    S, run = family_S(grid, cfg)
    feed = grid["feed"].to_numpy(float)
    fr = feed[rm & np.isfinite(feed)]
    chg = load_change(feed, cfg.load_change_buckets)[rm]
    ref = {"score_version": SCORE_VERSION, "config": asdict(cfg), "config_key": cfg.key(), "families": list(cfg.families),
           "ref_start": cfg.ref_start, "ref_end": cfg.ref_end, "n_reference_buckets": int(rm.sum()),
           "load": {"feed_p33": float(np.quantile(fr, 1 / 3)), "feed_p67": float(np.quantile(fr, 2 / 3)),
                    "feed_change_p90": float(np.quantile(chg[np.isfinite(chg)], 0.9))},
           "anchors": {d: anchor(S[rm, j], cfg) for j, d in enumerate(cfg.families)}, "anchors_by_band": {}}
    ref["reference_version"] = f"{SCORE_VERSION}/{cfg.name}/{cfg.key()}/{cfg.ref_start[:10]}..{cfg.ref_end[:10]}"
    bidx = load_band_index(feed, ref)
    if cfg.load_mode == "load_band":
        for b in range(3):
            sel = rm & (bidx == b)
            if all(np.isfinite(S[sel, j]).sum() >= MIN_REF_VALUES for j in range(len(cfg.families))):
                ref["anchors_by_band"][str(b)] = {d: anchor(S[sel, j], cfg) for j, d in enumerate(cfg.families)}
    M, Q = anchor_arrays(ref, len(grid), bidx)
    mg = magnitude(S, M, Q, cfg)
    v3 = rm & run & (mg["n_use"] >= cfg.min_usable_families)
    ref["H_ref90"] = float(np.quantile(mg["H"][v3], 0.90))
    core = score_core(grid, ref, cfg, ctx)
    R = core["R"][v3]
    ref["reference_score_quantiles"] = {f"p{q}": float(np.quantile(R, q / 100)) for q in (50, 75, 90, 95, 99)}
    ref["bands"] = fit_bands(R, ix[v3], cfg)
    af = mg["af"][v3]
    rho = np.atleast_2d(stats.spearmanr(af).statistic) if af.shape[1] > 1 else np.ones((1, 1))
    ref["family_spearman"] = {d: {e: (float(rho[i, j]) if np.isfinite(rho[i, j]) else None)
                                  for j, e in enumerate(cfg.families)} for i, d in enumerate(cfg.families)}
    lib = episodes[episodes.classification.eq("CALIBRATION_ONLY_ABNORMAL_LIKE")
                   & (episodes.end_time <= pd.Timestamp(cfg.ref_end))].sort_values("start_time")
    sigs = []
    for r in lib.itertuples():
        sel = (ix > r.start_time) & (ix <= r.end_time) & core["valid3"]
        if sel.any():
            sigs.append({"episode_id": r.episode_id, "signature": np.median(mg["af"][sel], axis=0).round(6).tolist()})
    ref["signatures"] = sigs
    return ref


def main():
    lg = log("reference_builder")
    ctx = load_context()
    hashes = read_json(CACHE / "input_hashes.json")
    code = code_sha256()
    ref = fit_reference(ctx["grid"], PRIMARY, ctx["episodes"], ctx)
    ref["input_hashes"], ref["code_sha256"] = hashes, code
    write_json(ref, OUT / "risk_score_reference.json")
    var = {n: {**fit_reference(ctx["grid"], c, ctx["episodes"], ctx), "input_hashes": hashes, "code_sha256": code}
           for n, c in CONFIDENCE_VARIANTS.items()}
    write_json(var, OUT / "risk_score_variant_references.json")
    lg.info("reference %s: %d buckets, H_ref90 %.4f, bands %s %s, degenerate anchors %s", ref["reference_version"],
            ref["n_reference_buckets"], ref["H_ref90"], ref["bands"]["status"],
            [(e["band"], round(e["value"], 2)) for e in ref["bands"]["edges"]],
            [d for d, a in ref["anchors"].items() if a["degenerate"]])


if __name__ == "__main__":
    main()
