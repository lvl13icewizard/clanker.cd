"""Production pass over the chosen clanker assets.

Everything deterministic, PIL only:
  1. Background removal by edge flood (the generated background is ~254;
     the character's off-white is ~246, so only border-connected near-white
     is cleared and the head keeps its fill).
  2. Favicon set from the head mark, with an ink keyline grown around the
     silhouette so the off-white head reads on white tabs and dark ones.
  3. The live disc: the generated disc in the hero and the avatar is
     replaced with a disc drawn from a real issue palette in the site's
     cover language (seeded mesh + grain), so the mascot holds the actual
     week's pressing. Dark ink (outline, fingers) inside the disc circle is
     preserved; only the disc surface repaints.

Run:  python3 produce.py [--palette ../../site/public/issues/palette-002.json]  (run from brand/mascot/) [--seed 2]
Outputs land in out/.
"""

import argparse
import json
import re
import math
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
BG_MIN = 250          # border-connected pixels at or above this go transparent
INK = (10, 10, 10, 255)

ASSETS = ["clanker-hero", "clanker-head-mark", "clanker-head-pixel",
          "clanker-avatar-peek", "clanker-circle-badge", "clanker-pose-sheet",
          "clanker-greeter"]

# The home page's rotation: any of these that exist ship to the site with
# the weekly disc composited in (poses without a disc pass through) and
# their eye boxes measured, so the page can blink them.
POSES = [("hero", "clanker-hero"), ("greeter", "clanker-greeter"),
         ("listen", "clanker-pose-listen"), ("spin", "clanker-pose-spin"),
         ("present", "clanker-pose-present"), ("strut", "clanker-pose-strut")]


def flood_transparent(im):
    """RGBA copy with border-connected near-white cleared."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()

    def bgish(x, y):
        r, g, b, a = px[x, y]
        return r >= BG_MIN and g >= BG_MIN and b >= BG_MIN

    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bgish(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if bgish(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                q.append((x, y))
    while q:
        x, y = q.popleft()
        px[x, y] = (255, 255, 255, 0)
        for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and bgish(nx, ny):
                seen[ny * w + nx] = 1
                q.append((nx, ny))
    # Enclosed pockets: background trapped inside the silhouette (between a
    # head and a raised arm) never connects to the border, so the flood
    # missed it. But several poses also DRAW near-white — sticker outline
    # strokes, bright panel slots — so only components that border the
    # off-white head or the coloured disc count as pockets; regions bordered
    # purely by ink are drawn features and stay.
    seenp = bytearray(w * h)
    for y0 in range(h):
        for x0 in range(w):
            if seenp[y0 * w + x0] or px[x0, y0][3] == 0 or not bgish(x0, y0):
                continue
            q = deque([(x0, y0)])
            seenp[y0 * w + x0] = 1
            comp = []
            touch_soft = touch_all = 0
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    if not seenp[ny * w + nx] and px[nx, ny][3] > 0 and bgish(nx, ny):
                        seenp[ny * w + nx] = 1
                        q.append((nx, ny))
                    elif px[nx, ny][3] > 0 and not bgish(nx, ny):
                        r2, g2, b2, a2 = px[nx, ny]
                        m = (r2 + g2 + b2) / 3
                        touch_all += 1
                        if 236 <= m < 250 or max(r2, g2, b2) - min(r2, g2, b2) > 25:
                            touch_soft += 1
            if len(comp) > 200 and touch_all and touch_soft / touch_all > 0.04:
                for x, y in comp:
                    px[x, y] = (255, 255, 255, 0)
    # Defringe: near-white pixels touching transparency are the background's
    # anti-aliased halo; erosion passes clear them without touching the
    # off-white fills, which sit behind darker edges.
    for _ in range(4):
        edge = []
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0 or (r + g + b) / 3 < 230:
                    continue
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] == 0:
                        edge.append((x, y))
                        break
        for x, y in edge:
            px[x, y] = (255, 255, 255, 0)
    # Keep only the largest connected piece: noisy generations leave pale
    # debris islands the flood cannot reach from the border.
    seen2 = bytearray(w * h)
    comps = []
    for y0 in range(h):
        for x0 in range(w):
            if seen2[y0 * w + x0] or px[x0, y0][3] == 0:
                continue
            q2 = deque([(x0, y0)])
            seen2[y0 * w + x0] = 1
            comp = []
            while q2:
                x, y = q2.popleft()
                comp.append((x, y))
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen2[ny * w + nx] and px[nx, ny][3] > 0:
                        seen2[ny * w + nx] = 1
                        q2.append((nx, ny))
            comps.append(comp)
    if comps:
        comps.sort(key=len, reverse=True)
        for comp in comps[1:]:
            for x, y in comp:
                px[x, y] = (255, 255, 255, 0)
    # Soften: a gentle blur on the alpha alone rounds the binary edge into
    # real anti-aliasing; the colours underneath are true by now, so the
    # soft ring reads as the character's own edge on any ground.
    alpha = rgba.getchannel("A").filter(ImageFilter.GaussianBlur(1.1))
    rgba.putalpha(alpha)
    return rgba


def trim(rgba, pad_frac=0.05):
    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        return rgba
    l, t, r, b = bbox
    pad = int(max(r - l, b - t) * pad_frac)
    l = max(0, l - pad); t = max(0, t - pad)
    r = min(rgba.width, r + pad); b = min(rgba.height, b + pad)
    return rgba.crop((l, t, r, b))


def keyline(rgba, grow, color=INK):
    """The silhouette grown by `grow` px in `color`, composited underneath."""
    a = rgba.getchannel("A")
    fat = a.filter(ImageFilter.MaxFilter(2 * grow + 1))
    under = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    under.paste(Image.new("RGBA", rgba.size, color), (0, 0), fat)
    return Image.alpha_composite(under, rgba)


# ---- the live disc ------------------------------------------------------

def mulberry(seed):
    a = seed & 0xFFFFFFFF
    def rand():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rand


def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def render_disc(diam, palette, seed=1):
    """A disc in the site's cover language: seeded soft mesh + grain,
    off-white centre hole with a grey ring. Returns RGBA of size diam."""
    S = 4  # supersample
    D = diam * S
    rand = mulberry(seed * 2654435761 & 0xFFFFFFFF or 1)
    cols = [hex_rgb(c) for c in palette][:6] or [(110, 110, 110)]
    cols.sort(key=lambda c: -(c[0] + c[1] + c[2]))
    cols = cols[:4] or cols
    cols = [tuple(int(v * 0.72 + 255 * 0.28) for v in c) for c in cols]
    base = cols[len(cols) // 2]
    im = Image.new("RGB", (D, D), base)
    dr = ImageDraw.Draw(im)
    for i, c in enumerate(cols * 2):
        cx, cy = rand() * D, rand() * D
        r = D * (0.28 + rand() * 0.34)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    im = im.filter(ImageFilter.GaussianBlur(D * 0.16))
    from PIL import ImageEnhance
    im = ImageEnhance.Brightness(im).enhance(1.12)
    noise = Image.effect_noise((D, D), 34).convert("L")
    im = Image.composite(Image.new("RGB", (D, D), (255, 255, 255)), im,
                         noise.point(lambda v: int(max(0, v - 208) * 0.9)))
    im = Image.composite(Image.new("RGB", (D, D), (12, 12, 12)), im,
                         noise.point(lambda v: int(max(0, 40 - v) * 0.9)))
    if diam < 90:
        # tiny discs (the wordmark period) go murky: lift them
        from PIL import ImageEnhance
        im = ImageEnhance.Brightness(im).enhance(1.3)
        im = ImageEnhance.Color(im).enhance(1.15)
    rgba = im.convert("RGBA")
    mask = Image.new("L", (D, D), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, D - 1, D - 1], fill=255)
    rgba.putalpha(mask)
    # centre hole: off-white fill, thin grey ring, CD proportions
    hole = D * 0.085
    ring = D * 0.012
    dr = ImageDraw.Draw(rgba)
    c0 = (D - 1) / 2
    dr.ellipse([c0 - hole - ring, c0 - hole - ring, c0 + hole + ring, c0 + hole + ring],
               fill=(158, 158, 158, 255))
    dr.ellipse([c0 - hole, c0 - hole, c0 + hole, c0 + hole], fill=(246, 246, 245, 255))
    return rgba.resize((diam, diam), Image.LANCZOS)


def render_mesh(w, h, palette, seed):
    """A soft mesh field in the cover language, sized to cover a region."""
    S = 2
    W, H = w * S, h * S
    rand = mulberry(seed * 2654435761 & 0xFFFFFFFF or 1)
    cols = [hex_rgb(c) for c in palette][:6] or [(110, 110, 110)]
    # the covers' register is soft: favour the lighter colours and mix
    # everything toward white so the disc reads pastel, not moody
    cols.sort(key=lambda c: -(c[0] + c[1] + c[2]))
    cols = cols[:4] or cols
    cols = [tuple(int(v * 0.72 + 255 * 0.28) for v in c) for c in cols]
    base = tuple(min(255, int(v * 0.35 + 244 * 0.65)) for v in cols[0])
    im = Image.new("RGB", (W, H), base)
    dr = ImageDraw.Draw(im)
    for c in cols * 2:
        cx, cy = rand() * W, rand() * H
        r = max(W, H) * (0.24 + rand() * 0.3)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    im = im.filter(ImageFilter.GaussianBlur(max(W, H) * 0.17))
    from PIL import ImageEnhance
    im = ImageEnhance.Brightness(im).enhance(1.14)
    noise = Image.effect_noise((W, H), 34).convert("L")
    im = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)), im,
                         noise.point(lambda v: int(max(0, v - 208) * 0.9)))
    return im.resize((w, h), Image.LANCZOS)


def detect_eyes(rgba):
    """The two round ink eye blobs in the head zone, as boxes normalised to
    the image size, or None. Eyes are dark, round, sit on the light head
    (their surrounding ring is opaque off-white), and come as a symmetric
    pair of similar size; grey furniture and merged features fail one of
    those tests. Thresholds adapt because earlier generations render the
    eyes as soft dark grey rather than true ink."""
    w, h = rgba.size
    px = rgba.load()
    top = int(h * 0.55)

    def blobs_at(t):
        seen = bytearray(w * top)
        out = []
        for y0 in range(top):
            for x0 in range(w):
                if seen[y0 * w + x0]:
                    continue
                r, g, b, a = px[x0, y0]
                if a == 0 or (r + g + b) / 3 >= t:
                    continue
                q = deque([(x0, y0)])
                seen[y0 * w + x0] = 1
                pts = []
                while q:
                    x, y = q.popleft()
                    pts.append((x, y))
                    for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                        if 0 <= nx < w and 0 <= ny < top and not seen[ny * w + nx]:
                            r2, g2, b2, a2 = px[nx, ny]
                            if a2 > 0 and (r2 + g2 + b2) / 3 < t:
                                seen[ny * w + nx] = 1
                                q.append((nx, ny))
                if not (w * h * 0.00006 < len(pts) < w * h * 0.008):
                    continue
                xs = [p2[0] for p2 in pts]; ys = [p2[1] for p2 in pts]
                bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
                if not (0.55 <= bw / bh <= 1.7):
                    continue
                if len(pts) / (bw * bh) < 0.55:
                    continue
                # the ring around an eye is the light head, not background
                bx, by = min(xs), min(ys)
                ring_ok = ring_all = 0
                pad = max(3, bw // 4)
                for y in range(max(0, by - pad), min(h, by + bh + pad)):
                    for x in range(max(0, bx - pad), min(w, bx + bw + pad)):
                        if bx <= x < bx + bw and by <= y < by + bh:
                            continue
                        ring_all += 1
                        r3, g3, b3, a3 = px[x, y]
                        if a3 > 0 and (r3 + g3 + b3) / 3 >= 190:
                            ring_ok += 1
                if ring_all and ring_ok / ring_all < 0.6:
                    continue
                out.append((bx, by, bw, bh, len(pts)))
        return out

    for t in (80, 95, 110):
        blobs = blobs_at(t)
        best = None
        for i in range(len(blobs)):
            for j in range(i + 1, len(blobs)):
                a1, b1 = blobs[i], blobs[j]
                if abs(a1[1] - b1[1]) > h * 0.025:
                    continue
                if not (w * 0.04 < abs(a1[0] - b1[0]) < w * 0.4):
                    continue
                big, small = max(a1[4], b1[4]), min(a1[4], b1[4])
                if big / small > 1.7:
                    continue
                score = abs(a1[1] - b1[1]) + abs(a1[4] - b1[4]) / big * 10
                if best is None or score < best[0]:
                    best = (score, (a1, b1) if a1[0] < b1[0] else (b1, a1))
        if best:
            return [{"x": round(bx / w, 4), "y": round(by / h, 4),
                     "w": round(bw / w, 4), "h": round(bh / h, 4)}
                    for bx, by, bw, bh, _n in best[1]]
    return None


def _fit_circle(points):
    """Kasa least-squares circle fit; returns (cx, cy, r)."""
    n = len(points)
    Sx = sum(p[0] for p in points); Sy = sum(p[1] for p in points)
    Sxx = sum(p[0] * p[0] for p in points); Syy = sum(p[1] * p[1] for p in points)
    Sxy = sum(p[0] * p[1] for p in points)
    Sxz = sum(p[0] * (p[0] * p[0] + p[1] * p[1]) for p in points)
    Syz = sum(p[1] * (p[0] * p[0] + p[1] * p[1]) for p in points)
    Sz = sum(p[0] * p[0] + p[1] * p[1] for p in points)
    # normal equations for x^2+y^2 + D x + E y + F = 0
    A = [[Sxx, Sxy, Sx], [Sxy, Syy, Sy], [Sx, Sy, n]]
    b = [-Sxz, -Syz, -Sz]
    det = (A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1])
           - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0])
           + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]))
    if abs(det) < 1e-9:
        return None
    def rep(col):
        M = [row[:] for row in A]
        for i in range(3):
            M[i][col] = b[i]
        return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
                - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
                + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
    D, E, F = rep(0) / det, rep(1) / det, rep(2) / det
    cx, cy = -D / 2, -E / 2
    r2 = cx * cx + cy * cy - F
    if r2 <= 0:
        return None
    return cx, cy, r2 ** 0.5


# Alpha at or below this is background, not artwork: flood_transparent's
# closing blur means the cut is a ramp, not a step.
BG_ALPHA = 40


def relive(rgba, palette, seed):
    """Repaint the disc in place. Geometry comes from the disc's own drawn
    ink rim: ink pixels that touch colour are rim samples, a least-squares
    circle fit (with one outlier-rejection pass) recovers the exact centre
    and radius, and everything inside is repainted except drawn ink (rim,
    fingers) and the white features (hole, glints), which stay untouched."""
    w, h = rgba.size
    px = rgba.load()

    def lum(x, y):
        r, g, b, a = px[x, y]
        return (r + g + b) / 3 if a else 255

    def satat(x, y):
        r, g, b, a = px[x, y]
        return max(r, g, b) - min(r, g, b) if a else 0

    # The disc's edge: colourful pixels that touch the removed background
    # (its outer arc), plus colourful pixels that touch ink (the gripped
    # arc). Nothing else on the character is saturated, so these samples
    # trace only the disc.
    #
    # "Touches the background" cannot mean alpha exactly 0. flood_transparent
    # ends by blurring the alpha channel to soften the cut, which leaves a
    # two-pixel ramp around every edge, so nothing beside the disc reads 0 any
    # more. That silently cost the fit its rim: 41 samples on the hero where
    # it needs 60, and none at all on spin. Anything this faint is background.
    rim = []
    sat_total = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if satat(x, y) <= 30:
                continue
            sat_total += 1
            edge = False
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if px[nx, ny][3] < BG_ALPHA or lum(nx, ny) < 80:
                    edge = True
                    break
            if edge:
                rim.append((x, y))
    # A pose can simply not be holding a disc: the headphones one has no
    # colour on it anywhere. That is not a failed fit, it is nothing to fit,
    # and the pose passes through whole.
    if sat_total < 200:
        print("  no disc — passed through")
        return rgba, True
    if len(rim) < 60:
        print("  no rim found — skipped")
        return rgba, False
    # Keep only the outermost sample per direction: a gripped disc also
    # yields colour-meets-ink samples along the fingers INSIDE the face,
    # and those drag the fit inward, leaving a ring of the old disc.
    cx0 = sum(p2[0] for p2 in rim) / len(rim)
    cy0 = sum(p2[1] for p2 in rim) / len(rim)
    import math
    hull = {}
    for x, y in rim:
        # 3-degree buckets. At 6 the discs held up (spin) or across the body
        # (present) only ever filled 22 and 15 of the 24 the fit demands: the
        # arc they show is short, so the buckets have to be fine enough to
        # sample it. The outlier pass after the fit drops anything this lets
        # through from the fingers.
        ang = int(math.atan2(y - cy0, x - cx0) / math.pi * 60)
        d2 = (x - cx0) ** 2 + (y - cy0) ** 2
        if ang not in hull or d2 > hull[ang][0]:
            hull[ang] = (d2, (x, y))
    rim = [v[1] for v in hull.values()]
    if len(rim) < 24:
        print("  rim too sparse — skipped")
        return rgba, False
    fit = _fit_circle(rim)
    if not fit:
        print("  circle fit failed — skipped")
        return rgba, False
    cx, cy, r = fit
    # Two passes of one-sided trimming. A hand across the face (present,
    # strut) yields colour-meets-ink samples INSIDE the true circle, never
    # outside, so the first fit lands small and the real rim sits outside it
    # with positive residual. The old symmetric trim kept those fingers and
    # painted a disc a few pixels short of its own edge, leaving a grey ring
    # of the old surface showing. Drop only the inward samples and refit.
    pts = list(rim)
    for _ in range(2):
        res = [((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - r for x, y in pts]
        tol = max(4.0, sorted(abs(e) for e in res)[len(res) // 2] * 2.5)
        kept_pts = [p2 for p2, e in zip(pts, res) if e >= -tol]
        if len(kept_pts) < 24 or len(kept_pts) == len(pts):
            break
        f2 = _fit_circle(kept_pts)
        if not f2:
            break
        cx, cy, r = f2
        pts = kept_pts
    print(f"  rim {len(rim)} samples -> circle ({cx:.0f}, {cy:.0f}) r {r:.0f}")

    # The repaint covers the whole surface the ink encloses, found by flooding
    # out from the centre and stopping at ink or background. A circle of the
    # fitted radius is not enough: the drawn disc carries an outer iridescent
    # ring, silver-grey along part of its run, and grey has no saturation, so
    # that band never yields rim samples and the fit lands on the inner face.
    # Painting to the fitted radius then stops short of the ring and leaves
    # the old surface showing as a pale band (present, strut). The flood is
    # capped at 1.35 r so a gap in the outline cannot leak it into the body.
    def ink(x, y):
        rr, gg, bb, aa = px[x, y]
        return aa <= BG_ALPHA or ((rr + gg + bb) / 3 < 80 and max(rr, gg, bb) - min(rr, gg, bb) < 40)
    seed_pt = None
    for ring in range(0, 14):          # the centre is the hole; if a hand
        for dy in range(-ring, ring + 1):  # covers it, start just beside it
            for dx in range(-ring, ring + 1):
                sx, sy = int(round(cx)) + dx, int(round(cy)) + dy
                if 0 <= sx < w and 0 <= sy < h and not ink(sx, sy):
                    seed_pt = (sx, sy); break
            if seed_pt: break
        if seed_pt: break
    if not seed_pt:
        print("  disc centre is covered — skipped")
        return rgba, False
    cap2 = (r * 1.35) ** 2
    seen = {seed_pt}
    q = deque([seed_pt])
    inside = []
    while q:
        x, y = q.popleft()
        inside.append((x, y))
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) in seen or not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx - cx) ** 2 + (ny - cy) ** 2 > cap2 or ink(nx, ny):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    if len(inside) < 200:
        print("  disc surface not found from the centre — skipped")
        return rgba, False
    xs = [p2[0] for p2 in inside]
    ys = [p2[1] for p2 in inside]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    rin = max((x1 - x0), (y1 - y0)) / 2   # for the log line
    # white features (hole, glints): connected near-white blobs, grown 2px
    white = {(x, y) for x, y in inside if lum(x, y) >= 225}
    keep = set()
    left = set(white)
    while left:
        s0 = left.pop()
        q2 = deque([s0]); blob2 = [s0]
        while q2:
            x, y = q2.popleft()
            for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if (nx, ny) in left:
                    left.discard((nx, ny)); q2.append((nx, ny)); blob2.append((nx, ny))
        if len(blob2) >= 40:
            keep.update(blob2)
    inset = set(inside)
    for _ in range(2):
        keep |= {(x + dx, y + dy) for x, y in keep
                 for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)) if (x + dx, y + dy) in inset}

    mesh = render_mesh(x1 - x0 + 1, y1 - y0 + 1, palette, seed)
    mpx = mesh.load()
    out = rgba.copy()
    opx = out.load()
    painted = 0
    for x, y in inside:
        if (x, y) in keep or lum(x, y) < 80:
            continue
        nr, ng, nb = mpx[x - x0, y - y0]
        opx[x, y] = (nr, ng, nb, px[x, y][3])
        painted += 1
    print(f"  repainted {painted} px inside r {rin:.0f}, kept {len(keep)} white px + ink")
    return out, True


def main():
    ap = argparse.ArgumentParser()
    # The brand assets ship with the STANDARD disc, not a real issue's: the
    # public site should look the same every week. Pass a palette-NNN.json to
    # build a live set for the personal app.
    ap.add_argument("--palette", default=str(HERE / "brand-disc.json"))
    ap.add_argument("--seed", type=int, default=2, help="drives the standard disc's mesh")
    # The personal app's robots hold the week's disc, repainted from the
    # issue's own cover palette. The press rebuilds just that set.
    ap.add_argument("--live-palette", default=None,
                    help="palette-NNN.json for the live set; default the newest in site/public/issues")
    ap.add_argument("--live-only", action="store_true",
                    help="rebuild only the live set (what weekly.sh runs)")
    args = ap.parse_args()
    pal = json.loads(Path(args.palette).read_text())
    colors = pal.get("colors") or pal.get("palette") or []
    OUT.mkdir(exist_ok=True)

    cut = {}
    issues = HERE / "../../site/public/issues"
    live_pal = args.live_palette
    if live_pal is None:
        found = sorted(issues.glob("palette-*.json"))
        live_pal = str(found[-1]) if found else None

    if args.live_only:
        if not live_pal:
            raise SystemExit("no palette for the live set")
        live_colors = json.loads(Path(live_pal).read_text()).get("colors") or []
        m = re.search(r"palette-(\d+)", Path(live_pal).name)
        live_seed = int(m.group(1)) if m else 1
        n = emit_poses(HERE / "../../site/public/brand/live", "/brand/live",
                       live_colors, live_seed, cut)
        print(f"live set: {n} poses from {Path(live_pal).name}, seed {live_seed}")
        raise SystemExit(0)

    for name in ASSETS:
        rgba = trim(flood_transparent(Image.open(HERE / f"{name}.png")))
        rgba.save(OUT / f"{name}-t.png")
        cut[name] = rgba
        print(f"{name}: transparent {rgba.size}")

    # favicon set from the head mark, keyline so it reads on any ground
    head = cut["clanker-head-mark"]
    sq = Image.new("RGBA", (max(head.size),) * 2, (0, 0, 0, 0))
    sq.paste(head, ((sq.width - head.width) // 2, (sq.height - head.height) // 2))
    lined = keyline(sq, max(2, sq.width // 96))
    for size in (512, 180, 32, 16):
        lined.resize((size, size), Image.LANCZOS).save(OUT / f"favicon-{size}.png")
    print("favicon set: 512 180 32 16 (ink keyline)")

    # The live disc, hero only. The avatar's disc is part-occluded and its
    # sandy mid-tones fall below the saturation threshold, so the circle
    # fit fractures; as a static social avatar it keeps its baked gradient.
    live, ok = relive(cut["clanker-hero"], colors, args.seed)
    if ok:
        live.save(OUT / "clanker-hero-live.png")
        print(f"clanker-hero: live disc composited (issue palette, seed {args.seed})")

    # The standard set: the public site's robots, holding the brand disc.
    # One asset serves both themes: dark mode lifts the silhouette with a
    # CSS glow that follows the true alpha contour, so there is no keylined
    # dark variant to bridge the gaps between limbs.
    brand = HERE / "../../site/public/brand"
    brand.mkdir(exist_ok=True)
    lined.resize((96, 96), Image.LANCZOS).save(brand / "head-96.png")
    n = emit_poses(brand, "/brand", colors, args.seed, cut, hero_copy=True)
    print(f"standard set: head-96 + {n} poses (brand disc, seed {args.seed})")

    if live_pal:
        live_colors = json.loads(Path(live_pal).read_text()).get("colors") or []
        m = re.search(r"palette-(\d+)", Path(live_pal).name)
        live_seed = int(m.group(1)) if m else 1
        n = emit_poses(brand / "live", "/brand/live", live_colors, live_seed, cut)
        print(f"live set: {n} poses from {Path(live_pal).name}, seed {live_seed}")
    print(f"web brand assets: head-96 + {len(manifest)} poses "
          f"({sum(1 for m in manifest if m['eyes'])} with blinkable eyes)")
    return 0


def emit_poses(out_dir, prefix, colors, seed, cut, hero_copy=False):
    """Write the pose rotation for one disc palette: pose-*.png plus the
    poses.json manifest the site reads, with each pose's eye boxes measured
    so the page can blink them. A pose whose disc did not repaint still
    carries the source art's own gradient, which on the page reads as one
    robot holding a different record from the rest, so it does not ship."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for slug, src in POSES:
        sp = HERE / f"{src}.png"
        if not sp.exists():
            continue
        rgba = cut.get(src) or trim(flood_transparent(Image.open(sp)))
        live2, ok2 = relive(rgba, colors, seed)
        if not ok2:
            print(f"  DROPPED pose {slug}: disc did not repaint, would ship the baked gradient")
            continue
        eyes = detect_eyes(live2)
        web = live2.resize((480, int(live2.height * 480 / live2.width)), Image.LANCZOS)
        web.save(out_dir / f"pose-{slug}.png")
        manifest.append({"slug": slug, "file": f"{prefix}/pose-{slug}.png",
                         "w": web.width, "h": web.height, "eyes": eyes})
        if slug == "hero" and hero_copy:
            web.save(out_dir / "clanker-hero.png")   # stable fallback path
    (out_dir / "poses.json").write_text(json.dumps({"poses": manifest}, indent=1) + "\n")
    return len(manifest)


if __name__ == "__main__":
    sys.exit(main())
