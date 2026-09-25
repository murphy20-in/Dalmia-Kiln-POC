"""Step 1 - read the Phase 1 metadata contract and verify the source (GATE 1 input).

- Loads data/raw/source_manifest.csv; only status == USE files are approved.
- Re-hashes EVERY manifest file (sha256 + size) and records mtime; fails hard on a
  sha256/size mismatch for an approved file.
- Builds the tag contract (real Phase 1 columns only) and column-level holds derived
  from Phase 1 artifacts.
Outputs: outputs/source_verification.csv, outputs/tag_contract.csv,
         outputs/column_holds.csv, outputs/frozen_windows.csv
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from p2common import RAW, SOURCE_ROOT, sha256, write_csv, read_p1, log

lg = log("load_phase1_manifest")


def verify_source() -> pd.DataFrame:
    m = pd.read_csv(RAW / "source_manifest.csv")
    rows = []
    for r in m.itertuples():
        p = SOURCE_ROOT / r.relative_path
        st = p.stat()
        h = sha256(p)
        rows.append({"relative_path": r.relative_path, "status": r.status, "manifest_sha256": r.sha256, "current_sha256": h,
                     "manifest_size": r.file_size_bytes, "current_size": st.st_size, "current_mtime_ns": st.st_mtime_ns,
                     "sha256_match": h == r.sha256, "size_match": st.st_size == r.file_size_bytes})
    v = pd.DataFrame(rows)
    write_csv(v, "source_verification.csv", lg)
    bad = v[(v.status == "USE") & ~(v.sha256_match & v.size_match)]
    if len(bad):
        lg.error("Approved source files changed since Phase 1: %s", bad.relative_path.tolist())
        sys.exit(2)
    return v


def tag_contract() -> pd.DataFrame:
    t = read_p1("process_tag_inventory.csv")
    keep = ["dataset", "source_column", "original_name", "normalized_name", "group_header_ffill_candidate", "detected_unit",
            "inferred_category", "likely_process_family", "confidence", "classification_evidence", "completeness_class",
            "health_class", "unit_label_review_required"]
    t = t[keep].copy()
    write_csv(t, "tag_contract.csv", lg)
    return t


def column_holds(t: pd.DataFrame) -> pd.DataFrame:
    """Column-level exclusions from the baseline population (values remain in data/processed)."""
    H = []
    ur = read_p1("unit_consistency_review.csv")
    for r in ur.itertuples():
        if str(r.dataset).startswith("["):
            continue  # cross-dataset unit-spelling notes are INFO only
        H.append((r.dataset, r.source_column, "UNIT_REVIEW_HOLD", f"{r.check}: {r.evidence}"))
    fl = read_p1("flatline_profile.csv")
    for r in fl[fl.health_class.str.startswith("CONSTANT", na=False)].itertuples():
        H.append((r.dataset, r.tag, "CONSTANT_COLUMN", f"single value {r.most_common_value:g} over the supplied period"))
    dq = read_p1("data_quality_report.csv")
    for r in dq[dq.completeness_class == "RED"].itertuples():
        H.append((r.dataset, r.source_column, "SPARSE_COLUMN", f"{r.null_percentage:.1f}% missing (Phase 1 RED, POC heuristic)"))
    s = dq[dq.sentinel_candidate_rows > 0]
    for r in s[s.sentinel_candidate_rows / s.total_rows > 0.5].itertuples():
        H.append((r.dataset, r.source_column, "SENTINEL_DOMINATED", f"sentinel candidates {r.sentinel_candidate_values} in >50% of rows"))
    ip = read_p1("identical_column_pairs.csv")
    for r in ip.itertuples():
        H.append((r.dataset, r.column_b, "REDUNDANT_DUPLICATE_COLUMN", f"identical to {r.column_a} '{r.name_a}' (rate {r.identical_value_rate})"))
    # the operating-state candidate itself is not baselined as a process value
    for r in t[t.original_name.str.lower().str.startswith("kiln md")].itertuples():
        H.append((r.dataset, r.source_column, "STATE_INDICATOR_COLUMN", "'Kiln MD' used only as operating-state proxy input (meaning UNCONFIRMED)"))
    h = pd.DataFrame(H, columns=["dataset", "source_column", "hold", "evidence"])
    h = h.merge(t[["dataset", "source_column", "original_name"]], on=["dataset", "source_column"], how="left", validate="many_to_one")
    missing = h[h.original_name.isna()]
    if len(missing):
        lg.error("Hold refers to a column not in the Phase 1 tag inventory: %s", missing.to_dict("records"))
        sys.exit(3)
    write_csv(h, "column_holds.csv", lg)
    return h


def frozen_windows() -> pd.DataFrame:
    """Synchronised flatlines (>= 20 tags sharing the same non-zero flat window) = suspected frozen export."""
    fp = read_p1("flatline_periods.csv")
    nz = fp[~fp.is_zero_value.astype(bool)]
    g = nz.groupby(["start", "end"]).agg(tags=("tag", "size"), datasets=("dataset", lambda s: json.dumps(sorted(set(s))))).reset_index()
    g = g[g.tags >= 20].rename(columns={"start": "window_start", "end": "window_end"})
    g["rule"] = ">=20 tags hold an identical non-zero value over the same window (Phase 1 flatline_periods)"
    write_csv(g, "frozen_windows.csv", lg)
    return g


def main():
    verify_source()
    t = tag_contract()
    column_holds(t)
    frozen_windows()


if __name__ == "__main__":
    main()
