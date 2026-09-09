"""Mark which album-of-the-week candidates Spotify actually carries.

The album of the week is the one pick the reader is asked to sit through
front to back, and the companion playlist is built around it. Ranking it on
taste alone can hand back a record Spotify does not have — My Bloody
Valentine's "isn't anything" outranked everything for issue 003, and Spotify
carries "m b v" and a couple of singles and nothing else. The issue was
valid, the prose was fine, and the playlist had no album in it.

Availability has to be decided BEFORE the writer commits, because the
module's receipts and prose are built around whichever record it picks;
swapping the album afterwards would leave the copy describing a different
one. So this runs between `select` and `issue`, walks the ranked
front_to_back shortlist in order, and annotates each candidate:

    "available": true|false        checked against Spotify
    "spotify_album_uri": "..."     carried through to the issue
    "spotify_url": "..."

It stops at the first available candidate, so the ones below it stay
unchecked (`available` absent) — the writer never reaches them anyway, and
the calls are not worth making.

Degrades rather than dies: with no Spotify auth, or on any API failure, the
proposal is left exactly as it was and the writer keeps its old behaviour of
taking the top-ranked candidate.

Run:  PYTHONPATH=<root> python3 -m engine.deliver.availability
      ... --dry-run    check and print, write nothing
"""

import argparse
import json
import sys
from pathlib import Path

from engine.deliver.resolve_tracks import find_album_uri
from engine.deliver.spotify_auth import get_access_token
from engine.lib.config import load_config

# How far down the shortlist to look before giving up. The list is ranked by
# taste; something 10 deep is a weak album of the week even if it streams.
MAX_CHECKS = 6


def annotate(proposal, token, max_checks=MAX_CHECKS, resolver=None):
    """Annotate front_to_back in place. Returns (chosen, checked, notes).

    `resolver` is injectable so tests need neither a token nor a network.
    """
    resolve = resolver or find_album_uri
    items = proposal.get("front_to_back") or []
    notes = []
    checked = 0
    for it in items[:max_checks]:
        artist, title = it.get("artist"), it.get("title")
        if not artist or not title:
            continue
        uri, url = resolve(token, artist, title)
        checked += 1
        it["available"] = bool(uri)
        if uri:
            it["spotify_album_uri"] = uri
            it["spotify_url"] = url
            return it, checked, notes
        notes.append(f"not on Spotify: {artist} — {title}")
    if items:
        notes.append(
            f"no album of the week resolved in the top {checked} candidates; "
            "the writer will fall back to the highest-ranked pick and the "
            "playlist will have no album in it")
    return None, checked, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="check and print, write nothing")
    ap.add_argument("--max-checks", type=int, default=MAX_CHECKS)
    args = ap.parse_args(argv)

    cfg = load_config()
    path = Path(cfg["OUT_DIR"]) / "selection-proposal.json"
    if not path.exists():
        print(f"availability: {path} not found — run select first", file=sys.stderr)
        return 2
    proposal = json.loads(path.read_text())

    token = get_access_token()
    chosen, checked, notes = annotate(proposal, token, args.max_checks)

    for n in notes:
        print(f"  {n}")
    if chosen:
        print(f"album of the week: {chosen.get('artist')} — "
              f"{chosen.get('title')} ({chosen.get('spotify_album_uri')})")
    print(f"availability: {checked} candidate(s) checked")

    if args.dry_run:
        print("dry run — nothing written")
        return 0
    path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
