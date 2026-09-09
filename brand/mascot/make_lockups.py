"""Wordmarks and lockups for Clanker.CD, set in Figtree SemiBold.

Nothing generated: type is rendered from the variable Figtree face at
weight 600 (the site's own family), the mini disc comes from produce.py's
renderer, and the head mark is the produced transparent cut. Light (ink)
and dark (paper) variants of every piece.

Run:  python3 make_lockups.py    (after produce.py; writes out/lockups/)
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from produce import render_disc

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "lockups"
INK = (10, 10, 10, 255)
PAPER = (242, 242, 242, 255)
CAP = 200          # cap height target at working scale


def font(size):
    f = ImageFont.truetype(str(HERE / "Figtree.ttf"), size)
    f.set_variation_by_axes([600])
    return f


def text_img(s, fill, tracking=0):
    f = font(int(CAP * 1.35))
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    l, t, r, b = probe.textbbox((0, 0), s, font=f)
    im = Image.new("RGBA", (r - l + 40 + tracking * max(0, len(s) - 1), b - t + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if tracking:
        x = 20 - l
        for ch in s:
            d.text((x, 20 - t), ch, font=f, fill=fill)
            x += d.textlength(ch, font=f) + tracking
    else:
        d.text((20 - l, 20 - t), s, font=f, fill=fill)
    bbox = im.getchannel("A").getbbox()
    return im.crop(bbox)


def row(parts, gap, align="baseline", baselines=None):
    """Compose images left to right. With align='baseline', baselines gives
    each part's baseline offset from its own top; parts sit on one line."""
    if align == "baseline":
        base = max(baselines)
        h = base + max(im.height - bl for im, bl in zip(parts, baselines))
        w = sum(im.width for im in parts) + gap * (len(parts) - 1)
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = 0
        for im, bl in zip(parts, baselines):
            out.alpha_composite(im, (x, base - bl))
            x += im.width + gap
        return out
    h = max(im.height for im in parts)
    w = sum(im.width for im in parts) + gap * (len(parts) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for im in parts:
        out.alpha_composite(im, (x, (h - im.height) // 2))
        x += im.width + gap
    return out


def pad(im, p):
    out = Image.new("RGBA", (im.width + 2 * p, im.height + 2 * p), (0, 0, 0, 0))
    out.alpha_composite(im, (p, p))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pal = json.loads((HERE / "../../site/public/issues/palette-002.json").read_text())
    colors = pal.get("colors") or []

    for tone, fill in (("light", INK), ("dark", PAPER)):
        # plain wordmarks, both casings
        for s, slug in (("clanker.cd", "wordmark-lower"), ("Clanker.CD", "wordmark-cased")):
            pad(text_img(s, fill), 40).save(OUT / f"{slug}-{tone}.png")

        # the disc as the period: clanker ● cd  (the .cd family gesture)
        left = text_img("clanker", fill)
        right = text_img("cd", fill)
        disc = render_disc(int(CAP * 0.56), colors, seed=2)
        g = int(CAP * 0.10)
        mark = row([left, disc, right], g, align="baseline",
                   baselines=[left.height, disc.height - int(CAP * 0.02), right.height])
        pad(mark, 40).save(OUT / f"wordmark-disc-{tone}.png")

        # head + wordmark lockup
        head = Image.open(HERE / "out" / "clanker-head-mark-t.png").convert("RGBA")
        hh = int(CAP * 1.7)
        head = head.resize((int(head.width * hh / head.height), hh), Image.LANCZOS)
        if tone == "dark":
            # the ink features sit on the off-white head, so the art works on
            # dark as-is; nothing to recolor.
            pass
        lock = row([head, text_img("clanker.cd", fill)], int(CAP * 0.34), align="center")
        pad(lock, 40).save(OUT / f"lockup-head-{tone}.png")
    print("lockups written:", len(list(OUT.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
