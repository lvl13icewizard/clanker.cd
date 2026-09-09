"""Load the cleaned listening history and answer played/never-played queries.

Sources (from SPOTIFY_CLEAN_DIR):
  artists.csv  artist,plays,hours,unique_tracks,skip_rate,completion_rate,first_played,last_played
  tracks.csv   track,artist,album,plays,hours,skip_rate,completion_rate,first_played,last_played,track_uri
  plays.csv    ts,track,artist,album,ms_played,reason_start,reason_end,shuffle,skipped,platform,track_uri

Fresh overlay (OUT_DIR/fresh-listens.json, engine.model.fresh_listens):
listens since the export's last event. Merged into the artist and track
tables here, so every reader — verification, the model, the seeds, phase 2
— sees the same history. An overlay built against a different export is
ignored. Plays and dates move; hours never do (no duration is recorded).
"""

import csv
import json
from pathlib import Path

from .config import load_config
from .normalize import norm_artist, norm_title, track_key

_cache = {}
_fresh_override = None
FRESH_FILE = "fresh-listens.json"


def _clean_dir():
    return Path(load_config()["SPOTIFY_CLEAN_DIR"])


def tail_last_play_ts():
    """Timestamp of the final plays.csv row (the file is chronological), or
    None when there is no play log. Cheap: reads the last 4 KB."""
    try:
        p = _clean_dir() / "plays.csv"
        with open(p, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode("utf-8", errors="replace").strip().splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    ts = lines[-1].split(",", 1)[0]
    return ts if ts[:2] in ("19", "20") else None


def set_fresh(doc):
    """Tests: use this overlay document (or None for none) instead of the
    file. Clears the loaded tables so they are rebuilt with it."""
    global _fresh_override
    _fresh_override = doc if doc is not None else {"listens": [], "_off": True}
    _cache.clear()


def fresh_overlay():
    """The overlay document, or None when absent or built for another export."""
    if "fresh" in _cache:
        return _cache["fresh"]
    doc = None
    if _fresh_override is not None:
        doc = None if _fresh_override.get("_off") else _fresh_override
    else:
        p = Path(load_config()["OUT_DIR"]) / FRESH_FILE
        if p.exists():
            try:
                doc = json.loads(p.read_text())
            except ValueError:
                doc = None
        if doc and doc.get("export_cutoff") != tail_last_play_ts():
            doc = None
    _cache["fresh"] = doc
    return doc


def fresh_summary():
    doc = fresh_overlay()
    if not doc:
        return {"listens": 0, "watermark": None, "export_cutoff": None}
    return {"listens": len(doc.get("listens") or []),
            "watermark": doc.get("watermark"),
            "export_cutoff": doc.get("export_cutoff")}


def _fresh_by_artist():
    """norm artist -> {artist, plays, first, last, tracks: {norm title ->
    {track, album, plays, first, last}}} from the overlay."""
    if "fresh_artists" in _cache:
        return _cache["fresh_artists"]
    out = {}
    for r in (fresh_overlay() or {}).get("listens") or []:
      # A joined credit counts for every artist on it (the export names
      # the primary artist; the feature is on the record all the same).
      for name in (r.get("artists") or [r.get("artist")]):
        na = norm_artist(name or "")
        if not na:
            continue
        d = str(r.get("ts") or "")[:10]
        a = out.setdefault(na, {"artist": name, "plays": 0,
                                "first": d, "last": d, "tracks": {}})
        a["plays"] += 1
        a["first"] = min(a["first"], d)
        a["last"] = max(a["last"], d)
        nt = norm_title(r.get("title") or "")
        if nt:
            t = a["tracks"].setdefault(nt, {"track": r["title"], "album": r.get("release") or "",
                                            "plays": 0, "first": d, "last": d})
            t["plays"] += 1
            t["first"] = min(t["first"], d)
            t["last"] = max(t["last"], d)
    _cache["fresh_artists"] = out
    return out


def _overlay_artists(d):
    for na, a in _fresh_by_artist().items():
        row = d.get(na)
        if row is None:
            # Rates are unknown for an overlay-only artist (no duration is
            # recorded); "0" keeps every float() consumer working and the
            # fresh_plays/source fields say where the row came from.
            d[na] = {"artist": a["artist"], "plays": str(a["plays"]), "hours": "0",
                     "unique_tracks": str(len(a["tracks"])), "skip_rate": "0",
                     "completion_rate": "0", "first_played": a["first"],
                     "last_played": a["last"], "fresh_plays": str(a["plays"]),
                     "source": "listenbrainz"}
            continue
        row["plays"] = _fmt((_num(row.get("plays")) or 0) + a["plays"])
        row["last_played"] = max(row.get("last_played") or "", a["last"])
        if not row.get("first_played"):
            row["first_played"] = a["first"]
        row["fresh_plays"] = str(a["plays"])


def _overlay_tracks(d):
    for na, a in _fresh_by_artist().items():
        for nt, t in a["tracks"].items():
            row = d.get((na, nt))
            if row is None:
                d[(na, nt)] = {"track": t["track"], "artist": a["artist"],
                               "album": t["album"], "plays": str(t["plays"]),
                               "hours": "0", "skip_rate": "0", "completion_rate": "0",
                               "first_played": t["first"], "last_played": t["last"],
                               "track_uri": "", "fresh_plays": str(t["plays"]),
                               "source": "listenbrainz"}
                continue
            row["plays"] = _fmt((_num(row.get("plays")) or 0) + t["plays"])
            row["last_played"] = max(row.get("last_played") or "", t["last"])
            row["fresh_plays"] = str(t["plays"])


_SUM = ("plays", "hours", "unique_tracks")
_WEIGHTED = ("skip_rate", "completion_rate")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(x):
    return str(int(x)) if float(x).is_integer() else f"{x:.6g}"


def _fold_rows(into, row, name_key):
    """Aggregate a second CSV row with the same normalized key into the
    first, instead of overwriting it. Two rows share a key when the export
    spelt one act two ways ("Fred again.." / "Fred Again..") or when the
    old normalizer emptied a non-Latin name; either way, keeping the last
    row made the statistics depend on file order and threw the rest away.
    Sums add, dates take the extremes, rates are plays-weighted, and the
    raw name of the busier row is the one kept. Every merge is recorded so
    a wrong one can be seen rather than silently believed."""
    a_p, b_p = _num(into.get("plays")) or 0.0, _num(row.get("plays")) or 0.0
    for k in _SUM:
        x, y = _num(into.get(k)), _num(row.get(k))
        if x is not None or y is not None:
            into[k] = _fmt((x or 0.0) + (y or 0.0))
    for k in _WEIGHTED:
        x, y = _num(into.get(k)), _num(row.get(k))
        if x is not None and y is not None and (a_p + b_p) > 0:
            into[k] = _fmt((x * a_p + y * b_p) / (a_p + b_p))
        elif x is None and y is not None:
            into[k] = row[k]
    if row.get("first_played") and (not into.get("first_played")
                                    or row["first_played"] < into["first_played"]):
        into["first_played"] = row["first_played"]
    if row.get("last_played") and (not into.get("last_played")
                                   or row["last_played"] > into["last_played"]):
        into["last_played"] = row["last_played"]
    if b_p > a_p:
        into[name_key] = row[name_key]
    for k in ("track_uri", "album"):
        if not into.get(k) and row.get(k):
            into[k] = row[k]


def _load_grouped(filename, keyfn, name_key, merges):
    d = {}
    with open(_clean_dir() / filename, newline="") as f:
        for row in csv.DictReader(f):
            k = keyfn(row)
            if k in d:
                merges.setdefault(k, [d[k][name_key]])
                if row[name_key] not in merges[k]:
                    merges[k].append(row[name_key])
                _fold_rows(d[k], row, name_key)
            else:
                d[k] = dict(row)
    return d


def load_artists():
    """dict: normalized artist -> row dict (raw name kept under 'artist').
    Rows sharing a key are aggregated, never overwritten; see _fold_rows."""
    if "artists" not in _cache:
        merges = {}
        d = _load_grouped(
            "artists.csv", lambda r: norm_artist(r["artist"]), "artist", merges)
        _overlay_artists(d)
        _cache["artists"] = d
        _cache["artist_merges"] = merges
    return _cache["artists"]


def load_tracks():
    """dict: (norm_artist, norm_title) -> row dict, aggregated on key."""
    if "tracks" not in _cache:
        merges = {}
        d = _load_grouped(
            "tracks.csv", lambda r: track_key(r["artist"], r["track"]), "track", merges)
        _overlay_tracks(d)
        by_title = {}
        for k, row in d.items():
            by_title.setdefault(k[1], []).append(row)
        _cache["tracks"] = d
        _cache["by_title"] = by_title
        _cache["track_merges"] = merges
    return _cache["tracks"]


def merges():
    """What the loaders folded together: {key: [raw names]} for artists
    and for tracks. Inspect this after a normalizer change."""
    load_artists(); load_tracks()
    return {"artists": _cache["artist_merges"], "tracks": _cache["track_merges"]}


def reset():
    """Drop the loaded caches and any test overlay (tests point
    SPOTIFY_CLEAN_DIR elsewhere; set_fresh after reset to inject one)."""
    global _fresh_override
    _fresh_override = None
    _cache.clear()


def title_collisions(title):
    """All played tracks sharing this normalized title, any artist."""
    load_tracks()
    return _cache["by_title"].get(norm_title(title), [])


def artist_played(name):
    return load_artists().get(norm_artist(name))


def track_played(artist, title):
    return load_tracks().get(track_key(artist, title))


def near_artist_matches(name, limit=8):
    """Round-two ammunition: substring containment either way, normalized."""
    n = norm_artist(name)
    if not n:
        return []
    out = []
    for k, row in load_artists().items():
        if n == k:
            continue
        if (len(n) > 3 and n in k) or (len(k) > 3 and k in n):
            out.append(row)
            if len(out) >= limit:
                break
    return out


def iter_plays():
    """Lazy row iterator over the full play log (161k rows)."""
    with open(_clean_dir() / "plays.csv", newline="") as f:
        yield from csv.DictReader(f)


def stats():
    return {"artists": len(load_artists()), "tracks": len(load_tracks())}
