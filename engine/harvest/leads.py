"""Shared bookkeeping for the similarity adapters: retained edges and yield.

Leads
  Every adapter used to keep the FIRST seed that reached a candidate and
  throw the rest away, along with the provider's own similarity number. The
  ranker was then left with nothing to tell two candidates apart when they
  came through the same seed and source (audit F11: both scored 0.924).

  A Leads accumulator keeps one candidate per artist per source (the
  contract: "include a candidate artist once per source") but records every
  edge that reached it — seed, the seed's lane, the provider's rank and a
  strength in (0, 1] normalized within that provider's own response, so a
  Last.fm match, a ListenBrainz session score and a Deezer rank position are
  comparable before they are blended. `via` and `cluster_hint` come from the
  strongest edge, not the first one, so provider order no longer decides
  the explanation.

Yield
  What each seed query actually produced, in NOVEL leads: artists the play
  history has never seen. Adapters use it to decide when to page deeper
  (audit F10: 511 of 581 lead records in the saved run were already played)
  and report it per lane in their status line so a thin lane is visible in
  the harvest log instead of only in the rack.
"""

from collections import OrderedDict

from engine.lib import history
from engine.lib.normalize import norm_artist

# A seed whose first page yields fewer novel artists than this is queried
# deeper, up to DEEP_PER_SEED, before the adapter moves on.
NOVEL_FLOOR = 3
PER_SEED = 10
DEEP_PER_SEED = 30


def is_novel(name):
    """True when the play history (export plus fresh overlay) has no row."""
    return history.artist_played(name or "") is None


class Leads:
    def __init__(self, source):
        self.source = source
        self._by_artist = OrderedDict()   # norm artist -> candidate dict

    def add(self, name, seed, rank, strength):
        """Record one edge seed -> name. strength in (0, 1], 1 = strongest
        neighbour in that provider's response for that seed."""
        k = norm_artist(name or "")
        if not k:
            return
        edge = {"seed": seed.get("artist"), "cluster": seed.get("cluster"),
                "rank": int(rank), "strength": round(float(strength), 4)}
        c = self._by_artist.get(k)
        if c is None:
            c = self._by_artist[k] = {
                "artist": name, "title": None, "source": self.source,
                "via": None, "cluster_hint": None, "strength": 0.0,
                "edges": [],
            }
        if any(e["seed"] == edge["seed"] for e in c["edges"]):
            return  # same seed reported twice (a deeper page re-lists it)
        c["edges"].append(edge)
        best = max(c["edges"], key=lambda e: (e["strength"], -e["rank"]))
        c["via"] = best["seed"]
        c["cluster_hint"] = best["cluster"]
        c["strength"] = best["strength"]

    def alias(self, name, aliases):
        """Attach the other names an artist is known by (verification asks
        the history about each one)."""
        c = self._by_artist.get(norm_artist(name or ""))
        if c is not None and aliases:
            c["aliases"] = [a for a in aliases if a]

    def candidates(self):
        return list(self._by_artist.values())

    def __len__(self):
        return len(self._by_artist)


class Yield:
    def __init__(self):
        self.rows = []   # (seed, lane, leads, novel, deepened)

    def record(self, seed, names, deepened=False):
        novel = sum(1 for n in names if is_novel(n))
        self.rows.append((seed.get("artist"), seed.get("cluster") or "unclustered",
                          len(names), novel, bool(deepened)))
        return novel

    def by_lane(self):
        out = {}
        for _, lane, leads, novel, _ in self.rows:
            e = out.setdefault(lane, {"seeds": 0, "leads": 0, "novel": 0})
            e["seeds"] += 1
            e["leads"] += leads
            e["novel"] += novel
        return out

    def summary(self):
        leads = sum(r[2] for r in self.rows)
        novel = sum(r[3] for r in self.rows)
        deep = sum(1 for r in self.rows if r[4])
        s = "%d novel of %d" % (novel, leads)
        if deep:
            s += ", %d seeds deepened" % deep
        lanes = self.by_lane()
        if lanes:
            s += "; lanes " + " ".join(
                "%s %d/%d" % (lane, v["novel"], v["leads"])
                for lane, v in sorted(lanes.items()))
        return s


def strength_by_rank(rank, limit):
    """Rank-only providers (Deezer): position among `limit`, 1 = first."""
    limit = max(1, int(limit))
    return max(1, limit - int(rank)) / limit
