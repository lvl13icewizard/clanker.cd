"""Catalog pool from the two local Pitchfork sqlite DBs.

Sources (paths from .env, both optional — skip cleanly when absent):
  PITCHFORK_SCRAPED_DB  reviews(slug, url, artist, title, score, best_new_music,
                        best_new_reissue, genres, label, release_year, author,
                        pub_date, dek, body, scraped_at) — covers 2017→present,
                        genres as a comma-separated string ("Electronic, Rock").
  PITCHFORK_KAGGLE_DB   reviews(reviewid, title, artist, url, score,
                        best_new_music, author, pub_date, ...) + genres(reviewid,
                        genre lowercase) + years(reviewid, year) — 1999→2017-01.

Filter: score >= 8.2 OR best_new_music, genres intersecting
{Electronic, Jazz, Rap, Experimental, Rock, Global}. Dedupe across DBs on
(norm_artist, norm_title), scraped wins (richer row). Cap ~400 preferring
post-2010 (300) plus a slice of classics (100).

Genre -> cluster_hint (crude by design; null when unsure is fine):
  Jazz -> jazz-bridge, Rap -> underground-rap, Global -> cosmic-groove,
  Experimental -> beats-idm, Rock -> punk-turn,
  Electronic -> beats-idm | club-continuum | french-electronic via keyword
  rules on the dek (else null; when Electronic is present but unresolved we
  do NOT fall through to Rock/Experimental hints).
"""

import re
import sqlite3

from engine.lib.config import load_config
from engine.lib.lanes import GENRE_PRIORITY, rock_cluster
from engine.lib.normalize import norm_artist, norm_title

MIN_SCORE = 8.2
GENRES = {"electronic", "jazz", "rap", "experimental", "rock", "global"}
CAP_POST2010 = 300
CAP_CLASSICS = 100

_SIMPLE_HINT = {
    "jazz": "jazz-bridge",
    "rap": "underground-rap",
    "global": "cosmic-groove",
    "experimental": "beats-idm",
}
# Order and the rock rule are shared with the Critics Desk; see
# engine.lib.lanes. Electronic still sits before Rock/Experimental so an
# unresolved Electronic blocks their hints (an Electronic-tagged record is
# probably not a punk-turn lead).

_FRENCH = re.compile(r"\bfrench touch\b|\bfilter house\b|\bed banger\b|\bfrench house\b", re.I)
_CLUB = re.compile(
    r"\bhouse\b|\btechno\b|\bclub\b|\bgarage\b|\bjungle\b|\bfootwork\b|"
    r"\bdancefloor\b|\brave\b|\bdubstep\b|\bgrime\b|\bdrum\s?['n&]+\s?bass\b", re.I)
_BEATS = re.compile(
    r"\bidm\b|\bbraindance\b|\bglitch\b|\bbeat scene\b|\binstrumental hip-?hop\b|"
    r"\btrip-?hop\b|\bdowntempo\b|\bbeat tape\b", re.I)


def _electronic_hint(text):
    if not text:
        return None
    if _FRENCH.search(text):
        return "french-electronic"
    if _CLUB.search(text):
        return "club-continuum"
    if _BEATS.search(text):
        return "beats-idm"
    return None


def cluster_hint(genres, dek=None, modern=False):
    """genres: iterable of lowercase genre names.

    `modern` says the review comes from Pitchfork's scraped era, which is what
    decides where a rock record lands. The Critics Desk decides it the same
    way; both read engine.lib.lanes.
    """
    gs = {g.strip().lower() for g in genres if g and g.strip()}
    for g in GENRE_PRIORITY:
        if g not in gs:
            continue
        if g == "electronic":
            return _electronic_hint(dek)  # unresolved Electronic -> null, stop
        if g == "rock":
            return rock_cluster(modern)
        return _SIMPLE_HINT[g]
    return None


def _from_scraped(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT artist, title, score, best_new_music, genres, release_year,"
        " author, url, dek FROM reviews"
        " WHERE artist IS NOT NULL AND title IS NOT NULL"
        " AND (score >= ? OR best_new_music = 1)", (MIN_SCORE,)).fetchall()
    con.close()
    out = []
    for r in rows:
        genres = [g.strip().lower() for g in (r["genres"] or "").split(",")]
        if not (set(genres) & GENRES):
            continue
        out.append({
            "artist": r["artist"], "title": r["title"],
            "year": r["release_year"],
            "source": "pitchfork_catalog", "cluster_hint": cluster_hint(genres, r["dek"], modern=True),
            "p4k": {"score": r["score"], "bnm": bool(r["best_new_music"]),
                    "url": r["url"], "author": r["author"], "dek": r["dek"]},
            "release_date": None, "via": None,
        })
    return out


def _from_kaggle(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT r.reviewid, r.artist, r.title, r.score, r.best_new_music,"
        " r.author, r.url, MIN(y.year) AS year,"
        " GROUP_CONCAT(DISTINCT g.genre) AS genres"
        " FROM reviews r"
        " JOIN genres g ON g.reviewid = r.reviewid"
        " LEFT JOIN years y ON y.reviewid = r.reviewid"
        " WHERE r.artist IS NOT NULL AND r.title IS NOT NULL"
        " AND (r.score >= ? OR r.best_new_music = 1)"
        " GROUP BY r.reviewid", (MIN_SCORE,)).fetchall()
    con.close()
    out = []
    for r in rows:
        genres = [g.strip().lower() for g in (r["genres"] or "").split(",")]
        if not (set(genres) & GENRES):
            continue
        out.append({
            # kaggle artist/title are lowercased in the dump; emit as-is
            # (normalization downstream is case-insensitive anyway).
            "artist": r["artist"], "title": r["title"],
            "year": r["year"],
            "source": "pitchfork_catalog", "cluster_hint": cluster_hint(genres, None, modern=False),
            "p4k": {"score": r["score"], "bnm": bool(r["best_new_music"]),
                    "url": r["url"], "author": r["author"], "dek": None},
            "release_date": None, "via": None,
        })
    return out


def harvest(limit=None):
    """Return ({"album_candidates": [...]}, status)."""
    cfg = load_config()
    pools, parts = [], []
    scraped, kaggle = cfg.get("PITCHFORK_SCRAPED_DB"), cfg.get("PITCHFORK_KAGGLE_DB")
    if scraped:
        pools.append(_from_scraped(scraped))
        parts.append("scraped")
    if kaggle:
        pools.append(_from_kaggle(kaggle))
        parts.append("kaggle")
    if not pools:
        return {"album_candidates": []}, "skipped: no pitchfork DBs configured"

    # Dedupe across DBs; scraped listed first wins.
    seen, merged = set(), []
    for pool in pools:
        for c in pool:
            k = (norm_artist(c["artist"]), norm_title(c["title"]))
            if k in seen:
                continue
            seen.add(k)
            merged.append(c)

    def rank(c):
        return (-int(c["p4k"]["bnm"]), -(c["p4k"]["score"] or 0),
                norm_artist(c["artist"]), norm_title(c["title"]))

    post2010 = sorted([c for c in merged if c["year"] and c["year"] >= 2010], key=rank)
    classics = sorted([c for c in merged if not c["year"] or c["year"] < 2010], key=rank)
    cap_a, cap_b = CAP_POST2010, CAP_CLASSICS
    picked = post2010[:cap_a] + classics[:cap_b]
    # Top up either bucket from the other if short.
    total = cap_a + cap_b
    if len(picked) < total:
        extra = post2010[cap_a:] + classics[cap_b:]
        picked += extra[: total - len(picked)]
    if limit:
        picked = picked[:limit]
    status = "ok: %d candidates (dbs: %s; pool %d)" % (len(picked), "+".join(parts), len(merged))
    return {"album_candidates": picked}, status


if __name__ == "__main__":
    payload, status = harvest()
    print(status)
    for c in payload["album_candidates"][:10]:
        print(" ", c["artist"], "—", c["title"], c["year"], c["cluster_hint"], c["p4k"]["score"])
