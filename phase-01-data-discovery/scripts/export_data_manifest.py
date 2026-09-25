"""Publish the Phase 1 source manifest into the project data/ layer.

The source workbooks are NOT copied (project rule). data/raw/ receives a
reference manifest so later phases know exactly which files exist, which to
use, and which to exclude, with hashes to detect any change in the source.
Outputs: ../../data/raw/source_manifest.csv, ../../data/raw/dataset_registry.csv
"""
from __future__ import annotations

import pandas as pd

from common import PHASE_DIR, SOURCE_ROOT, read_out

RAW_DIR = PHASE_DIR.parent / "data" / "raw"


def main():
    fi = read_out("file_inventory.csv")
    fi = fi[fi.scope == "SOURCE_DATA"]
    ts = read_out("timestamp_inventory.csv")
    tf = ts[ts.level == "FILE"].set_index("source_file")
    ov = read_out("file_overlaps.csv")
    si = read_out("sheet_inventory.csv")
    proc = si[si.sheet_kind == "PROCESS_LOG_TABLE"].set_index("workbook")
    # a file whose filename month is absent from its data and whose content duplicates another file
    dup_files = {r.file_a if not tf.loc[r.file_a, "filename_month_matches_data"] else r.file_b for r in ov.itertuples()}
    rows = []
    for r in fi.itertuples():
        f = r.relative_path
        if not r.readable:
            status, note = "EXCLUDE_UNREADABLE", "Truncated XLSX container; request re-export"
        elif f in dup_files:
            status, note = "EXCLUDE_DUPLICATE_CONTENT", "Contains another month's data (identical to that month's file); filename month is absent"
        else:
            status, note = "USE", ""
        t = tf.loc[f] if f in tf.index else None
        p = proc.loc[f] if f in proc.index else None
        rows.append({
            "relative_path": f, "absolute_path": str(SOURCE_ROOT / f), "equipment_from_folder": r.equipment_from_folder,
            "month_label_in_filename": r.month_label_in_filename,
            "months_present_in_data": t.months_present_in_data if t is not None else "",
            "first_timestamp": t.earliest_timestamp if t is not None else "", "last_timestamp": t.latest_timestamp if t is not None else "",
            "data_rows": int(p.data_row_count) if p is not None else None,
            "header_rows": p.header_rows if p is not None else "", "unit_row": int(p.unit_row) if p is not None else None,
            "data_start_row": int(p.data_start_row) if p is not None else None,
            "process_sheet": p.sheet_name if p is not None else "",
            "file_size_bytes": r.file_size_bytes, "sha256": r.sha256, "status": status, "notes": note,
        })
    m = pd.DataFrame(rows)
    m["data_rows"] = m["data_rows"].astype("Int64")
    m["unit_row"] = m["unit_row"].astype("Int64")
    m["data_start_row"] = m["data_start_row"].astype("Int64")
    m.to_csv(RAW_DIR / "source_manifest.csv", index=False)
    em = read_out("equipment_data_matrix.csv")
    em.to_csv(RAW_DIR / "dataset_registry.csv", index=False)
    print(f"  wrote data/raw/source_manifest.csv ({len(m)} rows), data/raw/dataset_registry.csv ({len(em)} rows)")


if __name__ == "__main__":
    main()
