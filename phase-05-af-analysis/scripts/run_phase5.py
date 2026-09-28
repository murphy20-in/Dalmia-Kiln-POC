"""Run the complete Phase 5 pipeline (gate G7 - reproducibility).

  ../../.venv/bin/python run_phase5.py            # re-run every step (previous outputs used for the determinism check)
  ../../.venv/bin/python run_phase5.py --clean    # delete Phase 5 outputs/, reports/, cache/ first

The source directory is hashed (sha256, size, mtime) before and after the run and never written. Phase 1-4 outputs, the
Phase 3 / Phase 4 scripts, tests, cache and reports (files and directory listings) and data/ are snapshotted before and
after (Phase 5 writes nothing upstream). Determinism: SHA-256 of the key outputs of the previous run (if any) is compared
with the new run. Subprocesses use fixed argument lists (no shell), PYTHONDONTWRITEBYTECODE=1 and single-threaded BLAS.
Nothing uses the network.
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

from af_core import CACHE, CURATED, OUT, P1_OUT, P2_OUT, P3_DIR, P4_DIR, PROCESSED, RAW, REPORTS, SOURCE_ROOT, log, sha256

lg = log("run_phase5")
HERE = Path(__file__).parent
SERIAL_1 = ["load_phase5_inputs.py", "build_afr_inventory.py", "profile_afr_quality.py", "build_afr_operating_bands.py",
            "detect_afr_transitions.py"]
PARALLEL = ["analyze_afr_load.py", "analyze_afr_combustion.py", "analyze_afr_thermal.py", "analyze_afr_efficiency.py",
            "analyze_afr_leading_indicators.py", "matched_analysis.py"]
SERIAL_2 = ["sensitivity_analysis.py", "validate_af_analysis.py"]
DETERMINISM = ["afr_inventory.csv", "afr_data_quality.csv", "afr_operating_bands.csv", "afr_daily_summary.csv",
               "afr_monthly_summary.csv", "afr_transition_episodes.parquet", "afr_load_relationships.csv",
               "afr_combustion_relationships.csv", "afr_thermal_relationships.csv", "afr_efficiency_relationships.csv",
               "afr_indicator_relationships.csv", "afr_matched_analysis.csv", "afr_sensitivity_analysis.csv",
               "afr_data_requirements.csv", "afr_version_manifest.csv"]
REPORT_FILES = ["PHASE_5_ALTERNATIVE_FUEL_ANALYSIS.md", "PHASE_5_ALTERNATIVE_FUEL_ANALYSIS.html"]
FIRST_PASS = REPORTS / ".report_first_pass.sha256.json"   # report hashes BEFORE the G7 rows exist (comparable across runs)
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
       "MKL_NUM_THREADS": "1"}


def file_hash(p: Path) -> str | None:
    """Content hash. Manifest code_sha256 rows (change with code edits) and the report lines carrying the G7 runtime /
    determinism evidence (change with wall-clock and with the previous run) are excluded."""
    if not p.exists():
        return None
    data = p.read_bytes()
    if p.name == "afr_version_manifest.csv":
        data = b"\n".join(line for line in data.split(b"\n") if not line.startswith(b"code_sha256:"))
    return hashlib.sha256(data).hexdigest()


def upstream_snapshot() -> dict:
    snap = {}
    for d in (P1_OUT, P2_OUT, P3_DIR / "outputs", P4_DIR / "outputs"):
        snap.update({f"{d.parent.name}/{p.name}": sha256(p) for p in sorted(d.glob("*")) if p.is_file()})
    for base in (P3_DIR, P4_DIR):
        for d in (base / "scripts", base / "tests", base / "cache", base / "reports"):
            snap.update({str(p.relative_to(base.parent)): (p.stat().st_size, p.stat().st_mtime_ns)
                         for p in sorted(d.rglob("*")) if p.is_file()})
            snap[f"{d.relative_to(base.parent)}::dirs"] = tuple(sorted(str(p.relative_to(d)) for p in d.rglob("*")
                                                                         if p.is_dir()))
    for d in (PROCESSED, CURATED, RAW):
        snap.update({f"{d.name}/{p.name}": (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.glob("*"))
                     if p.is_file()})
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
    lg.info("[clean] removed Phase 5 outputs/, reports/, cache/")


def run(cmd: list[str]) -> int:
    t = time.time()
    lg.info("[run] %s", " ".join(cmd))
    r = subprocess.run([sys.executable, *cmd], cwd=HERE, env=ENV, check=False)
    lg.info("      done in %.0fs (exit %d)", time.time() - t, r.returncode)
    return r.returncode


def run_parallel(scripts: list[str]) -> list[str]:
    """Independent analysis steps (disjoint outputs) run concurrently; logs in cache/log_<script>.txt."""
    t = time.time()
    logs = {s: open(CACHE / f"log_{s}.txt", "w") for s in scripts}
    procs = {s: subprocess.Popen([sys.executable, s], cwd=HERE, env=ENV, stdout=logs[s], stderr=subprocess.STDOUT)
             for s in scripts}
    failed = [s for s, p in procs.items() if p.wait() != 0]
    for f in logs.values():
        f.close()
    lg.info("[parallel] %d steps done in %.0fs; failed %s", len(scripts), time.time() - t, failed)
    return failed


def main():
    prev = {n: file_hash(OUT / n) for n in DETERMINISM}
    prev.update(json.loads(FIRST_PASS.read_text()) if FIRST_PASS.exists() else {})
    if "--clean" in sys.argv:
        clean()
    t0 = time.time()
    before, up_before = source_snapshot(), upstream_snapshot()
    for s in SERIAL_1:
        if run([s]) != 0:
            sys.exit(f"step {s} failed")
    if run_parallel(PARALLEL):
        sys.exit("parallel analysis step failed (see cache/log_*.txt)")
    for s in SERIAL_2:
        if run([s]) != 0:
            sys.exit(f"step {s} failed")
    if run(["generate_report.py"]) != 0:              # writes the version manifest; regenerated below with G7
        sys.exit(1)
    first = {n: file_hash(REPORTS / n) for n in REPORT_FILES}
    FIRST_PASS.write_text(json.dumps(first, indent=1, sort_keys=True))
    v = pd.read_csv(OUT / "afr_validation.csv")

    def add(check: str, ok: bool, ev: str, result: str | None = None, kind: str = "INDEPENDENT"):
        v.loc[len(v)] = {"gate": "G7 reproducibility", "check": check, "check_type": kind,
                         "result": result or ("PASS" if ok else "FAIL"), "evidence": ev}
    add("All pipeline steps completed without manual intervention", True,
        " -> ".join(SERIAL_1 + ["[" + ", ".join(PARALLEL) + "]"] + SERIAL_2 + ["generate_report.py"]))
    rc = run(["-m", "unittest", "discover", "-s", str(HERE.parent / "tests")])
    add("Unit tests pass (value classes, bands, runs, transitions, episode windows, matching, shifts, evidence rules, "
        "wording scanner, leakage, imports)", rc == 0, f"unittest exit code {rc}")
    compared = {n: (prev[n], file_hash(OUT / n)) for n in DETERMINISM if prev[n]}
    compared.update({n: (prev[n], first[n]) for n in REPORT_FILES if prev.get(n)})
    expected = DETERMINISM + REPORT_FILES
    diff = [n for n, (a, b) in compared.items() if a != b]
    missing = [n for n in expected if n not in compared]
    if not compared:
        add("Key outputs byte-identical to the previous run (determinism)", False,
            "no previous run to compare: run `run_phase5.py --clean` a second time to verify", result="NOT_MET_REPORTED")
    else:
        # report files are compared as of the first generate_report pass (before the G7 rows exist in both runs)
        add("Key outputs and reports byte-identical to the previous run (determinism; every key output compared)",
            not diff and not missing, f"{len(compared)}/{len(expected)} files compared; differing: {diff}; "
            f"not compared: {missing}")
    after, up_after = source_snapshot(), upstream_snapshot()
    ch = [k for k in up_before if up_before[k] != up_after.get(k)] + sorted(set(up_after) - set(up_before))
    add("Phase 1-4 outputs, Phase 3 / 4 scripts, tests, cache and reports (incl. directory listings: no __pycache__, no "
        "recreated cache) and data/ unchanged during the run (G1)", not ch, f"{len(up_before)} entries; changed/added {ch[:10]}")
    add("Source directory unchanged during the run (sha256, size, mtime)", before == after,
        f"{len(before)} files; {sum(before[k] != after.get(k) for k in before)} changed, {len(set(after) - set(before))} added")
    add("Runtime recorded", True, f"{time.time() - t0:.0f} s", kind="INFO", result="INFO")
    v.to_csv(OUT / "afr_validation.csv", index=False)
    if run(["generate_report.py"]) != 0:
        sys.exit(1)
    fails = int((v.result == "FAIL").sum())
    lg.info("[done] %.0fs; %d validation rows: %s", time.time() - t0, len(v), v.result.value_counts().to_dict())
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
