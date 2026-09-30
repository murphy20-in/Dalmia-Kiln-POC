import { h } from "./dom.js";
import { ApiError } from "./api.js";

export function pageHeader(title, lede) {
  return h("header", { class: "page-head" },
    h("h1", {}, title),
    lede ? h("p", { class: "lede" }, lede) : null);
}

export function links() {
  return h("p", { class: "crosslinks" },
    "Related: ",
    h("a", { href: "/methodology" }, "Methodology"),
    ", ",
    h("a", { href: "/data-quality" }, "Limitations and data quality"),
    ", ",
    h("a", { href: "/validation" }, "Validation"));
}

export function loading(message) {
  return h("p", { class: "state", role: "status" }, message);
}

export function failure(err, fallback) {
  const message = err instanceof ApiError ? err.message : (fallback || "This page could not be loaded.");
  return h("div", { class: "state state-error", role: "alert" },
    h("p", {}, message),
    links());
}

export function empty(message) {
  return h("p", { class: "state", role: "status" }, message);
}

export function fmt(n, digits = 3) {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-GB", { maximumFractionDigits: digits });
}

export function stamp(value) {
  return value ? String(value).replace("T", " ") : "—";
}

export function table(caption, headers, records) {
  return h("div", { class: "table-wrap" },
    h("table", { class: "resp" },
      h("caption", {}, caption),
      h("thead", {}, h("tr", {}, headers.map((header) => h("th", { scope: "col" }, header)))),
      h("tbody", {}, records.map((record) => h("tr", {}, record.map((cell, i) =>
        h("td", { "data-label": headers[i] }, cell)))))));
}

export function field(id, label, control, error) {
  return h("div", { class: "field" },
    h("label", { for: id }, label),
    control,
    error ? h("p", { class: "field-error", id: `${id}-error` }, error) : null);
}

export function select(id, options, value, extra = {}) {
  return h("select", { id, name: id, ...extra },
    options.map(([val, label]) => h("option", { value: val, ...(val === value ? { selected: true } : {}) }, label)));
}
