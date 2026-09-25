"""Step 2 - canonical long-format time series from approved source files only.

One Parquet file per dataset in data/processed/ (masks are added by
build_quality_masks.py). One row per (source file, source row, source column):
nothing is resampled, interpolated or invented; rows only exist where the source
has a row. Non-numeric cell content is preserved verbatim in raw_value_text.
Header parsing reuses the Phase 1 parser (phase-01-data-discovery/scripts/common.py)
and is checked against the Phase 1 tag contract.

Parse cache: phase-02-baseline/cache/<sha256>_<parser hash>.pkl (source content + parser version).
Outputs: data/processed/<dataset>.parquet (unmasked), outputs/parse_log.csv
"""
from __future__ import annotations

import pickle
import sys
from datetime import datetime

import numpy as np
import openpyxl
import pandas as pd

from p2common import (CACHE, RAW, SOURCE_ROOT, P1_SCRIPTS, PROCESSED, processed_path, write_csv, read_out, log)

sys.path.insert(0, str(P1_SCRIPTS))
from common import parse_sheet, parse_ts  # noqa: E402  (Phase 1 parser, read-only use)

lg = log("build_processed_data")


PARSER_HASH = __import__("hashlib").sha256((P1_SCRIPTS / "common.py").read_bytes()).hexdigest()[:12]


def parse_file(rel: str, sha: str):
    # cache key = source content hash + Phase 1 parser hash (a parser change invalidates the cache)
    cp = CACHE / f"{sha}_{PARSER_HASH}.pkl"
    if cp.exists():
        with open(cp, "rb") as fh:
            return pickle.load(fh)
    wb = openpyxl.load_workbook(SOURCE_ROOT / rel, read_only=True, data_only=False)
    out = None
    for si, ws in enumerate(wb.worksheets):
        rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
        sp = parse_sheet(ws, rel, si, rows)
        if sp.kind == "PROCESS_LOG_TABLE":
            if out is not None:
                raise RuntimeError(f"{rel}: more than one process sheet")
            out = (sp, rows[sp.data_start_row - 1: sp.data_end_row])
    wb.close()
    with open(cp, "wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return out


def cell_arrays(col_vals: list):
    """Return (value float array, raw_text object array, cell_class array) without coercing text."""
    n = len(col_vals)
    val = np.full(n, np.nan)
    txt = np.empty(n, dtype=object)
    cls = np.empty(n, dtype=object)
    for i, v in enumerate(col_vals):
        if v is None:
            cls[i] = "EMPTY"
        elif isinstance(v, bool):
            cls[i] = "TEXT"; txt[i] = str(v)
        elif isinstance(v, (int, float)):
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                cls[i] = "NONFINITE"; txt[i] = repr(v)
            else:
                val[i] = float(v); cls[i] = "NUMERIC"
        elif isinstance(v, datetime):
            cls[i] = "TEXT"; txt[i] = v.isoformat()
        else:
            s = str(v)
            if s.strip() == "":
                cls[i] = "BLANK_STRING"
            else:
                txt[i] = s
                try:
                    float(s.strip().replace(",", ""))
                    cls[i] = "NUMERIC_STRING"   # NOT coerced; flagged downstream
                except ValueError:
                    cls[i] = "TEXT"
    return val, txt, cls


def main():
    m = pd.read_csv(RAW / "source_manifest.csv")
    use = m[m.status == "USE"].sort_values(["equipment_from_folder", "first_timestamp"])
    contract = read_out("tag_contract.csv")
    plog, per_ds = [], {}
    for r in use.itertuples():
        sp, data = parse_file(r.relative_path, r.sha256)
        eq = r.equipment_from_folder
        cmeta = contract[contract.dataset == eq].set_index("source_column")
        # header must match the Phase 1 contract exactly (original names preserved)
        mism = [c.col_letter for c in sp.columns[1:] if c.original_name != cmeta.loc[c.col_letter, "original_name"]]
        if mism or len(sp.columns) - 1 != len(cmeta):
            lg.error("%s: header does not match Phase 1 contract (%s)", r.relative_path, mism)
            sys.exit(4)
        ncol = sp.max_col
        data = [tuple(x) + (None,) * (ncol - len(x)) for x in data]
        ts_parsed = [parse_ts(x[0]) for x in data]
        ts = pd.to_datetime(pd.Series([p[0] for p in ts_parsed], dtype="datetime64[ns]"))
        src_row = np.arange(sp.data_start_row, sp.data_start_row + len(data), dtype=np.int32)
        frames = []
        for j, c in enumerate(sp.columns[1:], start=1):
            val, txt, cls = cell_arrays([x[j] for x in data])
            frames.append(pd.DataFrame({
                "ts": ts.values, "source_row": src_row, "source_column": c.col_letter,
                "value": val, "raw_value_text": txt, "cell_class": cls}))
        f = pd.concat(frames, ignore_index=True)
        f.insert(0, "source_file", r.relative_path)
        f.insert(0, "dataset", eq)
        f["source_sheet"] = sp.sheet_name
        f["ts_raw"] = np.tile(np.array([str(x[0]) if x[0] is not None else None for x in data], dtype=object), len(sp.columns) - 1)
        per_ds.setdefault(eq, []).append(f)
        plog.append({"source_file": r.relative_path, "dataset": eq, "sheet": sp.sheet_name, "sha256": r.sha256,
                     "data_start_row": sp.data_start_row, "data_end_row": sp.data_end_row, "data_rows": len(data),
                     "columns": len(sp.columns) - 1, "long_rows": len(f), "ts_unparsed_rows": int(ts.isna().sum()),
                     "header_matches_phase1": True})
        lg.info("parsed %s (%d rows)", r.relative_path, len(data))
    for eq, parts in per_ds.items():
        d = pd.concat(parts, ignore_index=True)
        meta = contract[contract.dataset == eq][["source_column", "original_name", "normalized_name", "detected_unit", "likely_process_family"]]
        d = d.merge(meta, on="source_column", how="left", validate="many_to_one").rename(columns={"detected_unit": "unit"})
        for c in ("dataset", "source_file", "source_sheet", "source_column", "original_name", "normalized_name", "unit",
                  "likely_process_family", "cell_class"):
            d[c] = d[c].astype("category")
        d = d.sort_values(["source_column", "ts", "source_file", "source_row"], kind="stable").reset_index(drop=True)
        d.to_parquet(processed_path(eq), index=False)
        lg.info("wrote %s (%d rows)", processed_path(eq).relative_to(PROCESSED.parents[1]), len(d))
    write_csv(pd.DataFrame(plog), "parse_log.csv", lg)


if __name__ == "__main__":
    main()
