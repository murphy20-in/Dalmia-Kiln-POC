import { api } from "../api.js";
import { h } from "../dom.js";
import { failure, fmt, links, loading, pageHeader, stamp } from "../ui.js";

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading analytical overview…"));
  try {
    const [meta, status, periods, events, requirements] = await Promise.all([
      api("/api/v1/metadata", { signal: ctx.signal }),
      api("/api/v1/metadata/status", { signal: ctx.signal }),
      api("/api/v1/abnormal-periods?limit=1", { signal: ctx.signal }),
      api("/api/v1/events?limit=1", { signal: ctx.signal }),
      api("/api/v1/metadata/data-requirements", { signal: ctx.signal }),
    ]);
    const data = meta.data;
    const gt = status.data.ground_truth;
    const validation = data.validation_state.phase8_primary_endpoint;
    root.replaceChildren(
      pageHeader("Overview", "Historical evidence from the Ariyalur kiln POC. Figures below are read from the analytical service."),
      h("section", { class: "strip", "aria-label": "Project status" },
        h("p", {}, h("span", { class: "k" }, "Mode"), h("span", {}, "Historical analysis")),
        h("p", {}, h("span", { class: "k" }, "Service"), h("span", {}, `${data.phase_name} (${data.service_version})`)),
        h("p", {}, h("span", { class: "k" }, "Early-warning validation"), h("span", {}, validation)),
        h("p", {}, h("span", { class: "k" }, "Plant event ground truth"), h("span", {}, data.event_ground_truth_status))),
      h("section", { class: "cards", "aria-label": "Evidence summary" },
        card("Operational score rows", "…", data.periods.operational_scoring_period, { "data-score-card": "1" }),
        card("KPI-derived abnormal periods", String(periods.pagination.total), "Phase 6 periods. Not plant events."),
        card("Plant annotations", String(gt.plant_annotations_recorded), "Plant-supplied records. Ground truth is still " + data.event_ground_truth_status + "."),
        card("Validation status", validation, data.validation_state.o2_excluded_note),
        card("Missing months", String(data.periods.missing_months.length), data.periods.missing_months.map((m) => `${m.dataset} ${m.month}`).join("; "))),
      h("section", {},
        h("h2", {}, "Open this evidence"),
        h("ul", { class: "view-list" },
          item("/history", "Historical risk", "Empirical score trend, gaps, and the O₂-excluded sensitivity overlay."),
          item("/abnormal-periods", "Abnormal periods", "The KPI-derived periods and their score trajectories."),
          item("/events", "Plant events", "Enter plant annotations independently of the score."),
          item("/validation", "Validation", "Phase 8 historical result, including the negative result."),
          item("/data-quality", "Data quality", "Coverage, missing periods, and open plant questions."))),
      h("section", {},
        h("h2", {}, "What remains unvalidated"),
        h("p", {}, "Plant event annotations will provide the ground truth needed to re-run the frozen validation protocol. No current dashboard result should be interpreted as a validated plant-event detector."),
        h("ul", {}, (requirements.data.plant_data_requirements || []).slice(0, 4).map((row) =>
          h("li", {}, row.data))),
        links()),
    );
    const scoreCard = root.querySelector("[data-score-card]");
    const score = await api("/api/v1/risk-scores?limit=1", { signal: ctx.signal });
    if (scoreCard) {
      scoreCard.querySelector("[data-value]").textContent = fmt(score.pagination.total, 0);
      const note = scoreCard.querySelector("[data-note]");
      note.textContent = `${note.textContent} · ${stamp(score.data_extent.first_timestamp)} – ${stamp(score.data_extent.last_timestamp)}`;
    }
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "Historical evidence could not be loaded. Check that the analytical service is available."));
  }
}

function card(title, value, note, attrs) {
  return h("article", { class: "card", ...(attrs || {}) },
    h("h2", {}, title),
    h("p", { class: "card-value", "data-value": "1" }, value || "…"),
    h("p", { class: "card-note", "data-note": "1" }, note || ""));
}

function item(href, title, text) {
  return h("li", {}, h("a", { href }, h("strong", {}, title), h("span", {}, text)));
}
