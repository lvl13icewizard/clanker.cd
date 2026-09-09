"""Label model: the record labels the reader actually lives on.

Similarity engines describe sound. Labels describe curation: who signed
whom, which scene a record came out of. A reader with 60 hours on Ghostly
International has a relationship with the label's taste that "sounds like
Tycho" cannot express, and the label's roster is a pool the similarity
engines never surface once the first ring is used up.

Built from MusicBrainz (free, 1.1 s per request, URL-cached for 30 days so
the weekly run is cheap after the first):

  1. For the top TOP_ARTISTS artists by hours, browse their official
     releases with label info. An artist's hours are split across their
     labels by share of releases, so Tycho's 46 hours land mostly on
     Ghostly, some on Ninja Tune and Mom+Pop.
  2. Sum per label: hours, the artists behind them, the lanes those artists
     belong to. Majors, distributors, "[no label]" and self-releases are
     excluded (MAJORS): a roster of a hundred thousand records is not a
     scene.
  3. For the top ROSTER_LABELS labels, browse the catalogue (up to
     ROSTER_PAGES pages of 100) into a roster: artist, releases on the
     label, first and last release date. Browse order is catalogue order,
     so a big label's first pages are its earliest era; catalogues larger
     than the window are topped up with a dated search over the last
     RECENT_YEARS (RECENT_PAGES pages). Labels over ROSTER_MAX_RELEASES
     are kept as signal but not expanded.

Writes out/label-model.json:
  {"generated_at", "artists_scanned", "labels": [{name, mbid, hours,
    artists: [{artist, hours, share, releases}], lanes: {cid: hours},
    release_count, roster: [{artist, mbid, releases, first_date, last_date}]
    | roster_status}]}

Run:  PYTHONPATH=<root> python3 -m engine.model.build_label_model [--top N]
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from ..harvest.musicbrainz import MB_ROOT, resolve_artist_mbid
from ..lib import http, names
from ..lib.config import load_config
from ..lib.normalize import norm_artist

TOP_ARTISTS = 250
LABELS_KEEP = 40
ROSTER_LABELS = 25
ROSTER_PAGES = 8
ROSTER_MAX_RELEASES = 4000
RECENT_PAGES = 3
RECENT_YEARS = 10
MB_RATE = {"rate_key": "musicbrainz", "min_interval": 1.1}

MAJORS = re.compile(
    r"\b(universal|umg|sony|columbia|warner|wea|emi|interscope|atlantic|capitol|"
    r"rca|island|virgin|polydor|republic|def jam|epic|parlophone|geffen|"
    r"mercury|arista|elektra|motown|decca|believe|distrokid|tunecore|cd baby|"
    r"awal|kobalt|the orchard|ditto|amuse|empire|ingrooves|symphonic|"
    r"self[- ]released|not on label|no label|various)\b", re.I)


def is_major(name):
    return not name or bool(MAJORS.search(name)) or name.startswith("[")


def artist_labels(mbid):
    """{label name: {"mbid", "releases"}} from the artist's official releases."""
    q = urlencode({"artist": mbid, "inc": "labels", "status": "official",
                   "limit": 100, "fmt": "json"})
    data = http.get_json("%s/release?%s" % (MB_ROOT, q), ttl_days=30, **MB_RATE)
    out = {}
    for r in data.get("releases") or []:
        seen = set()
        for li in r.get("label-info") or []:
            lab = li.get("label") or {}
            name = (lab.get("name") or "").strip()
            if not name or name in seen or is_major(name):
                continue
            seen.add(name)
            e = out.setdefault(name, {"mbid": lab.get("id"), "releases": 0})
            e["releases"] += 1
    return out


def absorb_releases(by, releases):
    """Fold release rows (browse or search shape) into the roster dict."""
    for r in releases:
        d = (r.get("date") or "")[:10]
        for ac in r.get("artist-credit") or []:
            a = ac.get("artist") or {}
            name = (ac.get("name") or a.get("name") or "").strip()
            if not name or name.lower() == "various artists":
                continue
            als = None
            if not names.is_latin(name):
                als = names.aliases(a.get("id"), name)
                name = names.latin_name(a.get("id"), name)
            e = by.setdefault(norm_artist(name), {
                "artist": name, "mbid": a.get("id"), "releases": 0,
                "first_date": d or None, "last_date": d or None})
            if als:
                e["aliases"] = als
            e["releases"] += 1
            if d:
                e["first_date"] = min(e["first_date"] or d, d)
                e["last_date"] = max(e["last_date"] or d, d)
    return by


def recent_releases(label_mbid, since, pages=RECENT_PAGES):
    """The label's releases dated since `since`, via search (browse has no
    date order, so a big catalogue's first pages are its earliest era and
    the current roster never appears)."""
    out = []
    for page in range(pages):
        q = urlencode({"query": f"laid:{label_mbid} AND date:[{since} TO 2100]",
                       "limit": 100, "offset": page * 100, "fmt": "json"})
        data = http.get_json("%s/release/?%s" % (MB_ROOT, q), ttl_days=30, **MB_RATE)
        rels = data.get("releases") or []
        out.extend(rels)
        if len(rels) < 100:
            break
    return out


def roster(label_mbid, pages=ROSTER_PAGES, since=None):
    """(roster list, release_count). Artists credited on the label's
    releases, most releases first; 'Various Artists' dropped. Catalogues
    larger than the browse window are topped up with their recent era."""
    by = {}
    total = None
    for page in range(pages):
        q = urlencode({"label": label_mbid, "inc": "artist-credits",
                       "limit": 100, "offset": page * 100, "fmt": "json"})
        data = http.get_json("%s/release?%s" % (MB_ROOT, q), ttl_days=30, **MB_RATE)
        if total is None:
            total = int(data.get("release-count") or 0)
            if total > ROSTER_MAX_RELEASES:
                return [], total
        rels = data.get("releases") or []
        absorb_releases(by, rels)
        if len(rels) < 100:
            break
    if total and total > pages * 100:
        since = since or (datetime.now(timezone.utc).date()
                          .replace(year=datetime.now(timezone.utc).year - RECENT_YEARS)
                          .isoformat())
        seen = set()
        fresh = []
        for r in recent_releases(label_mbid, since):
            if r.get("id") in seen:
                continue
            seen.add(r.get("id"))
            fresh.append(r)
        absorb_releases(by, fresh)
    out = sorted(by.values(), key=lambda e: (-e["releases"], e["artist"]))
    return out, total or 0


def score(artist_rows, labels_by_artist):
    """artist_rows: {norm: {artist, hours, clusters}}; labels_by_artist:
    {norm: {label: {mbid, releases}}}. Returns labels sorted by hours."""
    labels = {}
    for na, labs in labels_by_artist.items():
        row = artist_rows.get(na)
        if not row or not labs:
            continue
        total = sum(v["releases"] for v in labs.values()) or 1
        for name, v in labs.items():
            share = v["releases"] / total
            h = float(row.get("hours") or 0) * share
            L = labels.setdefault(name, {"name": name, "mbid": v["mbid"],
                                         "hours": 0.0, "artists": [],
                                         "lanes": defaultdict(float)})
            L["hours"] += h
            L["artists"].append({"artist": row["artist"], "hours": round(h, 1),
                                 "share": round(share, 2), "releases": v["releases"]})
            for cid in row.get("clusters") or []:
                L["lanes"][cid] += h
    out = []
    for L in labels.values():
        L["hours"] = round(L["hours"], 1)
        L["artists"].sort(key=lambda a: -a["hours"])
        L["lanes"] = {k: round(v, 1) for k, v in
                      sorted(L["lanes"].items(), key=lambda kv: -kv[1])}
        out.append(L)
    out.sort(key=lambda L: (-L["hours"], L["name"]))
    return out


def build(top=TOP_ARTISTS, keep=LABELS_KEEP, expand=ROSTER_LABELS, log=print):
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])
    tm = json.loads((out_dir / "taste-model.json").read_text())
    index = tm.get("artists_index") or {}
    rows = sorted(index.items(), key=lambda kv: -float(kv[1].get("hours") or 0))[:top]
    artist_rows = {na: {"artist": r.get("artist") or na, "hours": r.get("hours"),
                        "clusters": r.get("clusters") or []} for na, r in rows}

    labels_by_artist, unresolved = {}, 0
    for i, (na, r) in enumerate(artist_rows.items(), 1):
        mbid = resolve_artist_mbid(r["artist"])
        if not mbid:
            unresolved += 1
            continue
        try:
            labels_by_artist[na] = artist_labels(mbid)
        except Exception as e:  # noqa: BLE001
            log(f"  [warn] labels failed for {r['artist']}: {e}")
        if i % 50 == 0:
            log(f"  {i}/{len(artist_rows)} artists scanned")

    labels = score(artist_rows, labels_by_artist)[:keep]
    for j, L in enumerate(labels):
        if j >= expand or not L.get("mbid"):
            L["roster_status"] = "not expanded"
            continue
        try:
            ros, total = roster(L["mbid"])
        except Exception as e:  # noqa: BLE001
            L["roster_status"] = f"error: {e}"
            continue
        L["release_count"] = total
        if not ros and total > ROSTER_MAX_RELEASES:
            L["roster_status"] = f"skipped: {total} releases (major-sized)"
        else:
            L["roster"] = ros
            L["roster_status"] = f"ok: {len(ros)} artists from {min(total, ROSTER_PAGES * 100)} of {total} releases"
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artists_scanned": len(artist_rows), "artists_unresolved": unresolved,
        "labels": labels,
    }
    (out_dir / "label-model.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--top", type=int, default=TOP_ARTISTS)
    ap.add_argument("--expand", type=int, default=ROSTER_LABELS)
    args = ap.parse_args(argv)
    doc = build(top=args.top, expand=args.expand)
    print(f"label model: {len(doc['labels'])} labels from {doc['artists_scanned']} "
          f"artists ({doc['artists_unresolved']} unresolved) -> out/label-model.json")
    for L in doc["labels"][:15]:
        ros = len(L.get("roster") or [])
        print(f"  {L['name']:34s} {L['hours']:6.1f}h  {len(L['artists']):3d} artists  "
              f"roster {ros:4d}  {L.get('roster_status', '')}")


if __name__ == "__main__":
    main()
