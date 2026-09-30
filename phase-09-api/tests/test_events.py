"""Plant event annotation: CRUD, soft delete, validation, conflicts, audit trail, isolation from analytical labels."""
import sqlite3
import unittest

import _client as c

APP = TMP = None
E = "/api/v1/events"


def setUpModule():
    global APP, TMP
    APP, TMP = c.make_app()


def tearDownModule():
    TMP.cleanup()


def create(**kw):
    return c.call(APP, "POST", E, body=c.event_body(**kw), headers=c.ACTOR)


class TestCrud(unittest.TestCase):
    def test_create_read_update_delete_with_audit(self):
        r = create(event_type="RING", equipment="kiln inlet", start_time="2025-07-01T06:00:00",
                   end_time="2025-07-01T09:00:00", severity="MODERATE", plant_confirmation="CONFIRMED")
        self.assertEqual(r.status, 201, r.json)
        e = r.json["data"]
        for k, v in {"event_type": "RING", "status": "ACTIVE", "version": 1, "label_origin": "PLANT_SUPPLIED",
                     "created_by": "test.engineer", "updated_by": "test.engineer", "analytical_label": None}.items():
            self.assertEqual(e[k], v, k)
        self.assertTrue(e["created_at"].endswith("Z"))
        self.assertIn("PLANT_LOCAL_NAIVE", e["timestamp_basis"])
        self.assertTrue(r.json["interpretation"]["is_plant_supplied"])
        self.assertFalse(r.json["interpretation"]["is_analytical_label"])
        eid = e["event_id"]
        self.assertEqual(c.call(APP, "GET", f"{E}/{eid}").json["data"]["description"], e["description"])

        u = c.call(APP, "PATCH", f"{E}/{eid}", body={"severity": "MAJOR", "expected_version": 1},
                   headers={"HTTP_X_ACTOR": "reviewer.two"})
        self.assertEqual((u.status, u.json["data"]["severity"], u.json["data"]["version"],
                          u.json["data"]["updated_by"], u.json["data"]["created_by"]),
                         (200, "MAJOR", 2, "reviewer.two", "test.engineer"))
        self.assertEqual(c.call(APP, "DELETE", f"{E}/{eid}", headers=c.ACTOR).status, 422)     # version required
        self.assertEqual(c.call(APP, "DELETE", f"{E}/{eid}", "expected_version=1", headers=c.ACTOR).status, 409)
        d = c.call(APP, "DELETE", f"{E}/{eid}", "expected_version=2", headers=c.ACTOR)
        self.assertEqual((d.status, d.json["data"]["status"]), (200, "DELETED"))
        self.assertEqual(c.call(APP, "GET", f"{E}/{eid}").json["data"]["status"], "DELETED")   # still readable
        a = c.call(APP, "GET", f"{E}/{eid}/audit").json["data"]
        self.assertEqual([x["operation"] for x in a], ["CREATE", "UPDATE", "DELETE"])
        self.assertIsNone(a[0]["old_value"])
        self.assertEqual((a[1]["old_value"]["severity"], a[1]["new_value"]["severity"]), ("MODERATE", "MAJOR"))
        self.assertEqual([x["actor"] for x in a], ["test.engineer", "reviewer.two", "test.engineer"])
        self.assertNotIn(eid, [x["event_id"] for x in c.call(APP, "GET", E, "limit=1000").json["data"]])
        self.assertIn(eid, [x["event_id"] for x in c.call(APP, "GET", E, "status=DELETED").json["data"]])

    def test_deleted_event_cannot_be_modified(self):
        eid = create(event_type="CLEANING", start_time="2025-06-02T01:00:00", end_time="2025-06-02T02:00:00"
                     ).json["data"]["event_id"]
        c.call(APP, "DELETE", f"{E}/{eid}", "expected_version=1", headers=c.ACTOR)
        self.assertEqual(c.call(APP, "PATCH", f"{E}/{eid}", body={"severity": "MINOR", "expected_version": 2},
                                headers=c.ACTOR).status, 409)
        self.assertEqual(c.call(APP, "DELETE", f"{E}/{eid}", "expected_version=2", headers=c.ACTOR).status, 409)

    def test_list_filters_and_stable_order(self):
        ids = [create(event_type="MAINTENANCE", start_time=f"2025-05-0{d}T08:00:00",
                      end_time=f"2025-05-0{d}T10:00:00").json["data"]["event_id"] for d in (3, 1, 2)]
        r = c.call(APP, "GET", E, "event_type=MAINTENANCE&start=2025-05-01T00:00:00&end=2025-05-04T00:00:00").json
        self.assertEqual([x["start_time"][:10] for x in r["data"]], ["2025-05-01", "2025-05-02", "2025-05-03"])
        self.assertEqual(set(x["event_id"] for x in r["data"]), set(ids))
        p = c.call(APP, "GET", E, "event_type=MAINTENANCE&start=2025-05-01T00:00:00&end=2025-05-04T00:00:00&limit=2").json["pagination"]
        self.assertEqual((p["returned"], p["has_more"], p["total"]), (2, True, 3))

    def test_revalidation_fields_are_optional_and_validated(self):
        r = create(event_type="RING", start_time="2025-06-22T00:00:00", end_time="2025-06-22T08:00:00",
                   time_precision="WITHIN_SHIFT", time_basis="ESTIMATED_ONSET", entry_kind="RETROSPECTIVE",
                   annotator_viewed_risk_score=False)
        self.assertEqual(r.status, 201, r.json)
        d = r.json["data"]
        self.assertEqual((d["time_precision"], d["time_basis"], d["entry_kind"], d["annotator_viewed_risk_score"]),
                         ("WITHIN_SHIFT", "ESTIMATED_ONSET", "RETROSPECTIVE", False))
        self.assertEqual(create(annotator_viewed_risk_score="no").status, 422)
        self.assertEqual(create(time_precision="ROUGHLY").status, 422)

    def test_noop_patch_is_rejected(self):
        eid = create(event_type="OTHER", start_time="2025-06-23T00:00:00", end_time="2025-06-23T01:00:00",
                     annotator_viewed_risk_score=True).json["data"]["event_id"]
        r = c.call(APP, "PATCH", f"{E}/{eid}", body={"expected_version": 1, "annotator_viewed_risk_score": True},
                   headers=c.ACTOR)
        self.assertEqual(r.status, 422)
        self.assertEqual(len(c.call(APP, "GET", f"{E}/{eid}/audit").json["data"]), 1)

    def test_open_ended_event_is_allowed(self):
        r = create(event_type="STOPPAGE", start_time="2025-06-20T10:00:00", end_time=None)
        self.assertEqual((r.status, r.json["data"]["end_time"]), (201, None))

    def test_overlap_with_kpi_periods_is_context_only(self):
        d = create(event_type="PROCESS_UPSET", start_time="2025-07-16T04:00:00",
                   end_time="2025-07-16T05:00:00").json["data"]
        self.assertEqual(d["analytical_context"]["overlapping_kpi_derived_abnormal_periods"], ["P6-031"])
        self.assertEqual(d["event_type"], "PROCESS_UPSET")          # never changed by the analytical layer
        self.assertIsNone(d["analytical_label"])


class TestValidation(unittest.TestCase):
    def assert422(self, r, field):
        self.assertEqual(r.status, 422, r.json)
        self.assertIn(field, [d["field"] for d in r.json["error"]["details"]])

    def test_rules(self):
        self.assert422(create(start_time="2025-08-15T14:00:00", end_time="2025-08-15T08:00:00"), "end_time")
        self.assert422(create(start_time="2025-08-15T08:00:00", end_time="2025-08-15T08:00:00"), "end_time")
        self.assert422(create(event_type="DEPOSIT_PROBABILITY"), "event_type")
        self.assert422(create(source=""), "source")
        self.assert422(create(source="EMAIL"), "source")
        self.assert422(create(description="x" * 2001), "description")
        self.assert422(create(description="   "), "description")
        self.assert422(create(start_time="2025-02-30T08:00:00"), "start_time")
        self.assert422(create(start_time="2025-08-15 08:00:00"), "start_time")
        self.assert422(create(start_time="2025-08-15T08:00"), "start_time")
        self.assert422(create(equipment="a\nb"), "equipment")
        self.assert422(create(severity="CRITICAL"), "severity")

    def test_timezone_is_never_inferred_or_converted(self):
        for ts in ("2025-08-15T08:00:00Z", "2025-08-15T08:00:00+05:30", "2025-08-15T08:00:00-01:00"):
            r = create(start_time=ts)
            self.assert422(r, "start_time")
            self.assertIn("timezone", r.json["error"]["details"][0]["issue"])

    def test_server_controlled_and_analytical_fields_are_rejected(self):
        for k, v in (("analytical_label", "KPI_DERIVED"), ("label_origin", "ANALYTICAL"), ("created_by", "x"),
                     ("status", "ACTIVE"), ("event_id", "abc"), ("risk_score", 99)):
            self.assert422(create(**{k: v}), k)

    def test_patch_requires_expected_version_and_detects_stale_writes(self):
        eid = create(event_type="FEED_REDUCTION", start_time="2025-06-05T01:00:00",
                     end_time="2025-06-05T02:00:00").json["data"]["event_id"]
        self.assert422(c.call(APP, "PATCH", f"{E}/{eid}", body={"severity": "MINOR"}, headers=c.ACTOR),
                       "expected_version")
        r = c.call(APP, "PATCH", f"{E}/{eid}", body={"severity": "MINOR", "expected_version": 7}, headers=c.ACTOR)
        self.assertEqual((r.status, r.json["error"]["details"][0]["current_version"]), (409, 1))
        self.assert422(c.call(APP, "PATCH", f"{E}/{eid}", body={"end_time": "2025-06-05T00:00:00",
                                                                 "expected_version": 1}, headers=c.ACTOR), "end_time")

    def test_actor_header_required(self):
        self.assertEqual(c.call(APP, "POST", E, body=c.event_body()).status, 400)
        self.assertEqual(c.call(APP, "POST", E, body=c.event_body(), headers={"HTTP_X_ACTOR": "<script>"}).status,
                         400)


class TestConflictsAndIntegrity(unittest.TestCase):
    def test_duplicate_overlapping_same_type_and_equipment_is_409(self):
        a = create(event_type="COATING", equipment="riser", start_time="2025-04-10T00:00:00",
                   end_time="2025-04-10T06:00:00")
        self.assertEqual(a.status, 201)
        b = create(event_type="COATING", equipment="riser", start_time="2025-04-10T05:00:00",
                   end_time="2025-04-10T07:00:00")
        self.assertEqual(b.status, 409)
        self.assertEqual(b.json["error"]["details"][0]["conflicting_event_ids"], [a.json["data"]["event_id"]])
        self.assertEqual(create(event_type="CLEANING", equipment="riser", start_time="2025-04-10T05:00:00",
                                end_time="2025-04-10T07:00:00").status, 201)          # different type is fine
        self.assertEqual(create(event_type="COATING", equipment=" RISER ", start_time="2025-04-10T01:00:00",
                                end_time="2025-04-10T02:00:00").status, 409)          # case / space-insensitive
        self.assertEqual(create(event_type="COATING", equipment="riser", source="INSPECTION",
                                start_time="2025-04-10T01:00:00", end_time="2025-04-10T02:00:00").status, 201)

    def test_one_overlap_rule_back_to_back_and_instants(self):
        kw = dict(event_type="MAINTENANCE", equipment="cooler")
        self.assertEqual(create(start_time="2025-04-12T00:00:00", end_time="2025-04-12T10:00:00", **kw).status, 201)
        self.assertEqual(create(start_time="2025-04-12T10:00:00", end_time="2025-04-12T12:00:00", **kw).status, 201)
        self.assertEqual(create(start_time="2025-04-12T11:00:00", end_time=None, **kw).status, 409)   # inside
        self.assertEqual(create(start_time="2025-04-12T12:00:00", end_time=None, **kw).status, 201)   # at end
        self.assertEqual(create(start_time="2025-04-12T12:00:00", end_time=None, **kw).status, 409)   # same instant
        r = c.call(APP, "GET", E, "event_type=MAINTENANCE&start=2025-04-12T10:00:00&end=2025-04-12T12:00:00").json
        self.assertEqual([x["start_time"] for x in r["data"]], ["2025-04-12T10:00:00"])   # [start, end)

    def test_audit_is_append_only_and_events_are_never_hard_deleted(self):
        eid = create(event_type="OTHER", start_time="2025-04-20T00:00:00", end_time="2025-04-20T01:00:00"
                     ).json["data"]["event_id"]
        con = sqlite3.connect(APP.events.path)
        try:
            for sql, args in (("UPDATE plant_event_audit SET actor = 'x'", ()),
                              ("DELETE FROM plant_event_audit", ()),
                              ("DELETE FROM plant_events WHERE event_id = ?", (eid,))):
                with self.assertRaises(sqlite3.DatabaseError, msg=sql):
                    con.execute(sql, args)
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE plant_events SET label_origin = 'ANALYTICAL' WHERE event_id = ?", (eid,))
            for sql in ("UPDATE plant_events SET created_by = 'x', version = version + 1 WHERE event_id = ?",
                        "UPDATE plant_events SET severity = 'MINOR' WHERE event_id = ?",          # no version bump
                        "UPDATE plant_events SET start_time = '2025-04-20 00:00:00', version = version + 1 "
                        "WHERE event_id = ?",
                        "INSERT OR REPLACE INTO plant_events SELECT * FROM plant_events WHERE event_id = ?"):
                with self.assertRaises(sqlite3.DatabaseError, msg=sql):
                    con.execute(sql, (eid,))
        finally:
            con.close()

    def test_analytical_reads_never_write_the_event_store(self):
        def n():
            con = sqlite3.connect(APP.events.path)
            try:
                return con.execute("SELECT (SELECT count(*) FROM plant_events), "
                                   "(SELECT count(*) FROM plant_event_audit)").fetchone()
            finally:
                con.close()
        before = n()
        for p in c.GET_ENDPOINTS:
            c.call(APP, "GET", p, "limit=5" if p.endswith(("scores", "comparison", "periods", "findings")) else "")
        self.assertEqual(n(), before)


if __name__ == "__main__":
    unittest.main()
