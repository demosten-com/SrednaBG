#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scripts

"""Replay a GPX track into SrednaBG's debug build over adb.

Pairs with ``DebugControlReceiver.ACTION_FEED_POINT``: each trackpoint is
delivered as a broadcast intent that injects a fake ``Location`` directly
into ``LocationTrackingService``'s update listener — bypassing FLP and
working on a physical phone + DHU (no emulator, no mock-location app).

Usage:

    # Generate a route first (if you don't have one):
    python scrapers/scripts/make_test_route.py --out /tmp/route.gpx

    # Then play it back in real time (requires debug APK installed, DHU open):
    python scrapers/scripts/feed_gpx.py /tmp/route.gpx

    # 4x faster playback for impatient QA:
    python scrapers/scripts/feed_gpx.py /tmp/route.gpx --speed 4

    # Force a specific Hz if the GPX has no <time> tags:
    python scrapers/scripts/feed_gpx.py /tmp/route.gpx --hz 2

Prereq: the debug APK must be installed and SrednaBG must be open on the
DHU so ``LocationTrackingService`` is live (it is started automatically
when the car-app Session is created). If the service isn't running the
script logs a warning per point — start tracking manually with::

    adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver \
        -a com.demosten.srednabg.debug.START_TRACKING
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

EARTH_RADIUS_M = 6_371_000.0

GPX_NS = {"g": "http://www.topografix.com/GPX/1/1"}

PACKAGE = "com.demosten.srednabg"
RECEIVER = "com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugControlReceiver"
ACTION_FEED_POINT = "com.demosten.srednabg.debug.FEED_POINT"
ACTION_START_TRACKING = "com.demosten.srednabg.debug.START_TRACKING"


@dataclass
class Point:
    lat: float
    lng: float
    t: float | None  # seconds since GPX epoch (first point); None if absent


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lng2 - lng1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def parse_time(s: str) -> datetime:
    # GPX time is ISO 8601 UTC; e.g. 2026-04-19T20:33:00Z
    if s.endswith("Z"):
        return datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(s)


def load_gpx(path: Path) -> list[Point]:
    tree = ET.parse(path)
    root = tree.getroot()
    # Namespace is annoying — some GPX files use the default namespace, others
    # don't declare it. Handle both.
    trkpts = root.findall(".//g:trkpt", GPX_NS)
    if not trkpts:
        trkpts = root.findall(".//trkpt")
    points: list[Point] = []
    t0: datetime | None = None
    for el in trkpts:
        lat = float(el.get("lat", "nan"))
        lng = float(el.get("lon", "nan"))
        if math.isnan(lat) or math.isnan(lng):
            continue
        t_el = el.find("g:time", GPX_NS)
        if t_el is None:
            t_el = el.find("time")
        t: float | None = None
        if t_el is not None and t_el.text:
            dt = parse_time(t_el.text.strip())
            if t0 is None:
                t0 = dt
            t = (dt - t0).total_seconds()
        points.append(Point(lat=lat, lng=lng, t=t))
    if not points:
        raise SystemExit(f"no <trkpt> elements found in {path}")
    return points


def adb_run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "shell"] + args,
        check=False,
        capture_output=True,
        text=True,
    )


def broadcast(action: str, extras: list[tuple[str, str]] = ()) -> None:
    cmd = ["am", "broadcast", "-n", RECEIVER, "-a", action]
    for k, v in extras:
        cmd += ["--es", k, v]
    # suppress output — we log our own cadence
    adb_run(cmd)


def ensure_tracking() -> None:
    broadcast(ACTION_START_TRACKING)
    # Give the foreground service a moment to come up on first launch.
    time.sleep(0.8)


def feed(points: list[Point], speed_mul: float, default_hz: float) -> None:
    default_dt = 1.0 / default_hz
    # Build a per-point wall-clock offset from the first sample, respecting
    # GPX <time> gaps when present and falling back to the default cadence
    # when not. This avoids drift vs. accumulating sleeps.
    offsets: list[float] = []
    acc = 0.0
    for i, p in enumerate(points):
        if i == 0:
            offsets.append(0.0)
            continue
        prev = points[i - 1]
        if p.t is not None and prev.t is not None:
            gap = max(p.t - prev.t, 0.0)
        else:
            gap = default_dt
        acc += gap
        offsets.append(acc)

    speed_mul = max(speed_mul, 0.1)
    start_wall = time.monotonic()
    for i, p in enumerate(points):
        if i == 0:
            speed_ms = 0.0
            brg: float | None = None
        else:
            prev = points[i - 1]
            dist = haversine_m(prev.lat, prev.lng, p.lat, p.lng)
            dt_raw = max(offsets[i] - offsets[i - 1], 1e-3)
            speed_ms = dist / dt_raw
            brg = bearing_deg(prev.lat, prev.lng, p.lat, p.lng)

        extras: list[tuple[str, str]] = [
            ("lat", f"{p.lat:.7f}"),
            ("lng", f"{p.lng:.7f}"),
            ("speed_ms", f"{speed_ms:.3f}"),
        ]
        if brg is not None:
            extras.append(("bearing", f"{brg:.2f}"))
        broadcast(ACTION_FEED_POINT, extras)

        if i % 10 == 0 or i == len(points) - 1:
            kmh = speed_ms * 3.6
            brg_str = "--" if brg is None else f"{brg:.1f}"
            print(
                f"  [{i+1}/{len(points)}] lat={p.lat:.5f} lng={p.lng:.5f} "
                f"speed={kmh:.1f} km/h bearing={brg_str}",
                flush=True,
            )

        # Sleep until the next wall-clock target so rate stays stable.
        if i + 1 < len(points):
            target = start_wall + offsets[i + 1] / speed_mul
            wait = target - time.monotonic()
            if wait > 0:
                time.sleep(wait)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gpx", type=Path, help="Path to GPX file to replay")
    ap.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (default 1.0)")
    ap.add_argument("--hz", type=float, default=1.0, help="Fallback sample rate if GPX has no <time> tags")
    ap.add_argument("--no-autostart", action="store_true", help="Don't auto-trigger START_TRACKING first")
    args = ap.parse_args(argv)

    if not args.gpx.exists():
        print(f"error: {args.gpx} not found", file=sys.stderr)
        return 1

    points = load_gpx(args.gpx)
    print(f"loaded {len(points)} points from {args.gpx}")
    has_time = all(p.t is not None for p in points)
    print(f"timing: {'from GPX <time>' if has_time else f'fallback {args.hz} Hz'}")
    print(f"speed mul: {args.speed}x")

    if not args.no_autostart:
        print("starting LocationTrackingService (START_TRACKING)…")
        ensure_tracking()

    try:
        feed(points, speed_mul=args.speed, default_hz=args.hz)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
