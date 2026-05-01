# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Wrong direction: drive the centerline backward.

The RoadMatcher rejects entries with bearing diff >45° from the zone's
nominal direction (RoadMatcher.kt:13-20). Driving Trakiya east-to-west
on a zone tagged 'east' should NEVER enter that specific zone. A valid
reverse traversal may legitimately enter the paired west-direction
zone, so we assert on zone id rather than "any InZone".
"""

from __future__ import annotations

from ...assertions import expect_never
from ...drive import DrivePlan, TrackPoint, pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    plan = base_plan("trakiya-01-east", speed_kmh=110).compressed(2.0)
    # Reverse temporal order — last point first, first point last.
    last_ms = plan.duration_ms
    reversed_pts = [
        TrackPoint(p.lat, p.lng, last_ms - p.t_offset_ms)
        for p in reversed(plan.points)
    ]
    plan_rev = DrivePlan(name=f"{plan.name}-reversed", points=reversed_pts)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(plan_rev)

    def asserts(ctx: RunContext) -> None:
        expect_never(
            ctx.obs,
            ZoneStateChange,
            where=lambda e: e.new == "InZone" and e.zone == "trakiya-01-east",
            within_s=plan_rev.duration_ms / 1000 + 5,
            description="wrong-direction drive must NOT enter trakiya-01-east",
        )

    return Scenario(
        name="edge.wrong_direction",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_reversed", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=plan_rev.duration_ms / 1000 + 30,
    )
