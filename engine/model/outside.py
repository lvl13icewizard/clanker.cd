"""What's outside the lanes — a read-only report.

Every artist in the cleaned history gets the same affinity the taste model
uses; the ones that belong to NO lane are ranked, tagged (Last.fm top tags,
cached and rate-limited like every other call), and grouped into
territories: tags carrying the most of your un-laned listening, marked as
ADJACENT to an existing lane (its members share the tag) or NEW. Ends with a
handful of candidate lanes (tag clusters + seed artists) for you to accept,
rename, or ignore. Nothing here changes the model.

Writes out/outside-lanes.md and out/outside-lanes.json.

Run:  PYTHONPATH=<root> python3 -m engine.model.outside [--top 160]
"""

import argparse
import csv
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

from ..lib.config import load_config
from ..lib.http import get_json
from ..lib.normalize import norm_artist

STOP = {"seen live", "favorites", "favourites", "favourite", "favorite", "awesome", "beautiful",
        "love", "loved", "all", "good", "cool", "usa", "american", "british", "uk", "canadian",
        "australian", "french", "german", "swedish", "japanese", "male vocalists", "female vocalists",
        "female vocalist", "male vocalist", "spotify", "under 2000 listeners", "check out",
        "00s", "10s", "90s", "80s", "70s", "60s", "2000s", "2010s", "2020s", "1990s", "1980s",
        "albums i own", "want to see live", "sexy", "epic", "fun", "summer", "winter", "night", "party"}


def affinity(hours, completion, rec_w):
    h = min(1.0, math.log1p(hours) / math.log1p(60.0))
    return round(0.55 * h + 0.25 * completion + 0.20 * rec_w, 3)


def lastfm_tags(name, key, n=6, min_weight=12):
    q = urlencode({"method": "artist.gettoptags", "artist": name, "api_key": key,
                   "format": "json", "autocorrect": 1})
    try:
        d = get_json("https://ws.audioscrobbler.com/2.0/?" + q, rate_key="lastfm",
                     min_interval=0.3, ttl_days=30)
    except Exception:
        return []
    tags = ((d.get("toptags") or {}).get("tag") or [])
    out = []
    an = name.lower()
    for t in tags:
        nm = str(t.get("name", "")).strip().lower()
        try:
            w = int(t.get("count", 0))
        except (TypeError, ValueError):
            w = 0
        if not nm or nm in STOP or nm == an or w < min_weight or nm.isdigit():
            continue
        out.append((nm, w))
        if len(out) == n:
            break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", type=int, default=160, help="un-laned artists to tag")
    ap.add_argument("--min-hours", type=float, default=1.5)
    args = ap.parse_args(argv)
    cfg = load_config()
    key = cfg.get("LASTFM_API_KEY")
    if not key:
        raise SystemExit("LASTFM_API_KEY missing in .env")
    out_dir = Path(cfg["OUT_DIR"])
    model = json.loads((out_dir / "taste-model.json").read_text())
    ref = dt.date.fromisoformat((model.get("window") or {}).get("last_play", "2026-07-18")[:10])
    g = model.get("global") or {}
    laned, lane_of = set(), {}
    for c in model["clusters"]:
        for mem in c.get("members") or []:
            k = norm_artist(mem["artist"])
            laned.add(k)
            lane_of.setdefault(k, c["id"])

    rows = []
    with open(Path(cfg["SPOTIFY_CLEAN_DIR"]) / "artists.csv") as f:
        for r in csv.DictReader(f):
            try:
                hours = float(r["hours"]); plays = int(float(r["plays"]))
                comp = float(r.get("completion_rate") or 0); skip = float(r.get("skip_rate") or 0)
            except (TypeError, ValueError):
                continue
            last = r.get("last_played") or ""
            try:
                days = (ref - dt.date.fromisoformat(last[:10])).days
            except Exception:
                days = 3650
            recw = 0.5 ** (max(0, days) / 548)
            rows.append({"artist": r["artist"], "key": norm_artist(r["artist"]), "hours": hours,
                         "plays": plays, "skip": skip, "completion": comp, "last": last[:10],
                         "affinity": affinity(hours, comp, recw)})
    total_hours = sum(r["hours"] for r in rows) or 1.0
    outside = [r for r in rows if r["key"] not in laned]
    outside_hours = sum(r["hours"] for r in outside)
    inside_hours = total_hours - outside_hours
    outside.sort(key=lambda r: (-r["affinity"], -r["hours"]))
    pick = [r for r in outside if r["hours"] >= args.min_hours][: args.top]

    # tags for the un-laned top, and a tag profile per lane (top members)
    for r in pick:
        r["tags"] = lastfm_tags(r["artist"], key)
    lane_tags = defaultdict(lambda: defaultdict(float))
    for c in model["clusters"]:
        mems = sorted(c.get("members") or [], key=lambda m: -m.get("affinity", 0))[:12]
        for mem in mems:
            for tg, w in lastfm_tags(mem["artist"], key):
                lane_tags[c["id"]][tg] += w * mem.get("affinity", 0.5)

    # territories: tag -> un-laned artists
    terr = defaultdict(list)
    for r in pick:
        for tg, w in r["tags"]:
            terr[tg].append(r)
    rows_t = []
    for tg, arts in terr.items():
        hrs = sum(a["hours"] for a in arts)
        adj = sorted(((lane_tags[lid].get(tg, 0.0), lid) for lid in lane_tags), reverse=True)
        adjacent = [lid for w, lid in adj if w >= 40][:2]
        rows_t.append({"tag": tg, "hours": round(hrs, 1), "artists": len(arts),
                       "top": [a["artist"] for a in sorted(arts, key=lambda a: -a["affinity"])[:6]],
                       "adjacent": adjacent})
    rows_t.sort(key=lambda t: -t["hours"])

    # candidate lanes: greedy over SPECIFIC territories with low artist
    # overlap (umbrella tags still show above, but "electronic" or "rock" is
    # not a lane; the specific tag underneath it is)
    UMBRELLA = {"electronic", "hip-hop", "hip hop", "rap", "rock", "indie", "alternative", "pop",
                "experimental", "dance", "chill", "instrumental", "music"}
    taken, cands = set(), []
    for t in rows_t:
        if t["tag"] in UMBRELLA:
            continue
        arts = [a for a in terr[t["tag"]] if a["key"] not in taken]
        if len(arts) < 3 or t["artists"] < 3:
            continue
        if len(arts) / max(1, t["artists"]) < 0.5:
            continue
        seeds = [a["artist"] for a in sorted(arts, key=lambda a: -a["affinity"])[:5]]
        cands.append({"tag": t["tag"], "hours": round(sum(a["hours"] for a in arts), 1),
                      "seeds": seeds, "adjacent": t["adjacent"]})
        taken.update(a["key"] for a in arts)
        if len(cands) == 12:
            break

    # ---- write
    md = []
    md.append("# What's outside the lanes\n")
    md.append(f"Reference date {ref}. {len(rows):,} artists in the history; {len(laned)} are lane members "
              f"(9 lanes). Laned artists carry {inside_hours:.0f} h = {100*inside_hours/total_hours:.0f}% of all "
              f"listening; everything else ({len(outside):,} artists) carries {outside_hours:.0f} h = "
              f"{100*outside_hours/total_hours:.0f}%. Tagged the top {len(pick)} un-laned artists by affinity "
              f"(>= {args.min_hours} h).\n")
    md.append("## Top un-laned artists\n")
    md.append("| # | artist | hours | plays | skip | last played | affinity | tags |\n|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(pick[:50], 1):
        md.append(f"| {i} | {r['artist']} | {r['hours']:.1f} | {r['plays']} | {int(round(r['skip']*100))}% | {r['last']} | {r['affinity']:.2f} | "
                  + ", ".join(t for t, _ in r["tags"][:4]) + " |")
    md.append("\n## Territories (tags carrying the most un-laned listening)\n")
    md.append("| tag | hours | artists | who | adjacent lanes |\n|---|---|---|---|---|")
    for t in rows_t[:30]:
        md.append(f"| {t['tag']} | {t['hours']} | {t['artists']} | {', '.join(t['top'])} | "
                  + (", ".join(t["adjacent"]) if t["adjacent"] else "NEW") + " |")
    md.append("\n## Candidate lanes (greedy, low overlap)\n")
    for c in cands:
        md.append(f"- **{c['tag']}** — {c['hours']} h un-laned; seeds: {', '.join(c['seeds'])}"
                  + (f"; borders {', '.join(c['adjacent'])}" if c["adjacent"] else "; new territory"))
    text = "\n".join(md) + "\n"
    (out_dir / "outside-lanes.md").write_text(text)
    (out_dir / "outside-lanes.json").write_text(json.dumps(
        {"reference": str(ref), "inside_hours": round(inside_hours, 1), "outside_hours": round(outside_hours, 1),
         "top": [{k: v for k, v in r.items() if k != "key"} for r in pick],
         "territories": rows_t, "candidates": cands}, indent=1))
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
