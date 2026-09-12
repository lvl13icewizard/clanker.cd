"""Press a demo persona's run of weekly issues from its catalog.

A catalog (demo/catalogs/<slug>.json, see demo/SPEC.md) holds the music and
the words: lanes, history artists, the pools every module draws from, and
the name of each issue. This turns that into a run of issues shaped exactly
like the real thing, writes them to site/public/demo/<slug>/, and checks
every one with the real receipts validator.

The split matters: the catalog never carries a number that appears in
prose. Every statistic in a rendered sentence is composed here, alongside
the receipt that backs it, so a demo issue passes the same gate a real one
does.

No Spotify anything: demo playlists are marked `status: "demo"` and carry no
URL, and item links point at a Spotify SEARCH for the record, which always
resolves to the real thing and never to a dead id.

Run:  python3 demo/build_demo.py --all
      python3 demo/build_demo.py --slug andrew
"""

import argparse
import json
import math
import random
import re
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.editorial.validate import validate_issue          # noqa: E402
from engine.lib.normalize import norm_artist                   # noqa: E402

CATALOGS = ROOT / "demo" / "catalogs"
OUT_ROOT = ROOT / "site" / "public" / "demo"

NUMWORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
            7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}

# Each persona's covers get their own hand: the gradient recipe is what makes
# one archive look like Berlin concrete and another like a pop single.
RECIPES = {
    "andrew": {"colors": 4, "blobSize": 0.62, "blur": 40, "grain": 0.16,
               "saturation": 1.08, "vignette": 0.16, "textSize": 0.105, "namePos": "bottom"},
    "electronic": {"colors": 3, "blobSize": 0.46, "blur": 26, "grain": 0.24,
                   "saturation": 0.92, "vignette": 0.3, "textSize": 0.092, "namePos": "bottom"},
    "altindie": {"colors": 5, "blobSize": 0.74, "blur": 54, "grain": 0.12,
                 "saturation": 1.0, "vignette": 0.1, "textSize": 0.1, "namePos": "top"},
    "pop": {"colors": 4, "blobSize": 0.56, "blur": 22, "grain": 0.05,
            "saturation": 1.28, "vignette": 0.06, "textSize": 0.12, "namePos": "bottom"},
}
DEFAULT_RECIPE = RECIPES["andrew"]

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def display_title_of(issue):
    """'Issue 016: Second Wind' -> 'Second Wind'."""
    t = issue.get("title") or f"Issue {issue.get('issue', 0):03d}"
    return t.split(": ", 1)[1] if ": " in t else t


def fmt(n):
    if isinstance(n, float) and n != int(n):
        return f"{n:,.1f}"
    return f"{int(n):,}"


def search_url(*parts):
    q = " ".join(str(p) for p in parts if p)
    return "https://open.spotify.com/search/" + urllib.parse.quote(q)


def pct(x):
    """A skip fraction as a whole-number percent."""
    return int(round(float(x) * 100))


def joinsent(*chunks):
    out = []
    for c in chunks:
        if not c:
            continue
        c = c.strip()
        if not c.endswith((".", "!", "?")):
            c += "."
        out.append(c)
    return " ".join(out)


# --------------------------------------------------------------- receipts

def artist_receipts(a):
    """The three receipts every anchored claim can draw on."""
    k = norm_artist(a["name"])
    return [
        {"stat_id": f"artist_plays:{k}", "claim": f"{a['name']}: {fmt(a['plays'])} plays",
         "value": a["plays"]},
        {"stat_id": f"artist_hours:{k}", "claim": f"{a['name']}: {a['hours']} hours",
         "value": a["hours"]},
        {"stat_id": f"artist_skip:{k}", "claim": f"{a['name']}: {pct(a['skip_rate'])}% skip",
         "value": pct(a["skip_rate"])},
    ]


ANCHOR_LINES = [
    lambda a, p, h, s: f"You've played {a} {p} times and skip them {s}% of the time, and this sits in the same room",
    lambda a, p, h, s: f"{a} is {h} hours of your listening, and this is the next room over",
    lambda a, p, h, s: f"{p} plays of {a} say you'll take to this",
    lambda a, p, h, s: f"This came through {a}, {h} hours deep and still going",
    lambda a, p, h, s: f"Your {a} habit runs to {p} plays at a {s}% skip rate, and this shares the nerve",
    lambda a, p, h, s: f"{a} at {h} hours is the anchor here",
    lambda a, p, h, s: f"If {a} is worth {p} plays to you, this is worth an afternoon",
    lambda a, p, h, s: f"You keep {a} at a {s}% skip rate, which is the tell",
    lambda a, p, h, s: f"{h} hours with {a} is the reason this is here",
    lambda a, p, h, s: f"{a} has {p} plays and a {s}% skip rate in your listening, and this is cut from it",
    lambda a, p, h, s: f"The {a} shelf runs {h} hours deep, and this belongs beside it",
    lambda a, p, h, s: f"{p} plays, {h} hours: {a} is the door this came through",
]


def anchor_line(artist, rnd):
    """A receipt-backed sentence about the anchor, plus its receipts."""
    f = ANCHOR_LINES[rnd.randrange(len(ANCHOR_LINES))]
    return (f(artist["name"], fmt(artist["plays"]), artist["hours"], pct(artist["skip_rate"])),
            artist_receipts(artist))


LABEL_LINES = [
    lambda l, a, h, k, r: f"{l} runs {h} hours deep on your shelf, {k} of its artists in your rotation, and {a} has {r} releases there you have never opened",
    lambda l, a, h, k, r: f"You play {k} artists on {l}, {h} hours between them, and {a} sits on the same label with {r} releases",
    lambda l, a, h, k, r: f"The door here is the label: {h} hours of {l} in your listening, {k} of its artists you know, and {r} releases by {a} you do not",
]


def label_line(label, artist, rnd):
    """The receipt sentence for a label-introduced single, in the same hand
    as anchor_line: the numbers are the label model's, the prose is ours."""
    f = LABEL_LINES[rnd.randrange(len(LABEL_LINES))]
    return f(label["name"], artist, label["hours"], label["artists"], label["releases"])


def companion_playlist(cat, n, meta, tracks):
    """The demo's playlist record. A persona's catalog may carry `playlists`,
    keyed by issue number, for the few issues whose playlist was actually
    created on Spotify (the owner's account, from the issue's exact tracks);
    those read as published and the rail links to them. Every other issue
    says plainly that nothing exists."""
    real = (cat.get("playlists") or {}).get(str(n))
    if real:
        return {"name": f"Issue {n:03d}: {meta['title']}", "status": "published",
                "id": real["id"], "uri": f"spotify:playlist:{real['id']}",
                "spotify_url": f"https://open.spotify.com/playlist/{real['id']}",
                "track_count": real.get("track_count", tracks),
                "published_at": real.get("published_at"),
                "note": real.get("note") or "created on Spotify from this issue's exact tracks"}
    return {"name": f"Issue {n:03d}: {meta['title']}", "status": "demo",
            "track_count": tracks, "note": "demo persona: nothing was created on Spotify"}


# ------------------------------------------------------------------ intros

SINGLES_INTROS = [
    "{n} doors this week, one per corner of your listening, sequenced so it plays as a single run.",
    "{n} singles, each from an artist you have never played, each next to something you play constantly.",
    "{n} tracks, arranged as an arc rather than a list: the quiet end first, the loud end last.",
    "{n} new names, chosen for how they sit beside the music you already keep close.",
    "{n} singles from {n} directions. None of these artists appear anywhere in your listening.",
    "{n} doors, no repeats, and every one of them opens onto something you already love.",
]
MIX_INTROS = [
    "Two radio hours that match the week's shape, with enough familiar names to hold on to and enough new ones to make it a trip.",
    "Two broadcasts, picked for overlap: not so familiar that you know it all, not so foreign that there is nothing to hold.",
    "Two hours of someone else's taste, chosen because their record collection and yours share a corner.",
    "Two shows this week. Both sit on the border between what you play and what you have not found yet.",
]
REVIVAL_INTROS = {
    "fade_outs": "Songs you wore out and then dropped. Not forgotten the way barely-played songs are forgotten; these were played into the ground, peaked in a single month, and then went quiet.",
    "barely_played": "Tracks that passed through your listening once or twice and never came back. Not rejected, just missed on a busy week.",
    "time_capsule": "Songs from a specific stretch of your listening that stopped when that stretch ended. They are not worse than they were.",
}
LEDGER_INTROS = [
    "Last issue, graded. Every pick was new to you, so any play at all counts as a result.",
    "The report card. Nothing here was in your listening before it was recommended, so a single play is a hit.",
    "Last week's issue, measured against what you actually played. No credit for good intentions.",
]
NTW_INTROS = [
    "New releases from artists already deep in your listening.",
    "Out now, from names you already keep close.",
    "This week's releases from the shelf you already own.",
]
FRANCHISES = ["fade_outs", "barely_played", "time_capsule"]


# ------------------------------------------------------------ module builds

def build_singles(cat, n, rnd, lanes_by_id):
    per = cat["per_issue"]["singles"]
    picks = cat["singles"][(n - 1) * per: n * per]
    artists = {a["name"]: a for a in cat["artists"]}
    tracks = []
    for i, s in enumerate(picks):
        if s.get("label"):
            # A door opened by a label the listener lives on: the same card
            # and receipts the engine's writer prints for a label lead.
            from engine.editorial.writer import _label_receipts
            receipts = _label_receipts(s["label"], s["artist"])
            line = label_line(s["label"], s["artist"], rnd)
            extra = {"relation": "label", "label": s["label"]}
        else:
            a = artists[s["anchor"]]
            line, receipts = anchor_line(a, rnd)
            extra = {}
        tracks.append({
            "artist": s["artist"], "title": s["title"], "cluster": s["lane"],
            "why": s.get("why") or joinsent(s["note"], line),
            "receipts": receipts,
            "spotify_url": search_url(s["artist"], s["title"]),
            "cover_url": None, **extra,
        })
    intro = SINGLES_INTROS[rnd.randrange(len(SINGLES_INTROS))].format(
        n=NUMWORDS.get(len(picks), str(len(picks))))
    return {"type": "singles_rack", "intro": intro, "tracks": tracks}


def build_album(cat, n, rnd, lanes_by_id):
    al = cat["albums"][n - 1]
    artists = {a["name"]: a for a in cat["artists"]}
    a = artists[al["anchor"]]
    line, receipts = anchor_line(a, rnd)
    lane = lanes_by_id.get(al["lane"]) or {}
    extra = ""
    if lane.get("hours"):
        receipts = [{"stat_id": f"cluster_hours:{al['lane']}",
                     "claim": f"{lane.get('name', al['lane'])}: {lane['hours']} hours lifetime "
                              f"across {lane.get('members', 0)} member artists",
                     "value": lane["hours"]}] + receipts
        extra = (f"{lane.get('name', al['lane'])} is {lane['hours']} hours of your life, "
                 f"so this record is built for attention you already give")
    critics = None
    if al.get("pitchfork") is not None:
        critics = {"pitchfork": {"score": al["pitchfork"], "bnm": bool(al.get("bnm")),
                                 "url": None, "author": None, "dek": None},
                   "fantano": None}
        receipts = receipts + [{"stat_id": f"p4k_score:{norm_artist(al['artist'])}",
                                "claim": f"Pitchfork scored it {al['pitchfork']}",
                                "value": al["pitchfork"]}]
    mod = {
        "type": "front_to_back", "cluster": al["lane"],
        "album": {"artist": al["artist"], "title": al["title"], "year": al["year"],
                  "label": al.get("label"), "cover_url": None,
                  "spotify_url": search_url(al["artist"], al["title"]), "odesli_url": None},
        "why": al.get("why") or joinsent(al["note"], extra, line),
        "receipts": receipts,
    }
    if critics:
        mod["critics"] = critics
    return mod


def build_mix(cat, n, rnd, lanes_by_id):
    per = cat["per_issue"]["mixes"]
    picks = cat["mixes"][(n - 1) * per: n * per]
    artists = {a["name"]: a for a in cat["artists"]}
    mixes = []
    for m in picks:
        a = artists[m["anchor"]]
        new = m["tracks_total"] - m["known"]
        key = re.sub(r"[^a-z0-9]+", "-", m["show"].lower()).strip("-")[:40]
        receipts = [
            {"stat_id": f"mix_tracks:{key}", "claim": f"{m['tracks_total']} tracks in the broadcast",
             "value": m["tracks_total"]},
            {"stat_id": f"mix_known:{key}", "claim": f"{m['known']} by artists you play",
             "value": m["known"]},
            {"stat_id": f"mix_new:{key}", "claim": f"{new} tracks new to you", "value": new},
        ] + artist_receipts(a)
        line = (f"{m['tracks_total']} tracks, {m['known']} by artists you already play and "
                f"{new} you have never heard, with {a['name']} ({fmt(a['plays'])} plays) "
                f"in there as a foothold")
        mixes.append({
            "show": m["show"],
            "episode": m.get("episode") or (f"with {m['host']}" if m.get("host") else m["show"]),
            "date": m["date"], "cluster": m["lane"],
            "station": m.get("station") or station_of(m["show"]),
            # A real destination for every station. An entry that names its
            # real episode (url, listen links, artwork: the harvest's own
            # shape) is used as given; otherwise NTS shows get NTS's own
            # search and the rest get the station's home. Never an invented
            # episode link, and never null, which the validator refuses.
            "url": m.get("url") or station_url(m["show"]),
            "listen_urls": list(m.get("listen_urls") or []),
            "tracks_total": m["tracks_total"], "known_count": m["known"], "new_count": new,
            "why": m.get("why") or joinsent(m["note"], line),
            "receipts": receipts, "cover_url": m.get("cover_url"),
        })
    return {"type": "the_mix", "intro": MIX_INTROS[rnd.randrange(len(MIX_INTROS))], "mixes": mixes}


def build_revival(cat, n, rnd, lanes_by_id):
    picks = cat["revivals"][(n - 1) * 3: n * 3]
    artists = {a["name"]: a for a in cat["artists"]}
    franchise = FRANCHISES[(n - 1) % len(FRANCHISES)]
    tracks = []
    for r in picks:
        ym = r["last_played"][:7]
        receipts = [{"stat_id": f"track_plays:{norm_artist(r['artist'])}",
                     "claim": f"you: {r['plays']} plays, last {ym}", "value": r["plays"]}]
        a = artists.get(r["artist"])
        if a:
            receipts += artist_receipts(a)
        if franchise == "barely_played":
            line = f"{r['plays']} plays in total, and then it left rotation without ever being a habit"
        elif franchise == "time_capsule":
            line = f"{r['plays']} plays inside one stretch of your listening, and none since"
        else:
            line = f"{r['plays']} plays, most of them close together, then a clean stop"
        tracks.append({
            "artist": r["artist"], "title": r["title"], "album": r.get("album") or None,
            "plays": r["plays"], "last_played": r["last_played"],
            "why": joinsent(r["note"], line), "receipts": receipts,
            "spotify_url": search_url(r["artist"], r["title"]), "cover_url": None,
        })
    return {"type": "revival_desk", "franchise": franchise,
            "intro": REVIVAL_INTROS[franchise], "tracks": tracks}


def build_critics(cat, n, rnd, lanes_by_id, persona_stats):
    per = cat["per_issue"]["critics"]
    picks = cat["critics"][(n - 1) * per: n * per]
    artists = {a["name"]: a for a in cat["artists"]}
    reviewed, avg = persona_stats
    albums = []
    for c in picks:
        a = artists[c["anchor"]]
        line, receipts = anchor_line(a, rnd)
        receipts = [{"stat_id": f"p4k_score:{norm_artist(c['artist'])}",
                     "claim": f"Pitchfork scored it {c['score']}", "value": c["score"]}] + receipts
        albums.append({
            "artist": c["artist"], "title": c["title"], "year": c["year"],
            "score": c["score"], "bnm": bool(c.get("bnm")), "fresh": False,
            "genre": c.get("genre"), "cluster": c["lane"], "url": None,
            "why": joinsent(c["note"], line), "receipts": receipts, "cover_url": None,
        })
    intro = (f"Pitchfork has reviewed {reviewed} of your top forty artists and averages "
             f"{avg} on the music you already love. These scored higher than that, sit "
             f"squarely in your taste, and you have never played any of them.")
    return {"type": "critics_desk", "intro": intro,
            "receipts": [
                {"stat_id": "p4k_top40_reviewed",
                 "claim": f"{reviewed} of your top 40 artists have been reviewed by Pitchfork",
                 "value": reviewed},
                {"stat_id": "p4k_top40_avg", "claim": f"their reviews average {avg}", "value": avg},
            ], "albums": albums}


def build_catalog(cat, idx, rnd):
    c = cat["catalogs"][idx]
    a = {x["name"]: x for x in cat["artists"]}[c["artist"]]
    k = norm_artist(a["name"])
    receipts = [
        {"stat_id": f"artist_plays:{k}", "claim": f"{a['name']}: {fmt(a['plays'])} plays", "value": a["plays"]},
        {"stat_id": f"catalog_breadth:{k}", "claim": f"across only {c['unique_tracks']} unique tracks",
         "value": c["unique_tracks"]},
        {"stat_id": f"catalog_top3:{k}", "claim": f"the top 3 tracks are {c['top3_share']}% of all of it",
         "value": c["top3_share"]},
        {"stat_id": f"artist_hours:{k}", "claim": f"{a['hours']} hours lifetime", "value": a["hours"]},
        {"stat_id": f"artist_skip:{k}", "claim": f"at {pct(a['skip_rate'])}% skip", "value": pct(a["skip_rate"])},
    ]
    line = (f"You've played {a['name']} {fmt(a['plays'])} times but only {c['unique_tracks']} "
            f"different songs, and the top three carry {c['top3_share']}% of that")
    return {
        "type": "catalog_room", "artist": a["name"],
        "why": joinsent(line, c["note"]),
        "receipts": receipts,
        "unheard": [{"title": u["title"], "year": u["year"], "cover_url": None} for u in c["unheard"]],
        "heard_note": "On the record already: " + ", ".join(c["heard"][:4]),
    }


def build_ntw(cat, n, rnd, issue_date):
    per = cat["per_issue"]["releases"]
    picks = cat["releases"][(n - 1) * per: n * per]
    releases = []
    # Dates land in the three weeks before the issue; one can land on the day.
    today_idx = rnd.randrange(len(picks)) if picks and rnd.random() < 0.45 else None
    for i, r in enumerate(picks):
        if i == today_idx:
            d = issue_date
        else:
            d = issue_date - timedelta(days=rnd.randrange(1, 22))
        releases.append({
            "artist": r["artist"], "title": r["title"], "release_date": d.isoformat(),
            "release_type": r["release_type"], "relationship": "played", "via": None,
            "note": r.get("note") or None,
        })
    releases.sort(key=lambda x: x["release_date"], reverse=True)
    intro = NTW_INTROS[rnd.randrange(len(NTW_INTROS))]
    if today_idx is not None:
        t = picks[today_idx]
        intro += f" {t['artist']}'s {t['release_type']} lands today."
    return {"type": "new_this_week", "intro": intro, "releases": releases}


LEDGER_ROW_SOURCES = [
    ("front_to_back", lambda m: [f"{m['album']['artist']} — {m['album']['title']}"]),
    ("singles_rack", lambda m: [f"{t['artist']} — {t['title']}" for t in m.get("tracks", [])]),
    ("revival_desk", lambda m: [f"{t['artist']} — {t['title']}" for t in m.get("tracks", [])]),
    ("critics_desk", lambda m: [f"{a['artist']} — {a['title']}" for a in m.get("albums", [])]),
    ("catalog_room", lambda m: [f"{m['artist']} — {u['title']}" for u in m.get("unheard", [])]),
    ("the_mix", lambda m: [m["show"] for m in m.get("mixes", [])]),
]


def build_ledger(cat, prev_issue, rnd, adoption, issue_date):
    """Grade the previous issue: its own picks, some of them played."""
    labels = []
    for mod in prev_issue["modules"]:
        for kind, fn in LEDGER_ROW_SOURCES:
            if mod.get("type") == kind:
                try:
                    for lb in fn(mod):
                        labels.append((lb, kind))
                except Exception:
                    pass
    prev_date = date.fromisoformat(prev_issue["date"])
    window = (issue_date - prev_date).days
    rows, played_n, returned = [], 0, 0
    # The playlist sitting: most of what gets played is played in one go.
    sitting = prev_date + timedelta(days=rnd.randrange(0, 3))
    for lb, kind in labels:
        hit = rnd.random() < adoption
        if hit:
            played_n += 1
            plays = 1 if rnd.random() < 0.72 else rnd.randrange(2, 4)
            if plays > 1:
                returned += 1
            first = sitting if rnd.random() < 0.68 else prev_date + timedelta(days=rnd.randrange(1, max(2, window)))
            rows.append({"label": lb, "module": kind, "played": True, "plays": plays,
                         "first_play": first.isoformat()})
        else:
            rows.append({"label": lb, "module": kind, "played": False, "plays": 0,
                         "first_play": None})
    rows.sort(key=lambda r: (not r["played"], r["label"].lower()))
    total = len(rows)
    rate = int(round(100 * played_n / total)) if total else 0
    receipts = [
        {"stat_id": f"ledger_scored:{prev_issue['issue']}", "claim": f"{total} picks were measurable", "value": total},
        {"stat_id": f"ledger_played:{prev_issue['issue']}", "claim": f"{played_n} of them got played", "value": played_n},
        {"stat_id": f"ledger_rate:{prev_issue['issue']}", "claim": f"{rate}% adoption", "value": rate},
        {"stat_id": f"ledger_window:{prev_issue['issue']}", "claim": f"{window} days since it went out", "value": window},
        {"stat_id": f"ledger_returned:{prev_issue['issue']}", "claim": f"{returned} earned a second play", "value": returned},
    ]
    same_day = sum(1 for r in rows if r["played"] and r["first_play"] == sitting.isoformat())
    tail = ("Most of that happened in one sitting with the companion playlist on, rather than "
            "separate returns to separate records."
            if same_day > max(1, played_n // 2) else
            "The plays are spread across the week, which is the shape you want: separate "
            "returns to separate records.")
    verdict = joinsent(
        f"Last issue, graded against what actually got played: {total} picks were measurable, "
        f"{played_n} of them got played, {rate}% adoption, {window} days since it went out, "
        f"{returned} earned a second play", tail)
    return {"type": "ledger", "intro": LEDGER_INTROS[rnd.randrange(len(LEDGER_INTROS))],
            "verdict": verdict, "receipts": receipts, "rows": rows}


# ------------------------------------------------------------------- issues

def catalog_schedule(k, count):
    """Which issue numbers carry a catalog_room, spread evenly."""
    if count <= 0:
        return set()
    return {int(round(1 + i * (k - 1) / max(1, count - 1))) for i in range(count)}


def persona_p4k(cat):
    """A stable 'reviewed / average' pair for the critics desk intro."""
    r = random.Random(f"{cat['slug']}:p4k")
    return r.randrange(28, 39), round(r.uniform(6.9, 7.7), 1)


# ---------------------------------------------------------- collision repair

POOL_ARTIST = {
    "singles": lambda x: x.get("artist"),
    "critics": lambda x: x.get("artist"),
    "revivals": lambda x: x.get("artist"),
}


def issue_artists(cat, n, per):
    """Every artist an issue would feature, and where from."""
    out = {}
    al = cat["albums"][n - 1]
    out.setdefault(al["artist"].strip().lower(), []).append(("albums", n - 1))
    for pool, get in POOL_ARTIST.items():
        k = 3 if pool == "revivals" else per[pool]
        for i in range((n - 1) * k, min(n * k, len(cat[pool]))):
            nm = (get(cat[pool][i]) or "").strip().lower()
            out.setdefault(nm, []).append((pool, i))
    return out


def repair_collisions(cat, sched, quiet=False):
    """An artist twice in one issue reads as a bug, so move the smaller of the
    two picks to another issue. Only single items move, and only into a slot
    that stays collision-free, so the editorial grouping of each issue holds."""
    per = cat["per_issue"]
    k = cat["issue_count"]
    cat_artist = {}
    for idx, n in enumerate(sorted(sched)):
        if idx < len(cat["catalogs"]):
            cat_artist[n] = cat["catalogs"][idx]["artist"].strip().lower()

    moved, stuck = 0, []
    for _ in range(6):
        collision = None
        for n in range(1, k + 1):
            seen = issue_artists(cat, n, per)
            ca = cat_artist.get(n)
            if ca:
                seen.setdefault(ca, []).append(("catalogs", -1))
            for nm, where in seen.items():
                if nm and len(where) > 1:
                    movable = [w for w in where if w[0] in POOL_ARTIST]
                    if movable:
                        collision = (n, nm, movable[-1])
                        break
            if collision:
                break
        if not collision:
            break
        n, nm, (pool, idx) = collision
        span = 3 if pool == "revivals" else per[pool]
        # nearest other issue whose slice takes this artist without a clash
        order = sorted((m for m in range(1, k + 1) if m != n), key=lambda m: abs(m - n))
        done = False
        for m in order:
            mine = issue_artists(cat, m, per)
            if cat_artist.get(m):
                mine.setdefault(cat_artist[m], []).append(("catalogs", -1))
            if nm in mine:
                continue
            for j in range((m - 1) * span, min(m * span, len(cat[pool]))):
                other = (POOL_ARTIST[pool](cat[pool][j]) or "").strip().lower()
                here = issue_artists(cat, n, per)
                if cat_artist.get(n):
                    here.setdefault(cat_artist[n], []).append(("catalogs", -1))
                if other in here:
                    continue  # swapping in would just move the problem
                cat[pool][idx], cat[pool][j] = cat[pool][j], cat[pool][idx]
                moved += 1
                done = True
                break
            if done:
                break
        if not done:
            stuck.append((n, nm, pool))
            break
    if not quiet and (moved or stuck):
        print(f"  collision repair: moved {moved} pick(s)"
              + (f", {len(stuck)} unresolved {stuck}" if stuck else ""))
    return moved, stuck


# Demo radio shows and where they really live. Programme names that belong
# to NTS carry the NTS label; the rest are stations in their own right.
STATIONS = {
    "NTS Radio": ("NTS", None), "NTS Breakfast Show": ("NTS", None),
    "Do!! You!!! Breakfast Show": ("NTS", None), "Sounds of the Dawn": ("NTS", None),
    "Worldwide FM": ("Worldwide FM", "https://worldwidefm.net"),
    "Rinse FM": ("Rinse FM", "https://rinse.fm"),
    "BBC Radio 1": ("BBC Radio 1", "https://www.bbc.co.uk/sounds"),
    "Dublab": ("Dublab", "https://www.dublab.com"),
    "The Lot Radio": ("The Lot Radio", "https://www.thelotradio.com"),
    "Balamii": ("Balamii", "https://www.balamii.com"),
    "Beats in Space": ("Beats in Space", "https://www.beatsinspace.net"),
    "Mixmag Lab": ("Mixmag", "https://mixmag.net"),
    "Apple Music 1": ("Apple Music 1", "https://music.apple.com/us/radio"),
    "Apple Music Hits": ("Apple Music Hits", "https://music.apple.com/us/radio"),
    "Apple Music Country": ("Apple Music Country", "https://music.apple.com/us/radio"),
    "Apple Music Latin": ("Apple Music Latin", "https://music.apple.com/us/radio"),
}


def station_of(show):
    return STATIONS.get(show, (show, None))[0]


def station_url(show):
    label, home = STATIONS.get(show, (show, None))
    if label == "NTS":
        return "https://www.nts.live/search?q=" + urllib.parse.quote(show)
    if home:
        return home
    print(f"  [warn] no station home for {show!r}; the validator will refuse a null url")
    return None


def build_issue(cat, n, prev_issue, lanes_by_id, sched, p4k, adoption):
    meta = cat["issues"][n - 1]
    d = date.fromisoformat(cat["first_date"]) + timedelta(days=7 * (n - 1))
    rnd = random.Random(f"{cat['slug']}:{n}")
    mods = [
        build_singles(cat, n, rnd, lanes_by_id),
        build_album(cat, n, rnd, lanes_by_id),
        build_mix(cat, n, rnd, lanes_by_id),
        build_revival(cat, n, rnd, lanes_by_id),
        build_critics(cat, n, rnd, lanes_by_id, p4k),
    ]
    if n in sched:
        idx = sorted(sched).index(n)
        if idx < len(cat["catalogs"]):
            mods.append(build_catalog(cat, idx, rnd))
    mods.append(build_ntw(cat, n, rnd, d))
    if prev_issue is not None:
        mods.append(build_ledger(cat, prev_issue, rnd, adoption, d))
    h = cat["history"]
    tracks = len(mods[0]["tracks"]) + 1 + 3
    return {
        "issue": n, "date": d.isoformat(),
        "title": f"Issue {n:03d}: {meta['title']}", "dek": meta["dek"],
        "masthead_note": "Every number in this issue comes from your own listening history.",
        "modules": mods,
        "verification": {
            "tracks_checked_against": h["tracks"], "artists_checked_against": h["artists"],
            "rounds": 2,
            "method": "two-round normalized match against the merged play log: exact "
                      "artist/track keys, then near-name and title-collision checks",
        },
        "companion_playlist": companion_playlist(cat, n, meta, tracks),
        "generated": {
            "engine_version": "0.1-demo",
            "generated_at": datetime.combine(d, datetime.min.time(), timezone.utc)
                .replace(hour=9).isoformat(timespec="seconds"),
            "llm": True,
            "notes": [f"synthetic demo persona {cat['slug']!r}; picks are real records, "
                      f"statistics are modelled, "
                      + ("the playlist was created on Spotify from these exact tracks"
                         if (cat.get("playlists") or {}).get(str(n)) else "no playlist was published")],
        },
    }


def fix_release_notes(issue):
    """Null any new_this_week note the validator reads as mis-paired."""
    fixed = 0
    for _ in range(6):
        errs = [e for e in validate_issue(issue) if "pairing error" in e]
        if not errs:
            break
        for e in errs:
            m = re.search(r"modules\[(\d+)\]\.releases\[(\d+)\]|releases\[(\d+)\]", e)
            idx = None
            if m:
                idx = int(m.group(2) or m.group(3))
            for mod in issue["modules"]:
                if mod.get("type") == "new_this_week" and idx is not None and idx < len(mod["releases"]):
                    mod["releases"][idx]["note"] = None
                    fixed += 1
    return fixed


def build_persona(path, out_root, quiet=False):
    cat = json.loads(path.read_text())
    slug, k = cat["slug"], cat["issue_count"]
    lanes_by_id = {l["id"]: l for l in cat["lanes"]}
    sched = catalog_schedule(k, len(cat["catalogs"]))
    p4k = persona_p4k(cat)
    adoption = 0.30 + (sum(ord(c) for c in slug) % 20) / 100.0
    repair_collisions(cat, sched, quiet=quiet)
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("issue-*.json"):
        old.unlink()

    issues, problems, notes_fixed = [], [], 0
    prev = None
    for n in range(1, k + 1):
        iss = build_issue(cat, n, prev, lanes_by_id, sched, p4k, adoption)
        notes_fixed += fix_release_notes(iss)
        errs = validate_issue(iss)
        if errs:
            problems.append((n, errs))
        (out / f"issue-{n:03d}.json").write_text(
            json.dumps(iss, indent=1, ensure_ascii=False) + "\n")
        issues.append(iss)
        prev = iss

    # An artist twice in one issue reads as a bug even when the records
    # differ, so it is reported rather than silently shipped.
    collisions = []
    for iss in issues:
        seen = {}
        for mod in iss["modules"]:
            t = mod.get("type")
            rows = []
            if t == "front_to_back":
                rows = [(mod["album"]["artist"], "album of the week")]
            elif t in ("singles_rack", "revival_desk"):
                rows = [(x["artist"], t) for x in mod.get("tracks", [])]
            elif t == "critics_desk":
                rows = [(x["artist"], t) for x in mod.get("albums", [])]
            elif t == "catalog_room":
                rows = [(mod["artist"], t)]
            for name, where in rows:
                key = name.strip().lower()
                if key in seen and seen[key] != where:
                    collisions.append((iss["issue"], name, seen[key], where))
                seen[key] = where
    if collisions and not quiet:
        print(f"  ARTIST TWICE IN ONE ISSUE ({len(collisions)}):")
        for n, name, a, b in collisions:
            print(f"    issue {n:03d}: {name} in {a} and {b}")

    index = [{"issue": i["issue"], "date": i["date"], "title": i["title"]} for i in issues]
    index.sort(key=lambda e: -e["issue"])
    (out / "index.json").write_text(json.dumps({"issues": index}, indent=1, ensure_ascii=False) + "\n")

    lanes = []
    for l in cat["lanes"]:
        lanes.append({
            "id": l["id"], "name": l["name"], "hue": l["hue"], "description": l["description"],
            "state": l["state"], "state_evidence": l["arc"],
            "members": l["members"], "hours": l["hours"], "seeds": l["seeds"],
            "top": l["top"],
        })
    (out / "lanes.json").write_text(json.dumps(
        {"lanes": lanes, "generated_at": issues[-1]["generated"]["generated_at"]},
        indent=1, ensure_ascii=False) + "\n")

    if not quiet:
        print(f"{slug}: {len(issues)} issues -> {out}")
        n_cat = len(sched & set(range(1, k + 1)))
        print(f"  lanes {len(lanes)} · catalog_room in {n_cat} issues"
              f" · adoption {adoption:.0%} · notes unpaired-and-dropped {notes_fixed}")
        if problems:
            print(f"  VALIDATOR: {len(problems)} issue(s) with problems")
            for n, errs in problems[:4]:
                for e in errs[:4]:
                    print(f"    issue {n:03d}: {e}")
        else:
            print("  validator: all issues pass")
    return cat, issues, problems


def write_manifest(out_root, built):
    personas = []
    for cat, issues in built:
        last = issues[-1]
        personas.append({
            "slug": cat["slug"], "name": cat["name"], "persona": cat["persona"],
            "blurb": cat["blurb"], "issues": len(issues),
            "first_date": issues[0]["date"], "last_date": last["date"],
            "palette": cat["palette"],
            "history": {"plays": cat["history"]["plays"], "hours": cat["history"]["hours"],
                        "artists": cat["history"]["artists"],
                        "since": cat["history"]["window_start"][:4]},
            "lanes": [{"id": l["id"], "name": l["name"], "hue": l["hue"], "state": l["state"]}
                      for l in cat["lanes"]],
            "latest": {"issue": last["issue"], "title": last["title"], "dek": last["dek"]},
            "covers": [f"/demo/{cat['slug']}/cover-{i['issue']:03d}.jpg"
                       for i in issues[::-1][:4]],
        })
    personas.sort(key=lambda p: -p["issues"])
    out = out_root / "index.json"
    out.write_text(json.dumps(
        {"personas": personas,
         "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        indent=1, ensure_ascii=False) + "\n")
    print(f"manifest: {len(personas)} persona(s) -> {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", help="one persona (default: --all)")
    ap.add_argument("--all", action="store_true", help="every catalog in demo/catalogs")
    ap.add_argument("--out", default=str(OUT_ROOT))
    args = ap.parse_args(argv)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    paths = ([CATALOGS / f"{args.slug}.json"] if args.slug
             else sorted(CATALOGS.glob("*.json")))
    paths = [p for p in paths if p.exists()]
    if not paths:
        print("no catalogs found in demo/catalogs")
        return 1
    built, bad = [], 0
    for p in paths:
        cat, issues, problems = build_persona(p, out_root)
        built.append((cat, issues))
        bad += len(problems)
    # The manifest lists every persona already on disk, not just this run.
    have = {c["slug"] for c, _ in built}
    for p in sorted(CATALOGS.glob("*.json")):
        if p.stem in have:
            continue
        d = Path(args.out) / p.stem
        if (d / "index.json").exists():
            # Read what is already on disk. Rebuilding would wipe the
            # artwork art.py and mix_tiles.py fill in after a build.
            cat = json.loads(p.read_text())
            issues = [json.loads(f.read_text()) for f in sorted(d.glob("issue-*.json"))]
            if issues:
                built.append((cat, issues))
    write_manifest(out_root, built)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
