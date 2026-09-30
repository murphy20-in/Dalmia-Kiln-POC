import { h } from "./dom.js";
import { addMinutes, decimate, flatten, parseTs, segments, yDomain } from "./pure/series.js";

const VB_W = 860;
const VB_H = 360;
const PAD = { l: 52, r: 16, t: 28, b: 36 };

export function timeSeriesFigure(spec) {
  const start = spec.start;
  const end = spec.end;
  const prepared = spec.series.map((series) => {
    const segs = decimate(segments(series.rows, series.key, spec.gaps), spec.maxPoints || 900);
    return { ...series, segs };
  });
  const domain = yDomain(prepared.flatMap((s) => s.segs));
  const plotW = VB_W - PAD.l - PAD.r;
  const plotH = VB_H - PAD.t - PAD.b;
  const t0 = parseTs(start);
  const t1 = parseTs(end);
  const xOf = (ts) => {
    const t = parseTs(ts);
    if (t0 == null || t1 == null || t1 === t0 || t == null) return PAD.l;
    return PAD.l + ((t - t0) / (t1 - t0)) * plotW;
  };
  const yOf = (y) => {
    const [lo, hi] = domain;
    return PAD.t + (1 - (y - lo) / (hi - lo || 1)) * plotH;
  };
  const points = flatten(prepared[0]?.segs || []);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${VB_W} ${VB_H}`);
  svg.setAttribute("class", "chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-labelledby", spec.titleId);
  svg.setAttribute("aria-describedby", spec.descId);

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.append(pattern());
  svg.append(defs);
  svg.append(rect(0, 0, VB_W, VB_H, "chart-bg"));

  for (const gap of spec.gaps || []) {
    const x1 = xOf(gap[0]);
    const x2 = xOf(gap[1]);
    if (x2 > x1) svg.append(rect(x1, PAD.t, x2 - x1, plotH, "chart-gap"));
  }
  for (const period of spec.periods || []) {
    const x1 = xOf(period.start_time);
    const x2 = xOf(period.end_time);
    if (x2 > x1) svg.append(rect(x1, PAD.t, Math.max(2, x2 - x1), plotH, "chart-period"));
  }

  axis(svg, domain, yOf, plotH);
  for (const series of prepared) {
    for (const seg of series.segs) {
      const pl = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      pl.setAttribute("points", seg.map((p) => `${xOf(p.timestamp).toFixed(1)},${yOf(p.y).toFixed(1)}`).join(" "));
      pl.setAttribute("class", series.dash ? "series series-sensitivity" : "series series-primary");
      if (series.dash) pl.setAttribute("stroke-dasharray", "6 4");
      svg.append(pl);
    }
  }
  for (const event of spec.events || []) {
    const x = xOf(event.start_time);
    svg.append(diamond(x, PAD.t + 8));
  }

  const readout = h("p", { class: "chart-readout", "aria-live": "polite" }, "Move along the series to read a score.");
  const slider = h("input", {
    type: "range",
    min: "0",
    max: String(Math.max(points.length - 1, 0)),
    value: "0",
    "aria-label": "Inspect a point on the historical score series",
    oninput: () => announce(points, slider, readout),
  });
  if (!points.length) slider.disabled = true;

  const tip = h("p", { class: "chart-tip" }, "Hover the chart to read a timestamp and score.");
  svg.addEventListener("pointermove", (event) => {
    const nearest = nearestPoint(event, svg, points, xOf);
    tip.textContent = nearest
      ? `${nearest.timestamp.replace("T", " ")} · score ${formatScore(nearest.y)}`
      : "No plotted point at this position.";
  });

  const figure = h("figure", { class: "chart-figure" },
    h("figcaption", { id: spec.titleId, class: "chart-title" }, spec.title),
    h("p", { id: spec.descId, class: "chart-desc" }, spec.description),
    svg,
    tip,
    points.length ? h("label", { class: "inspect" }, "Keyboard inspect", slider) : null,
    readout,
    legend(spec),
  );
  return { figure, table: fallbackTable(prepared, spec.gaps || []), points };
}

function announce(points, slider, readout) {
  const point = points[Number(slider.value)];
  readout.textContent = point
    ? `${point.timestamp.replace("T", " ")} · empirical risk score ${formatScore(point.y)}`
    : "No plotted point.";
}

function nearestPoint(event, svg, points, xOf) {
  if (!points.length) return null;
  const box = svg.getBoundingClientRect();
  const x = ((event.clientX - box.left) / box.width) * VB_W;
  let best = null;
  let bestDx = Infinity;
  for (const point of points) {
    const dx = Math.abs(xOf(point.timestamp) - x);
    if (dx < bestDx) {
      best = point;
      bestDx = dx;
    }
  }
  return bestDx < 18 ? best : null;
}

function legend(spec) {
  const items = [h("li", {}, h("span", { class: "swatch swatch-primary" }), "Empirical risk score (primary)")];
  if (spec.showSensitivity) items.push(h("li", {}, h("span", { class: "swatch swatch-sensitivity" }), "O₂-excluded sensitivity"));
  if (spec.periods) items.push(h("li", {}, h("span", { class: "swatch swatch-period" }), "KPI-derived abnormal period"));
  if (spec.events) items.push(h("li", {}, h("span", { class: "swatch swatch-event" }), "Plant-supplied event"));
  items.push(h("li", {}, h("span", { class: "swatch swatch-gap" }), "Gap (no data, not a zero score)"));
  return h("ul", { class: "legend" }, items);
}

function fallbackTable(prepared, gaps) {
  const rows = [];
  for (const series of prepared) {
    for (const seg of series.segs) {
      for (const point of seg) rows.push([series.name, point.timestamp, formatScore(point.y)]);
    }
  }
  const shown = rows.length > 40 ? [...rows.slice(0, 20), ...rows.slice(-5)] : rows;
  return h("details", { class: "table-fallback" },
    h("summary", {}, "Data table for this chart"),
    h("p", {}, rows.length > 40
      ? `Showing 25 of ${rows.length} plotted points (first 20 and last 5). Plotted points are API values; a long window is thinned for drawing without filling gaps.`
      : "Every plotted point. Values come from the analytical service."),
    h("p", {}, gaps.length ? `${gaps.length} gap${gaps.length === 1 ? "" : "s"} in this response.` : "No gaps in this response."),
    h("div", { class: "table-wrap" },
      h("table", {},
        h("caption", { class: "sr-only" }, "Plotted historical scores"),
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Series"), h("th", { scope: "col" }, "Timestamp"), h("th", { scope: "col" }, "Score"))),
        h("tbody", {}, shown.map(([name, ts, score]) => h("tr", {},
          h("td", { "data-label": "Series" }, name),
          h("td", { "data-label": "Timestamp" }, ts.replace("T", " ")),
          h("td", { "data-label": "Score" }, score)))))),
  );
}

function axis(svg, domain, yOf, plotH) {
  const [lo, hi] = domain;
  for (const tick of [lo, (lo + hi) / 2, hi]) {
    const y = yOf(tick);
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "46");
    label.setAttribute("y", String(y + 4));
    label.setAttribute("class", "tick");
    label.setAttribute("text-anchor", "end");
    label.textContent = String(Math.round(tick));
    svg.append(label);
  }
  svg.append(line(PAD.l, PAD.t + plotH, VB_W - PAD.r, PAD.t + plotH));
}

function pattern() {
  const p = document.createElementNS("http://www.w3.org/2000/svg", "pattern");
  p.setAttribute("id", "periodHatch");
  p.setAttribute("width", "6");
  p.setAttribute("height", "6");
  p.setAttribute("patternUnits", "userSpaceOnUse");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M0 6 L6 0");
  path.setAttribute("class", "hatch");
  p.append(path);
  return p;
}

function rect(x, y, w, hgt, cls) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  el.setAttribute("x", String(x));
  el.setAttribute("y", String(y));
  el.setAttribute("width", String(Math.max(0, w)));
  el.setAttribute("height", String(Math.max(0, hgt)));
  el.setAttribute("class", cls);
  return el;
}

function line(x1, y1, x2, y2) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "line");
  el.setAttribute("x1", String(x1));
  el.setAttribute("y1", String(y1));
  el.setAttribute("x2", String(x2));
  el.setAttribute("y2", String(y2));
  el.setAttribute("class", "axis");
  return el;
}

function diamond(x, y) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  el.setAttribute("points", `${x},${y - 6} ${x + 5},${y} ${x},${y + 6} ${x - 5},${y}`);
  el.setAttribute("class", "event-mark");
  return el;
}

function formatScore(y) {
  return Number(y).toLocaleString("en-GB", { maximumFractionDigits: 2 });
}

export function defaultWindow(extent) {
  if (!extent?.first_timestamp || !extent?.last_timestamp) return null;
  const start = addMinutes(extent.last_timestamp, -14 * 24 * 60);
  return {
    start: start && start > extent.first_timestamp ? start : extent.first_timestamp,
    end: addMinutes(extent.last_timestamp, 10) || extent.last_timestamp,
  };
}
