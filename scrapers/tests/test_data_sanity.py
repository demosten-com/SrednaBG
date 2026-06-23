# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Sanity gate on the committed data/zones.json snapshot.

These assertions hold the *shipped* data to the same invariants the
pipeline now enforces — so a bad upstream change (or a pipeline
regression) can't land in the bundle silently. If a test here fails after
a refresh, the scraped data is wrong; fix the pipeline, don't relax the
test.
"""

from pathlib import Path

import pytest

from src.geo import haversine_m
from src.output import MIN_PUBLISH_ZONES
from src.validator import validate
from src.zone_schema import ZoneDatabase

DATA_PATH = Path(__file__).parent.parent / "data" / "zones.json"
BACKEND_DATA_PATH = (
    Path(__file__).parent.parent.parent / "backend" / "data" / "zones.json"
)


@pytest.fixture(scope="module")
def db() -> ZoneDatabase:
    return ZoneDatabase.model_validate_json(DATA_PATH.read_text(encoding="utf-8"))


class TestShippedData:
    def test_enough_zones(self, db):
        assert len(db.zones) >= MIN_PUBLISH_ZONES

    def test_hash_matches_content(self, db):
        assert db.hash == db.compute_hash()

    def test_no_validation_warnings(self, db):
        """The shipped data produces zero validate() warnings — no crossed
        Latin/Cyrillic names, no km markers running against the zone's
        direction, no description/endpoint disagreement, no drifted junction
        seams, no reversed centerlines. Asserting on the full list (rather than
        a substring allow-list) means a reworded or newly-added warning can't
        slip through unnoticed."""
        _, warnings = validate(db.zones)
        assert warnings == []

    def test_centerlines_start_first(self, db):
        for z in db.zones:
            assert len(z.centerline) >= 2, z.id
            first, last = z.centerline[0], z.centerline[-1]
            d_first = haversine_m(first[0], first[1], z.start.lat, z.start.lng)
            d_last = haversine_m(last[0], last[1], z.start.lat, z.start.lng)
            assert d_first <= d_last, f"{z.id} centerline is reversed"

    def test_backend_copy_is_byte_identical(self):
        assert DATA_PATH.read_bytes() == BACKEND_DATA_PATH.read_bytes(), (
            "scrapers/data/zones.json and backend/data/zones.json have "
            "diverged — run scrapers/scripts/refresh-zones.sh"
        )
