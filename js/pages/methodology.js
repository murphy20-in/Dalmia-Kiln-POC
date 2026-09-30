import { api } from "../api.js";
import { h } from "../dom.js";
import { failure, links, loading, pageHeader } from "../ui.js";

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading methodology…"));
  try {
    const [method, meta] = await Promise.all([
      api("/api/v1/metadata/methodology", { signal: ctx.signal }),
      api("/api/v1/metadata", { signal: ctx.signal }),
    ]);
    const data = method.data;
    root.replaceChildren(
      pageHeader("Methodology", "How the frozen POC pieces relate. This page explains the analysis. It does not recompute it."),
      h("ol", { class: "flow" },
        step("Phase 3", "POC efficiency KPI."),
        step("Phase 6", data.phase6_periods.definition),
        step("Phase 7", `${data.phase7_score.name}. ${data.phase7_score.formula}`),
        step("Phase 8", data.phase8_validation.definition),
        step("Phase 9", "Read-only API over those artifacts, plus a plant annotation store."),
        step("Phase 10", "This dashboard. It draws the API responses and does not calculate a score.")),
      h("section", { class: "boundary" },
        h("h2", {}, "Analytical boundary"),
        h("p", { class: "boundary-line" }, "Empirical POC"),
        h("p", { class: "boundary-line" }, "is not a validated plant-event detector"),
        h("p", { class: "boundary-line" }, "is not a prediction system"),
        h("p", { class: "boundary-line" }, "is not an alarm system")),
      h("section", {},
        h("h2", {}, "Score"),
        h("p", {}, data.phase7_score.band_semantics),
        h("p", { class: "meta-line" }, `Score version ${data.phase7_score.score_version}. Reference version ${data.phase7_score.reference_version}. Reference buckets ${data.phase7_score.n_reference_buckets}.`),
        h("p", {}, "Reference-relative bands exist in the service response. This dashboard does not paint them as limits.")),
      h("section", {},
        h("h2", {}, "O₂-excluded variant"),
        h("p", {}, data.o2_excluded_variant.definition),
        h("p", {}, `Status ${data.o2_excluded_variant.status}. preferred = ${data.o2_excluded_variant.preferred}.`)),
      h("section", {},
        h("h2", {}, "Service state"),
        h("ul", {}, Object.entries(meta.data.analytical_state).map(([key, value]) => h("li", {}, `${key}: ${value}`)))),
      h("p", { class: "meta-line" }, method.disclaimer || ""),
      links(),
    );
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "Methodology could not be loaded."));
  }
}

function step(title, text) {
  return h("li", {}, h("strong", {}, title), " ", text);
}
