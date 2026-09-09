"""Fresh album leads from RSS: Pitchfork reviews (+BNM) and Bandcamp Daily.

Feeds (verified live 2026-07 — Pitchfork's old /rss/reviews/... URLs are 404;
the current ones are advertised on https://pitchfork.com/rss/):
  https://pitchfork.com/feed/reviews/best/albums/rss   (BNM)   -> pitchfork_rss
  https://pitchfork.com/feed/feed-album-reviews/rss    (all)   -> pitchfork_rss
  https://daily.bandcamp.com/feed                              -> bandcamp_daily

Format notes:
- Pitchfork item <title> is the ALBUM title only; the artist lives in the URL
  slug (/reviews/albums/<artist>-<album-slug>/). We slugify the album title,
  strip it from the end of the slug, and de-slugify the remainder into the
  artist name (lowercase, spaces — normalization downstream is case-blind).
  Items whose slug doesn't end with the title slug are skipped and counted,
  never guessed.
- The BNM feed is processed first; its items win the dedupe with bnm=true.
  The BNM feed's window (30 latest BNM) fully covers the all-feed's ~1-week
  window, so bnm=false on the remainder is sound.
- Bandcamp Daily only yields candidates from album-of-the-day items
  (link contains /album-of-the-day/, title 'Artist, "Album"'); the rest of
  that feed is lists/features with no single album, skipped and counted.
"""

import html
import re
import unicodedata
import xml.etree.ElementTree as ET

from engine.lib import http
from engine.lib.normalize import norm_artist, norm_title

P4K_BNM_FEED = "https://pitchfork.com/feed/reviews/best/albums/rss"
P4K_ALL_FEED = "https://pitchfork.com/feed/feed-album-reviews/rss"
BC_DAILY_FEED = "https://daily.bandcamp.com/feed"

_DC = "{http://purl.org/dc/elements/1.1/}"
_TAGS = re.compile(r"<[^>]+>")
_AOTD_TITLE = re.compile(r'^(.+?),\s*[“"](.+?)[”"]$')


def _text(item, tag):
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else None


def _clean(s, cap=400):
    if not s:
        return None
    s = html.unescape(_TAGS.sub(" ", s))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:cap] or None


def _slugify(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _artist_from_link(link, album_title):
    """Strip the slugified album title off the URL slug; remainder = artist."""
    if not link:
        return None
    seg = link.rstrip("/").rsplit("/", 1)[-1]
    variants = {_slugify(album_title),
                _slugify(album_title.replace("&", " and "))}
    for t in variants:
        if t and seg.endswith("-" + t):
            artist = seg[: -(len(t) + 1)].replace("-", " ").strip()
            if artist:
                return artist
    return None


def _fetch_items(url):
    body = http.get(url, rate_key="rss", min_interval=1.0, ttl_days=1)
    root = ET.fromstring(body)
    return root.findall(".//item")


def _pitchfork_candidates(items, bnm):
    out, skipped = [], 0
    for item in items:
        title = _text(item, "title")
        link = _text(item, "link")
        artist = _artist_from_link(link, title) if title else None
        if not artist:
            skipped += 1
            continue
        out.append({
            "artist": artist, "title": title, "year": None,
            "source": "pitchfork_rss", "cluster_hint": None,
            "p4k": {"score": None, "bnm": bnm, "url": link,
                    "author": _text(item, _DC + "creator"),
                    "dek": _clean(_text(item, "description"))},
            "release_date": None, "via": None,
        })
    return out, skipped


def _bandcamp_candidates(items):
    out, skipped = [], 0
    for item in items:
        link = _text(item, "link") or ""
        m = _AOTD_TITLE.match(_text(item, "title") or "")
        if "/album-of-the-day/" not in link or not m:
            skipped += 1  # lists/features — no single album to extract
            continue
        out.append({
            "artist": m.group(1).strip(), "title": m.group(2).strip(), "year": None,
            "source": "bandcamp_daily", "cluster_hint": None, "p4k": None,
            "release_date": None, "via": None,
        })
    return out, skipped


def harvest(limit=None):
    """Return ({"album_candidates": [...]}, status)."""
    candidates, seen = [], set()
    notes, errors = [], []

    feeds = [
        ("p4k_bnm", P4K_BNM_FEED, lambda it: _pitchfork_candidates(it, True)),
        ("p4k_all", P4K_ALL_FEED, lambda it: _pitchfork_candidates(it, False)),
        ("bc_daily", BC_DAILY_FEED, _bandcamp_candidates),
    ]
    for name, url, parse in feeds:  # BNM first so its bnm=true wins the dedupe
        try:
            got, skipped = parse(_fetch_items(url))
        except Exception as e:  # noqa: BLE001 — any one feed may fail
            errors.append("%s: %s" % (name, e))
            continue
        kept = 0
        for c in got:
            k = (c["source"], norm_artist(c["artist"]), norm_title(c["title"]))
            if k in seen:
                continue
            seen.add(k)
            candidates.append(c)
            kept += 1
        notes.append("%s %d kept/%d skipped-unparsed" % (name, kept, skipped))

    if limit:
        candidates = candidates[:limit]
    if not candidates and errors:
        return {"album_candidates": []}, "error: " + "; ".join(errors)
    status = "ok: %d candidates (%s)" % (len(candidates), "; ".join(notes))
    if errors:
        status += " [partial errors: %s]" % "; ".join(errors)
    return {"album_candidates": candidates}, status


if __name__ == "__main__":
    payload, status = harvest()
    print(status)
    for c in payload["album_candidates"][:14]:
        bnm = c["p4k"]["bnm"] if c["p4k"] else "-"
        print(" ", c["source"], "| bnm=%s |" % bnm, c["artist"], "—", c["title"])
