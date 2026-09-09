"""Artwork for radio shows and mixes, per source.

A mix is not a record: there is no sleeve to look up. Each source keeps its
own picture somewhere, and this module knows where:

  NTS         the episode's media picture (engine.art.nts_cover)
  KEXP        the programme's own artwork from the shows API
              (`program_image_uri`), else the host's photo
  MixesDB     the page's {{Player}} mirrors: a YouTube video's thumbnail,
              else the SoundCloud or Mixcloud upload's artwork via oEmbed
  any listen  the same thumbnail rule applied to a mix's listen links, so
              a source with no picture of its own still gets one when it
              mirrors to YouTube, SoundCloud or Mixcloud

Every lookup is keyless and goes through engine.lib.http (disk-cached), so
re-runs cost nothing. Nothing here invents an image: a mix with no picture
anywhere stays null and the site renders its artwork-unavailable tile.
"""

import re
import urllib.parse
import urllib.request

from . import http

UA = {"User-Agent": "clanker-cd/0.1 (music-discovery issue builder)"}

_YT = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^\s&#]*&)?v=|embed/|shorts/|live/)"
    r"|youtu\.be/)([A-Za-z0-9_-]{11})")
_PLAYER_HOSTS = ("youtube.com", "youtu.be", "soundcloud.com", "mixcloud.com",
                 "hearthis.at")
_URL = re.compile(r"https?://[^\s|<>\"'\]\}]+")


def youtube_id(url):
    m = _YT.search(url or "")
    return m.group(1) if m else None


def player_urls(text):
    """Player/mirror URLs in a MixesDB wikitext or an HTML page, in page
    order, de-duplicated. Only the hosts a thumbnail can come from."""
    out = []
    for u in _URL.findall(text or ""):
        u = u.rstrip(".,;)")
        host = urllib.parse.urlsplit(u).netloc.lower()
        if not any(host == h or host.endswith("." + h) for h in _PLAYER_HOSTS):
            continue
        if "soundcloud.com/player" in u or "/oembed" in u:
            continue  # the embed frame, not the upload
        if u not in out:
            out.append(u)
    return out


def _head_ok(url, timeout=10):
    req = urllib.request.Request(url, method="HEAD", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def youtube_thumbnail(url, head=_head_ok):
    """The video's largest thumbnail; every video has hqdefault, only some
    have maxresdefault, so that one is checked first."""
    vid = youtube_id(url)
    if not vid:
        return None
    best = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
    return best if head(best) else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def _oembed(endpoint, url, rate_key):
    q = urllib.parse.urlencode({"format": "json", "url": url})
    try:
        return http.get_json(f"{endpoint}?{q}", rate_key=rate_key,
                             min_interval=0.5, ttl_days=30, headers=UA)
    except Exception:
        return {}


def soundcloud_artwork(url):
    d = _oembed("https://soundcloud.com/oembed", url, "soundcloud")
    return d.get("thumbnail_url") or None


def mixcloud_artwork(url):
    d = _oembed("https://www.mixcloud.com/oembed/", url, "mixcloud")
    return d.get("image") or None


def thumbnail(url, head=_head_ok):
    """Artwork for one listen link, by host. None when the host has none."""
    host = urllib.parse.urlsplit(url or "").netloc.lower()
    if "youtu" in host:
        return youtube_thumbnail(url, head=head)
    if host.endswith("soundcloud.com"):
        return soundcloud_artwork(url)
    if host.endswith("mixcloud.com"):
        return mixcloud_artwork(url)
    return None


def first_thumbnail(urls, head=_head_ok):
    """The first listen link that yields artwork, YouTube first: a video
    still is what the reader sees when they open the broadcast."""
    urls = list(urls or [])
    ordered = [u for u in urls if youtube_id(u)] + [u for u in urls if not youtube_id(u)]
    for u in ordered:
        t = thumbnail(u, head=head)
        if t:
            return t
    return None


# ------------------------------------------------------------------- KEXP

def kexp_show_id(url):
    m = re.search(r"#show-(\d+)", url or "")
    return m.group(1) if m else None


def kexp_cover(url, fetch=None):
    """The programme's artwork for a KEXP playlist URL; the host's photo
    when the programme has none."""
    sid = kexp_show_id(url)
    if not sid:
        return None
    try:
        d = (fetch or (lambda u: http.get_json(u, rate_key="kexp", min_interval=0.5,
                                               ttl_days=90, headers=UA)))(
            f"https://api.kexp.org/v2/shows/{sid}/")
    except Exception:
        return None
    return d.get("program_image_uri") or d.get("image_uri") or None


# ---------------------------------------------------------------- MixesDB

def mixesdb_title(url):
    """'https://www.mixesdb.com/w/2026-05-07_-_Boombass_%28Cassius%29...'
    -> the wiki page title."""
    path = urllib.parse.urlsplit(url or "").path
    if not path.startswith("/w/"):
        return None
    return urllib.parse.unquote(path[3:]).replace("_", " ") or None


def mixesdb_players(url, wikitext=None):
    """Player mirrors listed on a MixesDB page."""
    title = mixesdb_title(url)
    if not title:
        return []
    if wikitext is None:
        from ..harvest.mixesdb import _wikitext
        try:
            wikitext = _wikitext(title)
        except Exception:
            return []
    return player_urls(wikitext)
