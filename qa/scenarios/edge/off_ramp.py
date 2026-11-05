# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Off-ramp exit: drive zone normally, then divert >150m off centerline.

ZoneDetector exits early when the point is no longer 'on road'
(MAX_ROAD_DISTANCE_M=100, motorway override 150). Asserts state goes
to Exiting before the natural end of the zone.
"""

from __future__ import annotations

from ...assertions import expect_in_order
from ... import geo
from ...drive import DrivePlan, TrackPoint, pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import DEFAULT_ZONE, base_plan, resolve_zone, scenario_setup, scenario_teardown


def build() -> Scenario:
    # Splice on the UNCOMPRESSED plan and compress LAST — rebuilding
    # TrackPoints from a compressed plan drops `sim_offset_ms` and breaks
    # the sim timeline at the splice seam (see wrong_direction.py).
    plan = base_plan(resolve_zone(DEFAULT_ZONE))
    # Replace points after the temporal midpoint with off-ramp points
    # ~300m perpendicular to the centerline at the divert moment.
    half = plan.duration_ms // 2
    survivors = [p for p in plan.points if p.t_offset_ms < half]
    if not survivors:
        raise RuntimeError("plan too short to splice off-ramp")
    last = survivors[-1]
    # Leave perpendicular to the selected road, whatever its direction.
    heading = geo.bearing_deg(survivors[-2].lat, survivors[-2].lng, last.lat, last.lng)
    detour_pts = []
    for i in range(1, 6):
        lat, lng = geo.destination_point(last.lat, last.lng, (heading + 90) % 360, 110 * i)
        detour_pts.append(TrackPoint(lat, lng, last.t_offset_ms + i * 1000))
    spliced = DrivePlan(name=f"{plan.name}-offramp",
                        points=survivors + detour_pts).compressed(2.0)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(spliced)

    def asserts(ctx: RunContext) -> None:
        expect_in_order(
            ctx.obs,
            [
                (ZoneStateChange, lambda e: e.new == "InZone"),
                (ZoneStateChange, lambda e: e.new == "Exiting"),
            ],
            within_s=spliced.duration_ms / 1000 + 30,
            description="enter then off-ramp exit",
        )

    return Scenario(
        name="edge.off_ramp",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_off_ramp", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=spliced.duration_ms / 1000 + 60,
    )
