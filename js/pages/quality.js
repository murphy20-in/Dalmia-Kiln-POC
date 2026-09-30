import { api } from "../api.js";
import { h } from "../dom.js";
import { failure, links, loading, pageHeader } from "../ui.js";

const OPEN_FIRST = new Set([
  "MISSING_MONTH_KILN_I_SEPTEMBER",
  "KILN_IIIA_APRIL_DUPLICATION",
  "FROZEN_WINDOW",
  "SENTINEL_VALUES",
  "UNIT_REVIEW_HOLDS",
  "EVENT_GROUND_TRUTH",
  "O2_ANALYSER_KILN_I_X",
]);

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading data-quality metadata…"));
  try {
    const [limits, meta, requirements, provenance] = await Promise.all([
      api("/api/v1/metadata/limitations", { signal: ctx.signal }),
      api("/api/v1/metadata", { signal: ctx.signal }),
      api("/api/v1/metadata/data-requirements", { signal: ctx.signal }),
      api("/api/v1/metadata/provenance", { signal: ctx.signal }),
    ]);
    const items = limits.data.limitations || [];
    const lead = items.filter((item) => OPEN_FIRST.has(item.topic));
    const rest = items.filter((item) => !OPEN_FIRST.has(item.topic));
    const quality = limits.data.operational_row_quality;
    root.replaceChildren(
      pageHeader("Data quality", "Coverage and known limitations of the frozen historical dataset. Missing data is not treated as a zero score or as normal operation."),
      coverage(meta.data.periods),
      h("section", {},
        h("h2", {}, "Operational score rows"),
        h("p", {}, `${quality.n_rows.toLocaleString("en-GB")} operational rows. Data-quality status and confidence are properties of those rows, not an alarm state.`),
        h("ul", {}, [
          `Data-quality status: ${pairs(quality.data_quality_status)}`,
          `Confidence band: ${pairs(quality.confidence_band)}`,
          `Rows with ambient-suspect kiln-inlet O₂: ${quality.o2_ambient_suspect_rows.toLocaleString("en-GB")}`,
        ].map((line) => h("li", {}, line)))),
      h("section", {},
        h("h2", {}, "Known quality issues"),
        h("div", { class: "issues" }, lead.map(issue)),
        h("details", {},
          h("summary", {}, `Other recorded limitations (${rest.length})`),
          h("div", { class: "issues" }, rest.map(issue)))),
      h("section", {},
        h("h2", {}, "Unresolved plant questions"),
        h("ul", {}, (requirements.data.plant_questions_open || []).map((q) => h("li", {}, q)))),
      h("section", {},
        h("h2", {}, "Plant data still required"),
        h("p", {}, "These are requirements for a future validation. They are not inputs to the current score."),
        h("ol", {}, (requirements.data.plant_data_requirements || []).map((row) =>
          h("li", {}, `${row.data} (${row.unblocks})`)))),
      h("section", {},
        h("h2", {}, "Artifact status"),
        h("ul", { class: "artifacts" }, (provenance.data.artifacts || []).map((artifact) =>
          h("li", {}, `${artifact.key} · ${artifact.version || "—"} · ${artifact.analytical_status || "—"} · ${(artifact.sha256 || "").slice(0, 12)}`)))),
      h("p", { class: "meta-line" }, limits.data.timestamp_semantics),
      links(),
    );
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "Data-quality metadata could not be loaded."));
  }
}

function pairs(obj) {
  return Object.entries(obj || {}).map(([k, v]) => `${k} ${v}`).join(", ");
}

function issue(item) {
  return h("article", { class: "issue" },
    h("h3", {}, item.topic),
    h("p", {}, item.detail),
    h("p", { class: "hint" }, `${item.id} · ${item.status}`));
}

function coverage(periods) {
  const months = [
    ["2025-04", "Apr", "reference"],
    ["2025-05", "May", "reference"],
    ["2025-06", "Jun", "available"],
    ["2025-07", "Jul", "available"],
    ["2025-08", "Aug", "partial"],
    ["2025-09", "Sep", "missing"],
  ];
  return h("section", {},
    h("h2", {}, "Data coverage"),
    h("p", { class: "meta-line" }, `Source window ${periods.source_period}. Operational scoring ${periods.operational_scoring_period}. Reference ${periods.reference_period}.`),
    h("ul", { class: "coverage", "aria-label": "Month coverage" }, months.map(([key, label, kind]) => {
      const missing = (periods.missing_months || []).filter((m) => m.month === key);
      const text = missing.length ? missing.map((m) => m.reason).join(" ") : kind;
      return h("li", { class: `cov cov-${kind}` }, h("span", { class: "cov-label" }, label), h("span", {}, text));
    })),
    h("ul", { class: "legend" },
      h("li", {}, h("span", { class: "swatch swatch-primary" }), "Operational scores available"),
      h("li", {}, h("span", { class: "swatch swatch-gap" }), "Reference window, not the operational score series"),
      h("li", {}, h("span", { class: "swatch swatch-missing" }), "Missing"),
      h("li", {}, h("span", { class: "swatch swatch-event" }), "Partial (score ends 23 Aug)")),
    h("ul", {}, (periods.missing_months || []).map((m) => h("li", {}, `${m.dataset} ${m.month}: ${m.reason}`))));
}
