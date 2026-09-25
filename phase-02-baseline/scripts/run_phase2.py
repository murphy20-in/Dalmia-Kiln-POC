"""Run the complete Phase 2 pipeline (GATE 5 - reproducibility).

  python3 run_phase2.py            # reuse the sha256-keyed parse cache
  python3 run_phase2.py --clean    # delete Phase 2 outputs/reports/cache and data/processed|curated parquet first

Use the project virtual environment (pyarrow, matplotlib):
  /home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia-Kiln-POC/.venv/bin/python run_phase2.py --clean
The source directory is never written; it is hashed before and after the run.
Determinism: SHA-256 of key outputs from the previous run (if any) is compared with the new run.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from p2common import OUT, REPORTS, CACHE, PROCESSED, CURATED, SOURCE_ROOT, sha256, log

lg = log("run_phase2")
HERE = Path(__file__).parent
STEPS = ["load_phase1_manifest.py", "build_processed_data.py", "build_quality_masks.py", "analyze_operating_state.py",
         "identify_regimes.py", "calculate_baseline.py", "calculate_stability.py", "analyze_temporal_baseline.py",
         "analyze_multivariate_baseline.py", "build_baseline_reference.py", "validate_phase2.py"]
DETERMINISM = ["processed_dataset_manifest.csv", "baseline_population.csv", "baseline_statistics.csv", "baseline_reference_bands.csv",
               "baseline_stability.csv", "baseline_confidence.csv", "operating_regimes.csv", "operating_state_events.csv",
               "multivariate_baseline.csv", "baseline_temporal_analysis.csv"]


def file_hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def snapshot() -> dict:
    return {str(p.relative_to(SOURCE_ROOT)): (sha256(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(SOURCE_ROOT.rglob("*")) if p.is_file()}


def clean():
    for d in (OUT, REPORTS, CACHE):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        if d != CACHE:
            (d / ".gitkeep").touch()
    for d in (PROCESSED, CURATED):
        for p in d.glob("*.parquet"):
            p.unlink()
    lg.info("[clean] removed Phase 2 outputs/, reports/, cache/ and data/processed|curated/*.parquet")


def run(script: str):
    t = time.time()
    lg.info("[run] %s", script)
    subprocess.run([sys.executable, script], cwd=HERE, check=True)
    lg.info("      %s done in %.0fs", script, time.time() - t)


def main():
    prev = {n: file_hash(OUT / n) for n in DETERMINISM}
    if "--clean" in sys.argv:
        clean()
    t0 = time.time()
    before = snapshot()
    for s in STEPS:
        run(s)
    v = pd.read_csv(OUT / "phase2_validation.csv")

    def add(check: str, ok: bool, ev: str):
        v.loc[len(v)] = ["G5 reproducibility", check, "PASS" if ok else "FAIL", ev]
    add("All pipeline steps completed without manual intervention", True, " -> ".join(STEPS))
    compared = {n: (prev[n], file_hash(OUT / n)) for n in DETERMINISM if prev[n]}
    diff = [n for n, (a, b) in compared.items() if a != b]
    add("Key outputs byte-identical to the previous run (determinism)", not diff if compared else True,
        f"{len(compared)} files compared; differing: {diff}" if compared else "no previous run to compare (first run)")
    v.to_csv(OUT / "phase2_validation.csv", index=False)
    run("generate_report.py")
    for p in (REPORTS / "PHASE_2_NORMAL_OPERATING_BASELINE.md", REPORTS / "PHASE_2_NORMAL_OPERATING_BASELINE.html"):
        add(f"Generated {p.name}", p.exists() and p.stat().st_size > 0, f"{p.stat().st_size if p.exists() else 0} bytes")
    after = snapshot()
    add("Source directory unchanged during the run (sha256, size, mtime)", before == after,
        f"{sum(before[k] != after.get(k) for k in before)} changed, {len(set(after) - set(before))} added")
    v.to_csv(OUT / "phase2_validation.csv", index=False)
    fails = int((v.result == "FAIL").sum())
    lg.info("[done] %.0fs; %d validation checks, %d failures", time.time() - t0, len(v), fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
