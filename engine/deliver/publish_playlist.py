"""Publish an issue's tracks to a Spotify playlist from EXACT URIs.

    python3 -m engine.deliver.publish_playlist --n 1
    python3 -m engine.deliver.publish_playlist --n 1 --dry-run

Uses the post-February-2026 endpoints: POST /me/playlists to create and
PUT /playlists/{id}/items to set contents. The old /playlists/{id}/tracks
paths are gone — do not reintroduce them.

Idempotent: the playlist id is recorded in the issue file, and a re-run
replaces that playlist's contents rather than creating a duplicate. Order
mirrors the reader: singles_rack first, then the album of the week front to
back (its tracks fetched from the album at publish time), then revival_desk.
"""

import argparse
import json
from datetime import datetime, timezone
import sys
from pathlib import Path

from engine.deliver.spotify_auth import api, get_access_token
from engine.lib.config import load_config

MAX_ITEMS_PER_CALL = 100


def album_track_uris(issue, token):
    """The album of the week's tracks, in album order, or ([], []) when the
    issue has no resolved album. Needs a token: the tracklist is fetched."""
    album = None
    for mod in issue.get("modules", []):
        if mod.get("type") == "front_to_back" and isinstance(mod.get("album"), dict):
            album = mod["album"]
            break
    uri = (album or {}).get("spotify_album_uri") or ""
    if not uri.startswith("spotify:album:"):
        return [], []
    aid = uri.split(":")[-1]
    uris, labels, offset = [], [], 0
    while True:
        d = api("GET", f"/albums/{aid}/tracks?limit=50&offset={offset}", token)
        items = d.get("items") or []
        for t in items:
            if t.get("uri"):
                uris.append(t["uri"])
                labels.append(f"{album.get('artist')} — {t.get('name')}  (album)")
        offset += len(items)
        if not items or (d.get("total") and offset >= d["total"]):
            return uris, labels


def collect_uris(issue, token=None):
    """(uris, labels, missing) mirroring the reader's order: singles first,
    then the album of the week front to back, then the second chances. The
    album needs a token to resolve; without one (dry runs) it is noted and
    skipped."""
    out = {"singles_rack": ([], []), "revival_desk": ([], [])}
    missing = []
    for mod in issue.get("modules", []):
        if mod.get("type") not in out:
            continue
        for t in mod.get("tracks", []):
            uri = t.get("spotify_track_uri")
            label = f"{t.get('artist')} — {t.get('title')}"
            if uri and uri.startswith("spotify:track:"):
                out[mod["type"]][0].append(uri)
                out[mod["type"]][1].append(label)
            else:
                missing.append(label)
    if token:
        alb_u, alb_l = album_track_uris(issue, token)
    else:
        alb_u, alb_l = [], ["(album of the week resolves at publish time)"]
        if not any(m.get("type") == "front_to_back" for m in issue.get("modules", [])):
            alb_l = []
    uris = out["singles_rack"][0] + alb_u + out["revival_desk"][0]
    labels = out["singles_rack"][1] + alb_l + out["revival_desk"][1]
    return uris, labels, missing


def publish(issue_path, dry_run=False):
    issue = json.loads(Path(issue_path).read_text())
    n = issue.get("issue")
    title = issue.get("title") or f"Issue {n:03d}"
    if dry_run:
        uris, labels, missing = collect_uris(issue)
        print(f"issue {n}: {len(uris)} tracks + the album")
        for i, lab in enumerate(labels, 1):
            print(f"  {i:2d}. {lab}")
        if missing:
            print(f"  ({len(missing)} unresolved, skipped: {'; '.join(missing)})")
        print("dry run — nothing sent")
        return 0

    token = get_access_token()
    uris, labels, missing = collect_uris(issue, token)
    if not uris:
        raise SystemExit("no resolved track URIs in this issue — nothing to publish")
    print(f"issue {n}: {len(uris)} tracks")
    for i, lab in enumerate(labels, 1):
        print(f"  {i:2d}. {lab}")
    if missing:
        print(f"  ({len(missing)} unresolved, skipped: {'; '.join(missing)})")
    existing = (issue.get("companion_playlist") or {}).get("id")
    desc = (issue.get("dek") or "")[:300]

    if existing:
        api("PUT", f"/playlists/{existing}", token,
            {"name": title, "description": desc})
        pid = existing
        print(f"updating existing playlist {pid}")
    else:
        me = api("GET", "/me", token)
        created = api("POST", "/me/playlists", token,
                      {"name": title, "description": desc, "public": False})
        pid = created["id"]
        print(f"created playlist {pid} for {me.get('id')}")

    # PUT replaces contents wholesale (first call), POST appends the remainder.
    api("PUT", f"/playlists/{pid}/items", token,
        {"uris": uris[:MAX_ITEMS_PER_CALL]})
    for i in range(MAX_ITEMS_PER_CALL, len(uris), MAX_ITEMS_PER_CALL):
        api("POST", f"/playlists/{pid}/items", token,
            {"uris": uris[i:i + MAX_ITEMS_PER_CALL]})

    got = api("GET", f"/playlists/{pid}/items?fields=total", token)
    total = got.get("total")
    if total != len(uris):
        print(f"WARNING: playlist reports {total} items, expected {len(uris)}")

    url = f"https://open.spotify.com/playlist/{pid}"
    # Merge, never replace: the record also carries cover_art and whatever
    # else later stages have stamped, and a republish must not lose it.
    cp = issue.get("companion_playlist") or {}
    cp.update({
        "name": title, "id": pid, "uri": f"spotify:playlist:{pid}",
        "spotify_url": url, "status": "published", "track_count": total,
        # The moment the picks were actually exposed; the ledger grades from
        # here rather than from midnight of the issue date.
        "published_at": cp.get("published_at") or datetime.now(timezone.utc).isoformat(),
        "note": "singles, then the album front to back, then second chances; "
                "written from verified URIs via the dev-mode app "
                "(POST /me/playlists + PUT /playlists/{id}/items)"})
    issue["companion_playlist"] = cp
    out = json.dumps(issue, indent=1, ensure_ascii=False)
    Path(issue_path).write_text(out)
    site = Path(load_config()["SITE_ISSUES_DIR"]) / Path(issue_path).name
    site.write_text(out)
    print(f"published {total} tracks -> {url}")
    print(f"stamped {issue_path} and {site}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="issue number")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the tracklist without calling Spotify")
    args = ap.parse_args()
    cfg = load_config()
    path = Path(cfg["ISSUES_DIR"]) / f"issue-{args.n:03d}.json"
    if not path.exists():
        raise SystemExit(f"no such issue: {path}")
    return publish(path, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
