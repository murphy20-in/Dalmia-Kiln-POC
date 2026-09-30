import { barFigure, timelineFigure } from "../chart.js";
import { MSG, PAGE, PERIOD_LABEL, PERIOD_ONE } from "../copy.js";
import { h } from "../dom.js";
import { countBy, plain, shortStamp } from "../pure/present.js";
import { addMinutes } from "../pure/series.js";
import { enumText, facts, fmtInt, hero, kpis, loading, section, to, writeLink } from "../ui.js";
import { annotateQuery, loadExtent, loadStory, storySections, versions } from "./common.js";

export async function render(root, ctx) {
  root.replaceChildren(hero(PAGE.periods), loading());
  const [story, extent] = await Promise.all([loadStory(), loadExtent()]);
  const periods = story.periods;
  const id = ctx.route.id;
  const period = id ? periods.find((p) => p.period_id === id) : null;
  const sev = countBy(periods, "kpi_severity_class");
  const conf = countBy(periods, "confidence");
  const load = countBy(periods, "load_association");
  const censored = countBy(periods, "onset_censored");
  const family = countBy(periods, "dominant_family");
  const version = periods[0]?.method_version || "—";

  root.replaceChildren(
    hero(PAGE.periods, h("p", { class: "hero-label" }, `Label: ${PERIOD_LABEL}. ${story.periodsEnvelope.disclaimer || ""}`)),
    id ? detail(period, id, periods, story) : null,
    kpis([
      { label: "Periods", value: String(periods.length), meaning: PERIOD_LABEL, source: "Phase 6 · /abnormal-periods", link: to("/abnormal-periods", {}, "timeline") },
      { label: "KPI severity", value: `${sev.get("HIGH") || 0} · ${sev.get("MODERATE") || 0} · ${sev.get("LOW") || 0}`, meaning: "high · moderate · low severity (a KPI class, not plant severity)", source: "Phase 6 · kpi_severity_class", link: to("/abnormal-periods", {}, "timeline") },
      { label: "Confidence", value: `${conf.get("MEDIUM") || 0} · ${conf.get("LOW") || 0}`, meaning: "medium · low. None can be higher without plant records", source: "Phase 6 · confidence", link: to("/methodology", {}, "periods") },
      { label: "Load-associated", value: `${load.get("LOAD_ASSOCIATED") || 0} of ${periods.length}`, meaning: "periods the served load-association field marks as load-associated", source: "Phase 6 · load_association", link: to("/data-quality", {}, "L08") },
      { label: "Capped start times", value: `${censored.get(true) || 0} of ${periods.length}`, meaning: MSG.cappedMeaning, source: "Phase 6 · onset_censored", link: to("/validation", {}, "censoring") },
    ]),
    section("Timeline and families", "graph",
      timelineFigure({
        id: "timeline",
        title: `The ${periods.length} ${PERIOD_LABEL}, Jun–Aug 2025`,
        description: "One row per period, placed on the calendar. Hatch density and outline weight show KPI severity, and the row label names it. Select a row to open that period.",
        start: extent.first_timestamp,
        end: addMinutes(extent.last_timestamp, 10),
        periods,
        highlight: id,
        periodHref: (pid) => to(`/abnormal-periods/${pid}`),
        footnote: `Periods ${version} · ${versions(story)}`,
      }),
      barFigure({
        title: "Periods by dominant process family",
        description: "Number of served period rows per dominant_family. A count of rows, not a rate.",
        labelHeader: "Dominant family",
        entries: [...family].map(([k, n]) => [plain("family", k).text, n]),
        footnote: `Periods ${version} · ${versions(story)}`,
      })),
    ...storySections("periods", story, { period }),
  );
}

function detail(p, id, periods, story) {
  if (!p) {
    return h("section", { class: "detail", id: "detail", tabindex: "-1", "data-focus": "", "aria-labelledby": "detail-h" },
      h("h2", { id: "detail-h" }, `No period ${id}`),
      h("p", {}, "That period id is not in the served list. Choose one from the timeline below."));
  }
  const i = periods.indexOf(p);
  const prev = periods[i - 1];
  const next = periods[i + 1];
  const trend = { from: addMinutes(p.start_time, -1440), to: addMinutes(p.end_time, 1440), period: p.period_id };
  return h("section", { class: "detail", id: "detail", tabindex: "-1", "data-focus": "", "aria-labelledby": "detail-h" },
    h("p", { class: "detail-kicker" }, PERIOD_ONE),
    h("h2", { id: "detail-h" }, `${p.period_id} · ${shortStamp(p.start_time, true)} – ${shortStamp(p.end_time, true)}`),
    facts([
      ["KPI severity class", enumText("severity", p.kpi_severity_class)],
      ["Confidence", enumText("confidence", p.confidence)],
      ["Duration", `${fmtInt(p.duration_minutes)} minutes`],
      ["Onset", `${shortStamp(p.onset_time, true)}${p.onset_censored ? MSG.cappedOnset : ""}`],
      ["Dominant family", enumText("family", p.dominant_family)],
      ["Deviating families", (p.deviating_families || []).map((f) => plain("family", f).text).join(", ") || "—"],
      ["Load association", enumText("load", p.load_association)],
      ["Operating context", enumText("context", p.primary_context)],
      ["Plant event?", p.is_plant_event ? "Yes" : "No — this is a KPI-derived label"],
      ["Ground truth", enumText("status", p.event_ground_truth_status)],
      ["Label", enumText("label", p.label_type)],
    ]),
    h("div", { class: "action-bar" },
      writeLink("Annotate this period", "/events/new", annotateQuery(p)),
      h("a", { class: "btn btn-secondary", href: to("/history", trend) }, "View on trend"),
      prev ? h("a", { class: "btn btn-ghost", href: to(`/abnormal-periods/${prev.period_id}`) }, `← ${prev.period_id}`) : null,
      next ? h("a", { class: "btn btn-ghost", href: to(`/abnormal-periods/${next.period_id}`) }, `${next.period_id} →`) : null,
      h("a", { class: "btn btn-ghost", href: to("/abnormal-periods", {}, "timeline") }, "Close")),
    h("p", { class: "hint" }, `Source: Phase 6 · ${p.method_version} · ${story.findingsEnvelope.service_version}`));
}
