# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/scenarios/bulk_loader.py — the in-zone-rebound (flap)
assertion.

Pure-logic coverage (no device): pins the scoping rule that the flap check
applies to the *target* zone only, so the synthetic straight-line approach leg
clipping a curved adjacent zone (e.g. i4-04-east's approach across i4-03-east's
tail) is not a false positive.
"""

import unittest

import _paths  # noqa: F401

from qa.events import ZoneStateChange
from qa.scenarios.bulk_loader import _find_in_zone_rebound


def changes(*specs):
    """Build ZoneStateChange events from (prev, new, zone) triples."""
    return [
        ZoneStateChange(monotonic_ms=i * 1000, raw="", prev=p, new=n,
                        zone=z, speed_kmh=None)
        for i, (p, n, z) in enumerate(specs)
    ]


class InZoneReboundTests(unittest.TestCase):
    def test_clean_target_drive_no_rebound(self):
        seq = changes(
            ("Outside", "InZone", "z1"),
            ("InZone", "Exiting", "z1"),
            ("Exiting", "Outside", "-"),
        )
        self.assertIsNone(_find_in_zone_rebound(seq, "z1"))

    def test_target_zone_flap_is_caught(self):
        seq = changes(
            ("Outside", "InZone", "z1"),
            ("InZone", "Exiting", "z1"),
            ("Exiting", "Outside", "-"),
            ("Outside", "InZone", "z1"),   # rebound into the target
        )
        flap = _find_in_zone_rebound(seq, "z1")
        self.assertIsNotNone(flap)
        self.assertEqual(flap.zone, "z1")

    def test_adjacent_zone_flap_in_approach_is_ignored(self):
        # Mirrors the real i4-04-east failure: the 2 km approach clips the
        # curved tail of the adjacent i4-03-east (which ends exactly where
        # i4-04-east begins), flapping in/out of i4-03-east, then the target
        # zone is driven cleanly. Only the adjacent zone flaps -> not a failure.
        seq = changes(
            ("Outside", "InZone", "i4-03-east"),    # approach clips adjacent
            ("InZone", "Exiting", "i4-03-east"),
            ("Exiting", "Outside", "-"),
            ("Outside", "InZone", "i4-03-east"),    # adjacent rebound (artifact)
            ("InZone", "Exiting", "i4-03-east"),
            ("Exiting", "Outside", "-"),
            ("Outside", "InZone", "i4-04-east"),    # target, clean
            ("InZone", "Exiting", "i4-04-east"),
            ("Exiting", "Outside", "-"),
        )
        self.assertIsNone(_find_in_zone_rebound(seq, "i4-04-east"))

    def test_adjacent_flap_plus_target_flap_still_caught(self):
        # An adjacent flap must not mask a genuine target-zone flap.
        seq = changes(
            ("Outside", "InZone", "i4-03-east"),
            ("InZone", "Exiting", "i4-03-east"),
            ("Exiting", "Outside", "-"),
            ("Outside", "InZone", "i4-03-east"),
            ("InZone", "Exiting", "i4-03-east"),
            ("Exiting", "Outside", "-"),
            ("Outside", "InZone", "i4-04-east"),
            ("InZone", "Exiting", "i4-04-east"),
            ("Exiting", "Outside", "-"),
            ("Outside", "InZone", "i4-04-east"),    # genuine target flap
        )
        flap = _find_in_zone_rebound(seq, "i4-04-east")
        self.assertIsNotNone(flap)
        self.assertEqual(flap.zone, "i4-04-east")


if __name__ == "__main__":
    unittest.main()
