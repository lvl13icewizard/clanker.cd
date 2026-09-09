// The weekly cover: a gradient mesh built from the issue's own palette, a
// little grain, and the issue's name. One renderer for the cover lab (live
// preview, export) and for the weekly engine step (headless render) so the
// site and Spotify always show the same image. Deterministic: the same
// issue number + recipe seed always draws the same picture.

export const DEFAULT_RECIPE = {
  colors: 4,        // palette colours used (2-4)
  blobSize: 0.62,   // radius of each colour field, as a share of the side
  blur: 40,         // px of softening on a 640px canvas (scales with size)
  grain: 0.16,      // 0-1 film grain strength
  saturation: 1.08, // mesh saturation lift
  vignette: 0.16,   // 0-1 darkened edges
  seed: 1,          // reshuffles positions without changing the palette
  textSize: 0.105,  // name size as a share of the side
  textTone: "auto", // auto | ink | paper
  showIssue: true,  // small "Issue 002" line above the name
  namePos: "bottom",// bottom | center
};

export const NEUTRAL_PALETTE = ["#1a1a1a", "#6e6e6e", "#c9c9c9", "#f4f4f4"];

export function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hexToRgb(hex) {
  const h = String(hex).replace("#", "");
  const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const rgba = (hex, a) => { const [r, g, b] = hexToRgb(hex); return `rgba(${r},${g},${b},${a})`; };
const lum = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

function wrapName(ctx, text, maxWidth) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = "";
  for (const w of words) {
    const t = cur ? cur + " " + w : w;
    if (ctx.measureText(t).width <= maxWidth || !cur) cur = t;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 3);
}

/** Draw the cover onto `canvas` at `size` px square. Returns the tone used.
 *  `plain: true` (or recipe.plain) draws the mesh only, no name: the variant
 *  the site uses where the title already sits beside the image. */
export function renderCover(canvas, { name, issue, palette, recipe, size = 640, plain = false }) {
  const r = { ...DEFAULT_RECIPE, ...(recipe || {}) };
  const noText = plain || r.plain === true;
  const pal = (palette && palette.length ? palette : NEUTRAL_PALETTE).slice(0, Math.max(2, Math.min(4, r.colors)));
  while (pal.length < 2) pal.push(pal[0] || NEUTRAL_PALETTE[0]);
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext("2d");
  const k = size / 640;
  const rnd = mulberry32(((issue || 0) * 7919 + (r.seed | 0) * 131 + 17) >>> 0);

  // ground: the darkest palette colour, slightly lifted
  const ground = [...pal].sort((a, b) => lum(hexToRgb(a)) - lum(hexToRgb(b)))[0];
  ctx.fillStyle = ground; ctx.fillRect(0, 0, size, size);

  // colour fields, two per colour, softened
  ctx.save();
  ctx.filter = `blur(${Math.round(r.blur * k)}px) saturate(${r.saturation})`;
  const order = [...pal];
  for (let pass = 0; pass < 2; pass++) {
    for (const c of order) {
      const x = (0.1 + rnd() * 0.8) * size, y = (0.1 + rnd() * 0.8) * size;
      const rad = size * r.blobSize * (0.55 + rnd() * 0.7);
      const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
      g.addColorStop(0, rgba(c, 0.95));
      g.addColorStop(0.55, rgba(c, 0.55));
      g.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.restore();

  // vignette
  if (r.vignette > 0) {
    const v = ctx.createRadialGradient(size / 2, size / 2, size * 0.35, size / 2, size / 2, size * 0.78);
    v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, `rgba(0,0,0,${r.vignette})`);
    ctx.fillStyle = v; ctx.fillRect(0, 0, size, size);
  }

  // grain
  if (r.grain > 0) {
    const g = document.createElement("canvas"); g.width = size; g.height = size;
    const gctx = g.getContext("2d");
    const img = gctx.createImageData(size, size);
    const d = img.data;
    const grnd = mulberry32(((issue || 0) * 31 + (r.seed | 0) * 7 + 3) >>> 0);
    for (let i = 0; i < d.length; i += 4) {
      const n = 128 + (grnd() - 0.5) * 255;
      d[i] = d[i + 1] = d[i + 2] = n; d[i + 3] = 255;
    }
    gctx.putImageData(img, 0, 0);
    ctx.save();
    ctx.globalCompositeOperation = "overlay";
    ctx.globalAlpha = Math.min(1, r.grain * 0.9);
    ctx.drawImage(g, 0, 0);
    ctx.restore();
  }

  if (noText) return "none";

  // text tone: sample where the name will sit
  const pad = size * 0.08;
  const nameSize = Math.round(size * r.textSize);
  let tone = r.textTone;
  if (tone === "auto") {
    const sx = Math.round(pad), sw = Math.round(size * 0.6);
    const sy = r.namePos === "center" ? Math.round(size * 0.4) : Math.round(size * 0.62);
    const sh = Math.round(size * 0.3);
    const px = ctx.getImageData(sx, sy, sw, sh).data;
    let s = 0, n = 0;
    for (let i = 0; i < px.length; i += 16) { s += lum([px[i], px[i + 1], px[i + 2]]); n++; }
    tone = s / n > 0.58 ? "ink" : "paper";
  }
  const color = tone === "ink" ? "#0a0a0a" : "#ffffff";

  ctx.fillStyle = color;
  ctx.textBaseline = "alphabetic";
  ctx.font = `600 ${nameSize}px Figtree, "Helvetica Neue", Arial, sans-serif`;
  const lines = wrapName(ctx, name, size - pad * 2);
  const lh = nameSize * 1.04;
  const small = Math.round(size * 0.034);
  const block = lines.length * lh + (r.showIssue ? small * 1.9 : 0);
  let y = r.namePos === "center" ? (size - block) / 2 + (r.showIssue ? small * 1.6 : 0) + nameSize * 0.8
                                 : size - pad - (lines.length - 1) * lh;
  if (r.showIssue) {
    ctx.save();
    ctx.font = `500 ${small}px Figtree, "Helvetica Neue", Arial, sans-serif`;
    ctx.globalAlpha = 0.82;
    ctx.fillText(`Issue ${String(issue || 0).padStart(3, "0")}`, pad, y - (r.namePos === "center" ? nameSize * 0.8 + small * 0.6 : nameSize * 1.05));
    ctx.restore();
  }
  ctx.font = `600 ${nameSize}px Figtree, "Helvetica Neue", Arial, sans-serif`;
  lines.forEach((ln, i) => ctx.fillText(ln, pad, y + i * lh));
  return tone;
}
