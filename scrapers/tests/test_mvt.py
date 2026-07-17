# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the minimal Mapbox Vector Tile decoder."""

import gzip

import pytest

from src import mvt
from tests.mvt_encoding import encode_tile


def _line_tile(**extra_props) -> bytes:
    props = {
        "id": "S-PL-TEST01",
        "title": "А - Б, Тракия",
        "country": "BG",
        "type": "section_control",
        "speed_limit": 140,
        "oneway": True,
        "heading": 90.5,
        **extra_props,
    }
    return encode_tile({
        "polylines": {
            "extent": 4096,
            "features": [{
                "props": props,
                "type": 2,
                "parts": [[(0, 100), (2048, 150), (4096, 200)]],
            }],
        },
    })


class TestDecode:
    def test_round_trip_layer_and_geometry(self):
        layers = mvt.decode(_line_tile())
        assert set(layers) == {"polylines"}
        layer = layers["polylines"]
        assert layer["extent"] == 4096
        (feature,) = layer["features"]
        assert feature["type"] == 2
        assert feature["parts"] == [[(0, 100), (2048, 150), (4096, 200)]]

    def test_round_trip_property_types(self):
        (feature,) = mvt.decode(_line_tile())["polylines"]["features"]
        props = feature["props"]
        assert props["id"] == "S-PL-TEST01"
        assert props["title"] == "А - Б, Тракия"  # UTF-8 Cyrillic survives
        assert props["speed_limit"] == 140
        assert props["oneway"] is True
        assert props["heading"] == pytest.approx(90.5)

    def test_gzipped_tile_is_transparent(self):
        raw = _line_tile()
        assert mvt.decode(gzip.compress(raw)) == mvt.decode(raw)

    def test_negative_buffer_coordinates(self):
        # Clipped geometry legitimately extends outside [0, extent] into the
        # tile buffer — negative zigzag deltas must decode correctly.
        tile = encode_tile({
            "polylines": {
                "extent": 4096,
                "features": [{
                    "props": {"id": "x"},
                    "type": 2,
                    "parts": [[(-20, 4116), (100, 4000)]],
                }],
            },
        })
        (feature,) = mvt.decode(tile)["polylines"]["features"]
        assert feature["parts"] == [[(-20, 4116), (100, 4000)]]

    def test_multiple_parts(self):
        tile = encode_tile({
            "polylines": {
                "extent": 4096,
                "features": [{
                    "props": {"id": "x"},
                    "type": 2,
                    "parts": [[(0, 0), (10, 10)], [(500, 500), (600, 600)]],
                }],
            },
        })
        (feature,) = mvt.decode(tile)["polylines"]["features"]
        assert len(feature["parts"]) == 2
        assert feature["parts"][1] == [(500, 500), (600, 600)]


class TestTileMath:
    def test_lnglat_tile_round_trip(self):
        # Sofia-ish point at z12
        lng, lat, z = 23.32, 42.70, 12
        fx, fy = mvt.lnglat_to_tile(lng, lat, z)
        tx, ty = int(fx), int(fy)
        px = round((fx - tx) * 4096)
        py = round((fy - ty) * 4096)
        back_lat, back_lng = mvt.tile_point_to_latlng(z, tx, ty, px, py, 4096)
        assert back_lat == pytest.approx(lat, abs=1e-4)
        assert back_lng == pytest.approx(lng, abs=1e-4)

    def test_tile_range_covers_bulgaria_at_z8(self):
        tiles = list(mvt.tile_range(41.2, 22.3, 44.2, 28.7, 8))
        xs = {x for x, _ in tiles}
        ys = {y for _, y in tiles}
        assert xs == set(range(143, 149))
        assert ys == set(range(92, 96))

    def test_tile_range_clamps_to_world(self):
        tiles = list(mvt.tile_range(-89.9, -200.0, 89.9, 200.0, 0))
        assert tiles == [(0, 0)]
