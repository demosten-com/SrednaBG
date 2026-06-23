# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/geo.py — the canonical great-circle helpers."""

import math
import unittest

import _paths  # noqa: F401

from qa import geo

SOFIA = (42.6975, 23.3242)
PLOVDIV = (42.1354, 24.7453)


class HaversineTests(unittest.TestCase):
    def test_zero_distance(self):
        self.assertEqual(geo.haversine_m(*SOFIA, *SOFIA), 0.0)

    def test_symmetric(self):
        d1 = geo.haversine_m(*SOFIA, *PLOVDIV)
        d2 = geo.haversine_m(*PLOVDIV, *SOFIA)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_known_distance(self):
        # Sofia ↔ Plovdiv is ~132 km great-circle.
        d_km = geo.haversine_m(*SOFIA, *PLOVDIV) / 1000.0
        self.assertAlmostEqual(d_km, 132.3, delta=2.0)

    def test_one_degree_latitude_is_about_111km(self):
        d = geo.haversine_m(42.0, 23.0, 43.0, 23.0)
        self.assertAlmostEqual(d / 1000.0, 111.2, delta=0.5)


class BearingTests(unittest.TestCase):
    def test_due_north(self):
        self.assertAlmostEqual(geo.bearing_deg(42.0, 23.0, 43.0, 23.0), 0.0, delta=0.1)

    def test_due_east(self):
        self.assertAlmostEqual(geo.bearing_deg(42.0, 23.0, 42.0, 24.0), 90.0, delta=0.5)

    def test_range_is_0_to_360(self):
        b = geo.bearing_deg(42.0, 23.0, 41.0, 22.0)  # heading roughly south-west
        self.assertTrue(0.0 <= b < 360.0)
        self.assertAlmostEqual(b, 215.0, delta=10.0)


class DestinationPointTests(unittest.TestCase):
    def test_roundtrips_with_bearing_and_distance(self):
        dist = geo.haversine_m(*SOFIA, *PLOVDIV)
        brg = geo.bearing_deg(*SOFIA, *PLOVDIV)
        lat, lng = geo.destination_point(SOFIA[0], SOFIA[1], brg, dist)
        # Walking `dist` along the initial bearing lands on Plovdiv (tiny
        # great-circle error since bearing changes along the path).
        self.assertLess(geo.haversine_m(lat, lng, *PLOVDIV), 1.0)

    def test_longitude_normalized(self):
        _, lng = geo.destination_point(42.0, 179.9, 90.0, 50_000.0)
        self.assertTrue(-180.0 <= lng <= 180.0)


class PolylineTests(unittest.TestCase):
    def test_length_sums_segments(self):
        poly = [(42.0, 23.0), (42.0, 23.1), (42.1, 23.1)]
        expected = (geo.haversine_m(42.0, 23.0, 42.0, 23.1)
                    + geo.haversine_m(42.0, 23.1, 42.1, 23.1))
        self.assertAlmostEqual(geo.polyline_length_m(poly), expected, places=6)

    def test_resample_uniform_spacing(self):
        poly = [(42.0, 23.0), (42.05, 23.0)]  # ~5.5 km due north
        step = 500.0
        pts = list(geo.resample_polyline(poly, step))
        self.assertEqual(pts[0], poly[0])  # starts at first vertex
        # Interior samples are `step` apart (within a metre).
        for a, b in zip(pts, pts[1:]):
            self.assertAlmostEqual(geo.haversine_m(a[0], a[1], b[0], b[1]), step, delta=1.0)
        # Roughly length/step samples (final tail past the last step is dropped).
        self.assertEqual(len(pts), math.floor(geo.polyline_length_m(poly) / step) + 1)

    def test_resample_empty(self):
        self.assertEqual(list(geo.resample_polyline([], 100.0)), [])


if __name__ == "__main__":
    unittest.main()
