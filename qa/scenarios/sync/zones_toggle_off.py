# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Zone-sync opt-out regression check (Android + iOS).

The "Automatic zone updates" setting gates only the *periodic background* zone
sync. The manual "Sync zones now" action must keep working when the toggle is
off — it routes through the zone repository's syncFromServer() directly
(Android: DebugSyncReceiver ACTION_SYNC_ZONES; iOS: DebugActionRouter
`/sync?action=zones`), bypassing the toggle. If anyone wires the toggle into
the manual path too, the manual sync short-circuits and this scenario fails
loud.

The background-task enqueue/cancel itself isn't observable from the harness;
it's covered by unit tests + a manual check (Android: `dumpsys jobscheduler`;
iOS: BGTaskScheduler has no public introspection).
"""

from __future__ import annotations

from ... import settings, sync
from ...assertions import AssertionFailure, expect_crash_free
from ...runner import RunContext, Scenario, step_lambda


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        ctx.obs.clear()
        # Opt out of the automatic background sync.
        settings.set_setting("zone_sync_enabled", False, obs=ctx.obs)
        try:
            # Manual "Sync zones now" must still work with auto-sync disabled.
            sync.force_sync_zones()
            result = sync.wait_for_sync(ctx.obs, "SYNC_ZONES", timeout_s=20)
            if result.outcome not in ("Updated", "UpToDate"):
                raise AssertionFailure(
                    "manual sync must work even with automatic zone updates off: "
                    f"expected Updated/UpToDate, got {result.outcome} (detail={result.detail})"
                )
        finally:
            # Restore the shipped default so later scenarios see normal behavior.
            settings.set_setting("zone_sync_enabled", True, obs=ctx.obs)

    def teardown(ctx: RunContext) -> None:
        settings.set_setting("zone_sync_enabled", True)  # belt + suspenders
        expect_crash_free(ctx.obs)

    return Scenario(
        name="sync.zones_toggle_off",
        steps=[step_lambda("manual_sync_with_auto_off", go)],
        teardown=teardown,
        timeout_s=60,
    )
