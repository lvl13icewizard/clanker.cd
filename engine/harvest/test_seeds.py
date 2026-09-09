"""Tests for seed-artist selection (audit F10).

Run:  PYTHONPATH=<root> python3 -m engine.harvest.test_seeds
"""

import csv
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from engine.harvest import seeds as S


def member(artist, aff, hours=10.0, last="2026-07-01"):
    return {"artist": artist, "affinity": aff, "hours": hours, "last_played": last}


def model(clusters, index=None, last_play="2026-07-18T00:00:00Z"):
    return {"window": {"last_play": last_play},
            "clusters": [{"id": cid, "members": ms} for cid, ms in clusters.items()],
            "artists_index": index or {}}


class TestFallbackOrdering(unittest.TestCase):
    def test_index_topup_is_sorted_by_hours_before_truncation(self):
        """The reproduced defect: a one-seed request took 'Alphabet First'
        (1 h) over 'Big Favorite' (100 h) because artists_index was filled
        alphabetically and only sorted afterwards."""
        m = model({}, index={
            "alphabet first": {"artist": "Alphabet First", "hours": 1.0, "clusters": []},
            "big favorite": {"artist": "Big Favorite", "hours": 100.0, "clusters": []},
        })
        got = S.select_seeds(m, n=1, issue_n=1)
        self.assertEqual([s["artist"] for s in got], ["Big Favorite"])

    def test_csv_fallback_sorts_by_hours(self):
        tmp = tempfile.mkdtemp()
        with open(Path(tmp) / "artists.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow("artist,plays,hours,unique_tracks,skip_rate,completion_rate,first_played,last_played".split(","))
            w.writerow(["Alphabet First", "5", "1.0", "2", "0", "0.9", "2024-01-01", "2024-02-01"])
            w.writerow(["Big Favorite", "500", "100.0", "40", "0", "0.9", "2020-01-01", "2026-06-01"])
        for name in ("tracks.csv", "plays.csv"):
            (Path(tmp) / name).write_text("ts\n" if name == "plays.csv" else "track,artist\n")
        _prev_clean = os.environ.get("SPOTIFY_CLEAN_DIR")
        os.environ["SPOTIFY_CLEAN_DIR"] = tmp
        from engine.lib import history
        history.reset()
        try:
            got = S._fallback(1)
        finally:
            history.reset()
            os.environ.pop("SPOTIFY_CLEAN_DIR", None); _prev_clean and os.environ.__setitem__("SPOTIFY_CLEAN_DIR", _prev_clean)
        self.assertEqual([s["artist"] for s in got], ["Big Favorite"])


class TestAllocation(unittest.TestCase):
    def setUp(self):
        # Lane A has ten strong members; lane B has two weak ones; one
        # recent artist and one unmapped artist live only in the index.
        a = {f"A{i}": member(f"A{i}", 0.9 - i * 0.01, hours=50 - i) for i in range(10)}
        b = {"B1": member("B1", 0.3, hours=3), "B2": member("B2", 0.2, hours=2)}
        self.m = model({"lane-a": list(a.values()), "lane-b": list(b.values())}, index={
            "fresh face": {"artist": "Fresh Face", "hours": 4.0, "clusters": ["lane-a"],
                           "last_played": "2026-07-10"},
            "loner": {"artist": "Loner", "hours": 6.0, "clusters": []},
        })

    def test_every_lane_gets_a_seat_in_the_first_round(self):
        got = S.select_seeds(self.m, n=8, issue_n=1)
        lanes = Counter(s["cluster"] for s in got)
        self.assertGreaterEqual(lanes["lane-b"], 1, got)
        self.assertGreaterEqual(lanes["lane-a"], 3)

    def test_unmapped_listening_is_searched(self):
        got = S.select_seeds(self.m, n=8, issue_n=1)
        self.assertIn("Loner", [s["artist"] for s in got])

    def test_recent_interest_reaches_the_head(self):
        got = S.select_seeds(self.m, n=8, issue_n=1)
        self.assertIn("Fresh Face", [s["artist"] for s in got])

    def test_no_duplicates_and_capped(self):
        got = S.select_seeds(self.m, n=6, issue_n=1)
        names = [s["artist"] for s in got]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 6)

    def test_rotation_changes_the_list_between_issues_but_keeps_the_head(self):
        one = [s["artist"] for s in S.select_seeds(self.m, n=8, issue_n=1)]
        two = [s["artist"] for s in S.select_seeds(self.m, n=8, issue_n=2)]
        self.assertNotEqual(one, two)
        self.assertEqual(one[0], two[0])           # strongest enduring seed stays
        self.assertEqual(S.select_seeds(self.m, n=8, issue_n=2),
                         S.select_seeds(self.m, n=8, issue_n=2))  # deterministic


class TestRotate(unittest.TestCase):
    def test_head_is_stable_and_tail_rotates(self):
        pool = list("abcdefg")
        self.assertEqual(S.rotate(pool, 1, 2), list("abcdefg"))
        r2 = S.rotate(pool, 2, 2)
        self.assertEqual(r2[:2], ["a", "b"])
        self.assertEqual(sorted(r2), sorted(pool))
        self.assertNotEqual(r2, pool)


if __name__ == "__main__":
    unittest.main()
