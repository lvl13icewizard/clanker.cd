"""Tests for Singles Rack lane interleaving and lane-aware backfill
(audit F13).

Run:  PYTHONPATH=<root> python3 -m engine.editorial.test_rack_order
"""

import unittest

from engine.deliver.resolve_tracks import backfill_singles
from engine.editorial.writer import RACK_LANE_FLOOR, rack_ranked


def it(artist, score):
    return {"artist": artist, "score": score, "via": "seed"}


class TestInterleave(unittest.TestCase):
    def test_a_slightly_weaker_lane_is_not_shut_out(self):
        """The reproduced defect: ten lane-A leads at 1.00..0.91 and one
        lane-B lead at 0.90 gave a rack of ten A's."""
        prop = {"singles_rack": {
            "lane-a": [it(f"A{i}", 1.0 - i * 0.01) for i in range(10)],
            "lane-b": [it("B1", 0.90)],
        }}
        top = [cid for cid, _ in rack_ranked(prop)[:10]]
        self.assertIn("lane-b", top)
        self.assertEqual(top[:2], ["lane-a", "lane-b"])

    def test_round_robin_across_lanes_strongest_lane_first(self):
        prop = {"singles_rack": {
            "x": [it("X1", 0.7), it("X2", 0.65)],
            "y": [it("Y1", 0.9), it("Y2", 0.8)],
            "z": [it("Z1", 0.8)],
        }}
        got = [(cid, i["artist"]) for cid, i in rack_ranked(prop)]
        self.assertEqual(got, [("y", "Y1"), ("z", "Z1"), ("x", "X1"),
                               ("y", "Y2"), ("x", "X2")])

    def test_a_lane_under_the_floor_yields_its_turn(self):
        prop = {"singles_rack": {
            "strong": [it("S1", 1.0), it("S2", 0.95), it("S3", 0.9)],
            "weak": [it("W1", RACK_LANE_FLOOR * 1.0 - 0.05)],
        }}
        got = [i["artist"] for _, i in rack_ranked(prop)]
        self.assertEqual(got[:3], ["S1", "S2", "S3"])
        self.assertEqual(got[-1], "W1")     # still ranked, just not forced up

    def test_artists_appear_once_across_lanes(self):
        prop = {"singles_rack": {
            "a": [it("Same Name", 0.9), it("A2", 0.5)],
            "b": [it("same name", 0.8), it("B2", 0.7)],
        }}
        got = [i["artist"].lower() for _, i in rack_ranked(prop)]
        self.assertEqual(got.count("same name"), 1)
        self.assertEqual(len(got), 3)

    def test_deterministic_and_complete(self):
        prop = {"singles_rack": {"a": [it("A1", 0.5)], "b": [it("B1", 0.5)],
                                 "c": []}}
        self.assertEqual(rack_ranked(prop), rack_ranked(prop))
        self.assertEqual(len(rack_ranked(prop)), 2)
        self.assertEqual(rack_ranked({}), [])


class TestBackfillKeepsTheMix(unittest.TestCase):
    def rack(self, *entries):
        return {"modules": [{"type": "singles_rack", "tracks": list(entries)}]}

    def slot(self, artist, lane, uri=None):
        return {"artist": artist, "title": None if uri is None else "T",
                "cluster": lane, "why": "w", "receipts": [],
                "spotify_track_uri": uri, "spotify_url": None}

    @staticmethod
    def search(_token, query, _kind, pages=1):
        name = query.split('artist:"')[-1].rstrip('"') if 'artist:"' in query else query
        return [{"name": "Song", "artists": [{"name": name}],
                 "uri": "spotify:track:" + name.lower().replace(" ", "")}]

    def test_replacement_comes_from_the_emptied_slots_lane_first(self):
        doc = self.rack(self.slot("A1", "lane-a", "spotify:track:a1"),
                        self.slot("B1", "lane-b"))
        reserves = [("lane-a", it("A9", 0.9)), ("lane-b", it("B9", 0.5))]
        filled, exhausted = backfill_singles(
            doc, None, set(), reserves, {}, 5,
            search=self.search, played=lambda *a, **k: None)
        self.assertEqual((filled, exhausted), (1, []))
        self.assertEqual(doc["modules"][0]["tracks"][1]["artist"], "B9")

    def test_falls_back_to_the_next_reserve_when_the_lane_is_empty(self):
        doc = self.rack(self.slot("B1", "lane-b"))
        reserves = [("lane-a", it("A9", 0.9)), ("lane-c", it("C9", 0.8))]
        backfill_singles(doc, None, set(), reserves, {}, 5,
                         search=self.search, played=lambda *a, **k: None)
        self.assertEqual(doc["modules"][0]["tracks"][0]["artist"], "A9")


if __name__ == "__main__":
    unittest.main()
