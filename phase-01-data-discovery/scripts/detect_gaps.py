"""Objective F - temporal continuity: gaps, duplicates, overlaps, duplicated records.

A gap is an interval between consecutive distinct timestamps larger than
gap_factor x observed mode interval (POC DATA-QUALITY HEURISTIC).
Outputs: outputs/gap_analysis.csv (summary), outputs/gap_events.csv (every gap),
         outputs/duplicate_records.csv, outputs/file_overlaps.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import iter_process_tables, table_frame, numeric_series, write_csv, HEURISTICS, jdump


def gaps_for(ts: pd.Series) -> tuple[float, pd.DataFrame]:
    u = pd.Series(np.sort(ts.dropna().unique()))
    d = u.diff().dt.total_seconds() / 60.0
    mode = float(d.dropna().mode().iloc[0])
    m = d > HEURISTICS["gap_factor"] * mode
    g = pd.DataFrame({"gap_start_after": u.shift(1)[m].values, "gap_end_before": u[m].values, "interval_min": d[m].values})
    g["missing_samples_at_mode"] = (g.interval_min / mode - 1).round().astype(int)
    g["missing_duration_min"] = g.interval_min - mode
    g["long_gap"] = g.interval_min >= HEURISTICS["long_gap_minutes"]
    return mode, g


def summary(level, dataset, src, ts, mode, g):
    return {
        "level": level, "dataset": dataset, "source": src,
        "timestamp_range_start": ts.min(), "timestamp_range_end": ts.max(),
        "expected_interval_min": f"{mode:g} (observed mode; plant logging interval NOT DOCUMENTED IN SOURCE)",
        "observed_median_interval_min": float(pd.Series(np.sort(ts.dropna().unique())).diff().dt.total_seconds().div(60).median()),
        "number_of_gaps": int(len(g)), "number_of_long_gaps": int(g.long_gap.sum()) if len(g) else 0,
        "largest_gap_min": float(g.interval_min.max()) if len(g) else 0.0,
        "largest_gap_start_after": g.loc[g.interval_min.idxmax(), "gap_start_after"] if len(g) else None,
        "total_missing_duration_min": float(g.missing_duration_min.sum()) if len(g) else 0.0,
        "total_missing_duration_hours": round(float(g.missing_duration_min.sum()) / 60, 2) if len(g) else 0.0,
        "missing_samples_at_mode": int(g.missing_samples_at_mode.sum()) if len(g) else 0,
        "duplicate_timestamp_rows": int(ts.dropna().duplicated().sum()),
    }


def main():
    sums, events, dups, spans = [], [], [], []
    per_eq = {}
    numeric_by_file = {}
    for t in iter_process_tables():
        df, ts, _ = table_frame(t)
        mode, g = gaps_for(ts)
        g.insert(0, "source", t["file_rel"]); g.insert(0, "level", "FILE"); g.insert(0, "dataset", t["equipment"])
        events.append(g)
        s = summary("FILE", t["equipment"], t["file_rel"], ts, mode, g)
        # duplicated records
        vals = df.iloc[:, 1:].astype(str)
        full = df.astype(str)
        dup_ts = ts.duplicated(keep=False) & ts.notna()
        same_ts_same_vals = full[dup_ts].duplicated(keep="first").sum()
        consec_same_vals = (vals == vals.shift(1)).all(axis=1).sum()
        s.update({
            "fully_duplicated_rows_incl_timestamp": int(full.duplicated(keep="first").sum()),
            "duplicate_ts_rows_identical_values": int(same_ts_same_vals),
            "duplicate_ts_rows_conflicting_values": int(dup_ts.sum() - ts[dup_ts].nunique() - same_ts_same_vals),
            "consecutive_rows_all_values_identical": int(consec_same_vals),
            "consecutive_rows_all_values_identical_pct": round(consec_same_vals / len(df) * 100, 3),
        })
        sums.append(s)
        if dup_ts.any():
            dd = pd.DataFrame({"ts": ts[dup_ts]})
            c = dd.groupby("ts").size().reset_index(name="rows_with_this_ts")
            c.insert(0, "source", t["file_rel"]); c.insert(0, "dataset", t["equipment"])
            dups.append(c)
        spans.append({"dataset": t["equipment"], "source": t["file_rel"], "start": ts.min(), "end": ts.max()})
        nf = pd.DataFrame({c: numeric_series(df[c]) for c in df.columns[1:]})
        nf.index = ts.values
        numeric_by_file[t["file_rel"]] = nf[~nf.index.duplicated()]
        per_eq.setdefault(t["equipment"], []).append(ts)
    for eq, parts in per_eq.items():
        ts = pd.concat(parts, ignore_index=True)
        mode, g = gaps_for(ts)
        g.insert(0, "source", "ALL FILES"); g.insert(0, "level", "DATASET"); g.insert(0, "dataset", eq)
        events.append(g)
        s = summary("DATASET", eq, "ALL FILES", ts, mode, g)
        sums.append(s)
    # overlaps between files of same equipment
    sp = pd.DataFrame(spans).sort_values(["dataset", "start"])
    ov = []
    for eq, grp in sp.groupby("dataset"):
        r = grp.to_dict("records")
        for i in range(len(r)):
            for j in range(i + 1, len(r)):
                a, b = r[i], r[j]
                lo, hi = max(a["start"], b["start"]), min(a["end"], b["end"])
                if lo <= hi:
                    fa, fb = numeric_by_file[a["source"]], numeric_by_file[b["source"]]
                    j = fa.join(fb, lsuffix="_a", rsuffix="_b", how="inner")
                    cols = [c for c in fa.columns]
                    same = np.mean([((j[c + "_a"] == j[c + "_b"]) | (j[c + "_a"].isna() & j[c + "_b"].isna())).mean() for c in cols])
                    ov.append({"dataset": eq, "file_a": a["source"], "file_b": b["source"], "overlap_start": lo, "overlap_end": hi,
                               "overlap_hours": round((hi - lo).total_seconds() / 3600, 2),
                               "common_timestamps": int(len(j)),
                               "mean_identical_cell_rate": round(float(same), 5),
                               "interpretation": ("overlapping files carry the SAME values (duplicate content)" if same > 0.999
                                                  else "overlapping files carry DIFFERENT values for the same timestamps")})
    write_csv(pd.DataFrame(sums).sort_values(["dataset", "level", "timestamp_range_start"], ascending=[True, False, True]), "gap_analysis.csv")
    write_csv(pd.concat(events, ignore_index=True), "gap_events.csv")
    write_csv(pd.concat(dups, ignore_index=True) if dups else pd.DataFrame(columns=["dataset", "source", "ts", "rows_with_this_ts"]), "duplicate_records.csv")
    write_csv(pd.DataFrame(ov, columns=["dataset", "file_a", "file_b", "overlap_start", "overlap_end", "overlap_hours",
                                         "common_timestamps", "mean_identical_cell_rate", "interpretation"]), "file_overlaps.csv")


if __name__ == "__main__":
    main()
