"""Phase 9 orchestrator: validate, build, serve, test, compare, report. Exits non-zero if any gate fails.

    cd phase-09-api/scripts && ../../.venv/bin/python -B run_phase9.py --clean     # run twice for G11

--clean deletes phase-09-api/outputs and reports only. The plant event store (phase-09-api/state/, or
DALMIA_KILN_EVENTS_DB) is never deleted: every service check here uses a throwaway database.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True

import pandas as pd  # noqa: E402

from p9common import (CONTRACT_FILE, DOCS, MANIFEST_FILE, OUT, PHASE_DIR, REPORTS, ROOT, SOURCE_ROOT, VERSION,  # noqa: E402
                      ServiceConfig, read_json, review_rows, sha256, write_json)

HERE = Path(__file__).parent
PY = sys.executable
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
CACHE = PHASE_DIR / "cache"
PREVIOUS = CACHE / "previous_run.sha256.json"
UPSTREAM = tuple(f"phase-0{i}-" for i in range(1, 9))
REQUIRED_DOCS = ("API_CONTRACT.md", "API_USAGE.md", "ANALYTICAL_SEMANTICS.md", "EVENT_ANNOTATION.md", "LIMITATIONS.md",
                 "DATA_LINEAGE.md")
REQUIRED_REVIEWERS = {"planner", "python-reviewer", "mle-reviewer", "cs-product-analyst", "database-reviewer"}
TEST_GATES = {"test_contract": ("G3", "G4", "G9", "G10"), "test_integrity": ("G2", "G5"), "test_events": ("G6",),
              "test_safety": ("G7",), "test_security": ("G8",)}
DETERMINISTIC_QUERIES = (
    ("/api/v1/metadata", ""), ("/api/v1/metadata/provenance", ""), ("/api/v1/metadata/limitations", ""),
    ("/api/v1/metadata/methodology", ""), ("/api/v1/metadata/data-requirements", ""),
    ("/api/v1/risk-scores", "limit=5000"), ("/api/v1/risk-scores", "limit=5000&offset=5000"),
    ("/api/v1/risk-scores", "variant=o2_excluded&limit=5000"),
    ("/api/v1/risk-scores", "variant=o2_excluded&limit=5000&offset=5000"),
    ("/api/v1/risk-scores/variant-comparison", "limit=5000"),
    ("/api/v1/risk-scores/variant-comparison", "limit=5000&offset=5000"), ("/api/v1/abnormal-periods", ""),
    ("/api/v1/validation/early-warning-historical", ""), ("/api/v1/findings", ""))
lg = logging.getLogger("run_phase9")


# ============================================================================== helpers
def snapshot() -> dict:
    """SHA-256 of every file under Phases 1-8 and data/ (bytecode caches excluded)."""
    out = {}
    for d in sorted(p for p in ROOT.iterdir() if p.is_dir() and (p.name.startswith(UPSTREAM) or p.name == "data")):
        for f in sorted(d.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                out[str(f.relative_to(ROOT))] = sha256(f)
    return out


def source_check() -> dict:
    man = pd.read_csv(ROOT / "data/raw/source_manifest.csv", usecols=["relative_path", "sha256"])
    bad = [r.relative_path for r in man.itertuples(index=False)
           if not (SOURCE_ROOT / r.relative_path).is_file() or sha256(SOURCE_ROOT / r.relative_path) != r.sha256]
    return {"files": len(man), "mismatched": bad}


def git_clean(*paths: str) -> bool:
    r = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == ""


def call(app, path: str, query: str = "", method: str = "GET", body=None, headers=None):
    raw = json.dumps(body).encode() if body is not None else b""
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query, "wsgi.input": io.BytesIO(raw),
           "CONTENT_LENGTH": str(len(raw)) if raw else "", "CONTENT_TYPE": "application/json", **(headers or {})}
    got = {}
    out = b"".join(app(env, lambda s, h: got.update(s=s)))
    return int(got["s"].split()[0]), out


def timed(fn, n: int) -> float:
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(ts), 2)


# ============================================================================== steps
def validate_config() -> dict:
    state = read_json(CONTRACT_FILE)["analytical_state"]
    return {"root_is_dir": ROOT.is_dir(), "root_env_var": "DALMIA_KILN_POC_ROOT",
            "analytical_state_all_false": bool(state) and all(v is False for v in state.values())}


def build() -> dict:
    """Manifest + O2x materialisation in a child process (it runs Phase 7 / 8 scoring code; this process only imports
    Phase 8's wording scanner, in docs_check)."""
    r = subprocess.run([PY, "-B", "build_artifacts.py"], cwd=HERE, env=ENV, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"build_artifacts failed:\n{r.stderr[-3000:]}")
    man = read_json(MANIFEST_FILE)
    import artifact_store as ast_
    need = {"risk_scores": ast_.SCORE_COLS, "risk_score_confidence": ast_.CONF_COLS,
            "risk_score_components": ast_.COMP_COLS, "abnormal_episodes": ast_.PERIOD_COLS,
            "p8_horizon": ast_.HORIZON_COLS}
    missing = {a["key"]: sorted(set(need[a["key"]]) - set(a["schema"] or {}))
               for a in man["artifacts"] if a["key"] in need}
    return {"artifacts": len(man["artifacts"]), "schema_missing_columns": {k: v for k, v in missing.items() if v},
            "matches_phase8_validated_inputs": [a["key"] for a in man["artifacts"]
                                                if a["matches_phase8_validated_input"]],
            "phase6_7_all_match_phase8_inputs": all(a["matches_phase8_validated_input"] for a in man["artifacts"]
                                                    if a["source_phase"] in (6, 7)),
            "o2x": man["o2_excluded_materialisation"]}


def service_checks() -> dict:
    """Init the service on a throwaway event DB: startup, latencies, memory, result digests, loopback socket smoke."""
    import api_app
    logging.getLogger("p9.api").setLevel(logging.WARNING)
    with tempfile.TemporaryDirectory() as tmp:
        t = time.perf_counter()
        app = api_app.App(ServiceConfig(root=ROOT, events_db=Path(tmp) / "events.sqlite3"))
        startup = time.perf_counter() - t
        if app.store is None:
            raise SystemExit(f"service not ready: {app.store_error}")
        lat = {
            "metadata_ms": timed(lambda: call(app, "/api/v1/metadata"), 50),
            "risk_scores_1000_rows_ms": timed(lambda: call(app, "/api/v1/risk-scores", "limit=1000"), 10),
            "risk_scores_one_day_ms": timed(lambda: call(app, "/api/v1/risk-scores",
                                                         "start=2025-07-01T00:00:00&end=2025-07-02T00:00:00"), 30),
            "variant_comparison_1000_rows_ms": timed(lambda: call(app, "/api/v1/risk-scores/variant-comparison",
                                                                  "limit=1000"), 10),
            "abnormal_periods_ms": timed(lambda: call(app, "/api/v1/abnormal-periods"), 50),
            "validation_ms": timed(lambda: call(app, "/api/v1/validation/early-warning-historical"), 20)}
        hdr, ids = {"HTTP_X_ACTOR": "run_phase9"}, []

        def create():
            n = len(ids)
            _, b = call(app, "/api/v1/events", method="POST", headers=hdr, body={
                "event_type": "OTHER", "start_time": f"2024-01-01T00:00:{n % 60:02d}", "description": "latency probe",
                "source": "OTHER", "equipment": f"probe-{n}"})
            ids.append(json.loads(b)["data"]["event_id"])
        lat["event_create_ms"] = timed(create, 30)
        lat["event_get_ms"] = timed(lambda: call(app, f"/api/v1/events/{ids[0]}"), 30)
        lat["event_list_ms"] = timed(lambda: call(app, "/api/v1/events"), 30)
        sev = iter(["MINOR", "MAJOR"] * 20)
        lat["event_patch_ms"] = timed(lambda: call(app, f"/api/v1/events/{ids[1]}", method="PATCH", headers=hdr,
                                                   body={"severity": next(sev), "expected_version": json.loads(
                                                       call(app, f"/api/v1/events/{ids[1]}")[1])["data"]["version"]}),
                                      20)
        digests = {}
        for p, q in DETERMINISTIC_QUERIES:
            s, b = call(app, p, q)
            if s != 200:
                raise SystemExit(f"{p}?{q} returned {s}")
            digests[f"{p}?{q}"] = hashlib.sha256(b).hexdigest()
        from wsgiref.simple_server import make_server
        sock = {}
        with make_server("127.0.0.1", 0, app, handler_class=api_app.QuietHandler) as httpd:     # real loopback HTTP
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_port}"
            for p in ("/health", "/ready", "/api/v1/metadata/status", "/api/v1/alerts"):
                try:
                    with urllib.request.urlopen(base + p, timeout=10) as r:
                        sock[p] = r.status
                except urllib.error.HTTPError as e:
                    sock[p] = e.code
            httpd.shutdown()
        return {"startup_seconds": round(startup, 2), "latency_median": lat, "socket_smoke": sock,
                "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                "query_digests": digests, "route_contract": api_app.route_contract()}


def run_tests() -> dict:
    out = {}
    for mod in TEST_GATES:
        r = subprocess.run([PY, "-B", "-m", "unittest", mod], cwd=PHASE_DIR / "tests", env=ENV, capture_output=True,
                           text=True)
        m = re.search(r"Ran (\d+) tests?", r.stderr)
        out[mod] = {"ran": int(m.group(1)) if m else 0, "ok": r.returncode == 0,
                    "tail": "" if r.returncode == 0 else r.stderr[-2000:]}
    return out


def docs_check() -> dict:
    sys.path.insert(0, str(ROOT / "phase-08-early-warning/scripts"))
    from p8common import forbidden_hits                                    # Phase 8, read-only
    missing = [d for d in REQUIRED_DOCS if not (DOCS / d).is_file()]
    files = [DOCS / d for d in REQUIRED_DOCS] + [PHASE_DIR / "README.md", CONTRACT_FILE]
    hits = {f.name: h for f in files if f.is_file() and (h := forbidden_hits(f.read_text(encoding="utf-8")))}
    return {"missing": missing + ([] if (PHASE_DIR / "README.md").is_file() else ["README.md"]),
            "wording_hits": hits}


DONE = ("RESOLVED", "ACCEPTED_WITH_REASON", "DEFERRED_WITH_REASON")


def review_check() -> dict:
    rows, pony = review_rows("REVIEW_LOG.md"), review_rows("PONYTAIL_AUDIT_REPORT.md")
    return {"findings": len(rows), "reviewers": sorted({r["Reviewer"] for r in rows} & REQUIRED_REVIEWERS),
            "unresolved": [r["ID"] for r in rows if r["Status"] not in DONE],
            "ponytail_report": (PHASE_DIR / "reviews/PONYTAIL_AUDIT_REPORT.md").is_file(),
            "ponytail_findings": len(pony),
            "ponytail_unresolved": [r["ID"] for r in pony if r["Status"] not in DONE],
            "ponytail_open_critical_high": [r["ID"] for r in pony if r["Severity"] in ("CRITICAL", "HIGH")
                                            and r["Status"] not in DONE]}


def boundary_check() -> dict:
    ui = [str(p.relative_to(PHASE_DIR)) for p in PHASE_DIR.rglob("*")
          if p.suffix in (".html", ".jsx", ".tsx", ".js", ".css", ".vue")]
    return {"frontend_files": ui, "dashboard_dir_untouched": git_clean("dashboard")}


def gate(ok: bool, evidence) -> dict:
    return {"result": "PASS" if ok else "FAIL", "evidence": evidence}


# ============================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stdout)
    t0 = time.time()
    cfg = validate_config()
    if not (cfg["root_is_dir"] and cfg["analytical_state_all_false"]):
        raise SystemExit(f"configuration invalid: {cfg}")
    before, src_before = snapshot(), source_check()
    if a.clean:
        for d in (OUT, REPORTS):
            for f in d.glob("*"):
                if f.name != ".gitkeep":
                    shutil.rmtree(f) if f.is_dir() else f.unlink()
    lg.info("config %s; upstream files %d; source files %d", cfg, len(before), src_before["files"])
    b = build()
    lg.info("manifest: %d artifacts; O2x %s", b["artifacts"], b["o2x"]["status"])
    svc = service_checks()
    write_json(OUT / "api_contract.json", {"service_version": VERSION, "routes": svc.pop("route_contract")})
    lg.info("service: startup %.2fs; socket %s", svc["startup_seconds"], svc["socket_smoke"])
    tests = run_tests()
    lg.info("tests: %s", {k: (v["ran"], v["ok"]) for k, v in tests.items()})
    docs, rev, bnd = docs_check(), review_check(), boundary_check()
    after, src_after = snapshot(), source_check()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    upstream_git = git_clean(*[f"{u}*" for u in UPSTREAM], "data")

    det = {"artifact_manifest.json": sha256(MANIFEST_FILE), "api_contract.json": sha256(OUT / "api_contract.json"),
           "o2_excluded_scores.parquet": sha256(OUT / "o2_excluded_scores.parquet"), **svc["query_digests"]}
    prev = read_json(PREVIOUS) if PREVIOUS.is_file() else None
    diff = sorted(k for k in det if prev and prev["files"].get(k) != det[k])

    def tests_ok(g):
        return all(v["ok"] and v["ran"] > 0 for m, v in tests.items() if g in TEST_GATES[m])
    G = {
        "G1 REPOSITORY INTEGRITY": gate(not changed and not src_after["mismatched"] and upstream_git and
                                        not src_before["mismatched"],
                                        {"upstream_files_hashed": len(after), "changed": changed[:20],
                                         "source_files": src_after["files"], "source_mismatched": src_after["mismatched"],
                                         "git_upstream_clean": upstream_git}),
        "G2 ARTIFACT INTEGRITY": gate(b["phase6_7_all_match_phase8_inputs"] and not b["schema_missing_columns"]
                                      and b["o2x"]["status"] == "VERIFIED_AGAINST_PHASE8" and tests_ok("G2"),
                                      {"phase8_validated_matches": len(b["matches_phase8_validated_inputs"]),
                                       "schema_missing": b["schema_missing_columns"], "o2x": b["o2x"]}),
        "G3 API CONTRACT": gate(tests_ok("G3"), {"routes": "outputs/api_contract.json",
                                                 "tests": tests["test_contract"]["ran"]}),
        "G4 PROVENANCE": gate(tests_ok("G4"), "every analytical response carries provenance (test_contract)"),
        "G5 TEMPORAL INTEGRITY": gate(tests_ok("G5"), {"tests": tests["test_integrity"]["ran"]}),
        "G6 EVENT ISOLATION": gate(tests_ok("G6"), {"tests": tests["test_events"]["ran"]}),
        "G7 SAFETY": gate(tests_ok("G7") and svc["socket_smoke"].get("/api/v1/alerts") == 404,
                          {"tests": tests["test_safety"]["ran"], "alerts_route": svc["socket_smoke"].get("/api/v1/alerts")}),
        "G8 SECURITY": gate(tests_ok("G8"), {"tests": tests["test_security"]["ran"]}),
        "G9 ERROR HANDLING": gate(tests_ok("G9"), "structured errors 400/404/405/409/413/415/422/500/503"),
        "G10 OBSERVABILITY": gate(tests_ok("G10") and all(v == 200 for k, v in svc["socket_smoke"].items()
                                                          if k != "/api/v1/alerts"),
                                  {"socket_smoke": svc["socket_smoke"], "latency_median": svc["latency_median"]}),
        "G11 DETERMINISM": gate(bool(a.clean and prev and prev.get("clean")) and not diff,
                                {"compared": len(det), "differing": diff, "previous_run_clean": bool(prev and
                                                                                                     prev.get("clean")),
                                 "this_run_clean": a.clean}),
        "G12 DOCUMENTATION": gate(not docs["missing"] and not docs["wording_hits"], docs),
        "G13 REVIEW": gate(rev["findings"] > 0 and not rev["unresolved"] and set(rev["reviewers"]) == REQUIRED_REVIEWERS,
                           {k: rev[k] for k in ("findings", "reviewers", "unresolved")}),
        "G14 PONYTAIL": gate(rev["ponytail_report"] and rev["ponytail_findings"] > 0
                             and not rev["ponytail_open_critical_high"] and not rev["ponytail_unresolved"],
                             {k: rev[k] for k in ("ponytail_report", "ponytail_findings", "ponytail_unresolved",
                                                  "ponytail_open_critical_high")}),
        "G15 PHASE BOUNDARY": gate(not bnd["frontend_files"] and bnd["dashboard_dir_untouched"], bnd),
    }
    report = {"phase9_version": VERSION, "clean_run": a.clean, "config": cfg, "build": b,
              "service": {k: v for k, v in svc.items() if k != "query_digests"}, "tests": tests,
              "tests_total": sum(v["ran"] for v in tests.values()), "docs": docs, "review": rev, "gates": G,
              "determinism_files": det, "runtime_seconds": round(time.time() - t0, 1)}
    write_json(OUT / "validation_report.json", report)
    (OUT / "validation_report.md").write_text(render_md(report), encoding="utf-8")
    CACHE.mkdir(exist_ok=True)
    write_json(PREVIOUS, {"clean": a.clean, "files": det})
    import phase9_report
    phase9_report.write(report)
    failed = [g for g, v in G.items() if v["result"] != "PASS"]
    lg.info("gates: %d PASS, %d FAIL %s; %.0fs", len(G) - len(failed), len(failed), failed, report["runtime_seconds"])
    return 1 if failed else 0


def render_md(r: dict) -> str:
    lines = [f"# Phase 9 Validation Report ({r['phase9_version']})", "",
             f"Clean run: {r['clean_run']}. Tests: {r['tests_total']}. Runtime: {r['runtime_seconds']} s.", "",
             "| Gate | Result | Evidence |", "|---|---|---|"]
    for g, v in r["gates"].items():
        lines.append(f"| {g} | {v['result']} | {json.dumps(v['evidence'], default=str)[:300].replace('|', '/')} |")
    s = r["service"]
    lines += ["", "## Service", "", f"- startup {s['startup_seconds']} s; max RSS {s['max_rss_mb']} MB",
              *[f"- {k}: {v} ms (median)" for k, v in s["latency_median"].items()],
              f"- loopback socket smoke: {s['socket_smoke']}", "", "## Tests", "",
              *[f"- {k}: {v['ran']} tests, {'OK' if v['ok'] else 'FAILED'}" for k, v in r["tests"].items()], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
