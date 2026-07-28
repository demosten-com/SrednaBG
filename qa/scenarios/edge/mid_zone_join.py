# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Mid-zone join: start feeding fixes from deep inside a zone, never crossing
its entry camera.

Regression for the third zone state. If the app did not see the driver cross an
entry camera it cannot produce trustworthy data and must not try to help — the
reason it missed the entry (app restart, permission granted mid-drive, tunnel,
process death, genuinely joining the road late) is deliberately irrelevant.

Before that rule, a mid-zone join opened a *full* traversal whose average
covered only the remainder: a number matching nothing BG TOLL computes, yet
rendered in the same chip, spoken in the same phrase and stored in the same
History row as a real traversal. That is the shape of the junk 24 km/h record
from the real drive on 2026-07-26.

Asserts the whole contract of `ZoneState.Unmeasured` end-to-end:
  (a) the state is reached and named `Unmeasured` in the log,
  (b) no measured traversal ever opens (`InZone`),
  (c) nothing is spoken — no entry, exit, over-limit or periodic line,
  (d) the History row count is unchanged across the drive.

(d) is a before/after comparison rather than `count == 0`: the History DB
accumulates across a suite run, so an absolute count would be asserting something
about the *other* scenarios, not this one.

See ZoneDetector.START_WITNESS_ARC_M (Kotlin) / startWitnessArcM (Swift).
"""

from __future__ import annotations

import time

from ...assertions import AssertionFailure, expect
from ...device import current as current_device
from ...drive import pump
from ...events import HistoryDump, TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown

ZONE_ID = "trakiya-01-east"
# Drop the generated approach plus the first stretch of the zone, so the very
# first fix the app ever sees is already well past the entry camera — far past
# START_WITNESS_ARC_M, and past ENTRY_CONFIRM_DISTANCE_M too, so the candidate
# still confirms (this must reach Unmeasured, not merely stay Outside).
SKIP_S = 120.0


def build() -> Scenario:
    full = base_plan(ZONE_ID, speed_kmh=120).compressed(2.0)
    plan = full.slice(int(SKIP_S * 1000), full.duration_ms)
    # Baseline History count, captured before the drive — see (d) above.
    baseline: list[int] = []

    def _dump_count(ctx: RunContext, *, settle_s: float = 0.0) -> int:
        if settle_s:
            time.sleep(settle_s)
        ctx.obs.clear()
        current_device().dump_history()
        ev = expect(
            ctx.obs,
            HistoryDump,
            within_s=10,
            description="DUMP_HISTORY responds",
        )
        return ev.count

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")
        baseline.append(_dump_count(ctx))
        ctx.obs.clear()

    def drive(ctx: RunContext) -> None:
        pump(plan)

    def asserts(ctx: RunContext) -> None:
        # Drain the whole run into a list rather than using expect/expect_never
        # in sequence: those are lossy (each discards what it skipped past), and
        # (a)–(c) below all need to see the same complete record. Same rolling
        # settle window as edge.parallel_motorway.
        states: list[ZoneStateChange] = []
        spoken: list[TtsSpeak] = []
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
            elif isinstance(ev, TtsSpeak):
                spoken.append(ev)
                deadline = time.monotonic() + settle

        # (a) The state must actually be reached — otherwise (b) and (c) would
        # pass vacuously on a drive that simply never matched a zone at all.
        if not any(e.new == "Unmeasured" and e.zone == ZONE_ID for e in states):
            raise AssertionFailure(
                f"joining {ZONE_ID} mid-way never produced Unmeasured. "
                f"Transitions: {[(e.prev, e.new, e.zone) for e in states]}",
                ctx.obs,
            )

        # (b) The original bug: a partial traversal presented as a complete one.
        entries = [e for e in states if e.new == "InZone"]
        if entries:
            raise AssertionFailure(
                f"joining {ZONE_ID} mid-way opened a measured traversal of "
                f"{[e.zone for e in entries]} — we never saw the entry camera, so "
                f"its average would match nothing BG TOLL computes",
                ctx.obs,
            )

        # (c) Silence. Any line here means the announcement layer treated
        # Unmeasured as a real entry/exit.
        if spoken:
            raise AssertionFailure(
                f"Unmeasured must be silent, but the app spoke: "
                f"{[s.text for s in spoken]}",
                ctx.obs,
            )

    def assert_no_new_history(ctx: RunContext) -> None:
        # (d) No new History row — the visible half of "Exiting only ever follows
        # InZone": an Unmeasured zone drops straight to Outside, so the recorder
        # is never handed a traversal to finalize. Runs after the assertions
        # above because the dump clears the observer. The 3 s settle gives an
        # (absent) async record write time to land.
        after = _dump_count(ctx, settle_s=3.0)
        before = baseline[0] if baseline else 0
        if after != before:
            raise AssertionFailure(
                f"a mid-zone join wrote {after - before} History record(s) — an "
                f"unwitnessed entry has no traversal to record "
                f"(count {before} -> {after})",
                ctx.obs,
            )

    return Scenario(
        name="edge.mid_zone_join",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_from_mid_zone", drive),
            step_lambda("asserts", asserts),
            step_lambda("assert_no_new_history", assert_no_new_history),
        ],
        teardown=scenario_teardown,
        timeout_s=plan.duration_ms / 1000 + 90,
    )
