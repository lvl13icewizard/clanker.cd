"""Supply gauge: how many weeks of Singles Rack the verified pool holds.

The rack promises ten artists a week the reader has never played. The pool
those come from is finite and shrinking: a deep history has already heard
the first ring around its favourites. This gauge answers, after every
verify, "how many never-played, never-offered artists are eligible right
now, and how many weeks is that?" so supply running low is a printed
warning in the press log, not a short rack one Saturday.

Counts are distinct artists that pass the selector's own eligibility rule
(verdict novel, not served, past the artist guard), split by lane and by
ring. Playability is unknown until resolve, so the weeks figure is an upper
bound; PLAYABLE_RATE (from the backfill history: roughly one lead in four
has no song behind it) gives the expected figure beside it.

Writes out/supply.json (current) and appends to out/supply-history.json.

Run:  PYTHONPATH=<root> python3 -m engine.harvest.supply
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from engine.lib.config import load_config
from engine.lib.normalize import norm_artist

RACK_PER_WEEK = 10
WARN_WEEKS = 3
PLAYABLE_RATE = 0.75


def _eligible(cand):
    from engine.select.select_issue import _eligible as sel
    return sel(cand)


def measure(verified, per_week=RACK_PER_WEEK, playable=PLAYABLE_RATE):
    lanes, rings, seen = Counter(), Counter(), {}
    for c in verified.get("track_candidates") or []:
        if not _eligible(c):
            continue
        na = norm_artist(c.get("artist") or "")
        if not na or na in seen:
            continue
        seen[na] = c
        lanes[c.get("cluster_hint") or "unclustered"] += 1
        rings[int(c.get("ring") or 1)] += 1
    n = len(seen)
    weeks = n / per_week if per_week else 0.0
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eligible_artists": n,
        "weeks_of_supply": round(weeks, 1),
        "weeks_expected_playable": round(weeks * playable, 1),
        "per_week": per_week,
        "by_lane": dict(sorted(lanes.items(), key=lambda kv: -kv[1])),
        "by_ring": {str(k): v for k, v in sorted(rings.items())},
        "low": weeks * playable < WARN_WEEKS,
    }


def report(m):
    lines = ["supply: %d eligible never-played artists = %.1f weeks of rack "
             "(%.1f expected playable)" % (m["eligible_artists"], m["weeks_of_supply"],
                                           m["weeks_expected_playable"])]
    if m["by_ring"]:
        lines.append("  rings: " + ", ".join("ring %s: %d" % kv for kv in m["by_ring"].items()))
    if m["by_lane"]:
        lines.append("  lanes: " + ", ".join("%s %d" % kv for kv in m["by_lane"].items()))
    if m["low"]:
        lines.append("  [warn] under %d weeks of supply — widen retrieval before "
                     "the rack runs short" % WARN_WEEKS)
    return "\n".join(lines)


def main(argv=None):
    cfg = load_config()
    out = Path(cfg["OUT_DIR"])
    p = out / "candidates-verified.json"
    if not p.exists():
        raise SystemExit("supply: %s not found — run engine.verify.zero_play first" % p)
    m = measure(json.loads(p.read_text()))
    (out / "supply.json").write_text(json.dumps(m, indent=1))
    hist_p = out / "supply-history.json"
    hist = json.loads(hist_p.read_text()) if hist_p.exists() else []
    hist.append({k: m[k] for k in ("measured_at", "eligible_artists", "weeks_of_supply",
                                    "weeks_expected_playable", "by_ring")})
    hist_p.write_text(json.dumps(hist[-104:], indent=1))
    print(report(m))


if __name__ == "__main__":
    main()
