#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scripts

"""Replay a GPX track into the booted iOS Simulator via ``xcrun simctl location``.

iOS counterpart to ``scripts/feed_gpx.py`` (which drives the Android debug
build over ``adb``). This script targets the Simulator only — there is no
equivalent debug broadcast/URL-scheme hook in the iOS shell yet, so physical
devices need Xcode's "Simulate Location" on a scheme.

Unlike the Android flow, we don't inject per-point broadcasts ourselves.
``simctl location start`` accepts a waypoint list and does its own
interpolation + CLLocation emission, which means it populates
``CLLocation.speed`` and ``CLLocation.course`` the way real hardware would.
The iOS tracker has fallbacks for missing speed/course, but letting simctl
synthesize them is closer to on-device behavior.

Usage:

    # Generate a route first (if you don't have one):
    python scrapers/scripts/make_test_route.py --out /tmp/route.gpx

    # Then play it back at the speed encoded in the GPX <time> tags:
    python scripts/feed_gpx_ios.py /tmp/route.gpx

    # 4x faster playback:
    python scripts/feed_gpx_ios.py /tmp/route.gpx --speed 4

    # Target a specific simulator instead of the booted one:
    python scripts/feed_gpx_ios.py /tmp/route.gpx --device 009589B5-...

    # Force an update interval + absolute cruise speed when GPX has no <time>:
    python scripts/feed_gpx_ios.py /tmp/route.gpx --interval 0.5 --cruise-kmh 140

Prereq: a simulator must be booted (``xcrun simctl list devices booted``)
and the SrednaBG iOS app running in the foreground with location
authorization granted.
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
DEFAULT_CRUISE_KMH = 130.0


@dataclass
class Point:
    lat: float
    lng: float
    t: float | None  # seconds since first GPX sample; None if <time> absent


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def parse_time(s: str) -> datetime:
    if s.endswith("Z"):
        return datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(s)


def load_gpx(path: Path) -> list[Point]:
    tree = ET.parse(path)
    root = tree.getroot()
    trkpts = root.findall(".//g:trkpt", GPX_NS) or root.findall(".//trkpt")
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


def derive_base_speed_ms(points: list[Point], cruise_kmh: float) -> tuple[float, str]:
    has_time = len(points) >= 2 and all(p.t is not None for p in points) and (points[-1].t or 0) > 0
    if has_time:
        total_dist = sum(
            haversine_m(points[i - 1].lat, points[i - 1].lng, points[i].lat, points[i].lng)
            for i in range(1, len(points))
        )
        avg_ms = total_dist / points[-1].t  # type: ignore[operator]
        return avg_ms, "GPX <time>"
    return cruise_kmh / 3.6, f"fallback {cruise_kmh:.0f} km/h (no GPX <time>)"


def ensure_device(device: str) -> None:
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "booted"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"xcrun simctl failed: {result.stderr.strip()}")
    if "Booted" not in result.stdout:
        raise SystemExit("no simulator is booted — start one from Xcode first")
    if device != "booted" and device not in result.stdout:
        raise SystemExit(f"device {device} is not booted; `simctl list devices booted` shows:\n{result.stdout}")


def clear_location(device: str) -> None:
    subprocess.run(
        ["xcrun", "simctl", "location", device, "clear"],
        check=False,
        capture_output=True,
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gpx", type=Path, help="Path to GPX file to replay")
    ap.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (default 1.0)")
    ap.add_argument("--device", default="booted", help="Simulator UDID or 'booted' (default)")
    ap.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="CLLocation update cadence in seconds (simctl --interval; default 1.0)",
    )
    ap.add_argument(
        "--cruise-kmh",
        type=float,
        default=DEFAULT_CRUISE_KMH,
        help="Cruise speed in km/h used when the GPX lacks <time> tags (default 130)",
    )
    args = ap.parse_args(argv)

    if not args.gpx.exists():
        print(f"error: {args.gpx} not found", file=sys.stderr)
        return 1

    ensure_device(args.device)
    points = load_gpx(args.gpx)
    base_ms, source = derive_base_speed_ms(points, args.cruise_kmh)
    effective_ms = max(base_ms * max(args.speed, 0.01), 0.1)

    print(f"loaded {len(points)} points from {args.gpx}")
    print(f"speed source: {source}")
    print(f"playback:     {effective_ms:.2f} m/s ({effective_ms * 3.6:.1f} km/h) @ {args.interval}s interval")
    print(f"device:       {args.device}")

    total_dist_m = sum(
        haversine_m(points[i - 1].lat, points[i - 1].lng, points[i].lat, points[i].lng)
        for i in range(1, len(points))
    )
    duration_s = total_dist_m / effective_ms
    print(f"distance:     {total_dist_m / 1000:.2f} km; duration ~{duration_s:.0f}s ({duration_s / 60:.1f} min)")

    cmd = [
        "xcrun", "simctl", "location", args.device, "start",
        f"--speed={effective_ms:.3f}",
        f"--interval={args.interval}",
        "-",
    ]
    payload = "".join(f"{p.lat:.7f},{p.lng:.7f}\n" for p in points)

    # Reset any previous simulated run so we start from a clean state.
    clear_location(args.device)

    print("starting simulation (Ctrl-C to stop)…", flush=True)
    result = subprocess.run(cmd, input=payload, text=True)
    if result.returncode != 0:
        print(f"simctl exited with {result.returncode}", file=sys.stderr)
        return result.returncode

    # simctl returns immediately; the animation runs inside the simulator's
    # CoreLocation daemon. Block here for the expected duration so Ctrl-C
    # gives the user a way to abort early. On natural completion we leave the
    # final waypoint pinned (mirrors real driving: GPS stops updating when
    # you stop moving, but the last fix stays valid).
    start = time.monotonic()
    tick = args.interval if args.interval < 5.0 else 5.0
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= duration_s:
                break
            pct = 100.0 * elapsed / duration_s if duration_s > 0 else 100.0
            remaining = max(duration_s - elapsed, 0.0)
            print(
                f"  [{pct:5.1f}%] elapsed {elapsed:6.1f}s / {duration_s:6.1f}s  remaining {remaining:6.1f}s",
                flush=True,
            )
            time.sleep(min(tick, remaining))
    except KeyboardInterrupt:
        clear_location(args.device)
        print("\ninterrupted (location cleared)", file=sys.stderr)
        return 130

    print("done (final waypoint left pinned; run `xcrun simctl location booted clear` to reset)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
