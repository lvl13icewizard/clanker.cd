"""Append everything an issue published to the served ledger.

The served ledger is what guarantees a recommendation never repeats: verify
consults it before any candidate is allowed through. Previously this was done
by hand after each issue, which is exactly the kind of step that gets skipped
and quietly breaks the guarantee.

Append-only exposure log: every item an issue module offered is one row,
stamped with the issue date, even when the same record was offered before
(module policies age from the last exposure; engine.verify.served_policy).
Idempotent: re-running for the same issue adds nothing.

Run:  PYTHONPATH=<root> python3 -m engine.serve_ledger --n 2
"""

import argparse
import json
from pathlib import Path

from .lib.config import load_config


def entries_for(issue):
    n = issue.get("issue")
    tag = lambda kind: f"issue-{n:03d}:{kind}"
    out = []
    # Stamped so the artist-level cooldown (engine.verify.repeat_guard) can
    # age an offer without having to look the issue date back up.
    when = issue.get("date")
    for m in issue.get("modules", []):
        t = m.get("type")
        if t == "front_to_back":
            a = m.get("album") or {}
            out.append({"artist": a.get("artist"), "title": a.get("title"),
                        "uri": a.get("spotify_album_uri"), "context": tag(t)})
        elif t in ("singles_rack", "revival_desk"):
            for x in m.get("tracks", []):
                out.append({"artist": x.get("artist"), "title": x.get("title"),
                            "uri": x.get("spotify_track_uri"),
                            "context": tag(t)})
        elif t == "critics_desk":
            for x in m.get("albums", []):
                out.append({"artist": x.get("artist"), "title": x.get("title"),
                            "uri": x.get("url"), "context": tag(t)})
        elif t == "catalog_room":
            out.append({"artist": m.get("artist"),
                        "title": "catalog room feature",
                        "uri": None, "context": tag(t)})
        elif t == "the_mix":
            for x in m.get("mixes", []):
                out.append({"artist": x.get("show"),
                            "title": x.get("episode") or x.get("show"),
                            "uri": x.get("url"), "context": tag(t)})
        elif t == "new_this_week":
            for x in m.get("releases", []):
                out.append({"artist": x.get("artist"), "title": x.get("title"),
                            "uri": None, "context": tag(t)})
    for e in out:
        e["served_at"] = when
    return [e for e in out if e.get("artist")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    n = ap.parse_args().n
    cfg = load_config()
    issue_p = Path(cfg["ISSUES_DIR"]) / f"issue-{n:03d}.json"
    if not issue_p.exists():
        raise SystemExit(f"no issue at {issue_p}")
    issue = json.loads(issue_p.read_text())

    sp = Path(cfg["SERVED_PATH"])
    served = json.loads(sp.read_text()) if sp.exists() else {"items": []}
    # One row per exposure: the same record offered again in a later issue
    # is a new row with its own date, so cooldowns age from the LAST offer
    # and the offer history is complete. Re-running for one issue adds nothing.
    have = {(i.get("artist"), i.get("title"), i.get("context")) for i in served["items"]}
    new = [e for e in entries_for(issue)
           if (e["artist"], e["title"], e["context"]) not in have]
    served["items"].extend(new)
    sp.write_text(json.dumps(served, indent=1, ensure_ascii=False))
    print(f"served ledger: +{len(new)} -> {len(served['items'])} items")


if __name__ == "__main__":
    main()
