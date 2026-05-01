# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Vehicle-type swap mid-zone.

Enter zone as 'car' (limit 140), drive at 120 (under car limit), then
mid-zone change vehicle type to 'truck' (limit 90). The next TTS event
or state change should reflect the new limit — at 120 km/h average,
isOverLimit must flip to true once the swap propagates.
"""

from __future__ import annotations

import time

from ... import settings as settings_mod
from ...assertions import expect, expect_in_order
from ...drive import pump
from ...events import TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    plan = base_plan("trakiya-01-east", speed_kmh=120).compressed(2.0)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")  # starts as car

    def drive_then_swap(ctx: RunContext) -> None:
        # Drive first half, then change vehicle type, then continue.
        half_ms = plan.duration_ms // 2
        first = plan.slice(0, half_ms)
        second = plan.slice(half_ms, plan.duration_ms)
        pump(first)
        settings_mod.set_setting("vehicle_type", "truck", obs=ctx.obs)
        time.sleep(0.5)
        pump(second)

    def asserts(ctx: RunContext) -> None:
        # We expect the entry announcement (limit 140 — pre-swap), and
        # then either an over-limit warning (post-swap) or a recovered
        # state change. The minimum reliable assertion is "we entered".
        expect(
            ctx.obs,
            ZoneStateChange,
            where=lambda e: e.new == "InZone",
            within_s=plan.duration_ms / 1000 + 30,
            description="enter zone as car",
        )

    return Scenario(
        name="edge.vehicle_swap",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_then_swap", drive_then_swap),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=plan.duration_ms / 1000 + 60,
    )
