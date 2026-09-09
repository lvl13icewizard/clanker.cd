"""Seed-artist selection shared by every similarity adapter.

The adapters query their provider for neighbours of a list of seed artists
and take the first SEED_COUNT (25) of whatever this module returns, so the
ORDER of the list is the allocation. Audit F10: the old list was the top 120
by affinity, which made every adapter search the same small neighbourhood
issue after issue, and a fallback path filled the list alphabetically before
sorting it.

Allocation (interleaved, so the first 25 already carry the mix):

  enduring   highest affinity in the model. The core of the list, three
             seats per round.
  recent     played in the last RECENT_DAYS before the model's reference
             date and NOT in the enduring core (top ENDURING_CORE by
             affinity), by hours. Two seats per round. Recent interests
             reach the adapters before they have earned lifetime affinity;
             without the exclusion this pool is the enduring pool again.
  lanes      one seat per round for every cluster, best remaining member
             first, so no lane the reader actually lives in goes unsearched
             because another lane has more hours.
  unmapped   listening the clusters do not describe, by hours. One seat.
  requests   explicit requests are not wired yet; the seat is reserved.

Rotation: each pool keeps a small stable head (its strongest entries are
searched every issue) and rotates the rest by issue number, so the same
seed list does not come back every week. The next issue number is read
from ISSUES_DIR, exactly as weekly.sh derives it, so a harvest and the
press it feeds agree.

Fallback without a model: artists.csv by hours, sorted BEFORE truncation.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

from engine.lib import history
from engine.lib.config import load_config
from engine.lib.normalize import norm_artist

SEED_COUNT = 120
RECENT_DAYS = 180
ENDURING_CORE = 30
# Stable heads per pool; everything after rotates by issue.
HEAD = {"enduring": 6, "recent": 2, "lane": 1, "unmapped": 1}
ROTATE_STRIDE = 3
# Seats per round of the interleave.
SEATS = {"enduring": 3, "recent": 2, "lane": 1, "unmapped": 1}


def next_issue_number(issues_dir=None):
    d = Path(issues_dir or load_config()["ISSUES_DIR"])
    ns = [int(m.group(1)) for p in d.glob("issue-*.json")
          for m in [re.search(r"issue-(\d+)\.json$", p.name)] if m]
    return max(ns) + 1 if ns else 1


def _rows(model):
    """norm artist -> {artist, cluster, hours, affinity, last_played, clusters}"""
    rows = {}
    for cl in model.get("clusters", []) or []:
        for m in cl.get("members", []) or []:
            name = m.get("artist")
            k = norm_artist(name or "")
            if not k:
                continue
            aff = float(m.get("affinity") or 0)
            r = rows.get(k)
            if r is None or aff > r["affinity"]:
                rows[k] = {"artist": name, "cluster": cl.get("id"),
                           "hours": float(m.get("hours") or 0), "affinity": aff,
                           "last_played": str(m.get("last_played") or ""),
                           "clusters": (r["clusters"] if r else set())}
            rows[k]["clusters"].add(cl.get("id"))
    for k, row in (model.get("artists_index") or {}).items():
        r = rows.get(k)
        if r is None:
            rows[k] = {"artist": row.get("artist") or k,
                       "cluster": (row.get("clusters") or [None])[0],
                       "hours": float(row.get("hours") or 0), "affinity": 0.0,
                       "last_played": str(row.get("last_played") or ""),
                       "clusters": set(row.get("clusters") or [])}
        else:
            r["last_played"] = max(r["last_played"], str(row.get("last_played") or ""))
            r["clusters"].update(row.get("clusters") or [])
    return rows


def _ref_date(model):
    g = model.get("global") or {}
    for s in (g.get("reference_date"), (model.get("window") or {}).get("last_play")):
        try:
            return date.fromisoformat(str(s)[:10])
        except (TypeError, ValueError):
            continue
    return date.today()


def _pools(rows, ref_date):
    recent_cut = (ref_date - timedelta(days=RECENT_DAYS)).isoformat()
    by_aff = sorted(rows.values(),
                    key=lambda r: (-r["affinity"], -r["hours"], r["artist"]))
    enduring = [r for r in by_aff if r["affinity"] > 0] or by_aff
    core = {norm_artist(r["artist"]) for r in enduring[:ENDURING_CORE]}
    recent = sorted((r for r in rows.values()
                     if r["last_played"][:10] >= recent_cut
                     and norm_artist(r["artist"]) not in core),
                    key=lambda r: (-r["hours"], r["artist"]))
    lanes = {}
    for r in by_aff:
        if r["cluster"]:
            lanes.setdefault(r["cluster"], []).append(r)
    unmapped = sorted((r for r in rows.values() if not r["clusters"]),
                      key=lambda r: (-r["hours"], r["artist"]))
    return {"enduring": enduring, "recent": recent,
            "lanes": dict(sorted(lanes.items())), "unmapped": unmapped}


def rotate(pool, issue_n, head):
    """Keep the strongest `head` entries first; rotate the rest by issue."""
    pool = list(pool)
    stable, rest = pool[:head], pool[head:]
    if len(rest) > 1:
        off = ((max(1, int(issue_n)) - 1) * ROTATE_STRIDE) % len(rest)
        rest = rest[off:] + rest[:off]
    return stable + rest


def _seed(r):
    return {"artist": r["artist"], "cluster": r["cluster"],
            "hours": r["hours"], "affinity": r["affinity"]}


def select_seeds(model, n=SEED_COUNT, issue_n=1):
    """Interleaved, rotated seed list of up to n entries from a taste model."""
    rows = _rows(model or {})
    if not rows:
        return []
    pools = _pools(rows, _ref_date(model or {}))
    queues = [("enduring", rotate(pools["enduring"], issue_n, HEAD["enduring"]))]
    queues.append(("recent", rotate(pools["recent"], issue_n, HEAD["recent"])))
    for cid, members in pools["lanes"].items():
        queues.append(("lane", rotate(members, issue_n, HEAD["lane"])))
    queues.append(("unmapped", rotate(pools["unmapped"], issue_n, HEAD["unmapped"])))

    out, used = [], set()
    idx = [0] * len(queues)
    while len(out) < n:
        advanced = False
        for qi, (kind, q) in enumerate(queues):
            for _ in range(SEATS[kind]):
                while idx[qi] < len(q) and norm_artist(q[idx[qi]]["artist"]) in used:
                    idx[qi] += 1
                if idx[qi] >= len(q) or len(out) >= n:
                    break
                r = q[idx[qi]]
                idx[qi] += 1
                used.add(norm_artist(r["artist"]))
                out.append(_seed(r))
                advanced = True
        if not advanced:
            break
    return out


def _fallback(n):
    rows = sorted(history.load_artists().values(),
                  key=lambda r: (-float(r["hours"] or 0), r["artist"]))
    return [{"artist": r["artist"], "cluster": None,
             "hours": float(r["hours"] or 0), "affinity": 0.0}
            for r in rows[:n]]


def get_seed_artists(n=SEED_COUNT, issue_n=None, model=None):
    """[{artist, cluster, hours, affinity}], allocation order (see module doc)."""
    cfg = load_config()
    if issue_n is None:
        issue_n = next_issue_number(cfg["ISSUES_DIR"])
    if model is None:
        tm_path = Path(cfg["OUT_DIR"]) / "taste-model.json"
        model = json.loads(tm_path.read_text()) if tm_path.exists() else None
    seeds = select_seeds(model, n, issue_n) if model else []
    return seeds or _fallback(n)


if __name__ == "__main__":
    for i, s in enumerate(get_seed_artists()[:30], 1):
        print("%2d %-32s %-18s aff %.2f  %.1fh" % (
            i, s["artist"], s["cluster"] or "-", s["affinity"], s["hours"]))
