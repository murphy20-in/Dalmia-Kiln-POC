"""Step 6 - Assemble the Efficiency Deterioration KPI dataset (primary + disclosed Sp.Heat variants).

Reads  cache/scored_primary.parquet, cache/buckets_primary_*.parquet, outputs/kpi_reference.json,
       outputs/kpi_reference_bands.csv, outputs/kpi_candidate_inventory.csv, cache/p2_input_hashes.json
Writes outputs/efficiency_deterioration_kpi.parquet  one row per 10-min bucket, 2025-04-01 .. 2025-09-30
       outputs/kpi_version_manifest.csv             KPI version, config, reference and input hashes, code hashes

The primary KPI uses BOTH Sp.Heat definitions (F and G each contribute; the plant has not said which is
authoritative). The single-definition KPIs are carried on every row so the ambiguity stays visible.
`efficiency_deterioration_kpi` is reported only OUT OF SAMPLE (after the training window); inside training the
same computation is kept in `kpi_in_sample_reference` for reference only.
Every derived operator field is causal (uses rows <= t): trend, band episode, hours in band, confidence.
kpi_alt_reference_w_jun_jul15 is a SHADOW column (later-anchored reference; empty inside its own training window).
"""
from __future__ import annotations

import json
import platform
from dataclasses import asdict

import numpy as np
import pandas as pd
import sklearn

from p3common import (BAND_LABEL, CACHE, COMPOSITE_LABEL, EQUIPMENT_VIEW, KPI_NAME, KPI_VERSION, OUT, PHASE_DIR,
                      PRIMARY, PROXY_LABEL, SCALE_LABEL, TRAINING_WINDOWS, load_buckets, log, read_out, sha256, variant,
                      write_csv)
from kpi_core import fit_score

lg = log("calculate_efficiency_kpi")


def causal_trend(k: pd.Series, days: int = 7) -> tuple[pd.Series, pd.Series]:
    """Trailing 7-day median of the reported KPI, and its change against the 7-day window ending 7 days earlier."""
    med = k.rolling(f"{days}D", min_periods=int(days * 144 * 0.25)).median()
    return med, med - med.shift(freq=f"{days}D").reindex(k.index)


def band_runs(band: pd.Series, bucket_min: int) -> tuple[pd.Series, pd.Series]:
    """Causal episode id (consecutive reported buckets in the same band) and hours spent in the current band so far."""
    b = band.where(band.ne(""))
    new = b.ne(b.shift()) | b.isna()
    eid = new.cumsum().where(b.notna())
    hours = (b.notna().groupby(eid).cumsum() * bucket_min / 60).where(b.notna())
    return eid, hours


def main():
    k = pd.read_parquet(CACHE / "scored_primary.parquet")
    ref = json.loads((OUT / "kpi_reference.json").read_text())
    bands = read_out("kpi_reference_bands.csv")
    b = load_buckets("primary")
    inv = read_out("kpi_candidate_inventory.csv")
    tags = inv[inv.included].tag.tolist()
    var = {}
    for name, cfg in {"F": variant(name="SP_HEAT_F_ONLY", sp_heat="F"), "G": variant(name="SP_HEAT_G_ONLY", sp_heat="G"),
                      "UNADJ": variant(name="EFFICIENCY_UNADJUSTED", load_mode="global"),
                      "ALT": variant(name="W_JUN_JUL15", train_start=TRAINING_WINDOWS["W_JUN_JUL15"][0],
                                     train_end=TRAINING_WINDOWS["W_JUN_JUL15"][1])}.items():
        var[name] = fit_score(b, cfg, tags)[1]["kpi"]
    conf = inv.set_index("tag").baseline_confidence
    comp = pd.read_parquet(OUT / "kpi_component_scores.parquet", columns=["ts", "tag", "tag_score", "bucket_value", "expected_value"])
    avail = comp.dropna(subset=["tag_score"]).assign(high=lambda d: d.tag.map(conf).eq("HIGH"))
    share_high = avail.groupby("ts").high.mean()
    sph = comp[comp.tag.isin(["Kiln-I!F", "Kiln-I!G"])].pivot(index="ts", columns="tag", values=["bucket_value", "expected_value"])
    win = pd.Timedelta(PRIMARY.persistence_window)
    t = k.index
    rep = k.efficiency_deterioration_kpi
    out = pd.DataFrame({"timestamp": t})
    out["equipment_view"] = EQUIPMENT_VIEW
    out["operating_state"] = k.bucket_state.to_numpy()
    out["operating_state_label"] = PROXY_LABEL
    out["load_context_feed_tph"] = k.load_context_feed_tph.to_numpy()
    out["out_of_training_load_range"] = k.out_of_training_load_range.fillna(False).to_numpy()
    for tag, lab in [("Kiln-I!F", "f"), ("Kiln-I!G", "g")]:
        out[f"sp_heat_{lab}_actual"] = t.map(sph[("bucket_value", tag)]) if ("bucket_value", tag) in sph else np.nan
        out[f"sp_heat_{lab}_expected_for_load"] = t.map(sph[("expected_value", tag)]) if ("expected_value", tag) in sph else np.nan
    out["efficiency_component"] = k.efficiency_component.to_numpy()
    out["efficiency_component_sp_heat_f"] = var["F"].efficiency_component.to_numpy()
    out["efficiency_component_sp_heat_g"] = var["G"].efficiency_component.to_numpy()
    out["efficiency_component_unadjusted"] = var["UNADJ"].efficiency_component.to_numpy()
    for d in ["combustion", "thermal", "draft_pressure", "stability"]:
        out[f"{d}_component"] = k[f"{d}_component"].to_numpy()
    for d in ["efficiency", "combustion", "thermal", "draft_pressure", "stability"]:
        out[f"contrib_{d}"] = k[f"contrib_{d}"].to_numpy()
    out["raw_deviation_score"] = k.raw_deviation_score.to_numpy()
    out["persistent_deviation_score"] = k.persistent_deviation_score.to_numpy()
    out["persistence_window_coverage"] = k.persistence_window_coverage.to_numpy()
    out["persistence_fraction_elevated"] = k.persistence_fraction_elevated.to_numpy()
    out["efficiency_deterioration_kpi"] = rep.to_numpy()
    out["kpi_in_sample_reference"] = k.kpi_in_sample_reference.to_numpy()
    out["kpi_training_percentile"] = k.kpi_training_percentile.to_numpy()
    out["kpi_band"] = k.kpi_band.to_numpy()
    out["kpi_band_code"] = k.kpi_band_code.to_numpy()
    lo = bands[bands.quantity.str.startswith("band_lo")].iloc[0]
    hi = bands[bands.quantity.str.startswith("band_hi")].iloc[0]
    near = (rep.between(lo.kpi_ci95_low, lo.kpi_ci95_high) | rep.between(hi.kpi_ci95_low, hi.kpi_ci95_high))
    out["near_band_boundary"] = near.where(rep.notna(), False).astype(bool).to_numpy()
    out["kpi_driver_class"] = k.kpi_driver_class.to_numpy()
    out["window_efficiency_share"] = k.window_efficiency_share.to_numpy()
    out["n_dims_elevated"] = k.n_dims_elevated.to_numpy()
    out["top_dimension"] = k.top_dimension.to_numpy()
    out["top_tag"] = k.top_tag.to_numpy()
    out["top_dimension_bucket"] = k.top_dimension_bucket.to_numpy()
    med7, tr7 = causal_trend(rep)
    out["kpi_7d_median"] = med7.to_numpy()
    out["kpi_trend_7d"] = tr7.to_numpy()
    eid, hrs = band_runs(k.kpi_band.where(rep.notna(), ""), PRIMARY.bucket_min)
    out["band_episode_id"] = eid.to_numpy()
    out["hours_in_current_band"] = hrs.to_numpy()
    out["kpi_sp_heat_f_only"] = var["F"].efficiency_deterioration_kpi.to_numpy()
    out["kpi_sp_heat_g_only"] = var["G"].efficiency_deterioration_kpi.to_numpy()
    out["kpi_alt_reference_w_jun_jul15"] = var["ALT"].efficiency_deterioration_kpi.to_numpy()
    out["secondary_validation_mahalanobis_kpi"] = k.secondary_mahalanobis_kpi.where(
        k.kpi_reference_state.str.startswith("OUT_OF_SAMPLE")).to_numpy()
    out["kpi_reference_state"] = k.kpi_reference_state.to_numpy()
    cov = (k.n_tags_available / k.n_tags_included.replace(0, np.nan)).to_numpy()
    running = k.bucket_state.eq("RUNNING").to_numpy()
    out["tag_coverage"] = cov
    out["data_quality"] = np.select([~running, cov >= 0.9, cov >= 0.6], ["NOT_APPLICABLE (not running)", "GOOD", "DEGRADED"],
                                    "POOR")
    out.loc[k.n_causal_frozen_minutes.to_numpy() > 0, "data_quality"] = "CAUSAL_FROZEN_MINUTES_IN_BUCKET"
    wcov = k.persistence_window_coverage.to_numpy()
    oor = out.out_of_training_load_range.to_numpy()
    kc = np.select([~rep.notna().to_numpy(), (cov < 0.6) | (wcov < 0.6) | oor,
                    (cov >= 0.9) & (wcov >= 0.8) & ~out.near_band_boundary.to_numpy()], ["", "LOW", "HIGH"], "MEDIUM")
    out["kpi_confidence"] = kc
    out["share_high_confidence_tags"] = t.map(share_high)
    out["baseline_confidence"] = np.select([out.share_high_confidence_tags >= 0.75, out.share_high_confidence_tags >= 0.5],
                                           ["INPUT_TAGS_MOSTLY_HIGH_P2_CONFIDENCE", "INPUT_TAGS_MIXED_P2_CONFIDENCE"],
                                           "INPUT_TAGS_MOSTLY_MEDIUM_LOW_P2_CONFIDENCE")
    out.loc[out.share_high_confidence_tags.isna(), "baseline_confidence"] = ""
    out["n_tags_available"] = k.n_tags_available.to_numpy()
    out["n_tags_included"] = k.n_tags_included.to_numpy()
    out["n_dims_available"] = k.n_dims_available.to_numpy()
    out["n_causal_frozen_minutes"] = k.n_causal_frozen_minutes.to_numpy()
    out["source_window_start"] = t - win + pd.Timedelta(minutes=1)
    out["source_window_end"] = t
    out["training_window_start"] = pd.Timestamp(PRIMARY.train_start)
    out["training_window_end"] = pd.Timestamp(PRIMARY.train_end)
    out["kpi_version"] = KPI_VERSION
    out["config_key"] = PRIMARY.key()
    out["scale_label"] = SCALE_LABEL
    out = out[(out.timestamp > pd.Timestamp(PRIMARY.train_start)) & (out.timestamp <= pd.Timestamp(PRIMARY.score_end) + pd.Timedelta(minutes=1))]
    out.to_parquet(OUT / "efficiency_deterioration_kpi.parquet", index=False)
    last_scored = out.timestamp[out.efficiency_deterioration_kpi.notna()].max()
    lg.info("KPI rows %d; out-of-sample scored %d (last %s); states %s", len(out), int(out.efficiency_deterioration_kpi.notna().sum()),
            last_scored, out.kpi_reference_state.value_counts().to_dict())

    hashes = json.loads((CACHE / "p2_input_hashes.json").read_text())
    code = {p.name: sha256(p) for p in sorted((PHASE_DIR / "scripts").glob("*.py"))}
    man = [("kpi_name", KPI_NAME), ("kpi_version", KPI_VERSION), ("config_key", PRIMARY.key()),
           ("config", json.dumps(asdict(PRIMARY), sort_keys=True, default=str)),
           ("scale", "0-100 POC normalized score: KPI = 100*(1 - 2^-e), e = max(0, P - m)/(q95 - m)"),
           ("scale_label", SCALE_LABEL), ("band_label", BAND_LABEL), ("state_label", PROXY_LABEL),
           ("composite_label", COMPOSITE_LABEL), ("training_window", f"{PRIMARY.train_start} .. {PRIMARY.train_end}"),
           ("scoring_window", f"{PRIMARY.train_end} .. last scored bucket {last_scored}; September = NO_EFFICIENCY_DATA"),
           ("included_tags", "|".join(tags)), ("n_included_tags", str(len(tags))),
           ("reference_sha256", sha256(OUT / "kpi_reference.json")),
           ("validation_status", "statistical / historical-data validation only; no event ground truth"),
           ("python", platform.python_version()), ("pandas", pd.__version__), ("numpy", np.__version__),
           ("scikit-learn", sklearn.__version__)]
    man += [(f"input_sha256:{n}", h) for n, h in sorted(hashes.items())]
    man += [(f"code_sha256:{n}", h) for n, h in code.items()]
    write_csv(pd.DataFrame(man, columns=["item", "value"]), "kpi_version_manifest.csv", lg)


if __name__ == "__main__":
    main()
