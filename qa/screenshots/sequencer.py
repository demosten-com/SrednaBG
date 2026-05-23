# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa.screenshots

"""Drive synthetic GPS sequences to land the app in a specific zone-state band.

The sequencer reads a zone's centerline from scrapers/data/zones.json and
walks it forward, pushing fixed-speed `feed_point` calls into the app's
debug back-channel (Android FEED_POINT broadcast / iOS /inject HTTP).

Band selection is deterministic given the ZoneStatusColor logic:
  - GREEN  : avg ≤ limit AND current ≤ limit
  - YELLOW : avg ≤ limit AND current  >  limit
  - RED    : avg  >  limit (SpeedStatus.isOverLimit)

The detector integrates distance via (prev_speed + cur_speed)/2 * dt, so a
long slow preamble followed by a short fast tail flips YELLOW without
flipping RED. RED takes ~10 s of sustained over-limit speed before the
rolling average crosses the limit.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from pathlib import Path
from typing import Optional

from qa import device as device_mod

ZONES_JSON = (
    Path(__file__).resolve().parents[2] / "scrapers" / "data" / "zones.json"
)

EARTH_M = 6_371_000.0


# ─────────────────────────── geo math ───────────────────────────


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    phi1, phi2 = radians(a[0]), radians(b[0])
    dphi = radians(b[0] - a[0])
    dl = radians(b[1] - a[1])
    h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dl / 2) ** 2
    return 2 * EARTH_M * asin(sqrt(h))


def _bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    phi1, phi2 = radians(a[0]), radians(b[0])
    dl = radians(b[1] - a[1])
    y = sin(dl) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dl)
    return (degrees(atan2(y, x)) + 360) % 360


def _step(p: tuple[float, float], brg_deg: float, d_m: float) -> tuple[float, float]:
    ang = d_m / EARTH_M
    theta = radians(brg_deg)
    phi1 = radians(p[0])
    l1 = radians(p[1])
    phi2 = asin(sin(phi1) * cos(ang) + cos(phi1) * sin(ang) * cos(theta))
    l2 = l1 + atan2(sin(theta) * sin(ang) * cos(phi1),
                    cos(ang) - sin(phi1) * sin(phi2))
    return degrees(phi2), ((degrees(l2) + 540) % 360) - 180


# ─────────────────────────── zone loading ───────────────────────────


@dataclass(frozen=True)
class ZoneFixture:
    id: str
    start: tuple[float, float]   # (lat, lng)
    end: tuple[float, float]
    centerline: list[tuple[float, float]]  # ordered start → end (lat, lng)
    speed_limit_kmh: float


def load_zone(zone_id: str) -> ZoneFixture:
    raw = json.loads(ZONES_JSON.read_text(encoding="utf-8"))
    zones = raw.get("zones") if isinstance(raw, dict) else raw
    for z in zones:
        if z.get("id") == zone_id:
            start = (z["start"]["lat"], z["start"]["lng"])
            end = (z["end"]["lat"], z["end"]["lng"])
            cl = [(pt[0], pt[1]) for pt in z["centerline"]]
            # Centerline orientation in the file is undefined; flip if
            # the first point is closer to `end` than to `start`.
            if _haversine_m(cl[0], end) < _haversine_m(cl[0], start):
                cl = list(reversed(cl))
            speed_limit = float(z["speed_limits"]["car"])
            return ZoneFixture(zone_id, start, end, cl, speed_limit)
    raise KeyError(f"zone {zone_id!r} not in {ZONES_JSON}")


def far_from_any_zone() -> tuple[float, float]:
    """A point well outside every Bulgaria zone, used for shot 01 (Home, outside).

    Sofia city centre — never a section-control segment. ~50m above sea level,
    inside the BG bounding box so the app considers it valid Bulgaria GPS.
    """
    return 42.6975, 23.3242


# ─────────────────────────── walker state ───────────────────────────


@dataclass
class Walker:
    """Cursor that walks `centerline` forward by metres per step."""

    centerline: list[tuple[float, float]]
    idx: int = 0
    along_m: float = 0.0   # how far we've walked along centerline total

    def position(self) -> tuple[float, float]:
        return self.centerline[self.idx]

    def bearing(self) -> float:
        i = min(self.idx, len(self.centerline) - 2)
        return _bearing_deg(self.centerline[i], self.centerline[i + 1])

    def advance(self, d_m: float) -> tuple[float, float]:
        """Move forward `d_m` along the centerline; return new (lat, lng)."""
        remaining = d_m
        while remaining > 0 and self.idx < len(self.centerline) - 1:
            a = self.centerline[self.idx]
            b = self.centerline[self.idx + 1]
            seg = _haversine_m(a, b)
            if seg <= remaining:
                self.idx += 1
                self.along_m += seg
                remaining -= seg
            else:
                # Interpolate inside this segment.
                brg = _bearing_deg(a, b)
                new_a = _step(a, brg, remaining)
                self.centerline[self.idx] = new_a
                self.along_m += remaining
                remaining = 0
        return self.centerline[self.idx]


# ─────────────────────────── driving ───────────────────────────


def _kmh_to_ms(v: float) -> float:
    return v / 3.6


# Monotonic timestamp of the most-recent feed_point fired by drive_steady /
# drive_outside, shared across calls. Lets back-to-back drive_steady calls
# preserve the inter-fix interval — without it, the first fix of the next
# call lands ~5ms after the last fix of the previous call, which the in-app
# SpeedInference reads as a 250 km/h positional jump, contaminates the
# Kalman filter, and drags the running average above the speed limit.
_last_fix_monotonic: Optional[float] = None


def _reset_pacing() -> None:
    global _last_fix_monotonic
    _last_fix_monotonic = None


def _wait_for_next_slot(interval_s: float) -> None:
    """Sleep so the next fix lands `interval_s` after the previous one (across
    drive_steady / drive_outside calls). No-op on the very first fix."""
    global _last_fix_monotonic
    if _last_fix_monotonic is not None:
        delay = _last_fix_monotonic + interval_s - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def _mark_fix() -> None:
    global _last_fix_monotonic
    _last_fix_monotonic = time.monotonic()


def drive_steady(walker: Walker, *, speed_kmh: float, duration_s: float,
                 hz: float = 1.0) -> None:
    """Push `feed_point`s at `hz` for `duration_s` while walking forward.

    Blocks. Uses real wall-clock pacing because the in-app average-speed
    calculator integrates against system time. Honors the module-level
    `_last_fix_monotonic` so consecutive drive_steady calls don't double-
    fire (which would alias as a 250 km/h SpeedInference jump).
    """
    d = device_mod.current()
    speed_ms = _kmh_to_ms(speed_kmh)
    step_m = speed_ms / hz
    n = max(1, int(round(duration_s * hz)))
    interval_s = 1.0 / hz
    for _ in range(n):
        _wait_for_next_slot(interval_s)
        lat, lng = walker.position()
        d.feed_point(lat, lng, speed_ms, walker.bearing())
        _mark_fix()
        walker.advance(step_m)


def drive_outside(*, cur_speed_kmh: float, duration_s: float = 6.0,
                  hz: float = 1.0) -> None:
    """Feed steady fixes far from any zone so the app shows Outside + current speed.

    Walks a short tangent so the underlying GPS smoother sees actual motion
    (otherwise speed can collapse to 0 after a couple of identical fixes).
    """
    d = device_mod.current()
    speed_ms = _kmh_to_ms(cur_speed_kmh)
    lat, lng = far_from_any_zone()
    pos = (lat, lng)
    bearing = 90.0  # arbitrary east heading
    step_m = speed_ms / hz
    n = max(1, int(round(duration_s * hz)))
    interval_s = 1.0 / hz
    for _ in range(n):
        _wait_for_next_slot(interval_s)
        d.feed_point(pos[0], pos[1], speed_ms, bearing)
        _mark_fix()
        pos = _step(pos, bearing, step_m)


# ─────────────────────────── high-level orchestration ───────────────────────────


@dataclass
class ZoneSequencer:
    zone: ZoneFixture

    def fresh_walker(self) -> Walker:
        """Walker reset to the start of the zone."""
        return Walker(centerline=[p for p in self.zone.centerline])

    def drive_into_zone(self, *, preamble_s: float = 15.0,
                        preamble_speed_kmh: Optional[float] = None) -> Walker:
        """Drive in from an off-zone preamble, then ~`preamble_s` inside the zone
        at the zone's limit. Returns a Walker positioned ~`preamble_s` worth of
        distance into the zone, ready for a per-shot tail.
        """
        speed = preamble_speed_kmh or self.zone.speed_limit_kmh - 10.0  # green-safe
        w = self.fresh_walker()
        # 6s entry approach so the detector picks up the zone (handleOutside
        # transitions when distToStart < 500m AND we're moving toward it).
        drive_steady(w, speed_kmh=speed, duration_s=6.0)
        # Then the in-zone preamble.
        drive_steady(w, speed_kmh=speed, duration_s=preamble_s)
        return w

    def drive_band_tail(self, walker: Walker, band: str) -> None:
        """Append a tail that lands the in-zone color at `band`."""
        limit = self.zone.speed_limit_kmh
        if band == "green":
            # Keep at limit minus margin; flush a few more fixes to stabilize the chip.
            drive_steady(walker, speed_kmh=limit - 10.0, duration_s=3.0)
        elif band == "yellow":
            # Brief burst above limit; running avg stays under after the long preamble.
            drive_steady(walker, speed_kmh=limit + 15.0, duration_s=2.0)
        elif band == "red":
            # Sustain well above limit until rolling avg crosses.
            drive_steady(walker, speed_kmh=limit + 35.0, duration_s=12.0)
        else:
            raise ValueError(f"drive_band_tail does not handle band={band!r}")
