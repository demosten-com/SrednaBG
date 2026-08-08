# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the zone validator and merger."""

import pytest

from src.bgtoll_scraper import scrape as bgtoll_scrape
from src.validator import (
    OFFICIAL_SOURCES,
    ZoneMatch,
    _coords_close,
    _haversine,
    _km_ranges_overlap,
    _orient_to,
    _polyline_length_m,
    align_centerline_to_endpoints,
    assign_ids,
    drop_unofficial_zones,
    match_zones,
    merge_all,
    merge_match,
    normalize_road,
    road_slug,
    snap_junction_seams,
    validate,
)
from src.zone_schema import SpeedLimits, Zone, ZoneEndpoint


def _make_zone(
    road="АМ Тракия",
    direction="east",
    start_settlement="Вакарел",
    end_settlement="Ихтиман",
    start_lat=0.0,
    start_lng=0.0,
    end_lat=0.0,
    end_lng=0.0,
    start_km="24+288",
    end_km="43+448",
    distance_m=19160,
    source="test",
    car=140,
    truck=90,
    bus=100,
) -> Zone:
    return Zone(
        id="temp",
        road=road,
        direction=direction,
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
        speed_limits=SpeedLimits(car=car, truck=truck, bus=bus),
        centerline=[[start_lat, start_lng], [end_lat, end_lng]]
        if start_lat != 0
        else [],
        source=source,
        last_verified="2026-04-12",
    )


class TestNormalizeRoad:
    def test_motorway_quotes(self):
        assert normalize_road('АМ "Тракия"') == "АМ Тракия"

    def test_motorway_plain(self):
        assert normalize_road("АМ Тракия") == "АМ Тракия"

    def test_national_road_bare(self):
        assert normalize_road("I-4") == "Път I-4"

    def test_national_road_full(self):
        assert normalize_road("Път I-4") == "Път I-4"

    def test_europa_parenthetical_suffix(self):
        assert (
            normalize_road('АМ "Европа" (Северна скоростна тангента)')
            == "АМ Европа"
        )

    def test_strips_unknown_parenthetical(self):
        assert normalize_road('АМ "Тракия" (нещо друго)') == "АМ Тракия"


class TestRoadSlug:
    def test_motorway(self):
        assert road_slug("АМ Тракия") == "trakiya"
        assert road_slug("АМ Хемус") == "hemus"

    def test_national_road(self):
        assert road_slug("Път I-4") == "i4"
        assert road_slug("Път II-55") == "ii55"


class TestMatchZones:
    def test_match_by_settlement(self):
        bg = [
            _make_zone(source="bgtoll"),
        ]
        tt = [
            _make_zone(
                source="tolltracker",
                start_lat=42.55,
                start_lng=23.70,
                end_lat=42.43,
                end_lng=23.86,
            ),
        ]
        matches = match_zones(bg, tt, [])
        assert len(matches) == 1
        assert matches[0].bgtoll is not None
        assert matches[0].tolltracker is not None
        assert "settlement" in matches[0].match_method

    def test_match_by_km_markers(self):
        bg = [
            _make_zone(
                source="bgtoll",
                start_settlement="Село А",
                end_settlement="Село Б",
                start_km="24+288",
                end_km="43+448",
            ),
        ]
        tt = [
            _make_zone(
                source="tolltracker",
                start_settlement="Село А",
                end_settlement="Село Б",
                start_km="24+500",
                end_km="43+200",
                start_lat=42.55,
                start_lng=23.70,
                end_lat=42.43,
                end_lng=23.86,
            ),
        ]
        matches = match_zones(bg, tt, [])
        assert len(matches) == 1
        assert matches[0].bgtoll is not None
        assert matches[0].tolltracker is not None

    def test_unmatched_bgtoll_included(self):
        bg = [_make_zone(source="bgtoll")]
        matches = match_zones(bg, [], [])
        assert len(matches) == 1
        assert matches[0].bgtoll is not None
        assert matches[0].tolltracker is None

    def test_unmatched_tolltracker_included(self):
        tt = [
            _make_zone(
                source="tolltracker",
                road="АМ Хемус",
                start_settlement="Горни Богров",
                end_settlement="Чурек",
                start_lat=42.73,
                start_lng=23.53,
                end_lat=42.78,
                end_lng=23.74,
            ),
        ]
        matches = match_zones([], tt, [])
        assert len(matches) == 1
        assert matches[0].tolltracker is not None
        assert matches[0].bgtoll is None


class TestMergeMatch:
    def test_prefers_tolltracker_coordinates(self):
        from src.validator import ZoneMatch

        bg = _make_zone(source="bgtoll", start_lat=0.0, start_lng=0.0)
        tt = _make_zone(
            source="tolltracker",
            start_lat=42.55,
            start_lng=23.70,
            end_lat=42.43,
            end_lng=23.86,
        )
        m = ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.5)
        merged = merge_match(m)
        assert merged.start.lat == pytest.approx(42.55)
        assert merged.start.lng == pytest.approx(23.70)

    def test_prefers_bgtoll_km_markers(self):
        from src.validator import ZoneMatch

        bg = _make_zone(source="bgtoll", start_km="24+288", end_km="43+448")
        tt = _make_zone(
            source="tolltracker",
            start_km=None,
            end_km=None,
            start_lat=42.55,
            start_lng=23.70,
            end_lat=42.43,
            end_lng=23.86,
        )
        m = ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.5)
        merged = merge_match(m)
        assert merged.start.km_marker == "24+288"
        assert merged.end.km_marker == "43+448"

    def test_source_attribution(self):
        from src.validator import ZoneMatch

        bg = _make_zone(source="bgtoll")
        tt = _make_zone(
            source="tolltracker",
            start_lat=42.55,
            start_lng=23.70,
            end_lat=42.43,
            end_lng=23.86,
        )
        m = ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.5)
        merged = merge_match(m)
        assert merged.source == "bgtoll+tolltracker"

    def test_speed_limits_merged_per_field(self):
        from src.validator import ZoneMatch

        # KML absent -> TollTracker is the top source but lacks a motorcycle
        # limit; BG TOLL (lower priority) supplies it. Per-field merge must take
        # car from TollTracker yet fill motorcycle from BG TOLL — not drop it by
        # taking TollTracker's SpeedLimits object all-or-nothing.
        tt = _make_zone(
            source="tolltracker",
            car=130,
            start_lat=42.55,
            start_lng=23.70,
            end_lat=42.43,
            end_lng=23.86,
        )
        assert tt.speed_limits.motorcycle is None
        bg = _make_zone(source="bgtoll", car=140)
        bg = bg.model_copy(
            update={"speed_limits": bg.speed_limits.model_copy(update={"motorcycle": 100})}
        )
        m = ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.5)
        merged = merge_match(m)
        assert merged.speed_limits.car == 130  # TollTracker (higher priority)
        assert merged.speed_limits.motorcycle == 100  # filled from BG TOLL


class TestAssignIds:
    def test_id_format(self):
        zones = [
            _make_zone(direction="east", start_km="24+288", end_km="43+448"),
            _make_zone(direction="west", start_km="43+448", end_km="24+288"),
        ]
        result = assign_ids(zones)
        ids = {z.id for z in result}
        assert "trakiya-01-east" in ids
        assert "trakiya-01-west" in ids

    def test_no_duplicate_ids(self):
        zones = [
            _make_zone(
                direction="east",
                start_km="24+288",
                end_km="43+448",
                start_settlement="A",
                end_settlement="B",
            ),
            _make_zone(
                direction="west",
                start_km="43+448",
                end_km="24+288",
                start_settlement="B",
                end_settlement="A",
            ),
            _make_zone(
                direction="east",
                start_km="82+263",
                end_km="107+663",
                start_settlement="C",
                end_settlement="D",
            ),
        ]
        result = assign_ids(zones)
        ids = [z.id for z in result]
        assert len(ids) == len(set(ids))

    def test_adjacent_sections_within_100m_get_distinct_ids(self):
        # Two distinct same-direction sections whose km ranges round to the same
        # 100 m band collided under the old ``:.1f`` section key (duplicate ID →
        # the second zone was silently dropped by validate()). Metre precision
        # (``:.3f``) must keep them apart.
        zones = [
            _make_zone(direction="east", start_km="24+288", end_km="24+350"),
            _make_zone(direction="east", start_km="24+320", end_km="24+400"),
        ]
        result = assign_ids(zones)
        ids = [z.id for z in result]
        assert len(ids) == len(set(ids)), f"expected distinct IDs, got {ids}"

    def test_national_road_slug(self):
        zones = [
            _make_zone(
                road="Път I-4",
                direction="east",
                start_km="13+536",
                end_km="22+734",
                car=90,
                truck=80,
                bus=80,
            ),
        ]
        result = assign_ids(zones)
        assert result[0].id.startswith("i4-")


class TestValidate:
    def test_warns_on_missing_coordinates(self):
        zones = [
            _make_zone(start_lat=0.0, start_lng=0.0),
        ]
        zones = assign_ids(zones)
        valid, warnings = validate(zones)
        assert any("no GPS coordinates" in w for w in warnings)

    def test_removes_duplicates(self):
        zone = _make_zone()
        zone_with_id = zone.model_copy(update={"id": "trakiya-01-east"})
        _, warnings = validate([zone_with_id, zone_with_id])
        assert any("Duplicate ID" in w for w in warnings)

    def test_warns_on_missing_motorway(self):
        zones = [
            _make_zone(road="АМ Тракия"),
        ]
        zones = assign_ids(zones)
        _, warnings = validate(zones)
        assert any("АМ Хемус" in w for w in warnings)

    def test_flags_reversed_centerline(self):
        # Centerline stored end -> start (the section-control reversal bug):
        # validate must catch it as a defense-in-depth tripwire even though
        # align_centerline_to_endpoints would normally have fixed it upstream.
        z = _make_zone(
            start_lat=42.50, start_lng=23.80, end_lat=42.40, end_lng=23.90,
        ).model_copy(update={
            "id": "trakiya-01-east",
            "centerline": [[42.40, 23.90], [42.45, 23.85], [42.50, 23.80]],
        })
        _, warnings = validate([z])
        assert any("reversed" in w and "trakiya-01-east" in w for w in warnings)

    def test_aligned_centerline_no_reversal_warning(self):
        z = _make_zone(
            start_lat=42.50, start_lng=23.80, end_lat=42.40, end_lng=23.90,
        ).model_copy(update={
            "id": "trakiya-01-east",
            "centerline": [[42.50, 23.80], [42.45, 23.85], [42.40, 23.90]],
        })
        _, warnings = validate([z])
        assert not any("reversed" in w for w in warnings)


class TestMergeAll:
    def test_end_to_end_with_fixtures(self, bgtoll_html, tolltracker_zones):
        """End-to-end merge using both fixtures."""
        bg_zones = bgtoll_scrape(html=bgtoll_html)
        tt_zones = tolltracker_zones

        merged = merge_all(bg_zones, tt_zones, [])

        # Should have zones from both sources
        assert len(merged) > 0

        # All IDs should be unique
        ids = [z.id for z in merged]
        assert len(ids) == len(set(ids))

        # Should cover multiple motorways
        roads = {normalize_road(z.road) for z in merged}
        assert "АМ Тракия" in roads

    def test_merged_zones_have_coordinates(self, bgtoll_html, tolltracker_zones):
        """Zones matched with TollTracker should have GPS coordinates."""
        bg_zones = bgtoll_scrape(html=bgtoll_html)
        tt_zones = tolltracker_zones
        merged = merge_all(bg_zones, tt_zones, [])

        matched = [z for z in merged if "tolltracker" in z.source]
        for z in matched:
            assert z.start.lat != 0.0, f"Zone {z.id} has no start coordinates"


class TestSnapJunctionSeams:
    def _zone(self, zid, start, end, source="tolltracker", direction="east"):
        z = _make_zone(
            direction=direction,
            start_lat=start[0],
            start_lng=start[1],
            end_lat=end[0],
            end_lng=end[1],
            source=source,
        )
        z.id = zid
        return z

    def test_snaps_shared_camera_endpoints(self):
        # B starts ~15 m from where A ends — the same physical camera.
        a = self._zone("trakiya-01-east", (42.550, 23.703), (42.427, 23.855))
        b = self._zone("trakiya-02-east", (42.4271, 23.8551), (42.400, 23.990))
        snap_junction_seams([a, b])
        assert (b.start.lat, b.start.lng) == (a.end.lat, a.end.lng)

    def test_tolltracker_backed_endpoint_wins(self):
        # A merged without TollTracker; B's start is the higher-precision
        # coordinate, so A's end moves onto it.
        a = self._zone(
            "trakiya-01-east", (42.550, 23.703), (42.427, 23.855), source="kml"
        )
        b = self._zone("trakiya-02-east", (42.4271, 23.8551), (42.400, 23.990))
        b_start = (b.start.lat, b.start.lng)
        snap_junction_seams([a, b])
        assert (a.end.lat, a.end.lng) == b_start

    def test_opposite_direction_is_never_snapped(self):
        # The opposite carriageway's start sits near this zone's end but is
        # a genuinely distinct point.
        a = self._zone("trakiya-01-east", (42.550, 23.703), (42.427, 23.855))
        b = self._zone(
            "trakiya-01-west",
            (42.4271, 23.8551),
            (42.5501, 23.7031),
            direction="west",
        )
        before = (b.start.lat, b.start.lng)
        snap_junction_seams([a, b])
        assert (b.start.lat, b.start.lng) == before

    def test_wide_gap_left_for_validate_warning(self):
        a = self._zone("trakiya-01-east", (42.550, 23.703), (42.427, 23.855))
        b = self._zone("trakiya-02-east", (42.428, 23.856), (42.400, 23.990))
        before = (b.start.lat, b.start.lng)
        snap_junction_seams([a, b])  # ~140 m gap — beyond JUNCTION_SNAP_M
        assert (b.start.lat, b.start.lng) == before


class TestAlignCenterlineToEndpoints:
    """Reconcile OSM centerline geometry with the BG TOLL/TollTracker endpoints
    so the drawn line starts/ends exactly at the markers and distance_m matches
    the arc. Regression for struma-02-south: the centerline ended ~79 m short of
    the end marker and distance_m disagreed with the arc length."""

    def _zone(self, centerline, start, end):
        return Zone(
            id="test-01-north", road="АМ Струма", direction="north",
            description="A – B",
            start=ZoneEndpoint(lat=start[0], lng=start[1], settlement="A"),
            end=ZoneEndpoint(lat=end[0], lng=end[1], settlement="B"),
            distance_m=9999,
            speed_limits=SpeedLimits(car=140, truck=90, bus=100),
            centerline=[list(p) for p in centerline],
            source="test", last_verified="2026-04-12",
        )

    def test_large_gap_inserts_endpoints(self):
        # Centerline ~1113 m, endpoints ~111 m beyond each terminal.
        z = self._zone(
            centerline=[[42.000, 23.0], [42.010, 23.0]],
            start=[41.999, 23.0], end=[42.011, 23.0],
        )
        out = align_centerline_to_endpoints(z)
        assert len(out.centerline) == 4  # start + 2 original + end
        assert _haversine(*out.centerline[0], out.start.lat, out.start.lng) < 0.5
        assert _haversine(*out.centerline[-1], out.end.lat, out.end.lng) < 0.5
        assert out.distance_m == round(_polyline_length_m(out.centerline))

    def test_small_gap_snaps_in_place(self):
        # Terminal ~2 m from the endpoint — snapped, not inserted.
        z = self._zone(
            centerline=[[42.00002, 23.0], [42.010, 23.0]],
            start=[42.000, 23.0], end=[42.010, 23.0],
        )
        out = align_centerline_to_endpoints(z)
        assert len(out.centerline) == 2
        assert out.centerline[0] == [42.000, 23.0]
        assert out.centerline[-1] == [42.010, 23.0]

    def test_idempotent(self):
        z = self._zone(
            centerline=[[42.000, 23.0], [42.010, 23.0]],
            start=[41.999, 23.0], end=[42.011, 23.0],
        )
        once = align_centerline_to_endpoints(z)
        twice = align_centerline_to_endpoints(once)
        assert twice.centerline == once.centerline
        assert twice.distance_m == once.distance_m

    def test_reversed_centerline_is_oriented(self):
        # Centerline stored end->start: canonicalized so terminal[0] pairs start.
        z = self._zone(
            centerline=[[42.010, 23.0], [42.000, 23.0]],
            start=[41.999, 23.0], end=[42.011, 23.0],
        )
        out = align_centerline_to_endpoints(z)
        assert _haversine(*out.centerline[0], out.start.lat, out.start.lng) < 0.5
        assert _haversine(*out.centerline[-1], out.end.lat, out.end.lng) < 0.5

    def test_too_few_points_unchanged(self):
        z = self._zone(centerline=[[42.0, 23.0]], start=[42.0, 23.0], end=[42.01, 23.0])
        out = align_centerline_to_endpoints(z)
        assert out.centerline == [[42.0, 23.0]]


class TestOrientationReconciliation:
    """merge_match must reorient secondary sources to the primary before
    copying per-endpoint fields. Regression for the crossed-carriageway bug:
    21 shipped sections paired TollTracker geometry/Latin names with the
    opposite end's BG TOLL settlements and km markers (e.g. i5-05)."""

    def _tt_southbound_i5(self) -> Zone:
        # Казанлък (42.613, 25.435) -> Ягода (42.547, 25.559): southbound.
        return _make_zone(
            road="Път I-5",
            direction="south",
            start_settlement="Казанлък",
            end_settlement="Ягода",
            start_lat=42.613,
            start_lng=25.435,
            end_lat=42.547,
            end_lng=25.559,
            start_km=None,
            end_km=None,
            source="tolltracker",
            car=90,
            truck=80,
            bus=80,
        )

    def _bg_reversed_row(self) -> Zone:
        # Same physical carriageway, listed end-first (Ягода -> Казанлък),
        # carrying the authoritative km markers. No GPS coords.
        return _make_zone(
            road="Път I-5",
            direction="south",
            start_settlement="Ягода",
            end_settlement="Казанлък",
            start_km="212+716",
            end_km="199+527",
            source="bgtoll",
            car=90,
            truck=80,
            bus=80,
        )

    def test_reverse_matched_bg_fields_land_on_correct_ends(self):
        tt = self._tt_southbound_i5()
        bg = self._bg_reversed_row()
        merged = merge_match(ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.5))

        # Coordinates come from TollTracker, settlements/km from BG TOLL —
        # and they must describe the SAME end.
        assert merged.start.lat == pytest.approx(42.613)
        assert merged.start.settlement == "Казанлък"
        assert merged.start.km_marker == "199+527"
        assert merged.end.settlement == "Ягода"
        assert merged.end.km_marker == "212+716"
        assert merged.description == "Казанлък – Ягода"

    def test_forward_matched_bg_unchanged(self):
        tt = self._tt_southbound_i5()
        bg = _make_zone(
            road="Път I-5",
            direction="south",
            start_settlement="Казанлък",
            end_settlement="Ягода",
            start_km="199+527",
            end_km="212+716",
            source="bgtoll",
            car=90,
            truck=80,
            bus=80,
        )
        merged = merge_match(ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.5))
        assert merged.start.settlement == "Казанлък"
        assert merged.start.km_marker == "199+527"

    def test_geometric_flip_for_coordinate_sources(self):
        primary = self._tt_southbound_i5()
        # KML drew the same carriageway in the opposite point order.
        kml = _make_zone(
            road="Път I-5",
            direction="north",
            start_settlement="Ягода",
            end_settlement="Казанлък",
            start_lat=42.547,
            start_lng=25.559,
            end_lat=42.613,
            end_lng=25.435,
            start_km=None,
            end_km=None,
            source="kml",
            car=90,
            truck=80,
            bus=80,
        )
        oriented = _orient_to(kml, primary)
        assert oriented.start.lat == pytest.approx(42.613)
        assert oriented.start.settlement == "Казанлък"
        assert oriented.end.settlement == "Ягода"
        assert oriented.direction == "south"
        # Centerline reversed to run with the primary.
        assert oriented.centerline[0] == [42.613, 25.435]

    def test_km_fallback_when_settlements_disagree(self):
        # BG TOLL spells the settlements differently, so name matching is
        # inconclusive — km ordering vs the road's km direction decides.
        # I-5 km increases southward; primary is southbound, so km must
        # increase start -> end. This row decreases -> reversed.
        tt = self._tt_southbound_i5()
        bg = _make_zone(
            road="Път I-5",
            direction="south",
            start_settlement="с. Ягода (обл. Ст. Загора)",
            end_settlement="гр. Казанлък",
            start_km="212+716",
            end_km="199+527",
            source="bgtoll",
            car=90,
            truck=80,
            bus=80,
        )
        merged = merge_match(ZoneMatch(bgtoll=bg, tolltracker=tt, confidence=0.3))
        assert merged.start.km_marker == "199+527"
        assert merged.end.km_marker == "212+716"


class TestConsecutiveZoneMatching:
    """Consecutive zones share a camera: zone A ends where zone B starts.
    The matcher's weak signals must not pair a zone with its neighbor."""

    def test_km_edge_touch_does_not_overlap(self):
        a = _make_zone(start_km="100+000", end_km="110+000")
        b = _make_zone(start_km="110+000", end_km="120+000")
        assert not _km_ranges_overlap(a, b)

    def test_km_small_overlap_does_not_count(self):
        a = _make_zone(start_km="100+000", end_km="110+000")
        b = _make_zone(start_km="108+000", end_km="120+000")  # 20% of shorter
        assert not _km_ranges_overlap(a, b)

    def test_km_same_range_overlaps(self):
        a = _make_zone(start_km="100+000", end_km="110+000")
        b = _make_zone(start_km="100+200", end_km="109+800")
        assert _km_ranges_overlap(a, b)

    def test_km_reversed_same_range_overlaps(self):
        a = _make_zone(start_km="100+000", end_km="110+000")
        b = _make_zone(start_km="110+000", end_km="100+000")
        assert _km_ranges_overlap(a, b)

    def test_coords_shared_camera_is_not_close(self):
        # B starts exactly where A ends (shared camera) — single-endpoint
        # coincidence must NOT count as the same zone.
        a = _make_zone(start_lat=42.50, start_lng=23.70, end_lat=42.50, end_lng=23.80)
        b = _make_zone(start_lat=42.50, start_lng=23.80, end_lat=42.50, end_lng=23.90)
        assert not _coords_close(a, b)

    def test_coords_same_zone_is_close(self):
        a = _make_zone(start_lat=42.50, start_lng=23.70, end_lat=42.50, end_lng=23.80)
        b = _make_zone(start_lat=42.501, start_lng=23.701, end_lat=42.501, end_lng=23.801)
        assert _coords_close(a, b)

    def test_coords_reversed_same_zone_is_close(self):
        a = _make_zone(start_lat=42.50, start_lng=23.70, end_lat=42.50, end_lng=23.80)
        b = _make_zone(start_lat=42.50, start_lng=23.80, end_lat=42.50, end_lng=23.70)
        assert _coords_close(a, b)

    def test_consecutive_zones_do_not_cross_pair(self):
        # Two consecutive BG TOLL rows; TollTracker only has the SECOND
        # section, with settlements spelled differently (no name signal).
        # The remaining signals must not attach the TT zone to row A.
        bg_a = _make_zone(
            start_settlement="Камера1", end_settlement="Камера2",
            start_km="100+000", end_km="110+000",
        )
        bg_b = _make_zone(
            start_settlement="Камера2", end_settlement="Камера3",
            start_km="110+000", end_km="120+000",
        )
        tt_b = _make_zone(
            start_settlement="Kамера2-различно", end_settlement="Kамера3-различно",
            start_km="110+000", end_km="120+000",
            start_lat=42.50, start_lng=23.80, end_lat=42.50, end_lng=23.90,
            source="tolltracker",
        )
        matches = match_zones([bg_a, bg_b], [tt_b], [])
        for m in matches:
            if m.bgtoll is bg_a:
                assert m.tolltracker is None, "zone A stole its neighbor's data"
            if m.tolltracker is tt_b:
                assert m.bgtoll is not bg_a


class TestValidateConsistencyChecks:
    def _zone(self, **kw) -> Zone:
        base = _make_zone(
            start_lat=42.50, start_lng=23.70, end_lat=42.50, end_lng=23.90, **kw
        )
        return base

    def test_translit_mismatch_warns(self):
        z = self._zone().model_copy(update={"id": "trakiya-01-east"})
        z = z.model_copy(update={
            "start": z.start.model_copy(update={"settlement_latin": "Ihtiman"}),
        })
        _, warnings = validate([z])
        assert any("Latin name" in w for w in warnings)

    def test_translit_match_silent(self):
        z = self._zone().model_copy(update={"id": "trakiya-01-east"})
        z = z.model_copy(update={
            "start": z.start.model_copy(update={"settlement_latin": "Vakarel"}),
            "end": z.end.model_copy(update={"settlement_latin": "Ihtiman"}),
        })
        _, warnings = validate([z])
        assert not any("Latin name" in w for w in warnings)

    def test_translit_tolerates_qualifier_prefix(self):
        z = self._zone(start_settlement="м/у 18 и п.в.Илиянци").model_copy(
            update={"id": "trakiya-01-east"}
        )
        z = z.model_copy(update={
            "start": z.start.model_copy(update={"settlement_latin": "Iliyantsi"}),
            "description": f"{z.start.settlement} – {z.end.settlement}",
        })
        _, warnings = validate([z])
        assert not any("Latin name" in w for w in warnings)

    def test_km_direction_mismatch_warns(self):
        # Тракия km increases eastward; an "east" zone with decreasing km
        # is mislabeled (or its endpoints are crossed).
        z = self._zone(start_km="43+448", end_km="24+288").model_copy(
            update={"id": "trakiya-01-east"}
        )
        _, warnings = validate([z])
        assert any("implies" in w and "km" in w for w in warnings)

    def test_km_direction_consistent_silent(self):
        z = self._zone().model_copy(update={"id": "trakiya-01-east"})
        _, warnings = validate([z])
        assert not any("implies" in w for w in warnings)

    def test_description_mismatch_warns(self):
        z = self._zone().model_copy(
            update={"id": "trakiya-01-east", "description": "Ихтиман – Вакарел"}
        )
        _, warnings = validate([z])
        assert any("description" in w for w in warnings)

    def test_junction_gap_in_band_warns(self):
        # B starts ~220 m past A's end on the same road+direction.
        a = self._zone().model_copy(update={"id": "trakiya-01-east"})
        b = _make_zone(
            start_settlement="Ихтиман", end_settlement="Друго",
            start_km="43+448", end_km="60+000",
            start_lat=42.502, start_lng=23.90, end_lat=42.50, end_lng=23.99,
        ).model_copy(update={"id": "trakiya-02-east"})
        _, warnings = validate([a, b])
        assert any("junction gap" in w for w in warnings)

    def test_junction_coincident_silent(self):
        a = self._zone().model_copy(update={"id": "trakiya-01-east"})
        b = _make_zone(
            start_settlement="Ихтиман", end_settlement="Друго",
            start_km="43+448", end_km="60+000",
            start_lat=42.50, start_lng=23.90, end_lat=42.50, end_lng=23.99,
        ).model_copy(update={"id": "trakiya-02-east"})
        _, warnings = validate([a, b])
        assert not any("junction gap" in w for w in warnings)

    def test_junction_distant_zones_silent(self):
        a = self._zone().model_copy(update={"id": "trakiya-01-east"})
        b = _make_zone(
            start_settlement="Далечно", end_settlement="Друго",
            start_km="100+000", end_km="120+000",
            start_lat=42.50, start_lng=24.50, end_lat=42.50, end_lng=24.70,
        ).model_copy(update={"id": "trakiya-03-east"})
        _, warnings = validate([a, b])
        assert not any("junction gap" in w for w in warnings)


class TestRoadClassLimitPlausibility:
    """The 2026-08 Път I-8 regression: the BG TOLL KML publishes motorway
    limits (140/90/100) for a class-I road, and KML outranks every other
    source for limits."""

    def test_kml_motorway_limit_on_a_class_i_road_loses_to_bgtoll(self):
        kml = _make_zone(
            road="Път I-8",
            start_settlement="Ихтиман",
            end_settlement="Мирово",
            start_km="123+404",
            end_km="134+876",
            start_lat=42.4606211,
            start_lng=23.803103,
            end_lat=42.3793752,
            end_lng=23.8763595,
            source="kml",
            car=140,
            truck=90,
            bus=100,
        )
        bg = _make_zone(
            road="Път I-8",
            start_settlement="Ихтиман",
            end_settlement="Мирово",
            start_km="123+404",
            end_km="134+876",
            source="bgtoll",
            car=90,
            truck=80,
            bus=80,
        )
        merged = merge_match(ZoneMatch(bgtoll=bg, kml=kml, confidence=1.0))
        assert merged.speed_limits.car == 90
        assert merged.speed_limits.truck == 80
        assert merged.speed_limits.bus == 80

    def test_motorway_keeps_its_140(self):
        kml = _make_zone(
            road="АМ Тракия",
            start_lat=42.5432,
            start_lng=23.8234,
            end_lat=42.4321,
            end_lng=23.9876,
            source="kml",
            car=140,
        )
        bg = _make_zone(road="АМ Тракия", source="bgtoll", car=130)
        merged = merge_match(ZoneMatch(bgtoll=bg, kml=kml, confidence=1.0))
        assert merged.speed_limits.car == 140

    def test_implausible_everywhere_keeps_top_source_and_warns(self):
        kml = _make_zone(
            road="Път I-8",
            start_lat=42.46,
            start_lng=23.80,
            end_lat=42.37,
            end_lng=23.87,
            source="kml",
            car=140,
            truck=90,
            bus=100,
        )
        merged = merge_match(ZoneMatch(kml=kml, confidence=1.0))
        assert merged.speed_limits.car == 140
        _, warnings = validate(assign_ids([merged]))
        assert any("impossible car limit" in w for w in warnings)


class TestUnknownRoadWarning:
    def test_road_missing_from_the_direction_tables_is_named(self):
        z = _make_zone(
            road="Път I-9",
            start_lat=42.46,
            start_lng=23.80,
            end_lat=42.37,
            end_lng=23.87,
            car=90,
            truck=80,
            bus=80,
        )
        _, warnings = validate(assign_ids([z]))
        assert any("ROAD_AXIS" in w and "Път I-9" in w for w in warnings)

    def test_a_known_road_produces_no_such_warning(self):
        z = _make_zone(
            road="Път I-8",
            start_lat=42.46,
            start_lng=23.80,
            end_lat=42.37,
            end_lng=23.87,
            car=90,
            truck=80,
            bus=80,
        )
        _, warnings = validate(assign_ids([z]))
        assert not any("ROAD_AXIS" in w for w in warnings)


class TestBgTollAuthorityForLimits:
    """BG TOLL is the authority — and for *limits* that means the KML.

    `bgtoll_scraper` scrapes no limits; it substitutes a statutory road-class
    constant. Letting that constant outrank BG TOLL's own published KML value
    would ship 140 on АМ Европа where BG TOLL says 120.
    """

    def _europa(self, source, car, motorcycle):
        z = _make_zone(
            road="АМ Европа",
            direction="east",
            start_settlement="м/у 18 и п.в.Илиянци",
            end_settlement="Чепинци",
            start_km="50+427",
            end_km="60+705",
            start_lat=42.7653671,
            start_lng=23.2969379,
            end_lat=42.7196194,
            end_lng=23.4004068,
            distance_m=10260,
            source=source,
            car=car,
            truck=90,
            bus=100,
        )
        return z.model_copy(
            update={"speed_limits": SpeedLimits(
                car=car, truck=90, bus=100, motorcycle=motorcycle,
            )}
        )

    def test_kml_beats_the_bgtoll_road_class_default(self):
        # The real regression: 140 here is our own MOTORWAY_SPEED_LIMITS
        # constant, not anything BG TOLL published.
        kml = self._europa("kml", car=120, motorcycle=120)
        bg = self._europa("bgtoll", car=140, motorcycle=140)
        merged = merge_match(ZoneMatch(bgtoll=bg, kml=kml, confidence=1.0))
        assert merged.speed_limits.car == 120
        assert merged.speed_limits.motorcycle == 120

    def test_the_bgtoll_default_still_fills_a_gap_the_kml_leaves(self):
        kml = self._europa("kml", car=120, motorcycle=120).model_copy(
            update={"speed_limits": SpeedLimits(car=120, truck=None, bus=None)}
        )
        bg = self._europa("bgtoll", car=140, motorcycle=140)
        merged = merge_match(ZoneMatch(bgtoll=bg, kml=kml, confidence=1.0))
        assert merged.speed_limits.car == 120       # authority wins
        assert merged.speed_limits.truck == 90      # gap filled from the default
        assert merged.speed_limits.bus == 100


class TestKmlIsTheAuthority:
    """The BG TOLL KML wins every field it *authors*.

    The carve-outs below are pinned just as hard: each was measured to make the
    data worse (see scrapers/CLAUDE.md "The BG TOLL KML is the authority"), so a
    future tidy-up that "makes the precedence consistent" must fail here rather
    than silently ship coarser geometry or crossed settlement names.
    """

    def _pair(self):
        common = dict(
            start_settlement="Ихтиман",
            end_settlement="Мирово",
            start_km="123+404",
            end_km="134+876",
        )
        kml = _make_zone(
            road="Път I-8",
            start_lat=42.4606211, start_lng=23.803103,
            end_lat=42.3793752, end_lng=23.8763595,
            source="kml", car=90, truck=80, bus=80, **common,
        )
        # Deliberately different coordinates so precedence is observable.
        tt = _make_zone(
            road="Път I-8",
            start_lat=42.4600000, start_lng=23.804000,
            end_lat=42.3800000, end_lng=23.875000,
            source="tolltracker", car=90, truck=80, bus=80, **common,
        )
        bg = _make_zone(road="Път I-8", source="bgtoll", car=90, truck=80, bus=80, **common)
        return kml, tt, bg

    def test_kml_wins_road_type(self):
        kml, tt, _ = self._pair()
        kml = kml.model_copy(update={"road_type": "road"})
        tt = tt.model_copy(update={"road_type": "motorway"})
        merged = merge_match(ZoneMatch(tolltracker=tt, kml=kml, confidence=1.0))
        assert merged.road_type == "road"

    def test_kml_wins_the_centerline(self):
        kml, tt, _ = self._pair()
        merged = merge_match(ZoneMatch(tolltracker=tt, kml=kml, confidence=1.0))
        assert merged.centerline == kml.centerline

    # ── carve-outs ──────────────────────────────────────────────────────────

    def test_carveout_coordinates_come_from_tolltracker_not_kml(self):
        """Instrument precision, not authority — KML endpoints broke 2 of 24
        junction seams and added 9 backwards-jog zones when measured."""
        kml, tt, _ = self._pair()
        merged = merge_match(ZoneMatch(tolltracker=tt, kml=kml, confidence=1.0))
        assert merged.start.lat == tt.start.lat
        assert merged.start.lng == tt.start.lng

    def test_carveout_settlements_come_from_bgtoll_not_kml(self):
        """The KML splits one segment title and assigns halves by proximity, so
        they can cross (they do on I-8). BG TOLL states them per endpoint.

        TollTracker is included because it is the orientation primary in
        production: BG TOLL carries no coordinates, so `_orient_to` falls back
        to matching *settlement names* against the primary — with the KML as
        primary a crossed pair there would drag BG TOLL's names across with it.
        Another reason the coordinate carve-out matters.
        """
        kml, tt, bg = self._pair()
        kml = kml.model_copy(update={
            "start": kml.start.model_copy(update={"settlement": "Мирово"}),
            "end": kml.end.model_copy(update={"settlement": "Ихтиман"}),
        })
        merged = merge_match(
            ZoneMatch(bgtoll=bg, tolltracker=tt, kml=kml, confidence=1.0)
        )
        assert merged.start.settlement == "Ихтиман"
        assert merged.end.settlement == "Мирово"

    def test_carveout_km_markers_come_from_bgtoll_not_kml(self):
        kml, tt, bg = self._pair()
        kml = kml.model_copy(update={
            "start": kml.start.model_copy(update={"km_marker": "999+999"}),
        })
        merged = merge_match(
            ZoneMatch(bgtoll=bg, tolltracker=tt, kml=kml, confidence=1.0)
        )
        assert merged.start.km_marker == "123+404"


class TestOnlyBgTollBackedZonesShip:
    """BG TOLL runs the cameras, so a section it publishes nowhere is one we
    have no authority for. Announcing an enforcement zone that does not exist is
    worse than staying quiet, so TollTracker-only zones are dropped."""

    def _z(self, source, **kw):
        return _make_zone(
            start_lat=42.5432, start_lng=23.8234,
            end_lat=42.4321, end_lng=23.9876,
            source=source, **kw,
        )

    def test_tolltracker_only_zone_is_dropped(self):
        kept, dropped = drop_unofficial_zones([self._z("tolltracker")])
        assert kept == []
        assert len(dropped) == 1

    def test_osm_only_zone_is_dropped(self):
        kept, dropped = drop_unofficial_zones([self._z("osm")])
        assert kept == []
        assert len(dropped) == 1

    def test_a_zone_the_kml_backs_is_kept(self):
        """The KML *is* BG TOLL — its own published map."""
        kept, dropped = drop_unofficial_zones([self._z("tolltracker+kml")])
        assert len(kept) == 1
        assert dropped == []

    def test_a_zone_the_faq_tables_back_is_kept(self):
        kept, dropped = drop_unofficial_zones([self._z("bgtoll+tolltracker")])
        assert len(kept) == 1
        assert dropped == []

    def test_the_shipped_data_is_entirely_bg_toll_backed(self):
        import json
        from pathlib import Path

        zones = json.loads(
            (Path(__file__).parent.parent / "data" / "zones.json").read_text("utf-8")
        )["zones"]
        unbacked = [
            z["id"] for z in zones
            if not (OFFICIAL_SOURCES & set(z["source"].split("+")))
        ]
        assert unbacked == [], f"shipped zones with no BG TOLL source: {unbacked}"
