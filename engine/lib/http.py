"""Cached, rate-limited HTTP GETs. Every external request goes through here.

Disk cache: cache/<sha1(url)>.body + .meta (json). Rate limiting is per
rate_key (one key per API host), enforced as a minimum interval between calls.
"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import load_config

UA = "clanker.cd/0.1 (+https://clanker.cd)"

# Query params whose values are credentials. The cache key is a hash of the
# full URL (one-way, safe), but the .meta sidecar stores the URL in plaintext
# for debugging — so secrets are stripped from that copy. Without this, a
# Last.fm api_key ends up readable in cache/*.meta.
_SECRET_PARAMS = {"api_key", "apikey", "key", "token", "secret", "sk",
                  "access_token", "client_secret"}

_last_call = {}


def redact(url):
    """URL with any credential-bearing query values replaced."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.query:
        return url
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    safe = [(k, "REDACTED" if k.lower() in _SECRET_PARAMS else v)
            for k, v in pairs]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path,
         urllib.parse.urlencode(safe), parts.fragment))


def _cache_paths(url):
    cfg = load_config()
    h = hashlib.sha1(url.encode()).hexdigest()
    base = Path(cfg["CACHE_DIR"]) / h
    return base.with_suffix(".body"), base.with_suffix(".meta")


def get(url, rate_key="default", min_interval=1.1, ttl_days=7, headers=None,
        allow_stale=True):
    """Return response body as str, from cache when fresh.

    Network failure with a stale cache present returns the stale body when
    allow_stale (harvests should keep working offline). Raises on failure
    with no cache at all.
    """
    body_p, meta_p = _cache_paths(url)
    now = time.time()
    if body_p.exists() and meta_p.exists():
        meta = json.loads(meta_p.read_text())
        if now - meta["fetched_at"] < ttl_days * 86400:
            return body_p.read_text()
    wait = _last_call.get(rate_key, 0) + min_interval - now
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    body = None
    # 429/503 are how polite APIs say "slow down" — honor with backoff, twice.
    for attempt in range(3):
        _last_call[rate_key] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            if allow_stale and body_p.exists():
                return body_p.read_text()
            raise
        except (urllib.error.URLError, TimeoutError):
            if allow_stale and body_p.exists():
                return body_p.read_text()
            raise
    body_p.write_text(body)
    meta_p.write_text(json.dumps({"url": redact(url),
                                  "fetched_at": time.time()}))
    return body


def get_json(url, **kw):
    return json.loads(get(url, **kw))
