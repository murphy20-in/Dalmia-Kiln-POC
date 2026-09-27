"""Step 10 - Phase 4 report (MD + HTML) and figures, generated only from Phase 4 outputs.

Writes reports/PHASE_4_LEADING_INDICATORS.md / .html, reports/figures/*.png, outputs/indicator_version_manifest.csv
The review log (reviews/REVIEW_LOG.md) is summarised when present.
"""
from __future__ import annotations

import json
import platform
from dataclasses import asdict

import matplotlib
import numpy as np
import pandas as pd
import scipy
import sklearn

from p4common import (CACHE, EPISODE_LABEL, FEATURE_DOC, FIG, HOLDOUT, INDICATOR_LABEL, MATERIALITY, METHOD_VERSION, OUT,
                      PHASE_DIR, PRIMARY, PROXY_LABEL, REPLICATION_MONTHS, REPORTS, THRESHOLD_LABEL, log, read_out, sha256,
                      write_csv)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

lg = log("generate_report")
# Reference categorical palette (dataviz skill, light mode), fixed order; neutral gray for context.
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"
GRAY, INK, INK2 = "#9a9893", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#c9c8c2", "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "#fcfcfb",
                     "axes.facecolor": "#fcfcfb", "svg.hashsalt": "p4"})


def md_table(df: pd.DataFrame, max_rows: int | None = None, max_col: int = 80, floatfmt: str = "{:.3g}") -> str:
    if df is None or df.empty:
        return "_None._\n"
    d = df.head(max_rows) if max_rows else df

    def cell(v):
        if isinstance(v, (float, np.floating)):
            s = "" if np.isnan(v) else (str(int(v)) if float(v).is_integer() and abs(v) < 1e12 else floatfmt.format(v))
        else:
            s = "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return s if len(s) <= max_col else s[: max_col - 1] + "…"
    out = "| " + " | ".join(map(str, d.columns)) + " |\n| " + " | ".join("---" for _ in d.columns) + " |\n"
    out += "".join("| " + " | ".join(cell(v) for v in r) + " |\n" for r in d.itertuples(index=False))
    if max_rows and len(df) > max_rows:
        out += f"\n_{len(df) - max_rows} more rows in the CSV._\n"
    return out


def save(fig, name: str) -> str:
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=100, metadata={"Software": None})
    plt.close(fig)
    return f"figures/{name}"


def fig_lag_profiles(lagdf: pd.DataFrame, ids: list[str], title: str, name: str) -> str:
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    for c, col in zip(ids[:4], [S1, S2, S3, S4]):
        g = lagdf[(lagdf.indicator_id == c) & (lagdf.window == "REPL")].sort_values("lag_minutes")
        x = np.arange(len(g))
        ax.plot(x, g.rho_p, color=col, lw=2, marker="o", ms=5, label=c)
        ax.fill_between(x, g.ci_lo, g.ci_hi, color=col, alpha=0.12, lw=0)
    ax.axhline(0, color=GRAY, lw=1)
    lags = sorted(lagdf.lag_minutes.unique())
    ax.set_xticks(range(len(lags)), [str(l) for l in lags])
    ax.set_xlabel("lag H (minutes): feature at t vs KPI change over (t, t+H]")
    ax.set_ylabel("partial Spearman ρ, Jun–Jul replication\n(95 % 3-day-block CI)")
    ax.set_title(title, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    return save(fig, name)


def fig_months(scores: pd.DataFrame, ids: list[str], name: str) -> str:
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    wins = ["disc", "jun", "jul", "repl", "holdout"]
    labels = ["Discovery\nApr–May", "Jun", "Jul", "Replication\nJun–Jul", "HOLDOUT\nAug (untouched)"]
    s = scores.set_index("indicator_id")
    w = 0.8 / max(len(ids), 1)
    for k, (c, col) in enumerate(zip(ids[:4], [S1, S2, S3, S4])):
        r = s.loc[c]
        v = np.array([r[f"{p}_rho_p"] for p in wins], float)
        lo = np.array([r[f"{p}_ci_lo"] for p in wins], float)
        hi = np.array([r[f"{p}_ci_hi"] for p in wins], float)
        x = np.arange(len(wins)) + (k - (len(ids) - 1) / 2) * w
        ax.errorbar(x, v, yerr=[v - lo, hi - v], fmt="o", color=col, ms=6, capsize=3, lw=1.5, label=c)
    ax.axhline(0, color=GRAY, lw=1)
    ax.axvspan(3.5, 4.5, color="#f1f0ec", zorder=0)
    ax.set_xticks(range(len(wins)), labels)
    ax.set_ylabel("partial Spearman ρ at the discovery lag\n(95 % 3-day-block CI)")
    ax.set_title("Temporal robustness: the discovery lag and sign in every window", color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    return save(fig, name)


def fig_episode(ep: pd.DataFrame, ids: list[str], name: str) -> str:
    fig, axes = plt.subplots(1, len(ids), figsize=(4.2 * len(ids), 3.4), squeeze=False)
    for ax, c in zip(axes[0], ids):
        g = ep[(ep.indicator_id == c) & ep.window.isin(list(REPLICATION_MONTHS))]
        for role, col, lab in (("EPISODE", S2, "before the start of KPI deterioration episodes"),
                               ("CONTROL", GRAY, "matched control times")):
            gg = g[g.role.eq(role) if role == "EPISODE" else g.role.str.startswith("CONTROL")]
            m = gg.groupby("rel_minutes").z_vs_discovery.median()
            ax.plot(m.index / 60, m.values, color=col, lw=2, label=lab)
        ax.axvline(0, color=GRAY, lw=1, ls=":")
        ax.set_title(c, color=INK, fontsize=9, loc="left")
        ax.set_xlabel("hours relative to the start of the rise (T)")
    axes[0][0].set_ylabel("median z vs discovery")
    axes[0][0].legend(frameon=False, fontsize=8)
    return save(fig, name)


def fig_false(scores: pd.DataFrame, ids: list[str], name: str) -> str:
    cats = ["n_true_lead_repl", "n_shutdown_related_repl", "n_load_transition_repl", "n_short_lived_repl",
            "n_directional_reversal_repl", "n_unexplained_repl"]
    lab = ["true lead", "shutdown-related (not evaluable)", "load transition", "short-lived", "reversal", "unexplained"]
    cols = [S1, GRAY, S2, S3, S4, "#c9c8c2"]
    s = scores.set_index("indicator_id").loc[ids]
    fig, ax = plt.subplots(figsize=(8.5, 0.9 + 0.5 * len(ids)))
    left = np.zeros(len(ids))
    for c, l, col in zip(cats, lab, cols):
        v = s[c].fillna(0).to_numpy(float)
        ax.barh(range(len(ids)), v, left=left, color=col, label=l, edgecolor="#fcfcfb", linewidth=2, height=0.6)
        left += v
    ax.set_yticks(range(len(ids)), ids, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("threshold-crossing onsets in Jun–Jul, by what followed within 12 h")
    ax.set_title("False-lead analysis (POC analytical thresholds; not plant alarms)", color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(axis="y", visible=False)
    return save(fig, name)


def version_manifest(cfg=PRIMARY) -> pd.DataFrame:
    hashes = json.loads((CACHE / "input_hashes.json").read_text())
    code = {p.name: sha256(p) for p in sorted((PHASE_DIR / "scripts").glob("*.py"))}
    code.update({f"tests/{p.name}": sha256(p) for p in sorted((PHASE_DIR / "tests").glob("*.py"))})
    man = [("method_version", METHOD_VERSION), ("config_key", cfg.key()),
           ("config", json.dumps(asdict(cfg), sort_keys=True, default=str)), ("indicator_label", INDICATOR_LABEL),
           ("episode_label", EPISODE_LABEL), ("threshold_label", THRESHOLD_LABEL), ("state_label", PROXY_LABEL),
           ("discovery_window", f"{cfg.disc_start} .. {cfg.disc_end}"),
           ("evaluation_windows", f"JUN {cfg.eval_jun}; JUL {cfg.eval_jul}; AUG {cfg.eval_aug} (KPI ends 2025-08-23)"),
           ("target", "dK(t,H) = median K over (t+H-30min, t+H] - K(t); Phase 3 kpi_in_sample_reference (Apr-May) / "
                      "efficiency_deterioration_kpi (Jun-Aug)"),
           ("feature_reference_sha256", sha256(OUT / "indicator_feature_reference.json")),
           ("validation_status", "statistical / historical validation only; no event ground truth"),
           ("python", platform.python_version()), ("pandas", pd.__version__), ("numpy", np.__version__),
           ("scipy", scipy.__version__), ("scikit-learn", sklearn.__version__)]
    man += [(f"input_sha256:{n}", h) for n, h in sorted(hashes.items())]
    man += [(f"code_sha256:{n}", h) for n, h in code.items()]
    return pd.DataFrame(man, columns=["item", "value"])




GLOSSARY = [
    ("Phase 3 KPI", "The 0–100 POC efficiency-deterioration score from Phase 3. 0 = typical April–May behaviour; 50 = the "
                    "training 95th percentile. It is a normalised score, not a plant limit."),
    ("Leading indicator (here)", "A process signal whose movement at time t tends to come before an increase of the KPI "
                                 "over the next minutes to hours. It is an empirical association, not a cause."),
    ("Lead time", "The horizon H that discovery (April–May) found strongest: the signal at t is compared with the KPI "
                  "change over the next H minutes."),
    ("Partial ρ (effect size)", "How strongly the signal's rank moves with the coming KPI change, AFTER removing what the "
                                "KPI's own current level, 1-h trend and already-known persistence (Kpend) predict. "
                                "0 = no extra information; ±0.05–0.15 = small but repeatable."),
    ("Kpend", "The part of the KPI's next 6-hour window that is already known at t. Removing it stops a KPI input from "
              "'leading' its own trailing median."),
    ("Discovery / replication / holdout", "April–May chooses the lag and direction; June–July decides the gates and "
                                          "the score; August is kept aside and shown once as a forward test."),
    ("Component precursor", "A KPI input (or near-copy of one) that moves before the KPI. It is useful for explanation, "
                            "but it is part of the KPI, so it is never a separate leading indicator."),
    ("Load proxy", "A signal whose lead disappears once feed level and feed changes are accounted for. It reflects load, "
                   "not process deterioration."),
    ("Circular-shift null", "The signal shifted by 2–59 days and re-tested. A real lead must beat the shifted copies, "
                            "which keep the same autocorrelation but no alignment."),
    ("False lead", "A threshold crossing not followed by a KPI rise within 12 h."),
    ("Precision lift", "Share of crossings followed by a rise, divided by the share of random running times followed "
                       "by a rise."),
    ("NOT_MET_REPORTED", "A robustness check that did not meet its pre-declared rule. It is shown, not hidden. It is "
                         "not a pipeline failure."),
]


def tb(x) -> bool:
    return str(x) == "True"


def main():
    cfg = PRIMARY
    write_csv(version_manifest(cfg), "indicator_version_manifest.csv", lg)
    inv = read_out("indicator_candidate_inventory.csv")
    lagdf = read_out("indicator_lag_analysis.csv")
    scores = read_out("indicator_scores.csv")
    lis = read_out("leading_indicator_set.csv")
    for d in (scores, lis):                      # labels are text, never NaN (e.g. empty flags / exclusion_reason)
        for c in ("flags", "exclusion_reason", "failed_gates", "selection_note"):
            if c in d:
                d[c] = d[c].fillna("")
    sens = read_out("indicator_sensitivity.csv")
    val = read_out("indicator_validation.csv")
    dq = read_out("indicator_data_quality.csv")
    eps = read_out("indicator_episodes.csv")
    bench = read_out("indicator_benchmarks.csv")
    ep_long = pd.read_parquet(OUT / "indicator_episode_analysis.parquet")
    sup = scores[scores.disc_supported].sort_values(["phase4_score", "indicator_id"], ascending=[False, True])
    members = lis[lis.selection_status.eq("SELECTED")].indicator_id.tolist()
    comp = sup[sup.eligibility.isin(["COMPONENT_PRECURSOR", "KPI_PROXY_PRECURSOR"])
               & sup.relationship_class.eq("LEADING")].indicator_id.tolist()
    n_tests = int(lagdf.window.eq("DISCOVERY").sum())
    n_q = int((lagdf.window.eq("DISCOVERY") & (lagdf.q_bh <= cfg.fdr_q)).sum())
    st = inv.status.value_counts().to_dict()
    tiers = inv[inv.status.ne("EXCLUDED")].tier.value_counts().to_dict()
    e_ep = eps[eps.role.eq("EPISODE")]
    vres = val.result.value_counts().to_dict()
    g7 = val[val.gate.str.startswith("G7")]
    s_m = scores.set_index("indicator_id")
    lis_m = lis.set_index("indicator_id")
    classes = sup.relationship_class.value_counts().to_dict()
    lp = sup[sup.relationship_class.eq("OPERATING_STATE_OR_LOAD_PROXY")]
    load_ctx = lp[lp.status.eq("CONTEXT_ONLY")]
    lp = lp[~lp.status.eq("CONTEXT_ONLY")]
    load_names = sorted({f"{r.dataset} {r.original_name}" for r in lp.itertuples()})
    unstable = sup[sup.relationship_class.eq("UNSTABLE_OR_SPURIOUS")].indicator_id.tolist()
    lagging = sup[sup.relationship_class.eq("LAGGING")].indicator_id.tolist()
    bm60 = bench[(bench.window == "REPL") & (bench.lag_minutes == 60)].set_index("benchmark").rho_raw_no_controls

    figs = {}
    lead_ids = (members + [c for c in comp if c not in members])[:4]
    figs["lag"] = fig_lag_profiles(lagdf, lead_ids, "Lag profiles: selected indicator and KPI-component precursors",
                                   "fig1_lag_profiles.png")
    others = [c for c in sup[sup.tier.eq("EXTERNAL")].indicator_id if c not in members][:3]
    figs["lag_ext"] = fig_lag_profiles(lagdf, (members + others)[:4], "Selected indicator vs other external signals "
                                       "(load-confounded / unstable)", "fig2_lag_profiles_external.png")
    figs["months"] = fig_months(scores, lead_ids, "fig3_temporal_robustness.png")
    ep_ids = [c for c in lead_ids if c in set(ep_long.indicator_id)][:3]
    figs["episode"] = fig_episode(ep_long, ep_ids, "fig4_episode_profiles.png") if ep_ids else ""
    figs["false"] = fig_false(scores, sup.indicator_id.tolist()[:12], "fig5_false_leads.png")

    def ind_line(c):
        r, l = s_m.loc[c], lis_m.loc[c] if c in lis_m.index else None
        name = l.display_name if l is not None else f"{r.dataset} {r.original_name} ({r.unit})"
        return (f"**{name}**, {FEATURE_DOC[r.feature_type][0].lower()} feature `{c}`: "
                f"{direction_words(r.feature_type, r.sign)} tends to come before a KPI increase within about "
                f"{int(r.lag_minutes)} min (discovery q = {r.disc_q_bh:.3f}). Effect beyond the KPI's own momentum: "
                f"partial ρ {r.repl_rho_p:.3f} [{r.repl_ci_lo:.3f}, {r.repl_ci_hi:.3f}] in June–July (June {r.jun_rho_p:.3f}, "
                f"July {r.jul_rho_p:.3f}; {int(r.repl_months_sig_same_sign)} of 2 months individually significant). "
                f"Circular-shift null p = {r.shift_null_p_repl:.3f}. **August holdout: {r.holdout_rho_p:.3f} "
                f"[{r.holdout_ci_lo:.3f}, {r.holdout_ci_hi:.3f}] — {r.holdout_result}.** About "
                f"{r.alarms_per_7_running_days_repl:.0f} threshold crossings per 7 running days; "
                f"{r.precision_repl:.0%} of them are followed by a KPI rise, against {r.base_rate_repl:.0%} of random "
                f"running times (lift {r.precision_lift_repl:.2f}; holdout {r.precision_lift_holdout:.2f}). Before the start "
                f"of KPI deterioration episodes it crosses its threshold {'less' if r.lift_repl < 0 else 'more'} often than "
                f"before matched control times ({r.hit_rate_episode_repl:.0%} vs {r.hit_rate_control_repl:.0%}, "
                f"{int(r.n_episodes_repl)} episodes). Confidence **{r.confidence}**; lead-time confidence "
                f"{r.lead_time_confidence}.")

    sel_cols = ["display_name", "feature_category", "lead_time_minutes", "relationship_direction", "effect_size",
                "effect_size_ci", "holdout_result", "confidence", "false_lead_rate", "precision_lift", "episode_lift",
                "phase4_score"]
    sel_tab = lis[lis.selection_status.eq("SELECTED")][sel_cols]
    sup_tab = sup[["indicator_id", "tier", "relationship_class", "eligibility", "failed_gates", "lag_minutes", "disc_q_bh",
                   "repl_rho_p", "repl_ci_lo", "repl_ci_hi", "jun_rho_p", "jul_rho_p", "shift_null_p_repl",
                   "rho_with_feed_controls", "holdout_rho_p", "holdout_result", "confidence", "phase4_score"]]
    cls = scores.groupby(["relationship_class"]).size().rename("indicators (all)").to_frame()
    cls["discovery-supported"] = sup.groupby("relationship_class").size()
    cls = cls.fillna(0).astype(int).reset_index()
    excl = inv[inv.status.eq("EXCLUDED")].exclusion_reason.str.extract(r"^(C\d)")[0].value_counts().sort_index()
    excl_tab = pd.DataFrame({"rule": excl.index, "rows excluded": excl.values})
    rule_text = {"C1": "Phase 2 column hold (unit review, sentinel, sparse, constant, state indicator, duplicate)",
                 "C2": "Phase 2 baseline confidence INSUFFICIENT", "C3": "duplicate of another dataset's tag (Phase 1 identical rate >= 0.99)",
                 "C4": "cumulative run-hour counter", "C5": "Phase 3 KPI output / derived construct, or reserved for Phase 5 (AFR)",
                 "C6": "undefined scale in discovery", "C7": "insufficient discovery coverage / days, or unusable flatline"}
    excl_tab["meaning"] = excl_tab.rule.map(rule_text)
    sens_sum = sens[sens.indicator_id.isin(sup.indicator_id)].groupby(["group", "variant"]).consistent.agg(["mean", "count"]).reset_index()
    sens_sum = sens_sum.rename(columns={"mean": "share consistent", "count": "indicators evaluated"})
    sens_set = sens[sens.indicator_id.isin(members)][["variant", "group", "indicator_id", "rho_reference", "rho_variant", "consistent"]]
    sens_rank = sens[sens.indicator_id.isin(["ALL_SUPPORTED", "SET"])][["variant", "rho_variant", "consistent", "note"]]
    dq_c = dq[dq.status.isin(["CANDIDATE", "CONTEXT_ONLY"])]
    fl_tab = sup[["indicator_id", "n_alarms_repl", "alarms_per_7_running_days_repl", "false_lead_rate_repl", "precision_repl",
                  "base_rate_repl", "precision_lift_repl", "precision_lift_holdout", "n_shutdown_related_repl",
                  "n_load_transition_repl", "n_short_lived_repl", "n_directional_reversal_repl", "n_unexplained_repl"]]
    ep_counts = e_ep.groupby(["window", "episode_type"]).size().rename("independent episodes").reset_index()
    ep_sum = []
    for c in lead_ids:
        g = ep_long[(ep_long.indicator_id == c) & ep_long.window.isin(list(REPLICATION_MONTHS))]
        row = {"indicator_id": c}
        for off, lab in ((-720, "T-12h"), (-360, "T-6h"), (-180, "T-3h"), (-120, "T-2h"), (-60, "T-1h"), (-30, "T-30m"), (0, "T")):
            e = g[(g.rel_minutes == off) & g.role.eq("EPISODE")].z_vs_discovery.median()
            k = g[(g.rel_minutes == off) & g.role.str.startswith("CONTROL")].z_vs_discovery.median()
            row[lab] = f"{e:.2f} / {k:.2f}"
        ep_sum.append(row)
    ep_sum = pd.DataFrame(ep_sum)
    bm = bench.pivot_table(index="lag_minutes", columns=["benchmark", "window"], values="rho_raw_no_controls").reset_index()
    bm.columns = [" ".join(str(x) for x in c if x).strip() for c in bm.columns]
    val_tab = val[["gate", "check", "check_type", "result"]]
    val_counts = val.groupby(["gate", "result"]).size().unstack(fill_value=0).reset_index()

    L = []
    A = L.append
    A("# Phase 4 — Leading Indicators of the Phase 3 POC Efficiency-Deterioration KPI\n")
    A(f"Method version `{METHOD_VERSION}` · config `{cfg.key()}` · generated from `phase-04-leading-indicators/outputs/`\n")
    A("> **These are empirical leading indicators of the Phase 3 efficiency-deterioration KPI. They are not validated "
      "predictors of deposits, rings, coating, equipment failure, or other plant events.**\n>\n"
      f"> Other caveats: operating state is a {PROXY_LABEL}; the folders are assumed to be one kiln line (unconfirmed); "
      "Sp.Heat F / G is unresolved; there is no event ground truth. **For discussion and review only; no operating "
      "action, alarm or limit is implied.**\n")
    A("## 1. Executive summary\n")
    A(f"- **Question.** Which process signals move before the Phase 3 KPI deteriorates, beyond what the KPI's own level "
      f"and trend already say?\n"
      f"- **Scope and design.**\n"
      f"  - Candidates: {st.get('CANDIDATE', 0)} candidate tags plus {st.get('CONTEXT_ONLY', 0)} load-context tags, 7 "
      f"causal features each, and 10 lags from 10 min to 12 h. That is {n_tests:,} tests.\n"
      f"  - Discovery (April–May) picks each indicator's lag and direction. June–July must replicate them. **August was "
      f"kept aside** and is reported once as a forward test.\n"
      f"- **Discovery screen.** {n_q} tests pass the false-discovery screen (q ≤ {cfg.fdr_q}, with autocorrelation-honest "
      f"inference). They come from {len(sup)} indicators.\n"
      f"- **Practical finding: very few process signals lead this KPI, and only weakly.**\n"
      f"  - **{len(members)} external indicator{'s' if len(members) != 1 else ''} passes every gate:**\n"
      + "".join(f"    - {ind_line(c)}\n" for c in members)
      + ("    - This is a **weak, tentative** lead. The selected tag is flagged as an operator- or controller-set "
         "variable, so the most plausible reading is an operator response to process conditions that the KPI registers "
         "later. It should not be read as a cause, or as something to act on.\n"
         if any(tb(s_m.manipulated_variable.get(m)) for m in members) else
         "    - Treat it as a **tentative** empirical lead, not as a cause or as something to act on.\n") +
      f"  - **{len(comp)} KPI-component precursors** replicate: {', '.join(comp) or 'none'}. These are parts of the KPI "
      f"itself (for example the burning-zone temperature trend), so they explain which part of the KPI moves first. They "
      f"are never independent indicators.\n"
      f"  - **{classes.get('OPERATING_STATE_OR_LOAD_PROXY', 0)} discovery-supported signals are load proxies.** "
      f"{len(load_ctx)} {'is' if len(load_ctx) == 1 else 'are'} the load context itself "
      f"({', '.join(load_ctx.indicator_id) or 'none'}). The other {len(lp)} ({', '.join(load_names)}) lose the lead once "
      f"feed level and feed changes are controlled.\n"
      f"  - **{len(unstable)} are unstable** (they do not replicate or do not beat the shift null), including the kiln "
      f"drive power and current trends. **{len(lagging)} lags** the KPI.\n"
      f"- **The KPI's own recent movement is far more informative.**\n"
      f"  - At a 60-min horizon, KPI momentum alone has raw ρ "
      f"{bm60.get('BENCHMARK:KPI_MOMENTUM_1H', np.nan):.2f} with the coming change.\n"
      f"  - The selected indicator adds only a small partial ρ on top of that.\n"
      f"  - Threshold crossings are mostly false leads.\n"
      f"  - Nothing here is an early-warning signal.\n"
      f"- **Validation.**\n"
      f"  - Results: {vres.get('PASS', 0)} checks PASS, {vres.get('FAIL', 0)} FAIL, "
      f"{vres.get('NOT_MET_REPORTED', 0)} robustness rules NOT_MET_REPORTED (shown in section 17), and "
      f"{vres.get('INFO', 0)} INFO.\n"
      f"  - The leakage test is exact at 9 cut points.\n"
      f"  - Reproducibility: see section 22.\n")
    A("### Glossary for plant users\n")
    A(md_table(pd.DataFrame(GLOSSARY, columns=["term", "meaning"]), max_col=400))
    A("\n**How the labels relate:**\n\n"
      "- *relationship class* says what the association looks like (leading, lagging, unstable, load proxy, …).\n"
      "- *eligibility* says whether the indicator may be selected at all (KPI inputs and load context never are).\n"
      "- *confidence* grades the evidence of eligible indicators (HIGH / MEDIUM / LOW; INSUFFICIENT = fails a gate; "
      "NOT_APPLICABLE = load context).\n"
      "- *selection status* says whether it is in the small complementary set.\n")
    A("## 2. Objective\n")
    A("Identify temporally leading, interpretable and statistically defensible process signals whose movement precedes "
      "increases in the Phase 3 KPI. They must be separated from contemporaneous, lagging, unstable, load/state-proxy and "
      "data-quality-limited associations. Phase 4 builds no dashboard, API, risk score or early-warning system.\n")
    A("## 3. Phase 3 KPI dependency\n")
    A("The target is the Phase 3 output itself, read from `efficiency_deterioration_kpi.parquet`. The scorer is not "
      "bypassed.\n\n"
      "- **Which KPI column is used:** the in-sample reference column inside the training window (discovery only), and "
      "the reported out-of-sample column from 1 June.\n"
      "- **Input contract:** all 55 Phase 3 validation checks must PASS, and every Phase 3 input is hashed.\n"
      "- **Masks, state and bucketing** are re-derived with Phase 3's `kpi_core`, imported read-only with no bytecode "
      "written. The rebuilt bucket state equals Phase 3's in every bucket.\n"
      "- **Controls:** the KPI, its 1-h momentum, and Kpend, built from Phase 3's `raw_deviation_score` and `to_kpi`.\n")
    A("## 4. Data used\n")
    A(f"- **Minute data.** `data/processed/<dataset>.parquet` for all 10 datasets, read-only through Phase 3's "
      f"`load_dataset`. Phase 2 causal cell tokens (missing, text, sentinel, physically impossible, duplicate conflict, "
      f"hourly) become NaN.\n"
      f"- **Minute index.** The Phase 3 minute index. Minutes outside it have no operating state and are never RUNNING.\n"
      f"- **Windows.**\n"
      f"  - Discovery: {cfg.disc_start} → {cfg.disc_end}.\n"
      f"  - Replication: {cfg.eval_jun[0]} → {cfg.eval_jul[1]}. The first 6 h of June overlap training.\n"
      f"  - Holdout: August, up to the KPI's last scored bucket, 2025-08-23. Kiln-I has no September data, so none is "
      f"used.\n"
      f"- **Episodes.** {len(e_ep)} independent KPI deterioration episodes ({EPISODE_LABEL}).\n")
    A("## 5. Candidate inventory\n")
    A(f"- **Inventory:** all {len(inv)} rows (every source tag and every Phase 3 output column) are in "
      f"`outputs/indicator_candidate_inventory.csv`. Status: {st}.\n"
      f"- **Tiers** of analysable tags: {tiers}.\n"
      "  - KPI_INPUT: the source tags feeding the Phase 3 KPI.\n"
      "  - KPI_PROXY: discovery |ρ| ≥ 0.8 with a KPI input.\n"
      "  - EXTERNAL: all others.\n"
      "- **Flags:** manipulated variables, May-only discovery (Kiln-IIIA), CBS-II hourly June data, load tracking, Phase 2 "
      "LOW confidence, and months that are not evaluable.\n")
    fam = inv[inv.status.ne("EXCLUDED")].groupby(["process_family", "tier"]).size().unstack(fill_value=0).reset_index()
    A(md_table(fam))
    A("## 6. Exclusion rules\n")
    A("- **Order:** the rules are applied in order, and the first failing rule gives the reason.\n"
      "- **Windows:** C2–C7 are judged on the **discovery window only**. C1 uses Phase 2's fixed label/unit/semantic "
      "holds.\n"
      "- **No transformation:** no unit is converted and no tag is renamed.\n")
    A(md_table(excl_tab))
    A("\nC8 (context confounders): kiln feed, clinker TPH and bucket-elevator current are analysed but never eligible. "
      "The AFR solid rate is reserved for Phase 5.\n")
    A("## 7. Feature engineering\n")
    A("- **Causal windows only.** Every feature at bucket t uses only buckets ≤ t, through right-closed trailing windows "
      "on a regular 10-min grid. There are no centred windows, no interpolation and no imputation.\n"
      "- **Frozen references.** References are fitted once, on the Phase 3 training population, and frozen.\n")
    A(md_table(pd.DataFrame([(k, v[0], v[1]) for k, v in FEATURE_DOC.items()], columns=["feature", "type", "definition"])))
    A("\n- **No cross-signal ratios:** CO/O₂ and feed/speed would divide quantities whose units and semantics are "
      "unconfirmed, and CO is a LOW-confidence tag.\n"
      "- **No oscillation features:** the 10-min grid cannot resolve control-loop oscillation.\n")
    A("## 8. Lag methodology\n")
    A("- **Target (T1):** ΔK(t, H) = median KPI over (t+H−30 min, t+H] − K(t), for horizons H from 10 min to 12 h. It "
      "is defined only while the kiln stays RUNNING over the whole horizon, so the results apply to RUNNING horizons "
      "only. The target is the only forward-looking quantity and is never a feature.\n"
      "- **Other targets:** the sign of ΔK (target A) is covered by the directional statistics. Future band occupancy "
      "(target B) is a sensitivity variant.\n"
      "- **Why a change target:** a level target would be dominated by the KPI's own 6-h persistence.\n"
      "- **Statistic:** partial Spearman ρ controlling for K(t), 1-h momentum and Kpend.\n"
      "- **Other associations reported:** backward (feature vs the past change) and contemporaneous (feature vs K(t)).\n")
    A("## 9. Lead-time methodology\n")
    A("- **The lead time** is the lag chosen on discovery only (smallest BH q), and the sign of that discovery ρ is the "
      "pre-declared direction.\n"
      "- **Post-hoc descriptives, computed on June–July and labelled as such:**\n"
      "  - The best replication lag.\n"
      "  - The *stable range*: lags with at least half the best ρ and a CI excluding 0.\n"
      "  - The monthly best lags.\n"
      "  - The episode lead: a new threshold crossing within 12 h before the *start* of an episode. It is suppressed when "
      "crossings are not more frequent before episodes than before matched controls.\n"
      "- **Lead-time confidence:**\n"
      "  - HIGH: the stable range is contiguous, contains the discovery lag, and both replication months' best lags fall "
      "inside it.\n"
      "  - MEDIUM: the range contains the discovery lag.\n"
      "  - LOW: otherwise.\n"
      "  - It is always capped at the indicator's overall confidence. Lead-time fields are empty unless the relationship "
      "is LEADING.\n")
    A("## 10. Operating-state treatment\n")
    A(f"- **Population:** RUNNING buckets only, from the causal Phase 3 state ({PROXY_LABEL}).\n"
      "- **STOPPED and TRANSITION:** no KPI is scored in these states, so a separate correlation analysis is not possible. "
      "A horizon containing a stop or transition is dropped.\n"
      "- **Sensitivity:** exclude the 6 h after a transition, and the 2 h before a stop (the second is an analysis filter "
      "only).\n"
      "- **False leads:** alarms next to stops or restarts are SHUTDOWN_RELATED excursions (section 15).\n")
    A("## 11. Load treatment\n")
    A("- **Primary:** the Phase 2 feed bands are TENTATIVE, so the primary does not condition on them. DEV_1H uses a "
      "feed-conditional reference.\n"
      "- **Load robustness is a gate.** Adding feed level and 1-h/3-h feed changes as controls must keep the sign and "
      "≥ 50 % of |ρ|.\n"
      "- **GMM feed bands** are a sensitivity check only.\n"
      "- **Decision:** feed-change control is kept as a gate because it is what separates load proxies from process "
      "signals.\n")
    A("## 12. Statistical methodology\n")
    ar = val[val.check.str.contains("AR\\(1\\)")].evidence
    nc = val[val.check.str.contains("Null calibration")].evidence
    A(f"- **Autocorrelation:** effective sample size (Bartlett / Pyper–Peterman, residual ACFs up to 3 days), Fisher z "
      f"with n_eff, and a **3-day-block** bootstrap CI ({cfg.n_boot} resamples; 1-day blocks in sensitivity).\n"
      f"- **Multiple testing:** Benjamini–Hochberg over all {n_tests:,} discovery tests, plus a CI excluding 0.\n"
      f"- **Replication:** June–July at the same lag and sign, plus a circular-shift null (58 shifts).\n"
      f"- **Calibration evidence:**\n"
      f"  - AR(1) nulls: {ar.iloc[0] if len(ar) else ''}.\n"
      f"  - All features shifted by 14 days: {nc.iloc[0] if len(nc) else ''}.\n"
      f"- **Winner's curse:** June–July ρ are selection-set estimates and are biased upward. Only the August holdout is "
      f"untouched.\n"
      f"- **No p-value is read as causation.**\n")
    A(f"![Lag profiles]({figs['lag']})\n")
    A("## 13. Leading indicator results\n")
    A("### Selected set (`leading_indicator_set.csv`, selection_status = SELECTED)\n")
    A(md_table(sel_tab, max_col=60) if len(sel_tab) else "_No indicator passed every gate; that is a valid outcome._\n")
    A("\n" + "".join(f"- {ind_line(c)}\n" for c in members))
    A("\nEvery statement about a selected indicator is an observation about the POC KPI only. No physical mechanism is "
      "inferred from category membership or from the sign of an association.\n")
    A("### All discovery-supported indicators\n")
    A(md_table(sup_tab, max_col=70))
    A("\n**Relationship classes:**\n")
    A(md_table(cls))
    A(f"\n![External signals]({figs['lag_ext']})\n")
    A("### Multivariate complementary set\n")
    A("- **Candidates:** eligible indicators, ranked by score.\n"
      "- **Redundancy:** one feature per tag, and discovery |ρ| < 0.7 with every member.\n"
      "- **Increment:** an incremental partial ρ on discovery, given the controls and earlier members, with a CI "
      "excluding 0.\n"
      "- **No black-box model** is used.\n\n"
      "With the present evidence the set is as large as the number of eligible external indicators.\n")
    A(md_table(scores[scores.selection_status.eq("SELECTED")][["indicator_id", "selection_note", "incremental_repl_rho_p",
                                                                "incremental_repl_ci", "incremental_holdout_rho_p",
                                                                "incremental_holdout_ci"]]))
    A("## 14. Indicator confidence\n")
    A("Confidence measures the quality of the evidence from discovery and replication. It does not measure importance. "
      "The holdout is reported beside it, never inside it.\n\n"
      "- **HIGH:**\n"
      "  - EXTERNAL tier, q ≤ 0.05.\n"
      "  - Both replication months individually significant.\n"
      "  - Consistent under Sp.Heat F/G and the state filters.\n"
      "  - Beats every circular shift.\n"
      "  - Positive episode lift with ≥ 8 episodes.\n"
      "- **MEDIUM:** ≥ 1 replication month individually significant, and shift-null p < 0.05.\n"
      "- **LOW:** otherwise.\n\n"
      "**Caps:**\n\n"
      "- KPI inputs and proxies: at most LOW.\n"
      "- Manipulated, May-only and Phase 2 LOW-confidence tags: at most MEDIUM.\n"
      "- Any failed gate: INSUFFICIENT.\n"
      "- Load context: NOT_APPLICABLE.\n")
    A(md_table(scores[scores.disc_supported].groupby(["eligibility", "confidence"]).size().rename("indicators").reset_index()))
    A(f"\n![Temporal robustness]({figs['months']})\n")
    A("## 15. False-lead analysis\n")
    A(f"- **Alarm:** at least 30 min beyond the directional discovery P90/P10 threshold, after ≥ 2 h clear. Alarms are "
      f"causal ({THRESHOLD_LABEL}).\n"
      f"- **Evaluable:** the next 12 h are RUNNING with ≥ 2/3 KPI coverage.\n"
      f"- **True lead:** the KPI rises by ≥ δ within 12 h, where δ is the discovery P75 of the 12-h maximum rise.\n"
      f"- **False-lead classes:** load transition, short-lived, directional reversal, unexplained.\n"
      f"- **Shutdown-related:** alarms with a stop or transition in the 6 h before or 12 h after. They are reported but "
      f"not evaluable.\n"
      f"- **Base rate:** computed with exactly the same evaluability rule.\n")
    A(md_table(fl_tab))
    A(f"\n![False leads]({figs['false']})\n")
    A(f"\n**Reading.** Replication false-lead rates range from {sup.false_lead_rate_repl.min():.2f} to "
      f"{sup.false_lead_rate_repl.max():.2f}, against a base rate of rises of about {sup.base_rate_repl.median():.2f}. "
      f"Even the replicated indicators only modestly raise the chance of a subsequent KPI rise. They indicate process "
      f"deviation; they are not alarms.\n")
    A("## 16. Temporal robustness\n")
    A("The design is **fixed-origin monthly replication** with an untouched holdout, not a rolling-origin refit:\n\n"
      "- Discovery chooses each indicator's lag and sign.\n"
      "- June and July must reproduce them, separately and pooled.\n"
      "- August is never used for gating, scoring or selection.\n\n"
      "G3 verifies that overwriting every evaluation statistic leaves the lag, sign and support unchanged. The monthly "
      "best lags are in `indicator_lead_time.csv`.\n")
    A("## 17. Sensitivity analysis\n")
    A("Groups A–H cover:\n\n"
      "- **A:** neighbouring lags.\n"
      "- **B:** split-half discovery, an April-only feature reference, and Phase 3's later-anchored KPI reference (16–31 "
      "July only, to keep August untouched).\n"
      "- **C:** state filters.\n"
      "- **D:** feed controls and GMM bands.\n"
      "- **E:** Sp.Heat F-only and G-only targets, including whether the best lag changes.\n"
      "- **F:** 60-min target smoothing and the band-occupancy target.\n"
      "- **G:** Phase 3 GOOD-quality buckets only.\n"
      "- **H:** 1-day blocks and no controls.\n\n"
      f"All variants run on June–July. A variant is consistent when it keeps the discovery sign and "
      f"≥ {MATERIALITY['rho_ratio_min']:.0%} of |ρ|.\n\n"
      "**Share of discovery-supported indicators consistent, per variant:**\n")
    A(md_table(sens_sum))
    A("\n**Set members, every variant:**\n")
    A(md_table(sens_set))
    A("\n**Ranking and set stability:**\n")
    A(md_table(sens_rank, max_col=200))
    A("\n**Sp.Heat F / G.**\n\n"
      "- The ranking of supported indicators differs between the F-only and G-only KPI targets. The Spearman of |ρ| is "
      "below the pre-declared 0.8, mostly because Sp.Heat-derived features follow their own definition.\n"
      "- The set member's rows above show whether its sign and strength hold under both.\n"
      "- Neither definition is declared authoritative; the plant must confirm which is.\n")
    A("## 18. Limitations\n")
    A("- **No event ground truth.** Episodes are synthetic windows built from the KPI. Nothing here predicts deposits, "
      "rings, coating or failures.\n"
      "- **Inherited Phase 3 caveats:**\n"
      "  - The KPI is mostly process-deviation-led.\n"
      "  - The discovery (in-sample) KPI is compressed, with half its values at 0.\n"
      "  - Part of June's level is fit optimism.\n"
      f"- **Small effects and few episodes.** Effects are small, and there are only "
      f"{int(e_ep.window.isin(list(REPLICATION_MONTHS)).sum())} independent replication episodes and "
      f"{int(e_ep.window.eq(HOLDOUT).sum())} holdout episodes. The June–July estimates carry winner's-curse bias.\n"
      "- **Manipulated variables.** Leads of operator- or controller-set tags (flagged) most plausibly reflect operator "
      "response.\n"
      "- **Scope of the results.** They apply only to horizons during which the kiln stays RUNNING. They are not "
      "deployable as they stand.\n"
      "- **Correlation is not causation.**\n")
    A("## 19. Data-quality limitations\n")
    A(f"- **Coverage gaps:** Kiln-IIIA has no April (its tags are discovered on May only), CBS-II is hourly on 1–10 June, "
      f"and Kiln-I has no September.\n"
      f"- **Frozen rows:** the 2025-05-06 frozen window is masked only once a run has lasted 10 min (causal).\n"
      f"- **Masking:** per-tag masking and coverage are in `indicator_data_quality.csv` ({len(dq_c)} analysable tags; "
      f"median masked share {dq_c.pct_flatline_or_frozen_masked.median():.1f} %).\n"
      f"- **Negative flows:** negative bypass-gas-flow buckets are reported, not altered.\n")
    A("## 20. Plant questions remaining\n")
    A("1. Are the Kiln-I / IA / II / III / IIIA / IIIB folders one kiln line?\n"
      "2. What does `Kiln MD` mean?\n"
      "3. Which Sp.Heat definition, F or G, is authoritative?\n"
      "4. Is PC coal firing (Kiln-I!I) adjusted manually or by a controller? What do operators respond to when they raise "
      "it?\n"
      "5. What changes kiln drive power at constant feed (speed changes, material load)?\n"
      "6. Can event logs be supplied (coating/ring observations, cleaning, stoppage reasons)?\n"
      "7. Can the plant re-export Kiln-I September and Kiln-IIIA April?\n"
      "8. What do negative bypass-gas-flow values mean?\n"
      "9. Which tags are operator set-points and which are measured values?\n")
    A("## 21. Validation results\n")
    A("**Check types:**\n\n"
      "- **INDEPENDENT:** can fail on a real defect.\n"
      "- **REGRESSION_GUARD:** re-checks a construction rule.\n"
      "- **INFO:** a reported quantity.\n")
    A(md_table(val_counts))
    A("\n" + md_table(val_tab, max_col=190))
    A("\n**KPI deterioration episodes (independent, ≥ 12 h apart, anchored at the start of the rise):**\n")
    A(md_table(ep_counts))
    A("\n**Median z, episode vs matched controls, T−12 h … T** (June–July; value = episode / control):\n")
    A(md_table(ep_sum))
    if figs["episode"]:
        A(f"\n![Episode profiles]({figs['episode']})\n")
    A("\n**KPI self-benchmarks** (raw Spearman of the KPI's own recent behaviour with the future change; never "
      "candidates):\n")
    A(md_table(bm))
    A("## 22. Reproducibility results\n")
    A("Run `../../.venv/bin/python run_phase4.py --clean` from `phase-04-leading-indicators/scripts`, twice.\n\n"
      "- **G7 check:** the second run compares every key output with the first by SHA-256 (the code-hash rows of the "
      "manifest are excluded). It fails if any file differs or is not compared.\n"
      "- **Determinism mechanisms:**\n"
      "  - Seeded draws.\n"
      "  - Stable sorts.\n"
      "  - Unrounded internal hand-offs, with CSV floats rounded to 6 dp.\n"
      "  - No figure metadata.\n"
      "  - Single-threaded BLAS in the workers.\n"
      "  - Ordered result assembly.\n\n")
    A(md_table(g7[["check", "result", "evidence"]], max_col=190) if len(g7) else "_G7 rows are appended by run_phase4.py._\n")
    A("## 23. Phase 5 handoff\n")
    A("**Phase 5 (Alternative Fuel Analysis) may consume:**\n\n"
      "- `outputs/leading_indicator_set.csv`, which carries `usable_downstream` and `permitted_use`.\n"
      "- `indicator_feature_values.parquet`: causal features, known at t.\n"
      "- `indicator_feature_reference.json`: frozen discovery references.\n"
      "- `indicator_scores.csv`: gates, criteria and classes.\n"
      "- `indicator_lag_analysis.csv`: all tests.\n"
      "- `indicator_episodes.csv` and `indicator_episode_analysis.parquet`.\n"
      "- `indicator_data_quality.csv`.\n\n"
      "**Rules for Phase 5:**\n\n"
      "- Use the load-proxy classes to avoid attributing load effects to fuel.\n"
      "- Fuel firing tags (coal kiln / PC) are set-points. In Phase 5 they are candidate *explanatory* variables, not "
      "outcomes.\n"
      "- AFR (`Kiln-I!K`) was reserved and not analysed here; the ALTERNATIVE FUEL family stays INSUFFICIENT.\n\n"
      "**Rules for later consumers (Phases 7 and 8):**\n\n"
      "- Use only rows with `usable_downstream = True`.\n"
      "- Treat every row as an empirical correlate of the POC KPI, with its label.\n"
      "- Do not treat episode windows as events, or thresholds as limits.\n"
      "- Re-validate on new data before any use.\n\n"
      "Phase 5 has **not** been started.\n")
    md = "\n".join(L)
    (REPORTS / "PHASE_4_LEADING_INDICATORS.md").write_text(md)
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark").enable("table").render(md)
    css = ("body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#0b0b0b;"
           "background:#fcfcfb;line-height:1.45}table{border-collapse:collapse;font-size:12px;margin:8px 0;display:block;"
           "overflow-x:auto}td,th{border:1px solid #e0dfda;padding:3px 6px;vertical-align:top}th{background:#f1f0ec}"
           "img{max-width:100%}blockquote{border-left:4px solid #eb6834;margin:12px 0;padding:4px 12px;background:#fdf3ee}"
           "code{background:#f1f0ec;padding:0 3px}@media (prefers-color-scheme: dark){body{background:#1a1a19;color:#fff}"
           "th{background:#2a2a28}td,th{border-color:#3a3a37}blockquote{background:#2a211c}code{background:#2a2a28}}")
    html = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
            f"initial-scale=1'><title>Phase 4 Leading Indicators</title><style>{css}</style></head><body>{body}</body></html>")
    (REPORTS / "PHASE_4_LEADING_INDICATORS.html").write_text(html)
    lg.info("report written (%d chars, %d figures)", len(md), sum(bool(v) for v in figs.values()))


def direction_words(feat: str, sign: int) -> str:
    if feat.startswith("ROC"):
        return "a **rising** trend" if sign > 0 else "a **falling** trend"
    if feat == "VOL_2H":
        return "**higher** variability" if sign > 0 else "**lower** variability"
    if feat.startswith("PERSIST"):
        return "**more** time outside its band" if sign > 0 else "**less** time outside its band"
    return "a **higher** level" if sign > 0 else "a **lower** level"


if __name__ == "__main__":
    main()
