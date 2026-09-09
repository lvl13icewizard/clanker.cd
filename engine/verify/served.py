"""Initialize the served ledger (served/served.json), optionally from Vol. 1.

With PLAYLIST_MD set, parses a Listening Record Vol. 1 write-up.
Track lines look like:

    2. **Lotus — Sven Wunder** · Swedish library-jazz groove ...

i.e. `^N. **TITLE — ARTIST**` — TITLE first, then an em dash (U+2014), then
ARTIST, closed by `**`; many lines carry a middot-prefixed annotation after
the closing `**` which is ignored. Spotify URIs come positionally from the
independently verified VOL1_URIS file (one `spotify:track:...` per line, same
order as the 30 listing — PLAYLIST.md calls it ground truth).

Output schema (exactly, per CONTRACTS.md):

    {"items": [{"artist": ..., "title": ..., "uri": ..., "context": "vol1"}]}

Degradation policy (never fabricate): the markdown parse must yield a
contiguous 1..N numbered list or we exit nonzero; if the URIs file is missing
or its count doesn't match, `uri` stays null for all items and a warning is
printed — we never guess a pairing.
"""

import json
import re
import sys
from pathlib import Path

from ..lib.config import load_config

# There is no default location for a Vol. 1 write-up. One installation had
# it at an absolute path that used to live here, which meant any other
# machine with no served ledger yet tried to open that path and died.
# Point PLAYLIST_MD at one to seed the ledger; otherwise it starts empty.

# TITLE — ARTIST (em dash U+2014), annotation after closing ** ignored.
_LINE = re.compile(r"^(\d+)\.\s+\*\*(.+?)\s+—\s+(.+?)\*\*", re.M)
_URI = re.compile(r"^spotify:track:[A-Za-z0-9]+$")


def parse_playlist(md_path):
    """Return ordered [(n, title, artist)] from the Vol. 1 markdown."""
    text = Path(md_path).read_text()
    rows = [(int(n), t.strip(), a.strip()) for n, t, a in _LINE.findall(text)]
    nums = [n for n, _, _ in rows]
    if not rows or nums != list(range(1, len(rows) + 1)):
        raise SystemExit(
            "served.py: PLAYLIST.md parse failed — expected a contiguous "
            f"1..N numbered list, got numbers {nums!r}"
        )
    return rows


def parse_uris(uri_path):
    """Return the verified spotify:track: URIs, in file order."""
    lines = [l.strip() for l in Path(uri_path).read_text().splitlines() if l.strip()]
    bad = [l for l in lines if not _URI.match(l)]
    if bad:
        raise SystemExit(f"served.py: malformed URI lines in {uri_path}: {bad[:3]!r}")
    return lines


def build(playlist_md=None, write=True, served_path=None):
    """Parse Vol. 1, pair URIs, write served/served.json. Returns the dict."""
    cfg = load_config()
    md_path = playlist_md or cfg.get("PLAYLIST_MD")
    if not md_path:
        raise SystemExit("served.py: no Vol. 1 write-up to seed from; set "
                         "PLAYLIST_MD or let the ledger start empty")
    rows = parse_playlist(md_path)

    uris = None
    uri_path = cfg.get("VOL1_URIS")
    if uri_path and Path(uri_path).exists():
        parsed = parse_uris(uri_path)
        if len(parsed) == len(rows):
            uris = parsed
        else:
            print(
                f"served.py: WARNING — {len(parsed)} URIs vs {len(rows)} tracks; "
                "leaving uri null rather than guessing the pairing",
                file=sys.stderr,
            )
    else:
        print(
            "served.py: WARNING — VOL1_URIS missing; uris left null",
            file=sys.stderr,
        )

    served = {
        "items": [
            {
                "artist": artist,
                "title": title,
                "uri": uris[i] if uris else None,
                "context": "vol1",
            }
            for i, (_, title, artist) in enumerate(rows)
        ]
    }
    if write:
        Path(served_path or cfg["SERVED_PATH"]).write_text(
            json.dumps(served, indent=2, ensure_ascii=False))
    return served


EMPTY = {"items": []}


def load_or_build(path=None):
    """Read served/served.json. Absent, it is seeded from the Vol. 1 write-up
    only when PLAYLIST_MD is configured and exists; otherwise the ledger
    simply starts empty, which is the correct state for a first press on a
    machine that has served nothing yet."""
    cfg = load_config()
    p = Path(path or cfg["SERVED_PATH"])
    if p.exists():
        return json.loads(p.read_text())
    md = cfg.get("PLAYLIST_MD")
    if md and Path(md).exists():
        return build(playlist_md=md, served_path=str(p))
    return {"items": []}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    playlist_md = argv[0] if argv else None
    served = build(playlist_md=playlist_md)
    items = served["items"]
    with_uri = sum(1 for i in items if i["uri"])
    cfg = load_config()
    print(f"served.py: wrote {cfg['SERVED_PATH']} — {len(items)} items, "
          f"{with_uri} with URIs")
    print(f"  first: {items[0]['title']} — {items[0]['artist']} [{items[0]['uri']}]")
    print(f"  last:  {items[-1]['title']} — {items[-1]['artist']} [{items[-1]['uri']}]")
    if len(items) != 30:
        raise SystemExit(f"served.py: expected 30 Vol. 1 items, parsed {len(items)}")


if __name__ == "__main__":
    main()
