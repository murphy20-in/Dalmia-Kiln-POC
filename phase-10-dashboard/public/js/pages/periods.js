import { api } from "../api.js";
import { timeSeriesFigure } from "../chart.js";
import { h } from "../dom.js";
import { addMinutes } from "../pure/series.js";
import { failure, fmt, links, loading, pageHeader, stamp, table } from "../ui.js";

const LABEL = "KPI-derived abnormal periods (not plant events)";

export async function render(root, ctx) {
  root.replaceChildren(loading("Loading KPI-derived abnormal periods…"));
  try {
    const body = await api("/api/v1/abnormal-periods?limit=100", { signal: ctx.signal });
    const periods = body.data || [];
    if (!periods.length) {
      root.replaceChildren(pageHeader("KPI-derived abnormal periods", LABEL),
        h("p", { class: "state" }, "No KPI-derived abnormal periods were returned."));
      return;
    }
    const detail = h("div", { id: "period-detail" });
    root.replaceChildren(
      pageHeader("KPI-derived abnormal periods", LABEL),
      h("p", { class: "callout" }, h("strong", {}, LABEL), " These periods were derived from the POC KPI. They are not confirmed plant events."),
      h("p", { class: "meta-line" }, body.disclaimer || ""),
      timeline(periods, (period) => showDetail(detail, period, ctx)),
      table("All KPI-derived abnormal periods",
        ["Period", "Start", "End", "Duration (min)", "KPI severity class", "Type", "Confidence", "Load association"],
        periods.map((p) => [
          button(p, () => showDetail(detail, p, ctx)),
          stamp(p.start_time), stamp(p.end_time), String(p.duration_minutes),
          p.kpi_severity_class, p.kpi_period_type, p.confidence, p.load_association,
        ])),
      detail,
      links(),
    );
  } catch (err) {
    if (err?.name === "AbortError") return;
    root.replaceChildren(failure(err, "KPI-derived abnormal periods could not be loaded."));
  }
}

function button(period, onClick) {
  return h("button", { type: "button", class: "linkish", onclick: onClick }, period.period_id);
}

function timeline(periods, onPick) {
  const start = periods.map((p) => p.start_time).sort()[0];
  const end = periods.map((p) => p.end_time).sort().at(-1);
  const t0 = Date.parse(`${start}Z`);
  const t1 = Date.parse(`${end}Z`);
  const span = Math.max(t1 - t0, 1);
  return h("ol", { class: "timeline", "aria-label": "KPI-derived abnormal period timeline" },
    periods.map((p) => {
      const left = ((Date.parse(`${p.start_time}Z`) - t0) / span) * 100;
      const width = Math.max(1.2, ((Date.parse(`${p.end_time}Z`) - Date.parse(`${p.start_time}Z`)) / span) * 100);
      return h("li", {},
        h("button", { type: "button", onclick: () => onPick(p) },
          h("span", { class: "tl-label" }, p.period_id),
          h("span", { class: "tl-track" }, h("span", { class: "tl-bar", style: `margin-left:${left}%;width:${width}%` }))));
    }));
}

async function showDetail(host, period, ctx) {
  host.replaceChildren(loading(`Loading ${period.period_id}…`));
  try {
    const end = addMinutes(period.end_time, 10);
    const scores = await api(`/api/v1/risk-scores?start=${period.start_time}&end=${end}&variant=primary&limit=5000`, { signal: ctx.signal });
    const chart = timeSeriesFigure({
      title: `Score trajectory during ${period.period_id}`,
      titleId: "period-chart-title",
      descId: "period-chart-desc",
      description: `Empirical risk score between ${stamp(period.start_time)} and ${stamp(period.end_time)}. This is the historical score, not a detection.`,
      start: period.start_time,
      end,
      gaps: scores.data_extent?.gaps_in_page || [],
      series: [{ name: "Primary", key: "empirical_risk_score", rows: scores.data }],
    });
    host.replaceChildren(
      h("article", { class: "detail" },
        h("h2", {}, period.period_id),
        h("p", {}, "This period was derived from the POC KPI and is not a confirmed plant event."),
        h("dl", { class: "facts" },
          fact("Analytical classification", `${period.label_type}; ${period.phase6_classification}`),
          fact("KPI severity class", period.kpi_severity_class),
          fact("Confidence", period.confidence),
          fact("Process families", (period.deviating_families || []).join(", ") || "—"),
          fact("Dominant family", period.dominant_family),
          fact("Context", `${period.primary_context || "—"} · ${period.load_association || "—"}`),
          fact("Onset", `${stamp(period.onset_time)}${period.onset_censored ? " (censored by the look-back cap)" : ""}`),
          fact("Duration", `${fmt(period.duration_minutes, 0)} min`),
          fact("Plant event", period.is_plant_event ? "yes" : "no"),
          fact("Ground truth", period.event_ground_truth_status)),
        chart.figure,
        chart.table),
    );
  } catch (err) {
    if (err?.name === "AbortError") return;
    host.replaceChildren(failure(err, "The period detail could not be loaded."));
  }
}

function fact(term, value) {
  return [h("dt", {}, term), h("dd", {}, value ?? "—")];
}
