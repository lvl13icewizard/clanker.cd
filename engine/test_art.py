"""Tests for cover-art attachment, and the staleness it used to allow.

The bug: art was written once and never revisited, so when a later stage
replaced a Singles Rack pick the card kept the sleeve of the track it
replaced. Issue 004 published two of those. The correct URL was fetched on
every run; only the write was gated.

Run:  PYTHONPATH=<root> python3 -m engine.test_art
"""

import unittest

from engine import art
from engine.art import strip_edition


class TestPutRefresh(unittest.TestCase):
    """resolve() drives put() through the module branches; these exercise the
    Singles Rack branch, which is the one a later stage can rewrite."""

    def rack(self, *tracks):
        return {"modules": [{"type": "singles_rack", "tracks": list(tracks)}]}

    def track(self, uri, cover=None, key=None):
        d = {"artist": "A", "title": "T", "spotify_track_uri": uri}
        if cover:
            d["cover_url"] = cover
        if key:
            d["cover_key"] = key
        return d

    def run_with(self, issue, covers):
        """Resolve with a stubbed Spotify lookup: uri -> cover url."""
        real = art.spotify_cover
        art.spotify_cover = lambda u: covers.get(u)
        try:
            return art.resolve(issue)
        finally:
            art.spotify_cover = real

    def test_fills_art_when_there_is_none(self):
        issue = self.rack(self.track("spotify:track:new"))
        self.run_with(issue, {"spotify:track:new": "http://img/new.jpg"})
        t = issue["modules"][0]["tracks"][0]
        self.assertEqual(t["cover_url"], "http://img/new.jpg")
        self.assertEqual(t["cover_key"], "spotify:track:new")

    def test_replaced_track_gets_fresh_art(self):
        # The issue-004 bug: the card was swapped to a new track but kept the
        # old sleeve, because a cover_url was already present.
        issue = self.rack(self.track("spotify:track:new",
                                     cover="http://img/OLD.jpg",
                                     key="spotify:track:old"))
        self.run_with(issue, {"spotify:track:new": "http://img/new.jpg"})
        self.assertEqual(issue["modules"][0]["tracks"][0]["cover_url"],
                         "http://img/new.jpg")

    def test_unchanged_track_keeps_its_art(self):
        issue = self.rack(self.track("spotify:track:same",
                                     cover="http://img/same.jpg",
                                     key="spotify:track:same"))
        self.run_with(issue, {"spotify:track:same": "http://img/same.jpg"})
        self.assertEqual(issue["modules"][0]["tracks"][0]["cover_url"],
                         "http://img/same.jpg")

    def test_failed_lookup_never_wipes_existing_art(self):
        # The half of the old guard that was worth keeping.
        issue = self.rack(self.track("spotify:track:x",
                                     cover="http://img/keep.jpg",
                                     key="spotify:track:x"))
        self.run_with(issue, {})
        self.assertEqual(issue["modules"][0]["tracks"][0]["cover_url"],
                         "http://img/keep.jpg")

    def test_art_from_before_keys_existed_is_refreshed_once(self):
        # Issues written before this fix carry no cover_key at all.
        issue = self.rack(self.track("spotify:track:new", cover="http://img/OLD.jpg"))
        self.run_with(issue, {"spotify:track:new": "http://img/new.jpg"})
        t = issue["modules"][0]["tracks"][0]
        self.assertEqual(t["cover_url"], "http://img/new.jpg")
        self.assertEqual(t["cover_key"], "spotify:track:new")

    def test_counts_report_filled_items(self):
        issue = self.rack(self.track("spotify:track:a"), self.track("spotify:track:b"))
        filled, total = self.run_with(issue, {"spotify:track:a": "http://img/a.jpg"})
        self.assertEqual((filled, total), (1, 2))


class TestStripEdition(unittest.TestCase):
    """Pitchfork reviews reissues, so its titles carry edition tags the
    catalogues do not. Liz Phair's Exile in Guyville showed a blank tile."""

    def test_drops_a_bracketed_anniversary_edition(self):
        self.assertEqual(
            strip_edition("exile in guyville [15th anniversary edition]"),
            "exile in guyville")

    def test_drops_a_parenthesised_deluxe(self):
        self.assertEqual(strip_edition("Psychocandy (Deluxe Edition)"),
                         "Psychocandy")

    def test_leaves_an_ordinary_title_alone(self):
        self.assertEqual(strip_edition("Horse Rotorvator"), "Horse Rotorvator")

    def test_leaves_a_meaningful_bracket_alone(self):
        # Not an edition tag; part of the record's actual name.
        self.assertEqual(strip_edition("Sir Lucious Left Foot (The Son of Chico Dusty)"),
                         "Sir Lucious Left Foot (The Son of Chico Dusty)")

    def test_handles_empty_input(self):
        self.assertEqual(strip_edition(None), "")
        self.assertEqual(strip_edition(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
