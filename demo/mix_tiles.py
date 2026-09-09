"""Generated tiles for demo radio shows.

Real NTS shows resolve to their real picture (demo/art.py). The rest are
programmes whose episode artwork cannot be looked up keylessly, so rather
than leaving a reader with a column of unavailable tiles, each show gets a
tile in the persona's own hand: the same canvas renderer as the issue
covers, the persona's palette, the show's name set on it. It reads as house
artwork, never as a station's logo.

Run:  python3 demo/mix_tiles.py            (every persona)
      python3 demo/mix_tiles.py --slug pop
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from demo.build_demo import DEFAULT_RECIPE, RECIPES  # noqa: E402

DEMO = ROOT / "site" / "public" / "demo"
CATALOGS = ROOT / "demo" / "catalogs"


def key_for(show):
    return hashlib.sha1(show.strip().lower().encode()).hexdigest()[:10]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug")
    args = ap.parse_args(argv)
    node = shutil.which("node")
    if not node:
        print("node not found; cannot render tiles")
        return 1
    slugs = ([args.slug] if args.slug
             else sorted(p.name for p in DEMO.iterdir()
                         if p.is_dir() and (p / "index.json").exists()))
    jobs, plans = [], []
    for slug in slugs:
        cat = json.loads((CATALOGS / f"{slug}.json").read_text())
        recipe = dict(RECIPES.get(slug, DEFAULT_RECIPE))
        # A station tile is not an issue cover: more grain, smaller name.
        recipe.update({"grain": min(0.32, recipe.get("grain", 0.16) + 0.1)})
        out = DEMO / slug
        want = {}
        for p in sorted(out.glob("issue-*.json")):
            d = json.loads(p.read_text())
            for m in d["modules"]:
                if m.get("type") != "the_mix":
                    continue
                for x in m.get("mixes") or []:
                    if x.get("cover_url"):
                        continue
                    show = x.get("show") or ""
                    k = key_for(show)
                    want.setdefault(k, show)
                    x["cover_url"] = f"/demo/{slug}/mix-{k}.jpg"
            plans.append((p, d))
        for i, (k, show) in enumerate(sorted(want.items())):
            r = dict(recipe)
            r["seed"] = 1000 + i
            jobs.append({"name": show, "issue": 0, "palette": cat["palette"],
                         "recipe": r, "outPlain": str(out / f"mix-{k}.jpg")})
        print(f"{slug}: {len(want)} show tile(s)")
    if not jobs:
        print("nothing to render; every mix already has artwork")
        return 0
    tmp = ROOT / "demo" / ".cover-jobs.json"
    tmp.write_text(json.dumps(jobs))
    try:
        res = subprocess.run([node, str(ROOT / "demo" / "render_covers.mjs"), str(tmp)],
                             capture_output=True, text=True, timeout=600)
    finally:
        tmp.unlink(missing_ok=True)
    if res.returncode != 0:
        print("tile render failed:", (res.stderr or res.stdout).strip()[:600])
        return 1
    for p, d in plans:
        p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    info = json.loads(res.stdout.strip().splitlines()[-1])
    print(f"rendered {info['rendered']} tiles, {info['bytes'] // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
