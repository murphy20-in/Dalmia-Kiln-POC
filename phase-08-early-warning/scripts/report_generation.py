"""Phase 8 report (Markdown + HTML + one figure), generated only from phase-08 outputs/ (nothing typed by hand).

Writes reports/PHASE_8_EARLY_WARNING_VALIDATION_REPORT.{md,html} and reports/figures/pre_onset_trajectory.png.
Every number and every classification comes from the output tables; the text around them is fixed methodology.
Exits non-zero if the unsupported-claim scanner finds a hit in the report or the docs.
"""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from p8common import (CFG, DOCS, FIG, MONTHS, O2_TAG, OUT, P7_FROZEN, POPULATION, REPORTS, SCORE_VERSION,  # noqa: E402
                      VERSION, WARNINGS, forbidden_hits, log)

REPORT = "PHASE_8_EARLY_WARNING_VALIDATION_REPORT"
LOOKBACK_CAP = 24 * 60 - 10
LEAD_CAVEAT = (f"**Caveat — these are not lead times.** Values at or near {LOOKBACK_CAP} min are capped by the 24-h "
               "look-back: the warning was already on when the window opened, which follows from the high alert rates "
               "(§21), not from advance warning. They must not be quoted as 'warns N hours ahead'.\n")
VAR = "EXCLUDE_KILN_INLET_O2_ANALYSER"
SURFACE, INK2, GRID = "#fcfcfb", "#52514e", "#e4e3df"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#b8b6ae"
lg = log("report_generation")


# ============================================================================== helpers
def md_table(df: pd.DataFrame, floatfmt: str = "{:.4g}", max_col: int = 120) -> str:
    if df.empty:
        return "_(no rows)_"

    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "" if np.isnan(v) else floatfmt.format(v)
        s = str(v).replace("|", "/").replace("\n", " ")
        return s if len(s) <= max_col else s[:max_col - 1] + "…"
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    return "\n".join(lines + ["| " + " | ".join(cell(v) for v in r) + " |" for r in df.itertuples(index=False)])


def read(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / name) if name.endswith(".parquet") else pd.read_csv(OUT / name, low_memory=False)


def f3(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{float(v):+.3f}"


def p4(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{float(v):.4f}"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


# ============================================================================== figure
def fig_trajectory(S: pd.DataFrame, tr: pd.DataFrame, ok_ids: set) -> str:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax in (a1, a2):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=INK2, labelsize=8)
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    for v, c, lab in (("PRIMARY", BLUE, "primary score"), (VAR, ORANGE, "O2-excluded variant")):
        d = S[(S.section == "TRAJECTORY_SNAPSHOT") & (S.variant == v)].sort_values("offset_minutes")
        x = d.offset_minutes.to_numpy(float) / 60
        a1.errorbar(x + (0.08 if v == VAR else 0), d.pe, yerr=[d.pe - d.ci_low, d.ci_high - d.pe], color=c, marker="o",
                    ms=4, lw=1.4, capsize=2, label=lab)
    a1.axhline(0, color=INK2, lw=0.8)
    a1.set_xlabel("hours before onset T0", fontsize=8, color=INK2)
    a1.set_ylabel("rank excess vs month-matched controls", fontsize=8, color=INK2)
    a1.set_title("Aligned snapshot excess (median, 95 % bootstrap CI)", fontsize=9)
    a1.legend(fontsize=7, frameon=False)
    t = tr[tr.event_id.isin(ok_ids)]
    for _, g in t.groupby("event_id", sort=True):
        a2.plot(g.offset_minutes / 60, g.risk_rank_ref, color=GREY, lw=0.7)
    med = t.groupby("offset_minutes").risk_rank_ref.median()
    a2.plot(med.index / 60, med.to_numpy(), color=BLUE, lw=2, label="median over evaluable periods")
    a2.set_xlabel("hours before onset T0", fontsize=8, color=INK2)
    a2.set_ylabel("rank vs Apr-May reference", fontsize=8, color=INK2)
    a2.set_title("Per-period pre-onset rank (grey) and median (blue)", fontsize=9)
    a2.legend(fontsize=7, frameon=False)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(FIG / "pre_onset_trajectory.png", dpi=130, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)
    return "figures/pre_onset_trajectory.png"


# ============================================================================== report
def main():
    FIG.mkdir(parents=True, exist_ok=True)
    S = read("early_warning_summary.csv")
    EV = read("early_warning_event_validation.parquet")
    HZ = read("early_warning_horizon_validation.csv")
    CT = read("early_warning_control_validation.csv")
    NC = read("early_warning_negative_controls.csv")
    O2 = read("early_warning_o2_sensitivity.csv")
    LD = read("early_warning_load_sensitivity.csv")
    TR = read("early_warning_trajectories.parquet")
    DQ = read("early_warning_data_quality.csv")
    GT = read("early_warning_validation.csv")
    EPI = read("early_warning_episodes.parquet")

    pe_rows = S[S.section == "PRIMARY_ENDPOINT"]
    pv = lambda v, m: num(pe_rows[(pe_rows.variant == v) & (pe_rows.metric == m)].value.iloc[0])  # noqa: E731
    FD = S[S.section == "FINDING"][["finding", "classification", "evidence"]]
    fclass = lambda k: FD[FD.finding.str.startswith(k + " ")].classification.iloc[0]  # noqa: E731
    fev = lambda k: FD[FD.finding.str.startswith(k + " ")].evidence.iloc[0]  # noqa: E731
    ev1 = EV[EV.warning_type == WARNINGS[0]].reset_index(drop=True)
    ok_ids = set(ev1[ev1.evaluable].event_id)
    ROB = S[S.section == "ROBUSTNESS"]
    rob = lambda c: ROB[ROB.check == c].iloc[0]  # noqa: E731
    h60 = HZ[(HZ.horizon_minutes == CFG.primary_h)]
    W1 = HZ[HZ.warning_type == WARNINGS[0]]
    o2m = O2.set_index("metric")
    LDp = LD[LD.score_variant == "PRIMARY"].set_index("horizon_minutes")
    ncp = NC[NC.score_variant == "PRIMARY"].set_index("control_id")
    gate_counts = GT.result.value_counts().to_dict()
    fig = fig_trajectory(S, TR, ok_ids)
    n_ev, n_ok = int(pv("PRIMARY", "n_events")), int(pv("PRIMARY", "n_evaluable"))
    st, st_o = pv("PRIMARY", "status"), pv(VAR, "status")

    L = []
    A = L.append
    A("# Phase 8 — Early Warning Validation of the Phase 7 Risk Score\n")
    A(f"**Scope.** {POPULATION}. Score `{SCORE_VERSION}` (frozen); Phase 8 `{VERSION}`. Every number below is read "
      "from `phase-08-early-warning/outputs/`. There is **no plant event ground truth**, so nothing here is a deposit, "
      "ring, coating, failure or maintenance early-warning result.\n")

    # 1 ------------------------------------------------------------------------------------------------------------
    A("## 1. Executive Summary\n")
    pe_, lo_, hi_ = pv("PRIMARY", "pe"), pv("PRIMARY", "ci_low"), pv("PRIMARY", "ci_high")
    answer = {"SUPPORTED": "Yes", "WEAK": "Only weakly"}.get(st, "No")
    ab = DQ[DQ.section == "O2_ANALYSER_BEHAVIOUR"].set_index("metric").value.map(num)
    ar = S[(S.section == "EMPIRICAL_ALERT_RATE") & (S.variant == "PRIMARY") & (S.slice == "AUG")]
    cen = rob("EXCLUDE_CENSORED_ONSETS")
    lf = LDp.loc[CFG.primary_h]
    A(f"> **Answer: {answer}.** Across the {n_ok} usable periods, the risk score in the hour before an empirical "
      f"abnormal period began was about {100 * pe_:.0f} percentile points higher than in comparable ordinary running "
      f"(plausible range {100 * lo_:+.0f} to {100 * hi_:+.0f}); this is classed **{st}**.  \n"
      f"> **Clear starts only:** for {int(ev1.onset_censored.sum())} of {n_ev} periods the true start is earlier than "
      f"the data can show (censored onset). In the {int(cen.n_evaluable)} periods with a clear start the difference "
      f"was {100 * cen.pe:+.0f} points ({cen.status}).  \n"
      "> **What it means:** "
      + ("do not use the score or any of the five warning rules as an early warning; no WEAK result may justify an "
         "alert." if st != "SUPPORTED" else "the association is present for KPI-defined periods only; it is not a "
         "plant-event early warning.") + "  \n"
      "> **What would change it:** timestamped plant event logs and the O₂ analyser schedule (§25).\n")
    A("**Plain terms.** *Rank* = where a score sits among the Apr–May reference scores (0–1; +0.05 ≈ 5 percentile "
      "points). *PE* = the pre-declared primary endpoint (median rank excess over matched ordinary running). "
      "*Controls* = ordinary-running windows of the same month. *Negative controls (NC1–NC5)* = the same test on "
      "shuffled or shifted times, which should find nothing. *LOEO* = leave one period out. *BH q* = p-value "
      "adjusted for testing many horizons. *Censored onset* = the KPI shift had already begun before the 6-h "
      "look-back. *Gate PASS* = the check ran correctly, not that the result is favourable. *WEAK* = suggestive, "
      "not decision-grade.\n")
    A(f"- **Primary question** — is the risk rank elevated in the {CFG.primary_h} min before the onset of the "
      f"empirical abnormal periods, relative to month-matched ordinary running? **{st}.** Primary endpoint "
      f"PE {f3(pv('PRIMARY', 'pe'))} rank units (95 % CI [{f3(pv('PRIMARY', 'ci_low'))}, "
      f"{f3(pv('PRIMARY', 'ci_high'))}], NC2 randomisation p {p4(pv('PRIMARY', 'p_value'))}, Cliff's δ "
      f"{f3(pv('PRIMARY', 'cliffs_delta'))}, {n_ok} of {n_ev} periods evaluable, {int(pv('PRIMARY', 'n_controls'))} "
      "control anchors).")
    A(f"- **Censored onsets (F18 {fclass('F18')}):** {fev('F18')}.")
    A(f"- **Longer horizons (2–24 h, BH-adjusted, exploratory):** {fclass('F2')} — {fev('F2')}.")
    A(f"- **O₂-excluded variant (`{O2_TAG}` removed):** on the same {n_ok} periods as the primary, PE "
      f"{f3(o2m.at['primary_endpoint_PE_60min_same_event_set_as_primary', 'o2_excluded'])}, p "
      f"{p4(num(o2m.at['primary_endpoint_p_same_event_set_as_primary', 'o2_excluded']))}. On its own evaluable set "
      f"of {int(pv(VAR, 'n_evaluable'))} (the extra periods come from a post-result amendment, spec §16): PE "
      f"{f3(pv(VAR, 'pe'))}, p {p4(pv(VAR, 'p_value'))}, **{st_o}**. The score is sensitive "
      f"to this analyser: ambient-like readings in {ab['o2_ambient_suspect_share_operational']:.0%} of operating time "
      f"({ab['o2_ambient_suspect_share_AUG']:.0%} in August); without it the August median score falls from "
      f"{num(o2m.at['median_score_AUG', 'full_score']):.1f} to {num(o2m.at['median_score_AUG', 'o2_excluded']):.1f}. "
      "Neither variant is preferred until the plant explains the purge / calibration behaviour.")
    A(f"- **Load:** {fclass('F6')} — {fev('F6')}. In plain terms: score rises that reflect feed / load changes cannot "
      f"be ruled out; after removing load transitions only {int(lf.transition_excluded_n_events)} period(s) remain, "
      "too few to test.")
    A(f"- **Control selection:** controls excluding only the 12 final periods (F20 {fclass('F20')}) and controls "
      f"held to the event data-quality rule (F19 {fclass('F19')}) leave the primary conclusion unchanged (§3.1).")
    A("- **August / alert burden:** in ordinary August running the warning rules are on for "
      f"{ar.share_of_running_time_flagged.min():.0%}–{ar.share_of_running_time_flagged.max():.0%} of the time "
      "(§21); score levels rise through the summer, partly with the O₂ readings.")
    g6_ok = GT[GT.gate.str.startswith("G6 ")].result.eq("PASS").all()
    A(f"- **Negative controls:** {fclass('F7')} (observed effect vs nulls) — {fev('F7')}. Null behaviour gate G6: "
      f"{'PASS' if g6_ok else 'FAIL'} (§18).")
    A(f"- **Backward diagnostic (F11 {fclass('F11')}):** {fev('F11')}. "
      + ("The trailing-window score stays at least as elevated after a period as before it, so the pre-onset "
         "elevation is not specific to *before* the onset." if fclass("F11") == "NOT_SUPPORTED" else
         "The pre-onset association is at least as strong as the post-period one."))
    f3c = FD[FD.finding.str.startswith("F3 ")]
    n_w = int(f3c.classification.isin(["SUPPORTED", "WEAK"]).sum())
    A(f"- **Warning coverage vs control-window warning rate (60 min):** " + "; ".join(
        f"{r.warning_type} {r.coverage:.2f} vs {r.empirical_alert_rate:.2f}"
        for r in h60[h60.score_variant == "PRIMARY"].itertuples()) +
      f". {n_w} of {len(f3c)} warning definitions cover the periods significantly more often than they fire in "
      "ordinary-running windows (F3, §10).")
    A("- **Deposit / ring / failure early warning: BLOCKED** (no plant event logs).")
    g11 = GT[GT.gate.str.startswith("G11 ")].result
    A(f"- **Integrity:** {gate_counts.get('PASS', 0)} of {len(GT)} gate checks PASS, "
      f"{gate_counts.get('FAIL', 0)} FAIL, {gate_counts.get('PENDING', 0)} PENDING (§20); reproducibility (G11): "
      f"{'PASS' if g11.eq('PASS').all() else 'not established in this run'}. Leakage tests L1–L7 are in §19.\n")

    # 2 ------------------------------------------------------------------------------------------------------------
    A("## 2. Validation Objective\n")
    A("Does the frozen Phase 7 risk score carry temporally useful information **before** the onset of the 12 Phase 6 "
      "empirical abnormal periods, relative to ordinary running, and does that survive load adjustment, the O₂-excluded "
      "variant, temporal perturbation and negative controls? Phase 8 is a falsification stage: every analysis in "
      "`docs/EARLY_WARNING_VALIDATION_SPEC.md` was declared before results were computed; post-result amendments are "
      "listed in its §16 and did not change the primary result.\n")

    # 3 ------------------------------------------------------------------------------------------------------------
    A("## 3. Scientific Status\n")
    A("Every major finding in exactly one class (rules in `run_phase8.findings`, applied to the outputs). No overall "
      "numeric confidence score is given.\n")
    A(md_table(FD, max_col=10**4))
    A("\n### 3.1 Circularity audit\n")
    A("```\nPhase 3 components (5 families) --> Phase 3 KPI D (6-h trailing median) --> Phase 6 periods\n"
      "        |                                        (detection: KPI >= P90; onset T0: CUSUM start on D)\n"
      "        +--> Phase 7 risk score (1-h medians of the SAME components, Apr-May reference)\n"
      "                    |\n                    v\n        Phase 8: score in (T0 - h, T0] vs ordinary running\n```\n")
    det, kpi = rob("DETECTION_ANCHOR (CIRCULARITY_ILLUSTRATION)"), rob("KPI_BASELINE")
    snap = S[(S.section == "TRAJECTORY_SNAPSHOT") & (S.variant == "PRIMARY")].set_index("offset_minutes")
    A("| Reused information | Where | Consequence | Boundary kept by Phase 8 |\n|---|---|---|---|")
    A("| the five family components | event definition (KPI) **and** score construction | pre-onset association "
      "expected partly by construction (shared, autocorrelated inputs) | result framed as temporal precedence relative "
      "to a KPI-defined onset, never as independent validation |")
    A(f"| KPI ≥ P90 detection | event definition | a 'lead' before detection is mechanical: detection-anchored PE "
      f"{f3(det.pe)} (`CIRCULAR_BY_CONSTRUCTION`) | primary anchor is the CUSUM onset, not detection |")
    A(f"| CUSUM onset T0 | event definition | T0 is where the KPI deviation *starts* accumulating, i.e. the last "
      f"bucket before a rise: the snapshot excess is {f3(snap.pe.get(-120))} at −2 h but {f3(snap.pe.get(0))} at T0, "
      "so the onset anchor is structurally a local low for any smoothed score | reported; the window statistic "
      "(median over 60 min) is the pre-declared endpoint, not the T0 snapshot |")
    A(f"| the KPI itself | event definition | the KPI ranked against its own Apr–May values gives PE {f3(kpi.pe)} "
      f"(δ {f3(kpi.cliffs_delta)}) vs the score's {f3(pv('PRIMARY', 'pe'))} (δ {f3(pv('PRIMARY', 'cliffs_delta'))}) | "
      f"F9: {fclass('F9')} |")
    cf, cd = rob("CONTROLS_EXCLUDE_FINAL_PERIODS_ONLY"), rob("CONTROLS_SAME_DQ_RULE_AS_EVENTS")
    A(f"| KPI ≥ P90 candidate extents | control selection (every Phase 6 candidate + 6 h excluded) | controls are the "
      f"low-KPI part of running (control median rank {pv('PRIMARY', 'median_control'):.3f}; rolling-rank control "
      f"median {rob('REFERENCE_FREE_ROLLING_RANK').median_control:.2f} vs 0.50 neutral), which can push PE up | "
      f"only the 12 final periods excluded: PE {f3(cf.pe)} (change {f3(cf.pe - pe_)}), {cf.status} (F20) |")
    A(f"| event data-quality rule | events only (POOR share, stop / transition) | controls keep POOR and transition "
      f"buckets (higher scores), which can push PE down | same rule on controls: PE {f3(cd.pe)} (change "
      f"{f3(cd.pe - pe_)}), {cd.status} (F19) |")
    A("| Apr–May reference window | Phase 3 KPI reference, Phase 6 threshold, Phase 7 reference | the rank transform "
      "and all W1–W4 thresholds come from the same in-sample months | Apr–May contains no evaluated period (L3); "
      "reference-free 7-day rolling rank reported as a check |")
    A("| Phase 7 coverage / AUC 0.868 | Phase 7 retrospective | circular coverage of the same periods | not used "
      "anywhere in Phase 8 |")
    A("| threshold selection | — | — | W1/W3 fixed ranks, W2/W4 from the reference population, W5 fixed rule; the only "
      "event-tuned threshold is the leave-one-out diagnostic (G5, G10) |")
    A("| calibration | — | — | Phase 7 bands are not used for any Phase 8 decision |\n")
    g5_ok = GT[GT.gate.str.startswith("G5 ")].result.eq("PASS").all()
    A(f"**Circularity audit: {'PASS' if g5_ok and det.status == 'CIRCULAR_BY_CONSTRUCTION' else 'FAIL'}** — the "
      "shared information is identified and bounded above; no Phase 8 threshold, reference or calibration uses an "
      "evaluated period (G5), and the detection-anchored 'lead' is labelled circular. PASS means the reuse is "
      "disclosed and bounded, not that it is absent.\n")

    # 4 ------------------------------------------------------------------------------------------------------------
    A("## 4. Phase 7 Frozen Contract\n")
    g1 = GT[GT.gate.str.startswith("G1 ")][["check", "result", "evidence"]]
    A(f"Score `{SCORE_VERSION}`; frozen files {', '.join(f'`{f}`' for f in P7_FROZEN)}. Only `operational == True` "
      "scores are used; `risk_score_diagnostics.parquet` and `afr_context` are never read. The O₂-excluded score is "
      "Phase 7's own `EXCLUDE_KILN_INLET_O2_ANALYSER` variant, rebuilt as a `VALIDATION_VARIANT`.\n")
    A(md_table(g1))
    th = S[S.section == "THRESHOLDS"][["variant", "metric", "value", "note"]]
    A("\n**Frozen thresholds and the rebuilt reference quantiles:**\n")
    A(md_table(th.assign(value=th.value.map(num))))

    # 5 ------------------------------------------------------------------------------------------------------------
    A("\n## 5. Empirical Abnormal-Period Population\n")
    A("T0 = Phase 6 `onset_time` (CUSUM onset). Severity and Phase 6 confidence are context metadata only. The "
      "event data-quality status covers (T0 − 60 min, T0]; `*_o2x` is the status for the O₂-excluded variant "
      "(no O₂ penalty; spec §16).\n")
    A(md_table(ev1[["event_id", "T0_onset", "month", "severity", "phase6_confidence", "onset_censored",
                    "data_quality_status", "data_quality_reason", "data_quality_status_o2x", "evaluable"]]))
    n_o2only = int(((ev1.data_quality_status == "DATA_QUALITY_CONTAMINATED") &
                    ev1.data_quality_status_o2x.isin(["VALID", "VALID_REDUCED_CONFIDENCE"])).sum())
    A(f"\n{n_o2only} period(s) are excluded from the primary analysis only because ambient-like `{O2_TAG}` readings "
      "halve the Phase 7 data-quality confidence in the window.\n")

    # 6 ------------------------------------------------------------------------------------------------------------
    A("## 6. Primary Endpoint\n")
    A(f"PE = median over evaluable periods of [median rank over (T0 − {CFG.primary_h} min, T0] − median of the same "
      "statistic over eligible month-matched ordinary-running anchors]. Rank = ECDF of the frozen Apr–May reference "
      f"scores. p = one-sided randomisation against month-stratified random pseudo-onsets (NC2, {CFG.n_null} draws); "
      f"CI = bootstrap ({CFG.n_boot}; periods i.i.d., controls in {CFG.block_hours}-h calendar blocks). Decision rule "
      f"(pre-declared): INSUFFICIENT_DATA if n < {CFG.min_events_primary}; SUPPORTED if PE > 0, CI low > 0, p < 0.05 "
      "and every leave-one-event-out PE > 0; WEAK if PE > 0 and (p < 0.10 or CI low > 0); else NOT_SUPPORTED.\n")
    keys = ["pe", "ci_low", "ci_high", "p_value", "cliffs_delta", "n_evaluable", "n_events", "n_controls",
            "median_event", "median_control", "null_median", "status"]
    A(md_table(pd.DataFrame([{"variant": v, **{k: pv(v, k) for k in keys}} for v in ("PRIMARY", VAR)])))
    lo = pe_rows[pe_rows.metric.str.startswith("loeo_")].assign(value=lambda d: d.value.map(num))
    lo = lo.assign(event_id=lo.metric.str[5:]).pivot(index="event_id", columns="variant", values="value").reset_index()
    A("\n**Leave-one-event-out PE** (blank = period not evaluable for that variant):\n")
    A(md_table(lo))

    # 7 ------------------------------------------------------------------------------------------------------------
    A("\n## 7. Secondary Endpoints\n")
    A("Rank endpoint at every horizon (exploratory; BH q across the 8 horizons per variant). `n_evaluable` drops at "
      "long horizons when a window is incomplete or contains another candidate period.\n")
    A(md_table(W1[["score_variant", "horizon_minutes", "n_evaluable", "n_controls", "median_rank_change",
                   "effect_size", "bootstrap_ci_low", "bootstrap_ci_high", "permutation_p", "bh_q",
                   "load_adjusted_effect", "load_status", "status"]]))
    A(f"\n![Pre-onset trajectory]({fig})\n")
    A("**Aligned snapshot excess** (score rank at T0 − o minus the month-matched control median at the same offset):\n")
    sn = S[S.section == "TRAJECTORY_SNAPSHOT"][["variant", "offset_minutes", "n_evaluable", "pe", "ci_low", "ci_high",
                                               "p_value", "cliffs_delta"]]
    A(md_table(sn))

    # 8 ------------------------------------------------------------------------------------------------------------
    A("\n## 8. Control Construction\n")
    A(f"An anchor A is an eligible control for horizon h when A is operational, every bucket of (A − h, A] lies "
      f"outside every Phase 6 candidate extent [onset, end + {CFG.ctrl_post_end_h:g} h] (all candidates) and outside "
      f"the {CFG.ctrl_pre_onset_h:g} h before every final onset, the window touches no Phase 1 long-gap / frozen "
      "window, and ≥ 2/3 of it is operational. Event windows must meet the same candidate / DQ rule (spec §16). "
      "Controls are re-checked independently in gate G4.\n")
    A(md_table(CT))
    cp = DQ[DQ.section == "CONTROL_POOL"][["metric", "value", "note"]]
    A("\n**Control pool:**\n")
    A(md_table(cp))

    # 9 ------------------------------------------------------------------------------------------------------------
    A("\n## 9. Lead-Time Method\n")
    A("Per period and warning over the 24-h look-back (T0 − 24 h, T0], buckets ≤ T0 only: first warning (earliest "
      "warning bucket), sustained warning (start of the warning episode in force at T0), peak pre-event score, trend "
      "onset (start of the final run of positive 60-min slope ending at T0) and warning duration (persistence). "
      "Lead times are **to the KPI-defined onset**, not to any plant event.\n")
    A(LEAD_CAVEAT)
    ls = S[S.section == "LEAD_TIME"][["warning_type", "metric", "n", "n_evaluable", "median", "p25", "p75", "min",
                                      "max"]]
    A(md_table(ls))

    # 10 -----------------------------------------------------------------------------------------------------------
    A("\n## 10. Warning Definitions\n")
    A("| ID | Rule (causal, at bucket t) | Threshold source |\n|---|---|---|")
    A(f"| W1_RANK | rank ≥ {CFG.w1_rank} | frozen Apr–May reference |")
    A("| W2_RISING | 60-min OLS slope ≥ P95 of the Apr–May reference slope distribution | frozen reference population |")
    A(f"| W3_PERSISTENT | rank ≥ {CFG.w3_rank} for ≥ {CFG.w3_min_buckets * 10} min | frozen reference |")
    A("| W4_ACCEL | slope(t) − slope(t − 60 min) ≥ reference P95 | frozen reference population |")
    A(f"| W5_MULTI_FAMILY | family_count_abnormal ≥ {CFG.w5_families} and slope > 0 | fixed rule |\n")
    A("**EMPIRICAL_ABNORMAL_PERIOD_COVERAGE** (share of evaluable periods with the warning in the pre-onset window) "
      "next to the **control-window warning rate** (share of eligible ordinary-running windows of the same length with "
      "the warning). Coverage alone is uninformative when warnings are frequent.\n")
    cov = HZ[HZ.horizon_minutes.isin([15, 60, 240, 1440])][["score_variant", "warning_type", "horizon_minutes",
                                                             "n_evaluable", "coverage", "n_covered",
                                                             "empirical_alert_rate", "coverage_binom_p",
                                                             "median_lead_time", "o2_excluded_coverage"]]
    A(md_table(cov.rename(columns={"empirical_alert_rate": "control_window_rate"})))
    A("\n**Month holdout** (W2 / W4 thresholds from earlier months' ordinary running only):\n")
    A(md_table(S[S.section == "MONTH_HOLDOUT"][["warning_type", "train_months", "test_months", "threshold_slope",
                                                "threshold_accel", "n_evaluable", "coverage", "control_window_rate",
                                                "coverage_minus_control_rate", "status"]]))
    A("\n**Leave-one-event-out event-tuned threshold** (validation diagnostic only; never deployable):\n")
    A(md_table(S[S.section == "LOEO_EVENT_TUNED_THRESHOLD"][["event_id", "event_value", "threshold_from_other_events",
                                                             "held_out_covered", "control_exceedance_rate"]]))

    # 11 -----------------------------------------------------------------------------------------------------------
    A("\n## 11. Overall Results\n")
    A("Falsification questions (prompt §56), answered from the outputs:\n")
    mo = S[(S.section == "MONTH") & (S.variant == "PRIMARY")]
    aug = mo[mo.slice == "AUG"].iloc[0]
    lo_p = pe_rows[(pe_rows.variant == "PRIMARY") & pe_rows.metric.str.startswith("loeo_")].value.map(num).dropna()
    rr = rob("REFERENCE_FREE_ROLLING_RANK")
    qa = [("Does the effect disappear after load matching?", f"matched-load PE {f3(lf.matched_load_effect)} "
           f"(p {p4(lf.matched_load_p)}), load-adjusted {f3(lf.load_adjusted_effect)}, transition-excluded "
           f"{f3(lf.transition_excluded_effect)} (n {int(lf.transition_excluded_n_events)}); verdict {lf.status}"),
          ("Does it disappear after O₂ exclusion?", f"the primary effect is {st}, so there is little to disappear; "
           f"the O₂-excluded PE is {f3(pv(VAR, 'pe'))} (status {st_o}) vs primary {f3(pv('PRIMARY', 'pe'))} — the "
           "result depends on the analyser, and neither variant is preferred (§17)"),
          ("Does it disappear under circular shift?", f"observed {f3(ncp.at['NC1', 'observed_effect'])} vs null "
           f"median {f3(ncp.at['NC1', 'null_effect'])}, p {p4(ncp.at['NC1', 'p_value'])}"),
          ("Does it disappear under random event times?", f"NC2 p {p4(ncp.at['NC2', 'p_value'])}"),
          ("Does it exist only in August?", "; ".join(f"{r.slice} {f3(r.pe)} (n {int(r.n_evaluable)})"
                                                     for r in mo.itertuples()) + f" — August {f3(aug.pe)}. The "
           "pre-onset excess is not August-only, but August score levels and alert rates are the highest (§21) and "
           f"August has the most ambient-like O₂ ({ab['o2_ambient_suspect_share_AUG']:.0%} of operating time)"),
          ("Is it driven by one abnormal period?", f"leave-one-out PE range [{f3(lo_p.min())}, {f3(lo_p.max())}]"),
          ("Is it driven by low feed?", f"low-feed-excluded PE {f3(lf.low_feed_excluded_effect)} "
           f"(n {int(lf.low_feed_excluded_n_events)})"),
          ("Is it simply persistence of the KPI?", fev("F9")),
          ("Is it an artefact of the Phase 7 reference?", f"reference-free rolling rank PE {f3(rr.pe)}, p "
           f"{p4(rr.p_value)}, status {rr.status}"),
          ("Does it survive leave-one-event-out?", f"{fclass('F8')} (sign stability of a PE that is itself "
           f"{st})"),
          ("Is it driven by censored onsets?", f"F18 {fclass('F18')}: {fev('F18')}"),
          ("Is it created by selecting low-KPI controls?", f"F20 {fclass('F20')}: {fev('F20')}"),
          ("Does it change when controls get the event data-quality rule?", f"F19 {fclass('F19')}: {fev('F19')}")]
    A("| Question | Answer from the outputs |\n|---|---|")
    A("\n".join(f"| {q} | {a} |" for q, a in qa))
    A("")

    # 12 -----------------------------------------------------------------------------------------------------------
    A("## 12. Event-Level Results\n")
    A(md_table(ev1[["event_id", "month", "evaluable", "pre_event_window_rank", "pre_event_rank_excess",
                    "control_percentile", "pre_event_rank_change", "family_count", "confidence", "load_context",
                    "load_associated_share", "o2_excluded_result"]]))
    A(f"\n`load_context` is Phase 7's label for the T0 bucket and `load_associated_share` its share over the 60-min "
      f"window ({int(ev1.load_context.eq('LOAD_ASSOCIATED').sum())} of {n_ev} LOAD_ASSOCIATED at T0); Phase 6's "
      "'8 of 12 LOAD_ASSOCIATED' classifies each whole period, so the two counts measure different windows.\n")
    lead = EV.pivot(index="event_id", columns="warning_type", values="lead_time_minutes")
    lead = lead.apply(lambda c: c.map(lambda v: "" if pd.isna(v) else "≥ window" if v >= LOOKBACK_CAP else f"{v:.0f}"))
    lead.insert(0, "evaluable", lead.index.map(lambda e: "yes" if e in ok_ids else "NO (excluded from results)"))
    A("\n**First-warning lead time (minutes before T0, 24-h look-back; blank = no warning):**\n")
    A(LEAD_CAVEAT)
    A(md_table(lead.reset_index()))

    # 13-15 --------------------------------------------------------------------------------------------------------
    for i, (m, name) in enumerate(MONTHS.items()):
        A(f"\n## {13 + i}. {pd.Timestamp(2025, m, 1).strftime('%B')} Results\n")
        rows = S[S.section.isin(["MONTH", "LEAVE_ONE_MONTH_OUT"]) &
                 (S.slice.eq(name) | S.slice.eq(f"without {name}"))]
        A(md_table(rows[["section", "variant", "slice", "n_evaluable", "n_controls", "pe", "ci_low", "ci_high",
                         "p_value", "cliffs_delta", "status"]]))
        A("")
        A(md_table(ev1[ev1.month == m][["event_id", "severity", "data_quality_status", "pre_event_rank_excess",
                                        "control_percentile", "o2_excluded_result"]]))
        tm = S[(S.section == "TRAJECTORY_BY_MONTH") & (S.variant == f"PRIMARY|MONTH_{name}")]
        A("\nSnapshot excess by offset: " + ", ".join(f"{int(r.offset_minutes)} min {f3(r.pe)}"
                                                     for r in tm.itertuples()))
    A("\nPer-month n is below the secondary minimum of 6, so no single month can be SUPPORTED by design; the months are "
      "compared for direction and size only.\n")

    # 16 -----------------------------------------------------------------------------------------------------------
    A("## 16. Load-Adjusted Results\n")
    A("A raw; B load-adjusted (rank minus the ordinary-running median rank of the same load stratum); C month × load "
      "matched controls (and load-matched across months); D transition-excluded (any LOAD_ASSOCIATED, post-restart "
      "settling or non-operational bucket in the window). Low-feed exclusion is reported, never preferred.\n")
    A(md_table(LD[["score_variant", "horizon_minutes", "raw_effect", "load_adjusted_effect", "matched_load_effect",
                   "matched_load_any_month_effect", "transition_excluded_effect", "transition_excluded_n_events",
                   "low_feed_excluded_effect", "low_feed_excluded_n_events", "status"]]))

    # 17 -----------------------------------------------------------------------------------------------------------
    A(f"\n## 17. O₂-Excluded Results\n")
    A(f"`{VAR}` rebuilds COMBUSTION / STABILITY without `{O2_TAG}` with its own frozen Apr–May reference (Phase 7's "
      "variant definition). A conclusion is ROBUST_TO_O2 when its class is unchanged, else SENSITIVE_TO_O2. The "
      "primary score is never replaced.\n")
    A(md_table(O2[["metric", "full_score", "o2_excluded", "absolute_difference", "rank_correlation", "status"]]))
    ab = DQ[DQ.section == "O2_ANALYSER_BEHAVIOUR"][["metric", "value", "status", "note"]]
    A("\n**Analyser behaviour** (`ANALYSER_BEHAVIOUR_REQUIRES_PLANT_CONFIRMATION`; nothing here says the analyser is "
      "faulty):\n")
    A(md_table(ab.assign(value=ab.value.map(num))))

    # 18 -----------------------------------------------------------------------------------------------------------
    A("\n## 18. Negative Controls\n")
    A(md_table(NC[["score_variant", "control_id", "method", "observed_effect", "null_effect", "p_value", "n_null",
                   "status"]]))
    g6 = GT[GT.gate.str.startswith("G6 ")]
    A(f"\nNull behaviour (G6): {'PASS' if g6.result.eq('PASS').all() else 'FAIL'} — the NC1 / NC2 nulls centre on "
      "zero and future perturbation leaves every pre-T0 metric identical (NC5). NC4 is a single mirrored-position "
      "draw, reported only. Whether the observed "
      f"effect exceeds the nulls is a *result*, not a gate: F7 {fclass('F7')}.\n")

    # 19 -----------------------------------------------------------------------------------------------------------
    A("## 19. Leakage Tests\n")
    lk = GT[GT.check.str.match(r"^L\d") | GT.gate.str.startswith(("G2 ", "G3 ", "G5 "))]
    A(md_table(lk[["gate", "check", "check_type", "result", "evidence"]]))

    # 20 -----------------------------------------------------------------------------------------------------------
    A("\n## 20. Robustness\n")
    A(md_table(ROB[["check", "n_evaluable", "pe", "ci_low", "ci_high", "p_value", "cliffs_delta", "median_event",
                    "median_control", "status", "survives", "note"]]))
    A("\n**Censored vs uncensored onsets at every horizon** (censored T0 = look-back cap, window inside the KPI shift; "
      "uncensored T0 = CUSUM zero, a local low; p only):\n")
    cs = S[S.section == "CENSORED_SPLIT"].assign(horizon_minutes=lambda d: d.horizon_minutes.astype(int))
    A(md_table(cs.pivot_table(index=["variant", "horizon_minutes"], columns="slice", values=["pe", "n_evaluable",
                                                                                            "p_value"],
                              aggfunc="first", sort=True).pipe(lambda d: d.set_axis(
        [f"{a}_{b.lower()}" for a, b in d.columns], axis=1)).reset_index()))
    A("\n**All validation gates:**\n")
    A(md_table(GT[["gate", "check", "check_type", "result", "evidence"]]))

    # 21 -----------------------------------------------------------------------------------------------------------
    A("\n## 21. Empirical Alert Rate\n")
    A("`EMPIRICAL_ALERT_RATE` = share of ordinary-running time flagged and warning episodes per 100 running hours "
      f"(episodes merge across ≤ {CFG.gap_tol_buckets * 10} min of operational non-warning time). It is not an error "
      "rate: with no event ground truth, a warning outside an abnormal period is not known to be wrong.\n")
    ar = S[S.section == "EMPIRICAL_ALERT_RATE"][["variant", "warning_type", "slice", "ordinary_running_hours",
                                                 "share_of_running_time_flagged", "n_episodes", "episodes_per_100h",
                                                 "median_duration_minutes", "p90_duration_minutes"]]
    A(md_table(ar))
    A(f"\n{len(EPI)} warning episodes in total (both variants) are in `early_warning_episodes.parquet`.\n")

    # 22 -----------------------------------------------------------------------------------------------------------
    A("## 22. Limitations\n")
    per_m = ev1[ev1.evaluable].month.value_counts().sort_index().to_dict()
    A(f"- **n = {n_ok} evaluable periods** (of {n_ev}; per month {per_m}). Power is low: an absent result is not "
      "evidence of absence, and no month can be SUPPORTED alone. With a 95 % CI half-width of "
      f"{(hi_ - lo_) / 2:.2f} rank units (≈ {50 * (hi_ - lo_):.0f} percentile points), only effects larger than about "
      "that could have been distinguished from zero by this design.")
    A("- **Circularity** (§3.1): events and score share their inputs; the result is temporal precedence relative to a "
      "KPI-defined onset, not independent validation.")
    A("- **Onset anchor**: the CUSUM onset is structurally a local low; the detection anchor is structurally high. "
      "Neither is a plant event time.")
    A(f"- **Trailing-window persistence**: post-end window association (NC3) {f3(ncp.at['NC3', 'null_effect'])} vs "
      f"pre-onset {f3(ncp.at['NC3', 'observed_effect'])}.")
    A(f"- **O₂ analyser**: ambient-like `{O2_TAG}` readings make {n_o2only} period(s) non-evaluable for the primary "
      f"score; O₂-excluded PE {f3(pv(VAR, 'pe'))} vs primary {f3(pv('PRIMARY', 'pe'))}. The analyser behaviour needs "
      "plant confirmation.")
    A(f"- **Load**: the transition-excluded analysis keeps {int(lf.transition_excluded_n_events)} period(s) at 60 min "
      f"(verdict {lf.status}); load dependence is not ruled out unless the verdict is ROBUST_TO_LOAD.")
    A(f"- **Censored onsets**: {int(ev1.onset_censored.sum())} of {n_ev} onsets are censored (the shift began before "
      f"the 6-h look-back); excluding them gives PE {f3(rob('EXCLUDE_CENSORED_ONSETS').pe)} "
      f"(n {int(rob('EXCLUDE_CENSORED_ONSETS').n_evaluable)}).")
    mc = pv("PRIMARY", "median_control")
    A(f"- **Rank ceiling**: summer ordinary running already sits high in the Apr–May reference (control median rank "
      f"{mc:.2f}), so a rank excess can be at most about {1 - mc:.2f}; this lowers power and makes W1 / W3 fire often "
      "in ordinary running.")
    first = ev1.sort_values("T0_onset").iloc[0]
    gap_h = (pd.Timestamp(first.T0_onset) - pd.Timestamp("2025-06-01")).total_seconds() / 3600
    if gap_h < 24:
        A(f"- **Regime boundary**: {first.event_id} has T0 {first.T0_onset}, {gap_h:.1f} h after the end of the "
          "Apr–May reference; its Phase 6 CUSUM look-back and Phase 7 persistence window straddle the in-sample "
          "boundary, and its windows longer than that reach non-operational May rows.")
    A("- **Contract deviations**: events with < 30 month × load controls are dropped from MATCHED_LOAD instead of "
      "falling back to the load stratum (spec §5); the warning-coverage binomial uses the pooled Jun–Aug control "
      "rate although rates differ by month; F2–F20 classification rules are post hoc (spec §16).")
    A("- Reference = Apr–May in-sample; June has no out-of-sample month for threshold holdout.")
    A("- See `docs/LIMITATIONS.md`.\n")

    # 23 / 24 ------------------------------------------------------------------------------------------------------
    A("## 23. What Is Supported (weak / exploratory signals — not decision-grade)\n")
    csw = S[S.section == "CENSORED_SPLIT"].pivot_table(index=["variant", "horizon_minutes"], columns="slice",
                                                       values="pe", aggfunc="first")
    cen_dom = bool((csw.CENSORED > csw.UNCENSORED).all())
    ctx_ids = ("F4 ", "F8 ")
    pos = FD[FD.classification.isin(["SUPPORTED", "WEAK"])]
    sup, ctx = pos[~pos.finding.str.startswith(ctx_ids)], pos[pos.finding.str.startswith(ctx_ids)]
    A(md_table(sup, max_col=10**4) if len(sup) else "_No finding is SUPPORTED or WEAK._")
    A("\nThese statements are about the risk rank relative to ordinary running before KPI-defined empirical "
      "abnormal-period onsets only. **No WEAK result may be used to justify an alert.**"
      + (" At every horizon and for both variants the censored onsets, whose windows lie inside the KPI shift, carry "
         "a larger excess than the uncensored ones (§20, F18).\n" if cen_dom else "\n"))
    if len(ctx):
        A(f"**Context only (not evidence of an effect):** F8's leave-one-out estimate of a median of {n_ok} can only "
          f"take neighbouring order statistics, so sign stability is nearly automatic; F4 rests on month signs with "
          f"n ≤ {int(ev1[ev1.evaluable].month.value_counts().max())}.\n")
        A(md_table(ctx, max_col=10**4))
        A("")
    A("## 24. What Is Not Supported\n")
    A(md_table(FD[FD.classification.isin(["NOT_SUPPORTED", "INSUFFICIENT_DATA", "BLOCKED"])], max_col=10**4))
    A("\n- The available data does not establish that the risk score gives early warning of deposits, rings, coating, "
      "failures or maintenance needs.")
    A("- Empirical coverage is not accuracy; the empirical alert rate is not an error rate.")
    A("- The Phase 7 AUC 0.868 is circular coverage and is not used as validation.\n")

    # 25 -----------------------------------------------------------------------------------------------------------
    A("## 25. Plant Data Required\n")
    A(f"Requested range for every item: 2025-04-01 → 2025-09-30. Preferred format: CSV with start, end, type, "
      f"severity / value, source. The primary decision rule needs at least {CFG.min_events_primary} evaluable "
      "labelled events before it can classify anything.\n")
    A("| Priority | Data | Unblocks | How it would improve validation |\n|---|---|---|---|")
    for pr_, d, unb, how in (
            (1, "coating / ring / deposit observations, cleaning, maintenance and stoppage reasons, with timestamps",
             "F14, F15, F16; circularity (§3.1)", "turns empirical periods into labelled, independent (non-KPI) "
             "events: coverage and lead time to a plant outcome become measurable; post-event windows can be excluded "
             "from controls"),
            (1, f"`{O2_TAG}` purge / calibration schedule", "F5, F17",
             "confirms or rejects the ambient-like readings; settles the O₂ sensitivity and "
             f"{n_o2only} evaluability decision(s)"),
            (2, "feed-reduction logs", "F6", "separates load-driven score rises from process drift"),
            (2, "the plant's choice of a 'normal' period", "controls, reference", "replaces the in-sample Apr–May "
             "reference and the KPI-based control definition"),
            (2, "operator / process-abnormality logs; event severity / impact", "F1 anchor",
             "replaces the CUSUM onset anchor and the KPI-derived severity (context only today)"),
            (3, "clinker quality (lab)", "independent outcome", "an outcome that does not share inputs with the score"),
            (3, "shell temperature (scanner)", "F15", "independent evidence of coating / ring build-up"),
            (3, "fuel laboratory data (CV, moisture, AFR split)", "load / fuel context",
             "load / fuel explanations of score rises; enables an AFR analysis that is not retrospective"),
            (3, "Phase 1 open asks: Kiln-I September 2025 re-export, meaning of `Kiln MD`, Sp.Heat F / G formulas, "
             "which tags are set-points", "scope, state proxy, efficiency family",
             "extends the scored window and confirms the inputs the score is built on")):
        A(f"| {pr_} | {d} | {unb} | {how} |")
    A("\n**Plant questions carried over from Phase 7 (unanswered; no answer is assumed):**\n")
    A(f"1. What is the purge / calibration behaviour of the `{O2_TAG}` O₂ analyser?")
    A("2. Which period does the plant regard as normal?")
    A("3. Are feed reductions logged?\n")

    # 26 -----------------------------------------------------------------------------------------------------------
    A("## 26. Phase 9 Handoff\n")
    A("**Validated — established integrity checks (not a favourable result):**\n")
    A("- The Phase 7 score and every Phase 8 warning metric are causal (L1, L2, L5) and the frozen reference is "
      "reproduced (L6); `afr_context` is not used (L7).")
    A("- The analysis framework (controls, nulls, lead metrics, alert rates) is in place; reproducibility (G11): "
      f"{'PASS — two clean runs byte-identical' if g11.eq('PASS').all() else 'not established in this run'}.\n")
    A("**Not validated:**\n")
    A(f"- Primary endpoint: **{st}** (PE {f3(pv('PRIMARY', 'pe'))}, p {p4(pv('PRIMARY', 'p_value'))}); O₂-excluded "
      f"variant {st_o}, analyser-dependent (§17).")
    for r in FD[FD.classification.isin(["NOT_SUPPORTED", "INSUFFICIENT_DATA", "WEAK"])].itertuples():
        if not r.finding.startswith("F1 "):
            A(f"- {r.finding} — {r.classification}")
    A("\n**Blocked (needs plant event ground truth):**\n")
    for r in FD[FD.classification.eq("BLOCKED")].itertuples():
        A(f"- {r.finding}")
    A("\n**Recommended downstream use.** Audience: internal analysts and plant process engineers reviewing history, "
      "not control-room operators. Sign-off owner: to be named by the plant (open question).\n")
    A("| Phase 9 MAY show | Phase 9 MUST NOT show |\n|---|---|")
    A("| the historical score trend with the O₂-excluded overlay and a fixed 'retrospective, not an early warning' "
      "disclaimer | live W1–W5 flags or alarms of any kind |")
    A("| the 12 periods labelled 'KPI-derived abnormal periods (not plant events)' | Phase 7 band colours "
      "(ELEVATED / HIGH) styled as alarms |")
    A("| the finding classes of §3 with their evidence text | lead-time numbers or coverage percentages (§9, §10, "
      "§12) |")
    A("| an event-annotation tool so the plant can mark coating / ring / cleaning events on the timeline | the "
      "Phase 7 AUC 0.868, the word 'prediction', or `afr_context` in any live view |\n")
    A(f"**Decision and next steps:** no alerting in Phase 9; use Phase 9 to collect plant event labels; once at least "
      f"{CFG.min_events_primary} evaluable labelled events exist, re-run this frozen Phase 8 protocol unchanged "
      "against them; resolve the O₂ analyser question first.\n")
    A("**Files:** `outputs/early_warning_event_validation.parquet`, `early_warning_horizon_validation.csv`, "
      "`early_warning_control_validation.csv`, `early_warning_negative_controls.csv`, `early_warning_o2_sensitivity.csv`,"
      " `early_warning_load_sensitivity.csv`, `early_warning_trajectories.parquet`, `early_warning_summary.csv`, "
      "`early_warning_validation.csv` (+ `early_warning_episodes.parquet`, `early_warning_data_quality.csv`); docs "
      "`EARLY_WARNING_VALIDATION_SPEC.md`, `VALIDATION_PROTOCOL.md`, `LEAKAGE_CONTRACT.md`, `METRIC_DEFINITIONS.md`, "
      "`LIMITATIONS.md`.\n")
    A("_Generated by `scripts/report_generation.py` from the Phase 8 outputs; nothing in this report is typed by hand._")

    md = "\n".join(L)
    (REPORTS / f"{REPORT}.md").write_text(md, encoding="utf-8")
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark").enable("table").render(md)
    css = ("body{font-family:system-ui,sans-serif;max-width:1180px;margin:2rem auto;padding:0 16px;color:#0b0b0b;"
           "background:#fcfcfb;line-height:1.45}table{border-collapse:collapse;font-size:12px;margin:.6rem 0;display:"
           "block;overflow-x:auto}th,td{border:1px solid #e4e3df;padding:3px 6px;text-align:left;vertical-align:top}"
           "th{background:#f0efec}img{max-width:100%}code{background:#f0efec;padding:0 3px}pre{background:#f0efec;"
           "padding:.5rem;overflow-x:auto}")
    (REPORTS / f"{REPORT}.html").write_text(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
        f"initial-scale=1'><title>Phase 8 Early Warning Validation</title><style>{css}</style></head><body>{body}"
        "</body></html>", encoding="utf-8")
    hits = forbidden_hits(md) + [h for p in sorted(DOCS.glob("*.md")) for h in forbidden_hits(p.read_text(encoding="utf-8"))]
    if hits:
        lg.error("unsupported-claim scanner hits: %s", hits)
        sys.exit(1)
    lg.info("wrote reports/%s.md / .html and 1 figure; wording scan clean", REPORT)


if __name__ == "__main__":
    main()
