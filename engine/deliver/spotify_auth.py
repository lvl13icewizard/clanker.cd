"""One-time Spotify OAuth, then silent token refresh forever after.

    python3 -m engine.deliver.spotify_auth        # authorize (opens a browser)
    python3 -m engine.deliver.spotify_auth --check  # verify stored token

Authorization Code flow. The refresh token is written to .spotify-token.json
at the project root (gitignored) and traded for short-lived access tokens on
demand, so scheduled runs never need a human.

Redirect URI must be registered in the Spotify dashboard EXACTLY as
REDIRECT_URI below. Spotify rejects `localhost`; plain HTTP is permitted only
for literal loopback addresses.
"""

import argparse
import base64
import http.server
import json
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from engine.lib.config import PROJECT_ROOT, load_config

REDIRECT_URI = "http://127.0.0.1:8888/callback"
PORT = 8888
SCOPES = "playlist-modify-private playlist-modify-public ugc-image-upload"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
TOKEN_PATH = PROJECT_ROOT / ".spotify-token.json"
UA = "discovery-dashboard/0.1 (personal project)"


class _Callback(http.server.BaseHTTPRequestHandler):
    result = {}

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        if parts.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        q = dict(urllib.parse.parse_qsl(parts.query))
        _Callback.result = q
        ok = "code" in q
        body = ("<h2>Authorized.</h2><p>Close this tab and return to the "
                "terminal.</p>" if ok else
                f"<h2>Authorization failed</h2><pre>{q.get('error','unknown')}</pre>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):  # keep the console clean
        pass


def _basic_auth(cfg):
    pair = f"{cfg['SPOTIFY_CLIENT_ID']}:{cfg['SPOTIFY_CLIENT_SECRET']}"
    return base64.b64encode(pair.encode()).decode()


def _post_token(cfg, data):
    req = urllib.request.Request(
        TOKEN_URL, data=urllib.parse.urlencode(data).encode(),
        headers={"Authorization": f"Basic {_basic_auth(cfg)}",
                 "Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"token request failed (HTTP {e.code}): {detail}")


def _require_creds(cfg):
    missing = [k for k in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")
               if not (cfg.get(k) or "").strip()]
    if missing:
        raise SystemExit(
            f"{' and '.join(missing)} missing from .env — see SPOTIFY-APP.md")


def authorize():
    cfg = load_config()
    _require_creds(cfg)
    state = secrets.token_urlsafe(16)
    params = {"client_id": cfg["SPOTIFY_CLIENT_ID"], "response_type": "code",
              "redirect_uri": REDIRECT_URI, "scope": SCOPES, "state": state}
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    server = http.server.HTTPServer(("127.0.0.1", PORT), _Callback)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"opening browser — approve access as your Spotify user\n  {url}\n")
    webbrowser.open(url)

    deadline = time.time() + 300
    while not _Callback.result and time.time() < deadline:
        time.sleep(0.3)
    server.shutdown()
    res = _Callback.result
    if not res:
        raise SystemExit("timed out waiting for the browser callback")
    if "error" in res:
        raise SystemExit(f"authorization denied: {res['error']}")
    if res.get("state") != state:
        raise SystemExit("state mismatch — aborting (possible CSRF)")

    tok = _post_token(cfg, {"grant_type": "authorization_code",
                            "code": res["code"], "redirect_uri": REDIRECT_URI})
    if "refresh_token" not in tok:
        raise SystemExit(f"no refresh_token in response: {sorted(tok)}")
    TOKEN_PATH.write_text(json.dumps({"refresh_token": tok["refresh_token"],
                                      "scope": tok.get("scope"),
                                      "obtained_at": time.time()}, indent=1))
    TOKEN_PATH.chmod(0o600)
    print(f"stored refresh token -> {TOKEN_PATH.name} (gitignored, 0600)")
    print(f"scopes granted: {tok.get('scope')}")
    return True


def get_access_token():
    """Fresh access token from the stored refresh token."""
    cfg = load_config()
    _require_creds(cfg)
    if not TOKEN_PATH.exists():
        raise SystemExit("not authorized yet — run "
                         "`python3 -m engine.deliver.spotify_auth`")
    stored = json.loads(TOKEN_PATH.read_text())
    tok = _post_token(cfg, {"grant_type": "refresh_token",
                            "refresh_token": stored["refresh_token"]})
    # Spotify may hand back a rotated refresh token; persist it when it does.
    if tok.get("refresh_token") and tok["refresh_token"] != stored["refresh_token"]:
        stored["refresh_token"] = tok["refresh_token"]
        stored["rotated_at"] = time.time()
        TOKEN_PATH.write_text(json.dumps(stored, indent=1))
        TOKEN_PATH.chmod(0o600)
    return tok["access_token"]


def api(method, path, token, body=None):
    """Call the Web API. path is like '/me/playlists'."""
    url = f"https://api.spotify.com/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"{method} {path} failed (HTTP {e.code}): {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the stored token instead of re-authorizing")
    args = ap.parse_args()
    if args.check:
        me = api("GET", "/me", get_access_token())
        print(f"ok — authorized as '{me.get('display_name') or me.get('id')}' "
              f"({me.get('product')})")
        return 0
    authorize()
    return 0


if __name__ == "__main__":
    sys.exit(main())
