# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Stop silences TTS: drive into a zone (over the limit so announcements
fire), then Stop tracking and assert no further announcement is produced.

Regression guard for "TTS keeps talking after the user stops tracking". The
fix (a) cuts the current utterance off immediately via
`AVSpeechTTSEngine.stop()`, and (b) suppresses the announcement pipeline so an
in-flight detached `handle` task can't kick off a fresh utterance after Stop.

Scope note: the harness observes announcement *decisions* via the `speak:`
log line, NOT audio playback, so it cannot measure the audio cut-off latency
directly — that immediacy is covered by the `AVSpeechTTSEngine` /
`AudioAlertManager` Swift unit tests. What this scenario guards end-to-end is
the system-level invariant that **no new announcement is emitted once tracking
has stopped**.
"""

from __future__ import annotations

from ... import settings as settings_mod
from ...assertions import expect, expect_never
from ...drive import pump
from ...events import TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    # 150 km/h on trakiya-01-east (car limit 140) → over-limit, so the voice
    # pipeline is actively producing announcements while we're in the zone.
    plan = base_plan("trakiya-01-east", speed_kmh=150).compressed(2.0)
    # Only drive into the first stretch of the zone — enough to enter and
    # speak, then we Stop while still mid-zone (announcements still live).
    entry_plan = plan.slice(0, int(plan.duration_ms * 0.55))

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")  # voice on, periodic on, car

    def drive(ctx: RunContext) -> None:
        pump(entry_plan)

    def assert_spoke(ctx: RunContext) -> None:
        expect(
            ctx.obs, ZoneStateChange,
            where=lambda e: e.new == "InZone",
            within_s=entry_plan.duration_ms / 1000 + 30,
            description="enter zone",
        )
        # Confirm the pipeline actually spoke during the zone — otherwise the
        # silence assertion below would pass vacuously.
        expect(
            ctx.obs, TtsSpeak,
            within_s=30,
            description="an announcement fires while in the zone",
        )

    def stop_and_verify_silence(ctx: RunContext) -> None:
        ctx.obs.clear()
        settings_mod.stop_tracking()
        # After Stop, the announcement pipeline must go quiet — no `speak:`
        # decision may be emitted by an in-flight handler.
        expect_never(
            ctx.obs, TtsSpeak,
            within_s=8,
            description="no TTS announcement after Stop",
        )

    return Scenario(
        name="edge.stop_silences_tts",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_into_zone", drive),
            step_lambda("assert_spoke", assert_spoke),
            step_lambda("stop_and_verify_silence", stop_and_verify_silence),
        ],
        teardown=scenario_teardown,
        timeout_s=entry_plan.duration_ms / 1000 + 90,
    )
