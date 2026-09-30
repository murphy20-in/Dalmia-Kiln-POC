"""Security: path traversal, arbitrary file access, malformed input, oversized bodies, injection, invalid IDs, no
stack-trace / filesystem leakage, hash-verified artifacts."""
import json
import tempfile
import unittest
from pathlib import Path

import _client as c
from p9common import MANIFEST_FILE, ServiceConfig, read_json, write_json

APP = TMP = None
E = "/api/v1/events"
LEAKS = (b"Traceback", b"/home/", b"POPOS-DATA", b"File \"", b"sqlite3.")


def setUpModule():
    global APP, TMP
    APP, TMP = c.make_app()


def tearDownModule():
    TMP.cleanup()


class TestSecurity(unittest.TestCase):
    def assertNoLeak(self, r):
        for s in LEAKS:
            self.assertNotIn(s, r.raw, s)

    def test_path_traversal_and_file_access_are_404(self):
        for p in ("/api/v1/../../etc/passwd", "/api/v1/events/../../../etc/passwd", "/api/v1/risk-scores/../metadata",
                  "/api/v1/metadata/provenance/../../phase-07-risk-score/outputs/risk_scores.parquet",
                  "/api/v1/files", "/api/v1/artifacts/risk_scores.parquet", "/etc/passwd", "/api/v1/events/%2e%2e",
                  "/api/v1/risk-scores/", "//api/v1/metadata", "/api/v1/metadata\x00", "/health\n", "/ready\n",
                  "/api/v1/metadata\n", "/api/v1/events/%0a"):
            r = c.call(APP, "GET", p)
            self.assertEqual(r.status, 404, p)
            self.assertNoLeak(r)

    def test_no_query_parameter_can_name_a_file(self):
        for q in ("path=/etc/passwd", "file=risk_scores.parquet", "artifact=../x", "variant=../../etc/passwd",
                  "variant=primary&variant=o2_excluded", "start=2025-01-01T00:00:00;DROP TABLE plant_events"):
            r = c.call(APP, "GET", "/api/v1/risk-scores", q)
            self.assertEqual(r.status, 400, q)
            self.assertNoLeak(r)

    def test_malformed_query_parameters(self):
        for q in ("limit=-1", "limit=0", "limit=99999999", "limit=abc", "offset=1e3", "start=", "start=yesterday",
                  "limit=1&&&", "a" * 5000 + "=1", "limit=%D9%A3", "offset=%EF%BC%91"):
            self.assertEqual(c.call(APP, "GET", "/api/v1/risk-scores", q).status, 400, q[:40])

    def test_invalid_ids_are_404_without_touching_sql(self):
        for eid in ("1", "' OR '1'='1", "00000000-0000-4000-8000-000000000000", "x" * 500, "%27%20OR%201%3D1"):
            r = c.call(APP, "GET", f"{E}/{eid}")
            self.assertEqual(r.status, 404, eid)
            self.assertNoLeak(r)

    def test_oversized_malformed_and_non_object_bodies(self):
        big = json.dumps(c.event_body(description="x" * 20000)).encode()
        self.assertEqual(c.call(APP, "POST", E, raw=big, headers=c.ACTOR).status, 413)
        for raw in (b"{not json", b"\xff\xfe\x00", b'{"a": NaN}', b'{"event_type": "RING", "event_type": "COATING"}'):
            r = c.call(APP, "POST", E, raw=raw, headers=c.ACTOR)
            self.assertEqual(r.status, 400, raw[:30])
            self.assertNoLeak(r)
        for raw in (b"[1, 2]", b"[" * 8000 + b"]" * 8000, b'"text"'):          # valid JSON, not an object
            r = c.call(APP, "POST", E, raw=raw, headers=c.ACTOR)
            self.assertIn(r.status, (400, 422), raw[:20])
            self.assertNoLeak(r)
        self.assertEqual(c.call(APP, "POST", E, raw=b"{}", headers={**c.ACTOR, "CONTENT_LENGTH": ""}).status, 400)

    def test_injection_strings_are_stored_literally(self):
        evil = "'); DROP TABLE plant_events; -- <script>alert(1)</script> {{7*7}} ${jndi:ldap://x}"
        r = c.call(APP, "POST", E, body=c.event_body(description=evil, event_type="OTHER",
                                                     start_time="2025-04-02T00:00:00", end_time="2025-04-02T01:00:00"),
                   headers=c.ACTOR)
        self.assertEqual(r.status, 201)
        self.assertEqual(c.call(APP, "GET", f"{E}/{r.json['data']['event_id']}").json["data"]["description"], evil)
        self.assertEqual(c.call(APP, "GET", E).status, 200)          # table still there

    def test_unexpected_enum_values_rejected(self):
        self.assertEqual(c.call(APP, "GET", "/api/v1/risk-scores", "variant=best").status, 400)
        self.assertEqual(c.call(APP, "GET", "/api/v1/findings", "classification=POSITIVE").status, 400)
        self.assertEqual(c.call(APP, "GET", E, "event_type=FAILURE").status, 400)

    def test_tampered_artifact_hash_makes_the_service_unready(self):
        man = read_json(MANIFEST_FILE)
        man["artifacts"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manifest.json"
            write_json(p, man)
            app, tmp = c.make_app(manifest_path=p)
            try:
                r = c.call(app, "GET", "/api/v1/risk-scores")
                self.assertEqual((r.status, r.json["error"]["code"]), (503, "ANALYTICAL_ARTIFACT_UNAVAILABLE"))
                self.assertNoLeak(r)
                rd = c.call(app, "GET", "/ready")
                self.assertEqual(rd.status, 503)
                self.assertNoLeak(rd)
            finally:
                tmp.cleanup()

    def test_default_bind_is_loopback(self):
        self.assertEqual(ServiceConfig(root=Path("."), events_db=Path("x")).host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
