"""Step 9 - Phase 2 report (MD + HTML), generated only from Phase 2 outputs.

Outputs: reports/PHASE_2_NORMAL_OPERATING_BASELINE.md / .html
The review log (phase-02-baseline/reviews/REVIEW_LOG.md) is included when present.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from p2common import (OUT, REPORTS, PHASE_DIR, RAW, H, BAND_LABEL, PROXY_LABEL, COMPOSITE_LABEL, KEY_TAGS, read_out, log)

lg = log("generate_report")


def md_table(df: pd.DataFrame, max_rows: int | None = None, max_col: int = 80, floatfmt: str = "{:.4g}") -> str:
    if df is None or df.empty:
        return "_None._\n"
    d = df.head(max_rows) if max_rows else df

    def cell(v):
        if isinstance(v, float):
            s = "" if np.isnan(v) else (str(int(v)) if v.is_integer() and abs(v) < 1e12 else floatfmt.format(v))
        else:
            s = "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return s if len(s) <= max_col else s[: max_col - 1] + "…"
    out = "| " + " | ".join(map(str, d.columns)) + " |\n| " + " | ".join("---" for _ in d.columns) + " |\n"
    out += "".join("| " + " | ".join(cell(v) for v in r) + " |\n" for r in d.itertuples(index=False))
    if max_rows and len(df) > max_rows:
        out += f"\n_{len(df) - max_rows} more rows in the CSV._\n"
    return out


def main():
    man = read_out("processed_dataset_manifest.csv")
    plog = read_out("parse_log.csv")
    src = pd.read_csv(RAW / "source_manifest.csv")
    holds = read_out("column_holds.csv")
    fw = read_out("frozen_windows.csv")
    msum = read_out("mask_summary.csv")
    osa = read_out("operating_state_analysis.csv")
    ev = read_out("operating_state_events.csv")
    rg = read_out("operating_regimes.csv")
    pop = read_out("baseline_population.csv")
    st = read_out("baseline_statistics.csv")
    bands = read_out("baseline_reference_bands.csv")
    stab = read_out("baseline_stability.csv")
    tmp = read_out("baseline_temporal_analysis.csv")
    mv = read_out("multivariate_baseline.csv")
    conf = read_out("baseline_confidence.csv")
    fam = read_out("baseline_family_readiness.csv")
    val = read_out("phase2_validation.csv")
    cur = read_out("baseline_current_reference.csv")
    run = st[st.population == "BASELINE_RUNNING"]
    regimes_supported = rg.query("test == 'SUPPORT_DECISION' and dimension == 'LOAD'").value.iloc[0] == 1.0
    regime_status = rg.query("test == 'REGIME_STATUS'").detail.iloc[0]
    boot = rg.query("test == 'BOOTSTRAP_BAND_STABILITY'").detail.iloc[0]
    fitw = rg.query("test == 'FIT_WINDOW'").detail.iloc[0]
    sens = read_out("baseline_sensitivity.csv")
    confr = conf[conf.population == "BASELINE_RUNNING"]
    L = []
    A = L.append
    A("# Phase 2 — Normal Operating Baseline\n")
    A("**Dalmia Cement, Ariyalur — Kiln Efficiency & Deposit Build-Up POC**\n")
    A(f"Generated {datetime.now().isoformat(timespec='seconds')} by `phase-02-baseline/scripts/generate_report.py` from `phase-02-baseline/outputs/`.\n")
    A("> **What this is:** an empirical POC reference that describes normal behaviour in the supplied historical data.\n>\n"
      "> **What it is not:** plant-approved operating limits, alarm thresholds, engineering or control limits, or a statement that the kiln is healthy.\n>\n"
      f"> - Every baseline value depends on an operating-state **{PROXY_LABEL}**.\n"
      f"> - Any cross-dataset view is a **{COMPOSITE_LABEL}**.\n"
      "> - The report contains no KPI, model, risk score or operational recommendation.\n")

    A("**Plain-language glossary:**\n")
    A("- *Kiln running (inferred)* = RUNNING_PROXY.")
    A("- *Typical range* = P05–P95 of baseline values.")
    A("- *Typical spread* = scaled MAD, a robust standard deviation.")
    A("- *Steady / moderately variable / highly variable* = stability class LOW / MODERATE / HIGH short-term variation.")
    A("- *Load band* = a feed-rate cluster found in the data.")
    A("- *Confidence* = how well the data support each baseline (criteria C1–C8).")
    A("- *Data-quality class* (GREEN/AMBER/RED) describes data completeness, not process health.\n")
    # 1
    s_min = osa[osa.section == "STATE_MINUTES"].set_index("item").value
    inc_total = int(pop.included.sum()); cells_total = int(pop.cells_total.sum())
    n_base_tags = int(run[["dataset", "tag"]].drop_duplicates().shape[0])
    k = lambda eq, t: run[(run.dataset == eq) & (run.tag == t)].iloc[0]
    fe, sp, bz = k("Kiln-I", "C"), k("Kiln-I", "O"), k("Kiln-I", "AF")
    A("## 1. Executive Summary\n")
    A(f"- **Data processed:** {len(plog)} approved workbooks (manifest `status == USE`) across {len(man)} datasets, giving {cells_total:,} source cells in "
      f"long format. Nothing was resampled, interpolated or unit-converted.")
    A(f"- **Baseline population:** {inc_total:,} cells ({inc_total / cells_total:.1%}) are INCLUDED. Everything else is MASKED (quality flags) or "
      "EXCLUDED (column holds, non-running state, hourly rows), and every cell records its reason.")
    A(f"- **Operating state ({PROXY_LABEL}):** the two observed `Kiln MD` values track independent signals.")
    A(f"  - `Kiln MD` = 0.02 → Kiln-I feed median {fe['median']:.0f} TPH, kiln speed {sp['median']:.2f} RPM, burning zone {bz['median']:.0f} °C.")
    A("  - `Kiln MD` = 0 → feed and speed absent or zero.")
    A(f"  - Composite minutes: RUNNING {int(s_min.get('RUNNING_PROXY', 0)):,}, STOPPED {int(s_min.get('STOPPED_PROXY', 0)):,}, "
      f"transition {int(s_min.get('TRANSITION_RAMP_PROXY', 0) + s_min.get('TRANSITION_PRE_STOP_PROXY', 0)):,}.")
    A(f"  - The longest stop runs from 2025-08-24 to 2025-09-10.")
    if regimes_supported:
        mb = rg[rg.test == "MERGED_BAND"]
        A("- **Operating regimes:** on the full data, kiln feed forms "
          f"{len(mb)} separated, persistent load bands: "
          + "; ".join(r.detail.split(':')[0] + f" ≈{r.value:.0f} TPH ({r.detail.split('weight ')[-1]})" for r in mb.itertuples())
          + f". The structure does not hold up under resampling ({boot.split(';')[-1].strip()}), so its status is **{regime_status.split(';')[0]}**. "
            "The single RUNNING baseline is primary. Bands are a secondary stratification.")
    else:
        A("- **Operating regimes:** no load regime met the support criteria, so a single running-state baseline is used.")
    A(f"- **Parameters baselined:** {n_base_tags} tags. Baseline confidence for the primary population: "
      f"{confr.baseline_confidence.value_counts().to_dict()}. Held columns count as INSUFFICIENT. The grade measures evidence for the baseline, not equipment health.")
    A(f"- **Stability:** {stab.stability_class.value_counts().to_dict()}.")
    A(f"- **Family readiness:** {fam.set_index('process_family').baseline_readiness.to_dict()}. No family reaches READY. The operating state is unconfirmed, "
      "and many tags show month-to-month level shifts (criterion C6).")
    A(f"- **Validation:** {int((val.result == 'PASS').sum())}/{len(val)} checks PASS.\n")

    # 2
    A("## 2. Input Data\n")
    A("The Phase 1 metadata contract was used as-is: `data/raw/source_manifest.csv`, `process_tag_inventory.csv`, `data_quality_report.csv`, "
      "`unit_consistency_review.csv`, `flatline_periods.csv`, `flatline_profile.csv`, `identical_column_pairs.csv`, `gap_events.csv`, "
      "`sampling_changes.csv`, `outlier_profile.csv` and `file_inventory.csv`.\n")
    A(md_table(src.groupby(["status"]).relative_path.count().reset_index().rename(columns={"relative_path": "files"})))
    A("Not loaded: " + "; ".join(f"`{r.relative_path.split('/')[-1]}` ({r.status}: {r.notes})" for r in src[src.status != 'USE'].itertuples()) + ".\n")
    A(md_table(man[["dataset", "source_frequency", "analysis_frequency", "resampling_required", "first_ts", "last_ts", "distinct_timestamps", "segments"]], max_col=70))
    A("\nPer-file parse log (`outputs/parse_log.csv`): every header was checked against the Phase 1 original names. The run stops if any header differs.\n")

    # 3
    A("## 3. Data Preparation\n")
    A("**Processed layer** (`data/processed/<dataset>.parquet`): one row per source cell (file, row, column).\n")
    A("- Columns: `value` (native numbers only) and `raw_value_text` (verbatim text for any non-numeric cell).")
    A("- Mask columns: `value_valid`, `quality_flag` (GOOD/SUSPECT/BAD/MISSING), `mask_reason`, `dup_status`, `row_repeat_prev`, `segment_id`, `column_hold`.")
    A("- State columns: `operating_state`, `load_regime`, `baseline_status`, `baseline_reason`.\n")
    A("**Curated layer** (`data/curated/<dataset>_baseline.parquet`): only the INCLUDED cells approved for the baseline.\n")
    A(md_table(man[["dataset", "rows_long", "cells_GOOD", "cells_SUSPECT", "cells_BAD", "cells_MISSING", "dup_conflict_cells", "dup_identical_copy_cells",
                    "rows_repeating_previous_row_pct"]]))
    A("\n**Mask rules:**\n")
    A("- **Sentinels:** `99999` and `9999` are masked as `SENTINEL_*`.")
    A("- **Impossible temperatures:** values ≤ −273 in `Deg.C` columns are masked.")
    A("- **Text:** `Error 6` and other text become `TEXT_VALUE`; numeric-looking text is kept but flagged.")
    A(f"- **Frozen export window(s):** {', '.join(f'{r.window_start}→{r.window_end} ({r.tags} tags)' for r in fw.itertuples())} are masked `SUSPECTED_FROZEN_WINDOW` in the affected datasets.")
    A("- **Duplicate timestamps (deterministic):** duplicates are keyed by (column, ts) and ordered by file and row.")
    A("  - If every copy is identical, the first is kept and the rest are masked.")
    A("  - If copies conflict, **all** copies are masked and no winner is chosen.")
    A("- **CBS-II 1–10 June:** hourly rows are kept as hourly (`RESOLUTION_HOURLY`) and excluded from the 1-minute baseline.")
    A("- **Repeated rows:** rows that repeat the previous row exactly are kept and flagged. The sensitivity of median, scale and rolling std to them is reported.")
    A("- **Gaps:** gaps are never filled, and `segment_id` breaks at every gap.\n")
    A("Column-level holds (values kept in `data/processed`, excluded from the baseline):\n")
    A(md_table(holds[["dataset", "source_column", "original_name", "hold", "evidence"]], max_col=90))
    A("\n## 3a. Baseline population accounting\n")
    pa = pop.groupby("dataset")[["cells_total", "included", "masked", "excluded_column", "excluded_state", "excluded_resolution"]].sum().reset_index()
    A(md_table(pa))

    # 4
    A("\n## 4. Operating State\n")
    A(f"`Kiln MD` (column B, unit `hrs`) is not defined in the source. Its meaning was tested against independent signals, and it is used only as a **{PROXY_LABEL}**.\n")
    A(md_table(osa[osa.section.isin(["KILN_MD_AGREEMENT_WITH_COMPOSITE"])][["item", "value", "detail"]].rename(columns={"item": "dataset", "value": "agreement"})))
    A("\nIndependent signals by `Kiln MD` state:\n")
    A(md_table(osa[osa.section == "INDEPENDENT_SIGNAL_BY_KILN_MD_STATE"][["item", "value", "detail"]].rename(columns={"value": "median"}), max_col=120))
    A("\nState rules (retrospective and used only to define the population; not a real-time rule):\n")
    A(f"- **Pre-stop window:** {H['pre_stop_window_min']} min before each stop is labelled `TRANSITION_PRE_STOP_PROXY`.")
    A("- **Restart ramp:** after each restart, minutes are labelled `TRANSITION_RAMP_PROXY`. "
      + osa[osa.section == "RAMP_RULE"].detail.iloc[0] + ".")
    A("- **Conflicts:** `STATE_CONFLICT` marks minutes where independent signals disagree with the proxy.\n")
    A(md_table(osa[osa.section == "STATE_MINUTES"][["item", "value", "detail"]].rename(columns={"item": "state", "value": "minutes"})))
    A(f"\n{int((ev.event == 'STOP').sum())} stops and {int((ev.event == 'RESTART').sum())} restarts are listed in `outputs/operating_state_events.csv`.\n")
    A("Evidence behind the state at each minute (`state_basis`):\n")
    A(md_table(osa[osa.section == "STATE_BASIS_MINUTES"][["item", "value"]].rename(columns={"item": "state basis", "value": "minutes"})))
    A("\n" + osa[osa.section == "RAMP_RULE"].iloc[-1]["item"] + f": {osa[osa.section == 'RAMP_RULE'].iloc[-1]['value']} "
      f"({osa[osa.section == 'RAMP_RULE'].iloc[-1]['detail']}).\n")
    A("![operating state](figures/operating_state_evidence.png)\n")

    # 5
    A("## 5. Operating Regimes\n")
    A("Regimes were investigated only inside RUNNING_PROXY minutes and declared only where they met documented support criteria.\n")
    A(md_table(rg[rg.test.isin(["GMM_BIC", "GMM_COMPONENT", "MERGED_BAND", "SUPPORT_DECISION", "ZERO_WHILE_RUNNING_SHARE", "DWELL_MEDIAN_ZERO_MIN"])][
        ["dimension", "test", "k", "value", "detail"]], max_col=160))
    A("\nBand share by month:\n")
    bm = rg[rg.test == "BAND_SHARE_BY_MONTH"].copy()
    if len(bm):
        bm["month"] = bm.detail.str.split(":").str[0]; bm["band"] = bm.detail.str.split(": ").str[1]
        A(md_table(bm.pivot(index="month", columns="band", values="value").reset_index()))
    A(f"\n**Status: {regime_status}.** The mixture is fitted on 10-minute medians over the full period ({fitw}). "
      "The bands are **descriptive data clusters** of kiln feed (Kiln-I C), not plant-defined operating modes. Other datasets receive band labels by timestamp, "
      "as part of the composite view. Minutes without a Kiln-I feed value (September, and trailing warm-up minutes) are `BASELINE_UNBANDED`. "
      "AFR on/off was tested and did not qualify as a stratum.\n")
    A("![regimes](figures/regimes_feed.png)\n")

    # 6
    A("## 6. Baseline Methodology\n")
    A("- **Population:** a cell is INCLUDED when all of these hold: `value_valid`, no column hold, `operating_state == RUNNING_PROXY`, and not hourly. "
      "Precedence for exclusion is MASKED > EXCLUDED_COLUMN > EXCLUDED_STATE > EXCLUDED_RESOLUTION.")
    A("- **Statistics** (`baseline_statistics.csv`): count, valid, missing, mean, median, std, min, max, P01…P99, IQR, MAD, scaled MAD (1.4826·MAD), CV, "
      "robust CV and 5% trimmed mean. Populations:")
    A("  - `BASELINE_RUNNING`: the primary baseline.")
    A("  - `BASELINE_FEED_BAND_k`: one per supported load band.")
    A("  - `REFERENCE_ALL_VALID`: all valid values regardless of state. It exists only to show contamination; it is not a baseline.")
    A(f"- **Robust vs classical:** `std_to_scaled_mad_ratio` > {H['outlier_sensitivity_ratio']} or |mean−median| > 0.5 scaled MAD means the mean/std baseline "
      "is **sensitive to extremes**. In that case median and MAD are the recommended centre and scale. Outliers are not removed; they stay in the population.")
    A(f"- **Uncertainty:** 1-minute values are strongly autocorrelated, so a 95% CI is given for the median of daily medians "
      f"(day-block bootstrap, {H['bootstrap_reps']} reps, fixed seed) instead of a naive i.i.d. CI.")
    A(f"- **Reference bands:** P05–P95 (`lower_reference`, `upper_reference`) and median ± {H['band_mad_k']}·scaled MAD (`robust_lower`, `robust_upper`). "
      f"**{BAND_LABEL}.**")
    A("- **Confidence (criteria C1–C8)** is graded **per population** using that population's own INCLUDED values. The rules are documented in "
      "`build_baseline_reference.py` and `baseline_confidence.csv`:")
    A("  - The criteria are C1 volume, C2 coverage, C3 completeness, C4 continuity (single-tag flatlines), C5 contamination (IQR-3 fences), "
      "C6 drift, C7 dispersion and C8 semantics.")
    A("  - C6 drift needs at least 2 evaluable months, each with at least 30 prior days, and a floored prior scale.")
    A("  - HIGH = all pass.")
    A("  - LOW = C5, C6 or C7 fails, or 3 or more criteria fail.")
    A("  - MEDIUM = otherwise.")
    A("  - INSUFFICIENT = held, or fewer than 1,440 values, or fewer than 7 valid days.")
    A("  - Tentative load-band populations are capped at MEDIUM.")
    A("- **Fit window:** every statistic and band is fitted on the full supplied period. That is acceptable for a descriptive baseline, but "
      "**later phases must refit on their own training window** before using a band, label or threshold to score a period. Otherwise the same data "
      "would both build and evaluate the reference.")
    A("- **Temporal integrity:** rolling statistics are trailing and stay within a segment. Drift compares each period only with data strictly before it. "
      "Regime smoothing is trailing.\n")
    A(f"Outlier sensitivity across baseline tags: {sens}.\n")

    # 7
    A("## 7. Parameter Baselines\n")
    A("Key tags per process family (BASELINE_RUNNING). The full list is in `baseline_reference_bands.csv`.\n")
    kt = bands[bands.baseline_population == "BASELINE_RUNNING"].copy()
    kt["key"] = list(zip(kt.dataset, kt.tag))
    show = kt[kt.key.isin(KEY_TAGS)][["process_family", "dataset", "tag", "original_name", "unit", "median", "scale", "lower_reference", "upper_reference",
                                      "stability_class", "baseline_confidence", "band_caution"]]
    show = show.rename(columns={"median": "centre (median)", "scale": "typical spread (scaled MAD)", "lower_reference": "typical range low (P05)",
                                "upper_reference": "typical range high (P95)"})
    A(md_table(show.sort_values(["process_family", "dataset"]), max_col=60))
    A("\nThe **typical range** is P05–P95 of baseline values. The robust band (median ± 3·scaled MAD) is kept in the CSV for later analysis only. "
      "Neither is a limit. `band_caution` flags ranges an operator could misread; they need plant review.\n")
    if regimes_supported:
        A("\nBaseline by load band for the Kiln-I key tags (median [P05–P95]):\n")
        kb = bands[(bands.dataset == "Kiln-I") & bands.tag.isin([t for e, t in KEY_TAGS if e == "Kiln-I"]) & bands.baseline_population.str.startswith("BASELINE_FEED")]
        kb = kb.assign(v=lambda d: d.apply(lambda r: f"{r['median']:.4g} [{r.p05:.4g}–{r.p95:.4g}]", axis=1))
        A(md_table(kb.pivot_table(index=["tag", "original_name", "unit"], columns="baseline_population", values="v", aggfunc="first").reset_index(), max_col=40))
    A("\nConfidence by population:\n")
    A(md_table(pd.crosstab(conf.population, conf.baseline_confidence).reset_index()))
    A("\nNumber of baseline tags per family and confidence (primary population):\n")
    A(md_table(fam[["process_family", "tags", "HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]]))
    A("\n![distributions](figures/distributions_key_tags.png)\n")
    A("### 7a. Current reference state (latest 7 days vs prior baseline)\n")
    A("Each dataset is dated from its own last baseline minute. Kiln-I data end earlier because its September workbook is unreadable. "
      "The window is compared only with baseline values **before** the window. This is a description, not a health assessment.\n")
    A(md_table(cur.groupby("dataset").as_of.first().reset_index()))
    ck = cur.assign(key=list(zip(cur.dataset, cur.tag)))
    ck = ck[ck.key.isin(KEY_TAGS)][["dataset", "tag", "original_name", "unit", "window_median", "reference_median", "reference_p05", "reference_p95",
                                     "shift_in_reference_scaled_mad", "window_median_inside_reference_p05_p95"]]
    A(md_table(ck, max_col=40))

    # 8
    A("## 8. Stability\n")
    A("The stability ratio is the median trailing 60-minute rolling std divided by the baseline scaled MAD. It compares short-term with overall variation. Classes are "
      "LOW (< 0.5), MODERATE (0.5–1.0) and HIGH (> 1.0); these are POC analytical heuristics.\n")
    A(md_table(stab.stability_class.value_counts().reset_index().rename(columns={"count": "tags"})))
    A("\nHighest short-term variation:\n")
    A(md_table(stab.sort_values("stability_ratio", ascending=False)[["dataset", "tag", "original_name", "unit", "stability_ratio", "rolling_std_60_median",
                                                                    "abs_rate_of_change_1min_p95", "high_variation_days"]].head(12), max_col=60))
    A("\nMost stable relative to overall spread:\n")
    A(md_table(stab.sort_values("stability_ratio")[["dataset", "tag", "original_name", "unit", "stability_ratio", "pct_minutes_within_robust_band",
                                                     "pct_days_median_within_p05_p95"]].head(12), max_col=60))
    rr = stab.dropna(subset=["rolling_std_60_median", "rolling_std_60_median_excl_repeated_rows"])
    rel = (rr.rolling_std_60_median_excl_repeated_rows / rr.rolling_std_60_median.replace(0, np.nan)).dropna()
    A(f"\nRepeated-row sensitivity: excluding exact repeated rows changes the median rolling-60 std by a median factor of {rel.median():.3f} "
      f"(P90 {rel.quantile(0.9):.3f}). Repeated rows therefore dampen short-term variation measures modestly.\n")
    A("![stability](figures/stability_rolling_std.png)\n")

    # 9
    A("## 9. Temporal Behaviour\n")
    mon = tmp[tmp.level == "MONTH"]
    A(f"Monthly observations: {mon.observation.value_counts().to_dict()}. A 'notable level shift' means |month median − prior median| ≥ "
      f"{H['drift_mad_units']} prior scaled MAD. It **describes** a change and does not interpret it as deterioration.\n")
    top = mon.dropna(subset=["shift_in_prior_scaled_mad"]).assign(a=lambda d: d.shift_in_prior_scaled_mad.abs()).sort_values("a", ascending=False)
    A(md_table(top[["dataset", "tag", "original_name", "unit", "period_start", "median", "prior_median", "shift_in_prior_scaled_mad", "iqr_ratio_vs_prior"]].head(15), max_col=40))
    hod = tmp[tmp.level == "HOUR_OF_DAY"].drop_duplicates(["dataset", "tag"]).sort_values("diurnal_amplitude_in_scaled_mad", ascending=False)
    A("\nLargest diurnal (hour-of-day) amplitude, in scaled MAD units:\n")
    A(md_table(hod[["dataset", "tag", "original_name", "unit", "diurnal_amplitude_in_scaled_mad"]].head(10), max_col=50))
    wk = tmp[(tmp.level == "WEEK")]
    A(f"\nWeekly level: {wk.observation.value_counts().to_dict()}. Daily aggregates for every tag are in `baseline_temporal_analysis.csv` (level=DAY).\n")
    A("![temporal](figures/temporal_daily_baseline.png)\n")

    # 10
    A("## 10. Multivariate Behaviour\n")
    A(f"This section uses 10-minute medians of INCLUDED values, and a bucket is used only if at least {H['mv_bucket_min_valid']} of its 10 minutes are valid. "
      "It describes associations only; nothing here is causal or a model.\n")
    c = mv[(mv.record == "CORRELATION") & (mv.view == "WITHIN_DATASET:Kiln-I")].assign(a=lambda d: d.spearman.abs()).sort_values("a", ascending=False)
    A("Strongest Kiln-I relationships (Spearman ρ):\n")
    A(md_table(c[["var_a", "name_a", "var_b", "name_b", "n_buckets", "pearson", "spearman"]].head(15), max_col=40))
    for view in ["WITHIN_DATASET:Kiln-I", "COMPOSITE"]:
        pe = mv[(mv.view == view) & (mv.record == "PCA_EXPLAINED_VARIANCE")]
        pl = mv[(mv.view == view) & (mv.record == "PCA_LOADING") & mv.var_a.isin(["PC1", "PC2"])]
        A(f"\nPCA ({view}; rank-based): explained variance " + ", ".join(f"{r.var_a} {r.value:.1%}" for r in pe.itertuples()) + ".\n")
        A(md_table(pl[["var_a", "var_b", "name_b", "value"]].rename(columns={"var_a": "component", "var_b": "tag", "value": "loading"}), max_col=40))
    cc = mv[(mv.record == "CORRELATION") & (mv.view == "COMPOSITE")].copy()
    cc = cc[cc.var_a.str.split("!").str[0] != cc.var_b.str.split("!").str[0]].assign(a=lambda d: d.spearman.abs()).sort_values("a", ascending=False)
    A(f"\nStrongest cross-dataset relationships ({COMPOSITE_LABEL}):\n")
    A(md_table(cc[["var_a", "name_a", "var_b", "name_b", "n_buckets", "spearman"]].head(12), max_col=40))
    A("\n![correlation](figures/corr_kiln_i.png)\n\n![pca](figures/pca_kiln_i.png)\n")

    # 11
    A("## 11. Data Limitations\n")
    lim = [
        f"The operating state is a **{PROXY_LABEL}** built from `Kiln MD`. If the plant defines `Kiln MD` differently, the baseline population changes.",
        "Equipment identity: whether the Kiln-* folders are pages of one kiln remains UNCONFIRMED. Cross-dataset results are composite views.",
        "Kiln-I September 2025 is **MISSING / UNAVAILABLE** (truncated workbook). All fuel, AFR, combustion, feed and burning-zone baselines cover April–August only.",
        "Kiln-IIIA April 2025 is missing. The May-repeat file was not loaded and was not relabelled.",
        "September restart ramps are measured on Kiln-IA hood temperature because Kiln-I feed is unavailable. The median uncensored ramp is a fallback, "
        "used only where no signal exists (2 very short runs, capped at their run length).",
        "No event ground truth exists, so 'normal' cannot be validated against known good or bad periods. The baseline may still contain deposit or coating effects.",
        "13 unit-review columns are held until plant confirmation, including `PC O/L | O2` (Kiln-I AA), the CBS BH temperatures in amps, and `Bypass Percent`.",
        "Many tags show month-to-month level shifts (criterion C6), so a single pooled baseline blends operating periods.",
        f"The frozen export window {fw.window_start.iloc[0]}–{fw.window_end.iloc[0]} is masked. Repeated rows (up to 32% in CBS-II) suggest the historian holds values.",
        "Load bands are TENTATIVE: they are supported on the full data but reproduced in only a minority of bootstrap resamples. Load varies more continuously than three discrete regimes would imply.",
        "In September the operating state rests on Kiln MD plus Kiln-IA hood temperature, because Kiln-I feed is unavailable. Excluding those minutes shifts some baselines "
        "(see the `excl_state_without_kiln_i_feed_evidence` sensitivity).",
        "All bands, labels and statistics are fitted on the full supplied period. Later phases must refit on a training window to avoid evaluating on data that built the reference.",
        "No fuel quality, calorific value, RDF split or clinker quality data exist, so these families cannot be baselined.",
        "There are two specific-heat signals. Kiln-I F `Sp.Heat | Sp.Heat` and Kiln-I G `Sp.Heat` differ in level by about 60 kcal/kg. Kiln-I G and Kiln-IIIA X "
        "`Sp.Heat Consumtion` are the same signal: identical values in Phase 1 and ρ≈1 here. The plant must say which specific-heat tag is authoritative before Phase 3 relies on one.",
        "Some reference ranges contain values an operator may find implausible: negative current and power on the IKN cooler drive, negative NOx P05, and Kiln-I inlet O2 "
        "P95 near atmospheric levels. They are reported as observed (`band_caution`), not corrected.",
    ]
    for x in lim:
        A(f"- {x}")
    A("\nUnresolved plant questions: (1) Are all Kiln-* folders one kiln line? (2) What is `Kiln MD`, and does 0 mean stopped? (3) What does 99999 / 9999 mean? "
      "(4) Can the plant re-export Kiln-I September and Kiln-IIIA April? (5) Can it supply event logs for coating, ring, stops and cleaning? "
      "(6) Can it supply fuel and clinker lab data? (7) What is the historian timezone and interpolation setting? (8) Can it confirm the units of the held columns?\n")

    # 12
    A("## 12. Baseline Readiness\n")
    A("Readiness is per process family, using the rule in `build_baseline_reference.py`. It is conditional on the unconfirmed operating-state proxy.\n")
    A(md_table(fam[["process_family", "tags", "HIGH", "MEDIUM", "LOW", "INSUFFICIENT", "baseline_readiness", "datasets"]], max_col=100))
    A("\nHIGH and READY describe **evidence for the baseline**. They are not assessments of equipment or process health.\n")
    A("\nCLINKER QUALITY and EVENT / MAINTENANCE: **INSUFFICIENT**. No source data exists for them (Phase 1).\n")
    A("**Overall baseline status: PARTIAL.** A traceable empirical baseline exists for every family with data. It is conditional on the operating-state proxy and "
      "the equipment mapping, and no family meets the READY rule.\n")

    # 13
    A("## 13. Phase 3 Inputs\n")
    A("Phase 3 (Efficiency Deterioration KPI) can consume:\n")
    for f_, why in [
        ("data/curated/<dataset>_baseline.parquet", "baseline-approved 1-minute values with full traceability (source file, row, original name, unit)"),
        ("data/processed/<dataset>.parquet", "every cell with masks, operating state, load band and baseline status (for non-baseline periods)"),
        ("data/processed/operating_state_timeline.parquet / regime_timeline.parquet", f"{PROXY_LABEL} state and load-band labels per minute"),
        ("outputs/baseline_reference_bands.csv", "centre, scale and reference bands per tag and population (not limits)"),
        ("outputs/baseline_statistics.csv", "full univariate and robust statistics, including per load band"),
        ("outputs/baseline_stability.csv / baseline_temporal_analysis.csv", "short-term variation and the prior-referenced drift history"),
        ("outputs/multivariate_baseline.csv", "normal-operation correlation structure and PCA loadings"),
        ("outputs/baseline_confidence.csv / baseline_family_readiness.csv", "which tags are usable, with what confidence and why"),
        ("outputs/column_holds.csv", "tags that must not be used until the plant confirms them"),
        ("outputs/baseline_current_reference.csv", "latest 7-day state per dataset against the prior-only baseline, with an as-of date per dataset"),
    ]:
        A(f"- `{f_}`: {why}.")
    A("\nCandidate efficiency-related signals with a baseline, for Phase 3 to evaluate: Kiln-I `Sp.Heat` (F, G), Kiln-I `Coal Firing | Sp.Power` (E), "
      "Kiln-IIIA `Sp.Heat Consumtion` (X), `Sp.Power` (W), `Tota l power` (V), `Clinker TPH` (M), and Kiln-I feed and coal firing rates. "
      "Their confidence is in `baseline_confidence.csv`. Phase 3 must define the KPI itself; Phase 2 defines none.\n")

    # appendix
    A("## Appendix A — Validation gates\n")
    A(md_table(val, max_col=160))
    rv = PHASE_DIR / "reviews" / "REVIEW_LOG.md"
    if rv.exists():
        A("\n## Appendix B — Reviews\n")
        A(rv.read_text(encoding="utf-8"))
    A("\n## Appendix C — Reproducibility\n")
    A("```bash\ncd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-02-baseline/scripts\n"
      "../../.venv/bin/python run_phase2.py --clean\n```\n")
    A(f"POC analytical heuristics (not plant limits): `{json.dumps(H)}`\n")
    md = "\n".join(L)
    (REPORTS / "PHASE_2_NORMAL_OPERATING_BASELINE.md").write_text(md, encoding="utf-8")
    from markdown_it import MarkdownIt
    css = (":root{--bg:#fff;--fg:#1d2330;--line:#d9dde5;--head:#f3f5f8;--accent:#0b5cad}"
           "@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e6e9ef;--line:#2c323c;--head:#1c2027;--accent:#6aa9ff}}"
           "body{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:16px}"
           "table{border-collapse:collapse;display:block;overflow-x:auto;font-size:12px;margin:8px 0}th,td{border:1px solid var(--line);padding:3px 6px;text-align:left}"
           "th{background:var(--head)}img{max-width:100%;background:#fff}blockquote{border-left:3px solid var(--accent);margin:0;padding:4px 12px}"
           "code,pre{background:var(--head)}pre{padding:8px;overflow-x:auto}h2{border-bottom:1px solid var(--line);margin-top:2em}")
    body = MarkdownIt("commonmark").enable("table").render(md)
    (REPORTS / "PHASE_2_NORMAL_OPERATING_BASELINE.html").write_text(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Phase 2 Baseline</title><style>{css}</style></head><body>{body}</body></html>", encoding="utf-8")
    lg.info("wrote reports/PHASE_2_NORMAL_OPERATING_BASELINE.md / .html")


if __name__ == "__main__":
    main()
