"""Tests for mix artwork resolution, per source.

Run:  PYTHONPATH=<root> python3 -m engine.lib.test_media
"""

import unittest

from engine import art
from engine.lib import media as M

WIKITEXT = """{|{{NormalTableFormat}}
{{Player|mode=mirrors
 |https://youtu.be/_d_8fp8dneI
 |https://soundcloud.com/platform/cassius-paris-thursday
}}
# [00:00] Cassius - The Sound of Violence [Virgin]
"""


class TestUrls(unittest.TestCase):
    def test_youtube_ids_in_every_form(self):
        for u in ("https://youtu.be/_d_8fp8dneI", "https://www.youtube.com/watch?v=_d_8fp8dneI",
                  "https://www.youtube.com/watch?feature=share&v=_d_8fp8dneI&t=10",
                  "https://youtube.com/embed/_d_8fp8dneI", "https://m.youtube.com/shorts/_d_8fp8dneI"):
            self.assertEqual(M.youtube_id(u), "_d_8fp8dneI", u)
        self.assertIsNone(M.youtube_id("https://soundcloud.com/x/y"))

    def test_player_urls_from_wikitext(self):
        self.assertEqual(M.player_urls(WIKITEXT),
                         ["https://youtu.be/_d_8fp8dneI",
                          "https://soundcloud.com/platform/cassius-paris-thursday"])

    def test_embed_frames_and_other_hosts_are_ignored(self):
        text = ("https://w.soundcloud.com/player/?url=https://soundcloud.com/a/b "
                "https://www.mixesdb.com/w/Other https://www.mixcloud.com/NTSRadio/deadboy/")
        self.assertEqual(M.player_urls(text), ["https://www.mixcloud.com/NTSRadio/deadboy/"])

    def test_mixesdb_title_from_url(self):
        self.assertEqual(
            M.mixesdb_title("https://www.mixesdb.com/w/2026-05-07_-_Boombass_%28Cassius%29_%40_Boiler_Room%2C_Paris"),
            "2026-05-07 - Boombass (Cassius) @ Boiler Room, Paris")
        self.assertIsNone(M.mixesdb_title("https://www.nts.live/shows/x"))

    def test_kexp_show_id(self):
        self.assertEqual(M.kexp_show_id("https://www.kexp.org/playlist/2026/8/23/#show-67604"), "67604")
        self.assertIsNone(M.kexp_show_id("https://www.kexp.org/"))


class TestThumbnails(unittest.TestCase):
    def test_youtube_prefers_maxres_when_it_exists(self):
        self.assertEqual(M.youtube_thumbnail("https://youtu.be/_d_8fp8dneI", head=lambda u: True),
                         "https://i.ytimg.com/vi/_d_8fp8dneI/maxresdefault.jpg")
        self.assertEqual(M.youtube_thumbnail("https://youtu.be/_d_8fp8dneI", head=lambda u: False),
                         "https://i.ytimg.com/vi/_d_8fp8dneI/hqdefault.jpg")

    def test_first_thumbnail_puts_youtube_first(self):
        urls = ["https://soundcloud.com/platform/cassius", "https://youtu.be/_d_8fp8dneI"]
        self.assertEqual(M.first_thumbnail(urls, head=lambda u: True),
                         "https://i.ytimg.com/vi/_d_8fp8dneI/maxresdefault.jpg")

    def test_unknown_hosts_yield_nothing(self):
        self.assertIsNone(M.thumbnail("https://www.kexp.org/playlist/2026/8/23/"))
        self.assertIsNone(M.first_thumbnail([]))

    def test_kexp_programme_art_then_host_photo(self):
        url = "https://www.kexp.org/playlist/2026/8/23/#show-67604"
        self.assertEqual(M.kexp_cover(url, fetch=lambda u: {"program_image_uri": "p.jpg", "image_uri": "h.jpg"}), "p.jpg")
        self.assertEqual(M.kexp_cover(url, fetch=lambda u: {"image_uri": "h.jpg"}), "h.jpg")
        self.assertIsNone(M.kexp_cover(url, fetch=lambda u: {}))
        self.assertIsNone(M.kexp_cover("https://www.kexp.org/", fetch=lambda u: 1 / 0))

    def test_mixesdb_players_from_a_page(self):
        url = "https://www.mixesdb.com/w/2026-05-07_-_Boombass_%28Cassius%29_%40_Boiler_Room%2C_Paris"
        self.assertEqual(M.mixesdb_players(url, wikitext=WIKITEXT)[0], "https://youtu.be/_d_8fp8dneI")
        self.assertEqual(M.mixesdb_players("https://www.nts.live/x", wikitext=WIKITEXT), [])


class TestMixCoverDispatch(unittest.TestCase):
    """engine.art.mix_cover picks the source rule and fills listen links."""

    def test_kexp_uses_the_programme_art(self):
        x = {"station": "KEXP", "url": "https://www.kexp.org/playlist/2026/8/23/#show-67604", "listen_urls": []}
        cover = art.mix_cover(x, kexp=lambda u: "https://www.kexp.org/media/theroadhouse-800x800.jpg",
                              players=lambda u: [], thumb=lambda urls: None)
        self.assertEqual(cover, "https://www.kexp.org/media/theroadhouse-800x800.jpg")

    def test_mixesdb_uses_the_youtube_still_and_records_the_mirrors(self):
        x = {"station": "Boiler Room",
             "url": "https://www.mixesdb.com/w/2026-05-07_-_Boombass_%28Cassius%29_%40_Boiler_Room%2C_Paris",
             "listen_urls": []}
        mirrors = ["https://youtu.be/_d_8fp8dneI", "https://soundcloud.com/platform/cassius-paris-thursday"]
        cover = art.mix_cover(x, kexp=lambda u: None, players=lambda u: mirrors,
                              thumb=lambda urls: "https://i.ytimg.com/vi/_d_8fp8dneI/maxresdefault.jpg" if urls else None)
        self.assertEqual(cover, "https://i.ytimg.com/vi/_d_8fp8dneI/maxresdefault.jpg")
        self.assertEqual(x["listen_urls"], mirrors)          # backfilled for the reader

    def test_existing_listen_links_are_kept_and_used(self):
        x = {"station": None, "url": "https://www.nts.live/shows/a/episodes/b",
             "listen_urls": ["https://soundcloud.com/x/y"]}
        calls = []
        cover = art.mix_cover(x, nts=lambda u: None, kexp=lambda u: None,
                              players=lambda u: calls.append(u) or [],
                              thumb=lambda urls: "sc.jpg" if urls else None)
        self.assertEqual(cover, "sc.jpg")
        self.assertEqual(x["listen_urls"], ["https://soundcloud.com/x/y"])
        self.assertEqual(calls, [])                           # no page fetch for NTS

    def test_nts_picture_wins_when_present(self):
        x = {"url": "https://www.nts.live/shows/a/episodes/b", "listen_urls": ["https://youtu.be/_d_8fp8dneI"]}
        self.assertEqual(art.mix_cover(x, nts=lambda u: "nts.jpg", thumb=lambda urls: "yt.jpg"), "nts.jpg")

    def test_nothing_anywhere_stays_none(self):
        x = {"station": "KEXP", "url": "https://www.kexp.org/playlist/2026/9/5/#show-1", "listen_urls": []}
        self.assertIsNone(art.mix_cover(x, kexp=lambda u: None, players=lambda u: [], thumb=lambda urls: None))


if __name__ == "__main__":
    unittest.main()
