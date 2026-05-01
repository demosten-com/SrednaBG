# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Scrape zone data from the BG TOLL Google My Maps KML/KMZ file.

This is the richest single data source — contains 36 bidirectional segments with:
- Full polyline centerline coordinates
- Distance in meters
- Speed limits per vehicle category
- Road identifiers
- Camera GPS coordinates with km markers (from the cameras layer)

Each KML segment is bidirectional — we produce TWO Zone objects per segment
(forward and reverse), same as TollTracker.
"""

import io
import logging
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import requests

from src.zone_schema import SpeedLimits, Zone, ZoneEndpoint

logger = logging.getLogger(__name__)

KML_URL = (
    "https://www.google.com/maps/d/kml"
    "?mid=1bydr93x-u18Oz3lm7ngmWhVTgsP2Eys"
)

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

# Road ID mapping: KML uses "A-1", "I-5" etc.
ROAD_ID_TO_NAME: dict[str, str] = {
    "A-1": "АМ Тракия",
    "A-2": "АМ Хемус",
    "A-3": "АМ Струма",
    "A-4": "АМ Марица",
    "A-6": "АМ Европа",
}

# Direction inference from coordinates for each road
# Maps canonical road name -> (primary_axis, positive_direction, negative_direction)
ROAD_AXIS: dict[str, tuple[str, str, str]] = {
    "АМ Тракия": ("lng", "east", "west"),
    "АМ Хемус": ("lng", "east", "west"),
    "АМ Марица": ("lng", "east", "west"),
    "АМ Европа": ("lat", "north", "south"),
    "АМ Струма": ("lat", "south", "north"),  # Sofia->Kulata = lat decreasing = south
    "Път I-1": ("lat", "south", "north"),
    "Път I-2": ("lng", "east", "west"),
    "Път I-3": ("lat", "south", "north"),
    "Път I-4": ("lng", "east", "west"),
    "Път I-5": ("lat", "south", "north"),
    "Път I-6": ("lng", "east", "west"),
    "Път II-55": ("lat", "south", "north"),
}


def fetch_kmz(url: str = KML_URL, timeout: int = 30) -> str:
    """Fetch and extract KML from the KMZ archive."""
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "SrednaBG/1.0 (zone-scraper)"},
            )
            resp.raise_for_status()

            # KMZ is a zip archive containing doc.kml
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                kml_names = [n for n in zf.namelist() if n.endswith(".kml")]
                if not kml_names:
                    raise ValueError("No KML file found in KMZ archive")
                return zf.read(kml_names[0]).decode("utf-8")
        except requests.RequestException as e:
            logger.warning("KML fetch attempt %d failed: %s", attempt + 1, e)
            if attempt == 2:
                raise
    return ""  # unreachable


def _parse_road_name(road_id: str) -> str:
    """Convert KML road ID to canonical road name."""
    if road_id in ROAD_ID_TO_NAME:
        return ROAD_ID_TO_NAME[road_id]
    # National roads: I-5 -> Път I-5, II-55 -> Път II-55
    if re.match(r"^I{1,3}-\d+$", road_id):
        return f"Път {road_id}"
    return road_id


def _parse_description(desc_text: str) -> dict:
    """Parse the HTML description of a segment placemark."""
    result: dict = {}

    road_match = re.search(r"Път\s+([A-Za-z0-9-]+)", desc_text)
    if road_match:
        result["road_id"] = road_match.group(1)

    dist_match = re.search(r"Дължина.*?(\d+)", desc_text)
    if dist_match:
        result["distance_m"] = int(dist_match.group(1))

    # Speed limits by category
    cat_a = re.search(r"Категория А,А2,В\s*-\s*(\d+)", desc_text)
    if cat_a:
        result["car_limit"] = int(cat_a.group(1))

    cat_b1 = re.search(r"Категория В1\s*-\s*(\d+)", desc_text)
    if cat_b1:
        result["b1_limit"] = int(cat_b1.group(1))

    cat_bus = re.search(
        r"Категория BE,C1,C1E,D,D1,D1E,DE\s*-\s*(\d+)", desc_text
    )
    if cat_bus:
        result["bus_limit"] = int(cat_bus.group(1))

    cat_truck = re.search(r"Категория C и CE\s*-\s*(\d+)", desc_text)
    if cat_truck:
        result["truck_limit"] = int(cat_truck.group(1))

    return result


def _parse_camera_description(desc_text: str) -> dict:
    """Parse the HTML description of a camera placemark."""
    result: dict = {}

    num_match = re.search(r"Номер\s+(\d+)", desc_text)
    if num_match:
        result["camera_number"] = int(num_match.group(1))

    km_match = re.search(r"км\s+(\d+\+\d+)", desc_text)
    if km_match:
        result["km_marker"] = km_match.group(1)

    return result


def _parse_linestring_coords(text: str) -> list[list[float]]:
    """Parse KML LineString coordinates into [[lat, lng], ...] format.

    KML uses lng,lat,alt format (space-separated tuples).
    """
    coords = []
    for part in text.strip().split():
        part = part.strip()
        if not part:
            continue
        components = part.split(",")
        if len(components) >= 2:
            lng = float(components[0])
            lat = float(components[1])
            coords.append([lat, lng])
    return coords


def _parse_point_coords(text: str) -> tuple[float, float]:
    """Parse KML Point coordinates into (lat, lng)."""
    parts = text.strip().split(",")
    return float(parts[1]), float(parts[0])


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
    """Infer compass direction from start to end coordinates."""
    if road_name in ROAD_AXIS:
        axis, pos_dir, neg_dir = ROAD_AXIS[road_name]
        if axis == "lng":
            return pos_dir if end_lng > start_lng else neg_dir
        else:
            return pos_dir if end_lat < start_lat else neg_dir

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
    return {"east": "west", "west": "east", "north": "south", "south": "north"}[
        direction
    ]


def parse_kml(kml_text: str) -> tuple[list[dict], list[dict]]:
    """Parse the KML into camera and segment data.

    Returns:
        (cameras, segments) where each is a list of dicts.
    """
    root = ET.fromstring(kml_text)
    folders = root.findall(".//kml:Folder", KML_NS)

    cameras: list[dict] = []
    segments: list[dict] = []

    for folder in folders:
        name_el = folder.find("kml:name", KML_NS)
        folder_name = name_el.text if name_el is not None else ""

        placemarks = folder.findall("kml:Placemark", KML_NS)

        if "камери" in folder_name.lower():
            # Camera placemarks
            for pm in placemarks:
                pm_name = pm.find("kml:name", KML_NS)
                desc = pm.find("kml:description", KML_NS)
                point = pm.find(".//kml:Point/kml:coordinates", KML_NS)

                if point is None or point.text is None:
                    continue

                lat, lng = _parse_point_coords(point.text)
                info = _parse_camera_description(
                    desc.text if desc is not None and desc.text else ""
                )
                info["name"] = pm_name.text if pm_name is not None else ""
                info["lat"] = lat
                info["lng"] = lng
                cameras.append(info)

        elif "участъци" in folder_name.lower() or "сертифициран" in folder_name.lower():
            # Segment placemarks
            for pm in placemarks:
                pm_name = pm.find("kml:name", KML_NS)
                desc = pm.find("kml:description", KML_NS)
                line = pm.find(
                    ".//kml:LineString/kml:coordinates", KML_NS
                )

                if line is None or line.text is None:
                    continue

                coords = _parse_linestring_coords(line.text)
                info = _parse_description(
                    desc.text if desc is not None and desc.text else ""
                )
                info["name"] = pm_name.text if pm_name is not None else ""
                info["centerline"] = coords
                segments.append(info)

    logger.info(
        "Parsed KML: %d cameras, %d segments", len(cameras), len(segments)
    )
    return cameras, segments


def _parse_settlement_name(name: str) -> tuple[str, str]:
    """Parse segment name like 'Казанлък - Ягода' into two settlement names.

    Note: the name order is arbitrary and may not match the polyline direction.
    Use _assign_settlements_to_endpoints() to match names to coordinates.
    """
    for sep in [" - ", "-", " – ", "–"]:
        if sep in name:
            parts = name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return name.strip(), ""


def _assign_settlements_to_endpoints(
    name_a: str,
    name_b: str,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    cameras: list[tuple[float, float, str | None, str]],
) -> tuple[str, str]:
    """Assign settlement names to start/end based on camera proximity.

    KML segment names are unordered — this matches each name to the
    correct polyline endpoint using nearby camera locations.
    Returns (start_settlement, end_settlement).
    """
    # Find cameras matching each settlement name
    def find_camera(settlement: str) -> tuple[float, float] | None:
        settlement_lower = settlement.lower()
        for cam_lat, cam_lng, _, cam_name in cameras:
            if settlement_lower in cam_name.lower():
                return cam_lat, cam_lng
        return None

    cam_a = find_camera(name_a)
    cam_b = find_camera(name_b)

    if cam_a and cam_b:
        # Both found — assign based on distance to polyline start
        dist_a_to_start = _haversine(cam_a[0], cam_a[1], start_lat, start_lng)
        dist_b_to_start = _haversine(cam_b[0], cam_b[1], start_lat, start_lng)
        if dist_a_to_start <= dist_b_to_start:
            return name_a, name_b
        else:
            return name_b, name_a
    elif cam_a:
        dist_a_to_start = _haversine(cam_a[0], cam_a[1], start_lat, start_lng)
        dist_a_to_end = _haversine(cam_a[0], cam_a[1], end_lat, end_lng)
        if dist_a_to_start <= dist_a_to_end:
            return name_a, name_b
        else:
            return name_b, name_a
    elif cam_b:
        dist_b_to_start = _haversine(cam_b[0], cam_b[1], start_lat, start_lng)
        dist_b_to_end = _haversine(cam_b[0], cam_b[1], end_lat, end_lng)
        if dist_b_to_start <= dist_b_to_end:
            return name_b, name_a
        else:
            return name_a, name_b

    # No camera match — keep original order from name (best-effort)
    return name_a, name_b


def segments_to_zones(
    segments: list[dict], cameras: list[dict]
) -> list[Zone]:
    """Convert parsed KML segments into Zone objects.

    Each segment produces two zones (forward + reverse).
    Camera data is used to enrich endpoints with km markers.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    zones: list[Zone] = []

    # Build camera lookup by approximate location
    camera_points = [
        (c["lat"], c["lng"], c.get("km_marker"), c.get("name", ""))
        for c in cameras
    ]

    for seg in segments:
        try:
            road_id = seg.get("road_id", "")
            road = _parse_road_name(road_id)
            is_motorway = road_id.startswith("A-")

            name = seg.get("name", "")
            name_a, name_b = _parse_settlement_name(name)

            centerline = seg.get("centerline", [])
            if len(centerline) < 2:
                logger.warning("Skipping segment with <2 coords: %s", name)
                continue

            start_lat, start_lng = centerline[0]
            end_lat, end_lng = centerline[-1]

            # Assign settlement names to correct endpoints
            start_settlement, end_settlement = _assign_settlements_to_endpoints(
                name_a, name_b,
                start_lat, start_lng, end_lat, end_lng,
                camera_points,
            )

            distance_m = seg.get("distance_m", 0)
            if distance_m <= 0:
                continue

            # Speed limits
            car_limit = seg.get("car_limit", 140 if is_motorway else 90)
            truck_limit = seg.get("truck_limit", 90 if is_motorway else 80)
            bus_limit = seg.get("bus_limit", 100 if is_motorway else 80)
            # Category A includes motorcycles — same as car for KML data
            motorcycle_limit = car_limit

            speed_limits = SpeedLimits(
                car=car_limit,
                truck=truck_limit,
                bus=bus_limit,
                motorcycle=motorcycle_limit,
            )

            # Try to find matching cameras for km markers
            start_km = _find_camera_km(
                start_lat, start_lng, camera_points, threshold_m=1500
            )
            end_km = _find_camera_km(
                end_lat, end_lng, camera_points, threshold_m=1500
            )

            # Direction
            fwd_direction = infer_direction(
                start_lat, start_lng, end_lat, end_lng, road
            )
            rev_direction = _opposite_direction(fwd_direction)

            road_type = "motorway" if is_motorway else "road"

            fwd_id = f"kml-{road_id}-{start_settlement[:8]}-{fwd_direction}"
            rev_id = f"kml-{road_id}-{end_settlement[:8]}-{rev_direction}"

            forward = Zone(
                id=fwd_id,
                road=road,
                direction=fwd_direction,
                description=f"{start_settlement} – {end_settlement}",
                start=ZoneEndpoint(
                    lat=start_lat,
                    lng=start_lng,
                    km_marker=start_km,
                    settlement=start_settlement,
                ),
                end=ZoneEndpoint(
                    lat=end_lat,
                    lng=end_lng,
                    km_marker=end_km,
                    settlement=end_settlement,
                ),
                distance_m=distance_m,
                speed_limits=speed_limits,
                centerline=centerline,
                road_type=road_type,
                source="kml",
                last_verified=today,
            )

            reverse = Zone(
                id=rev_id,
                road=road,
                direction=rev_direction,
                description=f"{end_settlement} – {start_settlement}",
                start=ZoneEndpoint(
                    lat=end_lat,
                    lng=end_lng,
                    km_marker=end_km,
                    settlement=end_settlement,
                ),
                end=ZoneEndpoint(
                    lat=start_lat,
                    lng=start_lng,
                    km_marker=start_km,
                    settlement=start_settlement,
                ),
                distance_m=distance_m,
                speed_limits=speed_limits,
                centerline=list(reversed(centerline)),
                road_type=road_type,
                source="kml",
                last_verified=today,
            )

            zones.append(forward)
            zones.append(reverse)

        except Exception:
            logger.warning(
                "Failed to parse KML segment: %s",
                seg.get("name", "unknown"),
                exc_info=True,
            )
            continue

    logger.info("Parsed %d zones from %d KML segments", len(zones), len(segments))
    return zones


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_camera_km(
    lat: float,
    lng: float,
    cameras: list[tuple[float, float, str | None, str]],
    threshold_m: float = 1500,
) -> str | None:
    """Find the closest camera to a point and return its km marker."""
    best_dist = threshold_m
    best_km = None
    for cam_lat, cam_lng, km_marker, _ in cameras:
        if km_marker is None:
            continue
        d = _haversine(lat, lng, cam_lat, cam_lng)
        if d < best_dist:
            best_dist = d
            best_km = km_marker
    return best_km


def scrape(kml_text: str | None = None) -> list[Zone]:
    """Main entry point. Fetch and parse KML data.

    Args:
        kml_text: Pre-fetched KML text (for testing). If None, fetches from network.

    Returns:
        List of Zone objects (2 per physical segment: forward + reverse).
    """
    try:
        if kml_text is None:
            kml_text = fetch_kmz()

        cameras, segments = parse_kml(kml_text)
        return segments_to_zones(segments, cameras)
    except Exception:
        logger.warning("KML scraper failed", exc_info=True)
        return []
