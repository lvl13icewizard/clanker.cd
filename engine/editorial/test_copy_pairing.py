"""Tests for the copy → release note pairing (writer) and the validator's
note guard. Pure functions, no data or network.

Run:  python3 -m unittest engine.editorial.test_copy_pairing -v
"""

import unittest

from engine.editorial import validate as V
from engine.editorial.writer import _pair_release_notes, _release_stat_forms


def _rel(artist, title, rtype, date):
    return {"artist": artist, "title": title, "release_type": rtype,
            "release_date": date, "relationship": "played", "via": None,
            "note": None}


def _row(plays, hours, skip, unique):
    return {"plays": str(plays), "hours": str(hours), "skip_rate": str(skip),
            "unique_tracks": str(unique)}


# Issue 002's actual list, in proposal order, with its artist rows.
BASE = [
    _rel("Bonobo", "Always on Your Side", "ep", "2026-08-03"),
    _rel("Bonobo", "Fire on the Water / Drift", "single", "2026-07-07"),
    _rel("Jacques Greene", "Closer", "single", "2026-07-08"),
    _rel("Denzel Curry", "ii", "album", "2026-08-21"),
    _rel("The Alchemist", "Sorry, we don't have an album title yet ...",
         "album", "2026-08-28"),
    _rel("Larry June", "Who Coppin", "album", "2026-07-17"),
    _rel("Emancipator", "The Painted Lady", "single", "2026-07-24"),
    _rel("Blockhead", "Boatshoes", "album", "2026-07-17"),
    _rel("Fontaines D.C.", "Marianne", "single", "2026-08-18"),
    _rel("Bibio", "Shame", "single", "2026-07-22"),
]
ROWS = {
    "Bonobo": _row(420, 20.8, 0.19, 66),
    "Jacques Greene": _row(315, 14.7, 0.07, 52),
    "Denzel Curry": _row(701, 23.5, 0.23, 64),
    "The Alchemist": _row(574, 12.8, 0.35, 115),
    "Larry June": _row(471, 13.6, 0.59, 91),
    "Emancipator": _row(403, 13.3, 0.11, 85),
    "Blockhead": _row(313, 12.0, 0.28, 70),
    "Fontaines D.C.": _row(179, 8.0, 0.36, 40),
    "Bibio": _row(222, 7.8, 0.07, 60),
}
FORMS = [_release_stat_forms(
    {"artist": r["artist"], "verification": {"artist_row": ROWS[r["artist"]]}},
    None) for r in BASE]

# The copy as written for Issue 002: editorial order, no identity keys.
COPY_002 = [
    {"note": "Out today, from an artist with 701 plays and 23.5 hours in the "
             "record — a top-25 name whose last album arrived in your biggest "
             "listening year."},
    {"note": "A new Bonobo EP; 420 plays and 20.8 hours say this gets opened."},
    {"note": "The producer's producer, and a full album. Alchemist beats are all "
             "over the Griselda records you have played to death."},
    {"note": "Larry June's unhurried Bay-area cool — an album, not a teaser."},
    {"note": "Fontaines D.C. sit inside the rising punk lane; anything they "
             "release is on the path."},
    {"note": "313 plays and 12 hours deep — a new Blockhead record is a "
             "guaranteed week of instrumentals."},
    {"note": "403 plays of downtempo at an 11% skip rate, quiet since spring."},
    {"note": "7% skip over 222 plays since 2019 — the freshest thread in the pool."},
]
EXPECTED_002 = {0: 1, 1: None, 2: None, 3: 0, 4: 2, 5: 3, 6: 6, 7: 5, 8: 4, 9: 7}


def pair(copy, base=BASE, forms=FORMS, date="2026-08-21"):
    notes = []
    over = _pair_release_notes(base, copy, forms, date, notes)
    return over, notes


def targets(over, copy):
    """base index -> copy index of the note it received (None if none)."""
    by_text = {e.get("note"): i for i, e in enumerate(copy) if isinstance(e, dict)}
    return {i: (by_text.get(o.get("note")) if o else None)
            for i, o in enumerate(over)}


class Issue002(unittest.TestCase):
    def test_editorial_order_is_repaired(self):
        over, notes = pair(COPY_002)
        self.assertEqual(targets(over, COPY_002), EXPECTED_002)
        self.assertTrue(any("8 of 8 copy notes attached" in n for n in notes), notes)
        self.assertFalse(any("REFUSED" in n for n in notes), notes)

    def test_bonobo_note_goes_to_the_ep(self):
        over, _ = pair(COPY_002)
        self.assertIn("EP", over[0]["note"])
        self.assertEqual(over[1], {})

    def test_identity_keys_win(self):
        copy = [{"artist": "Denzel Curry", "note": "No numbers, no name."},
                {"artist": "Bonobo", "title": "Fire on the Water / Drift",
                 "note": "Two sides."},
                {"artist": "Bonobo", "release_type": "ep", "note": "Four sides."}]
        over, notes = pair(copy)
        self.assertEqual(over[3], {"note": "No numbers, no name."})
        self.assertEqual(over[1], {"note": "Two sides."})
        self.assertEqual(over[0], {"note": "Four sides."})
        self.assertFalse(any("REFUSED" in n for n in notes), notes)

    def test_identity_tolerates_the(self):
        over, _ = pair([{"artist": "Alchemist", "note": "Beats."}])
        self.assertEqual(over[4], {"note": "Beats."})

    def test_identity_contradicted_by_numbers_is_refused(self):
        over, notes = pair([{"artist": "Bonobo",
                             "note": "701 plays and 23.5 hours."}])
        self.assertTrue(all(o == {} for o in over))
        self.assertTrue(any("REFUSED" in n and "Denzel Curry" in n for n in notes), notes)

    def test_identity_contradicted_by_name_is_refused(self):
        over, notes = pair([{"artist": "Bonobo", "note": "Larry June's week."}])
        self.assertTrue(all(o == {} for o in over))
        self.assertTrue(any("REFUSED" in n for n in notes), notes)

    def test_unknown_identity_is_refused(self):
        over, notes = pair([{"artist": "Tycho", "note": "Not in this list."}])
        self.assertTrue(all(o == {} for o in over))
        self.assertTrue(any("not a listed release artist" in n for n in notes), notes)

    def test_numbers_pointing_elsewhere_than_the_name_refuse(self):
        over, notes = pair([{"note": "Bonobo, 701 plays."}])
        self.assertTrue(all(o == {} for o in over))
        self.assertTrue(any("REFUSED" in n for n in notes), notes)

    def test_numbers_of_two_artists_are_ambiguous(self):
        over, notes = pair([{"note": "701 plays here, 420 there."}])
        self.assertTrue(all(o == {} for o in over))
        self.assertTrue(any("several listed artists" in n for n in notes), notes)

    def test_name_breaks_a_numbers_tie(self):
        note = "Denzel Curry: 701 plays, against the 420 of the runner-up."
        over, _ = pair([{"note": note}])
        self.assertEqual(over[3], {"note": note})

    def test_both_named_and_both_quoted_is_ambiguous(self):
        over, notes = pair([{"note": "Denzel Curry: 701 plays to Bonobo's 420."}])
        self.assertTrue(all(o == {} for o in over))
        self.assertTrue(any("several listed artists" in n for n in notes), notes)

    def test_today_picks_within_an_artist(self):
        base = [_rel("Bonobo", "A", "single", "2026-08-21"),
                _rel("Bonobo", "B", "single", "2026-08-01")]
        forms = [set(), set()]
        over, _ = pair([{"note": "Out today: Bonobo."}], base, forms)
        self.assertEqual(over[0], {"note": "Out today: Bonobo."})
        over, _ = pair([{"note": "Out today: Bonobo."}], base, forms, date="2026-08-01")
        self.assertEqual(over[1], {"note": "Out today: Bonobo."})

    def test_title_picks_within_an_artist(self):
        over, _ = pair([{"note": "Bonobo — Fire on the Water / Drift, two sides."}])
        self.assertEqual(over[1]["note"], "Bonobo — Fire on the Water / Drift, two sides.")
        self.assertEqual(over[0], {})


class Positional(unittest.TestCase):
    def test_aligned_copy_keeps_position(self):
        copy = [{"note": "Plain note, no evidence."},
                {"note": "Another plain one."},
                {"note": "Jacques Greene, again."}]
        over, notes = pair(copy)
        self.assertEqual(over[0], {"note": "Plain note, no evidence."})
        self.assertEqual(over[1], {"note": "Another plain one."})
        self.assertEqual(over[2], {"note": "Jacques Greene, again."})
        self.assertTrue(any("2 by position" in n for n in notes), notes)
        self.assertTrue(any("add artist keys" in n for n in notes), notes)

    def test_reordered_copy_refuses_evidence_less_notes(self):
        copy = [{"note": "Denzel Curry, out today."},   # belongs at 3 — moved
                {"note": "Plain note, no evidence."}]
        over, notes = pair(copy)
        self.assertEqual(over[3], {"note": "Denzel Curry, out today."})
        self.assertEqual(over[1], {})
        self.assertTrue(any("REFUSED" in n and "not in proposal order" in n
                            for n in notes), notes)

    def test_overflow_position_is_refused(self):
        copy = [{"note": "x"}] * 10 + [{"note": "eleventh"}]
        over, notes = pair(copy)
        self.assertEqual(len(over), 10)
        self.assertTrue(any("beyond the 10 listed releases" in n for n in notes), notes)

    def test_only_note_key_passes_through(self):
        over, _ = pair([{"artist": "Alchemist", "release_type": "album",
                         "note": "Beats.", "title": "wrong title on purpose"}])
        # a wrong title narrows to nothing: refused rather than overwriting
        self.assertEqual(over[4], {})
        over, _ = pair([{"artist": "Alchemist", "note": "Beats."}])
        self.assertEqual(list(over[4].keys()), ["note"])

    def test_empty_note_attaches_nothing(self):
        over, notes = pair([{"artist": "Bibio", "note": ""}])
        self.assertTrue(all(o == {} for o in over))

    def test_one_release_per_note(self):
        copy = [{"note": "Bibio, one."}, {"note": "Bibio, two."}]
        over, notes = pair(copy)
        self.assertEqual(over[9], {"note": "Bibio, one."})
        self.assertTrue(any("REFUSED" in n and "no unclaimed" in n for n in notes), notes)


class ValidatorGuard(unittest.TestCase):
    def _module(self, notes_by_index):
        rel = [dict(r) for r in BASE]
        for i, t in notes_by_index.items():
            rel[i]["note"] = t
        return {"type": "new_this_week", "intro": "x", "releases": rel}

    def _errors(self, module):
        errors = []
        V._check_module(module, 0, 2, errors)
        return errors

    def test_correct_pairing_passes(self):
        m = self._module({3: COPY_002[0]["note"], 0: COPY_002[1]["note"],
                          4: COPY_002[2]["note"], 5: COPY_002[3]["note"],
                          8: COPY_002[4]["note"], 7: COPY_002[5]["note"],
                          6: COPY_002[6]["note"], 9: COPY_002[7]["note"]})
        self.assertEqual(self._errors(m), [])

    def test_wrong_artist_is_a_violation(self):
        m = self._module({3: "Larry June's unhurried Bay-area cool."})
        errs = self._errors(m)
        self.assertEqual(len(errs), 1)
        self.assertIn("names 'Larry June'", errs[0])

    def test_mentioning_own_and_another_is_fine(self):
        m = self._module({3: "Denzel Curry, with The Alchemist on the boards."})
        self.assertEqual(self._errors(m), [])

    def test_wrong_release_type_of_same_artist_is_a_violation(self):
        m = self._module({1: "A new Bonobo EP; 420 plays."})
        errs = self._errors(m)
        self.assertEqual(len(errs), 1)
        self.assertIn("'Bonobo''s ep", errs[0])

    def test_type_word_without_a_sibling_is_fine(self):
        m = self._module({9: "Bibio's EP-length single."})  # no Bibio EP listed
        self.assertEqual(self._errors(m), [])

    def test_mentions(self):
        self.assertTrue(V.mentions_artist("Alchemist beats", "The Alchemist"))
        self.assertTrue(V.mentions_artist("Fontaines D.C. sit", "Fontaines D.C."))
        self.assertTrue(V.mentions_artist("Larry June's cool", "Larry June"))
        self.assertFalse(V.mentions_artist("a low skip rate", "Low"))
        self.assertFalse(V.mentions_artist("bonoboland", "Bonobo"))
        self.assertEqual(V.release_type_mentions("a new Blockhead record"), set())
        self.assertEqual(V.release_type_mentions("A new Bonobo EP"), {"ep"})


if __name__ == "__main__":
    unittest.main()
