"""Tests for evidence-aware ranking and the revival served filter
(audit F11, F16).

Run:  PYTHONPATH=<root> python3 -m engine.select.test_evidence
"""

import unittest

from engine.select import select_issue as S


def lead(artist, source, via, strength=None, cluster="lane-a", edges=None):
    c = {"artist": artist, "title": None, "source": source, "via": via,
         "cluster_hint": cluster,
         "verification": {"verdict": "novel", "served_before": False,
                          "artist_repeat": {"state": "clear"}}}
    if strength is not None:
        c["strength"] = strength
    if edges is not None:
        c["edges"] = edges
    return c


MODEL = S.Model({
    "clusters": [{"id": "lane-a", "state": "active",
                  "members": [{"artist": "Seed A", "affinity": 0.8},
                              {"artist": "Seed B", "affinity": 0.8}]}],
    "artists_index": {},
})


class TestFamilies(unittest.TestCase):
    def test_same_review_via_two_routes_is_one_family(self):
        self.assertEqual(len(S.families({"pitchfork_catalog", "pitchfork_rss"})), 1)
        self.assertEqual(len(S.families({"pitchfork_rss", "bandcamp_daily"})), 2)
        self.assertEqual(len(S.families({"lb_labs", "lastfm_similar", "deezer_related"})), 3)


class TestRelationshipStrength(unittest.TestCase):
    def test_strength_separates_two_leads_through_the_same_seed_and_source(self):
        """The reproduced defect: both scored 0.924."""
        strong = lead("Close Cousin", "lb_labs", "Seed A", strength=1.0)
        weak = lead("Distant Cousin", "lb_labs", "Seed A", strength=0.2)
        prop = S.build_proposal(1, {"track_candidates": [strong, weak]}, MODEL, {}, [])
        by = {it["artist"]: it["score"] for it in prop["singles_rack"]["lane-a"]}
        self.assertGreater(by["Close Cousin"], by["Distant Cousin"])

    def test_via_comes_from_the_strongest_edge_not_provider_order(self):
        first = lead("Newcomer", "deezer_related", "Seed A", strength=0.3,
                     edges=[{"seed": "Seed A", "cluster": "lane-a", "rank": 7, "strength": 0.3}])
        second = lead("Newcomer", "lb_labs", "Seed B", strength=0.95, cluster="lane-b",
                      edges=[{"seed": "Seed B", "cluster": "lane-b", "rank": 0, "strength": 0.95}])
        for order in ([first, second], [second, first]):
            prop = S.build_proposal(1, {"track_candidates": order}, MODEL, {}, [])
            items = [it for lane in prop["singles_rack"].values() for it in lane]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["via"], "Seed B")
            self.assertIn("lane-b", prop["singles_rack"])
            self.assertEqual(items[0]["seeds"], 2)
            self.assertEqual(items[0]["source"], "deezer_related+lb_labs")

    def test_relation_follows_the_strongest_edge(self):
        lab = lead("Newcomer", "label_roster", "Warp", strength=0.5,
                   edges=[{"seed": "Warp", "cluster": "lane-a", "rank": 0,
                           "strength": 0.5, "kind": "label"}])
        lab["relation"] = "label"
        lab["label"] = {"name": "Warp", "hours": 97.8, "artists": 18, "releases": 3}
        sim = lead("Newcomer", "lb_labs", "Seed A", strength=0.9)
        prop = S.build_proposal(1, {"track_candidates": [lab, sim]}, MODEL, {}, [])
        it = [i for lane in prop["singles_rack"].values() for i in lane][0]
        self.assertEqual(it["via"], "Seed A")
        self.assertIsNone(it["relation"])           # not "the label Seed A"
        self.assertIsNone(it["label"])
        sim_weak = lead("Newcomer", "lb_labs", "Seed A", strength=0.2)
        prop = S.build_proposal(1, {"track_candidates": [sim_weak, lab]}, MODEL, {}, [])
        it = [i for lane in prop["singles_rack"].values() for i in lane][0]
        self.assertEqual((it["via"], it["relation"]), ("Warp", "label"))
        self.assertEqual(it["label"]["hours"], 97.8)

    def test_leads_without_strength_are_scored_as_before(self):
        old = lead("Legacy Lead", "lb_labs", "Seed A")
        score, basis = S._score(MODEL, old, "lane-a", {"lb_labs"}, None)
        self.assertNotIn("rel", basis)
        self.assertAlmostEqual(score, (0.4 + 0.6 * 0.8) * 1.05, places=4)

    def test_more_seeds_is_a_small_bonus_two_families_a_larger_one(self):
        c = lead("X", "lb_labs", "Seed A", strength=1.0)
        one, _ = S._score(MODEL, c, "lane-a", {"lb_labs"}, None, strength=1.0, seeds=1)
        two_seeds, _ = S._score(MODEL, c, "lane-a", {"lb_labs"}, None, strength=1.0, seeds=2)
        two_fam, _ = S._score(MODEL, c, "lane-a", {"lb_labs", "deezer_related"}, None,
                              strength=1.0, seeds=1)
        self.assertGreater(two_seeds, one)
        self.assertGreater(two_fam, two_seeds)


class TestRevivalFilter(unittest.TestCase):
    POOLS = {"barely_played": [{"artist": "Tycho", "track": "Awake", "plays": 2},
                               {"artist": "Bonobo", "track": "Kerala", "plays": 3}],
             "fade_outs": [{"artist": "Air", "track": "Alone in Kyoto", "plays": 50}],
             "time_capsule": []}

    def test_recently_offered_pairs_sit_out(self):
        notes = []
        prop = S.build_proposal(5, {}, MODEL, self.POOLS, notes,
                                served_revival={("tycho", "awake")})
        self.assertEqual([e["artist"] for e in prop["revival_desk"]["barely_played"]],
                         ["Bonobo"])
        self.assertTrue(any("sit out" in n for n in notes), notes)

    def test_recently_played_pairs_are_not_revivals(self):
        notes = []
        prop = S.build_proposal(5, {}, MODEL, self.POOLS, notes,
                                recent_plays={("air", "alone in kyoto")})
        self.assertEqual(prop["revival_desk"]["fade_outs"], [])
        self.assertTrue(any("played in the last" in n for n in notes), notes)

    def test_nothing_served_leaves_pools_intact(self):
        prop = S.build_proposal(5, {}, MODEL, self.POOLS, [])
        self.assertEqual(len(prop["revival_desk"]["barely_played"]), 2)


if __name__ == "__main__":
    unittest.main()
