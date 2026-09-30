import { MSG, NAV } from "./copy.js";
import { h } from "./dom.js";
import { linkTarget, parseLocation } from "./pure/route.js";
import { failure, readOnly, to } from "./ui.js";
import { render as overview } from "./pages/overview.js";
import { render as historyPage } from "./pages/history.js";
import { render as periods } from "./pages/periods.js";
import { render as events } from "./pages/events.js";
import { render as validation } from "./pages/validation.js";
import { render as quality } from "./pages/quality.js";
import { render as methodology } from "./pages/methodology.js";

const PAGES = {
  "/": overview,
  "/history": historyPage,
  "/abnormal-periods": periods,
  "/events": events,
  "/validation": validation,
  "/data-quality": quality,
  "/methodology": methodology,
};

let controller = null;
let lastPage = null;

function current() {
  return parseLocation(location, readOnly);
}

/** Navigate inside the app. Path mode and hash mode both use the History API so back/forward work. */
export function go(target, { replace = false } = {}) {
  const url = readOnly ? `${location.pathname}${target}` : target;
  history[replace ? "replaceState" : "pushState"]({}, "", url);
  render();
}

function start() {
  document.getElementById("nav").replaceChildren(...NAV.map(([path, label]) =>
    h("li", {}, h("a", { href: to(path), "data-nav": path }, label))));
  if (readOnly) document.getElementById("ro-banner").hidden = false;
  const bar = document.querySelector(".disclaimer");
  new ResizeObserver(() => document.documentElement.style.setProperty("--sticky", `${bar.offsetHeight}px`)).observe(bar);
  document.body.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a");
    if (!link || link.target) return;
    const raw = link.getAttribute("href");
    if (raw === "#main") {
      event.preventDefault();
      document.getElementById("main").focus();
      return;
    }
    if (!linkTarget(raw, readOnly)) return;
    event.preventDefault();
    go(raw);
  });
  window.addEventListener("popstate", render);
  render();
}

function render() {
  controller?.abort();
  controller = new AbortController();
  const signal = controller.signal;
  const route = current();
  const page = PAGES[route.page];
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === route.page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  const main = document.getElementById("main");
  const key = `${route.page}|${route.id || ""}|${route.mode || ""}`;
  const samePage = lastPage === key;
  lastPage = key;
  const keep = samePage ? document.activeElement?.id || "" : "";
  // Pages only call root.replaceChildren; a superseded render must not overwrite the page the reader moved to.
  const root = { replaceChildren: (...nodes) => { if (!signal.aborted) main.replaceChildren(...nodes); } };
  Promise.resolve(page(root, { signal, route, go })).then(() => {
    if (signal.aborted) return;
    if (!route.known) main.querySelector(".hero")?.after(h("p", { class: "callout", role: "status" }, MSG.notFound));
    const title = main.querySelector("h1");
    document.title = `${title ? title.textContent : "Overview"} — Kiln Analytical POC — Dalmia Cement`;
    focusTarget(main, route, samePage, keep);
  }).catch((err) => {
    if (err?.name === "AbortError" || signal.aborted) return;
    console.error("[dashboard] route", route.page, err?.status || "", err?.code || "");
    main.replaceChildren(failure(err));
  });
}

/** Anchor target gets scroll + focus; otherwise a new page focuses its h1 so screen readers hear it. */
function focusTarget(main, route, samePage, keep) {
  const target = route.anchor ? document.getElementById(route.anchor) : null;
  if (target) {
    for (let d = target.closest("details"); d; d = d.parentElement?.closest("details")) d.open = true;
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
    return;
  }
  const panel = main.querySelector("[data-focus]");
  if (panel) {
    panel.scrollIntoView({ block: "start" });
    panel.focus({ preventScroll: true });
    return;
  }
  if (samePage) {
    if (keep) document.getElementById(keep)?.focus({ preventScroll: true });
    return;
  }
  window.scrollTo(0, 0);
  main.querySelector("h1")?.focus({ preventScroll: true });
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
else start();
