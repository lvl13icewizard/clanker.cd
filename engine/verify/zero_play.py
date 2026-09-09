"""Two-round zero-play verification of harvested candidates.

Reads a candidates file shaped like out/candidates-raw.json (HARVEST's
output), attaches a `verification` block to every candidate in
album_candidates / track_candidates / new_releases, and writes
out/candidates-verified.json plus a human summary at
out/verification-report.md.

Protocol (CONTRACTS.md):
  Round 1 — exact normalized checks via engine.lib.history:
    artist_played(artist) and, when the candidate has a title,
    track_played(artist, title).
  Round 2 — near_artist_matches() and title_collisions() are recorded for
    ALL candidates regardless of round-1 outcome.

Verdict resolution (when in doubt -> ambiguous, never guess):
  1. exact artist or exact artist+title match in history  -> "played"
  2. else any non-empty near_matches or title_collisions  -> "ambiguous"
     ("unless clearly distinct" is deliberately NOT decided here — that
     judgment belongs to curation; we only surface the evidence)
  3. else                                                 -> "novel"

Served ledger: a candidate whose normalized artist+title exactly matches a
Vol. 1 item gets served_before=true (and select_issue excludes it — an
already-served track is not novel-eligible). A candidate by a served artist
with a different (or no) title keeps served_before=false, per the contract's
"different track by a served artist" carve-out.

New-release entries with relationship=played are exempt from the novelty
requirement (follow-your-artists news); their verdict is still computed and
recorded honestly, and the exemption is applied at selection time.

Runs standalone before the real harvest exists:
  python3 -m engine.verify.zero_play --candidates PATH [--out PATH] [--report PATH]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..lib import history
from ..lib.config import load_config
from ..lib.normalize import norm_artist, norm_title
from . import repeat_guard as guard_mod
from . import served as served_mod

CATEGORIES = ("album_candidates", "track_candidates", "new_releases")


def _served_track_set(served):
    return {
        (norm_artist(i["artist"]), norm_title(i["title"]))
        for i in served.get("items", [])
    }


def verify_candidate(cand, served_tracks, guard=None):
    """Return the verification dict for one candidate (contract schema)."""
    artist = cand.get("artist") or ""
    title = cand.get("title")  # None is normal for track_candidates

    # Round 1 — exact normalized checks, under every name the artist is
    # known by (a MusicBrainz canonical name in another script hides a
    # Latin-credited artist the reader plays; engine.lib.names).
    artist_row = history.artist_played(artist)
    for alias in cand.get("aliases") or []:
        if artist_row:
            break
        if alias and alias != artist:
            artist_row = history.artist_played(alias)
    track_row = history.track_played(artist, title) if title else None

    # Round 2 — recorded for ALL candidates.
    near = [r["artist"] for r in history.near_artist_matches(artist)]
    collisions = (
        [f"{r['artist']} — {r['track']}" for r in history.title_collisions(title)]
        if title
        else []
    )

    served_before = bool(
        title and (norm_artist(artist), norm_title(title)) in served_tracks
    )

    # Artist-level repeat state. The title-level check above cannot see a
    # repeat when the candidate has no title, which is every Singles Rack
    # lead; it also cannot see an artist played only since the last history
    # export. Both are recorded here and enforced at selection.
    repeat = guard.status(artist) if guard else None

    if artist_row or track_row:
        verdict = "played"
    elif repeat and repeat["state"] == "blocked":
        # Played per a previous Ledger, but too recently for the export.
        verdict = "played"
    elif near or collisions:
        verdict = "ambiguous"
    else:
        verdict = "novel"

    return {
        "artist_played": bool(artist_row) or bool(repeat and repeat["ledger"]),
        "artist_row": dict(artist_row) if artist_row else None,
        "near_matches": near,
        "title_collisions": collisions,
        "served_before": served_before,
        "artist_repeat": repeat,
        "verdict": verdict,
    }


def _report(data, counts, ambiguous, served_hits, in_path, n_served,
            repeat_hits=(), guard=None):
    st = history.stats()
    lines = [
        "# Verification report",
        "",
        f"- Generated: {data['verified_at']}",
        f"- Input: `{in_path}`",
        f"- Checked against: {st['artists']:,} artists / {st['tracks']:,} tracks "
        "(round 1 exact normalized match, round 2 near-miss + title-collision "
        "sweep on every candidate)",
        f"- Served ledger: {n_served} items (vol1)",
        "",
        "## Verdict counts",
        "",
        "| category | total | novel | played | ambiguous | served_before "
        "| artist blocked | artist cooldown |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cat in CATEGORIES:
        c = counts[cat]
        lines.append(
            f"| {cat} | {c['total']} | {c['novel']} | {c['played']} "
            f"| {c['ambiguous']} | {c['served_before']} "
            f"| {c.get('artist_blocked', 0)} | {c.get('artist_cooldown', 0)} |"
        )
    exempt = sum(
        1
        for c in data.get("new_releases", [])
        if c.get("relationship") == "played"
    )
    lines += [
        "",
        f"Note: {exempt} new_release entries have relationship=played and are "
        "exempt from the novelty requirement (follow-your-artists news).",
        "",
        "## Ambiguous cases",
        "",
    ]
    if not ambiguous:
        lines.append("None.")
    for cat, cand in ambiguous:
        v = cand["verification"]
        title = cand.get("title") or "(artist-level)"
        lines.append(f"### {cand.get('artist')} — {title}  `[{cat}]`")
        if v["near_matches"]:
            lines.append(f"- near artist matches: {', '.join(v['near_matches'])}")
        if v["title_collisions"]:
            lines.append(
                f"- title collisions (played): {'; '.join(v['title_collisions'])}"
            )
        lines.append("")
    lines += ["## Served-before matches", ""]
    if not served_hits:
        lines.append("None.")
    for cat, cand in served_hits:
        lines.append(
            f"- {cand.get('artist')} — {cand.get('title')} `[{cat}]` — exact "
            "match against a Vol. 1 item; excluded from novel selection"
        )

    lines += ["", "## Artist-level repeats", ""]
    if guard is not None:
        s = guard.summary()
        lines += [
            f"{s['offered_artists']} artists have been offered before; "
            f"{s['played_since_serving']} were played after being served. "
            f"Cooldown is {s['cooldown_days']} days.",
            "",
            "`blocked` = played, so no longer a stranger (Revival Desk and "
            "Catalog Room are where familiar artists belong). `cooldown` = "
            "offered and passed on, eligible again once it expires.",
            "",
        ]
    if not repeat_hits:
        lines.append("None.")
    seen = set()
    for cat, cand in repeat_hits:
        r = cand["verification"]["artist_repeat"]
        key = (cand.get("artist"), r["state"])
        if key in seen:
            continue
        seen.add(key)
        until = f", clear after {r['cooldown_until']}" if r["cooldown_until"] else ""
        lines.append(
            f"- **{r['state']}** {cand.get('artist')} `[{cat}]` — "
            f"{r['reason']}{until}"
        )
    lines.append("")
    return "\n".join(lines)


def run(candidates_path, out_path, report_path):
    p = Path(candidates_path)
    if not p.exists():
        raise SystemExit(
            f"zero_play: candidates file not found: {p} — run the harvest "
            "first or pass --candidates"
        )
    data = json.loads(p.read_text())

    served = served_mod.load_or_build()
    served_tracks = _served_track_set(served)
    guard = guard_mod.build_guard(served=served)

    counts = {
        cat: {"total": 0, "novel": 0, "played": 0, "ambiguous": 0,
              "served_before": 0, "artist_blocked": 0, "artist_cooldown": 0}
        for cat in CATEGORIES
    }
    ambiguous, served_hits, repeat_hits = [], [], []
    for cat in CATEGORIES:
        for cand in data.get(cat, []):
            v = verify_candidate(cand, served_tracks, guard)
            cand["verification"] = v
            c = counts[cat]
            c["total"] += 1
            c[v["verdict"]] += 1
            if v["served_before"]:
                c["served_before"] += 1
                served_hits.append((cat, cand))
            repeat = v.get("artist_repeat") or {}
            state = repeat.get("state")
            # Count only what the guard adds. An artist already in the
            # history export is counted under `played`; the guard's own
            # contribution is the one played only since being served, which
            # the export cannot see yet.
            if state == "blocked" and repeat.get("ledger"):
                c["artist_blocked"] += 1
                repeat_hits.append((cat, cand))
            elif state == "cooldown":
                c["artist_cooldown"] += 1
                repeat_hits.append((cat, cand))
            if v["verdict"] == "ambiguous":
                ambiguous.append((cat, cand))

    st = history.stats()
    data["verified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["verification_meta"] = {
        "rounds": 2,
        "artists_checked_against": st["artists"],
        "tracks_checked_against": st["tracks"],
        "served_items": len(served.get("items", [])),
        "method": "round 1 exact normalized artist/track match; round 2 "
        "near-artist + title-collision sweep recorded for all candidates; "
        "non-empty round-2 evidence => ambiguous (left to curation)",
    }

    data["verification_meta"]["repeat_guard"] = guard.summary()

    Path(out_path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    Path(report_path).write_text(
        _report(data, counts, ambiguous, served_hits, candidates_path,
                len(served.get("items", [])), repeat_hits, guard)
    )
    total = sum(c["total"] for c in counts.values())
    print(f"zero_play: verified {total} candidates -> {out_path}")
    for cat in CATEGORIES:
        print(f"  {cat}: {counts[cat]}")
    print(f"  report -> {report_path}")
    return data


def main(argv=None):
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--candidates",
        default=str(Path(cfg["OUT_DIR"]) / "candidates-raw.json"),
        help="input candidates file (default out/candidates-raw.json)",
    )
    ap.add_argument(
        "--out", default=str(Path(cfg["OUT_DIR"]) / "candidates-verified.json")
    )
    ap.add_argument(
        "--report", default=str(Path(cfg["OUT_DIR"]) / "verification-report.md")
    )
    args = ap.parse_args(argv)
    run(args.candidates, args.out, args.report)


if __name__ == "__main__":
    main()
