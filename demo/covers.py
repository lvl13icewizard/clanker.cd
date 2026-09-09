"""Render every demo persona's covers and record them on the issues.

Each persona has a palette (from its catalog) and a recipe (a per-persona
hand in demo/build_demo.py), so one archive looks like Berlin concrete and
another like a pop single. Within a persona, the renderer's own seed is the
issue number, so every week's cover differs while the family holds.

Two variants per issue, the same pair the real engine writes:
  cover-NNN.jpg        the mesh with the issue's name
  cover-NNN-plain.jpg  the bare mesh, for list rows

Run:  python3 demo/covers.py            (every persona)
      python3 demo/covers.py --slug andrew
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from demo.build_demo import DEFAULT_RECIPE, RECIPES, display_title_of  # noqa: E402

DEMO = ROOT / "site" / "public" / "demo"
CATALOGS = ROOT / "demo" / "catalogs"


def jobs_for(slug):
    cat = json.loads((CATALOGS / f"{slug}.json").read_text())
    out = DEMO / slug
    recipe = dict(RECIPES.get(slug, DEFAULT_RECIPE))
    jobs, issues = [], sorted(out.glob("issue-*.json"))
    for p in issues:
        d = json.loads(p.read_text())
        n = d["issue"]
        r = dict(recipe)
        r["seed"] = n  # a different mesh every week, same hand
        jobs.append({
            "name": display_title_of(d), "issue": n,
            "palette": cat["palette"], "recipe": r,
            "outText": str(out / f"cover-{n:03d}.jpg"),
            "outPlain": str(out / f"cover-{n:03d}-plain.jpg"),
        })
    return cat, jobs, issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug")
    args = ap.parse_args(argv)
    node = shutil.which("node")
    if not node:
        print("node not found; cannot render covers")
        return 1
    slugs = ([args.slug] if args.slug
             else sorted(p.name for p in DEMO.iterdir()
                         if p.is_dir() and (p / "index.json").exists()))
    if not slugs:
        print("no personas built yet; run demo/build_demo.py first")
        return 1

    all_jobs, per_slug = [], {}
    for slug in slugs:
        cat, jobs, issues = jobs_for(slug)
        per_slug[slug] = (cat, jobs, issues)
        all_jobs.extend(jobs)
    if not all_jobs:
        print("no issues to cover")
        return 1

    tmp = ROOT / "demo" / ".cover-jobs.json"
    tmp.write_text(json.dumps(all_jobs))
    try:
        res = subprocess.run([node, str(ROOT / "demo" / "render_covers.mjs"), str(tmp)],
                             capture_output=True, text=True, timeout=900)
    finally:
        tmp.unlink(missing_ok=True)
    if res.returncode != 0:
        print("cover render failed:", (res.stderr or res.stdout).strip()[:800])
        return 1
    info = json.loads(res.stdout.strip().splitlines()[-1])

    # Record the covers on the issues, the way the engine does.
    for slug, (cat, jobs, issues) in per_slug.items():
        for p in issues:
            d = json.loads(p.read_text())
            n = d["issue"]
            d.setdefault("companion_playlist", {})["cover_art"] = {
                "text": f"/demo/{slug}/cover-{n:03d}.jpg",
                "plain": f"/demo/{slug}/cover-{n:03d}-plain.jpg",
                "palette": cat["palette"],
                "recipe_source": "demo",
            }
            p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
        print(f"{slug}: {len(jobs)} covers x2 variants recorded")
    print(f"rendered {info['rendered']} files, {info['bytes'] // 1024} KB total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
