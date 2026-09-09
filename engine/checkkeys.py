"""Verify configured API keys without ever printing their values.

    python3 -m engine.checkkeys

Reports presence + a live round-trip per credential. Deliberately does NOT use
engine.lib.http: that layer caches to disk, and credential checks should leave
no cached artifact behind.
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from engine.lib.config import load_config

UA = "discovery-dashboard/0.1 (personal project)"


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _fingerprint(secret):
    """Enough to confirm which key is loaded, never enough to reconstruct it."""
    return f"{len(secret)} chars, ends {secret[-4:]}" if len(secret) >= 8 else "too short"


def check_lastfm(key):
    q = urllib.parse.urlencode({
        "method": "artist.getsimilar", "artist": "Khruangbin",
        "api_key": key, "format": "json", "limit": 3})
    try:
        data = _get(f"https://ws.audioscrobbler.com/2.0/?{q}")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} — key rejected"
    except Exception as e:
        return False, f"unreachable: {e}"
    if "error" in data:
        return False, f"API error {data.get('error')}: {data.get('message')}"
    similar = (data.get("similarartists") or {}).get("artist") or []
    names = ", ".join(a.get("name", "?") for a in similar[:3])
    return True, f"live — Khruangbin similar: {names}"


def check_listenbrainz(token):
    try:
        data = _get("https://api.listenbrainz.org/1/validate-token?"
                    + urllib.parse.urlencode({"token": token}))
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} — token rejected"
    except Exception as e:
        return False, f"unreachable: {e}"
    if not data.get("valid"):
        return False, data.get("message", "token reported invalid")
    return True, f"valid — user '{data.get('user_name')}'"


def main():
    cfg = load_config()
    checks = [
        ("LASTFM_API_KEY", check_lastfm,
         "widens candidate harvesting (similar-artist fan-out)"),
        ("LISTENBRAINZ_TOKEN", check_listenbrainz,
         "optional bonus tier; labs APIs work without it"),
    ]
    failed = False
    for name, fn, why in checks:
        val = (cfg.get(name) or "").strip()
        if not val:
            print(f"  {name:<20} absent — {why}")
            continue
        ok, detail = fn(val)
        mark = "ok " if ok else "FAIL"
        print(f"  {name:<20} {mark} [{_fingerprint(val)}] {detail}")
        if not ok:
            failed = True
    # ANTHROPIC_API_KEY is declared but nothing in the engine calls Anthropic
    # yet. Prose reaches an issue one of two ways today: a copy file written
    # outside the engine (whoever writes it — an agent session, a person),
    # or the receipt-joined template. Both are gated by the same validator.
    # The key is reserved for a third route, a bring-your-own-key writer that
    # emits the same copy file; until that exists, say so rather than imply a
    # mode that does not.
    if (cfg.get("ANTHROPIC_API_KEY") or "").strip():
        print("  ANTHROPIC_API_KEY    present — reserved; no engine code calls it yet")
    else:
        print("  ANTHROPIC_API_KEY    absent — prose comes from a copy file "
              "or the template")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
