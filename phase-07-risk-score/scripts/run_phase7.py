"""Run the complete Phase 7 pipeline (gate G8 - reproducibility; run-time part of G1).

  ../../.venv/bin/python run_phase7.py            # re-run every step (previous outputs used for the determinism check)
  ../../.venv/bin/python run_phase7.py --clean    # delete Phase 7 outputs/, reports/, cache/ first

The source directory is hashed (sha256, size, mtime) before and after the run and never written. Phase 1-6 outputs, the
Phase 3-6 scripts, tests, cache and reports (files and directory listings) and data/ are snapshotted before and after
(Phase 7 writes nothing upstream). Determinism: SHA-256 of every key output (and the report before the G8 rows exist) of
the previous run is compared with the new run. Subprocesses use fixed argument lists (no shell), PYTHONDONTWRITEBYTECODE=1
and single-threaded BLAS. Nothing uses the network. Only phase-07-risk-score/{outputs,reports,cache} are ever deleted.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from common import CACHE, OUT, P1_OUT, P2_OUT, P3_DIR, P4_DIR, P6_DIR, PHASE_DIR, PROCESSED, REPORTS, ROOT, SOURCE_ROOT, \
    forbidden_hits, log, sha256

lg = log("run_phase7")
HERE = Path(__file__).parent
STEPS = ["feature_engineering.py", "reference_builder.py", "calibration.py", "robustness.py", "validation.py",
         "report_generation.py"]
DETERMINISM = ["risk_scores.parquet", "risk_score_diagnostics.parquet", "risk_score_variant_references.json",
               "risk_score_components.parquet", "risk_score_reasons.parquet",
               "risk_score_confidence.parquet", "risk_score_feature_inventory.csv", "risk_score_reference.json",
               "risk_score_bands.csv", "risk_score_calibration.csv", "risk_score_robustness.csv",
               "risk_score_data_quality.csv", "risk_score_event_similarity.csv", "risk_score_summary.csv"]
REPORT_FILES = ["PHASE_7_RISK_SCORE_REPORT.md", "PHASE_7_RISK_SCORE_REPORT.html"]
FIRST_PASS = REPORTS / ".report_first_pass.sha256.json"   # report hashes BEFORE the G8 rows exist (comparable across runs)
P5_DIR = ROOT / "phase-05-af-analysis"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
       "MKL_NUM_THREADS": "1"}
OWNED = (OUT, REPORTS, CACHE)


def file_hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def upstream_snapshot() -> dict:
    snap = {}
    for d in (P1_OUT, P2_OUT, P3_DIR / "outputs", P4_DIR / "outputs", P5_DIR / "outputs", P6_DIR / "outputs"):
        snap.update({f"{d.parent.name}/{p.name}": sha256(p) for p in sorted(d.glob("*")) if p.is_file()})
    for base in (P3_DIR, P4_DIR, P5_DIR, P6_DIR):
        for d in (base / "scripts", base / "tests", base / "cache", base / "reports"):
            if not d.exists():
                continue
            snap.update({str(p.relative_to(base.parent)): (p.stat().st_size, p.stat().st_mtime_ns)
                         for p in sorted(d.rglob("*")) if p.is_file()})
            snap[f"{d.relative_to(base.parent)}::dirs"] = tuple(sorted(str(p.relative_to(d)) for p in d.rglob("*")
                                                                     if p.is_dir()))
    for d in (PROCESSED, ROOT / "data" / "curated", ROOT / "data" / "raw"):
        snap.update({f"{d.name}/{p.name}": (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.glob("*"))
                     if p.is_file()})
    return snap


def source_snapshot() -> dict:
    return {str(p.relative_to(SOURCE_ROOT)): (sha256(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(SOURCE_ROOT.rglob("*")) if p.is_file()}


def clean():
    for d in OWNED:
        if d.resolve().parent != PHASE_DIR.resolve():        # guard: never delete anything outside Phase 7
            raise RuntimeError(f"refusing to delete {d}")
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        if d != CACHE:
            (d / ".gitkeep").touch()
    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)
    lg.info("[clean] removed Phase 7 outputs/, reports/, cache/")


def run(cmd: list[str]) -> int:
    t = time.time()
    lg.info("[run] %s", " ".join(cmd))
    r = subprocess.run([sys.executable, "-B", *cmd], cwd=HERE, env=ENV, check=False)
    lg.info("      done in %.0fs (exit %d)", time.time() - t, r.returncode)
    return r.returncode


def main():
    prev = {n: file_hash(OUT / n) for n in DETERMINISM}
    prev.update(json.loads(FIRST_PASS.read_text(encoding="utf-8")) if FIRST_PASS.exists() else {})
    if "--clean" in sys.argv:
        clean()
    t0 = time.time()
    before, up_before = source_snapshot(), upstream_snapshot()
    for s in STEPS:
        if run([s]) != 0:
            sys.exit(f"step {s} failed")
    first = {n: file_hash(REPORTS / n) for n in REPORT_FILES}
    FIRST_PASS.write_text(json.dumps(first, indent=1, sort_keys=True), encoding="utf-8")
    v = pd.read_csv(OUT / "risk_score_validation.csv")

    def add(gate: str, check: str, ok: bool, ev: str, result: str | None = None, kind: str = "INDEPENDENT"):
        v.loc[len(v)] = {"gate": gate, "check": check, "check_type": kind,
                         "result": result or ("PASS" if ok else "FAIL"), "evidence": ev}
    add("G8 reproducibility", "All pipeline steps completed without manual intervention", True, " -> ".join(STEPS))
    rc = run(["-m", "unittest", "discover", "-s", str(HERE.parent / "tests"), "-t", str(HERE.parent / "tests")])
    add("G8 reproducibility", "Unit tests pass (core score, confidence, temporal leakage, feature engineering, "
        "calibration, robustness, reproducibility)", rc == 0, f"unittest exit code {rc}")
    compared = {n: (prev[n], file_hash(OUT / n)) for n in DETERMINISM if prev[n]}
    compared.update({n: (prev[n], first[n]) for n in REPORT_FILES if prev.get(n)})
    expected = DETERMINISM + REPORT_FILES
    diff = [n for n, (a, b) in compared.items() if a != b]
    missing = [n for n in expected if n not in compared]
    if not compared:
        add("G8 reproducibility", "Key outputs byte-identical to the previous run (determinism)", False,
            "no previous run to compare: run `run_phase7.py --clean` a second time to verify", result="NOT_MET_REPORTED")
    else:
        add("G8 reproducibility", "Key outputs and first-pass reports byte-identical to the previous run (determinism; "
            "every key output compared)", not diff and not missing,
            f"{len(compared)}/{len(expected)} files compared; differing: {diff}; not compared: {missing}")
    after, up_after = source_snapshot(), upstream_snapshot()
    ch = [k for k in up_before if up_before[k] != up_after.get(k)] + sorted(set(up_after) - set(up_before))
    add("G1 source integrity", "Phase 1-6 outputs, Phase 3-6 scripts / tests / cache / reports (incl. directory "
        "listings: no __pycache__) and data/ unchanged during the run", not ch,
        f"{len(up_before)} entries; changed/added {ch[:10]}")
    add("G1 source integrity", "Source directory unchanged during the run (sha256, size, mtime)", before == after,
        f"{len(before)} files; {sum(before[k] != after.get(k) for k in before)} changed, "
        f"{len(set(after) - set(before))} added")
    hits = forbidden_hits((REPORTS / REPORT_FILES[0]).read_text(encoding="utf-8"))
    add("G6 empirical period coverage", "Unsupported-claim scan of the generated report", not hits, f"hits {hits[:5]}")
    v.to_csv(OUT / "risk_score_validation.csv", index=False)
    if run(["report_generation.py"]) != 0:
        sys.exit(1)
    fails = int((v.result == "FAIL").sum())
    lg.info("[done] %.0fs; %d validation rows: %s", time.time() - t0, len(v), v.result.value_counts().to_dict())
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
