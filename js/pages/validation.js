import { api } from "../api.js";
import { h } from "../dom.js";
import { evidenceForDisplay } from "../pure/present.js";
import { failure, links, loading, pageHeader, table } from "../ui.js";

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading historical validation results…"));
  try {
    const [validation, findings] = await Promise.all([
      api("/api/v1/validation/early-warning-historical", { signal: ctx.signal }),
      api("/api/v1/findings?limit=100", { signal: ctx.signal }),
    ]);
    const data = validation.data;
    const primary = data.primary_endpoint.by_variant.primary;
    const o2 = data.primary_endpoint.by_variant.o2_excluded;
    root.replaceChildren(
      pageHeader("Early-warning validation", "Historical result against the available KPI-derived abnormal periods. This is not evidence that future plant events cannot be validated."),
      h("p", { class: "status-word" }, data.historical_validation_status),
      h("p", {}, data.question),
      h("p", { class: "meta-line" }, validation.disclaimer || ""),
      h("section", {},
        h("h2", {}, "Primary endpoint"),
        h("p", {}, data.primary_endpoint.definition),
        endpointTable(primary)),
      h("section", {},
        h("h2", {}, "Sensitivity analysis"),
        h("p", { class: "callout" }, "O₂-excluded is a sensitivity analysis, not an alternative production model. preferred = false."),
        h("p", {}, o2.note || ""),
        endpointTable(o2),
        h("p", { class: "meta-line" }, `Like-for-like p-value on ${o2.like_for_like_event_set}: ${exact(o2.like_for_like_p_value)}. comparable_to_primary = ${o2.comparable_to_primary}.`)),
      h("section", {},
        h("h2", {}, "Censoring"),
        h("p", {}, `${data.censoring.n_onset_censored} of ${data.censoring.n_periods} onsets are censored.`),
        h("p", {}, data.censoring.meaning)),
      h("section", {},
        h("h2", {}, "Negative controls"),
        h("p", {}, "These are checks on the historical protocol. They are not combined into an overall score."),
        table("Negative controls", ["Control", "Method", "Variant", "Status", "p-value"],
          (data.negative_controls || []).map((row) => [
            row.control_id, row.method, row.score_variant, row.status, exact(row.p_value),
          ]))),
      h("section", {},
        h("h2", {}, "Findings"),
        h("p", {}, findings.note || "Each finding keeps its Phase 8 class. Classes are not summed."),
        findingsList(findings.data || [])),
      h("p", { class: "meta-line" }, data.phase8_integrity_checks.meaning),
      links(),
    );
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "Validation results could not be loaded."));
  }
}

function exact(n) {
  return typeof n === "number" && Number.isFinite(n) ? String(n) : "—";
}

function endpointTable(block) {
  return table("Endpoint figures as returned by the analytical service",
    ["Status", "Effect estimate", "95% CI", "p-value", "Periods", "Evaluable", "Controls"],
    [[
      block.historical_validation_status,
      exact(block.effect_estimate_median_rank_excess),
      `${exact(block.ci95_low)} to ${exact(block.ci95_high)}`,
      exact(block.randomisation_p_value),
      String(block.n_periods),
      String(block.n_evaluable_periods),
      String(block.n_controls),
    ]]);
}

function findingsList(rows) {
  return h("div", { class: "findings" }, rows.map((row) => {
    const evidence = evidenceForDisplay(row.evidence);
    return h("article", { class: "finding" },
      h("h3", {}, `${row.finding_id} · ${row.classification}`),
      h("p", {}, row.title),
      evidence ? h("p", { class: "meta-line" }, evidence) : h("p", { class: "meta-line" }, "Evidence text withheld in this view."),
      row.context_only ? h("p", { class: "hint" }, row.context_only_reason || "Context only.") : null);
  }));
}
