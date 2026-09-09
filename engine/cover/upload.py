"""Set the issue's companion-playlist cover on Spotify.

PUT /playlists/{id}/images with the JPEG as base64 (limit 256 KB). Needs the
ugc-image-upload scope: if the stored token predates it, this prints the
one-line re-authorization and exits 0 without changing anything (the issue
itself is fine without a cover). Records companion_playlist.cover_uploaded_at.

Run:  PYTHONPATH=<root> python3 -m engine.cover.upload --n 2
"""

import argparse
import base64
import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ..deliver.spotify_auth import get_access_token
from ..lib.config import load_config


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True)
    args = ap.parse_args(argv)
    cfg = load_config()
    name = f"issue-{args.n:03d}.json"
    src = Path(cfg["ISSUES_DIR"]) / name
    issue = json.loads(src.read_text())
    cp = issue.get("companion_playlist") or {}
    pid = cp.get("id")
    if not pid:
        print("cover upload: no companion playlist id yet; skipping")
        return 0
    img = Path(cfg["SITE_ISSUES_DIR"]) / f"cover-{args.n:03d}.jpg"
    if not img.exists():
        print(f"cover upload: {img.name} not rendered yet; skipping")
        return 0
    data = img.read_bytes()
    if len(data) > 256 * 1024:
        print(f"cover upload: {img.name} is {len(data)//1024} KB, over Spotify's 256 KB; skipping")
        return 0
    token = get_access_token()
    req = urllib.request.Request(f"https://api.spotify.com/v1/playlists/{pid}/images",
                                 data=base64.b64encode(data), method="PUT",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "image/jpeg"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:200]
        except Exception:
            pass
        if e.code in (401, 403):
            print("cover upload: Spotify needs the image scope once. Run:\n"
                  "  PYTHONPATH=. python3 -m engine.deliver.spotify_auth\n"
                  f"  ({e.code}: {body.strip()})")
            return 0
        print(f"cover upload failed: HTTP {e.code} {body}")
        return 1
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for p in (src, Path(cfg["SITE_ISSUES_DIR"]) / name):
        d = json.loads(p.read_text())
        d.setdefault("companion_playlist", {})["cover_uploaded_at"] = stamp
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print(f"cover upload: set on playlist {pid} (HTTP {status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
