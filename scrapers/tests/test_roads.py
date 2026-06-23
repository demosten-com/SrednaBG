# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the shared road tables and direction inference.

Direction labels are geographic truth (lat increasing = north, lng
increasing = east). Regression suite for the inverted lat-axis entries
that shipped opposite-carriageway labels on I-1, I-3, I-5 and II-55.
"""

import pytest

from src.roads import (
    ROAD_AXIS,
    ROAD_DIRECTIONS,
    infer_direction_from_coords,
    infer_direction_from_km,
    is_motorway,
    normalize_road,
    opposite_direction,
    road_slug,
)


class TestInferDirectionFromCoords:
    def test_i5_northbound_is_north(self):
        # Ягода (42.55, 25.56) -> Казанлък (42.61, 25.43): lat increases.
        # The shipped bug labeled this "south" and crossed the carriageways.
        d = infer_direction_from_coords(42.547, 25.559, 42.613, 25.435, "Път I-5")
        assert d == "north"

    def test_i5_southbound_is_south(self):
        d = infer_direction_from_coords(42.613, 25.435, 42.547, 25.559, "Път I-5")
        assert d == "south"

    def test_i1_lat_axis_truthful(self):
        # Жеглица -> Срацимирово runs along I-1 (lat axis).
        assert (
            infer_direction_from_coords(43.93, 22.66, 43.85, 22.65, "Път I-1")
            == "south"
        )
        assert (
            infer_direction_from_coords(43.85, 22.65, 43.93, 22.66, "Път I-1")
            == "north"
        )

    def test_europa_is_lng_axis(self):
        # The enforced АМ Европа section (Severna Tangenta) runs E-W:
        # п.в. Илиянци (lng 23.297) <-> Чепинци (lng 23.400).
        d = infer_direction_from_coords(42.765, 23.297, 42.720, 23.400, "АМ Европа")
        assert d == "east"
        d = infer_direction_from_coords(42.720, 23.400, 42.765, 23.297, "АМ Европа")
        assert d == "west"

    def test_struma_north(self):
        d = infer_direction_from_coords(41.515, 23.272, 41.573, 23.240, "АМ Струма")
        assert d == "north"

    def test_trakiya_east_west(self):
        assert (
            infer_direction_from_coords(42.55, 23.70, 42.43, 23.85, "АМ Тракия")
            == "east"
        )
        assert (
            infer_direction_from_coords(42.43, 23.85, 42.55, 23.70, "АМ Тракия")
            == "west"
        )

    def test_accepts_uncanonicalized_road_name(self):
        d = infer_direction_from_coords(42.55, 23.70, 42.43, 23.85, 'АМ "Тракия"')
        assert d == "east"

    def test_unknown_road_bearing_fallback(self):
        assert (
            infer_direction_from_coords(42.0, 24.0, 42.0, 25.0, "Unknown") == "east"
        )
        assert (
            infer_direction_from_coords(42.0, 24.0, 43.0, 24.0, "Unknown") == "north"
        )


class TestInferDirectionFromKm:
    def test_i5_km_increases_southward(self):
        # km 0 is at Ruse (north); markers grow toward Kardzhali (south).
        assert infer_direction_from_km("Път I-5", 199.527, 212.716) == "south"
        assert infer_direction_from_km("Път I-5", 212.716, 199.527) == "north"

    def test_europa_km_increases_eastward(self):
        # km 50+427 = п.в. Илиянци (west), 60+705 = Чепинци (east).
        assert infer_direction_from_km("АМ Европа", 50.427, 60.705) == "east"

    def test_trakiya(self):
        assert infer_direction_from_km("АМ Тракия", 24.288, 43.448) == "east"

    def test_unknown_road_defaults_east_west(self):
        assert infer_direction_from_km("Unknown", 1.0, 2.0) == "east"
        assert infer_direction_from_km("Unknown", 2.0, 1.0) == "west"


class TestTableConsistency:
    def test_every_km_direction_road_has_an_axis(self):
        assert set(ROAD_DIRECTIONS) == set(ROAD_AXIS)

    def test_km_directions_lie_on_the_road_axis(self):
        # A road whose dominant axis is lat can only run north/south, etc.
        # Catches a future table edit that reintroduces a label inversion.
        for road, (inc_dir, dec_dir) in ROAD_DIRECTIONS.items():
            expected = (
                {"north", "south"} if ROAD_AXIS[road] == "lat" else {"east", "west"}
            )
            assert {inc_dir, dec_dir} == expected, road


class TestNames:
    def test_normalize_road(self):
        assert normalize_road('АМ "Тракия"') == "АМ Тракия"
        assert normalize_road("I-5") == "Път I-5"
        assert (
            normalize_road('АМ "Европа" (Северна скоростна тангента)') == "АМ Европа"
        )

    def test_road_slug(self):
        assert road_slug("АМ Тракия") == "trakiya"
        assert road_slug("Път II-55") == "ii55"

    def test_opposite_direction(self):
        assert opposite_direction("north") == "south"
        assert opposite_direction("east") == "west"

    def test_opposite_direction_rejects_unknown(self):
        with pytest.raises(ValueError, match="unknown direction"):
            opposite_direction("East")


class TestIsMotorway:
    def test_bgtoll_canonical_names(self):
        assert is_motorway("АМ Тракия") is True
        assert is_motorway("АМ Струма") is True

    def test_kml_and_bare_road_codes(self):
        # KML uses "A-1"; some sources use the bare "A1" form.
        assert is_motorway("A-1") is True
        assert is_motorway("A2") is True

    def test_national_roads_are_not_motorways(self):
        assert is_motorway("Път I-5") is False
        assert is_motorway("I-5") is False
        assert is_motorway("II-55") is False
