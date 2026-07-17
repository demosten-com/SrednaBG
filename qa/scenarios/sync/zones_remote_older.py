# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Recency gate: an older server must never downgrade newer local zones.

Guards the ISSUE-011 fix (`ZoneDataRecency` on both platforms). A client can
carry zone data *newer* than the server — a locally built app bundles a fresh
scrape while the production cron only publishes on Mondays. Before the fix,
sync treated any hash mismatch as "server is newer" and silently replaced the
fresher local data with the older server data.

1. Poison `cached_zone_hash` with a sentinel (guaranteed mismatch) AND set
   `cached_zone_version` to a far-future timestamp, then sync → expect
   `UpToDate`: the hash differs but the server's version is older than the
   (claimed) local one, so the recency gate must skip the fetch. A regression
   to hash-only compare re-fetches and reports `Updated` — failing loud.
2. Reset `cached_zone_version` to "" (not comparable → legacy fallback) with
   the sentinel hash still in place, then sync → expect `Updated`: the full
   re-fetch runs and persists the real server hash + version, restoring the
   device state for any scenario that follows.
"""

from __future__ import annotations

from ... import settings, sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda

# Non-empty and structurally hash-shaped, but can never equal a real server
# digest — guarantees a hash mismatch so only the recency gate can skip.
_SENTINEL_HASH = "sha256:qa-remote-older-000000000000000000000000000000000000"

# Far enough in the future that any real server scrape timestamp is older.
_FUTURE_VERSION = "2099-01-01T00:00:00Z"


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        # 1) Hash mismatch + far-future local version → recency gate skips.
        settings.set_setting("cached_zone_hash", _SENTINEL_HASH)
        settings.set_setting("cached_zone_version", _FUTURE_VERSION)
        ctx.obs.clear()
        sync.force_sync_zones()
        first = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=20)
        if first.outcome != "UpToDate":
            raise AssertionFailure(
                "older server data must not replace newer local data: "
                f"expected UpToDate, got {first.outcome} (detail={first.detail})"
            )

        # 2) Clear the version (legacy fallback) → full re-fetch restores the
        #    real server hash + version so later scenarios aren't poisoned.
        settings.set_setting("cached_zone_version", "")
        ctx.obs.clear()
        sync.force_sync_zones()
        second = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=20)
        if second.outcome != "Updated":
            raise AssertionFailure(
                "legacy (empty) cached version must fall back to a re-fetch: "
                f"expected Updated, got {second.outcome} (detail={second.detail})"
            )

    def teardown(ctx: RunContext) -> None:
        # Belt and braces: if a step failed mid-way the device could be left
        # with the future version pinned — reset and re-sync (unasserted) so
        # the rest of the suite runs against real server state.
        settings.set_setting("cached_zone_version", "")
        sync.force_sync_zones()
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.zones_remote_older",
        steps=[step_lambda("remote_older_is_skipped", go)],
        teardown=teardown,
        timeout_s=90,
    )
