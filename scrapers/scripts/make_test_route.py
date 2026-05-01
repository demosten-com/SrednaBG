#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Generate a GPX route that drives through a SrednaBG zone.

Reads scrapers/data/zones.json, picks a zone by id, and writes a GPX file
with three phases: approach (outside the zone) -> traverse the centerline ->
exit (past the end endpoint). Load the result in the Android Studio AAOS
emulator: Extended Controls -> Location -> Routes -> Import GPX -> Play.

The approach and exit segments are straight-line extrapolations from the
zone's bearing at start/end; simple and dependency-free. The zone boundary
vertices — centerline[0] and centerline[-1] — are always emitted as explicit
GPX points so the zone crossing never falls between samples.

A sibling .html Leaflet preview is written beside every .gpx for quick
eyeball verification before driving the route in the emulator.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0


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


def destination_point(lat: float, lng: float, bearing: float, distance_m: float) -> tuple[float, float]:
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
    total = 0.0
    for i in range(len(poly) - 1):
        total += haversine_m(poly[i][0], poly[i][1], poly[i + 1][0], poly[i + 1][1])
    return total


def resample_polyline(points: list[tuple[float, float]], step_m: float) -> Iterable[tuple[float, float]]:
    """Yield points evenly spaced by step_m along a polyline.

    Starts with points[0]. The final vertex (points[-1]) is NOT guaranteed to
    be emitted — if the total length is not an exact multiple of step_m, the
    tail past the last sample is dropped. Callers that need explicit
    endpoints must append them after resampling.
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


def load_zone(zones_path: Path, zone_id: str) -> dict:
    with zones_path.open() as f:
        zones = json.load(f)["zones"]
    for z in zones:
        if z["id"] == zone_id:
            return z
    ids = sorted(z["id"] for z in zones)
    sys.stderr.write(f"Zone id not found: {zone_id}\nAvailable ids ({len(ids)}):\n")
    for i in ids:
        sys.stderr.write(f"  {i}\n")
    sys.exit(2)


def emit_gpx(points: list[tuple[float, float]], hz: float, out_path: Path, name: str) -> None:
    dt_step = timedelta(seconds=1.0 / hz)
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    with out_path.open("w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<gpx version="1.1" creator="srednabg-make-test-route" ')
        f.write('xmlns="http://www.topografix.com/GPX/1/1">\n')
        f.write(f"  <trk><name>{name}</name><trkseg>\n")
        for i, (lat, lng) in enumerate(points):
            ts = (t0 + i * dt_step).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f'    <trkpt lat="{lat:.7f}" lon="{lng:.7f}"><time>{ts}</time></trkpt>\n')
        f.write("  </trkseg></trk>\n")
        f.write("</gpx>\n")


def emit_leaflet_preview(
    html_path: Path,
    zone: dict,
    centerline: list[tuple[float, float]],
    approach: list[tuple[float, float]],
    exit_seg: list[tuple[float, float]],
    gpx_points: list[tuple[float, float]],
) -> None:
    """Write a minimal Leaflet HTML preview alongside the GPX."""
    def as_js(poly: list[tuple[float, float]]) -> str:
        return json.dumps([[lat, lng] for lat, lng in poly])

    zone_label = f"{zone.get('road', '')} ({zone.get('id', '')})".strip()
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{zone_label} — GPX preview</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map {{ height: 100%; margin: 0; }}
  #legend {{
    position: absolute; top: 8px; right: 8px; z-index: 1000;
    background: rgba(255,255,255,0.95); padding: 8px 12px;
    border-radius: 6px; font: 13px/1.4 system-ui, sans-serif;
    box-shadow: 0 1px 4px rgba(0,0,0,0.25); max-width: 340px;
  }}
  .sw {{ display: inline-block; width: 18px; height: 3px; vertical-align: middle; margin-right: 6px; }}
</style>
</head><body>
<div id="map"></div>
<div id="legend">
  <div><strong>{zone_label}</strong></div>
  <div><span class="sw" style="background:#1a9850"></span>zone centerline</div>
  <div><span class="sw" style="border-top:3px dashed #e8833a;background:transparent;height:0"></span>straight-line approach / exit</div>
  <div><span class="sw" style="background:#e03e3e"></span>GPX track</div>
</div>
<script>
const centerline = {as_js(centerline)};
const approach = {as_js(approach)};
const exitSeg = {as_js(exit_seg)};
const gpx = {as_js(gpx_points)};

const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}}).addTo(map);

if (approach.length >= 2) {{
  L.polyline(approach, {{color: '#e8833a', weight: 3, opacity: 0.85, dashArray: '6,6'}}).addTo(map);
}}
if (exitSeg.length >= 2) {{
  L.polyline(exitSeg, {{color: '#e8833a', weight: 3, opacity: 0.85, dashArray: '6,6'}}).addTo(map);
}}
L.polyline(centerline, {{color: '#1a9850', weight: 5, opacity: 0.9}}).addTo(map);
const gpxLine = L.polyline(gpx, {{color: '#e03e3e', weight: 2, opacity: 0.85}}).addTo(map);
if (gpx.length > 0) {{
  L.circleMarker(gpx[0], {{radius: 6, color: '#e03e3e', fillColor: '#e03e3e', fillOpacity: 1}})
    .bindTooltip('GPX start', {{permanent: false}}).addTo(map);
}}

map.fitBounds(gpxLine.getBounds().pad(0.1));
</script>
</body></html>
"""
    html_path.write_text(html, encoding="utf-8")


def build_straight_segment(
    from_lat: float, from_lng: float, bearing: float, length_m: float
) -> list[tuple[float, float]]:
    """Return a 2-vertex polyline from (from_lat, from_lng) along bearing."""
    end = destination_point(from_lat, from_lng, bearing, length_m)
    return [(from_lat, from_lng), end]


def build_gpx_points(
    centerline: list[tuple[float, float]],
    approach: list[tuple[float, float]],
    exit_seg: list[tuple[float, float]],
    step_m: float,
) -> list[tuple[float, float]]:
    """Resample each sub-polyline independently and stitch, preserving the
    zone boundary vertices (centerline[0] and centerline[-1]) verbatim.

    Done segment-by-segment rather than on the combined polyline because
    resample_polyline doesn't guarantee emitting the final vertex. Treating
    approach / centerline / exit separately makes centerline[0] the first
    sample of the centerline segment and centerline[-1] its last explicit
    anchor — both always present in the output.
    """
    approach_pts = list(resample_polyline(approach, step_m))
    centerline_pts = list(resample_polyline(centerline, step_m))
    exit_pts = list(resample_polyline(exit_seg, step_m))

    c0 = centerline[0]
    c_end = centerline[-1]

    out: list[tuple[float, float]] = []
    out.extend(approach_pts)
    # Guarantee centerline[0] is present: drop any approach tail samples
    # that fell between c0 and the preceding vertex (i.e. past c0) and
    # append c0 verbatim.
    while out and haversine_m(out[-1][0], out[-1][1], c0[0], c0[1]) < step_m / 2:
        out.pop()
    out.append(c0)

    # Skip the first centerline sample (it's c0, already appended).
    if centerline_pts and centerline_pts[0] == c0:
        out.extend(centerline_pts[1:])
    else:
        out.extend(centerline_pts)

    # Ensure centerline[-1] is present as an explicit anchor before the exit.
    while out and out[-1] != c_end and \
            haversine_m(out[-1][0], out[-1][1], c_end[0], c_end[1]) < step_m / 2:
        out.pop()
    if not out or out[-1] != c_end:
        out.append(c_end)

    # Exit starts at centerline[-1] (already appended); skip duplicate seam.
    if exit_pts and exit_pts[0] == c_end:
        out.extend(exit_pts[1:])
    else:
        out.extend(exit_pts)

    return out


def main() -> None:
    default_zones = Path(__file__).resolve().parent.parent / "data" / "zones.json"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--zone-id", default="trakiya-01-east")
    p.add_argument("--out", type=Path, default=Path("test_route.gpx"))
    p.add_argument("--speed-kmh", type=float, default=130.0)
    p.add_argument("--approach-km", type=float, default=2.0)
    p.add_argument("--exit-km", type=float, default=1.0)
    p.add_argument("--hz", type=float, default=1.0, help="samples per second")
    p.add_argument("--zones", type=Path, default=default_zones)
    p.add_argument(
        "--no-html", action="store_true",
        help="Skip writing the sibling .html Leaflet preview",
    )
    args = p.parse_args()

    zone = load_zone(args.zones, args.zone_id)
    centerline = [(pt[0], pt[1]) for pt in zone["centerline"]]
    if len(centerline) < 2:
        sys.exit(f"Zone {args.zone_id} has fewer than 2 centerline points; cannot build a route")

    step_m = (args.speed_kmh / 3.6) / args.hz
    if step_m <= 0:
        sys.exit("speed-kmh * hz must be positive")

    entry_bearing = bearing_deg(
        centerline[0][0], centerline[0][1], centerline[1][0], centerline[1][1]
    )
    exit_bearing = bearing_deg(
        centerline[-2][0], centerline[-2][1], centerline[-1][0], centerline[-1][1]
    )

    # Straight-line approach extending backward from the zone start along the
    # reverse of the entry bearing. Approach ends exactly at centerline[0].
    approach_origin = destination_point(
        centerline[0][0], centerline[0][1],
        (entry_bearing + 180.0) % 360.0,
        args.approach_km * 1000.0,
    )
    approach = [approach_origin, (centerline[0][0], centerline[0][1])]

    # Straight-line exit extending forward past centerline[-1] along the
    # final centerline bearing.
    exit_terminus = destination_point(
        centerline[-1][0], centerline[-1][1], exit_bearing, args.exit_km * 1000.0
    )
    exit_seg = [(centerline[-1][0], centerline[-1][1]), exit_terminus]

    points = build_gpx_points(centerline, approach, exit_seg, step_m)

    emit_gpx(points, args.hz, args.out, name=f"{zone['road']} ({zone['id']})")

    html_path = args.out.with_suffix(".html")
    if not args.no_html:
        emit_leaflet_preview(
            html_path,
            zone=zone,
            centerline=centerline,
            approach=approach,
            exit_seg=exit_seg,
            gpx_points=points,
        )

    total_km = (
        args.approach_km
        + polyline_length_m(centerline) / 1000.0
        + args.exit_km
    )
    duration_s = len(points) / args.hz
    msg = (
        f"Wrote {len(points)} trackpoints covering ~{total_km:.1f} km "
        f"({duration_s:.0f} s at {args.speed_kmh:.0f} km/h {args.hz:g} Hz) to {args.out}"
    )
    if not args.no_html:
        msg += f"\nPreview: {html_path}"
    print(msg)


if __name__ == "__main__":
    main()
