# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""The entry announcement fires when we are *on* the zone, not 300 m later.

Driver-reported (real drive, Android + iPhone side by side, 2026-08-24): the
spoken entry landed roughly 300 m past the entry camera on both platforms, while
Waze had alerted well before it. That lateness was `ENTRY_CONFIRM_DISTANCE_M` —
a zone does not open until the car covers 300 m of centerline arc since the
first matching fix, which is the anti-phantom guard from the A3/Кочериново bug.

The measurement was never wrong: a confirmed traversal is back-dated to the
candidate's first fix. Only the *voice* waited, and the driver has no way to know
that. So the announcement now speaks from the detector's entry **candidate**
(`ZoneDetector.pendingEntryInfo`), while every piece of detection, measurement,
provenance and History logic keeps waiting for confirmation exactly as before.

This scenario drives one zone normally and asserts the whole contract:
  (a) the entry is announced from the candidate, and it is announced *before*
      the traversal opens — otherwise nothing was gained;
  (b) the candidate is announced exactly once, however many fixes it spans;
  (c) the confirmed transition does not repeat the entry line — one entry
      announcement per traversal, not two;
  (d) the candidate is reported `confirmed` and the traversal opens as a
      measured `InZone` — the announcement change must not have touched
      detection.

The drive stops shortly after the traversal opens: everything asserted here is
decided at the entry, and the rest of a 19 km zone would add ten wall-clock
minutes to the suite to re-test what `history.records_traversal` already covers.

Its companion is `edge.provisional_entry_abandoned` (announced, then dropped)
and `edge.parallel_motorway`, which asserts the phantom stays silent.
"""

from __future__ import annotations

import time

from ...assertions import AssertionFailure
from ...drive import pump
from ...events import ProvisionalEntry, TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown

ZONE_ID = "trakiya-01-east"
SPEED_KMH = 120.0
APPROACH_KM = 2.0
# Far enough past the camera that the candidate has confirmed (well over
# ENTRY_CONFIRM_DISTANCE_M) with room for the confirmed transition to be logged.
INTO_ZONE_M = 1500.0
# The BG and EN entry phrases share this stem — see TtsPhrases.swift /
# AudioAlertManager.getEntryMessage. Matching on the stem rather than the whole
# sentence keeps the scenario independent of the spelled-out limit.
ENTRY_STEMS = ("Влизате в зона", "Entering average speed zone")


def _is_entry(text: str) -> bool:
    return any(text.startswith(stem) for stem in ENTRY_STEMS)


def build() -> Scenario:
    full = base_plan(ZONE_ID, speed_kmh=SPEED_KMH, approach_km=APPROACH_KM, exit_km=1)
    cut_ms = int(((APPROACH_KM * 1000 + INTO_ZONE_M) / (SPEED_KMH / 3.6)) * 1000)
    plan = full.slice(0, cut_ms)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")
        ctx.obs.clear()

    def drive(ctx: RunContext) -> None:
        pump(plan)

    def asserts(ctx: RunContext) -> None:
        # Drain the whole run in order: (a) and (c) both need the interleaving
        # of announcements, speech and state changes, which expect/expect_never
        # would discard. Same rolling settle window as edge.parallel_motorway.
        timeline: list[object] = []
        settle = 4.0
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            try:
                ev = ctx.obs.queue.get(timeout=0.2)
            except Exception:
                continue
            if isinstance(ev, (ProvisionalEntry, TtsSpeak, ZoneStateChange)):
                timeline.append(ev)
                deadline = time.monotonic() + settle

        provisional = [e for e in timeline if isinstance(e, ProvisionalEntry)]
        announced = [e for e in provisional if e.outcome == "announced" and e.zone == ZONE_ID]
        entries = [
            e for e in timeline
            if isinstance(e, ZoneStateChange) and e.new == "InZone" and e.zone == ZONE_ID
        ]
        entry_lines = [e for e in timeline if isinstance(e, TtsSpeak) and _is_entry(e.text)]

        # (a) Announced, and announced early. Without the ordering clause this
        # would still pass if the announcement had simply moved to the confirmed
        # transition under a new log line — the exact thing being fixed.
        if not announced:
            raise AssertionFailure(
                f"driving {ZONE_ID} never announced an entry from the detector "
                f"candidate. Timeline: {[(type(e).__name__, getattr(e, 'zone', None)) for e in timeline]}",
                ctx.obs,
            )
        if not entries:
            raise AssertionFailure(
                f"driving {ZONE_ID} never opened a measured traversal — the "
                f"announcement change must not have altered detection",
                ctx.obs,
            )
        if timeline.index(announced[0]) >= timeline.index(entries[0]):
            raise AssertionFailure(
                "the entry was announced no earlier than the traversal opened, so "
                "nothing was gained over waiting for ENTRY_CONFIRM_DISTANCE_M",
                ctx.obs,
            )

        # (b) One announcement, not one per fix of the confirmation window.
        if len(announced) != 1:
            raise AssertionFailure(
                f"expected exactly one provisional announcement for {ZONE_ID}, got "
                f"{len(announced)} — every fix of the confirmation window re-reports "
                f"the same candidate and must not re-announce it",
                ctx.obs,
            )

        # (c) The confirmed transition must not say it again.
        if len(entry_lines) != 1:
            raise AssertionFailure(
                f"expected exactly one spoken entry line for the traversal, got "
                f"{len(entry_lines)}: {[e.text for e in entry_lines]}. A second one "
                f"means the confirmed Outside -> InZone branch repeated what the "
                f"candidate already said.",
                ctx.obs,
            )

        # (d) This drive took the happy path, so the abandoned branch is not what
        # (a)-(c) were measuring.
        if not any(e.outcome == "confirmed" and e.zone == ZONE_ID for e in provisional):
            raise AssertionFailure(
                f"the announced candidate for {ZONE_ID} was never reported confirmed: "
                f"{[(e.zone, e.outcome) for e in provisional]}",
                ctx.obs,
            )

    return Scenario(
        name="edge.provisional_entry",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive", drive),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=int(plan.duration_ms / 1000) + 120,
    )
