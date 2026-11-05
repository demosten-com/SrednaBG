# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors

"""Select scenario inputs by their properties in the catalog under test.

Only an unmet, explicit scenario prerequisite is NotApplicable. Invalid data
and programming errors must propagate as failures, never become skips.
"""

from . import geo, zone_source

# Reset per scenario by the orchestrator; records why and where an edge runs.
selections: list[dict] = []


class NotApplicable(Exception):
    """The catalog has no input that exercises this particular scenario."""


def centerline(zone: dict) -> list:
    points = zone["centerline"]
    start = zone["start"]
    if geo.haversine_m(*points[0], start["lat"], start["lng"]) > geo.haversine_m(
            *points[-1], start["lat"], start["lng"]):
        return list(reversed(points))
    return points


def road_class(zone: dict) -> str:
    # road_type is optional on the wire; match the clients' motorway inference
    # when a source supplies no classification.
    return zone.get("road_type") or ("motorway" if zone["road"].startswith("АМ ") else "road")


def length(zone: dict) -> float:
    return sum(geo.haversine_m(*a, *b)
               for a, b in zip(zone["centerline"], zone["centerline"][1:]))


def approach_clear(zone: dict, zones: dict, distance_m: float = 2000) -> bool:
    """Conservative prerequisite for assertions about exactly one entry.

    Use the route generator's 300 m heading anchor. Check the approach against
    other centerlines in either direction: a nearby jog can reverse a synthetic
    fix's bearing. This is eligibility, not a simulation of the detector.
    """
    cl = centerline(zone)
    acc = 0.0
    anchor = cl[-1]
    for a, b in zip(cl, cl[1:]):
        acc += geo.haversine_m(*a, *b)
        if acc >= 300:
            anchor = b
            break
    back = geo.bearing_deg(*anchor, *cl[0])
    for offset in range(200, int(distance_m) + 1, 100):
        point = geo.destination_point(*cl[0], back, offset)
        for other in zones.values():
            if other["id"] == zone["id"]:
                continue
            band = 150 if road_class(other) == "motorway" else 100
            if zone_source.distance_to_centerline_m(*point, other["centerline"]) < band + 50:
                return False
    return True


def exit_clear(zone: dict, zones: dict, distance_m: float = 1000) -> bool:
    # A hooked tail makes the generated car briefly reverse at the opposite
    # carriageway's entry camera. Its provisional announcement is legitimate,
    # so this geometry cannot support a whole-drive silence assertion.
    cl = centerline(zone)
    tail = []
    metres = 0.0
    for a, b in zip(reversed(cl[:-1]), reversed(cl[1:])):
        tail.append((a, b))
        metres += geo.haversine_m(*a, *b)
        if metres >= 300:
            break
    heading = geo.bearing_deg(*tail[-1][0], *cl[-1])
    if any(geo.haversine_m(*a, *b) > 1
           and abs((geo.bearing_deg(*a, *b) - heading + 180) % 360 - 180) > 90
           for a, b in tail):
        return False
    reverse = {**zone, "start": zone["end"], "end": zone["start"],
               "centerline": list(reversed(cl))}
    return approach_clear(reverse, zones, distance_m)


def select(role: str) -> dict:
    zones = zone_source.zones_by_id()
    # Sort by route length, then id, so choices are reproducible and economical.
    ordered = sorted(zones.values(), key=lambda z: (length(z), z["id"]))
    for zone in ordered:
        metres = length(zone)
        limits = zone["speed_limits"]
        if role == "long_drive":
            # 2 km approach + 1 km tail leave the midpoint well inside
            # a >=5 km section, even with the 30 simulated-second dropout.
            eligible = metres >= 5000 and road_class(zone) == "motorway"
        elif role == "wrong_direction":
            # The 5% blip allowance needs a long drive to remain meaningful.
            eligible = metres >= 15000 and road_class(zone) == "motorway"
        elif role == "silent_join":
            eligible = metres >= 5000 and exit_clear(zone, zones)
        elif role == "isolated_entry":
            eligible = metres >= 5000 and approach_clear(zone, zones)
        elif role == "vehicle_swap":
            eligible = metres >= 5000 and limits["car"] - limits["truck"] >= 10
        elif role in ("truck_limits", "bus_limits"):
            vehicle = role.split("_")[0]
            eligible = (metres >= 1500 and limits["car"] - limits[vehicle] >= 10
                        and approach_clear(zone, zones, 500))
        elif role == "dense_centerline":
            segments = [geo.haversine_m(*a, *b)
                        for a, b in zip(zone["centerline"], zone["centerline"][1:])]
            eligible = (metres >= 1500 and len(segments) >= 40
                        and sum(d < 30 for d in segments) > len(segments) / 2)
        elif role == "history":
            eligible = metres >= 1500
        else:
            raise ValueError(f"unknown zone selection role: {role}")
        if eligible:
            selections.append({"role": role, "zone_id": zone["id"]})
            return zone
    raise NotApplicable(f"no zone in the active catalog satisfies {role}")


def representative_zones(count: int = 6) -> list[dict]:
    """A bounded extra settings matrix; full-zones still drives EVERY zone.

    Greedily cover road classes, directions, limits, length bands and road names.
    No fixed ids or assumption that a particular road still exists.
    """
    candidates = sorted(zone_source.zones_by_id().values(), key=lambda z: (length(z), z["id"]))
    chosen = []
    covered: set[tuple] = set()

    def features(z):
        return {("type", road_class(z)), ("direction", z["direction"]),
                ("limit", z["speed_limits"]["car"]), ("road", z["road"]),
                ("length", "short" if length(z) < 5000 else
                 "medium" if length(z) < 15000 else "long")}

    while candidates and len(chosen) < count:
        zone = max(candidates, key=lambda z: len(features(z) - covered))
        chosen.append(zone)
        covered |= features(zone)
        candidates.remove(zone)
    if not chosen:
        raise ValueError("cannot test an empty zone catalog")
    return chosen
