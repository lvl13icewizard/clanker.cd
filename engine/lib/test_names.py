"""Tests for cross-script artist names and their use in verification.

Run:  PYTHONPATH=<root> python3 -m engine.lib.test_names
"""

import unittest

from engine.lib import history, names
from engine.verify.zero_play import verify_candidate

DOC = {"name": "宇山寛人", "sort-name": "Uyama, Hiroto", "aliases": [
    {"name": "Hiroto Uyama", "locale": "en", "primary": False, "type": "Legal name"},
    {"name": "Uyama Hiroto", "locale": "en", "primary": True, "type": "Artist name"},
]}


class TestNames(unittest.TestCase):
    def test_is_latin(self):
        self.assertTrue(names.is_latin("Maxïmo Park"))
        self.assertTrue(names.is_latin("!!!"))
        self.assertTrue(names.is_latin("Erlend Øye"))
        self.assertFalse(names.is_latin("宇山寛人"))
        self.assertFalse(names.is_latin("Кино"))

    def test_primary_english_alias_wins(self):
        self.assertEqual(names.pick_latin(DOC, "宇山寛人"), "Uyama Hiroto")
        self.assertEqual(names.latin_name("mbid", "宇山寛人", fetch=lambda m: DOC), "Uyama Hiroto")
        self.assertEqual(names.latin_name("mbid", "Nujabes", fetch=lambda m: 1 / 0), "Nujabes")

    def test_no_latin_alias_keeps_the_name(self):
        self.assertEqual(names.pick_latin({"aliases": [{"name": "うやま", "locale": "ja"}]}, "宇山寛人"),
                         "宇山寛人")

    def test_aliases_list_every_form_once(self):
        self.assertEqual(names.aliases("mbid", "宇山寛人", fetch=lambda m: DOC),
                         ["宇山寛人", "Hiroto Uyama", "Uyama Hiroto"])
        self.assertEqual(names.aliases("mbid", "Nujabes"), ["Nujabes"])


class TestVerifierUsesAliases(unittest.TestCase):
    def setUp(self):
        self._ap = history.artist_played
        self._near = history.near_artist_matches
        self._tc = history.title_collisions
        history.artist_played = lambda n: {"artist": "Uyama Hiroto", "plays": "12"} \
            if names.is_latin(n) and "uyama" in n.lower() else None
        history.near_artist_matches = lambda n, limit=8: []
        history.title_collisions = lambda t: []

    def tearDown(self):
        history.artist_played = self._ap
        history.near_artist_matches = self._near
        history.title_collisions = self._tc

    def test_canonical_script_name_is_played_through_its_alias(self):
        v = verify_candidate({"artist": "宇山寛人", "title": None,
                              "aliases": ["宇山寛人", "Uyama Hiroto"]}, set())
        self.assertEqual(v["verdict"], "played")
        self.assertTrue(v["artist_played"])
        self.assertEqual(v["artist_row"]["artist"], "Uyama Hiroto")

    def test_without_aliases_the_leak_remains_visible(self):
        v = verify_candidate({"artist": "宇山寛人", "title": None}, set())
        self.assertEqual(v["verdict"], "novel")


if __name__ == "__main__":
    unittest.main()
