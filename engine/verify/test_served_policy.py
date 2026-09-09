"""Tests for module-specific repeat policies and the exposure log
(audit F16).

Run:  PYTHONPATH=<root> python3 -m engine.verify.test_served_policy
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from engine import serve_ledger
from engine.verify import served_policy as P

TODAY = date(2026, 9, 6)


def row(artist, title, context, served_at=None, uri=None):
    d = {"artist": artist, "title": title, "context": context, "uri": uri}
    if served_at:
        d["served_at"] = served_at
    return d


class TestExposures(unittest.TestCase):
    def test_dates_come_from_the_row_then_the_issue_then_today(self):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "issue-002.json").write_text(json.dumps({"issue": 2, "date": "2026-08-15"}))
        served = {"items": [
            row("A", "T", "issue-002:singles_rack", served_at="2026-08-16"),
            row("B", "T", "issue-002:critics_desk"),
            row("C", "T", "vol1"),
            row("D", "T", "issue-009:singles_rack"),
        ]}
        got = {e["artist"]: e["served_at"] for e in P.exposures(served, tmp, TODAY)}
        self.assertEqual(got, {"A": "2026-08-16", "B": "2026-08-15",
                               "C": P.VOL1_DATE, "D": TODAY.isoformat()})


class TestWindows(unittest.TestCase):
    def setUp(self):
        self.exps = P.exposures({"items": [
            row("Fresh Offer", "Album", "issue-004:critics_desk", "2026-08-30"),
            row("Old Offer", "Album", "issue-001:critics_desk", "2025-01-01"),
            row("Announced", "Single", "issue-004:new_this_week", "2026-08-30"),
            row("Deep Devotion", "catalog room feature", "issue-002:catalog_room", "2026-08-01"),
        ]}, today=TODAY)

    def test_album_cooldown_expires(self):
        pairs = P.pairs_within(self.exps, {"critics_desk", "front_to_back"},
                               P.ALBUM_COOLDOWN_DAYS, TODAY)
        self.assertIn(("fresh offer", "album"), pairs)
        self.assertNotIn(("old offer", "album"), pairs)

    def test_an_announcement_is_not_a_discovery_offer(self):
        arts = P.artists_within(self.exps, {"critics_desk", "front_to_back",
                                            "singles_rack", "catalog_room"},
                                365, TODAY)
        self.assertNotIn("announced", arts)

    def test_catalog_cooldown_counts_only_catalog_rooms(self):
        self.assertEqual(P.artists_within(self.exps, {"catalog_room"},
                                          P.CATALOG_COOLDOWN_DAYS, TODAY),
                         {"deep devotion"})


class TestRevival(unittest.TestCase):
    def test_pairs_within_the_last_n_issues_sit_out(self):
        served = {"items": [
            row("Tycho", "Awake", "issue-001:revival_desk"),
            row("Bonobo", "Kerala", "issue-004:revival_desk"),
            row("Air", "Alone", "issue-004:singles_rack"),
        ]}
        got = P.revival_pairs_recent(served, issue_n=5, within_issues=3)
        self.assertEqual(got, {("bonobo", "kerala")})
        self.assertIn(("tycho", "awake"), P.revival_pairs_recent(served, 5, 6))


class TestShows(unittest.TestCase):
    def test_episodes_never_return_shows_sit_out_one_issue(self):
        served = {"items": [
            row("Old Show", "Ep 1", "issue-001:the_mix",
                uri="https://www.nts.live/shows/old-show/episodes/ep1"),
            row("Last Show", "Ep 2", "issue-004:the_mix",
                uri="https://www.nts.live/shows/last-show/episodes/ep2?x=1"),
        ]}
        urls, titles, shows = P.show_exclusions(served, sitout_issues=1)
        self.assertEqual(urls, {"https://www.nts.live/shows/old-show/episodes/ep1",
                                "https://www.nts.live/shows/last-show/episodes/ep2"})
        self.assertEqual(titles, {"ep 1", "ep 2"})
        self.assertEqual(shows, {"last-show", "last show"})

    def test_undated_rows_are_treated_as_recent(self):
        served = {"items": [row("Some Show", "Ep", "the_mix")]}
        _, _, shows = P.show_exclusions(served)
        self.assertEqual(shows, {"some show"})


class TestExposureLog(unittest.TestCase):
    def test_a_repeat_offer_in_a_later_issue_is_a_new_row(self):
        i3 = {"issue": 3, "date": "2026-08-22", "modules": [
            {"type": "revival_desk", "tracks": [{"artist": "Tycho", "title": "Awake"}]}]}
        i5 = {"issue": 5, "date": "2026-09-06", "modules": [
            {"type": "revival_desk", "tracks": [{"artist": "Tycho", "title": "Awake"}]}]}
        e3, e5 = serve_ledger.entries_for(i3), serve_ledger.entries_for(i5)
        self.assertEqual(e3[0]["served_at"], "2026-08-22")
        self.assertEqual(e5[0]["served_at"], "2026-09-06")
        self.assertNotEqual((e3[0]["artist"], e3[0]["title"], e3[0]["context"]),
                            (e5[0]["artist"], e5[0]["title"], e5[0]["context"]))


if __name__ == "__main__":
    unittest.main()
