import { api, getAll } from "../api.js";
import { trendFigure } from "../chart.js";
import { MSG, PAGE, PERIOD_LABEL, READ_ONLY } from "../copy.js";
import { h } from "../dom.js";
import { CONFIRMATIONS, ENTRY_KINDS, EVENT_TYPES, SEVERITIES, SOURCES, TIME_BASES, TIME_PRECISIONS, eventPayload, validateActor, validateEvent } from "../pure/form.js";
import { countBy, plain, shortStamp } from "../pure/present.js";
import { toApiTimestamp, toLocalInput } from "../pure/query.js";
import { addMinutes } from "../pure/series.js";
import { readActor, writeActor } from "../state.js";
import { enumText, facts, failure, field, hero, kpis, loading, readOnly, roButton, section, select, table, to, toast, writeLink } from "../ui.js";
import { loadExtent, loadStory, storySections, versions } from "./common.js";

const human = (v) => plain("x", v).text;
const options = (list) => list.map((v) => [v, human(v)]);

export async function render(root, ctx) {
  root.replaceChildren(hero(PAGE.events), loading());
  const { mode, id } = ctx.route;
  const [story, extent, status, list] = await Promise.all([
    loadStory(),
    loadExtent(),
    api("/api/v1/metadata/status", { signal: ctx.signal }),
    getAll("/api/v1/events", { status: "ALL" }, { signal: ctx.signal, pageLimit: 100 }),
  ]);
  const rows = list.rows;
  const one = id ? await loadOne(id, ctx) : null;
  let panel = null;
  if (mode === "new") panel = formPanel(ctx, null);
  else if (mode === "edit") panel = one ? formPanel(ctx, one) : missing(id);
  else if (mode === "detail") panel = one ? await detailPanel(ctx, one) : missing(id);

  const gt = status.data.ground_truth;
  const st = countBy(rows, "status");
  const active = rows.filter((r) => r.status === "ACTIVE");
  root.replaceChildren(
    hero(PAGE.events),
    panel,
    kpis([
      { label: "Active annotations", value: String(st.get("ACTIVE") || 0), meaning: "plant-supplied records in the annotation store", source: "Phase 9 · /events", link: to("/events", {}, "list") },
      { label: "Withdrawn", value: String(st.get("DELETED") || 0), meaning: "kept readable with their audit trail", source: "Phase 9 · /events", link: to("/events", {}, "list") },
      { label: "Needed to revalidate", value: `≥ ${gt.minimum_recommended_for_revalidation}`, meaning: "evaluable plant-labelled events before Phase 8 can be re-run", source: "Phase 9 · /metadata/status", link: to("/validation", {}, "primary") },
      { label: "Event ground truth", value: status.data.provenance?.ground_truth_status ? plain("status", status.data.provenance.ground_truth_status).text : "—", raw: status.data.provenance?.ground_truth_status, meaning: "no plant event records in the supplied data", source: "Phase 9 · /metadata/status", link: to("/data-quality", {}, "L01") },
    ]),
    section("Annotations on the calendar", "graph", trendFigure({
      compact: true,
      title: `Plant annotations and ${PERIOD_LABEL}, Jun–Aug 2025`,
      description: "Diamonds are active plant annotations; select one to open it. Hatched bands are KPI-derived periods for orientation only; overlap is shown as overlap, never as a detection.",
      start: extent.first_timestamp,
      end: addMinutes(extent.last_timestamp, 10),
      series: [],
      periods: story.periods,
      events: active,
      periodHref: (pid) => to(`/abnormal-periods/${pid}`),
      eventHref: (eid) => to(`/events/${eid}`),
      footnote: `Annotations: ${plain("label", list.envelope?.provenance?.source || "PLANT_SUPPLIED_ANNOTATION").text} · periods ${story.periods[0]?.method_version || "—"} · ${versions(story)}`,
    })),
    section("All annotations", "list", active.length ? null : emptyState(), rows.length ? annotationTable(rows, active.length ? "Plant annotations, newest first as served" : "Withdrawn annotations — kept in the audit trail") : null),
    ...storySections("events", story),
  );
}

async function loadOne(id, ctx) {
  try {
    return (await api(`/api/v1/events/${id}`, { signal: ctx.signal })).data;
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    if (err?.status === 404) return null;
    throw err;
  }
}

function missing(id) {
  return h("section", { class: "detail", id: "detail", tabindex: "-1", "data-focus": "", "aria-labelledby": "detail-h" },
    h("h2", { id: "detail-h" }, "Annotation not found"),
    h("p", {}, `No annotation has the id ${id}.`),
    h("a", { class: "btn btn-secondary", href: to("/events") }, "All annotations"));
}

function emptyState() {
  return h("div", { class: "empty" },
    h("p", {}, MSG.noAnnotations),
    writeLink(MSG.addFirst, "/events/new"));
}

function annotationTable(rows, caption) {
  return table(caption, ["Annotation", "Type", "Start", "End", "Status", "Recorded by"],
    rows.map((r) => [
      h("a", { href: to(`/events/${r.event_id}`) }, `Open ${r.event_id.slice(0, 8)}`),
      human(r.event_type),
      shortStamp(r.start_time, true),
      r.end_time ? shortStamp(r.end_time, true) : "—",
      `${plain("eventStatus", r.status).text} · version ${r.version}`,
      r.created_by,
    ]));
}

async function detailPanel(ctx, ev) {
  const audit = h("div", {}, loading("Loading the audit trail…"));
  const overlaps = ev.analytical_context?.overlapping_kpi_derived_abnormal_periods || [];
  const actions = h("div", { class: "action-bar" });
  if (ev.status === "ACTIVE") {
    actions.append(
      writeLink("Edit", `/events/${ev.event_id}/edit`, {}, "btn btn-primary"),
      readOnly ? roButton("Withdraw", "btn btn-secondary")
        : h("button", { type: "button", class: "btn btn-secondary", onclick: (e) => withdraw(ctx, ev, e.currentTarget) }, "Withdraw"));
  }
  actions.append(h("a", { class: "btn btn-ghost", href: to("/history", { from: addMinutes(ev.start_time, -1440), to: addMinutes(ev.end_time || ev.start_time, 1440) }) }, "View on trend"),
    h("a", { class: "btn btn-ghost", href: to("/events") }, "All annotations"));
  const panel = h("section", { class: "detail", id: "detail", tabindex: "-1", "data-focus": "", "aria-labelledby": "detail-h" },
    h("p", { class: "detail-kicker" }, "Plant-supplied annotation"),
    h("h2", { id: "detail-h" }, `${human(ev.event_type)} · ${shortStamp(ev.start_time, true)}`),
    h("p", { class: "plant-text" }, ev.description),
    facts([
      ["Status", `${plain("eventStatus", ev.status).text} · version ${ev.version}`],
      ["Start", shortStamp(ev.start_time, true)],
      ["End", ev.end_time ? shortStamp(ev.end_time, true) : "—"],
      ["Equipment", ev.equipment || "—"],
      ["Source", `${human(ev.source)}${ev.source_reference ? ` · ${ev.source_reference}` : ""}`],
      ["Plant severity", ev.severity ? human(ev.severity) : "—"],
      ["Plant confirmation", ev.plant_confirmation ? human(ev.plant_confirmation) : "—"],
      ["Annotator had viewed the score", ev.annotator_viewed_risk_score == null ? "Not recorded" : ev.annotator_viewed_risk_score ? "Yes" : "No"],
      ["Overlapping KPI-derived periods", overlaps.length ? overlaps.map((pid) => h("a", { href: to(`/abnormal-periods/${pid}`) }, pid)).flatMap((a, i) => (i ? [", ", a] : [a])) : "None (overlap is context, not a detection)"],
      ["Recorded by", `${ev.created_by} · ${ev.created_at}`],
    ]),
    actions,
    h("h3", {}, "Audit trail"),
    audit);
  api(`/api/v1/events/${ev.event_id}/audit`, { signal: ctx.signal }).then((body) => {
    const items = body.data || [];
    audit.replaceChildren(items.length
      ? h("ol", { class: "audit" }, items.map((a) => h("li", {}, `${human(a.operation || "change")} · ${a.at} · ${a.actor}${a.new_value?.version ? ` · version ${a.new_value.version}` : ""}`)))
      : h("p", {}, "No audit rows were returned."));
  }).catch((err) => {
    if (err?.name !== "AbortError") audit.replaceChildren(failure(err));
  });
  return panel;
}

async function withdraw(ctx, ev, button) {
  let actor = readActor();
  if (validateActor(actor)) {
    actor = (window.prompt(MSG.actorPrompt) || "").trim();
    const problem = validateActor(actor);
    if (problem) {
      toast(problem);
      return;
    }
    writeActor(actor);
  }
  if (!window.confirm(MSG.withdrawConfirm(human(ev.event_type), shortStamp(ev.start_time, true)))) return;
  button.disabled = true;
  try {
    // No route signal: leaving the page must not hide whether a committed write happened.
    await api(`/api/v1/events/${ev.event_id}?expected_version=${ev.version}`, { method: "DELETE", actor });
    toast(MSG.withdrawn);
  } catch (err) {
    toast(err.status === 409 ? MSG.conflict : err.message);
  }
  ctx.go(to(`/events/${ev.event_id}`), { replace: true });
}

function formPanel(ctx, ev) {
  const q = ctx.route.query;
  const ref = !ev && /^P6-\d{3}$/.test(q.ref || "") ? q.ref : "";
  const start = ev?.start_time || toApiTimestamp(q.start) || "";
  const end = ev?.end_time || toApiTimestamp(q.end) || "";
  const viewed = ev ? (ev.annotator_viewed_risk_score == null ? "" : String(ev.annotator_viewed_risk_score)) : (ref ? "true" : "");
  const status = h("p", { class: "form-status", role: "alert", id: "form-status" });
  const opt = (list, value) => [["", "—"], ...options(list)];
  const form = h("form", { class: "event-form", novalidate: true },
    h("fieldset", { disabled: readOnly, "aria-describedby": readOnly ? "form-ro" : null },
      h("legend", {}, ev ? `Edit annotation (version ${ev.version})` : "New plant annotation"),
      ref ? h("p", { class: "callout" }, MSG.fromPeriod(ref)) : null,
      field("actor", "Your name or role (required)", h("input", { id: "actor", maxlength: "100", autocomplete: "name", required: true, value: readActor() }), MSG.actorHelp),
      field("event_type", "What the plant records say happened (required)", select("event_type", [["", "Choose a type…"], ...options(EVENT_TYPES)], ev?.event_type || "", { required: true })),
      h("div", { class: "field-row" },
        field("start_time", "Start (required; plant-local, no timezone)", h("input", { id: "start_time", type: "datetime-local", required: true, value: toLocalInput(start) })),
        field("end_time", "End (optional)", h("input", { id: "end_time", type: "datetime-local", value: toLocalInput(end) }))),
      field("description", "Description (required)", h("textarea", { id: "description", required: true, maxlength: "2000", rows: "4" }, ev?.description || "")),
      h("div", { class: "field-row" },
        field("source", "Source", select("source", options(SOURCES), ev?.source || "PLANT_LOG")),
        field("equipment", "Equipment (optional)", h("input", { id: "equipment", maxlength: "100", value: ev?.equipment || "" }))),
      field("viewed", "Had you looked at the risk score before writing this?", select("viewed", [["", "Not recorded"], ["true", "Yes"], ["false", "No"]], viewed), ref ? MSG.viewedScore : null),
      h("details", {},
        h("summary", {}, "More record fields (optional)"),
        field("source_reference", "Source reference", h("input", { id: "source_reference", maxlength: "200", value: ev?.source_reference || "" })),
        field("severity", "Plant severity", select("severity", opt(SEVERITIES), ev?.severity || "")),
        field("plant_confirmation", "Plant confirmation", select("plant_confirmation", opt(CONFIRMATIONS), ev?.plant_confirmation || ""), MSG.confirmationHint),
        field("time_precision", "Time precision", select("time_precision", opt(TIME_PRECISIONS), ev?.time_precision || "")),
        field("time_basis", "Time basis", select("time_basis", opt(TIME_BASES), ev?.time_basis || ""), MSG.timeBasisHint),
        field("entry_kind", "Entry kind", select("entry_kind", opt(ENTRY_KINDS), ev?.entry_kind || ""), MSG.entryKindHint))),
    h("div", { class: "action-bar" },
      readOnly ? h("span", { class: "ro-wrap" }, h("button", { type: "button", class: "btn btn-primary", "aria-disabled": "true", "aria-describedby": "form-ro" }, ev ? "Save changes" : "Save annotation"), h("span", { class: "ro-reason", id: "form-ro" }, READ_ONLY.reason))
        : h("button", { type: "submit", class: "btn btn-primary" }, ev ? "Save changes" : "Save annotation"),
      h("a", { class: "btn btn-ghost", href: to(ev ? `/events/${ev.event_id}` : "/events") }, "Cancel")),
    status);
  form.addEventListener("submit", (event) => submit(event, form, ctx, ev, status));
  return h("section", { class: "detail", id: "detail", tabindex: "-1", "data-focus": "", "aria-labelledby": "detail-h" },
    h("h2", { id: "detail-h" }, ev ? "Edit annotation" : "Add a plant annotation"),
    form);
}

function readInput(form) {
  const v = (name) => form.querySelector(`#${name}`).value;
  const viewed = v("viewed");
  return {
    event_type: v("event_type"),
    start_time: toApiTimestamp(v("start_time")) || "",
    end_time: v("end_time") ? (toApiTimestamp(v("end_time")) || "") : "",
    equipment: v("equipment").trim(),
    source: v("source"),
    description: v("description"),
    source_reference: v("source_reference").trim(),
    severity: v("severity"),
    plant_confirmation: v("plant_confirmation"),
    time_precision: v("time_precision"),
    time_basis: v("time_basis"),
    entry_kind: v("entry_kind"),
    annotator_viewed_risk_score: viewed === "" ? undefined : viewed === "true",
  };
}

async function submit(event, form, ctx, ev, status) {
  event.preventDefault();
  if (readOnly) return;
  const actor = form.querySelector("#actor").value.trim();
  const input = readInput(form);
  const issues = validateEvent(input);
  const actorError = validateActor(actor);
  if (actorError) issues.unshift({ field: "actor", issue: actorError });
  if (issues.length) {
    showIssues(form, status, issues);
    return;
  }
  showIssues(form, status, []);
  writeActor(actor);
  status.textContent = "Saving…";
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    // No route signal: leaving the page must not hide whether a committed write happened.
    const body = ev
      ? await api(`/api/v1/events/${ev.event_id}`, { method: "PATCH", actor, body: eventPayload(input, ev.version, ev) })
      : await api("/api/v1/events", { method: "POST", actor, body: eventPayload(input) });
    toast(MSG.saved);
    ctx.go(to(`/events/${body.data.event_id}`), { replace: Boolean(ev) });
  } catch (err) {
    button.disabled = false;
    if (err.status === 409 && ev) {
      toast(MSG.conflict);
      ctx.go(to(`/events/${ev.event_id}/edit`), { replace: true });
      return;
    }
    if (err.details?.length) showIssues(form, status, err.details, true);
    else status.textContent = err.message;
  }
}

const FIELD_ID = { annotator_viewed_risk_score: "viewed" };

/** Each invalid control is marked and described by the error line; focus moves to the first. */
function showIssues(form, status, issues, named = false) {
  for (const el of form.querySelectorAll("[aria-invalid]")) el.removeAttribute("aria-invalid");
  status.textContent = issues.map((i) => (named && i.field && i.field !== "*" ? `${i.field.replace(/_/g, " ")}: ${i.issue}` : i.issue)).join(" ");
  let first = null;
  for (const i of issues) {
    const el = form.querySelector(`#${FIELD_ID[i.field] || i.field}`);
    if (!el) continue;
    el.setAttribute("aria-invalid", "true");
    const described = (el.getAttribute("aria-describedby") || "").split(" ").filter(Boolean);
    if (!described.includes("form-status")) el.setAttribute("aria-describedby", [...described, "form-status"].join(" "));
    first ||= el;
  }
  first?.focus();
}
