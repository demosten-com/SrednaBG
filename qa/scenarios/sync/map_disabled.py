# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Map-sync feature-gate regression check.

The production backend at srednabg.com doesn't yet serve `/api/map/bundle.zip`
or populate `map_hash` in `/api/version` — the Namecheap scraper cron only
emits zones. Until the backend bundle pipeline is live, both platforms gate
the client-side map-sync paths behind `FeatureFlags.IS_MAP_SYNC_ENABLED`
(Android) / `FeatureFlags.isMapSyncEnabled` (iOS).

This scenario triggers a SYNC_MAP via the debug surface and asserts both
platforms emit `DebugSync: ... -> Skipped (feature disabled)`. If anyone
accidentally removes one of the gates, the outcome flips to Updated /
UpToDate / Failed and this scenario fails loud.

It also verifies the bundled on-disk map is still healthy — the gate must
not break the offline bundle that ships in-app.
"""

from __future__ import annotations

from ... import sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        sync.force_sync_map()
        result = sync.wait_for_sync(ctx.obs, "SYNC_MAP", timeout_s=30)
        if result.outcome != "Skipped":
            raise AssertionFailure(
                "map sync feature gate appears removed: expected outcome=Skipped, "
                f"got outcome={result.outcome!r} detail={result.detail!r}. "
                "If this is intentional (backend now serves /api/map/bundle.zip), "
                "flip FeatureFlags on both platforms and restore the happy-path scenario."
            )
        # The bundled offline map ships in-app and must remain healthy even
        # with sync disabled — sanity-check on-disk integrity.
        integrity = sync.check_map_integrity()
        sync.assert_map_integrity_ok(integrity)

    def teardown(ctx: RunContext) -> None:
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.map_disabled",
        steps=[step_lambda("force_map_sync_expect_skipped", go)],
        teardown=teardown,
        timeout_s=60,
    )
