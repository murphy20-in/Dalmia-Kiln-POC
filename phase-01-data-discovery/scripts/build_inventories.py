"""Objectives J, K, L, M, N + cross-dataset compatibility.

Builds, from the source and the earlier Phase 1 outputs:
  unit_inventory.csv, unit_consistency_review.csv, process_tag_inventory.csv,
  equipment_data_matrix.csv, equipment_month_coverage.csv, event_data_inventory.csv,
  alternative_fuel_inventory.csv, cross_dataset_alignment.csv, cross_dataset_identical_signals.csv
Only evidence present in the supplied files is used.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from common import (SOURCE_ROOT, SUPPORTING_ROOT, EXPECTED_EQUIPMENT, HEURISTICS, dataset_frames, load_dataset,
                    source_xlsx_files, load_workbook_cached, rel, equipment_from_folder, folder_index,
                    write_csv, read_out, jdump)
from taxonomy import unit_key

EVENT_TERMS = ["coating", "ring", "deposit", "build-up", "buildup", "cleaning", "clean", "shutdown", "shut down",
               "stoppage", "stop", "trip", "maintenance", "breakdown", "outage", "disturbance", "abnormal",
               "jam", "blockage", "choke", "kiln off", "event", "alarm", "remark", "comment"]
AF_TERMS = {
    "alternative fuel": r"alternat|\bAFR\b|\bAF\b",
    "RDF": r"\bRDF\b|refuse",
    "plastic-derived fuel": r"plastic",
    "conventional fuel (coal/petcoke/diesel)": r"coal|pet\s*coke|diesel|\boil\b|\bHAG\b",
    "fuel mix / substitution rate": r"fuel\s*mix|\bTSR\b|substitution|thermal\s+substitution",
    "calorific value": r"calorific|\bNCV\b|\bGCV\b|\bCV\b|kcal/kg\s*fuel",
    "moisture": r"moisture|\bH2O\b|\bwet\b",
    "fuel quantity / rate": r"\bfiring\b|\bsolid\b|\bliquid\b|\bflow\b",
    "fuel percentage": r"fuel\s*%|%\s*fuel|AF\s*%|AFR\s*%",
    "specific heat consumption (related)": r"sp\.?\s?heat|heat\s+consum",
}


def month_range(ts_min, ts_max):
    return [str(p) for p in pd.period_range(ts_min, ts_max, freq="M")]


def main():
    inv = read_out("column_inventory.csv")
    dsinv = inv[inv.level == "DATASET"].copy()
    dq = read_out("data_quality_report.csv")
    fl = read_out("flatline_profile.csv")
    ol = read_out("outlier_profile.csv")
    tsi = read_out("timestamp_inventory.csv")
    fi = read_out("file_inventory.csv")
    sheets = read_out("sheet_inventory.csv")

    frames = {}
    for eq, tables in dataset_frames().items():
        frames[eq] = load_dataset(tables)

    # ------------------------------------------------------------------ units
    urows, review = [], []
    for eq, (df, meta) in frames.items():
        month = df.ts.dt.to_period("M").astype(str)
        for c, m in meta.items():
            med = df.groupby(month)[c].median().dropna()
            nz = med[med.abs() > 1e-9].abs()
            ratio = float(nz.max() / nz.min()) if len(nz) >= 2 else None
            row = dsinv[(dsinv.dataset == eq) & (dsinv.source_column == c)].iloc[0]
            drift = ratio is not None and ratio > HEURISTICS["unit_magnitude_ratio"]
            urows.append({
                "dataset": eq, "source_column": c, "original_name": m.original_name,
                "original_unit": m.unit_raw if m.unit_raw else "UNKNOWN",
                "source": f"{row.source_sheet} ! {m.unit_cell} (unit header row, identical in every monthly file)" if m.unit_cell else "no unit cell",
                "confidence": "HIGH (explicit unit text in source header row)" if m.unit_raw else "UNKNOWN",
                "measurement_type_from_unit": row.inferred_category,
                "monthly_median_values": jdump({k: round(float(v), 4) for k, v in med.items()}),
                "max_to_min_monthly_median_ratio": None if ratio is None else round(ratio, 3),
                "label_unit_review_required": bool(row.unit_label_review_required),
                "label_unit_review_reason": row.unit_label_review_reason if isinstance(row.unit_label_review_reason, str) else "",
                "magnitude_drift_flag": drift,
                "unit_consistency_status": ("UNIT CONSISTENCY REVIEW REQUIRED"
                                            if (row.unit_label_review_required or drift) else "NO INCONSISTENCY DETECTED"),
            })
            if row.unit_label_review_required:
                review.append({"check": "LABEL vs UNIT", "dataset": eq, "source_column": c, "original_name": m.original_name,
                               "unit": m.unit_raw, "evidence": row.unit_label_review_reason,
                               "status": "UNIT CONSISTENCY REVIEW REQUIRED"})
            if drift:
                review.append({"check": "MONTH-TO-MONTH MAGNITUDE (median ratio > 10x)", "dataset": eq, "source_column": c,
                               "original_name": m.original_name, "unit": m.unit_raw,
                               "evidence": f"monthly medians {jdump({k: round(float(v), 3) for k, v in med.items()})}",
                               "status": "UNIT CONSISTENCY REVIEW REQUIRED (may also be an operating-regime change)"})
            u = unit_key(m.unit_raw)
            x = df[c].dropna()
            if u == "%" and len(x) and ((x < 0) | (x > 100)).mean() > 0.01:
                review.append({"check": "PERCENT RANGE", "dataset": eq, "source_column": c, "original_name": m.original_name,
                               "unit": m.unit_raw,
                               "evidence": f"{((x < 0) | (x > 100)).mean() * 100:.1f}% of values outside 0-100; min={x.min():.4g}, max={x.max():.4g}",
                               "status": "UNIT CONSISTENCY REVIEW REQUIRED"})
    un = pd.DataFrame(urows)
    # same parameter label in several datasets with different unit spellings
    un["_label"] = un.original_name.str.split("|").str[-1].str.strip().str.lower()
    for lab, g in un.groupby("_label"):
        if g.dataset.nunique() > 1 and g.original_unit.nunique() > 1:
            review.append({"check": "SAME LABEL, DIFFERENT UNIT TEXT ACROSS DATASETS", "dataset": jdump(sorted(g.dataset.unique())),
                           "source_column": jdump(list(g.source_column)), "original_name": lab, "unit": jdump(sorted(g.original_unit.unique())),
                           "evidence": "unit strings differ (may be spelling variants only)", "status": "UNIT CONSISTENCY REVIEW REQUIRED"})
    write_csv(un.drop(columns="_label"), "unit_inventory.csv")
    write_csv(pd.DataFrame(review), "unit_consistency_review.csv")

    # ------------------------------------------------------ process tag inventory
    ol3 = ol[ol.method == "IQR_3.0"].set_index(["dataset", "column"])["percentage_of_points"]
    sen = ol[ol.method == "SENTINEL_VALUE_MATCH"].set_index(["dataset", "column"])["number_of_suspect_points"]
    fli = fl.set_index(["dataset", "tag"])
    dqi = dq.set_index(["dataset", "source_column"])
    ptag = []
    for _, r in dsinv.iterrows():
        k = (r.dataset, r.source_column)
        df = frames[r.dataset][0]
        present_months = sorted(df.loc[df[r.source_column].notna(), "ts"].dt.to_period("M").astype(str).unique())
        ptag.append({
            "dataset": r.dataset, "source_column": r.source_column, "original_name": r.original_name,
            "normalized_name": r.normalized_name, "group_header_ffill_candidate": r.group_header_ffill_candidate,
            "detected_unit": r.detected_unit, "inferred_category": r.inferred_category,
            "likely_process_family": r.likely_process_family, "confidence": r.confidence,
            "classification_evidence": r.classification_evidence,
            "months_with_values": jdump(present_months), "first_timestamp": r.first_valid_timestamp,
            "last_timestamp": r.last_valid_timestamp, "null_percentage": r.null_percentage,
            "completeness_class": dqi.loc[k, "completeness_class"], "health_class": fli.loc[k, "health_class"],
            "iqr3_suspect_pct": float(ol3.get(k, 0.0)), "sentinel_candidate_points": int(sen.get(k, 0)),
            "unit_label_review_required": r.unit_label_review_required,
        })
    write_csv(pd.DataFrame(ptag), "process_tag_inventory.csv")

    # ---------------------------------------------------------- equipment matrix
    study = (tsi[tsi.level == "FILE"].earliest_timestamp.min(), tsi[tsi.level == "FILE"].latest_timestamp.max())
    months = month_range(study[0], study[1])
    src = fi[fi.scope == "SOURCE_DATA"]
    folders = sorted({Path(p).parts[0] for p in src.relative_path})
    idx = sorted(int(folder_index(f)) for f in folders)
    missing_idx = [i for i in range(idx[0], idx[-1] + 1) if i not in idx]
    em, cov = [], []
    for eq in EXPECTED_EQUIPMENT:
        f = src[src.equipment_from_folder == eq]
        tl = tsi[(tsi.dataset == eq) & (tsi.level == "FILE")]
        dsr = tsi[(tsi.dataset == eq) & (tsi.level == "DATASET")]
        cols = dsinv[dsinv.dataset == eq]
        title = sheets.loc[sheets.equipment_from_folder == eq, "title_text"].dropna().unique()
        mcov = {}
        if eq in frames:
            df = frames[eq][0]
            per = df.ts.dt.to_period("M").astype(str)
            cnt = df.groupby(per).ts.nunique()
            for mth in months:
                days = pd.Period(mth).days_in_month
                n = int(cnt.get(mth, 0))
                mcov[mth] = round(n / (days * 1440) * 100, 2)
                cov.append({"equipment": eq, "month": mth, "unique_minutes_present": n, "minutes_in_month": days * 1440,
                            "coverage_pct": mcov[mth],
                            "source_files": jdump(sorted(df.loc[per == mth, "src_file"].unique()))})
        missing_months = [m for m, v in mcov.items() if v == 0] if mcov else months
        em.append({
            "equipment": eq, "dataset_folder": f.parent_folder.iloc[0] if len(f) else "NOT FOUND",
            "available": "Yes" if eq in frames else "No",
            "files_found": int(len(f)), "files_readable": int(f.readable.astype(bool).sum()),
            "files_unreadable": jdump(list(f.loc[~f.readable.astype(bool), "filename"])),
            "sheet_title_in_source": jdump(list(title)),
            "data_rows": int(dsr.rows_in_table.iloc[0]) if len(dsr) else 0,
            "unique_timestamps": int(dsr.unique_timestamps.iloc[0]) if len(dsr) else 0,
            "first_timestamp": dsr.earliest_timestamp.iloc[0] if len(dsr) else None,
            "last_timestamp": dsr.latest_timestamp.iloc[0] if len(dsr) else None,
            "months_in_study_window": jdump(months), "months_missing": jdump(missing_months),
            "monthly_coverage_pct": jdump(mcov),
            "parameter_columns": int(len(cols)),
            "process_families_present": jdump(cols.likely_process_family.value_counts().to_dict()),
            "notes": "",
        })
    em.append({"equipment": f"(folder index {', '.join('%02d' % i for i in missing_idx)})", "dataset_folder": "NOT FOUND",
               "available": "No", "files_found": 0,
               "notes": "Folder numbering has a gap; whether a dataset was intended here is NOT DETERMINABLE FROM SOURCE"} if missing_idx else {})
    emd = pd.DataFrame([e for e in em if e])
    for c in ("files_readable", "data_rows", "unique_timestamps", "parameter_columns"):
        emd[c] = emd[c].astype("Int64")
    write_csv(emd, "equipment_data_matrix.csv")
    write_csv(pd.DataFrame(cov), "equipment_month_coverage.csv")

    # ---------------------------------------------------------- event search
    hits = []
    texts = []  # (location, text)
    for p in source_xlsx_files():
        texts.append((f"filename: {rel(p)}", p.name))
        res = load_workbook_cached(p)
        if res is None:
            texts.append((f"UNREADABLE: {rel(p)}", ""))
            continue
        for sp, rows in res:
            if sp.kind != "PROCESS_LOG_TABLE":
                continue  # non-process sheet reviewed manually (see sheet_inventory notes)
            texts.append((f"{rel(p)} ! sheet name", sp.sheet_name))
            start = (sp.data_start_row or 1) - 1
            for i, r in enumerate(rows[:start]):
                for j, v in enumerate(r):
                    if isinstance(v, str) and v.strip():
                        texts.append((f"{rel(p)} ! header R{i + 1}C{j + 1}", v))
            seen = set()
            for i, r in enumerate(rows[start:], start=start):
                for j, v in enumerate(r[1:], start=1):
                    if isinstance(v, str) and v.strip() and (j, v) not in seen:
                        seen.add((j, v))
                        texts.append((f"{rel(p)} ! data R{i + 1}C{j + 1} (first occurrence)", v))
    supporting = []
    for p in sorted(SUPPORTING_ROOT.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".pdf", ".md", ".txt") and "Dalmia-Kiln-POC" not in p.parts:
            if p.suffix.lower() == ".pdf":
                try:
                    t = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=60).stdout
                except Exception:
                    t = ""
            else:
                t = p.read_text(errors="replace")
            supporting.append((str(p.relative_to(SUPPORTING_ROOT)), t))
    for term in EVENT_TERMS:
        rx = re.compile(r"\b" + re.escape(term) + r"\b", re.I)
        src_hits = [(loc, t) for loc, t in texts if rx.search(t or "")]
        sup_hits = [loc for loc, t in supporting if rx.search(t or "")]
        hits.append({
            "record_type": "KEYWORD SEARCH", "search_term": term,
            "found_in_process_data": bool(src_hits),
            "process_data_locations": jdump([f"{l}: {t!r}" for l, t in src_hits[:10]]),
            "found_in_supporting_documents": bool(sup_hits), "supporting_document_locations": jdump(sup_hits),
            "interpretation": ("Supporting documents describe the problem/requirements only; they are NOT event records."
                               if sup_hits and not src_hits else ""),
        })
    ev = pd.DataFrame(hits)
    found_real = ev.found_in_process_data.any()
    fields = ["event_source", "event_field", "event_type", "start_time", "end_time", "duration", "equipment", "severity"]
    ev_rows = ev.to_dict("records")
    ev_rows.append({"record_type": "CONCLUSION", "search_term": "ALL",
                    "interpretation": ("EVENT GROUND TRUTH NOT FOUND IN SUPPLIED DATA" if not found_real else
                                       "Event-like text found - see rows above; requires validation"),
                    **{f: "NOT FOUND IN SUPPLIED DATA" for f in fields}})
    # observed state signal (NOT an event label)
    if "Kiln-I" in frames:
        df = frames["Kiln-I"][0].drop_duplicates("ts")
        b = df["B"]
        z = (b == 0)
        gid = (z != z.shift()).cumsum()
        grp = df[z].groupby(gid[z]).ts.agg(["min", "max", "size"])
        long = grp[grp["size"] >= HEURISTICS["long_gap_minutes"]]
        ev_rows.append({"record_type": "OBSERVED SIGNAL - NOT EVENT GROUND TRUTH", "search_term": "Kiln-I column B 'Kiln MD' (hrs) == 0",
                        "interpretation": (f"{len(long)} contiguous periods of >= {HEURISTICS['long_gap_minutes']} min with value 0 "
                                           f"(total {int(long['size'].sum())} min). Meaning of 'Kiln MD' and of value 0 is NOT DEFINED "
                                           "in source; may relate to run status. Must NOT be used as a stoppage/coating label "
                                           "without plant confirmation."),
                        "event_source": "derived observation only", "event_field": "B"})
    write_csv(pd.DataFrame(ev_rows), "event_data_inventory.csv")

    # ------------------------------------------------------- AF / RDF inventory
    af = []
    for param, rx in AF_TERMS.items():
        m = dsinv[dsinv.original_name.str.contains(rx, case=False, regex=True) |
                  dsinv.group_header_ffill_candidate.fillna("").str.contains(rx, case=False, regex=True)]
        m = m[m.dataset.isin(frames)]
        if param in ("fuel quantity / rate", "conventional fuel (coal/petcoke/diesel)"):
            m = m[m.likely_process_family.isin(["FUEL", "ALTERNATIVE FUEL"] if param.startswith("fuel") else ["FUEL"])]
        if m.empty:
            af.append({"parameter": param, "found": "NOT FOUND IN SUPPLIED DATA", "source": "", "source_column": "",
                       "original_name": "", "unit": "", "time_range": "", "completeness": "",
                       "coverage_by_equipment": jdump({e: "Not found" for e in EXPECTED_EQUIPMENT})})
            continue
        for _, r in m.iterrows():
            k = (r.dataset, r.source_column)
            df = frames[r.dataset][0]
            mm = df.loc[df[r.source_column].notna(), "ts"].dt.to_period("M").astype(str).unique()
            af.append({"parameter": param, "found": "YES", "source": r.dataset, "source_column": r.source_column,
                       "original_name": r.original_name, "group_header_ffill_candidate": r.group_header_ffill_candidate,
                       "unit": r.detected_unit, "time_range": f"{r.first_valid_timestamp} -> {r.last_valid_timestamp}",
                       "months_with_values": jdump(sorted(mm)),
                       "completeness": f"{100 - r.null_percentage:.2f}% present ({dqi.loc[k, 'completeness_class']})",
                       "zero_pct_of_numeric": dqi.loc[k, "zero_pct_of_numeric"],
                       "classification_confidence": r.confidence,
                       "coverage_by_equipment": jdump({e: ("Available" if e == r.dataset else "Not found") for e in EXPECTED_EQUIPMENT}),
                       "notes": ("Kiln-I (Sep) workbook unreadable -> no September values" if r.dataset == "Kiln-I" else "")})
    write_csv(pd.DataFrame(af), "alternative_fuel_inventory.csv")

    # ---------------------------------------------------- cross-dataset alignment
    wide = {}
    for eq, (df, meta) in frames.items():
        d = df.drop_duplicates("ts", keep="first").set_index("ts")
        for c in meta:
            wide[(eq, c)] = d[c]
    W = pd.DataFrame(wide)
    # column B is compared only where its header is 'Kiln MD' (CBS-Calculation column B is a different parameter)
    kmd = [eq for eq, (df, meta) in frames.items() if "B" in meta and meta["B"].original_name.lower().startswith("kiln md")]
    eqs = list(frames)
    al = []
    for i, a in enumerate(eqs):
        for b in eqs[i + 1:]:
            both = W[[(a, "B"), (b, "B")]].dropna() if (a in kmd and b in kmd) else pd.DataFrame()
            al.append({"dataset_a": a, "dataset_b": b,
                       "common_timestamps": int(len(frames[a][0].ts.drop_duplicates().pipe(set) & set(frames[b][0].ts.drop_duplicates()))),
                       "timestamp_jaccard": round(len(set(frames[a][0].ts) & set(frames[b][0].ts)) / len(set(frames[a][0].ts) | set(frames[b][0].ts)), 4),
                       "colB_rows_compared": int(len(both)),
                       "colB_identical_rate": round(float((both.iloc[:, 0] == both.iloc[:, 1]).mean()), 5) if len(both) else None,
                       "colB_comparison": "Kiln MD vs Kiln MD" if len(both) else "NOT COMPARABLE (column B is not 'Kiln MD' in one dataset)"})
    write_csv(pd.DataFrame(al), "cross_dataset_alignment.csv")
    X = W.to_numpy()
    keys = list(W.columns)
    valid = ~np.isnan(X)
    ident = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if keys[i][0] == keys[j][0] or keys[i][1] == "B" or keys[j][1] == "B":
                continue
            m = valid[:, i] & valid[:, j]
            n = int(m.sum())
            if n < 1000:
                continue
            xi, xj = X[m, i], X[m, j]
            nonzero = float(((xi != 0) & (xj != 0)).mean())
            if nonzero < 0.2 or np.unique(xi).size <= 2:
                continue  # mostly-zero or binary columns match trivially
            rate = float((xi == xj).mean())
            if rate >= 0.95:
                ident.append({"dataset_a": keys[i][0], "column_a": keys[i][1], "name_a": frames[keys[i][0]][1][keys[i][1]].original_name,
                              "dataset_b": keys[j][0], "column_b": keys[j][1], "name_b": frames[keys[j][0]][1][keys[j][1]].original_name,
                              "rows_compared": n, "both_nonzero_share": round(nonzero, 4), "identical_value_rate": round(rate, 5)})
    write_csv(pd.DataFrame(ident, columns=["dataset_a", "column_a", "name_a", "dataset_b", "column_b", "name_b", "rows_compared", "both_nonzero_share", "identical_value_rate"]),
              "cross_dataset_identical_signals.csv")


if __name__ == "__main__":
    main()
