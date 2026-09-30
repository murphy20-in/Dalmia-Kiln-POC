"""In-process WSGI client for the Phase 9 tests (no HTTP library, no network). Each test module builds one App on the
real frozen artifacts with a throwaway event database, so the plant event store is never touched by tests."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import api_app  # noqa: E402
from p9common import MANIFEST_FILE, ROOT, ServiceConfig  # noqa: E402

ACTOR = {"HTTP_X_ACTOR": "test.engineer"}


def make_app(manifest_path=MANIFEST_FILE) -> tuple[api_app.App, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    return api_app.App(ServiceConfig(root=ROOT, events_db=Path(tmp.name) / "events.sqlite3"), manifest_path), tmp


class Resp:
    def __init__(self, status: str, headers: list, body: bytes):
        self.status = int(status.split()[0])
        self.headers = dict(headers)
        self.raw = body
        self.json = json.loads(body)


def call(app, method: str, path: str, query: str = "", body=None, raw: bytes | None = None,
         content_type: str = "application/json", headers: dict | None = None) -> Resp:
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query, "wsgi.input": io.BytesIO(data),
           "CONTENT_LENGTH": str(len(data)) if (data or body is not None) else "", "CONTENT_TYPE": content_type,
           **(headers or {})}
    got = {}

    def start_response(status, hdrs):
        got["s"], got["h"] = status, hdrs
    out = b"".join(app(env, start_response))
    return Resp(got["s"], got["h"], out)


def event_body(**kw) -> dict:
    return {"event_type": "COATING", "start_time": "2025-08-15T08:00:00", "end_time": "2025-08-15T14:00:00",
            "description": "coating observed at kiln inlet (synthetic test record)", "source": "PLANT_LOG", **kw}


def walk(obj, path=""):
    """Yield (key_path, key, value) for every key in a JSON document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


GET_ENDPOINTS = ("/api/v1/metadata", "/api/v1/metadata/status", "/api/v1/metadata/provenance",
                 "/api/v1/metadata/limitations", "/api/v1/metadata/methodology", "/api/v1/metadata/data-requirements",
                 "/api/v1/risk-scores", "/api/v1/risk-scores/variant-comparison", "/api/v1/abnormal-periods",
                 "/api/v1/validation/early-warning-historical", "/api/v1/findings")
