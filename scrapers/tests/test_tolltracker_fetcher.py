# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the TollTracker.eu fetcher."""


import pytest

from src.tolltracker_fetcher import (
    extract_segments,
    infer_direction,
    parse_segment,
    scrape,
)


class TestExtractSegments:
    def test_extracts_segments(self, tolltracker_html):
        segments = extract_segments(tolltracker_html)
        assert len(segments) == 6  # 6 segments in fixture

    def test_raises_on_missing(self):
        with pytest.raises(ValueError, match="speedEnforcementSegments"):
            extract_segments("<html><body></body></html>")


class TestParseSegment:
    def test_produces_two_zones(self, tolltracker_html):
        segments = extract_segments(tolltracker_html)
        fwd, rev = parse_segment(segments[0])
        assert fwd.direction != rev.direction

    def test_forward_zone_properties(self, tolltracker_html):
        # t10: Ихтиман -> Вакарел on Тракия
        segments = extract_segments(tolltracker_html)
        t10 = next(s for s in segments if s["properties"]["id"] == "t10")
        fwd, _ = parse_segment(t10)

        assert fwd.road == "АМ Тракия"
        assert fwd.distance_m == pytest.approx(19196, abs=1)
        assert fwd.speed_limits.car == 140
        assert fwd.speed_limits.truck == 90
        assert fwd.speed_limits.bus == 100
        assert fwd.source == "tolltracker"

    def test_reverse_zone_swaps_endpoints(self, tolltracker_html):
        segments = extract_segments(tolltracker_html)
        fwd, rev = parse_segment(segments[0])

        assert fwd.start.settlement == rev.end.settlement
        assert fwd.end.settlement == rev.start.settlement
        assert fwd.start.lat == rev.end.lat
        assert fwd.start.lng == rev.end.lng

    def test_centerline_coordinate_swap(self, tolltracker_html):
        """Verify GeoJSON [lng, lat] is converted to schema [lat, lng]."""
        segments = extract_segments(tolltracker_html)
        t10 = next(s for s in segments if s["properties"]["id"] == "t10")
        fwd, _ = parse_segment(t10)

        # First coordinate of t10: GeoJSON [23.8545, 42.4267] -> schema [42.4267, 23.8545]
        first_point = fwd.centerline[0]
        assert first_point[0] == pytest.approx(42.4267, abs=0.001)  # lat
        assert first_point[1] == pytest.approx(23.8545, abs=0.001)  # lng

    def test_reverse_centerline_is_reversed(self, tolltracker_html):
        segments = extract_segments(tolltracker_html)
        fwd, rev = parse_segment(segments[0])

        assert fwd.centerline[0] == rev.centerline[-1]
        assert fwd.centerline[-1] == rev.centerline[0]

    def test_national_road_speed_limits(self, tolltracker_html):
        segments = extract_segments(tolltracker_html)
        i1 = next(s for s in segments if s["properties"]["id"] == "i1-10")
        fwd, _ = parse_segment(i1)

        assert fwd.road == "Път I-1"
        assert fwd.speed_limits.car == 90
        assert fwd.speed_limits.truck == 80
        assert fwd.speed_limits.bus == 80


class TestInferDirection:
    def test_trakiya_west(self):
        """Ихтиман to Вакарел on Тракия = west (lng decreasing)."""
        direction = infer_direction(42.427, 23.855, 42.550, 23.703, "АМ Тракия")
        assert direction == "west"

    def test_trakiya_east(self):
        """Вакарел to Ихтиман = east (lng increasing)."""
        direction = infer_direction(42.550, 23.703, 42.427, 23.855, "АМ Тракия")
        assert direction == "east"

    def test_hemus_east(self):
        direction = infer_direction(42.725, 23.528, 42.779, 23.736, "АМ Хемус")
        assert direction == "east"

    def test_struma_north(self):
        """Дамяница to Сандански = north (lat increasing, Struma goes south)."""
        direction = infer_direction(41.515, 23.272, 41.573, 23.240, "АМ Струма")
        assert direction == "north"

    def test_unknown_road_fallback(self):
        """Unknown road uses bearing-based heuristic."""
        direction = infer_direction(42.0, 24.0, 42.0, 25.0, "Unknown Road")
        assert direction == "east"


class TestScrape:
    def test_scrape_with_html(self, tolltracker_html):
        zones = scrape(html=tolltracker_html)
        # 6 segments x 2 directions = 12 zones
        assert len(zones) == 12
        assert all(z.source == "tolltracker" for z in zones)

    def test_all_zones_have_coordinates(self, tolltracker_html):
        zones = scrape(html=tolltracker_html)
        for z in zones:
            assert z.start.lat != 0
            assert z.start.lng != 0
            assert z.end.lat != 0
            assert z.end.lng != 0

    def test_all_zones_have_centerlines(self, tolltracker_html):
        zones = scrape(html=tolltracker_html)
        for z in zones:
            assert len(z.centerline) >= 2

    def test_contains_multiple_roads(self, tolltracker_html):
        zones = scrape(html=tolltracker_html)
        roads = {z.road for z in zones}
        assert "АМ Тракия" in roads
        assert "АМ Хемус" in roads
        assert "АМ Струма" in roads
        assert "АМ Марица" in roads
