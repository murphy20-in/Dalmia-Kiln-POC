import assert from "node:assert/strict";
import test from "node:test";

const base = process.env.DALMIA_KILN_API_UPSTREAM || "http://127.0.0.1:8009";

async function get(path) {
  const response = await fetch(base + path);
  assert.equal(response.ok, true, path);
  return response.json();
}

test("Phase 9 fields the dashboard reads are present", async () => {
  const score = await get("/api/v1/risk-scores?limit=1");
  assert.equal(typeof score.data[0].empirical_risk_score, "number");
  assert.equal(score.data[0].variant, "primary");
  assert.ok(score.provenance);
  assert.equal(score.interpretation.is_retrospective, true);
  assert.equal(score.interpretation.is_prediction, false);
  assert.equal(score.interpretation.is_alert, false);
  assert.ok(Array.isArray(score.data_extent.gaps_in_page));
  assert.equal(score.variant.preferred, false);

  const compare = await get("/api/v1/risk-scores/variant-comparison?start=2025-08-01T00:00:00&end=2025-08-01T02:00:00&limit=2");
  assert.equal(compare.variants.o2_excluded.variant_status, "SENSITIVITY_ANALYSIS");
  assert.equal(compare.variants.o2_excluded.preferred, false);
  assert.equal("primary_empirical_risk_score" in compare.data[0], true);
  assert.equal("o2_excluded_empirical_risk_score" in compare.data[0], true);

  const periods = await get("/api/v1/abnormal-periods?limit=1");
  assert.equal(periods.data[0].label_type, "KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD");
  assert.equal(periods.data[0].is_plant_event, false);
  assert.equal(periods.pagination.total, 12);

  const validation = await get("/api/v1/validation/early-warning-historical");
  assert.equal(validation.data.historical_validation_status, "NOT_SUPPORTED");
  assert.equal(validation.data.primary_endpoint.by_variant.primary.preferred, false);
  assert.equal(validation.data.early_warning_supported, false);

  const events = await get("/api/v1/events?limit=1");
  assert.equal(events.interpretation.is_plant_supplied, true);
  assert.equal(events.provenance.source, "PLANT_SUPPLIED_ANNOTATION");
});
