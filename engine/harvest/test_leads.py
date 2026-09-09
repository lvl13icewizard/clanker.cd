"""Tests for retained edges and yield-driven deepening (audit F10, F11).

Run:  PYTHONPATH=<root> python3 -m engine.harvest.test_leads
"""

import unittest

from engine.harvest import deezer, lastfm, lb_labs, leads as L


SEED_A = {"artist": "Seed A", "cluster": "lane-a"}
SEED_B = {"artist": "Seed B", "cluster": "lane-b"}


class TestLeads(unittest.TestCase):
    def test_one_candidate_per_source_with_every_edge_kept(self):
        ld = L.Leads("lastfm_similar")
        ld.add("Newcomer", SEED_A, 0, 0.4)
        ld.add("Newcomer", SEED_B, 2, 0.9)
        cands = ld.candidates()
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(len(c["edges"]), 2)
        self.assertEqual(c["via"], "Seed B")          # strongest, not first
        self.assertEqual(c["cluster_hint"], "lane-b")
        self.assertEqual(c["strength"], 0.9)
        self.assertEqual(c["source"], "lastfm_similar")
        self.assertIsNone(c["title"])

    def test_same_seed_twice_is_one_edge(self):
        ld = L.Leads("deezer_related")
        ld.add("Newcomer", SEED_A, 0, 1.0)
        ld.add("Newcomer", SEED_A, 5, 0.5)
        self.assertEqual(len(ld.candidates()[0]["edges"]), 1)

    def test_rank_strength(self):
        self.assertEqual(L.strength_by_rank(0, 10), 1.0)
        self.assertAlmostEqual(L.strength_by_rank(9, 10), 0.1)
        self.assertGreater(L.strength_by_rank(0, 10), L.strength_by_rank(1, 10))


class TestYield(unittest.TestCase):
    def setUp(self):
        self._novel = L.is_novel
        L.is_novel = lambda n: n.startswith("New")

    def tearDown(self):
        L.is_novel = self._novel

    def test_counts_novel_per_lane(self):
        y = L.Yield()
        self.assertEqual(y.record(SEED_A, ["New 1", "Old 1", "New 2"]), 2)
        y.record(SEED_B, ["Old 2"], deepened=True)
        lanes = y.by_lane()
        self.assertEqual(lanes["lane-a"], {"seeds": 1, "leads": 3, "novel": 2})
        self.assertEqual(lanes["lane-b"], {"seeds": 1, "leads": 1, "novel": 0})
        self.assertIn("1 seeds deepened", y.summary())
        self.assertIn("lane-a 2/3", y.summary())


class TestAdaptersDeepen(unittest.TestCase):
    """A seed whose first page is mostly played is queried deeper."""

    def setUp(self):
        self._novel = L.is_novel
        L.is_novel = lambda n: n.startswith("New")

    def tearDown(self):
        L.is_novel = self._novel

    def test_lastfm_requests_a_deeper_page_when_yield_is_low(self):
        calls = []

        def similar(name, limit):
            calls.append((name, limit))
            rows = [{"name": f"Old {i}", "match": str(1 - i / 40)} for i in range(limit)]
            if limit > L.PER_SEED:
                rows[-1] = {"name": "New Deep", "match": "0.2"}
            return rows

        payload, status = lastfm.harvest(similar=similar, seeds=[SEED_A])
        self.assertEqual([c for _, c in calls], [L.PER_SEED, L.DEEP_PER_SEED])
        names = [c["artist"] for c in payload["track_candidates"]]
        self.assertIn("New Deep", names)
        self.assertIn("1 seeds deepened", status)
        self.assertEqual(payload["yield"]["lane-a"]["novel"], 1)

    def test_lastfm_does_not_deepen_a_productive_seed(self):
        calls = []

        def similar(name, limit):
            calls.append(limit)
            return [{"name": f"New {i}", "match": "0.5"} for i in range(limit)]

        lastfm.harvest(similar=similar, seeds=[SEED_A])
        self.assertEqual(calls, [L.PER_SEED])

    def test_lb_labs_reads_deeper_from_the_same_response_and_normalizes_score(self):
        rows = [{"name": f"Old {i}", "score": 200 - i} for i in range(40)]
        rows[25] = {"name": "New Deep", "score": 175}
        payload, status = lb_labs.harvest(similar=lambda mbid: rows,
                                          resolve=lambda name: "mbid-1",
                                          seeds=[SEED_A])
        by = {c["artist"]: c for c in payload["track_candidates"]}
        self.assertIn("New Deep", by)
        self.assertEqual(by["Old 0"]["strength"], 1.0)     # top of the response
        self.assertAlmostEqual(by["New Deep"]["strength"], 175 / 200, places=3)
        self.assertEqual(len(payload["track_candidates"]), L.DEEP_PER_SEED)

    def test_deezer_deepens_and_ranks(self):
        calls = []

        def related(aid, limit):
            calls.append(limit)
            rows = [{"name": f"Old {i}"} for i in range(limit)]
            if limit > L.PER_SEED:
                rows[limit - 1] = {"name": "New Deep"}
            return rows

        payload, _ = deezer.harvest(related=related, artist_id=lambda n: 7,
                                    seeds=[SEED_A])
        self.assertEqual(calls, [L.PER_SEED, L.DEEP_PER_SEED])
        by = {c["artist"]: c for c in payload["track_candidates"]}
        self.assertEqual(by["Old 0"]["strength"], 1.0)
        self.assertLess(by["New Deep"]["strength"], by["Old 0"]["strength"])


if __name__ == "__main__":
    unittest.main()
