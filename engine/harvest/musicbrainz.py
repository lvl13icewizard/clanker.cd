"""Orbit release calendar via MusicBrainz + shared seed-artist selection.

Seeds: `get_seed_artists()` is imported by lb_labs/deezer/lastfm so every
similarity adapter works from the same list; the selection itself (lane
allocation, rotation by issue, artists.csv fallback) is engine.harvest.seeds.

MBID resolution: /ws/2/artist search, exact normalized-name match preferred,
else top hit with ext:score >= 90, else None (no guessing). The http lib
caches by URL, so re-resolving from other modules costs no network.

Release calendar: browse /ws/2/release-group?artist=<mbid>&type=album|ep|single,
keep groups whose first-release-date is a FULL date (YYYY-MM-DD) within the
last WINDOW_DAYS days — partial dates (year or year-month) are too coarse for
a 45-day window and are ignored rather than approximated. Groups with
secondary types (compilation/live/remix/...) are skipped.

Rate: 1.1s minimum interval (rate_key "musicbrainz"), UA set by engine.lib.http.
"""

import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlencode

from engine.lib import http
from engine.harvest import seeds as seeds_mod
from engine.lib.config import load_config
from engine.lib.normalize import norm_artist, norm_title

MB_ROOT = "https://musicbrainz.org/ws/2"
WINDOW_DAYS = 45
SEED_COUNT = 120
_TYPE_MAP = {"album": "album", "ep": "ep", "single": "single"}


def get_seed_artists(n=SEED_COUNT, issue_n=None):
    """[{artist, cluster, hours, affinity}] in allocation order.

    Selection lives in engine.harvest.seeds (lane-allocated, rotated by
    issue, hours-sorted fallback); this name is kept because every
    similarity adapter imports it from here.
    """
    return seeds_mod.get_seed_artists(n=n, issue_n=issue_n)


def resolve_artist_mbid(name):
    """name -> MBID or None. Cached at the URL layer; safe to call repeatedly."""
    q = urlencode({"query": 'artist:"%s"' % name.replace('"', " "),
                   "fmt": "json", "limit": 5})
    try:
        data = http.get_json("%s/artist/?%s" % (MB_ROOT, q),
                             rate_key="musicbrainz", min_interval=1.1, ttl_days=30)
    except Exception:
        return None
    target = norm_artist(name)
    hits = data.get("artists") or []
    for a in hits:
        if norm_artist(a.get("name", "")) == target:
            return a["id"]
        for alias in a.get("aliases") or []:
            if norm_artist(alias.get("name", "")) == target:
                return a["id"]
    if hits and int(hits[0].get("score") or 0) >= 90:
        return hits[0]["id"]
    return None


def _recent_release_groups(mbid, since):
    q = urlencode({"artist": mbid, "type": "album|ep|single",
                   "limit": 100, "fmt": "json"})
    data = http.get_json("%s/release-group?%s" % (MB_ROOT, q),
                         rate_key="musicbrainz", min_interval=1.1, ttl_days=3)
    out = []
    for rg in data.get("release-groups") or []:
        frd = rg.get("first-release-date") or ""
        if len(frd) != 10:  # full YYYY-MM-DD only — see module docstring
            continue
        try:
            d = dt.date.fromisoformat(frd)
        except ValueError:
            continue
        if d < since or d > dt.date.today() + dt.timedelta(days=7):
            continue
        ptype = (rg.get("primary-type") or "").lower()
        if ptype not in _TYPE_MAP or rg.get("secondary-types"):
            continue
        out.append({"title": rg.get("title"), "release_date": frd,
                    "release_type": _TYPE_MAP[ptype], "mbid": rg.get("id")})
    return out


def harvest(limit=None):
    """Return ({"new_releases": [...]}, status). limit caps seed artists."""
    seeds = get_seed_artists()
    if limit:
        seeds = seeds[:limit]
    since = dt.date.today() - dt.timedelta(days=WINDOW_DAYS)
    releases, seen = [], set()
    resolved = unresolved = errors = 0
    for s in seeds:
        mbid = resolve_artist_mbid(s["artist"])
        if not mbid:
            unresolved += 1
            continue
        resolved += 1
        try:
            groups = _recent_release_groups(mbid, since)
        except Exception:
            errors += 1
            continue
        for g in groups:
            k = (norm_artist(s["artist"]), norm_title(g["title"] or ""))
            if k in seen:
                continue
            seen.add(k)
            releases.append({"artist": s["artist"], "title": g["title"],
                             "release_date": g["release_date"],
                             "release_type": g["release_type"],
                             "relationship": "played", "via": None,
                             "mbid": g["mbid"]})
    releases.sort(key=lambda r: (r["release_date"], r["artist"]), reverse=True)
    status = ("ok: %d releases from %d/%d seeds resolved"
              % (len(releases), resolved, len(seeds)))
    if unresolved:
        status += ", %d unresolved" % unresolved
    if errors:
        status += ", %d browse errors" % errors
    if resolved == 0 and seeds:
        status = "error: resolved 0 of %d seed artists" % len(seeds)
    return {"new_releases": releases}, status


if __name__ == "__main__":
    payload, status = harvest(limit=3)
    print(status)
    for r in payload["new_releases"]:
        print(" ", r["release_date"], r["release_type"], "|", r["artist"], "—", r["title"])
