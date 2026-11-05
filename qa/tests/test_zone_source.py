# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/zone_source.py — anchors and the served-catalog snapshot.

Pure-logic coverage (no device, no network). The anchor tests pin the property
the whole live-zones nightly rests on: a scenario's zone survives the upstream
renumbering that broke the nightly on 2026-09-21, when a section inserted at the
head of АМ Тракия turned `trakiya-01-east` into a different stretch of road.
"""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _paths  # noqa: F401

from qa import zone_source

TRAKIYA = "trakiya-vakarel-ihtiman-east"


def bundled() -> dict[str, dict]:
    return copy.deepcopy(zone_source.zones_by_id())


class AnchorTests(unittest.TestCase):
    def test_every_anchor_names_one_zone_of_the_bundled_catalog(self):
        for anchor in zone_source._anchors():
            with self.subTest(anchor=anchor):
                self.assertIn(zone_source.resolve(anchor), zone_source.zones_by_id())

    def test_anchor_follows_its_road_through_a_renumbering(self):
        zones = bundled()
        original = zone_source.resolve(TRAKIYA, zones)
        # What BG TOLL inserting a section ahead of it does: same road, new id,
        # and the old id now belongs to a different section.
        moved = zones.pop(original)
        moved["id"] = "trakiya-02-east"
        decoy = copy.deepcopy(zones["hemus-01-east"])
        decoy["id"] = original
        renumbered = {**zones, "trakiya-02-east": moved, original: decoy}
        self.assertEqual(zone_source.resolve(TRAKIYA, renumbered), "trakiya-02-east")

    def test_opposite_carriageway_is_not_a_match(self):
        zones = bundled()
        zones.pop(zone_source.resolve(TRAKIYA, zones))
        # The westbound twin runs within metres of the anchor point; only the
        # direction keeps it from being picked up.
        with self.assertRaises(zone_source.ZoneAnchorError):
            zone_source.resolve(TRAKIYA, zones)

    def test_section_split_shorter_than_the_scenarios_need_is_refused(self):
        zones = bundled()
        zones[zone_source.resolve(TRAKIYA, zones)]["distance_m"] = 4000
        with self.assertRaisesRegex(zone_source.ZoneAnchorError, "shorter than"):
            zone_source.resolve(TRAKIYA, zones)

    def test_unknown_anchor_names_the_known_ones(self):
        with self.assertRaisesRegex(zone_source.ZoneAnchorError, TRAKIYA):
            zone_source.resolve("trakiya-01-east")


class GeometryTests(unittest.TestCase):
    def test_distance_is_to_the_segment_not_just_its_vertices(self):
        # A point beside the middle of a ~2.2 km segment: ~1.1 km from either
        # vertex, ~55 m from the line itself.
        line = [[42.0, 23.0], [42.02, 23.0]]
        d = zone_source.distance_to_centerline_m(42.01, 23.00067, line)
        self.assertAlmostEqual(d, 55.4, delta=1.0)

    def test_degenerate_centerline_never_matches(self):
        self.assertEqual(
            zone_source.distance_to_centerline_m(42.0, 23.0, [[42.0, 23.0]]), float("inf"))


class SnapshotTests(unittest.TestCase):
    def test_feed_one_is_the_unsuffixed_endpoint(self):
        with mock.patch.object(zone_source, "feed_version", return_value=1):
            self.assertEqual(zone_source.endpoint("zones"), "https://srednabg.com/api/zones")
        with mock.patch.object(zone_source, "feed_version", return_value=2):
            self.assertEqual(zone_source.endpoint("zones"), "https://srednabg.com/api/zones.2")

    def test_download_keeps_the_payload_and_reports_its_identity(self):
        payload = {"version": "2026-09-28T06:12:03Z", "hash": "sha256:abc",
                   "zones": list(bundled().values())[:2]}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(zone_source, "_get_json", return_value=payload):
            snap = zone_source.download_snapshot(Path(tmp) / "nested" / "zones-live.json")
            self.assertEqual((snap.version, snap.hash, snap.zone_count),
                             ("2026-09-28T06:12:03Z", "sha256:abc", 2))
            self.assertTrue(snap.path.exists())

    def test_an_empty_catalog_is_not_a_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(zone_source, "_get_json",
                                  return_value={"hash": "sha256:abc", "zones": []}):
            with self.assertRaises(ValueError):
                zone_source.download_snapshot(Path(tmp) / "zones-live.json")

    def test_live_snapshot_switches_catalog_and_gpx_cache(self):
        self.addCleanup(zone_source.use_bundled)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zones-live.json"
            path.write_text('{"zones": [{"id": "only-01-east"}]}', encoding="utf-8")
            zone_source.use_snapshot(zone_source.Snapshot(
                path=path, version="v", hash="sha256:0123456789abcdef", zone_count=1))
            self.assertTrue(zone_source.is_live())
            self.assertEqual(list(zone_source.zones_by_id()), ["only-01-east"])
            self.assertEqual(zone_source.gpx_dir().name, "live-0123456789ab")
        zone_source.use_bundled()
        self.assertEqual(zone_source.gpx_dir(), zone_source.GPX_FIXTURES_DIR)


if __name__ == "__main__":
    unittest.main()
