#!/usr/bin/env python3
"""Check that candidate artist/title pairs are real records.

Every record in a demo persona is a real one, so a pick that iTunes cannot
find is treated as unverified and does not ship. Reads {"artist","title"}
objects as JSON on stdin, writes the same objects back with a "found" field
and the title iTunes matched, so a near-miss can be corrected rather than
guessed at again.

  python3 demo/verify_picks.py < candidates.json > checked.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo.art import track_cover  # noqa: E402


def main():
    picks = json.load(sys.stdin)
    out = []
    for i, p in enumerate(picks):
        url = None
        try:
            url = track_cover(p["artist"], p["title"])
        except Exception as exc:  # a lookup that errors is unverified, not fatal
            print(f"  {p['artist']} / {p['title']}: {exc}", file=sys.stderr)
        p = dict(p, found=bool(url))
        out.append(p)
        mark = "ok " if url else "MISS"
        print(f"  {mark} {p['artist']} / {p['title']}", file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    miss = [p for p in out if not p["found"]]
    print(f"\n{len(out) - len(miss)}/{len(out)} verified, {len(miss)} to replace", file=sys.stderr)


if __name__ == "__main__":
    main()
