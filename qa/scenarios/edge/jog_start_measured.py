# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Jog-start zone, honest approach: the traversal must still be MEASURED.

The positive-path companion to `edge.mid_zone_join`. That scenario proves an
unwitnessed entry opens `ZoneState.Unmeasured`; this one proves the rule didn't
overshoot and start refusing to measure real entries on the awkward half of the
zone data.

An ISSUE-001 zone is one whose stored centerline opens with a segment pointing
**away** from the road's direction (`cl[0]` is the camera, `cl[1]` sits *behind*
it, and the line only turns forward after that). A driver crossing that camera
therefore projects onto the far end of the jog rather than onto arc 0. The
original case was `i3-02-north`, whose jog was 121 m — past the 100 m an earlier
draft of the rule would have allowed, and the reason `START_WITNESS_ARC_M` is
200 m rather than 100 m. The core unit test (`ZoneUnmeasuredTest."a zone whose
centerline starts with a backwards jog is still measurable"` / Swift twin) pins
that band at unit level on a synthetic fixture; this drives real geometry
end-to-end.

**The zone is chosen from the catalog under test, not named**: the one with the
longest opening jog (`longest_jog_zone`). The jog is a data defect, and the
scraper keeps fixing them — the served feed lost `i3-02-north`'s on 2026-09-28,
leaving 80 m on `i6-01-east` as the longest. A scenario pinned to one zone dies
the night its defect is repaired upstream; this one moves to the worst jog that
is still really being served. If no jog reaches `MIN_JOG_M`, the live case is
reported as not applicable; the fixed native regression still runs nightly.

Asserts:
  (a) `InZone` is reached for the zone — a genuine approach still measures,
  (b) `Unmeasured` is never reported for it — the witness rule didn't misfire.

Both halves matter: (a) alone would pass on an engine that measures everything,
(b) alone would pass on a drive that never matched the zone at all.

**Verified to discriminate — on the 121 m jog.** Replaying the `i3-02-north`
trace through the Kotlin engine against the full real zone catalogue: with
`START_WITNESS_ARC_M = 200` it reports `InZone(i3-02-north)` at fix 88; with the
threshold tightened to 100 m the same drive reports `Unmeasured(i3-02-north)` —
the failure (a) forbids. That holds for a jog longer than 100 m. On a shorter
one (all the live feed has left) this still proves a jog-start zone is measured
end-to-end, but no longer separates 200 m from 100 m — the unit test does.

The drive is built here rather than via `base_plan`, which resamples the stored
centerline verbatim: on this zone that would make the car reverse 121 m at the
camera and pivot 180°, a manoeuvre no real drive performs and one whose
direction-match behaviour would be testing the fixture, not the engine. See
`physical_road_plan`.
"""

from __future__ import annotations

import time

from ... import geo, zone_source
from ...assertions import AssertionFailure
from ...drive import DrivePlan, TrackPoint
from ...drive import pump
from ...events import ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import scenario_setup, scenario_teardown

# Below this an opening "jog" is ordinary vertex noise, not the ISSUE-001 shape.
MIN_JOG_M = 50.0
SPEED_KMH = 90.0
APPROACH_KM = 2.0
# Far enough past the camera to clear ENTRY_CONFIRM_DISTANCE_M (300 m) with
# room to spare, but short of a long zone's end — we are testing the
# entry, not the traversal, and a full run would cost ~6 minutes.
INTO_ZONE_KM = 3.0
COMPRESSION = 2.0
HZ = 1.0


def _oriented_centerline(zone: dict) -> list[tuple[float, float]]:
    """Centerline as `(lat, lng)` running start → end.

    The engine self-orients (`ZoneDetector` ctor / `orientCenterlineToStart`);
    the fixture has to do the same or a stored end-first line would be driven
    backwards.
    """
    cl = [(p[0], p[1]) for p in zone["centerline"]]
    start = (zone["start"]["lat"], zone["start"]["lng"])
    head = geo.haversine_m(cl[0][0], cl[0][1], start[0], start[1])
    tail = geo.haversine_m(cl[-1][0], cl[-1][1], start[0], start[1])
    return cl[::-1] if tail < head else cl


def _forward_bearing_at_start(cl: list[tuple[float, float]], anchor_m: float = 300.0) -> float:
    """Direction the road actually runs at the entry camera.

    Read from a vertex ~`anchor_m` along the arc, not from `cl[0]→cl[1]` —
    that first segment is precisely the backwards jog under test.
    """
    acc = 0.0
    anchor = cl[-1]
    for a, b in zip(cl, cl[1:]):
        acc += geo.haversine_m(a[0], a[1], b[0], b[1])
        if acc >= anchor_m:
            anchor = b
            break
    return geo.bearing_deg(cl[0][0], cl[0][1], anchor[0], anchor[1])


def _along_m(cl: list[tuple[float, float]], forward: float, pt: tuple[float, float]) -> float:
    """Signed distance from the camera (`cl[0]`) along `forward` (negative = behind)."""
    camera = cl[0]
    d = geo.haversine_m(camera[0], camera[1], pt[0], pt[1])
    if d == 0:
        return 0.0
    brg = geo.bearing_deg(camera[0], camera[1], pt[0], pt[1])
    delta = abs(brg - forward) % 360
    delta = 360 - delta if delta > 180 else delta
    return d * (1 if delta <= 90 else -1)


def jog_length_m(zone: dict) -> float:
    """How far behind the entry camera the stored centerline reaches before it
    turns forward — 0 for a zone that starts cleanly."""
    cl = _oriented_centerline(zone)
    if len(cl) < 3:
        return 0.0
    forward = _forward_bearing_at_start(cl)
    reach = 0.0
    for pt in cl[1:]:
        along = _along_m(cl, forward, pt)
        if along > 0:
            break
        reach = max(reach, -along)
    return reach


def longest_jog_zone() -> dict:
    """The zone of the catalog under test with the longest opening jog."""
    zone = max(zone_source.zones_by_id().values(), key=jog_length_m)
    if jog_length_m(zone) < MIN_JOG_M:
        from ...zone_selection import NotApplicable
        raise NotApplicable(
            f"no zone opens with a backwards jog of {MIN_JOG_M:.0f} m or more; "
            "fixed native ISSUE-001 regressions still run")
    return zone


def physical_road_plan(zone: dict) -> DrivePlan:
    """A drive along the road as a car can actually travel it.

    Keeps the real geometry but drops the leading vertices that sit *behind*
    the entry camera along the road's forward direction — the ISSUE-001 jog.
    What survives is: a straight `APPROACH_KM` lead-in on the road's heading,
    the camera at `cl[0]`, and then the stored centerline from the first vertex
    genuinely ahead of it.

    The engine still sees the untouched stored geometry (that comes from
    zones.json on the device); only the *track we drive* is straightened, which
    is the whole point — the projection onto the jog is what the witness rule
    has to survive.
    """
    cl = _oriented_centerline(zone)
    camera = cl[0]
    forward = _forward_bearing_at_start(cl)

    ahead = [p for p in cl[1:] if _along_m(cl, forward, p) > 0]
    # Trim to INTO_ZONE_KM of arc so the run stays short.
    path: list[tuple[float, float]] = [camera]
    acc = 0.0
    for pt in ahead:
        acc += geo.haversine_m(path[-1][0], path[-1][1], pt[0], pt[1])
        path.append(pt)
        if acc >= INTO_ZONE_KM * 1000:
            break

    approach_start = geo.destination_point(
        camera[0], camera[1], (forward + 180) % 360, APPROACH_KM * 1000
    )
    step_m = (SPEED_KMH / 3.6) / HZ
    pts = list(geo.resample_polyline([approach_start, camera], step_m))
    pts += list(geo.resample_polyline(path, step_m))[1:]

    step_ms = int(1000 / HZ)
    return DrivePlan(
        name=f"{zone['id']}-jog-start",
        points=[TrackPoint(lat, lng, i * step_ms) for i, (lat, lng) in enumerate(pts)],
    )


def build() -> Scenario:
    zone = longest_jog_zone()
    zone_id = zone["id"]
    plan = physical_road_plan(zone).compressed(COMPRESSION)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")
        ctx.obs.clear()

    def drive(ctx: RunContext) -> None:
        pump(plan)

    def asserts(ctx: RunContext) -> None:
        # Drain the whole run rather than using expect/expect_never in sequence:
        # those are lossy, and both halves below need the same complete record.
        # Same rolling settle window as edge.mid_zone_join.
        states: list[ZoneStateChange] = []
        settle = 4.0
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            try:
                ev = ctx.obs.queue.get(timeout=0.2)
            except Exception:
                continue
            if isinstance(ev, ZoneStateChange):
                states.append(ev)
                deadline = time.monotonic() + settle

        # (a) A witnessed entry on a jog-start zone must still be measured.
        if not any(e.new == "InZone" and e.zone == zone_id for e in states):
            raise AssertionFailure(
                f"an honest approach to {zone_id} never opened a measured "
                f"traversal — START_WITNESS_ARC_M must absorb the zone's "
                f"backwards start jog (ISSUE-001). "
                f"Transitions: {[(e.prev, e.new, e.zone) for e in states]}",
                ctx.obs,
            )

        # (b) ...and must not be downgraded to the unwitnessed state.
        unmeasured = [e for e in states if e.new == "Unmeasured" and e.zone == zone_id]
        if unmeasured:
            raise AssertionFailure(
                f"{zone_id} was reported Unmeasured on a drive that crossed its "
                f"entry camera — the witness rule is rejecting real entries. "
                f"Transitions: {[(e.prev, e.new, e.zone) for e in states]}",
                ctx.obs,
            )

    return Scenario(
        zone_ids=(zone_id,),
        name="edge.jog_start_measured",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_through_jog_start", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=plan.duration_ms / 1000 + 90,
    )
