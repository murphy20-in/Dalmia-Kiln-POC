/** Shared page components. All text arrives as strings and is inserted as text nodes. */
import { ApiError } from "./api.js";
import { MSG, READ_ONLY, SECTION } from "./copy.js";
import { h } from "./dom.js";
import { plain } from "./pure/present.js";
import { href } from "./pure/route.js";
import { useSnapshot } from "./snapshot.js";

export const readOnly = useSnapshot();

/** Mode-aware in-app href. */
export function to(path, query = {}, anchor = "") {
  return href(path, query, anchor, readOnly);
}

export function hero(copy, extra) {
  return h("header", { class: "hero" },
    h("h1", { id: "page-title", tabindex: "-1" }, copy.title),
    h("p", { class: "hero-answer" }, copy.answer),
    extra || null,
    h("p", { class: "hero-meta" }, h("a", { href: to("/methodology", {}, copy.method) }, `${SECTION.method}: how this is worked out`)));
}

export function section(title, id, ...kids) {
  const headingId = `${id}-h`;
  return h("section", { class: `page-section section-${id}`, "aria-labelledby": headingId, id },
    h("h2", { id: headingId }, title), ...kids);
}

/** Enum rendered in plain English, raw value kept for traceability. */
export function enumText(kind, value) {
  const p = plain(kind, value);
  return p.raw && p.raw !== p.text ? h("abbr", { title: `API value: ${p.raw}` }, p.text) : p.text;
}

export function chip(kind, value) {
  const p = plain(kind, value);
  return h("span", { class: "chip", title: p.raw ? `API value: ${p.raw}` : null }, p.text);
}

/** KPI card: the whole card is a link. */
export function kpi({ label, value, raw, meaning, source, link }) {
  return h("a", { class: "kpi", href: link },
    h("span", { class: "kpi-label" }, label),
    h("span", { class: "kpi-value", title: raw ? `API value: ${raw}` : null }, value),
    h("span", { class: "kpi-meaning" }, meaning),
    h("span", { class: "kpi-source" }, `Source: ${source}`));
}

export function kpis(cards) {
  const cols = cards.length <= 4 ? cards.length : 3;
  return section(SECTION.kpis, "kpis", h("div", { class: "kpi-grid", style: `--cols:${cols}` }, cards.map(kpi)));
}

/** A link to a write route, or a disabled button with the reason on the hosted copy. */
export function writeLink(label, path, query = {}, cls = "btn btn-primary") {
  if (!readOnly) return h("a", { class: cls, href: to(path, query) }, label);
  return h("span", { class: "ro-wrap" },
    h("button", { type: "button", class: cls, disabled: true }, label),
    h("span", { class: "ro-reason" }, READ_ONLY.reason));
}

export function actionBar(spec) {
  const [label, path, write] = spec.primary;
  return h("nav", { class: "action-bar", "aria-label": SECTION.actions },
    write ? writeLink(label, path) : h("a", { class: "btn btn-primary", href: to(path) }, label),
    spec.secondary.map(([text, p, anchor, query]) => h("a", { class: "btn btn-secondary", href: to(p, query || {}, anchor || "") }, text)));
}

export function loading(message = MSG.loading) {
  return h("p", { class: "state state-loading", role: "status" }, message);
}

export function failure(err) {
  const message = err instanceof ApiError || err?.status ? err.message : MSG.failed;
  return h("div", { class: "state state-error", role: "alert" },
    h("p", {}, message),
    h("p", {}, h("a", { href: to("/methodology") }, "Methodology"), " · ", h("a", { href: to("/data-quality") }, "Data quality")));
}

export function table(caption, headers, records, attrs = {}) {
  return h("div", { class: "table-wrap" },
    h("table", { class: "resp", ...attrs },
      h("caption", {}, caption),
      h("thead", {}, h("tr", {}, headers.map((x) => h("th", { scope: "col" }, x)))),
      h("tbody", {}, records.map((r) => (r.nodeType ? r : h("tr", {}, r.map((cell, i) => h("td", { "data-label": headers[i] }, cell))))))));
}

export function facts(pairs) {
  return h("dl", { class: "facts" }, pairs.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v ?? "—")]));
}

export function field(id, label, control, hint) {
  return h("div", { class: "field" },
    h("label", { for: id }, label),
    control,
    hint ? h("p", { class: "hint", id: `${id}-hint` }, hint) : null);
}

export function select(id, options, value, extra = {}) {
  return h("select", { id, name: id, ...extra },
    options.map(([val, label]) => h("option", { value: val, selected: val === value }, label)));
}

export function toast(message) {
  const host = document.getElementById("toast");
  if (!host) return;
  host.textContent = message;
  host.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { host.hidden = true; }, 4000);
}

export function fmtInt(n) {
  return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("en-GB") : "—";
}

export function exact(n, digits = 3) {
  return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("en-GB", { maximumFractionDigits: digits }) : "—";
}
