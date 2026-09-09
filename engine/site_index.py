"""Write the issue index the site reads first: site/public/issues/index.json.

One small manifest, newest first, listing every issue in issues/ — so the
site loads exactly what exists instead of probing numbers. The site still
falls back to probing when the file is absent.

Run:  PYTHONPATH=<root> python3 -m engine.site_index
"""

import json
import re
import sys
from pathlib import Path

from .lib.config import load_config


def main(argv=None):
    cfg = load_config()
    src = Path(cfg["ISSUES_DIR"])
    entries = []
    for p in sorted(src.glob("issue-*.json")):
        m = re.search(r"issue-(\d+)\.json$", p.name)
        if not m:
            continue
        n = int(m.group(1))
        if n == 0:
            continue  # the synthetic fixture never lists
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        entries.append({"issue": n, "date": d.get("date"), "title": d.get("title")})
    entries.sort(key=lambda e: -e["issue"])
    out = Path(cfg["SITE_ISSUES_DIR"]) / "index.json"
    out.write_text(json.dumps({"issues": entries}, indent=1, ensure_ascii=False) + "\n")
    print(f"site index: {len(entries)} issue(s) -> {out}")
    write_lanes(cfg)
    return 0


def write_lanes(cfg):
    """The lane pages' data: each lane's name, description, state, the seeds
    and its strongest members, from the taste model (site/public/issues/
    lanes.json, gitignored like every other listening-derived file)."""
    mp = Path(cfg["OUT_DIR"]) / "taste-model.json"
    if not mp.exists():
        return
    model = json.loads(mp.read_text())
    lanes = []
    for c in model.get("clusters") or []:
        mem = sorted(c.get("members") or [], key=lambda m: -m.get("affinity", 0))
        lanes.append({
            "id": c.get("id"), "name": c.get("name"), "description": c.get("description"),
            "state": c.get("state"), "state_evidence": c.get("state_evidence"),
            "members": len(mem),
            "hours": round(sum(float(m.get("hours") or 0) for m in mem), 1),
            "seeds": c.get("seed_artists") or [],
            "top": [{"artist": m["artist"], "hours": m.get("hours"), "plays": m.get("plays"),
                     "skip_rate": m.get("skip_rate"), "affinity": m.get("affinity"), "via": m.get("via")}
                    for m in mem[:12]],
        })
    out = Path(cfg["SITE_ISSUES_DIR"]) / "lanes.json"
    out.write_text(json.dumps({"lanes": lanes, "generated_at": model.get("generated_at")}, indent=1, ensure_ascii=False) + "\n")
    print(f"site lanes: {len(lanes)} lane(s) -> {out}")


if __name__ == "__main__":
    sys.exit(main())
