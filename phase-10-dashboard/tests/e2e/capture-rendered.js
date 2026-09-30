// Playwright snippet (run with the Playwright MCP `browser_run_code_unsafe`, filename = this file).
// Visits every page on the local service and stores its rendered text in localStorage under capture.<page>.
// Then: browser_evaluate `() => JSON.stringify(Object.fromEntries(Object.keys(localStorage).filter(k => k.startsWith('capture.')).map(k => [k.slice(8), localStorage.getItem(k)])))`
// with a filename, and split the JSON into tests/fixtures/rendered/<page>.txt (see reviews/E2E_LOG.md).
// One block per element; an insight or finding card is one block, because it is read as one unit on screen.
async (page) => {
  const pages = [["overview", "/"], ["history", "/history"], ["periods", "/abnormal-periods/P6-025"], ["events", "/events"],
    ["events-new", "/events/new?start=2025-06-15T17:30:00&end=2025-06-16T00:20:00&ref=P6-025"], ["validation", "/validation"],
    ["quality", "/data-quality"], ["methodology", "/methodology"]];
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const [name, path] of pages) {
    await page.goto(`http://127.0.0.1:8010${path}`);
    await page.waitForSelector("#page-title");
    await page.waitForFunction(() => !document.querySelector(".state-loading"), null, { timeout: 15000 });
    await page.evaluate((n) => {
      document.querySelectorAll("details").forEach((d) => { d.open = true; });
      const unit = ".insight, .finding";
      const sel = "header p, .disclaimer, .ro-banner, h1, h2, h3, p, li, dt, dd, td, th, caption, figcaption, summary, legend, label, a.btn, button, .kpi, .chip, svg title, svg text";
      const blocks = [];
      const push = (el) => { const t = (el.textContent || "").replace(/\s+/g, " ").trim(); if (t) blocks.push(t); };
      document.querySelectorAll(unit).forEach(push);
      document.querySelectorAll(sel).forEach((el) => { if (!el.closest(unit)) push(el); });
      document.querySelectorAll("[aria-label], [title]").forEach((el) => { for (const a of ["aria-label", "title"]) { const v = el.getAttribute(a); if (v) blocks.push(v); } });
      localStorage.setItem(`capture.${n}`, blocks.join("\n\n"));
    }, name);
  }
  return pages.length;
}
