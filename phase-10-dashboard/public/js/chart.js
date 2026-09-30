/** Inline SVG charts. Every mark is a served value; gaps are drawn as gaps; nothing is interpolated. */
import { h } from "./dom.js";
import { MSG, TABLE_NOTE } from "./copy.js";
import { plain, shortDate, shortStamp } from "./pure/present.js";
import { decimate, flatten, formatTs, parseTs, segments, yDomain } from "./pure/series.js";

const NS = "http://www.w3.org/2000/svg";
const W = 960;

function el(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) node.setAttribute(k, String(v));
  for (const kid of kids.flat()) if (kid != null) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return node;
}

function svgRoot(height, labelId, descId, cls = "chart") {
  return el("svg", { viewBox: `0 0 ${W} ${height}`, class: cls, role: "group", "aria-labelledby": labelId, "aria-describedby": descId, style: `aspect-ratio:${W}/${height}` });
}

/** Hatch patterns: severity and gaps are told apart by pattern and weight, never by hue. */
function defs(prefix) {
  const hatch = (id, gap, width, cls) => el("pattern", { id: `${prefix}-${id}`, width: gap, height: gap, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
    el("line", { x1: 0, y1: 0, x2: 0, y2: gap, class: cls, "stroke-width": width }));
  return el("defs", {},
    hatch("gap", 6, 1, "hatch-gap"),
    hatch("high", 4, 2.2, "hatch-sev"),
    hatch("moderate", 6, 1.4, "hatch-sev"),
    hatch("low", 9, 0.8, "hatch-sev"));
}

let uid = 0;

function figure(id, title, description, svg, extras, footnote) {
  return h("figure", { class: "chart-figure", id },
    h("figcaption", { id: `${id}-title`, class: "chart-title" }, title),
    h("p", { id: `${id}-desc`, class: "chart-desc" }, description),
    h("div", { class: "chart-frame" }, svg),
    ...extras,
    footnote ? h("p", { class: "chart-foot" }, footnote) : null);
}

function tableToggle(caption, headers, rows, note) {
  return h("details", { class: "table-toggle" },
    h("summary", {}, MSG.tableToggle),
    note ? h("p", { class: "hint" }, note) : null,
    h("div", { class: "table-wrap" },
      h("table", { class: "resp" },
        h("caption", {}, caption),
        h("thead", {}, h("tr", {}, headers.map((x) => h("th", { scope: "col" }, x)))),
        h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c, i) => h("td", { "data-label": headers[i] }, c))))))));
}

/** Month (or day) ticks between t0 and t1 (ms, UTC-as-naive). */
function timeTicks(t0, t1) {
  const day = 86400000;
  const out = [];
  const span = (t1 - t0) / day;
  if (span > 40) {
    const d = new Date(t0);
    let y = d.getUTCFullYear();
    let m = d.getUTCMonth();
    for (;;) {
      const t = Date.UTC(y, m, 1);
      if (t > t1) break;
      if (t >= t0) out.push([t, shortDate(formatTs(t))]);
      m += 1;
      if (m > 11) { m = 0; y += 1; }
    }
    return out;
  }
  const step = [1, 2, 7, 14].find((s) => span / s <= 8) || 14;
  let t = Math.ceil(t0 / day) * day;
  for (; t <= t1; t += step * day) out.push([t, shortDate(formatTs(t))]);
  return out;
}

/**
 * Score trend with period bands, event diamonds, hatched gaps and optional drag-to-zoom.
 * spec: { title, description, start, end, series: [{name, key, rows, dash}], gaps, periods, highlight,
 *         events, compact, periodHref(id), eventHref(id), onBrush(from, to), footnote, inspect }
 */
export function trendFigure(spec) {
  const id = `chart-${++uid}`;
  const compact = Boolean(spec.compact);
  const H = compact ? 190 : 380;
  const PAD = { l: 44, r: 12, t: compact ? 26 : 34, b: 28 };
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const t0 = parseTs(spec.start);
  const t1 = parseTs(spec.end);
  const span = Math.max(1, t1 - t0);
  const xOfT = (t) => PAD.l + ((t - t0) / span) * plotW;
  const xOf = (ts) => xOfT(parseTs(ts) ?? t0);
  const clampX = (x) => Math.min(PAD.l + plotW, Math.max(PAD.l, x));
  const prepared = (spec.series || []).map((s) => ({ ...s, segs: decimate(segments(s.rows, s.key, spec.gaps), spec.maxPoints || 900) }));
  const domain = yDomain(prepared.flatMap((s) => s.segs));
  const yOf = (y) => PAD.t + (1 - (y - domain[0]) / (domain[1] - domain[0] || 1)) * plotH;

  const svg = svgRoot(H, `${id}-title`, `${id}-desc`);
  svg.append(defs(id), el("rect", { x: 0, y: 0, width: W, height: H, class: "chart-bg" }));

  for (const [y, label] of [[domain[0], String(Math.round(domain[0]))], [(domain[0] + domain[1]) / 2, String(Math.round((domain[0] + domain[1]) / 2))], [domain[1], String(Math.round(domain[1]))]]) {
    if (!prepared.length) break;
    svg.append(el("line", { x1: PAD.l, x2: PAD.l + plotW, y1: yOf(y), y2: yOf(y), class: "grid" }),
      el("text", { x: PAD.l - 6, y: yOf(y) + 4, class: "tick", "text-anchor": "end" }, label));
  }
  for (const [t, label] of timeTicks(t0, t1)) {
    if (xOfT(t) > W - PAD.r - 40) continue;
    svg.append(el("line", { x1: xOfT(t), x2: xOfT(t), y1: PAD.t + plotH, y2: PAD.t + plotH + 5, class: "axis" }),
      el("text", { x: xOfT(t) + 3, y: H - 8, class: "tick" }, label));
  }

  for (const [a, b] of spec.gaps || []) {
    const x1 = clampX(xOf(a));
    const x2 = clampX(xOf(b));
    if (x2 - x1 > 0.5) svg.append(el("rect", { x: x1, y: PAD.t, width: x2 - x1, height: plotH, class: "chart-gap", fill: `url(#${id}-gap)` }));
  }

  for (const p of spec.periods || []) {
    const x1 = clampX(xOf(p.start_time));
    const x2 = clampX(xOf(p.end_time));
    if (x2 <= PAD.l || x1 >= PAD.l + plotW) continue;
    const sev = String(p.kpi_severity_class || "LOW").toLowerCase();
    const focus = spec.highlight === p.period_id;
    const label = `${p.period_id}: ${plain("severity", p.kpi_severity_class).text} KPI-derived abnormal period, ${shortStamp(p.start_time)} to ${shortStamp(p.end_time)}. Open details.`;
    const band = el("rect", { x: x1, y: PAD.t, width: Math.max(4, x2 - x1), height: plotH, class: `band sev-${sev}${focus ? " band-focus" : ""}`, fill: `url(#${id}-${sev})` });
    const link = el("a", { href: spec.periodHref(p.period_id), class: "band-link", "aria-label": label }, el("title", {}, label), band);
    if (focus || (!compact && span < 20 * 86400000)) link.append(el("text", { x: x1 + 2, y: PAD.t - 6, class: `band-label${focus ? " band-label-focus" : ""}` }, p.period_id));
    svg.append(link);
  }

  for (const s of prepared) {
    for (const seg of s.segs) {
      const pts = seg.map((p) => `${xOf(p.timestamp).toFixed(1)},${yOf(p.y).toFixed(1)}`).join(" ");
      svg.append(el("polyline", { points: pts, class: s.dash ? "series series-sensitivity" : "series series-primary", "stroke-dasharray": s.dash ? "7 4" : null }));
    }
  }
  svg.append(el("line", { x1: PAD.l, x2: PAD.l + plotW, y1: PAD.t + plotH, y2: PAD.t + plotH, class: "axis" }));

  for (const ev of spec.events || []) {
    const x = clampX(xOf(ev.start_time));
    const y = PAD.t + plotH - 10;
    const label = `Plant annotation: ${ev.event_type}, ${shortStamp(ev.start_time)}. Open annotation.`;
    svg.append(el("a", { href: spec.eventHref(ev.event_id), class: "event-link", "aria-label": label }, el("title", {}, label),
      el("polygon", { points: `${x},${y - 8} ${x + 7},${y} ${x},${y + 8} ${x - 7},${y}`, class: "event-mark" })));
  }

  const points = flatten(prepared[0]?.segs || []);
  const readout = h("p", { class: "chart-readout", "aria-live": "polite" }, points.length ? MSG.brushHint : "");
  if (points.length) {
    svg.addEventListener("pointermove", (event) => {
      if (drag) return;
      const box = svg.getBoundingClientRect();
      const x = ((event.clientX - box.left) / box.width) * W;
      let best = null;
      let bestDx = Infinity;
      for (const p of points) {
        const dx = Math.abs(xOf(p.timestamp) - x);
        if (dx < bestDx) { best = p; bestDx = dx; }
      }
      readout.textContent = best && bestDx < 12 ? `${shortStamp(best.timestamp, true)} · primary score ${fmtScore(best.y)}` : MSG.brushHint;
    });
  }

  let drag = null;
  let dragged = false;
  if (spec.onBrush) {
    const shade = el("rect", { y: PAD.t, height: plotH, width: 0, class: "brush", visibility: "hidden" });
    svg.append(shade);
    const toX = (event) => {
      const box = svg.getBoundingClientRect();
      return clampX(((event.clientX - box.left) / box.width) * W);
    };
    svg.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      drag = { x: toX(event), id: event.pointerId };
      dragged = false;
    });
    svg.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const x = toX(event);
      if (Math.abs(x - drag.x) > 6 && !dragged) {
        dragged = true;
        svg.setPointerCapture(drag.id);
      }
      if (!dragged) return;
      shade.setAttribute("x", String(Math.min(x, drag.x)));
      shade.setAttribute("width", String(Math.abs(x - drag.x)));
      shade.setAttribute("visibility", "visible");
    });
    svg.addEventListener("pointerup", (event) => {
      if (!drag) return;
      const a = Math.min(drag.x, toX(event));
      const b = Math.max(drag.x, toX(event));
      drag = null;
      shade.setAttribute("visibility", "hidden");
      if (!dragged) return;
      const snap = (x) => formatTs(Math.round((t0 + ((x - PAD.l) / plotW) * span) / 600000) * 600000);
      spec.onBrush(snap(a), snap(b));
    });
    svg.addEventListener("pointercancel", () => { drag = null; shade.setAttribute("visibility", "hidden"); });
    svg.addEventListener("click", (event) => {
      if (!dragged) return;
      dragged = false;
      event.preventDefault();
      event.stopPropagation();
    }, true);
  }

  const legend = h("ul", { class: "legend" },
    prepared.map((s) => h("li", {}, h("span", { class: `swatch ${s.dash ? "swatch-sensitivity" : "swatch-primary"}`, "aria-hidden": "true" }), s.name)),
    spec.periods ? h("li", {}, h("span", { class: "swatch swatch-sev", "aria-hidden": "true" }), "KPI-derived abnormal period (hatch density = severity: dense high, medium moderate, sparse low)") : null,
    spec.events ? h("li", {}, h("span", { class: "swatch swatch-event", "aria-hidden": "true" }), "Plant annotation") : null,
    h("li", {}, h("span", { class: "swatch swatch-gap", "aria-hidden": "true" }), MSG.gapLegend));

  const rows = [];
  for (const s of prepared) for (const seg of s.segs) for (const p of seg) rows.push([s.name, shortStamp(p.timestamp, true), fmtScore(p.y)]);
  const shown = rows.length > 40 ? [...rows.slice(0, 20), ...rows.slice(-5)] : rows;
  const table = tableToggle(spec.title, ["Series", "Bucket end (plant-local)", "Score"], shown,
    `${rows.length > 40 ? TABLE_NOTE.thinned(shown.length, rows.length) : TABLE_NOTE.all} ${(spec.gaps || []).length} gaps in this range.`);

  return figure(id, spec.title, spec.description, svg, [readout, legend, table], spec.footnote);
}

/** Gantt-style timeline of periods. Severity = hatch density + outline weight + text. */
export function timelineFigure(spec) {
  const id = spec.id || `chart-${++uid}`;
  const rowH = 26;
  const PAD = { l: 250, r: 12, t: 10, b: 28 };
  const H = PAD.t + spec.periods.length * rowH + PAD.b;
  const plotW = W - PAD.l - PAD.r;
  const t0 = parseTs(spec.start);
  const t1 = parseTs(spec.end);
  const xOf = (ts) => PAD.l + ((parseTs(ts) - t0) / Math.max(1, t1 - t0)) * plotW;
  const svg = svgRoot(H, `${id}-title`, `${id}-desc`);
  svg.append(defs(id), el("rect", { x: 0, y: 0, width: W, height: H, class: "chart-bg" }));
  for (const [t, label] of timeTicks(t0, t1)) {
    const x = PAD.l + ((t - t0) / Math.max(1, t1 - t0)) * plotW;
    svg.append(el("line", { x1: x, x2: x, y1: PAD.t, y2: H - PAD.b, class: "grid" }), el("text", { x: x + 3, y: H - 8, class: "tick" }, label));
  }
  spec.periods.forEach((p, i) => {
    const y = PAD.t + i * rowH;
    const sev = String(p.kpi_severity_class || "LOW").toLowerCase();
    const sevText = plain("severity", p.kpi_severity_class).text;
    const focus = spec.highlight === p.period_id;
    const x1 = xOf(p.start_time);
    const label = `${p.period_id} · ${sevText}, ${shortStamp(p.start_time)} to ${shortStamp(p.end_time)}. Open details.`;
    svg.append(el("a", { href: spec.periodHref(p.period_id), class: "band-link", "aria-label": label, "aria-current": focus ? "true" : null },
      el("title", {}, label),
      el("rect", { x: 0, y, width: W, height: rowH, class: focus ? "row-focus" : "row-hit" }),
      el("text", { x: 8, y: y + 17, class: `row-label${focus ? " band-label-focus" : ""}` }, `${p.period_id} · ${sevText}`),
      el("rect", { x: x1, y: y + 5, width: Math.max(6, xOf(p.end_time) - x1), height: rowH - 10, class: `band sev-${sev}${focus ? " band-focus" : ""}`, fill: `url(#${id}-${sev})` })));
  });
  const legend = h("ul", { class: "legend" },
    ["HIGH", "MODERATE", "LOW"].map((s) => h("li", {}, h("span", { class: `swatch swatch-${s.toLowerCase()}`, "aria-hidden": "true" }), plain("severity", s).text)));
  const table = tableToggle(spec.title, ["Period", "KPI severity", "Start", "End", "Dominant family"],
    spec.periods.map((p) => [p.period_id, plain("severity", p.kpi_severity_class).text, shortStamp(p.start_time, true), shortStamp(p.end_time, true), plain("family", p.dominant_family).text]));
  return figure(id, spec.title, spec.description, svg, [legend, table], spec.footnote);
}

/** Horizontal bars of served-row counts. */
export function barFigure(spec) {
  const id = `chart-${++uid}`;
  const rowH = 30;
  const PAD = { l: 170, r: 40, t: 8, b: 8 };
  const H = PAD.t + spec.entries.length * rowH + PAD.b;
  const top = Math.max(1, ...spec.entries.map(([, n]) => n));
  const svg = svgRoot(H, `${id}-title`, `${id}-desc`, "chart chart-small");
  svg.append(el("rect", { x: 0, y: 0, width: W, height: H, class: "chart-bg" }));
  spec.entries.forEach(([label, n], i) => {
    const y = PAD.t + i * rowH;
    const w = ((W - PAD.l - PAD.r) * n) / top;
    svg.append(el("text", { x: PAD.l - 10, y: y + 20, class: "row-label", "text-anchor": "end" }, label),
      el("rect", { x: PAD.l, y: y + 6, width: w, height: rowH - 12, class: "bar" }),
      el("text", { x: PAD.l + w + 6, y: y + 20, class: "row-label" }, String(n)));
  });
  const table = tableToggle(spec.title, [spec.labelHeader, "Periods"], spec.entries.map(([l, n]) => [l, String(n)]));
  return figure(id, spec.title, spec.description, svg, [table], spec.footnote);
}

/**
 * Dot-and-interval plot of served estimates with a zero reference.
 * spec.rows: [{ group, series: "primary"|"sensitivity", value, lo, hi, status }]
 */
export function dotFigure(spec) {
  const id = `chart-${++uid}`;
  const groups = [...new Set(spec.rows.map((r) => r.group))];
  const rowH = 40;
  const PAD = { l: 190, r: 130, t: 30, b: 34 };
  const H = PAD.t + groups.length * rowH + PAD.b;
  const plotW = W - PAD.l - PAD.r;
  let lo = 0;
  let hi = 0;
  for (const r of spec.rows) { lo = Math.min(lo, r.lo ?? r.value); hi = Math.max(hi, r.hi ?? r.value); }
  const padX = (hi - lo) * 0.08 || 0.05;
  lo -= padX;
  hi += padX;
  const xOf = (v) => PAD.l + ((v - lo) / (hi - lo)) * plotW;
  const svg = svgRoot(H, `${id}-title`, `${id}-desc`);
  svg.append(el("rect", { x: 0, y: 0, width: W, height: H, class: "chart-bg" }));
  for (const v of [lo + padX, 0, hi - padX]) {
    svg.append(el("text", { x: xOf(v), y: H - 10, class: "tick", "text-anchor": "middle" }, fmtScore(v, 2)));
  }
  svg.append(el("line", { x1: xOf(0), x2: xOf(0), y1: PAD.t - 8, y2: H - PAD.b, class: "zero" }),
    el("text", { x: xOf(0) + 4, y: PAD.t - 12, class: "tick" }, spec.zeroLabel));
  groups.forEach((g, i) => {
    const y = PAD.t + i * rowH + rowH / 2;
    svg.append(el("text", { x: PAD.l - 12, y: y + 4, class: "row-label", "text-anchor": "end" }, g));
    if (i === 0) svg.append(el("text", { x: PAD.l - 12, y: PAD.t - 12, class: "tick", "text-anchor": "end" }, spec.rowTitle || ""));
    spec.rows.filter((r) => r.group === g).forEach((r) => {
      const dy = r.series === "primary" ? -7 : 7;
      const cls = r.series === "primary" ? "dot-primary" : "dot-sensitivity";
      if (r.lo != null && r.hi != null) svg.append(el("line", { x1: xOf(r.lo), x2: xOf(r.hi), y1: y + dy, y2: y + dy, class: `ci ${cls}`, "stroke-dasharray": r.series === "primary" ? null : "5 3" }));
      svg.append(el("circle", { cx: xOf(r.value), cy: y + dy, r: 5, class: cls }, el("title", {}, `${g}, ${r.name}: ${fmtScore(r.value, 3)} (${fmtScore(r.lo, 3)} to ${fmtScore(r.hi, 3)}), ${plain("status", r.status).text}`)));
      svg.append(el("text", { x: W - PAD.r + 10, y: y + dy + 4, class: `row-status ${cls}-text` }, plain("status", r.status).text));
    });
  });
  const legend = h("ul", { class: "legend" }, spec.legend.map(([cls, text]) => h("li", {}, h("span", { class: `swatch ${cls}`, "aria-hidden": "true" }), text)));
  const table = tableToggle(spec.title, spec.tableHeaders, spec.rows.map((r) => [r.group, r.name, fmtScore(r.value, 3), `${fmtScore(r.lo, 3)} to ${fmtScore(r.hi, 3)}`, plain("status", r.status).text]));
  return figure(id, spec.title, spec.description, svg, [legend, table], spec.footnote);
}

function fmtScore(y, digits = 2) {
  if (typeof y !== "number" || !Number.isFinite(y)) return "—";
  return y.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits > 2 ? digits : 0 });
}
