"""Tests for the fresh-listens overlay: ingest watermark, history merge,
model clock and same-run ledger in the guard (audit F15).

Run:  PYTHONPATH=<root> python3 -m engine.model.test_fresh_listens
"""

import csv
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from engine.lib import history
from engine.model import build_taste_model as M
from engine.model import fresh_listens as F
from engine.verify import repeat_guard as G

EXPORT_TAIL = "2026-07-18T19:46:54Z"


def _csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header.split(","))
        for r in rows:
            w.writerow(r)


def listen(epoch, artist, title, release="R"):
    return {"listened_at": epoch, "track_metadata": {
        "artist_name": artist, "track_name": title, "release_name": release}}


def overlay(*rows, export_cutoff=EXPORT_TAIL):
    listens = [{"ts": ts, "epoch": F._epoch(ts), "artist": a, "title": t, "release": "R"}
               for ts, a, t in rows]
    wm = max([r["epoch"] for r in listens] + [0])
    return {"export_cutoff": export_cutoff, "watermark_epoch": wm,
            "watermark": F._iso(wm) if wm else None, "listens": listens}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = tempfile.mkdtemp()
        _csv(Path(self.tmp) / "artists.csv",
             "artist,plays,hours,unique_tracks,skip_rate,completion_rate,first_played,last_played",
             [["Tycho", "100", "9.5", "20", "0.05", "0.9", "2015-01-01", "2026-07-01"]])
        _csv(Path(self.tmp) / "tracks.csv",
             "track,artist,album,plays,hours,skip_rate,completion_rate,first_played,last_played,track_uri",
             [["Awake", "Tycho", "Awake", "30", "2.0", "0.0", "0.9", "2015-01-01", "2026-07-01", "spotify:track:x"]])
        _csv(Path(self.tmp) / "plays.csv",
             "ts,track,artist,album,ms_played,reason_start,reason_end,shuffle,skipped,platform,track_uri",
             [["2015-01-01T00:00:00Z", "Awake", "Tycho", "Awake", "200000", "", "", "", "False", "", ""],
              [EXPORT_TAIL, "Awake", "Tycho", "Awake", "200000", "", "", "", "False", "", ""]])
        self._prev_clean = os.environ.get("SPOTIFY_CLEAN_DIR")
        os.environ["SPOTIFY_CLEAN_DIR"] = self.tmp
        os.environ["OUT_DIR"] = self.out
        history.reset()

    def tearDown(self):
        history.reset()
        (os.environ.__setitem__("SPOTIFY_CLEAN_DIR", self._prev_clean) if getattr(self, "_prev_clean", None) else os.environ.pop("SPOTIFY_CLEAN_DIR", None))
        os.environ.pop("OUT_DIR", None)


class TestIngest(Base):
    def test_fetches_after_the_export_tail_and_resumes_from_the_watermark(self):
        calls = []

        def fetch(user, since):
            calls.append(since)
            return [listen(F._epoch(EXPORT_TAIL) + 100, "Newcomer", "First"),
                    listen(F._epoch(EXPORT_TAIL) - 100, "Tycho", "Awake")]  # before tail

        cfg = {"OUT_DIR": self.out, "LISTENBRAINZ_USER": "u"}
        s = F.ingest(fetch=fetch, cfg=cfg)
        self.assertEqual(s["new"], 1)
        self.assertEqual(calls, [F._epoch(EXPORT_TAIL)])
        doc = F.load(cfg)
        self.assertEqual(doc["export_cutoff"], EXPORT_TAIL)
        self.assertEqual(doc["watermark_epoch"], F._epoch(EXPORT_TAIL) + 100)

        s = F.ingest(fetch=fetch, cfg=cfg)            # same listens again
        self.assertEqual(s["new"], 0)
        self.assertEqual(calls[-1], F._epoch(EXPORT_TAIL) + 100)
        self.assertEqual(len(F.load(cfg)["listens"]), 1)

    def test_no_user_is_a_skip_not_an_error(self):
        self.assertTrue(F.ingest(cfg={"OUT_DIR": self.out})["status"].startswith("skipped"))

    def test_an_overlay_for_another_export_is_discarded_on_ingest(self):
        cfg = {"OUT_DIR": self.out, "LISTENBRAINZ_USER": "u"}
        stale = overlay(("2026-07-20T00:00:00Z", "Ghost", "Song"), export_cutoff="2026-01-01T00:00:00Z")
        F.path(cfg).write_text(json.dumps(stale))
        F.ingest(fetch=lambda u, s: [], cfg=cfg)
        self.assertEqual(F.load(cfg)["listens"], [])


class TestHistoryOverlay(Base):
    def test_fresh_artist_becomes_played_and_fresh_plays_move_dates(self):
        history.set_fresh(overlay(("2026-08-20T10:00:00Z", "Newcomer", "First"),
                                  ("2026-08-21T10:00:00Z", "Tycho", "Awake"),
                                  ("2026-08-22T10:00:00Z", "Tycho", "Brand New Song")))
        row = history.artist_played("Newcomer")
        self.assertIsNotNone(row)
        self.assertEqual(row["source"], "listenbrainz")
        self.assertEqual(row["hours"], "0")                 # never invented
        # Unknown rates read as "0": the mix harvesters and phase 2 call
        # float() on them, and an empty string took the NTS harvest down.
        self.assertEqual((row["skip_rate"], row["completion_rate"]), ("0", "0"))
        self.assertEqual(history.track_played("Newcomer", "First")["skip_rate"], "0")
        tycho = history.artist_played("Tycho")
        self.assertEqual(tycho["plays"], "102")
        self.assertEqual(tycho["last_played"], "2026-08-22")
        self.assertEqual(tycho["hours"], "9.5")
        self.assertIsNotNone(history.track_played("Tycho", "Brand New Song"))
        self.assertEqual(history.track_played("Tycho", "Awake")["plays"], "31")

    def test_an_overlay_built_for_another_export_is_ignored(self):
        F.path({"OUT_DIR": self.out}).write_text(json.dumps(
            overlay(("2026-08-20T10:00:00Z", "Ghost", "Song"), export_cutoff="2020-01-01T00:00:00Z")))
        history.reset()
        self.assertIsNone(history.artist_played("Ghost"))
        self.assertEqual(history.fresh_summary()["listens"], 0)

    def test_matching_overlay_file_is_read(self):
        F.path({"OUT_DIR": self.out}).write_text(json.dumps(
            overlay(("2026-08-20T10:00:00Z", "Ghost", "Song"))))
        history.reset()
        self.assertIsNotNone(history.artist_played("Ghost"))
        self.assertEqual(history.fresh_summary()["watermark"], "2026-08-20T10:00:00Z")

    def test_a_joined_credit_counts_for_each_artist(self):
        raw = listen(F._epoch(EXPORT_TAIL) + 5, "Westside Gunn, Boldy James", "Song")
        raw["track_metadata"]["additional_info"] = {"artist_names": ["Westside Gunn", "Boldy James"]}
        row = F._row(raw)
        self.assertEqual(row["artists"], ["Westside Gunn", "Boldy James"])
        history.set_fresh({"export_cutoff": EXPORT_TAIL, "watermark": row["ts"],
                           "listens": [row]})
        self.assertIsNotNone(history.artist_played("Boldy James"))
        self.assertIsNotNone(history.track_played("Westside Gunn", "Song"))
        self.assertIsNone(history.artist_played("Westside Gunn, Boldy James"))

    def test_recent_track_pairs(self):
        doc = overlay(("2026-08-20T10:00:00Z", "Tycho", "Awake"),
                      ("2026-06-01T10:00:00Z", "Air", "Alone"))
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.assertEqual(F.recent_track_pairs(45, now=now, doc=doc), {("tycho", "awake")})
        self.assertEqual(F.recent_track_pairs(45, now=now, doc={}), set())


class TestModelClock(unittest.TestCase):
    def test_reference_date_is_the_newer_clock(self):
        export = date(2026, 7, 18)
        self.assertEqual(M.reference_date(export, {"watermark": "2026-09-05T01:00:00Z"}),
                         date(2026, 9, 5))
        self.assertEqual(M.reference_date(export, {"watermark": None}), export)
        self.assertEqual(M.reference_date(export, {"watermark": "2026-01-01T00:00:00Z"}), export)

    def test_recency_measured_from_the_reference_date(self):
        ref = date(2026, 9, 5)
        self.assertLess(M.recency_weight("2026-07-18", ref), M.recency_weight("2026-07-18", date(2026, 7, 18)))


class TestGuardReadsSameRunLedger(unittest.TestCase):
    def test_out_ledger_counts_as_played(self):
        issues = tempfile.mkdtemp()
        ledger = Path(tempfile.mkdtemp()) / "ledger.json"
        ledger.write_text(json.dumps({"issue": 4, "picks": [
            {"label": "Matt Duncan — Beacon", "module": "singles_rack", "played": True, "plays": 3},
            {"label": "Nobody — Nothing", "module": "singles_rack", "played": False, "plays": 0},
        ]}))
        played = G._played_since(issues, ledger)
        self.assertIn(G.norm_artist("Matt Duncan"), played)
        self.assertNotIn(G.norm_artist("Nobody"), played)
        self.assertEqual(played[G.norm_artist("Matt Duncan")]["issue"], 4)
        self.assertEqual(G._played_since(issues, Path(issues) / "missing.json"), {})


if __name__ == "__main__":
    unittest.main()
