"""Product safety: no alert / prediction / probability route or field, no live W1-W5 flag, no band-as-alarm field,
machine-readable analytical state flags, and the Phase 8 wording scanner over every served string."""
import re
import sys
import unittest

import _client as c
import api_app
from p9common import CONTRACT_FILE, ROOT, read_json

APP = TMP = None
PROHIBITED_PATHS = ("/api/v1/alerts", "/api/v1/alarms", "/api/v1/predictions", "/api/v1/predict", "/api/v1/alert",
                    "/api/v1/forecast", "/api/v1/early-warning", "/api/v1/warnings", "/api/v1/notifications",
                    "/api/v1/failure-probability", "/api/v1/deposit-probability", "/api/v1/ring-probability",
                    "/api/v1/risk-scores/live", "/api/v1/risk-scores/latest", "/api/v1/webhooks", "/predict",
                    "/alarms", "/api/v2/risk-scores", "/api/v1/failures", "/api/v1/deposits", "/api/v1/rings",
                    "/api/v1/incidents")
# field-name fragments that would imply alarm / prediction / probability / live-warning semantics
FORBIDDEN_KEY = re.compile(r"alarm|predict|forecast|probabilit|early_warning_active|risk_of_failure|^warning$|"
                           r"^alert$|^is_warning|alert_level|lead_time|coverage", re.I)
# the explicit negative flags and historical-validation fields are the only allowed exceptions
ALLOWED_KEYS = {"is_prediction", "is_alert", "is_probability", "prediction_enabled", "alerting_enabled",
                "probability_outputs_enabled", "prediction_status", "alerting_status", "early_warning_supported",
                "live_warning_flags_enabled", "lead_time_claims_enabled", "warning_definitions", "warning_definition",
                "family_coverage"}   # Phase 7 confidence part: share of usable process families, not event coverage


def setUpModule():
    global APP, TMP
    APP, TMP = c.make_app()
    sys.path.insert(0, str(ROOT / "phase-08-early-warning/scripts"))


def tearDownModule():
    TMP.cleanup()


def responses():
    for p in c.GET_ENDPOINTS:
        yield p, c.call(APP, "GET", p, "limit=200" if p.endswith(("scores", "comparison", "periods", "findings"))
                        else "").json
    yield "/api/v1/risk-scores?o2", c.call(APP, "GET", "/api/v1/risk-scores", "variant=o2_excluded&limit=50").json
    yield "/api/v1/events POST", c.call(APP, "POST", "/api/v1/events", body=c.event_body(), headers=c.ACTOR).json


class TestSafety(unittest.TestCase):
    def test_prohibited_routes_do_not_exist(self):
        for p in PROHIBITED_PATHS:
            for m in ("GET", "POST"):
                self.assertEqual(c.call(APP, m, p, body={} if m == "POST" else None).status, 404, (m, p))

    def test_route_table_has_no_prohibited_semantics(self):
        for r in api_app.ROUTES:
            path = r.template.replace("early-warning-historical", "")    # the one historical-validation route
            self.assertNotRegex(path, r"alert|alarm|predict|forecast|probab|warning|live|notif|webhook", r.template)
            if r.kind == "analytical":
                self.assertEqual(r.method, "GET", r.template)            # analytical layer is read-only

    def test_no_forbidden_field_names_and_no_live_flags(self):
        for p, body in responses():
            for path, k, v in c.walk(body):
                if k in ALLOWED_KEYS:
                    if k.startswith("is_") or k.endswith(("_enabled", "_supported")):
                        self.assertIs(v, False, (p, path))
                    continue
                self.assertIsNone(FORBIDDEN_KEY.search(k), (p, path))
                if k == "is_live_flag":
                    self.assertIs(v, False, (p, path))

    def test_no_coverage_or_lead_time_figures_in_any_served_value(self):
        figure = re.compile(r"coverage [0-9.]+|lead[- ]time[s]? (of )?[0-9]|alert rate [0-9]", re.I)
        for p, body in responses():
            for path, _, v in c.walk(body):
                if isinstance(v, str):
                    self.assertIsNone(figure.search(v), (p, path, v[:120]))

    def test_bands_are_reference_relative_not_alarm_levels(self):
        r = c.call(APP, "GET", "/api/v1/risk-scores", "limit=1").json["data"][0]
        self.assertIn("reference_relative_band", r)
        self.assertNotIn("risk_band", r)
        m = c.call(APP, "GET", "/api/v1/metadata/methodology").json["data"]["phase7_score"]
        self.assertIn("not plant limits, alarm levels", m["band_semantics"])

    def test_analytical_state_flags_are_machine_readable_and_false(self):
        state = read_json(CONTRACT_FILE)["analytical_state"]
        self.assertTrue(state and all(v is False for v in state.values()), state)
        for p in ("/api/v1/metadata", "/api/v1/metadata/status"):
            got = c.call(APP, "GET", p).json["data"]["analytical_state"]
            for k in ("early_warning_supported", "alerting_enabled", "prediction_enabled",
                      "plant_event_ground_truth_available"):
                self.assertIs(got[k], False, (p, k))
        s = c.call(APP, "GET", "/api/v1/metadata/status").json["data"]
        self.assertEqual(s["evidence_status"]["from_phase8_artifacts"]["phase8_primary_endpoint"], "NOT_SUPPORTED")
        self.assertEqual(s["ground_truth"]["minimum_recommended_for_revalidation"], 8)
        self.assertFalse(s["ground_truth"]["available"])

    def test_served_text_passes_the_phase8_wording_scanner(self):
        from p8common import forbidden_hits                            # Phase 8, read-only
        for p, body in responses():
            text = "\n".join(str(v) for _, _, v in c.walk(body) if isinstance(v, str))
            self.assertEqual(forbidden_hits(text), [], p)


if __name__ == "__main__":
    unittest.main()
