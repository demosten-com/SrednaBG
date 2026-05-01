# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the KML/KMZ scraper."""

import pytest

from src.kml_scraper import (
    infer_direction,
    parse_kml,
    scrape,
    segments_to_zones,
    _parse_description,
    _parse_road_name,
    _parse_settlement_name,
)


class TestParseRoadName:
    def test_motorway_a1(self):
        assert _parse_road_name("A-1") == "АМ Тракия"

    def test_motorway_a3(self):
        assert _parse_road_name("A-3") == "АМ Струма"

    def test_motorway_a6(self):
        assert _parse_road_name("A-6") == "АМ Европа"

    def test_national_road(self):
        assert _parse_road_name("I-5") == "Път I-5"

    def test_class_2_road(self):
        assert _parse_road_name("II-55") == "Път II-55"

    def test_unknown_road(self):
        assert _parse_road_name("X-99") == "X-99"


class TestParseDescription:
    def test_motorway_segment(self):
        desc = (
            'Любимец-Момково    <br>       <br>   '
            'Сертифициран участък    <br>   Път   A-4    <br>   '
            'Дължина на участъка в метри   5907    <br>   '
            'Категория А,А2,В   - 140 km/h    <br>   '
            'Категория В1   - 70 km/h    <br>   '
            'Категория BE,C1,C1E,D,D1,D1E,DE   - 100 km/h    <br>   '
            'Категория C и CE   - 90 km/h'
        )
        result = _parse_description(desc)
        assert result["road_id"] == "A-4"
        assert result["distance_m"] == 5907
        assert result["car_limit"] == 140
        assert result["truck_limit"] == 90
        assert result["bus_limit"] == 100

    def test_national_road_segment(self):
        desc = (
            'Път   I-5    <br>   '
            'Дължина на участъка в метри   13212    <br>   '
            'Категория А,А2,В   - 90 km/h    <br>   '
            'Категория C и CE   - 80 km/h'
        )
        result = _parse_description(desc)
        assert result["road_id"] == "I-5"
        assert result["distance_m"] == 13212
        assert result["car_limit"] == 90
        assert result["truck_limit"] == 80


class TestParseSettlementName:
    def test_with_spaces(self):
        a, b = _parse_settlement_name("Казанлък - Ягода")
        assert a == "Казанлък"
        assert b == "Ягода"

    def test_with_dash(self):
        a, b = _parse_settlement_name("Любимец-Момково")
        assert a == "Любимец"
        assert b == "Момково"

    def test_with_long_name(self):
        a, b = _parse_settlement_name("София - тунел Мало Бучино")
        assert a == "София"
        assert b == "тунел Мало Бучино"


class TestInferDirection:
    def test_trakiya_east(self):
        # Вакарел (west) -> Ихтиман (east)
        d = infer_direction(42.55, 23.70, 42.43, 23.85, "АМ Тракия")
        assert d == "east"

    def test_trakiya_west(self):
        # Ихтиман (east) -> Вакарел (west)
        d = infer_direction(42.43, 23.85, 42.55, 23.70, "АМ Тракия")
        assert d == "west"

    def test_struma_south(self):
        # Сандански (north) -> Дамяница (south)
        d = infer_direction(41.573, 23.240, 41.515, 23.272, "АМ Струма")
        assert d == "south"

    def test_unknown_road(self):
        d = infer_direction(42.0, 24.0, 42.0, 25.0, "Unknown")
        assert d == "east"


class TestParseKml:
    def test_parses_cameras_and_segments(self, kml_text):
        cameras, segments = parse_kml(kml_text)
        assert len(cameras) == 6
        assert len(segments) == 3

    def test_camera_has_coordinates(self, kml_text):
        cameras, _ = parse_kml(kml_text)
        for cam in cameras:
            assert cam["lat"] != 0
            assert cam["lng"] != 0

    def test_segment_has_centerline(self, kml_text):
        _, segments = parse_kml(kml_text)
        for seg in segments:
            assert len(seg["centerline"]) >= 2


class TestSegmentsToZones:
    def test_produces_two_zones_per_segment(self, kml_text):
        cameras, segments = parse_kml(kml_text)
        zones = segments_to_zones(segments, cameras)
        assert len(zones) == 6  # 3 segments x 2 directions

    def test_forward_reverse_directions(self, kml_text):
        cameras, segments = parse_kml(kml_text)
        zones = segments_to_zones(segments, cameras)
        # Each pair should have opposite directions
        for i in range(0, len(zones), 2):
            fwd, rev = zones[i], zones[i + 1]
            opposites = {"east": "west", "west": "east", "north": "south", "south": "north"}
            assert fwd.direction == opposites[rev.direction]

    def test_zones_have_coordinates(self, kml_text):
        cameras, segments = parse_kml(kml_text)
        zones = segments_to_zones(segments, cameras)
        for z in zones:
            assert z.start.lat != 0
            assert z.start.lng != 0

    def test_zones_have_speed_limits(self, kml_text):
        cameras, segments = parse_kml(kml_text)
        zones = segments_to_zones(segments, cameras)
        for z in zones:
            assert z.speed_limits.car > 0
            assert z.speed_limits.truck > 0

    def test_reverse_centerline_is_reversed(self, kml_text):
        cameras, segments = parse_kml(kml_text)
        zones = segments_to_zones(segments, cameras)
        fwd, rev = zones[0], zones[1]
        assert fwd.centerline[0] == rev.centerline[-1]
        assert fwd.centerline[-1] == rev.centerline[0]


class TestScrape:
    def test_scrape_with_kml(self, kml_text):
        zones = scrape(kml_text=kml_text)
        assert len(zones) == 6
        assert all(z.source == "kml" for z in zones)

    def test_contains_multiple_roads(self, kml_text):
        zones = scrape(kml_text=kml_text)
        roads = {z.road for z in zones}
        assert "АМ Тракия" in roads
        assert "АМ Струма" in roads
        assert "Път I-5" in roads
