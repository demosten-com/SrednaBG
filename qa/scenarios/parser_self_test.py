# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Parser self-test — the tripwire that catches app-log-shape drift.

Runs LAST in the smoke suite. By then the suite has applied a settings combo,
started tracking, driven a zone (with TTS announcements) and synced zones, so
every load-bearing event type must have been parsed at least once. The
observer's `type_counts` accumulate across the whole suite (`clear()` keeps
them), which is what this scenario judges.

If an app log line changes shape — e.g. `speak:` renamed, `onZoneStateChanged`
reordered — its regex in `qa/parsers.py` stops matching, the event type goes
missing here, and this scenario fails naming the dead regex. Lines under known
tags that matched no regex at all are attached as `UnparsedLog` samples; the
renamed line is usually among them.

Note: this scenario is only meaningful after the full smoke suite — running it
alone (e.g. via `--filter parsers`) fails vacuously because nothing was driven.
"""

from __future__ import annotations

from .. import device as device_mod
from ..assertions import AssertionFailure
from ..runner import RunContext, Scenario, step_lambda

# Event type → the regex in qa/parsers.py that produces it. Every entry must
# be observed at least once during the smoke suite, on both platforms.
REQUIRED_EVENT_SOURCES = {
    "LocationUpdate": "LOC_RE (SrednaBG.Loc 'onLocation: …')",
    "ZoneStateChange": "STATE_RE (SrednaBG.TTS 'onZoneStateChanged …')",
    "TtsSpeak": "SPEAK_RE (SrednaBG.TTS 'speak: \"…\"')",
    "SettingChanged": "SETTING_RE (DebugSettings 'set <key>=<value>')",
    "SyncResult": "SYNC_RE (DebugSync 'SYNC_X -> SyncResult.Y')",
}
# Android-only requirements:
#  - LocationSourceSelected: iOS has a single CLLocationManager path and emits
#    no SrednaBG.LocSrc line (see _location_source_prefix in srednabg_qa.py).
#  - DisplaySpeed: the `displaySpeed:` diagnostic exists only in the Android
#    LocationTrackingService; the iOS app has no equivalent log line.
#  - ZonesLoaded: iOS's ZoneTrackingService.updateZones logs `zones changed`
#    only when the catalog CONTENT changes — the initial load happens at app
#    launch (before the suite's log stream attaches) and an UpToDate sync
#    re-emits nothing, so a steady-state suite run legitimately never sees it.
#    Android re-emits on every tracking start, so it's reliable there.
ANDROID_ONLY_EVENT_SOURCES = {
    "LocationSourceSelected": "LOC_SRC_RE (SrednaBG.LocSrc 'Selecting …LocationSource')",
    "DisplaySpeed": "DISPLAY_SPEED_RE (SrednaBG.Loc 'displaySpeed: …')",
    "ZonesLoaded": "ZONES_RE (SrednaBG.Loc 'zones changed (n=…)')",
}


def build() -> Scenario:
    def go(ctx: RunContext) -> None:
        required = dict(REQUIRED_EVENT_SOURCES)
        if device_mod.current().platform == "android":
            required.update(ANDROID_ONLY_EVENT_SOURCES)

        counts = ctx.obs.type_counts
        missing = {name: src for name, src in required.items()
                   if counts.get(name, 0) == 0}
        if not missing:
            return

        lines = ["parser self-test: load-bearing event types were never parsed "
                 "this suite — an app log line likely changed shape. Fix the "
                 "regex in qa/parsers.py:"]
        for name, src in sorted(missing.items()):
            lines.append(f"  - {name}: expected from {src}")
        if ctx.obs.unparsed_samples:
            lines.append("unparsed lines under known tags (the renamed line is "
                         "usually one of these):")
            for raw in ctx.obs.unparsed_samples[:8]:
                lines.append(f"  | {raw}")
        else:
            lines.append("(no unparsed lines were seen — if the suite was "
                         "filtered or aborted early, the events may simply "
                         "never have been emitted; run the full smoke suite)")
        raise AssertionFailure("\n".join(lines), ctx.obs)

    return Scenario(
        name="parsers.self_test",
        steps=[step_lambda("check_event_type_coverage", go)],
        timeout_s=30,
    )
