"""The release calendar: everything the harvest has ever seen, rolled up.

The weekly harvest looks a short window back; this step accumulates every
release it has ever reported into a persistent store (served/
releases-store.json, so first-seen dates survive between runs), resolves
cover art through the same resolvers the issues use, and writes the site's
calendar file. The issue's New This Week module carries only the fresh
slice; this file is the whole shelf.

Run:  PYTHONPATH=<root> python3 -m engine.releases
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .art import album_cover
from .lib.config import load_config
from .lib.http import get_json

WINDOW_DAYS = 210      # how far back the calendar reaches


def single_cover(artist, title):
    """A single often exists only as a track: search iTunes songs and take
    the release artwork the track sits on."""
    import urllib.parse
    try:
        d = get_json("https://itunes.apple.com/search?term="
                     + urllib.parse.quote(f"{artist} {title}")
                     + "&entity=song&limit=10", rate_key="itunes",
                     min_interval=0.6, ttl_days=30)
    except Exception:
        return None
    a_l = (artist or "").lower()
    for r in d.get("results") or []:
        if a_l in (r.get("artistName") or "").lower():
            url = r.get("artworkUrl100") or ""
            if url:
                return url.replace("100x100bb", "600x600bb")
    return None


def key_for(r):
    return r.get("mbid") or f"{(r.get('artist') or '').lower()}|{(r.get('title') or '').lower()}"


def main():
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])
    raw = out_dir / "candidates-raw.json"
    store_p = Path(cfg["SERVED_PATH"]).parent / "releases-store.json"
    site_p = Path(cfg["SITE_ISSUES_DIR"]) / "releases.json"

    store = {}
    if store_p.exists():
        store = json.loads(store_p.read_text())

    today = date.today().isoformat()
    fresh = 0
    if raw.exists():
        for r in json.loads(raw.read_text()).get("new_releases", []):
            k = key_for(r)
            if k in store:
                continue
            store[k] = {**{f: r.get(f) for f in
                           ("artist", "title", "release_date", "release_type",
                            "relationship", "via", "mbid")},
                        "first_seen": today}
            fresh += 1
    else:
        print("out/candidates-raw.json missing — calendar keeps its last state")

    floor = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = [r for r in store.values() if (r.get("release_date") or "") >= floor]
    rows.sort(key=lambda r: (r.get("release_date") or "", r.get("artist") or ""), reverse=True)

    looked = 0
    for r in rows:
        if r.get("cover_url"):
            continue
        year = (r.get("release_date") or "")[:4]
        try:
            url = album_cover(r.get("artist"), r.get("title"), int(year) if year.isdigit() else None)
        except Exception:
            url = None
        if not url and r.get("release_type") == "single":
            url = single_cover(r.get("artist"), r.get("title"))
        r["cover_url"] = url
        looked += 1

    store_p.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    site_p.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "releases": rows,
    }, indent=1, ensure_ascii=False))
    covered = sum(1 for r in rows if r.get("cover_url"))
    print(f"release calendar: {len(rows)} releases in the window "
          f"({fresh} new to the store, covers {covered}/{len(rows)}, {looked} lookups) -> {site_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
