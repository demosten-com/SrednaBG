# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Wrong direction: drive the centerline backward.

The RoadMatcher rejects entries with bearing diff >45° from the zone's
nominal direction (RoadMatcher.kt). Driving Trakiya east-to-west on a
zone tagged 'east' must never SUSTAIN a traversal of that zone. A valid
reverse traversal may legitimately enter the paired west-direction
zone, so we assert on zone id rather than "any InZone".

Why a fraction and not "never": the synthetic route follows the stored
centerline vertex-by-vertex, including its data quirks — trakiya-01-east
jogs ~40 m BACKWARD at its very first vertex, so the reversed drive
briefly travels the zone's true direction for one fix and the engine
(correctly, per its rules) admits it for that instant. The admission
then takes ~10 more updates to unwind: bearing is deliberately not
re-checked while in-zone, and the off-road exit hysteresis must run its
grace fixes (measured: exactly 11 consecutive InZone updates on BOTH
platforms — deterministic engine mechanics, not a bug). A real
wrong-way car has a smooth bearing and never produces the admission at
all. So we judge by the share of the drive spent in the forbidden zone
— same dominant-traversal philosophy as `validate-zones.sh`:
blip + exit latency ≈ 1.5%, a route-construction bug that drives a leg
the zone's way ≈ 9%, a genuine bearing-gate failure ≥ 50%.
"""

from __future__ import annotations

from ...assertions import AssertionFailure
from ...drive import DrivePlan, TrackPoint, pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ..bulk_loader import _drain_buffered
from ._helpers import base_plan, scenario_setup, scenario_teardown

# Ceiling on the share of detector updates spent InZone(forbidden zone).
# Sits ~3× above the benign jog blip (+exit latency) and ~2× below the
# smallest real failure mode observed (see module docstring).
MAX_FORBIDDEN_FRACTION = 0.05


def build() -> Scenario:
    # Splice on the UNCOMPRESSED plan and compress LAST: rebuilding
    # TrackPoints from a compressed plan drops `sim_offset_ms`, so the pump
    # derived speed over the compressed timeline and fed 220 km/h instead of
    # the encoded 110. compressed() on the final plan keeps the sim timeline.
    plan = base_plan("trakiya-01-east", speed_kmh=110)
    # Reverse temporal order — last point first, first point last.
    last_ms = plan.duration_ms
    reversed_pts = [
        TrackPoint(p.lat, p.lng, last_ms - p.t_offset_ms)
        for p in reversed(plan.points)
    ]
    plan_rev = DrivePlan(name=f"{plan.name}-reversed", points=reversed_pts).compressed(2.0)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        pump(plan_rev)

    def asserts(ctx: RunContext) -> None:
        # Drive completed — events are buffered; judge the whole sequence.
        changes = [e for e in _drain_buffered(ctx.obs)
                   if isinstance(e, ZoneStateChange)]
        if not changes:
            raise AssertionFailure(
                "no detector updates observed — drive never reached the app",
                ctx.obs)
        forbidden = sum(1 for e in changes
                        if e.new == "InZone" and e.zone == "trakiya-01-east")
        frac = forbidden / len(changes)
        if frac > MAX_FORBIDDEN_FRACTION:
            raise AssertionFailure(
                f"wrong-direction drive spent {forbidden}/{len(changes)} "
                f"detector updates ({frac:.1%}) InZone trakiya-01-east "
                f"(allowance {MAX_FORBIDDEN_FRACTION:.0%} for the known "
                f"first-vertex jog blip) — the bearing gate admitted a "
                f"reverse traversal", ctx.obs)

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
