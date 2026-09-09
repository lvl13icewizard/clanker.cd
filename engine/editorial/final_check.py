"""The last gate before an issue is published: semantic, on the final document.

The numbers gate (validate.py) proves every figure in the prose has a
receipt. It does not prove the prose sits on the right record, that a track
chosen at resolve time is still new, that a copy pass or a backfill kept the
picks the selector chose, or that nothing already served came back. Those
are checks on identity, and they only mean anything on the document as it
will actually ship, after selection, resolution, copy and correction have
all had their turn. That is what this runs.

    python3 -m engine.editorial.final_check --n 4

Errors stop a press. Warnings (a track with no Spotify id) are printed and
do not: a short playlist is survivable, a wrong record is not.
"""

import argparse
import json
import sys
from pathlib import Path

from engine.lib.normalize import norm_artist, norm_title, track_key


def _proposal_rack_artists(proposal):
    out = set()
    for items in (proposal.get("singles_rack") or {}).values():
        for it in items or []:
            out.add(norm_artist(it.get("artist") or ""))
    return out


def _proposal_revival_keys(proposal):
    out = set()
    pools = proposal.get("revival_desk") or {}
    for items in pools.values():
        for it in items or []:
            if isinstance(it, dict):
                out.add(track_key(it.get("artist") or "", it.get("track") or it.get("title") or ""))
    return out


def _proposal_album_keys(proposal):
    out = set()
    for it in proposal.get("front_to_back") or []:
        if isinstance(it, dict):
            out.add(track_key(it.get("artist") or "", it.get("title") or ""))
    return out


def final_check(issue, proposal, served, artist_played, track_played):
    """Return (errors, warnings). artist_played(name) and
    track_played(artist, title) answer from the play history."""
    errors, warnings = [], []
    served_keys = {track_key(i.get("artist") or "", i.get("title") or "")
                   for i in (served or {}).get("items") or []}
    rack_artists = _proposal_rack_artists(proposal)
    revival_keys = _proposal_revival_keys(proposal)
    album_keys = _proposal_album_keys(proposal)

    for m in issue.get("modules") or []:
        t = m.get("type")
        if t == "singles_rack":
            seen = set()
            for i, tr in enumerate(m.get("tracks") or []):
                where = f"singles_rack.tracks[{i}]"
                a, ti = tr.get("artist"), tr.get("title")
                if not a or not ti:
                    errors.append(f"{where}: a card with no track behind it ({a!r} / {ti!r})")
                    continue
                na = norm_artist(a)
                if na in seen:
                    errors.append(f"{where}: {a!r} appears twice in the rack")
                seen.add(na)
                if rack_artists and na not in rack_artists:
                    errors.append(f"{where}: {a!r} was not among the selector's leads; identity changed after selection")
                if artist_played(a):
                    errors.append(f"{where}: {a!r} is in the play history; the rack promises never-played artists")
                elif track_played(a, ti):
                    errors.append(f"{where}: {a!r} / {ti!r} is in the play history")
                if track_key(a, ti) in served_keys:
                    errors.append(f"{where}: {a!r} / {ti!r} was already served")
                if not tr.get("spotify_track_uri"):
                    warnings.append(f"{where}: no Spotify id; it will sit out of the playlist")
        elif t == "revival_desk":
            for i, tr in enumerate(m.get("tracks") or []):
                where = f"revival_desk.tracks[{i}]"
                k = track_key(tr.get("artist") or "", tr.get("title") or "")
                if revival_keys and k not in revival_keys:
                    errors.append(f"{where}: {tr.get('artist')!r} / {tr.get('title')!r} is not in any revival pool")
        elif t == "front_to_back":
            al = m.get("album") or {}
            k = track_key(al.get("artist") or "", al.get("title") or "")
            if not al.get("artist") or not al.get("title"):
                errors.append("front_to_back: no album")
            else:
                if album_keys and k not in album_keys:
                    errors.append(f"front_to_back: {al.get('artist')!r} / {al.get('title')!r} was not a selector candidate")
                if artist_played(al.get("artist")):
                    errors.append(f"front_to_back: {al.get('artist')!r} is in the play history")
                if k in served_keys:
                    errors.append(f"front_to_back: {al.get('artist')!r} / {al.get('title')!r} was already served")
        elif t == "critics_desk":
            for i, al in enumerate(m.get("albums") or []):
                if al.get("artist") and artist_played(al.get("artist")):
                    errors.append(f"critics_desk.albums[{i}]: {al.get('artist')!r} is in the play history")
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    args = ap.parse_args(argv)
    from engine.lib.config import load_config
    from engine.lib import history
    from engine.verify import served as served_mod
    cfg = load_config()
    issue_p = Path(cfg["ISSUES_DIR"]) / f"issue-{args.n:03d}.json"
    issue = json.loads(issue_p.read_text())
    prop_p = Path(cfg["OUT_DIR"]) / "selection-proposal.json"
    proposal = json.loads(prop_p.read_text()) if prop_p.exists() else {}
    if not proposal:
        print("final_check: no selection proposal in out/; identity-vs-selection checks skipped", file=sys.stderr)
    served = served_mod.load_or_build()
    # The served ledger includes THIS issue once serve_ledger has run; do not
    # count an issue's own entries as repeats.
    own = {track_key(i.get("artist") or "", i.get("title") or "")
           for i in served.get("items") or [] if f"issue-{args.n:03d}" in str(i.get("context") or "")}
    served = {"items": [i for i in served.get("items") or []
                        if track_key(i.get("artist") or "", i.get("title") or "") not in own]}
    errors, warnings = final_check(issue, proposal, served,
                                   lambda a: bool(history.artist_played(a)),
                                   lambda a, t: bool(history.track_played(a, t)))
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    print(f"final_check: issue {args.n:03d}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
