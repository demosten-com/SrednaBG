# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the output pipeline."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src import output, validator
from src.bgtoll_scraper import scrape as bgtoll_scrape
from src.validator import merge_all
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

    def test_hash_ignores_last_verified(self):
        """last_verified should not affect the hash — it's a run-time stamp,
        not data. Two zones identical except for last_verified must hash equal.
        """
        z1 = _sample_zone()
        z2 = z1.model_copy(update={"last_verified": "2099-12-31"})
        db1 = ZoneDatabase(version="v1", zones=[z1])
        db2 = ZoneDatabase(version="v1", zones=[z2])
        assert db1.compute_hash() == db2.compute_hash()

    def test_hash_still_changes_on_real_field(self):
        """Sanity check: changing any non-excluded field still changes the hash."""
        z1 = _sample_zone()
        z2 = z1.model_copy(update={"distance_m": z1.distance_m + 1})
        assert (
            ZoneDatabase(version="v1", zones=[z1]).compute_hash()
            != ZoneDatabase(version="v1", zones=[z2]).compute_hash()
        )


class TestPipelineHashStability:
    """End-to-end: the hash must not change between runs that differ only
    in the wall clock. Regression test for the bug where every zone got a
    fresh last_verified stamp baked into the hash.
    """

    def _run_pipeline_on_date(self, bgtoll_html, tolltracker_zones, date_str):
        """Run the merge pipeline with datetime.now patched to return date_str."""
        fake_now = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now if tz is None else fake_now.astimezone(tz)

        # Patch the symbol imported into validator (merge_match stamps
        # last_verified there). The per-source scrapers also stamp, but
        # merge_match overwrites those.
        with patch.object(validator, "datetime", _FakeDatetime):
            bg_zones = bgtoll_scrape(html=bgtoll_html)
            tt_zones = tolltracker_zones
            merged = merge_all(bg_zones, tt_zones, [])
            db = ZoneDatabase(version="v1", zones=merged).with_hash()
        return db

    def test_hash_stable_across_dates(self, bgtoll_html, tolltracker_zones):
        db_day1 = self._run_pipeline_on_date(
            bgtoll_html, tolltracker_zones, "2026-05-11"
        )
        db_day2 = self._run_pipeline_on_date(
            bgtoll_html, tolltracker_zones, "2026-08-23"
        )

        # Sanity: confirm the patch actually moved last_verified.
        assert db_day1.zones[0].last_verified == "2026-05-11"
        assert db_day2.zones[0].last_verified == "2026-08-23"

        # The whole point of this fix: hash must be identical.
        assert db_day1.hash == db_day2.hash

    def test_write_target_dir_no_snapshot_when_only_date_changed(
        self, bgtoll_html, tolltracker_zones, tmp_path
    ):
        """write_target_dir snapshots zones.json only on a genuine content
        change. The trigger is gated on ``db.hash`` (which excludes
        ``last_verified``), so a run that only re-stamps last_verified — the
        common cron case — must NOT rotate a snapshot.
        """
        db1 = self._run_pipeline_on_date(
            bgtoll_html, tolltracker_zones, "2026-05-11"
        )
        output.write_target_dir(db1, tmp_path)
        version1 = json.loads((tmp_path / "version.json").read_text())

        db2 = self._run_pipeline_on_date(
            bgtoll_html, tolltracker_zones, "2026-08-23"
        )
        output.write_target_dir(db2, tmp_path)
        version2 = json.loads((tmp_path / "version.json").read_text())

        # The hash served to clients is stable across dates.
        assert version1["hash"] == version2["hash"]
        # ...and no spurious snapshot was rotated despite last_verified moving.
        assert list(tmp_path.glob("zones-*.json")) == []

    def test_write_target_dir_snapshots_on_content_change(
        self, bgtoll_html, tolltracker_zones, tmp_path
    ):
        """A genuine data change (different hash) DOES rotate a snapshot."""
        db1 = self._run_pipeline_on_date(
            bgtoll_html, tolltracker_zones, "2026-05-11"
        )
        output.write_target_dir(db1, tmp_path)

        z0 = db1.zones[0]
        changed = z0.model_copy(
            update={
                "speed_limits": z0.speed_limits.model_copy(
                    update={"car": z0.speed_limits.car + 1}
                )
            }
        )
        db2 = ZoneDatabase(version="v2", zones=[changed, *db1.zones[1:]]).with_hash()
        assert db2.hash != db1.hash

        output.write_target_dir(db2, tmp_path)
        assert len(list(tmp_path.glob("zones-*.json"))) == 1

    def test_write_target_dir_prunes_old_snapshots(self, tmp_path):
        """The snapshot ring keeps only the newest SNAPSHOT_RETENTION files."""
        retain = output.SNAPSHOT_RETENTION
        seeded = retain + 4
        # Seed more snapshots than the ring holds, with sortable timestamp names.
        for i in range(seeded):
            (tmp_path / f"zones-2026{i:04d}T000000Z.json").write_text("{}")

        # A first-time write here (no prior zones.json) makes no new snapshot,
        # but the prune still runs over the seeded files.
        db = ZoneDatabase(version="v1", zones=[_sample_zone()]).with_hash()
        output.write_target_dir(db, tmp_path)

        remaining = sorted(p.name for p in tmp_path.glob("zones-*.json"))
        assert len(remaining) == retain
        # The newest `retain` survive; the 4 oldest are pruned.
        expected = sorted(
            f"zones-2026{i:04d}T000000Z.json" for i in range(seeded)
        )[-retain:]
        assert remaining == expected


class TestSourceFailure:
    """Any failed or empty source aborts the run — publishing without a
    source would silently degrade the shipped data."""

    def _patch_sources(self, monkeypatch, bgtoll, tolltracker, kml):
        monkeypatch.setattr(output.bgtoll_scraper, "scrape", bgtoll)
        monkeypatch.setattr(output.tolltracker_fetcher, "scrape", tolltracker)
        monkeypatch.setattr(output.kml_scraper, "scrape", kml)

    def test_raising_source_fails_the_pipeline(self, monkeypatch):
        def broken():
            raise ValueError("tile schema changed")

        self._patch_sources(
            monkeypatch,
            bgtoll=lambda: [_sample_zone()],
            tolltracker=broken,
            kml=lambda: [_sample_zone()],
        )
        with pytest.raises(output.SourceFailure) as exc:
            output.run_pipeline()
        assert exc.value.errors == [
            "TollTracker: ValueError: tile schema changed"
        ]

    def test_empty_source_fails_the_pipeline(self, monkeypatch):
        self._patch_sources(
            monkeypatch,
            bgtoll=lambda: [_sample_zone()],
            tolltracker=lambda: [_sample_zone()],
            kml=lambda: [],
        )
        with pytest.raises(output.SourceFailure) as exc:
            output.run_pipeline()
        assert exc.value.errors == ["KML: returned no zones"]

    def test_all_failures_reported_together(self, monkeypatch):
        def broken():
            raise ConnectionError("timed out")

        self._patch_sources(
            monkeypatch, bgtoll=broken, tolltracker=broken, kml=lambda: []
        )
        with pytest.raises(output.SourceFailure) as exc:
            output.run_pipeline()
        assert len(exc.value.errors) == 3
        assert exc.value.errors[-1] == "KML: returned no zones"

    def test_main_exits_nonzero_and_leaves_files(
        self, tmp_path, monkeypatch, caplog
    ):
        healthy = ZoneDatabase(
            version="v1", zones=[_sample_zone()]
        ).with_hash()
        output.write_target_dir(healthy, tmp_path)
        zones_before = (tmp_path / "zones.json").read_text()

        def broken_pipeline():
            raise output.SourceFailure(["TollTracker: ValueError: boom"])

        monkeypatch.setattr(output, "run_pipeline", broken_pipeline)
        monkeypatch.setattr(
            "sys.argv", ["src.output", "--target-dir", str(tmp_path)]
        )
        with pytest.raises(SystemExit) as exc:
            output.main()
        assert exc.value.code == 1
        assert (tmp_path / "zones.json").read_text() == zones_before
        # The concise per-source error is re-logged for the Telegram log tail.
        assert any(
            "TollTracker: ValueError: boom" in r.getMessage()
            for r in caplog.records
        )


class TestPublishGuard:
    """The pipeline must refuse to overwrite good data with a collapsed
    scrape (e.g. every upstream source broke and returned [])."""

    def _db(self, count: int, roads: list[str] | None = None) -> ZoneDatabase:
        roads = roads or ["АМ Тракия", "АМ Хемус", "АМ Струма", "АМ Марица"]
        zones = [
            _sample_zone(f"test-{i:02d}-east").model_copy(
                update={"road": roads[i % len(roads)]}
            )
            for i in range(count)
        ]
        return ZoneDatabase(version="v1", zones=zones).with_hash()

    def test_healthy_db_passes(self):
        assert output.publish_guard_errors(self._db(72)) == []

    def test_too_few_zones_fails(self):
        errors = output.publish_guard_errors(self._db(3))
        assert any("minimum" in e for e in errors)

    def test_empty_db_fails(self):
        errors = output.publish_guard_errors(
            ZoneDatabase(version="v1", zones=[]).with_hash()
        )
        assert errors

    def test_missing_motorway_fails(self):
        db = self._db(72, roads=["АМ Тракия", "АМ Хемус", "АМ Струма"])
        errors = output.publish_guard_errors(db)
        assert any("АМ Марица" in e for e in errors)

    def test_count_drop_vs_previous_fails(self):
        errors = output.publish_guard_errors(self._db(50), prev_count=100)
        assert any("dropped" in e for e in errors)

    def test_small_count_change_vs_previous_passes(self):
        assert output.publish_guard_errors(self._db(70), prev_count=72) == []

    def test_main_exits_nonzero_and_leaves_files(self, tmp_path, monkeypatch):
        # Seed a healthy target dir, then make the pipeline collapse.
        healthy = self._db(72)
        output.write_target_dir(healthy, tmp_path)
        zones_before = (tmp_path / "zones.json").read_text()

        monkeypatch.setattr(output, "run_pipeline", lambda: self._db(2))
        monkeypatch.setattr(
            "sys.argv", ["src.output", "--target-dir", str(tmp_path)]
        )
        with pytest.raises(SystemExit) as exc:
            output.main()
        assert exc.value.code == 1
        assert (tmp_path / "zones.json").read_text() == zones_before
