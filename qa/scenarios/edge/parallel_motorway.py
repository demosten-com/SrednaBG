# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""A parallel motorway must not open a phantom traversal of the road beside it.

Regression for a user-reported bug (real drive, Greece -> Sofia, 2026-07-26,
reproduced identically on an Android phone and an iPhone running side by side).
Driving *northbound on the A3 "Струма" motorway* past the Кочериново interchange
produced a full "entering average-speed zone" announcement for the I-1 zone
`i1-02-north` — a 10.6 km zone on a different road — followed 13-21 s later by an
exit, leaving a junk History record with a nonsense average.

Why it happened: the A3 sweeps within ~7 m of the I-1 centerline for ~190 m at
that interchange, on a heading that sat inside `DIRECTION_TOLERANCE_DEG` of the
zone's *end-to-end* bearing. A single fix inside the on-road band was enough to
open a traversal, and the off-road exit grace then kept the phantom alive for a
few more seconds after the motorway pulled away. Both the Sofia-bound and the
Greece-bound carriageways hit it, so every driver on the country's busiest
corridor collected bogus records.

The fix is two-part, both in the shared core:
  * direction matching reads the centerline's *local* heading over a ±150 m
    window instead of its end-to-end bearing, and
  * entry now has to be confirmed over `ENTRY_CONFIRM_DISTANCE_M` of travel
    along the centerline before a traversal opens (back-dated to the first
    confirming fix, so genuine entries lose no averaging accuracy).

This scenario replays the real motorway geometry through `feed_point` and
asserts the app never enters the zone. Its companion — that a genuine drive on
I-1 itself still produces one clean traversal — is `qa/validate-zones.sh`, which
covers all 72 zones.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from ... import device as device_mod
from ... import geo
from ...assertions import AssertionFailure
from ...events import ProvisionalEntry, TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import load_zone, scenario_setup, scenario_teardown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "a3_kocherinovo_corridor.yaml"
INTERVAL_S = 1.0
# Mirrors RoadMatcher.DIRECTION_TOLERANCE_DEG — used only by the anti-vacuous
# guard below, which re-derives the *old* engine's entry gates.
DIRECTION_TOLERANCE_DEG = 45.0


def _load_fixture() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _point_to_polyline_m(lat: float, lng: float, poly: list[tuple[float, float]]) -> float:
    """Nearest distance from a point to a polyline, sampled at its vertices.

    Vertex sampling is enough here: the fixture and the centerline are both
    densely resampled, so the vertex minimum tracks the true perpendicular
    distance closely, and this only guards the fixture's premise.
    """
    return min(geo.haversine_m(lat, lng, p[0], p[1]) for p in poly)


def _bearing_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def _build_fixes(fixture: dict) -> list[tuple[float, float, float]]:
    """(lat, lng, bearing) per fix along the motorway.

    Heading is the course made good between consecutive fixture points plus the
    fixture's `course_bias_deg` — see the fixture header for why that bias is
    part of reproducing the reported drive rather than a fudge.
    """
    pts = [(float(p[0]), float(p[1])) for p in fixture["points"]]
    bias = float(fixture.get("course_bias_deg", 0.0))
    fixes: list[tuple[float, float, float]] = []
    for i, p in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else pts[i - 1]
        brg = (
            geo.bearing_deg(p[0], p[1], nxt[0], nxt[1])
            if i + 1 < len(pts)
            else geo.bearing_deg(nxt[0], nxt[1], p[0], p[1])
        )
        fixes.append((p[0], p[1], (brg + bias) % 360))
    return fixes


def build() -> Scenario:
    fixture = _load_fixture()
    zone_id = fixture["zone_id"]
    speed_ms = float(fixture["speed_kmh"]) / 3.6
    fixes = _build_fixes(fixture)
    drive_s = len(fixes) * INTERVAL_S

    def setup(ctx: RunContext) -> None:
        # Anti-vacuous guard. Without it this scenario would "pass" the moment
        # the geometry stopped reproducing the bug — which is exactly the case a
        # regression test must not silently absorb. So re-derive the *old*
        # engine's two entry gates here (inside the on-road band AND within
        # DIRECTION_TOLERANCE_DEG of the zone's end-to-end bearing) and require
        # that the replay would have tripped them. If a zone-data refresh ever
        # moves the roads apart or straightens the centerline, this fails loudly
        # and the fixture gets refreshed from Overpass instead of rotting.
        zone = load_zone(zone_id)
        centerline = [(p[0], p[1]) for p in zone["centerline"]]
        band = float(fixture["on_road_band_m"])
        whole_line = geo.bearing_deg(
            centerline[0][0], centerline[0][1], centerline[-1][0], centerline[-1][1]
        )
        would_have_matched = [
            (lat, lng)
            for lat, lng, brg in fixes
            if _point_to_polyline_m(lat, lng, centerline) <= band
            and _bearing_diff(brg, whole_line) <= DIRECTION_TOLERANCE_DEG
        ]
        if not would_have_matched:
            closest = min(_point_to_polyline_m(lat, lng, centerline) for lat, lng, _ in fixes)
            raise AssertionFailure(
                f"fixture no longer reproduces the bug: no fix in the A3 corridor clears "
                f"both of the old entry gates for {zone_id} (closest approach {closest:.0f} m "
                f"vs a {band:.0f} m band), so this would pass even with the fix reverted. "
                f"Refresh {FIXTURE.name} from Overpass.",
                ctx.obs,
            )
        scenario_setup(ctx, settings_id="S1")

    def drive(ctx: RunContext) -> None:
        d = device_mod.current()
        next_slot = time.monotonic()
        for lat, lng, brg in fixes:
            delay = next_slot - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            d.feed_point(lat, lng, speed_ms, brg)
            next_slot += INTERVAL_S

    def asserts(ctx: RunContext) -> None:
        changes: list[ZoneStateChange] = []
        provisional: list[ProvisionalEntry] = []
        spoken: list[TtsSpeak] = []
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
            elif isinstance(ev, ProvisionalEntry):
                provisional.append(ev)
            elif isinstance(ev, TtsSpeak):
                spoken.append(ev)

        # Neither InZone nor Unmeasured. Both of those require a *confirmed*
        # candidate, and the A3 corridor only ever accumulates ~109 m of
        # direction-matching travel against the 300 m ENTRY_CONFIRM_DISTANCE_M —
        # so the phantom never confirms and the detector stays Outside
        # throughout. Unmeasured is checked explicitly because it is the softer
        # failure the third zone state introduced: quieter than a full phantom
        # traversal (no TTS, no History row) but still wrong, since the car was
        # never on that road at all.
        entries = [e for e in changes if e.new in ("InZone", "Unmeasured")]
        if entries:
            raise AssertionFailure(
                f"driving the A3 motorway opened a phantom "
                f"{entries[0].new} of {[e.zone for e in entries]} — a road the "
                f"car was never on. "
                f"Transitions: {[(e.prev, e.new, e.zone) for e in changes]}",
                ctx.obs,
            )

        # …and it must stay *silent*. Not opening a traversal is no longer
        # enough on its own: the entry announcement is spoken from the
        # detector's candidate, ENTRY_CONFIRM_DISTANCE_M before a traversal
        # would confirm, so the confirmation window that kills the phantom
        # traversal no longer gags the phantom *voice*. What does is the
        # START_WITNESS_ARC_M guard on the candidate's arc: the A3 first matches
        # 282 m into the zone on Android and 289 m on iOS (each run logs
        # `provisional entry suppressed zone=i1-02-north arcM=… > 200`), far past
        # the 200 m threshold, so it can only ever have confirmed as Unmeasured
        # and is never announced. Drop that
        # guard and the user's original symptom — a spoken "entering
        # average-speed zone" for a road they are not on, with the wrong limit —
        # comes straight back, with everything above still passing.
        announced = [e for e in provisional if e.outcome == "announced"]
        if announced or spoken:
            raise AssertionFailure(
                f"driving the A3 motorway announced a phantom entry: "
                f"provisional={[(e.zone, e.outcome) for e in provisional]} "
                f"spoken={[e.text for e in spoken]}. The START_WITNESS_ARC_M "
                f"guard on the entry candidate is what must keep this silent.",
                ctx.obs,
            )

    return Scenario(
        name="edge.parallel_motorway",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_a3_corridor", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=drive_s + 90,
    )
