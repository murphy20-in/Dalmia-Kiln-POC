import { h, text } from "./dom.js";
import { readRange, writeRange } from "./state.js";
import { render as overview } from "./pages/overview.js";
import { render as history } from "./pages/history.js";
import { render as periods } from "./pages/periods.js";
import { render as events } from "./pages/events.js";
import { render as validation } from "./pages/validation.js";
import { render as quality } from "./pages/quality.js";
import { render as methodology } from "./pages/methodology.js";

const STATIC_HOST = location.hostname.endsWith("github.io");

const ROUTES = {
  "/": overview,
  "/history": history,
  "/abnormal-periods": periods,
  "/events": events,
  "/validation": validation,
  "/data-quality": quality,
  "/methodology": methodology,
};

let controller = null;

export function start() {
  if (STATIC_HOST) {
    document.querySelectorAll("a[href^='/']").forEach((link) => {
      const href = link.getAttribute("href");
      link.setAttribute("href", `#${href}`);
    });
    const note = document.getElementById("static-note");
    if (note) note.hidden = false;
  }
  document.body.addEventListener("click", (event) => {
    const link = event.target.closest("a");
    if (!link || link.origin !== location.origin || link.target || event.metaKey || event.ctrlKey || event.shiftKey) return;
    const path = link.hash.startsWith("#/") ? link.hash.slice(1).split("?")[0] : link.pathname;
    if (!ROUTES[path]) return;
    event.preventDefault();
    navigate(path);
  });
  window.addEventListener(STATIC_HOST ? "hashchange" : "popstate", () => render());
  render();
}

function navigate(path) {
  if (STATIC_HOST) {
    location.hash = path;
    return;
  }
  const url = new URL(location.href);
  url.pathname = path;
  history.pushState({}, "", url);
  render();
}

function currentPath() {
  if (!STATIC_HOST) return ROUTES[location.pathname] ? location.pathname : "/";
  const raw = (location.hash || "#/").slice(1).split("?")[0];
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  return ROUTES[path] ? path : "/";
}

function render() {
  controller?.abort();
  controller = new AbortController();
  const path = currentPath();
  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.getAttribute("href") === path) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const range = readRange();
  const label = document.getElementById("range-status");
  text(label, range ? `Score window ${range.start.replace("T", " ")} – ${range.end.replace("T", " ")} (end exclusive).` : "Score window not set. Historical Risk will open the latest 14 days of the operational series.");
  const main = document.getElementById("main");
  const page = ROUTES[path];
  page(main, {
    signal: controller.signal,
    range,
    setRange(next) {
      const saved = writeRange(next);
      text(label, saved ? `Score window ${saved.start.replace("T", " ")} – ${saved.end.replace("T", " ")} (end exclusive).` : label.textContent);
    },
  }).catch((err) => {
    if (err?.name === "AbortError") return;
    console.error("[dashboard]", "route", path);
    main.replaceChildren(h("p", { class: "state state-error", role: "alert" }, "This page could not be loaded."));
  });
}

start();
