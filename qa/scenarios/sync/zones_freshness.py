# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Manual zone-sync freshness round-trip (Android + iOS).

Guards the "Sync zones now" path that returned an instant "Up to date" on iOS:
`SyncClient` used `URLSession.shared`'s default `.useProtocolCachePolicy`, and
the backend serves `/api/version` with `Cache-Control: max-age=300`, so a tap
within 5 min of the launch sync was answered from `URLCache` — no network
round-trip, and a genuine server-side zone change stayed invisible. The fix
(`SyncClient.freshRequest`, `.reloadIgnoringLocalCacheData`) is pinned exactly
by the unit test `SyncClientTests.freshnessRequestsBypassHTTPCache`, because the
cache-served-vs-network-served distinction is not observable through the
harness's outcome log against the immutable production backend.

What this on-device scenario *does* assert — the round-trip the user reported
as broken ("a request is really fired and data gets back"):

1. Poison `cached_zone_hash` with a sentinel that can't match the server, then
   sync → expect `Updated`. A mismatch forces `fetchVersion` + `fetchZones`,
   proving the request fired, data came back, the store was replaced, and the
   real hash was persisted.
2. Sync again → expect `UpToDate`. The just-persisted real hash now matches a
   fresh `/api/version` check — the exact gate that was short-circuiting too
   quickly, exercised end-to-end on freshly-fetched data.

A regression that breaks the manual fetch (gate inverted, fetchZones skipped,
hash not persisted) flips one of these outcomes and fails loud.
"""

from __future__ import annotations

from ... import settings, sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda

# Non-empty and structurally hash-shaped, but can never equal a real server
# digest — guarantees the version gate falls through to a full re-fetch.
_SENTINEL_HASH = "sha256:qa-force-refetch-0000000000000000000000000000000000"

# Older than any real scrape. A poisoned *hash* alone no longer guarantees a
# re-fetch: `ZoneDataRecency` also skips a server whose `version` is older than
# the cached one, which is exactly the state right after a local
# `refresh-zones.sh` (the app bundles a scrape the weekly cron hasn't published
# yet). Backdating the cached version keeps this scenario testing what it means
# to test — the manual fetch round-trip — instead of the recency gate, which
# `zones_remote_older` owns.
_ANCIENT_VERSION = "2020-01-01T00:00:00Z"


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        # 1) Poison the cached hash + backdate the version, then sync → must
        #    re-fetch (Updated).
        settings.set_setting("cached_zone_hash", _SENTINEL_HASH)
        settings.set_setting("cached_zone_version", _ANCIENT_VERSION)
        ctx.obs.clear()
        sync.force_sync_zones()
        first = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=20)
        if first.outcome != "Updated":
            raise AssertionFailure(
                "poisoned cached hash must force a full re-fetch: "
                f"expected Updated, got {first.outcome} (detail={first.detail})"
            )

        # 2) Immediately sync again → the just-persisted real hash matches a
        #    fresh /api/version check (UpToDate). This is the path that was
        #    returning an instant, cache-served "Up to date".
        ctx.obs.clear()
        sync.force_sync_zones()
        second = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=20)
        if second.outcome != "UpToDate":
            raise AssertionFailure(
                "second sync should see the freshly-persisted hash: "
                f"expected UpToDate, got {second.outcome} (detail={second.detail})"
            )

    def teardown(ctx: RunContext) -> None:
        # The two syncs leave cached_zone_hash = the real server hash, so no
        # cleanup is needed beyond the crash check.
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.zones_freshness",
        steps=[step_lambda("manual_sync_force_refetch", go)],
        teardown=teardown,
        timeout_s=90,
    )
