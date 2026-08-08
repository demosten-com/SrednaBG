# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/parsers.py — the log-line → typed-Event regex set.

A regex regression here used to be caught only by the smoke suite's integration
tripwire (which needs a real device). These run headlessly in CI over sample
lines for each event shape.
"""

import math
import unittest

import _paths  # noqa: F401

from qa import parsers
from qa.events import (
    AutoStopped,
    DisplaySpeed,
    LocationSourceSelected,
    LocationUpdate,
    SettingChanged,
    SyncResult,
    TtsLeadIn,
    TtsSpeak,
    UnparsedLog,
    ZoneStateChange,
    ZonesDropped,
    ZonesRepaired,
    ZonesLoaded,
)


def line(tag: str, msg: str) -> str:
    """A realistic adb logcat threadtime line for (tag, msg)."""
    return f"04-16 14:23:45.123 12345 12345 D {tag}: {msg}"


class ThreadtimeLineTests(unittest.TestCase):
    def test_non_matching_line_returns_none(self):
        self.assertIsNone(parsers.parse_threadtime_line("not a logcat line"))

    def test_unknown_tag_returns_none(self):
        self.assertIsNone(parsers.parse_threadtime_line(line("SomeOther.Tag", "hi")))


class LocTests(unittest.TestCase):
    def test_location_update(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc",
            "onLocation: lat=42.5 lng=23.8 speed=30.0 accuracy=5.0 provider=gps mock=true"))
        self.assertIsInstance(ev, LocationUpdate)
        self.assertAlmostEqual(ev.lat, 42.5)
        self.assertAlmostEqual(ev.speed_mps, 30.0)
        self.assertEqual(ev.provider, "gps")
        self.assertTrue(ev.is_mock)

    def test_display_speed(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc",
            "displaySpeed: kmh=108.0 inferredKmh=107.5 reportedKmh=108.2 "
            "rawMs=30.0 accMs=5.0 fixAgeMs=100 fresh=true"))
        self.assertIsInstance(ev, DisplaySpeed)
        self.assertAlmostEqual(ev.kmh, 108.0)
        self.assertEqual(ev.fix_age_ms, 100)
        self.assertTrue(ev.fresh_fix)

    def test_display_speed_nan_accuracy(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc",
            "displaySpeed: kmh=0.0 inferredKmh=0.0 reportedKmh=0.0 "
            "rawMs=0.0 accMs=NaN fixAgeMs=0 fresh=false"))
        self.assertIsInstance(ev, DisplaySpeed)

    def test_zones_loaded(self):
        ev = parsers.parse_threadtime_line(line("SrednaBG.Loc", "zones changed (n=74)"))
        self.assertIsInstance(ev, ZonesLoaded)
        self.assertEqual(ev.count, 74)

    def test_zones_dropped(self):
        """The unusable-zone tripwire — body is identical on both platforms."""
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc",
            "zones dropped (n=2) ids=[i8-02-east, i8-02-west] "
            "origin=server 2026-08-03T06:11:22Z"))
        self.assertIsInstance(ev, ZonesDropped)
        self.assertEqual(ev.count, 2)
        self.assertEqual(ev.ids, ["i8-02-east", "i8-02-west"])
        self.assertEqual(ev.origin, "server 2026-08-03T06:11:22Z")

    def test_zones_repaired(self):
        """Distinct from dropped: fatal on shipped 1.x, invisible on current."""
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc",
            "zones repaired (n=2) ids=[i8-01-north, i8-01-south] "
            "origin=server 2026-08-03T06:11:22Z"))
        self.assertIsInstance(ev, ZonesRepaired)
        self.assertEqual(ev.count, 2)
        self.assertEqual(ev.ids, ["i8-01-north", "i8-01-south"])

    def test_repaired_and_dropped_are_not_confused(self):
        rep = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc", "zones repaired (n=1) ids=[a] origin=server x"))
        drop = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc", "zones dropped (n=1) ids=[b] origin=server x"))
        self.assertNotIsInstance(rep, ZonesDropped)
        self.assertNotIsInstance(drop, ZonesRepaired)

    def test_zones_loaded_is_not_confused_with_dropped(self):
        ev = parsers.parse_threadtime_line(line("SrednaBG.Loc", "zones changed (n=74)"))
        self.assertNotIsInstance(ev, ZonesDropped)

    def test_auto_stop(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.Loc", "auto-stop: idle for 10800s (threshold=10800s)"))
        self.assertIsInstance(ev, AutoStopped)
        self.assertEqual(ev.elapsed_s, 10800)
        self.assertEqual(ev.threshold_s, 10800)

    def test_unparsed_known_tag(self):
        ev = parsers.parse_threadtime_line(line("SrednaBG.Loc", "some unrecognized message"))
        self.assertIsInstance(ev, UnparsedLog)


class LocSrcTests(unittest.TestCase):
    def test_fused(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.LocSrc", "Selecting FusedLocationSource"))
        self.assertIsInstance(ev, LocationSourceSelected)
        self.assertEqual(ev.source, "fused")

    def test_system(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.LocSrc", "Selecting SystemLocationSource (GPS only)"))
        self.assertIsInstance(ev, LocationSourceSelected)
        self.assertEqual(ev.source, "system")


class TtsTests(unittest.TestCase):
    def test_zone_state_change(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.TTS",
            "onZoneStateChanged prev=Outside new=InZone zone=trakiya-01-east speed=108.0"))
        self.assertIsInstance(ev, ZoneStateChange)
        self.assertEqual(ev.prev, "Outside")
        self.assertEqual(ev.new, "InZone")
        self.assertEqual(ev.zone, "trakiya-01-east")
        self.assertAlmostEqual(ev.speed_kmh, 108.0)

    def test_zone_state_change_outside_dash_zone(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.TTS",
            "onZoneStateChanged prev=Exiting new=Outside zone=- speed=NaN"))
        self.assertIsInstance(ev, ZoneStateChange)
        self.assertEqual(ev.zone, "-")
        # "NaN" parses as a float (math.nan), not None — None is only for a
        # genuinely non-floatable token.
        self.assertTrue(math.isnan(ev.speed_kmh))

    def test_zone_state_change_non_float_speed_is_none(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.TTS",
            "onZoneStateChanged prev=Outside new=InZone zone=z speed=--"))
        self.assertIsInstance(ev, ZoneStateChange)
        self.assertIsNone(ev.speed_kmh)

    def test_speak(self):
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.TTS", 'speak: "Entering average speed zone. Speed limit one hundred forty."'))
        self.assertIsInstance(ev, TtsSpeak)
        self.assertIn("Entering average speed zone", ev.text)

    def test_speak_with_trailing_quote_in_text(self):
        # SPEAK_RE's greedy .* keeps an embedded trailing quote intact (the
        # nitpick the standalone tools' rstrip('"') used to over-strip).
        ev = parsers.parse_threadtime_line(line("SrednaBG.TTS", 'speak: "hello \\"q\\""'))
        self.assertIsInstance(ev, TtsSpeak)
        self.assertTrue(ev.text.endswith('"'))

    def test_speak_cold_start_lead_in(self):
        # The unquoted diagnostic must parse as TtsLeadIn, never as TtsSpeak —
        # the edge.tts_cold_start_leadin scenario orders on the distinction.
        ev = parsers.parse_threadtime_line(line(
            "SrednaBG.TTS", "speak: cold start, 400ms lead-in"))
        self.assertIsInstance(ev, TtsLeadIn)
        self.assertEqual(ev.lead_in_ms, 400)


class SyncTests(unittest.TestCase):
    def test_sync_updated(self):
        ev = parsers.parse_threadtime_line(line(
            "DebugSync", "com.demosten.srednabg.debug.SYNC_ZONES -> SyncResult.Updated"))
        self.assertIsInstance(ev, SyncResult)
        self.assertEqual(ev.action, "SYNC_ZONES")
        self.assertEqual(ev.outcome, "Updated")

    def test_sync_map_skipped(self):
        # The real map-disabled log shape (a space before the parenthetical, so
        # SYNC_RE captures the outcome but not the detail — map_disabled.py only
        # asserts the outcome).
        ev = parsers.parse_threadtime_line(line(
            "DebugSync", "com.demosten.srednabg.debug.SYNC_MAP -> Skipped (feature disabled)"))
        self.assertIsInstance(ev, SyncResult)
        self.assertEqual(ev.action, "SYNC_MAP")
        self.assertEqual(ev.outcome, "Skipped")

    def test_sync_failed_with_detail(self):
        # No space before "(" → the optional detail group is captured.
        ev = parsers.parse_threadtime_line(line(
            "DebugSync", "com.demosten.srednabg.debug.SYNC_ZONES -> SyncResult.Failed(offline)"))
        self.assertIsInstance(ev, SyncResult)
        self.assertEqual(ev.outcome, "Failed")
        self.assertEqual(ev.detail, "offline")


class SettingTests(unittest.TestCase):
    def test_setting(self):
        ev = parsers.parse_threadtime_line(line("DebugSettings", "set vehicle_type=truck"))
        self.assertIsInstance(ev, SettingChanged)
        self.assertEqual(ev.key, "vehicle_type")
        self.assertEqual(ev.value, "truck")


class ParseMessageDirectTests(unittest.TestCase):
    def test_parse_message_unknown_tag_returns_none(self):
        self.assertIsNone(parsers.parse_message("nope", "msg", "raw"))


if __name__ == "__main__":
    unittest.main()
