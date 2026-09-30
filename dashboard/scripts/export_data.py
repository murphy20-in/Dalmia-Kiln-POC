"""Export frozen Phase 1-9 outputs to static JSON for the pitch dashboard.

Read-only on every input. Deterministic: two runs give byte-identical files.
Run from the repo root:  .venv/bin/python -B dashboard/scripts/export_data.py
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "public" / "data"

P1 = "phase-01-data-discovery/outputs/"
P2 = "phase-02-baseline/outputs/"
P3 = "phase-03-efficiency-kpi/outputs/"
P5 = "phase-05-af-analysis/outputs/"
P6 = "phase-06-abnormal-events/outputs/"
P7 = "phase-07-risk-score/outputs/"
P8 = "phase-08-early-warning/outputs/"
P9 = "phase-09-api/outputs/"
BS = "reports/BUILD_STATUS.md"

FAMILIES = ["EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"]
ZONE = {"LOW": "N", "ELEVATED": "W", "HIGH": "A"}
MONTHS = {"JUN": "2025-06", "JUL": "2025-07", "AUG": "2025-08"}


def rd(path: str) -> pd.DataFrame:
    p = ROOT / path
    return pd.read_parquet(p) if path.endswith(".parquet") else pd.read_csv(p)


def r1(x) -> float | None:
    return None if pd.isna(x) else round(float(x), 1)


def r3(x) -> float | None:
    return None if pd.isna(x) else round(float(x), 3)


def ts(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M")


def write(name: str, obj: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    (OUT / name).write_text(text + "\n", encoding="utf-8")
    print(f"{name}: {len(text) / 1024:.0f} KB")


# ---------------------------------------------------------------- shared frames
scores = rd(P7 + "risk_scores.parquet")
op = scores[scores.operational].sort_values("timestamp").reset_index(drop=True)
summary7 = rd(P7 + "risk_score_summary.csv").set_index("slice")
bands = rd(P7 + "risk_score_bands.csv").set_index("band")
EDGE_W = round(float(bands.loc["ELEVATED", "lower_edge"]), 1)
EDGE_A = round(float(bands.loc["HIGH", "lower_edge"]), 1)
episodes = rd(P6 + "abnormal_episodes.parquet")
final = episodes[episodes.in_final_set].sort_values("start_time").reset_index(drop=True)
kpi = rd(P3 + "efficiency_deterioration_kpi.parquet")


def zone_shares() -> list[dict]:
    return [
        {"month": m, "normal": r3(summary7.loc[s, "share_low"]), "watch": r3(summary7.loc[s, "share_elevated"]),
         "warning": r3(summary7.loc[s, "share_ge_high"]), "median": r1(summary7.loc[s, "median"])}
        for s, m in MONTHS.items()
    ]


def kpi_monthly() -> list[dict]:
    oos = kpi[kpi.kpi_reference_state == "OUT_OF_SAMPLE"]
    med = oos.groupby(oos.timestamp.dt.strftime("%Y-%m")).efficiency_deterioration_kpi.median()
    return [{"month": m, "median": r1(med[m])} for m in MONTHS.values()]


# ---------------------------------------------------------------- summary.json
def export_summary() -> None:
    sheets = rd(P1 + "sheet_inventory.csv")
    issues = rd(P1 + "dq_issue_register.csv")
    conf = rd(P2 + "baseline_confidence.csv")
    conf = conf[conf.population == "BASELINE_RUNNING"]
    state = rd(P2 + "operating_state_analysis.csv").set_index("item")
    sev = final.severity_class.value_counts()
    fams = final.deviating_families.str.split(";")
    obj = {
        "_sources": {
            "rows": P1 + "sheet_inventory.csv (sum data_row_count)",
            "datasets": P1 + "sheet_inventory.csv (distinct equipment_from_folder)",
            "tags": P1 + "process_tag_inventory.csv (row count)",
            "tagsHighConfidence": P2 + "baseline_confidence.csv (BASELINE_RUNNING, HIGH)",
            "runningMinutes": P2 + "operating_state_analysis.csv (RUNNING_PROXY)",
            "issues": P1 + "dq_issue_register.csv (severity counts)",
            "periods": P6 + "abnormal_episodes.parquet (in_final_set)",
            "kpiMonthly": P3 + "efficiency_deterioration_kpi.parquet (OUT_OF_SAMPLE monthly median)",
            "zoneShares": P7 + "risk_score_summary.csv (share_low / share_elevated / share_ge_high)",
            "bandEdges": P7 + "risk_score_bands.csv (ELEVATED, HIGH lower_edge)",
            "operationalBuckets": P7 + "risk_scores.parquet (operational == True)",
            "kpiTags": BS + " §8 (33 tags)",
        },
        "rows": int(sheets.data_row_count.sum()),
        "datasets": int(sheets.equipment_from_folder.nunique()),
        "tags": len(rd(P1 + "process_tag_inventory.csv")),
        "tagsHighConfidence": int((conf.baseline_confidence == "HIGH").sum()),
        "runningMinutes": int(state.loc["RUNNING_PROXY", "value"]),
        "kpiTags": 33,  # manual copy from BUILD_STATUS §8; re-check if Phase 3 changes
        "issues": {s.lower(): int(n) for s, n in issues.severity.value_counts().sort_index().items()},
        "issuesTotal": len(issues),
        "periods": {"total": len(final), "high": int(sev.get("HIGH", 0)), "moderate": int(sev.get("MODERATE", 0)),
                    "low": int(sev.get("LOW", 0)), "multiSystem": int((fams.str.len() > 1).sum())},
        "kpiMonthly": kpi_monthly(),
        "zoneShares": zone_shares(),
        "bandEdges": {"watch": EDGE_W, "warning": EDGE_A},
        "operationalBuckets": len(op),
    }
    write("summary.json", obj)


# ---------------------------------------------------------------- console.json
def export_console() -> None:
    comp = rd(P7 + "risk_score_components.parquet")
    comp = comp[comp.operational].pivot(index="timestamp", columns="family", values="family_contribution").fillna(0.0)
    reasons = rd(P7 + "risk_score_reasons.parquet")
    drivers = reasons[reasons.reason_type == "SCORE_DRIVER"].sort_values(["timestamp", "driver_rank"])
    top3 = drivers.groupby("timestamp").reason_code.apply(lambda s: list(s)[:3])
    flags = reasons[reasons.reason_code.isin(["SUSPECT_ANALYSER_AMBIENT_O2", "POST_RESTART_SETTLING"])]
    flags = flags.sort_values(["timestamp", "reason_code"]).groupby("timestamp").reason_code.apply(list)
    rows = []
    for r in op.itertuples():
        c = comp.loc[r.timestamp]
        f = [r1(c.get(fam, 0.0)) for fam in FAMILIES] + [r1(c.get("CONCURRENCE", 0.0) + c.get("PERSISTENCE", 0.0))]
        rows.append([ts(r.timestamp), r1(r.risk_score), ZONE[r.risk_band], r1(r.kpi_value), f,
                     top3.get(r.timestamp, []), flags.get(r.timestamp, [])])
    # Gaps: Jun-Aug 10-min buckets that are not operational, merged into spans.
    grid = scores[(scores.timestamp >= op.timestamp.min()) & (scores.timestamp <= op.timestamp.max())]
    grid = grid.sort_values("timestamp")
    assert grid.timestamp.diff().dropna().eq(pd.Timedelta(minutes=10)).all(), "score grid is not a contiguous 10-min grid"
    gap = ~grid.operational
    span_id = (gap != gap.shift()).cumsum()
    gaps = [[ts(g.timestamp.iloc[0]), ts(g.timestamp.iloc[-1]), "stopped" if (g.risk_status == "STOPPED").mean() >= 0.5 else "nodata"]
            for _, g in grid[gap].groupby(span_id[gap])]
    obj = {
        "_sources": {
            "rows[t,s,z,k]": P7 + "risk_scores.parquet (timestamp, risk_score, risk_band, kpi_value; operational == True)",
            "rows[f]": P7 + "risk_score_components.parquet (family_contribution; last = CONCURRENCE + PERSISTENCE)",
            "rows[r]": P7 + "risk_score_reasons.parquet (SCORE_DRIVER by driver_rank, top 3)",
            "rows[x]": P7 + "risk_score_reasons.parquet (SUSPECT_ANALYSER_AMBIENT_O2, POST_RESTART_SETTLING)",
            "gaps": P7 + "risk_scores.parquet (operational == False spans; risk_status STOPPED → stopped)",
            "bandEdges": P7 + "risk_score_bands.csv",
        },
        "columns": ["t", "s", "z", "k", "f", "r", "x"],
        "families": FAMILIES + ["BREADTH_PERSISTENCE"],
        "stepMinutes": 10,
        "bandEdges": {"watch": EDGE_W, "warning": EDGE_A},
        "start": ts(op.timestamp.min()),
        "end": ts(op.timestamp.max()),
        "rows": rows,
        "gaps": gaps,
    }
    write("console.json", obj)


# ---------------------------------------------------------------- efficiency.json
def export_efficiency() -> None:
    o2 = rd(P9 + "o2_excluded_scores.parquet")
    day = op.groupby(op.timestamp.dt.strftime("%Y-%m-%d"))
    o2day = o2.groupby(o2.timestamp.dt.strftime("%Y-%m-%d")).o2_excluded_risk_score.median()
    daily = [{"d": d, "s": r1(g.risk_score.median()), "o2": r1(o2day.get(d)), "k": r1(g.kpi_value.median()), "n": len(g)}
             for d, g in day]
    o2m = o2.groupby(o2.timestamp.dt.strftime("%Y-%m")).o2_excluded_risk_score.median()
    cols = ["efficiency", "combustion", "thermal", "draft_pressure", "stability", "concurrence", "persistence"]
    drivers = [{"month": m, **{c: r3(summary7.loc[s, "share_points_" + c]) for c in cols}} for s, m in MONTHS.items()]
    obj = {
        "_sources": {
            "daily.s": P7 + "risk_scores.parquet (daily median of risk_score, operational)",
            "daily.o2": P9 + "o2_excluded_scores.parquet (daily median; sensitivity analysis, own reference)",
            "daily.k": P7 + "risk_scores.parquet (daily median kpi_value)",
            "zoneShares": P7 + "risk_score_summary.csv",
            "o2MonthlyMedian": P9 + "o2_excluded_scores.parquet (monthly median)",
            "drivers": P7 + "risk_score_summary.csv (share_points_*)",
            "kpiMonthly": P3 + "efficiency_deterioration_kpi.parquet",
            "periods": P6 + "abnormal_episodes.parquet (in_final_set)",
        },
        "bandEdges": {"watch": EDGE_W, "warning": EDGE_A},
        "daily": daily,
        "zoneShares": zone_shares(),
        "o2MonthlyMedian": [{"month": m, "median": r1(o2m[m])} for m in MONTHS.values()],
        "drivers": drivers,
        "kpiMonthly": kpi_monthly(),
        "periods": [{"id": p.episode_id, "start": ts(p.start_time), "end": ts(p.end_time), "severity": p.severity_class}
                    for p in final.itertuples()],
    }
    write("efficiency.json", obj)


# ---------------------------------------------------------------- periods.json
def export_periods() -> None:
    s = scores.set_index("timestamp")
    out = []
    for n, p in enumerate(final.itertuples(), start=1):
        win = s.loc[p.onset_time - pd.Timedelta(hours=24): p.end_time + pd.Timedelta(hours=24)]
        series = [[ts(t), r1(v.risk_score) if v.operational else None] for t, v in win.iterrows()]
        out.append({
            "id": p.episode_id, "n": n, "start": ts(p.start_time), "end": ts(p.end_time), "onset": ts(p.onset_time),
            "durationMin": int(p.duration_minutes), "severity": p.severity_class, "severityScore": r3(p.severity_score), "dominant": p.dominant_family,
            "systems": p.deviating_families.split(";"), "load": p.load_context, "feedChange": r1(p.feed_change_vs_pre2h),
            "robustness": r3(p.robustness_score), "peakKpi": r1(p.peak_kpi),
            "deviation": {f: r3(getattr(p, ("draft" if f == "DRAFT_PRESSURE" else f.lower()) + "_deviation")) for f in FAMILIES},
            "series": series,
        })
    obj = {
        "_sources": {
            "periods": P6 + "abnormal_episodes.parquet (in_final_set; start_time, end_time, onset_time, duration_minutes, severity_class, severity_score, "
                            "dominant_family, deviating_families, load_context, feed_change_vs_pre2h, robustness_score, *_deviation)",
            "series": P7 + "risk_scores.parquet (risk_score, onset − 24 h to end + 24 h; null when not operational)",
        },
        "bandEdges": {"watch": EDGE_W, "warning": EDGE_A},
        "periods": out,
    }
    write("periods.json", obj)


# ---------------------------------------------------------------- afr.json
# (key, relationships file, target_original_name, analysis_type, REPLICATION or episode window_compared)
CARDS = [
    ("feed", "load", "Kiln Feed | Pfister", "LAGGED_LEVEL", "REPLICATION"),
    ("coal", "load", "PC", "EPISODE_AFR_STOP", "(T+0, T+60] vs [T-60, T)"),
    ("o2", "combustion", "PH Outlet | O2", "LAGGED_LEVEL", "REPLICATION"),
    ("nox", "combustion", "NOX", "MOMENTUM", "REPLICATION"),
    ("tad", "thermal", "TAD Damper I/LTemp", "EPISODE_AFR_RAMP_DOWN", "(T+60, T+180] vs [T-60, T)"),
    ("cyclone1", "thermal", "Cyclone 1 | Mat.Temp", "EPISODE_AFR_STOP", "(T+0, T+60] vs [T-60, T)"),
    ("hood", "thermal", "Kiln Hood | Temp", "EPISODE_AFR_RAMP_DOWN", "(T+60, T+180] vs [T-60, T)"),
]


def strength(evidence: str, confidence: str, holdout: str) -> str:
    """Consistency of a link (Phase 5 evidence label), never its size. Phase 5 never assigned HIGH confidence."""
    if evidence == "ASSOCIATED" and confidence == "MEDIUM" and holdout == "CONFIRMED":
        return "Consistent"
    return "Lower confidence" if evidence == "ASSOCIATED" else "Emerging"


def export_afr() -> None:
    files = {re.fullmatch(r"afr_([a-z]+)_relationships\.csv", Path(f).name).group(1): pd.read_csv(f)
             for f in sorted(glob.glob(str(ROOT / P5 / "afr_*_relationships.csv")))}
    allr = pd.concat(files.values(), ignore_index=True)
    assoc = allr[(allr.evidence == "ASSOCIATED") & allr.window.isin(["REPLICATION", "POOLED_APR_JUL"])]
    cards = []
    for key, src, target, analysis, where in CARDS:
        d = files[src]
        m = (d.target_original_name == target) & (d.analysis_type == analysis)
        m &= ((d.window == where) & (d.evidence == "ASSOCIATED")) if where == "REPLICATION" else (d.window_compared == where) & (d.row_role == "EPISODE_PRIMARY")
        rows = d[m]
        assert len(rows) == 1, (key, len(rows))
        row = rows.iloc[0]
        cards.append({"key": key, "effect": r3(row.effect_size), "unit": row.target_unit if isinstance(row.target_unit, str) else "",
                      "metric": "rho" if "rho" in row.effect_metric else "delta",
                      "strength": strength(row.evidence, row.confidence, row.holdout_result),
                      "augustConfirmed": bool(row.holdout_result == "CONFIRMED")})
    monthly = rd(P5 + "afr_monthly_summary.csv")
    coal = next(c for c in cards if c["key"] == "coal")
    obj = {
        "_sources": {
            "monthly": P5 + "afr_monthly_summary.csv (mean_afr_running_tph, median_feed_running_tph)",
            "cards": P5 + "afr_{load,combustion,thermal}_relationships.csv (effect_size, evidence, confidence, holdout_result)",
            "associated": P5 + "afr_*_relationships.csv (evidence ASSOCIATED; REPLICATION + POOLED_APR_JUL rows)",
            "coalStepTph": P5 + "afr_load_relationships.csv (PC, EPISODE_AFR_STOP, (T+0, T+60])",
            "feedRho": BS + " §10 (+0.35 / +0.34 / +0.50)",
        },
        "monthly": [{"month": r.month, "afr": r1(r.mean_afr_running_tph), "feed": r1(r.median_feed_running_tph)} for r in monthly.itertuples()],
        "cards": cards,
        "associated": len(assoc),
        "augustConfirmed": int((assoc.holdout_result == "CONFIRMED").sum()),
        "coalStepTph": round(coal["effect"]),
        "feedRho": {"aprMay": 0.35, "junJul": 0.34, "aug": 0.50},  # manual copy from BUILD_STATUS §10
    }
    assert obj["associated"] == 43 and obj["augustConfirmed"] == 27, obj
    write("afr.json", obj)


# ---------------------------------------------------------------- data.json
def export_data() -> None:
    cov = rd(P1 + "equipment_month_coverage.csv")
    issues = rd(P1 + "dq_issue_register.csv").set_index("issue_id")
    ev = issues.evidence.astype(str)
    dup_rows = len(rd(P1 + "duplicate_records.csv"))
    frozen_tags = int(re.match(r"(\d+) tags", ev["DQ-016"]).group(1))
    sentinel_cols = int(re.match(r"(\d+) columns", str(issues.loc["DQ-017", "location"])).group(1))
    assert frozen_tags == 122 and dup_rows == 4135, (frozen_tags, dup_rows)
    examples = [
        {"severity": "HIGH", "title": "September kiln workbook was truncated",
         "body": "The main kiln file for September could not be opened (three-quarters of it was empty bytes), so September is left out rather than guessed.", "src": "DQ-002"},
        {"severity": "HIGH", "title": "An April file was a copy of May",
         "body": "One April workbook repeated May's readings minute for minute. It was caught and excluded before any modelling.", "src": "DQ-003"},
        {"severity": "MEDIUM", "title": f"A 10-hour frozen window across {frozen_tags} tags",
         "body": "On 6 May, 11:50–21:50, many unrelated readings stopped changing at once, a sign of a held export. Those minutes are masked.", "src": "DQ-016"},
        {"severity": "MEDIUM", "title": f"'99999' placeholder values in {sentinel_cols} columns",
         "body": "Historian placeholders were treated as missing, not as real readings, so they never distort the baseline.", "src": "DQ-017"},
        {"severity": "MEDIUM", "title": f"{dup_rows:,} duplicate timestamps",
         "body": "Rows that repeat the same minute were resolved before analysis so each minute counts once.", "src": "DQ-014"},
    ]
    asks = [
        {"priority": 1, "title": "Kiln event logs, Apr–Sep 2025", "detail": "Timestamped coating, ring, cleaning, maintenance and stoppage records, with reasons.",
         "unlocks": "Matching abnormal periods to real events, and calibrating early warning (Stage 2)."},
        {"priority": 1, "title": "Kiln-inlet O₂ analyser calibration and purge schedule", "detail": "When the analyser was purged, calibrated or reading ambient air.",
         "unlocks": "Separating real process drift from instrument effects in the August rise."},
        {"priority": 1, "title": "Alternative-fuel quality logs", "detail": "Calorific value, moisture, RDF / plastic split, chlorine and ash, with sample times.",
         "unlocks": "Fuel-quality → deposit-risk modelling."},
        {"priority": 2, "title": "Alternative-fuel operating log", "detail": "Why AFR feed was started, stopped or ramped (feeder trips, stock-outs, operator decisions).",
         "unlocks": "Separating operator actions from process responses."},
        {"priority": 2, "title": "Missing workbooks", "detail": "A re-export of the main kiln log for September 2025 and of the April 2025 file that duplicated May.",
         "unlocks": "A full six months of history instead of five."},
        {"priority": 2, "title": "Tag and definition confirmations", "detail": "Whether the ten folders are pages of one kiln line, what 'Kiln MD' means, and which specific-heat tag is authoritative.",
         "unlocks": "A firmer baseline and efficiency index."},
    ]
    obj = {
        "_sources": {
            "coverage": P1 + "equipment_month_coverage.csv (coverage_pct)",
            "issues": P1 + "dq_issue_register.csv (severity counts)",
            "examples": P1 + "dq_issue_register.csv (" + ", ".join(e["src"] for e in examples) + "); duplicates: " + P1 + "duplicate_records.csv",
            "asks": BS + " §4, §13; " + P5 + "afr_data_requirements.csv",
        },
        "months": sorted(cov.month.unique().tolist()),
        "coverage": [{"dataset": d, "pct": [r1(v) for v in g.sort_values("month").coverage_pct]} for d, g in cov.groupby("equipment", sort=True)],
        "issues": {s.lower(): int(n) for s, n in issues.severity.value_counts().sort_index().items()},
        "examples": examples,
        "asks": asks,
    }
    write("data.json", obj)


# ---------------------------------------------------------------- validation.json
def export_validation() -> None:
    summ = rd(P8 + "early_warning_summary.csv")
    pe = summ[(summ.section == "PRIMARY_ENDPOINT") & (summ.variant == "PRIMARY")].set_index("metric").value
    o2 = rd(P8 + "early_warning_o2_sensitivity.csv").set_index("metric")
    nc = rd(P8 + "early_warning_negative_controls.csv")
    nc = nc[nc.score_variant == "PRIMARY"].set_index("control_id")
    cens = final.onset_censored
    obj = {
        "_sources": {
            "primary": P8 + "early_warning_summary.csv (PRIMARY_ENDPOINT, PRIMARY: pe, ci_low, ci_high, p_value)",
            "censored": P6 + "abnormal_episodes.parquet (onset_censored, in_final_set)",
            "o2RankCorrelation": P8 + "early_warning_o2_sensitivity.csv",
            "negativeControls": P8 + "early_warning_negative_controls.csv (PRIMARY)",
            "revalidateAt": BS + " §13 (≥ 8 evaluable labelled events)",
            "checks": BS + " §7–§13 (validation gate counts)",
            "versions": P7 + "risk_scores.parquet (score_version); " + P6 + "abnormal_episodes.parquet (method_version)",
        },
        "primary": {"pe": r3(float(pe["pe"])), "ciLow": r3(float(pe["ci_low"])), "ciHigh": r3(float(pe["ci_high"])),
                    "p": r3(float(pe["p_value"])), "supported": False},
        "periods": len(final), "censored": int(cens.sum()), "uncensored": int((~cens).sum()),
        "o2RankCorrelation": r3(float(o2.loc["score_rank_correlation_operational_buckets", "o2_excluded"])),
        "negativeControls": {k: {"p": r3(nc.loc[k, "p_value"])} for k in ["NC1", "NC2"]},
        "futurePerturbationIdentical": bool(str(nc.loc["NC5", "status"]).startswith("PASS")),
        "revalidateAt": 8,
        # Manual copies from BUILD_STATUS §7–§13 (validation gate counts, revalidation rule, reference window).
        "checks": {"phase2": 123, "phase3": 55, "phase4": 61, "phase5": 56, "phase6": 47, "phase7": 48, "phase8": 43},
        "versions": {"index": str(op.score_version.iloc[0]), "periods": str(final.method_version.iloc[0]), "reference": "2025-04-01..2025-05-31"},
    }
    write("validation.json", obj)


if __name__ == "__main__":
    assert len(op) == 9557 and len(final) == 12
    assert set(op.risk_band) <= set(ZONE), set(op.risk_band)
    export_summary()
    export_console()
    export_efficiency()
    export_periods()
    export_afr()
    export_data()
    export_validation()
