"""Extract the week's palette from the issue's real cover art.

Every issue already carries the covers of its picks (cover_url, resolved by
engine.art). This reads them, quantizes the combined pixels, and writes the
six most characteristic colours to site/public/issues/palette-NNN.json so
the cover lab (and the weekly cover render) can build the gradient mesh out
of the music itself. Needs Pillow; without it, nothing is written and the
lab falls back to a neutral palette.

Run:  PYTHONPATH=<root> python3 -m engine.cover.palette --n 2
"""

import argparse
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

from ..lib.config import load_config

UA = {"User-Agent": "clanker-cd/0.1 (cover palette)"}


def _covers(issue):
    urls = []
    for m in issue.get("modules") or []:
        t = m.get("type")
        if t == "front_to_back" and isinstance(m.get("album"), dict):
            urls.append(m["album"].get("cover_url"))
        for key in ("tracks", "albums", "unheard"):
            for x in m.get(key) or []:
                urls.append(x.get("cover_url"))
    return [u for u in urls if u]


def _fetch(url, cache_dir):
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    p = cache_dir / f"{h}.img"
    if p.exists():
        return p.read_bytes()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read()
    p.write_bytes(data)
    return data


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in rgb)


def _sat(rgb):
    mx, mn = max(rgb), min(rgb)
    return 0.0 if mx == 0 else (mx - mn) / mx


def palette(issue, cache_dir, n_out=6):
    from PIL import Image  # optional dependency, only here
    tiles = []
    for u in _covers(issue):
        try:
            im = Image.open(io.BytesIO(_fetch(u, cache_dir))).convert("RGB").resize((40, 40))
            tiles.append(im)
        except Exception:
            continue
    if not tiles:
        return [], 0
    sheet = Image.new("RGB", (40 * len(tiles), 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, (40 * i, 0))
    q = sheet.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: 24 * 3]
    counts = sorted(q.getcolors(), reverse=True)  # (count, index)
    total = sum(c for c, _ in counts)
    scored = []
    for c, idx in counts:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        lum = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
        # frequency, lifted by saturation, and pulled away from near-black/white
        score = (c / total) * (0.35 + _sat(rgb)) * (0.4 + 0.6 * (1 - abs(lum - 0.5) * 1.6))
        scored.append((score, rgb))
    scored.sort(reverse=True)
    out = []
    for _, rgb in scored:
        if all(sum((a - b) ** 2 for a, b in zip(rgb, o)) ** 0.5 > 48 for o in out):
            out.append(rgb)
        if len(out) == n_out:
            break
    return [_hex(c) for c in out], len(tiles)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True)
    args = ap.parse_args(argv)
    cfg = load_config()
    src = Path(cfg["ISSUES_DIR"]) / f"issue-{args.n:03d}.json"
    if not src.exists():
        raise SystemExit(f"{src} not found")
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("palette: Pillow not installed; skipping (the lab uses a neutral palette)")
        return 0
    cache = Path(cfg["CACHE_DIR"]) / "covers"
    cache.mkdir(parents=True, exist_ok=True)
    issue = json.loads(src.read_text())
    colors, used = palette(issue, cache)
    out = Path(cfg["SITE_ISSUES_DIR"]) / f"palette-{args.n:03d}.json"
    out.write_text(json.dumps({"issue": args.n, "colors": colors, "covers": used}, indent=1) + "\n")
    print(f"palette {args.n:03d}: {' '.join(colors)} from {used} covers -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
