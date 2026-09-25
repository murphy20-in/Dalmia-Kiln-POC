"""Objective D - timestamp structure per file and per equipment dataset.

Frequency is computed from observed timestamps (never assumed).
Outputs: outputs/timestamp_inventory.csv, outputs/sampling_changes.csv
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from common import iter_process_tables, table_frame, write_csv, month_num_from_label, HEURISTICS, jdump


def interval_stats(ts: pd.Series, raw_order: bool = True) -> dict:
    """ts: parsed timestamps in source row order (NaT allowed)."""
    t = ts.dropna()
    d = {"n_timestamps": int(len(t)),
         "earliest_timestamp": t.min() if len(t) else None,
         "latest_timestamp": t.max() if len(t) else None,
         "unique_timestamps": int(t.nunique()),
         "duplicate_timestamp_rows": int(t.duplicated(keep="first").sum()),
         "distinct_timestamps_duplicated": int((t.value_counts() > 1).sum())}
    diffs_raw = t.diff().dropna().dt.total_seconds() / 60.0
    d["out_of_order_steps"] = int((diffs_raw < 0).sum()) if raw_order else None
    d["ordering"] = ("MONOTONIC_NON_DECREASING" if d["out_of_order_steps"] == 0 else "NOT_MONOTONIC")
    u = np.sort(t.unique())
    diffs = pd.Series(np.diff(u)).dt.total_seconds() / 60.0 if len(u) > 1 else pd.Series(dtype=float)
    if len(diffs):
        mode = float(diffs.mode().iloc[0])
        d.update({
            "median_interval_min": float(diffs.median()), "mode_interval_min": mode,
            "min_interval_min": float(diffs.min()), "max_interval_min": float(diffs.max()),
            "irregularity_pct": round(float((diffs != mode).mean() * 100), 4),
            "interval_distribution_top": jdump({f"{k:g}": int(v) for k, v in diffs.value_counts().head(6).items()}),
        })
        span = (u[-1] - u[0]) / np.timedelta64(1, "m")
        d["expected_samples_at_mode"] = int(span / mode) + 1 if mode > 0 else None
        d["coverage_pct_of_span"] = round(len(u) / d["expected_samples_at_mode"] * 100, 3) if mode > 0 else None
        d["observed_frequency"] = (f"{mode:g} minute" if mode < 60 else f"{mode / 60:g} hour") + \
                                  (" (regular)" if d["irregularity_pct"] < 1 else " (with irregularities)")
    return d


def main():
    rows, per_eq, changes = [], {}, []
    for t in iter_process_tables():
        df, ts, fmts = table_frame(t)
        fc = Counter(fmts)
        n = len(fmts)
        ok = n - sum(v for k, v in fc.items() if k in ("EMPTY", "UNPARSED_TEXT", "PATTERN_MATCH_BUT_INVALID", "NUMERIC_NOT_PARSED"))
        st = interval_stats(ts)
        months_in_data = sorted({(x.year, x.month) for x in ts.dropna()})
        exp_m = month_num_from_label(t["month_label"])
        dominant = Counter((x.year, x.month) for x in ts.dropna()).most_common(1)[0][0] if ok else None
        rows.append({
            "level": "FILE", "dataset": t["equipment"], "source_file": t["file_rel"], "source_sheet": t["sheet"].sheet_name,
            "timestamp_column": "A", "timestamp_header": "(no header text)", "date_column": "combined in A",
            "time_column": "combined in A", "combined_datetime": True,
            "timezone": "NOT PRESENT IN SOURCE (timezone NOT DETERMINABLE)",
            "timestamp_formats_observed": jdump(dict(fc)), "rows_in_table": n,
            "parse_success_count": ok, "parse_success_pct": round(ok / n * 100, 4) if n else None,
            **st,
            "month_label_in_filename": t["month_label"], "months_present_in_data": jdump([f"{y}-{m:02d}" for y, m in months_in_data]),
            "filename_month_matches_data": (dominant[1] == exp_m) if (dominant and exp_m) else None,
        })
        per_eq.setdefault(t["equipment"], []).append((t["file_rel"], ts))
        # sampling change by day
        s = ts.dropna().sort_values().drop_duplicates()
        dd = s.diff().dt.total_seconds().div(60)
        day = s.dt.date
        g = pd.DataFrame({"day": day, "d": dd}).dropna().groupby("day")["d"]
        for dayv, grp in g:
            m = grp.mode().iloc[0]
            if m != 1.0 or len(grp) < 1439 * 0.5:
                changes.append({"dataset": t["equipment"], "source_file": t["file_rel"], "day": dayv,
                                "samples": len(grp) + 1, "day_mode_interval_min": m, "day_max_interval_min": grp.max()})
    for eq, parts in per_eq.items():
        ts = pd.concat([p[1] for p in parts], ignore_index=True).sort_values(kind="stable").reset_index(drop=True)
        st = interval_stats(ts, raw_order=False)
        st["out_of_order_steps"] = None
        st["ordering"] = "N/A (files concatenated after sorting; see FILE level)"
        rows.append({"level": "DATASET", "dataset": eq, "source_file": jdump(sorted(p[0] for p in parts)),
                     "source_sheet": "", "timestamp_column": "A", "combined_datetime": True,
                     "timezone": "NOT PRESENT IN SOURCE (timezone NOT DETERMINABLE)",
                     "rows_in_table": int(len(ts)), "parse_success_count": int(ts.notna().sum()),
                     "parse_success_pct": round(ts.notna().mean() * 100, 4), **st})
    out = pd.DataFrame(rows).sort_values(["dataset", "level", "earliest_timestamp"], ascending=[True, False, True])
    write_csv(out, "timestamp_inventory.csv")
    write_csv(pd.DataFrame(changes), "sampling_changes.csv")


if __name__ == "__main__":
    main()
