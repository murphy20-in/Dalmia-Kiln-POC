"""Run the complete Phase 3 pipeline (gate G7 - reproducibility).

  ../../.venv/bin/python run_phase3.py            # reuse cache
  ../../.venv/bin/python run_phase3.py --clean    # delete Phase 3 outputs/, reports/, cache/ first

The source directory is hashed (sha256, size, mtime) before and after the run and never written. Phase 3 writes
only under phase-03-efficiency-kpi/. Determinism: SHA-256 of the key outputs of the previous run (if any) is compared
with the new run. Nothing is sent over the network.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from p3common import CACHE, OUT, P2_OUT, PROCESSED, CURATED, REPORTS, ROOT, SOURCE_ROOT, log, sha256

lg = log("run_phase3")
HERE = Path(__file__).parent
STEPS = ["load_phase2_inputs.py", "build_training_window.py", "select_kpi_candidates.py", "calculate_component_scores.py",
         "calculate_persistence.py", "calculate_efficiency_kpi.py", "sensitivity_analysis.py", "validate_kpi.py"]
DETERMINISM = ["kpi_candidate_inventory.csv", "kpi_excluded_candidates.csv", "kpi_training_windows.csv", "kpi_reference.json",
               "kpi_component_scores.parquet", "efficiency_deterioration_kpi.parquet", "kpi_reference_bands.csv",
               "kpi_sensitivity_analysis.csv", "kpi_data_quality.csv", "kpi_version_manifest.csv", "kpi_validation.csv"]


def file_hash(p: Path) -> str | None:
    """Content hash; for the version manifest the code_sha256 rows are excluded (they change with any code edit
    and would make the determinism check fail for a reason unrelated to the outputs)."""
    if not p.exists():
        return None
    data = p.read_bytes()
    if p.name == "kpi_version_manifest.csv":
        data = b"\n".join(l for l in data.split(b"\n") if not l.startswith(b"code_sha256:"))
    return hashlib.sha256(data).hexdigest()


def upstream_snapshot() -> dict:
    """Phase 2 outputs (sha256) and data/processed|curated (size, mtime) - Phase 3 must not write there."""
    snap = {f"p2/{p.name}": sha256(p) for p in sorted(P2_OUT.glob("*.csv"))}
    for d in (PROCESSED, CURATED, ROOT / "data" / "raw"):
        snap.update({f"{d.name}/{p.name}": (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(d.glob("*")) if p.is_file()})
    return snap


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
    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)
    lg.info("[clean] removed Phase 3 outputs/, reports/, cache/")


def run(cmd: list[str]) -> int:
    t = time.time()
    lg.info("[run] %s", " ".join(cmd))
    r = subprocess.run([sys.executable, *cmd], cwd=HERE)
    lg.info("      done in %.0fs (exit %d)", time.time() - t, r.returncode)
    return r.returncode


def main():
    prev = {n: file_hash(OUT / n) for n in DETERMINISM}
    if "--clean" in sys.argv:
        clean()
    t0 = time.time()
    before = snapshot()
    up_before = upstream_snapshot()
    for s in STEPS:
        if run([s]) != 0:
            lg.error("step %s failed", s)
            sys.exit(1)
    v = pd.read_csv(OUT / "kpi_validation.csv")

    def add(check: str, ok: bool, ev: str):
        v.loc[len(v)] = ["G7 reproducibility", check, "PASS" if ok else "FAIL", ev]
    add("All pipeline steps completed without manual intervention", True, " -> ".join(STEPS))
    rc = run(["-m", "unittest", "discover", "-s", str(HERE.parent / "tests")])
    add("Unit tests pass (normalisation, masking, rolling, persistence, scoring, aggregation, training separation, "
        "scaling, missing data, stopped / transition state, future-data leakage)", rc == 0, f"unittest exit code {rc}")
    compared = {n: (prev[n], file_hash(OUT / n)) for n in DETERMINISM if prev[n] and n != "kpi_validation.csv"}
    diff = [n for n, (a, b) in compared.items() if a != b]
    add("Key outputs byte-identical to the previous run (determinism)", not diff if compared else True,
        f"{len(compared)} files compared; differing: {diff}" if compared else "no previous run to compare (first run)")
    v.to_csv(OUT / "kpi_validation.csv", index=False)
    add("Report generator completed", run(["generate_report.py"]) == 0, "generate_report.py exit code")
    for p in (REPORTS / "PHASE_3_EFFICIENCY_DETERIORATION_KPI.md", REPORTS / "PHASE_3_EFFICIENCY_DETERIORATION_KPI.html"):
        add(f"Generated {p.name}", p.exists() and p.stat().st_size > 0, f"{p.stat().st_size if p.exists() else 0} bytes")
    after = snapshot()
    up_after = upstream_snapshot()
    add("Phase 2 outputs and data/ unchanged during the run (G2: Phase 3 wrote nothing upstream)", up_before == up_after,
        f"{len(up_before)} files; changed {[k_ for k_ in up_before if up_before[k_] != up_after.get(k_)]}")
    add("Source directory unchanged during the run (sha256, size, mtime)", before == after,
        f"{sum(before[k] != after.get(k) for k in before)} changed, {len(set(after) - set(before))} added")
    v.to_csv(OUT / "kpi_validation.csv", index=False)
    if run(["generate_report.py"]) != 0:            # final report includes the G7 rows
        v.loc[len(v)] = ["G7 reproducibility", "Final report regenerated with G7 rows", "FAIL", "generate_report.py failed"]
        v.to_csv(OUT / "kpi_validation.csv", index=False)
    fails = int((v.result == "FAIL").sum())
    lg.info("[done] %.0fs; %d validation checks, %d failures", time.time() - t0, len(v), fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
