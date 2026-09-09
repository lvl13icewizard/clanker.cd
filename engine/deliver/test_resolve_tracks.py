"""Tests for Singles Rack track choice: the song, not just the artist, must
be new to the reader.

The bug these cover: a Singles Rack lead is artist-level, so the song is
chosen at resolve time, after zero-play verification has already run and
found nothing (it had no title to check). The choice then asked whether the
LEAD artist had played the song — but the case the guard exists for is a
feature or compilation credit filing that song under a DIFFERENT artist, so
the question could never come back true. Issue 004 offered three songs the
reader had played 48, 25 and 15 times.

Run:  PYTHONPATH=<root> python3 -m engine.deliver.test_resolve_tracks
"""

import unittest

from engine.deliver.resolve_tracks import (
    backfill_singles,
    pick_track_for_artist,
    played_under_any_credit,
    revival_uri_from_history,
)
from engine.lib.normalize import track_key


def track(name, *artists):
    return {
        "name": name,
        "artists": [{"name": a} for a in artists],
        "uri": "spotify:track:" + name.lower().replace(" ", ""),
        "external_urls": {"spotify": "https://open.spotify.com/track/x"},
    }


def log(*pairs):
    """A fake play history: only these (artist, title) pairs were played."""
    have = {track_key(a, t) for a, t in pairs}

    def played(artist, title):
        return {"plays": 1} if track_key(artist, title) in have else None

    return played


def searcher(*items):
    def search(_token, _query, _kind, pages=1):
        return list(items)
    return search


class TestPlayedUnderAnyCredit(unittest.TestCase):
    def test_lead_artist_play_still_counts(self):
        t = track("Beacon", "Matt Duncan")
        self.assertTrue(played_under_any_credit(t, log(("Matt Duncan", "Beacon"))))

    def test_feature_credit_catches_the_real_owner(self):
        # The actual issue-004 defect: the log has it under MF DOOM.
        t = track("Rapp Snitch Knishes", "MF DOOM", "Mr. Fantastik")
        self.assertTrue(
            played_under_any_credit(t, log(("MF DOOM", "Rapp Snitch Knishes")))
        )

    def test_guest_credited_lead_is_not_enough_on_its_own(self):
        # Asking only the artist we searched for is what missed it.
        t = track("Rapp Snitch Knishes", "MF DOOM", "Mr. Fantastik")
        self.assertFalse(
            played_under_any_credit(t, log(("Mr. Fantastik", "Something Else")))
        )

    def test_unplayed_song_by_played_artists_is_allowed(self):
        # Bassnectar and Ragga Twins are both deep in the log; this song is
        # not. Artist-level fame must not disqualify a genuinely new track.
        t = track("Watch Out", "Dirtyphonics", "Bassnectar", "Ragga Twins")
        self.assertFalse(
            played_under_any_credit(
                t, log(("Bassnectar", "Timestretch"), ("Ragga Twins", "Spliffhead"))
            )
        )

    def test_same_title_by_an_unrelated_artist_is_allowed(self):
        # "Magnetizing" collides by title with a Handsome Boy Modeling School
        # song. Different record, nobody in common, still a fair pick.
        t = track("Magnetizing", "Marsmobil", "Roberto Di Gioia")
        self.assertFalse(
            played_under_any_credit(
                t, log(("Handsome Boy Modeling School", "Magnetizing"))
            )
        )

    def test_feature_decoration_in_the_title_still_matches(self):
        # Spotify says "On Top (feat. T-Shirt)"; the log says "On Top".
        t = track("On Top (feat. T-Shirt)", "Flume", "T-Shirt")
        self.assertTrue(played_under_any_credit(t, log(("Flume", "On Top"))))

    def test_no_credits_is_not_a_play(self):
        self.assertFalse(played_under_any_credit({"name": "X", "artists": []}, log()))


class TestPickTrackForArtist(unittest.TestCase):
    def test_skips_the_played_song_and_takes_the_next(self):
        pick, why = pick_track_for_artist(
            None,
            "Mr. Fantastik",
            set(),
            search=searcher(
                track("Rapp Snitch Knishes", "MF DOOM", "Mr. Fantastik"),
                track("Bells of Doom", "Mr. Fantastik"),
            ),
            played=log(("MF DOOM", "Rapp Snitch Knishes")),
        )
        self.assertIsNone(why)
        self.assertEqual(pick["title"], "Bells of Doom")

    def test_served_titles_still_skipped(self):
        pick, why = pick_track_for_artist(
            None,
            "Mr. Fantastik",
            {track_key("Mr. Fantastik", "Bells of Doom")},
            search=searcher(track("Bells of Doom", "Mr. Fantastik")),
            played=log(),
        )
        self.assertIsNone(pick)
        self.assertIn("already served or already played", why)

    def test_reports_when_every_candidate_is_already_known(self):
        pick, why = pick_track_for_artist(
            None,
            "Mr. Fantastik",
            set(),
            search=searcher(track("Rapp Snitch Knishes", "MF DOOM", "Mr. Fantastik")),
            played=log(("MF DOOM", "Rapp Snitch Knishes")),
        )
        self.assertIsNone(pick)
        self.assertIn("already served or already played", why)

    def test_wrong_artist_results_are_still_rejected(self):
        pick, why = pick_track_for_artist(
            None,
            "Mr. Fantastik",
            set(),
            search=searcher(track("Doomsday", "MF DOOM")),
            played=log(),
        )
        self.assertIsNone(pick)
        self.assertIn("nobody by that exact name", why)

    def test_clean_lead_resolves_normally(self):
        pick, why = pick_track_for_artist(
            None,
            "Ursula 1000",
            set(),
            search=searcher(track("Arrastao", "Ursula 1000")),
            played=log(),
        )
        self.assertIsNone(why)
        self.assertEqual(pick["title"], "Arrastao")
        self.assertTrue(pick["spotify_track_uri"].startswith("spotify:track:"))


class TestBackfillSingles(unittest.TestCase):
    """The rack promises ten. A lead that yields no song must be replaced
    from the ranked reserves, not left as a card with nothing behind it."""

    def rack(self, *entries):
        return {"modules": [{"type": "singles_rack", "tracks": list(entries)}]}

    def slot(self, artist, uri=None):
        return {"artist": artist, "title": None if uri is None else "T",
                "cluster": "beats-idm", "why": "w", "receipts": [],
                "spotify_track_uri": uri, "spotify_url": None}

    def reserves(self, *artists):
        return [("beats-idm", {"artist": a, "via": "KOAN Sound", "score": 1.0})
                for a in artists]

    def test_empty_slot_is_filled_from_the_reserves(self):
        doc = self.rack(self.slot("Ursula 1000", "spotify:track:a"),
                        self.slot("T.Shirt"))
        filled, exhausted = backfill_singles(
            doc, None, set(), self.reserves("Nubiyan Twist"), {}, 4,
            search=searcher(track("Return", "Nubiyan Twist")), played=log())
        tracks = doc["modules"][0]["tracks"]
        self.assertEqual((filled, exhausted), (1, []))
        self.assertEqual(tracks[1]["artist"], "Nubiyan Twist")
        self.assertEqual(tracks[1]["title"], "Return")
        self.assertTrue(tracks[1]["spotify_track_uri"])

    def test_filled_slots_are_left_alone(self):
        doc = self.rack(self.slot("Ursula 1000", "spotify:track:a"))
        filled, exhausted = backfill_singles(
            doc, None, set(), self.reserves("Nubiyan Twist"), {}, 4,
            search=searcher(track("Return", "Nubiyan Twist")), played=log())
        self.assertEqual((filled, exhausted), (0, []))
        self.assertEqual(doc["modules"][0]["tracks"][0]["artist"], "Ursula 1000")

    def test_replacement_keeps_the_slot_position(self):
        doc = self.rack(self.slot("A", "spotify:track:a"),
                        self.slot("T.Shirt"),
                        self.slot("C", "spotify:track:c"))
        backfill_singles(
            doc, None, set(), self.reserves("Nubiyan Twist"), {}, 4,
            search=searcher(track("Return", "Nubiyan Twist")), played=log())
        got = [t["artist"] for t in doc["modules"][0]["tracks"]]
        self.assertEqual(got, ["A", "Nubiyan Twist", "C"])

    def test_a_reserve_that_also_fails_is_skipped_for_the_next(self):
        # First reserve's only song is already played; second one is clean.
        def search(_token, query, _kind, pages=1):
            if "Dead End" in query:
                return [track("On Top (feat. T-Shirt)", "Flume", "Dead End")]
            return [track("Return", "Nubiyan Twist")]

        doc = self.rack(self.slot("T.Shirt"))
        filled, exhausted = backfill_singles(
            doc, None, set(), self.reserves("Dead End", "Nubiyan Twist"), {}, 4,
            search=search, played=log(("Flume", "On Top")))
        self.assertEqual((filled, exhausted), (1, []))
        self.assertEqual(doc["modules"][0]["tracks"][0]["artist"], "Nubiyan Twist")

    def test_reports_the_slot_when_reserves_run_out(self):
        doc = self.rack(self.slot("T.Shirt"))
        filled, exhausted = backfill_singles(
            doc, None, set(), [], {}, 4,
            search=searcher(), played=log())
        self.assertEqual(filled, 0)
        self.assertEqual(exhausted, ["T.Shirt"])
        self.assertEqual(doc["modules"][0]["tracks"][0]["artist"], "T.Shirt")

    def test_never_promotes_an_artist_already_in_the_rack(self):
        doc = self.rack(self.slot("Nubiyan Twist", "spotify:track:a"),
                        self.slot("T.Shirt"))
        filled, exhausted = backfill_singles(
            doc, None, set(), self.reserves("Nubiyan Twist", "Nala Sinephro"),
            {}, 4,
            search=searcher(track("Space 1", "Nala Sinephro")), played=log())
        self.assertEqual(filled, 1)
        self.assertEqual(doc["modules"][0]["tracks"][1]["artist"], "Nala Sinephro")

    def test_promoted_entry_has_the_same_shape_as_an_original(self):
        doc = self.rack(self.slot("T.Shirt"))
        backfill_singles(
            doc, None, set(), self.reserves("Nubiyan Twist"), {}, 4,
            search=searcher(track("Return", "Nubiyan Twist")), played=log())
        got = doc["modules"][0]["tracks"][0]
        for k in ("artist", "title", "cluster", "why", "receipts",
                  "spotify_track_uri", "spotify_url"):
            self.assertIn(k, got, f"promoted entry is missing {k}")

    def test_no_singles_module_is_harmless(self):
        self.assertEqual(
            backfill_singles({"modules": [{"type": "ledger"}]}, None, set(),
                             self.reserves("X"), {}, 4,
                             search=searcher(), played=log()),
            (0, []))


class TestRevivalUriFromHistory(unittest.TestCase):
    """Second Chances picks come out of the play log, which already knows
    their Spotify ids. Issue 004 lost two Tycho remixes to a title search for
    records it had the ids for."""

    def row(self, uri):
        def played(_artist, _title):
            return {"track_uri": uri} if uri is not None else None
        return played

    def test_uses_the_id_the_log_carries(self):
        uri, url = revival_uri_from_history(
            "Tycho", "Pink & Blue (feat. Saint Sinner) - RAC Mix",
            played=self.row("3rxYhGVE6GHQyAy4CdGfq1"))
        self.assertEqual(uri, "spotify:track:3rxYhGVE6GHQyAy4CdGfq1")
        self.assertEqual(
            url, "https://open.spotify.com/track/3rxYhGVE6GHQyAy4CdGfq1")

    def test_accepts_a_full_uri_in_the_log(self):
        uri, _ = revival_uri_from_history(
            "Tycho", "Skate", played=self.row("spotify:track:1ysN6YRxRx8ju8U7mE8Abn"))
        self.assertEqual(uri, "spotify:track:1ysN6YRxRx8ju8U7mE8Abn")

    def test_falls_back_when_the_row_has_no_uri(self):
        self.assertEqual(
            revival_uri_from_history("Tycho", "X", played=self.row("")),
            (None, None))

    def test_falls_back_when_the_track_is_not_in_the_log(self):
        self.assertEqual(
            revival_uri_from_history("Tycho", "X", played=self.row(None)),
            (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
