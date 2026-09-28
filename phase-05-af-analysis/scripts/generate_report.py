"""Step - Phase 5 report (Markdown + HTML), figures and the version manifest.

Reads  every Phase 5 output and cache/{input_hashes.json, bands.json, episodes.csv}
Writes reports/PHASE_5_ALTERNATIVE_FUEL_ANALYSIS.{md,html}, reports/figures/*.png, outputs/afr_version_manifest.csv

Every number in the report is read from the outputs at generation time. Wording follows the Phase 5 evidence labels and
is scanned for causal / control-recommendation language before writing (af_core.forbidden_hits).
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

from af_core import (ASSOC_LABEL, BAND_LABEL, CACHE, EPISODE_LABEL, EXCLUDED_TARGETS, FIG, METHOD_VERSION, OUT,  # noqa: E402
                     PHASE_DIR, PRIMARY, REPORTS, forbidden_hits, log, read_out, sha256, write_csv)

lg = log("generate_report")
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]            # validated reference categorical slots 1-3 (dataviz palette)
RAMP = ["#cde2fb", "#86b6ef", "#2a78d6", "#104281"]    # one-hue ordinal ramp for NO / LOW / MEDIUM / HIGH_AFR
INK, INK2 = "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "#fcfcfb",
                     "axes.facecolor": "#fcfcfb", "lines.linewidth": 2})
REL = {"LOAD": "afr_load_relationships.csv", "COMBUSTION": "afr_combustion_relationships.csv",
       "THERMAL": "afr_thermal_relationships.csv", "EFFICIENCY": "afr_efficiency_relationships.csv",
       "INDICATOR": "afr_indicator_relationships.csv"}
W3 = ("DISCOVERY", "REPLICATION", "HOLDOUT_AUG")


# ============================================================================== helpers
def md_table(df: pd.DataFrame, max_rows: int | None = None, max_col: int = 90, floatfmt: str = "{:.3g}") -> str:
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
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=100, metadata={"Software": None})
    plt.close(fig)
    return f"figures/{name}"


def f3(v, fmt="{:+.3f}") -> str:
    return "n/a" if v is None or not np.isfinite(v) else fmt.format(v)


def load_rel() -> pd.DataFrame:
    return pd.concat([read_out(f) for f in REL.values()], ignore_index=True)


def corr_summary(rel: pd.DataFrame, families: list[str]) -> pd.DataFrame:
    """One line per selected correlation relationship: discovery / replication / August effects and labels."""
    s = rel[rel.row_role.eq("SELECTED_LAG") & rel.target_family.isin(families)]
    key = ["target_family", "target_signal", "analysis_type"]
    w = s.pivot_table(index=key, columns="window", values="effect_size", aggfunc="first")
    d = s[s.window.eq("DISCOVERY")].set_index(key)
    w = w.reindex(d.index)
    names = [f"{n} ({u})" if isinstance(u, str) and u else str(n)
             for n, u in zip(d.target_original_name, d.target_unit)]
    out = pd.DataFrame({
        "target": d.index.get_level_values(1), "name": names,
        "type": d.index.get_level_values(2), "lag_min": d.lag_minutes.to_numpy(),
        "disc_rho [95% CI]": [f"{r:+.3f} [{lo:+.2f}, {hi:+.2f}]" if np.isfinite(r) else "n/a"
                              for r, lo, hi in zip(d.effect_size, d.confidence_interval_low, d.confidence_interval_high)],
        "q": d.adjusted_p_value.to_numpy(), "n_eff": d.effective_sample_size.to_numpy(),
        "jun_jul_rho": w["REPLICATION"].to_numpy(), "aug_rho": w["HOLDOUT_AUG"].to_numpy(),
        "stability": d.stability.to_numpy(), "holdout": d.holdout_result.to_numpy(),
        "null_pass": d.negative_control_pass.to_numpy(), "evidence": d.evidence.to_numpy(),
        "confidence": d.confidence.to_numpy()})
    order = {"ASSOCIATED": 0, "WEAK ASSOCIATION": 1, "NOT SUPPORTED": 2, "INSUFFICIENT DATA": 3, "NOT COMPUTABLE": 4}
    return out.assign(_o=out.evidence.map(order)).sort_values(["_o", "target", "type"], kind="mergesort").drop(columns="_o")


def episode_summary(rel: pd.DataFrame, families: list[str], only_supported: bool = True) -> pd.DataFrame:
    e = rel[rel.row_role.eq("EPISODE_PRIMARY") & rel.target_family.isin(families)
            & rel.analysis_type.str.startswith("EPISODE_AFR")]
    if only_supported:
        e = e[e.evidence.isin(["ASSOCIATED", "WEAK ASSOCIATION"])]
    return pd.DataFrame({"target": e.target_signal,
                         "name": [f"{n} ({u})" if isinstance(u, str) and u else str(n)
                                  for n, u in zip(e.target_original_name, e.target_unit)],
                         "transition": e.analysis_type.str.replace("EPISODE_", "", regex=False),
                         "window_compared": e.window_compared, "n": e.sample_count, "median_diff": e.effect_size,
                         "ci_low": e.confidence_interval_low, "ci_high": e.confidence_interval_high,
                         "perm_q": e.adjusted_p_value, "stability": e.stability, "august": e.holdout_result,
                         "evidence": e.evidence, "confidence": e.confidence}).reset_index(drop=True)


def get(rel, fam, tag, atype, window="DISCOVERY", col="effect_size"):
    r = rel[(rel.target_family == fam) & (rel.target_signal == tag) & (rel.analysis_type == atype)
            & ~rel.row_role.eq("LAG_PROFILE") & (rel.window == window)]
    return r[col].iloc[0] if len(r) else np.nan


def ep_get(rel, fam, tag, typ, lag, window="POOLED_APR_JUL", col="effect_size"):
    r = rel[(rel.target_family == fam) & (rel.target_signal == tag) & (rel.analysis_type == f"EPISODE_{typ}")
            & (rel.lag_minutes == lag) & (rel.window == window)]
    return r[col].iloc[0] if len(r) else np.nan


# ============================================================================== figures
def fig_daily(daily: pd.DataFrame) -> str:
    d = daily.assign(date=pd.to_datetime(daily.date))
    fig, ax = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True)
    ax[0].plot(d.date, d.median_nonzero_tph, color=SERIES[0])
    ax[0].set_ylabel("TPH")
    ax[0].set_title("Median non-zero AFR | Solid while running (daily)", loc="left", fontsize=9)
    ax[1].plot(d.date, 100 * (1 - d.duty_cycle_running), color=SERIES[0])
    ax[1].set_ylabel("% of running minutes")
    ax[1].set_title("Share of valid running minutes with AFR = 0 (daily)", loc="left", fontsize=9)
    for a in ax:
        a.axvspan(pd.Timestamp("2025-04-01"), pd.Timestamp("2025-06-01"), color="#e6e5e0", alpha=0.5, lw=0)
    ax[0].text(pd.Timestamp("2025-04-03"), ax[0].get_ylim()[1] * 0.97, "DISCOVERY", va="top", color=INK2, fontsize=8)
    return save(fig, "afr_daily.png")


def fig_bands(bands: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    wins = ["discovery", "jun", "jul", "aug"]
    bottom = np.zeros(len(wins))
    for i, r in enumerate(bands.itertuples()):
        v = np.array([getattr(r, f"occupancy_{w}") for w in wins], float) * 100
        ax.barh(["Apr-May", "Jun", "Jul", "Aug"], v, left=bottom, color=RAMP[i], edgecolor="#fcfcfb", linewidth=2,
                label=r.band)
        bottom += np.nan_to_num(v)
    ax.invert_yaxis()
    ax.set_xlabel("% of running 10-min buckets with valid AFR")
    ax.set_title(f"AFR {BAND_LABEL} occupancy by window (cuts fitted on Apr-May)", loc="left", fontsize=9)
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    ax.grid(axis="y", visible=False)
    return save(fig, "afr_band_occupancy.png")


def fig_stop_episode(long: pd.DataFrame) -> str:
    sig = [("AFR (Kiln-I!K)", "AFR | Solid (TPH)"), ("Kiln-I!I", "PC coal firing (TPH)"),
           ("Kiln-I!C", "Kiln feed (TPH)"), ("Kiln-II!O", "Cyclone 2 material temp (°C)")]
    e = long[long.status.eq("ELIGIBLE") & long.afr_transition.eq("AFR_STOP")]
    fig, axes = plt.subplots(2, 2, figsize=(9, 5.2), sharex=True)
    for ax, (s, title) in zip(axes.ravel(), sig):
        g = e[e.signal.eq(s)].groupby("rel_min").delta
        med, lo, hi = g.median(), g.quantile(0.25), g.quantile(0.75)
        ax.fill_between(med.index, lo, hi, color=SERIES[0], alpha=0.18, lw=0)
        ax.plot(med.index, med, color=SERIES[0])
        ax.axvline(0, color=INK2, lw=1, ls="--")
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_title(title, loc="left", fontsize=9)
    for ax in axes[1]:
        ax.set_xlabel("minutes from AFR_STOP (T)")
    fig.suptitle(f"AFR_STOP episodes (n = {e.episode_id.nunique()}): median change from [T-60, T) baseline, IQR band",
                 x=0.01, ha="left", fontsize=9)
    return save(fig, "afr_stop_episode_response.png")


def fig_forest(cs: pd.DataFrame) -> str:
    d = cs[cs.evidence.isin(["ASSOCIATED", "WEAK ASSOCIATION"])].copy()
    d["disc"] = d["disc_rho [95% CI]"].str.split(" ").str[0].astype(float)
    d = d.sort_values("disc", kind="mergesort")
    lab = d.target + " " + d.type.str.replace("_", " ").str.lower() + " (" + d.lag_min.astype(int).astype(str) + " min)"
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(8.5, max(3.0, 0.24 * len(d) + 1)))
    for j, (col, name) in enumerate((("disc", "Apr-May (discovery)"), ("jun_jul_rho", "Jun-Jul (replication)"),
                                     ("aug_rho", "Aug (holdout)"))):
        ax.scatter(d[col], y + (j - 1) * 0.22, s=22, color=SERIES[j], label=name, zorder=3, edgecolor="#fcfcfb",
                   linewidth=1)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(y, lab, fontsize=7)
    ax.set_xlabel("partial Spearman rho (AFR feature vs target)")
    ax.set_title("Correlation relationships labelled ASSOCIATED or WEAK ASSOCIATION", loc="left", fontsize=9)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    return save(fig, "afr_relationship_forest.png")


# ============================================================================== manifest
def version_manifest(bands: dict) -> pd.DataFrame:
    hashes = json.loads((CACHE / "input_hashes.json").read_text())
    code = {p.name: sha256(p) for p in sorted((PHASE_DIR / "scripts").glob("*.py"))}
    code.update({f"tests/{p.name}": sha256(p) for p in sorted((PHASE_DIR / "tests").glob("*.py"))})
    man = [("method_version", METHOD_VERSION), ("config_key", PRIMARY.key()),
           ("config", json.dumps(asdict(PRIMARY), sort_keys=True, default=str)),
           ("band_cuts", json.dumps(bands, sort_keys=True)), ("band_label", BAND_LABEL), ("episode_label", EPISODE_LABEL),
           ("association_label", ASSOC_LABEL),
           ("windows", "DISCOVERY 2025-04-01..05-31; JUN from 2025-06-01 06:00; JUL; AUG holdout (KPI ends 2025-08-23); "
                       "no September (Kiln-I September workbook unavailable)"),
           ("afr_series", "AFR_P2: Kiln-I!K after Phase 2 causal tokens, negatives -> NaN, dataset frozen rows -> NaN, "
                          "RUNNING 10-min bucket median (>= 8 valid minutes); no interpolation"),
           ("validation_status", "statistical / historical association only; no fuel properties; no event ground truth"),
           ("python", platform.python_version()), ("pandas", pd.__version__), ("numpy", np.__version__),
           ("scipy", scipy.__version__), ("matplotlib", matplotlib.__version__)]
    man += [(f"input_sha256:{n}", h) for n, h in sorted(hashes.items())]
    man += [(f"code_sha256:{n}", h) for n, h in code.items()]
    return pd.DataFrame(man, columns=["item", "value"])


# ============================================================================== report
def main():
    inv, dq = read_out("afr_inventory.csv"), read_out("afr_data_quality.csv")
    bands_df, monthly = read_out("afr_operating_bands.csv"), read_out("afr_monthly_summary.csv")
    daily = read_out("afr_daily_summary.csv")
    rel, sens, match = load_rel(), read_out("afr_sensitivity_analysis.csv"), read_out("afr_matched_analysis.csv")
    req, val = read_out("afr_data_requirements.csv"), read_out("afr_validation.csv")
    long = pd.read_parquet(OUT / "afr_transition_episodes.parquet")
    ep = pd.read_csv(CACHE / "episodes.csv")
    bands = json.loads((CACHE / "bands.json").read_text())
    write_csv(version_manifest(bands), "afr_version_manifest.csv", lg)
    cs_all = corr_summary(rel, ["LOAD", "FUEL_CO_MANIPULATION", "COMBUSTION", "THERMAL", "EFFICIENCY", "INDICATOR"])
    figs = {"daily": fig_daily(daily), "bands": fig_bands(bands_df), "stop": fig_stop_episode(long),
            "forest": fig_forest(cs_all)}

    iv = inv.set_index("indicator_id")
    k_all = dq[(dq.afr_signal == "Kiln-I!K") & dq.scope.eq("ALL_SUPPLIED")].iloc[0]
    k_run = dq[(dq.afr_signal == "Kiln-I!K") & dq.scope.eq("RUNNING_MINUTES")].iloc[0]
    k_nrun = dq[(dq.afr_signal == "Kiln-I!K") & dq.scope.eq("NOT_RUNNING_MINUTES")].iloc[0]
    l_all = dq[(dq.afr_signal == "Kiln-I!L") & dq.scope.eq("ALL_SUPPLIED")].iloc[0]
    prim = rel[rel.row_role.isin(["SELECTED_LAG", "EPISODE_PRIMARY"]) & rel.window.isin(["DISCOVERY", "POOLED_APR_JUL"])]
    ev_counts = prim.groupby(["target_family", "evidence"]).size().unstack(fill_value=0)
    n_elig = int(ep.status.eq("ELIGIBLE").sum())
    vcount = val.result.value_counts().to_dict()
    feed_lvl = [get(rel, "LOAD", "Kiln-I!C", "LAGGED_LEVEL", w) for w in W3]
    pc_lvl = [get(rel, "FUEL_CO_MANIPULATION", "Kiln-I!I", "LAGGED_LEVEL", w) for w in W3]
    pc_mom = [get(rel, "FUEL_CO_MANIPULATION", "Kiln-I!I", "MOMENTUM", w) for w in W3]
    pc_stop = ep_get(rel, "FUEL_CO_MANIPULATION", "Kiln-I!I", "AFR_STOP", 60)
    o2_lvl = [get(rel, "COMBUSTION", "Kiln-I!AD", "LAGGED_LEVEL", w) for w in W3]
    o2_mom = [get(rel, "COMBUSTION", "Kiln-I!AD", "MOMENTUM", w) for w in W3]
    nox_mom = [get(rel, "COMBUSTION", "Kiln-I!AC", "MOMENTUM", w) for w in W3]
    shf = [get(rel, "THERMAL", "Kiln-I!F", "LAGGED_LEVEL", w) for w in W3]
    shg = [get(rel, "THERMAL", "Kiln-I!G", "LAGGED_LEVEL", w) for w in W3]
    der = rel[rel.analysis_type.eq("SP_HEAT_DERIVATION_CHECK")].pivot_table(index="target_signal", columns="window",
                                                                            values="effect_size", aggfunc="first")
    der = der[[c for c in W3 if c in der.columns]]
    cyc2_stop = ep_get(rel, "THERMAL", "Kiln-II!O", "AFR_STOP", 60)
    kpi_lvl = [get(rel, "EFFICIENCY", "KPI:K", "LAGGED_LEVEL", w) for w in ("DISCOVERY", "JUN", "JUL", "HOLDOUT_AUG")]
    kpi_fc_ev = get(rel, "EFFICIENCY", "KPI:K", "FUTURE_CHANGE", col="evidence")
    kpi_stop = ep_get(rel, "EFFICIENCY", "KPI:K", "AFR_STOP", 180)
    act = [get(rel, "INDICATOR", "P4:Kiln-I!I|ROC_1H", "INDICATOR_ACTIVATION_FALLING_VS_STEADY_AFR", w) for w in W3]
    kf = "KPI:K future change (60 min)"
    att = {w: (get(rel, "INDICATOR", kf, "INDICATOR_KPI_LEAD_WITHOUT_AFR", w),
               get(rel, "INDICATOR", kf, "INDICATOR_KPI_LEAD_WITH_AFR_CONTROLS", w)) for w in W3}
    att_ci = get(rel, "INDICATOR", kf, "INDICATOR_KPI_LEAD_WITH_AFR_CONTROLS", "REPLICATION", "confidence_interval_low")
    kpi_prec = rel[rel.analysis_type.str.startswith("KPI_EPISODE_PRECURSOR") & rel.row_role.eq("EPISODE_PRIMARY")]
    null_share = prim[prim.row_role.eq("SELECTED_LAG")].negative_control_pass.astype(str).eq("True").mean()
    nc = sens[sens.group.eq("NC_MISALIGNED_30D")]
    counted = sens[sens.counted_in_agreement & sens.same_sign_as_primary.notna()]
    sens_tab = counted.groupby("group").agg(variants=("variant", "nunique"), rows=("variant", "size"),
                                            same_sign_share=("same_sign_as_primary",
                                                             lambda s: s.astype(bool).mean())).reset_index()
    n_assoc, n_weak = int((prim.evidence == "ASSOCIATED").sum()), int((prim.evidence == "WEAK ASSOCIATION").sum())
    mstat = match.drop_duplicates(["comparison", "window"])[["comparison", "window", "treated_candidates",
                                                             "control_candidates", "matched_pairs", "matching_status",
                                                             "not_supported_reason"]]
    def kind(flags):
        f = str(flags)
        if "CO_MANIPULATION" in f:
            return "CO_MANIPULATION"
        if "SP_HEAT" in f:
            return "SP_HEAT_OR_KPI"
        return "PROCESS"
    pa = prim[prim.evidence.eq("ASSOCIATED")]
    kinds = {k: int((pa["flags"].map(kind) == k).sum()) for k in ("PROCESS", "CO_MANIPULATION", "SP_HEAT_OR_KPI")}
    hold_counts = pa.holdout_result.value_counts().to_dict()
    fails = val[val.result.eq("FAIL")]
    vtxt = (f"{vcount.get('PASS', 0)} PASS, {vcount.get('INFO', 0)} INFO, {vcount.get('NOT_MET_REPORTED', 0)} "
            f"NOT_MET_REPORTED, {vcount.get('FAIL', 0)} FAIL (§23).")
    if len(fails):
        vtxt += " FAIL: " + "; ".join(f"{r.gate} — {r.check}: {r.evidence}" for r in fails.itertuples())
    L = []
    A = L.append
    A("# Phase 5 — Alternative Fuel (AFR) Analysis\n")
    A("**Dalmia Cement Ariyalur Kiln POC** · data April–August 2025 · method " + METHOD_VERSION + "\n")
    A("> Every relationship below is **AFR-associated, not AFR-caused**. AFR firing is a control input set by the operator "
      "or controller; no fuel properties (calorific value, moisture, composition) exist in the supplied data. Nothing here "
      "is a plant limit, a set-point or an operating recommendation. Bands are POC empirical bands; transition episodes "
      "are empirical windows, not plant events.\n")

    A("## 1. Executive Summary\n")
    A("### Operational takeaways\n")
    A(f"1. **AFR interruptions are fuel swaps.** When AFR | Solid stops or ramps down during running, PC coal firing goes "
      f"up at the same time (median {f3(pc_stop, '{:+.1f}')} TPH within 60 min vs matched controls). Feed is often cut, "
      f"and preheater / TAD temperatures dip and recover within about 1–2 h (cyclone-2 material temperature "
      f"{f3(cyc2_stop, '{:+.1f}')} °C). Treat an AFR stop as a simultaneous change of several inputs, not an AFR-only "
      "change.\n"
      f"2. **No AFR–efficiency-KPI signal survives.** Neither the AFR level nor AFR changes relate reproducibly to the "
      f"Phase 3 KPI. AFR behaviour does not precede the Phase 4 KPI deterioration episodes.\n"
      "3. **Stronger conclusions need three pieces of plant information:**\n"
      "   - the Sp.Heat formula;\n"
      "   - whether `Kiln-I!K` is a set-point or a measurement;\n"
      "   - an AFR operating log (§22a).\n"
      "   Fuel properties (calorific value, moisture) come next.\n")
    A("### Evidence detail\n")
    A(f"- **Signals.** `Kiln-I!K` *AFR | Solid* (TPH) was analysed. `Kiln-I!L` *Liquid* (LPH) is **INSUFFICIENT DATA**: "
      f"only {1 - l_all.missing_fraction:.1%} of minutes are present, it is bimodal and it contains "
      f"{int(l_all.sentinel_candidates_ge_9999)} values at or above 9,999.\n"
      f"- **Most AFR = 0 minutes are kiln stops.** {k_nrun.zero / k_all.zero:.0%} of AFR = 0 minutes occur while the kiln "
      f"is not running. While it is running, AFR is 0 in only {k_run.zero_fraction:.1%} of minutes.\n"
      f"- **AFR tracks load (ASSOCIATED).** In running buckets, the AFR 1-h level co-varies with kiln feed "
      f"(partial ρ {f3(feed_lvl[0])} Apr–May, {f3(feed_lvl[1])} Jun–Jul, {f3(feed_lvl[2])} August). Load is the first "
      "confounder of every AFR comparison.\n"
      f"- **AFR and PC coal are operated in opposite directions (co-manipulation, not a process effect).**\n"
      f"  - The level and 1-h-change correlations are ASSOCIATED in every window: level ρ {f3(pc_lvl[0])} / "
      f"{f3(pc_lvl[1])} / {f3(pc_lvl[2])}; change ρ {f3(pc_mom[0])} / {f3(pc_mom[1])} / {f3(pc_mom[2])}.\n"
      "  - The post-stop PC rise is ASSOCIATED at LOW confidence.\n"
      "  - Confidence for co-manipulation rows is capped at LOW by design.\n"
      f"- **Combustion and temperature co-movements are small and entangled with the fuel swap.**\n"
      f"  - Higher AFR co-occurs with lower preheater-outlet O₂ (level ρ {f3(o2_lvl[0])}, replicated, August confirmed) "
      "and with falling NOx.\n"
      "  - Preheater and TAD temperatures are lower in the hour after AFR stops and ramp-downs.\n"
      "  - Because PC coal is raised at the same time, none of these can be attributed to AFR alone.\n"
      f"- **Sp.Heat is closely reproducible from the firing rates, including AFR.** Sp.Heat F / G co-vary with the AFR "
      f"level (ρ {f3(shf[0])} / {f3(shg[0])}). Firing rates per ton of feed reproduce F with R² "
      f"{f3(der.loc['Kiln-I!F', 'DISCOVERY'], '{:.2f}')} and G with R² {f3(der.loc['Kiln-I!G', 'DISCOVERY'], '{:.2f}')} "
      "(Apr–May). This is **consistent with** Sp.Heat being calculated from the firing inputs, so the AFR–Sp.Heat link "
      "may be largely arithmetic. The plant must confirm the formula.\n"
      f"- **Efficiency KPI.**\n"
      f"  - The discovery association with the current KPI (ρ {f3(kpi_lvl[0])}) does **not** replicate (June "
      f"{f3(kpi_lvl[1])}, July {f3(kpi_lvl[2])}).\n"
      f"  - AFR change does not anticipate the KPI change ({kpi_fc_ev}).\n"
      f"  - A small KPI rise follows AFR stops ({f3(kpi_stop, '{:+.1f}')} points over 3 h vs controls), concurrent with "
      "the coal swap.\n"
      f"- **Phase 4 indicator.** The only usable Phase 4 indicator (rising PC coal, `Kiln-I!I|ROC_1H`) fires mostly when "
      f"AFR is falling: its activation rate is {f3(100 * act[1], '{:+.0f}')} percentage points higher in falling-AFR "
      f"hours than in steady-AFR hours (Jun–Jul). This is expected, because PC coal and AFR are swapped. Adding AFR terms "
      f"changes its already-small Jun–Jul lead on the KPI from ρ {f3(att['REPLICATION'][0])} to "
      f"{f3(att['REPLICATION'][1])}.\n")
    A("### Reviewer notes\n")
    A(f"- **Evidence counts.** {n_assoc} primary relationships are ASSOCIATED, of which:\n"
      f"  - {kinds['PROCESS']} are process-response rows;\n"
      f"  - {kinds['CO_MANIPULATION']} are co-manipulation of control inputs;\n"
      f"  - {kinds['SP_HEAT_OR_KPI']} are Sp.Heat / KPI rows.\n"
      f"  {n_weak} more are WEAK ASSOCIATION.\n"
      f"- **August holdout for the ASSOCIATED rows:** CONFIRMED {hold_counts.get('CONFIRMED', 0)}; same direction but "
      f"not significant {hold_counts.get('SAME_DIRECTION_NS', 0)}; opposite direction but not significant "
      f"{hold_counts.get('OPPOSITE_DIRECTION_NS', 0)}; not evaluable {hold_counts.get('NOT_EVALUABLE', 0)}. ASSOCIATED "
      "requires only that August does not significantly *reverse* the direction.\n"
      "- **Confidence** is never HIGH (no fuel properties).\n"
      "- **Matched ON-vs-OFF** comparisons are **MATCHING_NOT_SUPPORTED**, because steady AFR-off running hours are too "
      "rare.\n"
      f"- **Validation.** {vtxt}\n")

    A("## 2. Objective\n")
    A("Describe AFR availability, operating range and firing behaviour, and measure, without causal claims, how AFR "
      "co-varies with load, combustion, thermal behaviour, the Phase 3 efficiency-deterioration KPI and the usable Phase 4 "
      "indicator. The analysis tests stability across months, operating states and load, and lists the plant data needed "
      "for stronger conclusions. Whether alternative fuel *causes* kiln inefficiency is outside what the data can answer.\n")

    A("### Glossary\n")
    A("| Term | Plain meaning |\n|---|---|\n"
      "| AFR \\| Solid (`Kiln-I!K`) | Solid alternative-fuel firing rate, TPH. A control input (set-point / demand); not a "
      "fuel-energy value |\n"
      "| RUNNING bucket | A 10-minute interval in which the kiln is running (Phase 3 proxy); stops and restarts are "
      "excluded |\n"
      "| Partial ρ (rho) | Rank correlation after removing feed, coal / PC firing and time trend; ±0.1 is small, ±0.3 is "
      "moderate |\n"
      "| n_eff | Effective number of independent observations after allowing for autocorrelation |\n"
      "| BH q | p-value adjusted for testing many targets and lags (false-discovery rate) |\n"
      "| LAGGED_LEVEL | AFR level (1-h median) k minutes earlier vs the target now |\n"
      "| FUTURE_CHANGE | AFR change over the last hour vs how the target changes over the next h minutes |\n"
      "| MOMENTUM | AFR and the target both changing in the same hour |\n"
      "| Discovery / replication / holdout | Apr–May chooses lag and direction; Jun–Jul must repeat it; August is a "
      "one-off check |\n"
      "| STABLE_SIGN / SIGN_FLIP | Same direction in Apr–May, June and July / direction changes |\n"
      "| CONFIRMED / SAME_DIRECTION_NS / OPPOSITE_DIRECTION_NS / REVERSED | August same direction and significant / same "
      "direction, not significant / opposite, not significant / opposite and significant |\n"
      "| null_pass | Beats copies of AFR shifted by 2–21 days (which keep AFR's own pattern but lose alignment) |\n"
      "| Transition episode | An AFR start, stop, ramp-up or ramp-down found in the data (not a plant event); compared "
      "with matched times without a transition |\n"
      "| (T+0, T+60] vs [T−60, T) | Median in the hour after the transition minus the median in the hour before |\n"
      "| Duty cycle | Share of valid running minutes with AFR > 0.5 TPH |\n"
      "| KPI:K / KPI:D | Phase 3 efficiency-deterioration KPI (0–100) / its raw deviation score |\n"
      "| TAD / PH | Tertiary air duct / preheater |\n"
      "| Co-manipulation | Two control inputs (AFR, PC coal) changed together by the operator or controller; not a process "
      "response |\n\n")

    A("## 3. Available AFR Data\n")
    A(md_table(inv[["indicator_id", "original_name", "unit", "fuel_category", "control_or_measurement", "coverage_start",
                    "coverage_end", "valid_observations", "missing_fraction", "zero_fraction", "nonzero_fraction",
                    "health_class", "unit_confidence", "analysis_status"]]))
    A("\n- `Kiln-I!K` and `Kiln-I!L` exist only in the Kiln-I workbooks. The tags, names and units are taken from the "
      "Phase 1 inventory; nothing is inferred from a tag name.\n"
      "- All fuel firing tags are treated as **FUEL_CONTROL_INPUT**, following the Phase 4 handoff that fuel firing tags are "
      "set-points. Plant confirmation of set-point versus measurement is pending.\n"
      "- `Kiln-I!K` was reserved by Phase 4 (not analysed there) and is analysed here.\n"
      f"- **LIQUID_AFR_ANALYSIS = INSUFFICIENT_DATA:** {iv.loc['Kiln-I!L', 'exclusion_reason']}\n")

    A("## 4. AFR Data Quality\n")
    A(md_table(dq[dq.afr_signal.eq("Kiln-I!K")][["scope", "minutes", "missing", "invalid", "zero", "nonzero",
                                                   "zero_fraction", "median", "p05", "p25", "p75", "p95", "max",
                                                   "nonzero_median", "robust_variation_mad_nonzero", "p2_flatline_minutes",
                                                   "flatline_periods_ge_60min", "longest_flatline_min", "gaps_ge_10min"]]))
    A(f"\n- **Zero is not missing.** Across the supplied minutes, AFR | Solid has {int(k_all.missing)} missing, "
      f"{int(k_all.invalid)} invalid (Phase 2 flags, {int(k_all.negative)} negative), {int(k_all.zero):,} zero and "
      f"{int(k_all.nonzero):,} non-zero minutes. The accounting identity is checked in G4.\n"
      f"- **Resolution.** Values are integers (integer share {k_all.integer_share:.2f}; {int(k_all.distinct_values)} "
      "distinct values), which is consistent with a set-point or rounded feeder demand. This is not proof of either.\n"
      f"- **Flatlines.** Phase 2 flags {int(k_all.p2_flatline_minutes):,} minutes as SUSPECT_TAG_FLATLINE. Constant integer "
      "firing is plausible for a control input, so the primary series keeps these minutes, flagged. Sensitivity G removes "
      "them and also applies the Phase 3 flatline mask.\n"
      f"- **Duplicates.** {int(k_all.duplicate_timestamp_rows)} duplicate-timestamp rows ({int(k_all.duplicate_conflicts)} "
      "conflicts) are resolved exactly as in Phase 2/3.\n"
      "- **Gaps.** Kiln-I has no September workbook. In May, 2,880 running minutes (two days) have no Kiln-I rows, so AFR "
      "is missing there, not zero.\n")

    A("## 5. Missing Fuel Properties\n")
    A(md_table(inv[inv.analysis_status.eq("NOT_AVAILABLE")][["indicator_id", "analysis_status", "exclusion_reason"]]))
    A("\nCalorific value, moisture, ash, chlorine, RDF / plastic fraction, fuel mix and clinker quality are absent. Phase 5 "
      "therefore computes **no** energy-based AFR metric: no substitution rate, no energy flow per hour, no coal-equivalent "
      "and no fuel-energy share. These are **NOT COMPUTABLE** until the plant data in §22 are supplied (REQUIRED_FUTURE_DATA). "
      "The Sp.Heat derivation check (§11) publishes only R², never the fitted coefficients, because those would amount to "
      "an inferred fuel heat value.\n")

    A("## 6. AFR Operating Distribution\n")
    A(f"![AFR bands]({figs['bands']})\n")
    A("_Bands describe the observed Apr–May distribution. They are **not** a target range, an operating window or a "
      "plant limit._\n")
    A(md_table(bands_df[["band", "lower_tph", "upper_tph", "rule", "occupancy_discovery", "occupancy_jun", "occupancy_jul",
                         "occupancy_aug", "median_feed_discovery_tph", "median_feed_aug_tph", "label", "not_a"]]))
    A(f"\n- **Cuts.** The {BAND_LABEL} cuts are the Apr–May running non-zero P25 = {bands['q_lo']:g} TPH and "
      f"P75 = {bands['q_hi']:g} TPH, frozen for later months. They are empirical bands, **not plant limits**.\n"
      "- **Drift.** The distribution shifts down over the months. HIGH_AFR almost disappears after May, and August sits "
      "mostly in LOW_AFR. A band comparison across months is therefore also a comparison across time, and band contrasts "
      "are reported only as OBSERVED descriptions.\n")

    A("## 7. AFR Firing Patterns\n")
    A(f"![Daily AFR]({figs['daily']})\n")
    A("_`duty_cycle_running` = share of valid running minutes with AFR > 0.5 TPH (missing minutes excluded, never counted "
      "as zero)._\n")
    A(md_table(monthly[["month", "running_minutes", "afr_missing_running_minutes", "duty_cycle_running",
                        "mean_afr_running_tph", "median_nonzero_tph", "p05_nonzero_tph", "p95_nonzero_tph",
                        "max_sustained_1h_tph", "zero_to_nonzero_switches", "on_run_median_min", "off_run_median_min",
                        "off_run_p90_min", "ramp_1h_p05_tph", "ramp_1h_p95_tph", "minute_steps_ge_3tph",
                        "median_feed_running_tph"]]))
    A(f"\n- **Duty cycle.** AFR is on in {monthly.duty_cycle_running.min():.0%}–{monthly.duty_cycle_running.max():.0%} "
      "of valid running minutes every month.\n"
      f"- **Interruptions.** Off periods while running are short (median {monthly.off_run_median_min.min():.0f}–"
      f"{monthly.off_run_median_min.max():.0f} min) and occur {monthly.zero_to_nonzero_switches.min():.0f}–"
      f"{monthly.zero_to_nonzero_switches.max():.0f} times a month. On runs last from hours to days.\n"
      "- **Step changes.** Changes arrive as frequent 1-minute steps of 3 TPH or more, which fits an operator or controller "
      "input.\n"
      "- **Labelling.** All statistics in this section are descriptive and retrospective (non-causal). None is used as a "
      "predictive feature.\n")

    A("## 8. AFR Transition Analysis\n")
    A(md_table(ep.groupby(["afr_transition", "status"]).size().unstack(fill_value=0).reset_index()))
    A(f"\n- **Detection** (10-min running buckets):\n"
      f"  - AFR_START: ≥ 60 min off, then ≥ 30 min on. AFR_STOP is the mirror image.\n"
      f"  - AFR_RAMP_UP / RAMP_DOWN: AFR on throughout, and the 1-h median after minus the 1-h median before is at least "
      f"±{PRIMARY.ramp_tph:g} TPH.\n"
      f"  - A 6-h refractory period applies per type.\n"
      f"- **Eligibility.** An episode is used only if all of the following hold:\n"
      f"  - [T−120, T+180] is entirely running;\n"
      f"  - the 6 h before the window contain no kiln stop or transition;\n"
      f"  - no other AFR transition falls inside the pre-window [T−120, T) (EXCLUDED_PRIOR_TRANSITION);\n"
      f"  - AFR coverage is at least 70 %.\n"
      f"  That leaves **{n_elig} eligible AFR TRANSITION EPISODES**. AFR stops followed by a kiln stop are counted "
      f"separately (EXCLUDED_KILN_STOP_AFTER).\n"
      f"- **Many starts and ramp-ups follow recent interruptions.** Most AFR starts and many ramp-ups are the recovery "
      f"from an interruption that began less than 2 h earlier, so they are excluded. A stricter rule (no other "
      f"transition in the 6 h before the window as well) is tested in sensitivity E. The post window can contain the AFR "
      f"restart itself, which is part of the episode.\n"
      f"- **Controls.** Each episode is compared with up to 3 control times from the same window. Controls have no AFR "
      f"transition within ±6 h, the same AFR pre-state held unchanged, and the nearest 1-h feed level.\n"
      f"- **Tests.** Label-permutation (randomised transition labels) p-values are BH-adjusted. The primary test pools "
      f"Apr–Jul, and August is reported separately.\n"
      f"- **Too few starts.** AFR_START has too few eligible episodes with controls, because steady AFR-off running periods "
      f"are rare. Its rows are INSUFFICIENT DATA.\n")
    A(f"![AFR stop episodes]({figs['stop']})\n")

    excl_comb = "; ".join(f"`{k}` {v}" for k, v in EXCLUDED_TARGETS.items() if k.startswith(("Kiln-I!A", "CBS")))
    for sec, title, fams, extra in (
            (9, "AFR vs Kiln Load", ["LOAD", "FUEL_CO_MANIPULATION"],
             "LOAD rows are not feed-adjusted (feed is the target family). FUEL_CO_MANIPULATION rows relate two control "
             "inputs: they describe co-manipulation, not a process response."),
            (10, "AFR vs Combustion", ["COMBUSTION"], "Excluded combustion tags: " + excl_comb + "."),
            (11, "AFR vs Thermal Behaviour", ["THERMAL"],
             "`Kiln-IA!F` (TA duct temp) is a constant column (Phase 2 hold) and is excluded. No shell temperature or "
             "measured CO₂ exists.")):
        A(f"## {sec}. {title}\n")
        cs = corr_summary(rel, fams)
        sup = cs[cs.evidence.isin(["ASSOCIATED", "WEAK ASSOCIATION"])]
        A("**Correlation relationships labelled ASSOCIATED or WEAK ASSOCIATION** (RUNNING buckets; lag chosen on Apr–May; "
          "Jun–Jul and August at that lag). "
          f"{len(cs) - len(sup)} of {len(cs)} relationships in this family are NOT SUPPORTED / INSUFFICIENT; all rows are "
          f"in `{REL[fams[0]]}`:\n")
        A(md_table(sup))
        A("\n**Transition episodes** (ASSOCIATED / WEAK only). `median_diff` compares the change in the window after the "
          "transition with feed-matched no-transition controls; PC coal and feed can change in the same window:\n")
        A(md_table(episode_summary(rel, fams)))
        A(f"\n{extra}\n")
        if sec == 9:
            A(f"\n- **AFR and load rise and fall together.** In running buckets, AFR is higher when feed, bucket-elevator "
              f"current and clinker TPH are higher, and falls with feed during AFR stops and ramp-downs.\n"
              f"- **PC coal moves opposite to AFR** (level ρ {f3(pc_lvl[0])}), and PC coal is raised after AFR stops.\n"
              f"- **Coal-kiln firing (`Kiln-I!H`)** shows no stable level association.\n"
              f"- **Scope of the evidence.** This shows how the inputs are operated together. It cannot show why they are "
              f"moved (see §14).\n")
        if sec == 10:
            A(f"\n- **O₂ and NOx.** Higher AFR level and rising AFR co-occur with lower preheater-outlet O₂ (level "
              f"{f3(o2_lvl[0])} / {f3(o2_lvl[1])} / {f3(o2_lvl[2])}; 1-h change {f3(o2_mom[0])} / {f3(o2_mom[1])} / "
              f"{f3(o2_mom[2])}) and with falling NOx (`Kiln-I!AC`, 1-h change {f3(nox_mom[0])} / {f3(nox_mom[1])} / "
              f"{f3(nox_mom[2])}).\n"
              f"- **Kiln-inlet O₂ and CO.** Kiln-inlet O₂ (`Kiln-I!X`) and CO show no replicated relationship.\n"
              f"- **After AFR stops.** Preheater O₂ and NOx rise (WEAK ASSOCIATION).\n"
              f"- **What this cannot show.** These are consistent with different combustion conditions when AFR and coal "
              f"are swapped, but they cannot separate fuel type, fuel properties, air settings and load.\n")
        if sec == 11:
            A(f"\n- **Sp.Heat.** F and G co-vary strongly with the AFR level (F {f3(shf[0])} / {f3(shf[1])} / {f3(shf[2])}; "
              f"G {f3(shg[0])} / {f3(shg[1])} / {f3(shg[2])}).\n"
              f"- **Derivation check** (pre-declared, R² only):\n")
            A(md_table(der.reset_index().rename(columns={"target_signal": "Sp.Heat"})))
            A("\n  - Firing rates per ton of feed, **including AFR**, explain most of the variation of both Sp.Heat "
              "definitions. Without the AFR term the fit is poor (R² ≤ 0 in the CSV), although collinearity between the "
              "fuel inputs limits how far this can be read.\n"
              "  - This is **consistent with** the plant Sp.Heat being calculated from the firing inputs, with some heat "
              "factor for AFR. If so, the AFR–Sp.Heat association may be largely arithmetic rather than independent "
              "process evidence. The plant must confirm the formula (§22a Q3).\n"
              "  - Both definitions are kept, and neither is treated as authoritative.\n"
              "- **Temperatures.** Preheater cyclone and TAD temperatures fall after AFR stops and ramp-downs. Cyclone 3/4 "
              "temperatures rise with AFR over the same hour. Burning-zone temperature has no replicated level association.\n")

    A("## 12. AFR vs Efficiency KPI\n")
    A(md_table(corr_summary(rel, ["EFFICIENCY"])))
    A("\n**Transition episodes (KPI / raw deviation D; all rows):**\n")
    A(md_table(episode_summary(rel, ["EFFICIENCY"], only_supported=False)))
    A("\n**AFR before Phase 4 KPI deterioration episodes** (AFR in (T−6 h, T] vs Phase 4's matched control times; the "
      "episodes are synthetic KPI windows, not plant events):\n")
    A(md_table(kpi_prec[["analysis_type", "sample_count", "effect_size", "confidence_interval_low", "confidence_interval_high",
                         "p_value", "adjusted_p_value", "stability", "holdout_result", "evidence"]]))
    A(f"\n- **Current KPI.** The discovery association is positive (ρ {f3(kpi_lvl[0])} at the selected lag) but "
      f"**unstable**: June {f3(kpi_lvl[1])}, July {f3(kpi_lvl[2])}, August {f3(kpi_lvl[3])}. It is WEAK ASSOCIATION at "
      "most. The Apr–May KPI is also the compressed in-sample reference (flagged).\n"
      f"- **Future KPI change.** No anticipation ({kpi_fc_ev}). KPI momentum shows no replicated co-movement.\n"
      f"- **After AFR stops.** The KPI and the raw deviation score D rise after AFR stops (KPI {f3(kpi_stop, '{:+.2f}')} "
      "points over 3 h vs controls). This happens while PC coal is raised and preheater temperatures fall, and the KPI's "
      "efficiency half is Sp.Heat, which is largely a function of the firing rates.\n"
      "- **Before KPI episodes.** No AFR feature (level, change, on-share, number of transitions) differs before Phase 4 "
      "KPI deterioration episodes.\n"
      "- **Conclusion.** No AFR-related efficiency signal is supported beyond the concurrent fuel swap.\n")

    A("## 13. AFR vs Phase 4 Indicators\n")
    A("Only `Kiln-I!I|ROC_1H` has `usable_downstream = True`. Its permitted use, *empirical context feature, discussion / "
      "review only*, is followed: it is analysed as a series that may co-move with AFR, never as established evidence.\n")
    ind = rel[rel.target_family.eq("INDICATOR") & rel.row_role.isin(["SELECTED_LAG", "DESCRIPTIVE", "ATTENUATION_CHECK",
                                                                     "EPISODE_PRIMARY"])
              & rel.window.isin(["DISCOVERY", "REPLICATION", "HOLDOUT_AUG", "POOLED_APR_JUL"])
              & ~rel.analysis_type.str.startswith("BAND")]
    A(md_table(ind[["analysis_type", "lag_minutes", "window", "sample_count", "effect_size", "confidence_interval_low",
                    "confidence_interval_high", "adjusted_p_value", "evidence"]]))
    A(f"\n- **Activation.** The indicator (rising PC coal) is active far more often in hours of falling AFR. The activation "
      f"rate is higher by {f3(100 * act[0], '{:+.0f}')} (Apr–May), {f3(100 * act[1], '{:+.0f}')} (Jun–Jul) and "
      f"{f3(100 * act[2], '{:+.0f}')} (August) percentage points.\n"
      f"- **Lead on the KPI.** With AFR level and change added to the Phase 4 controls, the indicator's partial ρ with the "
      f"60-min future KPI change goes from {f3(att['DISCOVERY'][0])} to {f3(att['DISCOVERY'][1])} (Apr–May), from "
      f"{f3(att['REPLICATION'][0])} to {f3(att['REPLICATION'][1])} (Jun–Jul) and from {f3(att['HOLDOUT_AUG'][0])} to "
      f"{f3(att['HOLDOUT_AUG'][1])} (August).\n"
      "- **Reading.** This is close to expected: the indicator is the PC-coal trend, and PC coal is swapped against AFR. "
      "The indicator's lead was already negligible, and adding AFR changes it little. The observation mainly reinforces "
      "the Phase 4 LOW confidence and the operator-response reading.\n")

    A("## 14. Confounding Analysis\n")
    A("| Confounder | Evidence in the data | Handling | What remains |\n|---|---|---|---|\n"
      f"| Load | AFR level co-varies with feed (ρ {f3(feed_lvl[0])}); AFR stops coincide with feed cuts | Feed level / change "
      "controls; feed-matched episode controls; middle-feed-tercile and LOAD_COINCIDENT sensitivity | Residual load "
      "dynamics |\n"
      f"| Operator intervention | AFR and PC coal move oppositely (ρ {f3(pc_lvl[0])}); coal is raised after AFR stops | "
      "Coal / PC controls in correlations; co-manipulation family | Why AFR is changed is unknown (no operating log) |\n"
      "| Control set-points | All fuel tags are control inputs | Never used as outcomes; set-point vs measurement flagged "
      "pending | Delivered AFR is unknown |\n"
      "| Time drift | AFR level and zero share drift down Apr→Aug; HIGH_AFR vanishes | Elapsed-time control; within-window "
      "statistics; month sensitivity; 72-h matching caliper; circular-shift nulls | Slow process changes |\n"
      f"| Operating state | {k_nrun.zero / k_all.zero:.0%} of AFR = 0 minutes are non-running | RUNNING buckets only; "
      "episode windows fully running; post-restart / pre-stop sensitivity | Proxy state (unconfirmed) |\n"
      "| Missing fuel properties | No CV, moisture, composition | Nothing energy-based computed; confidence capped below "
      "HIGH | AFR mass ≠ AFR heat |\n"
      "| Sp.Heat construction | Sp.Heat largely reproducible from firing rates incl. AFR | Derivation check; KPI rows "
      "flagged | AFR–Sp.Heat / KPI links partly arithmetic |\n")

    A("## 15. Statistical Methodology\n")
    A("- **Unit.** RUNNING 10-min bucket medians (Phase 3/4 masks and state), with no interpolation. The AFR series is "
      "Phase 2-valid, negatives are removed, and it is not flatline-masked.\n"
      "- **Estimator.** Partial Spearman ρ (rank residuals on the ranked controls).\n"
      "  - **Effective sample size:** Bartlett / Pyper–Peterman n_eff with a max lag of 3 days. p-values use Fisher-z with "
      "n_eff.\n"
      "  - **Confidence intervals:** 95 % CI from a 3-day calendar-block bootstrap (1,000 draws).\n"
      "  - **Multiple testing:** BH within each family × analysis type over targets × lags in discovery.\n"
      "- **Types.**\n"
      "  - LAGGED_LEVEL: AFR 1-h level at t−k against the target at t.\n"
      "  - FUTURE_CHANGE: AFR 1-h change at t against the target change over (t, t+h]. This is the only forward-looking "
      "quantity, and it is always the dependent variable.\n"
      "  - MOMENTUM: same-hour changes.\n"
      "  - Lags are 0–360 min.\n"
      "- **Transition episodes.** The effect is the median paired difference, episode minus matched controls, with a "
      "day-block bootstrap CI and a randomised-label permutation p.\n"
      "- **Coal / PC as controls.** Coal / PC firing are controlled for as confounders. Because they are moved together "
      "with AFR by the same operator decision, they may also act as mediators. Controlling for them can then absorb part "
      "of an AFR-linked pattern, which biases the effects toward zero (conservative). Sensitivity C shows the effects "
      "without these controls.\n"
      "- **Matched comparisons.** Greedy 1:1 matching (exact window / feed quintile / speed tercile; |Δfeed| ≤ 2 TPH; "
      "|Δt| ≤ 72 h) with a balance gate.\n"
      "- **Evidence rules (pre-declared).**\n"
      "  - **ASSOCIATED** requires all of the following:\n"
      "    - discovery BH q < 0.05, |ρ| ≥ 0.10, and a CI that excludes 0;\n"
      "    - Jun–Jul with the same sign and p < 0.05;\n"
      "    - August not reversed;\n"
      "    - a pass against the circular-shift null in discovery and replication.\n"
      "  - **WEAK ASSOCIATION:** discovery q < 0.10 and a CI that excludes 0.\n"
      "  - **Episodes:** ASSOCIATED requires a permutation q < 0.05, a CI that excludes 0, the same sign in discovery and "
      "replication, and August not reversed.\n"
      "  - **Confidence:** MEDIUM requires ≥ 4 sensitivity groups evaluated with ≥ 80 % agreeing; otherwise LOW. It is "
      "never HIGH.\n")

    A("## 16. Temporal Validation\n")
    A("- **Windows.** Discovery = April–May, and it chooses the lag and sign. Replication = June (from 06:00) and July. "
      "Holdout = August, reported once. The KPI ends on 2025-08-23, and there is no September data.\n"
      "- **Order.** No window is shuffled. Horizons must end inside their window.\n"
      "- **Frozen fits.** Band cuts, feed terciles and deciles are fitted on discovery only.\n"
      "- **Checks.** G3 re-derives every lag choice from the published discovery profile. It also perturbs all future "
      "AFR and target values and confirms that the features and controls are unchanged.\n")
    A(md_table(prim[prim.row_role.eq("SELECTED_LAG")].groupby(["stability", "holdout_result"]).size()
               .unstack(fill_value=0).reset_index()))

    A("\n## 17. Sensitivity Analysis\n")
    A("A variant agrees when it keeps the primary discovery sign. Groups:\n"
      "- **A:** zero cut 2 / 5 TPH and band tertiles.\n"
      "- **B:** 6 h after a restart / 2 h before a stop excluded.\n"
      "- **C:** middle feed tercile, no feed or fuel controls, load-coincident episodes removed, coal / PC matching.\n"
      "- **D:** fixed 60-min lag and 60-min smoothing.\n"
      "- **E:** response windows (T, T+120] and (T+180, T+360], ramp thresholds 3 / 8 TPH, and no other AFR transition "
      "in the 6 h before the episode window.\n"
      "- **F:** Sp.Heat F↔G and single-definition KPIs.\n"
      "- **G:** data_quality GOOD, Phase 3-masked AFR, AFR without SUSPECT_TAG_FLATLINE minutes.\n"
      "- **H:** each month separately, and the alternative KPI reference.\n\n")
    A(md_table(sens_tab))
    fg = sens[sens.variant.eq("sp_heat_other_definition")]
    A(f"\n- **Sp.Heat F vs G.** Sign agreement at the same lag is {fg.same_sign_as_primary.mean():.0%} of rows. Both "
      "definitions give the same qualitative picture.\n"
      "- **Matching.** Every matched variant (group A zero cuts, group C coal / PC matching) is also "
      "MATCHING_NOT_SUPPORTED.\n\n")
    A("**Matched-control analysis (primary):**\n")
    A(md_table(mstat))

    A("\n## 18. Negative Controls\n")
    A(f"- **Circular shift** of AFR by 2–21 days within discovery and within replication. {null_share:.0%} of selected "
      "correlation relationships beat the 95th percentile of their shifted |ρ| in both windows, and every ASSOCIATED row "
      "does.\n"
      f"- **Misaligned AFR** (shifted 30 days, non-circular): median |ρ| {nc.effect_size.abs().median():.3f} against "
      f"{nc.primary_window_effect.abs().median():.3f} for the aligned series.\n"
      "- **Randomised transition labels:** the episode permutation p-values (§8).\n"
      "- **Null calibration** (7-day shift of every selected relationship): see G5 in §23.\n"
      "- **Interpretation.** Relationships that fail these controls are labelled NOT SUPPORTED or WEAK. Passing them rules "
      "out common trends and autocorrelation as the whole explanation, but it is **not** evidence of causality.\n")

    A("## 19. Key Findings\n")
    A("![Relationships](" + figs["forest"] + ")\n")
    findings = [
        ("F1 AFR co-varies with kiln load (ASSOCIATED)",
         f"AFR 1-h level vs kiln feed: ρ {f3(feed_lvl[0])} (Apr–May), {f3(feed_lvl[1])} (Jun–Jul), {f3(feed_lvl[2])} "
         "(August). Feed falls during AFR stops and ramp-downs.",
         "RUNNING buckets, Kiln-I!K vs Kiln-I!C / N and Kiln-IIIA!M.",
         "Which way the influence runs: is AFR reduced because load is reduced, or the reverse?"),
        ("F2 AFR and PC coal are operated in opposite directions (ASSOCIATED, co-manipulation)",
         f"Level ρ {f3(pc_lvl[0])} / {f3(pc_lvl[1])} / {f3(pc_lvl[2])}; 1-h change ρ {f3(pc_mom[0])} / {f3(pc_mom[1])} / "
         f"{f3(pc_mom[2])}; PC coal {f3(pc_stop, '{:+.1f}')} TPH within 60 min after AFR stops (vs controls).",
         "Two control inputs; stable in every month and in August.",
         "Whether this is an operator rule, a controller loop or a heat-balance compensation (§22a Q1)."),
        ("F3 Preheater O₂ and NOx fall as AFR rises (ASSOCIATED)",
         f"PH-outlet O₂ level ρ {f3(o2_lvl[0])} / {f3(o2_lvl[1])} / {f3(o2_lvl[2])}; NOx 1-h change ρ {f3(nox_mom[0])} / "
         f"{f3(nox_mom[1])} / {f3(nox_mom[2])}.",
         "RUNNING buckets, feed / coal / PC / time adjusted.",
         "Fuel properties, air settings and the simultaneous coal change are not observed."),
        ("F4 Preheater / TAD temperatures fall after AFR stops and ramp-downs (ASSOCIATED, episodes)",
         f"For example cyclone-2 material temperature {f3(cyc2_stop, '{:+.1f}')} °C within 60 min after AFR_STOP vs matched "
         "controls.", f"{n_elig} eligible transition episodes, fully running windows.",
         "The coal increase and feed changes happen in the same window."),
        ("F5 Sp.Heat is closely reproducible from firing rates incl. AFR (ASSOCIATED; consistent with Sp.Heat being "
         "calculated from them; plant to confirm)",
         f"Sp.Heat F / G level ρ {f3(shf[0])} / {f3(shg[0])}; firing-rate-per-feed R² "
         f"{f3(der.loc['Kiln-I!F', 'DISCOVERY'], '{:.2f}')} (F), {f3(der.loc['Kiln-I!G', 'DISCOVERY'], '{:.2f}')} (G).",
         "Kiln-I!F / G vs H, I, K and C.", "The plant formula for Sp.Heat and the heat factor it uses for AFR."),
        ("F6 No supported AFR–efficiency-KPI relationship beyond the fuel swap",
         f"Current-KPI association does not replicate (June {f3(kpi_lvl[1])}, July {f3(kpi_lvl[2])}); future-KPI change "
         f"{kpi_fc_ev}; no AFR precursor before KPI episodes; KPI {f3(kpi_stop, '{:+.2f}')} points after AFR stops.",
         "Phase 3 KPI (in-sample Apr–May, out-of-sample Jun–Aug).",
         "Whether AFR affects deposits / rings: there is no event ground truth and no fuel chemistry."),
        ("F7 The Phase 4 indicator fires mostly when AFR is falling (OBSERVED)",
         f"Activation rate {f3(100 * act[1], '{:+.0f}')} percentage points higher in falling-AFR than steady-AFR hours "
         f"(Jun–Jul); its small KPI lead changes from ρ {f3(att['REPLICATION'][0])} to {f3(att['REPLICATION'][1])} with "
         "AFR controls. Expected, since the indicator is the PC-coal trend and PC coal is swapped against AFR.",
         "Phase 4 official feature values.", "Whether the remaining lead reflects process state or operator response."),
    ]
    for t, obs, data, cannot in findings:
        A(f"### {t}\n")
        A(f"1. **Observed.** {obs}\n"
          "2. **Period.** April–August 2025 (Kiln-I; no September).\n"
          f"3. **Data.** {data}\n"
          "4. **Statistics.** See the tables in §§9–13: partial ρ with n_eff, block-bootstrap CI and BH q, or episode "
          "median differences with permutation q.\n"
          "5. **Replicated?** Jun–Jul, as shown in the stability columns.\n"
          "6. **August holdout?** As shown in the holdout column.\n"
          "7. **Confounders remaining.** Load, operator co-intervention (coal / PC), drift, unmeasured fuel properties.\n"
          f"8. **Cannot be concluded.** A causal role for AFR. Also unresolved: {cannot}\n")

    A("## 20. Evidence Strength\n")
    A(md_table(ev_counts.reset_index()))
    A(f"\n- **ASSOCIATED rows by kind:** {kinds['PROCESS']} process-response, {kinds['CO_MANIPULATION']} "
      f"co-manipulation of control inputs, and {kinds['SP_HEAT_OR_KPI']} Sp.Heat / KPI (largely reproducible from firing "
      "rates). Only the process-response rows can reach MEDIUM confidence.\n"
      f"- **August holdout for ASSOCIATED rows:** {hold_counts}.\n")
    A("\n- **Confidence.** MEDIUM means ASSOCIATED and robust across ≥ 4 sensitivity groups (≥ 80 % agreeing). LOW covers "
      "every other supported row.\n"
      "- **Cap.** HIGH is never assigned: AFR mass flow without fuel properties, and with co-manipulated inputs, cannot "
      "support high-confidence process evidence.\n")

    A("## 21. Limitations\n")
    A("- **Fuel properties.** None (CV, moisture, ash, chlorine, composition). AFR mass ≠ AFR heat.\n"
      "- **Control inputs.** AFR, coal and PC are control inputs moved together, so their separate associations cannot be "
      "isolated from observational data.\n"
      "- **Set-point or measurement?** Unknown for `Kiln-I!K`, and there is no delivered-AFR measurement.\n"
      "- **Liquid AFR.** Unusable (INSUFFICIENT_DATA).\n"
      "- **Matching.** Not supported: steady AFR-off running hours are rare, and HIGH_AFR is concentrated in April–May.\n"
      "- **Coal / PC controls.** Coal / PC controls can act as mediators as well as confounders (§15); effects are likely "
      "biased toward zero.\n"
      "- **Starts.** AFR_START episodes are too few.\n"
      "- **Upstream assumptions.** Sp.Heat is largely reproducible from firing rates. The KPI is the Phase 3 POC score "
      "(in-sample in Apr–May). The operating state is a proxy, and the one-kiln composite assumption is unconfirmed.\n"
      "- **Scope.** Results apply to running periods of April–August 2025 only. There is no deposit, ring or coating ground "
      "truth.\n")

    A("## 22. Required Plant Data\n")
    A(md_table(req[["priority", "item", "why_needed", "enables", "unblocks_finding", "effort", "status"]], max_col=200))
    A("\n### 22a. Questions for the plant\n")
    A("1. **Q1.** Is PC coal firing (`Kiln-I!I`) set manually or by a controller? Is it raised deliberately when AFR drops? "
      "Resolves F2 and F7.\n"
      "2. **Q2.** Which fuel tags are set-points, feeder demands or measured deliveries: AFR `Kiln-I!K`, coal `H`, PC `I`? "
      "Resolves F1, F2 and the FUEL_CONTROL_INPUT classification.\n"
      "3. **Q3.** What are the Sp.Heat F and G formulas, which fuel inputs enter them, and with what heat factor for AFR? "
      "Which definition is authoritative? Resolves F5 and F6.\n"
      "4. **Q4.** Why are AFR stops and ramp-downs initiated (feeder trip, stock-out, process upset, operator choice)? Is "
      "there a log? Resolves F2, F4 and F6.\n"
      "5. **Q5.** Can AFR lot properties (calorific value, moisture, chlorine, composition) be supplied with timestamps? "
      "This enables any energy-based AFR metric.\n"
      "6. **Q6.** Is `Kiln-I!L` *Liquid* a liquid AFR flow? What do the ~4 LPH values and the 10,000 value mean?\n"
      "7. **Q7.** Do the Kiln-I … IIIB folders describe one kiln line (the composite assumption inherited from Phases "
      "3–4)?\n")

    A("\n## 23. Validation Results\n")
    A(md_table(val.groupby(["gate", "result"]).size().unstack(fill_value=0).reset_index()))
    A("\n" + md_table(val[["gate", "check", "check_type", "result", "evidence"]], max_col=160))

    A("\n## 24. Reproducibility\n")
    A("```bash\ncd /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/phase-05-af-analysis/scripts\n"
      "../../.venv/bin/python run_phase5.py --clean      # run twice: G7 compares every key output byte-for-byte\n"
      "../../.venv/bin/python -B -m unittest discover -s ../tests -v\n```\n")
    A("- **Determinism.** Seeds are fixed and derived from SHA-256 (not Python's salted `hash()`). CSVs are rounded to "
      "6 dp. PNGs carry no timestamp metadata, and BLAS runs single-threaded.\n"
      "- **Integrity.** Inputs and code are hashed in `afr_version_manifest.csv`. The source, Phases 1–4 and data/ are "
      "snapshotted before and after every run.\n")

    A("## 25. Phase 6 Handoff\n")
    A("- **Usable outputs:**\n"
      "  - `afr_inventory.csv` and `afr_data_quality.csv`: use `Kiln-I!K` only; Liquid AFR is INSUFFICIENT_DATA.\n"
      "  - `afr_operating_bands.csv`: POC empirical bands, drift-affected.\n"
      "  - `afr_transition_episodes.parquet`: AFR TRANSITION EPISODES, **not** abnormal events.\n"
      "  - `afr_*_relationships.csv`: use `evidence` and `confidence` exactly.\n"
      "  - `afr_data_requirements.csv`.\n"
      "- **AFR as context for abnormal periods.** When Phase 6 studies historical abnormal periods, AFR stops, ramp-downs "
      "and the simultaneous PC-coal increase should be checked as **context**. They co-occur with feed cuts, falling "
      "preheater temperatures and small KPI rises, so an abnormal period that overlaps an AFR transition needs that "
      "context before any process explanation.\n"
      "- **Keep the two concepts apart.** *AFR-associated process behaviour* (this phase) is distinct from *historical "
      "abnormal events* (Phase 6). No AFR relationship here is an event, a limit or a predictor of deposits or rings.\n\n"
      "**Phase 6 has NOT been started.**\n")

    md = "\n".join(L)
    hits = forbidden_hits(md)
    if hits:
        raise SystemExit(f"report wording scan failed: {hits[:5]}")
    (REPORTS / "PHASE_5_ALTERNATIVE_FUEL_ANALYSIS.md").write_text(md)
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark").enable("table").render(md)
    css = (":root{--bg:#fcfcfb;--ink:#0b0b0b;--line:#e0dfda;--head:#f1f0ec;--note:#fdf3ee}"
           "@media (prefers-color-scheme: dark){:root:not([data-theme=light]){--bg:#1a1a19;--ink:#fff;--line:#3a3a37;"
           "--head:#2a2a28;--note:#2a211c}}"
           "body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:var(--ink);"
           "background:var(--bg);line-height:1.45}table{border-collapse:collapse;font-size:12px;margin:8px 0;display:block;"
           "overflow-x:auto}td,th{border:1px solid var(--line);padding:3px 6px;vertical-align:top}th{background:var(--head)}"
           "img{max-width:100%;background:#fcfcfb}blockquote{border-left:4px solid #eb6834;margin:12px 0;padding:4px 12px;"
           "background:var(--note)}code{background:var(--head);padding:0 3px}")
    html = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
            f"initial-scale=1'><title>Phase 5 AFR Analysis</title><style>{css}</style></head><body>{body}</body></html>")
    (REPORTS / "PHASE_5_ALTERNATIVE_FUEL_ANALYSIS.html").write_text(html)
    lg.info("report written (%d chars, %d figures)", len(md), len(figs))


if __name__ == "__main__":
    main()
