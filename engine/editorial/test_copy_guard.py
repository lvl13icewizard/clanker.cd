import os
import unittest

os.environ.setdefault("SPOTIFY_CLEAN_DIR", "/nonexistent-for-import-only")
from engine.editorial.writer import guard_copy, _merge


def _base():
    return {
        "issue": 4, "title": "Issue 004: Unopened", "dek": "old dek",
        "modules": [
            {"type": "singles_rack", "intro": "old intro",
             "tracks": [{"artist": "Keisha Plum", "title": "Flyy", "spotify_track_uri": "spotify:track:real",
                         "why": "old why", "receipts": [{"value": 3}]},
                        {"artist": "Roc Marciano", "title": "Snow", "why": "old why 2"}]},
            {"type": "ledger", "verdict": "old verdict"},
        ],
    }


class IdentityIsNotProse(unittest.TestCase):
    def test_renaming_an_artist_is_refused(self):
        over = {"modules": [{"type": "singles_rack", "tracks": [{"artist": "Someone Else", "why": "x"}]}]}
        _, errs = guard_copy(_base(), over, [])
        self.assertEqual(len(errs), 1); self.assertIn("modules[singles_rack].tracks[0].artist", errs[0])

    def test_retitling_a_track_is_refused(self):
        over = {"modules": [{"type": "singles_rack", "tracks": [{"title": "Flyy (Wrong)", "why": "x"}]}]}
        self.assertTrue(guard_copy(_base(), over, [])[1])

    def test_matching_anchors_are_fine_and_never_written(self):
        over = {"modules": [{"type": "singles_rack",
                             "tracks": [{"artist": "keisha plum", "title": "FLYY", "why": "new why"}]}]}
        safe, errs = guard_copy(_base(), over, [])
        self.assertEqual(errs, [])
        merged = _merge(_base(), safe)
        t = merged["modules"][0]["tracks"][0]
        self.assertEqual(t["why"], "new why")
        self.assertEqual((t["artist"], t["title"], t["spotify_track_uri"]), ("Keisha Plum", "Flyy", "spotify:track:real"))

    def test_non_prose_keys_are_dropped_and_named(self):
        notes = []
        over = {"modules": [{"type": "singles_rack",
                             "tracks": [{"spotify_track_uri": "spotify:track:fake", "receipts": [], "why": "w"}]}]}
        safe, errs = guard_copy(_base(), over, notes)
        self.assertEqual(errs, [])
        merged = _merge(_base(), safe)
        self.assertEqual(merged["modules"][0]["tracks"][0]["spotify_track_uri"], "spotify:track:real")
        self.assertEqual(merged["modules"][0]["tracks"][0]["receipts"], [{"value": 3}])
        self.assertTrue(any("spotify_track_uri" in n for n in notes))
        self.assertTrue(any("receipts" in n for n in notes))

    def test_top_level_title_and_dek_are_prose(self):
        safe, errs = guard_copy(_base(), {"title": "Issue 004: Slow Return", "dek": "new dek", "issue": 99}, [])
        self.assertEqual(errs, [])
        merged = _merge(_base(), safe)
        self.assertEqual((merged["title"], merged["dek"], merged["issue"]), ("Issue 004: Slow Return", "new dek", 4))

    def test_module_prose_merges_and_extra_items_are_ignored(self):
        notes = []
        over = {"modules": [{"type": "singles_rack", "intro": "new intro",
                             "tracks": [{"why": "a"}, {"why": "b"}, {"artist": "Ghost", "why": "c"}]},
                            {"type": "ledger", "verdict": "new verdict"},
                            {"type": "not_in_issue", "intro": "x"}]}
        safe, errs = guard_copy(_base(), over, notes)
        self.assertEqual(errs, [])
        merged = _merge(_base(), safe)
        self.assertEqual(merged["modules"][0]["intro"], "new intro")
        self.assertEqual([t["why"] for t in merged["modules"][0]["tracks"]], ["a", "b"])
        self.assertEqual(merged["modules"][1]["verdict"], "new verdict")
        self.assertTrue(any("beyond the issue" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
