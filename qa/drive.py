# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""GPX → DrivePlan → async pump that pushes `adb emu geo fix` at the right cadence.

A `DrivePlan` is just a list of `(lat, lng, t_offset_ms)` resolved before
the drive starts, so a scenario can rewrite or splice plans (mid-trip
detours, stops, dropouts) without re-parsing the GPX every time.

`time_compression` >1 makes the pump push fixes proportionally faster:
  compression=4 → real 1Hz GPX runs at 4Hz wall-clock, time-axis ÷4.
The Kalman filter and ZoneDetector tolerate up to ~4× without divergence;
above that, the bearing inference from sparse FLP deliveries gets noisy.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from . import device as device_mod

GPX_NS = "{http://www.topografix.com/GPX/1/1}"


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lng: float
    t_offset_ms: int  # relative to first point


@dataclass
class DrivePlan:
    name: str
    points: list[TrackPoint] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.points[-1].t_offset_ms if self.points else 0

    def compressed(self, factor: float) -> "DrivePlan":
        if factor == 1.0:
            return self
        return DrivePlan(
            name=f"{self.name}@{factor}x",
            points=[TrackPoint(p.lat, p.lng, int(p.t_offset_ms / factor)) for p in self.points],
        )

    def slice(self, start_ms: int, end_ms: int) -> "DrivePlan":
        kept = [
            TrackPoint(p.lat, p.lng, p.t_offset_ms - start_ms)
            for p in self.points
            if start_ms <= p.t_offset_ms <= end_ms
        ]
        return DrivePlan(name=f"{self.name}[{start_ms}:{end_ms}]", points=kept)

    def with_dropout(self, gap_start_ms: int, gap_end_ms: int) -> "DrivePlan":
        """Remove points inside (gap_start_ms, gap_end_ms) — simulates GPS loss."""
        kept = [
            p for p in self.points
            if not (gap_start_ms < p.t_offset_ms < gap_end_ms)
        ]
        return DrivePlan(name=f"{self.name}+gap{gap_start_ms}-{gap_end_ms}", points=kept)

    def with_stop(self, at_ms: int, duration_ms: int) -> "DrivePlan":
        """Hold position at the point closest to `at_ms` for `duration_ms`,
        shifting all later points by `duration_ms`. Models a rest stop."""
        if not self.points:
            return self
        idx = min(range(len(self.points)), key=lambda i: abs(self.points[i].t_offset_ms - at_ms))
        anchor = self.points[idx]
        # Insert ~5 fixes evenly across the dwell so the Kalman filter sees motion = 0.
        held = [
            TrackPoint(anchor.lat, anchor.lng, anchor.t_offset_ms + i)
            for i in range(0, duration_ms + 1, max(1, duration_ms // 5))
        ]
        shifted = [
            TrackPoint(p.lat, p.lng, p.t_offset_ms + duration_ms)
            for p in self.points[idx + 1 :]
        ]
        new_points = self.points[: idx + 1] + held[1:] + shifted
        return DrivePlan(name=f"{self.name}+stop@{at_ms}", points=new_points)


def parse_gpx(gpx_path: Path) -> DrivePlan:
    """Read a GPX 1.1 file produced by `make_test_route.py`.

    Time offsets are derived from `<time>` elements; if a file has no
    times, points are assumed to be 1 Hz.
    """
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    pts = root.findall(f".//{GPX_NS}trkpt")
    if not pts:
        raise ValueError(f"no trkpt elements in {gpx_path}")
    first_t: Optional[datetime] = None
    out: list[TrackPoint] = []
    for i, pt in enumerate(pts):
        lat = float(pt.attrib["lat"])
        lng = float(pt.attrib["lon"])
        t_el = pt.find(f"{GPX_NS}time")
        if t_el is not None and t_el.text:
            ts = datetime.strptime(t_el.text, "%Y-%m-%dT%H:%M:%SZ")
            if first_t is None:
                first_t = ts
            offset = int((ts - first_t).total_seconds() * 1000)
        else:
            offset = i * 1000
        out.append(TrackPoint(lat, lng, offset))
    return DrivePlan(name=gpx_path.stem, points=out)


def pump(plan: DrivePlan, *, on_each: Optional[callable] = None) -> None:  # type: ignore[type-arg]
    """Drive the plan in real wall-clock time. Blocks until the last point.

    The first fix is pushed immediately; later fixes wait until their
    `t_offset_ms` from the start. If the script falls behind (slow adb,
    GC pause), it catches up by skipping the sleep — never a fix.

    `on_each(point, idx)` is called after each successful push if given;
    use it to checkpoint progress in long runs.
    """
    if not plan.points:
        return
    d = device_mod.current()
    t0 = time.monotonic()
    for i, p in enumerate(plan.points):
        deadline = t0 + p.t_offset_ms / 1000.0
        delay = deadline - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        d.geo_fix(p.lng, p.lat)
        if on_each:
            on_each(p, i)


def synthetic_drive(
    waypoints: Iterable[tuple[float, float]],
    *,
    speed_kmh: float = 130.0,
    hz: float = 1.0,
) -> DrivePlan:
    """Build a DrivePlan from a list of (lat, lng) waypoints, sampled at `hz`.

    Used by edge scenarios that construct routes in-Python rather than
    going through the GPX file (e.g. wrong-direction reversal, U-turn).
    """
    from math import asin, atan2, cos, degrees, radians, sin, sqrt

    EARTH = 6_371_000.0

    def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
        phi1, phi2 = radians(a[0]), radians(b[0])
        dphi = radians(b[0] - a[0])
        dl = radians(b[1] - a[1])
        h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dl / 2) ** 2
        return 2 * EARTH * asin(sqrt(h))

    def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
        phi1, phi2 = radians(a[0]), radians(b[0])
        dl = radians(b[1] - a[1])
        y = sin(dl) * cos(phi2)
        x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dl)
        return (degrees(atan2(y, x)) + 360) % 360

    def step(p: tuple[float, float], brg: float, d_m: float) -> tuple[float, float]:
        ang = d_m / EARTH
        theta = radians(brg)
        phi1 = radians(p[0])
        l1 = radians(p[1])
        phi2 = asin(sin(phi1) * cos(ang) + cos(phi1) * sin(ang) * cos(theta))
        l2 = l1 + atan2(sin(theta) * sin(ang) * cos(phi1), cos(ang) - sin(phi1) * sin(phi2))
        return degrees(phi2), ((degrees(l2) + 540) % 360) - 180

    wp = list(waypoints)
    if len(wp) < 2:
        raise ValueError("need at least 2 waypoints")
    step_m = (speed_kmh / 3.6) / hz
    points: list[tuple[float, float]] = [wp[0]]
    for i in range(len(wp) - 1):
        a, b = wp[i], wp[i + 1]
        seg_len = haversine_m(a, b)
        if seg_len < 1.0:
            continue
        brg = bearing(a, b)
        d = step_m
        while d < seg_len:
            points.append(step(a, brg, d))
            d += step_m
        points.append(b)
    dt = int(1000 / hz)
    return DrivePlan(name="synthetic", points=[TrackPoint(p[0], p[1], i * dt) for i, p in enumerate(points)])
