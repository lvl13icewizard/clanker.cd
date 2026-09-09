"""Rank verified candidates into shortlists for issue N (NOT final picks).

Reads out/candidates-verified.json (VERIFY), out/taste-model.json (MODEL) and
out/revival-pools.json (MODEL); writes out/selection-proposal.json with four
ranked shortlists per CONTRACTS.md: front_to_back, singles_rack, revival_desk,
new_this_week. Curation happens outside the pipeline.

Eligibility: only verdict == "novel" candidates that are NOT served_before —
except new_this_week, where relationship=played releases are exempt from the
novelty requirement (adjacent releases still need verdict novel).

Scoring (documented factors, all multiplicative):
  score = affinity_factor * agreement_factor * quality_factor * state_factor
          * relation_factor
    affinity_factor  = 0.4 + 0.6 * A, where A in [0,1] is the best available
                       model affinity: the candidate artist's own cluster-member
                       affinity, else the `via` seed artist's, else the hinted
                       cluster's strength (mean of its top-10 member
                       affinities), else 0.5 when no signal / no model.
    agreement_factor = 1 + 0.25 * (independent evidence FAMILIES - 1)
                       + 0.05 * min(2, distinct seed artists - 1)
                       A family is a provider that gathers its own evidence:
                       the same Pitchfork review arriving from the local
                       corpus and from the RSS feed is one family, not two.
    relation_factor  = 0.85 + 0.15 * strength, where strength in (0,1] is
                       the strongest retained edge (provider-normalized
                       similarity from the harvest); 1.0 when no edge carries
                       a strength (album candidates, older harvests)
    quality_factor   = 0.7 + 0.06 * p4k_score (+0.15 if best_new_music) when a
                       Pitchfork record is present, else 1.0
    state_factor     = rising 1.15, active 1.05, dormant 0.9, burned 0.7,
                       unknown 1.0
Deterministic: ties are broken by random values seeded with the issue number
(random.seed(issue_n)), assigned in a stable candidate order — same issue
number, same output bytes.

Singles Rack leads merge every retained edge across sources; `via` and the
lane come from the strongest edge, not from whichever provider ran first.

Revival Desk pools are filtered against the served ledger (a pair offered by
the desk within REVIVAL_COOLDOWN_ISSUES issues sits out) and against recent
actual plays (a track the reader played in the last REVIVAL_RECENT_PLAY_DAYS
days is not a revival). Both counts land in meta.notes.

Degradation (never fabricate): a missing taste model or revival pools file
empties/neutralizes the affected parts and is recorded in meta.notes.

Run:  python3 -m engine.select.select_issue --n 1 [--candidates PATH]
      [--model PATH] [--pools PATH] [--out PATH]
"""

import argparse
import json
import re
import random
from datetime import datetime, timezone
from pathlib import Path

from ..lib.config import load_config
from ..lib.normalize import norm_artist, norm_title
from ..model import fresh_listens
from ..verify import served as served_mod
from ..verify import served_policy

STATE_FACTOR = {"rising": 1.15, "active": 1.05, "dormant": 0.9, "burned": 0.7}

# Sources that are really the same evidence gathered twice count once.
FAMILY = {
    "pitchfork_catalog": "pitchfork", "pitchfork_rss": "pitchfork",
    "bandcamp_daily": "bandcamp",
    "lb_labs": "listenbrainz", "lastfm_similar": "lastfm",
    "deezer_related": "deezer",
    "label_roster": "labels", "label_release": "labels",
}
REVIVAL_COOLDOWN_ISSUES = 6
REVIVAL_RECENT_PLAY_DAYS = 45


def families(sources):
    """Independent evidence families among a set of source names."""
    return {FAMILY.get(s, s) for s in sources if s}


def _load_json(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


class Model:
    """Affinity/cluster lookups over out/taste-model.json (tolerates None)."""

    def __init__(self, model):
        self.present = model is not None
        self.artist_aff = {}      # norm artist -> best member affinity
        self.artist_cluster = {}  # norm artist -> cluster id of that best entry
        self.cluster_strength = {}
        self.cluster_state = {}
        self.artist_hours = {}
        max_hours = 0.0
        if model:
            for cl in model.get("clusters", []):
                cid = cl.get("id")
                self.cluster_state[cid] = cl.get("state")
                affs = []
                for m in cl.get("members", []):
                    a = float(m.get("affinity") or 0.0)
                    affs.append(a)
                    na = norm_artist(m.get("artist", ""))
                    if a >= self.artist_aff.get(na, -1.0):
                        self.artist_aff[na] = a
                        self.artist_cluster[na] = cid
                top = sorted(affs, reverse=True)[:10]
                self.cluster_strength[cid] = sum(top) / len(top) if top else 0.0
            for na, row in (model.get("artists_index") or {}).items():
                h = float(row.get("hours") or 0.0)
                self.artist_hours[na] = h
                max_hours = max(max_hours, h)
        self._max_hours = max_hours or 1.0

    def affinity(self, artist=None, via=None, cluster=None):
        """Best available affinity signal in [0,1]; 0.5 when nothing known."""
        for name in (artist, via):
            if name and norm_artist(name) in self.artist_aff:
                return self.artist_aff[norm_artist(name)]
        if cluster and cluster in self.cluster_strength:
            return self.cluster_strength[cluster]
        for name in (artist, via):  # hours fallback for indexed artists
            if name and norm_artist(name) in self.artist_hours:
                return min(1.0, self.artist_hours[norm_artist(name)] / self._max_hours)
        return 0.5

    def cluster_for(self, cand):
        if cand.get("cluster_hint"):
            return cand["cluster_hint"]
        via = cand.get("via")
        if via and norm_artist(via) in self.artist_cluster:
            return self.artist_cluster[norm_artist(via)]
        return None

    def state_factor(self, cluster):
        return STATE_FACTOR.get(self.cluster_state.get(cluster), 1.0)


def _eligible(cand):
    """Novel, not served before, and past the artist-level repeat guard.

    The guard is applied asymmetrically on purpose:

      blocked  — the artist has been played. Never eligible anywhere here;
                 offering a played artist as a discovery is the one thing
                 this module exists to prevent.
      cooldown — offered before, never played. Blocked only for title-less
                 leads (the Singles Rack), where there is no track to
                 distinguish this offer from the last one. A candidate that
                 names a title is a different record by that artist, which
                 is the deep-cut case CONTRACTS.md's "different track by a
                 served artist" carve-out is for, so it passes.
    """
    v = cand.get("verification", {})
    if v.get("verdict") != "novel" or v.get("served_before"):
        return False
    repeat = v.get("artist_repeat") or {}
    if repeat.get("state") == "blocked":
        return False
    if repeat.get("state") == "cooldown" and not cand.get("title"):
        return False
    return True


def _quality_factor(p4k):
    if not p4k:
        return 1.0, None
    score = p4k.get("score")
    f = 0.7 + 0.06 * float(score) if score is not None else 1.0
    if p4k.get("bnm"):
        f += 0.15
    return f, score


def _score(model, cand, cluster, sources, p4k, strength=None, seeds=1):
    a = model.affinity(cand.get("artist"), cand.get("via"), cluster)
    qf, p4k_score = _quality_factor(p4k)
    sf = model.state_factor(cluster)
    fam = families(sources)
    agree = 1 + 0.25 * (max(1, len(fam)) - 1) + 0.05 * min(2, max(1, seeds) - 1)
    rel = 0.85 + 0.15 * float(strength) if strength is not None else 1.0
    score = (0.4 + 0.6 * a) * agree * qf * sf * rel
    basis = [f"aff {a:.2f}"]
    if cand.get("via"):
        basis[0] += f" (via {cand['via']})"
    if strength is not None:
        basis.append(f"rel {float(strength):.2f}")
    if len(fam) > 1:
        basis.append(f"{len(fam)} sources agree")
    if seeds > 1:
        basis.append(f"{seeds} seeds")
    if p4k:
        basis.append(
            f"p4k {p4k_score}{' BNM' if p4k.get('bnm') else ''}"
            if p4k_score is not None else "p4k reviewed"
        )
    if cluster:
        st = model.cluster_state.get(cluster)
        basis.append(f"cluster {cluster}" + (f" ({st})" if st else ""))
    return round(score, 4), "; ".join(basis)


def merge_leads(cands):
    """Group artist-level leads on the normalized artist, keeping every
    edge. Returns {norm: {cand, sources, edges}} where cand carries via,
    cluster_hint and strength from the STRONGEST edge across all sources."""
    by_artist = {}
    for c in cands:
        na = norm_artist(c.get("artist") or "")
        g = by_artist.setdefault(na, {"cand": dict(c), "sources": set(), "edges": [],
                                      "members": []})
        g["members"].append(c)
        g["sources"].add(c.get("source"))
        edges = c.get("edges")
        if not edges and c.get("via"):
            edges = [{"seed": c["via"], "cluster": c.get("cluster_hint"),
                      "rank": 0, "strength": c.get("strength")}]
        for e in edges or []:
            e = dict(e, source=c.get("source"))
            if c.get("relation") == "label" and not e.get("kind"):
                e["kind"] = "label"
            g["edges"].append(e)
    for g in by_artist.values():
        scored = [e for e in g["edges"] if e.get("strength") is not None]
        if scored:
            best = max(scored, key=lambda e: (e["strength"], -(e.get("rank") or 0)))
            g["cand"]["via"] = best.get("seed")
            g["cand"]["cluster_hint"] = best.get("cluster") or g["cand"].get("cluster_hint")
            g["cand"]["strength"] = best["strength"]
            # The card explains the STRONGEST edge, so the relation must
            # follow it: a label lead whose best edge is a similarity seed
            # is introduced by that artist, not "by the label <artist>".
            if best.get("kind") == "label":
                g["cand"]["relation"] = "label"
                g["cand"]["label"] = next(
                    (c.get("label") for c in g["members"]
                     if c.get("relation") == "label" and c.get("via") == best.get("seed")),
                    g["cand"].get("label"))
            else:
                g["cand"]["relation"] = None
                g["cand"]["label"] = None
        else:
            g["cand"]["strength"] = None
        g["seeds"] = len({e.get("seed") for e in g["edges"] if e.get("seed")}) or 1
    return by_artist


def _merge_albums(cands):
    """Group album candidates on (norm artist, norm title); merge sources/p4k."""
    merged = {}
    for c in cands:
        key = (norm_artist(c.get("artist") or ""), norm_title(c.get("title") or ""))
        g = merged.setdefault(key, {"cand": c, "sources": set(), "p4k": None})
        g["sources"].add(c.get("source"))
        p4k = c.get("p4k")
        if p4k and (
            g["p4k"] is None
            or (p4k.get("score") or 0) > (g["p4k"].get("score") or 0)
        ):
            g["p4k"] = p4k
    return merged


def build_proposal(issue_n, verified, model, pools, notes,
                   served_revival=None, recent_plays=None):
    rnd = random.Random(issue_n)

    def ranked(items):
        # items: list of (sort_name, dict). Stable order first, then seeded
        # tie-break values, then sort by score.
        items = sorted(items, key=lambda x: x[0])
        keyed = [(d, rnd.random()) for _, d in items]
        return [d for d, tb in sorted(keyed, key=lambda x: (-x[0]["score"], x[1]))]

    # ---- front_to_back: novel albums (catalog) + novel album-type releases.
    ftb = []
    albums = [c for c in verified.get("album_candidates", []) if _eligible(c)]
    for (na, nt), g in _merge_albums(albums).items():
        c = g["cand"]
        cluster = model.cluster_for(c)
        score, basis = _score(model, c, cluster, g["sources"], g["p4k"])
        ftb.append((na + "|" + nt, {
            "artist": c.get("artist"), "title": c.get("title"),
            "year": c.get("year"), "pool": "catalog", "cluster": cluster,
            "score": score, "p4k": g["p4k"], "basis": basis,
        }))
    for c in verified.get("new_releases", []):
        if c.get("release_type") == "album" and _eligible(c):
            cluster = model.cluster_for(c)
            score, basis = _score(model, c, cluster, {c.get("source", "mb")}, None)
            year = None
            if c.get("release_date"):
                year = int(str(c["release_date"])[:4])
            ftb.append((norm_artist(c.get("artist") or ""), {
                "artist": c.get("artist"), "title": c.get("title"),
                "year": year, "pool": "new_release", "cluster": cluster,
                "score": score, "p4k": None,
                "basis": basis + "; new release",
            }))
    front_to_back = ranked(ftb)[:10]

    # ---- singles_rack: novel artist-level leads grouped by cluster.
    by_artist = merge_leads(
        c for c in verified.get("track_candidates", []) if _eligible(c))
    rack = {}
    for na, g in sorted(by_artist.items()):
        c = g["cand"]
        cluster = model.cluster_for(c) or "unclustered"
        score, basis = _score(model, c, None if cluster == "unclustered" else cluster,
                              g["sources"], None, strength=c.get("strength"),
                              seeds=g["seeds"])
        rack.setdefault(cluster, []).append((na, {
            "artist": c.get("artist"),
            "source": "+".join(sorted(s for s in g["sources"] if s)),
            "via": c.get("via"),
            "relation": c.get("relation"),
            "label": c.get("label"),
            "strength": c.get("strength"),
            "seeds": g["seeds"],
            "score": score,
            "basis": basis,
        }))
    singles_rack = {cid: ranked(items)[:10] for cid, items in sorted(rack.items())}

    # ---- revival_desk: MODEL's pools (already affinity-sorted), minus what
    # the desk offered recently and what the reader just played on their own.
    franchises = ["barely_played", "fade_outs", "time_capsule"]
    sat_out = played = 0

    def fresh_pool(entries):
        nonlocal sat_out, played
        out = []
        for e in entries or []:
            key = (norm_artist(e.get("artist") or ""), norm_title(e.get("track") or ""))
            if key in (served_revival or set()):
                sat_out += 1
                continue
            if key in (recent_plays or set()):
                played += 1
                continue
            out.append(e)
        return out

    revival = {
        "franchise_suggestion": franchises[(issue_n - 1) % len(franchises)],
        "barely_played": fresh_pool((pools or {}).get("barely_played"))[:12],
        "fade_outs": fresh_pool((pools or {}).get("fade_outs"))[:10],
        "time_capsule": fresh_pool((pools or {}).get("time_capsule"))[:12],
    }
    if sat_out:
        notes.append(f"revival_desk: {sat_out} pool entries sit out (offered within "
                     f"the last {REVIVAL_COOLDOWN_ISSUES} issues)")
    if played:
        notes.append(f"revival_desk: {played} pool entries skipped (played in the "
                     f"last {REVIVAL_RECENT_PLAY_DAYS} days)")

    # ---- new_this_week: only the DELTA — releases dated after the previous
    # issue went out (future dates ride along as upcoming). The full shelf
    # lives on the site's release calendar; repeating it weekly went stale.
    prev_date = None
    idir = Path(load_config()["ISSUES_DIR"])
    for ip in sorted(idir.glob("issue-*.json")):
        m2 = re.search(r"issue-(\d+)\.json$", ip.name)
        if not m2 or int(m2.group(1)) >= issue_n:
            continue
        try:
            d0 = json.loads(ip.read_text()).get("date") or ""
        except Exception:
            continue
        if not prev_date or d0 > prev_date:
            prev_date = d0
    ntw, seen_rel = [], set()
    for c in verified.get("new_releases", []):
        if prev_date and not ((c.get("release_date") or "") > prev_date):
            continue
        # The same record can arrive from the artist's own calendar and
        # from its label's; one entry, the first (artist route) wins.
        rk = (norm_artist(c.get("artist") or ""), norm_title(c.get("title") or ""))
        if rk in seen_rel:
            continue
        seen_rel.add(rk)
        if c.get("relationship") == "played" or _eligible(c):
            a = model.affinity(c.get("artist"), c.get("via"), model.cluster_for(c))
            ntw.append((norm_artist(c.get("artist") or ""),
                        {**c, "affinity": round(a, 4)}))
    ntw = sorted(ntw, key=lambda x: x[0])
    keyed = [(d, rnd.random()) for _, d in ntw]
    new_this_week = [d for d, tb in
                     sorted(keyed, key=lambda x: (-x[0]["affinity"], x[1]))][:10]

    return {
        "front_to_back": front_to_back,
        "singles_rack": singles_rack,
        "revival_desk": revival,
        "new_this_week": new_this_week,
        "meta": {
            "issue": issue_n,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": notes,
        },
    }


def main(argv=None):
    cfg = load_config()
    out_dir = Path(cfg["OUT_DIR"])
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=1, help="issue number (seeds ties)")
    ap.add_argument("--candidates", default=str(out_dir / "candidates-verified.json"))
    ap.add_argument("--model", default=str(out_dir / "taste-model.json"))
    ap.add_argument("--pools", default=str(out_dir / "revival-pools.json"))
    ap.add_argument("--out", default=str(out_dir / "selection-proposal.json"))
    args = ap.parse_args(argv)

    verified = _load_json(args.candidates)
    if verified is None:
        raise SystemExit(
            f"select_issue: verified candidates not found: {args.candidates} — "
            "run engine.verify.zero_play first or pass --candidates"
        )
    notes = []
    model_raw = _load_json(args.model)
    if model_raw is None:
        notes.append(f"taste model missing ({args.model}); neutral affinity 0.5 "
                     "and no cluster states used")
    pools = _load_json(args.pools)
    if pools is None:
        notes.append(f"revival pools missing ({args.pools}); revival_desk empty")

    served_revival = served_policy.revival_pairs_recent(
        served_mod.load_or_build(), args.n, REVIVAL_COOLDOWN_ISSUES)
    recent_plays = fresh_listens.recent_track_pairs(REVIVAL_RECENT_PLAY_DAYS)
    proposal = build_proposal(args.n, verified, Model(model_raw), pools, notes,
                              served_revival=served_revival,
                              recent_plays=recent_plays)
    Path(args.out).write_text(json.dumps(proposal, indent=2, ensure_ascii=False))
    print(f"select_issue: issue {args.n} -> {args.out}")
    print(f"  front_to_back: {len(proposal['front_to_back'])}  "
          f"singles_rack clusters: {list(proposal['singles_rack'])}  "
          f"new_this_week: {len(proposal['new_this_week'])}")
    for n in notes:
        print(f"  note: {n}")


if __name__ == "__main__":
    main()
