"""Contract tests: endpoint availability, response envelope, provenance, error schema, route contract == docs,
observability fields, deterministic serialisation."""
import re
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import _client as c
import api_app
from p9common import DOCS

APP = TMP = None


def setUpModule():
    global APP, TMP
    APP, TMP = c.make_app()


def tearDownModule():
    TMP.cleanup()


class TestEnvelope(unittest.TestCase):
    def test_every_analytical_endpoint_has_envelope_provenance_and_interpretation(self):
        for p in c.GET_ENDPOINTS:
            r = c.call(APP, "GET", p, "limit=5" if p.endswith(("scores", "comparison", "periods", "findings")) else "")
            self.assertEqual(r.status, 200, p)
            for k in ("api_version", "service_version", "data", "provenance", "interpretation", "disclaimer"):
                self.assertIn(k, r.json, (p, k))
            self.assertEqual(r.json["api_version"], "v1")
            i = r.json["interpretation"]
            self.assertTrue(all(i[k] is False for k in ("is_prediction", "is_alert", "is_probability", "is_live",
                                                        "early_warning_supported", "event_ground_truth_available")), p)
            provs = r.json["provenance"] if isinstance(r.json["provenance"], list) else [r.json["provenance"]]
            for pv in provs:
                for k in ("source_phase", "artifact", "artifact_version", "artifact_sha256", "analytical_status",
                          "operational_status", "empirical", "plant_supplied", "ground_truth_status"):
                    self.assertIn(k, pv, (p, k))
                self.assertRegex(pv["artifact_sha256"], r"^[0-9a-f]{64}$")
                self.assertFalse(pv["plant_supplied"])

    def test_risk_score_provenance_names_phase7_version_and_variant(self):
        pv = c.call(APP, "GET", "/api/v1/risk-scores", "limit=1").json["provenance"]
        self.assertEqual((pv["source_phase"], pv["artifact_version"], pv["variant"], pv["analytical_status"]),
                         (7, "p7-risk-1.1.0", "primary", "EMPIRICAL_POC"))
        o = c.call(APP, "GET", "/api/v1/risk-scores", "variant=o2_excluded&limit=1").json["provenance"]
        self.assertEqual((o["source_phase"], o["variant"], o["analytical_status"]),
                         (9, "o2_excluded", "SENSITIVITY_ANALYSIS"))

    def test_collections_carry_explicit_pagination(self):
        n = int(pd.read_parquet(c.ROOT / "phase-07-risk-score/outputs/risk_scores.parquet").operational.sum())
        r = c.call(APP, "GET", "/api/v1/risk-scores", "limit=10&offset=5")
        self.assertEqual(r.json["pagination"], {"limit": 10, "offset": 5, "total": n, "returned": 10,
                                                "has_more": True, "next_offset": 15})
        last = c.call(APP, "GET", "/api/v1/risk-scores", f"limit=10&offset={n - 7}").json["pagination"]
        self.assertEqual((last["returned"], last["has_more"], last["next_offset"]), (7, False, None))

    def test_health_is_liveness_and_ready_is_readiness(self):
        self.assertEqual(c.call(APP, "GET", "/health").json["status"], "ok")
        r = c.call(APP, "GET", "/ready")
        self.assertEqual((r.status, r.json["analytical_artifacts"], r.json["event_store"]), (200, "VERIFIED", "OK"))


class TestErrors(unittest.TestCase):
    def assertError(self, r, status, code):
        self.assertEqual(r.status, status, r.json)
        self.assertEqual(set(r.json), {"error"})
        self.assertEqual(set(r.json["error"]), {"code", "message", "request_id", "details"})
        self.assertEqual(r.json["error"]["code"], code)
        self.assertEqual(r.json["error"]["request_id"], r.headers["X-Request-ID"])

    def test_error_schema_for_each_status(self):
        self.assertError(c.call(APP, "GET", "/api/v1/risk-scores", "bogus=1"), 400, "INVALID_REQUEST")
        self.assertError(c.call(APP, "GET", "/api/v1/nothing"), 404, "NOT_FOUND")
        self.assertError(c.call(APP, "PUT", "/api/v1/risk-scores"), 405, "METHOD_NOT_ALLOWED")
        self.assertError(c.call(APP, "GET", "/api/v1/risk-scores", "start=2025-08-02T00:00:00&end=2025-08-01T00:00:00"),
                         422, "VALIDATION_ERROR")
        self.assertError(c.call(APP, "POST", "/api/v1/events", body={}, headers=c.ACTOR), 422, "VALIDATION_ERROR")
        self.assertError(c.call(APP, "POST", "/api/v1/events", body=c.event_body(), content_type="text/plain",
                                headers=c.ACTOR), 415, "UNSUPPORTED_MEDIA_TYPE")

    def test_405_lists_allowed_methods(self):
        self.assertEqual(c.call(APP, "PUT", "/api/v1/events").headers["Allow"], "GET, POST")

    def test_503_when_manifest_missing(self):
        app, tmp = c.make_app(manifest_path=c.ROOT / "phase-09-api/outputs/does_not_exist.json")
        try:
            self.assertError(c.call(app, "GET", "/api/v1/risk-scores"), 503, "ANALYTICAL_ARTIFACT_UNAVAILABLE")
            self.assertEqual(c.call(app, "GET", "/health").status, 200)
            r = c.call(app, "GET", "/ready")
            self.assertEqual((r.status, r.json["ready"], r.json["analytical_artifacts"]), (503, False, "UNAVAILABLE"))
            self.assertEqual(c.call(app, "GET", "/api/v1/events").status, 200)    # plant annotation still usable
        finally:
            tmp.cleanup()

    def test_503_when_manifest_is_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            for text in ("{not json", '{"no_artifacts": []}', "[]"):
                p = Path(d) / "manifest.json"
                p.write_text(text, encoding="utf-8")
                app, tmp = c.make_app(manifest_path=p)
                try:
                    self.assertError(c.call(app, "GET", "/api/v1/metadata"), 503, "ANALYTICAL_ARTIFACT_UNAVAILABLE")
                finally:
                    tmp.cleanup()

    def test_internal_error_is_generic(self):
        orig = APP.findings
        APP.findings = lambda req: 1 / 0
        try:
            with self.assertLogs("p9.api", level="ERROR"):
                r = c.call(APP, "GET", "/api/v1/findings")
            self.assertError(r, 500, "INTERNAL_ERROR")
            self.assertNotIn(b"Traceback", r.raw)
            self.assertNotIn(b"ZeroDivision", r.raw)
        finally:
            APP.findings = orig


class TestRouteContract(unittest.TestCase):
    def test_docs_list_exactly_the_implemented_routes(self):
        doc = (DOCS / "API_CONTRACT.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `(GET|POST|PATCH|DELETE) ([^`]+)` \|", doc, flags=re.M))
        implemented = {(r["method"], r["path"]) for r in api_app.route_contract()}
        self.assertEqual(documented, implemented)

    def test_all_public_data_routes_are_versioned(self):
        for r in api_app.ROUTES:
            self.assertTrue(r.template.startswith("/api/v1/") or r.kind == "ops", r.template)


class TestObservabilityAndDeterminism(unittest.TestCase):
    def test_request_log_fields(self):
        with self.assertLogs("p9.api", level="INFO") as cm:
            r = c.call(APP, "GET", "/api/v1/risk-scores", "start=2025-07-01T00:00:00&end=2025-07-02T00:00:00")
        line = [x for x in cm.output if '"event": "request"' in x][-1]
        for k in ("request_id", "timestamp", "method", "path", "status", "duration_ms", "artifact_version", "variant",
                  "query_window", "result_count"):
            self.assertIn(f'"{k}"', line)
        self.assertIn(r.headers["X-Request-ID"], line)

    def test_event_description_is_not_logged(self):
        secret = "UNIQUE-DESCRIPTION-TEXT-7731"
        with self.assertLogs("p9.api", level="INFO") as cm:
            c.call(APP, "POST", "/api/v1/events", body=c.event_body(description=secret, event_type="OTHER"),
                   headers=c.ACTOR)
        self.assertFalse(any(secret in x for x in cm.output))

    def test_repeated_reads_are_byte_identical(self):
        for p, q in (("/api/v1/risk-scores", "limit=200&offset=3000"), ("/api/v1/abnormal-periods", ""),
                     ("/api/v1/validation/early-warning-historical", ""), ("/api/v1/findings", ""),
                     ("/api/v1/metadata/provenance", "")):
            self.assertEqual(c.call(APP, "GET", p, q).raw, c.call(APP, "GET", p, q).raw, p)


if __name__ == "__main__":
    unittest.main()
