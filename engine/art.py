"""Resolve cover art for an issue's items, at publish time.

The issue JSON carries Spotify URIs but no images, and the site no longer
embeds Spotify players — it shows the real square cover as the link. This
step fills `cover_url` on every item that can carry one, using keyless
sources, and writes the issue back to issues/ and site/public/issues/.

  front_to_back.album, singles_rack.tracks, revival_desk.tracks,
  companion_playlist        -> Spotify oEmbed thumbnail (640px)
  critics_desk.albums,
  catalog_room.unheard      -> MusicBrainz release-group (year-aware) ->
                               Cover Art Archive front; else iTunes Search
  the_mix.mixes             -> by source (engine.lib.media): NTS episode
                               media picture; KEXP programme artwork from
                               the shows API; MixesDB pages' YouTube still
                               (else SoundCloud/Mixcloud artwork); and the
                               same thumbnail rule over any listen link.
                               A MixesDB page's player mirrors are also
                               written to listen_urls when the item has
                               none, so the reader can open the broadcast.

Lookups go through engine.lib.http (disk-cached, rate-limited), so re-runs
cost nothing. Anything unresolved stays null and the site renders its
artwork-unavailable tile — never a wrong cover.

Run:  PYTHONPATH=<root> python3 -m engine.art --n 2
"""

import argparse
import json
import re
import urllib.parse
from pathlib import Path

from .lib.config import load_config
from .lib import media
from .lib.http import get_json

UA = {"User-Agent": "clanker-cd/0.1 (music-discovery issue builder)"}


def _open_url(uri_or_url):
    s = (uri_or_url or "").strip()
    if not s:
        return None
    if s.startswith("http"):
        return s.split("?")[0]
    parts = s.split(":")  # spotify:track:ID
    if len(parts) == 3 and parts[0] == "spotify":
        return f"https://open.spotify.com/{parts[1]}/{parts[2]}"
    return None


def spotify_cover(uri_or_url):
    url = _open_url(uri_or_url)
    if not url:
        return None
    try:
        d = get_json("https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe=""),
                     rate_key="spotify-oembed", min_interval=0.4, ttl_days=90, headers=UA)
        return d.get("thumbnail_url") or None
    except Exception:
        return None


def mb_cover(artist, title, year=None):
    """Year-aware MusicBrainz release-group search -> Cover Art Archive front.
    Year matters: iTunes and MB both carry several self-titled Caetano Veloso
    records; the 1968 debut is not the 1986 one."""
    q = f'releasegroup:"{title}" AND artist:"{artist}"'
    try:
        d = get_json("https://musicbrainz.org/ws/2/release-group/?query="
                     + urllib.parse.quote(q) + "&fmt=json&limit=10",
                     rate_key="musicbrainz", min_interval=1.1, ttl_days=90, headers=UA)
    except Exception:
        return None
    groups = d.get("release-groups") or []
    pick = None
    if year:
        for g in groups:
            if str(g.get("first-release-date", "")).startswith(str(year)):
                pick = g
                break
    if not pick and groups:
        pick = groups[0]
    if not pick:
        return None
    try:
        caa = get_json(f"https://coverartarchive.org/release-group/{pick['id']}",
                       rate_key="caa", min_interval=1.0, ttl_days=90, headers=UA)
    except Exception:
        return None
    for img in caa.get("images") or []:
        if img.get("front"):
            th = img.get("thumbnails") or {}
            url = th.get("500") or th.get("large") or img.get("image")
            return url.replace("http://", "https://", 1) if url else None
    return None


def artist_matches(artist, name):
    """Whole-word match of the artist inside a credited name, so "Gas" does
    not match "Julieta Venegas" but still matches "Gas & Wolfgang Voigt"."""
    a = (artist or "").strip().lower()
    n = (name or "").lower()
    if not a or not n:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", n) is not None


def itunes_cover(artist, title, year=None):
    term = f"{artist} {title}"
    try:
        d = get_json("https://itunes.apple.com/search?term=" + urllib.parse.quote(term)
                     + "&entity=album&limit=10", rate_key="itunes", min_interval=0.6,
                     ttl_days=90, headers=UA)
    except Exception:
        return None
    cands = [r for r in d.get("results") or []
             if artist_matches(artist, r.get("artistName"))]
    if year:
        yr = [r for r in cands if str(r.get("releaseDate", "")).startswith(str(year))]
        if yr:
            cands = yr
    if not cands:
        return None
    url = cands[0].get("artworkUrl100") or ""
    return url.replace("100x100bb", "600x600bb") or None


_EDITION = re.compile(
    r"\s*[\[\(][^\]\)]*\b(anniversary|deluxe|expanded|remaster(ed)?|reissue|"
    r"edition|version|bonus|special)\b[^\]\)]*[\]\)]\s*$", re.I)


def strip_edition(title):
    """Drop a trailing edition tag: '[15th Anniversary Edition]', '(Deluxe)'.

    The catalogues file the record under its plain name. Pitchfork reviews
    the reissue, so the corpus carries "exile in guyville [15th anniversary
    edition]", which matches nothing in MusicBrainz or iTunes and left the
    Critics Desk showing a blank tile in issue 004.
    """
    return _EDITION.sub("", title or "").strip()


def album_cover(artist, title, year=None):
    hit = mb_cover(artist, title, year) or itunes_cover(artist, title, year)
    if hit:
        return hit
    base = strip_edition(title)
    if base and base != (title or "").strip():
        return mb_cover(artist, base, year) or itunes_cover(artist, base, year)
    return None


def nts_cover(url):
    parts = (url or "").rstrip("/").split("/")
    if "shows" not in parts or "episodes" not in parts:
        return None
    try:
        alias = parts[parts.index("shows") + 1]
        ep = parts[parts.index("episodes") + 1]
        d = get_json(f"https://www.nts.live/api/v2/shows/{alias}/episodes/{ep}",
                     rate_key="nts", min_interval=0.7, ttl_days=90, headers=UA)
    except Exception:
        return None
    media = d.get("media") or {}
    return (media.get("picture_medium_large") or media.get("picture_large")
            or media.get("picture_medium") or None)


def mix_cover(x, nts=None, kexp=None, players=None, thumb=None):
    """Artwork for one Mixes item, by source. Fills x["listen_urls"] from a
    MixesDB page's mirrors when the item carries none (the harvest now
    records them; issues pressed before it did not)."""
    nts = nts or nts_cover
    kexp = kexp or media.kexp_cover
    players = players or media.mixesdb_players
    thumb = thumb or media.first_thumbnail
    url = x.get("url") or ""
    host = urllib.parse.urlsplit(url).netloc.lower()
    if "nts.live" in host:
        pic = nts(url)
        if pic:
            return pic
    if "kexp.org" in host:
        pic = kexp(url)
        if pic:
            return pic
    if "mixesdb.com" in host and not x.get("listen_urls"):
        mirrors = players(url)
        if mirrors:
            x["listen_urls"] = mirrors
    return thumb(x.get("listen_urls") or [])


def resolve(issue):
    """Fill cover_url in place; returns (filled, total) counts."""
    filled = total = 0

    def put(obj, url, key=None):
        """Attach art, refreshing it when the item it belongs to has changed.

        Art used to be written once and never revisited (`not
        obj.get("cover_url")`). That is right while an item is immutable and
        wrong the moment a later stage swaps what the item IS: resolve_tracks
        can replace a Singles Rack pick after art has already been resolved
        for the track it replaced. Issue 004 published two cards carrying the
        sleeve of a song that was no longer on them, because the correct URL
        was fetched on every run and then refused by this guard.

        So the cache is keyed on the item's identity rather than on whether a
        URL happens to be sitting there. A lookup that fails (url is None)
        still leaves existing art alone, which is what the guard was really
        protecting.
        """
        nonlocal filled, total
        total += 1
        if url and (not obj.get("cover_url") or obj.get("cover_key") != key):
            obj["cover_url"] = url
            obj["cover_key"] = key
        if obj.get("cover_url"):
            filled += 1

    for m in issue.get("modules") or []:
        t = m.get("type")
        if t == "front_to_back" and isinstance(m.get("album"), dict):
            a = m["album"]
            akey = a.get("spotify_album_uri") or a.get("spotify_url")
            put(a, spotify_cover(a.get("spotify_url") or a.get("spotify_album_uri")), akey)
        elif t in ("singles_rack", "revival_desk"):
            for x in m.get("tracks") or []:
                xkey = x.get("spotify_track_uri") or x.get("spotify_url")
                put(x, spotify_cover(x.get("spotify_url")
                                     or x.get("spotify_track_uri")), xkey)
        elif t == "critics_desk":
            for a in m.get("albums") or []:
                put(a, album_cover(a.get("artist", ""), a.get("title", ""),
                                   a.get("year")),
                    f'{a.get("artist", "")}|{a.get("title", "")}|{a.get("year")}')
        elif t == "catalog_room":
            for u in m.get("unheard") or []:
                put(u, album_cover(m.get("artist", ""), u.get("title", ""),
                                   u.get("year")),
                    f'{m.get("artist", "")}|{u.get("title", "")}|{u.get("year")}')
        elif t == "the_mix":
            for x in m.get("mixes") or []:
                put(x, mix_cover(x), x.get("url"))
    cp = issue.get("companion_playlist")
    if isinstance(cp, dict) and (cp.get("spotify_url") or cp.get("uri")):
        put(cp, spotify_cover(cp.get("spotify_url") or cp.get("uri")),
            cp.get("uri") or cp.get("spotify_url"))
    return filled, total


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True, help="issue number")
    args = ap.parse_args(argv)
    cfg = load_config()
    name = f"issue-{args.n:03d}.json"
    src = Path(cfg["ISSUES_DIR"]) / name
    if not src.exists():
        raise SystemExit(f"{src} not found")
    issue = json.loads(src.read_text())
    filled, total = resolve(issue)
    text = json.dumps(issue, indent=1, ensure_ascii=False)
    src.write_text(text)
    site = Path(cfg["SITE_ISSUES_DIR"]) / name
    site.write_text(text)
    print(f"cover art: {filled}/{total} resolved -> {src.name} (+ site copy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
