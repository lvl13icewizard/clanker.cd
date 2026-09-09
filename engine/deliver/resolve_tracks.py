"""Resolve every issue pick to a Spotify URI — the missing curation stage.

CONTRACTS.md says track_candidates are artist-level leads ("title null is
normal — the curation stage picks tracks") and that "curation happens outside
the pipeline". Outside the pipeline meant by hand, which is fine for a press
someone is sitting at and fatal for the scheduled one: issues 001 and 002 got
their titles and URIs typed in, and issue 003 published a companion playlist
of nothing at all, because no stage in weekly.sh ever asked Spotify anything.

This is that stage.

  singles_rack   artist-level lead -> the artist's most popular track that
                 has not been served and is not in the play history. Sets
                 title, spotify_track_uri, spotify_url.
  revival_desk   title already known (it came from the play history) -> URI
                 only. The title is never rewritten.
  front_to_back  album -> spotify_album_uri, so publish_playlist can pull
                 the tracklist and run the album front to back.

Never guesses. Every match is confirmed by normalized artist name (and, for
albums and revivals, by title) before it is written; anything unconfirmed
stays null, is reported, and the reader gets the artwork-unavailable tile
rather than a wrong record. Re-runnable: already-resolved items are skipped,
so a second run costs nothing.

Run:  PYTHONPATH=<root> python3 -m engine.deliver.resolve_tracks --n 3
      ... --dry-run     resolve and print, write nothing
"""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from engine.deliver.spotify_auth import api, get_access_token
from engine.lib import history
from engine.lib.config import load_config
from engine.lib.normalize import norm_artist, norm_title, strip_versions

MARKET = "US"
# This app's quota caps /search at 10 results per page (limit=11 is a 400)
# and blanks the `popularity` field, so depth comes from paging and the
# ranking is Spotify's own relevance order.
PAGE = 10
SEARCH_PAGES = 3


def _q(s):
    return urllib.parse.quote(s, safe="")


def _artist_matches(candidate_names, wanted):
    """True if any credited artist is the one we asked for."""
    w = norm_artist(wanted or "")
    return any(norm_artist(n or "") == w for n in candidate_names)


def _search(token, query, kind, pages=1):
    """Search results in Spotify's own relevance order, `pages` deep."""
    out = []
    for i in range(pages):
        path = (f"/search?q={_q(query)}&type={kind}&limit={PAGE}"
                f"&offset={i * PAGE}&market={MARKET}")
        try:
            d = api("GET", path, token)
        except SystemExit as e:        # api() raises SystemExit on HTTP error
            print(f"  search failed ({kind}): {e}", file=sys.stderr)
            break
        items = (d.get(f"{kind}s") or {}).get("items") or []
        out.extend(items)
        if len(items) < PAGE:
            break
    return out


def played_under_any_credit(track, played=None):
    """True when ANY artist credited on this Spotify track has that song in
    the play history.

    The lead artist is verified never-played, but a Singles Rack lead is
    artist-level: the song itself is chosen here, and a feature or a
    compilation credit routinely files that exact recording in the log under
    somebody else's name. "Rapp Snitch Knishes" is an MF DOOM record credited
    on Spotify to its guest, Mr. Fantastik; asking whether Mr. Fantastik has
    played it always answers no, because the 48 plays sit under MF DOOM.

    So the question has to be asked of every credited name, not just the one
    we searched for. Artist-level fame is deliberately NOT the test: Ragga
    Twins and Bassnectar are both in the log and both are credited on a
    Dirtyphonics track the reader has never heard, and that track is a
    perfectly good pick. Only a play of THIS song disqualifies it.
    """
    played = played or history.track_played
    name = track.get("name") or ""
    for a in track.get("artists") or []:
        if played(a.get("name") or "", name):
            return True
    return False


def pick_track_for_artist(token, artist, served_titles, search=None, played=None):
    """The artist's most popular track that is new to the reader.

    Spotify's /artists/{id}/top-tracks is 403 without extended quota, and
    restricted search results carry no popularity score, so the ranking is
    the order the search itself returns — which is relevance-weighted and in
    practice puts the artist's best-known song first. It picked "Beacon" for
    Matt Duncan, the same track issue 002 chose by hand.

    Skips anything already served and anything already in the play history —
    the artist is verified never-played, but a compilation credit or a
    feature can still put one of their tracks in the log, and the Singles
    Rack should not open with a song the reader already knows. That last
    check reads every credited artist on the track; see
    played_under_any_credit for why the lead artist alone cannot answer it.
    """
    search = search or _search
    items = search(token, f'artist:"{artist}"', "track", pages=SEARCH_PAGES)
    if not items:
        return None, "no Spotify tracks matched that artist"
    mine = [t for t in items
            if _artist_matches([a.get("name") for a in (t.get("artists") or [])],
                               artist)]
    if not mine:
        return None, "search returned nobody by that exact name"
    for t in mine:
        name = t.get("name") or ""
        if (norm_artist(artist), norm_title(name)) in served_titles:
            continue
        if played_under_any_credit(t, played):
            continue
        return {
            "title": name,
            "spotify_track_uri": t.get("uri"),
            "spotify_url": (t.get("external_urls") or {}).get("spotify"),
        }, None
    return None, "every track found was already served or already played"


def _base_title(title):
    """Title without the decorations the play log and the catalogue disagree
    about: ' - Jay Dee Remix', ' - 2019 remaster', 'feat. Guilty Simpson'.
    Cut by the same rule the matcher keys on, so the string sent to Spotify
    and the key it is compared under cannot disagree."""
    return strip_versions(title)


def find_track_uri(token, artist, title, search=None):
    """Exact lookup for a track whose title is already known.

    Two passes, each artist-confirmed, and neither guesses: the title as
    given, then the undecorated base title (the log carries Spotify's own
    suffixes on some rows and not others). Both require the normalized
    title to be EQUAL. There used to be a prefix pass between them, either
    way round, and it accepted "Love Story" for "Love" by the same artist:
    a prefix is search relevance, not identity, and a wrong track in the
    playlist is worse than a missing one.
    """
    search = search or _search
    want_t = norm_title(title)
    items = search(token, f'track:"{title}" artist:"{artist}"', "track", pages=2)

    def confirmed(pool):
        return [t for t in pool
                if _artist_matches([a.get("name") for a in (t.get("artists") or [])],
                                   artist)]

    for t in confirmed(items):
        if norm_title(t.get("name") or "") == want_t:
            return t.get("uri"), (t.get("external_urls") or {}).get("spotify")

    base = _base_title(title)
    if base and base != (title or "").strip():
        alt = search(token, f'track:"{base}" artist:"{artist}"', "track", pages=2)
        for t in confirmed(alt):
            if norm_title(t.get("name") or "") == want_t:
                return t.get("uri"), (t.get("external_urls") or {}).get("spotify")
    return None, None


def revival_uri_from_history(artist, title, played=None):
    """The Spotify id the play log already carries for a Second Chances pick.

    Revival picks are drawn out of the play history, and those rows carry the
    track_uri Spotify itself reported when the play was logged. Searching for
    them by name is how issue 004 lost two Tycho remixes: "Pink & Blue (feat.
    Saint Sinner) - RAC Mix" does not survive a title search, and it never
    needed one. The id was in the row the pick came from.

    Search stays as the fallback, for rows logged before URIs were captured.
    """
    played = played or history.track_played
    row = played(artist, title) or {}
    tid = (row.get("track_uri") or "").strip()
    if not tid:
        return None, None
    tid = tid.rsplit(":", 1)[-1]
    return f"spotify:track:{tid}", f"https://open.spotify.com/track/{tid}"


def find_album_uri(token, artist, title):
    """The album's URI, or (None, None) when Spotify does not carry it.

    A real album wins over a compilation or a single of the same name: the
    album of the week is played front to back, and a 2-track single named
    after its lead track is not that record.
    """
    items = _search(token, f'album:"{title}" artist:"{artist}"', "album", pages=2)
    want_t = norm_title(title)
    hits = []
    for a in items:
        names = [x.get("name") for x in (a.get("artists") or [])]
        got = norm_title(a.get("name") or "")
        if _artist_matches(names, artist) and (got == want_t
                                               or got.startswith(want_t)):
            hits.append(a)
    if not hits:
        return None, None
    hits.sort(key=lambda a: 0 if (a.get("album_type") or "") == "album" else 1)
    best = hits[0]
    return best.get("uri"), (best.get("external_urls") or {}).get("spotify")


def _served_titles(cfg):
    p = Path(cfg["SERVED_PATH"])
    if not p.exists():
        return set()
    items = json.loads(p.read_text()).get("items") or []
    return {(norm_artist(i.get("artist") or ""), norm_title(i.get("title") or ""))
            for i in items if i.get("title")}


def resolve_issue(doc, token, served_titles):
    """Fill URIs in place. Returns (resolved, skipped, unresolved[])."""
    resolved = skipped = 0
    unresolved = []

    for m in doc.get("modules") or []:
        t = m.get("type")

        if t == "singles_rack":
            for tr in m.get("tracks") or []:
                if tr.get("spotify_track_uri"):
                    skipped += 1
                    continue
                artist = tr.get("artist")
                if tr.get("title"):
                    uri, url = find_track_uri(token, artist, tr["title"])
                    if uri:
                        tr["spotify_track_uri"], tr["spotify_url"] = uri, url
                        resolved += 1
                        print(f"  singles   {artist} — {tr['title']}")
                    else:
                        unresolved.append(f"{artist} — {tr['title']} (no match)")
                    continue
                pick, why = pick_track_for_artist(token, artist, served_titles)
                if pick:
                    tr["title"] = pick["title"]
                    tr["spotify_track_uri"] = pick["spotify_track_uri"]
                    tr["spotify_url"] = pick["spotify_url"]
                    served_titles.add((norm_artist(artist),
                                       norm_title(pick["title"])))
                    resolved += 1
                    print(f"  singles   {artist} — {pick['title']}")
                else:
                    unresolved.append(f"{artist} (artist-level) — {why}")

        elif t == "revival_desk":
            for tr in m.get("tracks") or []:
                if tr.get("spotify_track_uri"):
                    skipped += 1
                    continue
                artist, title = tr.get("artist"), tr.get("title")
                if not title:
                    unresolved.append(f"{artist} — revival pick has no title")
                    continue
                uri, url = revival_uri_from_history(artist, title)
                how = "from the log"
                if not uri:
                    uri, url = find_track_uri(token, artist, title)
                    how = "by search"
                if uri:
                    tr["spotify_track_uri"] = uri
                    if url:
                        tr["spotify_url"] = url
                    resolved += 1
                    print(f"  revival   {artist} — {title} ({how})")
                else:
                    unresolved.append(f"{artist} — {title} (no match)")

        elif t == "front_to_back":
            album = m.get("album") or {}
            if album.get("spotify_album_uri"):
                skipped += 1
                continue
            artist, title = album.get("artist"), album.get("title")
            uri, url = find_album_uri(token, artist, title)
            if uri:
                album["spotify_album_uri"] = uri
                album["spotify_url"] = url
                resolved += 1
                print(f"  album     {artist} — {title}")
            else:
                unresolved.append(f"{artist} — {title} (album, no match)")

    return resolved, skipped, unresolved


def _singles_module(doc):
    for m in doc.get("modules") or []:
        if m.get("type") == "singles_rack":
            return m
    return None


def backfill_singles(doc, token, served_titles, proposal, model, issue_no,
                     search=None, played=None):
    """Fill Singles Rack slots whose lead produced no song, from the reserves.

    A lead is artist-level, so whether it can yield a song the reader has
    never heard is only discovered here, after the writer has already
    committed to a rack of ten. When one comes up empty the rack used to ship
    a card with no track behind it, which the validator allows (a null title
    is legal pre-curation) and the site renders as a door with nothing behind
    it. The reader is promised ten.

    The proposal already carries every ranked lead the writer did not use
    (28 leads for a rack of 10 in issue 004), so the replacement is chosen
    already and only has to be asked for. Promoted leads keep the writer's
    own ranking order and are built by the same rack_entry, so a replacement
    is indistinguishable from an original.

    Returns (filled, exhausted[]) — exhausted lists slots still empty because
    the reserves ran out, which is the one case a short rack is honest.
    """
    from engine.editorial.writer import rack_entry

    m = _singles_module(doc)
    if not m:
        return 0, []
    tracks = m.get("tracks") or []
    empty = [i for i, t in enumerate(tracks) if not t.get("spotify_track_uri")]
    if not empty:
        return 0, []

    used = {norm_artist(t.get("artist") or "") for t in tracks}
    reserves = [(cid, it) for cid, it in proposal
                if norm_artist(it.get("artist") or "") not in used]

    def next_reserve(lane):
        """The first reserve from the emptied slot's own lane, so the mix
        the rack was built with survives the replacement; the first
        reserve of any lane when that lane has none left."""
        for i, (cid, _) in enumerate(reserves):
            if cid == lane:
                return reserves.pop(i)
        return reserves.pop(0)

    filled, exhausted = 0, []
    for slot in empty:
        promoted = None
        lane = tracks[slot].get("cluster")
        while reserves:
            cid, it = next_reserve(lane)
            artist = it.get("artist")
            used.add(norm_artist(artist or ""))
            pick, why = pick_track_for_artist(token, artist, served_titles,
                                              search=search, played=played)
            if not pick:
                print(f"  backfill  skipped {artist} — {why}")
                continue
            entry = rack_entry(cid, it, model, issue_no)
            entry["title"] = pick["title"]
            entry["spotify_track_uri"] = pick["spotify_track_uri"]
            entry["spotify_url"] = pick["spotify_url"]
            served_titles.add((norm_artist(artist),
                               norm_title(pick["title"])))
            promoted = entry
            break
        if promoted is None:
            exhausted.append(tracks[slot].get("artist"))
            continue
        print(f"  backfill  {tracks[slot].get('artist')} -> "
              f"{promoted['artist']} — {promoted['title']}")
        tracks[slot] = promoted
        filled += 1
    return filled, exhausted


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True, help="issue number")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve and print, write nothing")
    args = ap.parse_args(argv)

    cfg = load_config()
    name = f"issue-{args.n:03d}.json"
    path = Path(cfg["ISSUES_DIR"]) / name
    if not path.exists():
        print(f"resolve_tracks: {path} not found", file=sys.stderr)
        return 2
    doc = json.loads(path.read_text())

    token = get_access_token()
    served = _served_titles(cfg)
    resolved, skipped, unresolved = resolve_issue(doc, token, served)

    out_dir = Path(cfg["OUT_DIR"])
    proposal_path = out_dir / "selection-proposal.json"
    if proposal_path.exists():
        from engine.editorial.writer import rack_ranked
        model_path = out_dir / "taste-model.json"
        model = (json.loads(model_path.read_text())
                 if model_path.exists() else {})
        filled, exhausted = backfill_singles(
            doc, token, served,
            rack_ranked(json.loads(proposal_path.read_text())),
            model, args.n)
        if filled:
            resolved += filled
            print(f"  backfill: {filled} rack slot(s) filled from the reserves")
        for a in exhausted:
            print(f"  backfill: no reserve left for {a} — rack is short")
    else:
        print(f"  backfill: {proposal_path} missing, rack left as built",
              file=sys.stderr)

    print(f"resolve_tracks: issue {args.n:03d} — {resolved} resolved, "
          f"{skipped} already had URIs, {len(unresolved)} unresolved")
    for u in unresolved:
        print(f"  unresolved: {u}")

    if args.dry_run:
        print("dry run — nothing written")
        return 0

    # The writer notes that rack titles are null pre-curation. True when it
    # ran, false once this stage has filled them, and it was still riding
    # along in the published issue 004.
    sm = _singles_module(doc)
    if sm and all(t.get("title") for t in sm.get("tracks") or []):
        gen = doc.get("generated") or {}
        notes = gen.get("notes")
        if isinstance(notes, list):
            gen["notes"] = [n for n in notes
                            if "titles are null pre-curation" not in str(n)]

    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    path.write_text(body)
    (Path(cfg["SITE_ISSUES_DIR"]) / name).write_text(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
