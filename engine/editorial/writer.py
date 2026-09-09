"""Issue writer — assembles issues/issue-NNN.json from pipeline outputs.

Inputs (from out/ by default; ``--in DIR`` redirects, e.g. to a fixtures
dir while upstream stages are still being built):

    selection-proposal.json   (required — no proposal, no issue)
    taste-model.json          (optional — receipts degrade without it)
    revival-pools.json        (optional — extra fields for revival tracks)

Modes:
    --no-llm       template prose: receipts joined plainly (VOICE.md rule 8)
    --copy PATH    prose overrides, same structure as the issue, merged on
                   top of the template (modules matched by "type", track
                   lists by index — except new_this_week.releases, whose
                   notes are paired to the release they describe; see
                   "copy pairing" below)

The template is always built first so the issue is structurally complete;
``--copy`` merges prose over it. ``generated.llm`` is true only when copy
prose was supplied. Missing inputs degrade honestly: affected modules are
dropped and the reason is recorded in ``generated.notes`` — nothing is
fabricated. Template prose only ever includes a receipt claim whose own
number tokens validate against the module's receipt pool, so ``--no-llm``
output always passes the validator.

The issue is validated with engine.editorial.validate BEFORE writing; on
violation the errors are printed and nothing is written (exit 1). On
success the JSON is written to issues/ and copied to site/public/issues/.

Run:  python3 -m engine.editorial.writer --n 1 --no-llm [--in out/fixtures]
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from engine.lib.config import load_config
from engine.lib.normalize import norm_artist, norm_title
from engine.editorial import validate as V

ENGINE_VERSION = "0.1"

SOURCE_NAMES = {
    "lb_labs": "ListenBrainz similar-artists",
    "deezer_related": "Deezer related",
    "lastfm_similar": "Last.fm similar",
    "pitchfork_catalog": "the Pitchfork catalog pool",
    "pitchfork_rss": "this week's Pitchfork reviews",
    "bandcamp_daily": "Bandcamp Daily",
    "orbit_release": "the orbit release calendar",
}

REVIVAL_LEADS = {
    "barely_played": "A song you met once and never saw again.",
    "fade_outs": "A song you wore out, then dropped.",
    "time_capsule": "Back for another listen.",
}


# ---------------------------------------------------------------- utilities

def _load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def _ym(datestr):
    """Month-precision date for prose: full dates put day-of-month tokens
    like '27' in front of the validator, which is correct to reject."""
    if not datestr:
        return None
    return str(datestr)[:7]


def _receipt(stat_id, claim, value):
    return {"stat_id": stat_id, "claim": claim, "value": value}


def _text_validates(text, receipts, issue_no):
    forms = V.receipt_value_forms(receipts)
    return all(V.token_allowed(t, forms, issue_no)
               for t in V.number_tokens(text))


def _safe_claims(receipts, issue_no):
    """Claims whose own number tokens all validate against the pool —
    guarantees template prose built from them passes the validator."""
    forms = V.receipt_value_forms(receipts)
    out, seen = [], set()
    for r in receipts:
        c = (r.get("claim") or "").strip().rstrip(".")
        if not c or c in seen:
            continue
        if all(V.token_allowed(t, forms, issue_no) for t in V.number_tokens(c)):
            out.append(c)
            seen.add(c)
    return out


def _dedupe_receipts(receipts):
    """Keep the first receipt per stat_id — pool-derived and model-derived
    stats for the same artist would otherwise repeat in prose."""
    out, seen = [], set()
    for r in receipts:
        sid = r.get("stat_id")
        if sid in seen:
            continue
        seen.add(sid)
        out.append(r)
    return out


def _artist_receipts(model, name):
    """Receipts for a raw artist name from the taste model's artists_index.
    Empty when the model or the artist is absent — never fabricated."""
    if not model or not name:
        return []
    row = (model.get("artists_index") or {}).get(norm_artist(name))
    if not row:
        return []
    raw = row.get("artist") or name
    key = norm_artist(name)
    out = []
    try:
        plays = int(float(row.get("plays", 0)))
        if plays:
            out.append(_receipt(f"artist_plays:{key}",
                                f"{raw}: {plays} plays", plays))
        hours = round(float(row.get("hours", 0.0)), 1)
        if hours:
            out.append(_receipt(f"artist_hours:{key}",
                                f"{raw}: {hours} hours", hours))
        skip = int(round(float(row.get("skip_rate", 0.0)) * 100))
        out.append(_receipt(f"artist_skip:{key}",
                            f"{raw}: {skip}% skip", skip))
    except (TypeError, ValueError):
        pass
    return out


def _label_receipts(label, artist=None):
    """Receipts for a label-roster lead: the reader's hours on the label,
    how many of its artists they play, and the lead's releases there. All
    three numbers come from the label model, none from prose."""
    name = label.get("name")
    if not name:
        return []
    key = norm_artist(name)
    out = []
    try:
        hours = round(float(label.get("hours") or 0), 1)
        if hours:
            out.append(_receipt(f"label_hours:{key}",
                                f"{name}: {hours} hours on your shelf", hours))
        n = int(label.get("artists") or 0)
        if n:
            out.append(_receipt(f"label_artists:{key}",
                                f"{name}: {n} of its artists you play", n))
        rel = int(label.get("releases") or 0)
        if rel and artist:
            out.append(_receipt(f"label_releases:{key}:{norm_artist(artist)}",
                                f"{artist}: {rel} releases on {name}", rel))
    except (TypeError, ValueError):
        pass
    return out


def _cluster(model, cluster_id):
    for c in (model or {}).get("clusters", []):
        if c.get("id") == cluster_id:
            return c
    return None


# ---------------------------------------------------------------- modules

def _pick_album(items, notes):
    """The highest-ranked candidate Spotify actually carries.

    `available` is written by engine.deliver.availability, which runs
    between select and issue precisely so this choice can be made before the
    module's receipts and prose are built around a record. When that stage
    has not run (no Spotify auth, an older proposal) nothing carries the
    flag and this is the old behaviour: take the top of the ranking.
    """
    for it in items:
        if it.get("available"):
            return it
    if any(it.get("available") is False for it in items):
        notes.append(
            "front_to_back: no checked candidate is on Spotify — taking the "
            "top-ranked pick, and the companion playlist will have no album")
    return items[0]


def _front_to_back(proposal, model, issue_no, notes):
    items = proposal.get("front_to_back") or []
    if not items:
        notes.append("front_to_back: no candidates in selection proposal — module dropped")
        return None
    it = _pick_album(items, notes)
    cluster_id = it.get("cluster")
    receipts = []
    cl = _cluster(model, cluster_id)
    if cl:
        receipts.extend(r for r in cl.get("receipts", []) if isinstance(r, dict))
    receipts.extend(_artist_receipts(model, it.get("artist")))
    receipts = _dedupe_receipts(receipts)
    if not receipts:
        notes.append("front_to_back: no receipts available (taste model missing "
                     "or artist/cluster not in it)")

    claims = _safe_claims(receipts, issue_no)
    basis = (it.get("basis") or "").strip()
    if basis and _text_validates(basis, receipts, issue_no):
        lead = basis[0].upper() + basis[1:]
        lead = lead.rstrip(".") + "."
    else:
        cname = (cl or {}).get("name") or cluster_id or "your listening"
        lead = f"This week's album, from the {cname} side of your listening."
    if claims:
        why = f"{lead} {'; '.join(claims)}."
    else:
        why = f"{lead} No receipts available for this pick."

    p4k = it.get("p4k")
    return {
        "type": "front_to_back",
        "cluster": cluster_id,
        "album": {
            "artist": it.get("artist"),
            "title": it.get("title"),
            "year": it.get("year"),
            "label": None,
            # Set by engine.deliver.availability when it confirmed this
            "spotify_album_uri": it.get("spotify_album_uri"),
            "spotify_url": it.get("spotify_url"),
            "cover_url": None,
            "odesli_url": None,
        },
        "why": why,
        "receipts": receipts,
        "critics": {"pitchfork": p4k if isinstance(p4k, dict) else None,
                    "fantano": None},
    }


# A lane takes its round-robin turn only while its next lead scores at least
# this fraction of the best lead still waiting anywhere. Below it the lane
# yields, and the strongest remaining lead is taken instead; a lane with one
# weak candidate is not forced into the top ten just to be represented.
RACK_LANE_FLOOR = 0.6


def rack_ranked(proposal):
    """Every Singles Rack lead in the proposal, in the order the rack uses.

    Round-robin across lanes, strongest lane first, each lane contributing
    its best remaining lead per round — so a rack of ten spans the lanes
    the harvest found rather than the one lane whose scores happen to run
    a hair higher (audit F13: ten lane-A leads at 1.00..0.91 shut out a
    lane-B lead at 0.90). Soft target, not a quota: a lane's turn is
    skipped while its next lead falls under RACK_LANE_FLOOR of the best
    lead waiting anywhere, and if no lane can take a turn the best lead is
    taken outright. Artists appear once.

    The writer takes the top `cap` of these; everything after that is the
    ranked reserve resolve_tracks draws on, in this same order, when a lead
    turns out to have no song behind it.
    """
    rack = proposal.get("singles_rack") or {}
    lanes = {cid: sorted(items or [], key=lambda it: -(it.get("score") or 0.0))
             for cid, items in rack.items()}
    lanes = {cid: items for cid, items in lanes.items() if items}
    order = sorted(lanes, key=lambda cid: (-(lanes[cid][0].get("score") or 0.0), cid))
    idx = {cid: 0 for cid in order}
    used, flat = set(), []

    def head(cid):
        items = lanes[cid]
        while idx[cid] < len(items) and \
                norm_artist(items[idx[cid]].get("artist") or "") in used:
            idx[cid] += 1
        return items[idx[cid]] if idx[cid] < len(items) else None

    def take(cid, it):
        idx[cid] += 1
        used.add(norm_artist(it.get("artist") or ""))
        flat.append((cid, it))

    while True:
        heads = [(cid, head(cid)) for cid in order]
        heads = [(cid, it) for cid, it in heads if it is not None]
        if not heads:
            break
        best = max(it.get("score") or 0.0 for _, it in heads)
        took = False
        for cid, it in heads:
            if head(cid) is not it:
                continue  # consumed earlier this round via the floor rule
            if (it.get("score") or 0.0) >= RACK_LANE_FLOOR * best:
                take(cid, it)
                took = True
        if not took:
            cid, it = max(heads, key=lambda h: ((h[1].get("score") or 0.0), -order.index(h[0])))
            take(cid, it)
    return flat


def rack_entry(cluster_id, it, model, issue_no):
    """One Singles Rack card, built from a ranked lead.

    Split out of _singles_rack so a lead promoted from the reserves after
    resolution gets an identical card: same receipts, same claim safety, same
    shape. A replacement must be indistinguishable from an original.
    """
    via = it.get("via")
    if it.get("relation") == "label" and it.get("label"):
        receipts = _label_receipts(it["label"], it.get("artist"))
        claims = _safe_claims(receipts, issue_no)
        lead = f"A door opened by the label {via}" if via else "A new door"
    else:
        receipts = _artist_receipts(model, via)
        claims = _safe_claims(receipts, issue_no)
        lead = f"A door opened by {via}" if via else "A new door"
    why = f"{lead}: {'; '.join(claims)}." if claims else f"{lead}."
    return {
        "artist": it.get("artist"),
        "title": it.get("title"),  # artist-level lead: null until curation
        "cluster": cluster_id,
        "why": why,
        "receipts": receipts,
        "spotify_track_uri": None,
        "spotify_url": None,
    }


def _singles_rack(proposal, model, issue_no, notes, cap=10):
    flat = rack_ranked(proposal)
    if not flat:
        notes.append("singles_rack: no candidates in selection proposal — module dropped")
        return None
    tracks = [rack_entry(cid, it, model, issue_no) for cid, it in flat[:cap]]
    if any(t["title"] is None for t in tracks):
        notes.append("singles_rack: titles are null pre-curation "
                     "(harvest leads are artist-level)")
    return {
        "type": "singles_rack",
        "intro": ("New names for you, each one a close cousin of an artist "
                  "you already play a lot."),
        "tracks": tracks,
    }


def _revival_desk(proposal, pools, model, issue_no, notes, cap=8):
    rd = proposal.get("revival_desk") or {}
    franchise = rd.get("franchise_suggestion") or "barely_played"
    entries = rd.get(franchise) or (pools or {}).get(franchise) or []
    if not entries:
        notes.append(f"revival_desk: no '{franchise}' entries in proposal or "
                     f"revival pools — module dropped")
        return None
    lead = REVIVAL_LEADS.get(franchise, "Back on the desk.")
    tracks = []
    for e in entries[:cap]:
        artist = e.get("artist")
        key = norm_artist(artist or "")
        receipts = []
        try:
            plays = int(float(e.get("plays", 0)))
        except (TypeError, ValueError):
            plays = 0
        last_ym = _ym(e.get("last_played"))
        if plays:
            noun = "play" if plays == 1 else "plays"
            claim = f"you: {plays} {noun}"
            if last_ym:
                claim += f", last {last_ym}"
            receipts.append(_receipt(f"track_plays:{key}", claim, plays))
        if e.get("artist_hours") is not None:
            try:
                h = round(float(e["artist_hours"]), 1)
                receipts.append(_receipt(f"artist_hours:{key}",
                                         f"{artist}: {h} hours lifetime", h))
            except (TypeError, ValueError):
                pass
        if e.get("peak_month_plays") is not None:
            try:
                pk = int(float(e["peak_month_plays"]))
                receipts.append(_receipt(
                    f"track_plays:{key}",
                    f"peak {pk} plays in {_ym(e.get('peak_month'))}", pk))
            except (TypeError, ValueError):
                pass
        receipts.extend(_artist_receipts(model, artist))
        receipts = _dedupe_receipts(receipts)
        claims = _safe_claims(receipts, issue_no)
        why = f"{lead} ({'; '.join(claims)}.)" if claims else lead
        tracks.append({
            "artist": artist,
            "title": e.get("track"),
            "album": e.get("album"),
            "plays": plays,
            "last_played": e.get("last_played"),
            "why": why,
            "receipts": receipts,
            "spotify_track_uri": None,
        })
    return {
        "type": "revival_desk",
        "franchise": franchise,
        "intro": (f"{franchise.replace('_', ' ').capitalize()}: songs from "
                  "your own shelf that deserve another listen."),
        "tracks": tracks,
    }


def _new_this_week(proposal, notes, cap=10):
    entries = proposal.get("new_this_week") or []
    if not entries:
        notes.append("new_this_week: no verified new releases — module dropped")
        return None
    releases = []
    for e in entries[:cap]:
        releases.append({
            "artist": e.get("artist"),
            "title": e.get("title"),
            "release_date": e.get("release_date"),
            "release_type": e.get("release_type"),
            "relationship": e.get("relationship"),
            "via": e.get("via"),
            "note": None,
        })
    from_labels = any(r.get("relationship") == "label" for r in releases)
    return {
        "type": "new_this_week",
        "intro": ("Fresh since the last issue, from your artists and the labels "
                  "you live on." if from_labels else
                  "Fresh since the last issue, from artists already deep in your listening."),
        "releases": releases,
    }


def _the_mix(proposal, model, issue_no, notes):
    entries = proposal.get("the_mix") or []
    if not entries:
        notes.append("the_mix: no candidates in proposal — module dropped")
        return None
    mixes = []
    for e in entries:
        key = (e.get("episode_alias") or e.get("show") or "mix").lower()
        receipts = [
            _receipt(f"mix_tracks:{key}",
                     f"{e['tracks_total']} tracks in the broadcast",
                     e["tracks_total"]),
            _receipt(f"mix_known:{key}",
                     f"{e['known_track_count']} tracks by artists from "
                     f"your record", e["known_track_count"]),
            _receipt(f"mix_new:{key}",
                     f"{e['new_track_count']} tracks new to you",
                     e["new_track_count"]),
        ]
        for k in (e.get("known_artists") or [])[:3]:
            nk = norm_artist(k["artist"])
            receipts.append(_receipt(f"artist_plays:{nk}",
                                     f"{k['artist']}: {k['plays']} plays",
                                     k["plays"]))
        receipts = _dedupe_receipts(receipts)
        claims = _safe_claims(receipts, issue_no)
        side = str(e.get("cluster") or "").replace("-", " ")
        lead = (f"A radio hour that fits your {side} listening" if side
                else "A radio hour that fits this week")
        why = f"{lead}: {'; '.join(claims)}." if claims else f"{lead}."
        mixes.append({
            "show": e.get("show"), "episode": e.get("episode"),
            "station": e.get("station"),
            "date": e.get("date"), "cluster": e.get("cluster"),
            "url": e.get("url"),
            "listen_urls": e.get("audio_sources") or [],
            "tracks_total": e["tracks_total"],
            "known_count": e["known_track_count"],
            "new_count": e["new_track_count"],
            "why": why,
            "receipts": receipts,
        })
    return {
        "type": "the_mix",
        "intro": ("Radio hours that fit the week: enough names you know to "
                  "trust them, enough you don't to make them worth the time. "
                  "Tracklists from NTS."),
        "mixes": mixes,
    }


def _critics_desk(proposal, model, issue_no, notes):
    cd = proposal.get("critics_desk") or {}
    entries = cd.get("albums") or []
    if not entries:
        notes.append("critics_desk: no eligible albums — module dropped")
        return None
    stats = cd.get("stats") or {}
    root_receipts = []
    if stats.get("top40_reviewed") is not None:
        root_receipts.append(_receipt(
            "p4k_top40_reviewed",
            f"{stats['top40_reviewed']} of your top 40 artists have been "
            f"reviewed by Pitchfork", stats["top40_reviewed"]))
    if stats.get("top40_avg_score") is not None:
        root_receipts.append(_receipt(
            "p4k_top40_avg",
            f"their reviews average {stats['top40_avg_score']}",
            stats["top40_avg_score"]))
    albums = []
    for e in entries:
        score = round(float(e["score"]), 1)
        key = norm_artist(e.get("artist") or "")
        receipts = [_receipt(f"p4k_score:{key}",
                             f"Pitchfork scored it {score}", score)]
        cl = _cluster(model, e.get("cluster"))
        lane = (cl or {}).get("name") or e.get("cluster") or "your lanes"
        lead = "Reviewed this month. " if e.get("fresh") else ""
        why = (f"{lead}Scored {score}"
               f"{', Best New Music' if e.get('bnm') else ''}. Loved by the "
               f"critics, close to the {lane} side of your taste, and never "
               f"once played by you.")
        if not _text_validates(why, receipts, issue_no):
            why = f"{lead}Close to the {lane} side of your taste, never played."
        albums.append({
            "artist": e["artist"], "title": e["title"],
            "year": e.get("year"), "score": score,
            "bnm": bool(e.get("bnm")), "fresh": bool(e.get("fresh")),
            "genre": e.get("genres"), "cluster": e.get("cluster"),
            "url": e.get("url"), "why": why, "receipts": receipts,
        })
    claims = _safe_claims(root_receipts, issue_no)
    intro = ("Records the critics loved, close to your taste, that you have "
             "never played." + (f" {'; '.join(claims)}." if claims else ""))
    return {
        "type": "critics_desk",
        "intro": intro,
        "receipts": root_receipts,
        "albums": albums,
    }


def _catalog_room(proposal, model, issue_no, notes):
    c = proposal.get("catalog_room")
    if not c:
        notes.append("catalog_room: no candidate — module dropped")
        return None
    key = norm_artist(c["artist"])
    top3_pct = int(round(float(c["top3_share"]) * 100))
    receipts = _dedupe_receipts([
        _receipt(f"artist_plays:{key}", f"{c['artist']}: {c['plays']} plays",
                 c["plays"]),
        _receipt(f"catalog_breadth:{key}",
                 f"across only {c['unique_tracks']} unique tracks",
                 c["unique_tracks"]),
        _receipt(f"catalog_top3:{key}",
                 f"the top 3 tracks are {top3_pct}% of all of it", top3_pct),
        _receipt(f"artist_hours:{key}", f"{c['hours']} hours lifetime",
                 c["hours"]),
        _receipt(f"artist_skip:{key}",
                 f"at {int(round(float(c.get('skip_rate', 0)) * 100))}% skip",
                 int(round(float(c.get("skip_rate", 0)) * 100))),
    ])
    claims = _safe_claims(receipts, issue_no)
    why = (f"An artist you love narrowly: {'; '.join(claims)}. The albums "
           f"below have never been opened.") if claims else \
        "An artist you love narrowly. The albums below have never been opened."
    return {
        "type": "catalog_room",
        "artist": c["artist"],
        "why": why,
        "receipts": receipts,
        "unheard": [{"title": a["title"], "year": a.get("year")}
                    for a in c.get("unheard", [])],
        "heard_note": ("On the record already: "
                       + ", ".join(c.get("heard_on_record", [])[:4])
                       if c.get("heard_on_record") else None),
    }


def _ledger(in_dir, issue_no, notes):
    """The self-grading module: how the PREVIOUS issue actually performed.

    Deliberately reports the shape of the adoption, not just the rate — a
    batch of first-plays on one date is the companion playlist being played,
    and calling that N independent successes would be the exact kind of
    flattery this project exists to avoid.
    """
    led = _load_json(Path(in_dir) / "ledger.json")
    if not led:
        return None                      # silent: issue 1 has no predecessor
    s = led.get("summary") or {}
    scored = s.get("scored_picks") or 0
    if not scored:
        notes.append("ledger: no scored picks — module dropped")
        return None
    played = s.get("played") or 0
    prev = led.get("issue")
    days = led.get("window_days") or 0
    returned = s.get("returned_to") or []
    sessions = s.get("batch_sessions") or []
    pct = int(round(100 * played / scored))

    receipts = _dedupe_receipts([
        _receipt(f"ledger_scored:{prev}",
                 f"{scored} picks were measurable", scored),
        _receipt(f"ledger_played:{prev}",
                 f"{played} of them got played", played),
        _receipt(f"ledger_rate:{prev}", f"{pct}% adoption", pct),
        _receipt(f"ledger_window:{prev}",
                 f"{days} days since it went out", days),
        _receipt(f"ledger_returned:{prev}",
                 f"{len(returned)} earned a second play", len(returned)),
    ])
    claims = _safe_claims(receipts, issue_no)

    caveat = ""
    if sessions:
        big = max(sessions, key=lambda x: x["picks"])
        if big["picks"] >= max(3, int(0.6 * played)):
            caveat = (" Most of that happened in one sitting, with the "
                      "companion playlist on, rather than separate returns "
                      "to separate records.")
    verdict = (f"Issue {prev:03d}, graded against what actually got played: "
               f"{'; '.join(claims)}.{caveat}") if claims else \
        f"Issue {prev:03d}, graded against what actually got played."

    rows = []
    for p in led.get("picks", []):
        if not p.get("scored"):
            continue
        rows.append({
            "label": p.get("label"),
            "module": p.get("module"),
            "played": bool(p.get("played")),
            "plays": int(p.get("plays") or 0),
            "first_play": p.get("first_play"),
        })
    rows.sort(key=lambda r: (not r["played"], -r["plays"], r["label"] or ""))
    return {
        "type": "ledger",
        "intro": ("Last issue, graded. Every pick was new to you, so any "
                  "play at all counts as a result."),
        "verdict": verdict,
        "receipts": receipts,
        "rows": rows,
    }


# ---------------------------------------------------------------- copy pairing
#
# Copy lists carry prose for items the template already built, and _merge
# lays them on by position. That is only right while the copy author keeps
# the proposal's order — Issue 002's new_this_week notes were written in
# editorial order (the release out today first, one note per artist) and
# landed on the wrong releases, stats and all. So for that module a copy
# entry may carry identity — ``artist``, plus ``title`` / ``release_type``
# / ``release_date`` when one artist has several releases listed — and a
# note without identity is paired by evidence, in this order:
#
#   1. identity keys on the copy entry;
#   2. numbers in the note that are one listed artist's own stats (plays,
#      hours, skip %, unique tracks) and nobody else's;
#   3. the artist the note names;
#   4. position — only when no other note had to move, i.e. the copy list
#      is demonstrably in proposal order.
#
# A note that points elsewhere (names or quotes another listed artist and
# not its own) is refused rather than guessed, and every refusal and every
# re-pairing is recorded in generated.notes. Within one artist, the title,
# a release-type word (EP / album / single) or "today" (the issue date)
# picks the release; otherwise the first unclaimed one in proposal order.
# The validator independently rejects a note that names another listed
# artist, so a wrong pairing cannot reach the site.

def _release_stat_forms(entry, model):
    """Number-token forms of a proposal release's artist stats (plays, hours,
    skip %, unique tracks) from its verification artist_row, else the taste
    model. Empty when neither knows the artist — never estimated."""
    row = (entry.get("verification") or {}).get("artist_row") or None
    if not row and model:
        row = (model.get("artists_index") or {}).get(
            norm_artist(entry.get("artist") or ""))
    if not row:
        return set()
    receipts = []
    try:
        plays = int(float(row.get("plays") or 0))
        if plays:
            receipts.append(_receipt("plays", "", plays))
        hours = round(float(row.get("hours") or 0.0), 1)
        if hours:
            receipts.append(_receipt("hours", "", hours))
        if row.get("skip_rate") not in (None, ""):
            receipts.append(_receipt(
                "skip", "", int(round(float(row["skip_rate"]) * 100))))
        unique = int(float(row.get("unique_tracks") or 0))
        if unique:
            receipts.append(_receipt("unique", "", unique))
    except (TypeError, ValueError):
        pass
    return V.receipt_value_forms(receipts)


def _evidence_tokens(text):
    """Number tokens in a note that can identify an artist: the validator's
    whitelist (integers <= 12, years) is too common to count as evidence."""
    out = set()
    for tok in V.number_tokens(text):
        t = tok.replace(",", "").rstrip(".")
        if not t:
            continue
        if t.isdigit():
            v = int(t)
            if v <= 12 or 1950 <= v <= 2030:
                continue
        out.add(t)
    return out


def _title_mentioned(text, title):
    nt = norm_title(title or "")
    if len(nt) < 3:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(nt) + r"(?![a-z0-9])",
                     norm_artist(text or "")) is not None


def _snip(text, n=48):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _pair_release_notes(base, copy_entries, stat_forms, issue_date, notes,
                        label="new_this_week"):
    """Pair copy entries with the releases they describe.

    base         the built module's releases (dicts with artist/title/...)
    copy_entries the copy's releases list (dicts with "note", optionally
                 identity keys)
    stat_forms   per base release: set of number-token forms of its
                 artist's stats (see _release_stat_forms)
    Returns an over-list aligned with ``base`` — ``{"note": ...}`` for a
    paired release, ``{}`` otherwise — so _merge's positional list merge
    lands every note on its release. Appends what moved and what was
    refused to ``notes``.
    """
    n = len(base)
    keys = [norm_artist(r.get("artist") or "") for r in base]
    raw = {}
    for r, k in zip(base, keys):
        raw.setdefault(k, r.get("artist"))
    claimed = [None] * n                      # base index -> copy index
    target = [None] * len(copy_entries)       # copy index -> base index
    how = [None] * len(copy_entries)
    refused = []

    def refuse(ci, why):
        refused.append((ci, why))

    def label_of(i):
        return f"{base[i].get('artist')} — {base[i].get('title')}"

    def stat_hits(text):
        toks = _evidence_tokens(text)
        hits = {}
        if toks:
            for i, forms in enumerate(stat_forms):
                got = toks & forms
                if got:
                    hits.setdefault(keys[i], set()).update(got)
        return hits                           # artist key -> tokens matched

    def mention_hits(text):
        return {k for k in raw if k and V.mentions_artist(text, raw[k])}

    def pick_within(key, text, entry):
        """The release of one artist that a note/entry describes: unclaimed
        ones, narrowed by explicit keys, then title, release-type word,
        "today"; else the first in proposal order. None when nothing fits."""
        cands = [i for i, k in enumerate(keys) if k == key and claimed[i] is None]
        if not cands:
            return None
        if entry.get("title"):
            want = norm_title(entry["title"])
            cands = [i for i in cands if norm_title(base[i].get("title") or "") == want]
        if entry.get("release_type"):
            want = str(entry["release_type"]).lower()
            cands = [i for i in cands
                     if (base[i].get("release_type") or "").lower() == want]
        if entry.get("release_date"):
            cands = [i for i in cands
                     if base[i].get("release_date") == entry["release_date"]]
        if len(cands) > 1:
            by_title = [i for i in cands if _title_mentioned(text, base[i].get("title"))]
            if by_title:
                cands = by_title
        if len(cands) > 1:
            types = V.release_type_mentions(text)
            if len(types) == 1:
                want = next(iter(types))
                by_type = [i for i in cands
                           if (base[i].get("release_type") or "").lower() == want]
                if by_type:
                    cands = by_type
        if len(cands) > 1 and issue_date and re.search(
                r"(?<![a-z])today(?![a-z])", norm_artist(text)):
            by_date = [i for i in cands if base[i].get("release_date") == issue_date]
            if by_date:
                cands = by_date
        return cands[0] if cands else None

    # pass 1: identity and evidence
    pending = []
    for ci, entry in enumerate(copy_entries):
        if not isinstance(entry, dict):
            refuse(ci, "entry is not an object")
            continue
        text = entry.get("note") if isinstance(entry.get("note"), str) else ""
        hits = stat_hits(text)
        ments = mention_hits(text)
        key = None
        if entry.get("artist"):
            ident = entry["artist"]
            key = norm_artist(ident)
            if key not in raw:
                named = {k for k in raw if k and V.mentions_artist(ident, raw[k])}
                key = next(iter(named)) if len(named) == 1 else None
            if key is None:
                refuse(ci, f"identity {ident!r} is not a listed release artist")
                continue
            if hits and key not in hits:
                refuse(ci, f"identity says {raw[key]!r} but its numbers are "
                           f"{raw[next(iter(hits))]!r}'s")
                continue
            if ments and key not in ments:
                refuse(ci, f"identity says {raw[key]!r} but the note names "
                           f"{raw[next(iter(ments))]!r}")
                continue
            how[ci] = "identity"
        elif len(hits) == 1:
            key = next(iter(hits))
            if ments and key not in ments:
                refuse(ci, f"numbers are {raw[key]!r}'s but the note names "
                           f"{raw[next(iter(ments))]!r}")
                continue
            how[ci] = "stats " + ", ".join(sorted(hits[key]))
        elif len(hits) > 1:
            tie = [k for k in ments if k in hits]
            if len(tie) == 1:
                key = tie[0]
                how[ci] = "name + stats"
            else:
                refuse(ci, "numbers match several listed artists: "
                           + ", ".join(repr(raw[k]) for k in sorted(hits)))
                continue
        elif len(ments) == 1:
            key = next(iter(ments))
            how[ci] = "name"
        elif len(ments) > 1:
            refuse(ci, "names several listed artists: "
                       + ", ".join(repr(raw[k]) for k in sorted(ments)))
            continue
        else:
            pending.append(ci)
            continue
        idx = pick_within(key, text, entry)
        if idx is None:
            refuse(ci, f"no unclaimed {raw[key]!r} release matches it")
            continue
        claimed[idx], target[ci] = ci, idx

    # pass 2: position, only if the evidence says the list is in order
    moved = any(t is not None and t != ci for ci, t in enumerate(target))
    for ci in pending:
        if moved:
            refuse(ci, "no artist or stats in the note, and the copy list is "
                       "not in proposal order (other notes had to move)")
        elif ci >= n:
            refuse(ci, f"position {ci} is beyond the {n} listed releases")
        elif claimed[ci] is not None:
            refuse(ci, f"position {ci} already carries note {claimed[ci]}")
        else:
            claimed[ci], target[ci], how[ci] = ci, ci, "position"

    over = [{} for _ in range(n)]
    attached = moved_n = positional = 0
    for ci, idx in enumerate(target):
        if idx is None:
            continue
        note = copy_entries[ci].get("note")
        if isinstance(note, str) and note.strip():
            over[idx] = {"note": note}
            attached += 1
        if how[ci] == "position":
            positional += 1
        if idx != ci:
            moved_n += 1
            notes.append(f"{label}: copy note {ci} ({_snip(note)!r}) → "
                         f"{label_of(idx)} [{how[ci]}]")
    for ci, why in refused:
        note = copy_entries[ci].get("note") if isinstance(copy_entries[ci], dict) else None
        notes.append(f"{label}: copy note {ci} ({_snip(note)!r}) REFUSED — {why}")
    summary = (f"{label}: {attached} of {len(copy_entries)} copy notes attached "
               f"({moved_n} re-paired, {positional} by position, "
               f"{len(refused)} refused)")
    if positional and not moved_n:
        summary += " — add artist keys to the copy entries to make the pairing explicit"
    notes.append(summary)
    return over


def _align_copy(copy_doc, modules, proposal, model, issue_date, notes):
    """Rewrite the copy's new_this_week.releases into a list aligned with
    the built module (see _pair_release_notes); everything else in the
    copy passes through untouched for _merge."""
    base = next((m for m in modules if m.get("type") == "new_this_week"), None)
    cmods = copy_doc.get("modules")
    if base is None or not isinstance(cmods, list):
        return copy_doc
    forms_by_release = {}
    for e in proposal.get("new_this_week") or []:
        k = (norm_artist(e.get("artist") or ""), norm_title(e.get("title") or ""),
             e.get("release_date"))
        forms_by_release.setdefault(k, _release_stat_forms(e, model))
    stat_forms = [forms_by_release.get(
        (norm_artist(r.get("artist") or ""), norm_title(r.get("title") or ""),
         r.get("release_date")), set()) for r in base["releases"]]
    out_mods = []
    for cm in cmods:
        if (isinstance(cm, dict) and cm.get("type") == "new_this_week"
                and isinstance(cm.get("releases"), list)):
            cm = dict(cm)
            cm["releases"] = _pair_release_notes(
                base["releases"], cm["releases"], stat_forms, issue_date, notes)
        out_mods.append(cm)
    out = dict(copy_doc)
    out["modules"] = out_mods
    return out


# ---------------------------------------------------------------- assembly

def _verification_block(model, notes):
    g = (model or {}).get("global") or {}
    tracks_n = g.get("tracks")
    artists_n = g.get("artists")
    if tracks_n is None or artists_n is None:
        try:
            from engine.lib import history
            s = history.stats()
            tracks_n, artists_n = s["tracks"], s["artists"]
        except Exception as e:  # degrade, never invent
            notes.append(f"verification counts unavailable: {e}")
            tracks_n = artists_n = None
    return {
        "tracks_checked_against": tracks_n,
        "artists_checked_against": artists_n,
        "rounds": 2,
        "method": ("two-round normalized match against the merged play log: "
                   "exact artist/track keys, then near-name and "
                   "title-collision review"),
    }


# ---------------------------------------------------------------- copy guard

# What a copy file is allowed to write, by where it sits. The top level owns
# the issue's name and standfirst; a module owns its prose; an item owns its
# note. Nothing else. A copy used to be merged as-is, key for key, so a
# "prose" file could rename an artist, retitle a track, swap a URI, or edit a
# receipt, and the numbers gate would pass it because the numbers still
# matched. The September audit reproduced exactly that. Identity keys may
# appear in a copy as anchors (they are useful to whoever writes it), but
# they are compared, never written: a mismatch is an error, not an edit.
_PROSE_TOP = {"title", "dek", "masthead_note"}
_PROSE_MODULE = {"intro", "why", "verdict", "heard_note", "note"}
_PROSE_ITEM = {"why", "note"}
_ITEM_LISTS = {"tracks", "albums", "mixes", "releases", "unheard"}
_IDENTITY = {"artist", "title", "album", "show", "episode", "track"}


def _same(a, b):
    return norm_artist(str(a or "")) == norm_artist(str(b or ""))


def guard_copy(base, over, notes, path="", level="top"):
    """Return (safe_copy, errors). safe_copy carries only the prose keys the
    level permits; identity keys are checked against base and dropped; any
    other key is dropped and named in notes."""
    errors = []
    if isinstance(over, dict):
        if not isinstance(base, dict):
            return None, errors
        allowed = {"top": _PROSE_TOP | {"modules"},
                   "module": _PROSE_MODULE | _ITEM_LISTS | {"type"},
                   "item": _PROSE_ITEM}[level]
        out = {}
        for k, v in over.items():
            here = f"{path}.{k}" if path else k
            if level != "top" and k in _IDENTITY:
                if k in base and not _same(base.get(k), v):
                    errors.append(f"copy changes identity at {here}: "
                                  f"{base.get(k)!r} -> {v!r}")
                continue                              # an anchor, never written
            if k not in allowed:
                notes.append(f"copy key ignored at {here} (not prose)")
                continue
            if k == "modules" and isinstance(v, list):
                by_type = {m.get("type"): m for m in base.get("modules") or []
                           if isinstance(m, dict)}
                mods = []
                for cm in v:
                    if not isinstance(cm, dict):
                        continue
                    bm = by_type.get(cm.get("type"))
                    if bm is None:
                        continue
                    sm, e = guard_copy(bm, cm, notes, f"{here}[{cm.get('type')}]", "module")
                    errors.extend(e)
                    if sm is not None:
                        mods.append(sm)
                out[k] = mods
            elif k in _ITEM_LISTS and isinstance(v, list):
                bl = base.get(k) or []
                items = []
                for i, ci in enumerate(v):
                    if i >= len(bl):
                        notes.append(f"copy item ignored at {here}[{i}]: beyond the issue's {len(bl)}")
                        continue
                    if not isinstance(ci, dict):
                        items.append(None); continue
                    si, e = guard_copy(bl[i], ci, notes, f"{here}[{i}]", "item")
                    errors.extend(e)
                    items.append(si)
                out[k] = items
            else:
                out[k] = v
        return out, errors
    return over, errors


def _merge(base, over):
    """Recursive prose merge: dicts key-wise; lists of typed dicts matched
    by 'type', other lists by index; scalars from the copy win. An explicit
    null in the copy keeps the base value."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = _merge(base.get(k), v) if k in base else v
        return out
    if isinstance(base, list) and isinstance(over, list):
        typed = (base and over
                 and all(isinstance(x, dict) and "type" in x for x in base)
                 and all(isinstance(x, dict) and "type" in x for x in over))
        if typed:
            by_type = {}
            for o in over:
                by_type.setdefault(o["type"], o)
            return [_merge(b, by_type[b["type"]]) if b["type"] in by_type else b
                    for b in base]
        return [_merge(b, over[i]) if i < len(over) else b
                for i, b in enumerate(base)]
    return over if over is not None else base


def build_issue(n, date, in_dir, copy_doc=None):
    """Build (and NOT yet validate) the issue document. Returns (doc, notes)."""
    notes = []
    in_dir = Path(in_dir)
    proposal = _load_json(in_dir / "selection-proposal.json")
    if proposal is None:
        raise SystemExit(
            f"writer: {in_dir / 'selection-proposal.json'} missing or "
            f"unreadable — no proposal, no issue (run `select` first, or "
            f"point --in at a fixtures dir)")
    model = _load_json(in_dir / "taste-model.json")
    if model is None:
        notes.append("taste-model.json missing — artist/cluster receipts degraded")
    pools = _load_json(in_dir / "revival-pools.json")
    if pools is None:
        notes.append("revival-pools.json missing — revival desk relies on the "
                     "proposal's own entries")

    # Running order: the singles open the issue, the album of the week follows.
    modules = [m for m in (
        _singles_rack(proposal, model, n, notes),
        _front_to_back(proposal, model, n, notes),
        _the_mix(proposal, model, n, notes),
        _revival_desk(proposal, pools, model, n, notes),
        _critics_desk(proposal, model, n, notes),
        _catalog_room(proposal, model, n, notes),
        _new_this_week(proposal, notes),
        _ledger(in_dir, n, notes),
    ) if m]
    if not modules:
        raise SystemExit("writer: selection proposal yielded zero modules — "
                         "nothing to publish")

    doc = {
        "issue": n,
        "date": date,
        "title": f"Issue {n:03d}",
        "dek": "A new week of listening, picked from your own history.",
        "masthead_note": ("Every number in this issue comes from your own "
                          "listening history."),
        "modules": modules,
        "verification": _verification_block(model, notes),
        "companion_playlist": {"name": f"discovery issue {n:03d}",
                               "uris": [], "spotify_url": None},
        "generated": {"engine_version": ENGINE_VERSION,
                      "generated_at": datetime.datetime.now(
                          datetime.timezone.utc).isoformat(timespec="seconds"),
                      "llm": copy_doc is not None,
                      "notes": notes},
    }

    if copy_doc is not None:
        have = {m.get("type") for m in modules}
        for m in copy_doc.get("modules", []) or []:
            if isinstance(m, dict) and m.get("type") not in have:
                notes.append(f"copy: module type {m.get('type')!r} not in the "
                             f"built issue — override ignored (prose cannot "
                             f"conjure data)")
        aligned = _align_copy(copy_doc, modules, proposal, model, date, notes)
        safe, errs = guard_copy(doc, aligned, notes)
        if errs:
            raise SystemExit("writer: the copy is not prose-only and was refused:\n  "
                             + "\n  ".join(errs))
        doc = _merge(doc, safe)
        doc["generated"]["llm"] = True
        doc["generated"]["notes"] = notes
    return doc, notes


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="python3 -m engine.editorial.writer",
        description="Assemble, validate, and write issues/issue-NNN.json")
    p.add_argument("--n", type=int, default=1, help="issue number")
    p.add_argument("--no-llm", dest="no_llm", action="store_true",
                   help="template prose only (receipts joined plainly)")
    p.add_argument("--copy", help="prose overrides JSON (same structure)")
    p.add_argument("--in", dest="in_dir", default=None,
                   help="input dir (default: out/)")
    p.add_argument("--date", default=None, help="issue date YYYY-MM-DD "
                   "(default: today)")
    args = p.parse_args(argv)

    cfg = load_config()
    in_dir = args.in_dir or cfg["OUT_DIR"]
    date = args.date or datetime.date.today().isoformat()

    copy_doc = None
    if args.copy:
        copy_doc = _load_json(args.copy)
        if copy_doc is None:
            print(f"writer: --copy {args.copy} missing or unreadable",
                  file=sys.stderr)
            return 2
    if not args.copy and not args.no_llm:
        print("writer: no --copy prose supplied; falling back to the "
              "template (--no-llm behavior)", file=sys.stderr)

    doc, notes = build_issue(args.n, date, in_dir, copy_doc)

    errors = V.validate_issue(doc)
    if errors:
        for e in errors:
            print(f"VALIDATION: {e}", file=sys.stderr)
        print(f"writer: issue {args.n:03d} REJECTED — {len(errors)} "
              f"violation(s); nothing written", file=sys.stderr)
        return 1

    name = f"issue-{args.n:03d}.json"
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    issue_path = Path(cfg["ISSUES_DIR"]) / name
    site_path = Path(cfg["SITE_ISSUES_DIR"]) / name
    issue_path.write_text(body)
    site_path.write_text(body)
    print(f"wrote {issue_path}")
    print(f"wrote {site_path}")
    for note in notes:
        print(f"note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
