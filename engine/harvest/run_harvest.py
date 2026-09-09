"""Harvest orchestrator -> out/candidates-raw.json.

Runs every adapter, tolerates any of them failing (a crash becomes an
"error: ..." entry in source_status — never a fabricated result), and merges
their payloads into the contract shape:

  {"generated_at", "source_status": {name: "ok|skipped|error: ..."},
   "album_candidates": [...], "track_candidates": [...], "new_releases": [...]}

Usage (from the project root):
  python3 -m engine.harvest.run_harvest              # full harvest
  python3 -m engine.harvest.run_harvest --smoke      # 2 seeds/source, quick
  python3 -m engine.harvest.run_harvest --only rss musicbrainz

musicbrainz runs before lb_labs so MBID resolutions land in the URL cache
first (lb_labs then resolves for free). After every source has run,
second_ring promotes the strongest never-played newcomers to seeds and asks
the similarity providers about them (engine.harvest.second_ring).
"""

import argparse
import datetime as dt
import json
from pathlib import Path

from engine.lib.config import load_config

from engine.harvest import (deezer, labels, lastfm, lb_labs, musicbrainz,
                            pitchfork_local, rss, second_ring)

SMOKE_SEEDS = 2

# (name, module, smoke_limit) — order matters: musicbrainz warms the MBID cache.
SOURCES = [
    ("pitchfork_local", pitchfork_local, None),
    ("rss", rss, None),
    ("musicbrainz", musicbrainz, SMOKE_SEEDS),
    ("lb_labs", lb_labs, SMOKE_SEEDS),
    ("deezer", deezer, SMOKE_SEEDS),
    ("lastfm", lastfm, SMOKE_SEEDS),
    ("labels", labels, SMOKE_SEEDS),
]


def run(only=None, smoke=False):
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_status": {},
        "album_candidates": [],
        "track_candidates": [],
        "new_releases": [],
    }
    for name, module, smoke_limit in SOURCES:
        if only and name not in only:
            out["source_status"][name] = "skipped: not selected"
            continue
        try:
            payload, status = module.harvest(limit=smoke_limit if smoke else None)
        except Exception as e:  # noqa: BLE001 — one source must never sink the run
            out["source_status"][name] = "error: %s: %s" % (type(e).__name__, e)
            continue
        out["source_status"][name] = status
        for key in ("album_candidates", "track_candidates", "new_releases"):
            out[key].extend(payload.get(key) or [])

    # Second ring: the newcomers the first ring found become seeds in turn.
    if only and "second_ring" not in only:
        out["source_status"]["second_ring"] = "skipped: not selected"
    else:
        try:
            ring, status, _ = second_ring.harvest(out["track_candidates"], smoke=smoke)
            added, merged = second_ring.merge(out["track_candidates"], ring)
            out["source_status"]["second_ring"] = status + (
                " -> +%d new artists, %d gained edges" % (added, merged) if ring else "")
        except Exception as e:  # noqa: BLE001
            out["source_status"]["second_ring"] = "error: %s: %s" % (type(e).__name__, e)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", metavar="SOURCE",
                    choices=[s[0] for s in SOURCES] + ["second_ring"],
                    help="run only these sources (others marked skipped)")
    ap.add_argument("--smoke", action="store_true",
                    help="cap network sources at %d seeds for a quick pass" % SMOKE_SEEDS)
    args = ap.parse_args(argv)

    cfg = load_config()
    result = run(only=args.only, smoke=args.smoke)
    dest = Path(cfg["OUT_DIR"]) / "candidates-raw.json"
    dest.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")

    print("wrote %s" % dest)
    for name, status in result["source_status"].items():
        print("  %-16s %s" % (name, status))
    print("  totals: %d album_candidates, %d track_candidates, %d new_releases"
          % (len(result["album_candidates"]), len(result["track_candidates"]),
             len(result["new_releases"])))


if __name__ == "__main__":
    main()
