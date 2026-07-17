# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Fetch speed enforcement zone data from TollTracker.eu.

TollTracker's 2026-07 redesign moved the zone data out of the Next.js RSC
payload and into a public Mapbox vector tileset (the site's map loads it as
tiles; there is no plain JSON endpoint anymore). This fetcher reads the same
tileset directly:

1. Discover the Mapbox access token + tileset id from the site's JS chunks
   (falling back to the last known values if the chunk layout changes).
2. Sweep Bulgaria at a coarse zoom to find every ``polylines`` feature with
   ``type == "section_control"`` and ``country == "BG"``.
3. Re-fetch each feature at a detail zoom for precise geometry, stitching the
   per-tile clipped pieces back into one centerline.

Unlike the old RSC payload, tile features are per-direction (one feature per
carriageway), carry a single speed limit (no per-vehicle values — the KML
source outranks us in the merge there anyway) and no Latin names — those are
synthesized from the Cyrillic title via the shared BDS transliteration.
"""

import logging
import re
from datetime import UTC, datetime

import requests

from src import mvt
from src.fetch import fetch_bytes, fetch_text
from src.geo import bearing_deg, haversine_m, polyline_length_m
from src.roads import infer_direction_from_coords, is_motorway, normalize_road, to_latin
from src.zone_schema import (
    BG_LAT_MAX,
    BG_LAT_MIN,
    BG_LNG_MAX,
    BG_LNG_MIN,
    SpeedLimits,
    Zone,
    ZoneEndpoint,
)

logger = logging.getLogger(__name__)

TOLLTRACKER_URL = "https://tolltracker.eu/map"
TOLLTRACKER_BASE = "https://tolltracker.eu"

# Last known tile source, used when runtime discovery fails. The token is a
# public (pk.) browser token embedded in TollTracker's own frontend.
FALLBACK_TILESET = "trackertech.tt-map-data"
FALLBACK_TOKEN = (
    "pk.eyJ1IjoidHJhY2tlcnRlY2giLCJhIjoiY21yYzlnNDc0MDFrMjJ5c2NwbGt1ZWhrZyJ9"
    ".8jbVatlhaGeDH9NnXm_szA"
)
TILE_URL = (
    "https://api.mapbox.com/v4/{tileset}/{z}/{x}/{y}.vector.pbf"
    "?access_token={token}"
)

POLYLINE_LAYER = "polylines"
SECTION_TYPE = "section_control"
COUNTRY_CODE = "BG"

# Coarse sweep to find features (Bulgaria is ~24 tiles), then a per-feature
# detail fetch. z12 tile units are ~1.8 m — comparable to the old payload's
# coordinate precision. The tileset is missing occasional high-zoom tiles
# (e.g. the eastern end of the Каспичан Хемус section at z12/z13), which
# would leave a hole in the stitched line — so each feature walks down the
# zoom ladder until its geometry reassembles completely.
DISCOVERY_ZOOM = 8
DETAIL_ZOOMS = (12, 11, 10, DISCOVERY_ZOOM)
BBOX_MARGIN_DEG = 0.01

# Stitching: adjacent tiles clip with a ~20-unit buffer (~40 m at z12), so
# pieces of one feature overlap slightly; 150 m is comfortably past any
# overlap yet far below zone length (shortest is ~2.3 km).
STITCH_JOIN_M = 150.0
# Warn when the stitched arc disagrees with the feature's length property.
LENGTH_WARN_RATIO = 0.10

_CHUNK_RE = re.compile(r"static/chunks/[A-Za-z0-9._-]+\.js")
_CHUNK_REF_RE = re.compile(r"[a-f0-9]{16}\.js")
_TOKEN_RE = re.compile(r"pk\.eyJ[A-Za-z0-9._-]{20,}")
_TILESET_RE = re.compile(r"[a-z][a-z0-9_-]*\.tt-map-data")
_MAX_CHUNK_FETCHES = 30


def discover_tile_source() -> tuple[str, str]:
    """Find the (tileset, token) pair in TollTracker's frontend JS.

    The map page's HTML lists the first-level JS chunks; the Mapbox config
    lives in a dynamically-imported chunk one level deeper, so chunk files
    referenced by first-level chunks are scanned too (breadth-first, capped).
    Falls back to the hardcoded last known values.
    """
    tileset = token = None
    try:
        html = fetch_text(TOLLTRACKER_URL, label="TollTracker")
        # Chunk paths also appear JSON-escaped inside the RSC payload.
        queue = list(dict.fromkeys(_CHUNK_RE.findall(html.replace("\\/", "/"))))
        seen: set[str] = set()
        fetched = 0
        while queue and fetched < _MAX_CHUNK_FETCHES and not (tileset and token):
            path = queue.pop(0)
            name = path.rsplit("/", 1)[-1]
            if name in seen:
                continue
            seen.add(name)
            js = fetch_text(
                f"{TOLLTRACKER_BASE}/_next/static/chunks/{name}",
                label="TollTracker chunk",
            )
            fetched += 1
            token = token or next(iter(_TOKEN_RE.findall(js)), None)
            tileset = tileset or next(iter(_TILESET_RE.findall(js)), None)
            queue.extend(
                ref for ref in _CHUNK_REF_RE.findall(js) if ref not in seen
            )
    except requests.RequestException as e:
        logger.warning("TollTracker tile-source discovery failed: %s", e)

    if not (tileset and token):
        logger.warning(
            "TollTracker Mapbox %s not found in site JS — using fallback",
            "token" if tileset else "tileset+token",
        )
    return tileset or FALLBACK_TILESET, token or FALLBACK_TOKEN


def _fetch_tile(tileset: str, token: str, z: int, x: int, y: int) -> bytes | None:
    """Fetch one vector tile; ``None`` for empty (404) tiles."""
    url = TILE_URL.format(tileset=tileset, token=token, z=z, x=x, y=y)
    return fetch_bytes(url, label="TollTracker tile", none_on_404=True) or None


def _section_features(tile_bytes: bytes) -> list[tuple[dict, list, int]]:
    """BG section-control features in a tile: (props, parts, extent)."""
    layer = mvt.decode(tile_bytes).get(POLYLINE_LAYER)
    if not layer:
        return []
    out = []
    for feature in layer["features"]:
        props = feature["props"]
        if (
            props.get("type") == SECTION_TYPE
            and props.get("country") == COUNTRY_CODE
            and props.get("id")
        ):
            out.append((props, feature["parts"], layer["extent"]))
    return out


def stitch_pieces(
    pieces: list[list[tuple[float, float]]], join_m: float = STITCH_JOIN_M
) -> tuple[list[list[float]], bool]:
    """Reassemble per-tile clipped pieces of one polyline feature.

    Tile clipping preserves point order along the line and adjacent pieces
    overlap inside the clip buffer, so the chain grows by attaching each
    remaining piece at whichever end it continues: the piece's point nearest
    the chain end marks the seam, and only the points beyond it are added.

    Returns ``(centerline, complete)`` — ``complete`` is False when a piece
    could not be attached (a hole in the tile coverage splits the feature).
    """
    # Drop exact duplicates (the same span can land in two tiles' buffers).
    unique: list[list[tuple[float, float]]] = []
    seen: set[tuple] = set()
    for piece in pieces:
        key = tuple(piece)
        if key not in seen:
            seen.add(key)
            unique.append(piece)

    unique.sort(key=len, reverse=True)
    chain = list(unique[0])
    pending = unique[1:]

    def nearest(piece: list, point: tuple[float, float]) -> tuple[int, float]:
        dists = [haversine_m(p[0], p[1], point[0], point[1]) for p in piece]
        idx = min(range(len(dists)), key=dists.__getitem__)
        return idx, dists[idx]

    progress = True
    while progress and pending:
        progress = False
        for piece in list(pending):
            j, d = nearest(piece, chain[-1])
            if d <= join_m and j < len(piece) - 1:
                chain.extend(piece[j + 1:])
                pending.remove(piece)
                progress = True
                continue
            j, d = nearest(piece, chain[0])
            if d <= join_m and j > 0:
                chain[:0] = piece[:j]
                pending.remove(piece)
                progress = True

    # A leftover fully inside the chain's buffer overlap is redundant;
    # anything else means the feature didn't reassemble cleanly.
    complete = all(
        all(nearest(chain, p)[1] <= join_m for p in piece) for piece in pending
    )
    return [[lat, lng] for lat, lng in chain], complete


def parse_feature(props: dict, centerline: list[list[float]]) -> Zone:
    """Build a Zone from tile feature properties and stitched geometry."""
    title = props["title"]  # e.g. "Илиянци - Чепинци, Европа"
    names, sep, road_raw = title.rpartition(", ")
    if not sep:
        raise ValueError(f"TollTracker title has no road suffix: {title!r}")
    road_raw = road_raw.strip()
    endpoints = [n.strip() for n in names.split(" - ")]
    if len(endpoints) != 2 or not all(endpoints):
        raise ValueError(f"TollTracker title has no 'start - end' pair: {title!r}")
    start_name, end_name = endpoints

    road = normalize_road(road_raw)
    start_pt, end_pt = centerline[0], centerline[-1]
    direction = infer_direction_from_coords(
        start_pt[0], start_pt[1], end_pt[0], end_pt[1], road
    )

    # The geometry is drawn in the title's travel order (start -> end),
    # verified against the old payload's endpoints. Sanity-check it against
    # the road heading — but only on one-way carriageways: on two-way roads
    # ``start_road_heading`` is the underlying OSM way's canonical heading,
    # which legitimately opposes the travel direction for one of the two
    # direction features.
    heading = props.get("start_road_heading")
    if (
        heading is not None
        and props.get("start_road_oneway") is True
        and len(centerline) >= 2
    ):
        b = bearing_deg(*centerline[0], *centerline[1])
        if min(abs(b - heading), 360 - abs(b - heading)) > 90:
            logger.warning(
                "TollTracker %s geometry bearing %.0f° disagrees with "
                "start_road_heading %.0f° — possible reversed centerline",
                props["id"], b, heading,
            )

    return Zone(
        id=props["id"],
        road=road,
        road_latin=to_latin(road_raw),
        direction=direction,
        description=f"{start_name} – {end_name}",
        start=ZoneEndpoint(
            lat=start_pt[0],
            lng=start_pt[1],
            settlement=start_name,
            settlement_latin=to_latin(start_name),
        ),
        end=ZoneEndpoint(
            lat=end_pt[0],
            lng=end_pt[1],
            settlement=end_name,
            settlement_latin=to_latin(end_name),
        ),
        distance_m=int(props["length"]),
        speed_limits=SpeedLimits(car=int(props["speed_limit"])),
        centerline=centerline,
        road_type="motorway" if is_motorway(road) else "road",
        source="tolltracker",
        last_verified=datetime.now(UTC).strftime("%Y-%m-%d"),
    )


def scrape() -> list[Zone]:
    """Main entry point. Fetch and parse TollTracker data.

    Returns one Zone per tile feature (features are already per-direction).
    Raises on fetch/decode failure — the pipeline treats a failed source as
    fatal (degraded data must not publish) and reports the error.
    """
    tileset, token = discover_tile_source()

    # Phase 1: coarse sweep over Bulgaria to find features and their
    # bounding boxes.
    bboxes: dict[str, list[float]] = {}  # id -> [lat0, lng0, lat1, lng1]
    props_by_id: dict[str, dict] = {}
    for tx, ty in mvt.tile_range(
        BG_LAT_MIN, BG_LNG_MIN, BG_LAT_MAX, BG_LNG_MAX, DISCOVERY_ZOOM
    ):
        data = _fetch_tile(tileset, token, DISCOVERY_ZOOM, tx, ty)
        if not data:
            continue
        for props, parts, extent in _section_features(data):
            fid = props["id"]
            props_by_id.setdefault(fid, props)
            bbox = bboxes.setdefault(fid, [90.0, 180.0, -90.0, -180.0])
            for part in parts:
                for px, py in part:
                    lat, lng = mvt.tile_point_to_latlng(
                        DISCOVERY_ZOOM, tx, ty, px, py, extent
                    )
                    bbox[0] = min(bbox[0], lat)
                    bbox[1] = min(bbox[1], lng)
                    bbox[2] = max(bbox[2], lat)
                    bbox[3] = max(bbox[3], lng)
    logger.info(
        "TollTracker discovery: %d BG section-control features", len(bboxes)
    )
    if not bboxes:
        raise ValueError(
            f"no '{SECTION_TYPE}' features for {COUNTRY_CODE} in tileset "
            f"{tileset} — the tile schema may have changed"
        )

    # Phase 2: per-feature detail geometry, walking down the zoom ladder
    # until the clipped pieces stitch into one complete line whose arc
    # matches the feature's declared length. Decoded tiles are cached —
    # opposite-direction siblings share almost all of theirs.
    tile_cache: dict[tuple[int, int, int], list] = {}

    def feature_pieces(fid: str, zoom: int) -> list[list[tuple[float, float]]]:
        lat0, lng0, lat1, lng1 = bboxes[fid]
        pieces = []
        for tx, ty in mvt.tile_range(
            lat0 - BBOX_MARGIN_DEG,
            lng0 - BBOX_MARGIN_DEG,
            lat1 + BBOX_MARGIN_DEG,
            lng1 + BBOX_MARGIN_DEG,
            zoom,
        ):
            key = (zoom, tx, ty)
            if key not in tile_cache:
                data = _fetch_tile(tileset, token, zoom, tx, ty)
                tile_cache[key] = _section_features(data) if data else []
            for props, parts, extent in tile_cache[key]:
                if props["id"] != fid:
                    continue
                for part in parts:
                    pieces.append([
                        mvt.tile_point_to_latlng(zoom, tx, ty, px, py, extent)
                        for px, py in part
                    ])
        return pieces

    zones = []
    for fid, props in props_by_id.items():
        try:
            declared_m = int(props["length"])
            best: list[list[float]] | None = None
            best_error = float("inf")
            for zoom in DETAIL_ZOOMS:
                pieces = feature_pieces(fid, zoom)
                if not pieces:
                    continue
                centerline, complete = stitch_pieces(pieces)
                error = abs(polyline_length_m(centerline) - declared_m)
                if error < best_error:
                    best, best_error = centerline, error
                if complete and error <= LENGTH_WARN_RATIO * declared_m:
                    break
            else:
                logger.warning(
                    "TollTracker %s geometry incomplete at every zoom — "
                    "best stitched arc is %.0f m off the declared %d m",
                    fid, best_error, declared_m,
                )
            if best is None:
                raise ValueError("no detail geometry found")
            zones.append(parse_feature(props, best))
        except Exception:
            logger.warning(
                "Failed to parse TollTracker feature %s (%s)",
                fid, props.get("title"), exc_info=True,
            )

    logger.info(
        "Parsed %d zones from %d TollTracker features", len(zones), len(bboxes)
    )
    return zones
