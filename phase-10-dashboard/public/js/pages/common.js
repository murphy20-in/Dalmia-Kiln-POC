/** The insights → advisory → next steps → actions tail every page shares. Text comes from served fields. */
import { api, getAll, getFrozen } from "../api.js";
import { ACTIONS, ADVICE, ADVISORY, INSIGHTS, SECTION, STEP_TEXT, STEPS, questionText, requestText } from "../copy.js";
import { h } from "../dom.js";
import { findingAnchor, shortStamp } from "../pure/present.js";
import { actionBar, chip, section, to, toast, writeLink } from "../ui.js";

export async function loadStory() {
  const [findings, limitations, requirements, validation, periods] = await Promise.all([
    getFrozen("/api/v1/findings?limit=100"),
    getFrozen("/api/v1/metadata/limitations"),
    getFrozen("/api/v1/metadata/data-requirements"),
    getFrozen("/api/v1/validation/early-warning-historical"),
    getFrozen("/api/v1/abnormal-periods?limit=100"),
  ]);
  return {
    findings: findings.data || [],
    findingsEnvelope: findings,
    limits: limitations.data,
    requirements: requirements.data,
    validation: validation.data,
    validationEnvelope: validation,
    periods: periods.data || [],
    periodsEnvelope: periods,
  };
}

function limitation(story, id) {
  return (story.limits.limitations || []).find((l) => l.id === id);
}

function insight(story, ref) {
  if (ref.startsWith("L")) {
    const lim = limitation(story, ref);
    if (!lim) return null;
    return h("li", { class: "insight" },
      chip("limitation", lim.status),
      h("p", {}, lim.detail),
      h("a", { class: "cite", href: to("/data-quality", {}, lim.id) }, `See evidence · ${lim.id}`));
  }
  const row = story.findings.find((f) => f.finding_id === ref);
  if (!row) return null;
  return h("li", { class: "insight" },
    chip("status", row.classification),
    h("p", {}, row.title),
    h("a", { class: "cite", href: to("/validation", {}, findingAnchor(row.finding_id)) }, `See evidence · ${row.finding_id}`));
}

function advisory(story, key) {
  const item = ADVISORY[key];
  if (item.from === "censoring") {
    const c = story.validation.censoring;
    return h("li", {},
      h("h3", {}, item.title),
      h("p", {}, `${c.n_onset_censored} of ${c.n_periods} onsets are censored by the look-back cap: ${c.meaning}.`),
      h("a", { class: "cite", href: to("/validation", {}, "censoring") }, "Source: Phase 8 censoring"));
  }
  const lim = limitation(story, item.from);
  if (!lim) return null;
  return h("li", {},
    h("h3", {}, item.title),
    h("p", {}, lim.detail),
    h("a", { class: "cite", href: to("/data-quality", {}, lim.id) }, `Source: ${lim.id}`));
}

function copyButton(text) {
  return h("button", {
    type: "button",
    class: "btn btn-secondary btn-small",
    onclick: () => {
      const done = navigator.clipboard?.writeText(text);
      if (!done) return toast(STEP_TEXT.copyFailed);
      done.then(() => toast(STEP_TEXT.copied), () => toast(STEP_TEXT.copyFailed));
    },
  }, STEP_TEXT.copy);
}

export function annotateQuery(period) {
  return { start: period.start_time, end: period.end_time, ref: period.period_id };
}

export function stepItem(story, spec, override) {
  const [kind, arg] = spec.split(":");
  const reqs = story.requirements;
  if (kind === "req") {
    const r = reqs.plant_data_requirements?.[Number(arg)];
    if (!r) return null;
    return h("li", { class: "step" },
      h("div", {}, h("p", { class: "step-text" }, r.data), h("p", { class: "hint" }, `Priority ${r.priority} · ${STEP_TEXT.unblocks(r.unblocks)}`)),
      copyButton(requestText(r)));
  }
  if (kind === "q") {
    const q = reqs.plant_questions_open?.[Number(arg)];
    if (!q) return null;
    return h("li", { class: "step" },
      h("div", {}, h("p", { class: "step-text" }, q), h("p", { class: "hint" }, STEP_TEXT.question)),
      copyButton(questionText(q)));
  }
  if (kind === "annotate") {
    const p = override || story.periods.find((x) => x.kpi_severity_class === arg);
    if (!p) return null;
    return h("li", { class: "step" },
      h("div", {}, h("p", { class: "step-text" }, STEP_TEXT.annotate(p.period_id, `${shortStamp(p.start_time)} – ${shortStamp(p.end_time)}`))),
      writeLink(STEP_TEXT.start, "/events/new", annotateQuery(p), "btn btn-secondary btn-small"));
  }
  if (kind === "revalidation") {
    const r = reqs.revalidation;
    return h("li", { class: "step" },
      h("div", {}, h("p", { class: "step-text" }, STEP_TEXT.revalidation(r.minimum_evaluable_events_for_revalidation)), h("p", { class: "hint" }, `Threshold meaning: ${r.meaning}.`)),
      writeLink(STEP_TEXT.add, "/events/new", {}, "btn btn-secondary btn-small"));
  }
  return null;
}

/** Insights, advisory, next steps and the action bar for a page key. */
export function storySections(key, story, { period } = {}) {
  return [
    section(SECTION.insights, "insights", h("ul", { class: "insights" }, INSIGHTS[key].map((ref) => insight(story, ref)))),
    section(SECTION.advisory, "advisory", h("ul", { class: "advisory" }, ADVICE[key].map((k) => advisory(story, k)))),
    section(SECTION.steps, "steps", h("ol", { class: "steps" }, STEPS[key].map((s) => stepItem(story, s, s.startsWith("annotate") ? period : null)))),
    actionBar(ACTIONS[key]),
  ];
}

export function versions(story, extra = []) {
  return [...extra, `API ${story.findingsEnvelope.service_version}`].join(" · ");
}

/** Version of a served envelope; provenance is one object or a list of artifacts. */
export function artifactVersion(envelope) {
  const p = envelope?.provenance;
  const list = Array.isArray(p) ? p : [p];
  return list.find((x) => x?.artifact_version)?.artifact_version || "—";
}

/** Score rows for a range, from /variant-comparison (3 fields a row). The full range is fetched once per page load. */
let full = null;
export function loadSeries(range) {
  if (range) return getAll("/api/v1/risk-scores/variant-comparison", range);
  if (!full) {
    full = getAll("/api/v1/risk-scores/variant-comparison", {}).catch((err) => {
      full = null;
      throw err;
    });
  }
  return full;
}

/** Served extent of the operational score series (first / last bucket, row count). */
export async function loadExtent() {
  const probe = await getFrozen("/api/v1/risk-scores?limit=1");
  return { ...probe.data_extent, total: probe.pagination?.total, version: probe.provenance?.artifact_version };
}

export function activeEvents(signal) {
  return api("/api/v1/events?status=ACTIVE&limit=100", { signal });
}
