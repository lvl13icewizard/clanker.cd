"""Label leads: roster gaps and new releases on the labels the reader lives on.

Reads out/label-model.json (engine.model.build_label_model). Two outputs:

track_candidates (source "label_roster")
  For each expanded label, every roster artist the play history has never
  seen. `via` is the label; the edge is kind "label" and its strength is
  the label's weight (hours relative to the reader's top label) shaped by
  how much of a career the artist has there (one 12" is weaker than five
  records) and whether they have released on it in the last DORMANT_YEARS.
  The card carries `relation: "label"` and a `label` block (hours, artists
  you play, the artist's releases there) so the writer can print a receipt
  that is true: "Ghostly International: 61.3 hours on your shelf".

new_releases (source "label_release")
  Releases on those labels dated within WINDOW_DAYS, via a MusicBrainz
  search on label id and date. `relationship` is "played" when the artist
  is in the history and "label" otherwise, so New This Week can carry a
  record from a label you live on by a name you have never played; the
  audit noted that adjacent new releases had no producer.

Rate: MusicBrainz 1.1 s (rate_key "musicbrainz"); one search per label.
"""

import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlencode

from engine.lib import history, http, names
from engine.lib.config import load_config
from engine.lib.normalize import norm_artist, norm_title

from engine.harvest.leads import is_novel as _is_novel
from engine.harvest.musicbrainz import MB_ROOT

SEED_COUNT = 25
WINDOW_DAYS = 45
DORMANT_YEARS = 10
CAREER_RELEASES = 5
MB_RATE = {"rate_key": "musicbrainz", "min_interval": 1.1}
_TYPE_MAP = {"album": "album", "ep": "ep", "single": "single"}


def load_model(cfg=None):
    p = Path((cfg or load_config())["OUT_DIR"]) / "label-model.json"
    return json.loads(p.read_text()) if p.exists() else None


def lane_of(label):
    lanes = label.get("lanes") or {}
    return max(lanes, key=lanes.get) if lanes else None


def roster_leads(labels, today=None, is_novel=None):
    """track_candidates from the labels' rosters; never-played artists only."""
    is_novel = is_novel or _is_novel
    today = today or dt.date.today()
    dormant = (today - dt.timedelta(days=365 * DORMANT_YEARS)).isoformat()
    max_h = max((float(L.get("hours") or 0) for L in labels), default=0.0) or 1.0
    out, seen = [], {}
    for L in labels:
        w = float(L.get("hours") or 0) / max_h
        lane = lane_of(L)
        info = {"name": L["name"], "hours": round(float(L.get("hours") or 0), 1),
                "artists": len(L.get("artists") or [])}
        for i, r in enumerate(L.get("roster") or []):
            name = r.get("artist")
            if not name or not is_novel(name):
                continue
            depth = min(1.0, (r.get("releases") or 1) / CAREER_RELEASES)
            recent = 1.0 if (r.get("last_date") or "") >= dormant else 0.6
            strength = round(w * (0.5 + 0.5 * depth) * recent, 4)
            edge = {"seed": L["name"], "cluster": lane, "rank": i,
                    "strength": strength, "kind": "label"}
            na = norm_artist(name)
            c = seen.get(na)
            if c is None:
                c = seen[na] = {
                    "artist": name, "title": None, "source": "label_roster",
                    "via": L["name"], "cluster_hint": lane, "strength": strength,
                    "relation": "label",
                    "label": dict(info, releases=r.get("releases") or 1),
                    "edges": [edge],
                }
                if r.get("aliases"):
                    c["aliases"] = list(r["aliases"])
                out.append(c)
                continue
            c["edges"].append(edge)
            if strength > c["strength"]:
                c.update(via=L["name"], cluster_hint=lane, strength=strength,
                         label=dict(info, releases=r.get("releases") or 1))
    return out


def _search_releases(label_mbid, since, until):
    q = urlencode({"query": f"laid:{label_mbid} AND date:[{since} TO {until}]",
                   "limit": 100, "fmt": "json"})
    data = http.get_json("%s/release/?%s" % (MB_ROOT, q), ttl_days=3, **MB_RATE)
    return data.get("releases") or []


def label_releases(labels, today=None, search=None, played=None):
    """new_releases on the labels within WINDOW_DAYS."""
    search = search or _search_releases
    played = played or (lambda name: history.artist_played(name) is not None)
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    until = (today + dt.timedelta(days=7)).isoformat()
    out, seen = [], set()
    for L in labels:
        if not L.get("mbid"):
            continue
        try:
            rels = search(L["mbid"], since, until)
        except Exception:
            continue
        for r in rels:
            rg = r.get("release-group") or {}
            ptype = (rg.get("primary-type") or "").lower()
            if ptype not in _TYPE_MAP or rg.get("secondary-types"):
                continue
            d = (r.get("date") or "")[:10]
            if len(d) != 10:
                continue
            credit = r.get("artist-credit") or []
            # The credited name first (Latin script, as printed on the
            # record, which is how the history knows it), the entity's
            # canonical name as fallback.
            artist = (credit[0].get("name") if credit else None) or \
                ((credit[0].get("artist") or {}).get("name") if credit else None)
            amb = ((credit[0].get("artist") or {}).get("id") if credit else None)
            als = names.aliases(amb, artist) if artist and not names.is_latin(artist) else None
            artist = names.latin_name(amb, artist) if artist else artist
            title = r.get("title")
            if not artist or not title or artist.lower() == "various artists":
                continue
            k = (norm_artist(artist), norm_title(title))
            if k in seen:
                continue
            seen.add(k)
            rel = {"artist": artist, "title": title, "release_date": d,
                   "release_type": _TYPE_MAP[ptype],
                   "relationship": "played" if played(artist) else "label",
                   "via": L["name"], "mbid": rg.get("id"),
                   "source": "label_release"}
            if als:
                rel["aliases"] = als
            out.append(rel)
    return sorted(out, key=lambda r: (r["release_date"], r["artist"]))


def harvest(limit=None, model=None, is_novel=None):
    """Return ({"track_candidates", "new_releases"}, status)."""
    model = model if model is not None else load_model()
    if not model:
        return {"track_candidates": [], "new_releases": []}, \
            "skipped: no label model (run engine.model.build_label_model)"
    labels = [L for L in model.get("labels") or [] if L.get("roster")]
    labels = labels[: (limit or SEED_COUNT)]
    cands = roster_leads(labels, is_novel=is_novel)
    rels = label_releases(labels)
    status = "ok: %d roster leads from %d labels, %d label releases" % (
        len(cands), len(labels), len(rels))
    return {"track_candidates": cands, "new_releases": rels}, status


if __name__ == "__main__":
    payload, status = harvest(limit=3)
    print(status)
    for c in payload["track_candidates"][:12]:
        print(" ", c["artist"], "(on %s, %.2f)" % (c["via"], c["strength"]))
    for r in payload["new_releases"][:8]:
        print(" ", r["release_date"], r["release_type"], "|", r["artist"], "—",
              r["title"], "(%s, %s)" % (r["via"], r["relationship"]))
