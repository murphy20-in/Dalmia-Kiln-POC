import { api } from "../api.js";
import { trendFigure } from "../chart.js";
import { CARD, MSG, PAGE, PERIOD_LABEL } from "../copy.js";
import { h } from "../dom.js";
import { countBy, plain, shortDate } from "../pure/present.js";
import { addMinutes } from "../pure/series.js";
import { failure, fmtInt, hero, kpis, loading, section, to } from "../ui.js";
import { activeEvents, artifactVersion, loadExtent, loadSeries, loadStory, storySections, versions } from "./common.js";

export async function render(root, ctx) {
  root.replaceChildren(hero(PAGE.overview), loading());
  const [status, extent, story] = await Promise.all([
    api("/api/v1/metadata/status", { signal: ctx.signal }),
    loadExtent(),
    loadStory(),
  ]);
  const ev = status.data.evidence_status.from_phase8_artifacts;
  const gt = status.data.ground_truth;
  const sev = countBy(story.periods, "kpi_severity_class");
  const primary = plain("status", ev.phase8_primary_endpoint);
  const o2 = plain("status", ev.phase8_o2_excluded_variant);
  const missing = story.limits.missing_months || [];
  const questions = story.requirements.plant_questions_open || [];
  const stage = h("div", { class: "chart-stage" }, loading(MSG.loadingChart));

  root.replaceChildren(
    hero(PAGE.overview),
    kpis([
      { label: CARD.scored.label, value: fmtInt(extent.total), meaning: `${CARD.scored.unit} · ${shortDate(extent.first_timestamp)} – ${shortDate(extent.last_timestamp, true)}`, source: "Phase 7 · /risk-scores", link: to("/history") },
      { label: CARD.periods.label, value: String(story.periods.length), meaning: `${sev.get("HIGH") || 0} high · ${sev.get("MODERATE") || 0} moderate · ${sev.get("LOW") || 0} low severity. ${CARD.periods.meaning}.`, source: "Phase 6 · /abnormal-periods", link: to("/abnormal-periods") },
      { label: CARD.validation.label, value: primary.text, raw: primary.raw, meaning: primary.meaning, source: "Phase 8 · /metadata/status", link: to("/validation", {}, "primary") },
      { label: CARD.o2.label, value: o2.text, raw: o2.raw, meaning: CARD.o2.meaning, source: "Phase 8 · /metadata/status", link: to("/validation", {}, "o2") },
      { label: CARD.annotations.label, value: String(gt.plant_annotations_recorded), meaning: CARD.annotations.meaning(gt.minimum_recommended_for_revalidation), source: "Phase 9 · /metadata/status", link: to("/events/new") },
      { label: CARD.gaps.label, value: `${missing.length} · ${questions.length}`, meaning: CARD.gaps.meaning(missing.length, questions.length), source: "Phase 9 · /metadata/limitations", link: to("/data-quality") },
    ]),
    section("Score and abnormal periods, Jun–Aug 2025", "graph", stage),
    ...storySections("overview", story),
  );

  try {
    const [series, events] = await Promise.all([loadSeries(), activeEvents(ctx.signal)]);
    if (ctx.signal.aborted) return;
    stage.replaceChildren(trendFigure({
      compact: true,
      title: `Primary risk score with the ${story.periods.length} ${PERIOD_LABEL}`,
      description: `Each outlined, diagonal-hatched band is one KPI-derived abnormal period; select a band to open it. Light grey hatching with no outline is a gap with no operational data. The line is the served primary score, 0–100, relative to Apr–May.`,
      start: extent.first_timestamp,
      end: addMinutes(extent.last_timestamp, 10),
      series: [{ name: "Primary risk score", key: "primary_empirical_risk_score", rows: series.rows }],
      gaps: series.gaps,
      periods: story.periods,
      events: events.data || [],
      periodHref: (id) => to(`/abnormal-periods/${id}`),
      eventHref: (id) => to(`/events/${id}`),
      footnote: `Score ${artifactVersion(series.envelope)} · periods ${story.periods[0]?.method_version || "—"} · ${versions(story)}`,
    }));
  } catch (err) {
    if (err?.name === "AbortError") return;
    stage.replaceChildren(failure(err));
  }
}
