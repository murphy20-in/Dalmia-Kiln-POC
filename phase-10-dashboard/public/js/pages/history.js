import { trendFigure } from "../chart.js";
import { MSG, PAGE, PERIOD_LABEL } from "../copy.js";
import { h } from "../dom.js";
import { shortStamp } from "../pure/present.js";
import { toApiTimestamp, toLocalInput } from "../pure/query.js";
import { addMinutes } from "../pure/series.js";
import { fmtInt, hero, kpis, loading, section, to } from "../ui.js";
import { activeEvents, artifactVersion, loadExtent, loadSeries, loadStory, storySections, versions } from "./common.js";

const MONTHS = [["Jun 2025", "2025-06-01T00:00:00", "2025-07-01T00:00:00"], ["Jul 2025", "2025-07-01T00:00:00", "2025-08-01T00:00:00"], ["Aug 2025", "2025-08-01T00:00:00", "2025-09-01T00:00:00"]];

export async function render(root, ctx) {
  const q = ctx.route.query;
  root.replaceChildren(hero(PAGE.history), loading(MSG.loadingChart));
  const [extent, story, series, events] = await Promise.all([loadExtent(), loadStory(), loadSeries(), activeEvents(ctx.signal)]);
  const fullEnd = addMinutes(extent.last_timestamp, 10);
  let from = toApiTimestamp(q.from) || extent.first_timestamp;
  let until = toApiTimestamp(q.to) || fullEnd;
  const badRange = from >= until;
  if (badRange) { from = extent.first_timestamp; until = fullEnd; }
  const overlay = q.overlay === "o2_excluded";
  const period = story.periods.find((p) => p.period_id === q.period) || null;
  const nav = (next) => ctx.go(to("/history", { from: next.from ?? from, to: next.to ?? until, period: "period" in next ? next.period : q.period, overlay: ("overlay" in next ? next.overlay : overlay) ? "o2_excluded" : "" }));

  // Display clip of served rows to the chosen range. No value is changed or derived.
  const rows = series.rows.filter((r) => r.timestamp >= from && r.timestamp < until);
  const gaps = series.gaps.filter(([a, b]) => b > from && a < until);
  const periods = story.periods.filter((p) => p.end_time > from && p.start_time < until);
  const evs = (events.data || []).filter((e) => e.start_time >= from && e.start_time < until);

  const form = h("form", { class: "controls", "aria-label": "Score history range" },
    h("div", { class: "field" }, h("label", { for: "h-from" }, "From (plant-local)"), h("input", { id: "h-from", type: "datetime-local", value: toLocalInput(from), min: toLocalInput(extent.first_timestamp), max: toLocalInput(fullEnd) })),
    h("div", { class: "field" }, h("label", { for: "h-to" }, "To (end excluded)"), h("input", { id: "h-to", type: "datetime-local", value: toLocalInput(until), min: toLocalInput(extent.first_timestamp), max: toLocalInput(fullEnd) })),
    h("button", { type: "submit", class: "btn btn-secondary" }, "Apply range"),
    h("div", { class: "presets", role: "group", "aria-label": "Quick ranges" },
      h("button", { type: "button", class: "btn btn-ghost", onclick: () => nav({ from: extent.first_timestamp, to: fullEnd, period: "" }) }, "Full range"),
      MONTHS.map(([label, a, b]) => h("button", { type: "button", class: "btn btn-ghost", onclick: () => nav({ from: a, to: b < fullEnd ? b : fullEnd }) }, label))),
    h("label", { class: "check" },
      h("input", { type: "checkbox", id: "h-overlay", checked: overlay, onchange: (e) => nav({ overlay: e.target.checked }) }),
      MSG.o2Toggle),
    h("p", { class: "field-error", role: "status", id: "h-error" }, badRange ? "That range was not valid, so the full range is shown." : ""));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const a = toApiTimestamp(form.querySelector("#h-from").value);
    const b = toApiTimestamp(form.querySelector("#h-to").value);
    if (!a || !b || a >= b) {
      form.querySelector("#h-error").textContent = "Enter a plant-local start and end; the end must be later than the start.";
      return;
    }
    nav({ from: a, to: b });
  });

  const chart = trendFigure({
    title: `Primary risk score, ${shortStamp(from, true)} – ${shortStamp(until, true)}${overlay ? ", with the O₂-excluded sensitivity overlay" : ""}`,
    description: `Served primary score for each operational ten-minute bucket. Hatched bands are ${PERIOD_LABEL}; diamonds are plant annotations; hatched grey is a gap with no operational data, never a zero score.`,
    start: from,
    end: until,
    series: [
      { name: "Primary risk score", key: "primary_empirical_risk_score", rows },
      ...(overlay ? [{ name: "O₂-excluded — sensitivity analysis, not preferred", key: "o2_excluded_empirical_risk_score", rows, dash: true }] : []),
    ],
    gaps,
    periods,
    highlight: period?.period_id,
    events: evs,
    periodHref: (id) => to(`/abnormal-periods/${id}`),
    eventHref: (id) => to(`/events/${id}`),
    onBrush: (a, b) => nav({ from: a, to: b }),
    footnote: `Score ${artifactVersion(series.envelope)} · periods ${story.periods[0]?.method_version || "—"} · ${versions(story)}. ${extent.gap_rule}.`,
  });

  root.replaceChildren(
    hero(PAGE.history),
    kpis([
      { label: "Buckets in view", value: fmtInt(rows.length), meaning: `of ${fmtInt(extent.total)} served operational buckets`, source: "Phase 7 · /risk-scores/variant-comparison", link: to("/history") },
      { label: "Gaps in view", value: fmtInt(gaps.length), meaning: "stretches with no operational data, drawn as gaps", source: "Phase 9 · gaps_in_page", link: to("/data-quality") },
      { label: "Abnormal periods in view", value: String(periods.length), meaning: `of ${story.periods.length} ${PERIOD_LABEL}`, source: "Phase 6 · /abnormal-periods", link: to("/abnormal-periods") },
      { label: "Plant annotations in view", value: String(evs.length), meaning: "active plant-supplied records", source: "Phase 9 · /events", link: to("/events") },
    ]),
    section("Score history", "graph",
      form,
      period ? h("p", { class: "callout" }, `Highlighting ${period.period_id} (${shortStamp(period.start_time)} – ${shortStamp(period.end_time)}), shown with 24 hours either side. `, h("a", { href: to(`/abnormal-periods/${period.period_id}`) }, "Back to the period details")) : null,
      overlay ? h("p", { class: "callout", id: "o2-note" }, MSG.o2Note) : null,
      chart),
    ...storySections("history", story, { period }),
  );
}
