"""Render the week's two covers and record them on the issue.

  cover-NNN.jpg        the gradient mesh with the issue's name (Spotify)
  cover-NNN-plain.jpg  the same mesh without text (site list view)

Inputs: the issue's name, its extracted palette (engine.cover.palette) and
the recipe saved from the cover lab (site/cover-recipe.json; the renderer's
defaults when absent). Rendering is the site's own canvas code run headless
(render.mjs), so what you tuned in the lab is exactly what ships. Records
companion_playlist.cover_art on the issue (issues/ and the site copy).

Run:  PYTHONPATH=<root> python3 -m engine.cover.render --n 2
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ..lib.config import PROJECT_ROOT, load_config

NEUTRAL = ["#1a1a1a", "#6e6e6e", "#c9c9c9", "#f4f4f4"]


def display_title(issue):
    t = issue.get("title") or f"Issue {issue.get('issue', 0):03d}"
    return t.split(": ", 1)[1] if ": " in t else t


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--size", type=int, default=640)
    args = ap.parse_args(argv)
    cfg = load_config()
    name = f"issue-{args.n:03d}.json"
    src = Path(cfg["ISSUES_DIR"]) / name
    if not src.exists():
        raise SystemExit(f"{src} not found")
    node = shutil.which("node")
    if not node:
        print("cover render: node not found; skipping")
        return 0
    issue = json.loads(src.read_text())
    site_dir = Path(cfg["SITE_ISSUES_DIR"])
    pal_p = site_dir / f"palette-{args.n:03d}.json"
    palette = NEUTRAL
    if pal_p.exists():
        try:
            colors = json.loads(pal_p.read_text()).get("colors") or []
            palette = colors if colors else NEUTRAL
        except Exception:
            pass
    recipe = {}
    rec_p = PROJECT_ROOT / "site" / "cover-recipe.json"
    source = "week"
    if rec_p.exists():
        try:
            doc = json.loads(rec_p.read_text())
            recipe = doc.get("recipe") or {}
            source = doc.get("source") or "week"
            if source == "custom" and doc.get("custom"):
                palette = doc["custom"]
        except Exception:
            pass
    out_text = site_dir / f"cover-{args.n:03d}.jpg"
    out_plain = site_dir / f"cover-{args.n:03d}-plain.jpg"
    cmd = [node, str(Path(__file__).with_name("render.mjs")),
           "--name", display_title(issue), "--issue", str(args.n),
           "--palette", ",".join(palette), "--recipe", json.dumps(recipe),
           "--size", str(args.size), "--out-text", str(out_text), "--out-plain", str(out_plain)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        print("cover render failed:", (res.stderr or res.stdout).strip()[:600])
        return 1
    info = json.loads(res.stdout.strip().splitlines()[-1])
    rel = {"text": f"/issues/{out_text.name}", "plain": f"/issues/{out_plain.name}",
           "palette": palette, "recipe_source": source}
    for p in (src, site_dir / name):
        d = json.loads(p.read_text())
        d.setdefault("companion_playlist", {})["cover_art"] = rel
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print(f"cover {args.n:03d}: {out_text.name} {info['text']['bytes']//1024} KB (q{info['text']['quality']}), "
          f"{out_plain.name} {info['plain']['bytes']//1024} KB; recorded on the issue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
