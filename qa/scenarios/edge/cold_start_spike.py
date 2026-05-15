# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Cold-start position jump: seed a far position, start tracking, jump to
the real position, then sit stationary.

Reproduces the symptom of the user-reported bug "Now shows 250 km/h after
pressing Start while standing still":

  - Sample 1 = far position (the 'cached last-known' analog).
  - Sample 2 = real position (~500m away).
  - Sample 3..N = real position, stationary.

Without the fix:
  - Sample 2 sets `lastInferredSpeedKmh = (500m/1s)*3.6 = 1800` clamped to
    `MAX_INFERRED_SPEED_KMH = 250.0`.
  - Sample 3+ have `deltaM < MIN_SPEED_INFER_M = 5m`, so the inference
    block never runs; `lastInferredSpeedKmh` stays at 250 forever.
  - `speedKmh = max(reportedSpeedKmh ≈ 0, 250) = 250` on every sample.

With the fix (LocationTrackingService.kt — `else if (deltaM < MIN_SPEED_INFER_M)`
resets `lastInferredSpeedKmh = 0.0`):
  - Sample 3 enters the new else-if branch, clears the inferred value to 0.
  - displaySpeed drops back to 0 within one sample.

The assertion: after a settling period following the position jump, no
`DisplaySpeed` event reports `kmh > 30`. 30 km/h is comfortably above
GPS jitter noise floor and comfortably below the 250 clamp, so the gap
is unambiguous.
"""

from __future__ import annotations

import time

from ... import device as device_mod
from ...assertions import expect_never
from ...events import DisplaySpeed
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import scenario_setup, scenario_teardown

# Two stationary positions ~500m apart in central Bulgaria, deliberately
# away from any zone polyline so we never trigger zone-state changes.
# Chosen near Stara Zagora's southern outskirts (no motorway nearby).
FAR_LAT, FAR_LNG = 42.3950, 25.6300
REAL_LAT, REAL_LNG = 42.3995, 25.6300  # ~500 m due north

# The far-zone GPS interval is INTERVAL_FAR_MS = 5000ms; budget enough
# wall time for at least 2 fresh deliveries at each step.
SETTLE_AFTER_JUMP_S = 7.0
STATIONARY_OBSERVE_S = 12.0


def build() -> Scenario:

    def setup(ctx: RunContext) -> None:
        # Seed the emulator with the "far" position BEFORE tracking starts,
        # so the first GPS update the LocationTrackingService receives is
        # this one (acting as the analog of FLP's cached last-known fix).
        device_mod.current().geo_fix(FAR_LNG, FAR_LAT)
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        # Let the first sample (FAR) flow through and seed lastRaw*.
        time.sleep(6.0)
        # Jump to the real position. On the unfixed code, this produces
        # the 250 clamp and pins it forever. On the fixed code, the next
        # stationary sample resets it.
        device_mod.current().geo_fix(REAL_LNG, REAL_LAT)
        # Wait for the jump-sample and at least one stationary sample
        # to be processed, then discard those events. Without this we'd
        # see the legitimate transient 250 spike on the jump-sample even
        # in the fixed build.
        time.sleep(SETTLE_AFTER_JUMP_S)
        ctx.obs.clear()
        # Observe the steady-state stationary period. All DisplaySpeed
        # events from this point onward should report kmh near 0.
        time.sleep(STATIONARY_OBSERVE_S)

    def asserts(ctx: RunContext) -> None:
        expect_never(
            ctx.obs,
            DisplaySpeed,
            where=lambda e: e.kmh > 30.0,
            within_s=1.0,
            description=(
                "Now km/h must not stay elevated after a cold-start position "
                "jump; lastInferredSpeedKmh should decay on stationary samples"
            ),
        )

    return Scenario(
        name="edge.cold_start_spike",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_cold_start", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=60,
    )
