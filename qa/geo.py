# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Canonical great-circle geometry for the QA harness.

Single home for haversine distance / initial bearing / destination-point /
polyline resampling. Before this module the same four formulas were
hand-reimplemented in `drive.py`, `screenshots/sequencer.py`, `feed_zone.py`,
and the edge scenarios (which lazy-imported `scrapers/scripts/make_test_route.py`
just to borrow them) — divergent copies could produce subtly different geometry.

Signatures mirror `scrapers/scripts/make_test_route.py` (scalar lat/lng), which
keeps its own stdlib-only copy on purpose (it must run without `qa/` on the
path). The `atan2` haversine form matches that copy so the two don't drift on
tiny distances.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two lat/lng points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial bearing (degrees, 0–360, north=0) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lng2 - lng1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def destination_point(lat: float, lng: float, bearing: float, distance_m: float) -> tuple[float, float]:
    """Point reached travelling `distance_m` from (lat, lng) along `bearing`."""
    ang = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lng)
    phi2 = math.asin(math.sin(phi1) * math.cos(ang) + math.cos(phi1) * math.sin(ang) * math.cos(theta))
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(ang) * math.cos(phi1),
        math.cos(ang) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), ((math.degrees(lambda2) + 540) % 360) - 180


def polyline_length_m(poly: list[tuple[float, float]]) -> float:
    """Total arc length (metres) of a (lat, lng) polyline."""
    total = 0.0
    for i in range(len(poly) - 1):
        total += haversine_m(poly[i][0], poly[i][1], poly[i + 1][0], poly[i + 1][1])
    return total


def resample_polyline(points: list[tuple[float, float]], step_m: float) -> Iterable[tuple[float, float]]:
    """Yield points evenly spaced by `step_m` along a (lat, lng) polyline.

    Starts with points[0]. The final vertex (points[-1]) is NOT guaranteed to
    be emitted — if the total length is not an exact multiple of step_m, the
    tail past the last sample is dropped. Callers that need explicit endpoints
    must append them after resampling.
    """
    if not points:
        return
    yield points[0]
    carry = 0.0
    for i in range(len(points) - 1):
        lat1, lng1 = points[i]
        lat2, lng2 = points[i + 1]
        seg = haversine_m(lat1, lng1, lat2, lng2)
        if seg == 0:
            continue
        b = bearing_deg(lat1, lng1, lat2, lng2)
        dist_into_seg = step_m - carry
        while dist_into_seg < seg:
            yield destination_point(lat1, lng1, b, dist_into_seg)
            dist_into_seg += step_m
        carry = seg - (dist_into_seg - step_m)
