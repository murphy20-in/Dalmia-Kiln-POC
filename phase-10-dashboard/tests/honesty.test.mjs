import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { BRAND, DISCLAIMER, READ_ONLY } from "../public/js/copy.js";
import { FORBIDDEN_UI, lineAllowsForbidden } from "../public/js/pure/present.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../public");

async function files(dir, re) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await files(full, re));
    else if (re.test(entry.name)) out.push(full);
  }
  return out;
}

/** Prose string literals ("…", '…', `…`) that contain a space. Single tokens are attribute values, not copy. */
function prose(source) {
  const out = [];
  const re = /"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g;
  for (const m of source.matchAll(re)) {
    const text = m[1] ?? m[2] ?? m[3];
    if (/\s/.test(text) && /[a-z]{3}/i.test(text)) out.push(text);
  }
  return out;
}

function violations(label, texts) {
  const hits = [];
  for (const text of texts) {
    if (!FORBIDDEN_UI.some((re) => re.test(text))) continue;
    if (!lineAllowsForbidden(text)) hits.push(`${label}: ${text.trim().slice(0, 160)}`);
  }
  return hits;
}

test("client copy never makes a forbidden claim (copy.js, pages, components, shell)", async () => {
  const sources = [
    path.join(root, "js/copy.js"), path.join(root, "js/ui.js"), path.join(root, "js/chart.js"), path.join(root, "js/app.js"),
    ...await files(path.join(root, "js/pages"), /\.js$/),
  ];
  const hits = [];
  for (const file of sources) hits.push(...violations(path.relative(root, file), prose(await readFile(file, "utf8"))));
  for (const file of [path.join(root, "index.html"), path.join(root, "404.html")]) {
    const text = (await readFile(file, "utf8")).replace(/<script[\s\S]*?<\/script>/g, "").replace(/<[^>]+>/g, "\n");
    hits.push(...violations(path.relative(root, file), text.split(/\n+/)));
  }
  assert.deepEqual(hits, []);
});

test("the static shell carries the copy.js disclaimer, wordmark and read-only banner verbatim", async () => {
  const html = await readFile(path.join(root, "index.html"), "utf8");
  for (const s of [DISCLAIMER.strong, DISCLAIMER.text, BRAND.mark, BRAND.product, READ_ONLY.banner]) assert.ok(html.includes(s), s);
});

test("hosted copy: write actions go through the read-only helpers, which always show the reason", async () => {
  const ui = await readFile(path.join(root, "js/ui.js"), "utf8");
  assert.match(ui, /export function roButton[\s\S]*?READ_ONLY\.reason/);
  assert.match(ui, /export function writeLink[\s\S]*?return roButton\(/);
  const direct = [];
  for (const file of await files(path.join(root, "js/pages"), /\.js$/)) {
    const text = await readFile(file, "utf8");
    // The Overview annotations KPI card opens the form, which is itself read-only with the reason on the hosted copy.
    for (const m of text.matchAll(/href: to\(\s*[`"]\/events\/(new|[^`"]*\/edit)/g)) direct.push(`${path.basename(file)}: ${m[0]}`);
  }
  assert.deepEqual(direct, []);
  const events = await readFile(path.join(root, "js/pages/events.js"), "utf8");
  assert.match(events, /readOnly \? roButton\("Withdraw"/);
  assert.match(events, /readOnly \?[^\n]*"aria-disabled": "true"[^\n]*READ_ONLY\.reason/);
});

test("rendered pages never make a forbidden claim (text captured by the browser journeys)", async (t) => {
  const dir = path.join(here, "fixtures/rendered");
  let names = [];
  try {
    names = (await readdir(dir)).filter((n) => n.endsWith(".txt"));
  } catch {
    t.skip("no rendered captures; run the browser journeys in reviews/E2E_LOG.md");
    return;
  }
  assert.ok(names.length >= 7, "one capture per page");
  const hits = [];
  for (const name of names) {
    const blocks = (await readFile(path.join(dir, name), "utf8")).split(/\n{2,}/);
    hits.push(...violations(name, blocks));
  }
  assert.deepEqual(hits, []);
});

test("the forbidden-wording rule itself catches claims and allows denials", () => {
  assert.equal(lineAllowsForbidden("The score predicts ring formation"), false);
  assert.equal(lineAllowsForbidden("Live monitoring of the kiln"), false);
  assert.equal(lineAllowsForbidden("Early warning available for coating"), false);
  assert.equal(lineAllowsForbidden("Retrospective, not an early warning."), true);
  assert.equal(lineAllowsForbidden("Early-warning validation: not supported"), true);
  assert.equal(lineAllowsForbidden("It does not show live data or raise alarms"), true);
  assert.equal(lineAllowsForbidden("KPI-derived abnormal periods (not plant events)"), true);
});

test("no statistic is computed on the client", async () => {
  const hits = [];
  for (const file of await files(path.join(root, "js"), /\.js$/)) {
    if (file.endsWith(`${path.sep}series.js`)) continue; // display thinning only
    const src = (await readFile(file, "utf8")).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
    src.split("\n").forEach((line, i) => {
      const where = `${path.relative(root, file)}:${i + 1}: ${line.trim()}`;
      if (/\b(const|let|var|function)\s+\w*(median|mean|average|avg|percent|pct|rate|ratio|share|corr|stdev|variance)\w*\b/i.test(line)) hits.push(where);
      if (/\.reduce\s*\(/.test(line)) hits.push(where);
      if (/\/\s*[\w.]*\.(length|total|n_rows|n_periods)\b/.test(line)) hits.push(where);
      if (/\*\s*100\b|\btoFixed\(\s*\d\s*\)\s*\+\s*["'`]%/.test(line)) hits.push(where);
    });
  }
  assert.deepEqual(hits, []);
});

test("data states never use alarm or brand-accent colours", async () => {
  const css = await readFile(path.join(root, "css/app.css"), "utf8");
  assert.equal(/\.(high|elevated|low|danger|safe|alarm|warning|critical)\b/.test(css), false);
  assert.equal(/#f00\b|#ff0000|\bred\b|\byellow\b|\borange\b|#c4511a|amber/i.test(css), false);
  for (const rule of css.match(/\.(sev-[a-z]+|cov-[a-z]+|chip|band(-link|-focus|-label[\w-]*)?|swatch-(high|moderate|low|sev))[^{]*\{[^}]*\}/g) || []) {
    assert.equal(/var\(--cyan\)/.test(rule), false, rule);
  }
});

test("untrusted text is never assigned as HTML", async () => {
  const js = [];
  for (const file of await files(path.join(root, "js"), /\.js$/)) js.push(await readFile(file, "utf8"));
  const source = js.join("\n");
  assert.equal(/\.innerHTML\s*=|outerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(/.test(source), false);
});

test("the O₂-excluded overlay is off by default and never styled as primary", async () => {
  const history = await readFile(path.join(root, "js/pages/history.js"), "utf8");
  assert.match(history, /const overlay = q\.overlay === "o2_excluded";/);
  assert.match(history, /O₂-excluded — sensitivity analysis, not preferred", key: "o2_excluded_empirical_risk_score", rows, dash: true/);
  const css = await readFile(path.join(root, "css/app.css"), "utf8");
  assert.match(css, /\.series-sensitivity \{ stroke: var\(--grey\)/);
});
