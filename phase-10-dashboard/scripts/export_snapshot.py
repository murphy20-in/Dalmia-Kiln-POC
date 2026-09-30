"""Export the Phase 9 responses the hosted dashboard reads. No score is recomputed."""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

BASE = os.environ.get("DALMIA_KILN_API_UPSTREAM", "http://127.0.0.1:8009").rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "public" / "snapshot"

WHOLE = {
    "metadata.json": "/api/v1/metadata",
    "status.json": "/api/v1/metadata/status",
    "provenance.json": "/api/v1/metadata/provenance",
    "limitations.json": "/api/v1/metadata/limitations",
    "methodology.json": "/api/v1/metadata/methodology",
    "data-requirements.json": "/api/v1/metadata/data-requirements",
    "periods.json": "/api/v1/abnormal-periods?limit=100",
    "events.json": "/api/v1/events?status=ALL&limit=100",
    "validation.json": "/api/v1/validation/early-warning-historical",
    "findings.json": "/api/v1/findings?limit=100",
}


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=120) as response:
        return json.loads(response.read().decode())


def pages(path: str) -> tuple[dict, list]:
    rows = []
    shell = None
    offset = 0
    while True:
        body = get(f"{path}{'&' if '?' in path else '?'}limit=5000&offset={offset}")
        if shell is None:
            shell = {k: v for k, v in body.items() if k not in ("data", "pagination")}
        rows.extend(body.get("data") or [])
        if not body.get("pagination", {}).get("has_more"):
            break
        offset = body["pagination"]["next_offset"]
    extent = shell.get("data_extent")
    if isinstance(extent, dict):
        extent = {k: v for k, v in extent.items() if k != "gaps_in_page"}
        shell["data_extent"] = extent
    return shell, rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, path in WHOLE.items():
        (OUT / name).write_text(json.dumps(get(path), separators=(",", ":")))
    shell, rows = pages("/api/v1/risk-scores?variant=primary")
    points = [[row["timestamp"], row["empirical_risk_score"]] for row in rows]
    (OUT / "scores-primary.json").write_text(json.dumps({"shell": shell, "points": points}, separators=(",", ":")))
    shell, rows = pages("/api/v1/risk-scores/variant-comparison")
    points = [[row["timestamp"], row["primary_empirical_risk_score"], row["o2_excluded_empirical_risk_score"]] for row in rows]
    (OUT / "scores-comparison.json").write_text(json.dumps({"shell": shell, "points": points}, separators=(",", ":")))
    events = json.loads((OUT / "events.json").read_text())
    audits = {}
    for event in events.get("data") or []:
        audits[event["event_id"]] = get(f"/api/v1/events/{event['event_id']}/audit")["data"]
    (OUT / "events-audit.json").write_text(json.dumps(audits, separators=(",", ":")))
    blob = "\n".join(path.read_text() for path in OUT.glob("*.json"))
    if "/home/" in blob or "/mnt/" in blob or "events.sqlite" in blob:
        raise SystemExit("snapshot contains a local path")
    print(f"wrote {OUT} ({sum(p.stat().st_size for p in OUT.glob('*.json'))} bytes)")


if __name__ == "__main__":
    main()
