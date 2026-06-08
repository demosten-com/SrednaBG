# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the zone validator and merger."""

import pytest

from src.bgtoll_scraper import scrape as bgtoll_scrape
from src.tolltracker_fetcher import scrape as tolltracker_scrape
from src.validator import (
    _haversine,
    _polyline_length_m,
    align_centerline_to_endpoints,
    assign_ids,
    match_zones,
    merge_all,
    merge_match,
    normalize_road,
    road_slug,
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
    def test_end_to_end_with_fixtures(self, bgtoll_html, tolltracker_html):
        """End-to-end merge using both fixtures."""
        bg_zones = bgtoll_scrape(html=bgtoll_html)
        tt_zones = tolltracker_scrape(html=tolltracker_html)

        merged = merge_all(bg_zones, tt_zones, [])

        # Should have zones from both sources
        assert len(merged) > 0

        # All IDs should be unique
        ids = [z.id for z in merged]
        assert len(ids) == len(set(ids))

        # Should cover multiple motorways
        roads = {normalize_road(z.road) for z in merged}
        assert "АМ Тракия" in roads

    def test_merged_zones_have_coordinates(self, bgtoll_html, tolltracker_html):
        """Zones matched with TollTracker should have GPS coordinates."""
        bg_zones = bgtoll_scrape(html=bgtoll_html)
        tt_zones = tolltracker_scrape(html=tolltracker_html)
        merged = merge_all(bg_zones, tt_zones, [])

        matched = [z for z in merged if "tolltracker" in z.source]
        for z in matched:
            assert z.start.lat != 0.0, f"Zone {z.id} has no start coordinates"


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
