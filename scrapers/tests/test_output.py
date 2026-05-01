# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the output pipeline."""

from src.zone_schema import SpeedLimits, Zone, ZoneDatabase, ZoneEndpoint


def _sample_zone(zone_id: str = "test-01-east") -> Zone:
    return Zone(
        id=zone_id,
        road="АМ Тракия",
        direction="east",
        description="Вакарел – Ихтиман",
        start=ZoneEndpoint(lat=42.55, lng=23.70, km_marker="24+288", settlement="Вакарел"),
        end=ZoneEndpoint(lat=42.43, lng=23.86, km_marker="43+448", settlement="Ихтиман"),
        distance_m=19160,
        speed_limits=SpeedLimits(car=140, truck=90, bus=100),
        centerline=[[42.55, 23.70], [42.43, 23.86]],
        source="test",
        last_verified="2026-04-12",
    )


class TestZoneDatabase:
    def test_compute_hash_deterministic(self):
        zones = [_sample_zone()]
        db1 = ZoneDatabase(version="2026-04-12T10:00:00Z", zones=zones)
        db2 = ZoneDatabase(version="2026-04-12T10:00:00Z", zones=zones)
        assert db1.compute_hash() == db2.compute_hash()

    def test_hash_changes_with_data(self):
        zone1 = _sample_zone("test-01-east")
        zone2 = _sample_zone("test-02-east")
        db1 = ZoneDatabase(version="v1", zones=[zone1])
        db2 = ZoneDatabase(version="v1", zones=[zone1, zone2])
        assert db1.compute_hash() != db2.compute_hash()

    def test_hash_format(self):
        db = ZoneDatabase(version="v1", zones=[_sample_zone()])
        h = db.compute_hash()
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64  # "sha256:" + 64 hex chars

    def test_with_hash(self):
        db = ZoneDatabase(version="v1", zones=[_sample_zone()])
        db_hashed = db.with_hash()
        assert db_hashed.hash.startswith("sha256:")
        assert db.hash == ""  # Original unchanged

    def test_json_roundtrip(self):
        db = ZoneDatabase(version="v1", zones=[_sample_zone()]).with_hash()
        json_str = db.model_dump_json(indent=2)
        db2 = ZoneDatabase.model_validate_json(json_str)
        assert db2.version == db.version
        assert db2.hash == db.hash
        assert len(db2.zones) == 1
        assert db2.zones[0].id == "test-01-east"

    def test_json_output_structure(self):
        db = ZoneDatabase(version="v1", zones=[_sample_zone()]).with_hash()
        data = db.model_dump()
        assert "version" in data
        assert "hash" in data
        assert "zones" in data
        zone = data["zones"][0]
        assert "id" in zone
        assert "road" in zone
        assert "direction" in zone
        assert "start" in zone
        assert "end" in zone
        assert "distance_m" in zone
        assert "speed_limits" in zone
        assert "centerline" in zone
        assert "source" in zone

    def test_empty_database(self):
        db = ZoneDatabase(version="v1", zones=[]).with_hash()
        assert db.hash.startswith("sha256:")
        assert len(db.zones) == 0
