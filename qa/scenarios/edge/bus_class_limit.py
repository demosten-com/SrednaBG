# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""The BE/C1/D licence class resolves its own limit all the way to the UI.

`speed_limits.bus` is BG TOLL's limit for the whole `BE,C1,C1E,D,D1,D1E,DE`
class — bus, minibus, truck 3.5-7.5 t, and anything towing a trailer — which is
why the Settings row is labelled for the class rather than for buses. This is
the sibling of `vehicle_type_limit_badge.py` (truck) for that class, and the
only automated coverage of the 100 km/h tier: the truck scenario exercises 90,
so the spelled-number path through the hundreds ("one hundred" / "сто") is
covered here and nowhere else.

The failure it guards is a vehicle type falling through to the car limit — the
`fromSetting` default is CAR, and an unrecognized token is indistinguishable
from "car" at the UI.

Drives struma-02-south — car 140, bus 100 — as 'bus' (combo S5, voice on) at
120 km/h: over the class limit, comfortably under the car limit. Asserts:

1. Zone entry is detected.
2. The entry announcement speaks the CLASS limit (100, not 140).
3. The over-limit warning fires — the engine judged 120 km/h against 100.
4. (Android only) the in-zone card renders 100 and not the car limit.
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

ZONE_ID = "struma-02-south"  # short zone with car (140) != bus (100)
CLASS_LIMIT = 100  # speed_limits.bus — the BE/C1/D class
CAR_LIMIT = 140
SPEED_KMH = 120.0  # over the class limit, under the car limit
SPEED_MS = SPEED_KMH / 3.6
INTERVAL_S = 1.0
APPROACH_M = 500.0
EXIT_TAIL_M = 300.0


def _build_fixes() -> list[tuple[float, float, float]]:
    """(lat, lng, bearing) per fix at a constant cruise, 1 Hz: approach →
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


def _assert_badge_shows_class_limit() -> None:
    xml = _dump_ui_xml()
    if not re.search(rf'\b{CLASS_LIMIT}\b', xml):
        raise AssertionError(
            f"UI dump has no '{CLASS_LIMIT}' while in-zone as bus — "
            "the limit badge did not resolve the BE/C1/D class limit"
        )
    if re.search(rf'(?:Speed limit|Ограничение)[ :]*{CAR_LIMIT}\b', xml):
        raise AssertionError(
            f"UI dump shows the car limit {CAR_LIMIT} while vehicle type is "
            "bus — the vehicle type fell through to the car limit"
        )


def build() -> Scenario:
    fixes = _build_fixes()
    drive_s = len(fixes) * INTERVAL_S
    mid = len(fixes) // 2  # solidly mid-zone (approach is ~15% of the route)

    def setup(ctx: RunContext) -> None:
        scenario_setup(ctx, settings_id="S5")  # bus class, EN voice

    def drive_and_check_badge(ctx: RunContext) -> None:
        _feed(fixes[:mid])
        expect(
            ctx.obs,
            ZoneStateChange,
            where=lambda e: e.new == "InZone" and e.zone == ZONE_ID,
            within_s=15,
            description=f"enter {ZONE_ID} as bus",
        )
        if device_mod.current().platform == "android":
            _assert_badge_shows_class_limit()
        _feed(fixes[mid:])

    def asserts(ctx: RunContext) -> None:
        expect(
            ctx.obs,
            TtsSpeak,
            # Speeds are spelled into words before TTS (see qa/speech_numbers.py).
            where=lambda e: (
                words(CLASS_LIMIT, False) in e.text or words(CLASS_LIMIT, True) in e.text
            )
            and ("limit" in e.text.lower() or "Ограничение" in e.text),
            within_s=10,
            description=f"entry announcement speaks the class limit {CLASS_LIMIT}",
        )
        expect(
            ctx.obs,
            TtsSpeak,
            where=lambda e: "Warning" in e.text or "Внимание" in e.text,
            within_s=30,
            description=(
                f"over-limit warning at {SPEED_KMH:.0f} km/h vs class limit {CLASS_LIMIT}"
            ),
        )

    return Scenario(
        name="edge.bus_class_limit",
        steps=[
            step_lambda("setup", setup),
            step_lambda("drive_and_check_badge", drive_and_check_badge),
            step_lambda("asserts", asserts),
        ],
        teardown=scenario_teardown,
        timeout_s=drive_s + 120,
    )
