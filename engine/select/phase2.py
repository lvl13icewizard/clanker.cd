"""Phase 2 selection: Mixes, Critics Desk, Catalog Room.

Merges three new sections into out/selection-proposal.json (backing the file
up first). Deterministic given its inputs; every number it emits is computed
from the local data it cites.

the_mix       top MIX_PICKS candidates from out/nts-harvest.json with
              distinct clusters.
critics_desk  The Backfill: albums from the local Pitchfork corpus with
              score >= 8.6 (or BNM >= 8.3) in genres mapped to his lanes,
              by artists with ZERO plays in 11 years (near-matches skipped,
              never guessed), never served. Plus one "fresh" pick reviewed
              in the last 45 days of the corpus. Plus the module stat: how
              many of his top-40 artists Pitchfork has reviewed, and their
              average score.
catalog_room  the artist he hammers narrowly — high plays, few tracks, top-3
              concentration — with the unheard studio albums pulled from
              MusicBrainz (browse by artist MBID, official albums, no
              secondary types).

Run:  PYTHONPATH=<root> python3 -m engine.select.phase2
"""

import json
import math
import re
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..lib.config import load_config
from ..lib.http import get_json
from ..lib.history import artist_played, load_artists, near_artist_matches
from ..lib.lanes import GENRE_PRIORITY, ROCK_ERA_CUTOFF, rock_cluster
from ..lib.normalize import norm_artist, norm_title
from ..verify import repeat_guard
from ..verify import served as served_mod
from ..verify import served_policy

MIX_PICKS = 2
BACKFILL_PICKS = 5
BACKFILL_SCORE = 8.6
BACKFILL_SCORE_MAX = 9.7    # a Pitchfork 10.0 is nearly always a canonization
                            # reissue review — homework, not discovery
BACKFILL_MIN_YEAR = 1965    # his catalog love reaches back to ~1972; a 1956
                            # Glenn Gould record via the "experimental" genre
                            # bucket is a taxonomy accident, not a lane
BACKFILL_BNM_SCORE = 8.3
FRESH_DAYS = 45
FRESH_MIN_SCORE = 7.8
PER_CLUSTER_CAP = 2
# comp/live/box formats reviewed at canon scores masquerade as albums
FORMAT_BLOCKLIST = re.compile(
    r"\b(singles|live at|live in|anthology|collection|box set|b-sides|"
    r"greatest hits|complete|sessions|variations|remaster)\b", re.I)

CATALOG_MIN_PLAYS = 250
CATALOG_MIN_HOURS = 8.0
CATALOG_MAX_TRACKS = 45
CATALOG_MIN_TOP3 = 0.28
CATALOG_MIN_UNHEARD = 1   # one unopened album from a deep devotion IS the
                          # room — issue 001's Dire Straits story. Two was
                          # killing every candidate: the concentration gates
                          # select narrow-catalog artists by design.
CATALOG_MAX_TRACKS_WIDE = 70

# The backfill leans toward the roots of the rooms he actually lives in:
# an album's score is weighted by its lane's share of lifetime hours, so a
# 9.6 in a 100-hour lane no longer outranks a 9.0 at the heart of a
# 500-hour one. This bakes in the issue-002 hand-overrule ("canonisation
# reissue is homework, not discovery") structurally.
LANE_WEIGHT_FLOOR = 0.85

GENRE_TO_CLUSTER = {
    "rap": "underground-rap",
    "jazz": "jazz-bridge",
    "electronic": "beats-idm",
    "experimental": "beats-idm",
    "rock": "punk-turn",
    "global": "cosmic-groove",
}

MB = "https://musicbrainz.org/ws/2"
MB_RATE = {"rate_key": "musicbrainz", "min_interval": 1.1}


def _exposures(cfg):
    served = served_mod.load_or_build()
    return served, served_policy.exposures(served, cfg["ISSUES_DIR"])


# ------------------------------------------------------------------ the mix

MIX_MIN_TRACKS = 15     # under this, it's a playlist, not a broadcast hour
MIX_RECENCY = ((2024, 1.0), (2020, 0.85), (0, 0.7))


def select_mix(cfg):
    # One pool across every station harvest that exists. Candidates share a
    # shape and a scoring formula, so they compete fairly.
    cands, missing = [], []
    for fname in ("nts-harvest.json", "kexp-harvest.json", "mixesdb-harvest.json"):
        fp = Path(cfg["OUT_DIR"]) / fname
        if fp.exists():
            cands.extend(json.loads(fp.read_text()).get("candidates", []))
        else:
            missing.append(fname)
    if not cands:
        return [], ["no mix harvests found — run engine.harvest.nts/kexp/mixesdb"]

    def adj(c):
        year = int(c["date"][:4]) if (c.get("date") or "")[:4].isdigit() else 0
        mult = next(m for y, m in MIX_RECENCY if year >= y)
        return c["score"] * mult

    ranked = sorted(cands, key=adj, reverse=True)

    def ok(c):
        return c["known_track_count"] >= 2 and c["tracks_total"] >= MIX_MIN_TRACKS

    # Two passes: first prefer distinct stations (two hours from two rooms
    # reads as range, not a rut), then fill from anywhere if needed.
    picks, seen_clusters, seen_shows, seen_stations = [], set(), set(), set()
    for require_new_station in (True, False):
        for c in ranked:
            if len(picks) >= MIX_PICKS:
                break
            if c["cluster"] in seen_clusters or c["show_alias"] in seen_shows:
                continue
            if require_new_station and c.get("station", "NTS") in seen_stations:
                continue
            if not ok(c):
                continue
            picks.append(c)
            seen_clusters.add(c["cluster"])
            seen_shows.add(c["show_alias"])
            seen_stations.add(c.get("station", "NTS"))
    notes = [f"mix harvests absent: {', '.join(missing)}"] if missing else []
    return picks, notes


# -------------------------------------------------------------- critics desk

def _rows(cfg):
    """Yield unified review rows from both local Pitchfork DBs."""
    # Both databases are optional (config.py: "everything else degrades
    # gracefully"), but this indexed them directly and a clean install
    # died here with a KeyError. Absent means no rows, and the Critics
    # Desk reports itself empty rather than taking the press down.
    scraped_cfg = cfg.get("PITCHFORK_SCRAPED_DB")
    kaggle_cfg = cfg.get("PITCHFORK_KAGGLE_DB")
    scraped = Path(scraped_cfg) if scraped_cfg else None
    kaggle = Path(kaggle_cfg) if kaggle_cfg else None
    if scraped is not None and scraped.exists():
        con = sqlite3.connect(str(scraped))
        for a, t, s, bnm, g, y, u, d in con.execute(
                "SELECT artist,title,score,best_new_music,genres,"
                "release_year,url,pub_date FROM reviews"):
            yield {"artist": a or "", "title": t or "", "score": s,
                   "bnm": bool(bnm), "genres": (g or "").lower(),
                   "year": y, "url": u, "pub_date": (d or "")[:10]}
        con.close()
    if kaggle is not None and kaggle.exists():
        con = sqlite3.connect(str(kaggle))
        for a, t, s, bnm, u, y, rid in con.execute(
                "SELECT r.artist, r.title, r.score, r.best_new_music, r.url,"
                " r.pub_year, r.reviewid FROM reviews r"):
            gs = [g for (g,) in con.execute(
                "SELECT genre FROM genres WHERE reviewid=?", (rid,)) if g]
            # RELEASE year lives in the years join table; pub_year is when
            # the review ran. Conflating them printed review dates as album
            # years ("Critical Beatdown (2004)").
            ys = [yy for (yy,) in con.execute(
                "SELECT year FROM years WHERE reviewid=?", (rid,))
                if yy is not None]
            yield {"artist": a or "", "title": t or "", "score": s,
                   "bnm": bool(bnm), "genres": ",".join(gs).lower(),
                   "year": min(ys) if ys else None, "url": u,
                   "pub_date": f"{y}-01-01"}
        con.close()


def _cluster_for_genres(genres, pub_date=""):
    """Lane for a review's genre string, most specific genre first.

    Order and the rock rule are shared with the catalogue harvest; see
    engine.lib.lanes. Iterating GENRE_TO_CLUSTER's own order used to put
    "experimental" ahead of "rock", which filed rock records under Beats & IDM.
    """
    for key in GENRE_PRIORITY:
        if key in (genres or ""):
            if key == "rock":
                return rock_cluster((pub_date or "") >= ROCK_ERA_CUTOFF)
            return GENRE_TO_CLUSTER[key]
    return None


def _lane_hours_weight(cfg):
    """cluster id -> 0..1 share of the largest lane's lifetime hours."""
    mp = Path(cfg["OUT_DIR"]) / "taste-model.json"
    if not mp.exists():
        return {}
    hours = {}
    for c in json.loads(mp.read_text()).get("clusters", []):
        cid = c.get("id") or c.get("cluster")
        h = c.get("lifetime_hours") or c.get("hours")
        if h is None:
            h = sum(float(m.get("hours") or 0) for m in c.get("members", []))
        if cid:
            hours[cid] = float(h)
    top = max(hours.values(), default=0)
    return {cid: h / top for cid, h in hours.items()} if top else {}


def select_critics(cfg):
    served, exps = _exposures(cfg)
    guard = repeat_guard.build_guard(served=served, issues_dir=cfg["ISSUES_DIR"])
    served_albums = served_policy.pairs_within(
        exps, {"critics_desk", "front_to_back"}, served_policy.ALBUM_COOLDOWN_DAYS)
    notes = []
    lane_w = _lane_hours_weight(cfg)
    max_pub = ""
    pool = []
    for r in _rows(cfg):
        if not r["artist"] or r["score"] is None:
            continue
        if r["pub_date"] > max_pub:
            max_pub = r["pub_date"]
        cid = _cluster_for_genres(r["genres"], r["pub_date"])
        if not cid:
            continue
        year = r.get("year")
        if isinstance(year, str) and year.isdigit():
            year = int(year)
        if not isinstance(year, int) or year < BACKFILL_MIN_YEAR:
            continue
        if r["score"] > BACKFILL_SCORE_MAX:
            continue
        if FORMAT_BLOCKLIST.search(r["title"] or ""):
            continue
        good = r["score"] >= BACKFILL_SCORE or \
            (r["bnm"] and r["score"] >= BACKFILL_BNM_SCORE)
        if good:
            pool.append((cid, r))

    fresh_cut = ""
    if max_pub:
        d = datetime.strptime(max_pub, "%Y-%m-%d") - timedelta(days=FRESH_DAYS)
        fresh_cut = d.strftime("%Y-%m-%d")

    def eligible(r):
        na = norm_artist(r["artist"])
        if artist_played(r["artist"]):
            return False
        # Artist offered as a discovery and not yet played: sits out the
        # cooldown; played since: blocked. Announced in New This Week or
        # named in a mix: no bearing (audit F16).
        if guard.status(r["artist"])["state"] != "clear":
            return False
        if (na, norm_title(r["title"] or "")) in served_albums:
            return False
        # round two: a plausible near-name means we skip, never guess
        if near_artist_matches(r["artist"], limit=1):
            return False
        return True

    # dedupe (artist,title) keeping the best-scored row
    best = {}
    for cid, r in pool:
        k = (norm_artist(r["artist"]), norm_title(r["title"]))
        if k not in best or r["score"] > best[k][1]["score"]:
            best[k] = (cid, r)

    def adj(cid, r):
        w = lane_w.get(cid, 0.5)
        return r["score"] * (LANE_WEIGHT_FLOOR + (1 - LANE_WEIGHT_FLOOR) * w)

    ranked = sorted(best.values(),
                    key=lambda cr: (-adj(cr[0], cr[1]), cr[1]["artist"]))
    picks, per_cluster, used_artists = [], {}, set()
    fresh_pick = None
    for cid, r in ranked:
        na = norm_artist(r["artist"])
        if na in used_artists or not eligible(r):
            continue
        entry = {**r, "cluster": cid}
        is_fresh = fresh_cut and r["pub_date"] >= fresh_cut and \
            r["score"] >= FRESH_MIN_SCORE
        if is_fresh and fresh_pick is None:
            fresh_pick = {**entry, "fresh": True}
            used_artists.add(na)
            continue
        if per_cluster.get(cid, 0) >= PER_CLUSTER_CAP:
            continue
        picks.append(entry)
        per_cluster[cid] = per_cluster.get(cid, 0) + 1
        used_artists.add(na)
        if len(picks) >= BACKFILL_PICKS:
            break
    if fresh_pick:
        picks.insert(0, fresh_pick)
    else:
        notes.append(f"no fresh pick in the last {FRESH_DAYS} days of corpus")

    # module stat: his top-40 artists vs the corpus
    top40 = sorted(load_artists().values(),
                   key=lambda r: -float(r["hours"]))[:40]
    by_artist = {}
    for r in _rows(cfg):
        if r["score"] is None:
            continue
        by_artist.setdefault(norm_artist(r["artist"]), []).append(r["score"])
    reviewed, means = 0, []
    for row in top40:
        scores = by_artist.get(norm_artist(row["artist"]))
        if scores:
            reviewed += 1
            means.append(sum(scores) / len(scores))
    avg = round(sum(means) / len(means), 1) if means else None
    stats = {"top40_reviewed": reviewed, "top40_avg_score": avg,
             "corpus_through": max_pub}
    return picks, stats, notes


# -------------------------------------------------------------- catalog room

def _mb_artist_mbid(name):
    q = urllib.parse.quote(f'artist:"{name}"')
    d = get_json(f"{MB}/artist?query={q}&fmt=json&limit=5",
                 ttl_days=30, **MB_RATE)
    want = name.strip().lower()
    for a in d.get("artists", []):
        if (a.get("name") or "").strip().lower() == want and \
                int(a.get("score", 0)) >= 90:
            return a["id"], a["name"]
    return None, None


def _mb_albums(mbid):
    d = get_json(f"{MB}/release-group?artist={mbid}&type=album"
                 f"&limit=100&fmt=json", ttl_days=30, **MB_RATE)
    out = []
    for rg in d.get("release-groups", []):
        if (rg.get("primary-type") or "") != "Album":
            continue
        if rg.get("secondary-types"):
            continue  # no live/comp/remix/soundtrack
        year = (rg.get("first-release-date") or "")[:4]
        out.append({"title": rg.get("title", ""),
                    "year": int(year) if year.isdigit() else None})
    out.sort(key=lambda a: (a["year"] is None, a["year"] or 0))
    return out


def select_catalog(cfg):
    _, exps = _exposures(cfg)
    served_catalog = served_policy.artists_within(
        exps, {"catalog_room"}, served_policy.CATALOG_COOLDOWN_DAYS)
    notes = []
    # per-artist track concentration from tracks.csv
    import csv
    per = {}
    with open(Path(cfg["SPOTIFY_CLEAN_DIR"]) / "tracks.csv", newline="") as f:
        for row in csv.DictReader(f):
            na = norm_artist(row["artist"])
            e = per.setdefault(na, {"plays": [], "albums": set(),
                                    "raw": row["artist"]})
            e["plays"].append(int(float(row["plays"])))
            if row.get("album"):
                e["albums"].add(norm_title(row["album"]))

    cands = []
    for na, row in load_artists().items():
        plays = int(float(row["plays"]))
        hours = float(row["hours"])
        n_tracks = int(float(row["unique_tracks"]))
        if plays < CATALOG_MIN_PLAYS or hours < CATALOG_MIN_HOURS:
            continue
        if n_tracks > CATALOG_MAX_TRACKS_WIDE or na in served_catalog:
            continue
        e = per.get(na)
        if not e or len(e["plays"]) < 3:
            continue
        top3 = sum(sorted(e["plays"], reverse=True)[:3]) / max(1, plays)
        if top3 < CATALOG_MIN_TOP3:
            continue
        h = min(1.0, math.log1p(hours) / math.log1p(60.0))
        cands.append({
            "artist": row["artist"], "norm": na, "plays": plays,
            "hours": round(hours, 1), "unique_tracks": n_tracks,
            "top3_share": round(top3, 2),
            "skip_rate": float(row["skip_rate"]),
            "heard_albums": sorted(e["albums"]),
            "score": round(h * top3, 4),
        })
    cands.sort(key=lambda c: -c["score"])
    if not cands:
        return None, ["no catalog-room candidate met the thresholds"]

    # catalog-complete artists (side projects with one album, artists whose
    # every record he has touched) burn slots — probe deep enough to get past
    # them, at one polite MB request pair per candidate
    for cand in cands[:20]:
        mbid, mb_name = _mb_artist_mbid(cand["artist"])
        if not mbid:
            notes.append(f"MB: no confident match for {cand['artist']!r}")
            continue
        albums = _mb_albums(mbid)
        heard = set(cand["heard_albums"])
        unheard = [a for a in albums
                   if a["title"] and norm_title(a["title"]) not in heard]
        if len(unheard) < CATALOG_MIN_UNHEARD:
            notes.append(f"{cand['artist']}: only {len(unheard)} unheard "
                         f"albums on MB — skipped")
            continue
        heard_titles = [a["title"] for a in albums
                        if norm_title(a["title"]) in heard]
        cand.pop("norm")
        cand.pop("heard_albums")
        cand["mbid"] = mbid
        cand["unheard"] = unheard
        cand["heard_on_record"] = heard_titles
        return cand, notes
    return None, notes + ["no candidate produced enough unheard albums"]


# --------------------------------------------------------------------- main

def main():
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])
    pp = out_dir / "selection-proposal.json"
    proposal = json.loads(pp.read_text()) if pp.exists() else {}
    (out_dir / "selection-proposal.pre-phase2.bak.json").write_text(
        json.dumps(proposal, indent=1, ensure_ascii=False))

    mix, mix_notes = select_mix(cfg)
    critics, critic_stats, critic_notes = select_critics(cfg)
    catalog, catalog_notes = select_catalog(cfg)

    proposal["the_mix"] = mix
    proposal["critics_desk"] = {"albums": critics, "stats": critic_stats}
    proposal["catalog_room"] = catalog
    meta = proposal.setdefault("meta", {})
    meta["phase2_generated_at"] = datetime.now(
        timezone.utc).isoformat(timespec="seconds")
    meta.setdefault("notes", [])
    meta["notes"].extend(mix_notes + critic_notes + catalog_notes)

    pp.write_text(json.dumps(proposal, indent=1, ensure_ascii=False))
    print(f"the_mix: {len(mix)} picks")
    for m in mix:
        print(f"   [{m['cluster']}] {m['show']} — {m['date']} · "
              f"{m['tracks_total']} tracks, {m['known_track_count']} known")
    print(f"critics_desk: {len(critics)} albums · stats {critic_stats}")
    for c in critics:
        print(f"   {c['score']:.1f}{' BNM' if c['bnm'] else ''} "
              f"[{c['cluster']}] {c['artist']} — {c['title']} "
              f"({c.get('year')}){' FRESH' if c.get('fresh') else ''}")
    if catalog:
        print(f"catalog_room: {catalog['artist']} — {catalog['plays']} plays "
              f"across {catalog['unique_tracks']} tracks, top-3 share "
              f"{catalog['top3_share']}, {len(catalog['unheard'])} unheard")
    if mix_notes + critic_notes + catalog_notes:
        print("notes:", mix_notes + critic_notes + catalog_notes)


if __name__ == "__main__":
    main()
