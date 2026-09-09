"""Harvest MixesDB for the Mixes module: Boiler Room and the Essential Mix.

Neither source publishes structured tracklists itself; MixesDB does, as an
open MediaWiki wiki (verified live 2026-08-28). Recent pages come from
list=categorymembers per source category, the tracklist from the page's
wikitext, where lines read `# [MM:SS] Artist - Title [Label]`. Pages
carrying Category:Tracklist: none are skipped, and each mix's genre
categories map to clusters through the same tag table NTS uses.

Output: out/mixesdb-harvest.json, same candidate shape as nts.py plus a
station per source. Selection happens in engine/select/phase2.py.

Run:  PYTHONPATH=<root> python3 -m engine.harvest.mixesdb
"""

import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from ..lib.config import load_config
from ..lib.http import get_json
from ..lib.media import player_urls
from ..lib.history import artist_played
from ..lib.normalize import norm_artist
from .nts import CLUSTER_TAGS, _affinity_proxy, _split_artists

API = "https://www.mixesdb.com/w/api.php"
RATE = {"rate_key": "mixesdb", "min_interval": 1.5,
        "headers": {"User-Agent": "clanker-cd/0.1 (music journal; respectful weekly poll)"}}

SOURCES = [
    # (category, station, default cluster, drop-suffix for the episode name)
    ("Essential Mix", "BBC Radio 1", "club-continuum", " - Essential Mix"),
    ("Boiler Room", "Boiler Room", "club-continuum", None),
]
PER_SOURCE = 8
MIN_TRACKS = 12
TRACK_RE = re.compile(r"^#\s*(?:\[[\d:?]+\]\s*)?(.+?)(?:\s*\[[^\]]*\])?\s*$")


def _members(category):
    q = urllib.parse.urlencode({
        "action": "query", "list": "categorymembers", "format": "json",
        "cmtitle": f"Category:{category}", "cmlimit": 30,
        "cmsort": "timestamp", "cmdir": "desc", "cmnamespace": 0,
    })
    d = get_json(f"{API}?{q}", ttl_days=3, **RATE)
    return [m["title"] for m in (d.get("query") or {}).get("categorymembers") or []]


def _wikitext(title):
    q = urllib.parse.urlencode({"action": "parse", "page": title,
                                "prop": "wikitext", "format": "json"})
    d = get_json(f"{API}?{q}", ttl_days=6, **RATE)
    return ((d.get("parse") or {}).get("wikitext") or {}).get("*") or ""


def _cluster_from_page(text, fallback):
    cats = [c.lower() for c in re.findall(r"\[\[Category:([^\]|]+)\]\]", text)]
    hits = {}
    for cid, needles in CLUSTER_TAGS.items():
        n = sum(1 for c in cats for nd in needles if nd in c)
        if n:
            hits[cid] = n
    return max(hits, key=hits.get) if hits else fallback


def _tracks(text):
    i = text.find("== Tracklist ==")
    if i == -1:
        return []
    out = []
    for line in text[i:].splitlines():
        m = TRACK_RE.match(line.strip())
        if not m:
            continue
        body = m.group(1).strip()
        if " - " in body:
            artist, title = body.split(" - ", 1)
        else:
            artist, title = body, ""
        if artist and artist.lower() not in ("?", "unknown"):
            out.append({"artist": artist.strip(), "title": title.strip()})
    return out


def main():
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])

    model = {}
    mp = out_dir / "taste-model.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        for c in m.get("clusters", []):
            for e in c.get("members", []):
                k = norm_artist(e["artist"])
                if e["affinity"] > model.get(k, 0):
                    model[k] = e["affinity"]

    served_urls = set()
    sp = Path(cfg["SERVED_PATH"])
    if sp.exists():
        for it in json.loads(sp.read_text()).get("items", []):
            if str(it.get("context", "")).endswith("the_mix") and it.get("uri"):
                served_urls.add(str(it["uri"]).split("?")[0])

    candidates, skipped = [], 0
    for category, station, default_cluster, drop in SOURCES:
        titles = [t for t in _members(category) if re.match(r"^\d{4}-\d{2}-\d{2} - ", t)]
        print(f"{category}: {len(titles)} recent pages")
        polled = 0
        for title in titles:
            if polled >= PER_SOURCE:
                break
            url = "https://www.mixesdb.com/w/" + urllib.parse.quote(title.replace(" ", "_"))
            if url in served_urls:
                continue
            polled += 1
            text = _wikitext(title)
            if not text or "Category:Tracklist: none" in text:
                skipped += 1
                continue
            tracks = _tracks(text)
            if len(tracks) < MIN_TRACKS:
                skipped += 1
                continue
            date, rest = title[:10], title[13:]
            episode = rest[:-len(drop)] if drop and rest.endswith(drop) else rest
            known, known_tracks = {}, 0
            for t in tracks:
                hit = None
                for cand in [t["artist"]] + _split_artists(t["artist"]):
                    row = artist_played(cand)
                    if row:
                        hit = row
                        break
                if hit:
                    known_tracks += 1
                    k = norm_artist(hit["artist"])
                    if k not in known:
                        known[k] = {
                            "artist": hit["artist"],
                            "plays": int(float(hit["plays"])),
                            "hours": float(hit["hours"]),
                            "skip_rate": float(hit["skip_rate"]),
                            "affinity": round(_affinity_proxy(
                                model.get(k), float(hit["hours"])), 3),
                        }
            total = len(tracks)
            new_tracks = total - known_tracks
            nr = new_tracks / total
            bell = max(0.1, 1 - abs(nr - 0.7) / 0.7)
            anchor = sum(sorted((k["affinity"] for k in known.values()), reverse=True)[:3])
            candidates.append({
                "cluster": _cluster_from_page(text, default_cluster), "tag_hits": 1,
                "show": category, "show_alias": f"mixesdb-{category.lower().replace(' ', '-')}",
                "episode": episode, "station": station,
                "date": date, "url": url,
                # The page's {{Player}} mirrors (YouTube, SoundCloud...):
                # the reader's listen links, and where the artwork comes from.
                "audio_sources": player_urls(text),
                "tracks_total": total,
                "known_track_count": known_tracks,
                "new_track_count": new_tracks,
                "known_artists": sorted(known.values(), key=lambda k: -k["affinity"])[:8],
                "score": round(anchor * bell, 4),
            })

    candidates.sort(key=lambda c: -c["score"])
    p = out_dir / "mixesdb-harvest.json"
    p.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meta": {"skipped_no_tracklist": skipped, "candidates": len(candidates)},
        "candidates": candidates,
    }, indent=1, ensure_ascii=False))
    print(f"wrote {p} — {len(candidates)} candidates ({skipped} skipped, no tracklist)")
    for c in candidates[:6]:
        print(f"  {c['score']:6.3f} [{c['cluster']:16}] {c['show']}: {c['episode']} — "
              f"{c['date']} · {c['tracks_total']} tracks, {c['known_track_count']} known")


if __name__ == "__main__":
    main()
