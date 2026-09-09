"""Issue validator — the numbers-must-be-receipts gate.

Enforces, per CONTRACTS.md ("issues/issue-NNN.json"):

1. Required fields at the top level and per module type.
2. Every number token (regex ``\\d+[.,]?\\d*``) appearing in prose fields —
   any ``why`` or ``intro`` inside a module, and the top-level ``dek`` —
   must string-match a receipt ``value`` in that same module (the dek is
   checked against the union of all modules' receipts). Comparison is by
   string after normalizing commas out of the token (``1,234`` → ``1234``)
   and stripping a trailing ``.``/``,`` the regex may capture at sentence
   end. Whitelisted tokens need no receipt: integer years 1950–2030,
   integers <= 12, and the issue number itself.
3. ``new_this_week`` notes must describe the release they sit on: a note
   that names another listed artist and not its own, or that describes the
   same artist's EP / album / single when that other release is listed, is
   a note-to-release pairing error (copy notes are merged onto releases by
   the writer — see ``writer.py`` "copy pairing").

Usable as a library (``validate_issue(doc) -> [error strings]``) or CLI:

    python3 -m engine.editorial.validate issues/issue-001.json

Exits 0 on a valid issue, 1 with one line per violation on an invalid one,
2 on usage/parse errors.
"""

import json
import re
import sys

from engine.lib.normalize import norm_artist

NUM_RE = re.compile(r"\d+[.,]?\d*")
_INT_RE = re.compile(r"\d+")

PROSE_KEYS = ("why", "intro", "verdict")

TOP_REQUIRED = [
    "issue", "date", "title", "dek", "masthead_note", "modules",
    "verification", "companion_playlist", "generated",
]

MODULE_REQUIRED = {
    "front_to_back": ["type", "cluster", "album", "why", "receipts"],
    "singles_rack": ["type", "intro", "tracks"],
    "revival_desk": ["type", "franchise", "intro", "tracks"],
    "new_this_week": ["type", "intro", "releases"],
    "the_mix": ["type", "intro", "mixes"],
    "critics_desk": ["type", "intro", "receipts", "albums"],
    "catalog_room": ["type", "artist", "why", "receipts", "unheard"],
    "ledger": ["type", "intro", "verdict", "receipts", "rows"],
}

LEDGER_ROW_REQUIRED = ["label", "module", "played", "plays"]

ALBUM_REQUIRED = ["artist", "title", "year"]

TRACK_REQUIRED = {
    "singles_rack": ["artist", "title", "cluster", "why", "receipts"],
    "revival_desk": ["artist", "title", "plays", "last_played", "why", "receipts"],
}

RELEASE_REQUIRED = ["artist", "title", "release_date", "release_type", "relationship"]

MIX_REQUIRED = ["show", "episode", "url", "tracks_total", "known_count",
                "new_count", "why", "receipts"]

CRITIC_ALBUM_REQUIRED = ["artist", "title", "score", "why", "receipts"]

UNHEARD_REQUIRED = ["title"]

RECEIPT_REQUIRED = ["stat_id", "claim", "value"]


# ---------------------------------------------------------------- helpers

def number_tokens(text):
    """All number tokens in a prose string, per the contract regex."""
    return NUM_RE.findall(text or "")


def _norm_token(tok):
    """Normalize a prose token for comparison: drop commas, trailing dot."""
    return tok.replace(",", "").rstrip(".")


def receipt_value_forms(receipts):
    """Set of acceptable string forms for the numeric values of receipts."""
    forms = set()
    for r in receipts or []:
        if not isinstance(r, dict):
            continue
        v = r.get("value")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        forms.add(str(v))
        if isinstance(v, float) and v.is_integer():
            forms.add(str(int(v)))
        if isinstance(v, int):
            forms.add(str(float(v)))
    return forms


def token_allowed(tok, value_forms, issue_no):
    """True if a prose number token is receipted or whitelisted."""
    t = _norm_token(tok)
    if not t:
        return True
    if t in value_forms:
        return True
    if _INT_RE.fullmatch(t):
        v = int(t)
        if v <= 12:
            return True
        if 1950 <= v <= 2030:
            return True
        if issue_no is not None and v == issue_no:
            return True
    return False


def collect_receipts(node):
    """Every receipt dict found in any 'receipts' list under node."""
    out = []
    if isinstance(node, dict):
        r = node.get("receipts")
        if isinstance(r, list):
            out.extend(x for x in r if isinstance(x, dict))
        for k, v in node.items():
            if k != "receipts":
                out.extend(collect_receipts(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(collect_receipts(v))
    return out


NAME_KEYS = ("artist", "title", "show", "episode", "album", "label",
             "genre", "name", "franchise")


def proper_names(node, out=None):
    """Every proper-name string under node: artist, title, show, episode and
    friends. These are data the writer did not author, so a digit inside one
    ("Air Max '97", "Blink-182", "1999") is a name, not a claim."""
    if out is None:
        out = []
    if isinstance(node, dict):
        r = node.get("receipts")
        if isinstance(r, list):
            # A claim reads "<name>: 1,252 plays", and prose quotes the name
            # half. The numbers live after the colon and stay checkable.
            for x in r:
                claim = isinstance(x, dict) and x.get("claim")
                if isinstance(claim, str) and ": " in claim:
                    out.append(claim.split(": ", 1)[0].strip())
        for k, v in node.items():
            if k in NAME_KEYS and isinstance(v, str) and v.strip():
                out.append(v.strip())
            else:
                proper_names(v, out)
    elif isinstance(node, list):
        for v in node:
            proper_names(v, out)
    return out


def strip_names(text, names):
    """Remove proper names from prose before looking for numbers, longest
    first so 'Super Discount 4' is masked before 'Super Discount'."""
    for n in sorted(names, key=len, reverse=True):
        if any(ch.isdigit() for ch in n):
            text = text.replace(n, " ")
    return text


def _prose_fields(node, path):
    """Yield (path, text) for every why/intro string under node."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k in PROSE_KEYS and isinstance(v, str):
                yield p, v
            else:
                yield from _prose_fields(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _prose_fields(v, f"{path}[{i}]")


# ------------------------------------------------- artist mentions in prose

_RELEASE_TYPE_WORDS = (
    ("ep", ("ep",)),
    ("album", ("album", "lp", "full length")),
    ("single", ("single",)),
)


def artist_pattern(name):
    """Compiled pattern locating a normalized artist name inside normalized
    prose (word-bounded). A leading "the" is optional, so "Alchemist" finds
    The Alchemist. Single-word names of three letters or fewer (Low, Air,
    Can) are ordinary words too often to count: returns None for those."""
    n = norm_artist(name or "")
    if n.startswith("the "):
        n = n[4:]
    if not n or (" " not in n and len(n) <= 3):
        return None
    return re.compile(r"(?<![a-z0-9])(?:the )?" + re.escape(n) + r"(?![a-z0-9])")


def mentions_artist(text, name):
    """True if the prose names the artist (after the same normalization the
    history matcher uses: case, accents, punctuation)."""
    pat = artist_pattern(name)
    return bool(pat and pat.search(norm_artist(text or "")))


def release_type_mentions(text):
    """Set of release types ("ep", "album", "single") the prose names as
    words. "Record" is deliberately not an album word: in this voice "the
    record" is the play log."""
    t = norm_artist(text or "")
    found = set()
    for rtype, words in _RELEASE_TYPE_WORDS:
        for w in words:
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t):
                found.add(rtype)
                break
    return found


# ---------------------------------------------------------------- checks

def _check_receipts_shape(module, label, errors):
    for r in collect_receipts(module):
        for k in RECEIPT_REQUIRED:
            if k not in r:
                errors.append(f"{label}: receipt missing '{k}': {r!r}")
        v = r.get("value")
        if "value" in r and (isinstance(v, bool) or not isinstance(v, (int, float))):
            errors.append(f"{label}: receipt value must be a number, got {v!r}")


def _check_items(items, required, label, errors, nullable=()):
    if not isinstance(items, list) or not items:
        errors.append(f"{label}: must be a non-empty list")
        return
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errors.append(f"{label}[{i}]: must be an object")
            continue
        for k in required:
            if k not in it:
                errors.append(f"{label}[{i}]: missing required field '{k}'")
            elif it[k] is None and k not in nullable:
                errors.append(f"{label}[{i}]: field '{k}' must not be null")


def _check_release_notes(releases, label, errors):
    """new_this_week: each note must describe the release it is attached to.
    Copy notes reach releases through the writer's pairing; a note that names
    a different listed artist (and not its own) — or the same artist's other
    listed release type — is a pairing error, and is reported as one."""
    if not isinstance(releases, list):
        return
    rows = [r for r in releases if isinstance(r, dict)]
    for i, r in enumerate(releases):
        if not isinstance(r, dict):
            continue
        note = r.get("note")
        if not isinstance(note, str) or not note.strip():
            continue
        artist = r.get("artist") or ""
        own_key = norm_artist(artist)
        own = mentions_artist(note, artist)
        others = []
        for o in rows:
            name = o.get("artist") or ""
            if (name and norm_artist(name) != own_key and name not in others
                    and mentions_artist(note, name)):
                others.append(name)
        if others and not own:
            errors.append(
                f"{label}[{i}]: note names {others[0]!r} but is attached to "
                f"{artist!r} (note-to-release pairing error)")
            continue
        types = release_type_mentions(note)
        if len(types) == 1:
            want = next(iter(types))
            have = (r.get("release_type") or "").lower()
            sibling = any(
                o is not r and norm_artist(o.get("artist") or "") == own_key
                and (o.get("release_type") or "").lower() == want
                for o in rows)
            if have and have != want and sibling:
                errors.append(
                    f"{label}[{i}]: note describes {artist!r}'s {want} but is "
                    f"attached to the {have} {r.get('title')!r} "
                    f"(note-to-release pairing error)")


def _check_module(m, i, issue_no, errors):
    label = f"modules[{i}]"
    t = m.get("type")
    if t not in MODULE_REQUIRED:
        errors.append(f"{label}: unknown or missing module type {t!r}")
        return
    label = f"{label} ({t})"
    for k in MODULE_REQUIRED[t]:
        if k not in m:
            errors.append(f"{label}: missing required field '{k}'")

    if t == "front_to_back":
        album = m.get("album")
        if not isinstance(album, dict):
            errors.append(f"{label}: 'album' must be an object")
        else:
            for k in ALBUM_REQUIRED:
                if k not in album or album[k] is None:
                    errors.append(f"{label}: album.{k} is required and non-null")
    elif t in ("singles_rack", "revival_desk"):
        # singles_rack titles may be null: harvest leads are artist-level
        # (CONTRACTS.md track_candidates) — the track gets picked at curation.
        nullable = ("title",) if t == "singles_rack" else ()
        _check_items(m.get("tracks"), TRACK_REQUIRED[t], f"{label}.tracks",
                     errors, nullable=nullable)
    elif t == "new_this_week":
        _check_items(m.get("releases"), RELEASE_REQUIRED, f"{label}.releases",
                     errors, nullable=("release_date", "via", "note"))
        _check_release_notes(m.get("releases"), f"{label}.releases", errors)
    elif t == "the_mix":
        _check_items(m.get("mixes"), MIX_REQUIRED, f"{label}.mixes",
                     errors, nullable=("date", "cluster", "listen_urls"))
    elif t == "critics_desk":
        _check_items(m.get("albums"), CRITIC_ALBUM_REQUIRED,
                     f"{label}.albums", errors,
                     nullable=("year", "genre", "url", "cluster"))
    elif t == "catalog_room":
        _check_items(m.get("unheard"), UNHEARD_REQUIRED, f"{label}.unheard",
                     errors, nullable=("year",))
    elif t == "ledger":
        _check_items(m.get("rows"), LEDGER_ROW_REQUIRED, f"{label}.rows",
                     errors, nullable=("first_play",))

    _check_receipts_shape(m, label, errors)

    # the numbers rule: every number token in this module's prose must be
    # a receipt value from this module (or whitelisted)
    forms = receipt_value_forms(collect_receipts(m))
    names = proper_names(m)
    for path, text in _prose_fields(m, label):
        for tok in number_tokens(strip_names(text, names)):
            if not token_allowed(tok, forms, issue_no):
                errors.append(
                    f"{path}: number {tok!r} has no matching receipt value in "
                    f"this module (whitelist: years 1950-2030, integers <= 12, "
                    f"the issue number)")


def validate_issue(doc):
    """Validate an issue document. Returns a list of error strings."""
    errors = []
    if not isinstance(doc, dict):
        return ["issue document must be a JSON object"]
    for k in TOP_REQUIRED:
        if k not in doc:
            errors.append(f"top level: missing required field '{k}'")
    issue_no = doc.get("issue") if isinstance(doc.get("issue"), int) else None
    if issue_no is None:
        errors.append("top level: 'issue' must be an integer")

    modules = doc.get("modules")
    if not isinstance(modules, list) or not modules:
        errors.append("top level: 'modules' must be a non-empty list")
        modules = []
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            errors.append(f"modules[{i}]: must be an object")
            continue
        _check_module(m, i, issue_no, errors)

    # dek is top-level prose: check against the union of all module receipts
    all_forms = receipt_value_forms(collect_receipts(modules))
    for tok in number_tokens(strip_names(doc.get("dek") or "", proper_names(doc))):
        if not token_allowed(tok, all_forms, issue_no):
            errors.append(
                f"dek: number {tok!r} has no matching receipt value in any "
                f"module (whitelist: years 1950-2030, integers <= 12, the "
                f"issue number)")
    return errors


# ---------------------------------------------------------------- CLI

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python3 -m engine.editorial.validate <issue.json>",
              file=sys.stderr)
        return 2
    try:
        with open(argv[0]) as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        print(f"VALIDATION: cannot read {argv[0]}: {e}", file=sys.stderr)
        return 2
    errors = validate_issue(doc)
    if errors:
        for e in errors:
            print(f"VALIDATION: {e}", file=sys.stderr)
        print(f"VALIDATION FAILED: {len(errors)} violation(s) in {argv[0]}",
              file=sys.stderr)
        return 1
    print(f"OK: {argv[0]} — issue {doc.get('issue')} passes "
          f"({len(doc.get('modules', []))} modules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
