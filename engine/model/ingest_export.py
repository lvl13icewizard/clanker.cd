"""Turn a Spotify Extended Streaming History export into the cleaned history
the engine reads.

    python3 -m engine.model.ingest_export <export> [<export> ...] --out <dir>

<export> is a folder Spotify sent you (the one holding
Streaming_History_Audio_*.json), or the zip it arrived in. Several exports
merge; a record present in more than one is counted once. Podcast plays are
dropped. Nothing is uploaded and no IP address or device id is kept.

Writes to <dir>:
  plays.csv    one row per music play, chronological
  tracks.csv   per-track aggregates, sorted by play count
  artists.csv  per-artist aggregates, sorted by hours

Point SPOTIFY_CLEAN_DIR in .env at <dir> and the engine has its history.
"""

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

PLAYS_FIELDS = ["ts", "track", "artist", "album", "ms_played", "reason_start",
                "reason_end", "shuffle", "skipped", "platform", "track_uri"]


def platform_family(p):
    p = (p or "").lower()
    if not p:
        return "other"
    if "ios" in p or "iphone" in p or "ipad" in p:
        return "ios"
    if "os x" in p or "macos" in p or "osx" in p:
        return "mac"
    if "android" in p:
        return "android"
    if "web" in p or "chrome" in p or "browser" in p:
        return "web"
    if "windows" in p:
        return "windows"
    if "sonos" in p or "cast" in p or "google" in p or "home" in p:
        return "speaker"
    if "ps4" in p or "ps5" in p or "xbox" in p or "tv" in p:
        return "tv_console"
    return "other"


def _records(source):
    """Yield the raw records of every Streaming_History_Audio_*.json under
    a folder, or inside a zip."""
    src = Path(source)
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            names = sorted(n for n in z.namelist()
                           if Path(n).name.startswith("Streaming_History_Audio_") and n.endswith(".json"))
            for n in names:
                with z.open(n) as f:
                    yield from json.load(io.TextIOWrapper(f, encoding="utf-8"))
        return
    files = sorted(src.rglob("Streaming_History_Audio_*.json"))
    if not files:
        raise SystemExit(f"no Streaming_History_Audio_*.json under {src}")
    for p in files:
        with open(p, encoding="utf-8") as f:
            yield from json.load(f)


def clean(sources):
    rows, seen, dupes = [], set(), 0
    for source in sources:
        for r in _records(source):
            if not r.get("master_metadata_track_name"):
                continue  # podcasts, audiobooks, blanks
            ts = r["ts"]
            ms = int(r.get("ms_played") or 0)
            key = (ts, ms, r.get("spotify_track_uri"))
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            rows.append({
                "ts": ts,
                "track": r["master_metadata_track_name"],
                "artist": r.get("master_metadata_album_artist_name") or "",
                "album": r.get("master_metadata_album_album_name") or "",
                "ms_played": ms,
                "reason_start": r.get("reason_start") or "",
                "reason_end": r.get("reason_end") or "",
                "shuffle": r.get("shuffle"),
                "skipped": r.get("skipped"),
                "platform": platform_family(r.get("platform")),
                "track_uri": (r.get("spotify_track_uri") or "").replace("spotify:track:", ""),
            })
    rows.sort(key=lambda r: r["ts"])
    return rows, dupes


def hours(ms):
    return round(ms / 3_600_000, 1)


def write(rows, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "plays.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PLAYS_FIELDS)
        w.writeheader()
        w.writerows(rows)

    tracks = defaultdict(lambda: {"plays": 0, "ms": 0, "skips": 0, "done": 0,
                                  "first": "", "last": "", "album": "", "uri": ""})
    artists = defaultdict(lambda: {"plays": 0, "ms": 0, "skips": 0, "done": 0,
                                   "tracks": set(), "first": "", "last": ""})
    for r in rows:
        day = r["ts"][:10]
        t = tracks[(r["track"], r["artist"])]
        t["plays"] += 1
        t["ms"] += r["ms_played"]
        t["skips"] += 1 if r["skipped"] else 0
        t["done"] += 1 if r["reason_end"] == "trackdone" else 0
        t["first"] = t["first"] or day
        t["last"] = day
        t["album"], t["uri"] = r["album"], r["track_uri"]
        a = artists[r["artist"]]
        a["plays"] += 1
        a["ms"] += r["ms_played"]
        a["skips"] += 1 if r["skipped"] else 0
        a["done"] += 1 if r["reason_end"] == "trackdone" else 0
        a["tracks"].add(r["track"])
        a["first"] = a["first"] or day
        a["last"] = day

    with open(out / "tracks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["track", "artist", "album", "plays", "hours", "skip_rate",
                    "completion_rate", "first_played", "last_played", "track_uri"])
        for (track, artist), t in sorted(tracks.items(), key=lambda kv: -kv[1]["plays"]):
            w.writerow([track, artist, t["album"], t["plays"], hours(t["ms"]),
                        round(t["skips"] / t["plays"], 2), round(t["done"] / t["plays"], 2),
                        t["first"], t["last"], t["uri"]])
    with open(out / "artists.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["artist", "plays", "hours", "unique_tracks", "skip_rate",
                    "completion_rate", "first_played", "last_played"])
        for artist, a in sorted(artists.items(), key=lambda kv: -kv[1]["ms"]):
            w.writerow([artist, a["plays"], hours(a["ms"]), len(a["tracks"]),
                        round(a["skips"] / a["plays"], 2), round(a["done"] / a["plays"], 2),
                        a["first"], a["last"]])
    return len(tracks), len(artists)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sources", nargs="+", help="export folder(s) or zip(s)")
    ap.add_argument("--out", required=True, help="where the cleaned CSVs go (your SPOTIFY_CLEAN_DIR)")
    args = ap.parse_args(argv)
    rows, dupes = clean(args.sources)
    if not rows:
        raise SystemExit("no music plays found in the export")
    n_tracks, n_artists = write(rows, args.out)
    total = sum(r["ms_played"] for r in rows)
    print(f"{len(rows):,} plays from {rows[0]['ts'][:10]} to {rows[-1]['ts'][:10]} "
          f"({hours(total):,} hours), {n_tracks:,} tracks, {n_artists:,} artists; "
          f"{dupes:,} duplicate records skipped")
    print(f"wrote plays.csv, tracks.csv, artists.csv to {Path(args.out).resolve()}")
    print("next: set SPOTIFY_CLEAN_DIR in .env to that folder")
    return 0


if __name__ == "__main__":
    sys.exit(main())
