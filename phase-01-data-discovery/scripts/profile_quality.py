"""Objectives E + G - completeness and value-validity candidates per dataset column.

Completeness classes are a POC DATA-QUALITY HEURISTIC (see common.HEURISTICS):
  GREEN >= 95 % non-missing, AMBER 70-95 %, RED < 70 %.
They are NOT plant engineering limits.

All flagged values are CANDIDATES requiring validation; nothing is declared invalid.
Outputs: outputs/data_quality_report.csv, outputs/completeness_by_month.csv,
         outputs/identical_column_pairs.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import dataset_frames, load_dataset, write_csv, read_out, HEURISTICS, SENTINEL_NUMERIC, jdump

NON_NEGATIVE_UNITS = {"a", "amps", "ma", "kv", "kw", "rpm", "tph", "lph", "m3/m", "m3/hr", "nm3/min", "kg/h",
                      "ton", "tons", "ppm", "hrs", "kwh/t", "kw/ton", "kcal/kg", "kcla/kgclnkr"}


def rag(pct_present: float) -> str:
    if pct_present >= HEURISTICS["completeness_green_min_pct"]:
        return "GREEN"
    if pct_present >= HEURISTICS["completeness_amber_min_pct"]:
        return "AMBER"
    return "RED"


def main():
    inv = read_out("column_inventory.csv")
    inv = inv[(inv.level == "DATASET")].set_index(["dataset", "source_column"])
    rows, monthly, pairs = [], [], []
    for eq, tables in dataset_frames().items():
        df, meta = load_dataset(tables)
        month = df.ts.dt.to_period("M").astype(str)
        runcol = df["B"] if "B" in df else None
        cols = [c for c in df.columns if c not in ("ts", "src_file")]
        for c in cols:
            x = df[c]
            m = meta[c]
            n = len(x)
            inv_row = inv.loc[(eq, c)]
            present_pct = float(inv_row.non_null_count / inv_row.total_rows * 100)
            unit = (m.unit_raw or "").strip().lower()
            v = x.dropna()
            sent = v[v.isin(list(SENTINEL_NUMERIC))]
            temp_floor = int((v <= -273).sum()) if unit == "deg.c" else 0
            pct_out = int(((v < 0) | (v > 100)).sum()) if unit == "%" else 0
            neg = int((v < 0).sum()) if unit in NON_NEGATIVE_UNITS else 0
            miss = x.isna()
            if runcol is not None and c != "B" and miss.any():
                miss_when_b0 = float(((runcol == 0) | runcol.isna())[miss].mean() * 100)
            else:
                miss_when_b0 = None
            rows.append({
                "dataset": eq, "source_column": c, "original_name": m.original_name, "detected_unit": m.unit_raw,
                "total_rows": int(inv_row.total_rows), "non_null_rows": int(inv_row.non_null_count),
                "null_rows": int(inv_row.null_count), "null_percentage": round(100 - present_pct, 4),
                "first_valid_observation": inv_row.first_valid_timestamp, "last_valid_observation": inv_row.last_valid_timestamp,
                "completeness_class": rag(present_pct),
                "completeness_rule": "POC DATA-QUALITY HEURISTIC: GREEN>=95% present, AMBER 70-95%, RED<70%",
                "datatype": inv_row.datatype,
                "numeric_rows": int(v.size), "text_in_numeric_rows": int(inv_row.text_count) if inv_row.numeric_count else 0,
                "numeric_stored_as_text_rows": int(inv_row.numeric_string_count),
                "top_text_values": inv_row.get("top_text_values", ""),
                "sentinel_candidate_rows": int(sent.size),
                "sentinel_candidate_values": jdump({f"{k:g}": int(cnt) for k, cnt in sent.value_counts().items()}),
                "temperature_at_or_below_minus273_rows": temp_floor,
                "percent_outside_0_100_rows": pct_out,
                "negative_in_normally_nonnegative_unit_rows": neg,
                "zero_rows": int((v == 0).sum()), "zero_pct_of_numeric": round(float((v == 0).mean() * 100), 3) if v.size else None,
                "infinite_rows": int(np.isinf(v).sum()),
                "constant_column": bool(v.nunique() <= 1),
                "pct_of_missing_rows_where_colB_is_0_or_missing": None if miss_when_b0 is None else round(miss_when_b0, 2),
                "validation_status": "CANDIDATES REQUIRE PLANT VALIDATION",
            })
            g = pd.DataFrame({"m": month, "present": x.notna()}).groupby("m")["present"].agg(["size", "mean"])
            for mm, r in g.iterrows():
                monthly.append({"dataset": eq, "source_column": c, "original_name": m.original_name, "month": mm,
                                "rows": int(r["size"]), "present_pct": round(float(r["mean"] * 100), 3),
                                "completeness_class": rag(float(r["mean"] * 100))})
        # identical / near-identical column pairs within dataset (possible duplicated signals)
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                both = df[a].notna() & df[b].notna()
                if both.sum() < 1000 or df[a][both].nunique() <= 2:
                    continue
                nonzero = float(((df[a][both] != 0) & (df[b][both] != 0)).mean())
                if nonzero < 0.2:
                    continue  # mostly-zero columns match trivially
                eqrate = float((df[a][both] == df[b][both]).mean())
                if eqrate >= 0.99:
                    pairs.append({"dataset": eq, "column_a": a, "name_a": meta[a].original_name, "column_b": b,
                                  "name_b": meta[b].original_name, "rows_compared": int(both.sum()), "both_nonzero_share": round(nonzero, 4),
                                  "identical_value_rate": round(eqrate, 5)})
    write_csv(pd.DataFrame(rows), "data_quality_report.csv")
    write_csv(pd.DataFrame(monthly), "completeness_by_month.csv")
    write_csv(pd.DataFrame(pairs, columns=["dataset", "column_a", "name_a", "column_b", "name_b", "rows_compared", "both_nonzero_share", "identical_value_rate"]),
              "identical_column_pairs.csv")


if __name__ == "__main__":
    main()
