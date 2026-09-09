"""Name/title normalization for matching against the listening history.

The zero-play guarantee lives or dies on this module. Titles collide across
different songs ("Lotus", "Careless", "Down in the Basement" are all real
collisions from Vol. 1), so normalization is used for candidate *matching*,
and near-miss review (round two) surfaces anything ambiguous for judgment.

Two rules the September 2026 audit forced into the open:

1. A key is never empty for a non-empty name. The old filter kept only
   ASCII letters and digits, so 宇多田ヒカル, 周杰倫, 아이유 and Молчат Дома
   all became "" and were filed as one artist. Letters in any script are
   letters. Latin diacritics still fold (Björk and Bjork are one key)
   because NFKD strips combining marks before the filter runs; scripts
   with no such decomposition pass through whole. A name made only of
   punctuation ("!!!") keeps its punctuation rather than vanishing.

2. Version decorations are stripped by CONTENT, not by position. The old
   tail regex only fired when a version word came right after the dash,
   so "Song - Remix" collapsed to "song" while "Song - Jay Dee Remix" did
   not, and identity depended on how a label wrote the credit. A dash or
   parenthesised tail is a version tail if it contains a version word
   anywhere; "Song - Part 2" is a different song and is left alone. This
   is song-level identity on purpose: for a never-played claim, counting
   every version as heard is the safe direction.
"""

import re
import unicodedata

_FEAT = re.compile(r"[\(\[]\s*(feat|ft|featuring|with)\.?\s+[^)\]]*[\)\]]", re.I)
_FEAT_TAIL = re.compile(r"\s+(feat|ft|featuring)\.?\s+.*$", re.I)

_VERSION_WORDS = (
    r"remaster(ed)?|deluxe|live|mono|stereo|radio edit|single version|"
    r"bonus track|extended|original mix|anniversary|expanded|edition|"
    r"reissue|edit|remix|mix|version|demo|instrumental|acoustic|dub|"
    r"rework|re-?edit|vip|bootleg|alternate|alt\.? take|take \d+|sped up|"
    r"slowed|session"
)
# " - <tail>" where the tail mentions a version word anywhere in it.
_VERSION_TAIL = re.compile(
    r"\s+-\s+(?=[^-]*\b(?:" + _VERSION_WORDS + r")\b)[^-]*$", re.I)
# A final "(…)" or "[…]" group mentioning a version word anywhere in it.
_VERSION_PAREN = re.compile(
    r"\s*[\(\[][^)\]]*\b(?:" + _VERSION_WORDS + r")\b[^)\]]*[\)\]]\s*$", re.I)
_SPACES = re.compile(r"\s+")


def _fold(s):
    """Strip combining marks so Latin diacritics fold to their base letter,
    then recompose so scripts that decompose (Hangul) return to their
    canonical form and compare stably."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s)


def _base(s):
    raw = (s or "").strip()
    if not raw:
        return ""
    t = _fold(raw.casefold()).replace("&", " and ")
    t = "".join(c if (c.isalnum() or c == " ") else " " for c in t)
    t = _SPACES.sub(" ", t).strip()
    if t:
        return t
    # Nothing alphanumeric survived ("!!!", "†††"): keep the punctuation as
    # the identity rather than collapsing every such name into one.
    return _SPACES.sub(" ", raw.casefold())


def strip_versions(title):
    """The title without its feature credit or version decoration, case and
    punctuation intact. Shared with the resolver so the string it sends to
    Spotify and the key it compares are cut by the same rule."""
    s = title or ""
    s = _FEAT.sub(" ", s)
    s = _FEAT_TAIL.sub(" ", s)
    prev = None
    while prev != s:                      # "(Live) [Remaster]": peel both
        prev = s
        s = _VERSION_PAREN.sub(" ", s)
        s = _VERSION_TAIL.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def norm_artist(s):
    return _base(s)


def norm_title(s):
    return _base(strip_versions(s))


def track_key(artist, title):
    return (norm_artist(artist), norm_title(title))
