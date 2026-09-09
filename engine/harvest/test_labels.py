"""Tests for the label model, roster-gap leads, label releases and the
label card.

Run:  PYTHONPATH=<root> python3 -m engine.harvest.test_labels
"""

import datetime as dt
import unittest

from engine.editorial.writer import rack_entry
from engine.harvest import labels as H
from engine.model import build_label_model as M

TODAY = dt.date(2026, 9, 7)


class TestAbsorb(unittest.TestCase):
    def test_browse_and_search_rows_merge_with_dates(self):
        by = {}
        M.absorb_releases(by, [
            {"date": "1994-03-01", "artist-credit": [{"name": "Autechre", "artist": {"id": "a", "name": "Autechre"}}]},
            {"date": "2024-05-01", "artist-credit": [{"name": "Autechre", "artist": {"id": "a", "name": "Autechre"}}]},
            {"date": "2023-01-01", "artist-credit": [{"name": "Various Artists", "artist": {"name": "Various Artists"}}]},
            {"date": "2025", "artist-credit": [{"name": "Squid", "artist": {"id": "s", "name": "Squid"}}]},
        ])
        self.assertEqual(sorted(by), ["autechre", "squid"])
        self.assertEqual(by["autechre"]["releases"], 2)
        self.assertEqual(by["autechre"]["first_date"], "1994-03-01")
        self.assertEqual(by["autechre"]["last_date"], "2024-05-01")
        self.assertEqual(by["squid"]["last_date"], "2025")


class TestLabelModel(unittest.TestCase):
    def test_majors_and_placeholders_are_excluded(self):
        for name in ("Universal Music Group", "Columbia", "[no label]",
                     "Sony Music Entertainment", "DistroKid", "Not On Label"):
            self.assertTrue(M.is_major(name), name)
        for name in ("Ghostly International", "Ninja Tune", "Warp", "Stones Throw"):
            self.assertFalse(M.is_major(name), name)

    def test_hours_split_by_release_share_and_summed_per_label(self):
        rows = {"tycho": {"artist": "Tycho", "hours": 40.0, "clusters": ["beats-idm"]},
                "lusine": {"artist": "Lusine", "hours": 10.0, "clusters": ["beats-idm", "the-mist"]}}
        labs = {"tycho": {"Ghostly": {"mbid": "g", "releases": 30},
                          "Ninja Tune": {"mbid": "n", "releases": 10}},
                "lusine": {"Ghostly": {"mbid": "g", "releases": 5}}}
        out = M.score(rows, labs)
        self.assertEqual([L["name"] for L in out], ["Ghostly", "Ninja Tune"])
        g = out[0]
        self.assertEqual(g["hours"], 40.0)                # 30 + 10
        self.assertEqual(g["artists"][0]["artist"], "Tycho")
        self.assertEqual(g["artists"][0]["share"], 0.75)
        self.assertEqual(g["lanes"], {"beats-idm": 40.0, "the-mist": 10.0})
        self.assertEqual(out[1]["hours"], 10.0)


def label(name, hours, roster, lanes=None, artists=3, mbid="m"):
    return {"name": name, "mbid": mbid, "hours": hours,
            "artists": [{}] * artists, "lanes": lanes or {"beats-idm": hours},
            "roster": roster}


def member(artist, releases=1, last="2024-01-01"):
    return {"artist": artist, "releases": releases, "last_date": last}


NOVEL = {"lusine", "dabrye", "shigeto"}


class TestRosterLeads(unittest.TestCase):
    def test_only_never_played_roster_artists_become_leads(self):
        labs = [label("Ghostly", 60.0, [member("Tycho", 30), member("Lusine", 6)])]
        out = H.roster_leads(labs, today=TODAY, is_novel=lambda n: n.lower() in NOVEL)
        self.assertEqual([c["artist"] for c in out], ["Lusine"])
        c = out[0]
        self.assertEqual(c["source"], "label_roster")
        self.assertEqual(c["via"], "Ghostly")
        self.assertEqual(c["relation"], "label")
        self.assertEqual(c["cluster_hint"], "beats-idm")
        self.assertEqual(c["label"], {"name": "Ghostly", "hours": 60.0, "artists": 3, "releases": 6})
        self.assertEqual(c["edges"][0]["kind"], "label")
        self.assertEqual(c["strength"], 1.0)              # top label, full career, recent

    def test_strength_weighs_label_career_and_dormancy(self):
        labs = [label("Ghostly", 60.0, [member("Lusine", 5), member("Dabrye", 1),
                                        member("Shigeto", 5, last="2009-01-01")]),
                label("Small", 6.0, [member("Lusine", 5)])]
        out = {c["artist"]: c for c in
               H.roster_leads(labs, today=TODAY, is_novel=lambda n: n.lower() in NOVEL)}
        self.assertEqual(out["Lusine"]["strength"], 1.0)
        self.assertAlmostEqual(out["Dabrye"]["strength"], 0.6, places=3)      # one 12"
        self.assertAlmostEqual(out["Shigeto"]["strength"], 0.6, places=3)     # dormant
        self.assertEqual(len(out["Lusine"]["edges"]), 2)                       # both labels kept
        self.assertEqual(out["Lusine"]["via"], "Ghostly")                      # strongest wins


class TestLabelReleases(unittest.TestCase):
    def test_parses_typed_dated_releases_and_marks_relationship(self):
        hits = [
            {"title": "New Record", "date": "2026-08-30",
             "release-group": {"id": "rg1", "primary-type": "Album"},
             "artist-credit": [{"name": "Lusine", "artist": {"name": "Lusine"}}]},
            {"title": "Old Friend EP", "date": "2026-08-20",
             "release-group": {"id": "rg2", "primary-type": "EP"},
             "artist-credit": [{"name": "Tycho", "artist": {"name": "Tycho"}}]},
            {"title": "Live Thing", "date": "2026-08-21",
             "release-group": {"id": "rg3", "primary-type": "Album", "secondary-types": ["Live"]},
             "artist-credit": [{"name": "Tycho", "artist": {"name": "Tycho"}}]},
            {"title": "Month Only", "date": "2026-08",
             "release-group": {"id": "rg4", "primary-type": "Single"},
             "artist-credit": [{"name": "Lusine", "artist": {"name": "Lusine"}}]},
            {"title": "New Record", "date": "2026-08-30",                     # duplicate
             "release-group": {"id": "rg1", "primary-type": "Album"},
             "artist-credit": [{"name": "Lusine", "artist": {"name": "Lusine"}}]},
        ]
        out = H.label_releases([label("Ghostly", 60.0, [])], today=TODAY,
                               search=lambda mbid, a, b: hits,
                               played=lambda n: n == "Tycho")
        self.assertEqual([(r["artist"], r["title"], r["relationship"], r["release_type"])
                          for r in out],
                         [("Tycho", "Old Friend EP", "played", "ep"),
                          ("Lusine", "New Record", "label", "album")])
        self.assertEqual(out[0]["via"], "Ghostly")
        self.assertEqual(out[0]["source"], "label_release")


class TestLabelCard(unittest.TestCase):
    def test_label_lead_gets_label_receipts_and_a_true_why(self):
        it = {"artist": "Lusine", "via": "Ghostly International", "relation": "label",
              "label": {"name": "Ghostly International", "hours": 61.3, "artists": 9,
                        "releases": 6}}
        card = rack_entry("beats-idm", it, {}, 5)
        self.assertIn("A door opened by the label Ghostly International", card["why"])
        self.assertIn("61.3 hours on your shelf", card["why"])
        ids = {r["stat_id"] for r in card["receipts"]}
        self.assertIn("label_hours:ghostly international", ids)
        self.assertIn("label_artists:ghostly international", ids)
        self.assertEqual(card["cluster"], "beats-idm")

    def test_artist_lead_is_unchanged(self):
        card = rack_entry("beats-idm", {"artist": "X", "via": "Tycho"}, {}, 5)
        self.assertEqual(card["why"], "A door opened by Tycho.")


if __name__ == "__main__":
    unittest.main()
