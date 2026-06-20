# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""A single coarse (low-accuracy) GPS fix must be dropped before it reaches
the speed/zone pipeline.

Regression for the user-reported S24 Ultra bug: the aosp flavor registered
both GPS and NETWORK providers, so cell/wifi fixes (100 m–2 km off) arrived
interleaved with GPS, producing wild speed spikes (130 → 242 km/h), zone
flapping, and inflated averages. The root-cause fix is GPS-only provider
selection (`chooseLocationProviders`, unit-tested). This scenario covers the
defense-in-depth half — the `MAX_ACCURACY_M` (50 m) gate in
`LocationTrackingService` — which drops any coarse fix regardless of source.

Shape:
  1. Feed clean (accuracy 5 m) stationary fixes to seed `lastRaw*` and prove
     tracking is alive (DisplaySpeed events appear, near 0).
  2. Inject ONE coarse fix (accuracy 200 m) ~1.1 km away, 1 s later.
  3. Feed clean fixes again at the original position.

Without the gate: step 2 has `deltaM ≈ 1100 m` over `dt = 1 s` →
`lastInferredSpeedKmh = (1100/1)*3.6 = 3960` clamped to 250 → DisplaySpeed
spikes to ~250 km/h, and the corrupt baseline lingers.

With the gate: the coarse fix is dropped before `deltaM` is computed (it never
seeds `lastRaw*` nor emits a DisplaySpeed), so no spike ever appears.

The assertion: after the coarse injection, no `DisplaySpeed` event reports
`kmh > 30`. 30 km/h is well above stationary GPS jitter and well below the 250
clamp, so the gap is unambiguous (same threshold as `cold_start_spike`).

Android-only: the gate lives in the Android service; iOS relies on
CoreLocation's internal quality filtering (see `_ANDROID_ONLY_EDGE` in
`srednabg_qa.py`).
"""

from __future__ import annotations

import time

from ... import device as device_mod
from ...assertions import expect, expect_never
from ...events import DisplaySpeed
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import scenario_setup, scenario_teardown

# A stationary position away from any zone polyline (Stara Zagora southern
# outskirts — same neighborhood as cold_start_spike, no motorway nearby) so we
# never trigger zone-state changes and isolate the speed pipeline.
BASE_LAT, BASE_LNG = 42.3950, 25.6300
# ~1.1 km due north — far enough that, unguarded, the implied speed pins at the
# 250 km/h clamp.
COARSE_LAT, COARSE_LNG = 42.4050, 25.6300

CLEAN_ACCURACY_M = 5.0
COARSE_ACCURACY_M = 200.0  # > MAX_ACCURACY_M (50)

FEED_DT_MS = 1000  # realistic 1 s cadence for the speed-inference dt


def build() -> Scenario:

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        dev = device_mod.current()
        t = int(time.time() * 1000)
        # 1) Clean stationary fixes — seed lastRaw*, establish tracking.
        for _ in range(5):
            dev.feed_point(BASE_LAT, BASE_LNG, speed_ms=0.0, bearing=0.0,
                           time_ms=t, accuracy_m=CLEAN_ACCURACY_M)
            t += FEED_DT_MS
            time.sleep(0.4)
        # Sanity: tracking is alive and reporting (low) speed before we test
        # the gate, so the later expect_never can't pass vacuously.
        expect(
            ctx.obs, DisplaySpeed,
            where=lambda e: e.kmh <= 30.0,
            within_s=2.0,
            description="clean stationary fixes should report a low DisplaySpeed",
        )
        ctx.obs.clear()
        # 2) One coarse fix ~1.1 km away. The gate must drop it.
        dev.feed_point(COARSE_LAT, COARSE_LNG, speed_ms=0.0, bearing=0.0,
                       time_ms=t, accuracy_m=COARSE_ACCURACY_M)
        t += FEED_DT_MS
        time.sleep(1.0)
        # 3) Clean fixes again at the original position.
        for _ in range(4):
            dev.feed_point(BASE_LAT, BASE_LNG, speed_ms=0.0, bearing=0.0,
                           time_ms=t, accuracy_m=CLEAN_ACCURACY_M)
            t += FEED_DT_MS
            time.sleep(0.5)

    def asserts(ctx: RunContext) -> None:
        expect_never(
            ctx.obs,
            DisplaySpeed,
            where=lambda e: e.kmh > 30.0,
            within_s=1.0,
            description=(
                "A coarse (>50 m accuracy) fix must be dropped, not turned into "
                "a phantom speed spike; DisplaySpeed must stay near 0"
            ),
        )

    return Scenario(
        name="edge.noisy_fix_rejected",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_noisy_fix", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=60,
    )
