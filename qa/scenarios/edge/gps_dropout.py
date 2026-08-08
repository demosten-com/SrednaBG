# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""GPS dropout: 15-second gap mid-zone. Detector should not phantom-exit.

Models a tunnel or signal blackout. A gap >10s (`GPS_DROPOUT_MS`) has no speed
samples to integrate, so the ZoneDetector bridges the distance from the
centerline projection instead — the car demonstrably covered that arc. It used
to drop the gap's distance outright, which left elapsed time counting ground the
average never got credit for and deflated the reported average (see ISSUE-012).
LocationTrackingService's adaptive interval is irrelevant here — we just stop
pushing fixes.
"""

from __future__ import annotations

from ...assertions import expect_in_order
from ...drive import pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    plan = base_plan("trakiya-01-east", speed_kmh=120).compressed(2.0)
    midpoint_ms = plan.duration_ms // 2
    plan_with_gap = plan.with_dropout(midpoint_ms - 7500, midpoint_ms + 7500)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(plan_with_gap)

    def asserts(ctx: RunContext) -> None:
        expect_in_order(
            ctx.obs,
            [
                (ZoneStateChange, lambda e: e.new == "InZone"),
                (ZoneStateChange, lambda e: e.new == "Exiting"),
            ],
            within_s=plan_with_gap.duration_ms / 1000 + 30,
            description="enter then exit despite GPS dropout",
        )

    return Scenario(
        name="edge.gps_dropout",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_with_gap", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=plan_with_gap.duration_ms / 1000 + 90,
    )
