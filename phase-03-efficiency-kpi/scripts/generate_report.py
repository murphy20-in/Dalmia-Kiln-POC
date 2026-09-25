"""Step 9 - Phase 3 report (MD + HTML), 8 figures and the KPI definition, generated only from Phase 3 outputs.

Writes reports/PHASE_3_EFFICIENCY_DETERIORATION_KPI.md / .html, reports/figures/*.png,
       outputs/kpi_definition.json (machine-readable KPI definition / interpretation rules)
The review log (reviews/REVIEW_LOG.md) is appended when present.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import matplotlib
import numpy as np
import pandas as pd

from p3common import (BAND_LABEL, CACHE, COMMON_SCORING, COMPOSITE_LABEL, EQUIPMENT_VIEW, FIG, KPI_NAME, KPI_VERSION,
                      MATERIALITY, OUT, PHASE_DIR, PRIMARY, PROXY_LABEL, REPORTS, SCALE_LABEL, TRAINING_WINDOWS, log,
                      read_out, read_p2)
from kpi_core import to_kpi

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

lg = log("generate_report")
C = {"kpi": "#1f5fa8", "ins": "#9aa3ad", "lo": "#d98c1f", "hi": "#b8322a", "f": "#2b8a3e", "g": "#7048a8"}
DIM_COLORS = {"EFFICIENCY": "#1f5fa8", "COMBUSTION": "#d98c1f", "THERMAL": "#b8322a", "DRAFT_PRESSURE": "#2b8a3e",
              "STABILITY": "#7048a8"}


def md_table(df: pd.DataFrame, max_rows: int | None = None, max_col: int = 70, floatfmt: str = "{:.3g}") -> str:
    if df is None or df.empty:
        return "_None._\n"
    d = df.head(max_rows) if max_rows else df

    def cell(v):
        if isinstance(v, (float, np.floating)):
            s = "" if np.isnan(v) else (str(int(v)) if float(v).is_integer() and abs(v) < 1e12 else floatfmt.format(v))
        else:
            s = "" if v is None else str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return s if len(s) <= max_col else s[: max_col - 1] + "…"
    out = "| " + " | ".join(map(str, d.columns)) + " |\n| " + " | ".join("---" for _ in d.columns) + " |\n"
    out += "".join("| " + " | ".join(cell(v) for v in r) + " |\n" for r in d.itertuples(index=False))
    if max_rows and len(df) > max_rows:
        out += f"\n_{len(df) - max_rows} more rows in the CSV._\n"
    return out


def save(fig, name: str) -> str:
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(FIG / name, dpi=100, metadata={"Software": None})
    plt.close(fig)
    return f"figures/{name}"


def shade_states(ax, k: pd.DataFrame):
    ns = k.operating_state.ne("RUNNING")
    grp = (ns != ns.shift()).cumsum()
    for _, g in k[ns].groupby(grp[ns]):
        ax.axvspan(g.index[0], g.index[-1], color="#cfd4da", alpha=0.5, lw=0)


def figures(k: pd.DataFrame, series: pd.DataFrame, k_lo: float, k_hi: float, comp: pd.DataFrame) -> dict:
    f = {}
    te = pd.Timestamp(PRIMARY.train_end)
    # 1 KPI time series
    fig, ax = plt.subplots(figsize=(13, 4))
    shade_states(ax, k)
    ax.plot(k.index, k.kpi_in_sample_reference, color=C["ins"], lw=0.6, label="in-sample (training window; reference only)")
    for cls, col in [("SPECIFIC_HEAT_LED", C["kpi"]), ("MIXED", "#6c757d"), ("PROCESS_DEVIATION_LED", C["lo"]), ("NO_DEVIATION", "#2b8a3e")]:
        m_ = k.kpi_driver_class.eq(cls)
        ax.scatter(k.index[m_], k.efficiency_deterioration_kpi[m_], s=1.5, color=col, label=f"KPI, {cls}")
    ax.plot(k.efficiency_deterioration_kpi.resample("1D").median(), color="k", lw=1.5, label="daily median (scored buckets)")
    ax.axvline(te, color="k", ls=":", lw=1)
    ax.set_ylim(0, 100); ax.set_ylabel("POC KPI (0–100)")
    ax.set_title("Figure 1 — POC Kiln Efficiency Deterioration KPI by driver class (grey spans: not running / not scored)")
    ax.legend(loc="upper left", fontsize=7, ncol=3, markerscale=4)
    f[1] = save(fig, "fig1_kpi_timeseries.png")
    # 2 KPI with reference bands
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.axhspan(0, k_lo, color="#e8f1fb"); ax.axhspan(k_lo, k_hi, color="#fdf1dc"); ax.axhspan(k_hi, 100, color="#f8e0de")
    ax.plot(k.index, k.kpi_in_sample_reference, color=C["ins"], lw=0.6)
    ax.plot(k.index, k.efficiency_deterioration_kpi, color=C["kpi"], lw=0.6)
    ax.axhline(50, color="k", lw=0.6, ls="--")
    for y, t in [(k_lo / 2, "WITHIN_REFERENCE_VARIATION (< training P90)"), ((k_lo + k_hi) / 2, "ELEVATED_POC_ANALYTICAL (training P90–P99)"),
                 ((k_hi + 100) / 2, "BEYOND_REFERENCE_P99 (≥ training P99)")]:
        ax.text(k.index[0], y, "  " + t, va="center", fontsize=8)
    ax.axvline(te, color="k", ls=":", lw=1)
    ax.set_ylim(0, 100); ax.set_ylabel("POC KPI")
    ax.set_title("Figure 2 — KPI with POC analytical reference bands (NOT plant alarm limits; dashed = training P95 → 50)")
    f[2] = save(fig, "fig2_kpi_reference_bands.png")
    # 3 component contributions (daily mean of weighted contributions to D)
    dims = ["efficiency", "combustion", "thermal", "draft_pressure", "stability"]
    S = k[[f"{d}_component" for d in dims]].where(k.raw_deviation_score.notna())
    sup = S.iloc[:, 1:]
    n = sup.notna().sum(axis=1).replace(0, np.nan)
    contrib = pd.DataFrame({"EFFICIENCY": PRIMARY.w_efficiency * S.iloc[:, 0]})
    for d in dims[1:]:
        contrib[d.upper()] = (1 - PRIMARY.w_efficiency) * S[f"{d}_component"] / n
    daily = contrib.resample("1D").median()
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.stackplot(daily.index, *[daily[c].fillna(0) for c in daily.columns], labels=daily.columns,
                 colors=[DIM_COLORS[c] for c in daily.columns], alpha=0.85)
    ax.plot(k.raw_deviation_score.resample("1D").median(), color="k", lw=1, label="raw deviation D (daily median)")
    ax.axvline(te, color="k", ls=":", lw=1)
    ax.set_ylabel("contribution to D (standardised units)")
    ax.set_title("Figure 3 — Component contributions to the raw deviation D (daily medians; efficiency weight 0.5, supporting 0.5 shared)")
    ax.legend(loc="upper left", fontsize=8, ncol=6)
    f[3] = save(fig, "fig3_component_contributions.png")
    # 4 distribution
    fig, ax = plt.subplots(1, 2, figsize=(13, 3.8))
    bins = np.linspace(0, 100, 51)
    ax[0].hist(k.kpi_in_sample_reference.dropna(), bins=bins, color=C["ins"], alpha=0.8, density=True, label="in-sample (training)")
    ax[0].hist(k.efficiency_deterioration_kpi.dropna(), bins=bins, color=C["kpi"], alpha=0.6, density=True, label="out of sample")
    for x in (k_lo, k_hi):
        ax[0].axvline(x, color="k", ls=":", lw=1)
    ax[0].set_xlabel("POC KPI"); ax[0].legend(fontsize=8); ax[0].set_title("KPI distribution")
    ax[1].hist(k.persistent_deviation_score.where(k.kpi_in_sample_reference.notna()).dropna(), bins=60, color=C["ins"], alpha=0.8,
               density=True, label="in-sample P")
    ax[1].hist(k.persistent_deviation_score.where(k.efficiency_deterioration_kpi.notna()).dropna(), bins=60, color=C["kpi"],
               alpha=0.6, density=True, label="out-of-sample P")
    ax[1].set_xlabel("persistent deviation score P"); ax[1].legend(fontsize=8); ax[1].set_title("Persistent score distribution")
    fig.suptitle("Figure 4 — KPI and persistent-score distributions")
    f[4] = save(fig, "fig4_kpi_distribution.png")
    # 5 training-window sensitivity
    fig, ax = plt.subplots(figsize=(13, 4))
    for c, col in [("PRIMARY", C["kpi"]), ("W_APR", "#6c757d"), ("W_APR_JUN", C["f"]), ("W_JUN_JUL15", C["hi"])]:
        if c in series:
            ax.plot(series[c].resample("1D").median(), lw=1.4, color=col, label=f"{c} ({'W_APR_MAY' if c == 'PRIMARY' else c})")
    ax.axvspan(pd.Timestamp(COMMON_SCORING[0]), pd.Timestamp(COMMON_SCORING[1]), color="#eef2f6", zorder=0)
    ax.set_ylim(0, 100); ax.set_ylabel("daily median KPI")
    ax.set_title("Figure 5 — Training-window sensitivity (shaded: common period where every window is out of sample)")
    ax.legend(fontsize=8)
    f[5] = save(fig, "fig5_training_window_sensitivity.png")
    # 6 Sp.Heat F vs G
    fig, ax = plt.subplots(1, 2, figsize=(13, 4), gridspec_kw={"width_ratios": [2.2, 1]})
    for c, col, lab in [("PRIMARY", C["kpi"], "primary (F and G)"), ("SP_HEAT_F_ONLY", C["f"], "Sp.Heat F only"),
                        ("SP_HEAT_G_ONLY", C["g"], "Sp.Heat G only")]:
        ax[0].plot(series[c].resample("1D").median(), lw=1.3, color=col, label=lab)
    ax[0].set_ylim(0, 100); ax[0].legend(fontsize=8); ax[0].set_ylabel("daily median KPI")
    both = series[["SP_HEAT_F_ONLY", "SP_HEAT_G_ONLY"]].dropna()
    ax[1].scatter(both.SP_HEAT_F_ONLY, both.SP_HEAT_G_ONLY, s=2, alpha=0.3, color=C["kpi"])
    ax[1].plot([0, 100], [0, 100], color="k", lw=0.8)
    ax[1].set_xlabel("KPI with Sp.Heat F"); ax[1].set_ylabel("KPI with Sp.Heat G"); ax[1].set_xlim(0, 100); ax[1].set_ylim(0, 100)
    fig.suptitle("Figure 6 — Specific-heat definition sensitivity (Kiln-I F 'Sp.Heat | Sp.Heat' vs Kiln-I G 'Sp.Heat')")
    f[6] = save(fig, "fig6_sp_heat_sensitivity.png")
    # 7 persistence-window sensitivity (zoom 5 days around the out-of-sample maximum)
    tmax = k.efficiency_deterioration_kpi.idxmax()
    z0, z1 = tmax - pd.Timedelta("3D"), tmax + pd.Timedelta("2D")
    fig, ax = plt.subplots(figsize=(13, 4))
    for c, col, lw in [("NO_PERSISTENCE (raw 10-min deviation)", "#c5cad1", 0.6), ("MEDIAN_1h", "#9ab8d8", 0.9),
                       ("MEDIAN_3h", "#5c8fc4", 1.0), ("PRIMARY", C["kpi"], 1.8), ("MEDIAN_12h", C["lo"], 1.1), ("MEDIAN_24h", C["hi"], 1.1)]:
        if c in series:
            s = series[c].loc[z0:z1]
            ax.plot(s.index, s, color=col, lw=lw, label="MEDIAN_6h (primary)" if c == "PRIMARY" else c)
    ax.set_ylim(0, 100); ax.legend(fontsize=8, ncol=3); ax.set_ylabel("POC KPI")
    ax.set_title(f"Figure 7 — Persistence-window sensitivity around the largest out-of-sample KPI ({tmax:%Y-%m-%d %H:%M})")
    f[7] = save(fig, "fig7_persistence_sensitivity.png")
    # 8 representative normal vs elevated periods (48 h each, out of sample)
    d = k.efficiency_deterioration_kpi.resample("2D").agg(["median", "count"])
    d = d[d["count"] >= 200]
    lo_t, hi_t = d["median"].idxmin(), d["median"].idxmax()
    fig, ax = plt.subplots(2, 2, figsize=(13, 6), sharey="row")
    for j, (t0, title) in enumerate([(lo_t, "representative normal-like period"), (hi_t, "elevated-KPI period")]):
        w = k.loc[t0:t0 + pd.Timedelta("2D")]
        ax[0, j].plot(w.index, w.efficiency_deterioration_kpi, color=C["kpi"]); ax[0, j].set_ylim(0, 100)
        ax[0, j].axhline(k_lo, color=C["lo"], ls=":"); ax[0, j].axhline(k_hi, color=C["hi"], ls=":")
        ax[0, j].set_title(f"{title}: {t0:%Y-%m-%d} (+48 h)", fontsize=10)
        cw = comp[(comp.ts > t0) & (comp.ts <= t0 + pd.Timedelta("2D"))]
        for tag, col in [("Kiln-I!F", C["f"]), ("Kiln-I!G", C["g"]), ("Kiln-I!X", C["lo"]), ("Kiln-I!S", "#2b8a3e"), ("Kiln-I!AF", C["hi"])]:
            s = cw[cw.tag == tag].set_index("ts").z
            ax[1, j].plot(s.index, s, lw=0.8, color=col, label=tag)
        ax[1, j].axhline(0, color="k", lw=0.5); ax[1, j].set_ylim(-10, 10)
        for a in (ax[0, j], ax[1, j]):
            a.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
            a.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax[0, 0].set_ylabel("POC KPI"); ax[1, 0].set_ylabel("tag z (load-adjusted, capped ±10)"); ax[1, 1].legend(fontsize=8, ncol=5)
    fig.suptitle("Figure 8 — Representative normal-like vs elevated-KPI 48-h periods (observed deviation, NOT deposit/ring evidence)")
    f[8] = save(fig, "fig8_normal_vs_elevated.png")
    f["periods"] = (lo_t, hi_t)
    return f


def main():
    k = pd.read_parquet(OUT / "efficiency_deterioration_kpi.parquet").set_index("timestamp")
    ref = json.loads((OUT / "kpi_reference.json").read_text())
    inv = read_out("kpi_candidate_inventory.csv")
    tw = read_out("kpi_training_windows.csv")
    bands = read_out("kpi_reference_bands.csv")
    sens = read_out("kpi_sensitivity_analysis.csv")
    val = read_out("kpi_validation.csv")
    dq = read_out("kpi_data_quality.csv")
    man = read_out("kpi_version_manifest.csv")
    comp = pd.read_parquet(OUT / "kpi_component_scores.parquet", columns=["ts", "tag", "z", "tag_score", "dimension",
                                                                         "bucket_value", "expected_value", "scale"])
    series = pd.read_parquet(CACHE / "sensitivity_series.parquet")
    sc = ref["scale"]
    k_lo, k_hi = (float(to_kpi([sc[q]], sc["m"], sc["q_anchor"])[0]) for q in ("q_band_lo", "q_band_hi"))
    figs = figures(k, series, k_lo, k_hi, comp)
    oos = k[k.kpi_reference_state.eq("OUT_OF_SAMPLE")]   # headline: excludes the 6 h whose window overlaps training
    ins = k[k.kpi_in_sample_reference.notna()]
    n_inc = int(inv.included.sum())
    n_cand = int(inv.dimension.notna().sum())
    status_counts = inv.status.value_counts().to_dict()
    sp = sens[sens.group == "C specific heat"]
    sp_verdict = "PASS" if (sp.verdict == "CONSISTENT").all() else "MATERIAL DIFFERENCE"
    n_fail = int((val.result == "FAIL").sum())
    leak = val[val.check.str.startswith("LEAKAGE TEST")].result.iloc[0]
    n_cuts = val[val.check.str.startswith("LEAKAGE TEST")].evidence.iloc[0].count(" @ ")
    g7 = val[val.gate.str.startswith("G7")]
    monthly = oos.groupby(oos.index.to_period("M")).agg(
        scored_buckets=("efficiency_deterioration_kpi", "size"), median_kpi=("efficiency_deterioration_kpi", "median"),
        p90_kpi=("efficiency_deterioration_kpi", lambda s: s.quantile(0.9)),
        share_elevated_or_above=("efficiency_deterioration_kpi", lambda s: (s >= k_lo).mean()),
        share_beyond_reference=("efficiency_deterioration_kpi", lambda s: (s >= k_hi).mean()),
        median_efficiency_component=("efficiency_component", "median"),
        median_efficiency_unadjusted=("efficiency_component_unadjusted", "median"),
        median_feed_tph=("load_context_feed_tph", "median")).reset_index().rename(columns={"timestamp": "month"})
    monthly["month"] = monthly.month.astype(str)
    band_share = oos.kpi_band.value_counts(normalize=True).round(4).to_dict()
    top_dim = oos.top_dimension.value_counts(normalize=True).round(3).to_dict()
    drv_all = oos.kpi_driver_class.value_counts(normalize=True).round(3).to_dict()
    drv_hi = oos[oos.kpi_band_code >= 1].kpi_driver_class.value_counts(normalize=True).round(3).to_dict()
    drv_top = oos[oos.kpi_band_code == 2].kpi_driver_class.value_counts(normalize=True).round(3).to_dict()
    ho = sens[sens.group == "I calibration"].iloc[0]
    trend = sens[~sens.group.str.startswith(("0", "S", "A")) & sens.variant_trend_jun_to_aug.notna()].variant_trend_jun_to_aug
    near = sens[sens.near_threshold.fillna(False).astype(bool)].variant.tolist()
    sec = sens[sens.group.str.startswith("S")]
    # episodes beyond reference (out of sample)
    e = (oos.efficiency_deterioration_kpi >= k_hi).reindex(k.index, fill_value=False)
    lab = ((e != e.shift()).cumsum()).where(e)
    eps = (k.assign(lab=lab).dropna(subset=["lab"]).groupby("lab")
           .agg(start=("efficiency_deterioration_kpi", lambda s: s.index.min()), end=("efficiency_deterioration_kpi", lambda s: s.index.max()),
                buckets=("efficiency_deterioration_kpi", "size"), max_kpi=("efficiency_deterioration_kpi", "max"),
                top_dimension=("top_dimension", lambda s: s.mode().iloc[0] if len(s.mode()) else ""),
                driver=("kpi_driver_class", lambda s: s.mode().iloc[0] if len(s.mode()) else ""),
                max_dims_elevated=("n_dims_elevated", "max"))
           .sort_values("max_kpi", ascending=False).reset_index(drop=True))
    eps["duration_h"] = eps.buckets * 10 / 60
    g = sens[sens.group == "G weighting"]
    w_lvl = f"{g.median_abs_diff.min():.0f}–{g.median_abs_diff.max():.0f}"
    w_rho = f"{g.spearman.min():.2f}–{g.spearman.max():.2f}"
    eff_days = int(tw.loc[tw.window_id == "W_APR_MAY", "train_effective_running_days (>=50% running)"].iloc[0])
    score_days = int(oos.index.normalize().nunique())
    nopers = sens[sens.variant.str.startswith("NO_PERSISTENCE")].iloc[0]
    # worked traceability example at the maximum KPI
    tmax = oos.efficiency_deterioration_kpi.idxmax()
    r = k.loc[tmax]
    win = k.loc[(k.index > tmax - pd.Timedelta(PRIMARY.persistence_window)) & (k.index <= tmax)]
    e_ = max(0.0, r.persistent_deviation_score - sc["m"]) / (sc["q_anchor"] - sc["m"])
    ct = comp[comp.ts == tmax].sort_values("tag_score", ascending=False).head(8)
    ct = ct.assign(original_name=ct.tag.map(inv.set_index("tag").original_name))
    definition = {
        "kpi_name": KPI_NAME, "kpi_version": KPI_VERSION, "config_key": PRIMARY.key(),
        "purpose": "Measure how far, and how persistently, the kiln's observed efficiency-related behaviour has moved in the "
                   "deteriorating direction relative to its own empirically observed normal (training-window) behaviour.",
        "operator_question": "Is the kiln's observed operating behaviour deteriorating relative to its own normal baseline, "
                             "how severe and how persistent is it, and which process dimensions are deviating?",
        "scale": "0-100 POC normalized score (" + SCALE_LABEL + ")",
        "direction": "Higher = further, and more persistently, from the training reference. 'Worse' is asserted only for the "
                     "efficiency half (higher specific heat than expected for the load) and for process variability; the "
                     "other supporting dimensions are two-sided (any departure from normal raises them). 0 = at or below the "
                     "training median of the persistent score; 50 = the training P95.",
        "anchors": {"0": "training median of the 6-h persistent score", "50": "training P95 of the persistent score",
                    "band_elevated_from": round(k_lo, 2), "band_beyond_reference_from": round(k_hi, 2)},
        "formula": "KPI = 100*(1 - 2^-e), e = max(0, P - m)/(q95 - m); P = trailing 6-h median of D; "
                   "D = 0.5*S_EFFICIENCY + 0.5*mean(S_COMBUSTION, S_THERMAL, S_DRAFT_PRESSURE, S_STABILITY); "
                   "S_d = max(0, (mean tag score in d - training median)/training robust scale); tag score = max(0,z) for "
                   "Sp.Heat and variability, |z| otherwise; z = (bucket value - load-conditional training median)/training robust scale",
        "efficiency_evidence": "Kiln-I Sp.Heat F and G (both; plant has not confirmed which is authoritative). One-sided: only "
                               "higher specific heat than expected for the load counts.",
        "supporting_context": "Combustion, thermal, draft/pressure and process-stability deviations are two-sided process-deviation "
                              "context, not efficiency measurements.",
        "reported_when": "RUNNING (causal POC proxy) buckets, out of sample (after the training window), >= 50 % of the 6-h "
                         "window scored, efficiency data present and >= 2 supporting dimensions.",
        "training_window": f"{PRIMARY.train_start} .. {PRIMARY.train_end}",
        "not_equivalent_to": ["plant alarm limit", "engineering / control limit", "deposit confirmation", "ring formation",
                              "coating build-up", "equipment failure", "specific fuel consumption"],
        "validation_status": "Statistical / historical-data validation only. No deposit, ring or event ground truth exists.",
        "labels": {"state": PROXY_LABEL, "view": COMPOSITE_LABEL, "bands": BAND_LABEL, "equipment": EQUIPMENT_VIEW},
        "interpretation_rules": [
            "Read the KPI with its band and its persistence_fraction_elevated; single values are not events.",
            "WITHIN_REFERENCE_VARIATION: behaviour comparable with the training period.",
            "ELEVATED_POC_ANALYTICAL: persistent deviation reached in ~9 % of the training period; look at top_dimension / top_tag.",
            "BEYOND_REFERENCE_P99: reached in ~1 % of the training period; a deterioration-LIKE period that needs process "
            "explanation, not a confirmed deposit or ring. Use hours_in_current_band: a short visit is not persistent change.",
            "kpi_driver_class tells what carries the 6-h score: SPECIFIC_HEAT_LED (efficiency >= 60 % of the window contribution), "
            "PROCESS_DEVIATION_LED (<= 40 %) or MIXED; n_dims_elevated counts dimensions above their own training P90.",
            "kpi_confidence (HIGH / MEDIUM / LOW) combines tag coverage, window coverage, load range and near_band_boundary "
            "(KPI inside the bootstrap CI of a band cut). kpi_trend_7d is the change of the 7-day median against the prior 7 days.",
            "Absolute KPI levels and band shares depend on the training window and the 0.5 efficiency weight; compare periods "
            "with the same KPI version, and trust the direction of change more than the level.",
            "If efficiency_component is 0 while the KPI is raised, the rise is process-deviation context, not higher specific heat.",
            "Compare kpi_sp_heat_f_only and kpi_sp_heat_g_only when the two disagree; the plant must confirm the authoritative Sp.Heat.",
            "out_of_training_load_range = True: the load adjustment is extrapolated (clamped); treat with caution.",
            "No KPI is produced in stopped, transition, conflict or unknown periods, nor in September (no Kiln-I data)."],
    }
    definition["fields"] = {
        "efficiency_deterioration_kpi": "primary KPI (out of sample only)", "kpi_band / kpi_band_code": "0/1/2 = within / elevated / beyond",
        "kpi_training_percentile": "percentile of the persistent score in the training (calibration) distribution",
        "kpi_driver_class / window_efficiency_share": "what carries the 6-h score", "n_dims_elevated": "dimensions above training P90",
        "top_dimension / top_tag": "largest 6-h-window contribution and the largest tag inside it (top_dimension_bucket = this bucket)",
        "contrib_*": "weighted contribution of each dimension to D", "sp_heat_*_actual / *_expected_for_load": "efficiency evidence",
        "kpi_trend_7d / kpi_7d_median": "causal 7-day trend", "band_episode_id / hours_in_current_band": "causal episode tracking",
        "kpi_confidence / near_band_boundary": "reliability of the reading", "baseline_confidence": "Phase 2 confidence mix of the INPUT tags (not KPI confidence)",
        "kpi_sp_heat_f_only / kpi_sp_heat_g_only": "single-definition variants", "kpi_alt_reference_w_jun_jul15": "shadow KPI, later reference",
        "secondary_validation_mahalanobis_kpi": "validation cross-check only; not an operator KPI"}
    (OUT / "kpi_definition.json").write_text(json.dumps(definition, indent=1, default=str))

    L: list[str] = []
    A = L.append
    A("# Phase 3 — Kiln Efficiency Deterioration KPI\n")
    A("**Dalmia Cement, Ariyalur — Kiln Efficiency & Deposit Build-Up POC**\n")
    A(f"Generated from `phase-03-efficiency-kpi/outputs/` by `generate_report.py`. KPI version `{KPI_VERSION}`, config `{PRIMARY.key()}`.\n")
    A("> **What this is:** a *POC Kiln Efficiency Deterioration KPI*. It is an empirical, traceable measure of how far, and how "
      "persistently, observed kiln behaviour has moved in the deteriorating direction relative to the kiln's own normal behaviour "
      "in a fixed training window.\n>\n"
      "> **What it is not:** it is not a deposit, ring or coating detector. It is not a plant alarm or engineering limit, and it is "
      "not a failure predictor or a specific-fuel-consumption measurement.\n>\n"
      "> **No event ground truth exists**, so validation is statistical only.\n>\n"
      f"> - Operating state: **{PROXY_LABEL}**.\n"
      f"> - Cross-dataset view: **{COMPOSITE_LABEL}**.\n")
    # 1
    A("## 1. Executive Summary\n")
    A(f"- **KPI status: PARTIAL.** A reproducible, leakage-tested KPI exists. It is conditional on an unconfirmed operating-state "
      f"proxy, an unconfirmed equipment mapping and an unresolved Sp.Heat definition. It has no event validation.\n"
      f"- **Definition.** 0–100 POC score. Higher means further, and more persistently, from the "
      f"{PRIMARY.train_start[:10]} → {PRIMARY.train_end[:10]} reference. 'Worse' is asserted only for the efficiency half and "
      f"for variability.\n"
      f"  - Half of the evidence is specific heat (Sp.Heat F and G, one-sided: higher than expected for the load).\n"
      f"  - The other half is supporting process deviation (combustion, thermal, draft/pressure, stability).\n"
      f"  - A 6-hour trailing median suppresses short spikes.\n"
      f"- **Inputs.** {n_inc} tags in 5 dimensions were included, from {n_cand} mapped candidates and 203 Phase 1/2 tags. "
      f"Statuses: {status_counts}.\n"
      f"- **Out-of-sample result** ({oos.index.min():%Y-%m-%d} → {oos.index.max():%Y-%m-%d}, {len(oos)} scored 10-min buckets):\n"
      f"  - Median KPI is {oos.efficiency_deterioration_kpi.median():.1f}. Band shares are {band_share}.\n"
      f"  - The monthly median rises from {monthly.median_kpi.iloc[0]:.1f} to {monthly.median_kpi.iloc[-1]:.1f}.\n"
      f"  - The rise is carried by the supporting process-deviation dimensions (top dimension shares {top_dim}), not by specific heat.\n"
      f"  - The unadjusted efficiency component has a median of {monthly.median_efficiency_unadjusted.max():.2f} in every scored month: "
      f"Jun–Aug specific heat is **not** higher than the Apr–May reference.\n"
      f"  - **What the number is:** an efficiency-anchored deviation score.\n"
      f"    - Driver classes of all scored buckets: {drv_all}.\n"
      f"    - In ELEVATED or higher buckets: {drv_hi}.\n"
      f"    - In BEYOND_REFERENCE buckets: {drv_top}.\n"
      f"    - The typical level rise is process deviation with Sp.Heat below reference; the highest readings are read with "
      f"`kpi_driver_class`.\n"
      f"- **Level vs direction:** absolute levels and band shares depend on the training window and the DOMAIN-ASSUMED weights "
      f"(Section 12).\n"
      f"  - The **direction** of the Jun → Aug change is non-negative in every non-window variant (range "
      f"{trend.min():+.1f} to {trend.max():+.1f} points).\n"
      f"  - A held-out calibration (anchors fitted on 16–31 May) lowers the June median from "
      f"{sens.loc[sens.variant == 'PRIMARY', 'variant_median_2025-06'].iloc[0]:.1f} to {ho['variant_median_2025-06']:.1f}. Much of the "
      f"June level is therefore in-sample fit optimism, not change; treat June as the no-change benchmark.\n"
      f"- **Reference caveat (headline):** April has the highest Sp.Heat in the data. \"No specific-heat deterioration\" therefore "
      f"means no deterioration relative to a high-consumption reference period. It does not mean efficient operation.\n"
      f"- **Specific heat F vs G: {sp_verdict}.** " + "; ".join(f"{r.variant}: Spearman {r.spearman:.3f}, band agreement "
                                                            f"{r.band_agreement:.1%}, median |ΔKPI| {r.median_abs_diff:.1f}" for r in sp.itertuples()) + ".\n"
      f"- **Leakage test: {leak}.** KPI(t ≤ T) is bit-identical with and without 14 days of later data, at {n_cuts} cut points. "
      f"The reference is identical when fitted on truncated data.\n"
      f"- **Validation:** {len(val) - n_fail}/{len(val)} checks PASS.\n")
    # 2
    A("## 2. Business Question\n")
    A("Operator question: *Is the kiln's observed operating behaviour deteriorating relative to its own normal operating baseline?* "
      "The KPI supports these follow-up questions:\n")
    A("| Operator question | Field that answers it |\n|---|---|\n"
      "| Is efficiency deteriorating? | `efficiency_component` (specific heat above the load-conditional reference); the KPI answers the combined question |\n"
      "| How severe? | `efficiency_deterioration_kpi` and `kpi_band` |\n"
      "| Is it persistent? | the 6-h median `persistent_deviation_score` and `persistence_fraction_elevated` |\n"
      "| Which dimensions deviate? | the `*_component` columns, `top_dimension` and `top_tag`; per-tag z in `kpi_component_scores.parquet` |\n"
      "| When did it begin? | `band_episode_id`, `hours_in_current_band` (causal) and the episode table in Results |\n"
      "| Is it getting worse? | `kpi_trend_7d` (7-day median against the previous 7 days) |\n"
      "| What is driving it? | `kpi_driver_class`, `window_efficiency_share`, `n_dims_elevated`, `contrib_*` |\n"
      "| How reliable is this reading? | `kpi_confidence`, `near_band_boundary`, `data_quality`, `out_of_training_load_range` |\n"
      "| How far from normal? | the persistent score in training-scale units, against the training anchors `m` and `q95` |\n")
    A("Decision the number supports (POC): whether a period deserves process review. It is not an alarm and does not "
      "trigger a control action.\n")
    # 3
    A("## 3. Data Inputs\n")
    A("- **Minute data:** `data/processed/<dataset>.parquet` for Kiln-I, Kiln-IA, Kiln-II and Kiln-IIIA, read-only.\n"
      "- **State timeline:** `data/processed/operating_state_timeline.parquet`.\n"
      "- **Phase 2 CSVs:** listed in the version manifest, with their SHA-256. `data/curated/*_baseline.parquet` is **not** used "
      "for scoring. It was built from a retrospective state and full-period masks, so using it would leak future information "
      "into the score.\n"
      "- **Causal cell validity:** only Phase 2 tokens that depend on the cell itself are used (MISSING, TEXT_VALUE, "
      "TIMESTAMP_UNPARSED, SENTINEL_*, PHYSICALLY_IMPOSSIBLE_TEMP, DUPLICATE_TIMESTAMP_*, RESOLUTION_HOURLY).\n"
      "- **Recomputed causally inside the scorer:** `SUSPECT_TAG_FLATLINE` and `SUSPECTED_FROZEN_WINDOW` were detected "
      "retrospectively in Phase 2. Phase 3 replaces them with causal versions:\n"
      "  - Flatline: a non-zero identical run is masked from its 60th sample.\n"
      "  - Frozen row: at least 20 tags, and at least 80% of a dataset's present tags, each flat for 10 or more samples.\n")
    A(md_table(dq[dq.tag.astype(str).str.startswith(("P2_", "CAUSAL"))][["tag", "minutes", "causal_frozen_minutes_inside",
                                                                          "first_causal_frozen_minute"]]))
    A("Per-tag accounting, comparing causal masks with the Phase 2 retrospective flags, is in `kpi_data_quality.csv`. "
      "Kiln-I September is MISSING (truncated workbook), so no KPI is produced after the last Kiln-I running minutes "
      f"({oos.index.max()}).\n")
    # 4
    A("## 4. Phase 2 Baseline Dependency\n")
    A("- **What Phase 3 takes from Phase 2:**\n"
      "  - which columns are usable: column holds, `BASELINE_RUNNING` confidence and the tag contract;\n"
      "  - the `state_basic` (Kiln MD) signal and the per-cell quality tokens;\n"
      "  - the ramp rule, which Phase 3 re-implements causally.\n"
      "- **What Phase 3 does not take:** Phase 2 statistics were fitted over the full supplied period, so **none of its bands, "
      "medians or scales are used to score**. Every centre, scale, load curve, dimension standardiser and anchor is refitted on "
      "the Phase 3 training window only.\n"
      "- **Integrity check:** Phase 2 inputs are hashed at load and re-checked at validation (G2), and Phase 2's own validation "
      f"is {int((read_p2('phase2_validation.csv').result == 'PASS').sum())}/{len(read_p2('phase2_validation.csv'))} PASS.\n"
      "- **Confidence labels:** Phase 2 confidence (full-period) is used only as a label. It drives the LOW flag and the "
      "'drop LOW' sensitivity; no inclusion rule depends on it except INSUFFICIENT.\n")
    # 5
    A("## 5. KPI Definition\n")
    A(f"**{KPI_NAME}** (`{KPI_VERSION}`). Scale: {SCALE_LABEL}.\n")
    A("```text\nKPI(t) = 100 · (1 − 2^(−e)),   e = max(0, P(t) − m) / (q95 − m)\nP(t)   = median of D over the trailing 6 h (t−6h, t], scored buckets only, ≥ 50 % coverage\n"
      "D(t)   = 0.5 · S_EFFICIENCY(t) + 0.5 · mean(S_COMBUSTION, S_THERMAL, S_DRAFT_PRESSURE, S_STABILITY)   [available dims]\n"
      "S_d(t) = max(0, (mean tag score in d − training median) / training robust scale)\n"
      "tag score = max(0, z) for Sp.Heat and variability tags;  |z| for supporting process tags\n"
      "z      = clip((bucket value − E[tag | feed]) / training robust residual scale, −10, 10)\n```\n")
    A(f"Training anchors: m = {sc['m']:.4f} (KPI 0), q95 = {sc['q_anchor']:.4f} (KPI 50). POC analytical bands on the KPI scale: "
      f"< {k_lo:.1f} WITHIN REFERENCE VARIATION; {k_lo:.1f}–{k_hi:.1f} ELEVATED; ≥ {k_hi:.1f} PERSISTENT DEVIATION BEYOND REFERENCE.\n")
    A("Machine-readable definition: `outputs/kpi_definition.json`.\n")
    # 6
    A("## 6. Candidate Feature Selection\n")
    A("Rules, in order:\n\n"
      "- **R1:** Phase 2 column hold.\n"
      "- **R2:** Phase 2 INSUFFICIENT baseline.\n"
      "- **R3:** not in a KPI dimension (explicit or family reason).\n"
      "- **R4:** training coverage: at least 2,000 valid running buckets and at least 50% of training buckets.\n"
      "- **R5:** training scale greater than 0.\n"
      "- **R6:** redundant within its dimension (training Spearman |ρ| ≥ 0.95 with a higher-priority tag).\n\n"
      "C6 drift is **not** an exclusion reason. Drift is what the KPI measures once it is refitted.\n")
    show = inv[inv.dimension.notna()][["tag", "original_name", "family", "unit", "baseline_confidence", "quality_class", "included",
                                       "exclusion_reason", "dimension", "direction", "train_valid_buckets"]]
    A(md_table(show, max_col=60))
    A(f"All 203 Phase 1/2 tags, plus the derived inputs, with their exclusion reasons are in `kpi_candidate_inventory.csv` "
      f"({len(inv)} rows). The excluded subset is in `kpi_excluded_candidates.csv`.\n")
    ex = inv[~inv.included].exclusion_reason.str.extract(r"^(R\d[^:]*)")[0].fillna("other").value_counts().rename_axis("rule").reset_index(name="tags")
    A(md_table(ex))
    # 7
    A("## 7. Component Definitions\n")
    A("| Component | Tags (included) | Direction | Evidence type |\n|---|---|---|---|\n")
    for d, desc in [("EFFICIENCY", "one-sided (higher specific heat than expected for the load)"),
                    ("COMBUSTION", "two-sided"), ("THERMAL", "two-sided"), ("DRAFT_PRESSURE", "two-sided"),
                    ("STABILITY", "one-sided (more variability than training)")]:
        tg = inv[(inv.dimension == d) & inv.included].tag.tolist()
        A(f"| {d} | {', '.join(tg)} | {desc} | {'efficiency evidence' if d == 'EFFICIENCY' else 'process-deviation context'} |\n")
    A("\n- **FUEL.** Coal firing (H+I) per load is evaluated in the sensitivity analysis only, for two reasons:\n"
      "  - it duplicates the fuel-energy information in Sp.Heat;\n"
      "  - AFR substitution and fuel CV are unknown (ALTERNATIVE FUEL is INSUFFICIENT).\n"
      "- **PRODUCTION.** Feed and clinker TPH are **context only**. Low production is not read as deterioration.\n"
      "- **ALTERNATIVE FUEL.** Kiln-I K is context only; AF coverage is INSUFFICIENT.\n")
    # 8
    A("## 8. Normalization Method\n")
    A("- **Grain:** 10-minute buckets, right-closed `(t−10 min, t]` and labelled by their end. A bucket is the median of RUNNING "
      "minutes and needs at least 8 valid minutes. This follows the Phase 2 multivariate grain, reduces autocorrelation and "
      "historian repeats, and keeps 10-minute resolution.\n"
      "- **Load conditioning (primary):** the expected value is the training median of the tag within training feed-quantile "
      "bins (≤ 10 bins, ≥ 200 buckets each), linearly interpolated between bin medians and clamped outside the training range.\n"
      "  - Buckets outside the training feed P01–P99 carry `out_of_training_load_range`.\n"
      "  - Evidence: drafts track feed at ρ ≈ −0.9 and fan power at +0.9. Without adjustment the KPI would largely measure load "
      "(Section 12D).\n"
      "  - Adjusting for feed can hide a throughput loss, so the feed rate is always reported next to the KPI.\n"
      "- **Scale:** robust residual scale = max(scaled MAD, IQR/1.349, value resolution, 1% of |median|), fitted on training "
      "only. z is capped at ±10.\n"
      "- **Stability tags:** log of the trailing 60-minute rolling std (at least 45 minutes), against the training median and "
      "robust scale.\n"
      "- **Dimension standardisation:** each dimension's mean tag score is standardised by its own training median and robust "
      "scale, floored at 0. That puts one-sided and two-sided dimensions on a common scale, so the tag count does not set the weights.\n")
    A(md_table(pd.DataFrame([{"dimension": d, "training_median_raw": v["median"], "training_robust_scale": v["scale"]}
                             for d, v in ref["dims"].items()])))
    # 9
    A("## 9. Persistence Method\n")
    A("- **Rule:** P(t) is the trailing clock-time **median** of D over (t−6 h, t], using scored buckets only. It is reported "
      "only when at least 50% of the 36 buckets are scored; otherwise the row is `INSUFFICIENT_WINDOW`.\n"
      "- **Why a median:** it follows a change only once more than half the window has changed. A short spike can shift P by at "
      "most an adjacent order statistic, **independent of the spike's size**, and the effect leaves once the spike leaves the "
      "window. Both properties are tested (G5 injection checks).\n"
      "- **Latency:** about 3 h to a genuine step.\n"
      "- **Window:** 6 h is fixed a priori. It is roughly the time over which the training autocorrelation of D decays "
      "substantially; the ACF is reported descriptively only.\n"
      "- **`persistence_fraction_elevated`:** the share of the window's buckets with D above the training P90 of D.\n")
    A(md_table(bands[bands.quantity.str.startswith("DESCRIPTIVE")][["quantity", "persistent_score_value"]]))
    # 10
    A("## 10. Composite KPI Method\n")
    A("- **Weighting (primary, efficiency-anchored):** efficiency evidence carries 0.5 and the mean of the available supporting "
      "dimensions 0.5. This split is **DOMAIN-ASSUMED**: the KPI answers an efficiency question, so direct efficiency evidence "
      "carries half the weight. Within the supporting half, dimensions carry equal weight after data-derived standardisation.\n"
      "- **Alternatives compared (Section 12G):**\n"
      "  - equal per dimension;\n"
      "  - equal per tag;\n"
      "  - data-derived inverse redundancy (weights from the training Spearman between dimension scores);\n"
      "  - w_efficiency = 0.33 and 0.67.\n"
      "- **Data-derived inverse-redundancy weights (training):** "
      + ", ".join(f"{d} {w:.3f}" for d, w in ref["dim_weights"].items()) + ".\n"
      "- **Missing data:** a bucket needs the efficiency dimension and at least 2 supporting dimensions, otherwise it is "
      "`INSUFFICIENT_COMPONENTS` or `NO_EFFICIENCY_DATA`.\n"
      "- **Secondary validation KPI (not a competing KPI):** a robust Mahalanobis distance (MinCovDet, support 0.75, fixed "
      f"seed) on the signed, capped z of {len(ref['secondary']['cols'])} tags. It is fitted on training complete cases "
      f"(n = {ref['secondary']['n_fit']}, condition number {ref['secondary']['condition_number']:.0f}) and put through the same "
      "persistence and scale.\n")
    # 11
    A("## 11. Training/Scoring Window\n")
    A("The selection rule was declared in `build_training_window.py` before any scoring:\n\n"
      "- training covers at least 45 days of Kiln-I data and at least 2 stop/restart cycles;\n"
      "- every tentative feed band is at least 5% of training;\n"
      "- scoring keeps at least 60 days;\n"
      "- of the windows that qualify, the earliest wins.\n")
    twc = ["window_id", "role", "train_start", "train_end", "train_days_with_kiln_i_sp_heat", "train_stops", "train_share_FEED_BAND_1",
           "train_share_FEED_BAND_2", "train_share_FEED_BAND_3", "train_sp_heat_F_median_running", "train_sp_heat_G_median_running",
           "score_days_with_kiln_i_sp_heat", "all_criteria", "selected_by_rule"]
    A(md_table(tw[twc]))
    A(f"- **Primary windows:** training {PRIMARY.train_start} → {PRIMARY.train_end} ({ref['n_train_buckets']} running buckets). "
      f"Scoring runs from 2025-06-01 to the last scored bucket ({oos.index.max()}).\n"
      "- **Fixed reference:** there is no rolling or expanding refit, so slow drift is not absorbed into the reference.\n"
      "- **In-sample values:** inside the training window the KPI column is empty. The in-sample value is kept in "
      "`kpi_in_sample_reference`, for reference only.\n"
      f"- **Band uncertainty:** the bands are in-sample quantiles of an autocorrelated series with about {eff_days} effective days. "
      "Their day-block bootstrap CIs are below.\n")
    A(md_table(bands[bands["quantile"].notna()][["quantity", "persistent_score_value", "ci95_low", "ci95_high", "kpi_value", "kpi_ci95_low",
                                               "kpi_ci95_high", "n_training_days"]]))
    # 12
    A("## 12. Sensitivity Analysis\n")
    A(f"- **Method:** each variant changes one choice, refits its own reference and is compared with the primary on buckets "
      f"both score out of sample. Training-window variants are compared on the common period {COMMON_SCORING[0][:10]} → "
      f"{COMMON_SCORING[1][:10]}.\n"
      f"- **Pre-declared verdicts:** MATERIAL DIFFERENCE if Spearman < {MATERIALITY['spearman_min']}, band agreement < "
      f"{MATERIALITY['band_agreement_min']:.0%} or median |ΔKPI| > {MATERIALITY['median_abs_diff_max']:.0f}; COLLAPSE if "
      f"Spearman < 0.30 or fewer than 50% of buckets are scored.\n")
    sc_cols = ["group", "variant", "n_common", "spearman", "band_agreement", "median_abs_diff", "primary_median_kpi",
               "variant_median_kpi", "variant_share_elevated_or_above", "variant_episodes_beyond_reference", "verdict"]
    A(md_table(sens[~sens.group.str.startswith(("0", "S"))][sc_cols], max_col=48))
    A("\n**Reading** (verdicts from the table; `near_threshold` marks knife-edge verdicts: " + (", ".join(near) or "none") + ").\n")
    for grp, gdf in sens[~sens.group.str.startswith(("0", "S"))].groupby("group"):
        cons = gdf[gdf.verdict == "CONSISTENT"].variant.tolist()
        mat = gdf[gdf.verdict != "CONSISTENT"].variant.tolist()
        A(f"- **{grp}**: consistent — {', '.join(cons) or 'none'}; material — {', '.join(mat) or 'none'}.")
    A("")
    A("- **Interpretation.**\n"
      "  - **Training window:** the largest methodological dependency. A reference that excludes high-Sp.Heat April lowers the "
      "level materially.\n"
      "  - **Load:** load conditioning matters, because the unadjusted variant leaks load into the score. The tentative "
      "band-conditioned variant agrees with the continuous adjustment.\n"
      "  - **Persistence:** without it, short spikes dominate. With a 3–12 h median or a 6-h mean the KPI is consistent.\n"
      "  - **Weights:** the efficiency/process weighting sets the absolute **level** "
      f"(median |ΔKPI| {w_lvl} points), while ranking over time stays moderately stable (ρ {w_rho}).\n"
      "  - **Operating state, Sp.Heat definition, outlier caps and masks:** none of these matter.\n")
    A("Secondary validation KPI (descriptive):\n")
    A(md_table(sec[["variant", "n_common", "spearman", "verdict"]]))
    A("\nThe Mahalanobis distance is two-sided and not anchored on efficiency, so it agrees only weakly with the primary. It "
      "agrees more closely with the supporting process-deviation part. It is reported as a cross-check, not as an alternative KPI.\n")
    A(f"![training window]({figs[5]})\n\n![sp heat]({figs[6]})\n\n![persistence]({figs[7]})\n")
    # 13
    A("## 13. Statistical Validation\n")
    A("There are no event labels, so validation tests internal consistency only. No accuracy, precision, recall or AUC is "
      "reported.\n")
    A(md_table(val, max_col=110))
    # 14
    A("## 14. Results\n")
    A(f"![kpi]({figs[1]})\n\n![bands]({figs[2]})\n\n![components]({figs[3]})\n\n![distribution]({figs[4]})\n")
    A("Monthly out-of-sample summary:\n")
    A(md_table(monthly))
    A(f"\nIn-sample (training) reference: median KPI {ins.kpi_in_sample_reference.median():.2f}. Band shares "
      f"{ins.kpi_band.value_counts(normalize=True).round(4).to_dict()} reproduce the 90/9/1% design.\n")
    A("Observed persistent-deviation periods (KPI at or above the beyond-reference band, out of sample), largest first. "
      "These are **observed deterioration-like periods**. They are not ring, deposit or failure events.\n")
    A(md_table(eps.head(12)[["start", "end", "duration_h", "max_kpi", "top_dimension", "driver", "max_dims_elevated"]]))
    lo_t, hi_t = figs["periods"]
    A(f"\n![normal vs elevated]({figs[8]})\n\nFigure 8 compares the 48-h period with the lowest median KPI ({lo_t:%Y-%m-%d}) "
      f"with the one with the highest ({hi_t:%Y-%m-%d}).\n")
    A(f"### 14a. Traceability — why did the KPI equal {r.efficiency_deterioration_kpi:.1f} at {tmax}?\n")
    A(f"1. **Persistent score.** P = median of D over the {int(win.raw_deviation_score.notna().sum())} scored buckets in "
      f"({tmax - pd.Timedelta(PRIMARY.persistence_window)}, {tmax}] = **{r.persistent_deviation_score:.4f}** "
      f"(coverage {r.persistence_window_coverage:.2f}; fraction of buckets elevated {r.persistence_fraction_elevated:.2f}).\n"
      f"2. **Scale.** e = max(0, {r.persistent_deviation_score:.4f} − {sc['m']:.4f}) / ({sc['q_anchor']:.4f} − {sc['m']:.4f}) = "
      f"{e_:.4f}, so KPI = 100·(1 − 2^−{e_:.4f}) = **{100 * (1 - 2 ** -e_):.2f}**.\n"
      f"3. **Components at T.** "
      + ", ".join(f"{d} {r[f'{d.lower()}_component']:.2f}" for d in ["EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"])
      + f", giving D = {r.raw_deviation_score:.3f}. Top dimension: {r.top_dimension}; top tag: {r.top_tag}.\n"
      f"4. **Largest tag scores at T** (from `kpi_component_scores.parquet`):\n")
    A(md_table(ct[["tag", "original_name", "dimension", "bucket_value", "expected_value", "scale", "z", "tag_score"]]))
    A("\nReference: `kpi_reference.json` (training window, tag curves, scales, anchors). Code and inputs: `kpi_version_manifest.csv`.\n")
    # 15
    A("## 15. Limitations\n")
    A("- **No ground truth.** There are no deposit, ring, coating or event labels, so the KPI cannot be validated as an early "
      "warning or detector.\n"
      "- **Reference dependence.** The KPI measures deviation from Apr–May 2025, whose specific heat was the highest in the "
      "data. A later-anchored reference changes the KPI materially (Section 12A).\n"
      "- **Unconfirmed state and equipment.** The operating state is a POC PROXY built on Kiln MD, whose meaning is unconfirmed. "
      "The folders are assumed to be one kiln line.\n"
      "- **Sp.Heat ambiguity.** Two definitions exist and the plant has not confirmed one. The primary uses both; F-only and "
      "G-only are carried per row.\n"
      "- **No SFC, CV or AF data.** There is no explicit specific fuel consumption, fuel CV, moisture or RDF split. AF is "
      "INSUFFICIENT, so fuel-mix effects on Sp.Heat cannot be separated.\n"
      "- **Load adjustment.** It hides throughput-driven change (a kiln forced to lower feed). Feed is LOW-confidence (C5) and "
      "absent in September.\n"
      "- **Weighting.** The 0.5 efficiency/support split is DOMAIN-ASSUMED and moves absolute levels (Section 12G).\n"
      "- **Band uncertainty.** Bands and anchors are in-sample quantiles of an autocorrelated 61-day series, with wide bootstrap "
      "CIs.\n"
      f"- **Limited scoring.** Only {score_days} scoring days on Kiln-I, and nothing in September.\n"
      "- **Scoring gaps.** Causal restart ramps can last up to 48 h and are not scored. Pre-stop minutes are scored, because the "
      "stop is unknown in advance.\n"
      "- **In-sample calibration.** Anchors and standardisers are fitted on the same window. The held-out calibration variant "
      "shows June's level is mostly fit optimism (Section 12I).\n"
      "- **Phase 2 labels used as design constants.**\n"
      "  - Retrospective Phase 2 RUNNING minutes define the *training* population only, which is hindsight inside the past "
      "window; pre-stop minutes are left out of training but scored later.\n"
      "  - Column holds, confidence labels and the descriptive feed bands come from the Phase 2 full period. The 'drop LOW' "
      "variant is therefore future-informed.\n"
      "- **Kiln feed is exempt from the flatline mask.** A feeder at setpoint is valid load information. The masked variant is "
      "consistent (Section 12H).\n"
      "- **Pre-stop dynamics.** A stop cannot be known in advance, so the minutes before it are scored. Feed reduction before a "
      "stop raises specific heat and other deviations (for example the last buckets on 2025-08-23); the 6-h median damps them.\n"
      "- **Pooled supporting half.** Supporting dimensions are two-sided process deviation. A rise driven by them shows the "
      "process has changed, not that efficiency is lost.\n")
    # 16
    A("## 16. Interpretation Rules\n")
    A("```text\n" + "\n".join([f"KPI name:           {KPI_NAME}", f"Purpose:            {definition['purpose']}",
                              f"Scale:              {definition['scale']}", f"Direction:          {definition['direction']}",
                              "Not equivalent to:  " + ", ".join(definition["not_equivalent_to"]),
                              f"Validation status:  {definition['validation_status']}"]) + "\n```\n")
    for i, rule in enumerate(definition["interpretation_rules"], 1):
        A(f"{i}. {rule}")
    A("")
    # 17
    A("## 17. Phase 4 Inputs\n")
    A("- **`efficiency_deterioration_kpi.parquet`:** one row per 10-min bucket. It carries the KPI, the components, the raw and "
      "persistent scores, the band, the state, load context, data quality, the Sp.Heat F/G variants, the secondary KPI and the "
      "training/source windows.\n"
      "- **`kpi_component_scores.parquet`:** per-tag bucket value, expected value, scale, z and score.\n"
      "- **`kpi_reference.json`:** the frozen training reference, to reuse for any later scoring without refitting.\n"
      "- **`kpi_reference_bands.csv`, `kpi_definition.json`:** anchors, bands with CIs, and interpretation rules.\n"
      "- **`kpi_candidate_inventory.csv`:** usable tags per dimension, with the kiln-drive and cooler tags deliberately left "
      "for Phase 4 as leading-indicator candidates.\n"
      "- **`kpi_sensitivity_analysis.csv`, `kpi_validation.csv`, `kpi_version_manifest.csv`.**\n"
      "- **`kpi_core.py`:** the causal scoring functions (`run_kpi`, `fit_reference`, `score`), which are leakage-tested.\n\n"
      "Phase 4 must treat the KPI as a *target/context series with known limitations*, not as event labels.\n")
    A("## Appendix A — Reproducibility\n")
    A("```bash\ncd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-03-efficiency-kpi/scripts\n"
      "../../.venv/bin/python run_phase3.py --clean\n```\n")
    A(md_table(g7, max_col=110) if len(g7) else "_G7 is recorded by run_phase3.py after this report is first generated._\n")
    A(f"\nConfiguration (all POC heuristics or design choices, not plant limits): `{json.dumps(asdict(PRIMARY), default=str)}`\n")
    A("Training windows compared: " + "; ".join(f"{k_}: {v[0]} → {v[1]} ({v[2]})" for k_, v in TRAINING_WINDOWS.items()) + "\n")
    A(md_table(man[~man.item.str.startswith(("code_sha256", "input_sha256", "config"))], max_col=120))
    rl = PHASE_DIR / "reviews" / "REVIEW_LOG.md"
    if rl.exists():
        A("\n## Appendix B — Reviews\n")
        A(rl.read_text(encoding="utf-8").split("\n", 1)[1])
    md = "\n".join(L)
    (REPORTS / "PHASE_3_EFFICIENCY_DETERIORATION_KPI.md").write_text(md, encoding="utf-8")
    from markdown_it import MarkdownIt
    css = (":root{--bg:#fff;--fg:#1d2330;--line:#d9dde5;--head:#f3f5f8;--accent:#0b5cad}"
           "@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e6e9ef;--line:#2c323c;--head:#1c2027;--accent:#6aa9ff}}"
           "body{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:16px}"
           "table{border-collapse:collapse;display:block;overflow-x:auto;font-size:12px;margin:8px 0}th,td{border:1px solid var(--line);padding:3px 6px;text-align:left}"
           "th{background:var(--head)}img{max-width:100%;background:#fff}blockquote{border-left:3px solid var(--accent);margin:0;padding:4px 12px}"
           "code,pre{background:var(--head)}pre{padding:8px;overflow-x:auto;white-space:pre-wrap}h2{border-bottom:1px solid var(--line);margin-top:2em}")
    body = MarkdownIt("commonmark").enable("table").render(md)
    (REPORTS / "PHASE_3_EFFICIENCY_DETERIORATION_KPI.html").write_text(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Phase 3 Efficiency KPI</title><style>{css}</style></head><body>{body}</body></html>", encoding="utf-8")
    lg.info("wrote reports/PHASE_3_EFFICIENCY_DETERIORATION_KPI.md / .html and outputs/kpi_definition.json")


if __name__ == "__main__":
    main()
