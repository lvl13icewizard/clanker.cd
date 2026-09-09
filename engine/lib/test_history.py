import csv
import os
import tempfile
import unittest
from pathlib import Path

ARTISTS = ["artist,plays,hours,unique_tracks,skip_rate,completion_rate,first_played,last_played"]
TRACKS = ["track,artist,album,plays,hours,skip_rate,completion_rate,first_played,last_played,track_uri"]


def _write(d, name, header, rows):
    with open(Path(d) / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header.split(","))
        for r in rows:
            w.writerow(r)


class Aggregation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _write(self.tmp, "artists.csv", ARTISTS[0], [
            ["Fred again..", "30", "1.5", "5", "0.10", "0.80", "2024-01-01", "2024-06-01"],
            ["Fred Again..", "10", "0.5", "2", "0.30", "0.60", "2023-05-01", "2024-02-01"],
            ["宇多田ヒカル", "7", "0.4", "3", "0.0", "0.9", "2022-01-01", "2022-02-01"],
            ["周杰倫", "9", "0.6", "4", "0.0", "0.9", "2021-01-01", "2021-02-01"],
        ])
        _write(self.tmp, "tracks.csv", TRACKS[0], [
            ["Marea", "Fred again..", "Actual Life", "20", "1.0", "0.1", "0.8", "2024-01-01", "2024-06-01", "spotify:track:aaa"],
            ["Marea - Edit", "Fred Again..", "Actual Life", "5", "0.2", "0.2", "0.7", "2024-03-01", "2024-03-02", ""],
        ])
        _write(self.tmp, "plays.csv", "ts,track,artist,album,ms_played,reason_start,reason_end,shuffle,skipped,platform,track_uri", [])
        self._prev_clean = os.environ.get("SPOTIFY_CLEAN_DIR")
        os.environ["SPOTIFY_CLEAN_DIR"] = self.tmp
        from engine.lib import history
        history.reset()
        self.h = history

    def tearDown(self):
        self.h.reset()
        (os.environ.__setitem__("SPOTIFY_CLEAN_DIR", self._prev_clean) if getattr(self, "_prev_clean", None) else os.environ.pop("SPOTIFY_CLEAN_DIR", None))

    def test_same_key_rows_are_summed_not_overwritten(self):
        row = self.h.artist_played("fred again")
        self.assertEqual(row["plays"], "40")
        self.assertEqual(row["hours"], "2")
        self.assertEqual(row["unique_tracks"], "7")
        self.assertEqual(row["first_played"], "2023-05-01")
        self.assertEqual(row["last_played"], "2024-06-01")
        self.assertEqual(row["artist"], "Fred again..")          # the busier spelling
        self.assertAlmostEqual(float(row["skip_rate"]), (0.10 * 30 + 0.30 * 10) / 40, places=6)

    def test_non_latin_rows_stay_separate(self):
        self.assertIsNotNone(self.h.artist_played("宇多田ヒカル"))
        self.assertIsNotNone(self.h.artist_played("周杰倫"))
        self.assertNotEqual(self.h.artist_played("宇多田ヒカル")["artist"],
                            self.h.artist_played("周杰倫")["artist"])
        self.assertEqual(self.h.stats()["artists"], 3)

    def test_track_versions_fold_and_keep_the_uri(self):
        row = self.h.track_played("Fred Again..", "Marea - Edit")
        self.assertIsNotNone(row)
        self.assertEqual(row["plays"], "25")
        self.assertEqual(row["track_uri"], "spotify:track:aaa")

    def test_a_parenthesised_subtitle_is_identity_not_a_version(self):
        # "(We've Lost Dancing)" names a different song from "Marea"; only a
        # bracket that mentions a version word is stripped.
        self.assertIsNone(self.h.track_played("Fred again..", "Marea (We've Lost Dancing)"))

    def test_merges_are_recorded(self):
        m = self.h.merges()
        self.assertEqual(m["artists"]["fred again"], ["Fred again..", "Fred Again.."])
        self.assertIn(("fred again", "marea"), m["tracks"])


if __name__ == "__main__":
    unittest.main()
