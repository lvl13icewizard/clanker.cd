"""Resolve real cover art for demo picks.

The picks are real records, so their artwork is real too: resolving it is
what makes a demo look like the product instead of a wireframe. Sources are
the same keyless ones the engine uses, in the cheaper order (iTunes first,
MusicBrainz and the Cover Art Archive as the fallback), and every lookup is
deduplicated across every persona and cached on disk, so a re-run is free.

Radio shows resolve against the NTS show index by name; anything unresolved
stays null and the site renders its artwork-unavailable tile, never a wrong
cover.

Run:  python3 demo/art.py               (every persona)
      python3 demo/art.py --slug andrew
"""

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.art import album_cover, artist_matches, itunes_cover, mb_cover  # noqa: E402
from engine.lib.http import get_json                        # noqa: E402

DEMO = ROOT / "site" / "public" / "demo"
CACHE = ROOT / "demo" / "art-cache.json"
UA = {"User-Agent": "clanker-cd-demo/0.1 (demo persona art)"}
MIX_RE = re.compile(r"\bDJ Mix\b|Today's Hits|\bMix\)", re.I)


def load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except Exception:
            pass
    return {}


def track_cover(artist, title, album=None):
    """A track's artwork: the album when we know it, else an iTunes song
    search, which returns the artwork of the release the track sits on."""
    if album:
        hit = album_cover(artist, album)
        if hit:
            return hit
    term = f"{artist} {title}"
    try:
        d = get_json("https://itunes.apple.com/search?term=" + urllib.parse.quote(term)
                     + "&entity=song&limit=10", rate_key="itunes", min_interval=0.6,
                     ttl_days=90, headers=UA)
    except Exception:
        return None
    for r in d.get("results") or []:
        # Apple Music DJ mixes credit every artist in them; skip the mix.
        if "apple music" in (r.get("collectionArtistName") or "").lower():
            continue
        if MIX_RE.search(r.get("collectionName") or ""):
            continue
        if artist_matches(artist, r.get("artistName")):
            url = r.get("artworkUrl100") or ""
            if url:
                return url.replace("100x100bb", "600x600bb")
    # A single is often its own release, so the release-group search catches
    # what the song search missed. Still an exact artist+title match.
    return album_cover(artist, title)


_NTS_SHOWS = None


def nts_show_cover(show):
    """Match a show name against the NTS index and take its picture."""
    global _NTS_SHOWS
    if _NTS_SHOWS is None:
        _NTS_SHOWS = {}
        offset = 0
        while offset < 1008:
            try:
                d = get_json(f"https://www.nts.live/api/v2/shows?limit=12&offset={offset}",
                             ttl_days=6, rate_key="nts", min_interval=0.7, headers=UA)
            except Exception:
                break
            rs = d.get("results") or []
            if not rs:
                break
            for sh in rs:
                nm = (sh.get("name") or "").strip().lower()
                pic = ((sh.get("media") or {}).get("picture_medium_large")
                       or (sh.get("media") or {}).get("picture_large")
                       or (sh.get("media") or {}).get("picture_medium"))
                if nm and pic and nm not in _NTS_SHOWS:
                    _NTS_SHOWS[nm] = pic
            offset += len(rs)
        print(f"  NTS show index: {len(_NTS_SHOWS)} shows with pictures")
    key = (show or "").strip().lower()
    if key in _NTS_SHOWS:
        return _NTS_SHOWS[key]
    # "NTS Radio" and station names are not shows; try the host's own show.
    for nm, pic in _NTS_SHOWS.items():
        if key and (key in nm or nm in key) and len(nm) > 6:
            return pic
    return None


def resolve_issue(issue, cache, stats):
    """Fill cover_url on every item that can carry one. Returns changed."""
    changed = False

    def put(obj, kind, *args):
        nonlocal changed
        stats["total"] += 1
        if obj.get("cover_url"):
            stats["already"] += 1
            return
        key = kind + "|" + "|".join(str(a or "") for a in args)
        if key in cache:
            url = cache[key]
            stats["cached"] += 1
        else:
            if kind == "album":
                url = album_cover(*args)
            elif kind == "track":
                url = track_cover(*args)
            elif kind == "show":
                url = nts_show_cover(*args)
            else:
                url = None
            cache[key] = url
            stats["looked_up"] += 1
        if url:
            obj["cover_url"] = url
            stats["filled"] += 1
            changed = True
        else:
            stats["missed"] += 1

    for m in issue.get("modules") or []:
        t = m.get("type")
        if t == "front_to_back" and isinstance(m.get("album"), dict):
            a = m["album"]
            put(a, "album", a.get("artist"), a.get("title"), a.get("year"))
        elif t == "singles_rack":
            for x in m.get("tracks") or []:
                put(x, "track", x.get("artist"), x.get("title"), None)
        elif t == "revival_desk":
            for x in m.get("tracks") or []:
                put(x, "track", x.get("artist"), x.get("title"), x.get("album"))
        elif t == "critics_desk":
            for a in m.get("albums") or []:
                put(a, "album", a.get("artist"), a.get("title"), a.get("year"))
        elif t == "catalog_room":
            for u in m.get("unheard") or []:
                put(u, "album", m.get("artist"), u.get("title"), u.get("year"))
        elif t == "the_mix":
            for x in m.get("mixes") or []:
                put(x, "show", x.get("show"))
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug")
    ap.add_argument("--limit", type=int, default=0, help="stop after N lookups (for a quick pass)")
    args = ap.parse_args(argv)
    slugs = ([args.slug] if args.slug
             else sorted(p.name for p in DEMO.iterdir()
                         if p.is_dir() and (p / "index.json").exists()))
    cache = load_cache()
    stats = {"total": 0, "already": 0, "cached": 0, "looked_up": 0, "filled": 0, "missed": 0}
    try:
        for slug in slugs:
            paths = sorted((DEMO / slug).glob("issue-*.json"))
            for p in paths:
                d = json.loads(p.read_text())
                if resolve_issue(d, cache, stats):
                    p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
                if args.limit and stats["looked_up"] >= args.limit:
                    raise KeyboardInterrupt
            print(f"{slug}: {stats['filled']}/{stats['total']} covers resolved so far")
    except KeyboardInterrupt:
        print("  stopped early (limit or interrupt); cache saved")
    finally:
        CACHE.write_text(json.dumps(cache, indent=0, ensure_ascii=False, sort_keys=True))
    print(f"art: {stats['filled']}/{stats['total']} filled "
          f"({stats['looked_up']} lookups, {stats['cached']} from cache, "
          f"{stats['already']} already set, {stats['missed']} unresolved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
