# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/drive.py — DrivePlan transforms + synthetic_drive geometry.

Pure-logic coverage (no device): exercises the plan invariants the compression-
dependent edge scenarios rely on.
"""

import unittest

import _paths  # noqa: F401

from qa import geo
from qa.drive import DrivePlan, TrackPoint, synthetic_drive


def plan_1hz(coords):
    """A 1 Hz DrivePlan from (lat, lng) pairs, sim-time == wall-time."""
    return DrivePlan(name="t", points=[
        TrackPoint(lat, lng, i * 1000) for i, (lat, lng) in enumerate(coords)
    ])


class DurationTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(DrivePlan(name="e").duration_ms, 0)

    def test_last_offset(self):
        p = plan_1hz([(42.0, 23.0), (42.0, 23.1), (42.0, 23.2)])
        self.assertEqual(p.duration_ms, 2000)


class CompressedTests(unittest.TestCase):
    def test_identity_factor_returns_self(self):
        p = plan_1hz([(42.0, 23.0), (42.0, 23.1)])
        self.assertIs(p.compressed(1.0), p)

    def test_halves_wallclock_preserves_sim_time(self):
        p = plan_1hz([(42.0, 23.0), (42.0, 23.1), (42.0, 23.2)])
        c = p.compressed(2.0)
        self.assertEqual([pt.t_offset_ms for pt in c.points], [0, 500, 1000])
        # Sim timeline (what the injected fix stamps use) is preserved.
        self.assertEqual([pt.sim_ms for pt in c.points], [0, 1000, 2000])


class DropoutTests(unittest.TestCase):
    def test_removes_points_strictly_inside_gap(self):
        p = plan_1hz([(42.0, 23.0)] * 5)  # offsets 0,1000,2000,3000,4000
        g = p.with_dropout(1000, 3000)
        # Strictly inside (1000, 3000) → only 2000 is removed; the endpoints stay.
        self.assertEqual([pt.t_offset_ms for pt in g.points], [0, 1000, 3000, 4000])


class StopTests(unittest.TestCase):
    def test_inserts_dwell_and_shifts_later_points(self):
        p = plan_1hz([(42.0, 23.0), (42.0, 23.1), (42.0, 23.2)])
        s = p.with_stop(at_ms=1000, duration_ms=5000)
        # Dwell fixes were inserted → more points than the original 3.
        self.assertGreater(len(s.points), len(p.points))
        # The final point is pushed out by the dwell duration.
        self.assertEqual(s.duration_ms, p.duration_ms + 5000)
        # A run of identical coordinates (the held position) appears.
        held = [(pt.lat, pt.lng) for pt in s.points]
        self.assertGreaterEqual(held.count((42.0, 23.1)), 2)


class SyntheticDriveTests(unittest.TestCase):
    def test_needs_two_waypoints(self):
        with self.assertRaises(ValueError):
            synthetic_drive([(42.0, 23.0)])

    def test_uniform_step_spacing(self):
        # 108 km/h @ 1 Hz → 30 m between fixes.
        wps = [(42.0, 23.0), (42.02, 23.0)]  # ~2.2 km due north
        plan = synthetic_drive(wps, speed_kmh=108.0, hz=1.0)
        gaps = [geo.haversine_m(a.lat, a.lng, b.lat, b.lng)
                for a, b in zip(plan.points, plan.points[1:])]
        # Every interior hop is one step (30 m); only the final hop onto the
        # exact waypoint may be shorter.
        for g in gaps[:-1]:
            self.assertAlmostEqual(g, 30.0, delta=1.0)
        self.assertLessEqual(gaps[-1], 30.0 + 1.0)

    def test_1hz_timestamps(self):
        plan = synthetic_drive([(42.0, 23.0), (42.02, 23.0)], speed_kmh=108.0, hz=1.0)
        offs = [pt.t_offset_ms for pt in plan.points]
        self.assertEqual(offs, list(range(0, len(offs) * 1000, 1000)))


if __name__ == "__main__":
    unittest.main()
