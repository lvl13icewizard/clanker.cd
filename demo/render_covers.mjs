// Batch-render demo covers with the site's own canvas renderer, one browser
// for the whole run (the engine's render.mjs launches one per cover, which is
// fine weekly and far too slow for sixty).
//
//   node demo/render_covers.mjs jobs.json
//
// jobs.json: [{ name, issue, palette: [..], recipe: {..}, outText, outPlain }]
// Prints one JSON line: {"rendered": n, "bytes": total}
//
// PLAYWRIGHT_DIR / PLAYWRIGHT_CHROMIUM override where playwright lives.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
// Playwright comes from whichever app has it installed (reader/ or site/
// after `npm install`), or from PLAYWRIGHT_DIR. Its own downloaded Chromium
// is used unless PLAYWRIGHT_CHROMIUM points at another binary.
const ROOT = path.resolve(here, "..");
const PW_CANDIDATES = [process.env.PLAYWRIGHT_DIR, path.join(ROOT, "reader/node_modules/playwright"), path.join(ROOT, "site/node_modules/playwright")].filter(Boolean);
const PW_DIR = PW_CANDIDATES.find((p) => fs.existsSync(path.join(p, "index.mjs")));
if (!PW_DIR) { console.error("playwright not found: run `npm install` in reader/ (then `npx playwright install chromium`), or set PLAYWRIGHT_DIR"); process.exit(1); }
const EXE = process.env.PLAYWRIGHT_CHROMIUM || undefined;
const { chromium } = await import(pathToFileURL(path.join(PW_DIR, "index.mjs")).href);

const SIZE = 640;
const MAX = 256 * 1024;
const src = fs.readFileSync(path.resolve(here, "../site/reader/cover/render.js"), "utf8")
  + "\nwindow.__renderCover = renderCover;\n";

const browser = await chromium.launch({ executablePath: fs.existsSync(EXE) ? EXE : undefined });
const page = await browser.newPage({ viewport: { width: SIZE + 40, height: SIZE + 40 }, deviceScaleFactor: 1 });
await page.setContent(`<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@500;600&display=swap">
<style>body{margin:0;background:#fff;font-family:Figtree,sans-serif}</style></head>
<body><span style="font:600 20px Figtree">warm</span><canvas id="c"></canvas></body></html>`,
  { waitUntil: "load" });
await page.addScriptTag({ type: "module", content: src });
await page.waitForFunction(() => typeof window.__renderCover === "function", null, { timeout: 15000 });
await page.evaluate(async () => {
  try {
    await Promise.all([document.fonts.load("600 64px Figtree"), document.fonts.load("500 20px Figtree")]);
    await document.fonts.ready;
  } catch {}
});

async function one(job, plain) {
  for (const q of [0.9, 0.86, 0.82, 0.78, 0.72, 0.66]) {
    const dataUrl = await page.evaluate(({ name, issue, palette, recipe, size, plain, q }) => {
      const c = document.getElementById("c");
      window.__renderCover(c, { name, issue, palette, recipe, size, plain });
      return c.toDataURL("image/jpeg", q);
    }, { ...job, size: SIZE, plain, q });
    const buf = Buffer.from(dataUrl.split(",")[1], "base64");
    if (buf.length <= MAX || q === 0.66) return buf;
  }
}

let rendered = 0, bytes = 0;
for (const job of jobs) {
  for (const [key, plain] of [["outText", false], ["outPlain", true]]) {
    if (!job[key]) continue;
    const buf = await one(job, plain);
    fs.mkdirSync(path.dirname(job[key]), { recursive: true });
    fs.writeFileSync(job[key], buf);
    rendered++;
    bytes += buf.length;
  }
}
await browser.close();
console.log(JSON.stringify({ rendered, bytes }));
