"""Adjacent-artist leads from ListenBrainz Labs similar-artists.

For the shared seed list (engine.harvest.seeds via musicbrainz), resolve
MBIDs (URL-cached — free after musicbrainz.py has run) and query
labs.api.listenbrainz.org/similar-artists/json. Emits artist-level
track_candidates (title null by contract; curation picks tracks later).

Each lead keeps every seed edge that reached it. ListenBrainz's `score` is
a session co-occurrence count with no fixed scale, so it is normalized
within each seed's response (top neighbour 1.0) before it becomes the edge
strength. A seed whose first PER_SEED neighbours yield fewer than
NOVEL_FLOOR never-played artists is read deeper, to DEEP_PER_SEED, from the
same response (the endpoint returns up to 100). Canonical names in another
script are shown and verified under their Latin aliases (engine.lib.names).

The algorithm string is the one ListenBrainz's own similar-artists UI uses.
Rate: 0.6s minimum interval (rate_key "lb_labs").
"""

from urllib.parse import urlencode

from engine.lib import http, names

from engine.harvest.leads import DEEP_PER_SEED, NOVEL_FLOOR, PER_SEED, Leads, Yield
from engine.harvest.musicbrainz import get_seed_artists, resolve_artist_mbid

LABS_URL = "https://labs.api.listenbrainz.org/similar-artists/json"
ALGORITHM = ("session_based_days_7500_session_300_contribution_5_threshold_10"
             "_limit_100_filter_True_skip_30")
SEED_COUNT = 25


def _similar(mbid):
    """All neighbours, strongest first (the caller takes what it needs)."""
    q = urlencode({"artist_mbids": mbid, "algorithm": ALGORITHM})
    data = http.get_json("%s?%s" % (LABS_URL, q),
                         rate_key="lb_labs", min_interval=0.6, ttl_days=7)
    if isinstance(data, dict):  # some deployments wrap the list
        data = data.get("data") or data.get("similar_artists") or []
    rows = [r for r in data if isinstance(r, dict) and r.get("name")]
    rows.sort(key=lambda r: -(r.get("score") or 0))
    return rows


def _strengths(rows):
    top = max((float(r.get("score") or 0) for r in rows), default=0.0)
    if top <= 0:
        return [1.0 / (i + 1) for i in range(len(rows))]
    return [max(0.01, float(r.get("score") or 0) / top) for r in rows]


def harvest(limit=None, similar=None, resolve=None, seeds=None):
    """Return ({"track_candidates": [...]}, status). limit caps seed artists."""
    similar = similar or _similar
    resolve = resolve or resolve_artist_mbid
    seeds = (seeds if seeds is not None else get_seed_artists())[: (limit or SEED_COUNT)]
    leads, yld = Leads("lb_labs"), Yield()
    used = unresolved = errors = 0
    for s in seeds:
        mbid = resolve(s["artist"])
        if not mbid:
            unresolved += 1
            continue
        try:
            rows = similar(mbid)
        except Exception:
            errors += 1
            continue
        used += 1
        take = rows[:PER_SEED]
        deepened = False
        if yld.record(s, [r["name"] for r in take]) < NOVEL_FLOOR and len(rows) > PER_SEED:
            take = rows[:DEEP_PER_SEED]
            deepened = True
            yld.rows.pop()
            yld.record(s, [r["name"] for r in take], deepened=True)
        for i, (r, st) in enumerate(zip(take, _strengths(take))):
            mbid = r.get("artist_mbid")
            name = names.latin_name(mbid, r["name"])
            leads.add(name, s, i, st)
            if name != r["name"]:
                leads.alias(name, names.aliases(mbid, r["name"]))
    cands = leads.candidates()
    status = "ok: %d artist leads from %d/%d seeds (%s)" % (
        len(cands), used, len(seeds), yld.summary())
    if unresolved:
        status += ", %d unresolved" % unresolved
    if errors:
        status += ", %d query errors" % errors
    if used == 0 and seeds:
        status = ("error: no seeds usable (%d unresolved, %d query errors)"
                  % (unresolved, errors))
    return {"track_candidates": cands, "yield": yld.by_lane()}, status


if __name__ == "__main__":
    payload, status = harvest(limit=2)
    print(status)
    for c in payload["track_candidates"][:12]:
        print(" ", c["artist"], "(via %s, %.2f, hint %s)"
              % (c["via"], c["strength"], c["cluster_hint"]))
