"""Fresh listens: everything played since the history export, from ListenBrainz.

The clean history (plays.csv and its aggregates) is a periodic export, so it
lags by weeks. Until now the model used the export's last event as its
clock, the novelty check saw only the export, and ListenBrainz was fetched
for grading alone (audit F15): someone discovered on their own after the
export could still be offered as new, and July's "recent" listening drove
September's seeds.

This module keeps out/fresh-listens.json, an overlay of listens dated after
the export's last event:

  export_cutoff    the export's last play timestamp the overlay was built
                   against. An overlay built for a different export is
                   stale and is ignored by every reader; the next ingest
                   starts over from the new tail.
  watermark        the newest listen fetched so far; ingest resumes here.
  listens          [{ts, epoch, artist, title, release, artists?}],
                   deduplicated on (epoch, artist, title), oldest first.
                   `artists` carries the parts of a joined credit.

Readers (engine.lib.history) merge it into the artist and track tables:
plays and last-played dates move, hours do not (ListenBrainz records no
duration; nothing is invented). The model reports the export cutoff, the
fresh cutoff and the reference date it used (`global`).

Run:  PYTHONPATH=<root> python3 -m engine.model.fresh_listens
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..lib import history
from ..lib.config import load_config
from ..lib.normalize import norm_artist, norm_title

FILE = history.FRESH_FILE


def path(cfg=None):
    return Path((cfg or load_config())["OUT_DIR"]) / FILE


def load(cfg=None):
    p = path(cfg)
    return json.loads(p.read_text()) if p.exists() else None


def _epoch(ts):
    """'2015-04-23T03:56:05Z' -> unix seconds (UTC)."""
    return int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())


def _iso(epoch):
    return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(listen):
    """One overlay row. ListenBrainz joins a multi-artist credit into one
    artist_name ("Westside Gunn, Boldy James") and lists the parts under
    additional_info.artist_names; the parts are kept so each credited
    artist counts as played, the way the export names them."""
    md = listen.get("track_metadata") or {}
    ep = int(listen.get("listened_at") or 0)
    names = (md.get("additional_info") or {}).get("artist_names")
    names = [n for n in (names or []) if isinstance(n, str) and n.strip()]
    row = {"ts": _iso(ep), "epoch": ep, "artist": md.get("artist_name"),
           "title": md.get("track_name"), "release": md.get("release_name")}
    if len(names) > 1:
        row["artists"] = names
    return row


def ingest(user=None, fetch=None, cfg=None, now=None):
    """Fetch listens newer than max(export tail, watermark) and merge them
    into the overlay. Returns a summary dict; never raises on a missing
    user (the overlay is optional)."""
    cfg = cfg or load_config()
    user = user or cfg.get("LISTENBRAINZ_USER")
    if not user:
        return {"status": "skipped: no LISTENBRAINZ_USER", "listens": 0}
    export_tail = history.tail_last_play_ts()
    if not export_tail:
        return {"status": "skipped: no play history export", "listens": 0}
    export_epoch = _epoch(export_tail)

    cur = load(cfg) or {"listens": []}
    if cur.get("export_cutoff") != export_tail:
        cur = {"listens": []}   # the export moved on; start from its new tail
    since = max(export_epoch, int(cur.get("watermark_epoch") or 0))

    if fetch is None:
        from ..ledger.build_ledger import fetch_listens as fetch
    raw = fetch(user, since)
    rows = [_row(l) for l in raw]
    rows = [r for r in rows if r["artist"] and r["title"] and r["epoch"] > export_epoch]
    seen = {(r["epoch"], norm_artist(r["artist"]), norm_title(r["title"]))
            for r in cur["listens"]}
    new = []
    for r in rows:
        k = (r["epoch"], norm_artist(r["artist"]), norm_title(r["title"]))
        if k in seen:
            continue
        seen.add(k)
        new.append(r)
    listens = sorted(cur["listens"] + new, key=lambda r: r["epoch"])
    wm = max([r["epoch"] for r in listens] + [since])
    doc = {
        "user": user, "source": "listenbrainz",
        "export_cutoff": export_tail,
        "watermark_epoch": wm, "watermark": _iso(wm),
        "fetched_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "listens": listens,
    }
    p = path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    history.reset()
    return {"status": "ok", "new": len(new), "listens": len(listens),
            "export_cutoff": export_tail, "watermark": doc["watermark"]}


def recent_track_pairs(days, now=None, doc=None):
    """(norm artist, norm title) pairs played in the last `days` days,
    from the overlay only (the export cannot be that recent)."""
    doc = doc if doc is not None else history.fresh_overlay()
    if not doc:
        return set()
    cutoff = int(((now or datetime.now(timezone.utc)) - timedelta(days=days)).timestamp())
    return {(norm_artist(r["artist"] or ""), norm_title(r["title"] or ""))
            for r in doc.get("listens") or [] if int(r.get("epoch") or 0) >= cutoff}


def main():
    s = ingest()
    if s["status"] != "ok":
        print(f"fresh listens: {s['status']}")
        return
    print(f"fresh listens: +{s['new']} -> {s['listens']} since export "
          f"{s['export_cutoff'][:10]} (watermark {s['watermark']})")


if __name__ == "__main__":
    main()
