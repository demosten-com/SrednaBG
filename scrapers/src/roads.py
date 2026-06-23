# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Single source of truth for road names, slugs, and direction inference.

Direction labels are geographic truth: lat increasing = north, lng
increasing = east. Every scraper labels the same physical carriageway the
same way, so the cross-source matcher can group by (road, direction) safely.
This module replaced three per-scraper copies of these tables after a
divergence shipped opposite-carriageway labels on the lat-axis national
roads (I-1, I-3, I-5, II-55).
"""

import re

from src.geo import bearing_deg

# Road name normalization across sources
ROAD_NAME_ALIASES: dict[str, str] = {
    'АМ "Тракия"': "АМ Тракия",
    "АМ Тракия": "АМ Тракия",
    'АМ "Хемус"': "АМ Хемус",
    "АМ Хемус": "АМ Хемус",
    'АМ "Струма"': "АМ Струма",
    "АМ Струма": "АМ Струма",
    'АМ "Марица"': "АМ Марица",
    "АМ Марица": "АМ Марица",
    'АМ "Европа"': "АМ Европа",
    "АМ Европа": "АМ Европа",
    'АМ "Европа" (Северна скоростна тангента)': "АМ Европа",
    "Път I-1": "Път I-1",
    "Път I-2": "Път I-2",
    "Път I-3": "Път I-3",
    "Път I-4": "Път I-4",
    "Път I-5": "Път I-5",
    "Път I-6": "Път I-6",
    "Път II-55": "Път II-55",
    "I-1": "Път I-1",
    "I-2": "Път I-2",
    "I-3": "Път I-3",
    "I-4": "Път I-4",
    "I-5": "Път I-5",
    "I-6": "Път I-6",
    "II-55": "Път II-55",
}

# Road slug for ID generation
ROAD_SLUGS: dict[str, str] = {
    "АМ Тракия": "trakiya",
    "АМ Хемус": "hemus",
    "АМ Струма": "struma",
    "АМ Марица": "maritsa",
    "АМ Европа": "europa",
}

# Which way km markers increase on each road:
# (direction_when_km_increases, direction_when_km_decreases)
ROAD_DIRECTIONS: dict[str, tuple[str, str]] = {
    # Motorways
    "АМ Тракия": ("east", "west"),      # Sofia -> Burgas
    "АМ Хемус": ("east", "west"),       # Sofia -> Varna
    "АМ Струма": ("south", "north"),    # Sofia -> Kulata
    "АМ Марица": ("east", "west"),      # Chirpan -> Svilengrad
    # The enforced АМ Европа section is the Severna Skorostna Tangenta, which
    # runs E-W: km 50+427 sits at п.в. Илиянци (west), 60+705 at Чепинци (east).
    "АМ Европа": ("east", "west"),
    # National roads
    "Път I-1": ("south", "north"),      # Sofia -> Blagoevgrad -> Kulata (N->S)
    "Път I-2": ("east", "west"),        # Sofia -> Plovdiv (W->E)
    "Път I-3": ("south", "north"),      # Byala -> Shipka -> Plovdiv (N->S)
    "Път I-4": ("east", "west"),        # Sofia -> V. Tarnovo (W->E)
    "Път I-5": ("south", "north"),      # Ruse -> Stara Zagora -> Kardzhali (N->S)
    "Път I-6": ("east", "west"),        # Sofia -> Karlovo -> Burgas (W->E)
    "Път II-55": ("south", "north"),    # V. Tarnovo -> Stara Zagora (N->S)
}

# Dominant axis of each road, for coordinate-based direction inference.
# "lng" = east-west road, "lat" = north-south road. The direction label
# itself is always geographic (lat increasing = north, lng increasing =
# east) — per-road inversions are NOT expressible by design.
ROAD_AXIS: dict[str, str] = {
    # Motorways
    "АМ Тракия": "lng",
    "АМ Хемус": "lng",
    "АМ Марица": "lng",
    "АМ Европа": "lng",  # the enforced section is the E-W Severna Tangenta
    "АМ Струма": "lat",
    # National roads
    "Път I-1": "lat",
    "Път I-2": "lng",
    "Път I-3": "lat",
    "Път I-4": "lng",
    "Път I-5": "lat",
    "Път I-6": "lng",
    "Път II-55": "lat",
}


def normalize_road(name: str) -> str:
    """Normalize a road name to canonical form."""
    name = name.strip()
    if name in ROAD_NAME_ALIASES:
        return ROAD_NAME_ALIASES[name]
    # Strip parenthetical suffixes and try again
    stripped = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
    if stripped != name and stripped in ROAD_NAME_ALIASES:
        return ROAD_NAME_ALIASES[stripped]
    # Handle bare national road patterns
    match = re.match(r"^(I{1,3})-(\d+)$", name)
    if match:
        return f"Път {name}"
    return name


def road_slug(canonical: str) -> str:
    """Convert canonical road name to slug for zone IDs."""
    if canonical in ROAD_SLUGS:
        return ROAD_SLUGS[canonical]
    match = re.match(r"Път\s+(I{1,3})-(\d+)", canonical)
    if match:
        prefix = match.group(1).lower()
        return f"{prefix}{match.group(2)}"
    return re.sub(r"[^a-z0-9]", "", canonical.lower())


def opposite_direction(direction: str) -> str:
    """Return the opposite compass direction."""
    opposites = {"east": "west", "west": "east", "north": "south", "south": "north"}
    try:
        return opposites[direction]
    except KeyError:
        raise ValueError(f"unknown direction: {direction!r}") from None


def is_motorway(road: str) -> bool:
    """True for motorways, given a canonical name or a road code.

    Single source of truth for the per-scraper checks that used to be spelled
    three different ways: BG TOLL canonical names (``АМ Тракия``), KML road
    codes (``A-1``), and bare codes (``A1``). TollTracker doesn't call this —
    its payload carries an explicit ``roadType`` field.
    """
    return road.startswith("АМ") or bool(re.match(r"^A-?\d", road))


def infer_direction_from_coords(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    road_name: str,
) -> str:
    """Infer the geographic travel direction from start to end coordinates.

    Projects onto the road's dominant axis when known, falls back to the
    bearing quadrant for unknown roads.
    """
    axis = ROAD_AXIS.get(normalize_road(road_name))
    if axis == "lng":
        return "east" if end_lng > start_lng else "west"
    if axis == "lat":
        return "north" if end_lat > start_lat else "south"

    # Fallback: use bearing
    b = bearing_deg(start_lat, start_lng, end_lat, end_lng)
    if 45 <= b < 135:
        return "east"
    elif 135 <= b < 225:
        return "south"
    elif 225 <= b < 315:
        return "west"
    else:
        return "north"


def infer_direction_from_km(road: str, start_km: float, end_km: float) -> str:
    """Infer travel direction from road name and km marker ordering.

    Falls back to an east/west heuristic for unknown roads.
    """
    increasing = end_km > start_km
    directions = ROAD_DIRECTIONS.get(normalize_road(road))
    if directions is not None:
        inc_dir, dec_dir = directions
        return inc_dir if increasing else dec_dir

    # Unknown roads: default heuristic — increasing km = east
    return "east" if increasing else "west"
