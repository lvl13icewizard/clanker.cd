"""Tests for the artist-level repeat guard and the eligibility rule it feeds.

Run:  PYTHONPATH=<root> python3 -m engine.verify.test_repeat_guard
"""

import unittest
from datetime import date

from engine.select.select_issue import _eligible
from engine.verify import repeat_guard as G

TODAY = date(2026, 8, 29)


def guard(offers=None, played=None, today=TODAY, in_history=()):
    """A guard over a fixed world: no real play log, no real issues dir."""
    known = {G.norm_artist(a) for a in in_history}
    return G.Guard(offers or {}, played or {}, today,
                   history_lookup=lambda a: ({"artist": a}
                                             if G.norm_artist(a) in known else None))


def offer(artist, when, context="issue-002:singles_rack"):
    return {G.norm_artist(artist): {"artist": artist, "last": when,
                                    "contexts": [context]}}


def ledger_row(artist, plays=5):
    return {G.norm_artist(artist): {"artist": artist, "issue": 3,
                                    "plays": plays, "first_play": "2026-08-21"}}


def candidate(artist, title=None, verdict="novel", repeat=None,
              served_before=False):
    return {"artist": artist, "title": title,
            "verification": {"verdict": verdict, "served_before": served_before,
                             "artist_repeat": repeat}}


class TestStatus(unittest.TestCase):
    def test_never_offered_is_clear(self):
        st = guard().status("Nobody At All")
        self.assertEqual(st["state"], "clear")
        self.assertEqual(st["reason"], "never offered")

    def test_played_after_serving_is_blocked(self):
        g = guard(offers=offer("Matt Duncan", "2026-08-21"),
                  played=ledger_row("Matt Duncan"))
        st = g.status("Matt Duncan")
        self.assertEqual(st["state"], "blocked")
        self.assertEqual(st["reason"], "played since it was served")
        self.assertIsNone(st["cooldown_until"])

    def test_blocked_beats_cooldown(self):
        """A played artist is blocked even while the cooldown would apply."""
        g = guard(offers=offer("Matt Duncan", "2026-08-28"),
                  played=ledger_row("Matt Duncan"))
        self.assertTrue(g.blocked("Matt Duncan"))

    def test_served_and_ignored_is_cooldown(self):
        g = guard(offers=offer("Space Laces", "2026-08-21"))
        st = g.status("Space Laces")
        self.assertEqual(st["state"], "cooldown")
        self.assertEqual(st["cooldown_until"], "2027-02-20")

    def test_cooldown_expires(self):
        g = guard(offers=offer("Old Lead", "2026-01-01"))
        st = g.status("Old Lead")
        self.assertEqual(st["state"], "clear")
        self.assertEqual(st["reason"], "cooldown expired")

    def test_cooldown_boundary_is_inclusive_of_the_last_day(self):
        served = (TODAY.toordinal() - G.COOLDOWN_DAYS)
        g = guard(offers=offer("Edge", date.fromordinal(served).isoformat()))
        self.assertEqual(g.status("Edge")["state"], "clear")
        g2 = guard(offers=offer("Edge", date.fromordinal(served + 1).isoformat()))
        self.assertEqual(g2.status("Edge")["state"], "cooldown")

    def test_matching_ignores_case_and_punctuation(self):
        g = guard(offers=offer("Peter Cat Recording Co.", "2026-07-30"))
        self.assertEqual(g.status("peter cat recording co")["state"], "cooldown")

    def test_undatable_offer_is_treated_as_todays(self):
        """Missing date suppresses a repeat rather than waving it through."""
        g = guard(offers=offer("Undated Lead", TODAY.isoformat()))
        self.assertEqual(g.status("Undated Lead")["state"], "cooldown")

    def test_artist_in_the_play_history_is_blocked(self):
        g = guard(in_history=["Khruangbin"])
        st = g.status("Khruangbin")
        self.assertEqual(st["state"], "blocked")
        self.assertEqual(st["reason"], "already in the play history")


class TestContexts(unittest.TestCase):
    def test_discovery_contexts_recognised(self):
        self.assertEqual(G._context_kind("issue-002:singles_rack"), "singles_rack")
        self.assertEqual(G._context_kind("vol1"), "vol1")
        self.assertEqual(G._context_issue("issue-012:critics_desk"), 12)

    def test_non_discovery_contexts_are_not_offers(self):
        """New This Week is artists already played; the_mix stores a show."""
        for kind in ("new_this_week", "the_mix"):
            self.assertNotIn(kind, G.DISCOVERY_CONTEXTS)

    def test_ledger_label_splits_on_the_artist_title_dash(self):
        self.assertEqual(
            G._LABEL_RE.match("Four Tet — As Serious As Your Life - Jay Dee Remix")
            .group(1),
            "Four Tet")


class TestEligibility(unittest.TestCase):
    def test_blocked_artist_never_eligible(self):
        c = candidate("Matt Duncan", repeat={"state": "blocked"})
        self.assertFalse(_eligible(c))

    def test_blocked_artist_not_eligible_even_with_a_title(self):
        c = candidate("Matt Duncan", title="Some Other Song",
                      repeat={"state": "blocked"})
        self.assertFalse(_eligible(c))

    def test_cooldown_blocks_artist_level_leads(self):
        c = candidate("Space Laces", title=None, repeat={"state": "cooldown"})
        self.assertFalse(_eligible(c))

    def test_cooldown_allows_a_different_named_record(self):
        """The deep-cut carve-out: a titled candidate is a different record."""
        c = candidate("Basic Channel", title="BCD 2", repeat={"state": "cooldown"})
        self.assertTrue(_eligible(c))

    def test_clear_artist_eligible(self):
        self.assertTrue(_eligible(candidate("DJ Falcon", repeat={"state": "clear"})))

    def test_missing_repeat_block_does_not_crash(self):
        self.assertTrue(_eligible(candidate("DJ Falcon", repeat=None)))

    def test_existing_rules_still_apply(self):
        self.assertFalse(_eligible(candidate("X", verdict="played",
                                             repeat={"state": "clear"})))
        self.assertFalse(_eligible(candidate("X", served_before=True,
                                             repeat={"state": "clear"})))


if __name__ == "__main__":
    unittest.main(verbosity=2)
