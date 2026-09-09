import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("SPOTIFY_CLEAN_DIR", "/nonexistent-for-import-only")
from engine.ledger.build_ledger import grade

DAY = 86400
PUB = datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc)
PUB_TS = int(PUB.timestamp())


def _issue(**cp):
    return {
        "issue": 4, "date": "2026-09-05",
        "generated": {"generated_at": "2026-09-05T13:20:30+00:00"},
        "companion_playlist": {"published_at": PUB.isoformat(), **cp},
        "modules": [
            {"type": "singles_rack", "tracks": [{"artist": "New Name", "title": "Door"}]},
            {"type": "revival_desk", "tracks": [{"artist": "Tycho", "title": "Skate"}]},
            {"type": "catalog_room", "artist": "Old Favorite",
             "unheard": [{"title": "Unheard A"}, {"title": "Unheard B"}]},
        ],
    }


def _listen(ts, artist, track, release=None):
    md = {"artist_name": artist, "track_name": track}
    if release:
        md["release_name"] = release
    return {"listened_at": ts, "track_metadata": md}


class CatalogAdoptionIsAlbumLevel(unittest.TestCase):
    def test_playing_the_familiar_artist_credits_no_album(self):
        listens = [_listen(PUB_TS + DAY, "Old Favorite", "Hit One", "Greatest Hits"),
                   _listen(PUB_TS + DAY + 60, "Old Favorite", "Hit Two", "Greatest Hits")]
        doc = grade(_issue(), listens, now=PUB + __import__("datetime").timedelta(days=7))
        cat = [p for p in doc["picks"] if p["module"] == "catalog_room"]
        self.assertEqual([p["played"] for p in cat], [False, False])
        self.assertEqual([p["match_basis"] for p in cat], ["album", "album"])
        self.assertEqual([p["artist_plays"] for p in cat], [2, 2])   # visible, not counted
        self.assertEqual(doc["summary"]["by_module"]["catalog_room"], {"total": 2, "played": 0})

    def test_a_track_from_the_unheard_album_does_count(self):
        listens = [_listen(PUB_TS + DAY, "Old Favorite", "Deep Cut", "Unheard A")]
        doc = grade(_issue(), listens, now=PUB + __import__("datetime").timedelta(days=7))
        cat = {p["label"]: p["played"] for p in doc["picks"] if p["module"] == "catalog_room"}
        self.assertEqual(cat, {"Old Favorite — Unheard A": True, "Old Favorite — Unheard B": False})


class ReturnMeansALaterDay(unittest.TestCase):
    def _doc(self, listens):
        return grade(_issue(), listens, now=PUB + __import__("datetime").timedelta(days=7))

    def test_two_plays_in_one_sitting_is_not_a_return(self):
        doc = self._doc([_listen(PUB_TS + 100, "New Name", "Door"),
                         _listen(PUB_TS + 400, "New Name", "Door")])
        self.assertEqual(doc["summary"]["returned_to"], [])
        self.assertEqual(doc["picks"][0]["play_days"], 1)

    def test_a_play_on_a_later_day_is(self):
        doc = self._doc([_listen(PUB_TS + 100, "New Name", "Door"),
                         _listen(PUB_TS + 2 * DAY, "New Name", "Door")])
        self.assertEqual(doc["summary"]["returned_to"], ["New Name — Door"])


class PublicationTime(unittest.TestCase):
    def test_listens_before_publish_are_excluded_even_on_the_issue_date(self):
        # 09:00 on the issue date, but the playlist went up at 14:00
        listens = [_listen(PUB_TS - 5 * 3600, "New Name", "Door")]
        doc = grade(_issue(), listens, now=PUB + __import__("datetime").timedelta(days=7))
        self.assertFalse(doc["picks"][0]["played"])
        self.assertEqual(doc["published_basis"], "published_at")

    def test_falls_back_to_generated_at_then_date(self):
        issue = _issue(); issue["companion_playlist"].pop("published_at")
        self.assertEqual(grade(issue, [])["published_basis"], "generated_at")
        issue["generated"] = {}
        self.assertEqual(grade(issue, [])["published_basis"], "date_midnight_utc")


class RevivalIsTrackLevel(unittest.TestCase):
    def test_same_artist_other_song_does_not_count(self):
        listens = [_listen(PUB_TS + DAY, "Tycho", "Awake")]
        doc = grade(_issue(), listens)
        rev = [p for p in doc["picks"] if p["module"] == "revival_desk"][0]
        self.assertFalse(rev["played"]); self.assertEqual(rev["match_basis"], "track")


if __name__ == "__main__":
    unittest.main()
