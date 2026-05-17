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
"""

from __future__ import annotations

import time

from ... import device as device_mod
from ...assertions import expect_never
from ...drive import pump, synthetic_drive
from ...events import DisplaySpeed
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import scenario_setup, scenario_teardown

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
        # Switch to stationary. Keep re-sending the same fix at the
        # cruise cadence so the GPS provider keeps delivering location
        # updates (CoreLocation in particular won't emit duplicates on
        # its own — the QA harness has to push them).
        end_settle = time.monotonic() + STOP_SETTLE_S
        while time.monotonic() < end_settle:
            device_mod.current().geo_fix(STOP_LNG, STOP_LAT)
            time.sleep(1.0)
        ctx.obs.clear()
        end_observe = time.monotonic() + STOP_OBSERVE_S
        while time.monotonic() < end_observe:
            device_mod.current().geo_fix(STOP_LNG, STOP_LAT)
            time.sleep(1.0)

    def asserts(ctx: RunContext) -> None:
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
