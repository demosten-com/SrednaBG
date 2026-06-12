# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Cross-reference, match, and merge zone data from multiple sources.

Merging priority per field:
- GPS coordinates: TollTracker > OSM > BG TOLL (has none)
- Km markers: BG TOLL > TollTracker
- Settlement names: BG TOLL (Cyrillic canonical) > TollTracker
- Speed limits: TollTracker (has motorcycle/bus) > BG TOLL (inferred)
- Centerline: TollTracker > OSM
- Distance: TollTracker (measured) > BG TOLL (km marker calc)
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from src.geo import haversine_m as _haversine
from src.geo import polyline_length_m as _polyline_length_m
from src.roads import (
    ROAD_DIRECTIONS,
    normalize_road,
    opposite_direction,
    road_slug,
)
from src.zone_schema import Zone, ZoneEndpoint

logger = logging.getLogger(__name__)

REQUIRED_MOTORWAYS = {"АМ Тракия", "АМ Хемус", "АМ Струма", "АМ Марица"}


@dataclass
class ZoneMatch:
    """A matched pair of zones from different sources."""

    bgtoll: Zone | None = None
    tolltracker: Zone | None = None
    osm: Zone | None = None
    kml: Zone | None = None
    confidence: float = 0.0
    match_method: str = ""


def _normalize_settlement(name: str | None) -> str:
    """Normalize a settlement name for fuzzy matching."""
    if not name:
        return ""
    text = unicodedata.normalize("NFC", name.strip().lower())
    # Remove common prefixes
    text = re.sub(r"^(м/у\s+\d+\s+и\s+п\.в\.\s*)", "", text)
    # Strip quotes (BG TOLL uses them, TollTracker doesn't)
    text = text.replace('"', "").replace('"', "").replace('"', "")
    text = text.replace("'", "").replace("'", "").replace("'", "")
    # Replace common Latin lookalikes with Cyrillic equivalents
    _latin_to_cyrillic = str.maketrans("aeopcxyAEOPCXY", "аеорсхуАЕОРСХУ")
    text = text.translate(_latin_to_cyrillic)
    # Collapse whitespace after removals
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_km(km_str: str | None) -> float | None:
    """Parse km marker string to float km value."""
    if not km_str:
        return None
    match = re.search(r"(\d+)\+(\d+)", km_str)
    if not match:
        return None
    return int(match.group(1)) + int(match.group(2)) / 1000.0


def _km_ranges_overlap(
    zone_a: Zone, zone_b: Zone, min_overlap_ratio: float = 0.5
) -> bool:
    """Check if two zones' km marker ranges substantially overlap.

    Requires the overlap to cover at least ``min_overlap_ratio`` of the
    shorter range. Consecutive zones share a camera, so their km ranges
    *touch* — an edge-touch (or near-touch) must not count as a match or
    a zone can claim its neighbor's data when stronger signals are absent.
    """
    a_start = _parse_km(zone_a.start.km_marker)
    a_end = _parse_km(zone_a.end.km_marker)
    b_start = _parse_km(zone_b.start.km_marker)
    b_end = _parse_km(zone_b.end.km_marker)

    if any(v is None for v in [a_start, a_end, b_start, b_end]):
        return False

    a_min, a_max = min(a_start, a_end), max(a_start, a_end)
    b_min, b_max = min(b_start, b_end), max(b_start, b_end)

    overlap = min(a_max, b_max) - max(a_min, b_min)
    shorter = min(a_max - a_min, b_max - b_min)
    if shorter <= 0:
        return False
    return overlap >= min_overlap_ratio * shorter


def _settlements_match(zone_a: Zone, zone_b: Zone) -> bool:
    """Check if start/end settlement names match between two zones."""
    a_start = _normalize_settlement(zone_a.start.settlement)
    a_end = _normalize_settlement(zone_a.end.settlement)
    b_start = _normalize_settlement(zone_b.start.settlement)
    b_end = _normalize_settlement(zone_b.end.settlement)

    if not a_start or not b_start:
        return False

    # Forward match: A.start==B.start AND A.end==B.end
    if a_start == b_start and a_end == b_end:
        return True

    # Reverse match: A.start==B.end AND A.end==B.start
    if a_start == b_end and a_end == b_start:
        return True

    return False


def _coords_close(zone_a: Zone, zone_b: Zone, threshold_m: float = 2000) -> bool:
    """Check if the zones' endpoint pairs coincide within threshold meters.

    Both endpoints must match, in either orientation. A single-endpoint
    check would also accept the *neighboring* zone at a shared camera.
    """
    if (zone_a.start.lat == 0 and zone_a.start.lng == 0) or (
        zone_b.start.lat == 0 and zone_b.start.lng == 0
    ):
        return False

    fwd = max(
        _haversine(
            zone_a.start.lat, zone_a.start.lng, zone_b.start.lat, zone_b.start.lng
        ),
        _haversine(zone_a.end.lat, zone_a.end.lng, zone_b.end.lat, zone_b.end.lng),
    )
    rev = max(
        _haversine(
            zone_a.start.lat, zone_a.start.lng, zone_b.end.lat, zone_b.end.lng
        ),
        _haversine(
            zone_a.end.lat, zone_a.end.lng, zone_b.start.lat, zone_b.start.lng
        ),
    )

    return min(fwd, rev) < threshold_m


def match_zones(
    bgtoll: list[Zone],
    tolltracker: list[Zone],
    osm: list[Zone],
    kml: list[Zone] | None = None,
) -> list[ZoneMatch]:
    """Match zones across sources by road, direction, and multiple criteria."""
    if kml is None:
        kml = []

    matches: list[ZoneMatch] = []
    used_bgtoll: set[int] = set()
    used_tolltracker: set[int] = set()

    # Group by canonical road + direction
    def group_key(z: Zone) -> tuple[str, str]:
        return (normalize_road(z.road), z.direction)

    bgtoll_groups: dict[tuple[str, str], list[tuple[int, Zone]]] = {}
    for i, z in enumerate(bgtoll):
        key = group_key(z)
        bgtoll_groups.setdefault(key, []).append((i, z))

    tt_groups: dict[tuple[str, str], list[tuple[int, Zone]]] = {}
    for i, z in enumerate(tolltracker):
        key = group_key(z)
        tt_groups.setdefault(key, []).append((i, z))

    # Match within each road+direction group
    for key, bg_zones in bgtoll_groups.items():
        tt_zones = tt_groups.get(key, [])

        for bg_idx, bg_zone in bg_zones:
            best_match: tuple[int, Zone, float, str] | None = None

            for tt_idx, tt_zone in tt_zones:
                if tt_idx in used_tolltracker:
                    continue

                score = 0.0
                methods = []

                if _settlements_match(bg_zone, tt_zone):
                    score += 0.5
                    methods.append("settlement")

                if _km_ranges_overlap(bg_zone, tt_zone):
                    score += 0.3
                    methods.append("km_marker")

                if _coords_close(bg_zone, tt_zone):
                    score += 0.2
                    methods.append("coords")

                if score > 0 and (
                    best_match is None or score > best_match[2]
                ):
                    best_match = (tt_idx, tt_zone, score, "+".join(methods))

            if best_match is not None:
                tt_idx, tt_zone, score, method = best_match
                matches.append(
                    ZoneMatch(
                        bgtoll=bg_zone,
                        tolltracker=tt_zone,
                        confidence=score,
                        match_method=method,
                    )
                )
                used_bgtoll.add(bg_idx)
                used_tolltracker.add(tt_idx)
            else:
                # Unmatched BG TOLL zone
                matches.append(
                    ZoneMatch(bgtoll=bg_zone, confidence=0.0, match_method="none")
                )
                used_bgtoll.add(bg_idx)

    # Add unmatched TollTracker zones
    for i, z in enumerate(tolltracker):
        if i not in used_tolltracker:
            matches.append(
                ZoneMatch(tolltracker=z, confidence=0.0, match_method="none")
            )

    # OSM zones: try to match to existing, otherwise add standalone
    for oz in osm:
        matched = False
        for m in matches:
            merged = m.tolltracker or m.bgtoll
            if merged and normalize_road(oz.road) == normalize_road(merged.road):
                if oz.direction == merged.direction and _coords_close(oz, merged):
                    m.osm = oz
                    matched = True
                    break
        if not matched:
            matches.append(ZoneMatch(osm=oz, confidence=0.0, match_method="osm_only"))

    # KML zones: match to existing by road+direction+coords/km/settlement
    used_kml: set[int] = set()
    kml_groups: dict[tuple[str, str], list[tuple[int, Zone]]] = {}
    for i, z in enumerate(kml):
        key = group_key(z)
        kml_groups.setdefault(key, []).append((i, z))

    for m in matches:
        primary = m.tolltracker or m.bgtoll or m.osm
        if primary is None:
            continue
        key = group_key(primary)
        kml_candidates = kml_groups.get(key, [])

        best_kml: tuple[int, Zone, float] | None = None
        for kml_idx, kml_zone in kml_candidates:
            if kml_idx in used_kml:
                continue
            score = 0.0
            if _settlements_match(primary, kml_zone):
                score += 0.5
            if _km_ranges_overlap(primary, kml_zone):
                score += 0.3
            if _coords_close(primary, kml_zone):
                score += 0.2
            if score > 0 and (best_kml is None or score > best_kml[2]):
                best_kml = (kml_idx, kml_zone, score)

        if best_kml is not None:
            kml_idx, kml_zone, _ = best_kml
            m.kml = kml_zone
            used_kml.add(kml_idx)

    # Add unmatched KML zones as standalone
    for i, z in enumerate(kml):
        if i not in used_kml:
            matches.append(
                ZoneMatch(kml=z, confidence=0.0, match_method="kml_only")
            )

    logger.info(
        "Matched %d zone pairs (%d BG TOLL, %d TollTracker, %d OSM, %d KML)",
        len(matches),
        len(bgtoll),
        len(tolltracker),
        len(osm),
        len(kml),
    )
    return matches


def _flip_zone(zone: Zone) -> Zone:
    """Return a copy of ``zone`` traversed in the opposite direction."""
    update: dict = {
        "start": zone.end,
        "end": zone.start,
        "centerline": [list(p) for p in reversed(zone.centerline)],
        "direction": opposite_direction(zone.direction),
    }
    if zone.end.settlement and zone.start.settlement:
        update["description"] = f"{zone.end.settlement} – {zone.start.settlement}"
    return zone.model_copy(update=update)


def _orientation(src: Zone, primary: Zone) -> int:
    """How ``src`` is oriented relative to ``primary``.

    Returns +1 (same direction), -1 (reversed), or 0 (undecidable).
    Tries, in order: endpoint geometry, settlement names, km-marker order
    vs the road's known km direction.
    """
    # Geometric: compare summed endpoint distances for both pairings.
    if src.start.lat != 0 and primary.start.lat != 0:
        fwd = _haversine(
            src.start.lat, src.start.lng, primary.start.lat, primary.start.lng
        ) + _haversine(src.end.lat, src.end.lng, primary.end.lat, primary.end.lng)
        rev = _haversine(
            src.start.lat, src.start.lng, primary.end.lat, primary.end.lng
        ) + _haversine(src.end.lat, src.end.lng, primary.start.lat, primary.start.lng)
        return 1 if fwd <= rev else -1

    # Settlement names (works for BG TOLL, which has no coordinates).
    s_start = _normalize_settlement(src.start.settlement)
    s_end = _normalize_settlement(src.end.settlement)
    p_start = _normalize_settlement(primary.start.settlement)
    p_end = _normalize_settlement(primary.end.settlement)
    if s_start and p_start:
        if s_start == p_start or (s_end and p_end and s_end == p_end):
            return 1
        if s_start == p_end or (s_end and p_start and s_end == p_start):
            return -1

    # km-marker order vs the road's known km direction for primary.direction.
    start_km = _parse_km(src.start.km_marker)
    end_km = _parse_km(src.end.km_marker)
    directions = ROAD_DIRECTIONS.get(normalize_road(primary.road))
    if start_km is not None and end_km is not None and directions is not None:
        if primary.direction in directions:
            expected_increasing = primary.direction == directions[0]
            src_increasing = end_km > start_km
            return 1 if src_increasing == expected_increasing else -1

    return 0


def _orient_to(src: Zone | None, primary: Zone) -> Zone | None:
    """Reorient ``src`` so its start/end correspond to ``primary``'s.

    Sources may describe the same physical section in opposite endpoint
    order (the matcher accepts reversed pairs). Field-by-field merging is
    only safe once every source agrees on which end is the start — without
    this, a reverse-matched pair crosses settlements/km markers onto the
    opposite carriageway's geometry.
    """
    if src is None or src is primary:
        return src
    if _orientation(src, primary) == -1:
        return _flip_zone(src)
    return src


def merge_match(m: ZoneMatch) -> Zone:
    """Merge a ZoneMatch into a single Zone using field priority rules.

    Priority per field:
    - GPS coordinates: TollTracker > KML > OSM > BG TOLL
    - Km markers: BG TOLL > KML > TollTracker
    - Settlements: BG TOLL > KML > TollTracker
    - Speed limits: KML (official per-category) > TollTracker > BG TOLL
    - Centerline: KML (richest) > TollTracker > OSM
    - Distance: KML > TollTracker (measured) > BG TOLL (km calc)
    - Road type: TollTracker > KML
    """
    bg = m.bgtoll
    tt = m.tolltracker
    osm = m.osm
    kml = m.kml

    # Determine primary source
    primary = tt or kml or bg or osm
    if primary is None:
        raise ValueError("ZoneMatch has no zones")

    # Reorient every secondary source to the primary's travel direction, so
    # per-endpoint fields (settlements, km markers, Latin names) merged from
    # different sources land on the same physical end.
    bg = _orient_to(bg, primary)
    tt = _orient_to(tt, primary)
    kml = _orient_to(kml, primary)
    osm = _orient_to(osm, primary)

    # Road name: prefer BG TOLL canonical
    road = normalize_road((bg or tt or kml or osm).road)

    # Direction
    direction = primary.direction

    # Coordinates: prefer TollTracker > KML > OSM > BG TOLL
    start_coords = (0.0, 0.0)
    end_coords = (0.0, 0.0)
    for src in [tt, kml, osm, bg]:
        if src and src.start.lat != 0:
            start_coords = (src.start.lat, src.start.lng)
            end_coords = (src.end.lat, src.end.lng)
            break

    # Km markers: prefer BG TOLL > KML > TollTracker
    start_km = None
    end_km = None
    for src in [bg, kml, tt]:
        if src and src.start.km_marker:
            start_km = src.start.km_marker
            end_km = src.end.km_marker
            break

    # Settlement names: prefer BG TOLL > KML > TollTracker
    start_settlement = None
    end_settlement = None
    for src in [bg, kml, tt]:
        if src and src.start.settlement:
            start_settlement = src.start.settlement
            end_settlement = src.end.settlement
            break

    # Latin names: prefer TollTracker > KML
    start_latin = None
    end_latin = None
    for src in [tt, kml]:
        if src and src.start.settlement_latin:
            start_latin = src.start.settlement_latin
            end_latin = src.end.settlement_latin
            break

    # Speed limits: prefer KML (official per-category) > TollTracker > BG TOLL
    speed_limits = (kml or tt or bg or osm).speed_limits

    # Distance: prefer KML > TollTracker > BG TOLL
    distance_m = (kml or tt or bg or osm).distance_m

    # Centerline: prefer KML (richest points) > TollTracker > OSM
    centerline: list[list[float]] = []
    for src in [kml, tt, osm]:
        if src and src.centerline:
            centerline = src.centerline
            break

    # Road type
    road_type = None
    for src in [tt, kml]:
        if src and src.road_type:
            road_type = src.road_type
            break

    # Source attribution
    sources = []
    if bg:
        sources.append("bgtoll")
    if tt:
        sources.append("tolltracker")
    if kml:
        sources.append("kml")
    if osm:
        sources.append("osm")
    source = "+".join(sources)

    # Description
    description = f"{start_settlement} – {end_settlement}" if start_settlement and end_settlement else primary.description

    # Road latin name from TollTracker or KML
    road_latin = None
    for src in [tt, kml]:
        if src and src.road_latin:
            road_latin = src.road_latin
            break

    return Zone(
        id="",  # Assigned later by assign_ids
        road=road,
        road_latin=road_latin,
        direction=direction,
        description=description,
        start=ZoneEndpoint(
            lat=start_coords[0],
            lng=start_coords[1],
            km_marker=start_km,
            settlement=start_settlement,
            settlement_latin=start_latin,
        ),
        end=ZoneEndpoint(
            lat=end_coords[0],
            lng=end_coords[1],
            km_marker=end_km,
            settlement=end_settlement,
            settlement_latin=end_latin,
        ),
        distance_m=distance_m,
        speed_limits=speed_limits,
        centerline=centerline,
        road_type=road_type,
        source=source,
        last_verified=datetime.now(UTC).strftime("%Y-%m-%d"),
    )


def assign_ids(zones: list[Zone]) -> list[Zone]:
    """Assign deterministic IDs based on road, km marker order, and direction.

    Format: {road_slug}-{sequence:02d}-{direction}
    """
    # Group by road
    by_road: dict[str, list[Zone]] = {}
    for z in zones:
        canonical = normalize_road(z.road)
        by_road.setdefault(canonical, []).append(z)

    result = []
    for canonical_road, road_zones in sorted(by_road.items()):
        slug = road_slug(canonical_road)

        # Group by physical section (same km markers or same settlements)
        # Sort by start km marker or start lat
        def sort_key(z: Zone) -> float:
            km = _parse_km(z.start.km_marker)
            if km is not None:
                return km
            # Fallback: use latitude
            return z.start.lat if z.start.lat != 0 else 0

        road_zones.sort(key=sort_key)

        # Pair forward/reverse directions and assign sequence numbers
        seen_sections: dict[str, int] = {}
        seq_counter = 0

        for z in road_zones:
            # Create a section key from km markers or settlements
            start_km = _parse_km(z.start.km_marker)
            end_km = _parse_km(z.end.km_marker)
            if start_km is not None and end_km is not None:
                section_key = f"{min(start_km, end_km):.1f}-{max(start_km, end_km):.1f}"
            else:
                # Use settlements
                names = sorted(
                    [
                        _normalize_settlement(z.start.settlement),
                        _normalize_settlement(z.end.settlement),
                    ]
                )
                section_key = f"{names[0]}-{names[1]}"

            if section_key not in seen_sections:
                seq_counter += 1
                seen_sections[section_key] = seq_counter

            seq = seen_sections[section_key]
            new_id = f"{slug}-{seq:02d}-{z.direction}"
            result.append(z.model_copy(update={"id": new_id}))

    return result


# Geometry alignment ---------------------------------------------------------
#
# The centerline (OSM) and the start/end endpoints (BG TOLL / TollTracker) come
# from different sources and rarely coincide exactly, so the drawn line can stop
# tens of metres short of the start/end markers and `distance_m` (official) can
# disagree with the centerline arc length. The app draws the centerline but
# pins the markers at start/end, and derives the progress bar from
# `distance_m` — so the mismatch shows as a marker floating off the road and a
# progress bar that never quite reaches 0. We silently reconcile the geometry
# here: snap a near-coincident terminal onto its endpoint, or insert the
# endpoint as a new terminal point when the gap is larger (preserving the OSM
# shape), then set `distance_m` to the resulting arc length so everything is
# internally consistent. Schema is unchanged — only coordinate/`distance_m`
# values move — so already-released clients keep parsing it.

# A terminal point within this distance of its endpoint is snapped onto it;
# larger gaps get the endpoint inserted so the road shape is preserved.
GEOMETRY_SNAP_EPS_M = 5.0
# Gaps beyond this are still aligned, but warned about — they usually mean the
# endpoint coordinate and the OSM trace genuinely disagree and the data needs
# a human look. Set to the motorway road-width band (RoadMatcher's
# MOTORWAY_MAX_DISTANCE_M): a terminal within ~150 m of its marker is still
# inside the road the detector matches against, so it's expected slack rather
# than a data error — only larger gaps are worth a human's attention.
GEOMETRY_WARN_GAP_M = 150.0


def align_centerline_to_endpoints(zone: Zone) -> Zone:
    """Make the centerline start at ``zone.start`` and end at ``zone.end``, and
    set ``distance_m`` to the centerline arc length.

    Idempotent: re-running on an already-aligned zone is a no-op. Returns the
    zone unchanged when it has fewer than two centerline points.
    """
    if len(zone.centerline) < 2:
        return zone

    cl = [list(p) for p in zone.centerline]
    start = [zone.start.lat, zone.start.lng]
    end = [zone.end.lat, zone.end.lng]

    # Canonicalize travel order start -> end (a no-op for well-formed data,
    # where centerline[0] is already nearest the start).
    if (_haversine(cl[0][0], cl[0][1], start[0], start[1])
            > _haversine(cl[-1][0], cl[-1][1], start[0], start[1])):
        cl.reverse()

    def fit(target: list[float], at_front: bool, label: str) -> None:
        term = cl[0] if at_front else cl[-1]
        gap = _haversine(term[0], term[1], target[0], target[1])
        if gap > GEOMETRY_WARN_GAP_M:
            logger.warning(
                "Zone %s: centerline %s is %.0f m from its endpoint — aligning "
                "anyway, but the endpoint/centerline geometry may be wrong",
                zone.id, label, gap,
            )
        if gap <= GEOMETRY_SNAP_EPS_M:
            if at_front:
                cl[0] = list(target)
            else:
                cl[-1] = list(target)
        elif at_front:
            cl.insert(0, list(target))
        else:
            cl.append(list(target))

    fit(start, at_front=True, label="start")
    fit(end, at_front=False, label="end")

    return zone.model_copy(update={
        "centerline": cl,
        "distance_m": max(1, round(_polyline_length_m(cl))),
    })


# Cyrillic -> Latin transliteration for the consistency check below (BDS/
# streamlined system, lowercase only — the check is case-insensitive).
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a",
    "ь": "y", "ю": "yu", "я": "ya",
}

# Junction continuity band: a gap below the floor is a shared camera (fine);
# one above the ceiling is a genuine inter-zone stretch (fine); in between
# is a seam that should coincide but doesn't — bad upstream data.
JUNCTION_GAP_MIN_M = 10.0
JUNCTION_GAP_MAX_M = 500.0


def _transliterate(cyrillic: str) -> str:
    """Lowercase Bulgarian-Cyrillic-to-Latin transliteration (loose)."""
    return "".join(_CYR_TO_LAT.get(c, c) for c in cyrillic.lower())


def _latin_matches_cyrillic(cyrillic: str, latin: str) -> bool:
    """Loose check that a Latin settlement name transliterates the Cyrillic one.

    Prefix containment either way tolerates qualifiers like
    'м/у 18 и п.в.Илиянци' vs 'Iliyantsi' and transliteration variants.
    """
    t = _transliterate(cyrillic)
    norm_latin = latin.lower()
    return norm_latin[:4] in t or t[:4] in norm_latin


def validate(zones: list[Zone]) -> tuple[list[Zone], list[str]]:
    """Final validation pass. Returns (valid_zones, warnings)."""
    warnings: list[str] = []
    valid = []

    ids_seen: set[str] = set()
    roads_seen: set[str] = set()

    for z in zones:
        # Check for duplicate IDs
        if z.id in ids_seen:
            warnings.append(f"Duplicate ID: {z.id}")
            continue
        ids_seen.add(z.id)

        # Check coordinates
        if z.start.lat == 0 and z.start.lng == 0:
            warnings.append(f"Zone {z.id} has no GPS coordinates")

        # Check distance
        if z.distance_m <= 0:
            warnings.append(f"Zone {z.id} has invalid distance: {z.distance_m}")
            continue

        # Centerline orientation guard (defense-in-depth post-condition of
        # align_centerline_to_endpoints, which merge_all runs just above). The
        # app derives a zone's travel direction from the centerline's own
        # geometry (start -> end), so a centerline stored end-first makes the
        # app match the *opposite-direction* sibling zone and flap on entry — the
        # section-control reversal bug. Assert here that the first centerline
        # point is nearer zone.start than the last point is, so a future refactor
        # that drops the aligner, or an upstream source that ships a reversed
        # centerline past it, is caught loudly instead of shipping silently.
        #
        # We compare endpoint *proximity*, NOT the coarse `direction` label:
        # `direction` is a route-level designation tied to the km markers, and a
        # correctly-ordered segment can legitimately run ~180° from `direction`'s
        # compass bearing (e.g. an ascending-km "south" carriageway that locally
        # heads north), so a direction-vs-bearing check would false-positive.
        if len(z.centerline) >= 2:
            first, last = z.centerline[0], z.centerline[-1]
            first_to_start = _haversine(first[0], first[1], z.start.lat, z.start.lng)
            last_to_start = _haversine(last[0], last[1], z.start.lat, z.start.lng)
            if first_to_start > last_to_start:
                warnings.append(
                    f"Zone {z.id} centerline is reversed (first point is "
                    f"{first_to_start:.0f} m from start but the last point is only "
                    f"{last_to_start:.0f} m) — not aligned to endpoints"
                )

        # Latin names must transliterate their Cyrillic counterparts. A
        # mismatch means per-endpoint fields from different sources were
        # merged onto opposite ends (the crossed-carriageway merge bug).
        for label, ep in (("start", z.start), ("end", z.end)):
            if ep.settlement and ep.settlement_latin and not _latin_matches_cyrillic(
                ep.settlement, ep.settlement_latin
            ):
                warnings.append(
                    f"Zone {z.id} {label} settlement '{ep.settlement}' does not "
                    f"match its Latin name '{ep.settlement_latin}'"
                )

        # km markers must run the way this road's km axis runs for the
        # zone's direction label.
        start_km = _parse_km(z.start.km_marker)
        end_km = _parse_km(z.end.km_marker)
        directions = ROAD_DIRECTIONS.get(normalize_road(z.road))
        if (
            start_km is not None
            and end_km is not None
            and start_km != end_km
            and directions is not None
            and z.direction in directions
        ):
            expected_increasing = z.direction == directions[0]
            if (end_km > start_km) != expected_increasing:
                warnings.append(
                    f"Zone {z.id} km markers run {z.start.km_marker} -> "
                    f"{z.end.km_marker} but direction '{z.direction}' implies "
                    f"{'increasing' if expected_increasing else 'decreasing'} km"
                )

        # Description must mirror the endpoint settlements in travel order.
        if z.start.settlement and z.end.settlement:
            expected_desc = f"{z.start.settlement} – {z.end.settlement}"
            if z.description != expected_desc:
                warnings.append(
                    f"Zone {z.id} description '{z.description}' does not match "
                    f"its endpoints ('{expected_desc}')"
                )

        roads_seen.add(normalize_road(z.road))
        valid.append(z)

    # Junction continuity: consecutive zones share a camera, so A.end and
    # B.start must coincide. A gap inside the ambiguous band means the seam
    # drifted (the app would briefly drop to Outside between the zones).
    for a in valid:
        if a.end.lat == 0 and a.end.lng == 0:
            continue
        for b in valid:
            if a is b or a.direction != b.direction:
                continue
            if normalize_road(a.road) != normalize_road(b.road):
                continue
            if b.start.lat == 0 and b.start.lng == 0:
                continue
            gap = _haversine(a.end.lat, a.end.lng, b.start.lat, b.start.lng)
            if JUNCTION_GAP_MIN_M < gap < JUNCTION_GAP_MAX_M:
                warnings.append(
                    f"Zones {a.id} -> {b.id} junction gap is {gap:.0f} m — "
                    f"shared-camera endpoints should coincide"
                )

    # Coverage check
    for motorway in REQUIRED_MOTORWAYS:
        if motorway not in roads_seen:
            warnings.append(f"Missing coverage for {motorway}")

    logger.info(
        "Validation: %d valid zones, %d warnings", len(valid), len(warnings)
    )
    for w in warnings:
        logger.warning("Validation: %s", w)

    return valid, warnings


def merge_all(
    bgtoll: list[Zone],
    tolltracker: list[Zone],
    osm: list[Zone],
    kml: list[Zone] | None = None,
) -> list[Zone]:
    """Top-level orchestrator: match -> merge -> assign IDs -> validate."""
    matches = match_zones(bgtoll, tolltracker, osm, kml)
    merged = [merge_match(m) for m in matches]
    with_ids = assign_ids(merged)
    aligned = [align_centerline_to_endpoints(z) for z in with_ids]
    valid, warnings = validate(aligned)
    return valid
