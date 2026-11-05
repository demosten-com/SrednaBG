# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Put the device and the harness on the same, freshly served zone catalog.

Not a test of the app — the step that makes the rest of a live-zones run mean
something. Three things have to hold for a drive scenario's expectations to
describe the device it runs on:

1. **The device holds what `/api/zones` serves.** Poison the cached hash and
   backdate the cached version so both of `ZoneDataRecency`'s gates fall
   through, force a sync, require `Updated` (same trick as
   `sync.zones_all_usable`).
2. **The harness holds the same payload.** Download it right after, and check
   the served hash did not move across the device's fetch — the weekly cron
   publishes on Monday mornings, inside the nightly's window. Retried, because
   that race is real rather than theoretical.
3. **Neither moves for the rest of the run.** A run takes hours; the device
   would otherwise pick up a mid-run publish (periodic `ZoneSyncWorker` / BG
   task) or re-seed from a bundle that is newer than the feed (the normal state
   right after `refresh-zones.sh`). So the periodic sync is switched off and the
   cached version is pinned to the far future — `decide()` then skips any
   server payload and `shouldReseedFromBundle()` any bundle.

`release()` undoes (3) at the end of the run. A run killed before it gets there
heals on the next one: this step re-pins the version, and `sync.zones_toggle_off`
turns the periodic sync back on.

Scenarios are *built* from the catalog, so everything after this step in a suite
has to be built after it has run — see `_live_plan` / `_nightly` in
`srednabg_qa.py`.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from .. import device as device_mod
from .. import settings, sync, zone_source
from ..assertions import AssertionFailure, expect_crash_free
from ..runner import RunContext, Scenario, step_lambda

PIN_NAME = "zones.pin_live"

# Non-empty and hash-shaped, but can never equal a real server digest.
_SENTINEL_HASH = "sha256:qa-pin-live-000000000000000000000000000000000000000000"
# Older than any real scrape, so the server can't be classified as stale.
_ANCIENT_VERSION = "2020-01-01T00:00:00Z"
# Newer than any real scrape or bundle, so nothing replaces the pinned catalog.
_FROZEN_VERSION = "2099-01-01T00:00:00Z"
_ATTEMPTS = 3

_frozen = False


def build(snapshot_path: Path | None = None) -> Scenario:
    def pin(ctx: RunContext) -> None:
        global _frozen
        device_mod.current().start_main()
        time.sleep(2.0)
        dest = ctx.report_dir / "zones-live.json"
        expected = zone_source.read_snapshot(snapshot_path) if snapshot_path else None
        snapshot = None
        for _ in range(_ATTEMPTS):
            try:
                served = zone_source.fetch_version()
            except (OSError, ValueError) as e:
                raise AssertionFailure(
                    f"cannot read {zone_source.endpoint('version')}: {e}") from e

            if expected and served.get("hash") != expected.hash:
                raise AssertionFailure(
                    "live feed changed after the shared snapshot was captured; "
                    "refusing to test different catalogs on Android and iOS")

            settings.set_setting("cached_zone_hash", _SENTINEL_HASH)
            settings.set_setting("cached_zone_version", _ANCIENT_VERSION)
            ctx.obs.clear()
            sync.force_sync_zones()
            try:
                result = sync.wait_for_sync(
                    ctx.obs, "SYNC_ZONES", timeout_s=sync.REFETCH_TIMEOUT_S)
            except TimeoutError as e:
                raise AssertionFailure(f"device never finished the zone sync: {e}") from e
            if result.outcome != "Updated":
                raise AssertionFailure(
                    "the device must fetch the served catalog here, got "
                    f"{result.outcome} (detail={result.detail})")

            try:
                candidate = zone_source.download_snapshot(dest)
            except (OSError, ValueError) as e:
                raise AssertionFailure(
                    f"cannot download {zone_source.endpoint('zones')}: {e}") from e
            if (candidate.hash == served.get("hash")
                    and (expected is None or candidate.hash == expected.hash)):
                snapshot = candidate
                break
            # The feed was republished between the version check and our
            # download, so the device may hold either payload. Go again.
        if snapshot is None:
            raise AssertionFailure(
                f"the zone feed changed under {_ATTEMPTS} consecutive attempts to "
                "pin it — device and harness can't be put on the same catalog")

        if expected:
            shutil.copyfile(expected.path, dest)
            snapshot = zone_source.read_snapshot(dest)
        _frozen = True
        settings.set_setting("zone_sync_enabled", False, obs=ctx.obs)
        settings.set_setting("cached_zone_version", _FROZEN_VERSION, obs=ctx.obs)
        zone_source.use_snapshot(snapshot)

    def teardown(ctx: RunContext) -> None:
        expect_crash_free(ctx.obs)

    return Scenario(
        name=PIN_NAME,
        steps=[step_lambda("pin_device_and_harness_to_served_zones", pin)],
        teardown=teardown,
        # Up to _ATTEMPTS full re-fetches plus as many catalog downloads.
        timeout_s=300,
    )


def release() -> None:
    """Undo the freeze so the device syncs normally again. Best-effort: runs on
    the way out of a suite, where the app may already be gone."""
    global _frozen
    if not _frozen:
        return
    _frozen = False
    try:
        device_mod.current().start_main()
        time.sleep(2.0)
        settings.set_setting("zone_sync_enabled", True)
        # Empty = "not comparable": the next sync sees the matching hash,
        # reports UpToDate and backfills the real version.
        settings.set_setting("cached_zone_version", "")
    except Exception as e:  # never mask the suite's own outcome
        print(f"warning: could not unfreeze zone sync on the device: {e}")
