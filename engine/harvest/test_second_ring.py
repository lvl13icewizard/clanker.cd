"""Tests for second-ring retrieval and the supply gauge.

Run:  PYTHONPATH=<root> python3 -m engine.harvest.test_second_ring
"""

import unittest

from engine.harvest import second_ring as R
from engine.harvest import supply as S


def lead(artist, via, strength, source="lb_labs", cluster="lane-a", ring=1):
    return {"artist": artist, "title": None, "source": source, "via": via,
            "cluster_hint": cluster, "strength": strength, "ring": ring,
            "edges": [{"seed": via, "cluster": cluster, "rank": 0, "strength": strength}]}


def verified(artist, verdict="novel", cluster="lane-a", ring=1, served=False,
             repeat="clear"):
    return {"artist": artist, "title": None, "cluster_hint": cluster, "ring": ring,
            "verification": {"verdict": verdict, "served_before": served,
                             "artist_repeat": {"state": repeat}}}


NOVEL = {"newcomer a", "newcomer b", "newcomer c", "far out"}


def is_novel(name):
    return name.lower() in NOVEL


class TestPickSeeds(unittest.TestCase):
    def test_strongest_novel_unoffered_newcomers_first(self):
        tc = [lead("Newcomer A", "Khruangbin", 0.5),
              lead("Newcomer A", "Tycho", 0.9, source="deezer_related"),
              lead("Newcomer B", "Khruangbin", 0.7),
              lead("Old Hat", "Khruangbin", 1.0),           # played
              lead("Newcomer C", "Bonobo", 0.95),           # offered before
              lead("Ring Two", "Newcomer A", 0.99, ring=2)]  # never re-expanded
        seeds = R.pick_seeds(tc, n=5, offered={"newcomer c"}, is_novel=is_novel)
        self.assertEqual([s["artist"] for s in seeds], ["Newcomer A", "Newcomer B"])
        self.assertEqual(seeds[0]["strength"], 0.9)
        self.assertEqual(seeds[0]["anchor"], "Tycho")
        self.assertEqual(seeds[0]["cluster"], "lane-a")

    def test_cap(self):
        tc = [lead(f"Newcomer {x}", "K", 0.5) for x in "ABC"]
        self.assertEqual(len(R.pick_seeds(tc, n=2, offered=set(), is_novel=is_novel)), 2)


class TestMarkAndMerge(unittest.TestCase):
    def test_ring_two_is_stamped_decayed_and_anchored(self):
        seeds = [{"artist": "Newcomer A", "cluster": "lane-a", "anchor": "Tycho"}]
        cands = R.mark([lead("Far Out", "Newcomer A", 1.0)], seeds)
        c = cands[0]
        self.assertEqual(c["ring"], 2)
        self.assertEqual(c["strength"], R.RING_DECAY)
        self.assertEqual(c["anchor"], "Tycho")
        self.assertEqual(c["edges"][0]["ring"], 2)
        self.assertEqual(c["edges"][0]["strength"], R.RING_DECAY)

    def test_merge_keeps_one_entry_per_source_and_adds_edges(self):
        existing = [lead("Far Out", "Khruangbin", 0.4)]
        ring = R.mark([lead("Far Out", "Newcomer A", 1.0),
                       lead("Brand New", "Newcomer A", 0.8)],
                      [{"artist": "Newcomer A", "cluster": "lane-a", "anchor": "Tycho"}])
        added, merged = R.merge(existing, ring)
        self.assertEqual((added, merged), (1, 1))
        self.assertEqual(len(existing), 2)
        far = existing[0]
        self.assertEqual(far.get("ring", 1), 1)             # first-ring entry kept
        self.assertEqual([e["seed"] for e in far["edges"]], ["Khruangbin", "Newcomer A"])

    def test_harvest_runs_every_adapter_and_survives_one_failing(self):
        import csv, os, tempfile
        from engine.lib import history
        tmp = tempfile.mkdtemp()
        for name, header in (("artists.csv", "artist,plays,hours,unique_tracks,skip_rate,completion_rate,first_played,last_played"),
                             ("tracks.csv", "track,artist,album,plays,hours,skip_rate,completion_rate,first_played,last_played,track_uri"),
                             ("plays.csv", "ts,track,artist,album,ms_played,reason_start,reason_end,shuffle,skipped,platform,track_uri")):
            with open(os.path.join(tmp, name), "w", newline="") as f:
                csv.writer(f).writerow(header.split(","))
        prev = os.environ.get("SPOTIFY_CLEAN_DIR")
        os.environ["SPOTIFY_CLEAN_DIR"] = tmp
        history.reset()
        self.addCleanup(lambda: (os.environ.__setitem__("SPOTIFY_CLEAN_DIR", prev) if prev else os.environ.pop("SPOTIFY_CLEAN_DIR", None), history.reset()))
        seeds = [{"artist": "Newcomer A", "cluster": "lane-a", "anchor": "Tycho",
                  "hours": 0.0, "affinity": 0.0}]

        def good(seeds):
            return {"track_candidates": [lead("Far Out", seeds[0]["artist"], 1.0)]}, "ok"

        def bad(seeds):
            raise RuntimeError("provider down")

        out, status, used = R.harvest([], adapters=[("good", good), ("bad", bad)], seeds=seeds)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["ring"], 2)
        self.assertIn("bad error: RuntimeError", status)
        self.assertEqual(used, seeds)

    def test_no_newcomers_is_a_skip(self):
        out, status, used = R.harvest([], seeds=[])
        self.assertEqual(out, [])
        self.assertTrue(status.startswith("skipped"))


class TestSupply(unittest.TestCase):
    def test_counts_distinct_eligible_artists_by_lane_and_ring(self):
        doc = {"track_candidates": [
            verified("A"), verified("A", cluster="lane-b"),           # one artist
            verified("B", ring=2, cluster="lane-b"),
            verified("Played", verdict="played"),
            verified("Served", served=True),
            verified("Cooling", repeat="cooldown"),
            verified("Blocked", repeat="blocked"),
        ]}
        m = S.measure(doc, per_week=10, playable=0.5)
        self.assertEqual(m["eligible_artists"], 2)
        self.assertEqual(m["weeks_of_supply"], 0.2)
        self.assertEqual(m["weeks_expected_playable"], 0.1)
        self.assertEqual(m["by_ring"], {"1": 1, "2": 1})
        self.assertEqual(m["by_lane"], {"lane-a": 1, "lane-b": 1})
        self.assertTrue(m["low"])
        self.assertIn("[warn]", S.report(m))

    def test_healthy_supply_does_not_warn(self):
        doc = {"track_candidates": [verified(f"A{i}") for i in range(60)]}
        m = S.measure(doc, per_week=10, playable=0.75)
        self.assertEqual(m["weeks_of_supply"], 6.0)
        self.assertFalse(m["low"])
        self.assertNotIn("[warn]", S.report(m))


if __name__ == "__main__":
    unittest.main()
