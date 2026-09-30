"""Offline Phase 9 build step: materialise the O2-excluded variant once and write the artifact manifest.

Never imported by the API process. Run by run_phase9.py (or directly: `../../.venv/bin/python -B build_artifacts.py`).

O2-excluded variant. Phase 8 builds it on every run with its own unchanged o2_sensitivity.o2_excluded_score (Phase 7's
EXCLUDE_KILN_INLET_O2_ANALYSER definition, a frozen Apr-May variant reference, Phase 7's score_core) but persists it
only inside the 12 event windows. Phase 9 calls that same function once, masks it to the PRIMARY operational rows exactly
as Phase 8's make_signals does, and refuses to write the file unless it reproduces
  (1) every persisted Phase 8 o2x_risk_score in early_warning_trajectories.parquet (after the same 6-dp rounding), and
  (2) the Phase 8 score_rank_correlation_operational_buckets in early_warning_o2_sensitivity.csv.
Nothing in Phase 7 or Phase 8 is modified; Phase 7's cache is read, never rebuilt.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from p9common import (ARTIFACTS, CONTRACT_FILE, MANIFEST_FILE, O2X_FILE, OUT, ROOT, VERSION, artifact,  # noqa: E402
                      read_json, sha256, write_json)

P8_SCRIPTS = ROOT / "phase-08-early-warning" / "scripts"
P7_CACHE_FILES = ("grid.parquet", "episodes.parquet", "afr_events.parquet", "dq_windows.parquet", "context_meta.json")
TOL = 5e-7   # Phase 8 outputs are rounded to 6 dp (round_frame)


def materialise_o2x() -> dict:
    missing = [f for f in P7_CACHE_FILES if not (ROOT / "phase-07-risk-score/cache" / f).is_file()]
    if missing:
        raise RuntimeError(f"Phase 7 cache missing {missing}: run Phase 7 first; Phase 9 never rebuilds upstream caches")
    if str(P8_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(P8_SCRIPTS))           # Phase 8 first; p8common appends Phase 7's scripts after it
    import o2_sensitivity as o2s                      # Phase 8, read-only
    from p8common import SCORE_VERSION, ic, p7c       # Phase 8 / Phase 7, read-only

    ctx = p7c.load_context()
    ix = ctx["grid"].index
    ic.check_grid(ix)
    s = pd.read_parquet(ROOT / artifact("risk_scores")["path"],
                        columns=["timestamp", "operational", "risk_score", "score_version"]).set_index("timestamp")
    if set(s.score_version.dropna().unique()) != {SCORE_VERSION}:
        raise RuntimeError(f"risk_scores.parquet is not {SCORE_VERSION}")
    s = s.reindex(ix)
    oper = s.operational.fillna(False).to_numpy(bool)
    o2_all, _ = o2s.o2_excluded_score({"grid": ctx["grid"], "ctx": ctx})
    o2x = np.where(oper, o2_all, np.nan)                # Phase 8 make_signals masking

    # gate 1: persisted Phase 8 trajectory values
    tr = pd.read_parquet(ROOT / artifact("p8_trajectories")["path"], columns=["timestamp", "o2x_risk_score"])
    if (tr.drop_duplicates().timestamp.duplicated()).any():          # overlapping windows must agree
        raise RuntimeError("Phase 8 trajectories carry different o2x values for the same timestamp")
    tr = tr.drop_duplicates("timestamp").set_index("timestamp")
    mine = pd.Series(o2x, index=ix).reindex(tr.index).round(6)
    theirs = tr.o2x_risk_score
    nan_equal = bool((mine.isna() == theirs.isna()).all())
    both = mine.notna() & theirs.notna()
    max_diff = float((mine[both] - theirs[both]).abs().max())
    # gate 2: Phase 8 rank correlation over operational buckets
    stored = s.risk_score.to_numpy(float)
    fin = oper & np.isfinite(stored) & np.isfinite(o2x)
    rho = float(stats.spearmanr(stored[fin], o2x[fin]).statistic)
    o2csv = pd.read_csv(ROOT / artifact("p8_o2_sensitivity")["path"]).set_index("metric")
    rho_p8 = float(o2csv.loc["score_rank_correlation_operational_buckets", "o2_excluded"])
    # gate 3: Phase 8's persisted full-series monthly medians of the variant (level check over all 9.5k rows)
    months = {"JUN": 6, "JUL": 7, "AUG": 8}
    med = {m: float(np.nanmedian(o2x[oper & (ix.month == k)])) for m, k in months.items()}
    med_diff = max(abs(med[m] - float(o2csv.loc[f"median_score_{m}", "o2_excluded"])) for m in months)
    checks = {"trajectory_rows_compared": int(both.sum()), "trajectory_nan_pattern_equal": nan_equal,
              "trajectory_months": sorted({str(t)[:7] for t in theirs.index[both]}),
              "monthly_median_max_abs_diff": med_diff,
              "trajectory_max_abs_diff": max_diff, "rank_correlation_rebuilt": rho,
              "rank_correlation_phase8": rho_p8, "rank_correlation_abs_diff": abs(rho - rho_p8)}
    ok = (nan_equal and both.sum() > 0 and max_diff <= TOL and checks["rank_correlation_abs_diff"] <= 1e-12
          and med_diff <= TOL)
    if not ok:
        raise RuntimeError(f"O2-excluded materialisation does not reproduce Phase 8: {checks}")

    out = pd.DataFrame({"timestamp": ix[oper], "o2_excluded_risk_score": np.round(o2x[oper], 6)})
    out["variant"] = o2s.VARIANT
    out["score_version"] = SCORE_VERSION
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(ROOT / O2X_FILE, index=False)
    used = [ROOT / "phase-07-risk-score/cache" / f for f in P7_CACHE_FILES] + [
        P8_SCRIPTS / f for f in ("o2_sensitivity.py", "p8common.py")] + [
        ROOT / "phase-07-risk-score/scripts" / f for f in ("reference_builder.py", "risk_core.py", "common.py")]
    return {**checks, "rows": len(out), "rows_with_score": int(out.o2_excluded_risk_score.notna().sum()),
            "variant": o2s.VARIANT, "producer": "phase-08-early-warning/scripts/o2_sensitivity.py::o2_excluded_score",
            "method": "one-off offline refit of the variant's Apr-May reference and rescore by Phase 8's own unchanged "
                      "code (what Phase 8 does on every run); the API only reads the stored result",
            "inputs_sha256": {str(f.relative_to(ROOT)): sha256(f) for f in used},
            "variant_reference_persisted_upstream": False,
            "status": "VERIFIED_AGAINST_PHASE8"}


def _schema(path) -> dict | None:
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        return {f.name: str(f.type) for f in pq.read_schema(path)}
    if path.suffix == ".csv":
        return {c: "csv" for c in pd.read_csv(path, nrows=0).columns}
    return None


def _version(key: str, path) -> str | None:
    """Versions are read from the artifacts themselves, never typed here."""
    if key in ("risk_scores", "o2_excluded_scores"):
        return ";".join(sorted(pd.read_parquet(path, columns=["score_version"]).score_version.dropna().unique()))
    if key == "abnormal_episodes":
        return ";".join(sorted(pd.read_parquet(path, columns=["method_version"]).method_version.dropna().unique()))
    if key == "risk_score_reference":
        return read_json(path)["reference_version"]
    if key == "risk_score_bands":
        return ";".join(sorted(pd.read_csv(path).reference_version.dropna().unique()))
    if key == "p8_summary":
        return ";".join(sorted(pd.read_csv(path, usecols=["phase8_version"]).phase8_version.dropna().unique()))
    if key == "analytical_contract":
        return read_json(path)["contract_version"]
    return None


def build_manifest(o2x: dict) -> dict:
    p8 = read_json(ROOT / artifact("p8_run_manifest")["path"])
    validated = p8["inputs_sha256"]
    rows = []
    for a in ARTIFACTS:
        p = ROOT / a["path"]
        h = sha256(p)
        rows.append({**a, "sha256": h, "bytes": p.stat().st_size, "version": _version(a["key"], p),
                     "schema": _schema(p),
                     "matches_phase8_validated_input": (h == validated[a["path"]]) if a["path"] in validated else None})
    bad = [r["path"] for r in rows if r["matches_phase8_validated_input"] is False]
    if bad:
        raise RuntimeError(f"artifacts differ from the inputs Phase 8 validated: {bad}")
    contract = read_json(CONTRACT_FILE)
    if p8["config"]["min_events_primary"] != contract["revalidation"]["minimum_evaluable_events_for_revalidation"]:
        raise RuntimeError("analytical_contract revalidation threshold differs from Phase 8 min_events_primary")
    return {"phase9_version": VERSION, "artifacts": rows, "o2_excluded_materialisation": o2x,
            "phase8_git_commit": p8.get("git_commit"),
            "note": "hashes are generated from the files; the API refuses analytical requests if any file differs"}


def main() -> dict:
    o2x = materialise_o2x()
    m = build_manifest(o2x)
    write_json(MANIFEST_FILE, m)
    return m


if __name__ == "__main__":
    man = main()
    print(f"wrote {MANIFEST_FILE.relative_to(ROOT)}: {len(man['artifacts'])} artifacts; O2x {man['o2_excluded_materialisation']}")
