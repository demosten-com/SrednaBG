# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the BG TOLL scraper."""

import pytest

from src.bgtoll_scraper import (
    infer_direction,
    normalize_road_name,
    parse_html,
    parse_km,
    parse_point_text,
    road_slug,
    scrape,
    to_zones,
)


class TestParseKm:
    def test_simple(self):
        assert parse_km("24+288") == pytest.approx(24.288)

    def test_large(self):
        assert parse_km("107+663") == pytest.approx(107.663)

    def test_zero_prefix(self):
        assert parse_km("0+672") == pytest.approx(0.672)

    def test_large_meters(self):
        assert parse_km("357+949") == pytest.approx(357.949)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_km("no-km-here")


class TestParsePointText:
    def test_standard_format(self):
        settlement, km = parse_point_text("Вакарел (км 24+288)")
        assert settlement == "Вакарел"
        assert km == "24+288"

    def test_long_name(self):
        settlement, km = parse_point_text("Горни Богров (км 6+804)")
        assert settlement == "Горни Богров"
        assert km == "6+804"

    def test_complex_name(self):
        settlement, km = parse_point_text(
            "м/у 18 и п.в.Илиянци (км 50+427)"
        )
        assert settlement == "м/у 18 и п.в.Илиянци"
        assert km == "50+427"

    def test_no_km_marker(self):
        settlement, km = parse_point_text("Some text without km")
        assert settlement == "Some text without km"
        assert km is None


class TestNormalizeRoadName:
    def test_motorway_with_quotes(self):
        assert normalize_road_name('АМ "Тракия"') == "АМ Тракия"

    def test_motorway_without_quotes(self):
        assert normalize_road_name("АМ Тракия") == "АМ Тракия"

    def test_national_road(self):
        assert normalize_road_name("I-1") == "Път I-1"

    def test_national_road_class_2(self):
        assert normalize_road_name("II-55") == "Път II-55"

    def test_europa_with_parenthetical(self):
        assert (
            normalize_road_name('АМ "Европа" (Северна скоростна тангента)')
            == "АМ Европа"
        )


class TestRoadSlug:
    def test_motorway(self):
        assert road_slug("АМ Тракия") == "trakiya"

    def test_national_road(self):
        assert road_slug("Път I-4") == "i4"

    def test_class_2_road(self):
        assert road_slug("Път II-55") == "ii55"


class TestInferDirection:
    def test_trakiya_east(self):
        assert infer_direction("АМ Тракия", 24.288, 43.448) == "east"

    def test_trakiya_west(self):
        assert infer_direction("АМ Тракия", 43.448, 24.288) == "west"

    def test_struma_south(self):
        assert infer_direction("АМ Струма", 0.672, 8.226) == "south"

    def test_struma_north(self):
        assert infer_direction("АМ Струма", 8.226, 0.672) == "north"

    def test_europa_north(self):
        assert infer_direction("АМ Европа", 50.427, 60.705) == "north"


class TestParseHtml:
    def test_parses_fixture(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        assert len(sections) == 20  # 10 physical sections x 2 directions

    def test_first_section(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        first = sections[0]
        assert 'АМ "Тракия"' in first.road
        assert "Вакарел" in first.start_text
        assert "24+288" in first.start_text
        assert "Ихтиман" in first.end_text

    def test_contains_all_motorways(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        roads = {s.road for s in sections}
        assert 'АМ "Тракия"' in roads
        assert 'АМ "Хемус"' in roads
        assert 'АМ "Струма"' in roads
        assert 'АМ "Марица"' in roads
        assert 'АМ "Европа"' in roads

    def test_empty_html(self):
        sections = parse_html("<html><body></body></html>")
        assert sections == []


class TestToZones:
    def test_converts_sections(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        zones = to_zones(sections)
        assert len(zones) == 20

    def test_zone_has_correct_source(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        zones = to_zones(sections)
        assert all(z.source == "bgtoll" for z in zones)

    def test_zone_has_placeholder_coords(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        zones = to_zones(sections)
        for z in zones:
            assert z.start.lat == 0.0
            assert z.start.lng == 0.0

    def test_zone_has_km_markers(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        zones = to_zones(sections)
        for z in zones:
            assert z.start.km_marker is not None
            assert z.end.km_marker is not None

    def test_zone_distance_positive(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        zones = to_zones(sections)
        for z in zones:
            assert z.distance_m > 0

    def test_trakiya_directions(self, bgtoll_html):
        sections = parse_html(bgtoll_html)
        zones = to_zones(sections)
        trakiya = [z for z in zones if "Тракия" in z.road]
        directions = {z.direction for z in trakiya}
        assert "east" in directions
        assert "west" in directions


class TestScrape:
    def test_scrape_with_html(self, bgtoll_html):
        zones = scrape(html=bgtoll_html)
        assert len(zones) == 20
        assert all(z.source == "bgtoll" for z in zones)
