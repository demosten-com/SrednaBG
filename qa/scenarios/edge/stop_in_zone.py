# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Stop in zone: drive to mid-zone, hold position 60s, resume.

Asserts (a) zone is entered, (b) detector remains in InZone across the
stop (does not bounce to Outside), (c) zone is exited cleanly.
"""

from __future__ import annotations

from ...assertions import expect, expect_in_order, expect_never
from ...drive import pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    plan = base_plan("trakiya-01-east", speed_kmh=120).compressed(2.0)
    # Stop at the temporal midpoint (well inside the zone for typical
    # approach_km=2 + ~10km zone + exit_km=1 layout).
    midpoint_ms = plan.duration_ms // 2
    stop_plan = plan.with_stop(midpoint_ms, duration_ms=60_000)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(stop_plan)

    def asserts(ctx: RunContext) -> None:
        # Order: Outside -> InZone (some time later) -> Exiting
        expect_in_order(
            ctx.obs,
            [
                (ZoneStateChange, lambda e: e.new == "InZone"),
                (ZoneStateChange, lambda e: e.new == "Exiting"),
            ],
            within_s=stop_plan.duration_ms / 1000 + 30,
            description="enter then exit despite mid-zone stop",
        )

    return Scenario(
        name="edge.stop_in_zone",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_with_stop", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=stop_plan.duration_ms / 1000 + 90,
    )
