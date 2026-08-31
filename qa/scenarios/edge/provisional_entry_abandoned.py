# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""The accepted cost of announcing early: an announcement with no traversal.

The entry announcement now fires when the detector opens an entry *candidate*,
`ENTRY_CONFIRM_DISTANCE_M` (300 m of centerline travel) before that candidate
can graduate into a traversal — see `edge.provisional_entry` for why. A car that
opens a candidate and then leaves the road before covering those 300 m has
therefore heard "entering average-speed zone" for a traversal that never
happens.

That trade was made deliberately and knowingly, so this scenario pins its exact
shape rather than pretending it cannot occur:

  (a) the entry is announced from the candidate;
  (b) the abandonment is *reported* on the QA channel — the counter that tells
      us how often this bites across `qa/validate-zones.sh`'s 76 zones;
  (c) nothing further is spoken. In particular there is no retraction: a
      correction the driver did not ask for is more confusing than silence, and
      no exit line may be invented for a traversal that never opened;
  (d) no traversal opens (`InZone`) and no History row is written — the
      announcement is voice-only and touches none of the measurement path.

(d) is what keeps this an announcement-level trade rather than a data one.
"""

from __future__ import annotations

import time

from ... import geo
from ...assertions import AssertionFailure, expect
from ...device import current as current_device
from ...drive import pump
from ...events import HistoryDump, ProvisionalEntry, TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, load_zone, scenario_setup, scenario_teardown

ZONE_ID = "trakiya-01-east"
APPROACH_KM = 2.0
SPEED_KMH = 120.0
# Stop feeding this far past the entry camera: comfortably past the point where
# the candidate opens (the on-road band reaches ~100-150 m *before* the camera,
# because a pre-camera fix's projection clamps to the polyline start), and
# comfortably short of the 300 m the candidate needs to graduate.
INTO_ZONE_M = 150.0
# How far off the road the departure fix sits. Beyond OFF_ROAD_HARD_M (1000 m)
# so no grace or band tolerance can keep the candidate alive.
DEPART_M = 3000.0
# The verdict is deliberately not passed the moment the candidate disappears: a
# single fix outside the band drops it and the next fix re-opens one for the
# same zone (observed on a real approach), so the app waits out the detector's
# own ENTRY_CONFIRM_TIMEOUT_MS before calling it abandoned. Drive away for
# longer than that, plus a margin, or this scenario asserts on a verdict that
# has not been reached yet.
DEPART_S = 40.0
ENTRY_STEMS = ("Влизате в зона", "Entering average speed zone")


def _is_entry(text: str) -> bool:
    return any(text.startswith(stem) for stem in ENTRY_STEMS)


def build() -> Scenario:
    full = base_plan(ZONE_ID, speed_kmh=SPEED_KMH, approach_km=APPROACH_KM, exit_km=1)
    # Cut the drive INTO_ZONE_M past the camera. The generated plan runs at a
    # constant speed from the start of the approach, so distance maps linearly
    # onto its timeline.
    cut_ms = int(((APPROACH_KM * 1000 + INTO_ZONE_M) / (SPEED_KMH / 3.6)) * 1000)
    plan = full.slice(0, cut_ms)
    baseline: list[int] = []

    def _dump_count(ctx: RunContext, *, settle_s: float = 0.0) -> int:
        if settle_s:
            time.sleep(settle_s)
        ctx.obs.clear()
        current_device().dump_history()
        ev = expect(ctx.obs, HistoryDump, within_s=10, description="DUMP_HISTORY responds")
        return ev.count

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")
        baseline.append(_dump_count(ctx))
        ctx.obs.clear()

    def drive(ctx: RunContext) -> None:
        pump(plan)

    def depart(ctx: RunContext) -> None:
        # Leave the corridor entirely. A few fixes so the detector sees a
        # sustained departure rather than one droppable blip.
        zone = load_zone(ZONE_ID)
        cl = zone["centerline"]
        heading = geo.bearing_deg(cl[0][0], cl[0][1], cl[-1][0], cl[-1][1])
        away = (heading + 90) % 360
        d = current_device()
        for i in range(int(DEPART_S)):
            lat, lng = geo.destination_point(
                cl[0][0], cl[0][1], away, DEPART_M + i * 30.0
            )
            d.feed_point(lat, lng, SPEED_KMH / 3.6, away)
            time.sleep(1.0)

    def asserts(ctx: RunContext) -> None:
        provisional: list[ProvisionalEntry] = []
        spoken: list[TtsSpeak] = []
        states: list[ZoneStateChange] = []
        settle = 4.0
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            try:
                ev = ctx.obs.queue.get(timeout=0.2)
            except Exception:
                continue
            if isinstance(ev, ProvisionalEntry):
                provisional.append(ev)
                deadline = time.monotonic() + settle
            elif isinstance(ev, TtsSpeak):
                spoken.append(ev)
                deadline = time.monotonic() + settle
            elif isinstance(ev, ZoneStateChange):
                states.append(ev)
                deadline = time.monotonic() + settle

        # (a) Anti-vacuous: without an announcement there is no trade to pin, and
        # (b)-(d) would all pass on a drive that simply never approached a zone.
        if not any(e.outcome == "announced" and e.zone == ZONE_ID for e in provisional):
            raise AssertionFailure(
                f"the short drive into {ZONE_ID} never announced an entry, so this "
                f"scenario is not exercising the abandoned-candidate path. "
                f"Provisional: {[(e.zone, e.outcome) for e in provisional]}",
                ctx.obs,
            )

        # (b) …and the abandonment must be visible to the harness.
        if not any(e.outcome == "abandoned" and e.zone == ZONE_ID for e in provisional):
            raise AssertionFailure(
                f"leaving the road before ENTRY_CONFIRM_DISTANCE_M did not report an "
                f"abandoned candidate for {ZONE_ID}: "
                f"{[(e.zone, e.outcome) for e in provisional]}",
                ctx.obs,
            )

        # (c) Exactly the one entry line, and nothing else — no retraction, no
        # invented exit-with-average for a traversal that never opened.
        non_entry = [s for s in spoken if not _is_entry(s.text)]
        if non_entry:
            raise AssertionFailure(
                f"an abandoned candidate must say nothing beyond the entry it already "
                f"spoke, but the app also said: {[s.text for s in non_entry]}",
                ctx.obs,
            )

        # (d) The measurement path is untouched.
        opened = [e for e in states if e.new in ("InZone", "Unmeasured")]
        if opened:
            raise AssertionFailure(
                f"the candidate must never have graduated — it covered less than "
                f"ENTRY_CONFIRM_DISTANCE_M — but the detector reported "
                f"{[(e.new, e.zone) for e in opened]}",
                ctx.obs,
            )

    def assert_no_history(ctx: RunContext) -> None:
        after = _dump_count(ctx, settle_s=3.0)
        before = baseline[0] if baseline else 0
        if after != before:
            raise AssertionFailure(
                f"an abandoned candidate wrote {after - before} History record(s) — "
                f"the early announcement is voice-only and must not reach the "
                f"recorder (count {before} -> {after})",
                ctx.obs,
            )

    return Scenario(
        name="edge.provisional_entry_abandoned",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_partway_in", drive),
            step_lambda("depart", depart),
            step_lambda("asserts", asserts),
            step_lambda("assert_no_history", assert_no_history),
        ],
        teardown=scenario_teardown,
        timeout_s=int(plan.duration_ms / 1000) + int(DEPART_S) + 120,
    )
