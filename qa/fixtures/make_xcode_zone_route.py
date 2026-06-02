#!/usr/bin/env python3
"""Generate a clean Xcode "Simulate Location" route through a real zone.

Unlike the dense 1 Hz QA fixtures, this is tuned for *manual* Xcode device
testing — it solves the three problems we hit driving `trakiya-01-east_160`:

  * **Arrow jitter** — Xcode's GPX interpolation gets noisy with dense 1 s
    waypoints, so we resample the zone centerline to SPARSE points
    (`--spacing-m`, default 150 m). Xcode then interpolates smoothly in
    straight segments → stable heading.
  * **Never over the limit** — Xcode plays these sparse GPX routes at roughly
    0.65–0.7× the encoded pace (measured: 320 km/h encoded → ~212 observed; a
    dense 1 s file runs slower still, ~0.5×). So we encode the speed high
    (`--speed-kmh`, default 240 → ~160 observed) to land clearly over the
    zone's car limit. Tune this if your Xcode shows a different pace.
  * **Long approach** — only a short lead-in before the zone (`--leadin-m`,
    default 250 m, a few real seconds) so you have just enough time to tap
    Start after Run, then immediately get the Outside→In-zone transition (and
    its entry announcement). A lead-in is required: starting *inside* the zone
    skips the transition, so no entry announcement fires.

Output is `<wpt>` format (the only thing Xcode reads — see `gpx_to_xcode.py`),
landing in qa/fixtures/gpx-xcode/ by default.

Usage:
    python qa/fixtures/make_xcode_zone_route.py trakiya-01-east
    python qa/fixtures/make_xcode_zone_route.py trakiya-01-east \
        --speed-kmh 300 --spacing-m 150 --leadin-m 250 \
        --out qa/fixtures/gpx-xcode/trakiya-01-east_overlimit.gpx
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from pathlib import Path

EARTH_M = 6_371_000.0
ZONES_JSON = Path(__file__).resolve().parents[2] / "backend" / "data" / "zones.json"
# Fixed, timezone-aware base instant — keeps the generator deterministic
# (Date.now() equivalents would churn the output on every run).
BASE_TIME = datetime(2026, 4, 17, 5, 0, 0, tzinfo=timezone.utc)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    phi1, phi2 = radians(a[0]), radians(b[0])
    dphi = radians(b[0] - a[0])
    dl = radians(b[1] - a[1])
    h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dl / 2) ** 2
    return 2 * EARTH_M * asin(sqrt(h))


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    phi1, phi2 = radians(a[0]), radians(b[0])
    dl = radians(b[1] - a[1])
    y = sin(dl) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dl)
    return (degrees(atan2(y, x)) + 360) % 360


def destination(p: tuple[float, float], brg: float, d_m: float) -> tuple[float, float]:
    ang = d_m / EARTH_M
    theta = radians(brg)
    phi1, l1 = radians(p[0]), radians(p[1])
    phi2 = asin(sin(phi1) * cos(ang) + cos(phi1) * sin(ang) * cos(theta))
    l2 = l1 + atan2(sin(theta) * sin(ang) * cos(phi1), cos(ang) - sin(phi1) * sin(phi2))
    return degrees(phi2), ((degrees(l2) + 540) % 360) - 180


def load_centerline(zone_id: str) -> list[tuple[float, float]]:
    data = json.loads(ZONES_JSON.read_text(encoding="utf-8"))
    zones = data["zones"] if isinstance(data, dict) and "zones" in data else data
    for z in zones:
        if z.get("id") == zone_id:
            cl = z.get("centerline")
            if not cl:
                raise SystemExit(f"zone {zone_id!r} has no centerline")
            return [(float(lat), float(lng)) for lat, lng in cl]
    raise SystemExit(f"zone {zone_id!r} not found in {ZONES_JSON}")


def resample(centerline: list[tuple[float, float]], spacing_m: float) -> list[tuple[float, float]]:
    """Keep centerline[0], then a point every `spacing_m` of travel, plus the
    final point — preserves road shape while thinning Xcode's interpolation."""
    out = [centerline[0]]
    acc = 0.0
    for prev, cur in zip(centerline, centerline[1:]):
        acc += haversine_m(prev, cur)
        if acc >= spacing_m:
            out.append(cur)
            acc = 0.0
    if out[-1] != centerline[-1]:
        out.append(centerline[-1])
    return out


def build_leadin(centerline: list[tuple[float, float]], leadin_m: float, spacing_m: float) -> list[tuple[float, float]]:
    """A few points behind the zone start, collinear with the first segment,
    so the approach is straight into the entry."""
    start, nxt = centerline[0], centerline[1]
    back_bearing = (bearing(start, nxt) + 180) % 360
    pts: list[tuple[float, float]] = []
    d = leadin_m
    step = min(spacing_m, leadin_m)
    while d > 0.5:
        pts.append(destination(start, back_bearing, d))
        d -= step
    return pts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zone_id")
    ap.add_argument("--speed-kmh", type=float, default=242.0,
                    help="encoded speed; Xcode plays sparse routes at ~0.66x, so ~242 → ~160 observed (default: 242)")
    ap.add_argument("--spacing-m", type=float, default=150.0,
                    help="distance between waypoints; larger = smoother heading (default: 150)")
    ap.add_argument("--leadin-m", type=float, default=250.0,
                    help="approach distance before the zone start (default: 250)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    centerline = load_centerline(args.zone_id)
    path = build_leadin(centerline, args.leadin_m, args.spacing_m) + resample(centerline, args.spacing_m)

    speed_mps = args.speed_kmh / 3.6
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="srednabg-make-xcode-zone-route" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
    ]
    elapsed = 0.0
    for i, (lat, lng) in enumerate(path):
        if i > 0:
            elapsed += haversine_m(path[i - 1], path[i]) / speed_mps
        ts = (BASE_TIME + timedelta(seconds=round(elapsed))).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f'  <wpt lat="{lat:.7f}" lon="{lng:.7f}"><time>{ts}</time></wpt>')
    lines.append("</gpx>")
    lines.append("")

    out = args.out or (Path(__file__).resolve().parent / "gpx-xcode" / f"{args.zone_id}_overlimit.gpx")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    total_m = sum(haversine_m(path[i - 1], path[i]) for i in range(1, len(path)))
    print(f"wrote {len(path)} waypoints ({total_m / 1000:.1f} km @ encoded {args.speed_kmh:.0f} km/h) -> {out}")


if __name__ == "__main__":
    main()
