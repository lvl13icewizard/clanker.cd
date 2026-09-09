"""Adjacent-artist leads from Last.fm artist.getSimilar.

Runs ONLY when LASTFM_API_KEY is present in config; otherwise reports
"skipped: no LASTFM_API_KEY" and emits nothing. Same shared seed list as the
other similarity adapters; artist-level track_candidates (title null).

Each lead keeps every seed edge that reached it with Last.fm's `match`
(already 0..1, top neighbour 1.0) as the edge strength. A seed whose first
page yields fewer than NOVEL_FLOOR never-played artists is queried again at
DEEP_PER_SEED before the adapter moves on (engine.harvest.leads).

Rate: 0.3s minimum interval (rate_key "lastfm").
"""

from urllib.parse import urlencode

from engine.lib import http
from engine.lib.config import load_config

from engine.harvest.leads import DEEP_PER_SEED, NOVEL_FLOOR, PER_SEED, Leads, Yield
from engine.harvest.musicbrainz import get_seed_artists

API = "https://ws.audioscrobbler.com/2.0/"
SEED_COUNT = 25


def _similar(name, key, limit=PER_SEED):
    q = urlencode({"method": "artist.getsimilar", "artist": name,
                   "api_key": key, "format": "json", "limit": limit,
                   "autocorrect": 1})
    data = http.get_json("%s?%s" % (API, q),
                         rate_key="lastfm", min_interval=0.3, ttl_days=7)
    if "error" in data:
        raise RuntimeError("lastfm error %s: %s" % (data.get("error"), data.get("message")))
    return (data.get("similarartists") or {}).get("artist") or []


def _strength(row):
    try:
        return max(0.01, min(1.0, float(row.get("match") or 0)))
    except (TypeError, ValueError):
        return 0.01


def harvest(limit=None, similar=None, seeds=None):
    """Return ({"track_candidates": [...]}, status). limit caps seed artists."""
    key = load_config().get("LASTFM_API_KEY")
    if not key and similar is None:
        return {"track_candidates": []}, "skipped: no LASTFM_API_KEY"
    similar = similar or (lambda name, lim: _similar(name, key, lim))
    seeds = (seeds if seeds is not None else get_seed_artists())[: (limit or SEED_COUNT)]
    leads, yld = Leads("lastfm_similar"), Yield()
    used = errors = 0
    for s in seeds:
        try:
            rows = similar(s["artist"], PER_SEED)
        except Exception:
            errors += 1
            continue
        used += 1
        deepened = False
        if yld.record(s, [r.get("name") for r in rows]) < NOVEL_FLOOR:
            try:
                rows = similar(s["artist"], DEEP_PER_SEED) or rows
                deepened = True
            except Exception:
                pass
        if deepened:
            yld.rows.pop()
            yld.record(s, [r.get("name") for r in rows], deepened=True)
        for i, r in enumerate(rows):
            leads.add(r.get("name"), s, i, _strength(r))
    cands = leads.candidates()
    status = "ok: %d artist leads from %d/%d seeds (%s)" % (
        len(cands), used, len(seeds), yld.summary())
    if errors:
        status += ", %d errors" % errors
    if used == 0 and seeds:
        status = "error: all %d seed queries failed" % len(seeds)
    return {"track_candidates": cands, "yield": yld.by_lane()}, status


if __name__ == "__main__":
    payload, status = harvest(limit=2)
    print(status)
    for c in payload["track_candidates"][:12]:
        print(" ", c["artist"], "(via %s, %.2f)" % (c["via"], c["strength"]))
