"""Tests for album-of-the-week availability and the writer's pick.

Run:  PYTHONPATH=<root> python3 -m engine.deliver.test_availability
"""

import unittest

from engine.deliver.availability import annotate
from engine.editorial.writer import _pick_album


def proposal(*pairs):
    return {"front_to_back": [{"artist": a, "title": t} for a, t in pairs]}


def resolver(on_spotify):
    """A fake find_album_uri: only these titles exist."""
    have = {t.lower() for t in on_spotify}
    calls = []

    def resolve(_token, artist, title):
        calls.append((artist, title))
        if title.lower() in have:
            return f"spotify:album:{title.lower().replace(' ', '')}", "https://x"
        return None, None

    resolve.calls = calls
    return resolve


class TestAnnotate(unittest.TestCase):
    def test_picks_the_first_available_candidate(self):
        p = proposal(("mbv", "isn't anything"), ("basinski", "the loops"))
        chosen, checked, notes = annotate(p, None, resolver=resolver(["the loops"]))
        self.assertEqual(chosen["artist"], "basinski")
        self.assertEqual(checked, 2)
        self.assertIn("not on Spotify: mbv — isn't anything", notes)

    def test_marks_the_rejected_candidate_false(self):
        p = proposal(("mbv", "isn't anything"), ("basinski", "the loops"))
        annotate(p, None, resolver=resolver(["the loops"]))
        self.assertIs(p["front_to_back"][0]["available"], False)
        self.assertIs(p["front_to_back"][1]["available"], True)

    def test_carries_the_uri_through(self):
        p = proposal(("basinski", "the loops"))
        annotate(p, None, resolver=resolver(["the loops"]))
        self.assertEqual(p["front_to_back"][0]["spotify_album_uri"],
                         "spotify:album:theloops")

    def test_stops_checking_once_one_is_available(self):
        r = resolver(["first"])
        p = proposal(("a", "first"), ("b", "second"), ("c", "third"))
        annotate(p, None, resolver=r)
        self.assertEqual(len(r.calls), 1)
        self.assertNotIn("available", p["front_to_back"][1])

    def test_respects_max_checks(self):
        r = resolver([])
        p = proposal(*[(f"a{i}", f"t{i}") for i in range(10)])
        _, checked, notes = annotate(p, None, max_checks=3, resolver=r)
        self.assertEqual(checked, 3)
        self.assertEqual(len(r.calls), 3)
        self.assertTrue(any("no album of the week resolved" in n for n in notes))

    def test_nothing_available_returns_no_choice(self):
        p = proposal(("a", "x"), ("b", "y"))
        chosen, _, _ = annotate(p, None, resolver=resolver([]))
        self.assertIsNone(chosen)

    def test_empty_shortlist_is_not_an_error(self):
        chosen, checked, notes = annotate({}, None, resolver=resolver([]))
        self.assertIsNone(chosen)
        self.assertEqual(checked, 0)
        self.assertEqual(notes, [])


class TestPickAlbum(unittest.TestCase):
    def test_prefers_the_available_one_over_the_top_rank(self):
        items = [{"artist": "mbv", "available": False},
                 {"artist": "basinski", "available": True}]
        self.assertEqual(_pick_album(items, [])["artist"], "basinski")

    def test_falls_back_to_top_rank_when_none_available(self):
        items = [{"artist": "mbv", "available": False},
                 {"artist": "b", "available": False}]
        notes = []
        self.assertEqual(_pick_album(items, notes)["artist"], "mbv")
        self.assertTrue(any("no checked candidate is on Spotify" in n
                            for n in notes))

    def test_unannotated_proposal_keeps_the_old_behaviour(self):
        """Availability never ran: take the top of the ranking, no note."""
        items = [{"artist": "top"}, {"artist": "second"}]
        notes = []
        self.assertEqual(_pick_album(items, notes)["artist"], "top")
        self.assertEqual(notes, [])

    def test_unchecked_candidates_are_not_treated_as_available(self):
        items = [{"artist": "unchecked"}, {"artist": "known", "available": True}]
        self.assertEqual(_pick_album(items, [])["artist"], "known")


if __name__ == "__main__":
    unittest.main(verbosity=2)
