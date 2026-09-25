"""Objective O + master report.

Reads every Phase 1 output, derives the data-quality issue register and the
data-readiness assessment, and renders
  reports/PHASE_1_DATA_DISCOVERY_REPORT.md and .html
Outputs: outputs/dq_issue_register.csv, outputs/phase1_data_readiness.csv,
         outputs/expected_parameter_presence.csv
All statements are generated from the CSV evidence; no analytical success is claimed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import pandas as pd

from common import OUT_DIR, REPORT_DIR, SOURCE_ROOT, HEURISTICS, EXPECTED_EQUIPMENT, write_csv, read_out

R = {n: read_out(n) for n in [
    "file_inventory.csv", "workbook_inventory.csv", "sheet_inventory.csv", "header_consistency.csv",
    "column_inventory.csv", "timestamp_inventory.csv", "sampling_changes.csv", "gap_analysis.csv", "gap_events.csv",
    "duplicate_records.csv", "file_overlaps.csv", "data_quality_report.csv", "completeness_by_month.csv",
    "identical_column_pairs.csv", "outlier_profile.csv", "flatline_profile.csv", "flatline_periods.csv",
    "unit_inventory.csv", "unit_consistency_review.csv", "process_tag_inventory.csv", "equipment_data_matrix.csv",
    "equipment_month_coverage.csv", "event_data_inventory.csv", "alternative_fuel_inventory.csv",
    "cross_dataset_alignment.csv", "cross_dataset_identical_signals.csv", "categorical_profile.csv"]}
VAL = OUT_DIR / "pipeline_validation.csv"

# Parameters named in the problem statement (Dalmia Problem Statement.pdf) -> header-text search patterns.
EXPECTED_PARAMS = [  # (name, regex on the column's own header text, optional family filter)
    ("Kiln feed", r"kiln\s+feed|pfister", None),
    ("Kiln speed", r"kiln\s+main\s+drive\s*\|\s*speed", None),
    ("Kiln temperature profile (burning zone / hood / inlet)", r"(?:burning\s+zone|kiln\s+hood|kiln\s+inlet).*temp", None),
    ("Kiln shell temperature", r"shell", None),
    ("Conventional fuel consumption", r"coal|diesel|\bHAG\b|^PC$", ["FUEL"]),
    ("Alternative fuel consumption", r"\bAFR\b|alternat|\bRDF\b|^Liquid$", ["ALTERNATIVE FUEL"]),
    ("RDF / plastic-derived fuel split", r"\bRDF\b|plastic", None),
    ("Fuel mix / substitution rate", r"fuel\s*mix|\bTSR\b|substitution", None),
    ("Fuel calorific value", r"calorific|\bNCV\b|\bGCV\b", None),
    ("Fuel moisture / ash / volatiles / chemistry", r"moisture|\bash\b|volatil|chlor|sulph|sulf", None),
    ("Preheater temperatures", r"temp", ["PREHEATER"]),
    ("Calciner (PC / TAD) temperature / pressure", r"temp|press|draft", ["CALCINER"]),
    ("Preheater / calciner / kiln-inlet draft or pressure", r"draft|press", ["DRAFT / ID FAN", "CALCINER", "PREHEATER"]),
    ("O2 (measured)", r"(?:^|\|\s*)O2$", None),
    ("CO (measured)", r"(?:^|\|\s*)CO$", None),
    ("CO2 (measured)", r"(?:^|\|\s*)CO2$", None),
    ("NOx", r"\bNOX\b", None),
    ("ID fan (explicitly labelled)", r"\bID\s*fan", None),
    ("Preheater fan (speed / draft / power)", r".", ["DRAFT / ID FAN"]),
    ("Heat consumption", r"sp\.?\s?heat|heat\s+consum", None),
    ("Specific fuel consumption (explicit)", r"specific\s+fuel|sp\.?\s?fuel", None),
    ("Clinker production", r"clinker\s+tph", None),
    ("Clinker quality (free lime, LSF, SM, AM, litre weight ...)", r"free\s*lime|\bLSF\b|\bSM\b|\bAM\b|litre|C3S|fcao", None),
    ("Cooler parameters", r".", ["COOLER"]),
    ("Coating / ring / cleaning / shutdown / maintenance history", r"coating|\bring\b|deposit|clean|shutdown|maint", None),
]


def md_table(df: pd.DataFrame, max_rows: int | None = None, max_col: int = 90) -> str:
    if df is None or df.empty:
        return "_None._\n"
    d = df.head(max_rows) if max_rows else df
    d = d.copy().astype(object).where(d.notna(), "")

    def cell(v):
        s = str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return s if len(s) <= max_col else s[:max_col - 1] + "…"
    head = "| " + " | ".join(map(str, d.columns)) + " |\n| " + " | ".join("---" for _ in d.columns) + " |\n"
    body = "".join("| " + " | ".join(cell(v) for v in r) + " |\n" for r in d.itertuples(index=False))
    more = f"\n_{len(df) - len(d)} more rows in the CSV._\n" if max_rows and len(df) > max_rows else ""
    return head + body + more


def fmt_ts(v):
    return "" if pd.isna(v) else str(v)[:16]


def expected_presence():
    ci = R["column_inventory.csv"]
    ci = ci[ci.level == "DATASET"]
    rows = []
    for name, rx, fams in EXPECTED_PARAMS:
        m = ci[ci.original_name.fillna("").str.contains(rx, case=False, regex=True)]
        if fams:
            m = m[m.likely_process_family.isin(fams)]
        rows.append({"expected_parameter (from problem statement)": name,
                     "found": "YES" if len(m) else "NOT FOUND IN SUPPLIED DATA",
                     "matches": "; ".join(f"{r.dataset}!{r.source_column} '{r.original_name}' [{r.detected_unit}]" for r in m.itertuples())[:600],
                     "search_pattern": rx, "family_filter": ",".join(fams or [])})
    out = pd.DataFrame(rows)
    write_csv(out, "expected_parameter_presence.csv")
    return out


def issue_register(ep):
    I = []

    def add(sev, source, location, desc, evidence, impact, action):
        I.append({"issue_id": f"DQ-{len(I) + 1:03d}", "severity": sev, "source": source, "location": location,
                  "description": desc, "evidence": evidence, "impact": impact, "recommended_action": action})

    fi, ev, af = R["file_inventory.csv"], R["event_data_inventory.csv"], R["alternative_fuel_inventory.csv"]
    ts, gp, dq = R["timestamp_inventory.csv"], R["gap_analysis.csv"], R["data_quality_report.csv"]
    # event ground truth
    concl = ev.loc[ev.record_type == "CONCLUSION", "interpretation"].iloc[0]
    if "NOT FOUND" in concl:
        add("CRITICAL", "All datasets", "Entire supplied dataset",
            "No coating / ring / deposit / cleaning / shutdown / maintenance event history in the supplied data",
            f"{(ev.record_type == 'KEYWORD SEARCH').sum()} keyword searches over every header, sheet name, filename and text cell: 0 hits in process data; "
            "hits only in the problem statement / notes (requirements text)",
            "No ground truth to validate abnormal-period detection, risk score or early-warning lead time",
            "Request plant event logs (coating/ring observations, kiln stops with reasons, cleaning and maintenance records) with timestamps")
    # corrupt file
    for r in fi[(fi.is_workbook) & (~fi.readable.astype(bool))].itertuples():
        add("HIGH", r.equipment_from_folder, r.relative_path, "Workbook is truncated / not a valid XLSX container",
            r.zip_diagnostic[:400], f"No {r.month_label_in_filename} data for {r.equipment_from_folder}; this dataset holds all fuel, AFR, "
            "combustion-gas, feed and burning-zone tags", "Request a fresh export of this workbook from the plant")
    # overlap / mislabelled month
    for r in R["file_overlaps.csv"].itertuples():
        add("HIGH", r.dataset, f"{r.file_a} vs {r.file_b}", "Two monthly files cover the same period; filename month is absent from the data",
            f"{r.common_timestamps} common timestamps {fmt_ts(r.overlap_start)}..{fmt_ts(r.overlap_end)}; identical cell rate {r.mean_identical_cell_rate}; {r.interpretation}",
            "The month named in one filename is actually absent from the dataset", "Request the correct month export; exclude the duplicate file from Phase 2")
    overl = set(R["file_overlaps.csv"].file_a) | set(R["file_overlaps.csv"].file_b)
    for r in ts[(ts.level == "FILE") & (ts.filename_month_matches_data == False) & (~ts.source_file.isin(overl))].itertuples():  # noqa: E712
        add("HIGH", r.dataset, r.source_file, "Filename month does not match timestamps in the file",
            f"filename month '{r.month_label_in_filename}', data months {r.months_present_in_data}",
            "Month coverage cannot be inferred from filenames", "Always derive coverage from timestamps (Phase 1 does)")
    for r in ts[(ts.level == "FILE") & (ts.parse_success_pct < 100)].itertuples():
        add("LOW", r.dataset, r.source_file, "Rows inside the data block without a parseable timestamp",
            f"{r.rows_in_table - r.parse_success_count} of {r.rows_in_table} rows; formats {r.timestamp_formats_observed}",
            "Row cannot be placed in time", "Exclude such rows in Phase 2 (they are not interpolated)")
    # missing parameters
    nf = ep[ep.found != "YES"]["expected_parameter (from problem statement)"].tolist()
    add("HIGH", "All datasets", "Parameter coverage", "Parameters named in the problem statement are absent from the supplied data",
        "NOT FOUND: " + "; ".join(nf), "AF-quality analysis, clinker-quality effects and deposit-specific indicators cannot be assessed",
        "Request fuel lab data (CV, moisture, ash/chlorine), RDF/plastic split, clinker quality, kiln shell scanner data")
    # equipment semantics
    al = R["cross_dataset_alignment.csv"]
    al = al[al.colB_comparison == "Kiln MD vs Kiln MD"]
    titles = R["sheet_inventory.csv"].dropna(subset=["title_text"]).groupby("equipment_from_folder").title_text.first().to_dict()
    add("HIGH", "Kiln-IA, Kiln-II, Kiln-III, Kiln-IIIA, Kiln-IIIB", "Folder names vs sheet content",
        "Folder names suggest separate kilns, but content evidence suggests SCADA display pages of one kiln system",
        f"Sheet titles {titles}; column 'Kiln MD' identical across datasets (min identical rate {al.colB_identical_rate.min():.5f} over {len(al)} pairs); "
        "Kiln-I 'Sp.Heat' (G) and Kiln-IIIA 'Sp.Heat Consumtion' (X) identical at 100%",
        "Wrong equipment mapping would mislead cross-kiln comparisons", "Plant to confirm whether all folders describe one kiln line")
    # gaps: windows shared by many datasets, then dataset-specific large gaps
    ge = R["gap_events.csv"]
    ge = ge[(ge.level == "DATASET") & (ge.long_gap)]
    shared = ge.groupby(["gap_start_after", "gap_end_before"]).dataset.nunique().reset_index()
    shared = shared[shared.dataset >= 5]
    shared_keys = set(zip(shared.gap_start_after, shared.gap_end_before))
    for r in shared.itertuples():
        add("LOW", f"{r.dataset} datasets", f"{fmt_ts(r.gap_start_after)} → {fmt_ts(r.gap_end_before)}",
            "Missing window common to many datasets", f"same gap present in {r.dataset} datasets",
            "Short common hole in all logs", "Mask; request from historian if needed")
    own = ge[~ge.apply(lambda x: (x.gap_start_after, x.gap_end_before) in shared_keys, axis=1)]
    for dsn, grp in own.groupby("dataset"):
        top = grp.sort_values("interval_min", ascending=False)
        if len(top) > 20:
            desc = f"{len(grp)} consecutive hourly gaps (see sampling change issue)"
            sev = "INFO"
        else:
            desc = f"{len(grp)} dataset-specific long gap(s) (>= {HEURISTICS['long_gap_minutes']} min)"
            sev = "MEDIUM" if top.interval_min.max() >= 360 else "LOW"
        spans = "; ".join(f"{fmt_ts(a)}→{fmt_ts(b)} ({int(m)} min)" for a, b, m in
                          top[["gap_start_after", "gap_end_before", "interval_min"]].head(4).itertuples(index=False))
        add(sev, dsn, "Timestamp column A", desc, f"largest {top.interval_min.max():.0f} min; total {top.missing_duration_min.sum() / 60:.1f} h; {spans}",
            "Breaks continuity for lagged / rolling-window analysis", "Treat as missing windows; do not interpolate across them")
    sc = R["sampling_changes.csv"]
    for (dsn, f), grp in sc[sc.day_mode_interval_min != 1].groupby(["dataset", "source_file"]):
        add("MEDIUM", dsn, f, "Sampling interval changes within the file",
            f"hourly (mode 60 min) sampling on {len(grp)} days: {grp.day.min()} .. {grp.day.max()}",
            "Mixed resolution inside one dataset", "Resample or restrict to 1-minute periods")
    # duplicates
    fg = gp[(gp.level == "FILE") & (gp.duplicate_timestamp_rows > 0)]
    if len(fg):
        dr = R["duplicate_records.csv"]
        ev_ = "; ".join(f"{r.source.split('/')[-1]}: {int(r.duplicate_timestamp_rows)} dup rows ({int(r.duplicate_ts_rows_conflicting_values)} with conflicting values)"
                        for r in fg.itertuples())
        add("MEDIUM", "; ".join(sorted(fg.dataset.unique())), "Timestamp column A", "Duplicate timestamps",
            ev_[:700], "Ambiguous value for a minute; inflates row counts", "De-duplicate deterministically in Phase 2 and log the rule")
    # consecutive identical rows
    ci = gp[(gp.level == "FILE") & (gp.consecutive_rows_all_values_identical_pct > 5)]
    if len(ci):
        add("MEDIUM", "; ".join(sorted(ci.dataset.unique())), "All columns",
            "Large share of rows repeat the previous row exactly (every column)",
            "; ".join(f"{r.source.split('/')[-1]}: {r.consecutive_rows_all_values_identical_pct:.1f}%" for r in ci.itertuples())[:700],
            "Effective resolution may be coarser than 1 minute (historian repeat / hold)", "Confirm historian export settings (interpolation / step)")
    # synchronised freeze
    fp = R["flatline_periods.csv"]
    nz = fp[~fp.is_zero_value.astype(bool)]
    sync = nz.groupby(["start", "end"]).agg(tags=("tag", "size"), datasets=("dataset", "nunique")).reset_index()
    sync = sync[(sync.tags >= 20)]
    for r in sync.itertuples():
        add("MEDIUM", f"{r.datasets} datasets", f"{fmt_ts(r.start)} → {fmt_ts(r.end)}",
            "Synchronised flatline across many unrelated tags (suspected data hold / frozen export)",
            f"{r.tags} tags in {r.datasets} datasets hold a constant non-zero value over the same window",
            "Frozen values would look like perfectly stable operation", "Mask this window as suspected frozen data pending plant confirmation")
    # sentinels
    s = dq[dq.sentinel_candidate_rows > 0].sort_values("sentinel_candidate_rows", ascending=False)
    add("MEDIUM", "; ".join(sorted(s.dataset.unique())), f"{len(s)} columns", "Sentinel / placeholder value candidates (mainly 99999)",
        "; ".join(f"{r.dataset}!{r.source_column} {r.sentinel_candidate_values}" for r in s.head(8).itertuples()),
        "Distorts statistics if treated as measurements", "Validate meaning of 99999 / 9999 with plant; mask in Phase 2")
    txt = dq[dq.text_in_numeric_rows > 0]
    for r in txt.itertuples():
        add("MEDIUM", r.dataset, f"column {r.source_column} '{r.original_name}'", "Text embedded in numeric column",
            f"{r.text_in_numeric_rows} rows; values {r.top_text_values}", "Column typed as mixed", "Confirm meaning of the text (calculation error code?)")
    for r in dq[dq.temperature_at_or_below_minus273_rows > 0].itertuples():
        add("LOW", r.dataset, f"column {r.source_column} '{r.original_name}'", "Temperature values at or below -273 Deg.C",
            f"{r.temperature_at_or_below_minus273_rows} rows", "Physically impossible reading; likely placeholder", "Mask as sentinel candidate")
    # unit review
    ur = R["unit_consistency_review.csv"]
    for chk, grp in ur.groupby("check"):
        sev = "MEDIUM" if chk in ("LABEL vs UNIT", "PERCENT RANGE") else "LOW"
        add(sev, "; ".join(sorted(set(grp.dataset))), f"{len(grp)} columns", f"UNIT CONSISTENCY REVIEW REQUIRED - {chk}",
            " || ".join(f"{r.dataset}!{r.source_column} {r.evidence}" for r in grp.head(6).itertuples())[:800],
            "Unit or label may be wrong; values may be misinterpreted", "Confirm with plant instrumentation list; do not convert in Phase 2 without approval")
    # identical columns
    for r in R["identical_column_pairs.csv"].itertuples():
        add("MEDIUM", r.dataset, f"{r.column_a} '{r.name_a}' vs {r.column_b} '{r.name_b}'",
            "Two differently-positioned columns carry identical values", f"identical rate {r.identical_value_rate} over {r.rows_compared} rows",
            "One column may be mis-mapped / duplicated in the export", "Confirm tag mapping")
    # completeness
    red = dq[dq.completeness_class == "RED"]
    add("MEDIUM", "; ".join(sorted(red.dataset.unique())), f"{len(red)} columns", "Columns with high missingness (RED, POC heuristic <70% present)",
        "; ".join(f"{r.dataset}!{r.source_column} '{r.original_name}' {r.null_percentage:.1f}% null" for r in red.itertuples())[:800],
        "Limited or no usable signal", "Exclude or treat as sparse in Phase 2")
    amb = dq[dq.completeness_class == "AMBER"]
    add("INFO", "Most datasets", f"{len(amb)} columns AMBER",
        "Moderate missingness is concentrated in periods where column B ('Kiln MD') is 0 or missing",
        f"median share of missing rows falling in col-B=0/missing periods: {dq.pct_of_missing_rows_where_colB_is_0_or_missing.median():.1f}%",
        "Missingness is structured, not random", "Phase 2 to confirm meaning of col B before using it as a run-state filter")
    const = R["flatline_profile.csv"]
    const = const[const.health_class.str.startswith("CONSTANT", na=False)]
    add("LOW", "; ".join(sorted(const.dataset.unique())), f"{len(const)} columns", "Constant-valued columns",
        "; ".join(f"{r.dataset}!{r.tag} '{r.original_name}'={r.most_common_value:g}" for r in const.itertuples())[:800],
        "No information content in the supplied period", "Exclude from modelling; confirm whether instrument is standby / unused")
    # workbook-level
    si = R["sheet_inventory.csv"]
    for r in si[si.sheet_kind == "NON_PROCESS_CONTENT"].itertuples():
        add("MEDIUM", r.equipment_from_folder, f"{r.workbook} ! {r.sheet_name}", "Workbook contains a non-process sheet",
            str(r.notes)[:300], "Potential personal data inside plant data package", "Remove from shared copies; do not ingest")
    add("LOW", "All datasets", "Header rows", "Group headers are not merged cells; assignment of a group label to neighbouring columns is positional",
        "0 merged ranges in all readable workbooks; e.g. Kiln-I E1='Coal Firing' above E2='Sp.Power'",
        "Some column meanings are ambiguous", "Keep original_name; confirm ambiguous columns (see process_tag_inventory confidence)")
    add("LOW", "All datasets", "Timestamp column A", "Timestamps carry no timezone and no header",
        "format dd.mm.yyyy HH:MM stored as text in unlabelled column A", "Alignment with external logs needs timezone confirmation",
        "Confirm plant/historian timezone")
    em = R["equipment_data_matrix.csv"]
    miss = em[em.available == "No"]
    for r in miss.itertuples():
        add("LOW", r.equipment, "Source directory", "Expected folder / dataset not present", str(r.notes), "Possible missing dataset", "Ask plant whether folder 07 exists")
    add("INFO", "All datasets", "Sheet names", "Sheet names are truncated to 31 characters and do not identify the equipment",
        "e.g. Kiln-IA workbook sheet is named '02.Process Log Sheet for Kiln-I'", "Sheet name cannot be used for equipment mapping",
        "Use folder + content evidence")
    out = pd.DataFrame(I)
    write_csv(out, "dq_issue_register.csv")
    return out


def readiness(ep):
    af = R["alternative_fuel_inventory.csv"]
    afr = af[(af.parameter == "alternative fuel") & (af.found == "YES")]
    af_ev = "; ".join(f"{r.source}!{r.source_column} '{r.original_name}' [{r.unit}] {r.completeness}" for r in afr.itertuples())
    rows = [
        ("Normal baseline", "1-min multivariate data for kiln, preheater, calciner, cooler, combustion tags; Apr–Sep 2025 (Kiln-I Apr–Aug)",
         "PARTIAL", "Plant definition of 'normal' operation; meaning of col B 'Kiln MD' (run-state?); masking rules for sentinels, frozen windows, gaps"),
        ("Efficiency KPI", "Sp.Heat (kcal/kg clinker), Sp.Power, fuel firing rates (TPH), Clinker TPH, kiln feed present",
         "PARTIAL", "Plant-approved KPI definition; fuel calorific value (NOT FOUND); clinker quality (NOT FOUND); validation of extreme Sp.Heat values"),
        ("Leading indicators", "Time-aligned 1-min series across datasets (identical timestamps, 'Kiln MD' identical across datasets)",
         "PARTIAL", "A labelled deterioration / event target (NOT FOUND) - only exploratory, unvalidated analysis possible"),
        ("AF vs behaviour", af_ev or "no AF tag", "PARTIAL",
         "RDF/plastic split, AF calorific value, moisture, composition (all NOT FOUND); AFR Liquid mostly empty; Kiln-I September unreadable"),
        ("Historical abnormal periods", "Process signals allow unsupervised detection of unusual periods",
         "PARTIAL", "EVENT GROUND TRUTH NOT FOUND IN SUPPLIED DATA - detected periods cannot be confirmed"),
        ("Risk score", "Candidate input tags exist (fuel, AF, combustion, draft, temperatures, Sp.Heat)",
         "PARTIAL", "No coating/ring/deposit ground truth for calibration or validation; kiln shell temperature NOT FOUND"),
        ("Early warning", "Continuous 1-min history available",
         "BLOCKED", "Event timestamps required to measure lead time and false-alarm rate (NOT FOUND); plant-approved action logic required"),
    ]
    out = pd.DataFrame(rows, columns=["future_objective", "data_evidence", "readiness", "missing_information"])
    out["assessment_type"] = "DATA READINESS ONLY - no analytical result claimed"
    write_csv(out, "phase1_data_readiness.csv")
    return out


def build_md(ep, issues, ready):
    fi, wb, si = R["file_inventory.csv"], R["workbook_inventory.csv"], R["sheet_inventory.csv"]
    ts, gp, dq = R["timestamp_inventory.csv"], R["gap_analysis.csv"], R["data_quality_report.csv"]
    em, af, ev = R["equipment_data_matrix.csv"], R["alternative_fuel_inventory.csv"], R["event_data_inventory.csv"]
    pt, ur, ol, fl = R["process_tag_inventory.csv"], R["unit_consistency_review.csv"], R["outlier_profile.csv"], R["flatline_profile.csv"]
    val = pd.read_csv(VAL) if VAL.exists() else pd.DataFrame()
    src = fi[fi.scope == "SOURCE_DATA"]
    proc = si[si.sheet_kind == "PROCESS_LOG_TABLE"]
    dsl = ts[ts.level == "DATASET"]
    total_rows = int(proc.data_row_count.sum())
    uniq_minutes = int(dsl.unique_timestamps.sum())
    L = []
    A = L.append
    A("# Phase 1 — Data Discovery Report\n")
    A("**Dalmia Cement, Ariyalur — Kiln Efficiency & Deposit Build-Up POC**\n")
    A(f"Generated {datetime.now().isoformat(timespec='seconds')} by `scripts/generate_report.py` from the CSVs in `outputs/`. "
      f"Source data root (read-only): `{SOURCE_ROOT}`.\n")
    A("> Phase 1 is observational. It establishes data facts only. It does not build baselines, KPIs, models or risk scores, "
      "and it gives no operational or control recommendations.\n")

    # 1
    A("## 1. Executive Summary\n")
    n_ok = int(src.readable.astype(bool).sum())
    A(f"- **{len(src)} source files** in {src.parent_folder.nunique()} equipment folders, all `.xlsx` "
      f"({src.file_size_bytes.sum() / 1e6:.1f} MB). **{n_ok} readable, {len(src) - n_ok} corrupt** "
      f"(`{src.loc[~src.readable.astype(bool), 'relative_path'].str.split('/').str[-1].tolist()}`). "
      f"{len(fi) - len(src)} supporting files beside the data root: problem statement, notes, and an archive identical to the source files.")
    A(f"- **{len(proc)} process-log sheets** (one per readable workbook) plus {int((si.sheet_kind != 'PROCESS_LOG_TABLE').sum())} non-process sheet. "
      f"**{total_rows:,} data rows** in total. Of these, {uniq_minutes:,} are unique dataset-minutes; the difference is duplicate timestamps, including "
      "the Kiln-IIIA 'April' file, which repeats May. Each sheet has 2–3 header rows (group / parameter / unit) and a text timestamp "
      "in unlabelled column A. There are no formulas, merged cells or hidden rows.")
    A(f"- **Coverage:** {fmt_ts(dsl.earliest_timestamp.min())} → {fmt_ts(dsl.latest_timestamp.max())}, observed at a **1-minute** interval "
      "(mode interval = 1 min in every file). Kiln-I has no September (corrupt file). Kiln-IIIA has no April: the 'April' file contains May data.")
    A(f"- **{len(pt)} parameter columns** across 10 datasets. Kiln-I holds all fuel, AFR, combustion-gas, feed and burning-zone tags. "
      "The other folders hold hood/TAD/PC, cyclones, cooler fans, cooler vent/ESP/clinker/Sp.Heat, CBS, and cooler-drive tags.")
    A("- **AF data:** only `AFR | Solid` (TPH) and `Liquid` (LPH, mostly empty) in Kiln-I. "
      "**RDF split, plastic fraction, calorific value, moisture and fuel mix are NOT FOUND IN SUPPLIED DATA.**")
    A("- **EVENT GROUND TRUTH NOT FOUND IN SUPPLIED DATA.** There are no coating, ring, deposit, cleaning, shutdown or maintenance records.")
    sev = issues.severity.value_counts().reindex(["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]).fillna(0).astype(int)
    A(f"- **Data-quality issues:** {len(issues)} ({', '.join(f'{k} {v}' for k, v in sev.items())}). See section 7 and `outputs/dq_issue_register.csv`.")
    A(f"- **Readiness:** " + ", ".join(f"{r.future_objective}: **{r.readiness}**" for r in ready.itertuples()) + ".\n")

    # 2
    A("## 2. Dataset Inventory\n")
    A("### 2.1 Files\n")
    f2 = src.assign(file=src.filename, MB=src.file_size_mb, month=src.month_label_in_filename)[
        ["equipment_from_folder", "file", "MB", "readable", "processing_status"]]
    A(md_table(f2))
    A("Supporting files (outside the data root, not process data):\n")
    A(md_table(fi[fi.scope == "SUPPORTING"][["relative_path", "file_size_mb", "file_type", "zip_diagnostic"]]))
    A(f"No duplicate files by SHA-256 inside the data root (max duplicate group size {int(src.duplicate_group_size.max())}). "
      f"No temp, backup, hidden or empty files. `Dalmia.zip` holds byte-identical copies of the 60 workbooks plus the problem statement "
      "(`outputs/archive_member_crosscheck.csv`). The Kiln-I (Sep) copy inside the archive is corrupt in the same way.\n")
    A("### 2.2 Workbooks and sheets\n")
    s2 = si.assign(wb=si.workbook.str.split("/").str[-1])[["wb", "sheet_name", "sheet_kind", "row_count_physical", "column_count_physical",
                                                          "header_rows", "unit_row", "data_start_row", "data_row_count", "title_text"]]
    A(md_table(s2))
    A("Structure facts (from raw OOXML inspection):\n")
    A(f"- Formula cells: {int(wb.formula_cells_total.sum())}. Merged ranges: {int(wb.merged_ranges_total.sum())}. Hidden sheets: none. "
      f"Hidden rows/columns: {int(si.hidden_rows.fillna(0).sum())}/{int(si.hidden_columns.fillna(0).sum())}. All values are static.")
    A("- Header layout: an optional title row (e.g. `KILN PAGE-2`), a group row, a parameter row and a unit row. Group labels sit only in the first "
      "column of their group and are not merged. `group_header_ffill_candidate` in the inventories is therefore an inference and is labelled as one.")
    hc = R["header_consistency.csv"]
    A(f"- Header signatures are identical in every monthly file of each dataset ({int(hc.consistent_across_months.sum())}/{len(hc)} columns consistent).")
    A("- `Kiln-I (Aug).xlsx` has an extra sheet `Sheet1` that is not plant data (a personal travel itinerary). Its contents are not reproduced.\n")

    # 3
    A("## 3. Date Coverage\n")
    cov = R["equipment_month_coverage.csv"].pivot(index="equipment", columns="month", values="coverage_pct").reset_index()
    A("Share of minutes present per calendar month (unique timestamps / minutes in month, %):\n")
    A(md_table(cov))
    A(md_table(dsl.assign(first=dsl.earliest_timestamp.map(fmt_ts), last=dsl.latest_timestamp.map(fmt_ts))[
        ["dataset", "first", "last", "rows_in_table", "unique_timestamps", "duplicate_timestamp_rows", "coverage_pct_of_span"]]))

    # 4
    A("## 4. Sampling Frequency\n")
    A("Frequency is computed from the observed timestamps, never assumed. The plant logging interval is NOT DOCUMENTED IN SOURCE.\n")
    A(md_table(dsl[["dataset", "observed_frequency", "median_interval_min", "mode_interval_min", "min_interval_min", "max_interval_min", "irregularity_pct"]]))
    fl_ = ts[ts.level == "FILE"]
    A(f"At file level, {int((fl_.mode_interval_min == 1).sum())}/{len(fl_)} files have a 1-minute mode interval, "
      f"with irregularity ≤ {fl_.irregularity_pct.max():.3f}% of intervals.")
    sc = R["sampling_changes.csv"]
    hr = sc[sc.day_mode_interval_min != 1]
    if len(hr):
        A(f" **Sampling change:** {hr.dataset.iloc[0]} is **hourly** from {hr.day.min()} to {hr.day.max()} "
          f"(`{hr.source_file.iloc[0].split('/')[-1]}`), then 1-minute.")
    A("\n")

    # 5
    A("## 5. Process Parameter Inventory\n")
    A("The full canonical list is in `outputs/process_tag_inventory.csv` (dataset level) and `outputs/column_inventory.csv` "
      "(file and dataset level, including statistics). `original_name` is the verbatim header text. `normalized_name` is an added key only.\n")
    fam = pt.pivot_table(index="dataset", columns="likely_process_family", values="source_column", aggfunc="count", fill_value=0).reset_index()
    A("Process-family classification (evidence-based keyword rules on header text; see `scripts/taxonomy.py`):\n")
    A(md_table(fam))
    A(f"Confidence: {pt.confidence.value_counts().to_dict()}. Abbreviations (PC, TAD, PH, SFM, HAG, 'Kiln MD', CBS, BH, RAL, FK) are **not defined in the source**. "
      "Where a family depends on reading one of them, confidence is MEDIUM or LOW and the evidence column says so.\n")
    A("Expected parameters from the problem statement, checked against the header text:\n")
    A(md_table(ep[["expected_parameter (from problem statement)", "found", "matches"]], max_col=160))
    A("\nAll parameter columns:\n")
    A(md_table(pt[["dataset", "source_column", "original_name", "detected_unit", "likely_process_family", "confidence", "null_percentage", "completeness_class", "health_class"]]))

    # 6
    A("## 6. Equipment Coverage\n")
    A(md_table(em[["equipment", "available", "files_found", "files_readable", "data_rows", "first_timestamp", "last_timestamp", "months_missing", "parameter_columns", "sheet_title_in_source", "notes"]]))
    A("\n**Interpretation caution.** 'Available' means a readable dataset exists in that folder. It does not mean a complete set of process "
      "parameters exists for a physical kiln with that name. The sheet titles (`Kiln Page-1A`, `KILN PAGE-2`, `KILN PAGE-3`, `KILN PAGE-3A`, `KILN PAGE-3B`), "
      "the identical `Kiln MD` column across all datasets, and identical signals across folders (section 11) are consistent with these folders being "
      "**SCADA display pages of a single kiln system**, not separate kilns. This is NOT CONFIRMED and needs plant confirmation.\n")

    # 7
    A("## 7. Data Quality\n")
    A(f"Completeness classes are a **POC DATA-QUALITY HEURISTIC** (GREEN ≥ {HEURISTICS['completeness_green_min_pct']}% present, AMBER ≥ "
      f"{HEURISTICS['completeness_amber_min_pct']}%, RED below). They are not plant engineering limits. Missing means an empty cell or a whitespace-only string.\n")
    A(md_table(dq.pivot_table(index="dataset", columns="completeness_class", values="source_column", aggfunc="count", fill_value=0).reset_index()))
    A("\n### 7.1 Gaps and duplicates\n")
    A(md_table(gp[gp.level == "DATASET"][["dataset", "timestamp_range_start", "timestamp_range_end", "expected_interval_min", "number_of_gaps",
                                          "number_of_long_gaps", "largest_gap_min", "total_missing_duration_hours", "duplicate_timestamp_rows"]], max_col=40))
    A("\n### 7.2 Outliers (SUSPECTED OUTLIER — data-quality scan, not anomaly detection)\n")
    o3 = ol[ol.method == "IQR_3.0"].sort_values("percentage_of_points", ascending=False)
    A(f"{ol.method.nunique()} methods (sentinel match, IQR 1.5/3.0, MAD robust z > {HEURISTICS['mad_z']}, p0.1/p99.9 tails, first-difference spikes). "
      f"Full results: `outputs/outlier_profile.csv` ({len(ol)} rows). Columns with the most IQR-3.0 suspects:\n")
    A(md_table(o3[["dataset", "column", "original_name", "unit", "number_of_suspect_points", "percentage_of_points", "example_values", "pct_suspects_where_colB_is_0_or_missing"]], max_rows=15))
    A("A statistically unusual value is not necessarily bad data. Many suspects fall in periods where column B is 0 (see last column). "
      "Those may be stops or start-ups, which Phase 1 does not label.\n")
    A("### 7.3 Flatlines / sensor health\n")
    A(f"Flatline = ≥ {HEURISTICS['flatline_min_samples']} consecutive identical samples (POC heuristic). Health class counts: {fl.health_class.value_counts().to_dict()}.\n")
    A(md_table(fl.sort_values("longest_nonzero_flatline_min", ascending=False)[["dataset", "tag", "original_name", "health_class", "number_of_flatline_periods",
                                                                                "longest_flatline_min", "longest_nonzero_flatline_min", "percentage_affected"]], max_rows=15))
    A("\n### 7.4 Issue register\n")
    A(md_table(issues, max_col=260))

    # 8
    A("## 8. Unit Analysis\n")
    ui = R["unit_inventory.csv"]
    A(f"Every parameter column has an explicit unit in the source unit row (confidence HIGH, source cell recorded in `outputs/unit_inventory.csv`). "
      f"Unit strings found: {sorted(ui.original_unit.unique().tolist())}. No unit conversion was applied.\n")
    A("**UNIT CONSISTENCY REVIEW REQUIRED:**\n")
    A(md_table(ur[["check", "dataset", "source_column", "original_name", "unit", "evidence"]], max_col=140))

    # 9
    A("## 9. Alternative Fuel Data Availability\n")
    A(md_table(af[["parameter", "found", "source", "source_column", "original_name", "unit", "time_range", "completeness", "notes"]], max_col=70))
    A("\nCoverage: Kiln-I holds all fuel and AF tags. Other datasets: not found. Kiln-I September is unavailable (corrupt workbook).\n")

    # 10
    A("## 10. Event Data Availability\n")
    A("```text\nHistorical ring/deposit/coating ground truth : NOT FOUND IN SUPPLIED DATA\nCleaning / maintenance records               : NOT FOUND IN SUPPLIED DATA\n"
      "Shutdown / stoppage records                  : NOT FOUND IN SUPPLIED DATA\nEVENT GROUND TRUTH NOT FOUND IN SUPPLIED DATA\n```\n")
    A(md_table(ev[ev.record_type != "KEYWORD SEARCH"][["record_type", "search_term", "interpretation"]], max_col=400))
    kw = ev[ev.record_type == "KEYWORD SEARCH"]
    A(f"\nKeywords searched ({len(kw)}): {', '.join(kw.search_term)}. They were searched in filenames, sheet names, every header cell and every distinct text "
      "cell of every readable process sheet. Hits appear only in the supporting documents, which contain requirements text, not records.\n")

    # 11
    A("## 11. Cross-Dataset Compatibility\n")
    al = R["cross_dataset_alignment.csv"]
    A(f"All readable datasets share the same timestamp grid (text `dd.mm.yyyy HH:MM`, 1 min). Pairwise timestamp Jaccard ranges from "
      f"{al.timestamp_jaccard.min():.3f} to {al.timestamp_jaccard.max():.3f}. It is lower only where a dataset lacks months (Kiln-I Sep, Kiln-IIIA Apr) or has hourly sampling (CBS-II June).\n")
    A(md_table(al[["dataset_a", "dataset_b", "common_timestamps", "timestamp_jaccard", "colB_identical_rate", "colB_comparison"]], max_col=60))
    A("\nSignals identical across datasets (possible duplicated exports of the same tag):\n")
    A(md_table(R["cross_dataset_identical_signals.csv"]))
    A("\nAlignment is technically possible on column A, after de-duplicating timestamps and masking gaps. It must not bridge the missing months.\n")

    # 12
    A("## 12. Data Risks\n")
    for r in issues[issues.severity.isin(["CRITICAL", "HIGH"])].itertuples():
        A(f"- **{r.issue_id} [{r.severity}] {r.description}.** {r.impact}.")
    A("")

    # 13
    A("## 13. Data Readiness\n")
    A("DATA READINESS ONLY. No objective has been attempted, and none is claimed to be achievable.\n")
    A(md_table(ready[["future_objective", "data_evidence", "readiness", "missing_information"]], max_col=300))

    # 14
    A("\n## 14. Recommended Phase 2 Inputs\n")
    A("Phase 2 should consume, from `phase-01-data-discovery/outputs/`:\n")
    for f, why in [
        ("process_tag_inventory.csv", "tag list with original names, units, families, confidence, completeness and health class"),
        ("column_inventory.csv", "per-file and per-dataset statistics and datatypes"),
        ("timestamp_inventory.csv / gap_events.csv / duplicate_records.csv", "time grid, gaps to mask, duplicates to resolve"),
        ("file_overlaps.csv / file_inventory.csv", "files to exclude (Kiln-IIIA April duplicate) and unreadable files (Kiln-I Sep)"),
        ("flatline_periods.csv", "suspected frozen windows (e.g. 2025-05-06 11:50–21:50) to mask"),
        ("outlier_profile.csv / data_quality_report.csv", "sentinel candidates (99999, 9999, -273, 'Error 6') to mask pending validation"),
        ("unit_consistency_review.csv", "columns whose unit or label must be confirmed before use"),
        ("equipment_data_matrix.csv / equipment_month_coverage.csv", "which datasets and months exist"),
        ("event_data_inventory.csv / alternative_fuel_inventory.csv", "confirmed absence of event ground truth and AF-quality data"),
        ("dq_issue_register.csv / phase1_data_readiness.csv", "open issues and readiness constraints"),
    ]:
        A(f"- `{f}`: {why}.")
    A("\nPhase 2 should also get these answers from the plant: whether the folders are pages of one kiln; the meaning of `Kiln MD` and its 0 value; "
      "the meaning of 99999; a replacement Kiln-I September export; the Kiln-IIIA April export; event logs; and fuel/clinker lab data.\n")

    # validation
    A("## Appendix A — Validation\n")
    if len(val):
        A(md_table(val, max_col=200))
    A("\n## Appendix B — Reproducibility\n")
    A("```bash\ncd phase-01-data-discovery/scripts\npython3 run_phase1.py --clean   # deletes outputs/, reports/, cache/ and regenerates everything\n```\n")
    A(f"POC DATA-QUALITY HEURISTICS used: `{json.dumps(HEURISTICS)}`. They are not plant limits.\n")
    return "\n".join(L)


HTML_CSS = """
:root{--bg:#fff;--fg:#1d2330;--muted:#5b6475;--line:#d9dde5;--head:#f3f5f8;--accent:#0b5cad}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e6e9ef;--muted:#a3abb9;--line:#2c323c;--head:#1c2027;--accent:#6aa9ff}}
body{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:0 auto;padding:16px}
h1,h2,h3{line-height:1.25}h2{border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:2em}
table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%;font-size:12px;margin:8px 0}
th,td{border:1px solid var(--line);padding:3px 6px;vertical-align:top;text-align:left}
th{background:var(--head);position:sticky;top:0}
code,pre{background:var(--head);border-radius:4px}pre{padding:8px;overflow-x:auto}code{padding:0 3px}
blockquote{border-left:3px solid var(--accent);margin:0;padding:4px 12px;color:var(--muted)}
"""


def main():
    ep = expected_presence()
    issues = issue_register(ep)
    ready = readiness(ep)
    md = build_md(ep, issues, ready)
    (REPORT_DIR / "PHASE_1_DATA_DISCOVERY_REPORT.md").write_text(md, encoding="utf-8")
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark").enable("table").render(md)
    html = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Phase 1 Data Discovery</title><style>{HTML_CSS}</style></head><body>{body}</body></html>")
    (REPORT_DIR / "PHASE_1_DATA_DISCOVERY_REPORT.html").write_text(html, encoding="utf-8")
    print("  wrote reports/PHASE_1_DATA_DISCOVERY_REPORT.md / .html")


if __name__ == "__main__":
    main()
