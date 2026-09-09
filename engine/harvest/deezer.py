"""Adjacent-artist leads from Deezer's keyless API.

Per seed (same shared list as lb_labs): /search/artist to find the Deezer id
— accepted only on an exact normalized name match, no fuzzy guessing — then
/artist/{id}/related for related artists. Emits artist-level
track_candidates (title null by contract).

Deezer reports no similarity number, so an edge's strength is its rank
position in the response (first of ten = 1.0, tenth = 0.1). A seed whose
first PER_SEED related artists yield fewer than NOVEL_FLOOR never-played
artists is queried again at DEEP_PER_SEED.

Rate: 0.4s minimum interval (rate_key "deezer"). No API key needed.
"""

from urllib.parse import quote

from engine.lib import http
from engine.lib.normalize import norm_artist

from engine.harvest.leads import (DEEP_PER_SEED, NOVEL_FLOOR, PER_SEED, Leads,
                                  Yield, strength_by_rank)
from engine.harvest.musicbrainz import get_seed_artists

API = "https://api.deezer.com"
SEED_COUNT = 25


def _get(path):
    return http.get_json(API + path, rate_key="deezer", min_interval=0.4, ttl_days=7)


def _artist_id(name):
    """Exact normalized-name matches only; among duplicates (Deezer carries
    empty duplicate pages, e.g. three artists named 'Tycho') take the one
    with the most fans. No fuzzy fallback."""
    data = _get("/search/artist?q=%s&limit=5" % quote(name))
    target = norm_artist(name)
    exact = [a for a in (data.get("data") or [])
             if norm_artist(a.get("name", "")) == target]
    if not exact:
        return None  # ambiguous / not found — skip rather than risk a homonym
    return max(exact, key=lambda a: a.get("nb_fan") or 0)["id"]


def _related(artist_id, limit=PER_SEED):
    data = _get("/artist/%d/related?limit=%d" % (artist_id, limit))
    return [a for a in (data.get("data") or []) if a.get("name")][:limit]


def harvest(limit=None, related=None, artist_id=None, seeds=None):
    """Return ({"track_candidates": [...]}, status). limit caps seed artists."""
    related = related or _related
    artist_id = artist_id or _artist_id
    seeds = (seeds if seeds is not None else get_seed_artists())[: (limit or SEED_COUNT)]
    leads, yld = Leads("deezer_related"), Yield()
    used = unmatched = errors = 0
    for s in seeds:
        try:
            aid = artist_id(s["artist"])
        except Exception:
            errors += 1
            continue
        if aid is None:
            unmatched += 1
            continue
        try:
            rows = related(aid, PER_SEED)
        except Exception:
            errors += 1
            continue
        used += 1
        page = PER_SEED
        if yld.record(s, [r["name"] for r in rows]) < NOVEL_FLOOR:
            try:
                deeper = related(aid, DEEP_PER_SEED)
            except Exception:
                deeper = None
            if deeper:
                rows, page = deeper, DEEP_PER_SEED
                yld.rows.pop()
                yld.record(s, [r["name"] for r in rows], deepened=True)
        for i, r in enumerate(rows):
            leads.add(r["name"], s, i, strength_by_rank(i, page))
    cands = leads.candidates()
    status = "ok: %d artist leads from %d/%d seeds (%s)" % (
        len(cands), used, len(seeds), yld.summary())
    if unmatched:
        status += ", %d unmatched" % unmatched
    if errors:
        status += ", %d errors" % errors
    if used == 0 and seeds:
        status = ("error: no seeds usable (%d unmatched, %d errors)"
                  % (unmatched, errors))
    return {"track_candidates": cands, "yield": yld.by_lane()}, status


if __name__ == "__main__":
    payload, status = harvest(limit=2)
    print(status)
    for c in payload["track_candidates"][:12]:
        print(" ", c["artist"], "(via %s, %.2f)" % (c["via"], c["strength"]))
