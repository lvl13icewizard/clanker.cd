import unittest
from engine.lib.normalize import norm_artist, norm_title, strip_versions, track_key


class NonLatinIdentity(unittest.TestCase):
    NAMES = ["宇多田ヒカル", "椎名林檎", "周杰倫", "아이유", "Молчат Дома"]

    def test_every_script_keeps_a_key(self):
        keys = [norm_artist(n) for n in self.NAMES]
        self.assertTrue(all(keys), keys)

    def test_distinct_names_stay_distinct(self):
        self.assertEqual(len({norm_artist(n) for n in self.NAMES}), len(self.NAMES))

    def test_hangul_is_stable_across_unicode_forms(self):
        import unicodedata
        nfc, nfd = "아이유", unicodedata.normalize("NFD", "아이유")
        self.assertNotEqual(nfc, nfd)
        self.assertEqual(norm_artist(nfc), norm_artist(nfd))

    def test_latin_diacritics_still_fold(self):
        self.assertEqual(norm_artist("Björk"), norm_artist("Bjork"))
        self.assertEqual(norm_artist("Beyoncé"), "beyonce")

    def test_punctuation_only_names_do_not_collapse_together(self):
        self.assertTrue(norm_artist("!!!"))
        self.assertNotEqual(norm_artist("!!!"), norm_artist("†††"))

    def test_empty_stays_empty(self):
        self.assertEqual(norm_artist(""), "")
        self.assertEqual(norm_artist("   "), "")


class VersionTails(unittest.TestCase):
    def test_version_word_anywhere_in_the_tail_strips_it(self):
        for t in ("Song - Remix", "Song - Jay Dee Remix", "Song - Live at Leeds",
                  "Song - 2019 Remaster", "Song (Jay Dee Remix)", "Song [Live] (Remastered)",
                  "Song - Original Mix", "Song (feat. X) - Radio Edit"):
            self.assertEqual(norm_title(t), "song", t)

    def test_a_dash_without_a_version_word_is_part_of_the_title(self):
        self.assertEqual(norm_title("Song - Part 2"), "song part 2")
        self.assertEqual(norm_title("Love - Story"), "love story")

    def test_strip_versions_keeps_case_for_the_search_string(self):
        self.assertEqual(strip_versions("Pink & Blue (feat. Saint Sinner) - RAC Mix"), "Pink & Blue")

    def test_track_key_pairs(self):
        self.assertEqual(track_key("Björk", "Hyperballad - Live"), ("bjork", "hyperballad"))


if __name__ == "__main__":
    unittest.main()
