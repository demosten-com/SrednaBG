# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the TollTracker.eu vector-tile fetcher."""


import pytest

from src import mvt, tolltracker_fetcher
from src.geo import haversine_m, polyline_length_m
from src.tolltracker_fetcher import (
    discover_tile_source,
    parse_feature,
    scrape,
    stitch_pieces,
)
from tests.mvt_encoding import encode_tile

# A west->east segment on АМ Тракия (Вакарел -> Ихтиман direction).
LINE = [
    (42.550, 23.700),
    (42.540, 23.740),
    (42.520, 23.790),
    (42.500, 23.840),
]
LINE_LENGTH_M = round(polyline_length_m([[lat, lng] for lat, lng in LINE]))

PROPS = {
    "id": "S-PL-TEST01",
    "title": "Вакарел - Ихтиман, Тракия",
    "type": "section_control",
    "country": "BG",
    "length": LINE_LENGTH_M,
    "speed_limit": 140,
    "start_road_oneway": True,
    "start_road_class": "motorway",
    "idx": 1,
}


def _tile_with_line(z: int, tx: int, ty: int, line=LINE, props=PROPS) -> bytes:
    """Encode ``line`` into tile (tx, ty) — full line, no clipping (points
    outside the tile land in what the decoder treats as buffer overshoot)."""
    extent = 4096
    parts = []
    part = []
    for lat, lng in line:
        fx, fy = mvt.lnglat_to_tile(lng, lat, z)
        part.append((round((fx - tx) * extent), round((fy - ty) * extent)))
    parts.append(part)
    return encode_tile({
        "polylines": {
            "extent": extent,
            "features": [{"props": props, "type": 2, "parts": parts}],
        },
    })


@pytest.fixture
def fake_tiles(monkeypatch):
    """Serve the LINE feature from every tile its bbox touches."""
    requested: list[tuple[int, int, int]] = []

    def fetch_tile(tileset, token, z, x, y):
        requested.append((z, x, y))
        lats = [p[0] for p in LINE]
        lngs = [p[1] for p in LINE]
        covering = set(mvt.tile_range(min(lats), min(lngs), max(lats), max(lngs), z))
        if (x, y) not in covering:
            return None
        return _tile_with_line(z, x, y)

    monkeypatch.setattr(tolltracker_fetcher, "_fetch_tile", fetch_tile)
    monkeypatch.setattr(
        tolltracker_fetcher,
        "discover_tile_source",
        lambda: ("test.tileset", "pk.test"),
    )
    return requested


class TestDiscoverTileSource:
    def test_finds_token_in_second_level_chunk(self, monkeypatch):
        pages = {
            tolltracker_fetcher.TOLLTRACKER_URL: (
                '<script src="/_next/static/chunks/aaaaaaaaaaaaaaaa.js"></script>'
            ),
            f"{tolltracker_fetcher.TOLLTRACKER_BASE}/_next/static/chunks/"
            "aaaaaaaaaaaaaaaa.js": 'import("bbbbbbbbbbbbbbbb.js")',
            f"{tolltracker_fetcher.TOLLTRACKER_BASE}/_next/static/chunks/"
            "bbbbbbbbbbbbbbbb.js": (
                'accessToken:"pk.eyJhbGciOiJIUzI1NiJ9.payload.sig",'
                'tileset:"someuser.tt-map-data"'
            ),
        }
        monkeypatch.setattr(
            tolltracker_fetcher, "fetch_text", lambda url, **kw: pages[url]
        )
        tileset, token = discover_tile_source()
        assert tileset == "someuser.tt-map-data"
        assert token == "pk.eyJhbGciOiJIUzI1NiJ9.payload.sig"

    def test_falls_back_when_site_unreachable(self, monkeypatch):
        import requests

        def boom(url, **kw):
            raise requests.ConnectionError("offline")

        monkeypatch.setattr(tolltracker_fetcher, "fetch_text", boom)
        tileset, token = discover_tile_source()
        assert tileset == tolltracker_fetcher.FALLBACK_TILESET
        assert token == tolltracker_fetcher.FALLBACK_TOKEN


class TestStitchPieces:
    def test_single_piece_passes_through(self):
        line, complete = stitch_pieces([list(LINE)])
        assert complete
        assert line == [[lat, lng] for lat, lng in LINE]

    def test_overlapping_pieces_join_without_duplicates(self):
        # Two clipped pieces sharing the middle stretch (buffer overlap).
        a = list(LINE[:3])
        b = list(LINE[1:])
        line, complete = stitch_pieces([a, b])
        assert complete
        assert line == [[lat, lng] for lat, lng in LINE]

    def test_piece_order_does_not_matter(self):
        a = list(LINE[:2])
        b = list(LINE[1:3])
        c = list(LINE[2:])
        for pieces in ([c, a, b], [b, c, a]):
            line, complete = stitch_pieces([p[:] for p in pieces])
            assert complete
            assert line == [[lat, lng] for lat, lng in LINE]

    def test_exact_duplicate_pieces_are_dropped(self):
        line, complete = stitch_pieces([list(LINE), list(LINE)])
        assert complete
        assert line == [[lat, lng] for lat, lng in LINE]

    def test_disconnected_piece_reports_incomplete(self):
        # A hole in tile coverage: the far piece can't attach across ~4 km.
        a = list(LINE[:2])
        far = [(42.400, 24.100), (42.390, 24.150)]
        _line, complete = stitch_pieces([a, far])
        assert not complete

    def test_subsumed_leftover_is_complete(self):
        # A buffer fragment lying entirely on the chain is redundant, not a
        # hole — it neither extends the chain nor marks it incomplete.
        line, complete = stitch_pieces([list(LINE), [LINE[1], LINE[2]]])
        assert complete
        assert line == [[lat, lng] for lat, lng in LINE]


class TestParseFeature:
    def _centerline(self):
        return [[lat, lng] for lat, lng in LINE]

    def test_zone_fields(self):
        zone = parse_feature(PROPS, self._centerline())
        assert zone.id == "S-PL-TEST01"
        assert zone.road == "АМ Тракия"
        assert zone.road_latin == "Trakiya"
        assert zone.direction == "east"  # lng increasing on a lng-axis road
        assert zone.description == "Вакарел – Ихтиман"
        assert zone.start.settlement == "Вакарел"
        assert zone.start.settlement_latin == "Vakarel"
        assert zone.end.settlement == "Ихтиман"
        assert zone.end.settlement_latin == "Ihtiman"
        assert zone.distance_m == LINE_LENGTH_M
        assert zone.speed_limits.car == 140
        assert zone.speed_limits.truck is None
        assert zone.speed_limits.bus is None
        assert zone.road_type == "motorway"
        assert zone.source == "tolltracker"

    def test_endpoints_come_from_geometry(self):
        zone = parse_feature(PROPS, self._centerline())
        assert (zone.start.lat, zone.start.lng) == LINE[0]
        assert (zone.end.lat, zone.end.lng) == LINE[-1]

    def test_national_road(self):
        props = dict(
            PROPS,
            title="Жеглица - Срацимирово, I-1",
            speed_limit=90,
            start_road_class="primary",
            start_road_oneway=False,
        )
        # North->south line (I-1 is a lat-axis road)
        centerline = [[43.878, 22.789], [43.820, 22.757]]
        zone = parse_feature(props, centerline)
        assert zone.road == "Път I-1"
        assert zone.road_latin == "I-1"
        assert zone.direction == "south"
        assert zone.road_type == "road"
        assert zone.speed_limits.car == 90

    def test_title_without_road_suffix_raises(self):
        with pytest.raises(ValueError, match="road suffix"):
            parse_feature(dict(PROPS, title="Вакарел - Ихтиман"), self._centerline())

    def test_title_without_endpoint_pair_raises(self):
        with pytest.raises(ValueError, match="start - end"):
            parse_feature(dict(PROPS, title="Вакарел, Тракия"), self._centerline())


class TestScrape:
    def test_end_to_end(self, fake_tiles):
        zones = scrape()
        assert len(zones) == 1
        zone = zones[0]
        assert zone.id == "S-PL-TEST01"
        assert zone.road == "АМ Тракия"
        assert zone.direction == "east"
        assert zone.source == "tolltracker"
        # Geometry survives the tile round-trip to within quantization
        assert haversine_m(zone.start.lat, zone.start.lng, *LINE[0]) < 10
        assert haversine_m(zone.end.lat, zone.end.lng, *LINE[-1]) < 10
        assert abs(polyline_length_m(zone.centerline) - LINE_LENGTH_M) < 100

    def test_detail_tiles_fetched_at_first_ladder_zoom(self, fake_tiles):
        scrape()
        zooms = {z for z, _, _ in fake_tiles}
        assert tolltracker_fetcher.DISCOVERY_ZOOM in zooms
        assert tolltracker_fetcher.DETAIL_ZOOMS[0] in zooms
        # Complete at the first detail zoom — the ladder never descends
        assert tolltracker_fetcher.DETAIL_ZOOMS[1] not in zooms

    def test_no_bg_section_features_raises(self, monkeypatch):
        # Foreign features are filtered out; a sweep that finds nothing for
        # BG means the tile schema changed — that must be a loud failure,
        # not an empty result.
        def fetch_tile(tileset, token, z, x, y):
            if (x, y) not in set(mvt.tile_range(41.2, 22.3, 44.2, 28.7, z)):
                return None
            return _tile_with_line(
                z, x, y,
                props=dict(PROPS, country="RO"),
            )

        monkeypatch.setattr(tolltracker_fetcher, "_fetch_tile", fetch_tile)
        monkeypatch.setattr(
            tolltracker_fetcher,
            "discover_tile_source",
            lambda: ("test.tileset", "pk.test"),
        )
        with pytest.raises(ValueError, match="section_control"):
            scrape()

    def test_raises_on_total_failure(self, monkeypatch):
        # Failures propagate — the pipeline fails the run rather than
        # publishing degraded data.
        def boom():
            raise RuntimeError("no network")

        monkeypatch.setattr(tolltracker_fetcher, "discover_tile_source", boom)
        with pytest.raises(RuntimeError, match="no network"):
            scrape()
