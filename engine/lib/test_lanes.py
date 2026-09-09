"""Tests for genre -> lane classification, shared by the harvest and the desk.

The bug: "experimental" is a modifier tag in Pitchfork's taxonomy, but both
classifiers ranked it above "rock", so rock records carrying it were filed
under Beats & IDM. Issue 004 shipped The Meadowlands as the album of the week
under an IDM lane tag. The two classifiers also disagreed about where rock
goes, and the harvest's answer is the one that wins for the album of the week.

Run:  PYTHONPATH=<root> python3 -m engine.lib.test_lanes
"""

import unittest

from engine.harvest.pitchfork_local import cluster_hint
from engine.lib.lanes import GENRE_PRIORITY, rock_cluster
from engine.select.phase2 import _cluster_for_genres as desk


class TestExperimentalIsLast(unittest.TestCase):
    def test_experimental_never_outranks_a_real_genre(self):
        self.assertEqual(GENRE_PRIORITY[-1], "experimental")

    def test_the_meadowlands_is_not_idm(self):
        # "experimental,rock", reviewed 2003. The album of the week in 004.
        self.assertEqual(desk("experimental,rock", "2003-01-01"), "dad-rock")
        self.assertEqual(cluster_hint(["experimental", "rock"], modern=False),
                         "dad-rock")

    def test_psychocandy_is_not_idm(self):
        self.assertEqual(desk("rock,experimental", "2011-01-01"), "dad-rock")

    def test_experimental_alone_still_classifies(self):
        self.assertEqual(desk("experimental", "2003-01-01"), "beats-idm")
        self.assertEqual(cluster_hint(["experimental"], modern=False), "beats-idm")

    def test_global_outranks_electronic(self):
        # A deliberate choice, not an accident: the two source lists ranked
        # these opposite ways and unifying them forced one. See lanes.py.
        self.assertLess(GENRE_PRIORITY.index("global"),
                        GENRE_PRIORITY.index("electronic"))
        self.assertEqual(desk("electronic, global", "2026-08-01"), "cosmic-groove")

    def test_electronic_still_beats_rock(self):
        # Coil: electronic, experimental, rock. Genuinely an IDM-lane record.
        self.assertEqual(desk("electronic, experimental, rock", "1999-01-01"),
                         "beats-idm")

    def test_rap_and_jazz_are_unaffected(self):
        self.assertEqual(desk("rap", "2010-01-01"), "underground-rap")
        self.assertEqual(desk("jazz", "2010-01-01"), "jazz-bridge")

    def test_no_known_genre_is_unclassified(self):
        self.assertIsNone(desk("metal", "2010-01-01"))
        self.assertIsNone(cluster_hint(["metal"], modern=False))


class TestRockEra(unittest.TestCase):
    def test_modern_rock_is_the_punk_turn(self):
        self.assertEqual(rock_cluster(True), "punk-turn")
        self.assertEqual(desk("rock", "2020-01-01"), "punk-turn")
        self.assertEqual(cluster_hint(["rock"], modern=True), "punk-turn")

    def test_older_rock_is_the_dad_rock_shelf(self):
        self.assertEqual(rock_cluster(False), "dad-rock")
        self.assertEqual(desk("rock", "2003-01-01"), "dad-rock")
        self.assertEqual(cluster_hint(["rock"], modern=False), "dad-rock")

    def test_unknown_era_takes_the_older_reading(self):
        self.assertEqual(desk("rock", ""), "dad-rock")
        self.assertEqual(cluster_hint(["rock"]), "dad-rock")

    def test_harvest_and_desk_agree_on_every_genre(self):
        """The disagreement that shipped: two classifiers, one lane tag."""
        for genres in (["rock"], ["experimental", "rock"], ["rap"], ["jazz"],
                       ["global"], ["experimental"]):
            for modern in (True, False):
                pub = "2020-01-01" if modern else "2003-01-01"
                self.assertEqual(
                    cluster_hint(genres, modern=modern),
                    desk(",".join(genres), pub),
                    f"harvest and desk disagree on {genres} modern={modern}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
