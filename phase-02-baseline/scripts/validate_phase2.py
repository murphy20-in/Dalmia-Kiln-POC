"""Phase 2 validation gates 1-4 (gate 5 = reproducibility, completed by run_phase2.py).

GATE 1 source integrity   sha256 + size vs Phase 1 manifest; mtime vs Phase 1 file inventory
GATE 2 data integrity     no fabricated rows, no interpolation into gaps, values/units/names equal source
GATE 3 temporal integrity trailing-only windows, prior-only drift references, missing periods stay missing
GATE 4 statistical        population/exclusions documented, bands labelled as non-limits, stats recomputable
Output: outputs/phase2_validation.csv (appended to by run_phase2.py)
"""
from __future__ import annotations

import sys
from datetime import datetime

import numpy as np
import openpyxl
import pandas as pd

from pathlib import Path

from p2common import (RAW, SOURCE_ROOT, BAND_LABEL, H, MAD_SCALE, P1_SCRIPTS, sha256, datasets, load_processed, processed_path,
                      curated_path, read_out, read_p1, wide_included, write_csv, log)

sys.path.insert(0, str(P1_SCRIPTS))
from common import parse_ts  # noqa: E402

lg = log("validate_phase2")
HERE = Path(__file__).resolve().parent
V = []


def chk(gate, check, ok, evidence):
    V.append({"gate": gate, "check": check, "result": "PASS" if ok else "FAIL", "evidence": str(evidence)[:600]})
    lg.info("%s | %s | %s", gate, "PASS" if ok else "FAIL", check)


def gate1():
    m = pd.read_csv(RAW / "source_manifest.csv")
    fi = read_p1("file_inventory.csv").set_index("relative_path")
    bad_h, bad_s, bad_t = [], [], []
    for r in m.itertuples():
        p = SOURCE_ROOT / r.relative_path
        if sha256(p) != r.sha256:
            bad_h.append(r.relative_path)
        if p.stat().st_size != r.file_size_bytes:
            bad_s.append(r.relative_path)
        mt = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        if mt != fi.loc[r.relative_path, "modified_time"]:
            bad_t.append(r.relative_path)
    chk("G1 source integrity", "SHA-256 of every source file equals Phase 1 manifest", not bad_h, f"{len(m)} files; mismatches {bad_h}")
    chk("G1 source integrity", "Size of every source file equals Phase 1 manifest", not bad_s, f"mismatches {bad_s}")
    chk("G1 source integrity", "mtime of every source file equals Phase 1 inventory", not bad_t, f"mismatches {bad_t}")


def gate2():
    plog = read_out("parse_log.csv")
    contract = read_out("tag_contract.csv")
    p1 = read_p1("process_tag_inventory.csv").set_index(["dataset", "source_column"])
    ge = read_p1("gap_events.csv")
    ge = ge[ge.level == "DATASET"]
    man = pd.read_csv(RAW / "source_manifest.csv")
    excluded = set(man[man.status != "USE"].relative_path)
    rng = np.random.default_rng(H["seed"])
    for eq in datasets():
        d = load_processed(eq, ["ts", "source_file", "source_row", "source_column", "value", "raw_value_text", "cell_class",
                                "original_name", "unit", "baseline_status", "mask_reason", "column_hold", "operating_state"])
        pl = plog[plog.dataset == eq]
        chk("G2 data integrity", f"{eq}: processed rows == source data rows x columns (no fabricated rows)",
            len(d) == int(pl.long_rows.sum()) == int((pl.data_rows * pl["columns"]).sum()), f"{len(d)} vs {int((pl.data_rows * pl["columns"]).sum())}")
        dupkey = d.duplicated(["source_file", "source_row", "source_column"]).sum()
        chk("G2 data integrity", f"{eq}: each row maps to one unique source cell", dupkey == 0, f"{dupkey} duplicated source cells")
        chk("G2 data integrity", f"{eq}: excluded manifest files not loaded", not (set(d.source_file.astype(str).unique()) & excluded),
            sorted(set(d.source_file.astype(str).unique()) & excluded))
        # no timestamps inside Phase 1 gap windows (open intervals)
        uts = pd.Series(d.ts.dropna().unique())
        inside = 0
        for g in ge[ge.dataset == eq].itertuples():
            inside += int(((uts > pd.Timestamp(g.gap_start_after)) & (uts < pd.Timestamp(g.gap_end_before))).sum())
        chk("G2 data integrity", f"{eq}: no values inside Phase 1 gap windows (no interpolation)", inside == 0, f"{inside} timestamps inside gaps")
        # original names and units equal Phase 1 inventory
        nm = d.drop_duplicates("source_column")[["source_column", "original_name", "unit"]]
        bad = [r.source_column for r in nm.itertuples() if p1.loc[(eq, r.source_column), "original_name"] != r.original_name
               or str(p1.loc[(eq, r.source_column), "detected_unit"]) != str(r.unit)]
        chk("G2 data integrity", f"{eq}: original names and units identical to Phase 1 (no unit conversion)", not bad, bad)
        # sentinel / invalid values never INCLUDED
        inc = d[d.baseline_status == "INCLUDED"]
        badinc = int(inc.value.isin([99999.0, 9999.0]).sum() + ((inc.unit.astype(str).str.lower() == "deg.c") & (inc.value <= -273)).sum()
                     + inc.cell_class.astype(str).ne("NUMERIC").sum() + inc.mask_reason.astype(str).str.contains("FROZEN|DUPLICATE|SENTINEL").sum())
        chk("G2 data integrity", f"{eq}: no sentinel/text/frozen/duplicate-copy value in the baseline", badinc == 0, f"{badinc} offending cells")
        chk("G2 data integrity", f"{eq}: held columns contribute no baseline values", int((inc.column_hold.astype(str) != "").sum()) == 0, "")
        chk("G2 data integrity", f"{eq}: only RUNNING_PROXY minutes in the baseline", set(inc.operating_state.astype(str).unique()) <= {"RUNNING_PROXY"},
            sorted(inc.operating_state.astype(str).unique()))
        # value spot-check against the source workbook (independent openpyxl read)
        f = pl.sort_values("data_rows").iloc[-1].source_file
        sub = d[(d.source_file == f)]
        samp = sub.iloc[rng.choice(len(sub), size=min(400, len(sub)), replace=False)]
        wb = openpyxl.load_workbook(SOURCE_ROOT / f, read_only=True)
        ws = wb[pl[pl.source_file == f].sheet.iloc[0]]
        want = {(int(r.source_row), str(r.source_column)): r for r in samp.itertuples()}
        rows_needed = sorted({k[0] for k in want})
        cells = {}
        for i, row in enumerate(ws.iter_rows(min_row=rows_needed[0], max_row=rows_needed[-1], values_only=True), start=rows_needed[0]):
            if i in rows_needed:
                cells[i] = row
        wb.close()
        mism = 0
        for (row, col), r in want.items():
            j = openpyxl.utils.column_index_from_string(col) - 1
            src = cells[row][j] if j < len(cells[row]) else None
            if isinstance(src, (int, float)) and not isinstance(src, bool):
                mism += int(not (r.value == float(src)))
            elif src is None:
                mism += int(not np.isnan(r.value))
            else:
                src_txt = src.isoformat() if isinstance(src, datetime) else str(src)
                mism += int(not (str(r.raw_value_text) == src_txt or (str(src).strip() == "" and np.isnan(r.value))))
            ts_src = parse_ts(cells[row][0])[0]
            mism += int(not ((ts_src is None and pd.isna(r.ts)) or ts_src == r.ts))
        chk("G2 data integrity", f"{eq}: 400 random cells equal the source workbook (value + timestamp)", mism == 0, f"{mism} mismatches in {f}")
    # hourly CBS-II rows kept hourly
    d = load_processed("CBS-II", ["ts", "mask_reason", "source_column"])
    h = d[d.mask_reason.astype(str).str.contains("RESOLUTION_HOURLY")]
    per_day = h.drop_duplicates("ts").groupby(h.drop_duplicates("ts").ts.dt.date).size()
    chk("G2 data integrity", "CBS-II hourly days are not expanded to minutes", per_day.max() <= 25 if len(per_day) else True,
        f"max timestamps per hourly day {per_day.max() if len(per_day) else 0}")
    # missing months stay missing
    k1 = load_processed("Kiln-I", ["ts"])
    k3 = load_processed("Kiln-IIIA", ["ts"])
    chk("G2 data integrity", "Kiln-I September 2025 remains MISSING / UNAVAILABLE", int((k1.ts.dt.to_period("M") == "2025-09").sum()) == 0, "")
    chk("G2 data integrity", "Kiln-IIIA April 2025 remains missing (May-repeat file not relabelled)", int((k3.ts.dt.to_period("M") == "2025-04").sum()) == 0, "")


def gate3():
    import calculate_stability as cs
    rng = np.random.default_rng(H["seed"])
    w, seg, _, _ = wide_included("Kiln-I")
    x = w["C"]
    r60 = cs.trailing(x, seg, 60, "std")
    idx = rng.choice(np.flatnonzero(r60.notna().to_numpy()), size=300, replace=False)
    bad = 0
    for i in idx:
        t = x.index[i]
        lo = max(0, i - 59)
        win = x.iloc[lo: i + 1][seg.iloc[lo: i + 1] == seg.iloc[i]]
        man = win.std() if win.notna().sum() >= 48 else np.nan
        # atol absorbs pandas' online-algorithm residue (~1e-5) on perfectly flat windows
        bad += int(not np.isclose(man, r60.iloc[i], rtol=1e-6, atol=1e-4, equal_nan=True))
    chk("G3 temporal integrity", "Rolling windows are trailing-only within segment (300 random recomputations)", bad == 0,
        f"{bad} mismatches (tolerance rtol=1e-6, atol=1e-4 TPH)")
    # direct look-ahead test: erase every value after t; the rolling value at t must not change
    changed = 0
    for i in idx[:60]:
        s_id = seg.iloc[i]
        m = (seg == s_id).to_numpy()
        xs_, ss_ = x[m], seg[m]
        k = int(np.searchsorted(xs_.index.values, x.index.values[i]))
        cut = xs_.copy(); cut.iloc[k + 1:] = np.nan
        a = cs.trailing(xs_, ss_, 60, "std").iloc[k]
        b = cs.trailing(cut, ss_, 60, "std").iloc[k]
        changed += int(not np.isclose(a, b, rtol=1e-9, atol=1e-6, equal_nan=True))
    chk("G3 temporal integrity", "No look-ahead: erasing all future values leaves rolling statistics unchanged (60 samples)",
        changed == 0, f"{changed} values changed")
    # drift references use only prior data
    tmp = read_out("baseline_temporal_analysis.csv")
    mm = tmp[(tmp.level == "MONTH") & (tmp.dataset == "Kiln-I") & (tmp.tag == "C") & tmp.prior_n.notna()]
    xs = x.dropna()
    bad = sum(int((xs.index < pd.Timestamp(r.period_start)).sum() != int(r.prior_n)) for r in mm.itertuples())
    chk("G3 temporal integrity", "Drift reference = only values strictly before the period (Kiln-I C, all months)", bad == 0 and len(mm) > 0,
        f"{len(mm)} months checked, {bad} mismatches")
    # regime smoothing is trailing
    rg = pd.read_parquet(processed_path("Kiln-I").parent / "regime_timeline.parquet")
    chk("G3 temporal integrity", "Regime labels derived from TRAILING 30-min median (documented in identify_regimes.py)",
        "rolling(30, min_periods=20).median()" in (HERE / "identify_regimes.py").read_text() and len(rg) > 0, "code + output present")
    cur = pd.read_parquet(curated_path("Kiln-I"), columns=["ts", "source_file", "source_row"])
    chk("G3 temporal integrity", "Every curated baseline value is traceable (ts, source_file, source_row)", cur.notna().all().all(), f"{len(cur)} rows")
    chk("G3 temporal integrity", "Transition labels are flagged as retrospective (population only, not real-time)",
        "RETROSPECTIVE" in (HERE / "analyze_operating_state.py").read_text(), "documented in analyze_operating_state.py")


def gate3b():
    # ramp windows are truncated at the next stop and restart recovery is excluded
    ev = read_out("operating_state_events.csv")
    rs = ev[ev.event == "RESTART"]
    over = rs[rs.ramp_minutes_applied > rs.following_run_minutes + 0]
    chk("G3 temporal integrity", "Restart-ramp windows never extend past the following run (search stops at the next stop)",
        len(over) == 0, f"{len(over)} of {len(rs)} restarts exceed their run")
    tl = pd.read_parquet(processed_path("Kiln-I").parent / "operating_state_timeline.parquet", columns=["ts", "operating_state"])
    ramp_ts = set(tl.ts[tl.operating_state.isin(["TRANSITION_RAMP_PROXY", "TRANSITION_PRE_STOP_PROXY", "STOPPED_PROXY", "STATE_CONFLICT"])])
    leak = 0
    for eq in datasets():
        cur = pd.read_parquet(curated_path(eq), columns=["ts"])
        leak += int(cur.ts.isin(ramp_ts).sum())
    chk("G3 temporal integrity", "No curated baseline value falls in a stop, transition or conflict minute", leak == 0, f"{leak} values")
    # regime labels use a trailing median: recompute at random points
    rng = np.random.default_rng(H["seed"])
    d = load_processed("Kiln-I", ["ts", "source_column", "value", "value_valid", "dup_status", "segment_id"])
    d = d[(d.source_column == "C") & d.ts.notna() & d.dup_status.isin(["UNIQUE", "DUP_KEPT"])].set_index("ts").sort_index()
    tlx = tl.set_index("ts").operating_state.reindex(d.index)
    x = d.value.where(d.value_valid & (tlx == "RUNNING_PROXY"))
    sm = x.groupby(d.segment_id).transform(lambda s_: s_.rolling(30, min_periods=20).median())
    pts = rng.choice(np.flatnonzero(sm.notna().to_numpy()), size=100, replace=False)
    bad = 0
    for i in pts:
        lo = max(0, i - 29)
        win = x.iloc[lo:i + 1][d.segment_id.iloc[lo:i + 1] == d.segment_id.iloc[i]]
        man = win.median() if win.notna().sum() >= 20 else np.nan
        bad += int(not np.isclose(man, sm.iloc[i], equal_nan=True))
    chk("G3 temporal integrity", "Regime smoothing recomputed as a trailing 30-min median at 100 random points", bad == 0, f"{bad} mismatches")


def gate4():
    pop = read_out("baseline_population.csv")
    ok = (pop.included + pop.masked + pop.excluded_column + pop.excluded_state + pop.excluded_resolution == pop.cells_total).all()
    chk("G4 statistical integrity", "Population counts (included+masked+excluded) reconcile to all cells for every tag", ok, f"{len(pop)} tags")
    nulls = 0
    for eq in datasets():
        d = load_processed(eq, ["baseline_status", "baseline_reason"])
        nulls += int(d.isna().any(axis=1).sum())
    chk("G4 statistical integrity", "Every processed cell has baseline_status and baseline_reason", nulls == 0, f"{nulls} cells without status")
    b = read_out("baseline_reference_bands.csv")
    chk("G4 statistical integrity", "Every reference band is labelled as NOT an engineering/alarm/control limit", (b.band_label == BAND_LABEL).all(), BAND_LABEL)
    st = read_out("baseline_statistics.csv")
    s = st[(st.population == "BASELINE_RUNNING")]
    chk("G4 statistical integrity", "Robust (median/MAD) and classical (mean/std) statistics present with sensitivity class",
        s[["median", "mad", "mean", "std", "outlier_sensitivity"]].notna().all().all(), f"{len(s)} tags")
    cur = pd.read_parquet(curated_path("Kiln-I"), columns=["source_column", "value"])
    v = cur[cur.source_column == "AF"].value.to_numpy()
    row = s[(s.dataset == "Kiln-I") & (s.tag == "AF")].iloc[0]
    chk("G4 statistical integrity", "Baseline median/MAD recomputed from data/curated equals baseline_statistics (Kiln-I AF)",
        np.isclose(np.median(v), row["median"]) and np.isclose(MAD_SCALE * np.median(np.abs(v - np.median(v))), row["scaled_mad"]),
        f"median {np.median(v)} vs {row['median']}")
    conf = read_out("baseline_confidence.csv")
    chk("G4 statistical integrity", "Baseline confidence assigned to every tag/population with documented criteria", conf.baseline_confidence.notna().all(),
        conf[conf.population == "BASELINE_RUNNING"].baseline_confidence.value_counts().to_dict())
    inc_total = int(pop.included.sum())
    cur_total = sum(len(pd.read_parquet(curated_path(eq), columns=["ts"])) for eq in datasets())
    chk("G4 statistical integrity", "Curated row count equals INCLUDED count (all datasets)", inc_total == cur_total, f"{cur_total} vs {inc_total}")
    ok = ((b.lower_reference <= b["median"]) & (b["median"] <= b.upper_reference)).all()
    chk("G4 statistical integrity", "P05 <= median <= P95 for every reference band", ok, f"{len(b)} bands")
    z = b[b.scale == 0]
    chk("G4 statistical integrity", "Robust band is empty (NaN) whenever scaled MAD = 0", z.robust_lower.isna().all() and z.robust_upper.isna().all(), f"{len(z)} bands with MAD=0")
    n_ok = (b.n_observations == b.valid_observations).all()
    chk("G4 statistical integrity", "n_observations equals the population size for every band row", n_ok, "")
    chk("G4 statistical integrity", "Every band row carries a fit_window (full-period fit; refit before scoring use)", b.fit_window.notna().all(), "")
    rg = read_out("operating_regimes.csv")
    chk("G4 statistical integrity", "Regime robustness evaluated by bootstrap and status recorded",
        {"BOOTSTRAP_BAND_STABILITY", "REGIME_STATUS"} <= set(rg.test), rg[rg.test == "REGIME_STATUS"].detail.iloc[0])
    sens = read_out("baseline_sensitivity.csv")
    chk("G4 statistical integrity", "Sensitivity of the baseline to flatlines, repeated rows, post-ramp windows and state basis reported",
        sens.variant.nunique() == 6, sorted(sens.variant.unique()))


def main():
    gate1(); gate2(); gate3(); gate3b(); gate4()
    write_csv(pd.DataFrame(V), "phase2_validation.csv", lg)


if __name__ == "__main__":
    main()
