import { getFrozen } from "../api.js";
import { METHOD, PAGE, PERIOD_LABEL } from "../copy.js";
import { h } from "../dom.js";
import { enumText, hero, loading, section, table, to } from "../ui.js";
import { plain } from "../pure/present.js";
import { loadStory, storySections, versions } from "./common.js";

export async function render(root, ctx) {
  root.replaceChildren(hero(PAGE.methodology), loading());
  const [story, method, meta] = await Promise.all([loadStory(), getFrozen("/api/v1/metadata/methodology"), getFrozen("/api/v1/metadata")]);
  const m = method.data;
  const s = m.phase7_score;
  root.replaceChildren(
    hero(PAGE.methodology),
    section("How the phases connect", "graph",
      h("figure", { class: "chart-figure" },
        h("figcaption", { class: "chart-title" }, "Analysis flow, Phase 3 to Phase 10"),
        h("ol", { class: "flow" }, METHOD.flow.map(([phase, text]) => h("li", {}, h("strong", {}, phase), h("span", {}, text)))),
        h("p", { class: "chart-foot" }, `Versions: ${Object.entries(meta.data.artifact_versions).map(([k, v]) => `${k} ${v}`).join(" · ")}`)),
      h("div", { class: "boundary" },
        h("h3", {}, "Analytical boundary"),
        h("ul", {}, METHOD.boundary.map((line) => h("li", {}, line))))),
    section("Risk score", "score",
      h("p", {}, `${s.name}: ${s.formula}.`),
      h("p", {}, `Reference window ${s.reference_window.join(" to ")} (${s.n_reference_buckets.toLocaleString("en-GB")} buckets). Score version ${s.score_version}.`),
      h("p", {}, `Bands: ${s.band_semantics}. They are shown here as text only and are never painted on a chart as limits.`),
      table("Reference-relative bands, as served", ["Band", "Lower edge", "Reference quantile", "Used", "Served rationale"],
        s.reference_relative_bands.map((b) => [enumText("band", b.band), String(b.lower_edge), String(b.reference_quantile), b.supported ? "Yes" : `No (merged into ${plain("band", b.merged_into).text})`, b.rationale])),
      h("p", { class: "hint" }, m.disclaimers.risk_score)),
    section(PERIOD_LABEL, "periods",
      h("p", {}, `Definition: ${m.phase6_periods.definition}.`),
      h("p", { class: "hint" }, m.disclaimers.abnormal_periods)),
    section("Historical validation", "validation",
      h("p", {}, `Protocol: ${m.phase8_validation.definition}.`),
      h("p", { class: "hint" }, m.disclaimers.validation),
      h("a", { href: to("/validation", {}, "primary") }, "See the served result")),
    section("O₂-excluded variant", "o2",
      h("p", {}, `${m.o2_excluded_variant.definition}.`),
      h("p", { class: "hint" }, m.disclaimers.o2_excluded)),
    section("Plant annotations", "annotations",
      h("p", {}, m.disclaimers.events),
      h("p", {}, "Annotations are saved through the analysis service with the actor's name as attribution, and every change is kept in an audit trail. A KPI-derived period that overlaps an annotation is listed as context, never as a detection.")),
    section("Data and timestamps", "data",
      h("p", {}, `Source window ${meta.data.periods.source_period}; operational scoring ${meta.data.periods.operational_scoring_period}; reference ${meta.data.periods.reference_period}.`),
      h("p", {}, meta.data.periods.timestamp_semantics),
      h("p", { class: "hint" }, `Dashboard: reads served results only · ${versions(story)}`)),
    ...storySections("methodology", story),
  );
}
