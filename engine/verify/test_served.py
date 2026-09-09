import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SPOTIFY_CLEAN_DIR", "/nonexistent-for-import-only")
from engine.verify import served


class CleanInstall(unittest.TestCase):
    def test_no_file_and_no_vol1_means_an_empty_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ.pop("PLAYLIST_MD", None)
            got = served.load_or_build(path=str(Path(d) / "served.json"))
            self.assertEqual(got, {"items": []})
            self.assertFalse((Path(d) / "served.json").exists(), "nothing was written")

    def test_existing_file_is_read_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "served.json"
            p.write_text(json.dumps({"items": [{"artist": "A", "title": "T", "uri": None, "context": "x"}]}))
            self.assertEqual(len(served.load_or_build(path=str(p))["items"]), 1)

    def test_build_refuses_without_a_source(self):
        os.environ.pop("PLAYLIST_MD", None)
        with self.assertRaises(SystemExit):
            served.build(write=False)

    def test_no_personal_path_in_the_module(self):
        src = Path(served.__file__).read_text()
        self.assertNotIn("/Users/", src)


if __name__ == "__main__":
    unittest.main()
