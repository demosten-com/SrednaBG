# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Speed decays to ~0 when the car stops after sustained motion.

User-reported regression on iOS following commit 04616e6 ("Added GPS noice
filter when speeds are very small"): after cruising at ~50 km/h for a few
minutes and stopping at a traffic light, the speed display decayed once to
~19 km/h and then **stalled there until the car moved again**.

Root cause was iOS-specific: `CLLocationTracker.setIntervalMs` mapped the
5s "far-from-zone" cadence to `CLLocationManager.distanceFilter = 50m`,
which is a minimum-distance gate. While stationary the device never moves
50m, so no fix is delivered, and the Kalman filter inside `GpsPointBuilder`
is starved — leaving the speed estimate frozen at whatever value the
filter held just after the user braked.

This scenario exercises the same shape against both platforms:
  - cruise at ~50 km/h for ~15 s of motion fixes,
  - hold the same coordinates for ~20 s,
  - assert that `DisplaySpeed` events in the latter half of the stationary
    period report `kmh <= 10`.

10 km/h is a comfortable margin: with the fix the filter decays to
< 1 km/h within ~2 fixes at the 5s cadence (Kalman gain ~0.89 once
`speedProcessNoise = 4 * dt` adds 20 to `speedVariance`). Without the fix
the value sticks somewhere between 15 and 25 km/h, which trips the assert.

Android uses `LocationRequest.Builder(PRIORITY_HIGH_ACCURACY, intervalMs)`
which is time-based and unaffected — this scenario keeps it as a regression
gate so a future change to the Android location request can't reintroduce
the freeze-on-stop class of bug.

Stationary feed: the hold dithers the coordinates by a sub-metre each fix
(`_hold_stationary` / STATIONARY_JITTER_DEG) rather than repeating one exact
point. That mirrors a real receiver (GPS never freezes its coordinates) and,
crucially, keeps the iOS Simulator delivering: `simctl location set` only
re-emits `didUpdateLocations` when the coordinate *changes*, so identical
repeats would starve the post-stop stream (`adb emu geo fix` re-delivers
regardless). The dither stays well under the 10 km/h decay assertion, so it
exercises the real CoreLocation `distanceFilter` delivery path on iOS without
masking a stuck speed.
"""

from __future__ import annotations

import time

from ... import device as device_mod
from ...assertions import expect_never
from ...drive import pump, synthetic_drive
from ...events import DisplaySpeed
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import assert_signal_observed, scenario_setup, scenario_teardown

# Stationary segment outside any zone (near Stara Zagora, same patch
# cold_start_spike uses) so the assertions aren't entangled with zone
# transitions.
STOP_LAT, STOP_LNG = 42.3995, 25.6300

# Cruise: ~225m heading north → ~15s at 50 km/h.
# 0.0001 lat ≈ 11.1m, so 0.0020 ≈ 222m.
CRUISE_START_LAT = 42.3975
CRUISE_SPEED_KMH = 50.0
CRUISE_HZ = 1.0

# After the cruise we hold STOP_LAT/LNG. The first half is a "settle"
# window we discard (transient decay sample from cruise → stop is real
# Kalman behavior, not the bug). The second half is the assertion window.
STOP_SETTLE_S = 8.0
STOP_OBSERVE_S = 12.0

# A stationary GPS receiver never reports the *exact* same fix twice — it
# dithers by a fraction of a metre every second. We reproduce that by flipping
# the latitude by ±STATIONARY_JITTER_DEG each fix. Two reasons:
#   1. Realism — "perfectly frozen coordinates" is not a real-world input.
#   2. It's REQUIRED on the iOS Simulator: `simctl location set` only re-emits
#      `didUpdateLocations` when the coordinate *changes*, so identical repeats
#      starve the fix stream and the post-stop window goes silent (`adb emu geo
#      fix` re-delivers regardless, which is why Android tolerated repeats).
# 0.000003° ≈ 0.33 m, so consecutive fixes are ~0.67 m apart → an apparent
# ~2.4 km/h at the 1 Hz feed before filtering — comfortably under the 10 km/h
# decay assertion, and the Kalman/small-speed filter pulls the displayed value
# lower still.
STATIONARY_JITTER_DEG = 0.000003


def _hold_stationary(seconds: float, counter: list[int]) -> None:
    """Feed jittered stationary fixes at ~1 Hz for `seconds`.

    `counter` is a single-element list used as a mutable cross-call index so the
    ± dither keeps alternating across the settle and observe windows.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        dlat = STATIONARY_JITTER_DEG if counter[0] % 2 == 0 else -STATIONARY_JITTER_DEG
        counter[0] += 1
        device_mod.current().geo_fix(STOP_LNG, STOP_LAT + dlat)
        time.sleep(1.0)


def build() -> Scenario:
    cruise_plan = synthetic_drive(
        [(CRUISE_START_LAT, STOP_LNG), (STOP_LAT, STOP_LNG)],
        speed_kmh=CRUISE_SPEED_KMH,
        hz=CRUISE_HZ,
    )

    def setup(ctx: RunContext) -> None:
        device_mod.current().geo_fix(STOP_LNG, CRUISE_START_LAT)
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(cruise_plan)
        # Switch to stationary, dithering by a sub-metre each fix (see
        # `_hold_stationary` / STATIONARY_JITTER_DEG) so the GPS provider keeps
        # delivering — CoreLocation on the Simulator won't re-emit an unchanged
        # fix, and a real receiver never freezes its coordinates anyway.
        fix_counter = [0]
        _hold_stationary(STOP_SETTLE_S, fix_counter)
        ctx.obs.clear()
        # Snapshot before the assertion window so asserts() can confirm the
        # speed signal actually arrived (anti-vacuous guard). type_counts
        # survives clear().
        ctx.data["ds_before"] = ctx.obs.type_counts["DisplaySpeed"]
        _hold_stationary(STOP_OBSERVE_S, fix_counter)

    def asserts(ctx: RunContext) -> None:
        assert_signal_observed(
            ctx, DisplaySpeed, since=ctx.data["ds_before"],
            label="the post-stop observation window",
        )
        expect_never(
            ctx.obs,
            DisplaySpeed,
            where=lambda e: e.kmh > 10.0,
            within_s=1.0,
            description=(
                "Now km/h must decay to near 0 while stationary; a stuck "
                "value would freeze the speedometer after a stop"
            ),
        )

    return Scenario(
        name="edge.speed_decay_after_stop",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_then_stop", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=int(cruise_plan.duration_ms / 1000) + STOP_SETTLE_S + STOP_OBSERVE_S + 30,
    )
