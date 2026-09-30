import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { FORBIDDEN_UI, lineAllowsForbidden } from "../public/js/pure/present.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../public");

async function files(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await files(full));
    else if (/\.(js|css|html)$/.test(entry.name)) out.push(full);
  }
  return out;
}

test("forbidden wording only appears where the claim is denied", async () => {
  const hits = [];
  for (const file of await files(root)) {
    if (file.endsWith(`${path.sep}present.js`)) continue;
    const lines = (await readFile(file, "utf8")).split("\n");
    lines.forEach((line, i) => {
      if (!FORBIDDEN_UI.some((re) => re.test(line))) return;
      if (!lineAllowsForbidden(line)) hits.push(`${path.relative(root, file)}:${i + 1}: ${line.trim()}`);
    });
  }
  assert.deepEqual(hits, []);
});

test("score bands are not styled as alarm states", async () => {
  const css = await readFile(path.join(root, "css/app.css"), "utf8");
  assert.equal(/\.(high|elevated|low|danger|safe|alarm)\b/.test(css), false);
  assert.equal(/#f00\b|#ff0000|red\b|yellow\b/i.test(css), false);
});

test("untrusted text is not assigned as HTML", async () => {
  const js = [];
  for (const file of await files(path.join(root, "js"))) js.push(await readFile(file, "utf8"));
  const source = js.join("\n");
  assert.equal(/\.innerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(/.test(source), false);
});
