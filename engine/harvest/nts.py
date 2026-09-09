"""Harvest NTS Radio episodes for the Mixes module.

Endpoints (unofficial JSON API, keyless — verified live 2026-08-02):
  /api/v2/shows?limit=100&offset=N              paginated show index (~1,730)
  /api/v2/shows/{alias}/episodes?limit=N        recent episodes
  /api/v2/shows/{s}/episodes/{e}/tracklist      results[{artist,title,...}]

Method
------
1. Fetch the full show index (cached 6 days). Score every show against each
   cluster by substring-matching its genre+mood tag values against the
   CLUSTER_TAGS map; a show is a candidate for its best-matching cluster.
2. Round-robin the clusters, taking the best-tagged shows first, capped at
   MAX_SHOWS total so a weekly run stays a couple of minutes of polite
   requests. For each show, take the most recent episode that has a tracklist
   of >= MIN_TRACKS and is not already in the served ledger.
3. Overlap analysis against the local history (the whole point): every
   tracklist artist is normalized and looked up in artists.csv — split on
   join separators ("A & B", "A x B") so collaborations count when any
   component is known. A track is "known" when any component matches.
4. Score = (sum of top-3 known-artist affinities) x novelty bell peaking at
   70% new: a mix you can anchor to but mostly haven't heard. Affinity comes
   from the taste model when the artist is a cluster member, else the H term
   ln(1+hours)/ln(61) alone.

Output: out/nts-harvest.json (candidates + meta). Selection happens in
engine/select/phase2.py, not here.

Run:  PYTHONPATH=<root> python3 -m engine.harvest.nts
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from ..lib.config import load_config
from ..lib.http import get_json
from ..lib.history import artist_played
from ..lib.normalize import norm_artist
from ..verify import served_policy

API = "https://www.nts.live/api/v2"
RATE = {"rate_key": "nts", "min_interval": 0.7}

MAX_SHOWS = 36          # total shows to pull episodes for, across clusters
EPISODES_PER_SHOW = 3
MIN_TRACKS = 8
HOURS_SATURATION = 60.0

CLUSTER_TAGS = {
    "the-mist": ["ambient", "new age", "drone", "downtempo", "meditat"],
    "beats-idm": ["idm", "beats", "electronica", "experimental", "glitch"],
    "club-continuum": ["house", "garage", "club", "breakbeat", "leftfield dance"],
    "underground-rap": ["hip hop", "rap", "boom bap"],
    "jazz-bridge": ["jazz"],
    "cosmic-groove": ["psychedelic", "funk", "soul", "tropical", "cumbia",
                      "afro", "brazil", "library"],
    "french-electronic": ["french", "disco", "italo", "electro "],
    "punk-turn": ["punk", "post-punk", "noise rock", "no wave", "hardcore"],
    "bass-edm": ["dubstep", "bass", "drum & bass", "jungle", "grime"],
    "house-garage": ["house", "uk garage", "garage", "deep house", "afterhours"],
    "liquid": ["drum & bass", "liquid", "jungle", "dnb"],
    "dad-rock": ["classic rock", "rock", "blues rock", "americana", "folk rock"],
}

JOINERS = [" & ", " x ", " X ", ", ", " feat. ", " ft. ", " and "]


def _split_artists(s):
    parts = [s]
    for j in JOINERS:
        nxt = []
        for p in parts:
            nxt.extend(p.split(j))
        parts = nxt
    return [p.strip() for p in parts if p.strip()] or [s]


def _tag_values(show):
    vals = []
    for key in ("genres", "moods"):
        for g in show.get(key) or []:
            v = (g.get("value") or "").strip().lower()
            if v:
                vals.append(v)
    return vals


def _match_clusters(tags):
    """{cluster_id: hit_count} over tag substrings."""
    hits = {}
    for cid, needles in CLUSTER_TAGS.items():
        n = sum(1 for t in tags for nd in needles if nd in t)
        if n:
            hits[cid] = n
    return hits


def _affinity_proxy(model_aff, hours):
    if model_aff is not None:
        return model_aff
    return min(1.0, math.log1p(hours) / math.log1p(HOURS_SATURATION))


def fetch_all_shows():
    """Page the show index. The API clamps limit to 12 regardless of what is
    asked, and 422s past a ~1000-offset search window — so 'all' means the
    first ~1000 shows, which is plenty of candidate surface. The 422 is an
    expected end-of-window, not an error."""
    shows, offset = [], 0
    while True:
        try:
            d = get_json(f"{API}/shows?limit=12&offset={offset}",
                         ttl_days=6, **RATE)
        except Exception:
            print(f"  show index window closed at offset {offset}")
            return shows
        rs = d.get("results") or []
        shows.extend(rs)
        count = ((d.get("metadata") or {}).get("resultset") or {}).get("count")
        offset += len(rs)
        if not rs or (count and offset >= count):
            return shows


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

    # Served episodes are matched on URL, not on name. The ledger stores the
    # episode's display title while this loop knows it by alias, so comparing
    # the two silently never matched and Issue 002 re-served Issue 001's mixes.
    # An episode never comes back; its show sits out SHOW_SITOUT_ISSUES issues
    # (engine.verify.served_policy), not forever.
    sp = Path(cfg["SERVED_PATH"])
    served_doc = json.loads(sp.read_text()) if sp.exists() else {"items": []}
    served_urls, served_titles, served_shows = served_policy.show_exclusions(served_doc)

    shows = fetch_all_shows()
    print(f"show index: {len(shows)}")

    per_cluster = {cid: [] for cid in CLUSTER_TAGS}
    for s in shows:
        if (s.get("type") or "show") != "show":
            continue
        hits = _match_clusters(_tag_values(s))
        if not hits:
            continue
        best = max(hits, key=hits.get)
        per_cluster[best].append((hits[best], s))
    for cid in per_cluster:
        per_cluster[cid].sort(key=lambda t: -t[0])

    # round-robin the clusters so no lane monopolises the budget
    picked, idx = [], {cid: 0 for cid in per_cluster}
    while len(picked) < MAX_SHOWS:
        advanced = False
        for cid in CLUSTER_TAGS:
            i = idx[cid]
            if i < len(per_cluster[cid]) and len(picked) < MAX_SHOWS:
                score, show = per_cluster[cid][i]
                picked.append((cid, score, show))
                idx[cid] = i + 1
                advanced = True
        if not advanced:
            break
    print(f"candidate shows: {len(picked)}")

    candidates, tl_missing = [], 0
    for cid, tag_hits, show in picked:
        alias = show.get("show_alias")
        if not alias:
            continue
        # A show that carried a previous issue sits out this one: two issues
        # running from the same programme reads as a rut, not a recommendation.
        if alias in served_shows or \
                (show.get("name") or "").strip().lower() in served_shows:
            continue
        try:
            eps = get_json(f"{API}/shows/{alias}/episodes"
                           f"?limit={EPISODES_PER_SHOW}", ttl_days=3, **RATE)
        except Exception as ex:
            print(f"  [warn] episodes failed for {alias}: {ex}")
            continue
        for ep in eps.get("results") or []:
            ep_alias = ep.get("episode_alias")
            if not ep_alias:
                continue
            ep_url = f"https://www.nts.live/shows/{alias}/episodes/{ep_alias}"
            if ep_url in served_urls:
                continue
            if (ep.get("name") or "").strip().lower() in served_titles:
                continue
            try:
                tl = get_json(f"{API}/shows/{alias}/episodes/{ep_alias}"
                              f"/tracklist", ttl_days=6, **RATE)
            except Exception:
                tl_missing += 1
                continue
            tracks = tl.get("results") or []
            if len(tracks) < MIN_TRACKS:
                tl_missing += 1
                continue

            known, known_tracks = {}, 0
            for t in tracks:
                raw = (t.get("artist") or "").strip()
                if not raw:
                    continue
                hit = None
                for cand in [raw] + _split_artists(raw):
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
            total = sum(1 for t in tracks if (t.get("artist") or "").strip())
            new_tracks = total - known_tracks
            if not total:
                continue
            nr = new_tracks / total
            bell = max(0.1, 1 - abs(nr - 0.7) / 0.7)
            anchor = sum(sorted((k["affinity"] for k in known.values()),
                                reverse=True)[:3])
            audio = [a.get("url") for a in ep.get("audio_sources") or []
                     if a.get("url")]
            candidates.append({
                "cluster": cid, "tag_hits": tag_hits,
                "show": show.get("name", "").strip(),
                "show_alias": alias,
                "episode": ep.get("name", "").strip(),
                "episode_alias": ep_alias,
                "date": (ep.get("broadcast") or "")[:10],
                "url": f"https://www.nts.live/shows/{alias}/episodes/{ep_alias}",
                "audio_sources": audio,
                "tracks_total": total,
                "known_track_count": known_tracks,
                "new_track_count": new_tracks,
                "known_artists": sorted(known.values(),
                                        key=lambda k: -k["affinity"])[:8],
                "score": round(anchor * bell, 4),
            })
            break  # one episode per show is enough for the pool

    candidates.sort(key=lambda c: -c["score"])
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meta": {"shows_indexed": len(shows), "shows_polled": len(picked),
                 "tracklists_missing_or_short": tl_missing,
                 "candidates": len(candidates)},
        "candidates": candidates,
    }
    p = out_dir / "nts-harvest.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {p} — {len(candidates)} candidates "
          f"({tl_missing} tracklists missing/short)")
    for c in candidates[:8]:
        print(f"  {c['score']:6.3f} [{c['cluster']:16}] {c['show']} — "
              f"{c['date']} · {c['tracks_total']} tracks, "
              f"{c['known_track_count']} known / {c['new_track_count']} new")


if __name__ == "__main__":
    main()
