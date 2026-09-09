import os
import unittest

os.environ.setdefault("SPOTIFY_CLEAN_DIR", "/nonexistent-for-import-only")
from engine.deliver.resolve_tracks import find_track_uri


def _t(name, artist="Someone", uri="spotify:track:x"):
    return {"name": name, "uri": uri, "artists": [{"name": artist}],
            "external_urls": {"spotify": "https://open.spotify.com/track/x"}}


def _searcher(results_by_query):
    def search(token, query, kind, pages=1):
        for key, items in results_by_query.items():
            if key in query:
                return items
        return []
    return search


class NoPrefixGuessing(unittest.TestCase):
    def test_prefix_of_a_longer_title_is_rejected(self):
        s = _searcher({'track:"Love"': [_t("Love Story")]})
        self.assertEqual(find_track_uri("tok", "Someone", "Love", search=s), (None, None))

    def test_longer_request_does_not_accept_a_shorter_title(self):
        s = _searcher({'track:"Love Story"': [_t("Love")]})
        self.assertEqual(find_track_uri("tok", "Someone", "Love Story", search=s), (None, None))

    def test_version_suffix_on_the_catalogue_side_still_matches(self):
        s = _searcher({'track:"Love"': [_t("Love - Remastered 2011", uri="spotify:track:ok")]})
        self.assertEqual(find_track_uri("tok", "Someone", "Love", search=s)[0], "spotify:track:ok")

    def test_decorated_log_title_falls_back_to_its_base(self):
        s = _searcher({'track:"Pink & Blue (feat. Saint Sinner) - RAC Mix"': [],
                       'track:"Pink & Blue"': [_t("Pink & Blue", uri="spotify:track:pb")]})
        self.assertEqual(find_track_uri("tok", "Someone", "Pink & Blue (feat. Saint Sinner) - RAC Mix", search=s)[0],
                         "spotify:track:pb")

    def test_wrong_artist_never_matches(self):
        s = _searcher({'track:"Love"': [_t("Love", artist="Somebody Else")]})
        self.assertEqual(find_track_uri("tok", "Someone", "Love", search=s), (None, None))


if __name__ == "__main__":
    unittest.main()
