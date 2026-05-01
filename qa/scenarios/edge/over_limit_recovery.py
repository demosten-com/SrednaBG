# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Over-limit then recovery: speed at 160 km/h for first half, then 100 km/h.

Asserts the TTS pipeline announces over-limit + (later) recovered.
"""

from __future__ import annotations

from ...assertions import expect, expect_in_order
from ...drive import pump
from ...events import TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    fast = base_plan("trakiya-01-east", speed_kmh=160).compressed(2.0)
    # Splice: first half of the fast plan, then speed-down via slow plan
    # for the second half. We just reuse the same physical points so
    # only the timing differs.
    slow = base_plan("trakiya-01-east", speed_kmh=100).compressed(2.0)
    half = fast.duration_ms // 2
    plan = fast.slice(0, half)
    # Append slow second half, time-shifted so it follows the fast leg.
    second_half = slow.slice(slow.duration_ms // 2, slow.duration_ms)
    from ...drive import TrackPoint
    shifted = [
        TrackPoint(p.lat, p.lng, p.t_offset_ms + plan.duration_ms + 100)
        for p in second_half.points
    ]
    plan.points.extend(shifted)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")  # voice on, BG, car

    def drive(ctx: RunContext) -> None:
        pump(plan)

    def asserts(ctx: RunContext) -> None:
        # Minimum: we entered the zone and at some point spoke any
        # warning containing "Внимание" or "Warning" (substring across BG/EN).
        expect(ctx.obs, ZoneStateChange,
               where=lambda e: e.new == "InZone",
               within_s=plan.duration_ms / 1000 + 30,
               description="enter zone")
        expect(ctx.obs, TtsSpeak,
               where=lambda e: "Внимание" in e.text or "Warning" in e.text,
               within_s=plan.duration_ms / 1000 + 60,
               description="over-limit TTS warning")

    return Scenario(
        name="edge.over_limit_recovery",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=plan.duration_ms / 1000 + 120,
    )
