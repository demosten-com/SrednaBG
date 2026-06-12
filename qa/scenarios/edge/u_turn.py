# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""U-turn / re-entry: drive zone, U-turn past exit, drive zone again.

Should produce TWO discrete enter/exit cycles, not one continuous one.
Intermediate wrong-direction segment should not trigger entries on the
opposite-direction zone (or trigger entry on a paired zone if one
exists — for trakiya-01-east the paired westbound zone is
trakiya-01-west).

This scenario tolerates either (a) two enter-exit on the original zone
(if there's no paired westbound) or (b) one enter-exit, then nothing
(if a westbound zone catches the reverse leg). The only thing it
forbids is a crash and a phantom never-enter.
"""

from __future__ import annotations

from ...assertions import expect, expect_in_order
from ...drive import DrivePlan, TrackPoint, pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    # Splice on the UNCOMPRESSED plan and compress LAST — rebuilding
    # TrackPoints from a compressed plan drops `sim_offset_ms` and doubles
    # the fed speed on the return leg (see wrong_direction.py).
    fwd = base_plan("trakiya-01-east", speed_kmh=110, exit_km=2)
    # Reverse: start from after the original exit, traverse backward.
    last_ms = fwd.duration_ms
    rev_pts = [
        TrackPoint(p.lat, p.lng, last_ms + 1000 + (last_ms - p.t_offset_ms))
        for p in reversed(fwd.points)
    ]
    plan = DrivePlan(name=f"{fwd.name}-uturn", points=fwd.points + rev_pts).compressed(2.0)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(plan)

    def asserts(ctx: RunContext) -> None:
        # First cycle is required; second cycle (if any) is optional.
        expect_in_order(
            ctx.obs,
            [
                (ZoneStateChange, lambda e: e.new == "InZone"),
                (ZoneStateChange, lambda e: e.new == "Exiting"),
            ],
            within_s=plan.duration_ms / 1000 + 30,
            description="first east-bound entry+exit",
        )

    return Scenario(
        name="edge.u_turn",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_uturn", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=plan.duration_ms / 1000 + 60,
    )
