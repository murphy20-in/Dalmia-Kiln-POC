import assert from "node:assert/strict";
import test from "node:test";
import { decimate, isGap, segments } from "../public/js/pure/series.js";
import { buildQuery, toApiTimestamp } from "../public/js/pure/query.js";
import { eventPayload, validateActor, validateEvent } from "../public/js/pure/form.js";
import { evidenceForDisplay } from "../public/js/pure/present.js";

test("gaps stay gaps and a zero score stays a point", () => {
  const rows = [
    { timestamp: "2025-08-01T00:00:00", empirical_risk_score: 0 },
    { timestamp: "2025-08-01T00:10:00", empirical_risk_score: 12 },
    { timestamp: "2025-08-01T01:00:00", empirical_risk_score: 4 },
    { timestamp: "2025-08-01T01:10:00", empirical_risk_score: null },
    { timestamp: "2025-08-01T01:20:00", empirical_risk_score: 8 },
  ];
  const segs = segments(rows, "empirical_risk_score", [["2025-08-01T00:10:00", "2025-08-01T01:00:00"]]);
  assert.equal(segs.length, 3);
  assert.equal(segs[0][0].y, 0);
  assert.equal(segs[0].length, 2);
  assert.equal(isGap("2025-08-01T00:00:00", "2025-08-01T00:10:00"), false);
  assert.equal(isGap("2025-08-01T00:10:00", "2025-08-01T01:00:00"), true);
});

test("decimate keeps segment ends and does not invent values", () => {
  const seg = Array.from({ length: 10 }, (_, i) => ({ timestamp: `t${i}`, y: i }));
  const [out] = decimate([seg], 4);
  assert.equal(out[0].y, 0);
  assert.equal(out.at(-1).y, 9);
  assert.ok(out.every((p) => seg.includes(p)));
});

test("timestamps reject offsets and empty seconds are filled", () => {
  assert.equal(toApiTimestamp("2025-08-01T00:40"), "2025-08-01T00:40:00");
  assert.equal(toApiTimestamp("2025-08-01T00:40:00Z"), null);
  assert.equal(toApiTimestamp("2025-02-30T00:00:00"), null);
  assert.equal(buildQuery({ start: "2025-08-01T00:00:00", variant: "primary", empty: "" }),
    "start=2025-08-01T00%3A00%3A00&variant=primary");
});

test("event form blocks a bad window and builds an API body", () => {
  assert.ok(validateActor("kiln.shift@plant").length === 0);
  assert.ok(validateActor("<script>").length > 0);
  const bad = validateEvent({
    event_type: "COATING", start_time: "2025-08-01T10:00:00", end_time: "2025-08-01T09:00:00",
    description: "inlet coating", source: "PLANT_LOG",
  });
  assert.ok(bad.some((issue) => issue.field === "end_time"));
  const body = eventPayload({
    event_type: "COATING", start_time: "2025-08-01T10:00:00", description: "inlet coating",
    source: "SHIFT_REPORT", equipment: "", severity: "MINOR",
  });
  assert.equal(body.equipment, undefined);
  assert.equal(body.severity, "MINOR");
  assert.equal("risk_score" in body, false);
});

test("withheld figures are not passed through for display", () => {
  assert.equal(evidenceForDisplay("PE +0.051, p 0.118"), "PE +0.051, p 0.118");
  assert.equal(evidenceForDisplay("AUC 0.868 on the training window"), "");
  assert.equal(evidenceForDisplay("lead time 40 min"), "");
});
