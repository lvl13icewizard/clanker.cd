"""Project configuration. Reads .env at the project root; real env vars win.

Only SPOTIFY_CLEAN_DIR is required. Everything else is optional and features
degrade gracefully when a path/key is absent (adapters must check and skip).
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_KEYS = [
    "SPOTIFY_CLEAN_DIR",
    "PLAYLIST_JSON",
    "LIBRARY_JSON",
    "PITCHFORK_SCRAPED_DB",
    "PITCHFORK_KAGGLE_DB",
    "FANTANO_DB",
    "VOL1_URIS",
    "LASTFM_API_KEY",
    "LISTENBRAINZ_TOKEN",
    "LISTENBRAINZ_USER",
    "PLAYLIST_MD",
    "ANTHROPIC_API_KEY",
]


def load_config():
    cfg = {}
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    for k in _KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    cfg = {k: v for k, v in cfg.items() if v}
    if "SPOTIFY_CLEAN_DIR" not in cfg:
        raise SystemExit("SPOTIFY_CLEAN_DIR missing — copy .env.example to .env")
    cfg["CACHE_DIR"] = str(PROJECT_ROOT / "cache")
    # Overridable so tests can point the fresh-listens overlay elsewhere.
    cfg["OUT_DIR"] = os.environ.get("OUT_DIR") or str(PROJECT_ROOT / "out")
    cfg["ISSUES_DIR"] = str(PROJECT_ROOT / "issues")
    cfg["SERVED_PATH"] = str(PROJECT_ROOT / "served" / "served.json")
    cfg["SITE_ISSUES_DIR"] = str(PROJECT_ROOT / "site" / "public" / "issues")
    for d in ("CACHE_DIR", "OUT_DIR", "ISSUES_DIR", "SITE_ISSUES_DIR"):
        Path(cfg[d]).mkdir(parents=True, exist_ok=True)
    Path(cfg["SERVED_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    return cfg
