"""Step 3 - AFR data-quality profile (Solid and Liquid), minute level. Descriptive only.

Reads  data/processed/kiln_i.parquet (columns K, L; read-only), cache/minute_afr.parquet (causal minute state)
Writes outputs/afr_data_quality.csv   one row per signal x scope (ALL_SUPPLIED, RUNNING_MINUTES, NOT_RUNNING_MINUTES,
                                      M04..M08). Flags are counted, never used to silently delete values.

Accounting identity (checked in G4): minutes = missing + invalid + zero + nonzero, where
  MISSING  = empty / NaN cell;   INVALID = present but Phase 2 value_valid False, or negative;
  ZERO     = 0 <= v <= zero_cut; NONZERO = v > zero_cut.  Missing is never treated as zero.
Flatline periods: runs of >= 60 identical NON-ZERO consecutive minutes (Phase 1 / Phase 3 rule). Gaps: runs of >= 10
consecutive MISSING minutes. Sentinel candidates: present values >= 9,999 (9,999 / 10,000 / 99,999 style codes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from af_core import AFR, AFR_LIQUID, CACHE, PRIMARY, classify, log, runs, write_csv
from p3common import processed_path

lg = log("profile_afr_quality")


def load(col: str) -> tuple[pd.DataFrame, dict]:
    d = pd.read_parquet(processed_path("Kiln-I"), columns=["ts", "source_column", "value", "value_valid", "dup_status",
                                                           "mask_reason", "tag_flatline"],
                        filters=[("source_column", "==", col)])
    dup = d.dup_status.value_counts().to_dict()
    d = d[d.ts.notna() & ~d.dup_status.eq("DUP_IDENTICAL_COPY")].drop_duplicates("ts").sort_values("ts")
    return d.reset_index(drop=True), dup


def flat_runs(v: np.ndarray, ts: np.ndarray) -> tuple[int, int]:
    """Count and longest length (minutes) of runs of >= 60 identical non-zero consecutive minutes."""
    step = np.r_[False, np.diff(ts.astype("datetime64[m]").astype(np.int64)) == 1]
    same = np.r_[False, v[1:] == v[:-1]] & step & np.isfinite(v) & (v != 0)
    grp = runs(np.where(same, 1.0, 0.0))
    g = grp[grp.value == 1.0].length.to_numpy() + 1
    g = g[g >= 60]
    return int(g.size), int(g.max()) if g.size else 0


def profile(sig: str, d: pd.DataFrame, sel: np.ndarray, scope: str, dup: dict) -> dict:
    s = d[sel]
    v = s.value.to_numpy(float)
    valid = s.value_valid.to_numpy(bool)
    c = classify(np.where(valid | np.isnan(v), v, -1.0), PRIMARY.zero_cut)
    n = len(s)
    ok = v[(c == "ZERO") | (c == "NONZERO")]
    nz = v[c == "NONZERO"]
    miss = runs((c == "MISSING").astype(float))
    gaps = miss[(miss.value == 1.0) & (miss.length >= 10)].length
    fl_n, fl_max = flat_runs(v, s.ts.to_numpy())

    def q(a, p):
        return float(np.quantile(a, p)) if a.size else np.nan
    return {"afr_signal": sig, "scope": scope, "minutes": n, "present": int(np.isfinite(v).sum()),
            "valid_observations": int(ok.size), "missing": int((c == "MISSING").sum()),
            "invalid": int((c == "INVALID").sum()), "negative": int((v < 0).sum()),
            "zero": int((c == "ZERO").sum()), "nonzero": int((c == "NONZERO").sum()),
            "coverage": float(np.isfinite(v).mean()) if n else np.nan,
            "missing_fraction": float((c == "MISSING").mean()) if n else np.nan,
            "zero_fraction": float((c == "ZERO").mean()) if n else np.nan,
            "nonzero_fraction": float((c == "NONZERO").mean()) if n else np.nan,
            "zero_fraction_of_valid": float((c == "ZERO").sum() / ok.size) if ok.size else np.nan,
            "median": q(ok, .5), "p05": q(ok, .05), "p25": q(ok, .25), "p75": q(ok, .75), "p95": q(ok, .95),
            "max": float(ok.max()) if ok.size else np.nan,
            "nonzero_median": q(nz, .5), "nonzero_p05": q(nz, .05), "nonzero_p95": q(nz, .95),
            "robust_variation_mad_nonzero": float(1.4826 * np.median(np.abs(nz - np.median(nz)))) if nz.size else np.nan,
            "iqr_nonzero": q(nz, .75) - q(nz, .25) if nz.size else np.nan,
            "distinct_values": int(np.unique(ok).size),
            "integer_share": float(np.mean(ok == np.round(ok))) if ok.size else np.nan,
            "p2_flatline_minutes": int(s.tag_flatline.fillna(False).astype(bool).sum()),
            "flatline_periods_ge_60min": fl_n, "longest_flatline_min": fl_max,
            "gaps_ge_10min": int(gaps.size), "longest_gap_min": int(gaps.max()) if gaps.size else 0,
            "sentinel_candidates_ge_9999": int((v >= 9999).sum()),
            "frozen_window_minutes": int(s.mask_reason.astype(str).str.contains("SUSPECTED_FROZEN_WINDOW").sum()),
            "duplicate_timestamp_rows": int(sum(dup.get(k, 0) for k in ("DUP_KEPT", "DUP_IDENTICAL_COPY", "DUP_CONFLICT")))
            if scope == "ALL_SUPPLIED" else np.nan,
            "duplicate_conflicts": int(dup.get("DUP_CONFLICT", 0)) if scope == "ALL_SUPPLIED" else np.nan}


def main():
    st = pd.read_parquet(CACHE / "minute_afr.parquet", columns=["state"]).state
    rows = []
    for sig, col in ((AFR, "K"), (AFR_LIQUID, "L")):
        d, dup = load(col)
        state = st.reindex(d.ts).fillna("UNKNOWN").to_numpy()
        rows.append(profile(sig, d, np.ones(len(d), dtype=bool), "ALL_SUPPLIED", dup))
        rows.append(profile(sig, d, state == "RUNNING", "RUNNING_MINUTES", dup))
        rows.append(profile(sig, d, state != "RUNNING", "NOT_RUNNING_MINUTES", dup))
        for m in range(4, 9):
            rows.append(profile(sig, d, d.ts.dt.month.to_numpy() == m, f"M{m:02d}", dup))
    out = pd.DataFrame(rows)
    out["missing_is_not_zero"] = True
    out["label"] = "DESCRIPTIVE DATA-QUALITY PROFILE (MINUTE LEVEL); flags counted, values not deleted"
    write_csv(out, "afr_data_quality.csv", lg)


if __name__ == "__main__":
    main()
