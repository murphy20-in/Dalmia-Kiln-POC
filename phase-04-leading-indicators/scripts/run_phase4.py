"""Run the complete Phase 4 pipeline (gate G7 - reproducibility).

  ../../.venv/bin/python run_phase4.py            # reuse cache
  ../../.venv/bin/python run_phase4.py --clean    # delete Phase 4 outputs/, reports/, cache/ first

The source directory is hashed (sha256, size, mtime) before and after the run and never written. Phase 1 / 2 / 3 outputs,
Phase 3 scripts / tests / cache and data/ are snapshotted before and after (Phase 4 must write nothing upstream).
Determinism: SHA-256 of the key outputs of the previous run (if any) is compared with the new run. Every subprocess runs
with PYTHONDONTWRITEBYTECODE=1 (no __pycache__ in phase-03). Nothing is sent over the network.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from p4common import CACHE, CURATED, OUT, P1_OUT, P2_OUT, P3_DIR, PROCESSED, RAW, REPORTS, SOURCE_ROOT, log, sha256

lg = log("run_phase4")
HERE = Path(__file__).parent
STEPS = ["load_phase3_inputs.py", "build_indicator_dataset.py", "build_causal_features.py", "calculate_lag_relationships.py",
         "build_indicator_episodes.py", "evaluate_lead_time.py", "sensitivity_analysis.py", "score_indicators.py",
         "validate_indicators.py"]
DETERMINISM = ["indicator_candidate_inventory.csv", "indicator_excluded_candidates.csv", "indicator_data_quality.csv",
               "indicator_feature_reference.json", "indicator_feature_values.parquet", "indicator_lag_analysis.csv",
               "indicator_episodes.csv", "indicator_episode_analysis.parquet", "indicator_lead_time.csv",
               "indicator_sensitivity.csv", "indicator_scores.csv", "leading_indicator_set.csv", "indicator_benchmarks.csv",
               "indicator_version_manifest.csv", "indicator_validation.csv"]
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
       "MKL_NUM_THREADS": "1"}     # no BLAS oversubscription across worker processes (PY-L7); results are unaffected


def file_hash(p: Path) -> str | None:
    """Content hash; code_sha256 rows of the manifest are excluded (they change with any code edit, not with outputs)."""
    if not p.exists():
        return None
    data = p.read_bytes()
    if p.name == "indicator_version_manifest.csv":
        data = b"\n".join(l for l in data.split(b"\n") if not l.startswith(b"code_sha256:"))
    return hashlib.sha256(data).hexdigest()


def upstream_snapshot() -> dict:
    snap = {}
    for d in (P1_OUT, P2_OUT, P3_DIR / "outputs"):
        snap.update({f"{d.parent.name}/{p.name}": sha256(p) for p in sorted(d.glob("*")) if p.is_file()})
    for d in (P3_DIR / "scripts", P3_DIR / "tests", P3_DIR / "cache", P3_DIR / "reports"):
        snap.update({str(p.relative_to(P3_DIR)): (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.rglob("*"))
                     if p.is_file()})
    for d in (PROCESSED, CURATED, RAW):
        snap.update({f"{d.name}/{p.name}": (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.glob("*")) if p.is_file()})
    return snap


def source_snapshot() -> dict:
    return {str(p.relative_to(SOURCE_ROOT)): (sha256(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(SOURCE_ROOT.rglob("*")) if p.is_file()}


def clean():
    for d in (OUT, REPORTS, CACHE):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        if d != CACHE:
            (d / ".gitkeep").touch()
    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)
    lg.info("[clean] removed Phase 4 outputs/, reports/, cache/")


def run(cmd: list[str]) -> int:
    t = time.time()
    lg.info("[run] %s", " ".join(cmd))
    r = subprocess.run([sys.executable, *cmd], cwd=HERE, env=ENV, check=False)
    lg.info("      done in %.0fs (exit %d)", time.time() - t, r.returncode)
    return r.returncode


def main():
    prev = {n: file_hash(OUT / n) for n in DETERMINISM}
    if "--clean" in sys.argv:
        clean()
    t0 = time.time()
    before, up_before = source_snapshot(), upstream_snapshot()
    for s in STEPS:
        if run([s]) != 0:
            lg.error("step %s failed", s)
            sys.exit(1)
    if run(["generate_report.py"]) != 0:              # writes the version manifest; report re-generated below with G7
        sys.exit(1)
    v = pd.read_csv(OUT / "indicator_validation.csv")

    def add(check: str, ok: bool, ev: str, result: str | None = None, kind: str = "INDEPENDENT"):
        v.loc[len(v)] = {"gate": "G7 reproducibility", "check": check, "check_type": kind,
                         "result": result or ("PASS" if ok else "FAIL"), "evidence": ev}
    add("All pipeline steps completed without manual intervention", True, " -> ".join(STEPS + ["generate_report.py"]))
    rc = run(["-m", "unittest", "discover", "-s", str(HERE.parent / "tests")])
    add("Unit tests pass (causal features, windows, targets, controls, statistics, BH, bootstrap, episodes, alarms, "
        "candidate rules, imports)", rc == 0, f"unittest exit code {rc}")
    expected = [n for n in DETERMINISM if n != "indicator_validation.csv"]
    compared = {n: (prev[n], file_hash(OUT / n)) for n in expected if prev[n]}
    diff = [n for n, (a, b) in compared.items() if a != b]
    missing = [n for n in expected if n not in compared]
    if not compared:
        add("Key outputs byte-identical to the previous run (determinism)", False,
            "no previous run to compare: run `run_phase4.py --clean` a second time to verify", result="NOT_MET_REPORTED")
    else:
        add("Key outputs byte-identical to the previous run (determinism; all key outputs must be compared)",
            not diff and not missing, f"{len(compared)}/{len(expected)} files compared; differing: {diff}; not compared: {missing}")
    after, up_after = source_snapshot(), upstream_snapshot()
    ch = [k for k in up_before if up_before[k] != up_after.get(k)] + sorted(set(up_after) - set(up_before))
    add("Phase 1 / 2 / 3 outputs, Phase 3 scripts / tests / cache / reports and data/ unchanged during the run (G1: "
        "Phase 4 wrote nothing upstream, no __pycache__ in phase-03)", not ch, f"{len(up_before)} files; changed/added {ch[:10]}")
    add("Source directory unchanged during the run (sha256, size, mtime)", before == after,
        f"{sum(before[k] != after.get(k) for k in before)} changed, {len(set(after) - set(before))} added")
    add("Runtime recorded", True, f"{time.time() - t0:.0f} s", kind="INFO", result="INFO")
    v.to_csv(OUT / "indicator_validation.csv", index=False)
    if run(["generate_report.py"]) != 0:
        sys.exit(1)
    fails = int((v.result == "FAIL").sum())
    lg.info("[done] %.0fs; %d validation rows: %s", time.time() - t0, len(v), v.result.value_counts().to_dict())
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
