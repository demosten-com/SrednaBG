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
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.fetch import fetch_text
from src.roads import infer_direction_from_coords, opposite_direction
from src.zone_schema import SpeedLimits, Zone, ZoneEndpoint

logger = logging.getLogger(__name__)

TOLLTRACKER_URL = "https://tolltracker.eu/map"


def fetch_page(url: str = TOLLTRACKER_URL, timeout: int = 30) -> str:
    """Fetch the TollTracker map page HTML."""
    return fetch_text(url, timeout=timeout, label="TollTracker")


def extract_segments(html: str) -> list[dict]:
    """Extract the speedEnforcementSegments array from the RSC flight payload.

    TollTracker uses Next.js App Router with React Server Components. The zone
    data is embedded in the server-rendered HTML as RSC flight payload inside
    self.__next_f.push([1,"<json-encoded-string>"]) script tags. This format is
    an undocumented Next.js internal; last verified working against Next.js 14
    App Router (2026-06). A framework upgrade can change it.
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
        # Let the stdlib JSON parser find the array end — it is string-aware,
        # so a stray ``]`` inside a settlement name or segment id can't
        # prematurely close the array (a hand-rolled bracket counter would).
        start = idx + len(key)
        start += len(decoded[start:]) - len(decoded[start:].lstrip())
        try:
            segments, _end = json.JSONDecoder().raw_decode(decoded, start)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Failed to parse speedEnforcementSegments array"
            ) from e

        if not isinstance(segments, list):
            raise ValueError("speedEnforcementSegments is not a list")

        logger.info("Found %d TollTracker segments", len(segments))
        return segments

    raise ValueError(
        "speedEnforcementSegments not found in RSC payload "
        f"(examined {len(scripts)} <script> tags) — the Next.js flight format "
        "may have changed"
    )


def _swap_coords(geojson_coords: list[list[float]]) -> list[list[float]]:
    """Convert GeoJSON [lng, lat] to schema [lat, lng]."""
    return [[coord[1], coord[0]] for coord in geojson_coords]


def infer_direction(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    road_name: str,
) -> str:
    """Infer compass direction from start to end coordinates."""
    return infer_direction_from_coords(
        start_lat, start_lng, end_lat, end_lng, road_name
    )


def parse_segment(feature: dict) -> tuple[Zone, Zone]:
    """Parse a single GeoJSON Feature into forward and reverse Zone objects."""
    props = feature["properties"]
    geom = feature["geometry"]

    seg_id = props["id"]
    road = props["majorRoadName"]
    # Source-provided motorway flag — the TollTracker equivalent of
    # roads.is_motorway() used by the BG TOLL / KML scrapers.
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
    rev_direction = opposite_direction(fwd_direction)

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
