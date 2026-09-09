// Builds the landing page's product reel: one clip per section of an issue,
// each a slow camera move over a high-resolution capture of the real page,
// stitched back to back into a single file with a chapter map.
//
// The camera is a crop window travelling over a still, so the moves are
// exact and repeatable, and re-running this after a design change re-presses
// the reel. Captures the approved reader (site/reader) showing Andrew's
// demo, so it needs the public dev server up (npm run dev, port 3011) and
// ffmpeg on PATH.
//
//   node scripts/make-reel.mjs [origin] [issue]
//
// Writes site/public/brand/reel/light.mp4, its poster, and reel.json (the
// chapter map the player reads). The reader has one theme, so one reel.

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLAYWRIGHT = [
  "playwright",
  new URL("../../reader/node_modules/playwright/index.mjs", import.meta.url).href,
];
let chromium;
for (const spec of PLAYWRIGHT) {
  try { ({ chromium } = await import(spec)); break; } catch { /* try the next */ }
}
if (!chromium) { console.error("playwright not found"); process.exit(1); }

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../public/brand/reel");
const TMP = resolve(HERE, "../.reel-tmp");
const ORIGIN = process.argv[2] || "http://localhost:3011";
const ISSUE = process.argv[3] ? `&n=${process.argv[3]}` : "&view=latest";
const DEMO = "andrew";
const THEME = "light";

// One chapter per row of the landing page's feature list, named to match.
const CHAPTERS = [
  { slug: "singles", label: "Singles Rack", section: "Singles Rack" },
  { slug: "album", label: "Album of the Week", section: "Album of the Week" },
  { slug: "mixes", label: "Mixes", section: "Mixes" },
  { slug: "second", label: "Second Chances", section: "Second Chances" },
  { slug: "critics", label: "Critics Desk", section: "Critics Desk" },
  { slug: "catalog", label: "Catalog Room", section: "Catalog Room" },
  { slug: "ntw", label: "New This Week", section: "New This Week" },
  { slug: "ledger", label: "The Ledger", section: "The Ledger" },
];

// The reader lays out at 1440: a chapter rail on the left, the reading
// column from about x=305 to x=1112, the listening rail on the right. The
// frame shows the reading column alone.
const PAGE_W = 1440;      // the width the app is captured at
const PAGE_H = 3000;      // tall enough to hold the longest section in one shot
const CROP_X = 285;
const CROP_W = 850;       // CSS px of page across the frame
const HEAD_ROOM = 44;     // room above a section head: the hairline, not the dead air
const TAIL = 40;

const FRAME_W = 1664;     // render size: 2x the 832px the reel is shown at
const FRAME_H = 1040;     // 16:10
const OUT_W = 1520;       // delivered size, scaled down from the render
const OUT_H = 950;
const CRF = 28;           // the size budget: this is a big page asset
const ASPECT = FRAME_W / FRAME_H;
const FPS = 30;
const SECONDS = 6;
const FADE = 0.45;        // seconds in and out, to the page's own paper
const PAN_RATE = 240;     // CSS px per second: the ceiling on how fast we move
const WIDE = 830;         // crop width at the start of a move: already in, not a wide shot
const TIGHT = 750;       // and at the end, so every clip pushes in a little

const PAPER = "#f7f7f4";  // the reader's ground
const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

async function settle(page) {
  await page.waitForFunction(() => [...document.images].every((i) => i.complete),
    null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(400);
}

const REUSE = process.env.REUSE_SHOTS === "1" && existsSync(`${TMP}/shots`);
if (!REUSE) rmSync(TMP, { recursive: true, force: true });
rmSync(`${TMP}/frames`, { recursive: true, force: true });
mkdirSync(`${TMP}/shots`, { recursive: true });
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch(
  process.env.CHROME_HEADLESS_SHELL ? { executablePath: process.env.CHROME_HEADLESS_SHELL } : {});

// ---- 1. capture each section at 2x, tall enough that the camera can travel
const shots = {};
{
  if (REUSE) {
    for (const c of CHAPTERS) {
      const file = `${TMP}/shots/${c.slug}.png`;
      if (existsSync(file)) shots[c.slug] = { file, h: null };
    }
  }
  if (Object.keys(shots).length === CHAPTERS.length) {
    console.log("  reusing shots");
  } else {
    const ctx = await browser.newContext({
      viewport: { width: PAGE_W, height: PAGE_H }, deviceScaleFactor: 2,
      colorScheme: THEME, reducedMotion: "reduce",
    });
    const page = await ctx.newPage();
    await page.goto(`${ORIGIN}/?demo=${DEMO}${ISSUE}&clean=1`, { waitUntil: "networkidle" });
    await page.waitForSelector("section.issue-section");
    await settle(page);
    for (const c of CHAPTERS) {
      const box = await page.evaluate(({ head, room }) => {
        const sec = [...document.querySelectorAll("section.issue-section")]
          .find((s) => s.querySelector("h2")?.textContent?.trim().startsWith(head));
        if (!sec) return null;
        const r = sec.getBoundingClientRect();
        const top = Math.max(0, r.top + window.scrollY - room);
        window.scrollTo({ top, behavior: "instant" });
        // The scroll clamps at the foot of the page, so read where the head
        // ACTUALLY landed and start the clip there.
        const after = sec.getBoundingClientRect();
        return { h: Math.round(r.height), y: Math.max(0, Math.round(after.top - room)) };
      }, { head: c.section, room: HEAD_ROOM });
      if (!box) { console.warn(`  skip ${c.slug}: no section`); continue; }
      await page.waitForTimeout(320);
      const h = Math.min(box.h + HEAD_ROOM + TAIL, PAGE_H - box.y);
      if (box.y > 2) console.warn(`  note ${c.slug}: scroll clamped, clipping from y=${box.y} (${h}px tall)`);
      const file = `${TMP}/shots/${c.slug}.png`;
      await page.screenshot({ path: file, clip: { x: CROP_X, y: box.y, width: CROP_W, height: h } });
      shots[c.slug] = { file, h };
      console.log(`  shot ${c.slug}  ${CROP_W}x${h}`);
    }
    await ctx.close();
  }
}

// ---- 2. fly the camera over each still and keep every frame
const total = SECONDS * FPS;
const rig = await browser.newContext({
  viewport: { width: FRAME_W, height: FRAME_H }, deviceScaleFactor: 1,
});
const stage = await rig.newPage();
const dir = `${TMP}/frames`;
mkdirSync(dir, { recursive: true });
const rigFile = `${TMP}/rig.html`;
writeFileSync(rigFile, `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;overflow:hidden;background:${PAPER}}
  #f{position:relative;width:${FRAME_W}px;height:${FRAME_H}px;overflow:hidden;background:${PAPER}}
  #i{position:absolute;top:0;left:0;transform-origin:0 0;will-change:transform,opacity}
</style><div id="f"><img id="i"></div>`);
await stage.goto("file://" + rigFile);

let n = 0;
const built = [];
for (const c of CHAPTERS) {
  const shot = shots[c.slug];
  if (!shot) continue;
  const loaded = await stage.evaluate((src) => new Promise((done) => {
    const i = document.getElementById("i");
    i.onload = () => done(true);
    i.onerror = () => done(false);
    setTimeout(() => done(i.naturalWidth > 0), 8000);
    i.src = src;
  }), "file://" + shot.file);
  if (!loaded) throw new Error(`could not load ${shot.file} into the rig`);
  shot.h = await stage.evaluate(() => document.getElementById("i").naturalHeight / 2);

  const frameH0 = WIDE / ASPECT;
  const frameH1 = TIGHT / ASPECT;
  const travel = clamp(shot.h - frameH1, 0, PAN_RATE * SECONDS);
  const cy0 = clamp(frameH0 / 2, 0, Math.max(0, shot.h - frameH0 / 2));
  const cy1 = travel > 0 ? cy0 + travel : cy0 + 14;

  for (let f = 0; f < total; f++) {
    const t = f / (total - 1);
    const e = ease(t);
    const w = WIDE + (TIGHT - WIDE) * e;
    const cy = cy0 + (cy1 - cy0) * e;
    const secs = f / FPS;
    const fade = Math.min(clamp(secs / FADE, 0, 1), clamp((SECONDS - secs) / FADE, 0, 1));
    await stage.evaluate(({ w, cy, fade, cropW, aspect, fw }) => {
      const scale = fw / (w * 2);              // the still is a 2x capture
      const tx = -((cropW / 2) * 2 - (w * 2) / 2) * scale;
      const ty = -(cy * 2 - (w / aspect) * 2 / 2) * scale;
      const i = document.getElementById("i");
      i.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
      i.style.opacity = String(fade);
    }, { w, cy, fade, cropW: CROP_W, aspect: ASPECT, fw: FRAME_W });
    await stage.screenshot({ path: `${dir}/${String(n++).padStart(5, "0")}.jpg`, type: "jpeg", quality: 92 });
  }
  built.push(c);
  console.log(`  flew ${c.slug}`);
}

// ---- 3. encode, and keep a poster for the paused state
const scale = `scale=${OUT_W}:${OUT_H}:flags=lanczos`;
execFileSync("ffmpeg", ["-y", "-framerate", String(FPS), "-i", `${dir}/%05d.jpg`,
  "-vf", scale, "-c:v", "libx264", "-preset", "veryslow", "-crf", String(CRF),
  "-pix_fmt", "yuv420p", "-movflags", "+faststart", `${OUT}/${THEME}.mp4`], { stdio: "ignore" });
execFileSync("ffmpeg", ["-y", "-i", `${dir}/00045.jpg`, "-vf", scale, "-q:v", "6",
  `${OUT}/${THEME}-poster.jpg`], { stdio: "ignore" });
console.log(`  encoded ${THEME}.mp4`);

await rig.close();
await browser.close();

writeFileSync(`${OUT}/reel.json`, JSON.stringify({
  fps: FPS, width: FRAME_W, height: FRAME_H, seconds: SECONDS, fade: FADE,
  chapters: built.map((c, i) => ({
    slug: c.slug, label: c.label, start: +(i * SECONDS).toFixed(3), end: +((i + 1) * SECONDS).toFixed(3),
  })),
}, null, 2) + "\n");

if (process.env.CLEAN === "1") rmSync(TMP, { recursive: true, force: true });
console.log("reel built");
