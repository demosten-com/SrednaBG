# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Cold-start TTS lead-in: the first announcement of an audio-focus session
must be preceded by the silent route-warmup utterance.

Regression guard for "voice messages cut at the start over Android Auto /
Bluetooth alongside Waze": after a fresh audio-focus grant the car / BT audio
route takes a few hundred ms to duck the other app and open our stream, and
speech synthesized in that window is swallowed. The fix in
`AudioAlertManager.speak()` prepends `ROUTE_WARMUP_SILENCE_MS` of silence
(`playSilentUtterance`) whenever the utterance queue is cold
(`pendingUtterances == 0`), and logs `speak: cold start, …ms lead-in`.

Scope note: like `stop_silences_tts`, the harness observes the *decision* via
log lines, not audio playback — it cannot hear whether words were clipped.
What it guards end-to-end is that a cold-start announcement is always entered
into the queue BEHIND a silent lead-in (ordered `TtsLeadIn` → `TtsSpeak`),
i.e. the warmup path can't silently regress out of `speak()`.
"""

from __future__ import annotations

from ...assertions import expect, expect_in_order
from ...drive import pump
from ...events import TtsLeadIn, TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ._helpers import base_plan, scenario_setup, scenario_teardown


def build() -> Scenario:
    # Within the limit — the only announcement is the Outside→InZone entry,
    # which is by construction the cold start of a focus session.
    plan = base_plan("trakiya-01-east", speed_kmh=120).compressed(2.0)
    entry_plan = plan.slice(0, int(plan.duration_ms * 0.4))

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S1")  # voice on, car

    def drive(ctx: RunContext) -> None:
        pump(entry_plan)

    def assert_lead_in_before_speech(ctx: RunContext) -> None:
        expect(
            ctx.obs, ZoneStateChange,
            where=lambda e: e.new == "InZone",
            within_s=entry_plan.duration_ms / 1000 + 30,
            description="enter zone",
        )
        # The entry announcement must arrive queued behind the silent warmup:
        # lead-in first, words second. A cold-start speak without the lead-in
        # line fails the first expectation.
        expect_in_order(
            ctx.obs,
            [
                (TtsLeadIn, None),
                (TtsSpeak, None),
            ],
            within_s=30,
            description="cold-start entry announcement is preceded by lead-in silence",
        )

    return Scenario(
        name="edge.tts_cold_start_leadin",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_into_zone", drive),
            step_lambda("assert_lead_in_before_speech", assert_lead_in_before_speech),
        ],
        teardown=scenario_teardown,
        timeout_s=entry_plan.duration_ms / 1000 + 90,
    )
