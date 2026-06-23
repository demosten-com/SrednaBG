# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Vehicle-type limit must reach the UI, not just the engine (ISSUE-002).

Start as 'truck' (settings combo S2) and drive struma-02-south — car limit
140, truck limit 90 — at 100 km/h: over the truck limit, comfortably under
the car limit. Asserts the whole vehicle-aware chain:

1. Zone entry is detected (state machine).
2. The entry announcement speaks the TRUCK limit (90, not 140).
3. The over-limit warning fires — the engine judged 100 km/h against 90.
4. (Android only) the HomeScreen in-zone card renders the truck limit:
   a `uiautomator dump` taken mid-zone must contain the vehicle-resolved
   limit and must NOT mention the car limit. This is the assertion that
   would have caught ISSUE-002 — the badge used to render 140.

Drives via `feed_point` (explicit speed + bearing, like dense_centerline),
resampled at a constant cruise speed along the endpoint-oriented centerline.

The exit-verdict color isn't observable from a UI dump; it's covered by
the JVM unit test `ZoneStatusChipVerdictTest`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time

from ... import device as device_mod
from ... import geo
from ...assertions import expect
from ...events import TtsSpeak, ZoneStateChange
from ...runner import RunContext, Scenario, step_lambda
from ...speech_numbers import words
from ._helpers import load_zone, scenario_setup, scenario_teardown

ZONE_ID = "struma-02-south"  # shortest zone with car (140) != truck (90)
TRUCK_LIMIT = 90
CAR_LIMIT = 140
SPEED_KMH = 100.0  # over truck limit, under car limit
SPEED_MS = SPEED_KMH / 3.6
INTERVAL_S = 1.0
APPROACH_M = 500.0
EXIT_TAIL_M = 300.0


def _build_fixes() -> list[tuple[float, float, float]]:
    """(lat, lng, bearing) per fix at constant 100 km/h, 1 Hz: approach →
    full zone → short exit tail."""
    zone = load_zone(ZONE_ID)
    cl = [(p[0], p[1]) for p in zone["centerline"]]
    # Orient start -> end so we drive the zone's signed direction.
    start = (zone["start"]["lat"], zone["start"]["lng"])
    if geo.haversine_m(*cl[0], *start) > geo.haversine_m(*cl[-1], *start):
        cl = cl[::-1]

    entry_bearing = geo.bearing_deg(cl[0][0], cl[0][1], cl[1][0], cl[1][1])
    exit_bearing = geo.bearing_deg(cl[-2][0], cl[-2][1], cl[-1][0], cl[-1][1])
    approach_start = geo.destination_point(
        cl[0][0], cl[0][1], (entry_bearing + 180) % 360, APPROACH_M)
    exit_end = geo.destination_point(cl[-1][0], cl[-1][1], exit_bearing, EXIT_TAIL_M)

    step_m = SPEED_MS * INTERVAL_S
    pts = list(geo.resample_polyline([approach_start, cl[0]], step_m))
    pts += list(geo.resample_polyline(cl, step_m))[1:]
    pts += list(geo.resample_polyline([cl[-1], exit_end], step_m))[1:]

    fixes: list[tuple[float, float, float]] = []
    for i, p in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else pts[i]
        brg = geo.bearing_deg(p[0], p[1], nxt[0], nxt[1]) if nxt != p else exit_bearing
        fixes.append((p[0], p[1], brg))
    return fixes


def _feed(fixes: list[tuple[float, float, float]]) -> None:
    d = device_mod.current()
    next_slot = time.monotonic()
    for lat, lng, brg in fixes:
        delay = next_slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        d.feed_point(lat, lng, SPEED_MS, brg)
        next_slot += INTERVAL_S


def _dump_ui_xml() -> str:
    """Android-only: uiautomator dump of the current screen as raw XML."""
    from ... import adb
    adb.shell("uiautomator dump /sdcard/window_dump.xml")
    return subprocess.run(
        [shutil.which("adb"), "exec-out", "cat", "/sdcard/window_dump.xml"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout


def _assert_badge_shows_truck_limit() -> None:
    xml = _dump_ui_xml()
    # The in-zone card's accessibility description interpolates the resolved
    # limit ("Speed limit 90." / "Ограничение 90."), and the limit InfoItem
    # renders it as a bare text node. Either is proof the UI got 90.
    if not re.search(rf'\b{TRUCK_LIMIT}\b', xml):
        raise AssertionError(
            f"UI dump has no '{TRUCK_LIMIT}' while in-zone as truck — "
            "the limit badge is not vehicle-aware"
        )
    if re.search(rf'(?:Speed limit|Ограничение)[ :]*{CAR_LIMIT}\b', xml):
        raise AssertionError(
            f"UI dump shows the car limit {CAR_LIMIT} while vehicle type is "
            "truck (ISSUE-002 regression)"
        )


def build() -> Scenario:
    fixes = _build_fixes()
    drive_s = len(fixes) * INTERVAL_S
    mid = len(fixes) // 2  # solidly mid-zone (approach is ~15% of the route)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S2")  # truck, EN voice

    def drive_and_check_badge(ctx: RunContext) -> None:
        # Feed to mid-zone, freeze the feed for the UI check, then finish
        # the drive. The 1-2 s feed pause is far below the 10 s dropout gate.
        _feed(fixes[:mid])
        expect(
            ctx.obs,
            ZoneStateChange,
            where=lambda e: e.new == "InZone" and e.zone == ZONE_ID,
            within_s=15,
            description=f"enter {ZONE_ID} as truck",
        )
        if device_mod.current().platform == "android":
            _assert_badge_shows_truck_limit()
        _feed(fixes[mid:])

    def asserts(ctx: RunContext) -> None:
        expect(
            ctx.obs,
            TtsSpeak,
            # Speeds are spelled into words before TTS (see qa/speech_numbers.py),
            # so match the spelled truck limit (ninety / деветдесет) — still
            # distinct from the car limit (140) — not the bare digits.
            where=lambda e: (words(TRUCK_LIMIT, False) in e.text or words(TRUCK_LIMIT, True) in e.text)
            and ("limit" in e.text.lower() or "Ограничение" in e.text),
            within_s=10,
            description=f"entry announcement speaks the truck limit {TRUCK_LIMIT}",
        )
        expect(
            ctx.obs,
            TtsSpeak,
            where=lambda e: "Warning" in e.text or "Внимание" in e.text,
            within_s=30,
            description=f"over-limit warning at {SPEED_KMH:.0f} km/h vs truck limit {TRUCK_LIMIT}",
        )

    return Scenario(
        name="edge.vehicle_type_limit_badge",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_and_check_badge", drive_and_check_badge),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=drive_s + 120,
    )
