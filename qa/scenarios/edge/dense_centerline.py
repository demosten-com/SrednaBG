# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Dense short-segment zone: a single clean traversal, no integrator-drift exit.

Regression for the qa/feed-zone.sh bug. A zone whose centerline is densely
sampled with segments far shorter than the per-second travel distance
(struma-02-south: 71 of 101 segments under 30 m) used to break the engine when
driven with a constant reported speed: the speed×time distance integrator
over-counted (it credited speed×interval per fix while the car physically moved
a shorter sub-segment), so `distanceTraveled` raced ahead of the true position.
The old engine then (a) collapsed the "max for remainder" to 0 km/h mid-zone
once the integrator passed the zone distance, and (b) tripped the
`distanceTraveled >= distanceM * 1.1` exit, immediately re-matching the same
zone as a mid-zone cold-start and resetting the stats — surfacing as
"zone ended → instantly re-enters, average starts over".

The fix sources the remaining distance and the exit decision from the polyline
projection (drift-free) instead of the integrator. This scenario reproduces the
exact bug input — constant speed via `feed_point`, fixes placed on the raw
(uneven) centerline vertices — and asserts the zone is entered exactly once and
exited exactly once.
"""

from __future__ import annotations

import importlib.util
import math
import time
from pathlib import Path

from ... import device as device_mod
from ...assertions import AssertionFailure
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import ZONES_JSON, load_zone, scenario_setup, scenario_teardown

ZONE_ID = "struma-02-south"
SPEED_MS = 30.0          # 108 km/h, under the 140 limit; > avg segment so the
                         # old integrator over-counts at the 1 Hz feed cadence.
INTERVAL_S = 1.0
REPO_ROOT = Path(__file__).resolve().parents[3]


def _geo():
    """Load make_test_route's stdlib geo helpers (bearing/haversine)."""
    path = REPO_ROOT / "scrapers" / "scripts" / "make_test_route.py"
    spec = importlib.util.spec_from_file_location("make_test_route", path)
    if not spec or not spec.loader:
        raise RuntimeError("could not load make_test_route.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_fixes() -> list[tuple[float, float, float]]:
    """(lat, lng, bearing) per fix: 4 approach points then every raw centerline
    vertex — deliberately uneven spacing to reproduce the integrator over-count."""
    mod = _geo()
    zone = load_zone(ZONE_ID)
    cl = [(p[0], p[1]) for p in zone["centerline"]]
    # Orient start -> end so we drive the zone's signed direction.
    start = (zone["start"]["lat"], zone["start"]["lng"])
    if mod.haversine_m(*cl[0], *start) > mod.haversine_m(*cl[-1], *start):
        cl = cl[::-1]

    entry_bearing = mod.bearing_deg(cl[0][0], cl[0][1], cl[1][0], cl[1][1])
    seg0 = mod.haversine_m(cl[0][0], cl[0][1], cl[1][0], cl[1][1])
    approach = [
        mod.destination_point(cl[0][0], cl[0][1], (entry_bearing + 180) % 360, seg0 * k)
        for k in (4, 3, 2, 1)
    ]
    pts = approach + cl

    fixes: list[tuple[float, float, float]] = []
    for i in range(len(pts)):
        nxt = pts[i + 1] if i + 1 < len(pts) else pts[i]
        brg = mod.bearing_deg(pts[i][0], pts[i][1], nxt[0], nxt[1]) if nxt != pts[i] else entry_bearing
        fixes.append((pts[i][0], pts[i][1], brg))
    return fixes


def build() -> Scenario:
    fixes = _build_fixes()
    drive_s = len(fixes) * INTERVAL_S

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        d = device_mod.current()
        next_slot = time.monotonic()
        for lat, lng, brg in fixes:
            delay = next_slot - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            d.feed_point(lat, lng, SPEED_MS, brg)
            next_slot += INTERVAL_S

    def asserts(ctx: RunContext) -> None:
        # Drain every zone-state transition emitted during the drive.
        changes: list[ZoneStateChange] = []
        settle = 4.0
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            try:
                ev = ctx.obs.queue.get(timeout=0.2)
            except Exception:
                continue
            if isinstance(ev, ZoneStateChange):
                changes.append(ev)
                deadline = time.monotonic() + settle

        entries = [e for e in changes if e.new == "InZone" and e.prev != "InZone"]
        exits = [e for e in changes if e.new == "Exiting"]

        if not entries:
            raise AssertionFailure(
                f"never entered zone {ZONE_ID} (transitions: "
                f"{[(e.prev, e.new) for e in changes]})", ctx.obs)
        # The bug produced a second entry (Exiting -> InZone re-match) and a
        # second Exiting mid-zone. A clean traversal has exactly one of each.
        if len(entries) != 1:
            raise AssertionFailure(
                f"expected a single uninterrupted traversal of {ZONE_ID}, but it was "
                f"entered {len(entries)}× — integrator-drift exit + mid-zone re-entry "
                f"regressed. Transitions: {[(e.prev, e.new) for e in changes]}", ctx.obs)
        if len(exits) > 1:
            raise AssertionFailure(
                f"expected one clean exit of {ZONE_ID}, saw {len(exits)} (spurious "
                f"mid-zone exit). Transitions: {[(e.prev, e.new) for e in changes]}",
                ctx.obs)

    return Scenario(
        name="edge.dense_centerline",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_dense_zone", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=drive_s + 90,
    )
