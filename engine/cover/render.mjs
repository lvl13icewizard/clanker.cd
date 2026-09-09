// Headless render of the weekly cover, using the site's own renderer so the
// engine and the lab can never disagree. No dev server needed: the renderer
// source is injected into a blank page, Figtree is loaded from Google Fonts,
// and both variants (with the name for Spotify, plain for the site) are
// written as JPEG under the Spotify 256 KB limit.
//
//   node engine/cover/render.mjs --name "Held Breath" --issue 2 \
//     --palette "#c08a66,#ee2519,#317a97,#882229" --recipe '{"blur":40}' \
//     --out-text site/public/issues/cover-002.jpg --out-plain site/public/issues/cover-002-plain.jpg
//
// PLAYWRIGHT_DIR overrides where the playwright package lives (default: the
// machine's existing install under listen-logger/node_modules).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, arr) => {
  if (a.startsWith("--")) acc.push([a.slice(2), arr[i + 1] && !arr[i + 1].startsWith("--") ? arr[i + 1] : "true"]);
  return acc;
}, []));
// Playwright comes from whichever app has it installed (reader/ or site/
// after `npm install`), or from PLAYWRIGHT_DIR. Its own downloaded Chromium
// is used unless PLAYWRIGHT_CHROMIUM points at another binary.
const ROOT = path.resolve(here, "../..");
const PW_CANDIDATES = [process.env.PLAYWRIGHT_DIR, path.join(ROOT, "reader/node_modules/playwright"), path.join(ROOT, "site/node_modules/playwright")].filter(Boolean);
const PW_DIR = PW_CANDIDATES.find((p) => fs.existsSync(path.join(p, "index.mjs")));
if (!PW_DIR) { console.error("playwright not found: run `npm install` in reader/ (then `npx playwright install chromium`), or set PLAYWRIGHT_DIR"); process.exit(1); }
const EXE = process.env.PLAYWRIGHT_CHROMIUM || undefined;
const { chromium } = await import(pathToFileURL(path.join(PW_DIR, "index.mjs")).href);

const size = parseInt(args.size || "640", 10);
const name = args.name || "";
const issue = parseInt(args.issue || "0", 10);
const palette = (args.palette || "").split(",").map((s) => s.trim()).filter(Boolean);
const recipe = args.recipe ? JSON.parse(args.recipe) : {};
const maxBytes = parseInt(args["max-bytes"] || String(256 * 1024), 10);
// The cover painter lives with the frozen first reader (the redesign
// promotion moved site/src; the archive copy is identical).
const src = fs.readFileSync(path.resolve(here, "../../site/reader/cover/render.js"), "utf8") + "\nwindow.__renderCover = renderCover;\n";

const browser = await chromium.launch({ executablePath: fs.existsSync(EXE) ? EXE : undefined });
const page = await browser.newPage({ viewport: { width: size + 40, height: size + 40 }, deviceScaleFactor: 1 });
await page.setContent(`<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@500;600&display=swap">
<style>body{margin:0;background:#fff;font-family:Figtree,sans-serif}</style></head>
<body><span style="font:600 20px Figtree">warm</span><canvas id="c"></canvas></body></html>`, { waitUntil: "load" });
await page.addScriptTag({ type: "module", content: src });
await page.waitForFunction(() => typeof window.__renderCover === "function", null, { timeout: 10000 });
await page.evaluate(async () => {
  try { await Promise.all([document.fonts.load("600 64px Figtree"), document.fonts.load("500 20px Figtree")]); await document.fonts.ready; } catch {}
});

async function render(plain) {
  for (const q of [0.9, 0.86, 0.82, 0.78, 0.72, 0.66]) {
    const dataUrl = await page.evaluate(({ name, issue, palette, recipe, size, plain, q }) => {
      const c = document.getElementById("c");
      window.__renderCover(c, { name, issue, palette, recipe, size, plain });
      return c.toDataURL("image/jpeg", q);
    }, { name, issue, palette, recipe, size, plain, q });
    const buf = Buffer.from(dataUrl.split(",")[1], "base64");
    if (buf.length <= maxBytes || q === 0.66) return { buf, q };
  }
}
const out = {};
if (args["out-text"]) { const { buf, q } = await render(false); fs.writeFileSync(args["out-text"], buf); out.text = { path: args["out-text"], bytes: buf.length, quality: q }; }
if (args["out-plain"]) { const { buf, q } = await render(true); fs.writeFileSync(args["out-plain"], buf); out.plain = { path: args["out-plain"], bytes: buf.length, quality: q }; }
await browser.close();
console.log(JSON.stringify(out));
