"""Artist names across scripts.

MusicBrainz's canonical name for an artist can be in the artist's own
script (宇山寛人) while every record, and the reader's history, credits the
Latin form (Uyama Hiroto). A candidate under the canonical name then passes
the never-played check by spelling alone: the reader has 3 records by Uyama
Hiroto and was offered 宇山寛人 as a stranger.

Two helpers, both cheap (one cached MusicBrainz artist lookup per
non-Latin name, 30 days):

  latin_name(mbid, name)   the name to display and search with: the
                           primary English alias, else any English alias,
                           else any Latin alias, else the name itself.
  aliases(mbid, name)      every name the artist is known by, so the
                           verifier can ask the history about all of them.
"""

import unicodedata

from . import http

MB_ROOT = "https://musicbrainz.org/ws/2"
MB_RATE = {"rate_key": "musicbrainz", "min_interval": 1.1}


def is_latin(name):
    """True when every letter in the name is Latin (digits/punctuation ignored)."""
    for ch in name or "":
        if ch.isalpha():
            try:
                if not unicodedata.name(ch).startswith("LATIN"):
                    return False
            except ValueError:
                return False
    return True


def _artist(mbid):
    return http.get_json(f"{MB_ROOT}/artist/{mbid}?inc=aliases&fmt=json",
                         ttl_days=30, **MB_RATE)


def pick_latin(doc, name):
    """Choose the Latin display name from an artist doc with aliases."""
    als = [a for a in (doc.get("aliases") or []) if a.get("name")]
    en = [a for a in als if (a.get("locale") or "").startswith("en") and is_latin(a["name"])]
    primary = [a for a in en if a.get("primary")]
    for pool in (primary, en, [a for a in als if is_latin(a["name"])]):
        if pool:
            return pool[0]["name"]
    return name


def latin_name(mbid, name, fetch=None):
    if is_latin(name) or not mbid:
        return name
    try:
        doc = (fetch or _artist)(mbid)
    except Exception:
        return name
    return pick_latin(doc, name)


def aliases(mbid, name, fetch=None):
    """[name, canonical, aliases...] with no duplicates; [name] when the
    name is Latin and needs no lookup."""
    if is_latin(name) or not mbid:
        return [name]
    try:
        doc = (fetch or _artist)(mbid)
    except Exception:
        return [name]
    out = [name]
    for n in [doc.get("name")] + [a.get("name") for a in doc.get("aliases") or []]:
        if n and n not in out:
            out.append(n)
    return out
