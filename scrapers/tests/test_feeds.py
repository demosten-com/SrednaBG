# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for data-feed versioning.

The load-bearing property here is that **feed 1 does not move**. Every install
ever published fetches `/api/zones`, computes nothing, and resyncs when the hash
changes; a feed-1 byte or hash that shifts because feeds were introduced would
force the entire fleet through a pointless full resync at best, and at worst
serve it something its parser has never seen. Most of these tests exist to pin
that, not to exercise feed 2.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src import feeds, output
from src.client_contract import ContractError, load_feeds, load_manifest
from src.feeds import FeedError
from src.zone_schema import SpeedLimits, Zone, ZoneDatabase, ZoneEndpoint

COMMITTED_ZONES = Path(__file__).parent.parent / "data" / "zones.json"


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


def _db(*zone_ids: str) -> ZoneDatabase:
    ids = zone_ids or ("test-01-east",)
    return ZoneDatabase(
        version="2026-04-12T10:00:00Z", zones=[_sample_zone(i) for i in ids]
    ).with_hash()


def _feed2(status: str = "active"):
    """Serve a throwaway feed 2 alongside feed 1, dropping the last zone.

    A projection that differs in *content* rather than shape is the cheapest
    thing that proves feeds are genuinely independent — separate files, separate
    hashes, separate snapshot histories.
    """
    entries = [
        {"version": 1, "status": "active"},
        {"version": 2, "status": status},
    ]
    projections = dict(feeds.PROJECTIONS)
    projections[2] = lambda db: db.model_copy(update={"zones": db.zones[:-1]})
    return (
        patch.object(feeds, "load_feeds", lambda *a, **k: entries),
        patch.dict(feeds.PROJECTIONS, projections, clear=True),
    )


class TestFilenames:
    def test_feed_one_has_no_suffix(self):
        """The compatibility promise: /api/zones must keep resolving forever."""
        assert feeds.zones_filename(1) == "zones.json"
        assert feeds.version_filename(1) == "version.json"
        assert feeds.snapshot_name(1, "20260412T100000Z") == "zones-20260412T100000Z.json"

    def test_later_feeds_are_suffixed(self):
        assert feeds.zones_filename(2) == "zones.2.json"
        assert feeds.version_filename(12) == "version.12.json"
        assert feeds.snapshot_name(2, "20260412T100000Z") == "zones.2-20260412T100000Z.json"

    def test_feed_one_glob_does_not_match_other_feeds(self, tmp_path):
        """`zones-*.json` would swallow `zones.2-<ts>.json` and prune feed 2's
        history while rotating feed 1's."""
        (tmp_path / feeds.snapshot_name(1, "20260412T100000Z")).touch()
        (tmp_path / feeds.snapshot_name(2, "20260412T100000Z")).touch()

        assert [p.name for p in tmp_path.glob(feeds.snapshot_glob(1))] == [
            "zones-20260412T100000Z.json"
        ]
        assert [p.name for p in tmp_path.glob(feeds.snapshot_glob(2))] == [
            "zones.2-20260412T100000Z.json"
        ]


class TestFeedOneIsUnchanged:
    """Nothing about the shipped feed may move because feeds now exist."""

    def test_committed_zones_json_round_trips_byte_identically(self):
        original = COMMITTED_ZONES.read_text(encoding="utf-8")
        projected = feeds.project(ZoneDatabase.model_validate_json(original), 1)
        assert projected.model_dump_json(indent=2, exclude_none=True) == original

    def test_committed_hash_is_unchanged(self):
        db = ZoneDatabase.model_validate_json(COMMITTED_ZONES.read_text(encoding="utf-8"))
        assert feeds.project(db, 1).hash == db.hash

    def test_manifest_declares_feed_one_active(self):
        assert {"version": 1, "status": "active"} in load_feeds()


class TestProjection:
    def test_unknown_feed_is_an_error_not_a_fallback(self):
        """Serving feed 1's shape under feed 2's name is worse than a failure."""
        with pytest.raises(FeedError, match="no projection"):
            feeds.project(_db(), 99)

    def test_a_content_difference_changes_that_feeds_hash(self):
        p1, p2 = _feed2()
        with p1, p2:
            db = _db("a-01-east", "b-01-east")
            assert feeds.project(db, 2).hash != feeds.project(db, 1).hash

    def test_served_feeds_rejects_a_feed_without_a_projection(self):
        entries = [{"version": 1, "status": "active"}, {"version": 7, "status": "active"}]
        with patch.object(feeds, "load_feeds", lambda *a, **k: entries):
            with pytest.raises(FeedError, match=r"\[7\]"):
                feeds.served_feeds()

    def test_retired_feeds_are_not_served(self):
        entries = [{"version": 1, "status": "active"}, {"version": 2, "status": "retired"}]
        with patch.object(feeds, "load_feeds", lambda *a, **k: entries):
            assert [f["version"] for f in feeds.served_feeds()] == [1]


class TestManifestValidation:
    def _write(self, tmp_path: Path, manifest: dict) -> Path:
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return tmp_path

    def test_missing_feeds_block_is_an_error(self, tmp_path):
        root = self._write(tmp_path, {"clients": []})
        with pytest.raises(ContractError, match="declares no feeds"):
            load_feeds(root)

    def test_non_integer_feed_version_is_an_error(self, tmp_path):
        root = self._write(tmp_path, {"feeds": [{"version": "1", "status": "active"}]})
        with pytest.raises(ContractError, match="positive integer"):
            load_feeds(root)

    def test_unknown_status_is_an_error(self, tmp_path):
        root = self._write(tmp_path, {"feeds": [{"version": 1, "status": "maybe"}]})
        with pytest.raises(ContractError, match="expected one of"):
            load_feeds(root)

    def test_a_client_on_an_undeclared_feed_is_an_error(self, tmp_path):
        """A client pointing at a feed nobody publishes is a client whose
        contract is enforced against nothing — silently unprotected."""
        (tmp_path / "c.json").write_text("{}", encoding="utf-8")
        root = self._write(
            tmp_path,
            {
                "feeds": [{"version": 1, "status": "active"}],
                "clients": [{"version": "9.9.9", "status": "live", "feed": 3,
                             "contract": "c.json"}],
            },
        )
        with pytest.raises(ContractError, match="not declared in `feeds`"):
            load_manifest(root)

    def test_duplicate_feed_versions_are_an_error(self, tmp_path):
        root = self._write(
            tmp_path,
            {"feeds": [{"version": 1, "status": "active"},
                       {"version": 1, "status": "unsupported"}]},
        )
        with pytest.raises(ContractError, match="duplicate feed"):
            load_feeds(root)


class TestWriteTargetDir:
    def test_writes_every_served_feed_side_by_side(self, tmp_path):
        p1, p2 = _feed2()
        with p1, p2:
            output.write_target_dir(_db("a-01-east", "b-01-east"), tmp_path)

        names = {p.name for p in tmp_path.iterdir()}
        assert {"zones.json", "version.json", "zones.2.json", "version.2.json"} <= names

        v1 = json.loads((tmp_path / "version.json").read_text(encoding="utf-8"))
        v2 = json.loads((tmp_path / "version.2.json").read_text(encoding="utf-8"))
        assert (v1["feed"], v1["zone_count"]) == (1, 2)
        assert (v2["feed"], v2["zone_count"]) == (2, 1)
        assert v1["hash"] != v2["hash"]

    def test_unsupported_flag_is_per_feed_and_absent_when_supported(self, tmp_path):
        p1, p2 = _feed2(status="unsupported")
        with p1, p2:
            output.write_target_dir(_db("a-01-east", "b-01-east"), tmp_path)

        v1 = json.loads((tmp_path / "version.json").read_text(encoding="utf-8"))
        v2 = json.loads((tmp_path / "version.2.json").read_text(encoding="utf-8"))
        assert "unsupported" not in v1, "a supported feed carries no flag at all"
        assert v2["unsupported"] == 1

    def test_each_feed_snapshots_its_own_history(self, tmp_path):
        p1, p2 = _feed2()
        with p1, p2:
            output.write_target_dir(_db("a-01-east", "b-01-east"), tmp_path)
            output.write_target_dir(_db("a-01-east", "c-01-east"), tmp_path)

        assert len(list(tmp_path.glob(feeds.snapshot_glob(1)))) == 1
        assert len(list(tmp_path.glob(feeds.snapshot_glob(2)))) == 0, (
            "feed 2 drops the last zone, so its content did not change"
        )

    def test_feed_one_files_are_written_when_it_is_the_only_feed(self, tmp_path):
        output.write_target_dir(_db(), tmp_path)
        assert {p.name for p in tmp_path.iterdir()} == {"zones.json", "version.json"}
