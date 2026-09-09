"""Second-ring retrieval: neighbours of the newcomers.

The first ring asks the providers who sounds like the artists the reader
already plays. After eleven years that ring is nearly used up: in the last
full harvest 511 of 581 leads were already played and 41 artists were new.
Digging deeper into the same neighbourhoods returns more of the same played
names (Khruangbin's 11th to 40th Deezer neighbours: none new).

This stage takes the never-played, never-offered artists the first ring did
find, in strength order, and asks the same providers who sounds like THEM.
Their neighbourhoods are anchored to the reader's taste one hop out and are
far less picked over. Every edge it produces is marked ring 2 and its
strength is scaled by RING_DECAY, so a second-ring lead never outranks a
first-ring lead on relationship alone; the seed it came through is a
newcomer, so the selector's affinity for it falls back to the lane's
strength, which is the honest signal.

Second-ring leads are merged into the same track_candidates list: an artist
already reported by a provider in ring one keeps its entry and gains the
new edges (the contract's one-entry-per-source rule holds).
"""

from engine.harvest import deezer, lastfm, lb_labs, leads as L
from engine.lib.normalize import norm_artist
from engine.verify import served as served_mod
from engine.verify.repeat_guard import DISCOVERY_CONTEXTS, _context_kind

RING_SEEDS = 12         # newcomers promoted to seeds per provider
RING_DECAY = 0.6
SMOKE_SEEDS = 2

ADAPTERS = [
    ("lb_labs", lambda seeds: lb_labs.harvest(seeds=seeds)),
    ("deezer", lambda seeds: deezer.harvest(seeds=seeds)),
    ("lastfm", lambda seeds: lastfm.harvest(seeds=seeds)),
]


def _offered_artists(served=None):
    served = served if served is not None else served_mod.load_or_build()
    return {norm_artist(i.get("artist") or "") for i in served.get("items") or []
            if _context_kind(i.get("context")) in DISCOVERY_CONTEXTS}


def pick_seeds(track_candidates, n=RING_SEEDS, offered=None, is_novel=None):
    """Strongest first-ring newcomers: never played, never offered as a
    discovery, one entry per artist, strongest edge first."""
    is_novel = is_novel or L.is_novel
    offered = offered if offered is not None else _offered_artists()
    best = {}
    for c in track_candidates:
        if c.get("ring", 1) != 1:
            continue
        na = norm_artist(c.get("artist") or "")
        if not na or na in offered:
            continue
        st = float(c.get("strength") or 0.0)
        if na not in best or st > best[na]["strength"]:
            best[na] = {"artist": c["artist"], "cluster": c.get("cluster_hint"),
                        "anchor": c.get("via"), "strength": st,
                        "hours": 0.0, "affinity": 0.0}
    ranked = sorted(best.values(), key=lambda s: (-s["strength"], s["artist"]))
    out = []
    for s in ranked:
        if len(out) >= n:
            break
        if is_novel(s["artist"]):
            out.append(s)
    return out


def mark(cands, seeds):
    """Ring-2 stamp and decay, in place. `via` becomes 'Newcomer' and
    `anchor` records the first-ring seed the newcomer came through."""
    anchors = {norm_artist(s["artist"]): s.get("anchor") for s in seeds}
    for c in cands:
        c["ring"] = 2
        for e in c.get("edges") or []:
            e["ring"] = 2
            e["strength"] = round(float(e.get("strength") or 0.0) * RING_DECAY, 4)
            e["anchor"] = anchors.get(norm_artist(e.get("seed") or ""))
        if c.get("strength") is not None:
            c["strength"] = round(float(c["strength"]) * RING_DECAY, 4)
        c["anchor"] = anchors.get(norm_artist(c.get("via") or ""))
    return cands


def merge(existing, new):
    """Fold ring-2 candidates into the list: same artist + same source keeps
    the first-ring entry and gains the edges; otherwise append."""
    index = {(c.get("source"), norm_artist(c.get("artist") or "")): c
             for c in existing}
    added = merged = 0
    for c in new:
        k = (c.get("source"), norm_artist(c.get("artist") or ""))
        have = index.get(k)
        if have is None:
            existing.append(c)
            index[k] = c
            added += 1
            continue
        seen = {e.get("seed") for e in have.get("edges") or []}
        for e in c.get("edges") or []:
            if e.get("seed") not in seen:
                have.setdefault("edges", []).append(e)
        merged += 1
    return added, merged


def harvest(track_candidates, smoke=False, adapters=None, seeds=None):
    """Return (ring2_candidates, status, seeds_used). Does not mutate input."""
    adapters = adapters or ADAPTERS
    seeds = seeds if seeds is not None else pick_seeds(
        track_candidates, n=SMOKE_SEEDS if smoke else RING_SEEDS)
    if not seeds:
        return [], "skipped: no first-ring newcomers to expand", []
    out, parts = [], []
    for name, fn in adapters:
        try:
            payload, status = fn(seeds)
        except Exception as e:  # noqa: BLE001 — one provider never sinks the ring
            parts.append("%s error: %s" % (name, type(e).__name__))
            continue
        cands = mark(payload.get("track_candidates") or [], seeds)
        out.extend(cands)
        parts.append("%s %d" % (name, len(cands)))
    novel = sum(1 for c in out if L.is_novel(c.get("artist")))
    status = "ok: %d leads (%d novel) from %d newcomer seeds; %s" % (
        len(out), novel, len(seeds), ", ".join(parts))
    return out, status, seeds
