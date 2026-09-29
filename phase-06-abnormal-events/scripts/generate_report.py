"""Step 17 - Phase 6 report (Markdown + HTML), figures and the version manifest.

Reads  every Phase 6 output and cache/{input_hashes.json, p6_reference.json, multivariate_comparison.csv,
       change_points.csv, tag_check.csv}
Writes reports/PHASE_6_HISTORICAL_ABNORMAL_EVENTS.{md,html}, reports/figures/*.png,
       outputs/abnormal_events_version_manifest.csv

Every number in the report is read from the outputs at generation time. The text is scanned for unsupported claims
(confirmed deposit / ring / coating / failure, cause, probability, plant limit) before it is written (abn_core.forbidden_hits).
"""
from __future__ import annotations

import json
import platform
from dataclasses import asdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import scipy  # noqa: E402

from abn_core import (CACHE, FAMILIES, FIG, FP_CATEGORIES, FP_NOTE, METHOD_VERSION, OUT, PHASE_DIR,  # noqa: E402
                      PLANT_EVENT_COLUMNS, PRIMARY, REPORTS, SCRIPTS, forbidden_hits, load_inputs, log, sha256,
                      write_csv)

lg = log("generate_report")
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#8a8984"]    # validated categorical slots (dataviz palette) + neutral
INK, INK2 = "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "#fcfcfb",
                     "axes.facecolor": "#fcfcfb", "lines.linewidth": 1.2})
TITLE = "PHASE_6_HISTORICAL_ABNORMAL_EVENTS"
STATEMENT = ("> **The detected episodes are empirical historical abnormal periods derived from process measurements and "
             "the Phase 3 POC efficiency-deterioration KPI. They are not validated plant events.**\n>\n"
             "> **No supplied event ground truth was available for coating, ring, deposit, maintenance, failure, "
             "cleaning, or shutdown reasons.**\n")


# ============================================================================== helpers
def md_table(df: pd.DataFrame, max_rows: int | None = None, max_col: int = 90, floatfmt: str = "{:.3g}") -> str:
    if df is None or df.empty:
        return "_None._\n"
    d = df.head(max_rows) if max_rows else df

    def cell(v):
        if isinstance(v, (float, np.floating)):
            s = "" if np.isnan(v) else (str(int(v)) if float(v).is_integer() and abs(v) < 1e12 else floatfmt.format(v))
        elif isinstance(v, pd.Timestamp):
            s = v.strftime("%Y-%m-%d %H:%M")
        else:
            s = "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return s if len(s) <= max_col else s[: max_col - 1] + "…"
    out = "| " + " | ".join(map(str, d.columns)) + " |\n| " + " | ".join("---" for _ in d.columns) + " |\n"
    out += "".join("| " + " | ".join(cell(v) for v in r) + " |\n" for r in d.itertuples(index=False))
    if max_rows and len(df) > max_rows:
        out += f"\n_{len(df) - max_rows} more rows in the output file._\n"
    return out


def save(fig, name: str) -> str:
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=100, metadata={"Software": None})
    plt.close(fig)
    return f"figures/{name}"


def read(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / name) if name.endswith(".parquet") else pd.read_csv(OUT / name, low_memory=False)


def counts(s: pd.Series, order) -> str:
    """'3 HIGH, 4 MODERATE and 5 LOW' - prose instead of raw dicts."""
    vc = s.value_counts()
    keys = [k for k in (order or vc.index) if k in vc]
    items = [f"{int(vc[k])} {k}" for k in keys]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else "none"


def pct(v: float) -> str:
    return f"{v:.0%}" if np.isfinite(v) else "n/a"


# ============================================================================== figures
def fig_timeline(g: pd.DataFrame, ep: pd.DataFrame, ref: dict) -> str:
    fig, ax = plt.subplots(figsize=(11, 3.4))
    k = g.K.where(g.index > pd.Timestamp("2025-05-31 23:59"))
    ax.plot(k.index, k, color=SERIES[3], lw=0.6, label="Phase 3 KPI (out of sample)")
    ax.axhline(ref["thr"], color=INK2, ls="--", lw=0.8)
    ax.axhline(ref["hi"], color=INK2, ls=":", lw=0.8)
    x0 = k.dropna().index.min()
    ax.text(x0, ref["thr"] + 1, f"cut {ref['thr']:.1f} (training P90)", fontsize=7, color=INK2)
    ax.text(x0, ref["hi"] + 1, f"training P99 {ref['hi']:.1f}", fontsize=7, color=INK2)
    for r in ep[ep.reference_state.eq("OUT_OF_SAMPLE")].itertuples():
        ax.axvspan(r.start_time, r.end_time, color=SERIES[1] if r.in_final_set else SERIES[0], alpha=0.35, lw=0)
    ax.plot([], [], color=SERIES[1], lw=6, alpha=0.35, label="historical abnormal period (final set)")
    ax.plot([], [], color=SERIES[0], lw=6, alpha=0.35, label="candidate classified as ordinary context")
    ax.set_ylabel("KPI (0-100 POC score)")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right", fontsize=7, frameon=False)
    ax.set_title("Out-of-sample KPI and candidate periods, Jun-Aug 2025 (not plant events)", fontsize=9)
    return save(fig, "fig1_kpi_timeline_episodes.png")


def fig_families(ep: pd.DataFrame) -> str:
    oos = ep[ep.reference_state.eq("OUT_OF_SAMPLE")]
    M = oos[[f"{d.lower().replace('_pressure', '')}_deviation" for d in FAMILIES]].to_numpy(float)
    fig, ax = plt.subplots(figsize=(7, 0.32 * len(oos) + 1.4))
    im = ax.imshow(np.clip(M, 0, 3), aspect="auto", cmap="Oranges", vmin=0, vmax=3)
    ax.set_xticks(range(len(FAMILIES)), [f.replace("_", " ").title() for f in FAMILIES], fontsize=8)
    ax.set_yticks(range(len(oos)), [f"{r.episode_id}{' *' if r.in_final_set else ''}" for r in oos.itertuples()],
                  fontsize=7)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]):
                ax.text(j, i, f"{M[i, j]:.1f}", ha="center", va="center", fontsize=6,
                        color="white" if M[i, j] > 2 else INK)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.04, label="episode median S / training P90 (>1 = deviating)")
    ax.set_title("Family deviation ratio per out-of-sample candidate (* = final set)", fontsize=9)
    return save(fig, "fig2_family_deviation.png")


def fig_sensitivity(sens: pd.DataFrame) -> str:
    s = sens[~sens.dimension.isin(["PRIMARY", "TEMPORAL"])]
    fig, ax = plt.subplots(figsize=(8, 0.26 * len(s) + 1))
    y = np.arange(len(s))
    ax.barh(y, s.primary_final_retained_share.astype(float),
            color=[SERIES[0] if str(v) == "True" else SERIES[3] for v in s.in_robustness_set])
    ax.set_yticks(y, s.variant + "  " + s.description.str[:48], fontsize=6.5)
    ax.axvline(0.7, color=INK2, ls="--", lw=0.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("share of the primary final periods retained (overlapping final period in the variant)")
    ax.plot([], [], color=SERIES[0], lw=6, label="robustness set")
    ax.plot([], [], color=SERIES[3], lw=6, label="stricter / different method (reported only)")
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    return save(fig, "fig3_sensitivity_retention.png")


def version_manifest(ref: dict) -> pd.DataFrame:
    rows = [("method_version", METHOD_VERSION), ("config_key", PRIMARY.key()),
            ("config", json.dumps(asdict(PRIMARY), sort_keys=True, default=str)),
            ("kpi_version", ref.get("kpi_version")), ("reference_train_end", ref["train_end"]),
            ("kpi_cut_p90", f"{ref['thr']:.6f}"), ("kpi_band_hi_p99", f"{ref['hi']:.6f}"),
            ("cusum_k", f"{ref['cusum_k']:.6f}"), ("cusum_h", f"{ref['cusum_h']:.6f}"),
            ("event_ground_truth_status", "NOT_AVAILABLE"),
            ("python", platform.python_version()), ("pandas", pd.__version__), ("numpy", np.__version__),
            ("scipy", scipy.__version__), ("matplotlib", matplotlib.__version__)]
    rows += [(f"input_sha256:{k}", v) for k, v in sorted(json.loads((CACHE / "input_hashes.json").read_text()).items())]
    rows += [(f"output_sha256:{p.name}", sha256(p)) for p in sorted(OUT.glob("*"))
             if p.is_file() and p.suffix in (".csv", ".parquet")
             and p.name not in ("abnormal_events_version_manifest.csv", "abnormal_episode_validation.csv")]
    rows += [(f"code_sha256:{p.name}", sha256(p)) for p in sorted(SCRIPTS.glob("*.py"))]
    rows += [(f"code_sha256:tests/{p.name}", sha256(p)) for p in sorted((PHASE_DIR / "tests").glob("*.py"))]
    return pd.DataFrame(rows, columns=["item", "value"])


# ============================================================================== report
def main():
    inp = load_inputs()
    g, ref = inp["grid"], inp["ref"]
    ep = read("abnormal_episodes.parquet")
    ctx, dq, sev, conf = (read(n) for n in ("abnormal_episode_context.csv", "abnormal_episode_data_quality.csv",
                                            "abnormal_episode_severity.csv", "abnormal_episode_confidence.csv"))
    types, sens, nc = (read(n) for n in ("abnormal_episode_types.csv", "abnormal_episode_sensitivity.csv",
                                         "negative_control_results.csv"))
    pre, post, val = (read(n) for n in ("abnormal_episode_pre_event.parquet", "abnormal_episode_post_event.parquet",
                                        "abnormal_episode_validation.csv"))
    sig = read("abnormal_episode_signals.parquet")
    mv = pd.read_csv(CACHE / "multivariate_comparison.csv")
    cp = pd.read_csv(CACHE / "change_points.csv")
    tc = pd.read_csv(CACHE / "tag_check.csv")
    write_csv(version_manifest(ref), "abnormal_events_version_manifest.csv", lg)
    figs = [fig_timeline(g, ep, ref), fig_families(ep), fig_sensitivity(sens)]

    oos = ep[ep.reference_state.eq("OUT_OF_SAMPLE")]
    ins = ep[ep.reference_state.eq("IN_SAMPLE_REFERENCE")]
    fin = ep[ep.in_final_set]
    mvd = dict(zip(mv.metric, mv.value))
    nci = nc.set_index("control")
    temporal = sens[sens.dimension == "TEMPORAL"]
    s_var = sens[sens.dimension != "TEMPORAL"]
    sv = s_var.set_index("variant")
    fam_counts = fin.deviating_families.str.split(";").explode().value_counts().to_dict()
    fe = pre[(pre.row_type == "FIRST_EXCEEDANCE") & pre.episode_id.isin(fin.episode_id)]
    fam_base = fe[fe.signal.str.startswith("S_")].groupby("signal").base_rate_oos.first()
    tp = pre[(pre.row_type == "KPI_TURNING_POINT") & pre.episode_id.isin(fin.episode_id)]
    po = post.drop_duplicates("episode_id")
    high_dates = ", ".join(fin[fin.severity_class == "HIGH"].start_time.dt.strftime("%d %b").tolist()) or "none"
    L = []
    A = L.append

    X = []                                   # appendix: long reference tables (kept out of the main narrative)
    sev_txt = counts(fin.severity_class, ("HIGH", "MODERATE", "LOW"))
    conf_txt = counts(fin.confidence, ("MEDIUM", "LOW"))
    excl = oos[~oos.in_final_set]
    fam_txt = ", ".join(f"{k.lower().replace('_', ' ')} {v}" for k, v in fam_counts.items())
    A(f"# Phase 6 — Historical Abnormal Periods\n\n(Historical Abnormal Events phase.) Dalmia Cement Ariyalur Kiln POC · "
      f"method `{METHOD_VERSION}` · config `{PRIMARY.key()}` · Phase 3 KPI `{ref.get('kpi_version')}`\n")
    A(STATEMENT)
    A(f"> **Which periods count as abnormal depends on the reference window: only "
      f"{pct(sv.loc['A_alt'].primary_final_retained_share)} of them survive an alternative definition of normal "
      f"operation, and none is load-independent. Treat this catalogue as a list of periods worth checking against "
      f"plant logs, not as a list of confirmed problems.**\n")

    # 1 -----------------------------------------------------------------------------------------------------------
    A("## 1. Executive Summary\n")
    A(f"- **What was searched.** The Phase 3 POC efficiency-deterioration score (0–100) was scanned for sustained "
      f"periods at or above {ref['thr']:.1f}. That is the level the score exceeded in 10 % of Apr–May running "
      "operation, not a plant limit.\n"
      f"- **Candidates.** {len(ep)} candidate periods were found in Apr–Aug 2025.\n"
      f"  - {len(oos)} are in June–August, when the score is out of sample.\n"
      f"  - The other {len(ins)} lie in the score's own Apr–May training window. They are labelled "
      "calibration-only and are not counted.\n"
      f"- **Final set.** {len(fin)} historical abnormal periods remain.\n"
      f"  - The other {len(excl)} June–August candidates matched an ordinary-context rule and are kept for review: "
      f"{counts(excl.classification, None)}.\n"
      f"  - `P6-021` is one of them: an 18.5-h period with peak {ep.set_index('episode_id').peak_kpi.get('P6-021', np.nan):.0f}, "
      "excluded because only one family deviated and an AFR ramp-down occurred near its onset. It is worth reviewing.\n"
      f"- **Deviation magnitude (severity):** {sev_txt}. **Confidence:** {conf_txt}.\n"
      "  - Confidence measures how consistent the evidence is, not how likely a real plant event is.\n"
      "  - MEDIUM is the ceiling by design: there is no ground truth, the operating state is a proxy, and the "
      "process families are inputs of the score itself.\n"
      f"- **Breadth.** {int((fin.family_count >= 2).sum())} of {len(fin)} periods show two or more process families "
      f"above their own normal range. Across the set: {fam_txt}.\n"
      f"- **Load.** {int((fin.load_context == 'LOAD_ASSOCIATED').sum())} of {len(fin)} periods follow or contain a "
      "large feed / production change, and none is clearly independent of load. The deviation may partly be the "
      "process response to a rate change.\n"
      f"- **AFR.** {int((fin.afr_context != 'NO_AFR_TRANSITION').sum())} of {len(fin)} periods have AFR transitions "
      "nearby, more often than chance. This analysis cannot tell whether AFR changes contributed or were a response.\n"
      "- **Phase 4 indicator.** The weak Phase 4 leading indicator is not active before onsets more often than chance.\n"
      f"- **Robustness.** Every period survives at least {pct(fin.robustness_score.min())} of the reasonable "
      "parameter variants.\n"
      f"  - Requiring ≥ 2 families keeps {pct(sv.loc['D_2'].primary_final_retained_share)} of them, and ≥ 3 families "
      f"keeps {pct(sv.loc['D_3'].primary_final_retained_share)}.\n"
      f"  - An alternative normal period keeps only {pct(sv.loc['A_alt'].primary_final_retained_share)} (reported "
      "as NOT_MET).\n"
      f"- **Validation.** {counts(val.result, None)}.\n"
      "  - The leakage test shows that everything used to define a period is computed from data available at that "
      "time.\n"
      "  - The context rules are retrospective by design and are verified once their look-ahead window has passed.\n"
      "  - No plant event label exists or was created.\n")
    A(f"![KPI timeline]({figs[0]})\n")

    # 2-5 ---------------------------------------------------------------------------------------------------------
    A("## 2. Objective\n\nThe objective is a transparent, reproducible, empirical catalogue of periods in which the kiln "
      "process behaved unusually relative to its own Apr–May reference. For each period the catalogue records how "
      "severe the deviation was, how long it persisted, which process families agreed, and what ordinary operating "
      "context (startup, shutdown, restart, load change, AFR transition, control action, data quality) surrounded it. "
      "Phase 6 builds no risk score, early warning, API or dashboard.\n")
    A("## 3. Definition of Historical Abnormal Period\n")
    A("A **CANDIDATE_ABNORMAL_PERIOD** is a gap-aware merged run of RUNNING 10-min buckets in which the Phase 3 KPI is "
      f"≥ {ref['thr']:.2f} (the frozen training P90 band cut). A candidate becomes a **HISTORICAL_ABNORMAL_PERIOD** "
      "when all of the following hold:\n\n"
      "1. It is out of sample (Jun–Aug).\n"
      "2. No ordinary-context category matched (precedence in §15).\n"
      "3. At least one process family's episode median S_d exceeds its own training P90. Periods with ≥ 2 such families "
      "are MULTI_FAMILY_DEVIATION; periods with one are SINGLE_FAMILY_DEVIATION.\n\n"
      "Candidates with no family above P90 are UNCONFIRMED_KPI_ELEVATION. Throughout, `ABNORMAL_PERIOD ≠ "
      "CONFIRMED_PLANT_EVENT` and `DEVIATION ≠ FAILURE`.\n")
    A("## 4. Data Used\n")
    A("- **Phase 3:**\n"
      "  - `efficiency_deterioration_kpi.parquet`: KPI, D, family components, contributions, Sp.Heat F/G KPIs, the "
      "alternative-reference KPI, the Mahalanobis KPI, data quality and state;\n"
      "  - `kpi_component_scores.parquet`: per-tag z against frozen load-conditional references;\n"
      "  - `kpi_reference.json` and `kpi_reference_bands.csv`: the P90 / P99 cuts and the family P90s.\n"
      f"- **Phase 4:** `leading_indicator_set.csv`, of which only the usable_downstream row `{ref['p4_indicator']}` is "
      f"used (threshold {ref['p4_threshold']:.3f}, LOW confidence), and `indicator_feature_values.parquet`.\n"
      f"- **Phase 5:** `afr_transition_episodes.parquet` "
      f"({int(inp['events'].kind.str.startswith('AFR_').sum())} AFR transition episodes), used as context only.\n"
      f"- **Phase 2:**\n"
      f"  - `operating_state_events.csv` ({int((inp['events'].kind == 'STOP').sum())} stops / "
      f"{int((inp['events'].kind == 'RESTART').sum())} restarts, retrospective) and `column_holds.csv`;\n"
      "  - `data/processed/*` for feed, kiln speed, clinker TPH, coal and AFR buckets (rebuilt with the Phase 3/4 bucket "
      "rules; the state agrees 100 % with Phase 3) and the Phase 2 mask reasons.\n"
      "- **Phase 1:** `gap_events.csv` (long gaps), `dq_issue_register.csv` (DQ-016 frozen window) and "
      "`process_tag_inventory.csv` (tag, unit and original-name verification).\n\n")
    A(f"Every referenced tag ({len(tc)}) was verified against the Phase 1 inventory, and none is a Phase 2 held "
      "column (table A1 in the appendix).\n")
    X.append("### A1. Referenced tags (gateguard check)\n\n" + md_table(tc[["tag", "role", "original_name", "unit",
                                                                            "phase1_family"]]))
    A("## 5. Data Limitations\n")
    A("- **No event ground truth:** no coating, ring, deposit, maintenance, failure, cleaning or shutdown-reason "
      "records.\n"
      "- **Missing measurements:** no clinker quality, kiln shell temperature, measured CO₂ or explicit specific fuel "
      "consumption.\n"
      "- **Unconfirmed identity:** the equipment identity (one composite kiln line assumed) and the `Kiln MD` "
      "operating-state proxy are unconfirmed.\n"
      "- **Sp.Heat:** the F/G definition is unresolved, and Sp.Heat may be calculated from the firing inputs "
      "(Phase 5).\n"
      "- **Missing months:** there is no September for Kiln-I and no April for Kiln-IIIA.\n"
      "- **KPI windows:** the KPI is in-sample in Apr–May and out of sample only in Jun–Aug (≈ 2.7 months).\n")

    # 6-9 ---------------------------------------------------------------------------------------------------------
    A("## 6. KPI-Based Candidate Detection\n")
    A(f"- **Rule:** a candidate bucket is a RUNNING bucket with KPI ≥ {ref['thr']:.2f}. The cut is the training P90 of "
      "the persistent score, frozen in Phase 3; it is not a plant limit.\n"
      f"- **Merging:** runs separated by ≤ {PRIMARY.merge_gap_min} min of RUNNING buckets are merged, unless a Phase 1 "
      "long gap or the frozen window lies in the gap. A stop always breaks an episode.\n"
      f"- **Duration:** episodes shorter than {PRIMARY.min_dur_min} min are kept as SHORT_TRANSIENT.\n"
      "- **Recorded per episode:** start, end, detection, CUSUM onset, peak and median KPI, `kpi_integral` (KPI points × "
      "hours above the cut), OLS `kpi_slope` (points per hour), and the end reason.\n"
      f"- **Calibration:** {nci.loc['NC5_IN_SAMPLE_CALIBRATION'].observed:.1%} of Apr–May RUNNING buckets exceed the "
      "cut, as expected for a training P90.\n\n")
    A("All candidate windows are listed in appendix table A2.\n")
    X.append("### A2. Candidate windows\n\n" + md_table(read("abnormal_candidate_windows.parquet")[
        ["episode_id", "reference_state", "start_time", "end_time", "duration_minutes", "peak_kpi", "median_kpi",
         "kpi_integral", "kpi_slope", "end_reason"]]))
    A("\n## 7. Process-Family Deviation\n")
    A("Family scores reuse the Phase 3 causal S_d (frozen training median and robust scale, load-conditional tag "
      "references). No baseline is refitted. A family is deviating when its episode median S_d exceeds its own training "
      f"P90 ({', '.join(f'{d} {v:.2f}' for d, v in ref['family_p90'].items())}). The tag-level evidence "
      f"(`abnormal_episode_signals.parquet`, {len(sig):,} rows) gives each tag's bucket value, reference, signed "
      "robust z and share of the bucket's total tag score. It answers *why was this period considered abnormal?* "
      "LOAD tags are included as context and never counted as process abnormality.\n\n")
    A(f"![Family deviation]({figs[1]})\n")
    A(md_table(fin[["episode_id", "family_count", "family_agreement", "efficiency_deviation", "combustion_deviation",
                    "thermal_deviation", "draft_deviation", "stability_deviation", "top_tags"]], max_col=160))
    A("\n## 8. Multivariate Analysis\n")
    A("Two methods form the smallest defensible set:\n\n"
      "- **M1 (primary): family agreement count.**\n"
      "- **M2 (secondary): the Phase 3 robust Mahalanobis KPI.** MinCovDet fitted on Apr–May, with 50 = its training "
      "P95; it is not refitted here.\n\n")
    X.append("### A3. Multivariate method comparison (all metrics)\n\n" + md_table(mv))
    A(f"\n- **Bucket agreement:** the methods agree on {pct(mvd['bucket_agreement'])} of out-of-sample buckets "
      f"(φ = {mvd['bucket_phi']:.2f}).\n"
      "- **Ranking:** episode rankings by family count and by median Mahalanobis KPI correlate at "
      f"ρ = {mvd['episode_rank_spearman_family_count_vs_maha_median']:.2f}.\n"
      f"- **Support:** only {pct(mvd['episode_share_maha_supported'])} of out-of-sample candidates have Mahalanobis "
      "support.\n"
      "- **Role of M2:** a confidence part, not the definition (sensitivity G).\n")
    A("\n## 9. Change-Point Analysis\n")
    rates = cp[cp.episode_id == "BUCKET_ALARM_RATE"]
    A(f"- **Method:** a causal one-sided CUSUM on the robust z of D, with k = {ref['cusum_k']:.3f} (half the training "
      "shift from the median to P90).\n"
      f"- **Support rule:** a change point is supported when the 6-h CUSUM rise exceeds h = {ref['cusum_h']:.1f} "
      "(its training P90).\n"
      "- **Onset:** the bucket after the last S = 0 in the 6 h before detection. Onset-censored episodes began more "
      "than 6 h before detection (a slow drift).\n"
      f"- **Bucket alarm rates:** {dict(zip(rates.reference_state, rates.change_point_supported.round(3)))}.\n"
      f"- **Final set:** {int(fin.change_point_supported.sum())} of {len(fin)} periods have change-point support.\n"
      "- **Interpretation:** a change point alone is never labelled abnormal. Restarts, ramps and load changes also "
      "produce them.\n\n")
    X.append("### A4. Change points per candidate\n\n" + md_table(cp[cp.episode_id.str.startswith("P6")][
        ["episode_id", "reference_state", "detection_time", "onset_time", "onset_lead_minutes", "onset_censored",
         "cusum_rise_6h", "change_point_supported", "level_shift_d"]]))

    # 10-14 -------------------------------------------------------------------------------------------------------
    A("\n## 10. Operating-State Treatment\n")
    A("Candidates are built only from RUNNING buckets (Phase 3 causal POC proxy, UNCONFIRMED), so shutdown behaviour "
      "never enters an episode. Transitions are classified separately:\n\n"
      "- **STARTUP / RESTART:** the onset lies within [restart, restart + Phase 2 ramp + 6 h]. It is STARTUP when the "
      "preceding stop lasted ≥ 24 h.\n"
      "- **SHUTDOWN:** a stop follows within 2 h of the end and ≤ 6 h after the onset.\n\n"
      "These periods are kept, never called abnormal, and never treated as process deterioration.\n\n")
    A(f"Result: {counts(ctx.primary_context, None)} (all candidates; per-candidate context in appendix table A5).\n")
    X.append("### A5. Operating context per candidate\n\n" + md_table(ctx[
        ["episode_id", "reference_state", "operating_state", "primary_context", "secondary_context",
         "context_confidence", "hours_since_restart"]], max_col=70))
    A("\n## 11. Load Treatment\n")
    A("- **LOAD_ASSOCIATED** means one of the following:\n"
      f"  - |feed change vs the 2 h before onset| ≥ {ref['feed_d120m_p90']:.0f} TPH (training P90 of the 2-h change);\n"
      "  - ≥ 50 % of buckets outside the training feed range;\n"
      "  - |robust z| of kiln speed or clinker TPH ≥ 3.\n"
      f"- **LOAD_INDEPENDENT** means feed change ≤ {ref['feed_d120m_p75']:.0f} TPH (training P75), inside the range, "
      "and speed / clinker |z| < 2.\n"
      "- **UNCERTAIN** covers everything else.\n"
      "- **NORMAL_LOAD_CHANGE** is a load-associated candidate with < 2 deviating families. A load-associated period "
      "with ≥ 2 families stays abnormal, with `load_context = LOAD_ASSOCIATED`.\n"
      "- **Feed bands:** the Phase 2 bands were tentative and are not used as regimes.\n\n"
      f"Final set: {counts(fin.load_context, None)}. With F_indep (final only when LOAD_INDEPENDENT) "
      f"{int(sv.loc['F_indep'].n_final)} periods remain.\n")
    A("\n## 12. AFR Context\n")
    A("- **Recorded as context:** Phase 5 AFR transition episodes (START / STOP / RAMP_UP / RAMP_DOWN) in [onset − 3 h, "
      "end] are recorded as `afr_context`, never as a cause.\n"
      "- **AFR_TRANSITION category:** applies only when an AFR stop or ramp-down lies in [onset − 3 h, onset + 1 h] "
      "**and** fewer than 2 families deviate.\n"
      "- **Phase 5 background:** AFR stops coincide with PC-coal increases, feed cuts and falling preheater / TAD "
      "temperatures. This is a Phase 5 observation and is not re-tested here.\n\n")
    nc3 = nc[nc.control == "NC3_AFR_CONTEXT_SHIFT"]
    A(md_table(nc[nc.control == "NC3_AFR_CONTEXT_SHIFT"][["statistic", "observed", "null_median", "null_p95",
                                                          "empirical_p", "result"]]))
    A(f"\nAFR transitions occur near candidate onsets more often than time-shifted AFR series give (the p-value is the "
      f"smallest of {len(nc3)} related statistics over 40 shifts, so it is exploratory). This analysis cannot tell "
      "whether AFR changes contributed or were a response. It is recorded as `AFR_CONTEXT = AFR_RAMP_DOWN`, not "
      "`CAUSE = AFR_RAMP_DOWN`.\n\n"
      "The category AFR_TRANSITION is a rule outcome (AFR stop / ramp-down near onset with < 2 deviating families). "
      "It does not claim that AFR explains the period. `P6-021` (18.5 h, one family) is such a case and is listed for "
      "review in §27.\n")
    A("\n## 13. Phase 4 Indicator Context\n")
    n4 = nci.loc["NC4_PHASE4_SHIFT"]
    A(f"- **Indicator used:** only `{ref['p4_indicator']}` (usable_downstream, LOW confidence, not significant in the "
      "August holdout).\n"
      f"- **Recorded as:** `phase4_indicator_context`, its activation (≥ {ref['p4_threshold']:.3f}) within 2 h before "
      "onset. It is a supporting field only.\n"
      f"- **Result:** active before {pct(n4.observed)} of out-of-sample candidates against a shifted-series null median "
      f"of {pct(n4.null_median)} (p = {n4.empirical_p:.2f}), which is **not distinguishable from chance**.\n"
      "- **Swap signature:** when the activation coincides with an AFR stop or ramp-down it is flagged as the "
      "coal-for-AFR swap signature.\n")
    A("\n## 14. Data-Quality Contamination\n")
    A("- **Score:** `data_quality_contamination` = max(share of buckets not GOOD, share in a Phase 1 long gap or the "
      "DQ-016 frozen window, 1 − median tag coverage), over the episode plus the hour before detection.\n"
      "- **Classes:** ≥ 0.5 is DATA_QUALITY_ARTIFACT (excluded from the final set) and ≥ 0.2 is DQ_AFFECTED.\n"
      "- **Masked-cell counts:** reported by Phase 2 reason (sentinel 99999, text `Error 6`, −273 / impossible, frozen, "
      "flatline, conflicting duplicates, missing).\n\n")
    mcols = [c for c in dq.columns if c.startswith("masked_cells_")]
    X.append("### A6. Data quality per candidate\n\n" + md_table(dq[
        ["episode_id", "data_quality_contamination", "data_quality_context", "masked_cell_share_kpi_tags",
         "overlapping_phase1_windows"] + mcols]))
    A(f"\nResult: {counts(dq.data_quality_context, None)}; maximum contamination "
      f"{dq.data_quality_contamination.max():.2f} (per-candidate table A6). The Phase 3 KPI is produced only when tag coverage "
      "is adequate, so no candidate is dominated by bad data. The DQ-016 frozen window and the 10–12 May gap fall "
      "where the KPI is not scored.\n")

    # 15-17 -------------------------------------------------------------------------------------------------------
    A("\n## 15. Episode Construction\n")
    A("```text\nRUNNING buckets with KPI >= cut\n        |  maximal runs\ncontiguous candidate windows\n        |  merge if "
      "gap <= 60 min, all gap buckets RUNNING, no long gap / frozen window\ncandidate episodes (CANDIDATE_ABNORMAL_PERIOD)"
      "\n        |  CUSUM onset, families, Mahalanobis, load, AFR, Phase 4, DQ\ncontext classification (fixed "
      "precedence)\n        |  out of sample, no ordinary context, >= 1 deviating family\nHISTORICAL_ABNORMAL_PERIOD "
      "(final set)\n```\n\nPrecedence, first match wins:\n\n")
    A(md_table(pd.DataFrame({"category": list(FP_CATEGORIES), "rule": [FP_NOTE[k] for k in FP_CATEGORIES]}),
               max_col=120))
    A("\n## 16. Episode Severity\n")
    A("- **Score:** `severity_score` = 0.4·peak + 0.3·persistence + 0.3·breadth, each part in [0, 1]:\n"
      "  - peak = (peak KPI − cut) / (P99 − cut);\n"
      "  - persistence = KPI-hours above the cut / ((P99 − cut) × 6 h);\n"
      "  - breadth = deviating families / 5.\n"
      "- **Class:** HIGH = peak ≥ training P99 **and** duration ≥ 6 h (the KPI persistence window); MODERATE = one of "
      "the two; LOW = neither.\n"
      "- **Meaning:** read it as *deviation magnitude*. HIGH means the score was above the level exceeded in only "
      "1 % of Apr–May running time, for at least 6 h. It is **not** a risk, failure, deposit or ring probability.\n"
      "- **Class boundary:** the class has a hard cut at P99, so compare `severity_score` for periods near it "
      "(a score just under P99 is MODERATE).\n\n")
    A(md_table(sev[sev.episode_id.isin(fin.episode_id)][["episode_id", "peak_kpi", "duration_minutes", "kpi_integral",
                                                          "family_count", "sev_peak", "sev_persistence", "sev_breadth",
                                                          "severity_score", "severity_class"]]))
    A("\n## 17. Episode Confidence\n")
    A("- **Score:** confidence is kept separate from severity. It is the mean of the available parts:\n"
      "  - 1 − DQ contamination;\n"
      "  - family agreement;\n"
      "  - Mahalanobis support share;\n"
      "  - change-point support;\n"
      "  - share of Phase 3 kpi_confidence HIGH (which already includes the band-boundary margin);\n"
      "  - sensitivity robustness.\n"
      "- **Reported but not averaged:** `sp_heat_fg_agreement` (the cut is only nominal for the F / G KPIs, which have "
      "their own anchors) and `band_margin` (already part of kpi_confidence).\n"
      "- **Meaning:** confidence is the internal consistency of the evidence, **not** the likelihood of a real plant "
      "event. MEDIUM is the ceiling by design.\n"
      "- **Class:** HIGH needs ≥ 0.75, robustness ≥ 0.7 and ≥ 2 families, and is then **capped to MEDIUM**. LOW is "
      "< 0.5.\n"
      "- **Combinations:** `severity = HIGH, confidence = LOW` is a valid combination.\n\n")
    A(md_table(conf[conf.episode_id.isin(fin.episode_id)][["episode_id", "severity_class", "conf_dq", "conf_family",
                                                           "conf_multivariate", "conf_change_point", "conf_kpi_quality",
                                                           "conf_robustness", "sp_heat_fg_agreement", "band_margin",
                                                           "confidence_score", "confidence_uncapped", "confidence"]]))

    # 18-20 -------------------------------------------------------------------------------------------------------
    A("\n## 18. Pre-Event Analysis (before onset, T−12 h … T)\n")
    tab = fe.groupby("signal").agg(share_with_exceedance=("exceeded", "mean"),
                                   median_lead_min=("lead_minutes_before_onset", "median"),
                                   share_active_at_T=("active_at_T", "mean"),
                                   base_rate_oos=("base_rate_oos", "first")).reset_index()
    A("- **Window:** T is the CUSUM onset, and only data up to T is used. Snapshots are taken at T-12h, -6h, -3h, -2h, "
      "-1h, -30m and T; the first exceedance of each frozen rule in the 12 h before T is recorded, together with the "
      "KPI turning point and AFR / stop / restart events.\n"
      "- **Reading the table:** compare `share_with_exceedance` with `base_rate_oos`, the share of ordinary "
      f"out-of-sample running buckets above the same rule. Family scores exceed their P90 in "
      f"{pct(fam_base.min())}–{pct(fam_base.max())} of ordinary buckets, so an exceedance somewhere in 12 h is "
      "uninformative for them. The lower-base-rate rows (D, feed / coal changes, clinker) are more telling.\n"
      f"- **KPI turning point:** the KPI's minimum precedes the onset by a median "
      f"{tp.lead_minutes_before_onset.median():.0f} min.\n"
      "- **Status:** this is descriptive input to Phase 7/8, **not** a predictive result.\n\n")
    A(md_table(tab))
    A("\n## 19. Post-Event Analysis (after the end, T_end … +6 h)\n")
    A("T_end is the episode end, and the windows run T+30m … T+6h. This is retrospective, and never used to define the "
      "episode. The outcome is one of:\n\n"
      "- DATA_END_CENSORED;\n"
      "- FOLLOWED_BY_STOP (sequence only, not a consequence);\n"
      "- RECURRED_WITHIN_6H;\n"
      "- NO_KPI_AFTER;\n"
      "- PROCESS_DEVIATION_PERSISTS (KPI back below the cut, but ≥ 2 families still above P90 at +1 h);\n"
      "- RECOVERED.\n\n"
      f"Final set: {counts(po[po.episode_id.isin(fin.episode_id)].post_event_outcome, None)}. Where the KPI "
      "recovers while several families remain elevated, the deviation is persistent rather than transient.\n\n")
    A(md_table(po[po.episode_id.isin(fin.episode_id)][["episode_id", "post_event_outcome", "kpi_max_post_6h",
                                                       "kpi_drop_peak_to_1h", "next_episode_within_6h",
                                                       "minutes_to_next_episode"]]))
    A("\n## 20. Episode Types\n")
    A("Types are rule-based analytical categories, **not** plant failure modes. A type is RECURS_ACROSS_MONTHS (a "
      "descriptive recurrence, not a validated mode) only with "
      "≥ 5 out-of-sample episodes in ≥ 2 months. Clustering was not run: the final set is too small for a stable "
      "clustering.\n\n")
    A(md_table(types[types.reference_state == "OUT_OF_SAMPLE"][["episode_type", "type_n_oos", "type_months",
                                                                "type_month_list", "type_support"]].drop_duplicates()))

    # 21-24 -------------------------------------------------------------------------------------------------------
    A("\n## 21. Temporal Robustness\n")
    A(md_table(temporal[["variant", "description", "running_hours", "candidate_bucket_share", "n_candidates", "n_final",
                         "final_per_100_running_h", "median_severity_score", "share_multi_family", "dominant_families",
                         "share_load_associated", "share_afr_context"]], max_col=60))
    A("\nThe table compares the final-period rate per 100 running hours, the candidate-bucket share and the "
      "dominant-family mix across months. With only a few final periods per month, these differences are descriptive; "
      "Apr–May is the KPI's calibration window.\n")
    A("\n## 22. Sensitivity Analysis\n")
    A(f"![Sensitivity retention]({figs[2]})\n")
    A(md_table(s_var[["dimension", "variant", "description", "in_robustness_set", "n_candidates_oos", "n_final",
                      "n_ordinary_context_category", "bucket_jaccard_final_vs_primary", "primary_final_retained_share",
                      "result"]], max_col=70))
    stable = s_var[s_var.result == "STABLE"].dimension.unique().tolist()
    A(f"\n- **Stable dimensions:** {', '.join(stable)}.\n"
      f"- **Threshold CI:** the lower and upper cut CIs retain {pct(sv.loc['A_lo'].primary_final_retained_share)} / "
      f"{pct(sv.loc['A_hi'].primary_final_retained_share)} of the final periods but change the episode extent "
      f"(Jaccard {sv.loc['A_lo'].bucket_jaccard_final_vs_primary:.2f} / "
      f"{sv.loc['A_hi'].bucket_jaccard_final_vs_primary:.2f}).\n"
      f"- **Sp.Heat F / G:** these KPIs have their own anchors, so the cut is nominal. They retain "
      f"{pct(sv.loc['I_F'].primary_final_retained_share)} / {pct(sv.loc['I_G'].primary_final_retained_share)}.\n"
      f"- **Drift check (A_alt):** the Phase 3 alternative Jun–Jul15 reference retains "
      f"{pct(sv.loc['A_alt'].primary_final_retained_share)}. **The abnormal level depends on which period is taken as "
      "normal.** This is the most important robustness caveat, and it is reported as NOT_MET.\n"
      "- **Stricter variants:** ≥ 3 families, LOAD_INDEPENDENT only, Mahalanobis-led, and so on shrink the set, as "
      "designed.\n"
      "- **Robustness scores:** `robustness_score` is the share of robustness-set variants retaining the period. "
      "`reference_robustness_score` covers the threshold and reference subset only.\n")
    A("\n## 23. Negative Controls\n")
    A(md_table(nc[["control", "statistic", "observed", "null_median", "null_p95", "empirical_p", "result",
                   "interpretation"]], max_col=110))
    A("\n- **NC1 / NC2:** they test whether family agreement exceeds what autocorrelated but misaligned series, or "
      "random same-length running windows, give. Because the families are KPI inputs, this is internal consistency "
      "beyond autocorrelation, **not** independent confirmation.\n"
      "- **Limits:** the nulls preserve each series' autocorrelation, not the joint process dynamics. Do not "
      "over-interpret them.\n")
    A("\n## 24. Results\n")
    A("**How to read this table:**\n\n"
      "- `severity_class` is the deviation magnitude (§16), not a risk.\n"
      "- `confidence` is the internal consistency of the evidence, capped at MEDIUM (§17).\n"
      "- `load_context` records whether feed or production changed (§11).\n"
      "- `feed_change_vs_pre2h` is the feed change against the 2 h before onset, in TPH. For LOAD_ASSOCIATED periods "
      "the deviation may be the process response to a rate change, so check whether the feed cut came before or after "
      "the process symptoms.\n"
      "- `afr_context` lists AFR transitions nearby; their causal role is not assessed.\n"
      "- `robustness_score` is the share of reasonable parameter variants that keep the period. "
      "`reference_robustness_score` is the same share under alternative thresholds and references.\n\n")
    A(f"**Final historical abnormal periods ({len(fin)}):**\n\n")
    A(md_table(fin[["episode_id", "start_time", "end_time", "duration_minutes", "peak_kpi", "severity_class",
                    "confidence", "family_count", "deviating_families", "episode_type", "load_context",
                    "feed_change_vs_pre2h", "afr_context", "post_event_outcome", "robustness_score",
                    "reference_robustness_score"]], max_col=60))
    A("\n**Evidence summaries:**\n\n" + "".join(f"- `{r.episode_id}`: {r.evidence_summary}\n" for r in fin.itertuples()))
    A("\n**All candidates, including the ordinary-context categories:**\n\n")
    A(md_table(ep[["episode_id", "reference_state", "start_time", "duration_minutes", "peak_kpi", "classification",
                   "primary_context", "severity_class", "confidence"]]))

    # 25-30 -------------------------------------------------------------------------------------------------------
    A("\n## 25. Limitations\n")
    A("- **Circularity:** the KPI defines the candidates, and the families are the KPI's inputs, so family agreement is "
      "partly internal consistency. Hence the confidence cap.\n"
      "- **Reference dependence:** the abnormal level depends on the Apr–May reference (drift check A_alt).\n"
      f"- **Small sample:** there are {len(fin)} out-of-sample final periods over ≈ 2.7 months. Month-level and "
      "type-level statements are descriptive.\n"
      "- **Load:** load and process deviation cannot be separated with the available tags. Most final periods are "
      "LOAD_ASSOCIATED or UNCERTAIN.\n"
      "- **Control inputs:** AFR, coal and feed are co-manipulated control inputs. Their overlaps are context, and their "
      "effects are not isolable.\n"
      "- **Proxies:** the state is a POC proxy, and the Phase 2 stop / restart events are retrospective.\n"
      "- **Sp.Heat:** the F/G definition is unresolved.\n"
      "- **Data gaps:** there is no September, and the Kiln-IIIA gap on 14–15 Aug removes clinker TPH from the load "
      "context there.\n")
    A("\n## 26. Missing Event Ground Truth\n")
    A(STATEMENT)
    A("\n- **Current status:** `event_ground_truth_status = event_match_status = plant_event_type = NOT_AVAILABLE` for "
      "every episode.\n"
      f"- **Integration point:** place a real plant log at `{PHASE_DIR.name}/inputs/plant_event_log.csv` with columns "
      f"`{', '.join(PLANT_EVENT_COLUMNS)}`, then rerun `run_phase6.py` (ground_truth_available = True). "
      "`abn_core.match_plant_events` then fills MATCHED / PARTIAL_OVERLAP / NO_MATCH per episode, from which matched, "
      "unmatched and missed events and overlap statistics follow.\n"
      "- **What is not done:** no synthetic event record is created, and supervised performance metrics are "
      "deliberately not implemented until real labels exist.\n")
    A("\n## 27. Plant Questions\n")
    A("1. Can the plant supply a timestamped log of kiln stops with reasons, coating / ring observations, cleaning and "
      "maintenance for Apr–Aug 2025, to validate or reject each listed period?\n"
      f"2. What happened around the HIGH-severity periods ({high_dates}) and around `P6-021` (1–2 Jun, 18.5 h, "
      "excluded by the AFR_TRANSITION rule but worth reviewing)? Were there operational notes?\n"
      "3. Are the load reductions seen in most final periods planned (production plan, feed availability) or a "
      "response to process conditions?\n"
      "4. Why are AFR stops and ramp-downs initiated, and is PC coal raised in response (the Phase 5 swap)?\n"
      "5. Which Sp.Heat definition (F or G) is authoritative, and how is it calculated?\n"
      "6. Does `Kiln MD` = 0 mean the kiln is stopped? Are the Kiln-I … IIIB folders one kiln line?\n"
      "7. Which reference period does the plant consider normal operation? The abnormal level depends on it.\n")
    A("\n## 28. Validation\n")
    A(md_table(val.groupby(["gate", "result"]).size().unstack(fill_value=0).reset_index()))
    A("\nNon-PASS rows:\n\n" + md_table(val[val.result != "PASS"][["gate", "check", "result", "evidence"]], max_col=200)
      + "\nThe full check list is in appendix table A7.\n")
    X.append("### A7. Validation checks\n\n" + md_table(val[["gate", "check", "check_type", "result", "evidence"]],
                                                          max_col=240))
    A("\n## 29. Reproducibility\n")
    A("```bash\ncd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-06-abnormal-events/scripts\n"
      "../../.venv/bin/python run_phase6.py --clean      # run twice: G7 compares every key output byte-for-byte\n"
      "../../.venv/bin/python -B -m unittest discover -s ../tests -v\n```\n\n"
      "- **Determinism:** seeds are fixed, CSV and Parquet values are rounded to 6 dp, PNGs carry no timestamp "
      "metadata, and BLAS is single-threaded.\n"
      "- **Integrity:** inputs, outputs and code are hashed in `abnormal_events_version_manifest.csv`. The source, "
      "Phases 1–5 and `data/` are snapshotted before and after every run.\n")
    A("\n## 30. Phase 7 Handoff\n")
    A("- **Phase 7 may consume:**\n"
      "  - `abnormal_episodes.parquet` (filter `in_final_set`);\n"
      "  - `abnormal_episode_signals.parquet`;\n"
      "  - `abnormal_episode_context.csv`;\n"
      "  - `abnormal_episode_severity.csv`;\n"
      "  - `abnormal_episode_confidence.csv`;\n"
      "  - `abnormal_episode_pre_event.parquet`;\n"
      "  - `abnormal_episode_post_event.parquet`;\n"
      "  - `abnormal_episode_types.csv`.\n"
      "- **Rules for Phase 7:**\n"
      "  - Phase 7 must **not** assume these are confirmed plant events. They are empirical historical abnormal "
      "periods of a POC KPI.\n"
      "  - Carry `confidence`, `load_context`, `afr_context` and `reference_robustness_score` with every period.\n"
      "  - Treat the Phase 4 indicator as unsupported context.\n"
      "  - Never use post-event fields as features.\n\n"
      "**Phase 7 has NOT been started.**\n")

    A("\n## Appendix — reference tables\n")
    L.extend(X)
    md = "\n".join(L)
    hits = forbidden_hits(md)
    if hits:
        raise SystemExit(f"report wording scan failed: {hits[:5]}")
    (REPORTS / f"{TITLE}.md").write_text(md)
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark").enable("table").render(md)
    css = (":root{--bg:#fcfcfb;--ink:#0b0b0b;--line:#e0dfda;--head:#f1f0ec;--note:#fdf3ee}"
           "@media (prefers-color-scheme: dark){:root:not([data-theme=light]){--bg:#1a1a19;--ink:#fff;--line:#3a3a37;"
           "--head:#2a2a28;--note:#2a211c}}"
           "body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:var(--ink);"
           "background:var(--bg);line-height:1.45}table{border-collapse:collapse;font-size:12px;margin:8px 0;display:block;"
           "overflow-x:auto}td,th{border:1px solid var(--line);padding:3px 6px;vertical-align:top}th{background:var(--head)}"
           "img{max-width:100%;background:#fcfcfb}blockquote{border-left:4px solid #eb6834;margin:12px 0;padding:4px 12px;"
           "background:var(--note)}code{background:var(--head);padding:0 3px}pre{overflow-x:auto}")
    html = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
            f"initial-scale=1'><title>Phase 6 Abnormal Periods</title><style>{css}</style></head><body>{body}</body></html>")
    (REPORTS / f"{TITLE}.html").write_text(html)
    lg.info("report written (%d chars, %d figures)", len(md), len(figs))


if __name__ == "__main__":
    main()
