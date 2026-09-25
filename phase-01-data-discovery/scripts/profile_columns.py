"""Objectives C + G - canonical column/tag inventory with datatype and value profiling.

One row per (source_file, source_column) [level=FILE] plus one row per
(dataset, column) across all monthly files [level=DATASET].
original_name is always preserved; normalized_name is an added key only.

Missing = empty cell OR whitespace-only string (documented choice).
Numeric statistics use native numeric cells only; numeric-looking strings are
counted separately and are NOT coerced.

Outputs: outputs/column_inventory.csv, outputs/categorical_profile.csv
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from common import (dataset_frames, table_frame, classify_cell, numeric_series, write_csv, jdump,
                    SENTINEL_NUMERIC, SENTINEL_TEXT)
from taxonomy import classify_family, measurement_type, label_unit_check


def own_text(c) -> str:
    parts = [str(x).strip() for x in c.header_cells if x is not None and str(x).strip() and str(x).strip() != (c.unit_raw or "")]
    # unit row is the last header row; exclude it from own text
    if c.unit_raw is not None and c.header_cells and str(c.header_cells[-1] or "").strip() == c.unit_raw:
        parts = [str(x).strip() for x in c.header_cells[:-1] if x is not None and str(x).strip()]
    return " | ".join(parts)


def sub_label(c) -> str:
    cells = c.header_cells[:-1] if c.unit_raw is not None else c.header_cells
    parts = [str(x).strip() for x in cells if x is not None and str(x).strip()]
    return parts[-1] if parts else ""


def datatype_of(counts: Counter, n_unique_text: int) -> str:
    present = {k: v for k, v in counts.items() if k not in ("empty", "blank_string") and v}
    if not present:
        return "EMPTY (no values)"
    kinds = set(present)
    if kinds <= {"int"}:
        return "integer"
    if kinds <= {"int", "float"}:
        return "floating point" if "float" in kinds else "integer"
    if kinds <= {"datetime"}:
        return "datetime"
    if kinds <= {"bool"}:
        return "boolean"
    if kinds <= {"text", "placeholder_text"}:
        return "categorical" if n_unique_text <= 50 else "string"
    return "mixed (" + "+".join(sorted(kinds)) + ")"


def profile(raw: pd.Series, ts: pd.Series) -> dict:
    cls = raw.map(classify_cell)
    counts = Counter(cls)
    n = len(raw)
    missing = counts.get("empty", 0) + counts.get("blank_string", 0)
    text_vals = raw[cls.isin(["text", "placeholder_text", "numeric_string"])].map(lambda v: str(v).strip())
    num = numeric_series(raw)
    valid = num.notna() | cls.isin(["text", "placeholder_text", "numeric_string", "datetime", "bool"])
    d = {
        "total_rows": n, "non_null_count": n - missing, "null_count": missing,
        "empty_cell_count": counts.get("empty", 0), "blank_string_count": counts.get("blank_string", 0),
        "null_percentage": round(missing / n * 100, 4) if n else None,
        "cell_type_counts": jdump(dict(counts)),
        "datatype": datatype_of(counts, text_vals.nunique()),
        "numeric_count": int(num.notna().sum()),
        "numeric_string_count": counts.get("numeric_string", 0),
        "text_count": counts.get("text", 0), "placeholder_text_count": counts.get("placeholder_text", 0),
        "unique_count": int(pd.concat([num.dropna().astype(object), text_vals]).nunique()),
        "first_valid_timestamp": ts[valid.values].min() if valid.any() else None,
        "last_valid_timestamp": ts[valid.values].max() if valid.any() else None,
    }
    x = num.dropna()
    if len(x):
        q = x.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        d.update({
            "min": float(x.min()), "max": float(x.max()), "mean": float(x.mean()), "median": float(x.median()),
            "standard_deviation": float(x.std()) if len(x) > 1 else 0.0,
            "p01": q[0.01], "p05": q[0.05], "p25": q[0.25], "p75": q[0.75], "p95": q[0.95], "p99": q[0.99],
            "zero_count": int((x == 0).sum()), "zero_pct": round(float((x == 0).mean() * 100), 3),
            "negative_count": int((x < 0).sum()), "infinite_count": int(np.isinf(x).sum()),
            "sentinel_candidate_values": jdump({f"{k:g}": int(v) for k, v in x[x.isin(list(SENTINEL_NUMERIC))].value_counts().items()}),
            "top_numeric_values": jdump({f"{k:g}": int(v) for k, v in x.value_counts().head(5).items()}),
            "top_value_share_pct": round(float(x.value_counts().iloc[0] / len(x) * 100), 3),
        })
    if len(text_vals):
        vc = text_vals.value_counts()
        d["top_text_values"] = jdump(vc.head(10).to_dict())
        d["text_value_examples_in_numeric_column"] = jdump(vc.head(5).to_dict()) if len(x) else ""
    return d, text_vals


def main():
    rows, cats = [], []
    for eq, tables in dataset_frames().items():
        agg_raw, agg_ts, files = {}, [], []
        for t in tables:
            sp = t["sheet"]
            df, ts, _ = table_frame(t)
            agg_ts.append(ts)
            files.append(t["file_rel"])
            for c in sp.columns:
                base = column_base(eq, sp, c)
                if c.is_timestamp_col:
                    ok = ts.notna()
                    rows.append({"level": "FILE", "source_file": t["file_rel"], "source_sheet": sp.sheet_name, **base,
                                 "datatype": "datetime (stored as text dd.mm.yyyy HH:MM)", "total_rows": len(ts),
                                 "non_null_count": int(ok.sum()), "null_count": int((~ok).sum()),
                                 "null_percentage": round(float((~ok).mean() * 100), 4),
                                 "unique_count": int(ts.nunique()), "first_timestamp": ts.min(), "last_timestamp": ts.max()})
                    continue
                d, tv = profile(df[c.col_letter], ts)
                rows.append({"level": "FILE", "source_file": t["file_rel"], "source_sheet": sp.sheet_name, **base, **d,
                             "first_timestamp": ts.min(), "last_timestamp": ts.max()})
                agg_raw.setdefault(c.col_letter, []).append(df[c.col_letter])
        ts_all = pd.concat(agg_ts, ignore_index=True)
        sp0 = tables[0]["sheet"]
        for c in sp0.columns:
            if c.is_timestamp_col:
                continue
            raw = pd.concat(agg_raw[c.col_letter], ignore_index=True)
            d, tv = profile(raw, ts_all)
            rows.append({"level": "DATASET", "source_file": jdump(sorted(files)), "source_sheet": sp0.sheet_name,
                         **column_base(eq, sp0, c), **d, "first_timestamp": ts_all.min(), "last_timestamp": ts_all.max()})
            if len(tv):
                for val, cnt in tv.value_counts().head(25).items():
                    cats.append({"dataset": eq, "source_column": c.col_letter, "original_name": c.original_name,
                                 "value": val, "count": int(cnt), "pct_of_rows": round(cnt / len(raw) * 100, 4),
                                 "suspicion_reason": suspicion(val, d.get("numeric_count", 0))})
    out = pd.DataFrame(rows)
    write_csv(out, "column_inventory.csv")
    write_csv(pd.DataFrame(cats, columns=["dataset", "source_column", "original_name", "value", "count", "pct_of_rows", "suspicion_reason"]),
              "categorical_profile.csv")


def suspicion(val: str, numeric_count: int) -> str:
    if val.upper() in SENTINEL_TEXT:
        return "PLACEHOLDER TEXT CANDIDATE - requires validation"
    try:
        float(val.replace(",", ""))
        return "NUMERIC VALUE STORED AS TEXT"
    except ValueError:
        pass
    if numeric_count:
        return "TEXT EMBEDDED IN NUMERIC COLUMN - requires validation"
    return ""


def column_base(eq, sp, c) -> dict:
    text = own_text(c)
    fam, conf, ev = ("N/A", "HIGH", "timestamp column") if c.is_timestamp_col else classify_family(eq, c.col_letter, text, c.group_ffill_candidate, sp.title_text)
    review, why = (False, "") if c.is_timestamp_col else label_unit_check(sub_label(c) or text, c.unit_raw)
    return {
        "dataset": eq, "source_column": c.col_letter, "original_name": c.original_name,
        "header_cells_raw": jdump(c.header_cells), "header_rows": jdump(c.header_rows),
        "group_header_ffill_candidate": c.group_ffill_candidate,
        "normalized_name": f"{eq.lower().replace(' ', '_').replace('-', '_')}__{c.normalized_name}",
        "detected_unit": c.unit_raw if c.unit_raw else ("N/A" if c.is_timestamp_col else "UNKNOWN"),
        "unit_source_cell": c.unit_cell, "timestamp_candidate": c.is_timestamp_col,
        "inferred_category": "TIMESTAMP" if c.is_timestamp_col else measurement_type(c.unit_raw),
        "likely_process_family": fam, "confidence": conf, "classification_evidence": ev,
        "unit_label_review_required": review, "unit_label_review_reason": why,
        "notes": ("header text absent; only unit present" if c.original_name == "(no header text)" else ""),
    }


if __name__ == "__main__":
    main()
