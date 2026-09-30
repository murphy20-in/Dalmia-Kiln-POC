/** Client checks before POST/PATCH. Enums match the Phase 9 event contract (no schema route exists). */

export const EVENT_TYPES = ["COATING", "RING", "DEPOSIT", "CLEANING", "MAINTENANCE", "STOPPAGE", "FEED_REDUCTION", "ANALYSER_CALIBRATION", "PROCESS_UPSET", "OTHER"];
export const SOURCES = ["PLANT_LOG", "SHIFT_REPORT", "MAINTENANCE_RECORD", "INSPECTION", "OPERATOR_RECALL", "OTHER"];
export const SEVERITIES = ["MINOR", "MODERATE", "MAJOR"];
export const CONFIRMATIONS = ["CONFIRMED", "PROBABLE", "UNCONFIRMED"];
export const TIME_PRECISIONS = ["EXACT", "WITHIN_HOUR", "WITHIN_SHIFT", "WITHIN_DAY"];
export const TIME_BASES = ["OBSERVED", "ESTIMATED_ONSET", "REPORTED"];
export const ENTRY_KINDS = ["CONTEMPORANEOUS", "RETROSPECTIVE"];
const ACTOR = /^[A-Za-z0-9 ._@-]{1,100}$/;
const CTRL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;

export function validateActor(actor) {
  if (!ACTOR.test(actor || "")) return "Actor is required: 1–100 characters (letters, digits, space, . _ @ -). Attribution only, not authentication.";
  return "";
}

export function validateEvent(input) {
  const issues = [];
  if (!EVENT_TYPES.includes(input.event_type)) issues.push({ field: "event_type", issue: "Choose an event type from the list." });
  if (!input.start_time) issues.push({ field: "start_time", issue: "Start time is required (plant-local, no timezone)." });
  if (input.end_time && input.start_time && input.end_time <= input.start_time) {
    issues.push({ field: "end_time", issue: "End time must be later than start time." });
  }
  const description = input.description ?? "";
  if (!description.trim()) issues.push({ field: "description", issue: "Description is required." });
  else if (description.length > 2000) issues.push({ field: "description", issue: "Description must be 2000 characters or fewer." });
  else if (CTRL.test(description)) issues.push({ field: "description", issue: "Description contains a control character the service rejects." });
  if (!SOURCES.includes(input.source)) issues.push({ field: "source", issue: "Choose a source from the list." });
  if (input.equipment && input.equipment.length > 100) issues.push({ field: "equipment", issue: "Equipment must be 100 characters or fewer." });
  if (input.source_reference && input.source_reference.length > 200) issues.push({ field: "source_reference", issue: "Source reference must be 200 characters or fewer." });
  for (const [field, allowed] of [["severity", SEVERITIES], ["plant_confirmation", CONFIRMATIONS], ["time_precision", TIME_PRECISIONS], ["time_basis", TIME_BASES], ["entry_kind", ENTRY_KINDS]]) {
    if (input[field] && !allowed.includes(input[field])) issues.push({ field, issue: "Unsupported value." });
  }
  return issues;
}

const OPTIONAL = ["end_time", "equipment", "source_reference", "severity", "plant_confirmation", "time_precision", "time_basis", "entry_kind", "annotator_viewed_risk_score"];

/** Body sent to the API. Empty optional fields are omitted on create. Phase 9 merges a PATCH onto the stored
 *  record, so on edit a field that was set and is now empty is sent as null to clear it. */
export function eventPayload(input, expectedVersion, previous) {
  const body = {
    event_type: input.event_type,
    start_time: input.start_time,
    description: input.description,
    source: input.source,
  };
  for (const key of OPTIONAL) {
    const value = input[key];
    if (value != null && value !== "") body[key] = value;
    else if (previous && previous[key] != null) body[key] = null;
  }
  if (expectedVersion != null) body.expected_version = expectedVersion;
  return body;
}
