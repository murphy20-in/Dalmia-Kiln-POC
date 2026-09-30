import { api, getAll } from "../api.js";
import { defaultWindow, timeSeriesFigure } from "../chart.js";
import { h } from "../dom.js";
import { toApiTimestamp, toLocalInput } from "../pure/query.js";
import { addMinutes } from "../pure/series.js";
import { failure, links, loading, pageHeader, stamp } from "../ui.js";

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading the historical score window…"));
  try {
    const probe = await api("/api/v1/risk-scores?limit=1", { signal: ctx.signal });
    const extent = probe.data_extent;
    let range = ctx.range || defaultWindow(extent);
    if (!ctx.range && range) ctx.setRange(range);
    root.replaceChildren(shell(extent, range, ctx));
    await draw(root, range, ctx);
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "Historical score data could not be loaded. Check that the analytical service is available."));
  }
}

function shell(extent, range, ctx) {
  const form = h("form", { class: "controls", id: "score-controls" },
    h("div", { class: "field" },
      h("label", { for: "score-start" }, "Start (inclusive)"),
      h("input", { id: "score-start", type: "datetime-local", required: true, value: toLocalInput(range.start) })),
    h("div", { class: "field" },
      h("label", { for: "score-end" }, "End (exclusive)"),
      h("input", { id: "score-end", type: "datetime-local", required: true, value: toLocalInput(range.end) })),
    h("label", { class: "check" },
      h("input", { id: "show-o2", type: "checkbox" }),
      "Show O₂-excluded sensitivity"),
    h("label", { class: "check" },
      h("input", { id: "show-periods", type: "checkbox", checked: true }),
      "Show KPI-derived periods"),
    h("label", { class: "check" },
      h("input", { id: "show-events", type: "checkbox" }),
      "Show plant events"),
    h("button", { type: "submit" }, "Apply window"),
    h("button", { type: "button", id: "zoom-recent" }, "Last 14 days"),
    h("button", { type: "button", id: "zoom-full" }, "Operational window"),
    h("button", { type: "button", id: "zoom-reset" }, "Reset"),
    h("p", { id: "range-error", class: "field-error", role: "alert" }));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const next = readForm(form);
    const err = form.querySelector("#range-error");
    if (!next) {
      err.textContent = "Enter a plant-local start and end. End must be later than start. Offsets are not accepted.";
      return;
    }
    err.textContent = "";
    ctx.setRange(next);
    draw(form.closest("main") || document.getElementById("main"), next, ctx);
  });
  form.querySelector("#zoom-recent").addEventListener("click", () => apply(form, defaultWindow(extent), ctx));
  form.querySelector("#zoom-full").addEventListener("click", () => apply(form, {
    start: extent.first_timestamp,
    end: addMinutes(extent.last_timestamp, 10),
  }, ctx));
  form.querySelector("#zoom-reset").addEventListener("click", () => apply(form, defaultWindow(extent), ctx));
  form.querySelector("#show-o2").addEventListener("change", () => form.requestSubmit());
  form.querySelector("#show-periods").addEventListener("change", () => form.requestSubmit());
  form.querySelector("#show-events").addEventListener("change", () => form.requestSubmit());

  return h("div", {},
    pageHeader("Historical risk", "Empirical POC risk score for operational rows. The line is the historical score magnitude."),
    h("p", { class: "meta-line" }, `Series extent ${stamp(extent.first_timestamp)} – ${stamp(extent.last_timestamp)} · ${extent.n_rows.toLocaleString("en-GB")} operational rows. ${extent.gap_rule}`),
    form,
    h("div", { id: "score-stage" }, loading("Loading scores for this window…")),
    links());
}

function apply(form, range, ctx) {
  form.querySelector("#score-start").value = toLocalInput(range.start);
  form.querySelector("#score-end").value = toLocalInput(range.end);
  ctx.setRange(range);
  draw(document.getElementById("main"), range, ctx);
}

function readForm(form) {
  const start = toApiTimestamp(form.querySelector("#score-start").value);
  const end = toApiTimestamp(form.querySelector("#score-end").value);
  if (!start || !end || start >= end) return null;
  return { start, end };
}

let drawToken = 0;

async function draw(root, range, ctx) {
  const token = ++drawToken;
  const stage = root.querySelector("#score-stage");
  const form = root.querySelector("#score-controls");
  if (!stage || !form) return;
  const showO2 = form.querySelector("#show-o2").checked;
  const showPeriods = form.querySelector("#show-periods").checked;
  const showEvents = form.querySelector("#show-events").checked;
  stage.replaceChildren(loading("Loading scores for this window…"));
  try {
    const scoreReq = showO2
      ? getAll("/api/v1/risk-scores/variant-comparison", range, { signal: ctx.signal })
      : getAll("/api/v1/risk-scores", { ...range, variant: "primary" }, { signal: ctx.signal });
    const [scores, periods, events] = await Promise.all([
      scoreReq,
      showPeriods ? api(`/api/v1/abnormal-periods?start=${range.start}&end=${range.end}&limit=100`, { signal: ctx.signal }) : null,
      showEvents ? api(`/api/v1/events?start=${range.start}&end=${range.end}&status=ACTIVE&limit=100`, { signal: ctx.signal }) : null,
    ]);
    if (token !== drawToken) return;
    if (!scores.rows.length) {
      stage.replaceChildren(h("p", { class: "state", role: "status" }, "No operational analytical data is available for this period."));
      return;
    }
    const variant = scores.envelope.variant || scores.envelope.variants?.primary;
    const rows = showO2
      ? scores.rows.map((row) => ({
        timestamp: row.timestamp,
        primary_empirical_risk_score: row.primary_empirical_risk_score,
        o2_excluded_empirical_risk_score: row.o2_excluded_empirical_risk_score,
      }))
      : scores.rows;
    const chart = timeSeriesFigure({
      title: "Historical empirical risk score",
      titleId: "score-title",
      descId: "score-desc",
      description: `Historical empirical risk score from ${stamp(range.start)} through ${stamp(range.end)}. Gaps indicate unavailable data, not a zero score.`,
      start: range.start,
      end: range.end,
      gaps: scores.gaps,
      showSensitivity: showO2,
      periods: showPeriods ? periods.data : null,
      events: showEvents ? events.data : null,
      series: showO2
        ? [
          { name: "Primary", key: "primary_empirical_risk_score", rows },
          { name: "O₂-excluded sensitivity", key: "o2_excluded_empirical_risk_score", rows, dash: true },
        ]
        : [{ name: "Primary", key: "empirical_risk_score", rows }],
    });
    const notes = [
      h("p", { class: "meta-line" }, `${scores.envelope.disclaimer || ""}`),
      variant?.preference_note ? h("p", { class: "meta-line" }, `${variant.variant_status || "primary"} · preferred = ${variant.preferred}. ${variant.preference_note}`) : null,
    ];
    if (showO2) {
      const o2 = scores.envelope.variants?.o2_excluded;
      notes.push(h("p", { class: "callout" }, "O₂-excluded is a sensitivity analysis. The kiln-inlet O₂ analyser behaviour remains an unresolved plant question."),
        h("p", { class: "meta-line" }, o2 ? `O₂-excluded status ${o2.variant_status}. preferred = ${o2.preferred}.` : ""));
    }
    stage.replaceChildren(...notes, chart.figure, chart.table);
  } catch (err) {
    if (err?.name === "AbortError") return;
    stage.replaceChildren(failure(err, "Historical score data could not be loaded. Check that the analytical service is available."));
  }
}
