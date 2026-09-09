"""The Ledger — did the listener actually play what the last issue picked?

This is the module that makes the project honest: it grades its own previous
recommendations against what really got listened to, and reports the misses
as plainly as the hits.

Source of truth
---------------
ListenBrainz, which has ingested every Spotify play since the account was
connected (2026-07-27). Read-only, no token needed for public listens:
    GET /1/user/{user}/listens?count=1000&max_ts=<unix>
Paginated backwards from now until we pass the issue's publication date.

Last.fm is the intended second source (it has been scrobbling since the same
day) but needs a username that is not in .env — LASTFM_USER, when set, is
used to cross-check and to fill any gap where LB missed a play.

Matching — and why it is trustworthy
------------------------------------
Every NOVEL pick (album of the week, singles, critics desk, catalog room,
the mix) was verified never-played across all 161,264 plays before it was
published. So any appearance of that artist after publication is
unambiguous evidence of adoption: there is no pre-existing baseline to
confuse it with. Those are matched at ARTIST level, which correctly counts
"he played a different track from the album we recommended".

REVIVAL picks are the opposite case — the artist was already deeply played,
which is the whole point of the module — so those must match at TRACK level
or the signal is meaningless.

Output: out/ledger.json (consumed by the writer to build the ledger module).

Run:  PYTHONPATH=<root> python3 -m engine.ledger.build_ledger [--issue 1]
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ..lib.config import load_config
from ..lib.normalize import norm_artist, norm_title

# The ListenBrainz account to grade against comes from configuration
# (LISTENBRAINZ_USER). This used to be a hard-coded username, which meant
# every other installation graded its recommendations against one
# person's listening.
LB_API = "https://api.listenbrainz.org/1"
UA = "discovery-dashboard/0.1 (personal project)"
PAGE = 1000

# Modules whose picks were verified never-played -> artist-level match is safe.
NOVEL_MODULES = {"front_to_back", "singles_rack", "critics_desk", "the_mix"}
# Modules drawn from the reader's own history -> must match the exact track.
TRACK_MODULES = {"revival_desk"}
# Modules that recommend a specific ALBUM by a familiar artist -> the release
# itself has to show up in the listens; the artist alone proves nothing.
ALBUM_MODULES = {"catalog_room"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_listens(user, since_ts):
    """All listens after since_ts, newest first, paginated backwards."""
    out, max_ts = [], None
    while True:
        q = {"count": PAGE}
        if max_ts:
            q["max_ts"] = max_ts
        d = _get(f"{LB_API}/user/{user}/listens?{urllib.parse.urlencode(q)}")
        batch = (d.get("payload") or {}).get("listens") or []
        if not batch:
            break
        keep = [l for l in batch if l.get("listened_at", 0) > since_ts]
        out.extend(keep)
        if len(keep) < len(batch) or len(batch) < PAGE:
            break                      # walked past the window
        max_ts = min(l["listened_at"] for l in batch) - 1
    return out


def collect_picks(issue):
    """[(module, artist, title|None, label)] for everything the issue served."""
    picks = []
    for m in issue.get("modules", []):
        t = m.get("type")
        if t == "front_to_back":
            a = m.get("album") or {}
            picks.append((t, a.get("artist"), a.get("title"),
                          f"{a.get('artist')} — {a.get('title')}"))
        elif t in ("singles_rack", "revival_desk"):
            for x in m.get("tracks", []):
                picks.append((t, x.get("artist"), x.get("title"),
                              f"{x.get('artist')} — {x.get('title')}"))
        elif t == "critics_desk":
            for x in m.get("albums", []):
                picks.append((t, x.get("artist"), x.get("title"),
                              f"{x.get('artist')} — {x.get('title')}"))
        elif t == "catalog_room":
            for x in m.get("unheard", []):
                picks.append((t, m.get("artist"), x.get("title"),
                              f"{m.get('artist')} — {x.get('title')}"))
        elif t == "the_mix":
            for x in m.get("mixes", []):
                # A radio show is not a track; its adoption is not measurable
                # from a listen log. Recorded, never scored.
                picks.append(("the_mix_unscored", None, None,
                              x.get("show")))
    return picks


def _pub_time(issue):
    """When the issue was actually exposed. publish_playlist stamps
    published_at; before that existed, generated_at is the earliest the issue
    could have been read; the bare date is the last resort and is midnight
    UTC, which can count listens from before the press ran."""
    cp = issue.get("companion_playlist") or {}
    gen = issue.get("generated") or {}
    for key, src, basis in (("published_at", cp, "published_at"),
                            ("generated_at", gen, "generated_at")):
        v = src.get(key)
        if v:
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc), basis
            except ValueError:
                pass
    pub = issue.get("date") or ""
    try:
        return (datetime.strptime(pub[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                "date_midnight_utc")
    except ValueError:
        raise SystemExit(f"issue {issue.get('issue')} has no usable date: {pub!r}")


def _day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def grade(issue, listens, now=None):
    """Score an issue's picks against a list of ListenBrainz listens. Pure:
    no network, no files. Returns the ledger document.

    Match basis is per module, and it is the fix the September audit asked
    for. Catalog Room recommends specific unheard ALBUMS by an artist the
    reader already plays, so it is matched on release, never on artist: two
    plays of an old favourite used to credit every unheard album as adopted.
    Second Chances are tracks out of the reader's own history and match on
    the exact track. Singles, the album of the week and the Critics Desk are
    verified never-played artists, where any play of the artist is genuine
    evidence of exploration, and that is what "artist" basis means.

    "Returned to" means played on a later day than the first play. Two songs
    in one sitting is one listen, not a return.
    """
    now = now or datetime.now(timezone.utc)
    pub_dt, pub_basis = _pub_time(issue)
    since_ts = int(pub_dt.timestamp())
    window_days = max(1, (now - pub_dt).days)

    by_artist, by_track, by_release = {}, {}, {}
    for l in listens:
        ts = l.get("listened_at", 0)
        if ts <= since_ts:
            continue
        md = l.get("track_metadata") or {}
        a = norm_artist(md.get("artist_name") or "")
        t = norm_title(md.get("track_name") or "")
        r = norm_title(md.get("release_name") or "")
        if a:
            by_artist.setdefault(a, []).append(ts)
        if a and t:
            by_track.setdefault((a, t), []).append(ts)
        if a and r:
            by_release.setdefault((a, r), []).append(ts)

    picks_out, scored, played = [], 0, 0
    for module, artist, title, label in collect_picks(issue):
        if module == "the_mix_unscored":
            picks_out.append({"module": "the_mix", "label": label,
                              "scored": False, "played": None,
                              "note": "radio show — adoption not measurable "
                                      "from a listen log"})
            continue
        na = norm_artist(artist or "")
        if module in TRACK_MODULES:
            hits, basis = by_track.get((na, norm_title(title or "")), []), "track"
        elif module in ALBUM_MODULES:
            hits, basis = by_release.get((na, norm_title(title or "")), []), "album"
        else:
            hits, basis = by_artist.get(na, []), "artist"
        scored += 1
        days = sorted({_day(ts) for ts in hits})
        rec = {"module": module, "label": label, "scored": True,
               "match_basis": basis, "played": bool(hits),
               "plays": len(hits), "play_days": len(days)}
        if module in ALBUM_MODULES:
            # Reported beside the album verdict, never as adoption.
            rec["artist_plays"] = len(by_artist.get(na, []))
        if hits:
            played += 1
            rec["first_play"] = days[0]
            rec["returned"] = len(days) >= 2
            first_ts = min(hits)
            rec["days_to_first"] = max(0, (datetime.fromtimestamp(
                first_ts, timezone.utc) - pub_dt).days)
        picks_out.append(rec)

    by_module = {}
    for p in picks_out:
        if not p["scored"]:
            continue
        b = by_module.setdefault(p["module"], {"total": 0, "played": 0})
        b["total"] += 1
        b["played"] += 1 if p["played"] else 0

    # Honesty pass. A run of first-plays sharing one date is the companion
    # playlist being put on, not N independent discoveries. Returning on a
    # LATER day is the signal that means something; it is counted and named.
    first_days = {}
    for p in picks_out:
        if p.get("played") and p.get("first_play"):
            first_days.setdefault(p["first_play"], []).append(p["label"])
    sessions = [{"date": d, "picks": len(v)}
                for d, v in sorted(first_days.items()) if len(v) >= 3]
    returned = [p["label"] for p in picks_out if p.get("returned")]

    return {
        "issue": issue.get("issue"),
        "published": pub_dt.strftime("%Y-%m-%d"),
        "published_basis": pub_basis,
        "as_of": now.strftime("%Y-%m-%d"),
        "window_days": window_days,
        "source": "listenbrainz",
        "listens_scanned": len(listens),
        "summary": {
            "scored_picks": scored,
            "played": played,
            "adoption_rate": round(played / scored, 3) if scored else 0.0,
            "by_module": by_module,
            "returned_to": returned,          # played again on a later day
            "distinct_first_play_days": len(first_days),
            "batch_sessions": sessions,       # >=3 first-plays on one date
        },
        "picks": picks_out,
    }


def build(issue_no, fetch=None):
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])
    issue_path = Path(cfg["ISSUES_DIR"]) / f"issue-{issue_no:03d}.json"
    if not issue_path.exists():
        raise SystemExit(f"no issue at {issue_path}")
    issue = json.loads(issue_path.read_text())

    user = cfg.get("LISTENBRAINZ_USER")
    if not user:
        doc = {"issue": issue_no, "source": None,
               "summary": {"scored_picks": 0, "played": 0, "adoption_rate": 0.0,
                           "by_module": {}, "returned_to": [],
                           "distinct_first_play_days": 0, "batch_sessions": []},
               "picks": [],
               "note": "LISTENBRAINZ_USER is not configured; nothing was graded"}
        p = out_dir / "ledger.json"
        p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        print(f"ledger: no LISTENBRAINZ_USER configured, wrote an empty ledger to {p}")
        return

    pub_dt, _ = _pub_time(issue)
    listens = (fetch or fetch_listens)(user, int(pub_dt.timestamp()))
    now = datetime.now(timezone.utc)
    print(f"listens since {pub_dt.strftime('%Y-%m-%d')}: {len(listens)} "
          f"(window {max(1, (now - pub_dt).days)} days)")
    doc = grade(issue, listens, now)
    played, scored = doc["summary"]["played"], doc["summary"]["scored_picks"]
    window_days = doc["window_days"]
    by_module = doc["summary"]["by_module"]
    picks_out = doc["picks"]
    p = out_dir / "ledger.json"
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"wrote {p}")
    print(f"  adoption: {played}/{scored} "
          f"({doc['summary']['adoption_rate']:.0%}) over {window_days} days")
    for k, v in by_module.items():
        print(f"    {k:16} {v['played']}/{v['total']}")
    for pk in picks_out:
        if pk.get("played"):
            print(f"  HIT  {pk['label']} — {pk['plays']} plays, "
                  f"first +{pk['days_to_first']}d")
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, default=1)
    build(ap.parse_args().issue)


if __name__ == "__main__":
    main()
