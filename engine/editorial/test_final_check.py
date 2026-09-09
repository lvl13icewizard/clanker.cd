import os
import unittest

os.environ.setdefault("SPOTIFY_CLEAN_DIR", "/nonexistent-for-import-only")
from engine.editorial.final_check import final_check

PROPOSAL = {
    "singles_rack": {"rap": [{"artist": "Keisha Plum"}, {"artist": "Roc Marciano"}, {"artist": "Reserve Act"}]},
    "revival_desk": {"barely_played": [{"artist": "Tycho", "track": "Skate"}]},
    "front_to_back": [{"artist": "The Wrens", "title": "The Meadowlands"}],
}
SERVED = {"items": [{"artist": "Sven Wunder", "title": "Lotus"}]}
PLAYED_ARTISTS = {"tycho", "westside gunn"}
PLAYED_TRACKS = {("keisha plum", "flyy")}


def _issue(rack=None, revival=None, album=None):
    return {"issue": 4, "modules": [
        {"type": "singles_rack", "tracks": rack if rack is not None else [
            {"artist": "Keisha Plum", "title": "Rockets", "spotify_track_uri": "spotify:track:a"},
            {"artist": "Roc Marciano", "title": "Snow", "spotify_track_uri": "spotify:track:b"}]},
        {"type": "revival_desk", "tracks": revival if revival is not None else [{"artist": "Tycho", "title": "Skate"}]},
        {"type": "front_to_back", "album": album or {"artist": "The Wrens", "title": "The Meadowlands"}},
    ]}


def _run(issue):
    return final_check(issue, PROPOSAL, SERVED,
                       lambda a: a.lower() in PLAYED_ARTISTS,
                       lambda a, t: (a.lower(), t.lower()) in PLAYED_TRACKS)


class FinalGate(unittest.TestCase):
    def test_clean_issue_passes(self):
        self.assertEqual(_run(_issue()), ([], []))

    def test_identity_changed_after_selection(self):
        errs, _ = _run(_issue(rack=[{"artist": "Someone Else", "title": "X", "spotify_track_uri": "u"}]))
        self.assertTrue(any("not among the selector's leads" in e for e in errs))

    def test_played_artist_in_the_rack(self):
        errs, _ = _run(_issue(rack=[{"artist": "Westside Gunn", "title": "X", "spotify_track_uri": "u"}]))
        self.assertTrue(any("play history" in e for e in errs))

    def test_played_song_by_a_new_artist(self):
        errs, _ = _run(_issue(rack=[{"artist": "Keisha Plum", "title": "Flyy", "spotify_track_uri": "u"}]))
        self.assertTrue(any("Flyy" in e and "play history" in e for e in errs))

    def test_duplicate_artist_and_empty_card(self):
        errs, _ = _run(_issue(rack=[{"artist": "Keisha Plum", "title": "A", "spotify_track_uri": "u"},
                                    {"artist": "keisha plum", "title": "B", "spotify_track_uri": "u"},
                                    {"artist": "Roc Marciano", "title": None}]))
        self.assertTrue(any("twice" in e for e in errs))
        self.assertTrue(any("no track behind it" in e for e in errs))

    def test_revival_outside_every_pool(self):
        errs, _ = _run(_issue(revival=[{"artist": "Tycho", "title": "Awake"}]))
        self.assertTrue(any("not in any revival pool" in e for e in errs))

    def test_served_repeat_and_album_not_a_candidate(self):
        errs, _ = _run(_issue(rack=[{"artist": "Sven Wunder", "title": "Lotus", "spotify_track_uri": "u"}],
                              album={"artist": "Other", "title": "Record"}))
        self.assertTrue(any("already served" in e for e in errs))
        self.assertTrue(any("not a selector candidate" in e for e in errs))

    def test_missing_uri_is_a_warning_not_an_error(self):
        errs, warns = _run(_issue(rack=[{"artist": "Roc Marciano", "title": "Snow"}]))
        self.assertEqual(errs, []); self.assertEqual(len(warns), 1)


if __name__ == "__main__":
    unittest.main()
