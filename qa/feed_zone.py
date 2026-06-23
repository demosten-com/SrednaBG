# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# Helper for feed-zone.sh: list bundled zones, or emit a drive route for one.
#
#   python3 feed_zone.py list  <zones.json>
#       -> prints the zone table (idx / id / road / limit / dist / pts)
#   python3 feed_zone.py route <zones.json> <selector> <step_m> <speed_ms>
#       -> prints a TSV route "lat<TAB>lng<TAB>speed_ms<TAB>bearing" on stdout
#          and a one-line summary on stderr. Selector is an index, an exact id,
#          or an unambiguous substring of the id/road.
import json
import sys
from pathlib import Path

# Allow `python3 qa/feed_zone.py …` (run from feed-zone.sh) to import the qa
# package, matching srednabg_qa.py's bootstrap.
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qa import geo  # noqa: E402


def car_limit(z):
    return (z.get("speed_limits") or {}).get("car", "?")


def road_label(z):
    return z.get("road_latin") or z.get("road", "")


# (lat, lng)-tuple adapters over the canonical scalar API in `qa.geo`.
def hav(a, b):
    return geo.haversine_m(a[0], a[1], b[0], b[1])


def brng(a, b):
    return geo.bearing_deg(a[0], a[1], b[0], b[1])


def offset(p, bearing, dist):
    return geo.destination_point(p[0], p[1], bearing, dist)


def load_zones(path):
    with open(path) as f:
        d = json.load(f)
    return d["zones"] if isinstance(d, dict) and "zones" in d else d


def cmd_list(zones):
    print(f"{'idx':>3}  {'id':<26} {'road':<22} {'lim':>4} {'dist':>7} {'pts':>4}")
    print(f"{'-' * 3}  {'-' * 26} {'-' * 22} {'-' * 4} {'-' * 7} {'-' * 4}")
    for i, z in enumerate(zones):
        dist = z.get("distance_m", 0) / 1000.0
        print(f"{i:>3}  {z.get('id', ''):<26.26} {road_label(z):<22.22} "
              f"{str(car_limit(z)):>4} {dist:>6.1f}k {len(z.get('centerline', [])):>4}")
    print(f"\n{len(zones)} zones. Feed one with: qa/feed-zone.sh <idx|id|substring>",
          file=sys.stderr)


def resolve(zones, sel):
    if sel.isdigit() and int(sel) < len(zones):
        return zones[int(sel)]
    exact = next((z for z in zones if z.get("id") == sel), None)
    if exact:
        return exact
    s = sel.lower()
    cands = [z for z in zones
             if s in f"{z.get('id', '')} {road_label(z)} {z.get('road', '')}".lower()]
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        ids = ", ".join(z.get("id", "?") for z in cands[:8])
        sys.exit(f"ambiguous '{sel}' matches {len(cands)} zones: {ids}")
    sys.exit(f"zone not found: '{sel}' (run with no args to list)")


def build_route(z, step):
    """Return the list of (lat, lng) waypoints to drive zone `z`, oriented by
    the zone's *endpoints* (start -> end) so the drive follows the real
    carriageway direction regardless of how the centerline points are ordered.
    Includes the four leading approach points (Outside before entry).

    Shared by the `route` CLI command and the validation harness
    (`validate_zones.py`) so both feed the identical geometry."""
    cl = [(p[0], p[1]) for p in z["centerline"]]
    if len(cl) < 2:
        raise ValueError(f"zone {z.get('id')} has too few centerline points")

    # Orient the centerline so it runs start -> end (drive the zone's direction).
    # This uses the start/end *endpoints* as ground truth — a centerline whose
    # points are stored end-first (a real data bug we have hit) still gets driven
    # in the true physical direction, which is exactly what surfaces a zone whose
    # polylineBearing disagrees with its endpoints.
    start = (z["start"]["lat"], z["start"]["lng"])
    if hav(cl[0], start) > hav(cl[-1], start):
        cl = cl[::-1]

    # Resample to *uniform* step-metre spacing along the full polyline arc length,
    # so every emitted fix is exactly `step` apart. The app integrates progress as
    # speed×time, so the geographic gap between fixes must equal speed×interval
    # (== step) or the integrator drifts. The previous per-segment loop appended
    # each segment's endpoint even when the segment was shorter than `step`,
    # emitting short (<step) hops while still tagging the constant feed speed — the
    # integrator then over-counted (~step/seg per short hop) and falsely tripped
    # the mid-zone "overshot the end" exit + reset. See qa/CLAUDE.md.
    pts = [cl[0]]
    target = step       # arc-length of the next sample to emit
    covered = 0.0       # arc-length consumed by segments already fully walked
    for i in range(1, len(cl)):
        a, b = cl[i - 1], cl[i]
        seg = hav(a, b)
        if seg <= 0:
            continue
        while target <= covered + seg:
            f = (target - covered) / seg
            pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            target += step
        covered += seg
    # Always finish on the true centerline end so the drive reaches the zone exit
    # (the trailing sub-step hop lands after the zone has already exited).
    if pts[-1] != cl[-1]:
        pts.append(cl[-1])

    # Prepend approach points before the start so we begin Outside, then enter.
    b0 = brng(pts[0], pts[1])
    approach = [offset(pts[0], (b0 + 180) % 360, step * k) for k in (4, 3, 2, 1)]
    return approach + pts


def cmd_route(zones, sel, step, speed):
    z = resolve(zones, sel)
    full = build_route(z, step)

    print(f"Zone {z.get('id')} ({road_label(z)}) — limit {car_limit(z)} km/h, "
          f"{z.get('distance_m', 0) / 1000:.1f} km, {len(full)} fixes @ {speed:.0f} m/s",
          file=sys.stderr)

    for i in range(1, len(full)):
        a, b = full[i - 1], full[i]
        print(f"{b[0]:.6f}\t{b[1]:.6f}\t{speed:.0f}\t{brng(a, b):.0f}")


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: feed_zone.py list|route <zones.json> [selector step_m speed_ms]")
    mode, path = argv[1], argv[2]
    zones = load_zones(path)
    if mode == "list":
        cmd_list(zones)
    elif mode == "route":
        cmd_route(zones, argv[3], float(argv[4]), float(argv[5]))
    else:
        sys.exit(f"unknown mode: {mode}")


if __name__ == "__main__":
    main(sys.argv)
