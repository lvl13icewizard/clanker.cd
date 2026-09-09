import os
import unittest

os.environ.setdefault("SPOTIFY_CLEAN_DIR", "/nonexistent-for-import-only")
from engine.select import phase2


class OptionalDatabases(unittest.TestCase):
    def test_missing_pitchfork_keys_yield_no_rows_not_a_crash(self):
        self.assertEqual(list(phase2._rows({})), [])

    def test_configured_but_absent_files_also_yield_nothing(self):
        cfg = {"PITCHFORK_SCRAPED_DB": "/nope/a.db", "PITCHFORK_KAGGLE_DB": "/nope/b.db"}
        self.assertEqual(list(phase2._rows(cfg)), [])


if __name__ == "__main__":
    unittest.main()
