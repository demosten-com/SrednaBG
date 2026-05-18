# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Auto-stop after inactivity: tracking shuts itself down after the
threshold of no zone-state activity elapses.

Drives the regression case for "if you start tracking and forget about
it, GPS keeps draining the battery indefinitely." The user-facing
setting is in hours (3/6/never); the harness uses the
`debug_auto_stop_seconds` override (DEBUG-only) so the assertion fires
in ~12 s instead of 3 h.

Asserts:
  1. The `AutoStopped` log line appears within the override window.
  2. The reported `threshold_s` matches what we set.
"""

from __future__ import annotations

import time

from ... import device as device_mod
from ... import settings as settings_mod
from ...assertions import expect, expect_crash_free
from ...events import AutoStopped
from ...runner import RunContext, Scenario, step_lambda


DEBUG_SECONDS = 10


def build() -> Scenario:
    def setup(ctx: RunContext) -> None:
        device_mod.current().start_main()
        time.sleep(2.0)
        combo = next(c for c in settings_mod.ALL_COMBOS if c.id == "S1")
        combo.apply(ctx.obs)
        # Set the debug override BEFORE start_tracking — the auto-stop
        # coroutine reads it on its periodic tick, but starting with the
        # override already set keeps the test deterministic.
        settings_mod.set_setting("debug_auto_stop_seconds", DEBUG_SECONDS, obs=ctx.obs)
        settings_mod.start_tracking()
        time.sleep(2.5)
        ctx.obs.clear()

    def idle(ctx: RunContext) -> None:
        # Don't pump any GPS — the existing emulator location stream (real
        # FLP / CLLocationManager) keeps firing fixes at the far-zone
        # cadence. Since none of them transition the zone state, the
        # inactivity timer keeps counting from start_tracking.
        time.sleep(DEBUG_SECONDS + 5)

    def asserts(ctx: RunContext) -> None:
        expect(
            ctx.obs,
            AutoStopped,
            where=lambda e: e.threshold_s == DEBUG_SECONDS,
            within_s=DEBUG_SECONDS + 30,
            description=f"auto-stop fires within {DEBUG_SECONDS} s threshold",
        )

    def teardown(ctx: RunContext) -> None:
        # Auto-stop already shut the service down; stop_tracking() is a
        # no-op here but keeps teardown symmetric with the other edge
        # scenarios. Clear the debug override so it doesn't bleed into
        # the next scenario in the suite.
        settings_mod.stop_tracking()
        try:
            settings_mod.set_setting("debug_auto_stop_seconds", 0, obs=ctx.obs)
        except Exception:
            pass
        expect_crash_free(ctx.obs)

    return Scenario(
        name="edge.auto_stop",
        steps=[
            step_lambda("setup", setup),
            step_lambda("idle", idle),
            step_lambda("asserts", asserts),
        ],
        teardown=teardown,
        timeout_s=DEBUG_SECONDS + 60,
    )
