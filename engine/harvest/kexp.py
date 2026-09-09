"""Harvest KEXP shows for the Mixes module.

KEXP runs a real public API (api.kexp.org, keyless — verified live
2026-08-28): /v2/shows is the broadcast log (program name, tags, hosts,
start time) and /v2/plays?show=<id> is the show's complete setlist. That
tracklist is what lets a KEXP hour be overlap-scored against the local
history exactly like an NTS episode.

Method: page recent shows (last DAYS days), map program tags to clusters,
pull plays for the best-tagged shows, score = (top-3 known-artist
affinities) x novelty bell peaking at 70% new — the same formula as NTS,
so candidates from both stations compete fairly in one pool.

Output: out/kexp-harvest.json, same candidate shape as nts.py plus
station: "KEXP". Selection happens in engine/select/phase2.py.

Run:  PYTHONPATH=<root> python3 -m engine.harvest.kexp
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..lib.config import load_config
from ..lib.http import get_json
from ..lib.history import artist_played
from ..lib.normalize import norm_artist
from .nts import HOURS_SATURATION, _affinity_proxy, _split_artists

API = "https://api.kexp.org/v2"
# NOTE: /v2/plays silently IGNORES a ?show= filter (verified live: asking
# for one show returns another's plays), so a show's setlist is fetched by
# its airdate window instead: [its start, the next show's start).
RATE = {"rate_key": "kexp", "min_interval": 0.6}

DAYS = 7                # how far back the broadcast log is read
MAX_SHOWS = 14          # shows to pull full setlists for
MIN_TRACKS = 12

TAG_CLUSTERS = {
    "hip-hop": "underground-rap", "rap": "underground-rap",
    "electronic": "club-continuum", "dance": "club-continuum", "dj": "club-continuum",
    "world": "cosmic-groove", "global": "cosmic-groove", "latin": "cosmic-groove",
    "soul": "cosmic-groove", "funk": "cosmic-groove",
    "jazz": "jazz-bridge",
    "punk": "punk-turn", "garage rock": "punk-turn",
    "roots": "dad-rock", "country": "dad-rock", "blues": "dad-rock", "rock": "dad-rock",
    "ambient": "the-mist",
    "experimental": "beats-idm", "eclectic": "beats-idm",
}


def _cluster_for(tags):
    hits = {}
    for t in (tags or "").lower().split(","):
        t = t.strip()
        for needle, cid in TAG_CLUSTERS.items():
            if needle in t:
                hits[cid] = hits.get(cid, 0) + 1
    return max(hits, key=hits.get) if hits else None, sum(hits.values())


def _recent_shows():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
    out, offset = [], 0
    while True:
        d = get_json(f"{API}/shows/?limit=20&offset={offset}", ttl_days=1, **RATE)
        rs = d.get("results") or []
        if not rs:
            return out
        for s in rs:
            if (s.get("start_time") or "") < cutoff:
                return out
            out.append(s)
        offset += len(rs)


def main():
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])

    model = {}
    mp = out_dir / "taste-model.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        for c in m.get("clusters", []):
            for e in c.get("members", []):
                k = norm_artist(e["artist"])
                if e["affinity"] > model.get(k, 0):
                    model[k] = e["affinity"]

    served_urls = set()
    sp = Path(cfg["SERVED_PATH"])
    if sp.exists():
        for it in json.loads(sp.read_text()).get("items", []):
            if str(it.get("context", "")).endswith("the_mix") and it.get("uri"):
                served_urls.add(str(it["uri"]).split("?")[0])

    shows = _recent_shows()
    print(f"KEXP shows in the last {DAYS} days: {len(shows)}")
    # newest first: each show ends where the previous list entry begins
    end_by_id = {}
    prev_start = datetime.now(timezone.utc).isoformat()
    for sh in shows:
        end_by_id[sh["id"]] = prev_start
        prev_start = sh.get("start_time") or prev_start
    tagged, seen_programs = [], set()
    for s in shows:                        # newest episode per program only
        cid, strength = _cluster_for(s.get("program_tags"))
        if not cid or s.get("program") in seen_programs:
            continue
        seen_programs.add(s.get("program"))
        tagged.append((strength, cid, s))
    tagged.sort(key=lambda t: -t[0])

    candidates = []
    for strength, cid, s in tagged[:MAX_SHOWS]:
        st = s.get("start_time") or ""
        date = st[:10]
        try:
            y, mo, dy = date.split("-")
            url = f"https://www.kexp.org/playlist/{int(y)}/{int(mo)}/{int(dy)}/#show-{s['id']}"
        except ValueError:
            continue
        if url.split("?")[0] in served_urls:
            continue
        import urllib.parse as _u
        window = (f"airdate_after={_u.quote(st, safe='')}"
                  f"&airdate_before={_u.quote(end_by_id.get(s['id'], ''), safe='')}")
        d = get_json(f"{API}/plays/?{window}&limit=200", ttl_days=6, **RATE)
        tracks = [t for t in d.get("results") or []
                  if t.get("play_type") == "trackplay" and t.get("show") == s["id"]]
        if len(tracks) < MIN_TRACKS:
            continue
        known, known_tracks = {}, 0
        for t in tracks:
            raw = (t.get("artist") or "").strip()
            if not raw:
                continue
            hit = None
            for cand in [raw] + _split_artists(raw):
                row = artist_played(cand)
                if row:
                    hit = row
                    break
            if hit:
                known_tracks += 1
                k = norm_artist(hit["artist"])
                if k not in known:
                    known[k] = {
                        "artist": hit["artist"],
                        "plays": int(float(hit["plays"])),
                        "hours": float(hit["hours"]),
                        "skip_rate": float(hit["skip_rate"]),
                        "affinity": round(_affinity_proxy(
                            model.get(k), float(hit["hours"])), 3),
                    }
        total = len(tracks)
        new_tracks = total - known_tracks
        nr = new_tracks / total
        bell = max(0.1, 1 - abs(nr - 0.7) / 0.7)
        anchor = sum(sorted((k["affinity"] for k in known.values()), reverse=True)[:3])
        hosts = ", ".join(s.get("host_names") or [])
        candidates.append({
            "cluster": cid, "tag_hits": strength,
            "show": s.get("program_name", "").strip(),
            "show_alias": f"kexp-{s.get('program')}",
            "episode": f"with {hosts}" if hosts else s.get("program_name", ""),
            "station": "KEXP",
            "date": date, "url": url, "audio_sources": [],
            "tracks_total": total,
            "known_track_count": known_tracks,
            "new_track_count": new_tracks,
            "known_artists": sorted(known.values(), key=lambda k: -k["affinity"])[:8],
            "score": round(anchor * bell, 4),
        })

    candidates.sort(key=lambda c: -c["score"])
    p = out_dir / "kexp-harvest.json"
    p.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meta": {"shows_seen": len(shows), "shows_polled": min(len(tagged), MAX_SHOWS),
                 "candidates": len(candidates)},
        "candidates": candidates,
    }, indent=1, ensure_ascii=False))
    print(f"wrote {p} — {len(candidates)} candidates")
    for c in candidates[:6]:
        print(f"  {c['score']:6.3f} [{c['cluster']:16}] {c['show']} — {c['date']} · "
              f"{c['tracks_total']} tracks, {c['known_track_count']} known")


if __name__ == "__main__":
    main()
