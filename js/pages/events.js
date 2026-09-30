import { api } from "../api.js";
import { h } from "../dom.js";
import { eventPayload, validateActor, validateEvent, EVENT_TYPES, SOURCES, SEVERITIES, CONFIRMATIONS, TIME_PRECISIONS, TIME_BASES, ENTRY_KINDS } from "../pure/form.js";
import { toApiTimestamp, toLocalInput } from "../pure/query.js";
import { readActor, writeActor } from "../state.js";
import { failure, field, links, loading, pageHeader, select, stamp } from "../ui.js";

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading plant event annotations…"));
  const state = { editing: null, rows: [] };
  try {
    await paint(root, ctx, state);
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "Plant event annotations could not be loaded."));
  }
}

async function paint(root, ctx, state) {
  const body = await api("/api/v1/events?status=ALL&limit=100", { signal: ctx.signal });
  state.rows = body.data || [];
  const listHost = h("div", { id: "event-list" });
  const formHost = h("div", { id: "event-form" });
  const auditHost = h("div", { id: "event-audit" });
  root.replaceChildren(
    pageHeader("Plant event annotations", "Plant annotations are supplied independently of the analytical score and are intended to provide ground truth for future validation."),
    h("p", { class: "callout" }, "A plant event is not a KPI-derived abnormal period. Overlap between the two is shown as overlap, not as a detection."),
    actorBar(),
    listHost,
    formHost,
    auditHost,
    links(),
  );
  renderList(listHost, state, ctx, root);
  renderForm(formHost, state, ctx, root, auditHost);
}

function actorBar() {
  const input = h("input", {
    id: "actor",
    maxlength: "100",
    autocomplete: "name",
    value: readActor(),
    "aria-describedby": "actor-help",
  });
  input.addEventListener("change", () => writeActor(input.value.trim()));
  return h("div", { class: "actor" },
    h("label", { for: "actor" }, "Actor"),
    input,
    h("p", { id: "actor-help", class: "hint" }, "X-Actor is attribution only. It is not authentication. This POC has no login."));
}

function renderList(host, state, ctx, root) {
  const active = state.rows.filter((row) => row.status !== "DELETED");
  if (!state.rows.length) {
    host.replaceChildren(h("p", { class: "state" }, "No plant event annotations have been recorded yet."));
    return;
  }
  const headers = ["Type", "Start", "End", "Equipment", "Source", "Description", "Status", "Created by", "Created", ""];
  const body = state.rows.map((row) => {
    const actions = h("td", { "data-label": "Actions" },
      h("button", { type: "button", onclick: () => edit(row, state, ctx, root) }, "Edit"));
    if (row.status === "ACTIVE") {
      actions.append(" ");
      actions.append(h("button", { type: "button", onclick: () => remove(row, state, ctx, root) }, "Soft delete"));
    }
    return h("tr", {},
      h("td", { "data-label": "Type" }, row.event_type),
      h("td", { "data-label": "Start" }, stamp(row.start_time)),
      h("td", { "data-label": "End" }, stamp(row.end_time)),
      h("td", { "data-label": "Equipment" }, row.equipment || "—"),
      h("td", { "data-label": "Source" }, row.source),
      h("td", { "data-label": "Description" }, row.description),
      h("td", { "data-label": "Status" }, `${row.status} · v${row.version}`),
      h("td", { "data-label": "Created by" }, row.created_by),
      h("td", { "data-label": "Created" }, stamp(row.created_at)),
      actions);
  });
  const hint = active.length === state.rows.length
    ? "Deleted annotations stay in the list so the audit remains visible."
    : "Deleted rows stay readable. They cannot be edited.";
  host.replaceChildren(
    h("div", { class: "table-wrap" },
      h("table", { class: "resp" },
        h("caption", {}, "Plant event annotations"),
        h("thead", {}, h("tr", {}, headers.map((cell) => h("th", { scope: "col" }, cell)))),
        h("tbody", {}, body))),
    h("p", { class: "hint" }, hint));
  const overlaps = state.rows.filter((row) => row.analytical_context?.overlapping_kpi_derived_abnormal_periods?.length);
  if (overlaps.length) {
    host.append(h("ul", { class: "overlap" }, overlaps.map((row) =>
      h("li", {}, `Plant event ${row.event_type} (${row.event_id.slice(0, 8)}) overlaps KPI-derived abnormal period ${row.analytical_context.overlapping_kpi_derived_abnormal_periods.join(", ")}. The labels stay separate.`))));
  }
}

function edit(row, state, ctx, root) {
  state.editing = row;
  renderForm(root.querySelector("#event-form"), state, ctx, root, root.querySelector("#event-audit"));
  root.querySelector("#event-form").scrollIntoView({ block: "nearest" });
}

function renderForm(host, state, ctx, root, auditHost) {
  const row = state.editing;
  const errors = {};
  const status = h("p", { id: "event-status", class: "hint", role: "status" });
  const form = h("form", { class: "event-form", novalidate: true },
    h("h2", {}, row ? `Edit ${row.event_type}` : "New plant annotation"),
    row ? h("p", { class: "hint" }, `Version ${row.version}. Saving sends this version so a newer edit is not overwritten.`) : null,
    field("event_type", "Event type", select("event_type", EVENT_TYPES.map((v) => [v, v]), row?.event_type || "COATING")),
    field("start_time", "Start time", h("input", { id: "start_time", type: "datetime-local", required: true, value: toLocalInput(row?.start_time || "") })),
    field("end_time", "End time (optional)", h("input", { id: "end_time", type: "datetime-local", value: toLocalInput(row?.end_time || "") })),
    field("equipment", "Equipment (optional)", h("input", { id: "equipment", maxlength: "100", value: row?.equipment || "" })),
    field("source", "Source", select("source", SOURCES.map((v) => [v, v]), row?.source || "PLANT_LOG")),
    field("description", "Description", h("textarea", { id: "description", required: true, maxlength: "2000", rows: "4" }, row?.description || "")),
    h("details", {},
      h("summary", {}, "Optional record fields"),
      field("source_reference", "Source reference", h("input", { id: "source_reference", maxlength: "200", value: row?.source_reference || "" })),
      field("severity", "Plant severity", select("severity", [["", "—"], ...SEVERITIES.map((v) => [v, v])], row?.severity || "")),
      field("plant_confirmation", "Plant confirmation", select("plant_confirmation", [["", "—"], ...CONFIRMATIONS.map((v) => [v, v])], row?.plant_confirmation || "")),
      field("time_precision", "Time precision", select("time_precision", [["", "—"], ...TIME_PRECISIONS.map((v) => [v, v])], row?.time_precision || "")),
      field("time_basis", "Time basis", select("time_basis", [["", "—"], ...TIME_BASES.map((v) => [v, v])], row?.time_basis || "")),
      field("entry_kind", "Entry kind", select("entry_kind", [["", "—"], ...ENTRY_KINDS.map((v) => [v, v])], row?.entry_kind || "")),
      field("viewed", "Annotator had looked at the risk score", select("viewed", [["", "Not recorded"], ["true", "Yes"], ["false", "No"]], viewedValue(row)))),
    h("div", { class: "form-actions" },
      h("button", { type: "submit" }, row ? "Save changes" : "Record annotation"),
      row ? h("button", { type: "button", id: "cancel-edit" }, "Cancel edit") : null,
      row ? h("button", { type: "button", id: "show-audit" }, "Audit history") : null),
    status,
  );
  form.addEventListener("submit", (event) => submit(event, form, state, ctx, root, status));
  form.querySelector("#cancel-edit")?.addEventListener("click", () => {
    state.editing = null;
    renderForm(host, state, ctx, root, auditHost);
  });
  form.querySelector("#show-audit")?.addEventListener("click", () => loadAudit(auditHost, row, ctx));
  host.replaceChildren(form, h("div", { id: "form-errors" }));
  void errors;
}

function viewedValue(row) {
  if (!row || row.annotator_viewed_risk_score == null) return "";
  return row.annotator_viewed_risk_score ? "true" : "false";
}

function readInput(form) {
  const value = (id) => form.querySelector(`#${id}`).value;
  const viewed = value("viewed");
  return {
    event_type: value("event_type"),
    start_time: toApiTimestamp(value("start_time")) || "",
    end_time: value("end_time") ? (toApiTimestamp(value("end_time")) || "") : "",
    equipment: value("equipment").trim(),
    source: value("source"),
    description: value("description"),
    source_reference: value("source_reference").trim(),
    severity: value("severity"),
    plant_confirmation: value("plant_confirmation"),
    time_precision: value("time_precision"),
    time_basis: value("time_basis"),
    entry_kind: value("entry_kind"),
    annotator_viewed_risk_score: viewed === "" ? undefined : viewed === "true",
  };
}

async function submit(event, form, state, ctx, root, status) {
  event.preventDefault();
  const actor = root.querySelector("#actor").value.trim();
  writeActor(actor);
  const actorError = validateActor(actor);
  const input = readInput(form);
  if (form.querySelector("#start_time").value && !input.start_time) {
    status.textContent = "Start time must be a valid plant-local time with no timezone offset.";
    return;
  }
  if (form.querySelector("#end_time").value && !input.end_time) {
    status.textContent = "End time must be a valid plant-local time with no timezone offset.";
    return;
  }
  const issues = validateEvent(input);
  if (actorError) issues.unshift({ field: "actor", issue: actorError });
  if (issues.length) {
    status.textContent = issues.map((issue) => issue.issue).join(" ");
    return;
  }
  status.textContent = "Saving…";
  try {
    if (state.editing) {
      await api(`/api/v1/events/${state.editing.event_id}`, {
        method: "PATCH",
        actor,
        body: eventPayload(input, state.editing.version),
        signal: ctx.signal,
      });
    } else {
      await api("/api/v1/events", { method: "POST", actor, body: eventPayload(input), signal: ctx.signal });
    }
    state.editing = null;
    await paint(root, ctx, state);
    root.querySelector("#event-status").textContent = "Saved.";
  } catch (err) {
    if (err?.name === "AbortError") return;
    if (err.status === 409 && state.editing) {
      status.textContent = "This annotation was changed before the save. It has been reloaded; review it and save again if it is still correct.";
      try {
        const fresh = await api(`/api/v1/events/${state.editing.event_id}`, { signal: ctx.signal });
        state.editing = fresh.data;
        renderForm(root.querySelector("#event-form"), state, ctx, root, root.querySelector("#event-audit"));
        root.querySelector("#event-status").textContent = status.textContent;
      } catch (reloadErr) {
        status.textContent = reloadErr.message;
      }
      return;
    }
    status.textContent = err.message;
  }
}

async function remove(row, state, ctx, root) {
  const actor = root.querySelector("#actor").value.trim();
  const actorError = validateActor(actor);
  if (actorError) {
    root.querySelector("#event-status")?.replaceChildren();
    const note = root.querySelector("#event-form p[role=status]") || root.querySelector(".hint");
    if (note) note.textContent = actorError;
    return;
  }
  if (!window.confirm(`Soft-delete ${row.event_type} starting ${stamp(row.start_time)}? The audit history is kept.`)) return;
  writeActor(actor);
  try {
    await api(`/api/v1/events/${row.event_id}?expected_version=${row.version}`, { method: "DELETE", actor, signal: ctx.signal });
    state.editing = null;
    await paint(root, ctx, state);
  } catch (err) {
    if (err.status === 409) {
      window.alert("This annotation changed before it could be deleted. The list has been refreshed.");
      await paint(root, ctx, state);
      return;
    }
    window.alert(err.message);
  }
}

async function loadAudit(host, row, ctx) {
  host.replaceChildren(loading("Loading audit history…"));
  try {
    const body = await api(`/api/v1/events/${row.event_id}/audit`, { signal: ctx.signal });
    const rows = body.data || [];
    host.replaceChildren(h("h2", {}, "Audit history"),
      rows.length ? h("ol", { class: "audit" }, rows.map((entry) =>
        h("li", {}, `${entry.action || entry.operation || "change"} · ${stamp(entry.at)} · ${entry.actor}`)))
        : h("p", {}, "No audit rows returned."));
  } catch (err) {
    host.replaceChildren(failure(err, "Audit history could not be loaded."));
  }
}
