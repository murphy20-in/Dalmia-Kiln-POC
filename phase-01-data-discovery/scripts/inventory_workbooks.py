"""Objective B - workbook and sheet inventory.

Reads every workbook read-only (openpyxl read_only mode + raw OOXML inspection for
merged cells, formulas, hidden rows/columns, data validation and dimension).
Parsed sheet contents are cached in ../cache for the downstream scripts.

Outputs: outputs/workbook_inventory.csv, outputs/sheet_inventory.csv,
         outputs/header_consistency.csv
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

from common import (SOURCE_ROOT, rel, source_xlsx_files, load_workbook_cached, is_valid_zip, write_csv,
                    equipment_from_folder, month_label_from_filename, parse_ts, clean_text, jdump)

# Reviewer observations recorded so they are reproducible; content itself is NOT reproduced.
MANUAL_OBSERVATIONS = {
    ("01.Process Log Sheet for Kiln-I/01.Process Log Sheet for Kiln-I (Aug).xlsx", "Sheet1"):
        "Reviewed manually: content is an unrelated personal travel itinerary (flight/booking details). "
        "Not plant process data. Contents deliberately not reproduced in Phase 1 outputs.",
}


def sheet_xml_map(z: zipfile.ZipFile) -> dict[str, str]:
    wb = z.read("xl/workbook.xml").decode("utf8", "replace")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8", "replace")
    rid_target = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    rid_target.update({a: b for b, a in re.findall(r'Target="([^"]+)"[^>]*Id="(rId\d+)"', rels)})
    out = {}
    for m in re.finditer(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb):
        name = m.group(1).replace("&amp;", "&")
        tgt = rid_target.get(m.group(2), "")
        out[name] = "xl/" + tgt.lstrip("/").removeprefix("xl/")
    return out


def xml_features(z: zipfile.ZipFile, part: str) -> dict:
    x = z.read(part).decode("utf8", "replace")
    dim = re.search(r'<dimension ref="([^"]+)"', x)
    return {
        "declared_dimension": dim.group(1) if dim else "",
        "merged_cell_ranges": len(re.findall(r"<mergeCell ", x)),
        "merged_cell_examples": ";".join(re.findall(r'<mergeCell ref="([^"]+)"', x)[:10]),
        "formula_cells": len(re.findall(r"<f[ >]", x)),
        "hidden_rows": len(re.findall(r'<row [^>]*hidden="1"', x)),
        "hidden_columns": len(re.findall(r'<col [^>]*hidden="1"', x)),
        "data_validations": len(re.findall(r"<dataValidation ", x)),
        "conditional_formats": len(re.findall(r"<conditionalFormatting", x)),
        "comments_or_notes_part": "",
    }


def preview(rows, start, n):
    return jdump([list(r) for r in rows[start:start + n]])


def main():
    wb_rows, sh_rows = [], []
    for p in source_xlsx_files():
        r = rel(p)
        base = {"workbook": r, "folder": p.parent.name, "equipment_from_folder": equipment_from_folder(p.parent.name),
                "month_label_in_filename": month_label_from_filename(p.name)}
        if not is_valid_zip(p):
            wb_rows.append({**base, "load_status": "NOT_READABLE_CORRUPT", "sheet_count": None,
                            "notes": "Container truncated (see file_inventory.zip_diagnostic). No sheets inspected."})
            continue
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            xmap = sheet_xml_map(z)
            wbxml = z.read("xl/workbook.xml").decode("utf8", "replace")
            app = z.read("docProps/app.xml").decode("utf8", "replace") if "docProps/app.xml" in names else ""
            core = z.read("docProps/core.xml").decode("utf8", "replace") if "docProps/core.xml" in names else ""
            feats = {s: xml_features(z, part) for s, part in xmap.items() if part in names}
            comments = [n for n in names if "comments" in n.lower()]
            ext_links = [n for n in names if "externalLink" in n]
        res = load_workbook_cached(p)
        sheets = [sp for sp, _ in res]
        g = lambda rx, t: (re.search(rx, t).group(1) if re.search(rx, t) else "")
        wb_rows.append({
            **base, "load_status": "READ_OK", "sheet_count": len(sheets),
            "sheet_names": jdump([s.sheet_name for s in sheets]),
            "hidden_sheets": jdump([s.sheet_name for s in sheets if s.sheet_state != "visible"]),
            "process_log_sheets": sum(s.kind == "PROCESS_LOG_TABLE" for s in sheets),
            "non_process_sheets": sum(s.kind == "NON_PROCESS_CONTENT" for s in sheets),
            "empty_sheets": sum(s.kind == "EMPTY" for s in sheets),
            "defined_names": len(re.findall(r"<definedName ", wbxml)),
            "formula_cells_total": sum(f["formula_cells"] for f in feats.values()),
            "merged_ranges_total": sum(f["merged_cell_ranges"] for f in feats.values()),
            "comment_parts": len(comments), "external_link_parts": len(ext_links),
            "trash_parts": sum(n.startswith("[trash]") for n in names),
            "application": g(r"<Application>([^<]+)</Application>", app),
            "doc_created_utc": g(r"<dcterms:created[^>]*>([^<]+)<", core),
            "doc_modified_utc": g(r"<dcterms:modified[^>]*>([^<]+)<", core),
            "notes": "",
        })
        for sp, rows in res:
            f = feats.get(sp.sheet_name, {})
            obs = MANUAL_OBSERVATIONS.get((r, sp.sheet_name), "")
            is_proc = sp.kind == "PROCESS_LOG_TABLE"
            rec = {
                "workbook": r, "equipment_from_folder": base["equipment_from_folder"],
                "month_label_in_filename": base["month_label_in_filename"],
                "sheet_name": sp.sheet_name, "sheet_index": sp.sheet_index, "sheet_state": sp.sheet_state,
                "sheet_kind": sp.kind, "row_count_physical": sp.max_row, "column_count_physical": sp.max_col, **f,
                "title_row": sp.title_row, "title_text": sp.title_text,
                "header_rows": jdump(sp.header_rows), "header_row_count": len(sp.header_rows),
                "unit_row": sp.unit_row, "unit_row_match_rate": sp.unit_row_match_rate,
                "data_start_row": sp.data_start_row, "data_end_row": sp.data_end_row,
                "data_row_count": sp.n_data_rows, "trailing_rows_without_timestamp": sp.trailing_rows_without_ts,
                "first_timestamp_raw": rows[sp.data_start_row - 1][0] if is_proc else "",
                "last_timestamp_raw": rows[sp.data_end_row - 1][0] if is_proc else "",
                "timestamp_column": "A (unlabelled)" if is_proc else "",
                "is_calculation_sheet": bool(re.search(r"calculation", r, re.I)) and is_proc,
                "formulas_vs_static": ("STATIC VALUES ONLY (0 formula cells)" if f.get("formula_cells", 0) == 0
                                       else f"{f['formula_cells']} FORMULA CELLS"),
                "header_preview": preview(rows, 0, (sp.data_start_row - 1) if is_proc else 0),
                "first_data_rows": preview(rows, sp.data_start_row - 1, 3) if is_proc else "[withheld]",
                "last_data_rows": preview(rows, sp.data_end_row - 3, 3) if is_proc else "[withheld]",
                "notes": "; ".join(sp.notes + ([obs] if obs else [])),
            }
            sh_rows.append(rec)
    write_csv(pd.DataFrame(wb_rows), "workbook_inventory.csv")
    sh = pd.DataFrame(sh_rows)
    write_csv(sh, "sheet_inventory.csv")

    # header consistency across monthly files of the same equipment
    hc = []
    for p in source_xlsx_files():
        res = load_workbook_cached(p)
        if res is None:
            continue
        for sp, _ in res:
            if sp.kind != "PROCESS_LOG_TABLE":
                continue
            for c in sp.columns:
                hc.append({"equipment": equipment_from_folder(p.parent.name), "workbook": rel(p),
                           "col_letter": c.col_letter, "original_name": c.original_name, "unit_raw": c.unit_raw,
                           "header_signature": f"{c.original_name} [{c.unit_raw}]"})
    hc = pd.DataFrame(hc)
    summ = (hc.groupby(["equipment", "col_letter"])
              .agg(n_files=("workbook", "nunique"),
                   n_distinct_signatures=("header_signature", "nunique"),
                   signatures=("header_signature", lambda s: jdump(sorted(set(s)))),
                   files_per_signature=("header_signature", lambda s: jdump(s.value_counts().to_dict())))
              .reset_index())
    summ["consistent_across_months"] = summ.n_distinct_signatures == 1
    write_csv(summ, "header_consistency.csv")


if __name__ == "__main__":
    main()
