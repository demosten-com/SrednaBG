# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""GPX → DrivePlan → pump that injects fixes through the app's debug feed.

A `DrivePlan` is just a list of `(lat, lng, t_offset_ms)` resolved before
the drive starts, so a scenario can rewrite or splice plans (mid-trip
detours, stops, dropouts) without re-parsing the GPX every time.

`compressed(factor)` makes the pump push fixes proportionally faster on the
wall clock while `sim_offset_ms` keeps the ORIGINAL plan timeline. The pump
stamps each fix's `time_ms` from the sim timeline, so the app's Kalman
filter / speed inference always see the realistic ~1 s cadence and the
GPX-encoded speed regardless of compression.

The pump feeds via `Device.feed_point` (Android FEED_POINT broadcast /
iOS `/inject`), carrying an explicit per-fix speed and bearing derived from
the plan geometry. The earlier `adb emu geo fix` transport carried neither —
the emulator's GPS pipe delivered fixes late and bunched, the app's inferred
course flipped on the jumps, and the detector admitted the opposite-direction
sibling zone at a shared camera (observed as the map arrow driving the zone
"backwards" from the red end-dot toward the green start-dot).
"""

from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from . import device as device_mod
from . import geo

GPX_NS = "{http://www.topografix.com/GPX/1/1}"


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lng: float
    t_offset_ms: int  # wall-clock offset relative to first point
    # Simulated-time offset (the plan's original, uncompressed timeline).
    # None means "same as t_offset_ms". `compressed()` shrinks t_offset_ms
    # but preserves this, so injected fix timestamps keep the real cadence.
    sim_offset_ms: Optional[int] = None

    @property
    def sim_ms(self) -> int:
        return self.t_offset_ms if self.sim_offset_ms is None else self.sim_offset_ms


@dataclass
class DrivePlan:
    name: str
    points: list[TrackPoint] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.points[-1].t_offset_ms if self.points else 0

    def _sim_per_t(self) -> float:
        """Sim-time milliseconds per wall-clock millisecond (the inverse of
        the compression factor; 1.0 for uncompressed plans)."""
        if len(self.points) < 2:
            return 1.0
        t_span = self.points[-1].t_offset_ms - self.points[0].t_offset_ms
        sim_span = self.points[-1].sim_ms - self.points[0].sim_ms
        return sim_span / t_span if t_span > 0 else 1.0

    def compressed(self, factor: float) -> "DrivePlan":
        if factor == 1.0:
            return self
        return DrivePlan(
            name=f"{self.name}@{factor}x",
            points=[
                TrackPoint(p.lat, p.lng, int(p.t_offset_ms / factor), p.sim_ms)
                for p in self.points
            ],
        )

    def slice(self, start_ms: int, end_ms: int) -> "DrivePlan":
        kept_src = [p for p in self.points if start_ms <= p.t_offset_ms <= end_ms]
        sim0 = kept_src[0].sim_ms if kept_src else 0
        kept = [
            TrackPoint(p.lat, p.lng, p.t_offset_ms - start_ms, p.sim_ms - sim0)
            for p in kept_src
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
        ratio = self._sim_per_t()
        idx = min(range(len(self.points)), key=lambda i: abs(self.points[i].t_offset_ms - at_ms))
        anchor = self.points[idx]
        # Insert ~5 fixes evenly across the dwell so the Kalman filter sees motion = 0.
        held = [
            TrackPoint(anchor.lat, anchor.lng, anchor.t_offset_ms + i,
                       anchor.sim_ms + int(i * ratio))
            for i in range(0, duration_ms + 1, max(1, duration_ms // 5))
        ]
        shifted = [
            TrackPoint(p.lat, p.lng, p.t_offset_ms + duration_ms,
                       p.sim_ms + int(duration_ms * ratio))
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


def _haversine_m(a: TrackPoint, b: TrackPoint) -> float:
    return geo.haversine_m(a.lat, a.lng, b.lat, b.lng)


def _bearing_deg(a: TrackPoint, b: TrackPoint) -> float:
    return geo.bearing_deg(a.lat, a.lng, b.lat, b.lng)


# Last injected fix timestamp (epoch ms) across pump() calls. Compression makes
# sim time outrun the wall clock, so a follow-up pump in the same scenario
# (e.g. vehicle_swap's two halves) must base its stamps after the previous
# pump's last stamp — the engine's average-speed math needs monotonic times.
_last_stamp_ms: int = 0


class DriveAborted(RuntimeError):
    """pump() was asked to stop mid-plan — raised when the runner's scenario
    timeout fires. Control flow only; the runner records the timeout itself."""


# Cross-thread abort flag for pump(). The runner executes scenario steps on a
# worker thread; when `Scenario.timeout_s` expires it sets this so a long
# drive unblocks promptly instead of pumping fixes until the plan ends.
_abort = threading.Event()


def request_abort() -> None:
    _abort.set()


def clear_abort() -> None:
    _abort.clear()


def pump(plan: DrivePlan, *, on_each: Optional[callable] = None) -> None:  # type: ignore[type-arg]
    """Drive the plan in real wall-clock time. Blocks until the last point.

    The first fix is pushed immediately; later fixes wait until their
    `t_offset_ms` from the start. If the script falls behind (slow adb,
    GC pause), it catches up by skipping the sleep — never a fix.

    Each fix is injected via the app's debug feed with an explicit speed and
    bearing (derived from the plan geometry over sim time) and a `time_ms`
    stamp from the plan's sim timeline, so the engine sees the encoded speed
    and a forward course even on compressed plans.

    `on_each(point, idx)` is called after each successful push if given;
    use it to checkpoint progress in long runs.
    """
    global _last_stamp_ms
    if not plan.points:
        return
    d = device_mod.current()
    pts = plan.points

    speeds: list[float] = []
    raw_bearings: list[Optional[float]] = []
    last_bearing: Optional[float] = None
    for i, p in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        if nxt is not None:
            dist = _haversine_m(p, nxt)
            sim_dt = (nxt.sim_ms - p.sim_ms) / 1000.0
            speeds.append(dist / sim_dt if sim_dt > 0 else 0.0)
            if dist >= 1.0:
                last_bearing = _bearing_deg(p, nxt)
        else:
            speeds.append(speeds[-1] if speeds else 0.0)
        raw_bearings.append(last_bearing)
    # Backfill leading stationary points with the first real course so the
    # very first fixes don't claim a due-north heading.
    first_moving = next((b for b in raw_bearings if b is not None), 0.0)
    bearings = [first_moving if b is None else b for b in raw_bearings]

    base_ms = max(int(time.time() * 1000), _last_stamp_ms + 1000) - pts[0].sim_ms
    t0 = time.monotonic()
    for i, p in enumerate(pts):
        deadline = t0 + p.t_offset_ms / 1000.0
        delay = deadline - time.monotonic()
        if delay > 0:
            # Sleep on the abort event so a runner-side timeout interrupts
            # the wait immediately instead of after the full inter-fix delay.
            _abort.wait(timeout=delay)
        if _abort.is_set():
            raise DriveAborted(plan.name)
        stamp = base_ms + p.sim_ms
        d.feed_point(p.lat, p.lng, speeds[i], bearings[i], time_ms=stamp)
        _last_stamp_ms = stamp
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
    wp = list(waypoints)
    if len(wp) < 2:
        raise ValueError("need at least 2 waypoints")
    step_m = (speed_kmh / 3.6) / hz
    points: list[tuple[float, float]] = [wp[0]]
    for i in range(len(wp) - 1):
        a, b = wp[i], wp[i + 1]
        seg_len = geo.haversine_m(a[0], a[1], b[0], b[1])
        if seg_len < 1.0:
            continue
        brg = geo.bearing_deg(a[0], a[1], b[0], b[1])
        d = step_m
        while d < seg_len:
            points.append(geo.destination_point(a[0], a[1], brg, d))
            d += step_m
        points.append(b)
    dt = int(1000 / hz)
    return DrivePlan(name="synthetic", points=[TrackPoint(p[0], p[1], i * dt) for i, p in enumerate(points)])
