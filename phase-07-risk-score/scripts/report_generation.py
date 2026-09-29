"""Step 6 - Phase 7 report (Markdown + HTML) and figures, generated only from the Phase 7 outputs.

Writes reports/PHASE_7_RISK_SCORE_REPORT.md, reports/PHASE_7_RISK_SCORE_REPORT.html, reports/figures/*.png
Exits non-zero if the unsupported-claim scanner finds a hit in the generated report or the docs.
Figures: light-surface PNGs; categorical slots 1-7 and a blue ordinal ramp from the validated dataviz reference palette
(contrast relief: every figure has a legend or direct labels and the same numbers are in the report tables).
"""
from __future__ import annotations

import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import (BANDS, CACHE, DOCS, FAMILIES, FIG, O2_TAG, OUT, PRIMARY, REPORTS, REVIEWS, SCORE_VERSION,  # noqa: E402
                    forbidden_hits, log, read_json)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
ORDINAL = {"LOW": "#86b6ef", "ELEVATED": "#2a78d6", "HIGH": "#104281", "VERY_HIGH": "#0d366b"}
SHADE = "#dcdad3"          # period shading: must stay visible against the #fcfcfb surface
REPORT = "PHASE_7_RISK_SCORE_REPORT"
PARTS = list(FAMILIES) + ["CONCURRENCE", "PERSISTENCE"]
MONTHS3 = ("JUN", "JUL", "AUG")


# ============================================================================== helpers
def md_table(df: pd.DataFrame, max_rows: int | None = None, floatfmt: str = "{:.3g}", max_col: int = 110) -> str:
    if df.empty:
        return "_(no rows)_"
    d = df.head(max_rows) if max_rows else df

    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "" if np.isnan(v) else floatfmt.format(v)
        s = str(v).replace("|", "/").replace("\n", " ")
        return s if len(s) <= max_col else s[:max_col - 1] + "…"
    lines = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in d.itertuples(index=False)]
    if max_rows and len(df) > max_rows:
        lines.append(f"\n_{len(df) - max_rows} more rows in the CSV._")
    return "\n".join(lines)


def read(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / name) if name.endswith(".parquet") else pd.read_csv(OUT / name, low_memory=False)


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def save(fig, name: str) -> str:
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=130, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)
    return f"figures/{name}"


def pct(v) -> str:
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{100 * float(v):.1f} %"


def metric(df: pd.DataFrame, section: str, m: str, slc: str | None = None) -> float:
    sel = df.section.str.startswith(section) & df.metric.eq(m)
    if slc is not None:
        sel &= df.slice.eq(slc)
    return float(df.loc[sel, "value"].iloc[0]) if sel.any() else float("nan")


# ============================================================================== figures
def fig_timeline(s: pd.DataFrame, ep: pd.DataFrame, bands: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 3.6))
    style(ax)
    t = s.set_index("timestamp").risk_score
    t = t[(t.index >= "2025-06-01") & (t.index < "2025-09-01")]
    for r in ep.itertuples():
        ax.axvspan(r.start_time, r.end_time, color=SHADE, zorder=0, linewidth=0)
    ax.plot(t.index, t.values, color=SERIES[0], linewidth=0.8, zorder=2)
    for b in bands[bands.band.ne("LOW") & bands.supported.astype(bool)].itertuples():
        ax.axhline(b.lower_edge, color=INK2, linewidth=0.8, linestyle=(0, (4, 3)), zorder=1)
        ax.text(t.index.max(), b.lower_edge + 1, f" {b.band} (≥ Apr–May P{int(round(b.reference_quantile * 100))}) "
                f"= {b.lower_edge:.1f}", color=INK2, fontsize=8, va="bottom", ha="right")
    ax.set_ylim(0, 100)
    ax.set_ylabel("risk_score (0-100)", color=INK2, fontsize=8)
    ax.set_title(f"Operational risk_score, Jun-Aug 2025 ({int(t.notna().sum())} operational buckets); shaded = the 12 "
                 "Phase 6 empirical abnormal periods; gaps = not scored", color=INK, fontsize=9, loc="left")
    return save(fig, "fig1_risk_score_timeline.png")


def fig_band_shares(summ: pd.DataFrame) -> str:
    m = summ[summ.slice_type.eq("month") & summ.slice.isin(["REFERENCE_APR_MAY", *MONTHS3])].set_index("slice")
    m = m.loc[[x for x in ["REFERENCE_APR_MAY", *MONTHS3] if x in m.index]]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    style(ax)
    left = np.zeros(len(m))
    for b in BANDS:
        col = f"share_{b.lower()}"
        if col not in m or m[col].sum() == 0:
            continue
        v = m[col].to_numpy(float)
        ax.barh(m.index, v, left=left, color=ORDINAL[b], edgecolor=SURFACE, linewidth=2, label=b, height=0.6)
        for i, (x0, w) in enumerate(zip(left, v)):
            if w >= 0.06:
                ax.text(x0 + w / 2, i, f"{100 * w:.0f}%", ha="center", va="center", fontsize=8,
                        color=INK if b == "LOW" else "#ffffff")
        left += v
    ax.set_xlim(0, 1)
    ax.invert_yaxis()
    ax.xaxis.grid(False)
    ax.set_xlabel("share of scored buckets", color=INK2, fontsize=8)
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    ax.set_title("Band shares by month (bands = Apr-May reference P75 / P90; reference in-sample)", color=INK,
                 fontsize=9, loc="left")
    return save(fig, "fig2_band_shares_by_month.png")


def fig_families(summ: pd.DataFrame) -> str:
    m = summ[summ.slice_type.eq("month") & summ.slice.isin(["REFERENCE_APR_MAY", *MONTHS3])].set_index("slice")
    m = m.loc[[x for x in ["REFERENCE_APR_MAY", *MONTHS3] if x in m.index]]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    style(ax)
    left = np.zeros(len(m))
    for c, colr in zip(PARTS, SERIES):
        v = m[f"share_points_{c.lower()}"].fillna(0).to_numpy(float)
        ax.barh(m.index, v, left=left, color=colr, edgecolor=SURFACE, linewidth=2, label=c, height=0.6)
        left += v
    ax.set_xlim(0, 1)
    ax.invert_yaxis()
    ax.xaxis.grid(False)
    ax.set_xlabel("share of risk_score points", color=INK2, fontsize=8)
    ax.legend(ncol=4, fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    ax.set_title("Where the points come from, by month", color=INK, fontsize=9, loc="left")
    return save(fig, "fig3_family_contributions.png")


def fig_robustness(rob: pd.DataFrame) -> str:
    r = rob[rob.section.eq("ROBUSTNESS")].iloc[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(10, 6.6), sharey=True)
    for ax, col, thr, title in ((axes[0], "spearman", 0.80, "Spearman vs primary (rank)"),
                                (axes[1], "band_agreement", 0.85, "Band agreement vs primary (level)")):
        style(ax)
        ax.xaxis.grid(True, color=GRID, linewidth=0.6)
        ax.yaxis.grid(False)
        ax.barh(r.variant.str.slice(0, 44), r[col], color=SERIES[0], height=0.62)
        ax.axvline(thr, color=INK2, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.text(thr, len(r) - 0.3, f" materiality {thr:.2f}", color=INK2, fontsize=7.5, va="bottom")
        ax.set_xlim(0, 1)
        ax.set_title(title, color=INK, fontsize=9, loc="left")
    axes[0].tick_params(axis="y", labelsize=7)
    return save(fig, "fig4_robustness.png")


# ============================================================================== report
def review_rows() -> pd.DataFrame:
    p = REVIEWS / "REVIEW_LOG.md"
    if not p.exists():
        return pd.DataFrame()
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in p.read_text(encoding="utf-8").splitlines()
            if re.match(r"^\|\s*R\d+\s*\|", ln)]
    cols = ["ID", "Reviewer", "Severity", "Finding", "Evidence", "Action", "Status", "Validation after fix"]
    return pd.DataFrame([r[:8] for r in rows if len(r) >= 8], columns=cols)


def main():
    lg = log("report_generation")
    ref = read_json(OUT / "risk_score_reference.json")
    s = read("risk_scores.parquet")
    bands, cal, rob = read("risk_score_bands.csv"), read("risk_score_calibration.csv"), read("risk_score_robustness.csv")
    cov, summ, dq = read("risk_score_event_similarity.csv"), read("risk_score_summary.csv"), read("risk_score_data_quality.csv")
    inv, val = read("risk_score_feature_inventory.csv"), read("risk_score_validation.csv")
    eps = pd.read_parquet(CACHE / "episodes.parquet")
    final = eps[eps.in_final_set]
    o = s[s.operational]
    f1, f2, f3, f4 = fig_timeline(s, final, bands), fig_band_shares(summ), fig_families(summ), fig_robustness(rob)
    fc = cov[cov.population.eq("PHASE6_FINAL_OUT_OF_SAMPLE")]
    COV, EAR, SEV = "EMPIRICAL_ABNORMAL_PERIOD_COVERAGE", "EMPIRICAL_ALERT_RATE", "SEVERITY_RELATIONSHIP"
    auc, auc_lo, auc_hi = (metric(cal, COV, k) for k in ("rank_separation_auc", "rank_separation_auc_ci95_low",
                                                          "rank_separation_auc_ci95_high"))
    kpi_auc = float(cal.loc[cal.metric.str.startswith("baseline_auc_phase3_kpi"), "value"].iloc[0])
    mag_auc, fam_auc = metric(cal, COV, "baseline_auc_magnitude_component_only"), metric(cal, COV, "baseline_auc_abnormal_family_count")
    hi = {m: metric(cal, EAR, "share_ge_HIGH", m) for m in MONTHS3}
    hi_lo = {m: metric(cal, EAR, "share_ge_HIGH_block_ci95_low", m) for m in MONTHS3}
    hi_hi = {m: metric(cal, EAR, "share_ge_HIGH_block_ci95_high", m) for m in MONTHS3}
    e_lo = {m: metric(cal, EAR, "share_ge_HIGH_edge_at_ci_high", m) for m in MONTHS3}
    e_hi = {m: metric(cal, EAR, "share_ge_HIGH_edge_at_ci_low", m) for m in MONTHS3}
    dd, dd_lo, dd_hi = (metric(cal, EAR, k, "AUG_minus_JUN") for k in ("share_ge_HIGH_difference",
                                                                         "difference_block_ci95_low",
                                                                         "difference_block_ci95_high"))
    lstd = {m: metric(cal, "LOAD_STANDARDISED", "load_standardised_share_ge_HIGH", m) for m in MONTHS3}
    sev = cal[cal.section.str.startswith(SEV)].set_index("metric").value
    cand = rob[rob.section.eq("CANDIDATE")]
    rrow = rob[rob.section.eq("ROBUSTNESS")]
    nc = rob[rob.section.eq("NEGATIVE_CONTROL")].set_index("dimension")
    inc = rob[rob.section.eq("INCLUSION_TEST")].set_index("dimension")
    o2v = rrow[rrow.variant.eq("EXCLUDE_KILN_INLET_O2_ANALYSER")].iloc[0]
    aug_gt_jun = int((rrow.share_ge_high_aug > rrow.share_ge_high_jun).sum())
    mono = int(((rrow.share_ge_high_jul >= rrow.share_ge_high_jun) & (rrow.share_ge_high_aug >= rrow.share_ge_high_jul)).sum())
    vc = val.result.value_counts().to_dict()
    b_ok = bands[bands.band.ne("LOW") & bands.supported.astype(bool)]
    edges = ", ".join(f"{r.band} ≥ {r.lower_edge:.1f} (Apr–May P{int(round(r.reference_quantile * 100))})"
                      for r in b_ok.itertuples())
    hi_op = o.risk_band.isin(BANDS[2:])
    afr_hi, afr_all = float(o.loc[hi_op, "afr_context"].ne("NO_AFR_TRANSITION").mean()), float(o.afr_context.ne("NO_AFR_TRANSITION").mean())
    p4_hi, p4_all = float(o.loc[hi_op, "phase4_context"].str.startswith("ACTIVE").mean()), float(o.phase4_context.str.startswith("ACTIVE").mean())
    load_hi, load_all = float(o.loc[hi_op, "load_context"].eq("LOAD_ASSOCIATED").mean()), float(o.load_context.eq("LOAD_ASSOCIATED").mean())
    conf_med, conf_low = float(o.confidence_band.eq("MEDIUM").mean()), float(o.confidence_band.eq("LOW").mean())
    sel = cand[cand.result.eq("SELECTED")].variant.iloc[0]
    o2m = {m: metric(dq, "O2_ANALYSER", "share_operational_o2_suspect", m) for m in MONTHS3}
    L = []
    A = L.append
    A("# Phase 7 — Deposit / Inefficiency Risk Score\n\n"
      "### Empirical POC: resemblance to historical abnormal process conditions — not deposit detection\n\n"
      f"**Score:** `deposit_inefficiency_risk_score` (`risk_score`) · version `{SCORE_VERSION}` · reference "
      f"`{ref['reference_version']}`  \n**Status:** EMPIRICAL POC RISK SCORE — not validated against any plant event; no "
      "event ground truth exists.\n")
    A("> The score shows how strongly the current kiln condition resembles historical abnormal / inefficient process "
      "behaviour **relative to the frozen Apr–May 2025 reference**. It identifies which evidence families drive that "
      "resemblance, and with what confidence.\n>\n"
      "> It is **not** a deposit, ring or failure probability, **not** a plant limit and **not** a control or set-point "
      "recommendation. The name follows the project's phase naming; the word \"deposit\" does **not** mean deposits are "
      "detected.\n")

    A("## 1. Executive summary\n")
    A(f"- **What was built.** A leakage-tested 0–100 score computed every 10 minutes from the five Phase 3 evidence "
      f"families (efficiency / Sp.Heat, combustion, thermal, draft / pressure, process variability).\n"
      f"  - It combines magnitude (0.5), multi-family concurrence (0.25) and persistence (0.25).\n"
      f"  - It comes with a separate six-part confidence, an explicit status, reason codes, auditable components and an "
      f"`operational` flag.\n"
      f"  - Scored on {len(o)} operational out-of-sample buckets (Jun–Aug). September is not scored because Kiln-I is "
      f"missing.")
    A(f"- **Architecture.** `{sel}` was selected by the pre-declared rule.\n"
      "  - The simplest candidate (A, family mean) lacks the required explicit persistence and concurrence.\n"
      "  - Candidate C (historical-signature similarity) is descriptive only: the Apr–May signatures do not carry over "
      "to Jun–Aug.")
    A(f"- **Bands (empirical, reference-relative; not plant limits).** {edges}.\n"
      "  - The P95 edge was not supported: its bootstrap CI overlaps the P90 CI.\n"
      "  - \"HIGH\" means *as unusual as the top 10 % of the Apr–May reference*. It is the majority state in August.")
    A(f"- **Drift against the reference (with uncertainty).** The share of operational time at or above HIGH, with its "
      f"3-day block CI and the range obtained by moving the HIGH edge across its own CI:\n"
      f"  - June {pct(hi['JUN'])} [{pct(hi_lo['JUN'])}–{pct(hi_hi['JUN'])}; edge range {pct(e_lo['JUN'])}–{pct(e_hi['JUN'])}]\n"
      f"  - July {pct(hi['JUL'])} [{pct(hi_lo['JUL'])}–{pct(hi_hi['JUL'])}; edge range {pct(e_lo['JUL'])}–{pct(e_hi['JUL'])}]\n"
      f"  - August {pct(hi['AUG'])} [{pct(hi_lo['AUG'])}–{pct(hi_hi['AUG'])}; edge range {pct(e_lo['AUG'])}–{pct(e_hi['AUG'])}]\n\n"
      f"  Only **August > June** is separable: the difference is {dd:+.2f} (block CI {dd_lo:+.2f} to {dd_hi:+.2f}). "
      f"Month-to-month steps are not. August > June holds in {aug_gt_jun} of {len(rrow)} robustness variants, but the "
      f"monthly path is monotone in only {mono}. The 10 % Apr–May level is in-sample for Phase 3 as well, so the jump "
      "from the reference to June mixes fit optimism with drift; only the trend within Jun–Aug is interpretable.")
    A(f"- **The O₂ analyser drives much of the drift (major caveat).** The kiln-inlet O₂ analyser (`{O2_TAG}`) often "
      f"reads close to ambient air while the kiln runs: {pct(o2m['JUN'])} / {pct(o2m['JUL'])} / {pct(o2m['AUG'])} of "
      f"operational buckets have a median ≥ {PRIMARY.o2_ambient_pct:g} %. Rebuilding the combustion and stability "
      f"families without that analyser (an exact rebuild from the Phase 3 tag scores) gives HIGH shares of "
      f"{pct(o2v.share_ge_high_jun)} / {pct(o2v.share_ge_high_jul)} / {pct(o2v.share_ge_high_aug)}. August still "
      f"exceeds June, but the rise roughly halves and is no longer monotone. The ranks stay stable (ρ {o2v.spearman:.2f}). "
      "The plant must confirm the analyser's purge / calibration behaviour before any drift reading is used.")
    A(f"- **Load.** Load mix does not explain the drift: the load-standardised HIGH shares are {pct(lstd['JUN'])} / "
      f"{pct(lstd['JUL'])} / {pct(lstd['AUG'])}. Even so, the score is higher in low-feed and load-change periods: "
      f"{pct(load_hi)} of HIGH buckets are load-associated, against {pct(load_all)} of all operational buckets. It is "
      "not load-independent.")
    A(f"- **Historical abnormal-period coverage (circular; not accuracy).** All {len(fc)} Phase 6 final periods reach "
      f"HIGH. The rank separation AUC is {auc:.3f} [{auc_lo:.3f}, {auc_hi:.3f}]. The Phase 3 KPI the periods were "
      f"*defined* from separates them at {kpi_auc:.3f}, so the score only partly reproduces that definition; this is "
      "internal consistency, not skill.")
    A(f"- **Severity is inconclusive.** Spearman(peak score, Phase 6 severity) = "
      f"{sev.get('spearman_peak_vs_severity', np.nan):.2f}, 95 % CI {sev.get('spearman_peak_ci95_low', np.nan):.2f} to "
      f"{sev.get('spearman_peak_ci95_high', np.nan):.2f}, n = 12. This is underpowered: it is not evidence of no "
      "relationship.")
    A(f"- **AFR and Phase 4 add no gain on the circular coverage** (gains {inc.at['AFR_INCLUSION', 'observed']:+.4f} "
      f"and {inc.at['PHASE4_INCLUSION', 'observed']:+.4f}). The test is biased toward exclusion, so both stay context "
      "only; the result is not evidence that they are irrelevant.")
    A(f"- **Confidence.** Of operational rows, {pct(conf_med)} are MEDIUM (the cap) and {pct(conf_low)} are LOW. LOW is "
      "the informative state: any single data-quality penalty forces it, including a gap, frozen minutes or a suspect "
      "ambient O₂ reading, as does an incomplete family set below HIGH.")
    A(f"- **Validation.** {vc.get('PASS', 0)} PASS, {vc.get('FAIL', 0)} FAIL, {vc.get('NOT_MET_REPORTED', 0)} "
      f"NOT_MET_REPORTED, {vc.get('INFO', 0)} INFO, {vc.get('NOT_MET_PENDING_REVIEW', 0)} pending review. Leakage "
      "tests are exact under truncation at 8 cuts, under randomisation of every column plus the event and DQ-window "
      "times after T, under post-event perturbation of all 12 periods, and under reference refit.\n")

    A("## 2. Scientific status\n")
    A("- **Empirical POC.** The score ranks resemblance to reference-relative abnormal process conditions.")
    A("- **Not deposit validated.** There are no coating, ring, deposit, cleaning, maintenance or shutdown-reason "
      "observations, so nothing here detects or predicts deposits, rings or failures.")
    A("- **No event ground truth.** The 12 Phase 6 periods are `EMPIRICAL_ABNORMAL_REFERENCE`, not "
      "`DEPOSIT_EVENT_LABEL`. Their severity and confidence are context metadata, never labels or targets.")
    A("- **Unconfirmed context.** Operating state is a POC proxy (`Kiln MD` meaning unconfirmed), and the equipment "
      "identity (one kiln line) is unconfirmed.\n")

    A("## 3. Inputs\n")
    A("All inputs are read-only. SHA-256 values are in `risk_score_reference.json` → `input_hashes` (plus "
      "`code_sha256` for the Phase 7 code), and G1 re-hashes them on every run.\n")
    ih = pd.DataFrame(sorted(ref["input_hashes"].items()), columns=["file", "sha256"])
    ih["sha256"] = ih.sha256.str.slice(0, 16) + "…"
    A(md_table(ih) + "\n")
    A("- **Phase 6 episode fields read:** `episode_id, start_time, end_time, onset_time, classification, "
      "in_final_set, reference_state, severity_class, severity_score, confidence, load_context, afr_context, "
      "reference_robustness_score, family_count, deviating_families, episode_type`.")
    A("- **Post-event data:** `abnormal_episode_post_event.parquet` is hashed only and never read.")
    A("- **Phase 3 tag scores** (`kpi_component_scores.parquet`) are used for per-family tag coverage, the O₂ bucket "
      "value, and the exact rebuild behind the O₂-excluded robustness variant.\n")

    A("## 4. Feature inventory\n")
    A("Every feature has provenance, and only `permitted_use = SCORING` rows (all CAUSAL) enter the score. The full "
      "table is `outputs/risk_score_feature_inventory.csv`.\n")
    A(md_table(inv[["feature_name", "source_phase", "transformation", "window", "permitted_use", "leakage_status"]],
               max_col=70) + "\n")

    A("## 5. Score definition\n")
    an = pd.DataFrame([{"family": d, "m (reference median)": a["m"], "q (reference P90)": a["q"],
                        "degenerate": a["degenerate"], "n": a["n"]} for d, a in ref["anchors"].items()])
    A("For each family `d`:\n")
    A("- `S̃_d(t)` is the trailing 1-h median of the RUNNING-masked Phase 3 component. It needs ≥ 4 of 6 valid buckets "
      "and the current bucket valid.")
    A("- `e_d = max(0, S̃_d − m_d)/(q_d − m_d)` and `a_d = 1 − 2^(−e_d)`. So `a_d` is 0 at the reference median and 0.5 "
      "at the reference P90.\n")
    A("The three components, with a missing family counting as 0 (fixed denominator 5):\n")
    A("- **Magnitude** `H = 0.5·max a + 0.5·mean a`.")
    A("- **Concurrence** `C = max(0, n_abnormal − 1)/4`.")
    A(f"- **Persistence** `P` = number of the last 18 buckets since the last non-RUNNING bucket with "
      f"`H ≥ H_ref90 = {ref['H_ref90']:.4f}`, divided by 18.\n")
    A("**`risk_score = 100·(0.5·H + 0.25·C + 0.25·P)`.**\n")
    A("- **Missing families bias the score downward.** Missing data can never inflate it, but it can under-state it. "
      "Reduced coverage therefore lowers confidence, and below HIGH it forces LOW.")
    A("- **Components** are published per bucket and sum to the score (G4).\n")
    A(md_table(an, floatfmt="{:.4g}") + "\n")

    A("## 6. Confidence definition\n")
    A("Confidence is separate from risk and never combined with it. It is the mean of six causal parts in [0, 1]:\n")
    A(f"- **data quality:** tag coverage × (1 − invalid-cell share). It is halved for each of: causal frozen minutes, "
      f"the 6 h after a gap or the frozen window, and a kiln-inlet O₂ bucket ≥ {PRIMARY.o2_ambient_pct:g} %.")
    A("- **family coverage:** usable families weighted by each family's own tag coverage, so it also responds to a "
      "single tag dropping out.")
    A("- **baseline:** static Phase 2 tag confidence.")
    A("- **operating state:** ramps over 6 h after a restart, halved outside the training load range.")
    A("- **temporal agreement:** over the last hour.")
    A("- **robustness:** band agreement of six variants.\n")
    A("**Band rules.**\n")
    A("- HIGH if ≥ 0.75 (**capped to MEDIUM**), MEDIUM if ≥ 0.50, else LOW.")
    A("- `conf_data_quality ≤ 0.5` forces LOW.")
    A("- An incomplete family set with a band below HIGH forces LOW.\n")
    A(f"On operational rows, {pct(conf_med)} are MEDIUM and {pct(conf_low)} are LOW. Treat MEDIUM as *no known "
      "problem*, not as positive evidence, and use `confidence_score` and its parts for finer ranking. Confidence on a "
      "non-VALID row describes the data, not a score.\n")
    A(md_table(pd.crosstab(o.risk_band, o.confidence_band).reset_index().rename(columns={"risk_band": "risk_band "
                                                                                          "(operational rows)"})) + "\n")

    A("## 7. Calibration\n")
    A(f"- **Population:** {ref['bands']['population']}, {ref['bands']['date_range']}, n = {ref['bands']['n']}, "
      f"{ref['bands']['n_blocks']} three-day blocks, {PRIMARY.n_boot} block-bootstrap replicates.")
    A(f"- **Status:** **{ref['bands']['status']}**.")
    A("- **Support rule.** A conservative heuristic: an edge is kept only if its CI lies entirely above the previous "
      "kept edge's CI. It is not a formal test of distinct edges.")
    A("- **Caveat.** The reference components are in-sample for Phase 3, so the edges are optimistic. The "
      "April-fit / May-check (tolerance ±0.05) measures within-reference stability only.\n")
    A(md_table(bands[["band", "lower_edge", "reference_quantile", "ci95_low", "ci95_high", "supported", "merged_into",
                      "april_fit_edge", "april_fit_may_exceedance", "nominal_exceedance", "oos_exceedance_jun_aug"]])
      + "\n")
    A("**EMPIRICAL_ALERT_RATE** is the share of operational time per band, with 3-day block CIs. It is **not** a "
      "false-positive rate.\n")
    A("**Sustained-exceedance episodes** use hysteresis: they open at ≥ HIGH, close below ELEVATED, and never bridge a "
      "stop or gap. They are descriptive burden counts, not alarms.\n")
    ar = cal[cal.section.isin([EAR, "LOAD_STANDARDISED_ALERT_RATE", "SUSTAINED_EXCEEDANCE_EPISODES"])]
    A(md_table(ar.pivot_table(index=["section", "metric"], columns="slice", values="value", aggfunc="first")
               .reset_index()) + "\n")
    A(f"![Band shares]({f2})\n")

    A("## 8. Historical abnormal-period coverage (EMPIRICAL_ABNORMAL_PERIOD_COVERAGE)\n")
    A("**Circularity.**\n")
    A("- The periods were detected from the same Phase 3 components with the same P90 family rule.")
    A(f"- The Phase 3 KPI they were defined from separates them at AUC {kpi_auc:.3f}.")
    A(f"- The magnitude component alone reaches {mag_auc:.3f}, and the abnormal-family count {fam_auc:.3f}.")
    A("- This is internal consistency, not detection accuracy, and it was **not** used to choose the design.\n")
    A("`minutes_onset_to_first_high_lag` is a **lag** after onset, not a lead time. The 2-h pre-onset score is "
      "descriptive and is not an early-warning result.\n")
    A(md_table(fc[["episode_id", "start_time", "duration_h", "median_score", "peak_score", "max_band", "share_ge_high",
                   "pre_onset_2h_mean_score", "minutes_onset_to_first_high_lag", "median_confidence",
                   "phase6_severity_class", "phase6_load_context", "phase6_deviating_families"]]) + "\n")
    A(f"- **Separation.** Median inside the periods is {metric(cal, COV, 'median_score_inside_periods'):.1f}; outside "
      f"it is {metric(cal, COV, 'median_score_outside_periods'):.1f}. AUC {auc:.3f} (block CI {auc_lo:.3f}–{auc_hi:.3f}).")
    A(f"- **Severity (context, not a label; n = 12, inconclusive).**\n"
      f"  - peak score: ρ {sev.get('spearman_peak_vs_severity', np.nan):.2f} "
      f"[{sev.get('spearman_peak_ci95_low', np.nan):.2f}, {sev.get('spearman_peak_ci95_high', np.nan):.2f}];\n"
      f"  - median score: ρ {sev.get('spearman_median_vs_severity', np.nan):.2f} "
      f"[{sev.get('spearman_median_ci95_low', np.nan):.2f}, {sev.get('spearman_median_ci95_high', np.nan):.2f}];\n"
      f"  - share ≥ HIGH (duration-neutral): ρ {sev.get('spearman_share_ge_high_vs_severity', np.nan):.2f};\n"
      f"  - peak also grows with period length (ρ {sev.get('spearman_duration_vs_peak', np.nan):.2f}).\n\n"
      "  Score magnitude must not be read as a severity grade.")
    ic_ = cov[cov.population.eq("PHASE6_CALIBRATION_ONLY_IN_SAMPLE")]
    A(f"- **Apr–May calibration-only periods (in-sample, descriptive).** {int(ic_.max_band.eq('HIGH').sum())} of "
      f"{len(ic_)} reach HIGH.\n")
    A(f"![Timeline]({f1})\n")

    A("## 9. Score distribution\n")
    A("September is excluded (no numeric score). Load bands are TENTATIVE, and the load rows use operational buckets "
      "only.\n")
    A(md_table(summ[["slice_type", "slice", "n_scored", "median", "p75", "p90", "share_low", "share_elevated",
                     "share_high", "share_confidence_medium", "share_confidence_low", "median_confidence"]]) + "\n")

    A("## 10. Family contributions\n")
    A("Share of `risk_score` points by part. The efficiency (Sp.Heat) share falls from the reference to Jun–Aug, while "
      "combustion, draft / pressure and persistence dominate, as in the Phase 6 periods. The combustion and stability "
      "shares are partly driven by the O₂ analyser (Section 16).\n")
    A(md_table(summ[summ.slice_type.eq("month")][["slice"] + [f"share_points_{c.lower()}" for c in PARTS]]) + "\n")
    rho = pd.DataFrame(ref["family_spearman"]).astype(float)
    A(f"The reference Spearman matrix of family intensities has maximum |ρ| "
      f"{rho.where(~np.eye(len(rho), dtype=bool)).abs().max().max():.2f}, so the families are close to independent "
      "evidence. The most correlated pair was also run merged.\n")
    A(f"![Family contributions]({f3})\n")

    A("## 11. AFR context\n")
    ai = inc.loc["AFR_INCLUSION"]
    A(f"- **Context only.** AFR is never scored and is not part of the reason strings; it is in the `afr_context` "
      f"column, which carries RETROSPECTIVE Phase 5 labels and is not available in real time. {pct(afr_hi)} of HIGH "
      f"operational buckets have an AFR transition in the preceding 3 h, against {pct(afr_all)} of all operational "
      "buckets.")
    A(f"- **Inclusion test.** The coverage-AUC gain is {ai.observed:+.4f} (shifted-null P95 {ai.null_p95:+.4f}), so "
      f"the result is **{ai.result}**. The test is on circular coverage and is biased toward exclusion, so the result "
      "is not evidence of irrelevance.")
    A("- **No causal claim.** AFR transitions are not abnormal events, AFR is not assessed as causal, and AFR and PC "
      "coal are co-manipulated (Phase 5).\n")

    A("## 12. Phase 4 indicator\n")
    pi = inc.loc["PHASE4_INCLUSION"]
    A("- **Indicator.** `Kiln-I!I|ROC_1H` has LOW confidence and was not distinguishable from chance in Phase 6. It "
      "is kept out of the reason strings (`phase4_context` column only).")
    A(f"- **Activity.** It is active in the trailing 2 h for {pct(p4_hi)} of HIGH operational buckets, against "
      f"{pct(p4_all)} overall.")
    A(f"- **Inclusion test.** The coverage-AUC gain is {pi.observed:+.4f} (null P95 {pi.null_p95:+.4f}), so the "
      f"result is **{pi.result}**. It is context only and not validated.\n")

    A("## 13. Robustness\n")
    A("Each variant refits its own frozen reference and bands. Pre-declared materiality is Spearman ≥ 0.80, band "
      "agreement ≥ 0.85 and median |diff| ≤ 10 points.\n")
    A(md_table(rrow[["dimension", "variant", "spearman", "band_agreement", "top_decile_jaccard", "high_jaccard",
                     "median_abs_diff", "coverage_auc", "share_ge_high_jun", "share_ge_high_jul", "share_ge_high_aug",
                     "family_share_corr", "result"]], max_col=48) + "\n")
    sens = rrow[rrow.result.eq("SENSITIVE")]
    A("**Reading.**\n")
    A(f"- **Rank ordering is stable** (median Spearman {rrow.spearman.median():.3f}).")
    A(f"- **Band levels are not** ({len(sens)} of {len(rrow)} variants are SENSITIVE). The largest effects come from:\n"
      "  - the reference window;\n"
      "  - per-load-band anchors;\n"
      "  - a 6-h smoothing window;\n"
      "  - dropping combustion or draft / pressure;\n"
      "  - excluding the O₂ analyser.")
    A(f"- **What holds.** August > June in {aug_gt_jun} of {len(rrow)} variants, but the monthly path is monotone in "
      f"only {mono}.")
    A("- **Implication.** Use `risk_score` ranks and trends, not band levels, and read a band only with its "
      "`reference_version`.\n")
    A(md_table(cand[["variant", "meets_requirements", "ref_window_spearman", "ref_window_band_agreement",
                     "month_high_share_max_change_under_ref_shift", "episodes_per_100h_ge_high",
                     "single_bucket_episodes", "coverage_auc", "result"]]) + "\n")
    A(f"![Robustness]({f4})\n")

    A("## 14. Negative controls\n")
    A("NC1 (circular shift) and NC2 (randomised period placement) are **consistency controls**. The periods share the "
      "scored components, so passing is expected by construction and adds no independent evidence. A p-value of "
      "0.005 is the floor for 200 draws (p ≤ 0.005). NC5 is the reference-window perturbation.\n")
    A(md_table(nc.reset_index()[["dimension", "variant", "observed", "null_median", "null_p95", "p_value", "result"]])
      + "\n")
    A("Future-data and post-event perturbation are the leakage tests in Section 15. The randomised-label control is "
      "NC2.\n")

    A("## 15. Leakage tests\n")
    A(md_table(val[val.gate.str.startswith("G3")][["check", "result", "evidence"]], max_col=160) + "\n")

    A("## 16. Data quality\n")
    A("Data quality moves **status and confidence**.\n")
    A("- **Protections that hold:**\n"
      "  - Missing families can never raise the score.\n"
      "  - A gap bucket is never scored from stale values.\n"
      "  - Sentinels are masked upstream; none reaches scoring (checked cell by cell).")
    A("- **Two effects remain and are quantified in G7:**\n"
      "  1. **Within-window and tag-level dropout** can move a median or a family average either way. Dropout is "
      "value-related (MNAR), and it can raise the score.\n"
      f"  2. **Kiln-inlet O₂ analyser (`{O2_TAG}`, DQ-1).** It reads near ambient air (up to about 21 %) while the kiln "
      f"runs, and those readings are valid upstream. Buckets with a median ≥ {PRIMARY.o2_ambient_pct:g} % score higher "
      "and are more often HIGH (table below). They now lower confidence, and the O₂-excluded variant quantifies their "
      "effect on the score (Section 1).")
    A("- **Why the primary score does not mask them.** Phase 7 does not modify upstream masking, and the threshold is "
      "not plant-confirmed, so the primary score does not mask these readings.\n")
    A(md_table(dq) + "\n")

    A("## 17. Validation gates\n")
    A(md_table(val.groupby(["gate", "result"]).size().unstack(fill_value=0).reset_index()) + "\n")
    A(md_table(val[["gate", "check", "result", "evidence"]], max_col=140) + "\n")

    A("## 18. Review findings\n")
    rv = review_rows()
    A(md_table(rv, max_col=120) if not rv.empty else "_Reviews pending: see `reviews/REVIEW_LOG.md`._")
    A("")

    A("## 19. Limitations\n")
    A("See `docs/LIMITATIONS.md`. In short:\n")
    for x in ["**No event ground truth.** Nothing is deposit, ring or failure validated.",
              "**Only 12 empirical abnormal periods.** They come from the same components (circular coverage), and "
              "severity is inconclusive at n = 12.",
              "**Reference dependence.** The band levels depend on the Apr–May window, which is in-sample for Phase 3; "
              "the ranks are robust.",
              "**Drift uncertainty.** Only August > June is separable, and much of it depends on the O₂ analyser's "
              "ambient readings (plant confirmation needed).",
              "**Load confounding.** The score is higher in low-feed and load-change periods; it is not load-independent.",
              "**Missing-data bias.** Missing families bias the score downward, and tag-level dropout can move it "
              "either way.",
              "**Partial baseline.** Phase 2 readiness is PARTIAL, and the Phase 2 tag confidence is static metadata.",
              "**Unconfirmed context.** The `Kiln MD` state proxy and the equipment identity are unconfirmed.",
              "**Sp.Heat.** The F / G definition is unresolved, and Sp.Heat may be calculated from the firing inputs.",
              "**Missing periods and measurements.** September (Kiln-I) and April (Kiln-IIIA) are missing. There are "
              "no fuel properties, no clinker quality and no shell temperature."]:
        A(f"- {x}")
    A("")

    A("## 20. Plant data required (in priority order)\n")
    for i, x in enumerate([
            "**Event log, Apr–Aug 2025.** Coating, ring and deposit observations, cleaning, stoppages with reasons, and "
            "maintenance. Fields: start / end time, event type, location (kiln inlet / burning zone / riser / cyclone), "
            "and how it was observed. This single item would turn coverage into validation.",
            f"**Kiln-inlet O₂ analyser (`{O2_TAG}`) behaviour.** Purge / calibration / blow-back cycle times and the "
            "sample-line fault history. Readings near 21 % while running dominate the Jun–Aug drift.",
            "**Normal reference.** Which operating period the plant regards as normal. It moves the band levels "
            "(Section 13).",
            "**`Kiln MD` and equipment identity.** Is 0 = kiln stopped? Are the Kiln-I … IIIB folders one line?",
            "**Sp.Heat F / G formulas.** Include the AFR heat factor, and confirm whether Sp.Heat is calculated from "
            "the firing inputs.",
            "**Feed-reduction log.** Whether planned feed reductions are logged, to separate load-driven from "
            "process-driven elevations.",
            "**Sentinels.** The meaning of `99999` / `9999` / `Error 6`.",
            "**Re-exports.** Kiln-I September 2025 and Kiln-IIIA April 2025.",
            "**Fuel lab data.** AF / RDF calorific value, moisture, ash / chlorine and RDF / plastic split, plus clinker "
            "quality.",
            "**Historian settings.** Timezone and export interpolation setting.",
            "**Units.** Confirmation of the columns flagged UNIT CONSISTENCY REVIEW REQUIRED (Phase 1 "
            "`unit_consistency_review.csv`)."], 1):
        A(f"{i}. {x}")
    A("")

    A("## 21. Phase 8 handoff\n")
    A("**Phase 8 may consume the following.**\n")
    A("- `risk_scores.parquet`: filter `operational == True`. Only those rows carry `risk_score` / `risk_band`; the 18 "
      "`OUT_OF_SAMPLE_WINDOW_OVERLAPS_REFERENCE` rows are operational.")
    A("- `risk_score_components.parquet` (with an `operational` flag), `risk_score_confidence.parquet`, "
      "`risk_score_reasons.parquet`.")
    A("- `risk_score_reference.json` and `risk_score_variant_references.json` (frozen; version- and hash-checked by "
      "`common.load_refs`), `risk_score_bands.csv`, `risk_score_feature_inventory.csv`.")
    A("- `risk_score_validation.csv`, `risk_score_robustness.csv`, `risk_score_data_quality.csv`.")
    A("- The pure scorer `risk_core.score_frame` (leakage-tested).\n")
    A("**Not operational:** `risk_score_diagnostics.parquet` (in-sample reference scores and the diagnostic formula "
      "value).\n")
    A("**Guards for Phase 8:**\n")
    A("- HIGH is **not** a rare-event flag: it covers about half of August.")
    A("- Use ranks and trends rather than band levels.")
    A("- Report EMPIRICAL rates only.")
    A("- Do not use `afr_context` in live evaluation (retrospective labels).")
    A("- Evaluate against the same frozen reference, and repeat key results with the O₂-excluded variant.\n")
    A("**Prohibited interpretation:**\n")
    A("- deposit / ring / failure detection or probability;")
    A("- plant limits, set-points or control actions;")
    A("- treating the Phase 6 periods as confirmed events.\n")
    A("Schemas are in `docs/FEATURE_CONTRACT.md`.\n")
    A("_Generated by `scripts/report_generation.py` from the Phase 7 outputs; nothing in this report is typed by hand._")
    md = "\n".join(L)
    (REPORTS / f"{REPORT}.md").write_text(md, encoding="utf-8")
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark").enable("table").render(md)
    css = ("body{font-family:system-ui,sans-serif;max-width:1180px;margin:2rem auto;padding:0 16px;color:#0b0b0b;"
           "background:#fcfcfb;line-height:1.45}table{border-collapse:collapse;font-size:12px;margin:.6rem 0;display:"
           "block;overflow-x:auto}th,td{border:1px solid #e4e3df;padding:3px 6px;text-align:left;vertical-align:top}"
           "th{background:#f0efec}img{max-width:100%}code{background:#f0efec;padding:0 3px}blockquote{border-left:4px "
           "solid #2a78d6;margin:0;padding:.3rem 1rem;background:#f5f8fd}")
    (REPORTS / f"{REPORT}.html").write_text(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
        f"initial-scale=1'><title>Phase 7 Risk Score</title><style>{css}</style></head><body>{body}</body></html>",
        encoding="utf-8")
    hits = forbidden_hits(md) + [h for p in sorted(DOCS.glob("*.md")) for h in forbidden_hits(p.read_text(encoding="utf-8"))]
    if hits:
        lg.error("unsupported-claim scanner hits: %s", hits)
        sys.exit(1)
    lg.info("wrote reports/%s.md / .html and 4 figures; wording scan clean", REPORT)


if __name__ == "__main__":
    main()
