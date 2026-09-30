import { getFrozen } from "../api.js";
import { MSG, PAGE } from "../copy.js";
import { h } from "../dom.js";
import { monthLabel, monthsIn, plain, shortDate } from "../pure/present.js";
import { chip, fmtInt, hero, kpis, loading, section, table, to } from "../ui.js";
import { loadExtent, loadStory, storySections, versions } from "./common.js";

const STATE = {
  available: ["Supplied", "No gap recorded by the API for this dataset-month."],
  missing: ["Missing", ""],
  reference: ["Reference", "Apr–May reference window: used to build the score, not scored."],
  scored: ["Scored", "Operational buckets scored."],
  partial: ["Partial", ""],
  unscored: ["Not scored", "No operational score for this month."],
};

export async function render(root, ctx) {
  root.replaceChildren(hero(PAGE.quality), loading());
  const [story, meta, method, provenance, extent] = await Promise.all([
    loadStory(),
    getFrozen("/api/v1/metadata"),
    getFrozen("/api/v1/metadata/methodology"),
    getFrozen("/api/v1/metadata/provenance"),
    loadExtent(),
  ]);
  const periods = meta.data.periods;
  const lim = story.limits;
  const quality = lim.operational_row_quality;
  const months = monthsIn(periods.source_period);
  const refMonths = monthsIn(String(periods.reference_period).split(" ")[0]);
  const lastMonth = extent.last_timestamp.slice(0, 7);
  const inputs = new Set();
  for (const f of method.data.phase7_score.feature_inventory || []) for (const d of String(f.source_dataset).split(";")) if (/^Kiln-/.test(d)) inputs.add(d);
  for (const m of lim.missing_months || []) inputs.add(m.dataset);
  const datasets = [...inputs].sort();

  const cells = [];
  const rows = [];
  for (const ds of datasets) {
    rows.push([ds, months.map((m) => {
      const gap = (lim.missing_months || []).find((x) => x.dataset === ds && x.month === m);
      const cell = { id: `${ds}-${m}`, ds, m, state: gap ? "missing" : "available", why: gap ? gap.reason : STATE.available[1] };
      cells.push(cell);
      return cell;
    })]);
  }
  rows.push(["Operational score (Phase 7)", months.map((m) => {
    let state = "scored";
    let why = STATE.scored[1];
    if (refMonths.includes(m)) { state = "reference"; why = STATE.reference[1]; }
    else if (m > lastMonth) { state = "unscored"; why = STATE.unscored[1]; }
    else if (m === lastMonth) { state = "partial"; why = `Scored to ${shortDate(extent.last_timestamp, true)}; nothing after that is filled.`; }
    const cell = { id: `score-${m}`, ds: "Operational score", m, state, why };
    cells.push(cell);
    return cell;
  })]);

  const matrix = h("figure", { class: "chart-figure", id: "matrix" },
    h("figcaption", { class: "chart-title", id: "matrix-title" }, "Dataset coverage by month"),
    h("p", { class: "chart-desc" }, `Source window ${periods.source_period}. Each cell names its state in text; pattern marks missing and partial. Select a cell for its detail.`),
    h("div", { class: "table-wrap" },
      h("table", { class: "matrix", "aria-labelledby": "matrix-title" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Dataset"), months.map((m) => h("th", { scope: "col" }, monthLabel(m))))),
        h("tbody", {}, rows.map(([ds, list]) => h("tr", {},
          h("th", { scope: "row" }, ds),
          list.map((c) => h("td", { class: `cov cov-${c.state}` },
            h("a", { href: to("/data-quality", {}, c.id), "aria-label": `${c.ds}, ${monthLabel(c.m)}: ${STATE[c.state][0]}. Open detail.` }, STATE[c.state][0])))))))),
    h("ul", { class: "legend" }, Object.entries(STATE).map(([k, [label]]) => h("li", {}, h("span", { class: `swatch cov-${k}`, "aria-hidden": "true" }), label))),
    h("p", { class: "chart-foot" }, `Missing months from ${lim.missing_months?.length ? "/metadata/limitations" : "—"} · score extent ${extent.version} · ${versions(story)}`));

  root.replaceChildren(
    hero(PAGE.quality),
    kpis([
      { label: "Missing dataset-months", value: String((lim.missing_months || []).length), meaning: (lim.missing_months || []).map((m) => `${m.dataset} ${monthLabel(m.month)}`).join(" · "), source: "Phase 9 · /metadata/limitations", link: to("/data-quality", {}, "matrix") },
      { label: "Open plant questions", value: String((story.requirements.plant_questions_open || []).length), meaning: "questions only the plant can answer", source: "Phase 9 · /metadata/data-requirements", link: to("/data-quality", {}, "questions") },
      { label: "Rows with poor data quality", value: fmtInt(quality.data_quality_status?.POOR), meaning: `of ${fmtInt(quality.n_rows)} operational rows; a row property, not a plant state`, source: "Phase 7 · operational_row_quality", link: to("/data-quality", {}, "rows") },
      { label: "Rows with ambient-like O₂", value: fmtInt(quality.o2_ambient_suspect_rows), meaning: "kiln-inlet O₂ readings that look like ambient air", source: "Phase 7 · operational_row_quality", link: to("/data-quality", {}, "L07") },
    ]),
    section("Coverage", "graph", matrix,
      h("details", { class: "table-toggle" },
        h("summary", {}, "Cell details"),
        table("Coverage cell details", ["Dataset", "Month", "State", "Detail"],
          cells.map((c) => h("tr", { id: c.id, tabindex: "-1" },
            h("td", { "data-label": "Dataset" }, c.ds), h("td", { "data-label": "Month" }, monthLabel(c.m)),
            h("td", { "data-label": "State" }, STATE[c.state][0]), h("td", { "data-label": "Detail" }, c.why)))))),
    section("Recorded limitations", "limitations",
      h("div", { class: "findings" }, (lim.limitations || []).map((l) => h("article", { class: "finding", id: l.id, "aria-labelledby": `${l.id}-h` },
        h("h3", { id: `${l.id}-h` }, h("span", { class: "fid" }, l.id), " ", plain("x", l.topic).text),
        chip("limitation", l.status),
        h("p", {}, l.detail),
        h("p", { class: "hint" }, `Source: ${l.source}`))))),
    section("Operational row quality", "rows",
      table("Operational row quality, as served", ["Measure", "Rows"], [
        ...Object.entries(quality.data_quality_status || {}).map(([k, n]) => [`Data quality: ${plain("x", k).text}`, fmtInt(n)]),
        ...Object.entries(quality.confidence_band || {}).map(([k, n]) => [`Confidence band: ${plain("x", k).text}`, fmtInt(n)]),
        ["Ambient-like kiln-inlet O₂", fmtInt(quality.o2_ambient_suspect_rows)],
        ["All operational rows", fmtInt(quality.n_rows)],
      ]),
      h("p", { class: "hint" }, lim.timestamp_semantics)),
    section("Open plant questions", "questions",
      h("ol", {}, (story.requirements.plant_questions_open || []).map((q) => h("li", {}, q)))),
    section("Artifact integrity", "artifacts",
      h("p", {}, "Each file the API serves is hash-checked at start-up. If any differs, the API refuses to answer: ", MSG.mismatch),
      table("Served artifacts", ["Artifact", "Version", "Status", "SHA-256 (first 12)"],
        (provenance.data.artifacts || []).map((a) => [a.key, a.version || "—", plain("x", a.analytical_status).text, (a.sha256 || "").slice(0, 12)]))),
    ...storySections("quality", story),
  );
}
