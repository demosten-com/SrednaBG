# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Fetch speed enforcement zone data from TollTracker.eu.

TollTracker embeds zone data as GeoJSON in the Next.js RSC (React Server
Components) flight payload — specifically in self.__next_f.push([1,"..."]) script
tags. This is the richest data source — provides GPS coordinates, speed limits per
vehicle type, distances, and full centerline geometry.

Each TollTracker segment is bidirectional (one physical road section).
We produce TWO Zone objects per segment: forward and reverse direction.
"""

import json
import logging
import math
import re
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from src.zone_schema import SpeedLimits, Zone, ZoneEndpoint

logger = logging.getLogger(__name__)

TOLLTRACKER_URL = "https://tolltracker.eu/map"

# Direction inference from coordinates for each motorway
# Maps canonical road name -> (primary_axis, positive_direction)
# primary_axis: "lng" means east-west road, "lat" means north-south road
ROAD_AXIS = {
    # Motorways
    "АМ Тракия": ("lng", "east", "west"),      # Sofia->Burgas, lng increases east
    "АМ Хемус": ("lng", "east", "west"),        # Sofia->Varna
    "АМ Марица": ("lng", "east", "west"),       # west->east
    "АМ Европа": ("lat", "north", "south"),     # south->north (Sofia->Botevgrad)
    "АМ Струма": ("lat", "north", "south"),     # lat increasing = north, decreasing = south
    # National roads
    "Път I-1": ("lat", "south", "north"),       # Sofia -> Kulata (N->S)
    "Път I-2": ("lng", "east", "west"),         # Sofia -> Plovdiv (W->E)
    "Път I-3": ("lat", "south", "north"),       # Byala -> Plovdiv (N->S)
    "Път I-4": ("lng", "east", "west"),         # Sofia -> V. Tarnovo (W->E)
    "Път I-5": ("lat", "south", "north"),       # Ruse -> Kardzhali (N->S)
    "Път I-6": ("lng", "east", "west"),         # Sofia -> Burgas (W->E)
    "Път II-55": ("lat", "south", "north"),     # V. Tarnovo -> Stara Zagora (N->S)
}


def fetch_page(url: str = TOLLTRACKER_URL, timeout: int = 30) -> str:
    """Fetch the TollTracker map page HTML."""
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "SrednaBG/1.0 (zone-scraper)"},
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            logger.warning(
                "TollTracker fetch attempt %d failed: %s", attempt + 1, e
            )
            if attempt == 2:
                raise
    return ""  # unreachable


def extract_segments(html: str) -> list[dict]:
    """Extract the speedEnforcementSegments array from the RSC flight payload.

    TollTracker uses Next.js App Router with React Server Components. The zone
    data is embedded in the server-rendered HTML as RSC flight payload inside
    self.__next_f.push([1,"<json-encoded-string>"]) script tags.
    """
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")

    for script in scripts:
        if not script.string or "speedEnforcementSegments" not in script.string:
            continue
        # Match the RSC flight push call — works regardless of how __next_f
        # is initialized (both self.__next_f.push and
        # (self.__next_f=self.__next_f||[]).push variants).
        m = re.search(
            r'\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)',
            script.string,
        )
        if not m:
            continue
        try:
            decoded = json.loads('"' + m.group(1) + '"')
        except json.JSONDecodeError:
            continue

        # Find and extract the speedEnforcementSegments JSON array
        key = '"speedEnforcementSegments":'
        idx = decoded.find(key)
        if idx == -1:
            continue
        start = idx + len(key)
        depth = 0
        end = start
        for j, c in enumerate(decoded[start:], start):
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break

        try:
            segments = json.loads(decoded[start:end])
        except json.JSONDecodeError as e:
            raise ValueError(
                "Failed to parse speedEnforcementSegments array"
            ) from e

        if not isinstance(segments, list):
            raise ValueError("speedEnforcementSegments is not a list")

        logger.info("Found %d TollTracker segments", len(segments))
        return segments

    raise ValueError("speedEnforcementSegments not found in RSC payload")


def _swap_coords(geojson_coords: list[list[float]]) -> list[list[float]]:
    """Convert GeoJSON [lng, lat] to schema [lat, lng]."""
    return [[coord[1], coord[0]] for coord in geojson_coords]


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute bearing in degrees from point 1 to point 2."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlng)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def infer_direction(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    road_name: str,
) -> str:
    """Infer compass direction from start to end coordinates.

    Uses road-specific axis knowledge when available, falls back to
    bearing-based heuristic for unknown roads.
    """
    if road_name in ROAD_AXIS:
        axis, pos_dir, neg_dir = ROAD_AXIS[road_name]
        if axis == "lng":
            return pos_dir if end_lng > start_lng else neg_dir
        else:
            return pos_dir if end_lat > start_lat else neg_dir

    # Fallback: use bearing
    b = _bearing(start_lat, start_lng, end_lat, end_lng)
    if 45 <= b < 135:
        return "east"
    elif 135 <= b < 225:
        return "south"
    elif 225 <= b < 315:
        return "west"
    else:
        return "north"


def _opposite_direction(direction: str) -> str:
    """Return the opposite compass direction."""
    opposites = {"east": "west", "west": "east", "north": "south", "south": "north"}
    return opposites[direction]


def parse_segment(feature: dict) -> tuple[Zone, Zone]:
    """Parse a single GeoJSON Feature into forward and reverse Zone objects."""
    props = feature["properties"]
    geom = feature["geometry"]

    seg_id = props["id"]
    road = props["majorRoadName"]
    road_type = props.get("roadType")  # "motorway" or "road"
    length = int(props["length"])

    # Speed limits
    sl = props["speedLimit"]
    speed_limits = SpeedLimits(
        car=sl["personal_car"],
        truck=sl["truck"],
        bus=sl["bus"],
        motorcycle=sl.get("motorcycle"),
    )

    # Start/end points
    s = props["start"]
    e = props["end"]

    start = ZoneEndpoint(
        lat=s["lat"],
        lng=s["lng"],
        settlement=s.get("title"),
        settlement_latin=s.get("titleLatin"),
    )
    end = ZoneEndpoint(
        lat=e["lat"],
        lng=e["lng"],
        settlement=e.get("title"),
        settlement_latin=e.get("titleLatin"),
    )

    # Centerline: convert from GeoJSON [lng, lat] to schema [lat, lng]
    centerline = _swap_coords(geom["coordinates"])

    # Direction for the forward zone (start -> end)
    fwd_direction = infer_direction(
        start.lat, start.lng, end.lat, end.lng, road
    )
    rev_direction = _opposite_direction(fwd_direction)

    fwd_description = f"{start.settlement} – {end.settlement}"
    rev_description = f"{end.settlement} – {start.settlement}"

    road_latin = props.get("titleLatin")

    forward = Zone(
        id=f"{seg_id}-{fwd_direction}",
        road=road,
        road_latin=road_latin,
        direction=fwd_direction,
        description=fwd_description,
        start=start,
        end=end,
        distance_m=length,
        speed_limits=speed_limits,
        centerline=centerline,
        road_type=road_type,
        source="tolltracker",
        last_verified=datetime.now(UTC).strftime("%Y-%m-%d"),
    )

    reverse = Zone(
        id=f"{seg_id}-{rev_direction}",
        road=road,
        road_latin=road_latin,
        direction=rev_direction,
        description=rev_description,
        start=end,
        end=start,
        distance_m=length,
        speed_limits=speed_limits,
        centerline=list(reversed(centerline)),
        road_type=road_type,
        source="tolltracker",
        last_verified=datetime.now(UTC).strftime("%Y-%m-%d"),
    )

    return forward, reverse


def scrape(html: str | None = None) -> list[Zone]:
    """Main entry point. Fetch and parse TollTracker data.

    Args:
        html: Pre-fetched HTML (for testing). If None, fetches from network.

    Returns:
        List of Zone objects (2 per physical segment: forward + reverse).
    """
    try:
        if html is None:
            html = fetch_page()
        segments = extract_segments(html)

        zones = []
        for feature in segments:
            try:
                fwd, rev = parse_segment(feature)
                zones.append(fwd)
                zones.append(rev)
            except Exception:
                logger.warning(
                    "Failed to parse segment: %s",
                    feature.get("properties", {}).get("id", "unknown"),
                    exc_info=True,
                )
                continue

        logger.info("Parsed %d zones from %d TollTracker segments", len(zones), len(segments))
        return zones
    except Exception:
        logger.warning("TollTracker scraper failed", exc_info=True)
        return []
