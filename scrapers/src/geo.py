# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Shared geodesic helpers used across the scraper pipeline."""

import math

EARTH_RADIUS_M = 6371000


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in meters between two points."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute bearing in degrees from point 1 to point 2."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlng)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def polyline_length_m(centerline: list[list[float]]) -> float:
    """Total arc length (m) of a [[lat, lng], ...] polyline."""
    return sum(
        haversine_m(centerline[i - 1][0], centerline[i - 1][1],
                    centerline[i][0], centerline[i][1])
        for i in range(1, len(centerline))
    )


def point_to_polyline_m(lat: float, lng: float,
                        polyline: list[list[float]]) -> float:
    """Minimum distance (m) from a point to a [[lat, lng], ...] polyline.

    Uses a local equirectangular projection around the query point — accurate
    for the short (sub-km) distances this is used for. Returns ``inf`` for a
    polyline with fewer than two points.
    """
    if len(polyline) < 2:
        return float("inf")

    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat))

    def to_xy(plat: float, plng: float) -> tuple[float, float]:
        return ((plng - lng) * m_per_deg_lng, (plat - lat) * m_per_deg_lat)

    best = float("inf")
    for i in range(1, len(polyline)):
        ax, ay = to_xy(polyline[i - 1][0], polyline[i - 1][1])
        bx, by = to_xy(polyline[i][0], polyline[i][1])
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        if seg_len2 == 0:
            t = 0.0
        else:
            t = max(0.0, min(1.0, (-ax * dx + -ay * dy) / seg_len2))
        cx, cy = ax + t * dx, ay + t * dy  # closest point on segment
        best = min(best, math.hypot(cx, cy))  # query point is the origin (0, 0)
    return best
